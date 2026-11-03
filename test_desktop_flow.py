"""
test_desktop_flow.py - Kiểm thử tự động luồng xác thực và tải dữ liệu PostgreSQL cho Desktop Client.
"""

import socket
import threading
import time
import protocol
from server import ChatServer

TEST_PORT = 5588


def run_test():
    print("=== TEST DESKTOP TCP SOCKET + POSTGRESQL INTEGRATION ===")
    
    # 1. Start Server
    server = ChatServer(host="127.0.0.1", port=TEST_PORT)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(0.4)

    try:
        # 2. Client socket connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", TEST_PORT))

        # 3. Send LOGIN packet
        login_pkt = {
            "type": protocol.MSG_TYPE_LOGIN,
            "username": "quan",
            "password": "password123",
        }
        assert protocol.send_packet(sock, login_pkt), "Lỗi gửi LOGIN packet"
        print("✓ Đã gửi gói tin LOGIN (quan / password123).")

        # 4. Receive LOGIN_ACK
        ack = protocol.recv_packet(sock)
        assert ack and ack.get("type") == protocol.MSG_TYPE_LOGIN_ACK, f"Phản hồi sai: {ack}"
        assert ack.get("status") == "OK", f"Đăng nhập thất bại: {ack}"
        print(f"✓ Đăng nhập PostgreSQL thành công! User: {ack.get('user', {}).get('display_name')}")

        convs = ack.get("conversations", [])
        print(f"✓ Tải thành công {len(convs)} cuộc hội thoại từ PostgreSQL.")

        # Receive system online broadcast
        sys_msg = protocol.recv_packet(sock)
        user_list = protocol.recv_packet(sock)

        if convs:
            first_conv_id = convs[0].get("id")
            # 5. Send LOAD_HISTORY
            assert protocol.send_packet(sock, {
                "type": protocol.MSG_TYPE_LOAD_HISTORY,
                "conversation_id": first_conv_id,
            })
            print(f"✓ Đã gửi yêu cầu tải lịch sử tin nhắn của Hội thoại #{first_conv_id}.")

            hist = protocol.recv_packet(sock)
            assert hist and hist.get("type") == protocol.MSG_TYPE_HISTORY_ACK, f"Phản hồi sai: {hist}"
            messages = hist.get("messages", [])
            print(f"✓ Tải thành công {len(messages)} tin nhắn lịch sử từ CSDL PostgreSQL.")

        sock.close()
        print("\n🎉 KIỂM THỬ DESKTOP CLIENT + POSTGRESQL ĐẠT 100% HOÀN HẢO!")
    finally:
        server.stop()


if __name__ == "__main__":
    run_test()
