#!/usr/bin/env python3
"""
client_gui.py - Ứng dụng Desktop Zalo Chat Room (Mô hình Client - Server Socket TCP & WebRTC).
Đồ án Lập trình Mạng (LTM) - SV: Phạm Huỳnh Quân (24IT220) & Lê Phú Bảo (24IT018).

Kiến trúc:
1. Core Chat & Data: 100% truyền nhận qua Socket TCP thuần (protocol.py) kết nối server.py:5555.
2. Cơ sở dữ liệu: Đồng bộ và lưu trữ bền vững với PostgreSQL (bảng auth_user, chat_conversation, chat_message).
3. Cuộc gọi Video: Sử dụng WebRTC P2P để mở Camera và truyền luồng hình ảnh/âm thanh khi nhấn Gọi Video.
"""

import base64
import os
import subprocess
import sys
import webbrowser
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap, QPainter, QBrush, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QFileDialog, QMessageBox, QDialog,
    QSplitter, QTextEdit, QSizePolicy
)

import protocol

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5555
WEB_PORT = 8000


# ==============================================================================
# 1. NETWORK WORKER THREAD (SOCKET TCP)
# ==============================================================================
class SocketWorker(QThread):
    sig_connected = pyqtSignal()
    sig_disconnected = pyqtSignal(str)
    sig_login_ack = pyqtSignal(dict)
    sig_history_ack = pyqtSignal(dict)
    sig_chat = pyqtSignal(dict)
    sig_file = pyqtSignal(dict)
    sig_user_list = pyqtSignal(dict)
    sig_call_req = pyqtSignal(dict)
    sig_call_resp = pyqtSignal(dict)
    sig_call_end = pyqtSignal(dict)
    sig_system = pyqtSignal(dict)

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        super().__init__()
        self.host = host
        self.port = port
        self.sock = None
        self.is_running = False

    def connect_server(self) -> bool:
        try:
            import socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.is_running = True
            self.sig_connected.emit()
            return True
        except Exception as e:
            self.sig_disconnected.emit(f"Không thể kết nối Server TCP ({e})")
            return False

    def send_packet(self, data: dict) -> bool:
        if self.sock and self.is_running:
            return protocol.send_packet(self.sock, data)
        return False

    def run(self):
        while self.is_running and self.sock:
            packet = protocol.recv_packet(self.sock)
            if not packet:
                break

            p_type = packet.get("type")
            if p_type == protocol.MSG_TYPE_LOGIN_ACK:
                self.sig_login_ack.emit(packet)
            elif p_type == protocol.MSG_TYPE_HISTORY_ACK:
                self.sig_history_ack.emit(packet)
            elif p_type == protocol.MSG_TYPE_CHAT:
                self.sig_chat.emit(packet)
            elif p_type == protocol.MSG_TYPE_FILE:
                self.sig_file.emit(packet)
            elif p_type == protocol.MSG_TYPE_USER_LIST:
                self.sig_user_list.emit(packet)
            elif p_type == protocol.MSG_TYPE_CALL_REQ:
                self.sig_call_req.emit(packet)
            elif p_type == protocol.MSG_TYPE_CALL_RESP:
                self.sig_call_resp.emit(packet)
            elif p_type == protocol.MSG_TYPE_CALL_END:
                self.sig_call_end.emit(packet)
            elif p_type == protocol.MSG_TYPE_SYSTEM:
                self.sig_system.emit(packet)

        self.is_running = False
        self.sig_disconnected.emit("Đã ngắt kết nối với TCP Socket Server.")

    def stop(self):
        self.is_running = False
        if self.sock:
            try:
                protocol.send_packet(self.sock, {"type": protocol.MSG_TYPE_QUIT})
                self.sock.close()
            except Exception:
                pass
            self.sock = None


# ==============================================================================
# 2. DIALOG ĐĂNG NHẬP (LOGIN DIALOG)
# ==============================================================================
class LoginDialog(QDialog):
    def __init__(self, worker: SocketWorker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.user_data = None
        self.conversations = []
        self.contacts = []

        self.setWindowTitle("Đăng nhập Zalo Desktop - Socket TCP")
        self.setFixedSize(420, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f4f9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
            }
            QLabel {
                color: #1a202c;
            }
            QLineEdit {
                padding: 10px 14px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background: #ffffff;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #0068ff;
            }
            QPushButton#btnLogin {
                background-color: #0068ff;
                color: white;
                font-weight: bold;
                font-size: 15px;
                padding: 11px;
                border-radius: 8px;
                border: none;
            }
            QPushButton#btnLogin:hover {
                background-color: #005ae0;
            }
            QPushButton.quick-btn {
                background: #ffffff;
                color: #0068ff;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton.quick-btn:hover {
                background: #e0f2fe;
            }
        """)

        self.setup_ui()
        self.worker.sig_login_ack.connect(self.on_login_ack)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_logo = QLabel("💬")
        lbl_logo.setFont(QFont("Segoe UI Emoji", 36))
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(lbl_logo)

        lbl_app = QLabel("Zalo Desktop")
        lbl_app.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        lbl_app.setStyleSheet("color: #0068ff;")
        lbl_app.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(lbl_app)

        lbl_sub = QLabel("Môn Lập Trình Mạng (Socket TCP & WebRTC)")
        lbl_sub.setFont(QFont("Arial", 11))
        lbl_sub.setStyleSheet("color: #64748b;")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(lbl_sub)
        layout.addLayout(title_box)

        layout.addSpacing(6)

        # Host & Port row
        lbl_server = QLabel("Địa chỉ Máy chủ Socket TCP:")
        lbl_server.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(lbl_server)

        row_server = QHBoxLayout()
        self.txt_host = QLineEdit(DEFAULT_HOST)
        self.txt_host.setPlaceholderText("IP Server (127.0.0.1)")
        self.txt_port = QLineEdit(str(DEFAULT_PORT))
        self.txt_port.setFixedWidth(80)
        self.txt_port.setPlaceholderText("5555")
        row_server.addWidget(self.txt_host)
        row_server.addWidget(self.txt_port)
        layout.addLayout(row_server)

        # Username
        lbl_user = QLabel("Tài khoản (PostgreSQL):")
        lbl_user.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(lbl_user)
        self.txt_user = QLineEdit("quan")
        self.txt_user.setPlaceholderText("Tên đăng nhập (quan, bao, camnt...)")
        layout.addWidget(self.txt_user)

        # Password
        lbl_pass = QLabel("Mật khẩu:")
        lbl_pass.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(lbl_pass)
        self.txt_pass = QLineEdit("password123")
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setPlaceholderText("Mật khẩu")
        layout.addWidget(self.txt_pass)

        # Quick demo accounts
        lbl_quick = QLabel("Đăng nhập nhanh tài khoản mẫu:")
        lbl_quick.setFont(QFont("Arial", 10))
        lbl_quick.setStyleSheet("color: #64748b;")
        layout.addWidget(lbl_quick)

        quick_box = QHBoxLayout()
        btn_q1 = QPushButton("Quân Phạm (quan)")
        btn_q1.setProperty("class", "quick-btn")
        btn_q1.clicked.connect(lambda: self.fill_account("quan", "password123"))

        btn_q2 = QPushButton("Lê Phú Bảo (bao)")
        btn_q2.setProperty("class", "quick-btn")
        btn_q2.clicked.connect(lambda: self.fill_account("bao", "password123"))

        btn_q3 = QPushButton("Cô Camnt (camnt)")
        btn_q3.setProperty("class", "quick-btn")
        btn_q3.clicked.connect(lambda: self.fill_account("camnt", "password123"))

        quick_box.addWidget(btn_q1)
        quick_box.addWidget(btn_q2)
        quick_box.addWidget(btn_q3)
        layout.addLayout(quick_box)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #dc2626; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        # Button Login
        self.btn_login = QPushButton("Đăng nhập Socket TCP")
        self.btn_login.setObjectName("btnLogin")
        self.btn_login.clicked.connect(self.do_login)
        layout.addWidget(self.btn_login)

    def fill_account(self, u, p):
        self.txt_user.setText(u)
        self.txt_pass.setText(p)

    def do_login(self):
        host = self.txt_host.text().strip()
        port = int(self.txt_port.text().strip() or "5555")
        user = self.txt_user.text().strip()
        pwd = self.txt_pass.text().strip()

        if not user:
            self.lbl_status.setText("Vui lòng nhập tên tài khoản!")
            return

        self.lbl_status.setStyleSheet("color: #0068ff; font-size: 12px;")
        self.lbl_status.setText("Đang kết nối tới Socket Server...")
        self.btn_login.setEnabled(False)

        self.worker.host = host
        self.worker.port = port

        if not self.worker.is_running:
            if not self.worker.connect_server():
                self.lbl_status.setStyleSheet("color: #dc2626;")
                self.lbl_status.setText(f"❌ Không thể kết nối tới {host}:{port}")
                self.btn_login.setEnabled(True)
                return
            self.worker.start()

        # Gửi gói tin LOGIN
        packet = {
            "type": protocol.MSG_TYPE_LOGIN,
            "username": user,
            "password": pwd,
        }
        self.worker.send_packet(packet)

    def on_login_ack(self, data: dict):
        self.btn_login.setEnabled(True)
        if data.get("status") == "OK":
            self.user_data = data.get("user")
            self.conversations = data.get("conversations", [])
            self.contacts = data.get("contacts", [])
            self.accept()
        else:
            self.lbl_status.setStyleSheet("color: #dc2626;")
            self.lbl_status.setText(f"❌ {data.get('message', 'Đăng nhập thất bại!')}")


# ==============================================================================
# 3. CỬA SỔ CHÍNH (MAIN ZALO DESKTOP WINDOW)
# ==============================================================================
class ZaloDesktopWindow(QMainWindow):
    def __init__(self, worker: SocketWorker, user_data: dict, conversations: list, contacts: list):
        super().__init__()
        self.worker = worker
        self.user_data = user_data
        self.conversations = conversations
        self.contacts = contacts
        self.current_conv_id = None
        self.current_peer_user = ""
        self.current_peer_name = ""
        self.online_users = []

        self.setWindowTitle(f"Zalo Desktop - {self.user_data.get('display_name')} (@{self.user_data.get('username')})")
        self.resize(1020, 700)
        self.setMinimumSize(850, 580)

        self.apply_theme()
        self.setup_ui()
        self.bind_signals()

        # Chọn hội thoại đầu tiên nếu có
        if self.conversations:
            self.list_convs.setCurrentRow(0)
            self.on_conv_selected(0)

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
            }
            QFrame#navRail {
                background-color: #005ae0;
                min-width: 64px;
                max-width: 64px;
            }
            QFrame#sidebarArea {
                background-color: #f7f9fa;
                border-right: 1px solid #e2e8f0;
                min-width: 280px;
                max-width: 340px;
            }
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border-radius: 8px;
                padding: 6px;
                margin: 2px 8px;
            }
            QListWidget::item:selected {
                background-color: #e5efff;
            }
            QListWidget::item:hover {
                background-color: #edf2f7;
            }
            QFrame#chatHeader {
                background-color: #ffffff;
                border-bottom: 1px solid #e2e8f0;
                min-height: 58px;
                max-height: 58px;
                padding: 0 16px;
            }
            QPushButton#btnVideoCall {
                background-color: #0068ff;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 16px;
                border-radius: 18px;
                border: none;
            }
            QPushButton#btnVideoCall:hover {
                background-color: #0050cc;
            }
            QScrollArea#scrollChat {
                background-color: #f0f4f9;
                border: none;
            }
            QWidget#chatContent {
                background-color: #f0f4f9;
            }
            QFrame#inputToolbar {
                background-color: #ffffff;
                border-top: 1px solid #e2e8f0;
                min-height: 60px;
                max-height: 60px;
                padding: 8px 16px;
            }
            QLineEdit#txtMessage {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 20px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QLineEdit#txtMessage:focus {
                background-color: #ffffff;
                border: 2px solid #0068ff;
            }
            QPushButton#btnSend {
                background-color: #0068ff;
                color: white;
                font-size: 16px;
                border-radius: 20px;
                width: 40px;
                height: 40px;
                border: none;
            }
            QPushButton#btnSend:hover {
                background-color: #005ae0;
            }
            QPushButton.tool-btn {
                background: transparent;
                border: none;
                font-size: 18px;
                padding: 6px;
                border-radius: 8px;
            }
            QPushButton.tool-btn:hover {
                background: #e2e8f0;
            }
        """)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. LEFT NAVIGATION RAIL (64px) ---
        nav_rail = QFrame()
        nav_rail.setObjectName("navRail")
        nav_layout = QVBoxLayout(nav_rail)
        nav_layout.setContentsMargins(8, 16, 8, 16)
        nav_layout.setSpacing(14)
        nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_my_avatar = QLabel("👤")
        lbl_my_avatar.setFont(QFont("Segoe UI Emoji", 24))
        lbl_my_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(lbl_my_avatar)

        lbl_my_name = QLabel(self.user_data.get("username", ""))
        lbl_my_name.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        lbl_my_name.setStyleSheet("color: white;")
        lbl_my_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(lbl_my_name)

        nav_layout.addSpacing(16)

        btn_tab_chat = QPushButton("💬")
        btn_tab_chat.setToolTip("Hội thoại")
        btn_tab_chat.setStyleSheet("font-size: 22px; color: white; background: transparent; border: none;")
        nav_layout.addWidget(btn_tab_chat)

        nav_layout.addStretch()

        btn_logout = QPushButton("🚪")
        btn_logout.setToolTip("Đăng xuất")
        btn_logout.setStyleSheet("font-size: 20px; color: white; background: transparent; border: none;")
        btn_logout.clicked.connect(self.close)
        nav_layout.addWidget(btn_logout)

        main_layout.addWidget(nav_rail)

        # --- 2. SIDEBAR (CONVERSATIONS LIST) ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebarArea")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 14, 10, 10)
        side_layout.setSpacing(10)

        # Search Bar
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Tìm kiếm hội thoại...")
        self.txt_search.textChanged.connect(self.filter_conversations)
        side_layout.addWidget(self.txt_search)

        lbl_conv_title = QLabel("HỘI THOẠI (POSTGRESQL)")
        lbl_conv_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        lbl_conv_title.setStyleSheet("color: #64748b; margin-top: 4px;")
        side_layout.addWidget(lbl_conv_title)

        # List Widget Conversations
        self.list_convs = QListWidget()
        self.populate_conversations()
        self.list_convs.currentRowChanged.connect(self.on_conv_selected)
        side_layout.addWidget(self.list_convs)

        main_layout.addWidget(sidebar)

        # --- 3. MAIN CHAT AREA ---
        chat_area = QFrame()
        chat_layout = QVBoxLayout(chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Header Bar
        header = QFrame()
        header.setObjectName("chatHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)

        header_info = QVBoxLayout()
        header_info.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_chat_title = QLabel("Chọn một cuộc trò chuyện để bắt đầu")
        self.lbl_chat_title.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self.lbl_chat_title.setStyleSheet("color: #1e293b;")
        header_info.addWidget(self.lbl_chat_title)

        self.lbl_chat_status = QLabel("TCP Socket 0ms")
        self.lbl_chat_status.setFont(QFont("Arial", 11))
        self.lbl_chat_status.setStyleSheet("color: #64748b;")
        header_info.addWidget(self.lbl_chat_status)
        h_layout.addLayout(header_info)

        h_layout.addStretch()

        # NÚT GỌI VIDEO WEBRTC (TÍNH NĂNG ĐẶC BIỆT MÔN LẬP TRÌNH MẠNG)
        self.btn_call = QPushButton("📹 Gọi Video (WebRTC)")
        self.btn_call.setObjectName("btnVideoCall")
        self.btn_call.setToolTip("Mở cuộc gọi Video WebRTC P2P kết nối Camera trực tiếp")
        self.btn_call.clicked.connect(self.start_video_call)
        h_layout.addWidget(self.btn_call)

        chat_layout.addWidget(header)

        # Scroll Area Messages
        self.scroll_chat = QScrollArea()
        self.scroll_chat.setObjectName("scrollChat")
        self.scroll_chat.setWidgetResizable(True)
        self.scroll_chat.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.chat_container = QWidget()
        self.chat_container.setObjectName("chatContent")
        self.chat_box_layout = QVBoxLayout(self.chat_container)
        self.chat_box_layout.setContentsMargins(20, 20, 20, 20)
        self.chat_box_layout.setSpacing(12)
        self.chat_box_layout.addStretch()

        self.scroll_chat.setWidget(self.chat_container)
        chat_layout.addWidget(self.scroll_chat)

        # Bottom Input Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("inputToolbar")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(12, 8, 12, 8)
        t_layout.setSpacing(10)

        btn_attach_file = QPushButton("📎")
        btn_attach_file.setProperty("class", "tool-btn")
        btn_attach_file.setToolTip("Gửi tệp tin tài liệu qua Socket TCP")
        btn_attach_file.clicked.connect(self.send_file_dialog)
        t_layout.addWidget(btn_attach_file)

        btn_attach_img = QPushButton("🖼️")
        btn_attach_img.setProperty("class", "tool-btn")
        btn_attach_img.setToolTip("Gửi hình ảnh qua Socket TCP")
        btn_attach_img.clicked.connect(self.send_image_dialog)
        t_layout.addWidget(btn_attach_img)

        self.txt_input = QLineEdit()
        self.txt_input.setObjectName("txtMessage")
        self.txt_input.setPlaceholderText("Nhập tin nhắn... (Nhấn Enter để gửi)")
        self.txt_input.returnPressed.connect(self.send_text_message)
        t_layout.addWidget(self.txt_input)

        self.btn_send = QPushButton("➤")
        self.btn_send.setObjectName("btnSend")
        self.btn_send.clicked.connect(self.send_text_message)
        t_layout.addWidget(self.btn_send)

        chat_layout.addWidget(toolbar)
        main_layout.addWidget(chat_area)

    def bind_signals(self):
        self.worker.sig_history_ack.connect(self.on_history_ack)
        self.worker.sig_chat.connect(self.on_chat_received)
        self.worker.sig_file.connect(self.on_file_received)
        self.worker.sig_user_list.connect(self.on_user_list)
        self.worker.sig_call_req.connect(self.on_call_req)
        self.worker.sig_call_resp.connect(self.on_call_resp)
        self.worker.sig_call_end.connect(self.on_call_end)
        self.worker.sig_disconnected.connect(self.on_disconnected)

    def populate_conversations(self):
        self.list_convs.clear()
        for idx, c in enumerate(self.conversations):
            item = QListWidgetItem()
            item.setSizeHint(QSize(240, 56))

            item_widget = QWidget()
            row = QHBoxLayout(item_widget)
            row.setContentsMargins(6, 4, 6, 4)

            # Avatar
            lbl_av = QLabel("💬" if c.get("is_group") else "👤")
            lbl_av.setFont(QFont("Segoe UI Emoji", 16))
            row.addWidget(lbl_av)

            # Details
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl_name = QLabel(c.get("name", "Hội thoại"))
            lbl_name.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            lbl_last = QLabel(c.get("last_message") or "Chưa có tin nhắn")
            lbl_last.setFont(QFont("Arial", 10))
            lbl_last.setStyleSheet("color: #64748b;")
            col.addWidget(lbl_name)
            col.addWidget(lbl_last)
            row.addLayout(col)

            row.addStretch()

            lbl_time = QLabel(c.get("updated_at", ""))
            lbl_time.setFont(QFont("Arial", 9))
            lbl_time.setStyleSheet("color: #94a3b8;")
            row.addWidget(lbl_time)

            self.list_convs.addItem(item)
            self.list_convs.setItemWidget(item, item_widget)

    def filter_conversations(self, keyword):
        kw = keyword.lower().strip()
        for idx in range(self.list_convs.count()):
            item = self.list_convs.item(idx)
            c = self.conversations[idx]
            match = kw in c.get("name", "").lower() or kw in c.get("other_username", "").lower()
            item.setHidden(not match)

    def on_conv_selected(self, row):
        if row < 0 or row >= len(self.conversations):
            return

        c = self.conversations[row]
        self.current_conv_id = c.get("id")
        self.current_peer_user = c.get("other_username", "")
        self.current_peer_name = c.get("name", "Hội thoại")

        self.lbl_chat_title.setText(self.current_peer_name)
        self.update_peer_online_status()

        # Xóa tin nhắn cũ đang hiển thị
        self.clear_chat_bubbles()

        # Gửi gói tin LOAD_HISTORY qua Socket TCP tới Server
        self.worker.send_packet({
            "type": protocol.MSG_TYPE_LOAD_HISTORY,
            "conversation_id": self.current_conv_id,
        })

    def update_peer_online_status(self):
        if self.current_peer_user in self.online_users:
            self.lbl_chat_status.setText(f"🟢 Trực tuyến (@{self.current_peer_user}) | Socket TCP")
            self.lbl_chat_status.setStyleSheet("color: #16a34a; font-weight: 500;")
        else:
            self.lbl_chat_status.setText(f"⚪ Offline (@{self.current_peer_user}) | Lưu CSDL PostgreSQL")
            self.lbl_chat_status.setStyleSheet("color: #64748b;")

    def clear_chat_bubbles(self):
        while self.chat_box_layout.count() > 1:
            child = self.chat_box_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def on_history_ack(self, data: dict):
        if data.get("conversation_id") != self.current_conv_id:
            return

        messages = data.get("messages", [])
        for m in messages:
            self.add_message_bubble(m)
        self.scroll_to_bottom()

    def on_chat_received(self, data: dict):
        if data.get("conversation_id") == self.current_conv_id:
            self.add_message_bubble(data)
            self.scroll_to_bottom()

    def on_file_received(self, data: dict):
        if data.get("conversation_id") == self.current_conv_id:
            self.add_message_bubble(data)
            self.scroll_to_bottom()

    def add_message_bubble(self, msg_data: dict):
        sender = msg_data.get("sender", "")
        is_me = (sender == self.user_data.get("username"))
        m_type = msg_data.get("message_type", "text")
        content = msg_data.get("content", "")
        timestamp = msg_data.get("timestamp", "")
        sender_name = msg_data.get("sender_name", sender)

        bubble_widget = QWidget()
        b_layout = QHBoxLayout(bubble_widget)
        b_layout.setContentsMargins(0, 2, 0, 2)

        card = QFrame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(4)

        # Style theo Người gửi (Phải: Xanh của bạn, Trái: Trắng đối phương)
        if is_me:
            b_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
            card.setStyleSheet("""
                QFrame {
                    background-color: #dbeafe;
                    border: 1px solid #bfdbfe;
                    border-radius: 12px;
                    max-width: 520px;
                }
            """)
        else:
            b_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            card.setStyleSheet("""
                QFrame {
                    background-color: #ffffff;
                    border: 1px solid #e2e8f0;
                    border-radius: 12px;
                    max-width: 520px;
                }
            """)
            lbl_sender = QLabel(sender_name)
            lbl_sender.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            lbl_sender.setStyleSheet("color: #0068ff;")
            card_layout.addWidget(lbl_sender)

        # Hiển thị nội dung theo Loại tin nhắn
        if m_type == "call":
            lbl_content = QLabel(f"📹 {content}")
            lbl_content.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            lbl_content.setStyleSheet("color: #0284c7;")
            card_layout.addWidget(lbl_content)
        elif m_type == "image":
            lbl_content = QLabel(f"🖼️ [Hình ảnh]: {msg_data.get('attachment_name') or 'Ảnh'}")
            lbl_content.setFont(QFont("Arial", 11))
            card_layout.addWidget(lbl_content)
        elif m_type == "file":
            lbl_content = QLabel(f"📄 [Tệp tin]: {msg_data.get('attachment_name') or msg_data.get('file_name')} ({msg_data.get('file_size_str', '')})")
            lbl_content.setFont(QFont("Arial", 11))
            card_layout.addWidget(lbl_content)
        else:
            lbl_content = QLabel(content)
            lbl_content.setFont(QFont("Arial", 11))
            lbl_content.setWordWrap(True)
            card_layout.addWidget(lbl_content)

        lbl_time = QLabel(timestamp)
        lbl_time.setFont(QFont("Arial", 8))
        lbl_time.setStyleSheet("color: #94a3b8;")
        lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        card_layout.addWidget(lbl_time)

        b_layout.addWidget(card)
        # Chèn trước phần stretch cuối cùng
        count = self.chat_box_layout.count()
        self.chat_box_layout.insertWidget(count - 1, bubble_widget)

    def scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_chat.verticalScrollBar().setValue(
            self.scroll_chat.verticalScrollBar().maximum()
        ))

    def send_text_message(self):
        text = self.txt_input.text().strip()
        if not text or not self.current_conv_id:
            return

        packet = {
            "type": protocol.MSG_TYPE_CHAT,
            "conversation_id": self.current_conv_id,
            "content": text,
        }
        self.worker.send_packet(packet)
        self.txt_input.clear()

    def send_file_dialog(self):
        if not self.current_conv_id:
            return
        filepath, _ = QFileDialog.getOpenFileName(self, "Chọn tệp tin gửi qua Socket TCP")
        if filepath:
            self.upload_file_packet(filepath, is_image=False)

    def send_image_dialog(self):
        if not self.current_conv_id:
            return
        filepath, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh gửi qua Socket TCP", "", "Images (*.png *.jpg *.jpeg *.gif)")
        if filepath:
            self.upload_file_packet(filepath, is_image=True)

    def upload_file_packet(self, filepath: str, is_image: bool = False):
        try:
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            with open(filepath, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

            packet = {
                "type": protocol.MSG_TYPE_FILE,
                "conversation_id": self.current_conv_id,
                "file_name": filename,
                "file_size": filesize,
                "file_data": b64_data,
                "is_image": is_image,
            }
            self.worker.send_packet(packet)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc file", f"Không thể gửi file: {e}")

    # ==========================================================================
    # WEBRTC VIDEO CALL HANDLERS
    # ==========================================================================
    def start_video_call(self):
        """Bắt đầu cuộc gọi Video WebRTC tới đối phương."""
        if not self.current_conv_id or not self.current_peer_user:
            QMessageBox.warning(self, "Chú ý", "Vui lòng chọn một người bạn để gọi video!")
            return

        room_id = f"room_{self.current_conv_id}_{self.user_data.get('username')}"

        # Gửi thông báo Báo hiệu yêu cầu gọi qua Socket TCP tới Server
        packet = {
            "type": protocol.MSG_TYPE_CALL_REQ,
            "target": self.current_peer_user,
            "caller_name": self.user_data.get("display_name"),
            "conversation_id": self.current_conv_id,
            "room_id": room_id,
        }
        self.worker.send_packet(packet)

        # Mở Cửa sổ Pop-up WebRTC Video Call của bên gọi
        self.open_webrtc_popup(self.current_conv_id, self.user_data.get("username"), self.current_peer_name, role="caller", room=room_id)

    def on_call_req(self, data: dict):
        """Nhận được yêu cầu cuộc gọi đến từ đối phương qua Socket TCP."""
        caller = data.get("caller")
        caller_name = data.get("caller_name", caller)
        conv_id = data.get("conversation_id")
        room_id = data.get("room_id")

        reply = QMessageBox.question(
            self,
            "📞 CUỘC GỌI VIDEO ĐẾN (WEBRTC)",
            f"🔔 {caller_name} (@{caller}) đang gọi video cho bạn!\n\nBạn có muốn mở Camera và trả lời cuộc gọi WebRTC không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Chấp nhận cuộc gọi
            self.worker.send_packet({
                "type": protocol.MSG_TYPE_CALL_RESP,
                "caller": caller,
                "status": "ACCEPT",
                "room_id": room_id,
                "conversation_id": conv_id,
            })
            # Mở cửa sổ WebRTC Video Call của bên nghe
            self.open_webrtc_popup(conv_id, self.user_data.get("username"), caller_name, role="callee", room=room_id)
        else:
            # Từ chối cuộc gọi
            self.worker.send_packet({
                "type": protocol.MSG_TYPE_CALL_RESP,
                "caller": caller,
                "status": "REJECT",
                "room_id": room_id,
                "conversation_id": conv_id,
            })

    def on_call_resp(self, data: dict):
        """Phản hồi cuộc gọi từ người nhận."""
        status = data.get("status")
        if status == "OFFLINE":
            QMessageBox.warning(self, "Cuộc gọi thất bại", "Người bạn này hiện không online qua Socket TCP!")
        elif status == "REJECT":
            QMessageBox.information(self, "Cuộc gọi bị từ chối", f"{data.get('callee')} đã từ chối cuộc gọi.")
        elif status == "ACCEPT":
            print("[CALL] Cuộc gọi đã được chấp nhận. Đang đàm thoại WebRTC.")

    def on_call_end(self, data: dict):
        """Cuộc gọi kết thúc."""
        conv_id = data.get("conversation_id")
        if conv_id == self.current_conv_id:
            dur = data.get("duration", 0)
            m_dur = f"{dur // 60:02d}:{dur % 60:02d}"
            self.add_message_bubble({
                "sender": data.get("sender"),
                "message_type": "call",
                "content": f"Cuộc gọi video ({m_dur})",
                "timestamp": data.get("timestamp", "")
            })
            self.scroll_to_bottom()

    def open_webrtc_popup(self, conv_id, username, peer_name, role="caller", room=""):
        """Kích hoạt mở Cửa sổ Pop-up WebRTC Video Call mở Camera."""
        call_url = f"http://127.0.0.1:{WEB_PORT}/call/?conv={conv_id}&user={username}&peer={peer_name}&role={role}&room={room}"

        # Ưu tiên mở dưới dạng App Window của Google Chrome (cửa sổ Desktop không thanh URL)
        chrome_bin = "/usr/bin/google-chrome"
        if os.path.exists(chrome_bin):
            try:
                subprocess.Popen([
                    chrome_bin,
                    f"--app={call_url}",
                    "--window-size=860,640",
                    "--window-position=200,100"
                ])
                return
            except Exception as e:
                print("Lỗi mở Chrome App Window:", e)

        # Fallback trình duyệt mặc định
        webbrowser.open(call_url)

    def on_user_list(self, data: dict):
        self.online_users = data.get("users", [])
        self.update_peer_online_status()

    def on_disconnected(self, msg: str):
        self.lbl_chat_status.setText(f"❌ {msg}")
        self.lbl_chat_status.setStyleSheet("color: #dc2626;")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    worker = SocketWorker(DEFAULT_HOST, DEFAULT_PORT)

    login_dlg = LoginDialog(worker)
    if login_dlg.exec() == QDialog.DialogCode.Accepted:
        win = ZaloDesktopWindow(worker, login_dlg.user_data, login_dlg.conversations, login_dlg.contacts)
        win.show()
        sys.exit(app.exec())
    else:
        worker.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
