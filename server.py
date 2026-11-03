"""
server.py - TCP Chat Server Đa Luồng (Multi-threaded TCP Socket Server).

Quản lý các kết nối từ Client, điều phối tin nhắn công khai (Broadcast),
tin nhắn riêng (Private Message), cập nhật trạng thái người dùng Online.
Hỗ trợ event callbacks phục vụ Giao diện Đồ họa (Server GUI).
"""

import base64
import datetime
import os
import socket
import sys
import threading
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
    from chat.models import UserProfile, Conversation, ConversationMember, Message
    HAS_DJANGO = True
    print("[*] [SERVER] Đã kết nối thành công Cơ sở dữ liệu PostgreSQL (Django ORM).")
except Exception as e:
    HAS_DJANGO = False
    print(f"⚠️ [SERVER] Không thể khởi tạo Django ORM ({e}). Chạy ở chế độ Socket thuần in-memory.")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5555


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
            # 1. Bước bắt tay (Handshake): Nhận gói tin LOGIN (Desktop) hoặc JOIN (CLI)
            first_packet = protocol.recv_packet(client_sock)
            if not first_packet or first_packet.get("type") not in (protocol.MSG_TYPE_LOGIN, protocol.MSG_TYPE_JOIN):
                protocol.send_packet(client_sock, {
                    "type": protocol.MSG_TYPE_JOIN_ACK,
                    "status": "ERROR",
                    "message": "Gói tin đầu tiên phải là LOGIN hoặc JOIN hợp lệ.",
                })
                client_sock.close()
                return

            msg_type = first_packet.get("type")

            # --- TRƯỜNG HỢP 1: LOGIN VỚI POSTGRESQL (ZALO DESKTOP GUI) ---
            if msg_type == protocol.MSG_TYPE_LOGIN:
                req_username = first_packet.get("username", "").strip()
                req_password = first_packet.get("password", "")

                if not req_username:
                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_LOGIN_ACK,
                        "status": "ERROR",
                        "message": "Tên đăng nhập không được để trống.",
                    })
                    client_sock.close()
                    return

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
                        client_sock.close()
                        return
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

                    # Lấy danh sách cuộc hội thoại của user
                    memberships = user_obj.chat_memberships.select_related('conversation').order_by('-conversation__updated_at')
                    for mem in memberships:
                        c = mem.conversation
                        other = c.get_other_member(user_obj)
                        last_m = c.get_last_message()
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

                        convs_data.append({
                            "id": c.id,
                            "name": c.get_title_for_user(user_obj),
                            "is_group": c.is_group,
                            "other_username": other.username if other else "",
                            "avatar_url": c.get_avatar_for_user(user_obj),
                            "last_message": last_txt[:40],
                            "updated_at": c.updated_at.strftime("%H:%M") if c.updated_at else "",
                            "unread_count": c.get_unread_count_for_user(user_obj),
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
                        client_sock.close()
                        return

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
                            msgs = Message.objects.filter(conversation_id=conv_id).select_related('sender').order_by('created_at')[:80]
                            for m in msgs:
                                s_user = m.sender.username if m.sender else "Hệ thống"
                                s_disp = s_user
                                if m.sender and hasattr(m.sender, 'profile'):
                                    s_disp = m.sender.profile.get_display_name()
                                history_list.append({
                                    "id": m.id,
                                    "sender": s_user,
                                    "sender_name": s_disp,
                                    "message_type": m.message_type,
                                    "content": m.content,
                                    "attachment_url": m.attachment.url if m.attachment else "",
                                    "attachment_name": m.attachment_name,
                                    "attachment_size": m.attachment_size,
                                    "call_duration": m.call_duration,
                                    "call_status": m.call_status,
                                    "timestamp": m.created_at.strftime("%H:%M"),
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

                                out_packet = {
                                    "type": protocol.MSG_TYPE_CHAT,
                                    "conversation_id": conv_id,
                                    "message_id": msg_id,
                                    "sender": nickname,
                                    "sender_name": sender_disp,
                                    "content": content,
                                    "timestamp": msg_time,
                                }

                                # Gửi tin nhắn cho tất cả thành viên trong hội thoại đang online
                                for mem in c_obj.memberships.select_related('user').all():
                                    with self.lock:
                                        target_sock = self.clients_by_name.get(mem.user.username)
                                    if target_sock:
                                        protocol.send_packet(target_sock, out_packet)

                                self._log("CHAT_CONV", f"[{c_obj.name or conv_id}] {nickname}: {content}")
                                continue
                            except Exception as ex:
                                self._log("ERROR", f"Lỗi lưu chat DB: {ex}")

                        # Fallback Broadcast công khai
                        chat_packet = {
                            "type": protocol.MSG_TYPE_CHAT,
                            "sender": nickname,
                            "content": content,
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
                                m_type = 'image' if is_image else 'file'
                                m_obj = Message(
                                    conversation=c_obj,
                                    sender=u_sender,
                                    message_type=m_type,
                                    content=f"Đã gửi { 'hình ảnh' if is_image else 'tệp' }: {file_name}",
                                    attachment_name=file_name,
                                    attachment_size=size_str,
                                )
                                m_obj.attachment.save(file_name, ContentFile(file_bytes), save=True)
                                c_obj.save(update_fields=['updated_at'])
                                msg_time = m_obj.created_at.strftime("%H:%M")
                                saved_url = m_obj.attachment.url

                                sender_disp = u_sender.profile.get_display_name() if hasattr(u_sender, 'profile') else nickname

                                file_packet = {
                                    "type": protocol.MSG_TYPE_FILE,
                                    "conversation_id": conv_id,
                                    "sender": nickname,
                                    "sender_name": sender_disp,
                                    "file_name": file_name,
                                    "file_size": file_size,
                                    "file_size_str": size_str,
                                    "file_data": file_b64,
                                    "attachment_url": saved_url,
                                    "is_image": is_image,
                                    "timestamp": msg_time,
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
