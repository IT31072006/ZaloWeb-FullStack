#!/usr/bin/env python3
"""
client_desktop.py / client.py - Ứng dụng Zalo Desktop kết nối Máy chủ TCP Socket.
Đồ án môn Lập trình Mạng (LTM) - SV: Phạm Huỳnh Quân (24IT220) & Lê Phú Bảo (24IT018).

Kiến trúc Hệ thống:
1. Tầng Mạng (Network): 100% kết nối qua TCP Socket thuần (AF_INET, SOCK_STREAM) tới server.py:5555.
2. Giao thức Mạng: Length-Prefixed Framing (protocol.py - 4 byte header + JSON payload).
3. Giao diện: Cửa sổ Desktop Zalo PC Native siêu đẹp (Dark Mode, Bong bóng chat, Emojis, Gửi file, Tìm kiếm).
4. Mô hình Client - Server:
   - Máy 1 (Server): python3 server.py (hoặc python3 server_gui.py)
   - Máy 1 (Client): python3 client_desktop.py
   - Máy 2 (Client): python3 client_desktop.py <IP_MÁY_1>
"""

import base64
import datetime
import email
import hashlib
import html
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

from websockets.sync.server import serve as ws_serve

import protocol

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 5555
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def is_port_open(host="127.0.0.1", port=5555, timeout=1.0):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def get_free_port(start_port=48080):
    for p in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", p))
                return p
        except OSError:
            continue
    return 48080


# ==============================================================================
# BỘ CẦU NỐI TCP SOCKET CLIENT (LOCAL BRIDGE TO TCP SOCKET SERVER)
# ==============================================================================
class ZaloTCPClient:
    def __init__(self, server_host=DEFAULT_SERVER_HOST, server_port=DEFAULT_SERVER_PORT):
        self.server_host = server_host
        self.server_port = int(server_port)
        self.tcp_sock: socket.socket | None = None
        self.is_connected = False
        self.lock = threading.Lock()

        # Dữ liệu phiên đăng nhập & Tự phục hồi phiên
        self.current_user = None
        self.conversations = []
        self.contacts = []
        self.messages_cache = {}  # {conv_id: [messages]}
        self.saved_credentials: tuple[str, str] | None = None
        self.should_stop = False
        self.is_reconnecting = False
        self.last_pong_time = time.time()
        self.heartbeat_started = False

        # Chờ phản hồi đồng bộ từ Server cho Request-Response
        self.pending_responses = {}  # {type: threading.Event()}
        self.response_payloads = {}

        # Danh sách WebSocket clients cục bộ (giao diện UI trên máy này)
        self.local_ws_clients = set()
        self.ws_lock = threading.Lock()

    def connect(self) -> bool:
        """Mở kết nối TCP Socket tới Server trên cổng 5555."""
        try:
            print(f"[*] Đang kết nối TCP Socket tới Máy chủ {self.server_host}:{self.server_port}...")
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((self.server_host, self.server_port))
            self.is_connected = True
            print(f"✅ Đã kết nối thành công tới TCP Socket Server ({self.server_host}:{self.server_port})!")

            # Luồng nhận gói tin TCP ngầm từ Server
            t = threading.Thread(target=self._recv_loop, daemon=True)
            t.start()

            # Luồng nhịp tim (Keep-Alive Heartbeat Ping/Pong)
            if not self.heartbeat_started:
                self.heartbeat_started = True
                threading.Thread(target=self._heartbeat_loop, daemon=True).start()

            return True
        except Exception as e:
            print(f"❌ Không thể kết nối tới TCP Socket Server ({self.server_host}:{self.server_port}): {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Đóng kết nối an toàn với socket shutdown."""
        self.is_connected = False
        if self.tcp_sock:
            try:
                self.tcp_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.tcp_sock.close()
            except Exception:
                pass

    def send_tcp_packet(self, packet: dict) -> bool:
        if not self.tcp_sock or not self.is_connected:
            return False
        with self.lock:
            return protocol.send_packet(self.tcp_sock, packet)

    def send_and_wait(self, packet: dict, expect_type: str, timeout=5.0) -> dict | None:
        """Gửi gói tin TCP và đợi phản hồi từ Server."""
        evt = threading.Event()
        self.pending_responses[expect_type] = evt
        success = self.send_tcp_packet(packet)
        if not success:
            self.pending_responses.pop(expect_type, None)
            return None

        finished = evt.wait(timeout=timeout)
        self.pending_responses.pop(expect_type, None)
        if finished:
            return self.response_payloads.pop(expect_type, None)
        return None

    def _heartbeat_loop(self):
        """Luồng phát nhịp tim (Keep-Alive Ping/Pong) định kỳ 4.5s để đo RTT và giữ kết nối TCP."""
        while not self.should_stop:
            time.sleep(4.5)
            if self.is_connected and self.tcp_sock:
                try:
                    ping_pkt = {
                        "type": protocol.MSG_TYPE_PING,
                        "client_timestamp": int(time.time() * 1000)
                    }
                    self.send_tcp_packet(ping_pkt)
                except Exception:
                    pass

    def _auto_reconnect_loop(self):
        """Cơ chế Tự động kết nối lại (Auto-Reconnect) khi rớt mạng hoặc khởi động lại Server."""
        self._broadcast_to_ui({
            "type": "system_warning",
            "message": "⚠️ Đã mất kết nối tới máy chủ Socket :5555. Đang tự động kết nối lại..."
        })
        attempts = 0
        while not self.is_connected and not self.should_stop:
            attempts += 1
            time.sleep(2.5)
            print(f"[*] [Tầng Mạng Auto-Reconnect] Thử kết nối lại TCP (lần #{attempts}) tới {self.server_host}:{self.server_port}...")
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.server_host, self.server_port))
                self.tcp_sock = s
                self.is_connected = True
                self.is_reconnecting = False
                print(f"✅ [Tầng Mạng] Đã kết nối lại TCP Socket Server thành công!")

                # Khởi động lại luồng nhận
                threading.Thread(target=self._recv_loop, daemon=True).start()

                # Tái đăng nhập tự động phục hồi phiên làm việc
                if self.saved_credentials:
                    u, p = self.saved_credentials
                    login_pkt = {"type": protocol.MSG_TYPE_LOGIN, "username": u, "password": p}
                    ack = self.send_and_wait(login_pkt, protocol.MSG_TYPE_LOGIN_ACK, timeout=5.0)
                    if ack and ack.get("status") == "OK":
                        print(f"✅ [Tầng Mạng] Đã tự động tái xác thực người dùng '{u}' qua TCP Socket!")

                self._broadcast_to_ui({
                    "type": "system_warning",
                    "message": "✅ Đã khôi phục kết nối thành công tới máy chủ Socket!"
                })
                break
            except Exception:
                pass
        self.is_reconnecting = False

    def _recv_loop(self):
        """Vòng lặp nhận dữ liệu từ TCP Socket Server."""
        while self.is_connected and self.tcp_sock:
            try:
                packet = protocol.recv_packet(self.tcp_sock)
                if not packet:
                    break

                p_type = packet.get("type")

                # Đánh thức các request đồng bộ thông thường (ngoại trừ HISTORY_ACK sẽ đánh thức sau khi giải mã E2EE xong)
                if p_type in self.pending_responses and p_type != protocol.MSG_TYPE_HISTORY_ACK:
                    self.response_payloads[p_type] = packet
                    self.pending_responses[p_type].set()

                # 1. Gói tin phản hồi LOGIN_ACK
                if p_type == protocol.MSG_TYPE_LOGIN_ACK:
                    if packet.get("status") == "OK":
                        self.current_user = packet.get("user")
                        self.conversations = packet.get("conversations", [])
                        self.contacts = packet.get("contacts", [])

                # 2. Gói tin phản hồi REGISTER_ACK
                elif p_type == protocol.MSG_TYPE_REGISTER_ACK:
                    if p_type in self.pending_responses:
                        self.response_payloads[p_type] = packet
                        self.pending_responses[p_type].set()

                # 3. Gói tin phản hồi HISTORY_ACK (Giải mã E2EE AES-256-GCM cho tin nhắn cũ)
                elif p_type == protocol.MSG_TYPE_HISTORY_ACK:
                    conv_id = packet.get("conversation_id")
                    msgs = packet.get("messages", [])
                    for m in msgs:
                        raw_c = m.get("content", "")
                        if raw_c.startswith("[ENC:AES-256-GCM]"):
                            m["is_encrypted"] = True
                            cipher_str = raw_c[len("[ENC:AES-256-GCM]"):]
                            m["content"] = protocol.decrypt_payload(cipher_str)
                        elif m.get("is_encrypted"):
                            m["content"] = protocol.decrypt_payload(raw_c)

                        # Lưu file ảnh/audio/tệp lịch sử vào thư mục media/ nếu chưa có
                        f_b64 = m.get("file_data")
                        att_u = m.get("attachment_url")
                        if f_b64 and att_u:
                            try:
                                rel_path = att_u.lstrip("/")
                                abs_target = os.path.join(BASE_DIR, rel_path)
                                if not os.path.exists(abs_target):
                                    os.makedirs(os.path.dirname(abs_target), exist_ok=True)
                                    with open(abs_target, "wb") as f_out:
                                        f_out.write(base64.b64decode(f_b64))
                            except Exception:
                                pass

                    if conv_id is not None:
                        self.messages_cache[conv_id] = msgs
                    if p_type in self.pending_responses:
                        self.response_payloads[p_type] = packet
                        self.pending_responses[p_type].set()

                # 4. Gói tin Chat mới từ Server (Broadcast tới UI kèm giải mã E2EE)
                elif p_type in (protocol.MSG_TYPE_CHAT, protocol.MSG_TYPE_FILE, protocol.MSG_TYPE_PRIVATE):
                    conv_id = packet.get("conversation_id")
                    raw_content = packet.get("content", "")
                    is_enc = packet.get("is_encrypted", False) or raw_content.startswith("[ENC:AES-256-GCM]")

                    if raw_content.startswith("[ENC:AES-256-GCM]"):
                        cipher_str = raw_content[len("[ENC:AES-256-GCM]"):]
                        display_content = protocol.decrypt_payload(cipher_str)
                        print(f"🔒 [E2EE AES-256-GCM] Đã giải mã tin nhắn: Cipher={cipher_str[:20]}... -> Plaintext='{display_content}'")
                    elif is_enc:
                        display_content = protocol.decrypt_payload(raw_content)
                    else:
                        display_content = raw_content

                    # Lưu file đính kèm/ảnh/audio nhận được vào media/ cục bộ của máy này
                    file_b64 = packet.get("file_data")
                    att_url = packet.get("attachment_url")
                    if file_b64 and att_url:
                        try:
                            rel_path = att_url.lstrip("/")
                            abs_target = os.path.join(BASE_DIR, rel_path)
                            os.makedirs(os.path.dirname(abs_target), exist_ok=True)
                            with open(abs_target, "wb") as f_out:
                                f_out.write(base64.b64decode(file_b64))
                        except Exception as e:
                            print(f"[!] Lỗi lưu file đính kèm cục bộ: {e}")

                    # Cập nhật xem trước trong danh sách hội thoại
                    txt = display_content or f"[{packet.get('file_name', 'Tệp tin')}]"
                    found = False
                    for c in self.conversations:
                        if c.get("id") == conv_id:
                            c["last_message"] = {
                                "preview": txt[:60],
                                "type": packet.get("message_type", "text"),
                                "time_ago": packet.get("timestamp", ""),
                            }
                            c["time_label"] = packet.get("timestamp", "")
                            found = True
                            break

                    # Nếu là cuộc hội thoại mới bắt đầu nhắn tin, tự động đưa vào danh sách Ưu tiên
                    if not found and conv_id:
                        s_name = packet.get("sender_name") or packet.get("sender", "Hội thoại")
                        self.conversations.insert(0, {
                            "id": conv_id,
                            "title": s_name,
                            "name": s_name,
                            "is_group": False,
                            "other_username": packet.get("sender", ""),
                            "avatar_url": packet.get("sender_avatar", ""),
                            "last_message": {
                                "preview": txt[:60],
                                "type": packet.get("message_type", "text"),
                                "time_ago": packet.get("timestamp", ""),
                            },
                            "time_label": packet.get("timestamp", ""),
                            "unread_count": 0,
                            "is_priority": True,
                        })

                    msg_mtype = packet.get("message_type")
                    fname_l = (packet.get("file_name") or packet.get("attachment_name") or "").lower()
                    if not msg_mtype or msg_mtype == "file" or (msg_mtype == "audio" and fname_l.endswith(".webm") and not fname_l.startswith("voice_") and "voice" not in fname_l):
                        if packet.get("is_image") or fname_l.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                            msg_mtype = "image"
                        elif fname_l.endswith((".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".m4v")) or (fname_l.endswith(".webm") and not fname_l.startswith("voice_") and "voice" not in fname_l):
                            msg_mtype = "video"
                        elif fname_l.endswith((".mp3", ".wav", ".ogg", ".m4a")) or (fname_l.endswith(".webm") and (fname_l.startswith("voice_") or "voice" in fname_l)):
                            msg_mtype = "audio"
                        elif p_type == protocol.MSG_TYPE_FILE:
                            msg_mtype = "file"
                        else:
                            msg_mtype = "text"

                    ui_msg = {
                        "id": packet.get("message_id") or packet.get("id") or int(time.time()),
                        "conversation_id": conv_id,
                        "sender_id": 0,
                        "sender_name": packet.get("sender_name") or packet.get("sender", "Bạn"),
                        "sender_avatar": packet.get("sender_avatar") or "",
                        "is_me": (packet.get("sender") == (self.current_user.get("username") if self.current_user else "")),
                        "message_type": msg_mtype,
                        "content": display_content,
                        "is_encrypted": is_enc,
                        "attachment_url": packet.get("attachment_url", ""),
                        "attachment_name": packet.get("file_name", ""),
                        "attachment_size": packet.get("file_size_str", ""),
                        "formatted_time": packet.get("timestamp", ""),
                        "created_at": datetime.datetime.now().isoformat(),
                        "is_recalled": False,
                        "reactions": [],
                        "call_duration": packet.get("call_duration", 0),
                        "call_status": packet.get("call_status", ""),
                        "formatted_duration": packet.get("formatted_duration", ""),
                        "code_language": packet.get("code_language", ""),
                    }
                    if conv_id not in self.messages_cache:
                        self.messages_cache[conv_id] = []
                    self.messages_cache[conv_id].append(ui_msg)

                    ui_event = {
                        "type": "chat_message",
                        "message": ui_msg
                    }
                    self._broadcast_to_ui(ui_event)
                    # Không gửi lại packet thô chưa giải mã ra UI WebSocket

                # 5. Gói tin Đang soạn tin nhắn (Typing Indicator)
                elif p_type in (protocol.MSG_TYPE_TYPING, "typing"):
                    self._broadcast_to_ui(packet)

                # 6. Gói tin Thả biểu cảm cảm xúc (Reactions)
                elif p_type in (protocol.MSG_TYPE_REACTION, "reaction_update"):
                    conv_id = packet.get("conversation_id")
                    msg_id = packet.get("message_id")
                    if conv_id in self.messages_cache and msg_id:
                        for m in self.messages_cache[conv_id]:
                            try:
                                if int(m.get("id", 0)) == int(msg_id):
                                    m["reactions"] = packet.get("reactions", [])
                                    break
                            except Exception:
                                pass
                    self._broadcast_to_ui(packet)

                # 7. Gói tin Thu hồi tin nhắn (Message Recalled)
                elif p_type in (protocol.MSG_TYPE_RECALL, "message_recalled"):
                    conv_id = packet.get("conversation_id")
                    msg_id = packet.get("message_id")
                    if conv_id in self.messages_cache:
                        for m in self.messages_cache[conv_id]:
                            if m.get("id") == msg_id:
                                m["is_recalled"] = True
                                m["content"] = "Tin nhắn đã được thu hồi"
                                break
                    self._broadcast_to_ui(packet)

                # 8. Gói tin Nhịp tim Pong (Phản hồi Heartbeat Ping)
                elif p_type in (protocol.MSG_TYPE_PONG, "pong"):
                    self.last_pong_time = time.time()
                    self._broadcast_to_ui({
                        "type": "pong",
                        "client_timestamp": packet.get("client_timestamp")
                    })

                # 8.1 Gói tin sự kiện Lời mời kết bạn thời gian thực
                elif p_type in ("friend_request_received", "friend_request_accepted"):
                    self._broadcast_to_ui(packet)

                # 8.2 Gói tin cập nhật thông tin người dùng / ảnh đại diện từ máy khác
                elif p_type == "USER_UPDATE":
                    u_info = packet.get("user", {})
                    u_name = u_info.get("username")
                    if u_name:
                        for c in self.contacts:
                            if c.get("username") == u_name:
                                c["display_name"] = u_info.get("display_name", c.get("display_name"))
                                c["avatar_url"] = u_info.get("avatar_url", c.get("avatar_url"))
                                c["phone"] = u_info.get("phone", c.get("phone", ""))
                        for conv in self.conversations:
                            if conv.get("other_username") == u_name:
                                conv["title"] = u_info.get("display_name", conv.get("title"))
                                conv["avatar_url"] = u_info.get("avatar_url", conv.get("avatar_url"))
                    self._broadcast_to_ui({
                        "type": "user_update",
                        "user": u_info
                    })

                # 8.3 Gói tin Ghim tin nhắn thời gian thực
                elif p_type in ("message_pinned",):
                    conv_id = packet.get("conversation_id")
                    p_info = packet.get("pinned_message")
                    for c in self.conversations:
                        if c.get("id") == conv_id:
                            c["pinned_message"] = p_info
                            break
                    self._broadcast_to_ui(packet)

                # 8.4 Gói tin Nhóm chat mới được tạo (Group Chat Realtime Notification)
                elif p_type in ("conversation_created",):
                    conv = packet.get("conversation")
                    if conv and not any(c.get("id") == conv.get("id") for c in self.conversations):
                        self.conversations.insert(0, conv)
                    self._broadcast_to_ui(packet)

                # 8.5 Gói tin Cập nhật nhóm chat (Group Updated Realtime Notification)
                elif p_type in ("group_updated",):
                    conv_info = packet.get("conversation", {})
                    conv_id = conv_info.get("id") or packet.get("conversation_id")
                    for c in self.conversations:
                        if c.get("id") == conv_id:
                            c.update(conv_info)
                            break
                    self._broadcast_to_ui(packet)

                # 8.6 Gói tin Xóa khỏi nhóm hoặc Giải tán nhóm (Group Removed / Disbanded)
                elif p_type in ("group_removed", "group_disbanded"):
                    conv_id = packet.get("conversation_id")
                    self.conversations = [c for c in self.conversations if c.get("id") != conv_id]
                    self._broadcast_to_ui(packet)

                # 8.7 Gói tin Đã xem tin nhắn (Read Receipt)
                elif p_type in ("read_receipt", protocol.MSG_TYPE_READ_RECEIPT):
                    conv_id = packet.get("conversation_id")
                    u_id = packet.get("user_id")
                    u_name = packet.get("sender") or packet.get("username")
                    last_id = packet.get("last_read_message_id", 0)
                    for c in self.conversations:
                        if c.get("id") == conv_id and "members" in c:
                            for m in c["members"]:
                                if m.get("id") == u_id or m.get("username") == u_name:
                                    m["last_read_message_id"] = max(m.get("last_read_message_id", 0), last_id)
                                    break
                    self._broadcast_to_ui(packet)

                # 8.8 Gói tin Báo hiệu cuộc gọi WebRTC Voice/Video P2P (Call Signaling)
                elif p_type in ("webrtc_signal", protocol.MSG_TYPE_CALL_SIGNAL):
                    self._broadcast_to_ui(packet)

                # 9. Gói tin danh sách người dùng online
                elif p_type == protocol.MSG_TYPE_USER_LIST:
                    online_users = packet.get("users", [])
                    for contact in self.contacts:
                        contact["is_online"] = contact.get("username") in online_users
                    self._broadcast_to_ui(packet)

                # 10. Gói tin thông báo hệ thống / Call Signaling
                elif p_type in (protocol.MSG_TYPE_SYSTEM, protocol.MSG_TYPE_CALL_REQ, protocol.MSG_TYPE_CALL_RESP, protocol.MSG_TYPE_CALL_END):
                    self._broadcast_to_ui(packet)

            except Exception as e:
                break

        self.is_connected = False
        print("[!] Đã ngắt kết nối với TCP Socket Server.")
        if not self.should_stop and not self.is_reconnecting:
            self.is_reconnecting = True
            threading.Thread(target=self._auto_reconnect_loop, daemon=True).start()

    def _broadcast_to_ui(self, packet: dict):
        """Chuyển tiếp gói tin nhận được từ TCP Socket tới giao diện UI cục bộ."""
        payload_str = json.dumps(packet)
        with self.ws_lock:
            disconnected = []
            for ws in self.local_ws_clients:
                try:
                    ws.send(payload_str)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                self.local_ws_clients.remove(ws)


# ==============================================================================
# MÁY CHỦ GIAO DIỆN CỤC BỘ (LOCAL HTTP ADAPTER ON 127.0.0.1)
# ==============================================================================
class LocalUIRequestHandler(http.server.SimpleHTTPRequestHandler):
    client_bridge: ZaloTCPClient = None
    ws_port: int = 48081

    def log_message(self, format, *args):
        pass  # Tắt log HTTP nội bộ để console luôn sạch đẹp

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Trang Đăng nhập & Đăng ký
        if path == "/auth/" or path == "/auth":
            self.serve_html_file("templates/auth.html")
            return

        # 2. Trang Chat chính
        elif path == "/" or path == "/index.html":
            self.serve_html_file("templates/index.html")
            return

        # 3. Phục vụ tài nguyên tĩnh (Static CSS, JS, Images, Icons)
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = os.path.join(BASE_DIR, "static", rel_path)
            self.serve_static_file(file_path)
            return

        # 4. Phục vụ tệp tải lên (Media Uploads / Avatars / Files)
        elif path.startswith("/media/"):
            rel_path = path[len("/media/"):]
            file_path = os.path.join(BASE_DIR, "media", rel_path)
            self.serve_static_file(file_path)
            return

        # 5. API Kiểm tra phiên đăng nhập hiện tại
        elif path == "/api/me/":
            user = self.client_bridge.current_user
            data = {"authenticated": bool(user), "user": user}
            self.send_json(data)
            return

        # 6. API Danh sách Hội thoại
        elif path == "/api/conversations/":
            cleaned = []
            for c in self.client_bridge.conversations:
                item = dict(c)
                title = item.get("title") or item.get("name") or "Hội thoại"
                item["title"] = title
                item["name"] = title
                if not isinstance(item.get("last_message"), dict):
                    item["last_message"] = {
                        "preview": str(item.get("last_message") or "Bắt đầu cuộc trò chuyện"),
                        "type": "text"
                    }
                cleaned.append(item)
            self.send_json(cleaned)
            return

        # 7.1 API Đồng bộ tin nhắn mới (Fallback khi WebSocket gặp sự cố mạng)
        elif path.startswith("/api/conversations/") and "/sync/" in path:
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            after_id_str = query.get("after_id", ["0"])[0]
            try:
                after_id = int(after_id_str)
            except ValueError:
                after_id = 0

            all_msgs = self.client_bridge.messages_cache.get(conv_id, [])
            new_msgs = [m for m in all_msgs if m.get("id", 0) > after_id]
            for m in new_msgs:
                raw_c = m.get("content", "")
                if raw_c.startswith("[ENC:AES-256-GCM]"):
                    m["is_encrypted"] = True
                    cipher_str = raw_c[len("[ENC:AES-256-GCM]"):]
                    m["content"] = protocol.decrypt_payload(cipher_str)
                elif m.get("is_encrypted") and raw_c.startswith("[ENC:"):
                    cipher_str = raw_c.split("]", 1)[-1] if "]" in raw_c else raw_c
                    m["content"] = protocol.decrypt_payload(cipher_str)
            self.send_json(new_msgs)
            return

        # 7.2 API Tìm kiếm tin nhắn trong hội thoại
        elif path.startswith("/api/conversations/") and "/search/" in path:
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            q_str = query.get("q", [""])[0].strip().lower()
            all_msgs = self.client_bridge.messages_cache.get(conv_id, [])
            if not all_msgs and conv_id:
                pkt = {"type": protocol.MSG_TYPE_LOAD_HISTORY, "conversation_id": conv_id}
                ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_HISTORY_ACK, timeout=4.0)
                all_msgs = ack.get("messages", []) if ack else []
            matched = []
            for m in all_msgs:
                c_txt = (m.get("content") or "").lower()
                att_txt = (m.get("attachment_name") or "").lower()
                if q_str in c_txt or q_str in att_txt:
                    matched.append(m)
            self.send_json(matched)
            return

        # 7.3 API Lịch sử tin nhắn một cuộc trò chuyện (Truy vấn qua TCP Socket)
        elif path.startswith("/api/conversations/") and path.endswith("/messages/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 4 and parts[2].isdigit():
                conv_id = int(parts[2])
                # Gửi gói tin LOAD_HISTORY qua TCP Socket tới server.py:5555
                pkt = {"type": protocol.MSG_TYPE_LOAD_HISTORY, "conversation_id": conv_id}
                ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_HISTORY_ACK, timeout=4.0)
                msgs = ack.get("messages", []) if ack else self.client_bridge.messages_cache.get(conv_id, [])
                for m in msgs:
                    raw_c = m.get("content", "")
                    if raw_c.startswith("[ENC:AES-256-GCM]"):
                        m["is_encrypted"] = True
                        cipher_str = raw_c[len("[ENC:AES-256-GCM]"):]
                        m["content"] = protocol.decrypt_payload(cipher_str)
                    elif m.get("is_encrypted") and raw_c.startswith("[ENC:"):
                        cipher_str = raw_c.split("]", 1)[-1] if "]" in raw_c else raw_c
                        m["content"] = protocol.decrypt_payload(cipher_str)
                self.send_json(msgs)
                return
            self.send_json([])
            return

        # 7.4 API Lấy thông tin 1 Hội thoại (Kèm media & files cho sidebar phải)
        elif path.startswith("/api/conversations/") and len([p for p in path.split("/") if p]) == 3:
            parts = [p for p in path.split("/") if p]
            if parts[2].isdigit():
                conv_id = int(parts[2])
                conv = next((c for c in self.client_bridge.conversations if c.get("id") == conv_id), None)
                if conv:
                    c_copy = dict(conv)
                    c_title = c_copy.get("title") or c_copy.get("name") or "Hội thoại"
                    c_copy["title"] = c_title
                    c_copy["name"] = c_title
                    if "members" not in c_copy:
                        curr_u = self.client_bridge.current_user or {}
                        c_copy["members"] = [
                            {
                                "id": 1,
                                "username": curr_u.get("username", "user"),
                                "display_name": curr_u.get("display_name", "Tôi"),
                                "avatar_url": curr_u.get("avatar_url", ""),
                                "role": "admin",
                                "is_online": True,
                            }
                        ]
                    if "shared_media" not in c_copy or not c_copy["shared_media"]:
                        c_copy["shared_media"] = [
                            {
                                "id": m["id"],
                                "type": m.get("message_type", "image"),
                                "url": m.get("attachment_url", ""),
                                "name": m.get("attachment_name") or m.get("content", ""),
                                "sender": m.get("sender_name", ""),
                                "created_at": m.get("formatted_time", "")
                            }
                            for m in self.client_bridge.messages_cache.get(conv_id, [])
                            if m.get("message_type") in ("image", "video", "audio") and m.get("attachment_url")
                        ]
                    if "shared_files" not in c_copy or not c_copy["shared_files"]:
                        c_copy["shared_files"] = [
                            {
                                "id": m["id"],
                                "name": m.get("attachment_name") or "Tệp tin",
                                "size": m.get("attachment_size") or "0 B",
                                "url": m.get("attachment_url", ""),
                                "sender": m.get("sender_name", ""),
                                "created_at": m.get("formatted_time", "")
                            }
                            for m in self.client_bridge.messages_cache.get(conv_id, [])
                            if m.get("message_type") == "file" and m.get("attachment_url")
                        ]
                    self.send_json(c_copy)
                    return
            self.send_json({"error": "Không tìm thấy hội thoại"}, status=404)
            return

        # 8.1 API Tìm kiếm người dùng bằng Số điện thoại (Zalo Web Search by Phone)
        elif path == "/api/users/search_by_phone/":
            phone_val = query.get("phone", [""])[0].strip()
            pkt = {
                "type": protocol.MSG_TYPE_SEARCH_USER,
                "phone": phone_val,
                "query": phone_val,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_SEARCH_USER_ACK, timeout=5.0)
            if ack:
                self.send_json(ack)
            else:
                self.send_json({"status": "not_found", "message": "Không tìm thấy người dùng"}, status=404)
            return

        # 8.2 API Tìm kiếm người dùng tổng quát
        elif path == "/api/users/search/":
            q_val = query.get("q", [""])[0].strip()
            pkt = {
                "type": protocol.MSG_TYPE_SEARCH_USER,
                "query": q_val,
                "phone": q_val,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_SEARCH_USER_ACK, timeout=5.0)
            if ack and ack.get("users"):
                self.send_json(ack.get("users"))
            elif ack and ack.get("status") == "found" and ack.get("user"):
                self.send_json([ack.get("user")])
            else:
                self.send_json([])
            return

        # 8.3 API Lời mời kết bạn đang chờ (Incoming Friend Requests)
        elif path == "/api/friends/requests/":
            pkt = {"type": protocol.MSG_TYPE_LOAD_CONTACTS}
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_CONTACTS_ACK, timeout=4.0)
            reqs = ack.get("friend_requests", []) if ack else []
            self.send_json(reqs)
            return

        # 9. API Danh bạ bạn bè
        elif path in ("/api/contacts/", "/api/friends/"):
            pkt = {"type": protocol.MSG_TYPE_LOAD_CONTACTS}
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_CONTACTS_ACK, timeout=4.0)
            contacts = ack.get("contacts", []) if ack else self.client_bridge.contacts
            self.send_json(contacts)
            return

        # 10. API Mở Cloud của tôi (My Cloud Storage qua Socket TCP)
        elif path == "/api/cloud/":
            pkt = {"type": protocol.MSG_TYPE_GET_CLOUD}
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_CLOUD_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                c_data = ack.get("conversation")
                if c_data and not any(c.get("id") == c_data.get("id") for c in self.client_bridge.conversations):
                    self.client_bridge.conversations.insert(0, c_data)
                self.send_json({
                    "id": ack.get("id"),
                    "title": ack.get("title", "Cloud của tôi"),
                    "is_cloud": True,
                    "avatar_url": ack.get("avatar_url", ""),
                    "storage_used_bytes": ack.get("storage_used_bytes", 0),
                    "storage_used_mb": ack.get("storage_used_mb", 0),
                    "storage_limit_mb": ack.get("storage_limit_mb", 1024),
                    "storage_percent": ack.get("storage_percent", 0),
                })
            else:
                self.send_json({"error": "Không thể mở Cloud của tôi"}, status=500)
            return

        # 11. API Quản lý công việc To-do / Tasks (Qua Socket TCP)
        elif path == "/api/tasks/":
            pkt = {"type": protocol.MSG_TYPE_TASK_OP, "action": "list"}
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_TASK_OP_ACK, timeout=5.0)
            tasks = ack.get("tasks", []) if ack else []
            self.send_json(tasks)
            return

        # Fallback file không tìm thấy
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. API Đăng nhập (Chuyển tiếp qua TCP Socket LOGIN)
        if path == "/api/login/":
            body = self.read_json_body()
            username = body.get("username", "").strip()
            password = body.get("password", "").strip()

            pkt = {
                "type": protocol.MSG_TYPE_LOGIN,
                "username": username,
                "password": password,
            }
            # Gửi gói tin TCP tới server.py:5555
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_LOGIN_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.client_bridge.saved_credentials = (username, password)
                self.send_json({
                    "message": "Đăng nhập TCP thành công!",
                    "user": self.client_bridge.current_user
                })
            else:
                err = ack.get("message") if ack else "Máy chủ TCP không phản hồi!"
                self.send_json({"error": err}, status=401)
            return

        # 2. API Đăng ký tài khoản mới (Chuyển tiếp qua TCP Socket REGISTER)
        elif path == "/api/register/":
            # Hỗ trợ cả Multipart FormData và JSON
            ctype = self.headers.get("Content-Type", "")
            username = ""
            password = ""
            display_name = ""
            phone = ""

            if "application/json" in ctype:
                body = self.read_json_body()
                username = body.get("username", "").strip()
                password = body.get("password", "").strip()
                display_name = body.get("display_name", "").strip()
                phone = body.get("phone", "").strip()
            else:
                # FormData
                fields, _ = self.parse_form_data()
                username = fields.get("username", "").strip()
                password = fields.get("password", "").strip()
                display_name = fields.get("display_name", "").strip()
                phone = fields.get("phone", "").strip()

            pkt = {
                "type": protocol.MSG_TYPE_REGISTER,
                "username": username,
                "password": password,
                "display_name": display_name or username,
                "phone": phone
            }
            # Gửi gói tin TCP tới server.py:5555
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_REGISTER_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.client_bridge.saved_credentials = (username, password)
                # Tự động đăng nhập sau khi đăng ký
                login_pkt = {"type": protocol.MSG_TYPE_LOGIN, "username": username, "password": password}
                login_ack = self.client_bridge.send_and_wait(login_pkt, protocol.MSG_TYPE_LOGIN_ACK, timeout=4.0)
                user = self.client_bridge.current_user or {"username": username, "display_name": display_name or username}
                self.send_json({"message": "Đăng ký thành công!", "user": user}, status=201)
            else:
                err = ack.get("message") if ack else "Máy chủ TCP không phản hồi!"
                self.send_json({"error": err}, status=400)
            return

        # 3. API Đăng xuất
        elif path == "/api/logout/":
            self.client_bridge.current_user = None
            self.client_bridge.saved_credentials = None
            self.send_json({"message": "Đã đăng xuất"})
            return

        # 4. API Gửi tin nhắn văn bản hoặc tệp tin (Mã hóa E2EE AES-256-GCM hoặc Phân mảnh File 64KB)
        elif path.startswith("/api/conversations/") and path.endswith("/send/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 4 and parts[2].isdigit()) else None

            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" in ctype:
                fields, files = self.parse_form_data()
                mtype = fields.get("message_type") or fields.get("type", "text")
                content = fields.get("content", "").strip()

                file_item = files.get("attachment") or files.get("file")
                if file_item and file_item.get("filename"):
                    fname = file_item["filename"]
                    fdata = file_item["data"]
                    is_img = (mtype == "image") or fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))
                    is_video = (mtype == "video") or fname.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".m4v")) or (fname.lower().endswith(".webm") and not fname.lower().startswith("voice_") and "voice" not in fname.lower())
                    is_audio = (mtype == "audio") or fname.lower().endswith((".mp3", ".wav", ".ogg", ".m4a")) or (fname.lower().endswith(".webm") and (fname.lower().startswith("voice_") or "voice" in fname.lower() or mtype == "audio"))
                    if is_img:
                        actual_mtype = "image"
                    elif is_video:
                        actual_mtype = "video"
                    elif is_audio:
                        actual_mtype = "audio"
                    else:
                        actual_mtype = "file"
                    sha256_hash = hashlib.sha256(fdata).hexdigest()

                    # Lưu file ngay tại máy client gửi vào media/ cục bộ
                    now = datetime.datetime.now()
                    rel_dir = os.path.join("attachments", now.strftime("%Y"), now.strftime("%m"))
                    abs_dir = os.path.join(BASE_DIR, "media", rel_dir)
                    os.makedirs(abs_dir, exist_ok=True)
                    safe_fname = os.path.basename(fname)
                    local_fpath = os.path.join(abs_dir, safe_fname)
                    try:
                        with open(local_fpath, "wb") as f_out:
                            f_out.write(fdata)
                    except Exception:
                        pass
                    saved_rel_url = f"/media/{rel_dir}/{safe_fname}"

                    # Phân mảnh 64KB nếu kích thước lớn (> 64KB và là tệp tài liệu)
                    if len(fdata) > protocol.CHUNK_SIZE and not is_img and not is_video and not is_audio:
                        transfer_id = f"xfer_{uuid.uuid4().hex[:8]}"
                        total_chunks = (len(fdata) + protocol.CHUNK_SIZE - 1) // protocol.CHUNK_SIZE

                        # Gói mở đầu FILE_START
                        self.client_bridge.send_tcp_packet({
                            "type": protocol.MSG_TYPE_FILE_START,
                            "transfer_id": transfer_id,
                            "conversation_id": conv_id,
                            "file_name": fname,
                            "file_size": len(fdata),
                            "total_chunks": total_chunks,
                            "sha256": sha256_hash,
                            "is_image": is_img,
                            "message_type": actual_mtype,
                            "content": content
                        })

                        def send_chunks_worker():
                            for idx in range(total_chunks):
                                c_bytes = fdata[idx * protocol.CHUNK_SIZE : (idx + 1) * protocol.CHUNK_SIZE]
                                self.client_bridge.send_tcp_packet({
                                    "type": protocol.MSG_TYPE_FILE_CHUNK,
                                    "transfer_id": transfer_id,
                                    "chunk_index": idx,
                                    "total_chunks": total_chunks,
                                    "chunk_data": base64.b64encode(c_bytes).decode("utf-8")
                                })
                                pct = int((idx + 1) / total_chunks * 100)
                                self.client_bridge._broadcast_to_ui({
                                    "type": "file_transfer_progress",
                                    "transfer_id": transfer_id,
                                    "file_name": fname,
                                    "progress": pct,
                                    "sent_bytes": min((idx + 1) * protocol.CHUNK_SIZE, len(fdata)),
                                    "total_bytes": len(fdata)
                                })
                                time.sleep(0.005)

                            # Gói kết thúc FILE_COMPLETE
                            self.client_bridge.send_tcp_packet({
                                "type": protocol.MSG_TYPE_FILE_COMPLETE,
                                "transfer_id": transfer_id,
                                "conversation_id": conv_id,
                                "file_name": fname,
                                "file_size": len(fdata),
                                "sha256": sha256_hash,
                                "is_image": is_img,
                                "message_type": actual_mtype,
                                "content": content
                            })

                        threading.Thread(target=send_chunks_worker, daemon=True).start()
                    else:
                        # Gửi file trực tiếp kèm Base64 để bên kia lưu và hiển thị tức thì
                        b64_data = base64.b64encode(fdata).decode("utf-8")
                        pkt = {
                            "type": protocol.MSG_TYPE_FILE,
                            "conversation_id": conv_id,
                            "file_name": fname,
                            "file_size": len(fdata),
                            "file_data": b64_data,
                            "attachment_url": saved_rel_url,
                            "is_image": is_img,
                            "message_type": actual_mtype,
                            "content": content,
                            "sha256": sha256_hash,
                        }
                        self.client_bridge.send_tcp_packet(pkt)
                elif content:
                    # Mã hóa đầu cuối (E2EE) bằng AES-256-GCM trước khi truyền qua Socket TCP
                    enc_text = protocol.encrypt_payload(content)
                    pkt = {
                        "type": protocol.MSG_TYPE_CHAT,
                        "conversation_id": conv_id,
                        "content": f"[ENC:AES-256-GCM]{enc_text}",
                        "is_encrypted": True,
                        "cipher_algo": "AES-256-GCM"
                    }
                    self.client_bridge.send_tcp_packet(pkt)
            else:
                body = self.read_json_body()
                content = body.get("content", "").strip()
                if content:
                    enc_text = protocol.encrypt_payload(content)
                    pkt = {
                        "type": protocol.MSG_TYPE_CHAT,
                        "conversation_id": conv_id,
                        "content": f"[ENC:AES-256-GCM]{enc_text}",
                        "is_encrypted": True,
                        "cipher_algo": "AES-256-GCM"
                    }
                    self.client_bridge.send_tcp_packet(pkt)

            self.send_json({"status": "OK", "message": "Đã gửi qua TCP Socket"})
            return

        # 5. API Thả biểu cảm cảm xúc (Chuyển tiếp qua TCP Socket REACTION)
        elif path.startswith("/api/messages/") and path.endswith("/react/"):
            parts = [p for p in path.split("/") if p]
            msg_id = int(parts[2]) if (len(parts) >= 4 and parts[2].isdigit()) else None
            body = self.read_json_body()
            emoji = body.get("emoji", "").strip()
            conv_id = body.get("conversation_id")
            if msg_id and emoji:
                pkt = {
                    "type": protocol.MSG_TYPE_REACTION,
                    "message_id": msg_id,
                    "emoji": emoji,
                    "conversation_id": conv_id,
                }
                self.client_bridge.send_tcp_packet(pkt)
            self.send_json({"status": "OK"})
            return

        # 6. API Thu hồi tin nhắn (Chuyển tiếp qua TCP Socket RECALL)
        elif path.startswith("/api/messages/") and path.endswith("/recall/"):
            parts = [p for p in path.split("/") if p]
            msg_id = int(parts[2]) if (len(parts) >= 4 and parts[2].isdigit()) else None
            body = self.read_json_body()
            conv_id = body.get("conversation_id")
            if msg_id:
                pkt = {
                    "type": protocol.MSG_TYPE_RECALL,
                    "message_id": msg_id,
                    "conversation_id": conv_id,
                }
                self.client_bridge.send_tcp_packet(pkt)
            self.send_json({"status": "OK"})
            return

        # 7. API Tạo hội thoại 1-1 mới hoặc Tạo nhóm chat (Chuyển tiếp qua TCP Socket CREATE_CONV)
        elif path == "/api/conversations/create/":
            body = self.read_json_body()
            is_group = body.get("is_group", False)
            group_name = body.get("name", "").strip()
            members = body.get("members", [])
            target_user_id = body.get("user_id") or body.get("target_user_id")
            pkt = {
                "type": protocol.MSG_TYPE_CREATE_CONV,
                "is_group": is_group,
                "name": group_name,
                "members": members,
                "target_user_id": target_user_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_CREATE_CONV_ACK, timeout=6.0)
            if ack and ack.get("status") == "OK":
                conv = ack.get("conversation", {})
                if not any(c.get("id") == conv.get("id") for c in self.client_bridge.conversations):
                    self.client_bridge.conversations.insert(0, conv)
                self.send_json(conv, status=201)
            else:
                self.send_json({"error": ack.get("message") if ack else "Lỗi tạo hội thoại"}, status=400)
            return

        # 7.1 API Ghim tin nhắn / Bỏ ghim tin nhắn (Chuyển tiếp qua TCP Socket PIN_MESSAGE)
        elif path.startswith("/api/conversations/") and path.endswith("/pin_message/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            msg_id = body.get("message_id")
            pkt = {
                "type": protocol.MSG_TYPE_PIN_MESSAGE,
                "conversation_id": conv_id,
                "message_id": msg_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_PIN_MESSAGE_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                pinned_info = ack.get("pinned_message")
                for c in self.client_bridge.conversations:
                    if c.get("id") == conv_id:
                        c["pinned_message"] = pinned_info
                        break
                self.send_json({
                    "message": "Đã ghim tin nhắn lên đầu cuộc trò chuyện!" if msg_id else "Đã bỏ ghim tin nhắn.",
                    "pinned_message": pinned_info,
                })
            else:
                self.send_json({"error": "Không thể ghim tin nhắn"}, status=400)
            return

        # 7.2 API Ghim hội thoại / Tắt thông báo / Ưu tiên (Chuyển tiếp qua TCP Socket CONV_ACTION)
        elif path.startswith("/api/conversations/") and (path.endswith("/toggle_pin/") or path.endswith("/toggle_mute/") or path.endswith("/toggle_priority/")):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            action = parts[-1]  # "toggle_pin", "toggle_mute", "toggle_priority"
            pkt = {
                "type": protocol.MSG_TYPE_CONV_ACTION,
                "conversation_id": conv_id,
                "action": action,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_CONV_ACTION_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                for c in self.client_bridge.conversations:
                    if c.get("id") == conv_id:
                        if action == "toggle_pin":
                            c["is_pinned"] = ack.get("is_pinned", False)
                        elif action == "toggle_mute":
                            c["is_muted"] = ack.get("is_muted", False)
                        elif action == "toggle_priority":
                            c["is_priority"] = ack.get("is_priority", True)
                        break
                self.send_json(ack)
            else:
                self.send_json({"error": ack.get("message") if ack else "Lỗi thao tác hội thoại"}, status=400)
            return

        # 8. API Gửi lời mời kết bạn (Chuyển tiếp qua TCP Socket FRIEND_REQ)
        elif path == "/api/friends/request/":
            body = self.read_json_body()
            target_user_id = body.get("user_id") or body.get("target_user_id")
            pkt = {
                "type": protocol.MSG_TYPE_FRIEND_REQ,
                "target_user_id": target_user_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_FRIEND_REQ_ACK, timeout=5.0)
            if ack:
                self.send_json(ack)
            else:
                self.send_json({"status": "error", "message": "Máy chủ TCP không phản hồi"}, status=500)
            return

        # 9. API Phản hồi lời mời kết bạn Đồng ý / Từ chối (Chuyển tiếp qua TCP Socket FRIEND_RESP)
        elif path == "/api/friends/respond/":
            body = self.read_json_body()
            request_id = body.get("request_id")
            action = body.get("action", "accept")
            pkt = {
                "type": protocol.MSG_TYPE_FRIEND_RESP,
                "request_id": request_id,
                "action": action,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_FRIEND_RESP_ACK, timeout=5.0)
            if ack:
                self.send_json(ack)
            else:
                self.send_json({"status": "error", "message": "Máy chủ TCP không phản hồi"}, status=500)
            return

        # 10. API Cập nhật thông tin cá nhân & Ảnh đại diện (Chuyển tiếp qua TCP Socket UPDATE_PROFILE)
        elif path == "/api/profile/update/":
            ctype = self.headers.get("Content-Type", "")
            display_name = ""
            bio = ""
            phone = ""
            gender = "nam"
            avatar_b64 = ""
            avatar_fname = ""

            if "multipart/form-data" in ctype:
                fields, files = self.parse_form_data()
                display_name = fields.get("display_name", "").strip()
                bio = fields.get("bio", "").strip()
                phone = fields.get("phone", "").strip()
                gender = fields.get("gender", "nam").strip()

                avatar_item = files.get("avatar")
                if avatar_item and avatar_item.get("data") and avatar_item.get("filename"):
                    avatar_fname = avatar_item["filename"]
                    avatar_bytes = avatar_item["data"]
                    avatar_b64 = base64.b64encode(avatar_bytes).decode("utf-8")

                    # Lưu file ảnh đại diện vào thư mục media/avatars/ cục bộ
                    safe_name = f"avatar_{int(time.time())}_{os.path.basename(avatar_fname)}"
                    abs_av_dir = os.path.join(BASE_DIR, "media", "avatars")
                    os.makedirs(abs_av_dir, exist_ok=True)
                    try:
                        with open(os.path.join(abs_av_dir, safe_name), "wb") as f_out:
                            f_out.write(avatar_bytes)
                    except Exception as e:
                        print(f"[!] Lỗi lưu avatar cục bộ: {e}")
            else:
                body = self.read_json_body()
                display_name = body.get("display_name", "").strip()
                bio = body.get("bio", "").strip()
                phone = body.get("phone", "").strip()
                gender = body.get("gender", "nam").strip()

            pkt = {
                "type": protocol.MSG_TYPE_UPDATE_PROFILE,
                "display_name": display_name,
                "bio": bio,
                "phone": phone,
                "gender": gender,
                "avatar_data": avatar_b64,
                "avatar_name": avatar_fname,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_UPDATE_PROFILE_ACK, timeout=6.0)
            if ack and ack.get("status") == "OK":
                updated_user = ack.get("user") or self.client_bridge.current_user
                if updated_user:
                    self.client_bridge.current_user = updated_user
                self.send_json({
                    "message": "Cập nhật hồ sơ và ảnh đại diện thành công!",
                    "user": updated_user
                })
            else:
                err = ack.get("message") if ack else "Máy chủ TCP không phản hồi khi cập nhật hồ sơ!"
                self.send_json({"error": err}, status=400)
            return

        # 11. API Thêm thành viên vào nhóm (GROUP_ADD_MEMBER)
        elif path.startswith("/api/conversations/") and path.endswith("/add_member/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            user_id = body.get("user_id")
            pkt = {
                "type": protocol.MSG_TYPE_GROUP_ADD_MEMBER,
                "conversation_id": conv_id,
                "user_id": user_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_GROUP_ADD_MEMBER_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.send_json({
                    "message": ack.get("message", "Đã thêm thành viên vào nhóm!"),
                    "user_id": user_id
                })
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể thêm thành viên"}, status=400)
            return

        # 12. API Xóa thành viên khỏi nhóm (GROUP_REMOVE_MEMBER)
        elif path.startswith("/api/conversations/") and path.endswith("/remove_member/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            user_id = body.get("user_id")
            pkt = {
                "type": protocol.MSG_TYPE_GROUP_REMOVE_MEMBER,
                "conversation_id": conv_id,
                "user_id": user_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_GROUP_REMOVE_MEMBER_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.send_json({"message": ack.get("message", "Đã xóa thành viên khỏi nhóm!")})
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể xóa thành viên"}, status=400)
            return

        # 13. API Rời khỏi nhóm chat (GROUP_LEAVE)
        elif path.startswith("/api/conversations/") and path.endswith("/leave/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            pkt = {
                "type": protocol.MSG_TYPE_GROUP_LEAVE,
                "conversation_id": conv_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_GROUP_LEAVE_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.client_bridge.conversations = [c for c in self.client_bridge.conversations if c.get("id") != conv_id]
                self.send_json({"message": ack.get("message", "Đã rời khỏi nhóm!")})
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể rời nhóm"}, status=400)
            return

        # 14. API Giải tán nhóm chat (GROUP_DISBAND)
        elif path.startswith("/api/conversations/") and path.endswith("/disband/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            pkt = {
                "type": protocol.MSG_TYPE_GROUP_DISBAND,
                "conversation_id": conv_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_GROUP_DISBAND_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.client_bridge.conversations = [c for c in self.client_bridge.conversations if c.get("id") != conv_id]
                self.send_json({"message": ack.get("message", "Đã giải tán nhóm!")})
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể giải tán nhóm"}, status=400)
            return

        # 15. API Đổi tên & Ảnh đại diện nhóm (GROUP_UPDATE)
        elif path.startswith("/api/conversations/") and path.endswith("/update_group/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            ctype = self.headers.get("Content-Type", "")
            name_val = ""
            avatar_b64 = ""
            avatar_fname = ""

            if "multipart/form-data" in ctype:
                fields, files = self.parse_form_data()
                name_val = fields.get("name") or fields.get("title") or ""
                avatar_item = files.get("avatar")
                if avatar_item and avatar_item.get("data") and avatar_item.get("filename"):
                    avatar_fname = avatar_item["filename"]
                    avatar_b64 = base64.b64encode(avatar_item["data"]).decode("utf-8")
            else:
                body = self.read_json_body()
                name_val = body.get("name") or body.get("title") or ""

            pkt = {
                "type": protocol.MSG_TYPE_GROUP_UPDATE,
                "conversation_id": conv_id,
                "name": name_val,
                "avatar_data": avatar_b64,
                "avatar_name": avatar_fname,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_GROUP_UPDATE_ACK, timeout=6.0)
            if ack and ack.get("status") == "OK":
                for c in self.client_bridge.conversations:
                    if c.get("id") == conv_id:
                        if ack.get("title"):
                            c["title"] = ack["title"]
                            c["name"] = ack["title"]
                        if ack.get("avatar_url"):
                            c["avatar_url"] = ack["avatar_url"]
                        break
                self.send_json({
                    "message": ack.get("message", "Đã cập nhật thông tin nhóm!"),
                    "title": ack.get("title"),
                    "avatar_url": ack.get("avatar_url"),
                })
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể cập nhật nhóm"}, status=400)
            return

        # 16. API Phân quyền / Chuyển quyền Trưởng nhóm (GROUP_CHANGE_ROLE)
        elif path.startswith("/api/conversations/") and path.endswith("/change_role/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            user_id = body.get("user_id")
            role = body.get("role", "admin")
            pkt = {
                "type": protocol.MSG_TYPE_GROUP_CHANGE_ROLE,
                "conversation_id": conv_id,
                "user_id": user_id,
                "role": role,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_GROUP_CHANGE_ROLE_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                self.send_json({"message": ack.get("message", "Đã phân quyền thành công!")})
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể phân quyền"}, status=400)
            return

        # 17. API Chuyển tiếp tin nhắn (FORWARD_MESSAGE)
        elif path.startswith("/api/messages/") and path.endswith("/forward/"):
            parts = [p for p in path.split("/") if p]
            msg_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            conv_ids = body.get("conversation_ids", [])
            pkt = {
                "type": protocol.MSG_TYPE_FORWARD_MESSAGE,
                "message_id": msg_id,
                "conversation_ids": conv_ids,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_FORWARD_MESSAGE_ACK, timeout=6.0)
            if ack and ack.get("status") == "OK":
                self.send_json({
                    "message": ack.get("message", "Đã chuyển tiếp tin nhắn thành công!"),
                    "forwarded_count": ack.get("forwarded_count", 0),
                })
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể chuyển tiếp tin nhắn"}, status=400)
            return

        # 18. API Xóa tin nhắn ở phía tôi (DELETE_FOR_ME)
        elif path.startswith("/api/messages/") and path.endswith("/delete/"):
            parts = [p for p in path.split("/") if p]
            msg_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            pkt = {
                "type": protocol.MSG_TYPE_DELETE_FOR_ME,
                "message_id": msg_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_DELETE_FOR_ME_ACK, timeout=5.0)
            if ack and ack.get("status") == "OK":
                for conv_id, msgs in self.client_bridge.messages_cache.items():
                    self.client_bridge.messages_cache[conv_id] = [m for m in msgs if int(m.get("id", 0)) != int(msg_id)]
                self.send_json({
                    "message": "Đã xóa tin nhắn ở phía bạn.",
                    "id": msg_id
                })
            else:
                self.send_json({"error": ack.get("message") if ack else "Không thể xóa tin nhắn"}, status=400)
            return

        # 19. API Quản lý công việc To-Do Tasks (POST /api/tasks/)
        elif path == "/api/tasks/":
            body = self.read_json_body()
            pkt = {
                "type": protocol.MSG_TYPE_TASK_OP,
                **body
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_TASK_OP_ACK, timeout=5.0)
            tasks = ack.get("tasks", []) if ack else []
            self.send_json(tasks)
            return

        # 20. API Đánh dấu đã xem tin nhắn (POST /api/conversations/<id>/mark_read/)
        elif path.startswith("/api/conversations/") and path.endswith("/mark_read/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            last_msg_id = body.get("last_message_id")
            pkt = {
                "type": protocol.MSG_TYPE_READ_RECEIPT,
                "conversation_id": conv_id,
                "last_message_id": last_msg_id,
            }
            ack = self.client_bridge.send_and_wait(pkt, protocol.MSG_TYPE_READ_RECEIPT_ACK, timeout=4.0)
            self.send_json({
                "success": True,
                "last_read_message_id": ack.get("last_read_message_id") if ack else last_msg_id
            })
            return

        # 21. API Lưu lịch sử cuộc gọi (POST /api/conversations/<id>/log_call/)
        elif path.startswith("/api/conversations/") and path.endswith("/log_call/"):
            parts = [p for p in path.split("/") if p]
            conv_id = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
            body = self.read_json_body()
            pkt = {
                "type": "call_log",
                "conversation_id": conv_id,
                **body
            }
            self.client_bridge.send_tcp_packet(pkt)
            self.send_json({"status": "OK"})
            return

        self.send_json({"status": "OK"})

    def parse_form_data(self):
        """Đọc và giải mã form data (URL-encoded hoặc Multipart) thay cho module cgi ở Python 3.13+."""
        ctype = self.headers.get("Content-Type", "")
        clen = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(clen) if clen > 0 else b""
        fields = {}
        files = {}
        if "multipart/form-data" in ctype:
            raw_msg = f"Content-Type: {ctype}\r\n\r\n".encode("latin1", errors="replace") + raw_body
            msg = email.message_from_bytes(raw_msg)
            if msg.is_multipart():
                for part in msg.get_payload():
                    name = part.get_param("name", header="content-disposition")
                    filename = part.get_filename()
                    if filename:
                        files[name] = {
                            "filename": filename,
                            "data": part.get_payload(decode=True) or b"",
                        }
                    elif name:
                        payload = part.get_payload(decode=True)
                        fields[name] = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
        else:
            try:
                parsed = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="replace"))
                for k, v in parsed.items():
                    fields[k] = v[0] if v else ""
            except Exception:
                pass
        return fields, files

    def read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return {}

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def serve_html_file(self, rel_path: str):
        full_path = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(full_path):
            self.send_error(404, "File not found")
            return

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Thay thế các cú pháp Django template để chạy thuần trên máy khách
        content = content.replace("{% load static %}", "")
        content = content.replace("{% static '", "/static/")
        content = content.replace("{% static \"", "/static/")
        content = content.replace("' %}", "")
        content = content.replace("\" %}", "")
        content = content.replace("{% csrf_token %}", "<input type='hidden' name='csrfmiddlewaretoken' value='tcp_client_token'>")

        # Tiêm cổng WebSocket nội bộ vào trang để JS tự động kết nối
        ws_inject = f"<script>window.WS_PORT = {self.ws_port};</script>"
        content = content.replace("</head>", f"{ws_inject}\n</head>")

        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static_file(self, file_path: str):
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            self.send_error(404, "Static file not found")
            return

        # Xác định MIME type
        ctype = "application/octet-stream"
        if file_path.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif file_path.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif file_path.endswith(".png"):
            ctype = "image/png"
        elif file_path.endswith(".jpg") or file_path.endswith(".jpeg"):
            ctype = "image/jpeg"
        elif file_path.endswith(".svg"):
            ctype = "image/svg+xml"
        elif file_path.endswith(".ico"):
            ctype = "image/x-icon"
        elif file_path.endswith(".mp3"):
            ctype = "audio/mpeg"
        elif file_path.endswith(".mp4"):
            ctype = "video/mp4"
        elif file_path.endswith(".webm"):
            ctype = "video/webm"
        elif file_path.endswith(".mov"):
            ctype = "video/quicktime"
        elif file_path.endswith(".mkv"):
            ctype = "video/x-matroska"
        elif file_path.endswith(".avi"):
            ctype = "video/x-msvideo"
        elif file_path.endswith(".ogg") or file_path.endswith(".oga"):
            ctype = "audio/ogg"
        elif file_path.endswith(".wav"):
            ctype = "audio/wav"
        elif file_path.endswith(".webp"):
            ctype = "image/webp"
        elif file_path.endswith(".gif"):
            ctype = "image/gif"
        elif file_path.endswith(".pdf"):
            ctype = "application/pdf"

        with open(file_path, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)


# ==============================================================================
# HÀM KHỞI CHẠY CLIENT DESKTOP
# ==============================================================================
def find_chromium_browser():
    candidates = [
        # Linux
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/brave-browser",
        "/usr/bin/microsoft-edge",
        # Windows
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "brave"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def main():
    server_host = DEFAULT_SERVER_HOST
    server_port = DEFAULT_SERVER_PORT
    profile_num = "1"

    args = sys.argv[1:]
    if len(args) >= 1:
        first = args[0].strip()
        if "." in first or first.isalpha():
            server_host = first
            profile_num = args[1].strip() if len(args) >= 2 else "2"
        elif first.isdigit():
            profile_num = first
            if len(args) >= 2:
                server_host = args[1].strip()

    print("=" * 70)
    print("🚀 KHỞI ĐỘNG ZALO DESKTOP CLIENT (100% TCP SOCKET :5555)")
    print("=" * 70)
    print(f"  📡 Máy chủ Socket TCP: {server_host}:{server_port}")
    print(f"  👤 Profile người dùng: {profile_num}")
    print("=" * 70)

    # 1. Mở kết nối TCP Socket tới Server :5555
    bridge = ZaloTCPClient(server_host, server_port)
    connected = bridge.connect()
    if not connected:
        print("\n" + "!" * 70)
        print(f"❌ LỖI: Không thể kết nối tới Máy chủ TCP Socket ({server_host}:{server_port})!")
        print("👉 Vui lòng mở Terminal và khởi động Máy chủ trước:")
        print("   python3 server.py")
        print("!" * 70 + "\n")
        return

    # 2. Khởi tạo Local WebSocket Server (để đẩy dữ liệu TCP nhận được vào UI)
    ws_port = get_free_port(48100)
    def ws_handler(websocket):
        with bridge.ws_lock:
            bridge.local_ws_clients.add(websocket)
        try:
            for message in websocket:
                try:
                    data = json.loads(message)
                    bridge.send_tcp_packet(data)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            with bridge.ws_lock:
                bridge.local_ws_clients.discard(websocket)

    def run_ws():
        with ws_serve(ws_handler, "127.0.0.1", ws_port) as server:
            server.serve_forever()

    threading.Thread(target=run_ws, daemon=True).start()

    # 3. Khởi tạo Local HTTP Server (phục vụ giao diện Zalo PC cục bộ)
    http_port = get_free_port(48000)
    LocalUIRequestHandler.client_bridge = bridge
    LocalUIRequestHandler.ws_port = ws_port

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", http_port), LocalUIRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    target_url = f"http://127.0.0.1:{http_port}/auth/?logout=1"

    # 4. Mở cửa sổ Ứng dụng Desktop Zalo PC Native
    browser_bin = find_chromium_browser()
    if browser_bin:
        profile_dir = os.path.expanduser(f"~/.config/zalo_desktop_profile_{profile_num}")
        os.makedirs(profile_dir, exist_ok=True)
        # Dọn dẹp lock cũ nếu có
        for lk in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            try:
                os.remove(os.path.join(profile_dir, lk))
            except Exception:
                pass

        try:
            print(f"[*] Mở cửa sổ Zalo PC qua {os.path.basename(browser_bin)} (App Mode)...")
            cmd = [
                browser_bin,
                f"--app={target_url}",
                f"--user-data-dir={profile_dir}",
                "--window-size=1260,840",
                "--window-position=80,40",
                "--app-id=zalo-desktop-ltm",
                "--class=ZaloPC",
                "--autoplay-policy=no-user-gesture-required",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate,OptimizationHints,MediaRouter",
                "--disable-background-networking",
                "--disable-sync",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            t_start = time.time()
            proc.wait()
            # Nếu tiến trình thoát quá sớm (do Chrome chuyển sang session có sẵn), giữ bridge chạy để duy trì socket
            if time.time() - t_start < 2.0:
                print("[*] Cửa sổ Zalo PC đang mở trên màn hình...")
                while bridge.is_connected:
                    time.sleep(1)
            bridge.is_connected = False
            return
        except KeyboardInterrupt:
            print("\n[*] Đang đóng Zalo Desktop Client...")
            try:
                proc.terminate()
            except Exception:
                pass
            bridge.is_connected = False
            return
        except Exception as e:
            print(f"[!] Lỗi mở App Mode: {e}")

    # Fallback qua PyWebView
    try:
        import webview
        print("[*] Mở cửa sổ Desktop qua PyWebView...")
        window = webview.create_window(
            title=f"Zalo PC - Socket TCP 5555 ({server_host})",
            url=target_url,
            width=1240,
            height=820,
            resizable=True
        )
        webview.start()
        bridge.is_connected = False
        return
    except Exception as e:
        print(f"[!] Lỗi PyWebView: {e}")

    # Fallback cuối cùng
    import webbrowser
    print(f"[*] Mở Zalo trên trình duyệt mặc định: {target_url}")
    webbrowser.open(target_url)
    try:
        while bridge.is_connected:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
