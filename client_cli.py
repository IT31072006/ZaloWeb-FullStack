"""
client_cli.py - TCP Chat Client Giao diện Dòng lệnh (CLI).

Sử dụng 2 luồng độc lập:
- 1 luồng lắng nghe tin nhắn từ Server.
- 1 luồng nhận dữ liệu nhập từ bàn phím và gửi đến Server.
"""

import socket
import sys
import threading

import protocol

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5555


class ChatClientCLI:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.nickname = ""
        self.is_running = False

    def print_help(self):
        """In bảng hướng dẫn sử dụng các lệnh trong phòng chat."""
        print("-" * 55)
        print("💡 CÁC LỆNH HỖ TRỢ TRONG PHÒNG CHAT:")
        print("  /help hoặc /?           : Xem bảng trợ giúp này")
        print("  /online hoặc /list      : Xem danh sách thành viên đang online")
        print("  /msg <tên> <nội dung>   : Gửi tin nhắn riêng cho 1 người")
        print("  /quit hoặc /exit        : Rời phòng chat và thoát chương trình")
        print("  <nội dung bình thường>  : Chat công khai tới cả phòng")
        print("-" * 55)

    def connect_and_join(self) -> bool:
        """Thực hiện kết nối tới Server và đăng ký nickname."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
        except Exception as e:
            print(f"❌ Không thể kết nối tới Server tại {self.host}:{self.port} ({e})")
            return False

        print(f"✅ Đã kết nối thành công tới Server {self.host}:{self.port}")

        # Vòng lặp yêu cầu nhập và xác thực Nickname
        while True:
            try:
                nickname_input = input("👉 Nhập biệt danh (Nickname) của bạn: ").strip()
            except (KeyboardInterrupt, EOFError):
                self.sock.close()
                return False

            if not nickname_input:
                print("⚠️ Biệt danh không được để trống!")
                continue

            # Gửi gói JOIN
            join_packet = {
                "type": protocol.MSG_TYPE_JOIN,
                "nickname": nickname_input,
            }
            if not protocol.send_packet(self.sock, join_packet):
                print("❌ Mất kết nối khi gửi yêu cầu tham gia.")
                self.sock.close()
                return False

            # Chờ phản hồi JOIN_ACK từ Server
            ack = protocol.recv_packet(self.sock)
            if not ack or ack.get("type") != protocol.MSG_TYPE_JOIN_ACK:
                print("❌ Phản hồi từ Server không hợp lệ.")
                self.sock.close()
                return False

            if ack.get("status") == "OK":
                self.nickname = nickname_input
                print(f"🎉 {ack.get('message')}\n")
                self.print_help()
                return True
            else:
                print(f"❌ Đăng ký thất bại: {ack.get('message')}")
                # Server sẽ đóng socket nếu từ chối, kết nối lại để nhập tên khác
                self.sock.close()
                try:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.connect((self.host, self.port))
                except Exception:
                    return False

    def receive_loop(self):
        """Luồng liên tục lắng nghe và hiển thị thông điệp từ Server."""
        while self.is_running:
            packet = protocol.recv_packet(self.sock)
            if not packet:
                if self.is_running:
                    print("\n⚠️ [Mất kết nối tới Server. Nhấn Enter để thoát...]")
                    self.is_running = False
                break

            msg_type = packet.get("type")
            ts = packet.get("timestamp", "")

            if msg_type == protocol.MSG_TYPE_CHAT:
                sender = packet.get("sender")
                content = packet.get("content")
                if sender == self.nickname:
                    print(f"[{ts}] [Tôi]: {content}")
                else:
                    print(f"[{ts}] <{sender}>: {content}")

            elif msg_type == protocol.MSG_TYPE_PRIVATE:
                sender = packet.get("sender")
                target = packet.get("target")
                content = packet.get("content")
                if sender == self.nickname:
                    print(f"[{ts}] 🔒 [Riêng tới @{target}]: {content}")
                else:
                    print(f"[{ts}] 🔒 [Riêng từ @{sender}]: {content}")

            elif msg_type == protocol.MSG_TYPE_USER_LIST:
                users = packet.get("users", [])
                user_str = ", ".join(users)
                print(f"\n👥 Thành viên đang online ({len(users)}): [{user_str}]")

            elif msg_type == protocol.MSG_TYPE_SYSTEM:
                msg = packet.get("message")
                print(f"[{ts}] 🔔 {msg}")

    def start(self):
        """Khởi động client."""
        if not self.connect_and_join():
            return

        self.is_running = True

        # Khởi chạy luồng nhận tin
        recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
        recv_thread.start()

        # Vòng lặp chính xử lý nhập liệu từ bàn phím
        try:
            while self.is_running:
                try:
                    line = input()
                except (EOFError, KeyboardInterrupt):
                    break

                text = line.strip()
                if not text:
                    continue

                if not self.is_running:
                    break

                # Xử lý các lệnh đặc biệt
                if text.lower() in ("/help", "/?"):
                    self.print_help()

                elif text.lower() in ("/online", "/list"):
                    protocol.send_packet(self.sock, {"type": protocol.MSG_TYPE_USER_LIST})

                elif text.lower() in ("/quit", "/exit"):
                    protocol.send_packet(self.sock, {"type": protocol.MSG_TYPE_QUIT})
                    break

                elif text.lower().startswith("/msg ") or text.lower().startswith("/w "):
                    parts = text.split(maxsplit=2)
                    if len(parts) < 3:
                        print("⚠️ Cú pháp sai! Vui lòng dùng: /msg <tên_người_nhận> <nội dung>")
                        continue
                    target_user = parts[1]
                    private_msg = parts[2]
                    packet = {
                        "type": protocol.MSG_TYPE_PRIVATE,
                        "target": target_user,
                        "content": private_msg,
                    }
                    protocol.send_packet(self.sock, packet)

                else:
                    # Gửi tin nhắn công khai (CHAT)
                    packet = {
                        "type": protocol.MSG_TYPE_CHAT,
                        "content": text,
                    }
                    protocol.send_packet(self.sock, packet)

        finally:
            self.stop()

    def stop(self):
        """Đóng kết nối client."""
        self.is_running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        print("🚪 Đã thoát phòng chat.")


if __name__ == "__main__":
    host = DEFAULT_HOST
    port = DEFAULT_PORT

    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            print("Cổng không hợp lệ! Dùng cổng mặc định 5555.")

    client = ChatClientCLI(host=host, port=port)
    client.start()
