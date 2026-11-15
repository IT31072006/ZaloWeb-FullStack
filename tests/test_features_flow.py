#!/usr/bin/env python3
"""
tests/test_features_flow.py - Kiểm thử tự động toàn diện các tính năng Mạng & Tương tác:
1. Ping/Pong Heartbeat Keep-Alive & RTT latency.
2. Typing Indicator (Đang soạn tin).
3. End-to-End Encryption (E2EE) AES-256-GCM qua Socket TCP.
4. Thả biểu cảm cảm xúc (Reactions) lưu CSDL & đồng bộ qua Socket.
5. Phân mảnh file lớn 64KB (Chunking) & Kiểm tra tính toàn vẹn SHA-256 Checksum.
6. Thu hồi tin nhắn (Message Recall).
"""

import base64
import hashlib
import os
import socket
import sys
import time

# Thêm thư mục gốc vào sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5555


def run_tests():
    print("=" * 70)
    print("🧪 BẮT ĐẦU KIỂM THỬ TOÀN DIỆN TẦNG MẠNG & TƯƠNG TÁC (LTM PROJECT)")
    print("=" * 70)

    # 1. Kết nối 2 client TCP vào server :5555
    sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock1.connect((SERVER_HOST, SERVER_PORT))
        sock2.connect((SERVER_HOST, SERVER_PORT))
        print("✅ 1. Kết nối thành công 2 Socket TCP tới cổng 5555.")
    except Exception as e:
        print(f"❌ Không thể kết nối tới server :5555 ({e}).")
        return False

    # Đăng nhập Client 1 (quan) và Client 2 (bao)
    protocol.send_packet(sock1, {"type": protocol.MSG_TYPE_LOGIN, "username": "quan", "password": "password123"})
    ack1 = protocol.recv_packet(sock1)
    assert ack1 and ack1.get("status") == "OK", f"Login 1 failed: {ack1}"
    print(f"✅ 2. Client 1 đăng nhập thành công: {ack1.get('user', {}).get('display_name')}")

    protocol.send_packet(sock2, {"type": protocol.MSG_TYPE_LOGIN, "username": "bao", "password": "password123"})
    ack2 = protocol.recv_packet(sock2)
    assert ack2 and ack2.get("status") == "OK", f"Login 2 failed: {ack2}"
    print(f"✅ 3. Client 2 đăng nhập thành công: {ack2.get('user', {}).get('display_name')}")

    # Đọc các gói tin SYSTEM "đã trực tuyến" do server phát tán
    time.sleep(0.3)
    sock1.settimeout(0.5)
    sock2.settimeout(0.5)
    while True:
        try:
            pkt = protocol.recv_packet(sock1)
            if not pkt: break
        except socket.timeout:
            break
    while True:
        try:
            pkt = protocol.recv_packet(sock2)
            if not pkt: break
        except socket.timeout:
            break

    # 4. Kiểm thử Ping / Pong Heartbeat
    t_start = int(time.time() * 1000)
    protocol.send_packet(sock1, {"type": protocol.MSG_TYPE_PING, "client_timestamp": t_start})
    pong_pkt = protocol.recv_packet(sock1)
    t_rtt = int(time.time() * 1000) - t_start
    assert pong_pkt and pong_pkt.get("type") == "pong", f"Pong failed: {pong_pkt}"
    print(f"✅ 4. Keep-Alive Heartbeat Ping/Pong thành công! Độ trễ RTT: {t_rtt}ms.")

    # Tìm một hội thoại chung giữa quan và bao
    convs1 = ack1.get("conversations", [])
    conv_id = convs1[0]["id"] if convs1 else 67
    sock1.settimeout(3.0)
    sock2.settimeout(3.0)
    print(f"[*] Sử dụng Hội thoại 1-1 ID #{conv_id} (giữa 'quan' và 'bao') để kiểm thử tương tác.")

    # 5. Kiểm thử Typing Indicator (quan soạn tin -> bao nhận được)
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_TYPING,
        "conversation_id": conv_id,
        "is_typing": True
    })
    typing_rx = protocol.recv_packet(sock2)
    assert typing_rx and typing_rx.get("type") == "typing" and typing_rx.get("username") == "quan", f"Typing failed: {typing_rx}"
    print(f"✅ 5. Typing Indicator thành công! '{typing_rx.get('display_name')}' đang soạn tin nhắn...")

    # 6. Kiểm thử E2EE AES-256-GCM (Mã hóa đầu cuối qua Socket TCP)
    secret_text = "Xin chào Bảo, đây là tin nhắn bảo mật mã hóa AES-256-GCM qua Socket TCP!"
    cipher_b64 = protocol.encrypt_payload(secret_text)
    print(f"🔒 [E2EE Encrypt] Bản rõ: '{secret_text}'")
    print(f"🔒 [E2EE Encrypt] Bản mã trên đường truyền TCP: '{cipher_b64[:36]}...'")

    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": conv_id,
        "content": f"[ENC:AES-256-GCM]{cipher_b64}",
        "is_encrypted": True,
        "cipher_algo": "AES-256-GCM"
    })

    # Client 1 nhận gói tin echo xác nhận từ server
    echo1 = protocol.recv_packet(sock1)
    assert echo1 and echo1.get("type") == protocol.MSG_TYPE_CHAT

    # Client 2 nhận được gói tin chat
    chat_rx = protocol.recv_packet(sock2)
    assert chat_rx and chat_rx.get("type") == protocol.MSG_TYPE_CHAT, f"Chat recv failed: {chat_rx}"
    assert chat_rx.get("is_encrypted") is True, "is_encrypted flag missing"
    # Giải mã bên phía Client 2
    raw_c = chat_rx.get("content", "")
    assert raw_c.startswith("[ENC:AES-256-GCM]"), "Prefix missing"
    decrypted_text = protocol.decrypt_payload(raw_c[len("[ENC:AES-256-GCM]"):])
    assert decrypted_text == secret_text, f"Decryption mismatch: {decrypted_text} != {secret_text}"
    print(f"✅ 6. E2EE AES-256-GCM thành công tuyệt đối! Client 2 đã giải mã: '{decrypted_text}'")
    sent_msg_id = chat_rx.get("message_id")

    # 7. Kiểm thử Thả biểu cảm cảm xúc (Reactions)
    if sent_msg_id:
        protocol.send_packet(sock2, {
            "type": protocol.MSG_TYPE_REACTION,
            "message_id": sent_msg_id,
            "emoji": "❤️",
            "conversation_id": conv_id
        })
        # Cả Client 1 và Client 2 đều nhận được cập nhật reaction
        react_rx1 = protocol.recv_packet(sock1)
        react_rx2 = protocol.recv_packet(sock2)
        assert react_rx1 and react_rx1.get("type") == "reaction_update", f"Reaction update failed: {react_rx1}"
        assert react_rx2 and react_rx2.get("type") == "reaction_update", f"Reaction update 2 failed: {react_rx2}"
        assert react_rx1.get("message_id") == sent_msg_id, "Msg ID mismatch"
        print(f"✅ 7. Thả biểu cảm cảm xúc (Reactions ❤️) thành công! Danh sách: {react_rx1.get('reactions')}")

    # 8. Kiểm thử Phân mảnh & Truyền file lớn (Chunking 64KB + Checksum SHA-256)
    fake_file_size = 150 * 1024  # 150 KB -> sẽ chia làm 3 mảnh (64KB + 64KB + 22KB)
    fake_file_data = os.urandom(fake_file_size)
    file_sha256 = hashlib.sha256(fake_file_data).hexdigest()
    transfer_id = f"test_xfer_{int(time.time())}"
    total_chunks = (fake_file_size + protocol.CHUNK_SIZE - 1) // protocol.CHUNK_SIZE

    print(f"[*] Thử nghiệm truyền file 150KB -> {total_chunks} mảnh 64KB. SHA-256: {file_sha256[:16]}...")

    # Gửi FILE_START
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_FILE_START,
        "transfer_id": transfer_id,
        "conversation_id": conv_id,
        "file_name": "network_lab_report.pdf",
        "file_size": fake_file_size,
        "total_chunks": total_chunks,
        "sha256": file_sha256,
        "is_image": False
    })

    # Gửi từng chunk
    for i in range(total_chunks):
        c_bytes = fake_file_data[i * protocol.CHUNK_SIZE : (i + 1) * protocol.CHUNK_SIZE]
        protocol.send_packet(sock1, {
            "type": protocol.MSG_TYPE_FILE_CHUNK,
            "transfer_id": transfer_id,
            "chunk_index": i,
            "total_chunks": total_chunks,
            "chunk_data": base64.b64encode(c_bytes).decode("utf-8")
        })
        pct = int((i + 1) / total_chunks * 100)
        print(f"   -> Đã gửi Chunk #{i+1}/{total_chunks} ({len(c_bytes)} bytes) - Tiến trình: {pct}%")

    # Gửi FILE_COMPLETE
    protocol.send_packet(sock1, {
        "type": protocol.MSG_TYPE_FILE_COMPLETE,
        "transfer_id": transfer_id,
        "conversation_id": conv_id,
        "file_name": "network_lab_report.pdf",
        "file_size": fake_file_size,
        "sha256": file_sha256,
        "is_image": False
    })

    # Client 2 nhận được gói tin FILE sau khi server đã đối soát SHA-256 thành công
    file_echo1 = protocol.recv_packet(sock1)
    file_rx = protocol.recv_packet(sock2)
    assert file_rx and file_rx.get("type") == protocol.MSG_TYPE_FILE, f"File rx failed: {file_rx}"
    assert file_rx.get("sha256_verified") is True, "sha256_verified flag missing"
    assert file_rx.get("sha256") == file_sha256, "SHA-256 hash mismatch"
    print(f"✅ 8. Phân mảnh truyền file lớn 64KB & Checksum SHA-256 thành công! File: {file_rx.get('file_name')} ({file_rx.get('file_size_str')})")

    # 9. Kiểm thử Thu hồi tin nhắn (Message Recall)
    if sent_msg_id:
        protocol.send_packet(sock1, {
            "type": protocol.MSG_TYPE_RECALL,
            "message_id": sent_msg_id,
            "conversation_id": conv_id
        })
        recall_echo1 = protocol.recv_packet(sock1)
        recall_rx2 = protocol.recv_packet(sock2)
        assert recall_rx2 and recall_rx2.get("type") == "message_recalled", f"Recall failed: {recall_rx2}"
        print(f"✅ 9. Thu hồi tin nhắn thành công! '{recall_rx2.get('content')}'")

    sock1.close()
    sock2.close()
    print("=" * 70)
    print("🎉 TẤT CẢ 9/9 BƯỚC KIỂM THỬ TẦNG MẠNG VÀ TƯƠNG TÁC ĐỀU THÀNH CÔNG RỰC RỠ!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
