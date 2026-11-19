"""
protocol.py - Định nghĩa giao thức truyền tin (Application Layer Protocol) qua TCP Socket.

Để tránh lỗi phân mảnh (fragmentation) và dính gói (packet coalescing) đặc trưng của TCP,
chúng ta sử dụng cơ chế Length-Prefixed Framing:
- Mỗi thông điệp gửi đi có tiền tố 4 byte (big-endian integer) biểu thị độ dài (bytes) của nội dung payload.
- Payload được mã hóa dưới dạng chuỗi JSON UTF-8.
- Hỗ trợ truyền tin nhắn văn bản, tin nhắn thoại (Voice Base64) và tệp tin tài liệu (File Base64).
"""

import json
import socket
import struct

HEADER_FORMAT = "!I"  # 4 bytes unsigned int (Big-endian / Network byte order)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Các loại thông điệp (Message Types)
MSG_TYPE_JOIN = "JOIN"                      # Client xin tham gia phòng chat kèm nickname (legacy)
MSG_TYPE_JOIN_ACK = "JOIN_ACK"              # Server xác nhận chấp nhận/từ chối nickname (legacy)
MSG_TYPE_LOGIN = "LOGIN"                    # Client đăng nhập với username và password từ PostgreSQL
MSG_TYPE_LOGIN_ACK = "LOGIN_ACK"            # Server trả về kết quả đăng nhập, user info và danh sách hội thoại
MSG_TYPE_REGISTER = "REGISTER"              # Client đăng ký tài khoản mới (username, password, display_name, phone)
MSG_TYPE_REGISTER_ACK = "REGISTER_ACK"      # Server trả về kết quả đăng ký tài khoản mới
MSG_TYPE_LOAD_HISTORY = "LOAD_HISTORY"      # Client yêu cầu tải lịch sử tin nhắn của một hội thoại từ DB
MSG_TYPE_HISTORY_ACK = "HISTORY_ACK"        # Server gửi về danh sách tin nhắn lịch sử từ CSDL
MSG_TYPE_CHAT = "CHAT"                      # Tin nhắn chat hội thoại / công khai
MSG_TYPE_PRIVATE = "PRIVATE"                # Tin nhắn chat riêng tư (1-1)
MSG_TYPE_VOICE = "VOICE"                    # Tin nhắn thoại ghi âm (Audio Voice Note Base64)
MSG_TYPE_FILE = "FILE"                      # Tệp tin / hình ảnh đính kèm (File Attachment Base64)
MSG_TYPE_USER_LIST = "USER_LIST"            # Server gửi danh sách các user đang online
MSG_TYPE_SYSTEM = "SYSTEM"                  # Thông báo hệ thống (vào/ra phòng, cảnh báo)
MSG_TYPE_QUIT = "QUIT"                      # Client thông báo rời phòng

# Tương tác thời gian thực (Real-time Interactions)
MSG_TYPE_TYPING = "TYPING"                  # Thông báo trạng thái đang soạn tin nhắn (typing indicator)
MSG_TYPE_REACTION = "REACTION"              # Thả biểu cảm cảm xúc (message_id, emoji)
MSG_TYPE_RECALL = "RECALL"                  # Thu hồi tin nhắn cho cả phòng
MSG_TYPE_PIN_MESSAGE = "PIN_MESSAGE"        # Ghim tin nhắn lên đầu hội thoại
MSG_TYPE_PIN_MESSAGE_ACK = "PIN_MESSAGE_ACK"# Xác nhận kết quả ghim tin nhắn

# Tìm kiếm người dùng, Khởi tạo hội thoại & Kết bạn (Friend System qua Socket TCP)
MSG_TYPE_SEARCH_USER = "SEARCH_USER"          # Tìm kiếm user theo SĐT hoặc username
MSG_TYPE_SEARCH_USER_ACK = "SEARCH_USER_ACK"  # Kết quả tìm kiếm người dùng
MSG_TYPE_CREATE_CONV = "CREATE_CONV"          # Tạo hoặc lấy hội thoại 1-1 giữa 2 người
MSG_TYPE_CREATE_CONV_ACK = "CREATE_CONV_ACK"  # Kết quả tạo hội thoại
MSG_TYPE_FRIEND_REQ = "FRIEND_REQ"            # Gửi lời mời kết bạn (target_user_id)
MSG_TYPE_FRIEND_REQ_ACK = "FRIEND_REQ_ACK"    # Kết quả gửi lời mời kết bạn
MSG_TYPE_FRIEND_RESP = "FRIEND_RESP"          # Đồng ý / từ chối lời mời kết bạn (request_id, action)
MSG_TYPE_FRIEND_RESP_ACK = "FRIEND_RESP_ACK"  # Kết quả phản hồi kết bạn
MSG_TYPE_LOAD_CONTACTS = "LOAD_CONTACTS"      # Tải danh bạ, bạn bè và danh sách lời mời kết bạn
MSG_TYPE_CONTACTS_ACK = "CONTACTS_ACK"        # Trả về danh bạ bạn bè và lời mời kết bạn
MSG_TYPE_UPDATE_PROFILE = "UPDATE_PROFILE"    # Cập nhật thông tin cá nhân và ảnh đại diện
MSG_TYPE_UPDATE_PROFILE_ACK = "UPDATE_PROFILE_ACK"  # Phản hồi cập nhật hồ sơ

# Quản lý Nhóm Chat (Group Management qua TCP Socket)
MSG_TYPE_GROUP_ADD_MEMBER = "GROUP_ADD_MEMBER"          # Thêm thành viên mới vào nhóm (conv_id, user_id)
MSG_TYPE_GROUP_ADD_MEMBER_ACK = "GROUP_ADD_MEMBER_ACK"  # Kết quả thêm thành viên
MSG_TYPE_GROUP_REMOVE_MEMBER = "GROUP_REMOVE_MEMBER"    # Xóa thành viên khỏi nhóm (conv_id, user_id)
MSG_TYPE_GROUP_REMOVE_MEMBER_ACK = "GROUP_REMOVE_MEMBER_ACK" # Kết quả xóa thành viên
MSG_TYPE_GROUP_LEAVE = "GROUP_LEAVE"                    # Rời nhóm chat (conv_id)
MSG_TYPE_GROUP_LEAVE_ACK = "GROUP_LEAVE_ACK"            # Kết quả rời nhóm
MSG_TYPE_GROUP_UPDATE = "GROUP_UPDATE"                  # Cập nhật tên/ảnh nhóm (conv_id, name, avatar_data)
MSG_TYPE_GROUP_UPDATE_ACK = "GROUP_UPDATE_ACK"          # Kết quả cập nhật nhóm
MSG_TYPE_GROUP_DISBAND = "GROUP_DISBAND"                # Giải tán nhóm (conv_id)
MSG_TYPE_GROUP_DISBAND_ACK = "GROUP_DISBAND_ACK"        # Kết quả giải tán nhóm
MSG_TYPE_GROUP_CHANGE_ROLE = "GROUP_CHANGE_ROLE"        # Phân quyền/Chuyển quyền trưởng nhóm
MSG_TYPE_GROUP_CHANGE_ROLE_ACK = "GROUP_CHANGE_ROLE_ACK"# Kết quả phân quyền nhóm

# Thao tác Tin nhắn & Cloud cá nhân (Message Ops & Cloud Storage qua TCP Socket)
MSG_TYPE_GET_CLOUD = "GET_CLOUD"                        # Yêu cầu mở hội thoại 'Cloud của tôi'
MSG_TYPE_CLOUD_ACK = "CLOUD_ACK"                        # Trả về thông tin hội thoại Cloud & dung lượng
MSG_TYPE_FORWARD_MESSAGE = "FORWARD_MESSAGE"            # Chuyển tiếp tin nhắn sang nhiều hội thoại
MSG_TYPE_FORWARD_MESSAGE_ACK = "FORWARD_MESSAGE_ACK"    # Kết quả chuyển tiếp tin nhắn
MSG_TYPE_DELETE_FOR_ME = "DELETE_FOR_ME"                # Xóa tin nhắn ở phía tôi (ẩn trong CSDL)
MSG_TYPE_DELETE_FOR_ME_ACK = "DELETE_FOR_ME_ACK"        # Xác nhận xóa tin nhắn ở phía tôi

# Nhịp tim & Đo độ trễ mạng (Heartbeat / Keep-Alive)
MSG_TYPE_PING = "PING"                      # Client định kỳ gửi kiểm tra độ trễ và giữ kết nối
MSG_TYPE_PONG = "PONG"                      # Server phản hồi nhịp tim kèm timestamp

# Phân mảnh & Truyền file lớn (Chunking & SHA-256 Checksum)
MSG_TYPE_FILE_START = "FILE_START"          # Khởi động truyền file lớn phân mảnh
MSG_TYPE_FILE_CHUNK = "FILE_CHUNK"          # Gói tin mảnh file (chunk)
MSG_TYPE_FILE_COMPLETE = "FILE_COMPLETE"    # Báo hoàn tất & đối soát mã băm SHA-256

# Kích thước phân mảnh chuẩn mạng: 64 KB
CHUNK_SIZE = 64 * 1024

# Thông điệp Báo hiệu Cuộc gọi WebRTC (WebRTC Call Signaling qua TCP Socket)
MSG_TYPE_CALL_REQ = "CALL_REQ"              # A yêu cầu gọi video tới B (caller -> server -> callee)
MSG_TYPE_CALL_RESP = "CALL_RESP"            # B trả lời chấp nhận hoặc từ chối cuộc gọi (callee -> server -> caller)
MSG_TYPE_CALL_SIGNAL = "CALL_SIGNAL"        # Truyền tín hiệu SDP Offer/Answer hoặc ICE Candidate giữa A và B
MSG_TYPE_CALL_END = "CALL_END"              # Kết thúc cuộc gọi và ghi lịch sử vào CSDL


# ==============================================================================
# BỘ MÃ HÓA ĐẦU CUỐI (END-TO-END ENCRYPTION - E2EE) BẰNG AES-256-GCM
# ==============================================================================
import base64
import hashlib
import os

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_AES = True
except ImportError:
    HAS_AES = False


def derive_key(secret_phrase: str) -> bytes:
    """Sinh khóa 256-bit (32 bytes) từ chuỗi mật khẩu/hội thoại dùng SHA-256."""
    return hashlib.sha256(secret_phrase.encode("utf-8")).digest()


def encrypt_payload(data_str: str, key_phrase: str = "zalo_e2ee_ltm_secret_key") -> str:
    """Mã hóa chuỗi văn bản bằng AES-256-GCM (Bảo mật & Toàn vẹn AEAD)."""
    if not HAS_AES:
        return data_str
    try:
        key = derive_key(key_phrase)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit nonce chuẩn cho GCM
        ciphertext = aesgcm.encrypt(nonce, data_str.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")
    except Exception:
        return data_str


def decrypt_payload(b64_cipher: str, key_phrase: str = "zalo_e2ee_ltm_secret_key") -> str:
    """Giải mã chuỗi Base64 ciphertext bằng AES-256-GCM."""
    if not HAS_AES:
        return b64_cipher
    try:
        key = derive_key(key_phrase)
        aesgcm = AESGCM(key)
        raw = base64.b64decode(b64_cipher.encode("utf-8"))
        if len(raw) < 12:
            return b64_cipher
        nonce = raw[:12]
        ciphertext = raw[12:]
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted_bytes.decode("utf-8")
    except Exception:
        return b64_cipher


def send_packet(sock: socket.socket, data: dict) -> bool:
    """Đóng gói dữ liệu dạng dictionary thành JSON và gửi qua socket kèm header độ dài."""
    try:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        header = struct.pack(HEADER_FORMAT, len(payload))
        sock.sendall(header + payload)
        return True
    except (socket.error, BrokenPipeError, ConnectionResetError):
        return False


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes | None:
    """Hàm bổ trợ đọc chính xác số byte yêu cầu từ socket."""
    buf = bytearray()
    while len(buf) < num_bytes:
        try:
            chunk = sock.recv(min(65536, num_bytes - len(buf)))
            if not chunk:
                return None  # Socket đã bị đóng
            buf.extend(chunk)
        except (socket.error, ConnectionResetError):
            return None
    return bytes(buf)


def recv_packet(sock: socket.socket) -> dict | None:
    """Đọc 1 gói tin hoàn chỉnh: đọc 4 byte header trước rồi đọc đúng số byte payload."""
    try:
        header_bytes = recv_exact(sock, HEADER_SIZE)
        if not header_bytes:
            return None

        (payload_length,) = struct.unpack(HEADER_FORMAT, header_bytes)
        payload_bytes = recv_exact(sock, payload_length)
        if not payload_bytes:
            return None

        data = json.loads(payload_bytes.decode("utf-8"))
        return data
    except (socket.error, json.JSONDecodeError, UnicodeDecodeError):
        return None
