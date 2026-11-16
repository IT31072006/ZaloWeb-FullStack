#!/usr/bin/env python3
"""
Test image with caption, voice note, and emoji text flow
"""
import os
import sys
import time
import socket
import base64
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
import client_desktop

def run_test():
    print("=" * 60)
    print("🧪 KIỂM THỬ: ẢNH KÈM CHÚ THÍCH, TIN NHẮN THOẠI & EMOJI")
    print("=" * 60)

    # 1. Connect Client A (quan) and Client B (0763538273)
    bridge_b = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert bridge_b.connect()
    ack_b = bridge_b.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "0763538273", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack_b and ack_b.get("status") == "OK"
    print("✅ Client B (lê bảo) đăng nhập thành công")

    bridge_a = client_desktop.ZaloTCPClient('127.0.0.1', 5555)
    assert bridge_a.connect()
    ack_a = bridge_a.send_and_wait({"type": protocol.MSG_TYPE_LOGIN, "username": "phammm", "password": "password123"}, protocol.MSG_TYPE_LOGIN_ACK, 3.0)
    assert ack_a and ack_a.get("status") == "OK"
    print("✅ Client A (phammm) đăng nhập thành công")

    # Get conversation id between phammm and 0763538273
    create_pkt = {
        "type": protocol.MSG_TYPE_CREATE_CONV,
        "target_username": "0763538273",
        "is_group": False
    }
    conv_ack = bridge_a.send_and_wait(create_pkt, protocol.MSG_TYPE_CREATE_CONV_ACK, 3.0)
    assert conv_ack and conv_ack.get("status") == "OK"
    conv_id = conv_ack["conversation"]["id"]
    print(f"✅ Hội thoại 1-1 ID: #{conv_id}")

    # 2. Test Text with Emojis
    emoji_text = "Xin chào Bảo! Cậu nhận được emoji này không? 😀👍❤️🔥"
    enc = protocol.encrypt_payload(emoji_text)
    bridge_a.send_tcp_packet({
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": conv_id,
        "content": f"[ENC:AES-256-GCM]{enc}",
        "is_encrypted": True,
        "cipher_algo": "AES-256-GCM"
    })
    time.sleep(0.5)

    # Check Client B's message cache
    msgs = bridge_b.messages_cache.get(conv_id, [])
    assert any(emoji_text in m.get("content", "") for m in msgs), f"Emoji message not found in {msgs}"
    print(f"✅ 1. Gửi và nhận tin nhắn Emoji thành công: '{emoji_text}'")

    # 3. Test Image with Caption
    sample_img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    img_b64 = base64.b64encode(sample_img_bytes).decode("utf-8")
    caption_text = "Ảnh chụp bài tập lớn mạng máy tính nè Bảo ơi!"

    bridge_a.send_tcp_packet({
        "type": protocol.MSG_TYPE_FILE,
        "conversation_id": conv_id,
        "file_name": "test_image.png",
        "file_size": len(sample_img_bytes),
        "file_data": img_b64,
        "attachment_url": "/media/attachments/2026/11/test_image.png",
        "is_image": True,
        "message_type": "image",
        "content": caption_text,
        "sha256": "dummy"
    })
    time.sleep(0.6)

    # Check Client B's message cache for image message
    msgs_b = bridge_b.messages_cache.get(conv_id, [])
    img_msg = next((m for m in msgs_b if m.get("message_type") == "image"), None)
    assert img_msg is not None, "Image message not found in Client B!"
    assert img_msg.get("content") == caption_text, f"Caption mismatch: {img_msg.get('content')}"
    print(f"✅ 2. Gửi ảnh kèm chú thích (Image with Caption) thành công!")
    print(f"   - Loại tin nhắn: {img_msg.get('message_type')}")
    print(f"   - Chú thích: '{img_msg.get('content')}'")
    print(f"   - File URL: '{img_msg.get('attachment_url')}'")

    # Verify file was written to disk for Client B
    rel_path = img_msg.get("attachment_url", "").lstrip("/")
    abs_path = os.path.join(BASE_DIR, rel_path)
    assert os.path.exists(abs_path), f"File not saved to disk at {abs_path}"
    print(f"✅ 3. Tệp ảnh đã tự động lưu thành công vào ổ đĩa Client B: {rel_path} ({os.path.getsize(abs_path)} bytes)")

    # 4. Test Voice Note (Audio)
    dummy_voice_bytes = b"RIFF....WAVEfmt ....data...."
    voice_b64 = base64.b64encode(dummy_voice_bytes).decode("utf-8")
    bridge_a.send_tcp_packet({
        "type": protocol.MSG_TYPE_FILE,
        "conversation_id": conv_id,
        "file_name": "voice_12345.webm",
        "file_size": len(dummy_voice_bytes),
        "file_data": voice_b64,
        "attachment_url": "/media/attachments/2026/11/voice_12345.webm",
        "is_image": False,
        "message_type": "audio",
        "content": "Tin nhắn thoại ghi âm",
        "sha256": "dummy"
    })
    time.sleep(0.6)

    msgs_b = bridge_b.messages_cache.get(conv_id, [])
    audio_msg = next((m for m in msgs_b if m.get("message_type") == "audio"), None)
    assert audio_msg is not None, "Audio message not found in Client B!"
    print(f"✅ 4. Gửi tin nhắn thoại (Voice Note) thành công! Loại: {audio_msg.get('message_type')}, URL: {audio_msg.get('attachment_url')}")

    # 5. Test Video (.webm Screencast and .mp4)
    dummy_video_bytes = b"\x1aE\xdf\xa3WebMHeader..."
    vid_b64 = base64.b64encode(dummy_video_bytes).decode("utf-8")
    bridge_a.send_tcp_packet({
        "type": protocol.MSG_TYPE_FILE,
        "conversation_id": conv_id,
        "file_name": "Screencast From 2026-11-16 08-00-00.webm",
        "file_size": len(dummy_video_bytes),
        "file_data": vid_b64,
        "attachment_url": "/media/attachments/2026/11/Screencast_test.webm",
        "is_image": False,
        "message_type": "video",
        "content": "Video quay màn hình bài tập nè!",
        "sha256": "dummy"
    })
    time.sleep(0.6)

    msgs_b = bridge_b.messages_cache.get(conv_id, [])
    vid_msg = next((m for m in msgs_b if m.get("message_type") == "video"), None)
    assert vid_msg is not None, "Video message not found in Client B!"
    assert vid_msg.get("content") == "Video quay màn hình bài tập nè!"
    print(f"✅ 5. Gửi video (Video Screencast .webm / .mp4) thành công! Loại: {vid_msg.get('message_type')}, Chú thích: '{vid_msg.get('content')}'")

    bridge_a.should_stop = True
    bridge_b.should_stop = True
    bridge_a.tcp_sock.close()
    bridge_b.tcp_sock.close()
    print("=" * 60)
    print("🎉 TẤT CẢ KIỂM THỬ ĐÃ VƯỢT QUA 100%!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
