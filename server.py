"""
server.py - TCP Chat Server Đa Luồng (Multi-threaded TCP Socket Server).

Quản lý các kết nối từ Client, điều phối tin nhắn công khai (Broadcast),
tin nhắn riêng (Private Message), cập nhật trạng thái người dùng Online.
Hỗ trợ event callbacks phục vụ Giao diện Đồ họa (Server GUI).
"""

import datetime
import socket
import sys
import threading
from typing import Callable

import protocol

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

        try:
            # 1. Bước bắt tay (Handshake / Join): Nhận gói tin JOIN đầu tiên
            first_packet = protocol.recv_packet(client_sock)
            if not first_packet or first_packet.get("type") != protocol.MSG_TYPE_JOIN:
                protocol.send_packet(client_sock, {
                    "type": protocol.MSG_TYPE_JOIN_ACK,
                    "status": "ERROR",
                    "message": "Gói tin đầu tiên phải là yêu cầu JOIN hợp lệ.",
                })
                client_sock.close()
                return

            req_name = first_packet.get("nickname", "").strip()

            # Kiểm tra tên người dùng
            with self.lock:
                if not req_name:
                    error_msg = "Nickname không được để trống."
                elif len(req_name) > 20:
                    error_msg = "Nickname không được vượt quá 20 ký tự."
                elif req_name in self.clients_by_name:
                    error_msg = f"Nickname '{req_name}' đã có người sử dụng. Hãy chọn tên khác."
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

                # Đăng ký nickname thành công
                nickname = req_name
                self.clients[client_sock] = nickname
                self.clients_by_name[nickname] = client_sock
                self.clients_info[nickname] = {
                    "nickname": nickname,
                    "ip": client_addr[0],
                    "port": client_addr[1],
                    "joined_at": self.get_timestamp(),
                }

            # Gửi xác nhận thành công về cho client
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
                "message": f"👉 [{nickname}] đã tham gia phòng chat.",
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
                    break  # Client đóng kết nối hoặc gặp lỗi mạng

                msg_type = packet.get("type")

                if msg_type == protocol.MSG_TYPE_CHAT:
                    content = packet.get("content", "").strip()
                    if content:
                        chat_packet = {
                            "type": protocol.MSG_TYPE_CHAT,
                            "sender": nickname,
                            "content": content,
                            "timestamp": self.get_timestamp(),
                        }
                        # Broadcast cho tất cả mọi người
                        self.broadcast(chat_packet)
                        self._log("CHAT", f"{nickname}: {content}")

                elif msg_type == protocol.MSG_TYPE_PRIVATE:
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
                        # Gửi cho người nhận
                        protocol.send_packet(target_sock, priv_packet)
                        # Gửi bản sao cho chính người gửi
                        protocol.send_packet(client_sock, priv_packet)
                        self._log("PRIVATE", f"{nickname} -> {target_user}: {content}")

                elif msg_type == protocol.MSG_TYPE_VOICE:
                    target_user = packet.get("target", "ALL").strip()
                    audio_data = packet.get("audio_data", "")
                    duration = packet.get("duration", 0)

                    if audio_data:
                        voice_packet = {
                            "type": protocol.MSG_TYPE_VOICE,
                            "sender": nickname,
                            "target": target_user,
                            "audio_data": audio_data,
                            "duration": duration,
                            "timestamp": self.get_timestamp(),
                        }
                        if target_user == "ALL" or not target_user:
                            self.broadcast(voice_packet)
                            self._log("VOICE", f"{nickname} gửi tin nhắn thoại tới Phòng Chung ({duration}s)")
                        else:
                            with self.lock:
                                target_sock = self.clients_by_name.get(target_user)
                            if target_sock:
                                protocol.send_packet(target_sock, voice_packet)
                                protocol.send_packet(client_sock, voice_packet)
                                self._log("VOICE", f"{nickname} -> {target_user}: Tin nhắn thoại ({duration}s)")
                            else:
                                protocol.send_packet(client_sock, {
                                    "type": protocol.MSG_TYPE_SYSTEM,
                                    "message": f"❌ Người dùng '{target_user}' đã offline.",
                                    "timestamp": self.get_timestamp(),
                                })

                elif msg_type == protocol.MSG_TYPE_FILE:
                    target_user = packet.get("target", "ALL").strip()
                    file_name = packet.get("file_name", "file")
                    file_size = packet.get("file_size", 0)
                    file_data = packet.get("file_data", "")

                    if file_data:
                        size_kb = file_size / 1024
                        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                        file_packet = {
                            "type": protocol.MSG_TYPE_FILE,
                            "sender": nickname,
                            "target": target_user,
                            "file_name": file_name,
                            "file_size": file_size,
                            "file_data": file_data,
                            "timestamp": self.get_timestamp(),
                        }
                        if target_user == "ALL" or not target_user:
                            self.broadcast(file_packet)
                            self._log("FILE", f"{nickname} gửi tệp '{file_name}' ({size_str}) tới Phòng Chung")
                        else:
                            with self.lock:
                                target_sock = self.clients_by_name.get(target_user)
                            if target_sock:
                                protocol.send_packet(target_sock, file_packet)
                                protocol.send_packet(client_sock, file_packet)
                                self._log("FILE", f"{nickname} -> {target_user}: Tệp '{file_name}' ({size_str})")
                            else:
                                protocol.send_packet(client_sock, {
                                    "type": protocol.MSG_TYPE_SYSTEM,
                                    "message": f"❌ Người dùng '{target_user}' đã offline.",
                                    "timestamp": self.get_timestamp(),
                                })

                elif msg_type == protocol.MSG_TYPE_USER_LIST:
                    with self.lock:
                        users = list(self.clients_by_name.keys())
                    protocol.send_packet(client_sock, {
                        "type": protocol.MSG_TYPE_USER_LIST,
                        "users": users,
                        "timestamp": self.get_timestamp(),
                    })

                elif msg_type == protocol.MSG_TYPE_QUIT:
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
