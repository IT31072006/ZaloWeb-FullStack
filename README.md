# HỆ THỐNG ZALO WEB FULL-STACK (DJANGO + POSTGRESQL / SQLITE)

Dự án bài tập lớn môn **Lập trình Mạng (LTM)**: Xây dựng hệ thống chat trực tuyến thời gian thực (Real-time Web Chat & Socket Room) theo kiến trúc **Client - Server**, nền tảng **Django Backend (Channels + Daphne ASGI)**, kết nối **WebSocket 0ms**, cuộc gọi **WebRTC P2P Voice & Video**, cùng giao diện web SPA chuẩn phong cách **Zalo Web**.

---

## 1. Cấu Trúc Dự Án

```
BaiTapGK/
├── run_web.py          # 🚀 Khởi chạy nhanh Zalo Web (Auto-migration & Daphne ASGI Server)
├── run_desktop.py      # 💬 Khởi chạy trọn bộ Zalo Desktop (TCP Socket + WebRTC + Desktop Window)
├── client_desktop.py   # 💻 Zalo Desktop Native App Window (Giao diện Zalo PC độc lập)
├── client_gui.py       # 🖥️ Giao diện Desktop Client PyQt6 kết nối Socket TCP thuần
├── manage.py           # ⚙️ Django CLI Management
├── zalo_project/       # 🛠️ Cấu hình Django Backend
│   ├── settings.py     # Cấu hình PostgreSQL / SQLite Fallback, Channels, CORS, REST Framework
│   ├── asgi.py         # Cấu hình ASGI ProtocolTypeRouter (HTTP & WebSocket Channels)
│   ├── wsgi.py         # Cấu hình WSGI tiêu chuẩn
│   └── urls.py         # Routing URL cấp cao nhất của hệ thống
├── chat/               # 💬 Ứng dụng Chat Core
│   ├── models.py       # CSDL: UserProfile, Conversation, ConversationMember, Message, Task, Friendship, FriendRequest
│   ├── views.py        # Logic API REST & View giao diện chính, Bạn bè, Cuộc gọi WebRTC
│   ├── consumers.py    # WebSocket Consumer: Realtime Chat, Presence, Typing, WebRTC Signaling
│   ├── routing.py      # Định tuyến WebSocket (/ws/chat/<conv_id>/)
│   ├── serializers.py  # Chuyển đổi dữ liệu JSON REST API
│   ├── authentication.py # CsrfExemptSessionAuthentication
│   └── urls.py         # Định tuyến API chi tiết
├── templates/          # 🎨 Giao diện HTML5 chuẩn Zalo Web
│   ├── index.html      # Giao diện chính Zalo Web (Rail, Sidebar, Chat, Info Drawer, WebRTC Call Modal)
│   ├── auth.html       # Giao diện Đăng nhập / Đăng ký chuyên biệt (hỗ trợ nhập IP/Port Server)
│   └── call_window.html # Cửa sổ Video Call WebRTC độc lập cho Desktop
├── static/             # 💅 CSS Zalo pixel-perfect & JS điều khiển
│   ├── css/zalo.css    # Hệ thống CSS Zalo chuẩn xác & Dark Theme hiện đại
│   └── js/zalo.js      # Client logic: WebSocket, WebRTC P2P, Web Audio, Uploads, Emojis, To-do
├── database/           # 🗄️ Cơ sở dữ liệu & Schema DDL
│   ├── schema.sql      # Định nghĩa cấu trúc DDL 9 bảng CSDL chuẩn SQL/PostgreSQL
│   ├── zalo_chat.sql   # File SQL dump sạch sẽ (DDL + dữ liệu tài khoản và Cloud mẫu)
│   └── README.md       # Tài liệu kiến trúc lưu trữ dữ liệu bền vững
├── seed_data.py        # 🌱 Khởi tạo dữ liệu mẫu 100% giống ảnh chụp Zalo Web
├── test_zalo_api.py    # 🧪 Bộ kiểm thử tự động 23/23 tính năng Web API
├── test_websocket_webrtc.py # 🚀 Bộ kiểm thử tự động WebSocket Channels & WebRTC Signaling
├── test_desktop_flow.py # 🧪 Kiểm thử tự động Desktop Client Socket TCP + PostgreSQL
├── protocol.py         # 📦 Định nghĩa giao thức truyền tin TCP Socket (Length-Prefixed Framing)
├── server.py           # ⚙️ TCP Multi-threaded Chat Room Server lõi kết nối PostgreSQL
├── client_cli.py       # 💻 TCP Chat Client Giao diện Dòng lệnh (CLI)
└── test_chat.py        # 🧪 Bộ kiểm thử tự động Socket TCP Client - Server
```

---

## 2. Các Tính Năng Đã Hoàn Thiện Trong Hệ Thống

### 💬 1. Trò Chuyện & Nhắn Tin Đa Phương Tiện
- **Tin nhắn văn bản**: Bong bóng chat chuẩn Zalo (Phải: Xanh của bạn, Trái: Trắng của đối phương kèm avatar và tên người gửi).
- **Gửi hình ảnh**: Tải ảnh trực tiếp từ máy tính hoặc dán clipboard, hiển thị thumbnail, bấm xem **Lightbox phóng to** và tải về.
- **Tin nhắn thoại ghi âm (Voice Note)**: Thu âm giọng nói trực tiếp với **Web Audio / MediaRecorder API**, hiển thị thanh đếm thời gian thực (`00:05`), hiệu ứng sóng âm dynamic và trình phát tùy biến.
- **Gửi đoạn mã lập trình (Code Snippet)**: Hỗ trợ gửi mã nguồn có phân loại ngôn ngữ (Java, Python, C++, SQL...), nút **"Sao chép mã"** một chạm.
- **Truyền tệp tin tài liệu**: Gửi tệp đính kèm với thẻ icon 📄, tên tệp, dung lượng và nút tải về trực tiếp.

### ⚡ 2. WebSocket Real-time & WebRTC P2P Video/Voice Call
- **WebSocket 0ms (Django Channels & Daphne)**: Nhận tin nhắn mới tức thì không cần tải lại trang hay chờ polling.
- **Presence Status**: Nhận biết trạng thái trực tuyến (Online dot xanh lá) thời gian thực.
- **Typing Indicator**: Hiển thị trạng thái *"Đang soạn tin nhắn..."* ngay khi đối phương gõ phím.
- **Cuộc gọi WebRTC P2P Voice & Video Call**:
  - Trao đổi tín hiệu báo hiệu (Signaling: Call Request, Accept, Decline, SDP Offer/Answer, ICE Candidates) qua WebSocket.
  - Hỗ trợ gọi 1-1 trực tiếp giữa 2 trình duyệt với luồng Video và Audio thực tế qua Camera/Mic.
  - Giao diện Call Modal chuyên nghiệp: Radar sóng âm lan tỏa, hiển thị Avatar người nhận, đồng hồ đếm giờ cuộc gọi `00:00`.
  - Các nút điều khiển: Bật/Tắt Mic 🎙️, Bật/Tắt Camera 📷, Toàn màn hình ⛶, Kết thúc cuộc gọi ❌.
  - Tự động ghi lại **Lịch sử cuộc gọi (Call Log)** vào hội thoại (Thời lượng, Trạng thái: Thành công / Cuộc gọi nhỡ / Bị từ chối).

### ❤️ 3. Tương Tác Tin Nhắn Chuyên Sâu
- **Thả cảm xúc Emoji**: Thả biểu cảm cảm xúc (❤️, 👍, 😂, 😮, 😢, 😡) vào bất kỳ tin nhắn nào, đồng bộ real-time cho các thành viên.
- **Ghim tin nhắn (Pin Message)**: Ghim tin nhắn quan trọng lên thanh tiêu đề hội thoại để xem nhanh; bấm bỏ ghim dễ dàng.
- **Thu hồi tin nhắn (Recall)**: Thu hồi tin nhắn ở cả 2 phía; tin nhắn đổi thành *"Tin nhắn đã được thu hồi"*.
- **Xóa tin nhắn phía tôi (Delete for me)**: Ẩn tin nhắn chỉ ở phía người dùng thực hiện mà không ảnh hưởng tới đối phương.
- **Trả lời tin nhắn (Reply / Quote)**: Trích dẫn nội dung tin nhắn gốc kèm tên người gửi khi phản hồi.

### 👥 4. Danh Bạ & Quản Lý Kết Bạn (Contacts & Friend Requests)
- **Quản lý bạn bè thực sự**: Chỉ người dùng đã kết bạn mới hiển thị trong danh bạ bạn bè.
- **Tìm bạn mới**: Tìm kiếm qua Số điện thoại hoặc Tên tài khoản (Username).
- **Gửi & Phản hồi lời mời kết bạn**:
  - Gửi lời mời kết bạn với thông báo đẩy thời gian thực qua WebSocket cá nhân (`user_<id>`).
  - Hộp thông báo "Lời mời kết bạn" với 2 nút: **Đồng ý** hoặc **Từ chối**.
  - Khi đồng ý, tự động thiết lập quan hệ bạn bè 2 chiều và mở ngay cuộc trò chuyện 1-1.
- **Tạo nhóm chat mới**: Đặt tên nhóm, tích chọn nhiều thành viên từ danh sách bạn bè.
- **Bộ lọc & Phân loại**:
  - Tab "Ưu tiên" / "Khác"
  - Bộ lọc: *Tất cả*, *Chỉ nhóm chat*, *Tin nhắn 1-1*, *Chưa đọc*
  - Ghim hội thoại (Pin conversation) lên đầu danh sách và Tắt/Bật thông báo (Mute).

### ☁️ 5. Cloud Của Tôi (My Cloud)
- Không gian lưu trữ dữ liệu cá nhân riêng tư cho từng tài khoản.
- Lưu lại văn bản, ghi chú, mã code, hình ảnh và tài liệu quan trọng của riêng mình.

### 📋 6. Giao Việc & Nhắc Hẹn (To-do Tasks)
- Bảng theo dõi tiến độ công việc tích hợp trong thanh điều hướng bên trái:
  - Thống kê: *Tổng việc*, *Đang thực hiện*, *Đã hoàn thành*.
  - Thẻ công việc kèm mức độ ưu tiên (*Cao 🔴*, *Trung bình 🟡*, *Bình thường 🟢*) và hạn chót.
  - Tích chọn checkbox để chuyển trạng thái hoàn thành hoặc nhấn nút xóa.
  - Tạo công việc mới liên kết với cuộc trò chuyện tương ứng.

### 🔍 7. Tìm Kiếm Nội Bộ & Ngăn Thông Tin (Info Drawer)
- **Tìm kiếm nội bộ**: Lọc và làm nổi bật tin nhắn khớp từ khóa, đếm số lượng kết quả.
- **Ngăn thông tin bên phải (ℹ️)**:
  - Xem danh sách thành viên, vai trò (Trưởng nhóm / Thành viên).
  - Bộ sưu tập **Ảnh / Video đã chia sẻ** trong hội thoại (xem phóng to).
  - Danh sách **Tệp tin tài liệu đã gửi** kèm dung lượng và link tải về.

### ⚙️ 8. Chế Độ Tối (Dark Mode) & Cài Đặt Hệ Thống
- Bật/tắt **Chế độ tối (Dark Mode)** lưu tự động vào `localStorage`.
- Bật/tắt âm thanh chuông thông báo Web Audio.
- Xem thông tin cấu hình máy chủ, database và uptime.

### 🖥️ 9. Ứng Dụng Zalo Desktop (Desktop Client)
- **Zalo Desktop Launcher (`run_desktop.py`)**: Tự động bật máy chủ Socket TCP (:5555), máy chủ Daphne ASGI (:8000) và mở giao diện Desktop.
- **Cửa sổ ứng dụng độc lập (`client_desktop.py`)**: Chạy cửa sổ Native Desktop Zalo PC không thanh URL, không tab trình duyệt, hỗ trợ đa Profile cho nhiều tài khoản test song song.
- **Client GUI Socket TCP (`client_gui.py`)**: Giao diện Desktop thuần viết bằng **PyQt6**, giao tiếp 100% qua Socket TCP (`protocol.py`) kết nối trực tiếp `server.py`, đồng bộ CSDL PostgreSQL.
- **Cửa sổ Cuộc gọi Video độc lập (`call_window.html`)**: Mở cửa sổ riêng biệt để truyền luồng Video/Audio Camera WebRTC P2P khi thực hiện gọi điện từ ứng dụng Desktop.
- **Cấu hình IP / Port linh hoạt**: Form đăng nhập cho phép cấu hình trực tiếp IP và Cổng của máy chủ trong mạng LAN.

---

## 3. Cấu Hình Cơ Sở Dữ Liệu (PostgreSQL & SQLite Fallback)

Hệ thống hỗ trợ kết nối trực tiếp tới cơ sở dữ liệu **PostgreSQL** qua `psycopg 3` hoặc tự động chuyển sang **SQLite** nếu PostgreSQL chưa khởi động:

```bash
# Tùy biến thông số PostgreSQL (Tùy chọn)
export DB_NAME="zalo_chat"
export DB_USER="postgres"
export DB_PASSWORD="postgres"
export DB_HOST="localhost"
export DB_PORT="5432"
```

---

## 4. Hướng Dẫn Khởi Chạy

### Cách 1: Chạy Zalo Desktop (Khuyên dùng cho báo cáo Đồ án LTM)
```bash
python3 run_desktop.py
```
> Tự động khởi chạy trọn gói hệ thống máy chủ và bật ngay Cửa sổ Ứng dụng Zalo Desktop.
> Để mở thêm Client thứ 2 trên cùng máy để test chat/gọi video: `python3 client_desktop.py 2`

### Cách 2: Chạy Client Desktop PyQt6 (Socket TCP Thuần)
```bash
# Bước 1: Khởi động TCP Server
python3 server.py

# Bước 2: Mở giao diện Desktop Client PyQt6
python3 client_gui.py
```

### Cách 3: Chạy Zalo Web Browser
```bash
python3 run_web.py
```
Script sẽ tự động kiểm tra migrations, kích hoạt Daphne ASGI Server hỗ trợ cả HTTP REST API và WebSocket Channels tại `http://127.0.0.1:8000/`.

### Cách 4: Khởi chạy chuẩn Django
```bash
python3 manage.py migrate
python3 seed_data.py          # Khởi tạo dữ liệu mẫu (nếu lần đầu chạy)
python3 manage.py runserver 0.0.0.0:8000
```

Mở trình duyệt và truy cập:
👉 **http://127.0.0.1:8000/**

### Tài khoản mẫu (Mật khẩu chung: `123456` hoặc `password123`)
- `quan`: Phạm Huỳnh Quân (Sinh viên VKU)
- `bao`: Lê Phú Bảo
- `camnt`: Cô Camnt (Giảng viên LTM)
- `phuc`: Nguyễn Hoàng Phúc
- `admin`: Quản trị viên (Mật khẩu: `admin123`)

---

## 5. Kiểm Thử Tự Động Toàn Diện (Automated Testing)

Hệ thống đi kèm 4 bộ kiểm thử tự động độc lập kiểm tra 100% các thành phần của đề tài:

### 1. Kiểm thử REST API Web (23/23 bài test)
```bash
python3 test_zalo_api.py
```
*Kiểm tra Đăng ký, Đăng nhập, Hồ sơ, Gửi tin nhắn đa phương tiện, Ghim/Bỏ ghim, Thả cảm xúc, Thu hồi, Xóa tin nhắn, Cloud, Danh bạ, Giao việc, Tìm kiếm.*

### 2. Kiểm thử WebSocket Channels & WebRTC P2P (8 bài test)
```bash
python3 test_websocket_webrtc.py
```
*Kiểm tra Kết nối WebSocket hai chiều, Presence Online, Gửi nhận tin nhắn 0ms, Typing Indicator, WebRTC Signaling (Call Request/Accept, SDP Offer/Answer, ICE Candidate), Thu hồi tin nhắn realtime, Đồng bộ Call Log.*

### 3. Kiểm thử Tích hợp Desktop Client Socket TCP + PostgreSQL
```bash
python3 test_desktop_flow.py
```
*Kiểm tra Xác thực đăng nhập qua Socket TCP với dữ liệu PostgreSQL, tải danh sách hội thoại và đồng bộ lịch sử tin nhắn.*

### 4. Kiểm thử TCP Socket Server & Protocol (Độc lập)
```bash
python3 test_chat.py
```
*Kiểm tra Giao thức TCP Socket tầng ứng dụng, Multi-threading, Broadcast, Private Message, Length-Prefixed Framing.*
