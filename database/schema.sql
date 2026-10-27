-- ==============================================================================
-- 🗄️ CƠ SỞ DỮ LIỆU ZALO WEB CHAT SYSTEM (POSTGRESQL / SQL COMPLIANT)
-- Đồ án: Lập Trình Mạng (LTM) - VKU
-- Mô tả: Lưu trữ tài khoản, hồ sơ người dùng, cuộc hội thoại và lịch sử tin nhắn
-- Đảm bảo: Dữ liệu bền vững 100% khi tắt máy chủ (Server Restart Persistence)
-- ==============================================================================

-- 1. BẢNG TÀI KHOẢN NGƯỜI DÙNG (auth_user)
-- Lưu trữ thông tin đăng nhập chính: Username, Password Hash, Email, Quyền hạn
CREATE TABLE IF NOT EXISTS auth_user (
    id SERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE NULL,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL DEFAULT '',
    last_name VARCHAR(150) NOT NULL DEFAULT '',
    email VARCHAR(254) NOT NULL DEFAULT '',
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    date_joined TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_user_username ON auth_user(username);

-- 2. BẢNG HỒ SƠ NGƯỜI DÙNG MỞ RỘNG (chat_userprofile)
-- Mở rộng thông tin cá nhân: Họ tên hiển thị, Avatar, Cover, SĐT, Giới tính, Trạng thái online
CREATE TABLE IF NOT EXISTS chat_userprofile (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL DEFAULT '',
    avatar VARCHAR(100) NULL,
    cover_image VARCHAR(100) NULL,
    phone VARCHAR(20) NOT NULL DEFAULT '',
    bio VARCHAR(255) NOT NULL DEFAULT 'Xin chào, tôi đang sử dụng Zalo!',
    gender VARCHAR(10) NOT NULL DEFAULT 'nam',
    date_of_birth DATE NULL,
    is_online BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_profile_user FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_userprofile_phone ON chat_userprofile(phone);
CREATE INDEX IF NOT EXISTS idx_userprofile_display_name ON chat_userprofile(display_name);

-- 3. BẢNG CUỘC HỘI THOẠI (chat_conversation)
-- Quản lý phòng chat: Trò chuyện 1-1, Nhóm chat (is_group=TRUE), 'Cloud của tôi', và Tin nhắn ghim
CREATE TABLE IF NOT EXISTS chat_conversation (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL DEFAULT '',
    is_group BOOLEAN NOT NULL DEFAULT FALSE,
    avatar VARCHAR(100) NULL,
    created_by_id INTEGER NULL,
    pinned_message_id BIGINT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_conversation_creator FOREIGN KEY (created_by_id) REFERENCES auth_user(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_conversation_updated ON chat_conversation(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_creator ON chat_conversation(created_by_id);
CREATE INDEX IF NOT EXISTS idx_conversation_pinned_msg ON chat_conversation(pinned_message_id);

-- 4. BẢNG THÀNH VIÊN TRONG HỘI THOẠI (chat_conversationmember)
-- Quản lý ai tham gia hội thoại nào, vai trò (trưởng nhóm/thành viên), ID tin nhắn đọc gần nhất, ghim & tắt thông báo
CREATE TABLE IF NOT EXISTS chat_conversationmember (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    user_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_read_message_id INTEGER NOT NULL DEFAULT 0,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    pinned_at TIMESTAMP WITH TIME ZONE NULL,
    is_muted BOOLEAN NOT NULL DEFAULT FALSE,
    is_priority BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_conversation_member UNIQUE (conversation_id, user_id),
    CONSTRAINT fk_member_conversation FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE,
    CONSTRAINT fk_member_user FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_member_conv ON chat_conversationmember(conversation_id);
CREATE INDEX IF NOT EXISTS idx_member_user ON chat_conversationmember(user_id);
CREATE INDEX IF NOT EXISTS idx_member_pinned ON chat_conversationmember(is_pinned);

-- 4.1 BẢNG VIỆC CẦN LÀM & NHẮC HẸN (chat_task)
CREATE TABLE IF NOT EXISTS chat_task (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    conversation_id BIGINT NULL,
    title VARCHAR(255) NOT NULL,
    due VARCHAR(100) NOT NULL DEFAULT 'Sắp tới',
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_task_user FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE,
    CONSTRAINT fk_task_conversation FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_task_user ON chat_task(user_id);
CREATE INDEX IF NOT EXISTS idx_task_done ON chat_task(done);

-- 5. BẢNG LỊCH SỬ TIN NHẮN (chat_message)
-- Lưu trữ vĩnh viễn toàn bộ tin nhắn: Văn bản, Hình ảnh, Tin nhắn thoại (Voice note), File tài liệu, Đoạn mã code, Cuộc gọi thoại/video
CREATE TABLE IF NOT EXISTS chat_message (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    sender_id INTEGER NULL,
    message_type VARCHAR(20) NOT NULL DEFAULT 'text',
    content TEXT NOT NULL DEFAULT '',
    attachment VARCHAR(100) NULL,
    attachment_name VARCHAR(255) NOT NULL DEFAULT '',
    attachment_size VARCHAR(50) NOT NULL DEFAULT '',
    code_language VARCHAR(50) NOT NULL DEFAULT 'java',
    call_duration INTEGER NOT NULL DEFAULT 0,
    call_status VARCHAR(30) NOT NULL DEFAULT 'completed',
    is_recalled BOOLEAN NOT NULL DEFAULT FALSE,
    reply_to_id BIGINT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_message_conversation FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE,
    CONSTRAINT fk_message_sender FOREIGN KEY (sender_id) REFERENCES auth_user(id) ON DELETE SET NULL,
    CONSTRAINT fk_message_reply FOREIGN KEY (reply_to_id) REFERENCES chat_message(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_message_conversation ON chat_message(conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_message_sender ON chat_message(sender_id);
CREATE INDEX IF NOT EXISTS idx_message_created ON chat_message(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_reply ON chat_message(reply_to_id);

-- Thêm khóa ngoại pinned_message cho bảng chat_conversation
ALTER TABLE chat_conversation
    ADD CONSTRAINT fk_conversation_pinned_msg FOREIGN KEY (pinned_message_id) REFERENCES chat_message(id) ON DELETE SET NULL;

-- 6. BẢNG BIỂU CẢM CẢM XÚC TIN NHẮN (chat_messagereaction)
-- Lưu cảm xúc của từng thành viên với mỗi tin nhắn (❤️, 👍, 😂, 😮, 😢, 😡)
CREATE TABLE IF NOT EXISTS chat_messagereaction (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL,
    user_id INTEGER NOT NULL,
    emoji VARCHAR(10) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_message_reaction UNIQUE (message_id, user_id),
    CONSTRAINT fk_reaction_msg FOREIGN KEY (message_id) REFERENCES chat_message(id) ON DELETE CASCADE,
    CONSTRAINT fk_reaction_user FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reaction_msg ON chat_messagereaction(message_id);
CREATE INDEX IF NOT EXISTS idx_reaction_user ON chat_messagereaction(user_id);

-- 7. BẢNG XÓA TIN NHẮN PHÍA CÁ NHÂN (chat_message_deleted_by)
-- Lưu vết người dùng chọn 'Xóa ở phía tôi' mà không làm mất tin nhắn của người khác
CREATE TABLE IF NOT EXISTS chat_message_deleted_by (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL,
    user_id INTEGER NOT NULL,
    CONSTRAINT uq_message_deleted UNIQUE (message_id, user_id),
    CONSTRAINT fk_deleted_msg FOREIGN KEY (message_id) REFERENCES chat_message(id) ON DELETE CASCADE,
    CONSTRAINT fk_deleted_user FOREIGN KEY (user_id) REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_deleted_msg ON chat_message_deleted_by(message_id);
CREATE INDEX IF NOT EXISTS idx_deleted_user ON chat_message_deleted_by(user_id);

-- ==============================================================================
-- 📌 CƠ CHẾ BẢO ĐẢM TÍNH BỀN VỮNG (PERSISTENCE GUARANTEE):
-- 1. Khi người dùng gửi tin nhắn qua giao diện Web:
--    -> Django View gọi: Message.objects.create(...)
--    -> Database ghi dòng mới vào bảng `chat_message` và cập nhật `updated_at` trong `chat_conversation`.
-- 2. Khi máy chủ Web bị tắt (Ctrl+C hoặc tắt máy tính):
--    -> Toàn bộ dữ liệu nằm an toàn trong Database PostgreSQL (hoặc file SQLite db.sqlite3).
-- 3. Khi máy chủ Web khởi động lại (python3 run_web.py):
--    -> Khi bấm vào cuộc trò chuyện, API `/api/conversations/<id>/messages/` được gọi.
--    -> Hệ thống thực hiện: SELECT * FROM chat_message WHERE conversation_id = <id> ORDER BY created_at ASC;
--    -> Toàn bộ tin nhắn trước đây xuất hiện đầy đủ trên giao diện.
-- ==============================================================================
