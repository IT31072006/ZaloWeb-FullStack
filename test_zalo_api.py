#!/usr/bin/env python3
"""
test_zalo_api.py - Kiểm thử toàn diện tất cả tính năng API của Zalo Web:
1. Đăng ký tài khoản mới kèm avatar
2. Đăng nhập
3. Xem hồ sơ & Cập nhật ảnh đại diện
4. Lấy danh sách hội thoại
5. Gửi tin nhắn văn bản
6. Gửi tin nhắn ảnh
7. Gửi tin nhắn thoại (Audio)
8. Gửi đoạn mã code lập trình (Java UDPServer)
9. Đồng bộ tin nhắn thời gian thực (Real-time sync)
"""

import os
import sys
import requests
import io

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=" * 65)
    print("🧪 BẮT ĐẦU KIỂM THỬ HỆ THỐNG ZALO WEB (DJANGO + POSTGRESQL/SQLITE)")
    print("=" * 65)

    session = requests.Session()

    # 1. Kiểm tra trang chủ
    res = session.get(f"{BASE_URL}/")
    assert res.status_code == 200, f"Lỗi tải trang chủ: {res.status_code}"
    csrftoken = session.cookies.get('csrftoken', '')
    print("✅ 1. Tải trang chủ Zalo Web thành công (HTTP 200)")

    # 2. Đăng ký tài khoản mới kèm Avatar
    fake_avatar = io.BytesIO(b"FAKE_IMAGE_DATA_HEADER_PNG_OR_JPG_AVATAR")
    fake_avatar.name = "avatar_test.png"

    username_test = f"user_test_{os.getpid()}"
    reg_data = {
        'username': username_test,
        'password': 'password123',
        'display_name': 'Sinh Viên VKU Test',
        'phone': '0988776655',
        'bio': 'Kiểm thử đồ án Lập trình Mạng 2026',
        'gender': 'nam'
    }
    reg_files = {'avatar': ('avatar.png', fake_avatar, 'image/png')}

    res = session.post(
        f"{BASE_URL}/api/register/",
        data=reg_data,
        files=reg_files,
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code == 201, f"Lỗi đăng ký: {res.status_code} - {res.text}"
    user_info = res.json()['user']
    print(f"✅ 2. Đăng ký tài khoản thành công: {user_info['display_name']} (@{user_info['username']})")

    # 3. Lấy thông tin tài khoản hiện tại (/api/me/)
    res = session.get(f"{BASE_URL}/api/me/")
    assert res.status_code == 200 and res.json()['authenticated'] is True
    print(f"✅ 3. Xem hồ sơ cá nhân thành công: Bio='{res.json()['user']['bio']}', Avatar={res.json()['user']['avatar_url']}")

    # 4. Cập nhật hồ sơ & tải ảnh đại diện mới (/api/profile/update/)
    new_avatar = io.BytesIO(b"NEW_AVATAR_IMAGE_DATA_BYTES")
    new_avatar.name = "new_avatar.png"
    update_data = {
        'display_name': 'Sinh Viên VKU (Đã Đổi Tên)',
        'bio': 'Trạng thái mới: Đang làm bài tập giữa kỳ LTM',
        'phone': '0911223344'
    }
    update_files = {'avatar': ('new_avatar.png', new_avatar, 'image/png')}
    res = session.post(
        f"{BASE_URL}/api/profile/update/",
        data=update_data,
        files=update_files,
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code == 200, f"Lỗi cập nhật hồ sơ: {res.text}"
    updated_user = res.json()['user']
    print(f"✅ 4. Cập nhật hồ sơ & ảnh đại diện thành công: {updated_user['display_name']}")

    # 5. Khởi tạo cuộc trò chuyện 1-1 với @quan (ID 1)
    res = session.post(
        f"{BASE_URL}/api/conversations/create/",
        json={'is_group': False, 'user_id': 1},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code in [200, 201], f"Lỗi tạo cuộc trò chuyện: {res.text}"
    conv_data = res.json()
    conv_id = conv_data['id']
    print(f"✅ 5. Khởi tạo cuộc trò chuyện 1-1 thành công với '{conv_data['title']}' (ID: {conv_id})")

    # 6. Gửi tin nhắn văn bản đầu tiên (Lưu vào Database)
    res = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        json={'message_type': 'text', 'content': 'Chào bạn Quân, mình cùng làm bài tập socket nhé!'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code == 201
    msg_text = res.json()
    print(f"✅ 6. Gửi tin nhắn văn bản thành công (ID: {msg_text['id']}, Content: '{msg_text['content']}')")

    # Kiểm tra danh sách hội thoại bây giờ đã có cuộc trò chuyện này
    res = session.get(f"{BASE_URL}/api/conversations/")
    assert res.status_code == 200
    convs = res.json()
    assert any(c['id'] == conv_id for c in convs), "Hội thoại vừa nhắn tin chưa xuất hiện trong danh sách!"
    print(f"✅ 6.1. Danh sách hội thoại hiển thị đúng: Có {len(convs)} cuộc trò chuyện sau khi gửi tin nhắn.")

    # 7. Gửi tin nhắn hình ảnh
    img_data = io.BytesIO(b"FAKE_IMAGE_DATA_DEMO_SCENE")
    img_data.name = "screenshot_demo.png"
    res = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        data={'message_type': 'image', 'content': 'Ảnh chụp sơ đồ mạng Socket'},
        files={'attachment': ('screenshot_demo.png', img_data, 'image/png')},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code == 201
    msg_img = res.json()
    print(f"✅ 7. Gửi tin nhắn hình ảnh thành công (ID: {msg_img['id']}, URL: {msg_img['attachment_url']})")

    # 8. Gửi tin nhắn thoại Audio (Voice Note)
    audio_data = io.BytesIO(b"FAKE_AUDIO_WEBM_VOICE_NOTE_BYTES")
    audio_data.name = "voice_sample.webm"
    res = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        data={'message_type': 'audio', 'content': 'Tin nhắn ghi âm thoại'},
        files={'attachment': ('voice_sample.webm', audio_data, 'audio/webm')},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code == 201
    msg_audio = res.json()
    print(f"✅ 8. Gửi tin nhắn thoại ghi âm thành công (ID: {msg_audio['id']}, URL: {msg_audio['attachment_url']})")

    # 9. Gửi đoạn mã code lập trình
    sample_code = """// Đoạn mã Java UDP Server từ bài tập
DatagramSocket socket = new DatagramSocket(2023);
byte[] buf = new byte[1024];
DatagramPacket packet = new DatagramPacket(buf, buf.length);
socket.receive(packet);"""
    res = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        json={'message_type': 'code', 'content': sample_code, 'code_language': 'java'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res.status_code == 201
    msg_code = res.json()
    print(f"✅ 9. Gửi đoạn mã lập trình thành công (ID: {msg_code['id']}, Ngôn ngữ: {msg_code['code_language']})")

    # 10. Đồng bộ tin nhắn thời gian thực (/api/conversations/<id>/sync/)
    res = session.get(f"{BASE_URL}/api/conversations/{conv_id}/sync/?after_id={msg_text['id']}")
    assert res.status_code == 200
    synced_msgs = res.json()
    print(f"✅ 10. Đồng bộ Real-time Sync thành công: Nhận {len(synced_msgs)} tin nhắn mới sau ID {msg_text['id']}")

    # 11. Kiểm tra Chi tiết hội thoại kèm Shared Media & Files
    res = session.get(f"{BASE_URL}/api/conversations/{conv_id}/")
    assert res.status_code == 200
    detail = res.json()
    assert 'shared_media' in detail and 'shared_files' in detail
    print(f"✅ 11. Xem chi tiết hội thoại & ngăn thông tin thành công: {len(detail['members'])} thành viên, {len(detail['shared_media'])} ảnh/media")

    # 12. Kiểm tra Danh bạ & Nhóm (/api/contacts/)
    res = session.get(f"{BASE_URL}/api/contacts/")
    assert res.status_code == 200
    contacts_data = res.json()
    assert 'contacts' in contacts_data and 'groups' in contacts_data
    print(f"✅ 12. Lấy danh bạ thành công: {len(contacts_data['contacts'])} bạn bè, {len(contacts_data['groups'])} nhóm")

    # 13. Kiểm tra Cloud của tôi (/api/cloud/)
    res = session.get(f"{BASE_URL}/api/cloud/")
    assert res.status_code == 200
    cloud_data = res.json()
    assert cloud_data['is_cloud'] is True and cloud_data['title'] == 'Cloud của tôi'
    print(f"✅ 13. Khởi tạo & truy cập Cloud của tôi thành công (ID: {cloud_data['id']})")

    # 14. Kiểm tra Giao việc / To-do & Nhắc hẹn (/api/tasks/)
    res = session.get(f"{BASE_URL}/api/tasks/")
    assert res.status_code == 200
    tasks_list = res.json()
    assert len(tasks_list) > 0
    # Thử tạo task mới
    res_task = session.post(
        f"{BASE_URL}/api/tasks/",
        json={'action': 'create', 'title': 'Lập trình socket kiểm thử', 'due': '23:59', 'priority': 'high'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_task.status_code == 200
    print(f"✅ 14. Quản lý việc cần làm / To-do thành công: Có {len(res_task.json())} công việc")

    # 15. Kiểm tra Tìm kiếm tin nhắn theo từ khóa (/api/conversations/<id>/search/)
    res = session.get(f"{BASE_URL}/api/conversations/{conv_id}/search/?q=Chào")
    assert res.status_code == 200
    search_results = res.json()
    print(f"✅ 15. Tìm kiếm tin nhắn trong hội thoại thành công: Tìm thấy {len(search_results)} kết quả chứa từ khóa")

    # 16. Kiểm tra Ghim / Bỏ ghim cuộc hội thoại (/api/conversations/<id>/toggle_pin/)
    res_pin = session.post(f"{BASE_URL}/api/conversations/{conv_id}/toggle_pin/", headers={'X-CSRFToken': csrftoken})
    assert res_pin.status_code == 200
    assert res_pin.json()['is_pinned'] is True
    print(f"✅ 16. Ghim cuộc trò chuyện lên đầu danh sách thành công (is_pinned: {res_pin.json()['is_pinned']})")

    # 17. Kiểm tra Bật / Tắt thông báo (/api/conversations/<id>/toggle_mute/)
    res_mute = session.post(f"{BASE_URL}/api/conversations/{conv_id}/toggle_mute/", headers={'X-CSRFToken': csrftoken})
    assert res_mute.status_code == 200
    assert res_mute.json()['is_muted'] is True
    print(f"✅ 17. Tắt/Bật thông báo hội thoại thành công (is_muted: {res_mute.json()['is_muted']})")

    # 18. Kiểm tra Chuyển đổi mục Ưu tiên / Khác (/api/conversations/<id>/toggle_priority/)
    res_priority = session.post(f"{BASE_URL}/api/conversations/{conv_id}/toggle_priority/", headers={'X-CSRFToken': csrftoken})
    assert res_priority.status_code == 200
    print(f"✅ 18. Phân loại hội thoại vào mục Ưu tiên/Khác thành công (is_priority: {res_priority.json()['is_priority']})")

    # =========================================================================
    # GIAI ĐOẠN 2: TƯƠNG TÁC CHAT ĐẶC TRƯNG CỦA ZALO
    # =========================================================================

    # 19. Trả lời / Trích dẫn tin nhắn (Reply / Quote)
    txt_msg_id = msg_text['id']
    res_reply = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        json={
            'message_type': 'text',
            'content': 'Tôi đang phản hồi tin nhắn văn bản trước đó!',
            'reply_to_id': txt_msg_id
        },
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_reply.status_code in [200, 201]
    reply_msg = res_reply.json()
    assert reply_msg['reply_to_details'] is not None
    assert reply_msg['reply_to_details']['id'] == txt_msg_id
    print(f"✅ 19. Trả lời/Trích dẫn tin nhắn thành công (Reply ID: {reply_msg['id']} -> Quoted ID: {txt_msg_id})")

    # 20. Thả biểu cảm cảm xúc Reaction (❤️, 👍, 😂, 😮, 😢, 😡)
    res_react1 = session.post(
        f"{BASE_URL}/api/messages/{txt_msg_id}/react/",
        json={'emoji': '❤️'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_react1.status_code == 200
    reactions = res_react1.json()['reactions']
    assert any(r['emoji'] == '❤️' and r['count'] == 1 for r in reactions)
    print(f"✅ 20a. Thả cảm xúc ❤️ thành công: {reactions}")

    # Đổi cảm xúc sang 👍
    res_react2 = session.post(
        f"{BASE_URL}/api/messages/{txt_msg_id}/react/",
        json={'emoji': '👍'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_react2.status_code == 200
    reactions2 = res_react2.json()['reactions']
    assert any(r['emoji'] == '👍' and r['count'] == 1 for r in reactions2)
    print(f"✅ 20b. Đổi cảm xúc sang 👍 thành công: {reactions2}")

    # Nhấn lại 👍 để gỡ bỏ cảm xúc
    res_react3 = session.post(
        f"{BASE_URL}/api/messages/{txt_msg_id}/react/",
        json={'emoji': '👍'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_react3.status_code == 200
    assert len(res_react3.json()['reactions']) == 0
    print(f"✅ 20c. Hủy biểu cảm cảm xúc thành công khi bấm lại")

    # 21. Ghim tin nhắn trong cuộc trò chuyện (Pin Message)
    res_pin_msg = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/pin_message/",
        json={'message_id': txt_msg_id},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_pin_msg.status_code == 200
    pin_data = res_pin_msg.json()
    assert pin_data['pinned_message']['id'] == txt_msg_id
    print(f"✅ 21a. Ghim tin nhắn lên thanh tiêu đề thành công (Pinned Msg: {pin_data['pinned_message']['snippet']})")

    # Bỏ ghim tin nhắn
    res_unpin_msg = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/pin_message/",
        json={'message_id': None},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_unpin_msg.status_code == 200
    assert res_unpin_msg.json()['pinned_message'] is None
    print(f"✅ 21b. Bỏ ghim tin nhắn thành công")

    # 22. Thu hồi tin nhắn (Recall Message)
    # Gửi 1 tin nhắn để thu hồi
    res_to_recall = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        json={'message_type': 'text', 'content': 'Tin nhắn này chuẩn bị được thu hồi'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_to_recall.status_code in [200, 201]
    msg_to_recall_id = res_to_recall.json()['id']
    res_recalled = session.post(
        f"{BASE_URL}/api/messages/{msg_to_recall_id}/recall/",
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_recalled.status_code == 200
    recalled_msg = res_recalled.json()['msg']
    assert recalled_msg['is_recalled'] is True
    assert recalled_msg['content'] == "Tin nhắn đã được thu hồi"
    print(f"✅ 22. Thu hồi tin nhắn thành công (is_recalled: {recalled_msg['is_recalled']}, content: '{recalled_msg['content']}')")

    # 23. Xóa tin nhắn ở phía tôi (Delete for me)
    res_to_delete = session.post(
        f"{BASE_URL}/api/conversations/{conv_id}/send/",
        json={'message_type': 'text', 'content': 'Tin nhắn này sẽ bị xóa chỉ ở phía tôi'},
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_to_delete.status_code in [200, 201]
    msg_to_del_id = res_to_delete.json()['id']
    res_deleted = session.post(
        f"{BASE_URL}/api/messages/{msg_to_del_id}/delete/",
        headers={'X-CSRFToken': csrftoken}
    )
    assert res_deleted.status_code == 200

    # Kiểm tra xem user hiện tại không còn thấy tin nhắn này nữa
    res_check_del = session.get(f"{BASE_URL}/api/conversations/{conv_id}/messages/")
    visible_ids = [m['id'] for m in res_check_del.json()]
    assert msg_to_del_id not in visible_ids
    print(f"✅ 23. Xóa tin nhắn ở phía tôi thành công (Tin nhắn ID {msg_to_del_id} đã biến mất khỏi giao diện user)")

    print("=" * 65)
    print("🎉 TẤT CẢ 23/23 BÀI KIỂM THỬ ĐÃ VƯỢT QUA XUẤT SẮC!")
    print("=" * 65)

if __name__ == '__main__':
    run_tests()

