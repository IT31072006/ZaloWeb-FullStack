# 🗄️ TÀI LIỆU CƠ SỞ DỮ LIỆU ZALO WEB (POSTGRESQL & SQLITE)

Tài liệu thiết kế và hướng dẫn lưu trữ dữ liệu cho hệ thống **Zalo Web Clone** (Đồ án Lập trình Mạng - VKU).

---

## 1. Cấu Trúc Bảng Dữ Liệu (Database Schema)

Hệ thống sử dụng 7 bảng trong PostgreSQL / SQLite:

| Tên Bảng | Ý Nghĩa / Chức Năng |
| :--- | :--- |
| `auth_user` | Bảng tài khoản người dùng chuẩn Django: Username, Mật khẩu băm (PBKDF2/SHA256), Quyền hạn, Thời gian tạo. |
| `chat_userprofile` | Hồ sơ cá nhân mở rộng: Tên hiển thị (`display_name`), Ảnh đại diện (`avatar`), Ảnh bìa (`cover_image`), Số điện thoại (`phone`), Tiểu sử (`bio`), Giới tính (`gender`), Ngày sinh (`date_of_birth`), Trạng thái trực tuyến (`is_online`), Lần cuối hoạt động (`last_seen`). |
| `chat_conversation` | Quản lý cuộc trò chuyện: Tên hội thoại (`name`), Phân loại nhóm/1-1 (`is_group`), Ảnh nhóm (`avatar`), Người khởi tạo (`created_by_id`), Tin nhắn đã ghim (`pinned_message_id`), Thời gian cập nhật (`updated_at`). |
| `chat_conversationmember` | Thành viên tham gia cuộc hội thoại: Vai trò (`role`: admin / member), Thời điểm tham gia (`joined_at`), ID tin nhắn đã đọc gần nhất (`last_read_message_id`), Đã ghim (`is_pinned`), Tắt thông báo (`is_muted`), Phân loại ưu tiên (`is_priority`). |
| `chat_message` | **Lịch sử tin nhắn vĩnh viễn**: Loại tin nhắn (`message_type`: text, image, audio, file, code, call), Nội dung (`content`), File đính kèm (`attachment`), Tên file gốc (`attachment_name`), Kích thước (`attachment_size`), Ngôn ngữ code (`code_language`), Thời lượng cuộc gọi (`call_duration`), Trạng thái cuộc gọi (`call_status`), Đã thu hồi (`is_recalled`), Trả lời tin nhắn (`reply_to_id`), Thời gian gửi (`created_at`). |
| `chat_task` | Quản lý việc cần làm / To-do & Nhắc hẹn: Tiêu đề (`title`), Hạn chót (`due`), Độ ưu tiên (`priority`), Đã hoàn thành (`done`), Người thực hiện (`user_id`), Hội thoại liên kết (`conversation_id`). |
| `chat_messagereaction` | Biểu cảm cảm xúc tin nhắn: Mã tin nhắn (`message_id`), Người thả cảm xúc (`user_id`), Emoji cảm xúc (`emoji`: ❤️, 👍, 😂, 😮, 😢, 😡), Thời gian tạo. |
| `chat_message_deleted_by` | Bảng liên kết trung gian (M2M): Quản lý tính năng "Xóa tin nhắn ở phía tôi" cho từng người dùng mà không ảnh hưởng tới đối phương. |

---

## 2. Quy Tắc Hiển Thị Khung Danh Sách Chat

Theo thiết kế thực tế của Zalo:
1. **Khung danh sách chat bên trái** chỉ hiển thị:
   - Các cuộc hội thoại **đã có ít nhất 1 tin nhắn** được trao đổi giữa 2 người hoặc trong nhóm.
   - Hoặc mục **Cloud của tôi** (nơi lưu trữ tài liệu cá nhân của người dùng).
   - Hoặc nhóm chat do người dùng tạo.
2. Các tài khoản chưa nhắn tin sẽ nằm trong mục **Danh bạ** hoặc tìm kiếm được qua thanh tìm kiếm.
3. Khi người dùng bấm **Nhắn tin** với bất kỳ ai trong Danh bạ và gửi tin nhắn đầu tiên:
   - Tin nhắn lập tức được lưu vào bảng `chat_message`.
   - Hội thoại đó lập tức xuất hiện vĩnh viễn trên danh sách chat bên trái!

---

## 3. Cơ Chế Lưu Trữ Vĩnh Viễn (Persistence Guarantee)

Khi bạn **tắt máy chủ Web** (`Ctrl+C` trong terminal hoặc tắt máy tính) và **chạy lại máy chủ** (`python3 run_web.py`):
1. **Dữ liệu không bao giờ bị mất**: Vì toàn bộ tin nhắn được ghi thẳng vào bảng `chat_message` trong CSDL PostgreSQL (hoặc file SQLite `db.sqlite3`).
2. **Khôi phục lịch sử**: Khi bạn mở lại web và bấm vào bất kỳ cuộc trò chuyện nào:
   - Frontend gửi yêu cầu: `GET /api/conversations/<id>/messages/`
   - Backend truy vấn: `SELECT * FROM chat_message WHERE conversation_id = <id> ORDER BY created_at ASC`
   - Toàn bộ tin nhắn trước đây (văn bản, ảnh, audio, file, code) kèm mốc thời gian thực tế sẽ được hiển thị đầy đủ.

---

## 4. Các Tệp Tin Trong Thư Mục Này

- `schema.sql`: Mã nguồn SQL DDL chi tiết để tạo bảng, khóa chính, khóa ngoại, chỉ mục.
- `zalo_chat.sql`: File SQL dump đầy đủ (DDL + dữ liệu tài khoản và Cloud sạch).
- `README.md`: Hướng dẫn kiến trúc CSDL này.

---

## 5. Lệnh Quản Trị & Kiểm Tra CSDL

- Xem trực quan dữ liệu trong terminal:
  ```bash
  python3 view_db.py
  ```
- Mở trang quản trị Admin trực quan trên trình duyệt:
  👉 `http://127.0.0.1:8000/admin/` (Tài khoản: `admin` / Mật khẩu: `admin123`)
