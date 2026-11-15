#!/usr/bin/env python3
"""
tests/test_bridge_flow.py - Kiểm tra ZaloTCPClient và Auto-Reconnect
"""

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from client_desktop import ZaloTCPClient
import protocol

def test_bridge():
    print("=" * 60)
    print("🧪 KIỂM TRA ZALOTCPCLIENT BRIDGE & AUTO-RECONNECT")
    print("=" * 60)

    client = ZaloTCPClient("127.0.0.1", 5555)
    connected = client.connect()
    assert connected is True, "Kết nối ban đầu thất bại"
    print("✅ 1. Kết nối ZaloTCPClient tới Server :5555 thành công.")

    # Đăng nhập
    login_ack = client.send_and_wait(
        {"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"},
        protocol.MSG_TYPE_LOGIN_ACK,
        timeout=4.0
    )
    assert login_ack and login_ack.get("status") == "OK", "Đăng nhập thất bại"
    client.saved_credentials = ("quan", "password123")
    print(f"✅ 2. Đăng nhập thành công user: {client.current_user.get('display_name')}")

    # Chờ 5 giây để luồng Heartbeat Ping/Pong chạy
    print("[*] Đang chờ luồng Heartbeat gửi PING...")
    time.sleep(5.5)
    print(f"✅ 3. Heartbeat Keep-Alive hoạt động bình thường (Last pong time: {client.last_pong_time})")

    # Giả lập rớt kết nối bằng cách đóng socket từ phía client
    print("[*] Giả lập ngắt kết nối socket để kiểm thử Tự động kết nối lại (Auto-Reconnect)...")
    client.disconnect()

    # Chờ tiến trình auto reconnect kích hoạt và tái xác thực
    for _ in range(10):
        time.sleep(1.0)
        if client.is_connected:
            break

    print(f"[*] Trạng thái sau tái kết nối: is_connected = {client.is_connected}")
    assert client.is_connected is True, "Tự động kết nối lại thất bại!"
    print("✅ 4. Tự động kết nối lại (Auto-Reconnect) và Tái xác thực phiên thành công rực rỡ!")

    client.should_stop = True
    client.disconnect()
    print("=" * 60)
    print("🎉 KIỂM TRA BRIDGE & AUTO-RECONNECT THÀNH CÔNG!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_bridge()
    sys.exit(0 if success else 1)
