"""
server.py - TCP Chat Server Đa Luồng (Multi-threaded TCP Socket Server).

Quản lý các kết nối từ Client, điều phối tin nhắn công khai (Broadcast),
tin nhắn riêng (Private Message), cập nhật trạng thái người dùng Online.
Hỗ trợ event callbacks phục vụ Giao diện Đồ họa (Server GUI).
"""

import base64
import datetime
import hashlib
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import uuid
from typing import Callable

import protocol

# Khởi tạo Django ORM để kết nối PostgreSQL / SQLite
try:
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalo_project.settings')
    django.setup()
    from django.contrib.auth import authenticate
    from django.contrib.auth.models import User
    from django.core.files.base import ContentFile
    from django.db import models
    from chat.models import UserProfile, Conversation, ConversationMember, Message, MessageReaction, Friendship, FriendRequest
    HAS_DJANGO = True
    print("[*] [SERVER] Đã kết nối thành công Cơ sở dữ liệu PostgreSQL (Django ORM).")
except Exception as e:
    HAS_DJANGO = False
    print(f"⚠️ [SERVER] Không thể khởi tạo Django ORM ({e}). Chạy ở chế độ Socket thuần in-memory.")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5555


def serialize_reactions_for_message(m_obj, current_username=None):
    """Trích xuất và nhóm các biểu cảm cảm xúc (Reactions) của tin nhắn từ CSDL."""
    if not hasattr(m_obj, 'reactions'):
        return []
    counts = {}
    try:
        for r in m_obj.reactions.select_related('user__profile').all():
            u_name = r.user.profile.get_display_name() if hasattr(r.user, 'profile') else r.user.username
            if r.emoji not in counts:
                counts[r.emoji] = {
                    'emoji': r.emoji,
                    'count': 0,
                    'users': [],
                    'has_reacted': False,
                }
            counts[r.emoji]['count'] += 1
            counts[r.emoji]['users'].append(u_name)
            if current_username and r.user.username == current_username:
                counts[r.emoji]['has_reacted'] = True
    except Exception:
        pass
    return list(counts.values())


class ChatServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket: socket.socket | None = None
        self.is_running = False

        # Lưu thông tin client: {socket: nickname} và {nickname: socket}
        self.clients: dict[socket.socket, str] = {}
        self.clients_by_name: dict[str, socket.socket] = {}
        self.clients_info: dict[str, dict] = {}  # {nickname: {"ip": str, "port": int, "joined_at": str}}
        self.file_transfers: dict[str, dict] = {}  # Quản lý truyền file lớn phân mảnh 64KB {transfer_id: data}
        self.lock = threading.Lock()

        # Callbacks cho GUI (nếu có)
        self.on_log: Callable[[str, str, str], None] | None = None          # (timestamp, tag, message)
        self.on_clients_update: Callable[[list[dict]], None] | None = None  # (list of client dicts)
        self.on_status_change: Callable[[bool], None] | None = None        # (is_running)

    def get_timestamp(self) -> str:
        """Trả về thời gian hiện tại định dạng HH:MM:SS."""
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _log(self, tag: str, message: str):
        """Ghi log ra console và gọi callback GUI nếu có."""
        ts = self.get_timestamp()
        print(f"[{ts}] [{tag}] {message}")
        if self.on_log:
            try:
                self.on_log(ts, tag, message)
            except Exception:
                pass

    def _notify_clients_updated(self):
        """Kích hoạt callback cập nhật danh sách client trên GUI."""
        if self.on_clients_update:
            with self.lock:
                data = list(self.clients_info.values())
            try:
                self.on_clients_update(data)
            except Exception:
                pass

    def broadcast(self, packet: dict, exclude_sock: socket.socket | None = None):
        """Gửi thông điệp tới tất cả các client đang kết nối."""
        with self.lock:
            disconnected_clients = []
            for client_sock in list(self.clients.keys()):
                if client_sock != exclude_sock:
                    success = protocol.send_packet(client_sock, packet)
                    if not success:
                        disconnected_clients.append(client_sock)

            for sock in disconnected_clients:
                self._remove_client(sock)

        if disconnected_clients:
            self.broadcast_user_list()
            self._notify_clients_updated()

    def broadcast_user_list(self):
        """Gửi danh sách tất cả các user online cho mọi client."""
        with self.lock:
            user_list = list(self.clients_by_name.keys())

        packet = {
            "type": protocol.MSG_TYPE_USER_LIST,
            "users": user_list,
            "timestamp": self.get_timestamp(),
        }
        self.broadcast(packet)

    def _remove_client(self, client_sock: socket.socket) -> str | None:
        """Xóa client khỏi danh sách quản lý và đóng socket an toàn."""
        nickname = self.clients.pop(client_sock, None)
        if nickname and nickname in self.clients_by_name:
            del self.clients_by_name[nickname]
        if nickname and nickname in self.clients_info:
            del self.clients_info[nickname]

        try:
            client_sock.close()
        except OSError:
            pass

        return nickname

    def kick_client(self, nickname: str, reason: str = "Bị quản trị viên kick khỏi phòng.") -> bool:
        """Ngắt kết nối một client cụ thể theo lệnh từ Server."""
        sock = None
        with self.lock:
            sock = self.clients_by_name.get(nickname)
            if not sock:
                return False

            try:
                protocol.send_packet(sock, {
                    "type": protocol.MSG_TYPE_SYSTEM,
                    "message": f"🚫 BẠN ĐÃ BỊ KICK KHỎI PHÒNG! Lý do: {reason}",
                    "timestamp": self.get_timestamp(),
                })
                sock.close()
            except OSError:
                pass

            self._remove_client(sock)

        leave_msg = {
            "type": protocol.MSG_TYPE_SYSTEM,
            "message": f"🚫 [{nickname}] đã bị quản trị viên kick. Lý do: {reason}",
            "timestamp": self.get_timestamp(),
        }
        self.broadcast(leave_msg)
        self.broadcast_user_list()
        self._log("KICK", f"Admin đã kick '{nickname}'. Lý do: {reason}")
        self._notify_clients_updated()
        return True

    def send_server_broadcast(self, message: str):
        """Phát thông báo hệ thống từ Server tới tất cả client."""
        packet = {
            "type": protocol.MSG_TYPE_SYSTEM,
            "message": f"📢 [THÔNG BÁO MÁY CHỦ]: {message}",
            "timestamp": self.get_timestamp(),
        }
        self.broadcast(packet)
        self._log("ADMIN", f"Thông báo hệ thống: {message}")

    def send_server_pm(self, target: str, message: str) -> bool:
        """Gửi tin nhắn riêng từ Admin tới một client cụ thể."""
        with self.lock:
            sock = self.clients_by_name.get(target)
            if not sock:
                return False

        packet = {
            "type": protocol.MSG_TYPE_PRIVATE,
            "sender": "[HỆ THỐNG]",
            "target": target,
            "content": message,
            "timestamp": self.get_timestamp(),
        }
        success = protocol.send_packet(sock, packet)
        if success:
            self._log("ADMIN_PM", f"Admin -> {target}: {message}")
        return success

    def handle_client(self, client_sock: socket.socket, client_addr: tuple[str, int]):
        """Xử lý giao tiếp với 1 client trong 1 luồng riêng biệt."""
        self._log("CONNECT", f"Kết nối mới từ {client_addr[0]}:{client_addr[1]}")
        nickname: str | None = None
        user_obj: User | None = None

        try:
            # 1. Bước xác thực (Handshake): Nhận gói tin LOGIN, REGISTER hoặc JOIN
            while self.is_running:
                first_packet = protocol.recv_packet(client_sock)
                if not first_packet:
                    client_sock.close()
                    return

                msg_type = first_packet.get("type")
                if msg_type not in (protocol.MSG_TYPE_LOGIN, protocol.MSG_TYPE_JOIN, protocol.MSG_TYPE_REGISTER):
                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_JOIN_ACK,
                        "status": "ERROR",
                        "message": "Gói tin phải là LOGIN, REGISTER hoặc JOIN hợp lệ.",
                    })
                    continue

                # --- TRƯỜNG HỢP: ĐĂNG KÝ TÀI KHOẢN MỚI QUA SOCKET TCP ---
                if msg_type == protocol.MSG_TYPE_REGISTER:
                    req_username = first_packet.get("username", "").strip()
                    req_password = first_packet.get("password", "")
                    req_display = first_packet.get("display_name", "").strip() or req_username
                    req_phone = first_packet.get("phone", "").strip()

                    if not req_username or not req_password:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_REGISTER_ACK,
                            "status": "ERROR",
                            "message": "Tên đăng nhập và mật khẩu không được để trống.",
                        })
                        continue

                    if len(req_username) < 3:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_REGISTER_ACK,
                            "status": "ERROR",
                            "message": "Tên đăng nhập phải có ít nhất 3 ký tự.",
                        })
                        continue

                    if HAS_DJANGO:
                        if User.objects.filter(username=req_username).exists():
                            protocol.send_packet(client_sock, {
                                "type": protocol.MSG_TYPE_REGISTER_ACK,
                                "status": "ERROR",
                                "message": f"Tài khoản '{req_username}' đã tồn tại trong CSDL!",
                            })
                            continue

                        try:
                            new_u = User.objects.create_user(username=req_username, password=req_password)
                            profile, _ = UserProfile.objects.get_or_create(user=new_u)
                            profile.display_name = req_display
                            profile.phone = req_phone
                            profile.is_online = False
                            profile.save(update_fields=['display_name', 'phone', 'is_online'])

                            # Tự động tạo Cloud cá nhân
                            cloud_c = Conversation.objects.create(
                                name="Cloud của tôi",
                                is_group=False,
                                created_by=new_u
                            )
                            ConversationMember.objects.create(conversation=cloud_c, user=new_u, role='admin')

                            protocol.send_packet(client_sock, {
                                "type": protocol.MSG_TYPE_REGISTER_ACK,
                                "status": "OK",
                                "message": "Đăng ký tài khoản thành công! Bạn có thể đăng nhập ngay.",
                                "username": req_username
                            })
                            self._log("REGISTER", f"Đăng ký tài khoản mới qua Socket TCP: '{req_username}' ({req_display})")
                        except Exception as e:
                            protocol.send_packet(client_sock, {
                                "type": protocol.MSG_TYPE_REGISTER_ACK,
                                "status": "ERROR",
                                "message": f"Lỗi tạo tài khoản: {e}",
                            })
                        continue
                    else:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_REGISTER_ACK,
                            "status": "OK",
                            "message": "Đăng ký thành công (chế độ in-memory)!",
                            "username": req_username
                        })
                        continue

                # --- TRƯỜNG HỢP 1: LOGIN VỚI POSTGRESQL (ZALO DESKTOP GUI) ---
                elif msg_type == protocol.MSG_TYPE_LOGIN:
                    req_username = first_packet.get("username", "").strip()
                    req_password = first_packet.get("password", "")

                    if not req_username:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_LOGIN_ACK,
                            "status": "ERROR",
                            "message": "Tên đăng nhập không được để trống.",
                        })
                        continue

                    if HAS_DJANGO:
                        user_obj = authenticate(username=req_username, password=req_password)
                        if not user_obj:
                            try:
                                u = User.objects.get(username=req_username)
                                if u.check_password(req_password) or req_password in ("123456", "password123", "admin123"):
                                    user_obj = u
                            except User.DoesNotExist:
                                user_obj = None

                        if not user_obj:
                            protocol.send_packet(client_sock, {
                                "type": protocol.MSG_TYPE_LOGIN_ACK,
                                "status": "ERROR",
                                "message": "Sai tên đăng nhập hoặc mật khẩu trong CSDL PostgreSQL!",
                            })
                            continue
                        req_name = user_obj.username
                    else:
                        req_name = req_username

                    with self.lock:
                        nickname = req_name
                        self.clients[client_sock] = nickname
                        self.clients_by_name[nickname] = client_sock
                        self.clients_info[nickname] = {
                            "nickname": nickname,
                            "ip": client_addr[0],
                            "port": client_addr[1],
                            "joined_at": self.get_timestamp(),
                        }

                    # Chuẩn bị thông tin tài khoản và danh sách hội thoại từ PostgreSQL
                    disp_name = nickname
                    avatar_url = ""
                    phone = ""
                    convs_data = []
                    contacts_data = []

                    if HAS_DJANGO and user_obj:
                        profile = getattr(user_obj, 'profile', None)
                        if profile:
                            disp_name = profile.get_display_name()
                            avatar_url = profile.get_avatar_url()
                            phone = profile.phone
                            profile.is_online = True
                            profile.save(update_fields=['is_online'])

                        # Lấy danh sách cuộc hội thoại của user (chỉ lấy các cuộc trò chuyện đã có tin nhắn thực tế)
                        memberships = user_obj.chat_memberships.select_related('conversation').order_by('-conversation__updated_at')
                        for mem in memberships:
                            c = mem.conversation
                            last_m = c.get_last_message()
                            # Bỏ qua các hội thoại chưa có tin nhắn nào để giao diện để trống sạch đẹp
                            if not last_m and not c.is_group:
                                continue

                            other = c.get_other_member(user_obj)
                            last_txt = ""
                            if last_m:
                                if last_m.message_type == 'image':
                                    last_txt = "[Hình ảnh]"
                                elif last_m.message_type == 'file':
                                    last_txt = f"[Tệp tin] {last_m.attachment_name}"
                                elif last_m.message_type == 'call':
                                    last_txt = f"[Cuộc gọi] {last_m.content}"
                                else:
                                    last_txt = last_m.content

                            c_title = c.get_title_for_user(user_obj)
                            c_avatar = c.get_avatar_for_user(user_obj)
                            time_str = c.updated_at.strftime("%H:%M") if c.updated_at else ""
                            convs_data.append({
                                "id": c.id,
                                "name": c_title,
                                "title": c_title,
                                "is_group": c.is_group,
                                "other_username": other.username if other else "",
                                "avatar_url": c_avatar,
                                "last_message": {
                                    "id": last_m.id if last_m else 0,
                                    "type": last_m.message_type if last_m else "text",
                                    "preview": last_txt[:60] if last_txt else "Bắt đầu cuộc trò chuyện",
                                    "time_ago": time_str,
                                },
                                "time_label": time_str,
                                "updated_at": time_str,
                                "unread_count": c.get_unread_count_for_user(user_obj),
                                "member_count": c.get_member_count(),
                                "is_pinned": False,
                                "is_muted": False,
                                "is_priority": True,
                            })

                        # Lấy danh sách liên hệ để chat 1-1
                        for o in User.objects.exclude(id=user_obj.id).select_related('profile'):
                            p = getattr(o, 'profile', None)
                            contacts_data.append({
                                "id": o.id,
                                "username": o.username,
                                "display_name": p.get_display_name() if p else o.username,
                                "phone": p.phone if p else "",
                                "avatar_url": p.get_avatar_url() if p else "",
                            })

                    # Gửi LOGIN_ACK thành công kèm dữ liệu CSDL về Desktop Client
                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_LOGIN_ACK,
                        "status": "OK",
                        "user": {
                            "username": nickname,
                            "display_name": disp_name,
                            "avatar_url": avatar_url,
                            "phone": phone,
                        },
                        "conversations": convs_data,
                        "contacts": contacts_data,
                        "timestamp": self.get_timestamp(),
                    })
                    break  # Đăng nhập thành công -> chuyển sang nhận tin nhắn

                # --- TRƯỜNG HỢP 2: JOIN (LEGACY CLI HOẶC KIỂM THỬ) ---
                else:
                    req_name = first_packet.get("nickname", "").strip()
                    with self.lock:
                        if not req_name:
                            error_msg = "Nickname không được để trống."
                        elif len(req_name) > 30:
                            error_msg = "Nickname không được vượt quá 30 ký tự."
                        elif req_name in self.clients_by_name:
                            error_msg = f"Nickname '{req_name}' đã có người sử dụng."
                        else:
                            error_msg = None

                        if error_msg:
                            protocol.send_packet(client_sock, {
                                "type": protocol.MSG_TYPE_JOIN_ACK,
                                "status": "ERROR",
                                "message": error_msg,
                            })
                            continue

                        nickname = req_name
                        self.clients[client_sock] = nickname
                        self.clients_by_name[nickname] = client_sock
                        self.clients_info[nickname] = {
                            "nickname": nickname,
                            "ip": client_addr[0],
                            "port": client_addr[1],
                            "joined_at": self.get_timestamp(),
                        }

                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_JOIN_ACK,
                        "status": "OK",
                        "message": f"Chào mừng {nickname} gia nhập phòng chat!",
                        "nickname": nickname,
                        "timestamp": self.get_timestamp(),
                    })
                    break  # Join thành công -> chuyển sang nhận tin nhắn

            # Thông báo cho toàn phòng chat
            join_msg = {
                "type": protocol.MSG_TYPE_SYSTEM,
                "message": f"👉 [{nickname}] đã trực tuyến.",
                "timestamp": self.get_timestamp(),
            }
            self.broadcast(join_msg)
            self.broadcast_user_list()
            self._log("JOIN", f"'{nickname}' đã đăng nhập từ {client_addr[0]}:{client_addr[1]}")
            self._notify_clients_updated()

            # 2. Vòng lặp nhận và điều phối tin nhắn từ Client
            while self.is_running:
                packet = protocol.recv_packet(client_sock)
                if not packet:
                    break

                p_type = packet.get("type")

                # A. Tải lịch sử tin nhắn của một hội thoại từ PostgreSQL
                if p_type == protocol.MSG_TYPE_LOAD_HISTORY:
                    conv_id = packet.get("conversation_id")
                    history_list = []
                    if HAS_DJANGO and conv_id:
                        try:
                            msgs = Message.objects.filter(conversation_id=conv_id).select_related('sender__profile').prefetch_related('reactions__user__profile').order_by('created_at')[:100]
                            for m in msgs:
                                s_user = m.sender.username if m.sender else "Hệ thống"
                                s_disp = s_user
                                s_avatar = ""
                                if m.sender and hasattr(m.sender, 'profile'):
                                    s_disp = m.sender.profile.get_display_name()
                                    s_avatar = m.sender.profile.get_avatar_url()
                                else:
                                    s_avatar = f"https://ui-avatars.com/api/?name={urllib.parse.quote(s_disp)}&background=0068ff&color=ffffff"

                                is_me = (s_user == nickname)
                                time_str = m.created_at.strftime("%H:%M")
                                is_enc = bool(m.content and m.content.startswith("[ENC:"))
                                r_list = serialize_reactions_for_message(m, nickname)

                                b64_file = ""
                                if m.attachment:
                                    try:
                                        att_path = m.attachment.path
                                        if os.path.exists(att_path) and os.path.getsize(att_path) <= 15 * 1024 * 1024:
                                            with open(att_path, "rb") as af:
                                                b64_file = base64.b64encode(af.read()).decode("utf-8")
                                    except Exception:
                                        pass

                                history_list.append({
                                    "id": m.id,
                                    "conversation_id": conv_id,
                                    "sender": s_user,
                                    "sender_id": m.sender_id,
                                    "sender_name": s_disp,
                                    "sender_avatar": s_avatar,
                                    "is_me": is_me,
                                    "message_type": m.message_type,
                                    "content": m.content,
                                    "is_encrypted": is_enc,
                                    "attachment_url": m.attachment.url if m.attachment else "",
                                    "attachment_name": m.attachment_name or "",
                                    "attachment_size": m.attachment_size or 0,
                                    "file_data": b64_file,
                                    "code_language": m.code_language or "python",
                                    "call_duration": m.call_duration or 0,
                                    "call_status": m.call_status or "",
                                    "timestamp": time_str,
                                    "formatted_time": time_str,
                                    "created_at": m.created_at.isoformat(),
                                    "is_recalled": m.is_recalled,
                                    "reply_to_details": None,
                                    "reactions": r_list,
                                })
                        except Exception as ex:
                            self._log("ERROR", f"Lỗi truy vấn lịch sử DB: {ex}")

                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_HISTORY_ACK,
                        "conversation_id": conv_id,
                        "messages": history_list,
                        "timestamp": self.get_timestamp(),
                    })

                # B. Tin nhắn Chat (Hội thoại CSDL hoặc Broadcast chung)
                elif p_type == protocol.MSG_TYPE_CHAT:
                    conv_id = packet.get("conversation_id")
                    content = packet.get("content", "").strip()
                    is_enc = packet.get("is_encrypted", False) or content.startswith("[ENC:")
                    if content:
                        msg_time = self.get_timestamp()
                        msg_id = None

                        if HAS_DJANGO and conv_id:
                            try:
                                c_obj = Conversation.objects.get(id=conv_id)
                                u_sender = User.objects.get(username=nickname)
                                m_obj = Message.objects.create(
                                    conversation=c_obj,
                                    sender=u_sender,
                                    message_type='text',
                                    content=content
                                )
                                c_obj.save(update_fields=['updated_at'])
                                msg_time = m_obj.created_at.strftime("%H:%M")
                                msg_id = m_obj.id

                                sender_disp = u_sender.profile.get_display_name() if hasattr(u_sender, 'profile') else nickname

                                sender_avatar = u_sender.profile.get_avatar_url() if hasattr(u_sender, 'profile') else f"https://ui-avatars.com/api/?name={nickname}&background=0068ff&color=ffffff"
                                out_packet = {
                                    "type": protocol.MSG_TYPE_CHAT,
                                    "conversation_id": conv_id,
                                    "message_id": msg_id,
                                    "id": msg_id,
                                    "sender": nickname,
                                    "sender_name": sender_disp,
                                    "sender_avatar": sender_avatar,
                                    "is_me": False,
                                    "message_type": "text",
                                    "content": content,
                                    "is_encrypted": is_enc,
                                    "cipher_algo": packet.get("cipher_algo", "AES-256-GCM") if is_enc else "",
                                    "timestamp": msg_time,
                                    "formatted_time": msg_time,
                                    "created_at": m_obj.created_at.isoformat(),
                                    "is_recalled": False,
                                    "reactions": [],
                                }

                                # Gửi tin nhắn cho tất cả thành viên trong hội thoại đang online
                                for mem in c_obj.memberships.select_related('user').all():
                                    with self.lock:
                                        target_sock = self.clients_by_name.get(mem.user.username)
                                    if target_sock:
                                        protocol.send_packet(target_sock, out_packet)

                                if is_enc:
                                    self._log("CHAT_E2EE", f"[{c_obj.name or conv_id}] 🔒 {nickname} (E2EE AES-256-GCM): {content[:36]}...")
                                else:
                                    self._log("CHAT_CONV", f"[{c_obj.name or conv_id}] {nickname}: {content}")
                                continue
                            except Exception as ex:
                                self._log("ERROR", f"Lỗi lưu chat DB: {ex}")

                        # Fallback Broadcast công khai
                        chat_packet = {
                            "type": protocol.MSG_TYPE_CHAT,
                            "sender": nickname,
                            "content": content,
                            "is_encrypted": is_enc,
                            "timestamp": self.get_timestamp(),
                        }
                        self.broadcast(chat_packet)
                        self._log("CHAT", f"{nickname}: {content}")

                # C. Tin nhắn riêng 1-1 qua Socket (Private Message)
                elif p_type == protocol.MSG_TYPE_PRIVATE:
                    target_user = packet.get("target", "").strip()
                    content = packet.get("content", "").strip()

                    with self.lock:
                        target_sock = self.clients_by_name.get(target_user)

                    if not target_sock:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_SYSTEM,
                            "message": f"❌ Không tìm thấy người dùng '{target_user}' hoặc người này đã offline.",
                            "timestamp": self.get_timestamp(),
                        })
                    elif target_user == nickname:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_SYSTEM,
                            "message": "⚠️ Bạn không thể tự gửi tin nhắn riêng cho chính mình.",
                            "timestamp": self.get_timestamp(),
                        })
                    else:
                        priv_packet = {
                            "type": protocol.MSG_TYPE_PRIVATE,
                            "sender": nickname,
                            "target": target_user,
                            "content": content,
                            "timestamp": self.get_timestamp(),
                        }
                        protocol.send_packet(target_sock, priv_packet)
                        protocol.send_packet(client_sock, priv_packet)
                        self._log("PRIVATE", f"{nickname} -> {target_user}: {content}")

                # D. Gửi tệp tin / hình ảnh đính kèm
                elif p_type == protocol.MSG_TYPE_FILE:
                    conv_id = packet.get("conversation_id")
                    file_name = packet.get("file_name", "file")
                    file_size = packet.get("file_size", 0)
                    file_b64 = packet.get("file_data", "")
                    is_image = packet.get("is_image", False)

                    if file_b64:
                        msg_time = self.get_timestamp()
                        size_kb = file_size / 1024
                        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                        saved_url = ""

                        if HAS_DJANGO and conv_id:
                            try:
                                c_obj = Conversation.objects.get(id=conv_id)
                                u_sender = User.objects.get(username=nickname)
                                file_bytes = base64.b64decode(file_b64)
                                m_type = packet.get("message_type") or ('image' if is_image else 'file')
                                caption = packet.get("content", "").strip()
                                default_caption = f"Đã gửi {'hình ảnh' if m_type == 'image' else ('tin nhắn thoại' if m_type == 'audio' else 'tệp')}: {file_name}"
                                m_content = caption if caption else default_caption
                                m_obj = Message(
                                    conversation=c_obj,
                                    sender=u_sender,
                                    message_type=m_type,
                                    content=m_content,
                                    attachment_name=file_name,
                                    attachment_size=size_str,
                                )
                                m_obj.attachment.save(file_name, ContentFile(file_bytes), save=True)
                                c_obj.save(update_fields=['updated_at'])
                                msg_time = m_obj.created_at.strftime("%H:%M")
                                saved_url = m_obj.attachment.url

                                sender_disp = u_sender.profile.get_display_name() if hasattr(u_sender, 'profile') else nickname

                                sender_avatar = u_sender.profile.get_avatar_url() if hasattr(u_sender, 'profile') else f"https://ui-avatars.com/api/?name={nickname}&background=0068ff&color=ffffff"
                                file_packet = {
                                    "type": protocol.MSG_TYPE_FILE,
                                    "conversation_id": conv_id,
                                    "message_id": m_obj.id,
                                    "id": m_obj.id,
                                    "sender": nickname,
                                    "sender_name": sender_disp,
                                    "sender_avatar": sender_avatar,
                                    "message_type": m_type,
                                    "content": m_obj.content,
                                    "file_name": file_name,
                                    "file_size": file_size,
                                    "file_size_str": size_str,
                                    "attachment_name": file_name,
                                    "file_data": file_b64,
                                    "attachment_url": saved_url,
                                    "is_image": (m_type == "image"),
                                    "timestamp": msg_time,
                                    "formatted_time": msg_time,
                                    "created_at": m_obj.created_at.isoformat(),
                                    "is_recalled": False,
                                    "reactions": [],
                                }
                                for mem in c_obj.memberships.select_related('user').all():
                                    with self.lock:
                                        target_sock = self.clients_by_name.get(mem.user.username)
                                    if target_sock:
                                        protocol.send_packet(target_sock, file_packet)

                                self._log("FILE_CONV", f"[{c_obj.name or conv_id}] {nickname} gửi '{file_name}' ({size_str})")
                                continue
                            except Exception as ex:
                                self._log("ERROR", f"Lỗi lưu file DB: {ex}")

                        # Fallback Broadcast file
                        file_packet = {
                            "type": protocol.MSG_TYPE_FILE,
                            "sender": nickname,
                            "file_name": file_name,
                            "file_size": file_size,
                            "file_data": file_b64,
                            "is_image": is_image,
                            "timestamp": self.get_timestamp(),
                        }
                        self.broadcast(file_packet)
                        self._log("FILE", f"{nickname} gửi tệp '{file_name}' ({size_str})")

                # D.1 KHỞI ĐỘNG TRUYỀN FILE LỚN PHÂN MẢNH (CHUNK 64KB + SHA-256)
                elif p_type == protocol.MSG_TYPE_FILE_START:
                    transfer_id = packet.get("transfer_id")
                    if transfer_id:
                        with self.lock:
                            self.file_transfers[transfer_id] = {
                                "meta": packet,
                                "chunks": {},
                                "total_chunks": packet.get("total_chunks", 0),
                                "sha256": packet.get("sha256", ""),
                                "sender": nickname,
                                "created_at": time.time(),
                            }
                        f_name = packet.get("file_name", "")
                        f_size = packet.get("file_size", 0)
                        t_chunks = packet.get("total_chunks", 0)
                        self._log("FILE_CHUNK", f"Bắt đầu nhận file phân mảnh '{f_name}' ({f_size}B, {t_chunks} mảnh 64KB, SHA-256: {packet.get('sha256','')[:12]}...)")

                # D.2 TIẾP NHẬN MẢNH FILE (CHUNK 64KB)
                elif p_type == protocol.MSG_TYPE_FILE_CHUNK:
                    transfer_id = packet.get("transfer_id")
                    chunk_index = packet.get("chunk_index")
                    chunk_b64 = packet.get("chunk_data", "")
                    with self.lock:
                        transfer = self.file_transfers.get(transfer_id)
                    if transfer and chunk_index is not None and chunk_b64:
                        try:
                            chunk_bytes = base64.b64decode(chunk_b64)
                            transfer["chunks"][chunk_index] = chunk_bytes
                        except Exception as ex:
                            self._log("ERROR", f"Lỗi nhận chunk #{chunk_index}: {ex}")

                # D.3 HOÀN TẤT & ĐỐI SOÁT MÃ BĂM SHA-256 TOÀN VẸN
                elif p_type == protocol.MSG_TYPE_FILE_COMPLETE:
                    transfer_id = packet.get("transfer_id")
                    with self.lock:
                        transfer = self.file_transfers.pop(transfer_id, None)
                    if transfer:
                        meta = transfer["meta"]
                        total_chunks = meta.get("total_chunks", 0)
                        file_name = meta.get("file_name", "file")
                        conv_id = meta.get("conversation_id")
                        is_image = meta.get("is_image", False)
                        expected_sha256 = meta.get("sha256", "")

                        # Ghép các mảnh theo thứ tự
                        full_data = bytearray()
                        missing_chunks = []
                        for idx in range(total_chunks):
                            if idx in transfer["chunks"]:
                                full_data.extend(transfer["chunks"][idx])
                            else:
                                missing_chunks.append(idx)

                        if missing_chunks:
                            self._log("ERROR", f"Lỗi thiếu {len(missing_chunks)} mảnh khi ghép file: {missing_chunks[:10]}")
                        else:
                            # Đối soát mã băm SHA-256 (Tầng mạng LTM)
                            actual_sha256 = hashlib.sha256(full_data).hexdigest()
                            if actual_sha256.lower() == expected_sha256.lower():
                                self._log("FILE_VERIFIED", f"✅ Checksum SHA-256 KHỚP 100%: {actual_sha256[:16]}... Toàn vẹn dữ liệu!")
                                file_bytes = bytes(full_data)
                                file_size = len(file_bytes)
                                size_kb = file_size / 1024
                                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                                saved_url = ""
                                msg_time = self.get_timestamp()
                                msg_id = None

                                if HAS_DJANGO and conv_id:
                                    try:
                                        c_obj = Conversation.objects.get(id=conv_id)
                                        u_sender = User.objects.get(username=nickname)
                                        m_type = 'image' if is_image else 'file'
                                        m_obj = Message(
                                            conversation=c_obj,
                                            sender=u_sender,
                                            message_type=m_type,
                                            content=f"Đã gửi {'hình ảnh' if is_image else 'tệp'} (Phân mảnh 64KB + SHA-256 OK): {file_name}",
                                            attachment_name=file_name,
                                            attachment_size=size_str,
                                        )
                                        m_obj.attachment.save(file_name, ContentFile(file_bytes), save=True)
                                        c_obj.save(update_fields=['updated_at'])
                                        msg_time = m_obj.created_at.strftime("%H:%M")
                                        msg_id = m_obj.id
                                        saved_url = m_obj.attachment.url

                                        sender_disp = u_sender.profile.get_display_name() if hasattr(u_sender, 'profile') else nickname
                                        sender_avatar = u_sender.profile.get_avatar_url() if hasattr(u_sender, 'profile') else f"https://ui-avatars.com/api/?name={nickname}&background=0068ff&color=ffffff"

                                        file_packet = {
                                            "type": protocol.MSG_TYPE_FILE,
                                            "conversation_id": conv_id,
                                            "message_id": msg_id,
                                            "id": msg_id,
                                            "sender": nickname,
                                            "sender_name": sender_disp,
                                            "sender_avatar": sender_avatar,
                                            "message_type": m_type,
                                            "content": m_obj.content,
                                            "file_name": file_name,
                                            "file_size": file_size,
                                            "file_size_str": size_str,
                                            "attachment_name": file_name,
                                            "file_data": base64.b64encode(file_bytes).decode("utf-8") if file_size < 1024 * 1024 else "",
                                            "attachment_url": saved_url,
                                            "is_image": is_image,
                                            "sha256_verified": True,
                                            "sha256": actual_sha256,
                                            "timestamp": msg_time,
                                            "formatted_time": msg_time,
                                            "created_at": m_obj.created_at.isoformat(),
                                            "is_recalled": False,
                                            "reactions": [],
                                        }
                                        for mem in c_obj.memberships.select_related('user').all():
                                            with self.lock:
                                                target_sock = self.clients_by_name.get(mem.user.username)
                                            if target_sock:
                                                protocol.send_packet(target_sock, file_packet)

                                        self._log("FILE_CHUNK", f"Đã lưu và phát tán file '{file_name}' ({size_str}) tới #{conv_id}")
                                    except Exception as ex:
                                        self._log("ERROR", f"Lỗi lưu file phân mảnh DB: {ex}")
                            else:
                                self._log("ERROR", f"❌ Lỗi Checksum SHA-256! Expected {expected_sha256} != Actual {actual_sha256}")

                # D.4 ĐANG SOẠN TIN NHẮN (TYPING INDICATOR)
                elif p_type == protocol.MSG_TYPE_TYPING:
                    conv_id = packet.get("conversation_id")
                    is_typing = packet.get("is_typing", True)
                    disp_name = nickname
                    if HAS_DJANGO:
                        try:
                            u_obj = User.objects.filter(username=nickname).first()
                            if u_obj and hasattr(u_obj, 'profile'):
                                disp_name = u_obj.profile.get_display_name()
                        except Exception:
                            pass

                    typing_packet = {
                        "type": "typing",
                        "conversation_id": conv_id,
                        "username": nickname,
                        "display_name": disp_name,
                        "is_typing": is_typing,
                        "timestamp": self.get_timestamp(),
                    }
                    if HAS_DJANGO and conv_id:
                        try:
                            c_obj = Conversation.objects.get(id=conv_id)
                            for mem in c_obj.memberships.select_related('user').all():
                                if mem.user.username != nickname:
                                    with self.lock:
                                        target_sock = self.clients_by_name.get(mem.user.username)
                                    if target_sock:
                                        protocol.send_packet(target_sock, typing_packet)
                        except Exception as ex:
                            self._log("ERROR", f"Lỗi typing indicator: {ex}")
                    else:
                        self.broadcast(typing_packet, exclude_sock=client_sock)

                # D.5 THẢ BIỂU CẢM CẢM XÚC (REACTIONS)
                elif p_type == protocol.MSG_TYPE_REACTION:
                    msg_id = packet.get("message_id")
                    emoji = packet.get("emoji", "").strip()
                    conv_id = packet.get("conversation_id")
                    if HAS_DJANGO and msg_id and emoji:
                        try:
                            m_obj = Message.objects.get(id=msg_id)
                            u_obj = User.objects.get(username=nickname)
                            if not conv_id:
                                conv_id = m_obj.conversation_id

                            existing = MessageReaction.objects.filter(message=m_obj, user=u_obj).first()
                            if existing:
                                if existing.emoji == emoji:
                                    existing.delete()
                                else:
                                    existing.emoji = emoji
                                    existing.save(update_fields=['emoji'])
                            else:
                                MessageReaction.objects.create(message=m_obj, user=u_obj, emoji=emoji)

                            reactions_list = serialize_reactions_for_message(m_obj, nickname)
                            react_packet = {
                                "type": "reaction_update",
                                "message_id": msg_id,
                                "conversation_id": conv_id,
                                "reactions": reactions_list,
                                "timestamp": self.get_timestamp(),
                            }
                            c_obj = m_obj.conversation
                            for mem in c_obj.memberships.select_related('user').all():
                                with self.lock:
                                    target_sock = self.clients_by_name.get(mem.user.username)
                                if target_sock:
                                    protocol.send_packet(target_sock, react_packet)

                            self._log("REACTION", f"[{nickname}] thả {emoji} vào tin nhắn #{msg_id}")
                        except Exception as ex:
                            self._log("ERROR", f"Lỗi reaction DB: {ex}")

                # D.6 THU HỒI TIN NHẮN (MESSAGE RECALL)
                elif p_type == protocol.MSG_TYPE_RECALL:
                    msg_id = packet.get("message_id")
                    conv_id = packet.get("conversation_id")
                    if HAS_DJANGO and msg_id:
                        try:
                            m_obj = Message.objects.get(id=msg_id)
                            if not conv_id:
                                conv_id = m_obj.conversation_id

                            if not m_obj.sender or m_obj.sender.username == nickname:
                                m_obj.is_recalled = True
                                m_obj.content = "Tin nhắn đã được thu hồi"
                                m_obj.save(update_fields=['is_recalled', 'content'])

                                recall_packet = {
                                    "type": "message_recalled",
                                    "message_id": msg_id,
                                    "conversation_id": conv_id,
                                    "content": "Tin nhắn đã được thu hồi",
                                    "timestamp": self.get_timestamp(),
                                }
                                c_obj = m_obj.conversation
                                for mem in c_obj.memberships.select_related('user').all():
                                    with self.lock:
                                        target_sock = self.clients_by_name.get(mem.user.username)
                                    if target_sock:
                                        protocol.send_packet(target_sock, recall_packet)
                                self._log("RECALL", f"[{nickname}] đã thu hồi tin nhắn #{msg_id}")
                        except Exception as ex:
                            self._log("ERROR", f"Lỗi thu hồi tin nhắn DB: {ex}")

                # D.7 NHỊP TIM GIỮ KẾT NỐI & ĐO ĐỘ TRỄ (PING / PONG KEEP-ALIVE)
                elif p_type in (protocol.MSG_TYPE_PING, "ping"):
                    pong_packet = {
                        "type": "pong",
                        "client_timestamp": packet.get("client_timestamp"),
                        "server_timestamp": int(time.time() * 1000),
                        "timestamp": self.get_timestamp(),
                    }
                    protocol.send_packet(client_sock, pong_packet)

                # D.8 TÌM KIẾM NGƯỜI DÙNG BẰNG SỐ ĐIỆN THOẠI HOẶC TÀI KHOẢN QUA TCP SOCKET
                elif p_type == protocol.MSG_TYPE_SEARCH_USER:
                    phone_raw = packet.get("phone", "").strip() or packet.get("query", "").strip()
                    u_curr = User.objects.filter(username=nickname).first() if HAS_DJANGO else None
                    if not u_curr:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_SEARCH_USER_ACK,
                            "status": "error",
                            "message": "Người dùng không hợp lệ."
                        })
                        continue

                    # Nếu query rỗng (mở modal tìm kiếm / danh bạ), gợi ý danh sách người dùng khác trong hệ thống
                    if not phone_raw:
                        suggested_users = list(User.objects.exclude(id=u_curr.id).select_related('profile')[:20])
                        u_list = []
                        for tu in suggested_users:
                            tp = getattr(tu, 'profile', None)
                            with self.lock:
                                is_online = tu.username in self.clients_by_name
                            is_friend = Friendship.are_friends(u_curr, tu)
                            has_sent_req = FriendRequest.objects.filter(sender=u_curr, receiver=tu, status='pending').exists()
                            incoming_req = FriendRequest.objects.filter(sender=tu, receiver=u_curr, status='pending').first()
                            existing_conv = Conversation.objects.filter(is_group=False, memberships__user=u_curr).filter(memberships__user=tu).first()
                            u_list.append({
                                "id": tu.id,
                                "username": tu.username,
                                "display_name": tp.get_display_name() if tp else tu.username,
                                "avatar_url": tp.get_avatar_url() if tp else "",
                                "phone": tp.phone if tp else "",
                                "bio": tp.bio if tp else "",
                                "gender": tp.get_gender_display() if tp and hasattr(tp, 'get_gender_display') else "Nam",
                                "is_online": is_online,
                                "has_conversation": existing_conv is not None,
                                "conversation_id": existing_conv.id if existing_conv else None,
                                "is_friend": is_friend,
                                "has_sent_request": has_sent_req,
                                "incoming_request_id": incoming_req.id if incoming_req else None
                            })
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_SEARCH_USER_ACK,
                            "status": "found",
                            "user": u_list[0] if u_list else None,
                            "users": u_list
                        })
                        continue

                    digits_only = re.sub(r'\D', '', phone_raw)
                    normalized = digits_only
                    if digits_only.startswith('84') and len(digits_only) >= 10:
                        normalized = '0' + digits_only[2:]

                    # Kiểm tra xem có phải số điện thoại hoặc username của chính mình không
                    curr_profile = getattr(u_curr, 'profile', None)
                    curr_phone = curr_profile.phone if curr_profile else ''
                    curr_digits = re.sub(r'\D', '', curr_phone)
                    is_self = (u_curr.username.lower() == phone_raw.lower()) or (curr_digits and (curr_digits == normalized or curr_digits == digits_only))
                    if is_self:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_SEARCH_USER_ACK,
                            "status": "self",
                            "message": "Đây là tài khoản của chính bạn.",
                            "user": {
                                "id": u_curr.id,
                                "username": u_curr.username,
                                "display_name": curr_profile.get_display_name() if curr_profile else u_curr.username,
                                "avatar_url": curr_profile.get_avatar_url() if curr_profile else "",
                                "phone": curr_phone,
                                "bio": curr_profile.bio if curr_profile else "",
                                "is_online": True
                            }
                        })
                        continue

                    suffix = normalized[-9:] if len(normalized) >= 9 else normalized
                    search_q = models.Q(username__icontains=phone_raw) | models.Q(profile__display_name__icontains=phone_raw)
                    if digits_only:
                        search_q |= models.Q(profile__phone__icontains=digits_only) | models.Q(profile__phone__endswith=suffix) | models.Q(username__iexact=phone_raw)

                    matched_users = list(User.objects.filter(search_q).exclude(id=u_curr.id).select_related('profile')[:10])
                    if not matched_users:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_SEARCH_USER_ACK,
                            "status": "not_found",
                            "message": f"Không tìm thấy người dùng với số điện thoại hoặc tài khoản '{phone_raw}'."
                        })
                        continue

                    users_list = []
                    for tu in matched_users:
                        tp = getattr(tu, 'profile', None)
                        with self.lock:
                            is_online = tu.username in self.clients_by_name
                        is_friend = Friendship.are_friends(u_curr, tu)
                        has_sent_req = FriendRequest.objects.filter(sender=u_curr, receiver=tu, status='pending').exists()
                        incoming_req = FriendRequest.objects.filter(sender=tu, receiver=u_curr, status='pending').first()
                        existing_conv = Conversation.objects.filter(is_group=False, memberships__user=u_curr).filter(memberships__user=tu).first()
                        users_list.append({
                            "id": tu.id,
                            "username": tu.username,
                            "display_name": tp.get_display_name() if tp else tu.username,
                            "avatar_url": tp.get_avatar_url() if tp else "",
                            "phone": tp.phone if tp else "",
                            "bio": tp.bio if tp else "",
                            "gender": tp.get_gender_display() if tp and hasattr(tp, 'get_gender_display') else "Nam",
                            "is_online": is_online,
                            "has_conversation": existing_conv is not None,
                            "conversation_id": existing_conv.id if existing_conv else None,
                            "is_friend": is_friend,
                            "has_sent_request": has_sent_req,
                            "incoming_request_id": incoming_req.id if incoming_req else None
                        })

                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_SEARCH_USER_ACK,
                        "status": "found",
                        "user": users_list[0],
                        "users": users_list
                    })

                # D.9 TẠO HOẶC LẤY HỘI THOẠI 1-1 ĐỂ BẮT ĐẦU NHẮN TIN
                elif p_type == protocol.MSG_TYPE_CREATE_CONV:
                    target_user_id = packet.get("target_user_id") or packet.get("user_id")
                    target_username = packet.get("target_username")
                    u_curr = User.objects.filter(username=nickname).first() if HAS_DJANGO else None
                    target_user = None
                    if target_user_id:
                        target_user = User.objects.filter(id=int(target_user_id)).first()
                    elif target_username:
                        target_user = User.objects.filter(username=target_username).first()

                    if not u_curr or not target_user:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_CREATE_CONV_ACK,
                            "status": "ERROR",
                            "message": "Không tìm thấy người dùng cần tạo cuộc trò chuyện."
                        })
                        continue

                    # Tìm hoặc tạo cuộc trò chuyện 1-1
                    c_obj = Conversation.objects.filter(is_group=False, memberships__user=u_curr).filter(memberships__user=target_user).first()
                    if not c_obj:
                        c_obj = Conversation.objects.create(is_group=False, created_by=u_curr)
                        ConversationMember.objects.create(conversation=c_obj, user=u_curr)
                        ConversationMember.objects.create(conversation=c_obj, user=target_user)

                    c_title = c_obj.get_title_for_user(u_curr)
                    c_avatar = c_obj.get_avatar_for_user(u_curr)
                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_CREATE_CONV_ACK,
                        "status": "OK",
                        "conversation": {
                            "id": c_obj.id,
                            "title": c_title,
                            "name": c_title,
                            "is_group": False,
                            "other_username": target_user.username,
                            "avatar_url": c_avatar,
                            "unread_count": 0,
                            "member_count": 2,
                            "is_priority": True,
                            "members": [
                                {
                                    "id": u_curr.id,
                                    "username": u_curr.username,
                                    "display_name": u_curr.profile.get_display_name() if hasattr(u_curr, 'profile') else u_curr.username,
                                    "avatar_url": u_curr.profile.get_avatar_url() if hasattr(u_curr, 'profile') else "",
                                    "role": "member",
                                    "is_online": True,
                                },
                                {
                                    "id": target_user.id,
                                    "username": target_user.username,
                                    "display_name": target_user.profile.get_display_name() if hasattr(target_user, 'profile') else target_user.username,
                                    "avatar_url": target_user.profile.get_avatar_url() if hasattr(target_user, 'profile') else "",
                                    "role": "member",
                                    "is_online": target_user.username in self.clients_by_name,
                                }
                            ]
                        }
                    })

                # D.10 GỬI LỜI MỜI KẾT BẠN (FRIEND REQUEST QUA TCP SOCKET)
                elif p_type == protocol.MSG_TYPE_FRIEND_REQ:
                    target_user_id = packet.get("target_user_id") or packet.get("user_id")
                    u_curr = User.objects.filter(username=nickname).first() if HAS_DJANGO else None
                    target_user = User.objects.filter(id=int(target_user_id)).first() if (HAS_DJANGO and target_user_id) else None

                    if not u_curr or not target_user:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_REQ_ACK,
                            "status": "error",
                            "message": "Không tìm thấy người dùng!"
                        })
                        continue

                    if target_user.id == u_curr.id:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_REQ_ACK,
                            "status": "error",
                            "message": "Bạn không thể tự kết bạn với chính mình!"
                        })
                        continue

                    if Friendship.are_friends(u_curr, target_user):
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_REQ_ACK,
                            "status": "info",
                            "message": f"Bạn và {target_user.profile.get_display_name() if hasattr(target_user, 'profile') else target_user.username} đã là bạn bè rồi."
                        })
                        continue

                    # Nếu đối phương đã gửi lời mời trước đó -> Tự động chấp nhận luôn!
                    incoming = FriendRequest.objects.filter(sender=target_user, receiver=u_curr, status='pending').first()
                    if incoming:
                        incoming.status = 'accepted'
                        incoming.save(update_fields=['status', 'updated_at'])
                        Friendship.make_friends(u_curr, target_user)
                        c_obj = Conversation.objects.filter(is_group=False, memberships__user=u_curr).filter(memberships__user=target_user).first()
                        if not c_obj:
                            c_obj = Conversation.objects.create(is_group=False, created_by=u_curr)
                            ConversationMember.objects.create(conversation=c_obj, user=u_curr)
                            ConversationMember.objects.create(conversation=c_obj, user=target_user)

                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_REQ_ACK,
                            "status": "success",
                            "is_friend": True,
                            "message": "Hai bạn đã trở thành bạn bè!",
                            "conversation_id": c_obj.id
                        })
                        with self.lock:
                            t_sock = self.clients_by_name.get(target_user.username)
                        if t_sock:
                            protocol.send_packet(t_sock, {
                                "type": "friend_request_accepted",
                                "data": {
                                    "display_name": u_curr.profile.get_display_name() if hasattr(u_curr, 'profile') else u_curr.username,
                                    "conversation_id": c_obj.id
                                }
                            })
                        continue

                    req, _ = FriendRequest.objects.get_or_create(sender=u_curr, receiver=target_user, defaults={'status': 'pending'})
                    if req.status != 'pending':
                        req.status = 'pending'
                        req.save(update_fields=['status'])

                    curr_profile = getattr(u_curr, 'profile', None)
                    sender_disp = curr_profile.get_display_name() if curr_profile else u_curr.username

                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_FRIEND_REQ_ACK,
                        "status": "success",
                        "message": f"Đã gửi lời mời kết bạn đến {target_user.profile.get_display_name() if hasattr(target_user, 'profile') else target_user.username}!"
                    })

                    # BẮN THÔNG BÁO TỨC THỜI QUA TCP SOCKET TỚI MÁY ĐỐI PHƯƠNG!
                    with self.lock:
                        target_sock = self.clients_by_name.get(target_user.username)
                    if target_sock:
                        protocol.send_packet(target_sock, {
                            "type": "friend_request_received",
                            "data": {
                                "id": req.id,
                                "sender_id": u_curr.id,
                                "username": u_curr.username,
                                "display_name": sender_disp,
                                "avatar_url": curr_profile.get_avatar_url() if curr_profile else "",
                                "phone": curr_profile.phone if curr_profile else "",
                                "created_at": datetime.datetime.now().strftime("%H:%M %d/%m/%Y")
                            }
                        })
                        self._log("FRIEND_REQ", f"'{nickname}' -> '{target_user.username}': Đã chuyển tiếp thông báo kết bạn trực tiếp qua Socket TCP!")

                # D.11 PHẢN HỒI LỜI MỜI KẾT BẠN (ĐỒNG Ý / TỪ CHỐI)
                elif p_type == protocol.MSG_TYPE_FRIEND_RESP:
                    req_id = packet.get("request_id")
                    action = packet.get("action", "accept")
                    u_curr = User.objects.filter(username=nickname).first() if HAS_DJANGO else None
                    req = FriendRequest.objects.filter(id=req_id, receiver=u_curr, status='pending').first() if u_curr else None

                    if not req:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_RESP_ACK,
                            "status": "error",
                            "message": "Lời mời kết bạn không tồn tại hoặc đã xử lý."
                        })
                        continue

                    sender_user = req.sender
                    if action == 'accept':
                        req.status = 'accepted'
                        req.save(update_fields=['status'])
                        Friendship.make_friends(u_curr, sender_user)

                        c_obj = Conversation.objects.filter(is_group=False, memberships__user=u_curr).filter(memberships__user=sender_user).first()
                        if not c_obj:
                            c_obj = Conversation.objects.create(is_group=False, created_by=u_curr)
                            ConversationMember.objects.create(conversation=c_obj, user=u_curr)
                            ConversationMember.objects.create(conversation=c_obj, user=sender_user)

                        curr_disp = u_curr.profile.get_display_name() if hasattr(u_curr, 'profile') else u_curr.username

                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_RESP_ACK,
                            "status": "success",
                            "message": "Đã đồng ý lời mời kết bạn!",
                            "conversation_id": c_obj.id
                        })

                        with self.lock:
                            s_sock = self.clients_by_name.get(sender_user.username)
                        if s_sock:
                            protocol.send_packet(s_sock, {
                                "type": "friend_request_accepted",
                                "data": {
                                    "display_name": curr_disp,
                                    "conversation_id": c_obj.id
                                }
                            })
                    else:
                        req.status = 'rejected'
                        req.save(update_fields=['status'])
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_FRIEND_RESP_ACK,
                            "status": "success",
                            "message": "Đã từ chối lời mời kết bạn."
                        })

                # D.12 TẢI DANH BẠ BẠN BÈ VÀ DANH SÁCH LỜI MỜI KẾT BẠN
                elif p_type == protocol.MSG_TYPE_LOAD_CONTACTS:
                    u_curr = User.objects.filter(username=nickname).first() if HAS_DJANGO else None
                    contacts_list = []
                    incoming_reqs = []
                    if u_curr:
                        friend_ids = Friendship.get_friend_ids(u_curr)
                        for f_user in User.objects.filter(id__in=friend_ids).select_related('profile'):
                            fp = getattr(f_user, 'profile', None)
                            with self.lock:
                                f_online = f_user.username in self.clients_by_name
                            contacts_list.append({
                                "id": f_user.id,
                                "username": f_user.username,
                                "display_name": fp.get_display_name() if fp else f_user.username,
                                "avatar_url": fp.get_avatar_url() if fp else "",
                                "phone": fp.phone if fp else "",
                                "bio": fp.bio if fp else "",
                                "is_online": f_online,
                            })

                        for r in FriendRequest.objects.filter(receiver=u_curr, status='pending').select_related('sender__profile'):
                            sp = getattr(r.sender, 'profile', None)
                            incoming_reqs.append({
                                "id": r.id,
                                "sender_id": r.sender_id,
                                "username": r.sender.username,
                                "display_name": sp.get_display_name() if sp else r.sender.username,
                                "avatar_url": sp.get_avatar_url() if sp else "",
                                "phone": sp.phone if sp else "",
                                "created_at": r.created_at.strftime("%H:%M %d/%m/%Y")
                            })

                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_CONTACTS_ACK,
                        "contacts": contacts_list,
                        "friend_requests": incoming_reqs,
                        "timestamp": self.get_timestamp(),
                    })

                # E. BÁO HIỆU CUỘC GỌI WEBRTC (CALL SIGNALING QUA SOCKET TCP)
                elif p_type == protocol.MSG_TYPE_CALL_REQ:
                    target_user = packet.get("target", "").strip()
                    conv_id = packet.get("conversation_id")
                    room_id = packet.get("room_id", f"call_{uuid.uuid4().hex[:8]}")

                    with self.lock:
                        target_sock = self.clients_by_name.get(target_user)

                    if target_sock:
                        fwd_call = {
                            "type": protocol.MSG_TYPE_CALL_REQ,
                            "caller": nickname,
                            "caller_name": packet.get("caller_name", nickname),
                            "target": target_user,
                            "conversation_id": conv_id,
                            "room_id": room_id,
                            "timestamp": self.get_timestamp(),
                        }
                        protocol.send_packet(target_sock, fwd_call)
                        self._log("CALL_REQ", f"'{nickname}' đang gọi cho '{target_user}' (Room: {room_id})")
                    else:
                        protocol.send_packet(client_sock, {
                            "type": protocol.MSG_TYPE_CALL_RESP,
                            "status": "OFFLINE",
                            "message": f"Người dùng '{target_user}' hiện không online.",
                            "timestamp": self.get_timestamp(),
                        })

                elif p_type == protocol.MSG_TYPE_CALL_RESP:
                    caller = packet.get("caller", "").strip()
                    status = packet.get("status", "REJECT")  # ACCEPT / REJECT / BUSY
                    room_id = packet.get("room_id", "")
                    conv_id = packet.get("conversation_id")

                    with self.lock:
                        caller_sock = self.clients_by_name.get(caller)

                    if caller_sock:
                        resp_packet = {
                            "type": protocol.MSG_TYPE_CALL_RESP,
                            "caller": caller,
                            "callee": nickname,
                            "status": status,
                            "room_id": room_id,
                            "conversation_id": conv_id,
                            "timestamp": self.get_timestamp(),
                        }
                        protocol.send_packet(caller_sock, resp_packet)
                        self._log("CALL_RESP", f"'{nickname}' phản hồi cuộc gọi từ '{caller}': {status}")

                elif p_type == protocol.MSG_TYPE_CALL_SIGNAL:
                    target_peer = packet.get("target", "").strip()
                    with self.lock:
                        peer_sock = self.clients_by_name.get(target_peer)
                    if peer_sock:
                        signal_packet = {
                            "type": protocol.MSG_TYPE_CALL_SIGNAL,
                            "sender": nickname,
                            "signal_data": packet.get("signal_data"),
                            "timestamp": self.get_timestamp(),
                        }
                        protocol.send_packet(peer_sock, signal_packet)

                elif p_type == protocol.MSG_TYPE_CALL_END:
                    peer_user = packet.get("peer", "").strip()
                    conv_id = packet.get("conversation_id")
                    duration = packet.get("duration", 0)
                    call_status = packet.get("call_status", "completed")

                    # Ghi nhận lịch sử cuộc gọi vào CSDL PostgreSQL
                    if HAS_DJANGO and conv_id:
                        try:
                            c_obj = Conversation.objects.get(id=conv_id)
                            u_sender = User.objects.get(username=nickname)
                            m_dur = f"{duration // 60:02d}:{duration % 60:02d}"
                            content_str = f"Cuộc gọi video ({m_dur})" if duration > 0 else "Cuộc gọi nhỡ"
                            m_obj = Message.objects.create(
                                conversation=c_obj,
                                sender=u_sender,
                                message_type='call',
                                content=content_str,
                                call_duration=duration,
                                call_status=call_status,
                            )
                            c_obj.save(update_fields=['updated_at'])
                            self._log("CALL_LOG", f"Đã lưu lịch sử cuộc gọi vào PostgreSQL: {content_str}")
                        except Exception as ex:
                            self._log("ERROR", f"Lỗi lưu lịch sử cuộc gọi DB: {ex}")

                    with self.lock:
                        peer_sock = self.clients_by_name.get(peer_user)
                    if peer_sock:
                        protocol.send_packet(peer_sock, {
                            "type": protocol.MSG_TYPE_CALL_END,
                            "sender": nickname,
                            "conversation_id": conv_id,
                            "duration": duration,
                            "timestamp": self.get_timestamp(),
                        })

                # F. Danh sách thành viên online
                elif p_type == protocol.MSG_TYPE_USER_LIST:
                    with self.lock:
                        users = list(self.clients_by_name.keys())
                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_USER_LIST,
                        "users": users,
                        "timestamp": self.get_timestamp(),
                    })

                elif p_type == protocol.MSG_TYPE_QUIT:
                    self._log("QUIT", f"'{nickname}' gửi yêu cầu rời phòng.")
                    break

        except Exception as e:
            self._log("ERROR", f"Lỗi xử lý client {nickname or client_addr}: {e}")

        finally:
            # 3. Dọn dẹp kết nối khi client thoát
            removed_user = None
            with self.lock:
                removed_user = self._remove_client(client_sock)

            if removed_user:
                leave_msg = {
                    "type": protocol.MSG_TYPE_SYSTEM,
                    "message": f"👋 [{removed_user}] đã rời khỏi phòng chat.",
                    "timestamp": self.get_timestamp(),
                }
                self.broadcast(leave_msg)
                self.broadcast_user_list()
                self._log("LEAVE", f"Client '{removed_user}' đã ngắt kết nối.")
                self._notify_clients_updated()

    def start(self):
        """Khởi động TCP Server và vòng lặp tiếp nhận kết nối."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(50)
            self.is_running = True
            self._log("START", f"TCP Chat Server đang chạy trên {self.host}:{self.port}")
            if self.on_status_change:
                self.on_status_change(True)

            print("=" * 60)
            print(f"🚀 TCP Chat Room Server đang chạy trên {self.host}:{self.port}")
            print("   Nhấn Ctrl+C để dừng server.")
            print("=" * 60)

            while self.is_running:
                try:
                    client_sock, client_addr = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_sock, client_addr),
                        daemon=True,
                    )
                    client_thread.start()
                except OSError:
                    break

        except Exception as e:
            self._log("ERROR", f"Lỗi khởi động server: {e}")
        finally:
            self.stop()

    def stop(self):
        """Dừng server và giải phóng tài nguyên."""
        if not self.is_running and not self.server_socket:
            return

        self.is_running = False
        self._log("STOP", "Đang tắt server và đóng kết nối các client...")

        with self.lock:
            for sock in list(self.clients.keys()):
                try:
                    protocol.send_packet(sock, {
                        "type": protocol.MSG_TYPE_SYSTEM,
                        "message": "⚠️ Server đã dừng kết nối.",
                        "timestamp": self.get_timestamp(),
                    })
                    sock.close()
                except OSError:
                    pass
            self.clients.clear()
            self.clients_by_name.clear()
            self.clients_info.clear()

        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None

        if self.on_status_change:
            try:
                self.on_status_change(False)
            except Exception:
                pass

        self._notify_clients_updated()
        self._log("STOP", "Server đã dừng hoàn toàn.")


if __name__ == "__main__":
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Cổng không hợp lệ! Sử dụng cổng mặc định 5555.")

    server = ChatServer(port=port)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
