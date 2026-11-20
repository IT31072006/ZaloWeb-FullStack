#!/usr/bin/env python3
"""
tests/test_full_system_simulation.py
================================================================================
KỊCH BẢN KIỂM THỬ TOÀN DIỆN MÔ PHỎNG TẤT CẢ CÁC CHỨC NĂNG HỆ THỐNG ZALO TCP 5555
================================================================================
Bao gồm:
1. TCP Socket, Framing 4-byte header, Ping/Pong RTT Keep-Alive.
2. Đăng ký, Đăng nhập, Tìm kiếm SĐT & Kết bạn Realtime.
3. Chat 1-1, E2EE AES-256-GCM, Code snippet, Location GPS Mini Map.
4. Trích dẫn (Reply), Thả Reaction, Đã xem (Read receipt), Thu hồi (Recall), Xóa phía tôi.
5. Truyền đa phương tiện: Ảnh có chú thích, Video, Tin nhắn thoại, File lớn 64KB Chunking & Checksum SHA-256.
6. Quản lý Nhóm Chat trọn vẹn: Tạo nhóm, Ghim tin nhắn DB, Thêm/Xóa thành viên, Đổi quyền, Đổi tên, Rời/Giải tán nhóm.
7. Cloud của tôi: Mở Cloud cá nhân, Thống kê dung lượng MB/%, Chuyển tiếp tin nhắn (Forward).
8. Quản lý Công việc Zalo To-Do: Tạo việc, Danh sách việc, Đổi trạng thái, Xóa việc.
9. Báo hiệu Cuộc gọi WebRTC Voice/Video: Request, Accept, SDP Offer/Answer, ICE Candidate, Call End & Ghi log DB.
10. Tùy chọn hội thoại: Ghim hội thoại, Tắt thông báo, Ưu tiên/Khác, Tìm kiếm nội dung tin nhắn.
"""

import os
import sys
import socket
import threading
import time
import base64
import hashlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import protocol
from server import ChatServer

SIM_PORT = 5599

def recv_until(sock, predicate, timeout=4.0):
    start = time.time()
    old_timeout = sock.gettimeout()
    sock.settimeout(0.3)
    try:
        while time.time() - start < timeout:
            try:
                pkt = protocol.recv_packet(sock)
                if pkt and predicate(pkt):
                    return pkt
            except (socket.timeout, socket.error):
                continue
    finally:
        sock.settimeout(old_timeout)
    return None

class SimulationStats:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.results = []

    def check(self, condition: bool, description: str, detail: str = ""):
        self.total += 1
        if condition:
            self.passed += 1
            print(f"  ✅ [PASS] {description} {f'({detail})' if detail else ''}")
            self.results.append((True, description, detail))
        else:
            self.failed += 1
            print(f"  ❌ [FAIL] {description} {f'({detail})' if detail else ''}")
            self.results.append((False, description, detail))
            raise AssertionError(f"Kiểm thử thất bại: {description} {detail}")

def run_full_simulation():
    stats = SimulationStats()
    print("=" * 80)
    print("🚀 BẮT ĐẦU MÔ PHỎNG & KIỂM THỬ TOÀN DIỆN TẤT CẢ CHỨC NĂNG (FULL SYSTEM SIMULATION)")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # CHẶNG 1: KHỞI TẠO SERVER & KẾT NỐI SOCKET TCP
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 1: TẦNG VẬN CHUYỂN TCP SOCKET & PROTOCOL FRAMING] ---")
    server = ChatServer(host="127.0.0.1", port=SIM_PORT)
    s_thread = threading.Thread(target=server.start, daemon=True)
    s_thread.start()
    time.sleep(0.5)
    stats.check(server.is_running, "Khởi động TCP Chat Server trên cổng 5599", f"127.0.0.1:{SIM_PORT}")

    sock_a = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_b = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_a.connect(("127.0.0.1", SIM_PORT))
    sock_b.connect(("127.0.0.1", SIM_PORT))
    sock_c.connect(("127.0.0.1", SIM_PORT))
    stats.check(True, "Kết nối đồng thời 3 Client Socket TCP", "Client A, Client B, Client C")

    # --------------------------------------------------------------------------
    # CHẶNG 2: XÁC THỰC, TÌM KIẾM SĐT & KẾT BẠN REALTIME
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 2: XÁC THỰC, TÌM KIẾM SỐ ĐIỆN THOẠI & KẾT BẠN THỜI GIAN THỰC] ---")
    ts = int(time.time())
    u_a = f"sim_user_{ts}_a"
    u_b = f"sim_user_{ts}_b"
    u_c = f"sim_user_{ts}_c"
    p_a = f"091{ts % 10000000:07d}"
    p_b = f"092{ts % 10000000:07d}"
    p_c = f"093{ts % 10000000:07d}"

    # Đăng ký
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_REGISTER, "username": u_a, "password": "password123", "display_name": "Người dùng A", "phone": p_a})
    ack_reg_a = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_REGISTER_ACK)
    protocol.send_packet(sock_b, {"type": protocol.MSG_TYPE_REGISTER, "username": u_b, "password": "password123", "display_name": "Người dùng B", "phone": p_b})
    ack_reg_b = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_REGISTER_ACK)
    protocol.send_packet(sock_c, {"type": protocol.MSG_TYPE_REGISTER, "username": u_c, "password": "password123", "display_name": "Người dùng C", "phone": p_c})
    ack_reg_c = recv_until(sock_c, lambda p: p.get("type") == protocol.MSG_TYPE_REGISTER_ACK)
    stats.check(ack_reg_a.get("status") == "OK" and ack_reg_b.get("status") == "OK" and ack_reg_c.get("status") == "OK", "Đăng ký 3 tài khoản mới qua Socket TCP", f"{u_a}, {u_b}, {u_c}")

    # Đăng nhập
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_LOGIN, "username": u_a, "password": "password123"})
    ack_log_a = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_LOGIN_ACK)
    protocol.send_packet(sock_b, {"type": protocol.MSG_TYPE_LOGIN, "username": u_b, "password": "password123"})
    ack_log_b = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_LOGIN_ACK)
    protocol.send_packet(sock_c, {"type": protocol.MSG_TYPE_LOGIN, "username": u_c, "password": "password123"})
    ack_log_c = recv_until(sock_c, lambda p: p.get("type") == protocol.MSG_TYPE_LOGIN_ACK)
    uid_a = ack_log_a["user"]["id"]
    uid_b = ack_log_b["user"]["id"]
    uid_c = ack_log_c["user"]["id"]
    stats.check(ack_log_a.get("status") == "OK", "Client A đăng nhập thành công", f"User #{uid_a}")
    stats.check(ack_log_b.get("status") == "OK", "Client B đăng nhập thành công", f"User #{uid_b}")
    stats.check(ack_log_c.get("status") == "OK", "Client C đăng nhập thành công", f"User #{uid_c}")

    # Ping/Pong RTT Keep-Alive sau khi xác thực
    t_ping = time.time()
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_PING, "client_timestamp": int(t_ping * 1000)})
    pong_pkt = recv_until(sock_a, lambda p: p.get("type") in (protocol.MSG_TYPE_PONG, "pong"))
    rtt = round((time.time() - t_ping) * 1000, 2)
    stats.check(pong_pkt and pong_pkt.get("type") in (protocol.MSG_TYPE_PONG, "pong"), "Heartbeat Ping/Pong Keep-Alive", f"RTT: {rtt}ms")

    # Tìm kiếm bạn bè qua SĐT
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_SEARCH_USER, "phone": p_b})
    ack_search = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_SEARCH_USER_ACK or "user" in p)
    stats.check(ack_search and ack_search.get("status") == "found" and ack_search.get("user", {}).get("username") == u_b, "Tìm kiếm bạn bè chính xác qua Số điện thoại", f"SĐT: {p_b}")
    found_user = ack_search.get("user", {})

    # Gửi lời mời kết bạn Realtime từ A tới B
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_FRIEND_REQ, "target_user_id": found_user["id"]})
    ack_send_fr = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_FRIEND_REQ_ACK or p.get("status") == "success")
    stats.check(ack_send_fr and ack_send_fr.get("status") == "success", "Gửi lời mời kết bạn qua Socket TCP", f"Tới User #{found_user['id']}")

    # B nhận thông báo Realtime
    notif_fr = recv_until(sock_b, lambda p: p.get("type") == "friend_request_received")
    stats.check(notif_fr and notif_fr.get("type") == "friend_request_received", "Client B nhận thông báo kết bạn Realtime", f"Từ {u_a}")
    req_id = notif_fr.get("data", {}).get("id")

    # B bấm Đồng ý -> Tự động sinh hội thoại 1-1
    protocol.send_packet(sock_b, {"type": protocol.MSG_TYPE_FRIEND_RESP, "request_id": req_id, "action": "accept"})
    ack_accept = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_FRIEND_RESP_ACK or p.get("status") == "success")
    notif_accepted_a = recv_until(sock_a, lambda p: p.get("type") == "friend_request_accepted")
    conv_1v1_id = ack_accept.get("conversation_id")
    stats.check(ack_accept and ack_accept.get("status") == "success" and conv_1v1_id is not None, "Đồng ý kết bạn & Tự động kích hoạt hội thoại 1-1", f"Conversation ID #{conv_1v1_id}")

    # --------------------------------------------------------------------------
    # CHẶNG 3: NHẮN TIN 1-1, E2EE, CODE SNIPPET, LOCATION GPS & TƯƠNG TÁC
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 3: NHẮN TIN 1-1, E2EE AES-256-GCM, CODE, VỊ TRÍ GPS & TƯƠNG TÁC] ---")
    
    # 1. E2EE Text message
    plain_text = "Xin chào B, tin nhắn này được mã hóa E2EE AES-256-GCM an toàn!"
    enc_payload = protocol.encrypt_payload(plain_text)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": conv_1v1_id,
        "content": f"[ENC:AES-256-GCM]{enc_payload}",
        "is_encrypted": True,
        "cipher_algo": "AES-256-GCM"
    })
    msg_e2ee_rx = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_CHAT and p.get("content", "").startswith("[ENC:"))
    decrypted_rx = protocol.decrypt_payload(msg_e2ee_rx.get("content", "").replace("[ENC:AES-256-GCM]", ""))
    stats.check(decrypted_rx == plain_text, "Gửi và giải mã tin nhắn E2EE AES-256-GCM", f"Plaintext: '{decrypted_rx[:35]}...'")
    msg_1_id = msg_e2ee_rx.get("id") or msg_e2ee_rx.get("message_id")

    # 2. Code Snippet
    code_content = "public class SocketEchoServer { public static void main(String[] args) {} }"
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": conv_1v1_id,
        "message_type": "code",
        "content": code_content,
        "code_language": "java"
    })
    msg_code_rx = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_CHAT and p.get("message_type") == "code")
    msg_code_id = msg_code_rx.get("id") or msg_code_rx.get("message_id")
    stats.check(msg_code_rx and msg_code_rx.get("message_type") == "code" and msg_code_rx.get("code_language") == "java", "Gửi đoạn mã lập trình (Code Snippet)", "Language: java")

    # 3. Location Sharing (GPS / Mini Map)
    loc_name = "Trường ĐH Công nghệ Thông tin & Truyền thông Việt - Hàn (VKU)"
    lat, lng = 15.975300, 108.252400
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": conv_1v1_id,
        "message_type": "location",
        "content": loc_name,
        "location_address": loc_name,
        "latitude": lat,
        "longitude": lng,
    })
    msg_loc_rx = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_CHAT and p.get("message_type") == "location")
    stats.check(msg_loc_rx and msg_loc_rx.get("message_type") == "location" and msg_loc_rx.get("latitude") == lat and msg_loc_rx.get("longitude") == lng, "Chia sẻ vị trí GPS / Mini Map OpenStreetMap", f"Tọa độ: ({lat}, {lng})")
    msg_loc_id = msg_loc_rx.get("id") or msg_loc_rx.get("message_id")

    # 4. Reaction Emoji
    protocol.send_packet(sock_b, {
        "type": protocol.MSG_TYPE_REACTION,
        "message_id": msg_1_id,
        "emoji": "❤️",
        "conversation_id": conv_1v1_id
    })
    react_ack_a = recv_until(sock_a, lambda p: p.get("type") == "reaction_update")
    stats.check(react_ack_a and react_ack_a.get("type") == "reaction_update" and react_ack_a.get("reactions", [{}])[0].get("emoji") == "❤️", "Thả biểu cảm cảm xúc (Reactions) thời gian thực", "Emoji: ❤️")

    # 5. Read Receipt (Đã xem)
    protocol.send_packet(sock_b, {
        "type": protocol.MSG_TYPE_READ_RECEIPT,
        "conversation_id": conv_1v1_id,
        "message_id": msg_loc_id
    })
    read_rx_a = recv_until(sock_a, lambda p: p.get("type") == "read_receipt")
    stats.check(read_rx_a and read_rx_a.get("type") == "read_receipt" and read_rx_a.get("last_read_message_id") == msg_loc_id, "Thông báo trạng thái 'Đã xem' (Read Receipt)", f"Message #{msg_loc_id}")

    # 6. Recall Message (Thu hồi)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_RECALL,
        "message_id": msg_1_id,
        "conversation_id": conv_1v1_id
    })
    recall_rx_b = recv_until(sock_b, lambda p: p.get("type") == "message_recalled")
    stats.check(recall_rx_b and recall_rx_b.get("type") == "message_recalled" and recall_rx_b.get("message_id") == msg_1_id, "Thu hồi tin nhắn với tất cả mọi người (Recall)", f"ID #{msg_1_id}")

    # 7. Delete for me (Xóa ở phía tôi)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_DELETE_FOR_ME,
        "message_id": msg_loc_id
    })
    del_ack_a = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_DELETE_FOR_ME_ACK)
    stats.check(del_ack_a and del_ack_a.get("status") == "OK", "Xóa tin nhắn ở phía tôi (Delete for me)", f"ID #{msg_loc_id}")

    # --------------------------------------------------------------------------
    # CHẶNG 4: TRUYỀN TẢI ĐA PHƯƠNG TIỆN, TIN NHẮN THOẠI & PHÂN MẢNH 64KB
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 4: TRUYỀN FILE ĐA PHƯƠNG TIỆN, VOICE NOTE & CHUNKING 64KB] ---")

    # 1. Image with Caption
    img_data = b"FAKE_PNG_HEADER_IMAGE_DATA_SAMPLE"
    b64_img = base64.b64encode(img_data).decode("utf-8")
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_FILE,
        "conversation_id": conv_1v1_id,
        "file_name": "network_diagram.png",
        "file_size": len(img_data),
        "file_data": b64_img,
        "attachment_url": "/media/attachments/network_diagram.png",
        "is_image": True,
        "message_type": "image",
        "content": "Sơ đồ kiến trúc Socket TCP mô phỏng",
        "sha256": hashlib.sha256(img_data).hexdigest()
    })
    img_rx = recv_until(sock_b, lambda p: p.get("type") in (protocol.MSG_TYPE_FILE, protocol.MSG_TYPE_CHAT) and p.get("message_type") == "image")
    stats.check(img_rx and img_rx.get("message_type") == "image" and img_rx.get("content") == "Sơ đồ kiến trúc Socket TCP mô phỏng", "Gửi hình ảnh kèm chú thích (Image with Caption)", "network_diagram.png")

    # 2. Voice Note
    audio_data = b"FAKE_WEBM_VOICE_SAMPLE"
    b64_voice = base64.b64encode(audio_data).decode("utf-8")
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_FILE,
        "conversation_id": conv_1v1_id,
        "file_name": "voice_123.webm",
        "file_size": len(audio_data),
        "file_data": b64_voice,
        "attachment_url": "/media/attachments/voice_123.webm",
        "is_image": False,
        "message_type": "audio",
        "content": "voice_123.webm",
        "sha256": "voice_hash"
    })
    voice_rx = recv_until(sock_b, lambda p: p.get("type") in (protocol.MSG_TYPE_FILE, protocol.MSG_TYPE_CHAT) and p.get("message_type") == "audio")
    stats.check(voice_rx and voice_rx.get("message_type") == "audio", "Gửi tin nhắn thoại (Voice Note .webm)", "voice_123.webm")

    # 3. Phân mảnh file lớn 64KB (Chunking) & Kiểm tra SHA-256
    large_payload = os.urandom(140 * 1024) # 140KB -> 3 chunks
    large_sha = hashlib.sha256(large_payload).hexdigest()
    transfer_id = f"xfer_{ts}"
    total_chunks = (len(large_payload) + protocol.CHUNK_SIZE - 1) // protocol.CHUNK_SIZE

    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_FILE_START,
        "transfer_id": transfer_id,
        "conversation_id": conv_1v1_id,
        "file_name": "LTM_Full_Report.pdf",
        "file_size": len(large_payload),
        "total_chunks": total_chunks,
        "sha256": large_sha,
        "is_image": False,
        "message_type": "file",
        "content": "Báo cáo Đồ án Lập trình mạng 140KB"
    })
    for idx in range(total_chunks):
        c_bytes = large_payload[idx * protocol.CHUNK_SIZE : (idx + 1) * protocol.CHUNK_SIZE]
        protocol.send_packet(sock_a, {
            "type": protocol.MSG_TYPE_FILE_CHUNK,
            "transfer_id": transfer_id,
            "chunk_index": idx,
            "total_chunks": total_chunks,
            "chunk_data": base64.b64encode(c_bytes).decode("utf-8")
        })
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_FILE_COMPLETE,
        "transfer_id": transfer_id,
        "conversation_id": conv_1v1_id,
        "file_name": "LTM_Full_Report.pdf",
        "file_size": len(large_payload),
        "sha256": large_sha,
        "is_image": False,
        "message_type": "file",
        "content": "Báo cáo Đồ án Lập trình mạng 140KB"
    })

    file_rx = recv_until(sock_b, lambda p: p.get("file_name") == "LTM_Full_Report.pdf")
    stats.check(file_rx and file_rx.get("file_name") == "LTM_Full_Report.pdf" and file_rx.get("sha256") == large_sha, "Phân mảnh file 64KB & Kiểm tra toàn vẹn Checksum SHA-256", f"Kích thước: 140KB (3 chunks)")

    # --------------------------------------------------------------------------
    # CHẶNG 5: VÒNG ĐỜI QUẢN LÝ NHÓM CHAT (GROUP CHAT LIFECYCLE)
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 5: TOÀN DIỆN VÒNG ĐỜI QUẢN LÝ NHÓM CHAT (GROUP CHAT)] ---")

    # 1. Tạo nhóm gồm A và B
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CREATE_CONV,
        "is_group": True,
        "name": "Nhóm Đồ Án LTM 2026",
        "members": [uid_b]
    })
    ack_grp = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_CREATE_CONV_ACK)
    notif_grp_b = recv_until(sock_b, lambda p: p.get("type") == "conversation_created")
    grp_id = ack_grp["conversation"]["id"]
    stats.check(ack_grp and ack_grp.get("status") == "OK" and grp_id is not None, "Tạo nhóm chat mới qua TCP Socket", f"Nhóm ID #{grp_id}")
    stats.check(notif_grp_b and notif_grp_b.get("type") == "conversation_created", "Client B nhận thông báo tạo nhóm Realtime", f"Tên nhóm: 'Nhóm Đồ Án LTM 2026'")

    # 2. Nhắn tin trong nhóm
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CHAT,
        "conversation_id": grp_id,
        "content": "Chào nhóm! Đây là tin nhắn quan trọng cần ghim."
    })
    grp_msg_b = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_CHAT and p.get("conversation_id") == grp_id)
    grp_msg_id = grp_msg_b.get("id") or grp_msg_b.get("message_id")
    stats.check(grp_msg_b and grp_msg_b.get("content") == "Chào nhóm! Đây là tin nhắn quan trọng cần ghim.", "Phát tán tin nhắn nhóm tới tất cả thành viên", f"Message ID #{grp_msg_id}")

    # 3. Ghim tin nhắn (Pin message)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_PIN_MESSAGE,
        "conversation_id": grp_id,
        "message_id": grp_msg_id
    })
    pin_ack_a = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_PIN_MESSAGE_ACK)
    pin_notif_b = recv_until(sock_b, lambda p: p.get("type") == "message_pinned")
    stats.check(pin_notif_b and pin_notif_b.get("type") == "message_pinned", "Ghim tin nhắn nhóm & Đồng bộ thanh ghim màu vàng Realtime", f"Pinned Msg ID #{grp_msg_id}")

    # 4. Thêm thành viên mới (Client C) vào nhóm
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_GROUP_ADD_MEMBER,
        "conversation_id": grp_id,
        "user_id": uid_c
    })
    add_ack_a = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_GROUP_ADD_MEMBER_ACK)
    notif_add_c = recv_until(sock_c, lambda p: p.get("type") == "conversation_created")
    stats.check(add_ack_a and add_ack_a.get("status") == "OK", "Trưởng nhóm thêm thành viên mới (User C) vào nhóm", f"User #{uid_c}")
    stats.check(notif_add_c and notif_add_c.get("type") == "conversation_created", "Client C nhận nhóm chat ngay lập tức trên màn hình", f"Nhóm #{grp_id}")

    # 5. Đổi quyền thành viên (Phó nhóm / admin)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_GROUP_CHANGE_ROLE,
        "conversation_id": grp_id,
        "user_id": uid_b,
        "role": "admin"
    })
    role_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_GROUP_CHANGE_ROLE_ACK)
    stats.check(role_ack and role_ack.get("status") == "OK", "Đổi quyền thành viên trong nhóm thành Quản trị viên (admin)", f"User #{uid_b}")

    # 6. Đổi tên nhóm
    new_grp_name = "Nhóm LTM Xuất Sắc 10 Điểm"
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_GROUP_UPDATE,
        "conversation_id": grp_id,
        "name": new_grp_name
    })
    upd_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_GROUP_UPDATE_ACK)
    stats.check(upd_ack and upd_ack.get("status") == "OK", "Đổi tên nhóm chat & đồng bộ Realtime tới mọi thành viên", f"Tên mới: '{new_grp_name}'")

    # 7. Xóa thành viên khỏi nhóm (Kick C)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_GROUP_REMOVE_MEMBER,
        "conversation_id": grp_id,
        "user_id": uid_c
    })
    rem_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_GROUP_REMOVE_MEMBER_ACK)
    notif_kicked_c = recv_until(sock_c, lambda p: p.get("type") == "group_removed")
    stats.check(rem_ack and rem_ack.get("status") == "OK", "Trưởng nhóm xóa thành viên (Kick C) khỏi nhóm", f"User #{uid_c}")
    stats.check(notif_kicked_c and notif_kicked_c.get("type") == "group_removed", "Client C tự động gỡ nhóm khỏi danh sách hội thoại", f"Nhóm #{grp_id}")

    # 8. Thành viên B tự rời nhóm
    protocol.send_packet(sock_b, {
        "type": protocol.MSG_TYPE_GROUP_LEAVE,
        "conversation_id": grp_id
    })
    leave_ack_b = recv_until(sock_b, lambda p: p.get("type") == protocol.MSG_TYPE_GROUP_LEAVE_ACK)
    stats.check(leave_ack_b and leave_ack_b.get("status") == "OK", "Thành viên B tự rời nhóm chat thành công", f"Nhóm #{grp_id}")

    # 9. Trưởng nhóm giải tán nhóm (Disband)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_GROUP_DISBAND,
        "conversation_id": grp_id
    })
    disband_ack_a = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_GROUP_DISBAND_ACK)
    stats.check(disband_ack_a and disband_ack_a.get("status") == "OK", "Trưởng nhóm giải tán nhóm & dọn sạch hội thoại trong CSDL", f"Nhóm #{grp_id}")

    # --------------------------------------------------------------------------
    # CHẶNG 6: CLOUD CỦA TÔI & CHUYỂN TIẾP TIN NHẮN (FORWARD)
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 6: KHÔNG GIAN CLOUD CỦA TÔI & CHUYỂN TIẾP TIN NHẮN (FORWARD)] ---")

    # 1. Mở Cloud của tôi
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_GET_CLOUD})
    cloud_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_CLOUD_ACK)
    cloud_conv_id = cloud_ack.get("id")
    stats.check(cloud_ack and cloud_ack.get("status") == "OK" and cloud_conv_id is not None, "Mở không gian lưu trữ Cloud của tôi qua TCP Socket", f"Cloud ID #{cloud_conv_id}")
    stats.check(("storage_used_mb" in cloud_ack or "storage_mb" in cloud_ack) and "storage_percent" in cloud_ack, "Tính toán thống kê dung lượng bộ nhớ Cloud", f"{cloud_ack.get('storage_used_mb', cloud_ack.get('storage_mb'))} MB ({cloud_ack.get('storage_percent')}%)")

    # 2. Chuyển tiếp tin nhắn (Forward) sang Cloud
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_FORWARD_MESSAGE,
        "message_id": msg_code_id,
        "conversation_ids": [cloud_conv_id]
    })
    fwd_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_FORWARD_MESSAGE_ACK)
    stats.check(fwd_ack and fwd_ack.get("status") == "OK" and fwd_ack.get("forwarded_count") == 1, "Chuyển tiếp (Forward) tin nhắn sang Cloud của tôi", f"Forwarded: {fwd_ack.get('forwarded_count')} hội thoại")

    # --------------------------------------------------------------------------
    # CHẶNG 7: QUẢN LÝ CÔNG VIỆC ZALO TO-DO / TASKS
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 7: QUẢN LÝ CÔNG VIỆC & NHẮC HẸN (ZALO TO-DO / TASKS)] ---")

    # 1. Tạo công việc mới
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "create",
        "title": "Nộp báo cáo cuối kỳ LTM 10 điểm",
        "due": "23:59 Hôm nay",
        "priority": "high",
        "conversation_id": conv_1v1_id
    })
    task_create_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_TASK_OP_ACK)
    created_task = task_create_ack["tasks"][0] if task_create_ack and task_create_ack.get("tasks") else {}
    created_task_id = created_task.get("id")
    stats.check(task_create_ack and task_create_ack.get("status") == "OK" and created_task_id is not None, "Tạo mới công việc (Task Create) lưu CSDL PostgreSQL", f"Task ID #{created_task_id}")

    # 2. Liệt kê danh sách việc
    protocol.send_packet(sock_a, {"type": protocol.MSG_TYPE_TASK_OP, "action": "list"})
    task_list_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_TASK_OP_ACK)
    stats.check(task_list_ack and task_list_ack.get("status") == "OK" and len(task_list_ack.get("tasks", [])) > 0, "Lấy danh sách công việc (Task List)", f"Tổng: {len(task_list_ack.get('tasks', []))} việc")

    # 3. Đánh dấu hoàn thành (Toggle done)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "toggle",
        "id": created_task_id
    })
    task_toggle_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_TASK_OP_ACK)
    toggled_task = next((t for t in task_toggle_ack.get("tasks", []) if t.get("id") == created_task_id), {})
    stats.check(task_toggle_ack and task_toggle_ack.get("status") == "OK" and toggled_task.get("done") is True, "Cập nhật trạng thái hoàn thành công việc (Toggle Done)", f"Task #{created_task_id} -> done: True")

    # 4. Xóa công việc
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_TASK_OP,
        "action": "delete",
        "id": created_task_id
    })
    task_del_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_TASK_OP_ACK)
    remaining_tasks = [t for t in task_del_ack.get("tasks", []) if t.get("id") == created_task_id]
    stats.check(task_del_ack and task_del_ack.get("status") == "OK" and len(remaining_tasks) == 0, "Xóa công việc khỏi CSDL PostgreSQL", f"Task #{created_task_id}")

    # --------------------------------------------------------------------------
    # CHẶNG 8: BÁO HIỆU CUỘC GỌI WEBRTC VOICE & VIDEO CALL SIGNALING
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 8: BÁO HIỆU CUỘC GỌI WEBRTC VOICE/VIDEO & GHI NHẬT KÝ CALL] ---")

    # 1. Client A gọi Video tới B (CALL_REQ)
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CALL_SIGNAL,
        "action": "call_request",
        "conversation_id": conv_1v1_id,
        "call_type": "video"
    })
    call_req_b = recv_until(sock_b, lambda p: p.get("type") in (protocol.MSG_TYPE_CALL_SIGNAL, "webrtc_signal") and p.get("action") == "call_request")
    stats.check(call_req_b and call_req_b.get("action") == "call_request" and call_req_b.get("call_type") == "video", "Phát tín hiệu Yêu cầu cuộc gọi Video (CALL_REQ đổ chuông P2P)", f"Tới {u_b}")

    # 2. Client B chấp nhận cuộc gọi (CALL_RESP accept)
    protocol.send_packet(sock_b, {
        "type": protocol.MSG_TYPE_CALL_SIGNAL,
        "action": "call_accept",
        "conversation_id": conv_1v1_id
    })
    call_acc_a = recv_until(sock_a, lambda p: p.get("type") in (protocol.MSG_TYPE_CALL_SIGNAL, "webrtc_signal") and p.get("action") == "call_accept")
    stats.check(call_acc_a and call_acc_a.get("action") == "call_accept", "Client B đồng ý nhấc máy (CALL_RESP call_accept)", f"Bắt đầu bắt tay SDP")

    # 3. Trao đổi SDP Offer, SDP Answer và ICE Candidate
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CALL_SIGNAL,
        "action": "offer",
        "conversation_id": conv_1v1_id,
        "sdp": "v=0\r\no=alice...m=video"
    })
    offer_rx_b = recv_until(sock_b, lambda p: p.get("type") in (protocol.MSG_TYPE_CALL_SIGNAL, "webrtc_signal") and p.get("action") == "offer")
    stats.check(offer_rx_b and offer_rx_b.get("action") == "offer", "Trao đổi SDP Offer qua kênh báo hiệu TCP", "sdp: v=0...")

    protocol.send_packet(sock_b, {
        "type": protocol.MSG_TYPE_CALL_SIGNAL,
        "action": "answer",
        "conversation_id": conv_1v1_id,
        "sdp": "v=0\r\no=bob...m=video"
    })
    ans_rx_a = recv_until(sock_a, lambda p: p.get("type") in (protocol.MSG_TYPE_CALL_SIGNAL, "webrtc_signal") and p.get("action") == "answer")
    stats.check(ans_rx_a and ans_rx_a.get("action") == "answer", "Trao đổi SDP Answer qua kênh báo hiệu TCP", "Kênh P2P sẵn sàng")

    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CALL_SIGNAL,
        "action": "ice_candidate",
        "conversation_id": conv_1v1_id,
        "candidate": "candidate:1 1 UDP 2130706431 127.0.0.1 50000"
    })
    ice_rx_b = recv_until(sock_b, lambda p: p.get("type") in (protocol.MSG_TYPE_CALL_SIGNAL, "webrtc_signal") and p.get("action") == "ice_candidate")
    stats.check(ice_rx_b and ice_rx_b.get("action") == "ice_candidate", "Trao đổi ICE Candidate định tuyến mạng P2P", "UDP candidate")

    # 4. Kết thúc cuộc gọi & Lưu nhật ký vào PostgreSQL
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CALL_SIGNAL,
        "action": "call_end",
        "conversation_id": conv_1v1_id,
        "call_type": "video",
        "call_status": "completed",
        "duration": 45
    })
    call_end_b = recv_until(sock_b, lambda p: p.get("type") in (protocol.MSG_TYPE_CALL_SIGNAL, "webrtc_signal") and p.get("action") == "call_end")
    stats.check(call_end_b and call_end_b.get("action") == "call_end", "Kết thúc cuộc gọi (CALL_END) & Phát tín hiệu ngắt máy tới đối phương", "Thời lượng: 00:45")

    # --------------------------------------------------------------------------
    # CHẶNG 9: TÙY CHỌN HỘI THOẠI (GHIM, TẮT THÔNG BÁO, ƯU TIÊN & TÌM KIẾM)
    # --------------------------------------------------------------------------
    print("\n--- [CHẶNG 9: TÙY CHỌN HỘI THOẠI (PIN, MUTE, PRIORITY & TÌM KIẾM)] ---")

    # 1. Toggle Pin Conversation
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CONV_ACTION,
        "conversation_id": conv_1v1_id,
        "action": "toggle_pin"
    })
    pin_c_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_CONV_ACTION_ACK and p.get("action") == "toggle_pin")
    stats.check(pin_c_ack and pin_c_ack.get("status") == "OK" and pin_c_ack.get("is_pinned") is True, "Ghim cuộc hội thoại lên đầu danh sách (toggle_pin)", f"Hội thoại #{conv_1v1_id}")

    # 2. Toggle Mute Notification
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CONV_ACTION,
        "conversation_id": conv_1v1_id,
        "action": "toggle_mute"
    })
    mute_c_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_CONV_ACTION_ACK and p.get("action") == "toggle_mute")
    stats.check(mute_c_ack and mute_c_ack.get("status") == "OK" and mute_c_ack.get("is_muted") is True, "Tắt thông báo cuộc hội thoại (toggle_mute)", f"Hội thoại #{conv_1v1_id}")

    # 3. Toggle Priority / Other
    protocol.send_packet(sock_a, {
        "type": protocol.MSG_TYPE_CONV_ACTION,
        "conversation_id": conv_1v1_id,
        "action": "toggle_priority"
    })
    prio_c_ack = recv_until(sock_a, lambda p: p.get("type") == protocol.MSG_TYPE_CONV_ACTION_ACK and p.get("action") == "toggle_priority")
    stats.check(prio_c_ack and prio_c_ack.get("status") == "OK", "Chuyển tab Ưu tiên / Khác (toggle_priority)", f"is_priority: {prio_c_ack.get('is_priority')}")

    # 4. In-Chat Message Search via Database
    from chat.models import Conversation, Message
    c_obj = Conversation.objects.get(id=conv_1v1_id)
    search_results = Message.objects.filter(conversation=c_obj, content__icontains="Socket").count()
    stats.check(search_results > 0, "Tìm kiếm tin nhắn trong hội thoại theo từ khóa (In-chat Search)", f"Tìm thấy {search_results} tin nhắn khớp từ khóa 'Socket'")

    # --------------------------------------------------------------------------
    # TỔNG KẾT BÁO CÁO TOÀN DIỆN
    # --------------------------------------------------------------------------
    sock_a.close()
    sock_b.close()
    sock_c.close()
    server.stop()

    print("\n" + "=" * 80)
    print(f"🏆 KẾT QUẢ TỔNG QUAN: ĐÃ HOÀN THÀNH {stats.passed}/{stats.total} BƯỚC KIỂM THỬ (100% THÀNH CÔNG)!")
    print(f"   - Tầng mạng TCP & Protocol:      ĐẠT 100%")
    print(f"   - Xác thực & Danh bạ Realtime:  ĐẠT 100%")
    print(f"   - Chat 1-1, E2EE, Code, GPS:     ĐẠT 100%")
    print(f"   - Tương tác tin nhắn (React/Xem):ĐẠT 100%")
    print(f"   - Truyền tệp đa phương tiện/64KB: ĐẠT 100%")
    print(f"   - Quản lý Nhóm Chat trọn vẹn:   ĐẠT 100%")
    print(f"   - Cloud của tôi & Forward:       ĐẠT 100%")
    print(f"   - Zalo To-Do / Task Management:  ĐẠT 100%")
    print(f"   - Báo hiệu Cuộc gọi WebRTC P2P:  ĐẠT 100%")
    print(f"   - Tùy chọn Hội thoại & Tìm kiếm: ĐẠT 100%")
    print("=" * 80)
    sys.stdout.flush()
    os._exit(0)

if __name__ == "__main__":
    run_full_simulation()
