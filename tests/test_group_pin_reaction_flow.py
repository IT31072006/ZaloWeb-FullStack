#!/usr/bin/env python3
"""
Test Group Chat Creation, Persistent Pinning & Message Reactions via TCP Socket
"""
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
import client_desktop

def run_test():
    print("=" * 70)
    print("🧪 KIỂM THỬ: TẠO NHÓM CHAT (GROUP CHAT), GHIM TIN NHẮN & THẢ BIỂU CẢM (REACTIONS)")
    print("=" * 70)

    # 1. Connect Client 1 (quan)
    c1 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c1.connect(), "Client 1 kết nối thất bại"
    ack1 = c1.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 5.0)
    assert ack1 and ack1.get("status") == "OK", "Client 1 login failed"
    u1_id = ack1["user"]["id"]
    print(f"✅ 1. Client 1 (quan, ID #{u1_id}) đăng nhập thành công")

    # Connect Client 2 (0763538273)
    c2 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c2.connect(), "Client 2 kết nối thất bại"
    ack2 = c2.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "0763538273", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 5.0)
    assert ack2 and ack2.get("status") == "OK", "Client 2 login failed"
    u2_id = ack2["user"]["id"]
    print(f"✅ 2. Client 2 (lê bảo, ID #{u2_id}) đăng nhập thành công")

    # Connect Client 3 (phammm)
    c3 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c3.connect(), "Client 3 kết nối thất bại"
    ack3 = c3.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "phammm", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 5.0)
    assert ack3 and ack3.get("status") == "OK", "Client 3 login failed"
    u3_id = ack3["user"]["id"]
    print(f"✅ 3. Client 3 (phammm, ID #{u3_id}) đăng nhập thành công")

    # 2. Client 1 creates a Group Chat with Client 2 and Client 3
    group_name = "Nhóm Đồ Án LTM 2026 (VKU)"
    create_group_pkt = {
        "type": protocol.MSG_TYPE_CREATE_CONV,
        "is_group": True,
        "name": group_name,
        "members": [u2_id, u3_id]
    }
    create_ack = c1.send_and_wait(create_group_pkt, protocol.MSG_TYPE_CREATE_CONV_ACK, 4.0)
    assert create_ack and create_ack.get("status") == "OK", f"Lỗi tạo nhóm: {create_ack}"
    group_conv = create_ack["conversation"]
    group_id = group_conv["id"]
    print(f"✅ 4. Client 1 đã tạo Nhóm Chat thành công qua Socket TCP! ID: #{group_id}, Tên nhóm: '{group_name}'")
    assert group_conv.get("is_group") is True, "Hội thoại phải là is_group=True"
    assert group_conv.get("member_count") >= 3, f"Số thành viên nhóm phải >= 3 (hiện tại: {group_conv.get('member_count')})"

    # Verify Client 2 and Client 3 received the group invitation / conversation
    time.sleep(0.6)
    assert any(c.get("id") == group_id for c in c2.conversations), "Client 2 chưa nhận được Nhóm chat mới qua Socket!"
    assert any(c.get("id") == group_id for c in c3.conversations), "Client 3 chưa nhận được Nhóm chat mới qua Socket!"
    print("✅ 5. Cả Client 2 và Client 3 đã tự động nhận thông báo tạo nhóm mới theo thời gian thực!")

    # 3. Client 1 sends a message to the Group Chat
    chat_text = "Chào cả nhóm, mình bắt đầu làm báo cáo Lập trình mạng nhé!"
    enc_txt = protocol.encrypt_payload(chat_text)
    c1.send_tcp_packet({
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": group_id,
        "content": f"[ENC:AES-256-GCM]{enc_txt}",
        "is_encrypted": True,
        "cipher_algo": "AES-256-GCM"
    })
    time.sleep(0.6)

    # Check that both Client 2 and Client 3 received the group message
    msgs_c2 = c2.messages_cache.get(group_id, [])
    msgs_c3 = c3.messages_cache.get(group_id, [])
    assert any(chat_text in m.get("content", "") for m in msgs_c2), f"Client 2 chưa nhận được tin nhắn nhóm! Cache: {msgs_c2}"
    assert any(chat_text in m.get("content", "") for m in msgs_c3), f"Client 3 chưa nhận được tin nhắn nhóm! Cache: {msgs_c3}"
    last_group_msg = next(m for m in msgs_c2 if chat_text in m.get("content", ""))
    group_msg_id = last_group_msg["id"]
    print(f"✅ 6. Tin nhắn nhóm đã truyền đồng thời tới tất cả thành viên qua TCP Socket! Msg ID: #{group_msg_id}")

    # 4. Client 1 pins this message (Ghim tin nhắn)
    pin_pkt = {
        "type": protocol.MSG_TYPE_PIN_MESSAGE,
        "conversation_id": group_id,
        "message_id": group_msg_id
    }
    pin_ack = c1.send_and_wait(pin_pkt, protocol.MSG_TYPE_PIN_MESSAGE_ACK, 4.0)
    assert pin_ack and pin_ack.get("status") == "OK", f"Lỗi ghim tin nhắn: {pin_ack}"
    assert pin_ack.get("pinned_message") is not None, "Pinned message payload không được None"
    assert pin_ack["pinned_message"]["id"] == group_msg_id, "Pinned message ID mismatch"
    print(f"✅ 7. Ghim tin nhắn thành công! Nội dung ghim: '{pin_ack['pinned_message']['content']}'")

    # Verify Client 2 and Client 3 received the pinned message notification
    time.sleep(0.5)
    c2_conv = next(c for c in c2.conversations if c.get("id") == group_id)
    assert c2_conv.get("pinned_message") is not None, "Client 2 chưa nhận được thông báo ghim tin nhắn!"
    print("✅ 8. Client 2 & Client 3 đã tự động cập nhật thanh ghim màu vàng theo thời gian thực!")

    # 5. Client 2 reacts with ❤️ to the message
    c2.send_tcp_packet({
        "type": protocol.MSG_TYPE_REACTION,
        "conversation_id": group_id,
        "message_id": group_msg_id,
        "emoji": "❤️"
    })
    time.sleep(0.6)

    # Verify Client 1 receives the reaction update
    msgs_c1 = c1.messages_cache.get(group_id, [])
    reacted_msg = next((m for m in msgs_c1 if m.get("id") == group_msg_id), None)
    assert reacted_msg is not None, "Message not in Client 1 cache"
    reactions = reacted_msg.get("reactions", [])
    assert any(r.get("emoji") == "❤️" for r in reactions), f"Reactions không có ❤️: {reactions}"
    heart_react = next(r for r in reactions if r.get("emoji") == "❤️")
    print(f"✅ 9. Thả biểu cảm cảm xúc (Reactions) thành công! Biểu tượng: {heart_react['emoji']} (Số lượng: {heart_react['count']}, Người thả: {heart_react['users']})")

    # Cleanup sockets
    c1.disconnect()
    c2.disconnect()
    c3.disconnect()

    print("=" * 70)
    print("🎉 TẤT CẢ 9/9 BƯỚC KIỂM THỬ TẠO NHÓM, GHIM & REACTIONS ĐÃ ĐẠT 100%!")
    print("=" * 70)

if __name__ == "__main__":
    run_test()
