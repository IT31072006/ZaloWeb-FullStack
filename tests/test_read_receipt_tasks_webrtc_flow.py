#!/usr/bin/env python3
"""
Test Suite: Read Receipts, Zalo To-Do Tasks & WebRTC Voice/Video Signaling via TCP Socket 5555
"""
import os
import sys
import time
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
import client_desktop

class InstrumentedClient(client_desktop.ZaloTCPClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.received_ui_packets = []
        self._packet_waiters = [] # list of (predicate, Event, container)
        self._waiter_lock = threading.Lock()

    def _broadcast_to_ui(self, packet: dict):
        super()._broadcast_to_ui(packet)
        with self._waiter_lock:
            self.received_ui_packets.append(packet)
            for pred, evt, container in list(self._packet_waiters):
                if pred(packet):
                    container.append(packet)
                    evt.set()

    def wait_for_ui_packet(self, predicate, timeout=5.0):
        evt = threading.Event()
        container = []
        with self._waiter_lock:
            # Check already received packets first
            for p in self.received_ui_packets:
                if predicate(p):
                    return p
            self._packet_waiters.append((predicate, evt, container))
        
        ok = evt.wait(timeout=timeout)
        with self._waiter_lock:
            if (predicate, evt, container) in self._packet_waiters:
                self._packet_waiters.remove((predicate, evt, container))
        return container[0] if ok and container else None

def run_test():
    print("=" * 75)
    print("🧪 KIỂM THỬ: ĐÃ XEM (READ RECEIPTS), TO-DO TASKS & BÁO HIỆU WEBRTC CALL")
    print("=" * 75)

    # 1. Connect Client 1 (quan)
    c1 = InstrumentedClient('127.0.0.1', 5555)
    assert c1.connect(), "Client 1 kết nối thất bại tới TCP port 5555"
    ack1 = c1.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack1 and ack1.get("status") == "OK", "Client 1 login failed"
    u1_id = ack1["user"]["id"]
    print(f"✅ 1. Client 1 (quan, ID #{u1_id}) đăng nhập thành công!")

    # Connect Client 2 (0763538273)
    c2 = InstrumentedClient('127.0.0.1', 5555)
    assert c2.connect(), "Client 2 kết nối thất bại tới TCP port 5555"
    ack2 = c2.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "0763538273", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack2 and ack2.get("status") == "OK", "Client 2 login failed"
    u2_id = ack2["user"]["id"]
    print(f"✅ 2. Client 2 (lê bảo, ID #{u2_id}) đăng nhập thành công!")

    # Get or create 1-1 conversation between quan and 0763538273
    conv_id = None
    for c in c1.conversations:
        if not c.get("is_group") and not c.get("is_cloud"):
            other_u = c.get("other_username")
            if other_u == "0763538273":
                conv_id = c.get("id")
                break
    
    if not conv_id:
        create_ack = c1.send_and_wait({
            "type": protocol.MSG_TYPE_CREATE_CONV,
            "is_group": False,
            "target_user_id": u2_id,
            "user_id": u2_id
        }, protocol.MSG_TYPE_CREATE_CONV_ACK, 4.0)
        assert create_ack and create_ack.get("status") == "OK", f"Lỗi tạo hội thoại 1-1: {create_ack}"
        conv_id = create_ack["conversation"]["id"]
    
    print(f"✅ 3. Sử dụng cuộc trò chuyện 1-1 (ID #{conv_id}) giữa Client 1 và Client 2")

    # =========================================================================
    # PHẦN 1: KIỂM THỬ TRẠNG THÁI "ĐÃ XEM" (READ RECEIPTS)
    # =========================================================================
    print("\n--- [PHẦN 1: TRẠNG THÁI ĐÃ XEM / READ RECEIPTS] ---")
    # Client 1 sends a message to Client 2
    chat_content = f"Test Read Receipt Ping #{int(time.time())}"
    c1.send_tcp_packet({
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": conv_id,
        "content": chat_content,
        "is_encrypted": False
    })
    
    # Wait for Client 2 to receive the message
    c2_msg_pkt = c2.wait_for_ui_packet(
        lambda p: p.get("type") == "chat_message" and p.get("message", {}).get("conversation_id") == conv_id and p.get("message", {}).get("content") == chat_content,
        timeout=4.0
    )
    assert c2_msg_pkt is not None, "Client 2 không nhận được tin nhắn từ Client 1"
    sent_msg_id = c2_msg_pkt["message"]["id"]
    print(f"✅ 4. Client 2 đã nhận được tin nhắn (ID #{sent_msg_id}): '{chat_content}'")

    # Client 2 sends mark_read packet
    c2.send_tcp_packet({
        "type": protocol.MSG_TYPE_READ_RECEIPT,
        "conversation_id": conv_id,
        "last_message_id": sent_msg_id
    })

    # Client 1 should receive the read_receipt packet
    c1_read_pkt = c1.wait_for_ui_packet(
        lambda p: p.get("type") == "read_receipt" and p.get("conversation_id") == conv_id and p.get("last_read_message_id") >= sent_msg_id,
        timeout=4.0
    )
    assert c1_read_pkt is not None, "Client 1 không nhận được gói tin read_receipt từ Client 2"
    assert c1_read_pkt.get("sender") == "0763538273", "Người gửi read_receipt không khớp"
    print(f"✅ 5. Client 1 đã nhận được thông báo 'ĐÃ XEM' tức thì: Message ID #{c1_read_pkt.get('last_read_message_id')} đã được đọc bởi {c1_read_pkt.get('sender')}!")

    # Check conversation members in Client 1
    c1_conv = next((c for c in c1.conversations if c.get("id") == conv_id), None)
    if c1_conv:
        target_mem = next((m for m in c1_conv.get("members", []) if m.get("username") == "0763538273"), None)
        if target_mem:
            assert target_mem.get("last_read_message_id") >= sent_msg_id, "last_read_message_id chưa được cập nhật trong bộ nhớ c1"
            print(f"✅ 6. Bộ nhớ hội thoại Client 1 đã đồng bộ: last_read_message_id = {target_mem.get('last_read_message_id')}")

    # =========================================================================
    # PHẦN 2: KIỂM THỬ QUẢN LÝ CÔNG VIỆC (ZALO TO-DO / TASKS)
    # =========================================================================
    print("\n--- [PHẦN 2: QUẢN LÝ CÔNG VIỆC ZALO TO-DO / TASKS] ---")
    # A. List tasks
    list_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "list"
    }, protocol.MSG_TYPE_TASK_OP_ACK, 4.0)
    assert list_ack and list_ack.get("status") == "OK", f"Lỗi lấy danh sách task: {list_ack}"
    initial_tasks = list_ack.get("tasks", [])
    assert len(initial_tasks) >= 4, f"Số lượng task ban đầu không đủ (cần ít nhất 4 tasks mẫu, nhận: {len(initial_tasks)})"
    print(f"✅ 7. Lấy danh sách công việc thành công qua TCP Socket! Tổng số: {len(initial_tasks)} tasks")

    # B. Create new task
    new_task_title = f"Kiểm thử Socket TCP To-Do #{int(time.time())}"
    create_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "create",
        "title": new_task_title,
        "due": "Hôm nay 18:00",
        "priority": "high",
        "conversation_id": conv_id
    }, protocol.MSG_TYPE_TASK_OP_ACK, 4.0)
    assert create_ack and create_ack.get("status") == "OK", f"Lỗi tạo task: {create_ack}"
    tasks_after_create = create_ack.get("tasks", [])
    created_task = next((t for t in tasks_after_create if t.get("title") == new_task_title), None)
    assert created_task is not None, "Không tìm thấy task vừa tạo trong danh sách phản hồi"
    task_id = created_task.get("id")
    assert created_task.get("done") is False, "Task mới tạo phải ở trạng thái chưa hoàn thành (done=False)"
    print(f"✅ 8. Tạo mới công việc thành công! Task ID #{task_id}: '{new_task_title}' (Ưu tiên: {created_task.get('priority')})")

    # C. Toggle task done
    toggle_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "toggle",
        "id": task_id
    }, protocol.MSG_TYPE_TASK_OP_ACK, 4.0)
    assert toggle_ack and toggle_ack.get("status") == "OK", f"Lỗi toggle task: {toggle_ack}"
    tasks_after_toggle = toggle_ack.get("tasks", [])
    toggled_task = next((t for t in tasks_after_toggle if t.get("id") == task_id), None)
    assert toggled_task is not None and toggled_task.get("done") is True, f"Trạng thái task chưa đổi sang True: {toggled_task}"
    print(f"✅ 9. Đổi trạng thái công việc (Toggle Complete) thành công! Task ID #{task_id} -> done: True")

    # D. Delete task
    delete_ack = c1.send_and_wait({
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "delete",
        "id": task_id
    }, protocol.MSG_TYPE_TASK_OP_ACK, 4.0)
    assert delete_ack and delete_ack.get("status") == "OK", f"Lỗi xóa task: {delete_ack}"
    tasks_after_delete = delete_ack.get("tasks", [])
    assert not any(t.get("id") == task_id for t in tasks_after_delete), "Task vẫn còn tồn tại sau khi xóa"
    print(f"✅ 10. Xóa công việc khỏi CSDL PostgreSQL thành công! Danh sách còn lại: {len(tasks_after_delete)} tasks")

    # =========================================================================
    # PHẦN 3: KIỂM THỬ BÁO HIỆU CUỘC GỌI WEBRTC VOICE/VIDEO (CALL SIGNALING)
    # =========================================================================
    print("\n--- [PHẦN 3: BÁO HIỆU CUỘC GỌI WEBRTC VOICE/VIDEO CALL SIGNALING] ---")
    # A. Client 1 sends CALL_REQUEST (Cuộc gọi Video đi)
    c1.send_tcp_packet({
        "type": "webrtc_signal",
        "action": "call_request",
        "conversation_id": conv_id,
        "call_type": "video",
        "sender_name": "Phạm Huỳnh Quân"
    })

    # Client 2 should receive the call_request signal
    c2_call_req = c2.wait_for_ui_packet(
        lambda p: p.get("type") == "webrtc_signal" and p.get("action") == "call_request" and p.get("conversation_id") == conv_id,
        timeout=4.0
    )
    assert c2_call_req is not None, "Client 2 không nhận được tín hiệu call_request từ Client 1"
    assert c2_call_req.get("call_type") == "video", "Loại cuộc gọi không khớp (cần 'video')"
    print(f"✅ 11. Client 2 đã nhận được tín hiệu Cuộc gọi Video đến (Đổ chuông P2P) từ {c2_call_req.get('sender')}!")

    # B. Client 2 sends CALL_ACCEPT (Chấp nhận cuộc gọi)
    c2.send_tcp_packet({
        "type": "webrtc_signal",
        "action": "call_accept",
        "conversation_id": conv_id
    })

    # Client 1 should receive the call_accept signal
    c1_call_accept = c1.wait_for_ui_packet(
        lambda p: p.get("type") == "webrtc_signal" and p.get("action") == "call_accept" and p.get("conversation_id") == conv_id,
        timeout=4.0
    )
    assert c1_call_accept is not None, "Client 1 không nhận được tín hiệu call_accept từ Client 2"
    print("✅ 12. Client 1 đã nhận được tín hiệu 'call_accept' từ Client 2 (Bắt đầu bắt tay SDP P2P)!")

    # C. Client 1 sends SDP OFFER
    fake_offer_sdp = {"type": "offer", "sdp": "v=0\r\no=quan 123456 2 IN IP4 127.0.0.1\r\ns=ZaloVideoCall\r\n"}
    c1.send_tcp_packet({
        "type": "webrtc_signal",
        "action": "offer",
        "conversation_id": conv_id,
        "sdp": fake_offer_sdp
    })

    # Client 2 should receive SDP OFFER
    c2_offer = c2.wait_for_ui_packet(
        lambda p: p.get("type") == "webrtc_signal" and p.get("action") == "offer" and p.get("conversation_id") == conv_id,
        timeout=4.0
    )
    assert c2_offer is not None, "Client 2 không nhận được SDP OFFER"
    assert c2_offer.get("sdp", {}).get("type") == "offer", "Cấu trúc SDP Offer không đúng"
    print("✅ 13. Client 2 đã nhận được gói SDP OFFER từ Client 1!")

    # D. Client 2 sends SDP ANSWER
    fake_answer_sdp = {"type": "answer", "sdp": "v=0\r\no=lebao 654321 2 IN IP4 127.0.0.1\r\ns=ZaloVideoCall\r\n"}
    c2.send_tcp_packet({
        "type": "webrtc_signal",
        "action": "answer",
        "conversation_id": conv_id,
        "sdp": fake_answer_sdp
    })

    # Client 1 should receive SDP ANSWER
    c1_answer = c1.wait_for_ui_packet(
        lambda p: p.get("type") == "webrtc_signal" and p.get("action") == "answer" and p.get("conversation_id") == conv_id,
        timeout=4.0
    )
    assert c1_answer is not None, "Client 1 không nhận được SDP ANSWER"
    assert c1_answer.get("sdp", {}).get("type") == "answer", "Cấu trúc SDP Answer không đúng"
    print("✅ 14. Client 1 đã nhận được gói SDP ANSWER từ Client 2 (Kênh P2P đã sẵn sàng)!")

    # E. ICE Candidate exchange
    fake_candidate = {"candidate": "candidate:1 1 UDP 2130706431 127.0.0.1 50000 typ host", "sdpMid": "0", "sdpMLineIndex": 0}
    c1.send_tcp_packet({
        "type": "webrtc_signal",
        "action": "ice_candidate",
        "conversation_id": conv_id,
        "candidate": fake_candidate
    })

    c2_ice = c2.wait_for_ui_packet(
        lambda p: p.get("type") == "webrtc_signal" and p.get("action") == "ice_candidate" and p.get("conversation_id") == conv_id,
        timeout=4.0
    )
    assert c2_ice is not None and c2_ice.get("candidate") == fake_candidate, "Client 2 không nhận được ICE Candidate"
    print("✅ 15. Trao đổi ICE Candidate thành công giữa 2 máy khách!")

    # F. End call signal (CALL_END)
    c1.send_tcp_packet({
        "type": "webrtc_signal",
        "action": "call_end",
        "conversation_id": conv_id
    })

    c2_end = c2.wait_for_ui_packet(
        lambda p: p.get("type") == "webrtc_signal" and p.get("action") == "call_end" and p.get("conversation_id") == conv_id,
        timeout=4.0
    )
    assert c2_end is not None, "Client 2 không nhận được tín hiệu kết thúc cuộc gọi"
    print("✅ 16. Tín hiệu kết thúc cuộc gọi (call_end) đã được phát sóng tới đối phương thành công!")

    # G. Log call record into PostgreSQL database (CALL_LOG)
    c1.send_tcp_packet({
        "type": "call_log",
        "conversation_id": conv_id,
        "call_type": "video",
        "call_status": "completed",
        "duration": 52
    })

    # Both Client 1 and Client 2 should receive the call log chat message
    c1_call_log_msg = c1.wait_for_ui_packet(
        lambda p: p.get("type") == "chat_message" and p.get("message", {}).get("message_type") == "call" and p.get("message", {}).get("call_duration") == 52,
        timeout=4.0
    )
    c2_call_log_msg = c2.wait_for_ui_packet(
        lambda p: p.get("type") == "chat_message" and p.get("message", {}).get("message_type") == "call" and p.get("message", {}).get("call_duration") == 52,
        timeout=4.0
    )
    assert c1_call_log_msg is not None, "Client 1 không nhận được bản ghi lịch sử cuộc gọi"
    assert c2_call_log_msg is not None, "Client 2 không nhận được bản ghi lịch sử cuộc gọi"
    print(f"✅ 17. Lịch sử cuộc gọi đã được lưu vào CSDL PostgreSQL và phát sóng tới 2 máy (Thời lượng: {c1_call_log_msg['message']['formatted_duration']})!")

    # Disconnect
    c1.disconnect()
    c2.disconnect()
    print("\n" + "=" * 75)
    print("🎉 TẤT CẢ 17/17 BƯỚC KIỂM THỬ NHÓM 3 & NHÓM 4 ĐÃ ĐẠT 100% THÀNH CÔNG!")
    print("=" * 75)
    sys.stdout.flush()
    os._exit(0)

if __name__ == "__main__":
    run_test()
