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
MSG_TYPE_JOIN = "JOIN"                      # Client xin tham gia phòng chat kèm nickname
MSG_TYPE_JOIN_ACK = "JOIN_ACK"              # Server xác nhận chấp nhận/từ chối nickname
MSG_TYPE_CHAT = "CHAT"                      # Tin nhắn chat công khai (Broadcast)
MSG_TYPE_PRIVATE = "PRIVATE"                # Tin nhắn chat riêng tư (1-1)
MSG_TYPE_VOICE = "VOICE"                    # Tin nhắn thoại ghi âm (Audio Voice Note Base64)
MSG_TYPE_FILE = "FILE"                      # Tệp tin / tài liệu đính kèm (File Attachment Base64)
MSG_TYPE_USER_LIST = "USER_LIST"            # Server gửi danh sách các user đang online
MSG_TYPE_SYSTEM = "SYSTEM"                  # Thông báo hệ thống (vào/ra phòng, cảnh báo)
MSG_TYPE_QUIT = "QUIT"                      # Client thông báo rời phòng


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
