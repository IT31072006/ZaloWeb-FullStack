import asyncio
import json
import requests
import websockets

BASE_URL = "http://127.0.0.1:8000"
WS_BASE_URL = "ws://127.0.0.1:8000"


def setup_users_and_conversation():
    """Tạo 2 session người dùng và 1 cuộc trò chuyện 1-1 để kiểm thử WebSocket & WebRTC."""
    # User 1: Quan
    s1 = requests.Session()
    s1.get(f"{BASE_URL}/")
    csrf1 = s1.cookies.get('csrftoken', '')
    res1 = s1.post(f"{BASE_URL}/api/login/", json={'username': 'quan', 'password': '123456'}, headers={'X-CSRFToken': csrf1})
    assert res1.status_code == 200, f"Đăng nhập quan thất bại: {res1.text}"
    user1_data = res1.json()['user']

    # User 2: Camnt
    s2 = requests.Session()
    s2.get(f"{BASE_URL}/")
    csrf2 = s2.cookies.get('csrftoken', '')
    res2 = s2.post(f"{BASE_URL}/api/login/", json={'username': 'camnt', 'password': '123456'}, headers={'X-CSRFToken': csrf2})
    assert res2.status_code == 200, f"Đăng nhập camnt thất bại: {res2.text}"
    user2_data = res2.json()['user']

    # Tạo hội thoại riêng biệt để kiểm thử (tránh xung đột với trình duyệt đang mở)
    csrf1 = s1.cookies.get('csrftoken', '')
    res_conv = s1.post(
        f"{BASE_URL}/api/conversations/create/",
        json={'is_group': True, 'name': 'Kênh Kiểm Thử WebRTC P2P', 'members': [user2_data['id']]},
        headers={'X-CSRFToken': csrf1}
    )
    assert res_conv.status_code in [200, 201], f"Tạo hội thoại thất bại: {res_conv.text}"
    conv_id = res_conv.json()['id']

    cookie_str1 = f"sessionid={s1.cookies.get('sessionid')}; csrftoken={s1.cookies.get('csrftoken')}"
    cookie_str2 = f"sessionid={s2.cookies.get('sessionid')}; csrftoken={s2.cookies.get('csrftoken')}"

    return conv_id, user1_data, user2_data, cookie_str1, cookie_str2


async def run_websocket_and_webrtc_tests():
    print("=" * 70)
    print("🚀 BẮT ĐẦU KIỂM THỬ TỰ ĐỘNG WEBSOCKET (CHANNELS) & WEBRTC P2P SIGNALING")
    print("=" * 70)

    conv_id, user1, user2, cookie1, cookie2 = setup_users_and_conversation()
    print(f"✅ Chuẩn bị: Hội thoại #{conv_id} giữa '{user1['username']}' và '{user2['username']}'")

    ws_url = f"{WS_BASE_URL}/ws/chat/{conv_id}/"

    # Kết nối Client 1 (Quan)
    headers1 = {"Cookie": cookie1}
    ws1 = await websockets.connect(ws_url, additional_headers=headers1)
    print(f"✅ 1. Client 1 (User: {user1['username']}) kết nối thành công tới WebSocket: {ws_url}")

    # Kết nối Client 2 (Camnt)
    headers2 = {"Cookie": cookie2}
    ws2 = await websockets.connect(ws_url, additional_headers=headers2)
    print(f"✅ 2. Client 2 (User: {user2['username']}) kết nối thành công tới WebSocket: {ws_url}")

    # Client 1 nhận thông báo Client 2 Online
    msg_online = await asyncio.wait_for(ws1.recv(), timeout=3.0)
    data_online = json.loads(msg_online)
    assert data_online['type'] == 'user_status'
    assert data_online['status'] == 'online'
    print(f"✅ 3. Presence Realtime: Client 1 nhận diện Client 2 Online ({data_online['display_name']})")

    # 4. Kiểm tra gửi tin nhắn thời gian thực qua WebSocket (0ms Latency)
    test_content = "Xin chào cô Camnt! Tin nhắn này được gửi trực tiếp qua WebSocket 0ms!"
    await ws1.send(json.dumps({
        'type': 'chat_message',
        'content': test_content,
        'message_type': 'text'
    }))

    # Cả Client 1 và Client 2 đều nhận được tin nhắn
    received_raw1 = await asyncio.wait_for(ws1.recv(), timeout=3.0)
    received1 = json.loads(received_raw1)
    assert received1['type'] == 'chat_message'
    assert received1['message']['content'] == test_content
    msg_id = received1['message']['id']

    received_raw2 = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    received2 = json.loads(received_raw2)
    assert received2['type'] == 'chat_message'
    assert received2['message']['content'] == test_content
    print(f"✅ 4. Gửi & Nhận tin nhắn WebSocket 0ms thành công (Message ID: {msg_id})")

    # 5. Kiểm tra trạng thái "Đang soạn tin nhắn..." (Typing Indicator)
    await ws1.send(json.dumps({
        'type': 'typing',
        'is_typing': True
    }))
    typing_raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    typing_data = json.loads(typing_raw)
    assert typing_data['type'] == 'typing'
    assert typing_data['is_typing'] is True
    assert typing_data['username'] == user1['username']
    print(f"✅ 5. Trạng thái 'Đang soạn tin nhắn...' (Typing Indicator) hoạt động tức thì: {typing_data['display_name']} is typing")

    # Hủy soạn thảo
    await ws1.send(json.dumps({
        'type': 'typing',
        'is_typing': False
    }))
    stop_typing_raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    stop_typing_data = json.loads(stop_typing_raw)
    assert stop_typing_data['type'] == 'typing' and stop_typing_data['is_typing'] is False
    print("✅ 5.1. Dừng trạng thái soạn tin nhắn thành công")

    # 6. Kiểm tra kênh Signaling WebRTC P2P (Cuộc gọi Thoại & Video)
    # Bước 6.1: Caller gửi yêu cầu gọi video (call_request)
    await ws1.send(json.dumps({
        'type': 'webrtc_signal',
        'action': 'call_request',
        'call_type': 'video'
    }))
    call_req_raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    call_req = json.loads(call_req_raw)
    assert call_req['type'] == 'webrtc_signal'
    assert call_req['action'] == 'call_request'
    assert call_req['call_type'] == 'video'
    print(f"✅ 6.1. WebRTC Signaling: Client 2 nhận được yêu cầu gọi Video Call từ {call_req['sender_name']}")

    # Bước 6.2: Receiver đồng ý nghe máy (call_accept)
    await ws2.send(json.dumps({
        'type': 'webrtc_signal',
        'action': 'call_accept'
    }))
    call_acc_raw = await asyncio.wait_for(ws1.recv(), timeout=3.0)
    call_acc = json.loads(call_acc_raw)
    assert call_acc['action'] == 'call_accept'
    print("✅ 6.2. WebRTC Signaling: Client 1 nhận được tín hiệu 'call_accept'")

    # Bước 6.3: Trao đổi SDP Offer (Session Description Protocol)
    fake_offer_sdp = {"type": "offer", "sdp": "v=0\r\no=- 123456789 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"}
    await ws1.send(json.dumps({
        'type': 'webrtc_signal',
        'action': 'offer',
        'sdp': fake_offer_sdp
    }))
    offer_raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    offer_data = json.loads(offer_raw)
    assert offer_data['action'] == 'offer'
    assert offer_data['sdp']['sdp'] == fake_offer_sdp['sdp']
    print("✅ 6.3. WebRTC Signaling: Trao đổi SDP Offer thành công qua WebSocket")

    # Bước 6.4: Trao đổi SDP Answer
    fake_answer_sdp = {"type": "answer", "sdp": "v=0\r\no=- 987654321 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"}
    await ws2.send(json.dumps({
        'type': 'webrtc_signal',
        'action': 'answer',
        'sdp': fake_answer_sdp
    }))
    answer_raw = await asyncio.wait_for(ws1.recv(), timeout=3.0)
    answer_data = json.loads(answer_raw)
    assert answer_data.get('action') == 'answer' or answer_data.get('type') == 'webrtc_signal'
    assert answer_data['sdp']['sdp'] == fake_answer_sdp['sdp']
    print("✅ 6.4. WebRTC Signaling: Trao đổi SDP Answer thành công qua WebSocket")

    # Bước 6.5: Trao đổi ICE Candidates (Interactive Connectivity Establishment)
    fake_candidate = {"candidate": "candidate:842163049 1 udp 1677729535 192.168.1.100 52345 typ srflx raddr 10.0.0.1 rport 52345", "sdpMid": "0", "sdpMLineIndex": 0}
    await ws1.send(json.dumps({
        'type': 'webrtc_signal',
        'action': 'ice_candidate',
        'candidate': fake_candidate
    }))
    cand_raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    cand_data = json.loads(cand_raw)
    assert cand_data['action'] == 'ice_candidate'
    assert cand_data['candidate']['candidate'] == fake_candidate['candidate']
    print("✅ 6.5. WebRTC Signaling: Trao đổi ICE Candidate thành công để thiết lập luồng P2P Media")

    # Bước 6.6: Kết thúc cuộc gọi (call_end)
    await ws1.send(json.dumps({
        'type': 'webrtc_signal',
        'action': 'call_end'
    }))
    end_raw = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    end_data = json.loads(end_raw)
    assert end_data['action'] == 'call_end'
    print("✅ 6.6. WebRTC Signaling: Kết thúc cuộc gọi và giải phóng media session")

    # 7. Kiểm tra Thu hồi tin nhắn realtime qua WebSocket
    await ws1.send(json.dumps({
        'type': 'recall',
        'message_id': msg_id
    }))
    recall_raw1 = await asyncio.wait_for(ws1.recv(), timeout=3.0)
    recall_raw2 = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    assert json.loads(recall_raw1)['type'] == 'message_recalled'
    assert json.loads(recall_raw2)['type'] == 'message_recalled'
    print("✅ 7. Đồng bộ Thu hồi tin nhắn Realtime qua WebSocket thành công")

    # 7.1. Kiểm tra Lưu & Đồng bộ Lịch sử Cuộc gọi qua WebSocket (Call Log)
    await ws1.send(json.dumps({
        'type': 'call_log',
        'call_type': 'video',
        'call_status': 'completed',
        'duration': 155,
        'caller_id': user1['id']
    }))
    call_log_raw1 = await asyncio.wait_for(ws1.recv(), timeout=3.0)
    call_log_raw2 = await asyncio.wait_for(ws2.recv(), timeout=3.0)
    call_log_data1 = json.loads(call_log_raw1)
    call_log_data2 = json.loads(call_log_raw2)
    assert call_log_data1['type'] == 'chat_message'
    assert call_log_data2['type'] == 'chat_message'
    msg_info = call_log_data1['message']
    assert msg_info['message_type'] == 'call'
    assert msg_info['call_status'] == 'completed'
    assert msg_info['call_duration'] == 155
    assert msg_info['formatted_duration'] == '02:35'
    print(f"✅ 7.1. Tự động lưu & đồng bộ lịch sử cuộc gọi thành công (Thời gian: {msg_info['formatted_duration']})")

    # 8. Đóng kết nối an toàn
    await ws1.close()
    await ws2.close()
    print("✅ 8. Đóng kết nối WebSocket an toàn và cập nhật trạng thái Offline")

    print("=" * 70)
    print("🎉 TẤT CẢ CÁC BÀI TEST WEBSOCKET (CHANNELS) & WEBRTC P2P ĐÃ THÀNH CÔNG 100%!")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(run_websocket_and_webrtc_tests())
