"""
test_chat.py - Script tự động kiểm thử (Integration Test) hệ thống Chat Room Socket.
- Khởi động Server trên một cổng ngẫu nhiên.
- Tạo 2 Client kết nối (Alice và Bob).
- Kiểm tra tính năng Join phòng.
- Kiểm tra Chat công khai (Alice gửi, Bob nhận).
- Kiểm tra Chat riêng (Bob gửi cho Alice, Alice nhận).
- Kiểm tra danh sách User Online.
- Kiểm tra ngắt kết nối an toàn.
"""

import socket
import threading
import time

import protocol
from server import ChatServer

TEST_PORT = 5599


def run_tests():
    print("=== BẮT ĐẦU KIỂM THỬ TỰ ĐỘNG CHAT ROOM TCP SOCKET ===")

    # 1. Khởi chạy Server trong background thread
    server = ChatServer(host="127.0.0.1", port=TEST_PORT)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.3)  # Chờ server khởi động

    try:
        # 2. Tạo Client 1 (Alice)
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.connect(("127.0.0.1", TEST_PORT))
        protocol.send_packet(s1, {"type": protocol.MSG_TYPE_JOIN, "nickname": "Alice"})
        ack1 = protocol.recv_packet(s1)
        assert ack1 and ack1.get("status") == "OK", f"Lỗi đăng ký Alice: {ack1}"
        print("✓ Client 1 (Alice) kết nối và đăng ký thành công.")

        # Alice nhận thông báo join và user_list của chính mình
        sys_msg1 = protocol.recv_packet(s1)
        user_list1 = protocol.recv_packet(s1)
        assert "Alice" in user_list1.get("users", []), "Alice phải có trong user_list"

        # 3. Tạo Client 2 (Bob)
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.connect(("127.0.0.1", TEST_PORT))
        protocol.send_packet(s2, {"type": protocol.MSG_TYPE_JOIN, "nickname": "Bob"})
        ack2 = protocol.recv_packet(s2)
        assert ack2 and ack2.get("status") == "OK", f"Lỗi đăng ký Bob: {ack2}"
        print("✓ Client 2 (Bob) kết nối và đăng ký thành công.")

        # Alice sẽ nhận được thông báo Bob tham gia và user_list mới
        alice_recv_join = protocol.recv_packet(s1)
        alice_recv_list = protocol.recv_packet(s1)
        assert set(alice_recv_list.get("users", [])) == {"Alice", "Bob"}
        print("✓ Server cập nhật danh sách Online cho cả 2 client thành công.")

        # Bob nhận thông báo và user_list
        _ = protocol.recv_packet(s2)
        _ = protocol.recv_packet(s2)

        # 4. Kiểm tra Broadcast (Alice gửi tin nhắn chung)
        protocol.send_packet(s1, {"type": protocol.MSG_TYPE_CHAT, "content": "Xin chào cả phòng!"})
        msg_alice = protocol.recv_packet(s1)
        msg_bob = protocol.recv_packet(s2)
        assert msg_alice.get("content") == "Xin chào cả phòng!"
        assert msg_bob.get("content") == "Xin chào cả phòng!"
        assert msg_bob.get("sender") == "Alice"
        print("✓ Kiểm tra Chat công khai (Broadcast) thành công.")

        # 5. Kiểm tra Private Message (Bob gửi riêng cho Alice)
        protocol.send_packet(s2, {
            "type": protocol.MSG_TYPE_PRIVATE,
            "target": "Alice",
            "content": "Chào Alice, đây là tin nhắn bí mật!",
        })
        priv_alice = protocol.recv_packet(s1)
        priv_bob = protocol.recv_packet(s2)
        assert priv_alice.get("type") == protocol.MSG_TYPE_PRIVATE
        assert priv_alice.get("sender") == "Bob"
        assert priv_alice.get("content") == "Chào Alice, đây là tin nhắn bí mật!"
        assert priv_bob.get("type") == protocol.MSG_TYPE_PRIVATE
        print("✓ Kiểm tra Chat riêng tư (Private Message) thành công.")

        # 6. Kiểm tra thoát kết nối an toàn (Bob gửi QUIT)
        protocol.send_packet(s2, {"type": protocol.MSG_TYPE_QUIT})
        s2.close()
        time.sleep(0.1)

        # Alice phải nhận thông báo Bob đã rời phòng và danh sách user mới
        alice_leave_notice = protocol.recv_packet(s1)
        alice_new_list = protocol.recv_packet(s1)
        assert "Bob" not in alice_new_list.get("users", [])
        assert alice_new_list.get("users", []) == ["Alice"]
        print("✓ Kiểm tra rời phòng an toàn và dọn dẹp socket thành công.")

        s1.close()
        print("\n🎉 TẤT CẢ CÁC BÀI KIỂM THỬ ĐÃ ĐẠT 100%!")

    finally:
        server.stop()


if __name__ == "__main__":
    run_tests()
