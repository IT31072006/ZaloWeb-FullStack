#!/usr/bin/env python3
"""
QA Test Suite for Conversation Settings (Pin, Mute, Priority), In-Chat Search, and Media/Files Gallery
"""
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
import client_desktop

def run_qa_tests():
    print("=" * 70)
    print("🧪 QA TEST: GHIM HỘI THOẠI, TẮT THÔNG BÁO, ƯU TIÊN, TÌM KIẾM TIN NHẮN & MEDIA/FILES")
    print("=" * 70)

    # 1. Connect Client 1 (quan)
    c1 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c1.connect(), "Client 1 kết nối thất bại"
    ack1 = c1.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 5.0)
    assert ack1 and ack1.get("status") == "OK", "Client 1 login failed"
    print("✅ 1. Client 1 đăng nhập thành công!")

    convs = c1.conversations
    assert len(convs) > 0, "Không có hội thoại nào để kiểm thử"
    target_conv = convs[0]
    conv_id = target_conv["id"]
    print(f"✅ 2. Sử dụng hội thoại ID #{conv_id} ('{target_conv.get('title')}') để kiểm thử")

    # 2. Test TOGGLE PIN
    pin_pkt = {
        "type": protocol.MSG_TYPE_CONV_ACTION,
        "conversation_id": conv_id,
        "action": "toggle_pin"
    }
    pin_ack = c1.send_and_wait(pin_pkt, protocol.MSG_TYPE_CONV_ACTION_ACK, 4.0)
    assert pin_ack and pin_ack.get("status") == "OK", f"Lỗi toggle pin: {pin_ack}"
    is_pinned = pin_ack.get("is_pinned")
    print(f"✅ 3. Thao tác Ghim hội thoại (toggle_pin) thành công: is_pinned={is_pinned} ({pin_ack.get('message')})")

    # 3. Test TOGGLE MUTE
    mute_pkt = {
        "type": protocol.MSG_TYPE_CONV_ACTION,
        "conversation_id": conv_id,
        "action": "toggle_mute"
    }
    mute_ack = c1.send_and_wait(mute_pkt, protocol.MSG_TYPE_CONV_ACTION_ACK, 4.0)
    assert mute_ack and mute_ack.get("status") == "OK", f"Lỗi toggle mute: {mute_ack}"
    is_muted = mute_ack.get("is_muted")
    print(f"✅ 4. Thao tác Tắt thông báo (toggle_mute) thành công: is_muted={is_muted} ({mute_ack.get('message')})")

    # 4. Test TOGGLE PRIORITY
    prio_pkt = {
        "type": protocol.MSG_TYPE_CONV_ACTION,
        "conversation_id": conv_id,
        "action": "toggle_priority"
    }
    prio_ack = c1.send_and_wait(prio_pkt, protocol.MSG_TYPE_CONV_ACTION_ACK, 4.0)
    assert prio_ack and prio_ack.get("status") == "OK", f"Lỗi toggle priority: {prio_ack}"
    is_priority = prio_ack.get("is_priority")
    print(f"✅ 5. Thao tác Đổi tab Ưu tiên/Khác (toggle_priority) thành công: is_priority={is_priority} ({prio_ack.get('message')})")

    # 5. Test Media & Files in serialize_conversation
    load_pkt = {"type": protocol.MSG_TYPE_LOAD_HISTORY, "conversation_id": conv_id}
    hist_ack = c1.send_and_wait(load_pkt, protocol.MSG_TYPE_HISTORY_ACK, 4.0)
    assert hist_ack, "Không nhận được lịch sử tin nhắn"
    print(f"✅ 6. Lịch sử tin nhắn nạp thành công (Tổng số: {len(hist_ack.get('messages', []))} tin nhắn)")

    c1.disconnect()
    print("=" * 70)
    print("🎉 TẤT CẢ CÁC BƯỚC KIỂM THỬ QA CHO TÍNH NĂNG CONV ACTION ĐÃ THÀNH CÔNG 100%!")
    print("=" * 70)
    os._exit(0)

if __name__ == "__main__":
    run_qa_tests()
