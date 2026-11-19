#!/usr/bin/env python3
"""
Test Advanced Group Management, Cloud Storage, Message Forwarding & Delete for Me via TCP Socket 5555
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
    print("🧪 KIỂM THỬ: QUẢN LÝ NHÓM NÂNG CAO, CLOUD CỦA TÔI, CHUYỂN TIẾP & XÓA TIN NHẮN")
    print("=" * 70)

    # 1. Connect Client 1 (quan)
    c1 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c1.connect(), "Client 1 kết nối thất bại"
    ack1 = c1.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack1 and ack1.get("status") == "OK", "Client 1 login failed"
    u1_id = ack1["user"]["id"]
    print(f"✅ 1. Client 1 (quan, ID #{u1_id}) đăng nhập thành công")

    # Connect Client 2 (0763538273)
    c2 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c2.connect(), "Client 2 kết nối thất bại"
    ack2 = c2.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "0763538273", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack2 and ack2.get("status") == "OK", "Client 2 login failed"
    u2_id = ack2["user"]["id"]
    print(f"✅ 2. Client 2 (lê bảo, ID #{u2_id}) đăng nhập thành công")

    # Connect Client 3 (phammm)
    c3 = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert c3.connect(), "Client 3 kết nối thất bại"
    ack3 = c3.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "phammm", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack3 and ack3.get("status") == "OK", "Client 3 login failed"
    u3_id = ack3["user"]["id"]
    print(f"✅ 3. Client 3 (phammm, ID #{u3_id}) đăng nhập thành công")

    # 2. Test Cloud của tôi (GET_CLOUD)
    cloud_pkt = {"type": protocol.MSG_TYPE_GET_CLOUD}
    cloud_ack = c1.send_and_wait(cloud_pkt, protocol.MSG_TYPE_CLOUD_ACK, 4.0)
    assert cloud_ack and cloud_ack.get("status") == "OK", f"Lỗi mở Cloud: {cloud_ack}"
    cloud_id = cloud_ack.get("id")
    print(f"✅ 4. Mở 'Cloud của tôi' thành công! ID: #{cloud_id}, Dung lượng: {cloud_ack.get('storage_used_mb')} MB / {cloud_ack.get('storage_limit_mb')} MB ({cloud_ack.get('storage_percent')}%)")

    # 3. Client 1 creates a group with Client 2 only
    init_name = "Nhóm Ban Đầu LTM"
    create_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_CREATE_CONV,
        "is_group": True,
        "name": init_name,
        "members": [u2_id]
    }, protocol.MSG_TYPE_CREATE_CONV_ACK, 4.0)
    assert create_ack and create_ack.get("status") == "OK", "Lỗi tạo nhóm ban đầu"
    group_id = create_ack["conversation"]["id"]
    time.sleep(0.5)
    assert any(c.get("id") == group_id for c in c2.conversations), "Client 2 chưa nhận được nhóm"
    print(f"✅ 5. Đã tạo nhóm ban đầu (ID #{group_id}) với 2 thành viên (quan & lê bảo)")

    # 4. Client 1 adds Client 3 to the group (GROUP_ADD_MEMBER)
    add_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_GROUP_ADD_MEMBER,
        "conversation_id": group_id,
        "user_id": u3_id
    }, protocol.MSG_TYPE_GROUP_ADD_MEMBER_ACK, 4.0)
    assert add_ack and add_ack.get("status") == "OK", f"Lỗi thêm thành viên: {add_ack}"
    time.sleep(0.6)
    assert any(c.get("id") == group_id for c in c3.conversations), "Client 3 chưa nhận được nhóm sau khi được thêm"
    print(f"✅ 6. Thêm thành viên mới (phammm) vào nhóm thành công qua TCP Socket!")

    # 5. Client 1 updates group name (GROUP_UPDATE)
    new_name = "Nhóm Đồ Án LTM (Đã Đổi Tên)"
    update_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_GROUP_UPDATE,
        "conversation_id": group_id,
        "name": new_name
    }, protocol.MSG_TYPE_GROUP_UPDATE_ACK, 4.0)
    assert update_ack and update_ack.get("status") == "OK", f"Lỗi đổi tên nhóm: {update_ack}"
    time.sleep(0.6)
    c2_g = next((c for c in c2.conversations if c.get("id") == group_id), None)
    assert c2_g and c2_g.get("title") == new_name, f"Tên nhóm tại Client 2 chưa được đồng bộ: {c2_g}"
    print(f"✅ 7. Đổi tên nhóm thành '{new_name}' và đồng bộ realtime tới tất cả thành viên thành công!")

    # 6. Test Send Message & Forward Message (FORWARD_MESSAGE)
    # Send a message first
    c1.send_tcp_packet({
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": group_id,
        "content": "Tài liệu ôn thi Lập trình mạng 2026",
        "is_encrypted": False
    })
    time.sleep(0.8)
    # Find sent message ID from c1 messages_cache
    msgs_in_g = c1.messages_cache.get(group_id, [])
    assert len(msgs_in_g) > 0, "Không tìm thấy tin nhắn vừa gửi trong nhóm"
    orig_msg_id = msgs_in_g[-1]["id"]

    # Forward message from group to Cloud cá nhân
    fwd_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_FORWARD_MESSAGE,
        "message_id": orig_msg_id,
        "conversation_ids": [cloud_id]
    }, protocol.MSG_TYPE_FORWARD_MESSAGE_ACK, 4.0)
    assert fwd_ack and fwd_ack.get("status") == "OK", f"Lỗi chuyển tiếp tin nhắn: {fwd_ack}"
    time.sleep(0.6)
    print(f"✅ 8. Chuyển tiếp tin nhắn #{orig_msg_id} từ Nhóm sang 'Cloud của tôi' thành công! (Số cuộc trò chuyện: {fwd_ack.get('forwarded_count')})")

    # 7. Test Delete For Me (DELETE_FOR_ME)
    del_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_DELETE_FOR_ME,
        "message_id": orig_msg_id
    }, protocol.MSG_TYPE_DELETE_FOR_ME_ACK, 4.0)
    assert del_ack and del_ack.get("status") == "OK", f"Lỗi xóa tin nhắn: {del_ack}"

    # Load history at Client 1 and Client 2 to verify exclusion
    hist_c1 = c1.send_and_wait({"type": protocol.MSG_TYPE_LOAD_HISTORY, "conversation_id": group_id}, protocol.MSG_TYPE_HISTORY_ACK, 4.0)
    hist_c2 = c2.send_and_wait({"type": protocol.MSG_TYPE_LOAD_HISTORY, "conversation_id": group_id}, protocol.MSG_TYPE_HISTORY_ACK, 4.0)
    c1_msg_ids = [m["id"] for m in hist_c1.get("messages", [])]
    c2_msg_ids = [m["id"] for m in hist_c2.get("messages", [])]
    assert orig_msg_id not in c1_msg_ids, "Tin nhắn đã xóa ở phía tôi nhưng vẫn xuất hiện trong lịch sử của Client 1!"
    assert orig_msg_id in c2_msg_ids, "Tin nhắn bị xóa ở phía Client 2 (lẽ ra chỉ được xóa ở phía Client 1)!"
    print(f"✅ 9. Xóa tin nhắn ở phía tôi thành công! (Tin nhắn #{orig_msg_id} đã biến mất tại Client 1 nhưng vẫn tồn tại nguyên vẹn tại Client 2)")

    # 8. Test Client 1 removes Client 3 (GROUP_REMOVE_MEMBER)
    rem_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_GROUP_REMOVE_MEMBER,
        "conversation_id": group_id,
        "user_id": u3_id
    }, protocol.MSG_TYPE_GROUP_REMOVE_MEMBER_ACK, 4.0)
    assert rem_ack and rem_ack.get("status") == "OK", f"Lỗi xóa thành viên: {rem_ack}"
    time.sleep(0.6)
    assert not any(c.get("id") == group_id for c in c3.conversations), "Client 3 vẫn còn nhóm sau khi bị xóa khỏi nhóm!"
    print("✅ 10. Trưởng nhóm xóa thành viên (phammm) thành công! Client 3 đã tự động gỡ nhóm khỏi màn hình.")

    # 9. Test Client 2 leaves group (GROUP_LEAVE)
    leave_ack = c2.send_and_wait({
        "type": protocol.MSG_TYPE_GROUP_LEAVE,
        "conversation_id": group_id
    }, protocol.MSG_TYPE_GROUP_LEAVE_ACK, 4.0)
    assert leave_ack and leave_ack.get("status") == "OK", f"Lỗi rời nhóm: {leave_ack}"
    time.sleep(0.6)
    print("✅ 11. Thành viên (lê bảo) tự rời nhóm thành công qua TCP Socket!")

    # 10. Test Client 1 disbands group (GROUP_DISBAND)
    disband_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_GROUP_DISBAND,
        "conversation_id": group_id
    }, protocol.MSG_TYPE_GROUP_DISBAND_ACK, 4.0)
    assert disband_ack and disband_ack.get("status") == "OK", f"Lỗi giải tán nhóm: {disband_ack}"
    time.sleep(0.6)
    print("✅ 12. Trưởng nhóm giải tán nhóm thành công! Nhóm đã được dọn sạch hoàn toàn khỏi CSDL.")

    # Cleanup
    c1.disconnect()
    c2.disconnect()
    c3.disconnect()

    print("=" * 70)
    print("🎉 TẤT CẢ 12/12 BƯỚC KIỂM THỬ QUẢN LÝ NHÓM & CLOUD ĐÃ ĐẠT 100%!")
    print("=" * 70)

if __name__ == "__main__":
    run_test()
