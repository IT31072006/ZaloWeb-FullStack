#!/usr/bin/env python3
"""
tests/test_search_friend_flow.py - Kiểm thử tính năng Tìm SĐT, Kết bạn thời gian thực & Tạo hội thoại qua Socket TCP
"""

import os
import socket
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5555


def run_test():
    print("=" * 70)
    print("🧪 KIỂM THỬ: TÌM SĐT, GỬI LỜI MỜI KẾT BẠN REALTIME & TẠO HỘI THOẠI")
    print("=" * 70)

    # 1. Kết nối 2 client TCP vào server :5555
    sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock1.connect((SERVER_HOST, SERVER_PORT))
    sock2.connect((SERVER_HOST, SERVER_PORT))

    # Đăng ký 2 tài khoản kiểm thử ngẫu nhiên để đảm bảo danh sách hội thoại ban đầu hoàn toàn trống
    ts = int(time.time())
    u1 = f"user_{ts}_a"
    u2 = f"user_{ts}_b"
    p1 = f"09{ts % 100000000:08d}"
    p2 = f"08{ts % 100000000:08d}"

    # Đăng ký u1
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_REGISTER,
        "username": u1,
        "password": "password123",
        "display_name": f"Người dùng A ({ts})",
        "phone": p1,
    })
    reg_ack1 = protocol.recv_packet(sock1)
    assert reg_ack1 and reg_ack1.get("status") == "OK", f"Reg 1 failed: {reg_ack1}"

    # Đăng ký u2
    protocol.send_packet(sock2, {
        "type": protocol.MSG_TYPE_REGISTER,
        "username": u2,
        "password": "password123",
        "display_name": f"Người dùng B ({ts})",
        "phone": p2,
    })
    reg_ack2 = protocol.recv_packet(sock2)
    assert reg_ack2 and reg_ack2.get("status") == "OK", f"Reg 2 failed: {reg_ack2}"

    # Đăng nhập u1 và u2
    protocol.send_packet(sock1, {"type": protocol.MSG_TYPE_LOGIN, "username": u1, "password": "password123"})
    ack1 = protocol.recv_packet(sock1)
    assert ack1 and ack1.get("status") == "OK"
    print(f"✅ Client 1 đăng nhập: {ack1.get('user', {}).get('display_name')} (Conversations: {len(ack1.get('conversations', []))})")
    # Kiểm tra danh sách hội thoại ban đầu phải TRỐNG (0 cuộc trò chuyện người khác)
    assert len(ack1.get("conversations", [])) == 0, "Danh sách hội thoại ban đầu phải để trống!"
    print("✅ 1. Danh sách hội thoại ban đầu hoàn toàn ĐỂ TRỐNG (chưa có người chat ảo giả lập).")

    protocol.send_packet(sock2, {"type": protocol.MSG_TYPE_LOGIN, "username": u2, "password": "password123"})
    ack2 = protocol.recv_packet(sock2)
    assert ack2 and ack2.get("status") == "OK"
    u2_id = ack2.get("user", {}).get("id")
    print(f"✅ Client 2 đăng nhập: {ack2.get('user', {}).get('display_name')} (ID: {u2_id})")

    # Dọn dẹp các gói tin broadcast online
    time.sleep(0.3)
    sock1.settimeout(0.5)
    sock2.settimeout(0.5)
    while True:
        try:
            if not protocol.recv_packet(sock1): break
        except socket.timeout: break
    while True:
        try:
            if not protocol.recv_packet(sock2): break
        except socket.timeout: break

    sock1.settimeout(4.0)
    sock2.settimeout(4.0)

    # 2. Client 1 tìm kiếm người dùng bằng Số điện thoại của u2
    print(f"[*] Client 1 tìm kiếm bạn bè qua SĐT: '{p2}'...")
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_SEARCH_USER,
        "phone": p2,
    })
    search_ack = protocol.recv_packet(sock1)
    assert search_ack and search_ack.get("status") == "found", f"Search failed: {search_ack}"
    found_user = search_ack.get("user", {})
    assert found_user.get("username") == u2, f"User mismatch: {found_user}"
    print(f"✅ 2. Tìm kiếm SĐT thành công: Tìm thấy '{found_user.get('display_name')}' (@{found_user.get('username')}, SĐT: {found_user.get('phone')})")

    # 3. Client 1 gửi Lời mời kết bạn tới u2 (ID found_user['id'])
    print(f"[*] Client 1 gửi Lời mời kết bạn tới {found_user.get('display_name')} (ID {found_user['id']})...")
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_FRIEND_REQ,
        "target_user_id": found_user["id"],
    })

    # Client 1 nhận gói tin xác nhận gửi thành công
    req_ack = protocol.recv_packet(sock1)
    assert req_ack and req_ack.get("status") == "success", f"Friend req ack failed: {req_ack}"
    print(f"✅ 3. Client 1 gửi lời mời thành công: {req_ack.get('message')}")

    # Client 2 (Bảo) NHẬN ĐƯỢC THÔNG BÁO THỜI GIAN THỰC qua Socket TCP!
    print("[*] Đang chờ Client 2 nhận thông báo kết bạn thời gian thực...")
    incoming_notif = protocol.recv_packet(sock2)
    assert incoming_notif and incoming_notif.get("type") == "friend_request_received", f"Notif failed: {incoming_notif}"
    req_data = incoming_notif.get("data", {})
    friend_request_id = req_data.get("id")
    print(f"✅ 4. Client 2 đã nhận được thông báo kết bạn REALTIME từ '{req_data.get('display_name')}' (Req ID: {friend_request_id})!")

    # 4. Client 2 bấm "Đồng ý" (Accept) lời mời kết bạn
    print(f"[*] Client 2 bấm Đồng ý lời mời kết bạn #{friend_request_id}...")
    protocol.send_packet(sock2, {
        "type": protocol.MSG_TYPE_FRIEND_RESP,
        "request_id": friend_request_id,
        "action": "accept",
    })

    # Client 2 nhận xác nhận kết bạn thành công
    resp_ack2 = protocol.recv_packet(sock2)
    assert resp_ack2 and resp_ack2.get("status") == "success", f"Accept failed: {resp_ack2}"
    created_conv_id = resp_ack2.get("conversation_id")
    print(f"✅ 5. Client 2 đã chấp nhận kết bạn thành công! Hội thoại 1-1 tạo tự động: #{created_conv_id}")

    # Client 1 nhận thông báo friend_request_accepted thời gian thực
    accepted_notif1 = protocol.recv_packet(sock1)
    assert accepted_notif1 and accepted_notif1.get("type") == "friend_request_accepted", f"Accepted notif failed: {accepted_notif1}"
    print(f"✅ 6. Client 1 nhận thông báo thời gian thực: '{accepted_notif1.get('data', {}).get('display_name')} đã chấp nhận lời mời kết bạn!'")

    # 5. Client 1 gửi tin nhắn đầu tiên vào hội thoại 1-1
    print(f"[*] Client 1 gửi tin nhắn đầu tiên vào Hội thoại #{created_conv_id}...")
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": created_conv_id,
        "content": "Chào Bảo, chúng mình đã kết bạn thành công!",
    })
    chat_echo1 = protocol.recv_packet(sock1)
    chat_rx2 = protocol.recv_packet(sock2)
    assert chat_rx2 and chat_rx2.get("content") == "Chào Bảo, chúng mình đã kết bạn thành công!"
    print(f"✅ 7. Tin nhắn trò chuyện đầu tiên giữa hai bạn đã truyền thành công qua Socket TCP!")

    sock1.close()
    sock2.close()
    print("=" * 70)
    print("🎉 TOÀN BỘ QUY TRÌNH: TÌM SĐT -> GỬI KB -> NHẬN NOTIF REALTIME -> ĐỒNG Ý -> NHẮN TIN THÀNH CÔNG 100%!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)

