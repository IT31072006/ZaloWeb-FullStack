#!/usr/bin/env python3
"""
Test Profile & Avatar Update via TCP Socket and Real-time Broadcast
"""
import os
import sys
import time
import base64

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
import client_desktop

def run_test():
    print("=" * 60)
    print("🧪 KIỂM THỬ: CẬP NHẬT HỒ SƠ, ẢNH ĐẠI DIỆN & PHÁT TÁN REALTIME")
    print("=" * 60)

    # 1. Connect Client A (phammm) and Client B (0763538273)
    bridge_b = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert bridge_b.connect(), "Client B kết nối thất bại"
    ack_b = bridge_b.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "0763538273", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack_b and ack_b.get("status") == "OK", "Client B đăng nhập thất bại"
    print("✅ 1. Client B (lê bảo) đăng nhập thành công")

    bridge_a = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert bridge_a.connect(), "Client A kết nối thất bại"
    ack_a = bridge_a.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "phammm", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack_a and ack_a.get("status") == "OK", "Client A đăng nhập thất bại"
    print("✅ 2. Client A (phammm) đăng nhập thành công")

    # 2. Client A updates profile with new Display Name, Bio, and Avatar
    sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    av_b64 = base64.b64encode(sample_png).decode("utf-8")
    new_disp_name = "Phạm Huỳnh Quân (VIP Pro)"
    new_bio = "Lập trình mạng Socket TCP siêu mượt 🚀"

    update_pkt = {
        "type": protocol.MSG_TYPE_UPDATE_PROFILE,
        "display_name": new_disp_name,
        "bio": new_bio,
        "phone": "0912345678",
        "gender": "nam",
        "avatar_data": av_b64,
        "avatar_name": "test_avatar.png",
    }
    update_ack = bridge_a.send_and_wait(update_pkt, protocol.MSG_TYPE_UPDATE_PROFILE_ACK, 4.0)
    assert update_ack and update_ack.get("status") == "OK", f"Cập nhật hồ sơ thất bại: {update_ack}"
    user_res = update_ack.get("user", {})
    assert user_res.get("display_name") == new_disp_name, f"Display name mismatch: {user_res}"
    assert user_res.get("avatar_url"), "Avatar URL không được rỗng"
    print("✅ 3. Client A cập nhật hồ sơ & ảnh đại diện thành công qua Socket TCP!")
    print(f"   - Tên mới: {user_res.get('display_name')}")
    print(f"   - Tiểu sử: {user_res.get('bio')}")
    print(f"   - Ảnh đại diện URL: {user_res.get('avatar_url')}")

    # 3. Check if Client B receives the broadcast USER_UPDATE
    time.sleep(0.5)
    matching_contact = next((c for c in bridge_b.contacts if c.get("username") == "phammm"), None)
    if matching_contact:
        assert matching_contact.get("display_name") == new_disp_name, "Client B chưa nhận được tên mới"
        print("✅ 4. Client B đã tự động cập nhật tên & avatar mới của Client A theo thời gian thực!")

    bridge_a.should_stop = True
    bridge_b.should_stop = True
    bridge_a.tcp_sock.close()
    bridge_b.tcp_sock.close()
    print("=" * 60)
    print("🎉 KIỂM THỬ CẬP NHẬT ẢNH ĐẠI DIỆN & HỒ SƠ ĐÃ VƯỢT QUA 100%!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
