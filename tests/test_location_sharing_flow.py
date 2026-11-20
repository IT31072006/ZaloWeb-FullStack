#!/usr/bin/env python3
"""
Test Suite: Location Sharing (Bản đồ / Tọa độ GPS / Mini Map) via Socket TCP 5555 & PostgreSQL.
"""
import os
import sys
import socket
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
from server import ChatServer
import client_desktop

TEST_PORT = 5595

def run_tests():
    print("=" * 75)
    print("🧪 KIỂM THỬ: TÍNH NĂNG CHIA SẺ VỊ TRÍ ĐỊA LÝ (LOCATION SHARING / MINI MAP)")
    print("=" * 75)

    # 1. Khởi động ChatServer TCP
    server = ChatServer(host="127.0.0.1", port=TEST_PORT)
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    time.sleep(0.5)
    print(f"✅ 1. TCP Server khởi động thành công trên cổng {TEST_PORT}")

    # 2. Kết nối và đăng nhập 2 Clients: quan và bao
    sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock1.connect(("127.0.0.1", TEST_PORT))
    sock2.connect(("127.0.0.1", TEST_PORT))

    protocol.send_packet(sock1, {"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"})
    ack1 = protocol.recv_packet(sock1)
    assert ack1 and ack1.get("status") == "OK", f"Client 1 (quan) login failed: {ack1}"
    print(f"✅ 2. Client 1 (quan) đăng nhập thành công! User ID: {ack1['user']['id']}")

    protocol.send_packet(sock2, {"type": protocol.MSG_TYPE_LOGIN, "username": "bao", "password": "password123"})
    ack2 = protocol.recv_packet(sock2)
    assert ack2 and ack2.get("status") == "OK", f"Client 2 (bao) login failed: {ack2}"
    print(f"✅ 3. Client 2 (bao) đăng nhập thành công! User ID: {ack2['user']['id']}")

    # Tìm hội thoại chung giữa quan và bao
    convs1 = ack1.get("conversations", [])
    target_conv_id = None
    for c in convs1:
        # Kiểm tra hội thoại 1-1 với bao hoặc nhóm có bao
        members = [m.get("username") for m in c.get("members", [])]
        if "bao" in members or c.get("other_username") == "bao":
            target_conv_id = c["id"]
            break

    # Nếu chưa có hội thoại chung, tạo mới
    if not target_conv_id:
        protocol.send_packet(sock1, {
            "type": protocol.MSG_TYPE_CREATE_GROUP,
            "name": "Nhóm Test Vị trí VKU",
            "member_ids": [ack2["user"]["id"]]
        })
        time.sleep(0.5)
        # Nạp lại
        protocol.send_packet(sock1, {"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"})
        ack1_new = protocol.recv_packet(sock1)
        target_conv_id = ack1_new["conversations"][0]["id"]

    assert target_conv_id, "Không tìm thấy hoặc không tạo được hội thoại để kiểm thử"
    print(f"✅ 4. Sử dụng hội thoại ID #{target_conv_id} để kiểm thử chia sẻ vị trí")

    # 3. Client 1 gửi tin nhắn Vị trí qua TCP Socket
    loc_address = "Trường ĐH Công nghệ Thông tin & Truyền thông Việt - Hàn (VKU)"
    lat = 15.975300
    lng = 108.252400

    send_pkt = {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": target_conv_id,
        "message_type": "location",
        "content": loc_address,
        "location_address": loc_address,
        "latitude": lat,
        "longitude": lng,
    }
    protocol.send_packet(sock1, send_pkt)
    print("✅ 5. Client 1 đã gửi gói tin MSG_TYPE_CHAT kèm message_type='location', tọa độ VKU (15.9753, 108.2524)")

    # 4. Client 2 nhận gói tin thời gian thực qua TCP Socket
    received_location = None
    start_wait = time.time()
    while time.time() - start_wait < 4.0:
        pkt = protocol.recv_packet(sock2)
        if not pkt:
            continue
        if pkt.get("type") == protocol.MSG_TYPE_CHAT and pkt.get("message_type") == "location":
            received_location = pkt
            break

    assert received_location, "Client 2 không nhận được gói tin vị trí thời gian thực!"
    print(f"✅ 6. Client 2 đã nhận được tin nhắn vị trí thời gian thực từ {received_location.get('sender')}!")
    assert received_location.get("latitude") == lat, f"Sai vĩ độ: {received_location.get('latitude')}"
    assert received_location.get("longitude") == lng, f"Sai kinh độ: {received_location.get('longitude')}"
    assert received_location.get("location_address") == loc_address, f"Sai địa chỉ: {received_location.get('location_address')}"
    assert received_location.get("code_language") == f"{lat},{lng}", f"Sai code_language coords: {received_location.get('code_language')}"
    print(f"   📍 Vĩ độ: {received_location.get('latitude')}, Kinh độ: {received_location.get('longitude')}")
    print(f"   🏠 Địa chỉ: {received_location.get('location_address')}")

    # 5. Client 2 kiểm tra nạp lịch sử tin nhắn LOAD_HISTORY từ PostgreSQL
    protocol.send_packet(sock2, {
        "type": protocol.MSG_TYPE_LOAD_HISTORY,
        "conversation_id": target_conv_id
    })
    hist_ack = protocol.recv_packet(sock2)
    assert hist_ack and hist_ack.get("type") == protocol.MSG_TYPE_HISTORY_ACK, f"Phản hồi lịch sử sai: {hist_ack}"
    messages = hist_ack.get("messages", [])
    assert len(messages) > 0, "Lịch sử tin nhắn trống"
    
    # Tìm tin nhắn vị trí vừa lưu
    last_loc_msg = None
    for m in reversed(messages):
        if m.get("message_type") == "location":
            last_loc_msg = m
            break

    assert last_loc_msg, "Không tìm thấy tin nhắn vị trí trong CSDL PostgreSQL!"
    assert last_loc_msg.get("latitude") == lat
    assert last_loc_msg.get("longitude") == lng
    assert last_loc_msg.get("location_address") == loc_address
    print(f"✅ 7. CSDL PostgreSQL lưu trữ bền vững tin nhắn vị trí (ID #{last_loc_msg.get('id')})")

    # 6. Kiểm tra xem trước tin nhắn trong serialize_conversation
    from chat.models import Conversation, Message, User
    c_obj = Conversation.objects.get(id=target_conv_id)
    u_obj = User.objects.get(username="quan")
    conv_data = server.serialize_conversation(c_obj, u_obj)
    last_txt = conv_data.get("last_message", {}).get("preview", "")
    print(f"✅ 8. Xem trước hội thoại trong danh sách: '{last_txt}'")
    assert "[Vị trí]" in last_txt, f"Xem trước hội thoại phải có nhãn [Vị trí], thực tế: {last_txt}"

    # 7. Kiểm tra chuyển tiếp (Forward) tin nhắn vị trí
    fwd_pkt = {
        "type": protocol.MSG_TYPE_FORWARD_MESSAGE,
        "message_id": last_loc_msg["id"],
        "conversation_ids": [target_conv_id]
    }
    protocol.send_packet(sock1, fwd_pkt)
    
    fwd_ack = None
    start_wait = time.time()
    while time.time() - start_wait < 4.0:
        pkt = protocol.recv_packet(sock1)
        if pkt and pkt.get("type") == protocol.MSG_TYPE_FORWARD_MESSAGE_ACK:
            fwd_ack = pkt
            break

    assert fwd_ack and fwd_ack.get("status") == "OK", f"Lỗi chuyển tiếp tin nhắn vị trí: {fwd_ack}"
    print("✅ 9. Chuyển tiếp (Forward) tin nhắn vị trí thành công!")

    # Client 2 nhận tin nhắn chuyển tiếp
    fwd_loc = None
    start_wait = time.time()
    while time.time() - start_wait < 3.0:
        pkt = protocol.recv_packet(sock2)
        if pkt and pkt.get("type") == protocol.MSG_TYPE_CHAT and pkt.get("message_type") == "location":
            fwd_loc = pkt
            break
    assert fwd_loc, "Client 2 không nhận được tin nhắn vị trí chuyển tiếp"
    assert fwd_loc.get("latitude") == lat
    assert fwd_loc.get("longitude") == lng
    print("✅ 10. Tin nhắn vị trí chuyển tiếp giữ nguyên tọa độ bản đồ mini chính xác!")

    sock1.close()
    sock2.close()
    server.stop()
    print("=" * 75)
    print("🎉 TẤT CẢ 10 BƯỚC KIỂM THỬ CHIA SẺ VỊ TRÍ ĐỊA LÝ ĐÃ ĐẠT 100%!")
    print("=" * 75)
    os._exit(0)

if __name__ == "__main__":
    run_tests()
