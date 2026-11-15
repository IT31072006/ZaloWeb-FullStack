#!/usr/bin/env python3
"""
server_gui.py - Giao diện Đồ họa Quản trị Máy chủ Zalo Chat (Server GUI).
Đồ án môn Lập trình Mạng (LTM) - SV: Phạm Huỳnh Quân (24IT220) & Lê Phú Bảo (24IT018).

Tính năng:
1. Quản lý toàn diện TCP Socket Server (:5555) và Web/WebRTC ASGI Daphne (:8000).
2. Điều khiển Khởi động (Start) / Dừng (Stop) máy chủ trực quan chỉ với 1 chạm.
3. Theo dõi danh sách Client đang kết nối thời gian thực (IP, Port, Nickname, Uptime).
4. Tính năng Kick client vi phạm hoặc ngắt kết nối an toàn.
5. Phát thông báo khẩn từ Máy chủ (Broadcast System Message) tới toàn bộ Client.
6. Màn hình Live Log hiển thị phân màu trực quan mọi sự kiện mạng (Connect, Chat, Call, File).
7. Phím tắt mở nhanh Zalo Web, Trang Quản trị Django Admin, và Client Chat Desktop.
"""

import datetime
import html
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QPainter, QBrush, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QFrame, QCheckBox, QMessageBox, QFileDialog,
    QSplitter, QProgressBar
)

# Tải cấu hình và lõi ChatServer
from server import ChatServer, DEFAULT_HOST, DEFAULT_PORT
try:
    from django.conf import settings
    DB_ENGINE = settings.DATABASES['default']['ENGINE'].split('.')[-1].upper()
    DB_NAME = settings.DATABASES['default'].get('NAME', 'zalo_chat')
except Exception:
    DB_ENGINE = "SQLITE"
    DB_NAME = "db.sqlite3"


def kill_port(port: int):
    """Giải phóng cổng mạng triệt để bằng SIGKILL, tránh lỗi Address already in use."""
    try:
        subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], capture_output=True, timeout=2)
    except Exception:
        pass
    try:
        res = subprocess.run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True, timeout=2)
        if res.stdout.strip():
            my_pid = os.getpid()
            for pid_str in res.stdout.strip().split():
                try:
                    pid = int(pid_str)
                    if pid != my_pid:
                        os.kill(pid, 9)
                except Exception:
                    pass
    except Exception:
        pass
    time.sleep(0.2)


def get_lan_ip() -> str:
    """Lấy IP Wi-Fi/LAN thực tế của máy chủ để các máy khác kết nối."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ServerBridge(QObject):
    """Cầu nối truyền tín hiệu an toàn giữa Socket Thread và Qt GUI Thread."""
    sig_log = pyqtSignal(str, str, str)     # timestamp, tag, message
    sig_clients = pyqtSignal(list)          # list of client info dicts
    sig_status = pyqtSignal(bool)           # is_running
    sig_web_status = pyqtSignal(bool)       # is_web_running


class ServerMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zalo Chat Server - Bảng Quản Trị Máy Chủ TCP & Web (Lập Trình Mạng)")
        self.resize(1180, 750)
        self.setMinimumSize(950, 600)

        self.bridge = ServerBridge()
        self.server: ChatServer | None = None
        self.server_thread: threading.Thread | None = None
        self.daphne_proc: subprocess.Popen | None = None
        self.start_time: float | None = None

        self.bridge.sig_log.connect(self.on_receive_log)
        self.bridge.sig_clients.connect(self.on_receive_clients)
        self.bridge.sig_status.connect(self.on_status_changed)
        self.bridge.sig_web_status.connect(self.on_web_status_changed)

        # Timer cập nhật Uptime
        self.uptime_timer = QTimer(self)
        self.uptime_timer.timeout.connect(self.update_uptime)
        self.uptime_timer.start(1000)

        self.setup_ui()
        self.apply_styles()

        # Log khởi động ban đầu
        self.add_log_entry("SYSTEM", "Giao diện Quản trị Máy chủ Zalo Chat đã sẵn sàng.")
        self.add_log_entry("NETWORK", f"Địa chỉ IP LAN của máy chủ: {self.lan_ip}")
        self.add_log_entry("GUIDE", f"👉 Máy bạn bè kết nối qua link: http://{self.lan_ip}:8000")
        self.add_log_entry("DB", f"Cơ sở dữ liệu đang liên kết: {DB_ENGINE} ({DB_NAME})")

    # ==========================================================================
    # GIAO DIỆN NGƯỜI DÙNG (UI)
    # ==========================================================================
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(14)

        # 1. HEADER & METRICS CARDS
        header_widget = self.create_header()
        main_layout.addWidget(header_widget)

        # 2. CONTROL TOOLBAR
        control_card = self.create_controls()
        main_layout.addWidget(control_card)

        # 3. SPLITTER (BẢNG CLIENT + LIVE LOG)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        # Cột trái: Quản lý Client Online & Broadcast
        clients_panel = self.create_clients_panel()
        splitter.addWidget(clients_panel)

        # Cột phải: Khung Console Log trực quan
        log_panel = self.create_log_panel()
        splitter.addWidget(log_panel)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        main_layout.addWidget(splitter, 1)

        # 4. STATUS BAR CHÂN TRANG
        status_bar = self.create_footer_status()
        main_layout.addWidget(status_bar)

    def create_header(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Brand / Title
        brand_box = QVBoxLayout()
        title_label = QLabel("🛡️ ZALO SERVER DASHBOARD")
        title_label.setObjectName("lblHeaderTitle")
        sub_label = QLabel("Hệ Thống Máy Chủ Socket TCP (:5555) & WebRTC Signaling (:8000) | Đồ Án LTM")
        sub_label.setObjectName("lblHeaderSub")
        brand_box.addWidget(title_label)
        brand_box.addWidget(sub_label)
        layout.addLayout(brand_box)

        layout.addStretch()

        # Thẻ 0: IP LAN Máy Chủ
        self.lan_ip = get_lan_ip()
        self.card_ip = self.create_metric_card(
            "IP MÁY CHỦ (LAN)", self.lan_ip, "Cổng TCP: 5555", "#eff6ff", "#1d4ed8"
        )
        layout.addWidget(self.card_ip)

        # Thẻ 1: Trạng thái Socket Server
        self.card_socket = self.create_metric_card(
            "MÁY CHỦ TCP SOCKET", "ĐÃ DỪNG 🔴", "Cổng: 5555", "#fee2e2", "#991b1b"
        )
        layout.addWidget(self.card_socket)

        # Thẻ 2: Client Online
        self.card_clients_count = self.create_metric_card(
            "CLIENT ONLINE", "0", "Đang kết nối", "#e0f2fe", "#0369a1"
        )
        layout.addWidget(self.card_clients_count)

        # Thẻ 3: Database
        db_badge = "PostgreSQL" if "POSTGRES" in DB_ENGINE else "SQLite"
        self.card_db = self.create_metric_card(
            "CƠ SỞ DỮ LIỆU", db_badge, DB_NAME, "#f0fdf4", "#15803d"
        )
        layout.addWidget(self.card_db)

        return widget

    def create_metric_card(self, title: str, val: str, sub: str, bg: str, fg: str) -> QFrame:
        card = QFrame()
        card.setFixedSize(175, 74)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 10px;
            }}
        """)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b;")
        lbl_v = QLabel(val)
        lbl_v.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {fg};")
        lbl_s = QLabel(sub)
        lbl_s.setStyleSheet("font-size: 11px; color: #64748b;")

        vbox.addWidget(lbl_t)
        vbox.addWidget(lbl_v)
        vbox.addWidget(lbl_s)
        card.lbl_val = lbl_v
        card.lbl_sub = lbl_s
        return card

    def create_controls(self) -> QFrame:
        card = QFrame()
        card.setObjectName("controlCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        # Nút Bật Server TCP
        self.btn_start = QPushButton("▶  Khởi Động Server TCP")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_all_servers)
        layout.addWidget(self.btn_start)

        # Nút Tắt Server TCP
        self.btn_stop = QPushButton("⏹  Dừng Server")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop_all_servers)
        layout.addWidget(self.btn_stop)

        layout.addStretch()

        # Nút Mở Zalo Desktop Native (Giao diện Zalo PC đẹp chuẩn)
        btn_open_client = QPushButton("💬 Mở Zalo Desktop (PC)")
        btn_open_client.setObjectName("btnClient")
        btn_open_client.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_client.clicked.connect(lambda: self.launch_desktop_client("1"))
        layout.addWidget(btn_open_client)

        btn_open_client2 = QPushButton("👥 Mở Client 2 (Test 2 Máy)")
        btn_open_client2.setObjectName("btnSecondary")
        btn_open_client2.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_client2.clicked.connect(lambda: self.launch_desktop_client("2"))
        layout.addWidget(btn_open_client2)

        # Nút Mở Client PyQt6
        btn_open_pyqt = QPushButton("📱 Client PyQt6")
        btn_open_pyqt.setObjectName("btnSecondary")
        btn_open_pyqt.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_pyqt.clicked.connect(self.launch_pyqt_client)
        layout.addWidget(btn_open_pyqt)
        btn_open_client2.setObjectName("btnSecondary")
        btn_open_client2.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_client2.clicked.connect(lambda: self.launch_desktop_client("2"))
        layout.addWidget(btn_open_client2)

        return card

    def create_clients_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelFrame")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header
        top_bar = QHBoxLayout()
        lbl_title = QLabel("👥 Quản Lý Client Đang Online")
        lbl_title.setObjectName("lblPanelTitle")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        self.btn_kick_selected = QPushButton("🚫 Kick Client Đã Chọn")
        self.btn_kick_selected.setObjectName("btnKick")
        self.btn_kick_selected.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_kick_selected.clicked.connect(self.kick_selected_client)
        top_bar.addWidget(self.btn_kick_selected)

        layout.addLayout(top_bar)

        # Bảng danh sách Client
        self.table_clients = QTableWidget()
        self.table_clients.setColumnCount(4)
        self.table_clients.setHorizontalHeaderLabels(["Tài khoản (Nick)", "Địa chỉ IP", "Cổng", "Tham gia lúc"])
        self.table_clients.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_clients.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_clients.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_clients.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_clients.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_clients.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_clients.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_clients, 1)

        # Thanh phát thông báo hệ thống (Broadcast Message)
        broadcast_box = QHBoxLayout()
        self.txt_broadcast = QLineEdit()
        self.txt_broadcast.setPlaceholderText("Nhập thông báo gửi tới tất cả người dùng trong hệ thống...")
        self.txt_broadcast.returnPressed.connect(self.send_broadcast)
        broadcast_box.addWidget(self.txt_broadcast, 1)

        btn_broadcast = QPushButton("📢 Phát Thông Báo")
        btn_broadcast.setObjectName("btnBroadcast")
        btn_broadcast.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_broadcast.clicked.connect(self.send_broadcast)
        broadcast_box.addWidget(btn_broadcast)

        layout.addLayout(broadcast_box)
        return panel

    def create_log_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelFrame")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header Log
        top_bar = QHBoxLayout()
        lbl_title = QLabel("📜 Nhật Ký Hoạt Động (Live Server Logs)")
        lbl_title.setObjectName("lblPanelTitle")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        btn_clear_log = QPushButton("🗑️ Xóa Log")
        btn_clear_log.setObjectName("btnSmall")
        btn_clear_log.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_log.clicked.connect(self.clear_logs)
        top_bar.addWidget(btn_clear_log)

        btn_save_log = QPushButton("💾 Xuất File")
        btn_save_log.setObjectName("btnSmall")
        btn_save_log.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_log.clicked.connect(self.save_logs)
        top_bar.addWidget(btn_save_log)

        layout.addLayout(top_bar)

        # Màn hình Log
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setObjectName("logViewer")
        layout.addWidget(self.log_viewer, 1)

        return panel

    def create_footer_status(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(4, 0, 4, 0)

        self.lbl_footer_status = QLabel("● Sẵn sàng")
        self.lbl_footer_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_footer_status)

        layout.addStretch()

        self.lbl_uptime = QLabel("⏱️ Thời gian hoạt động: 00:00:00")
        self.lbl_uptime.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.lbl_uptime)

        return footer

    # ==========================================================================
    # LOGIC ĐIỀU KHIỂN SERVER
    # ==========================================================================
    def start_all_servers(self):
        """Khởi động Socket Server và Daphne Web Server."""
        if self.server and self.server.is_running:
            return

        self.add_log_entry("START", "Đang khởi tạo máy chủ...")
        self.btn_start.setEnabled(False)

        # Giải phóng cổng 5555 nếu có tiến trình cũ chiếm dụng
        try:
            subprocess.run(["fuser", "-k", f"{DEFAULT_PORT}/tcp"], capture_output=True)
            time.sleep(0.3)
        except Exception:
            pass

        # 1. Khởi chạy TCP Socket Server (:5555)
        self.server = ChatServer(host=DEFAULT_HOST, port=DEFAULT_PORT)
        self.server.on_log = lambda ts, tag, msg: self.bridge.sig_log.emit(ts, tag, msg)
        self.server.on_clients_update = lambda clients: self.bridge.sig_clients.emit(clients)
        self.server.on_status_change = lambda status: self.bridge.sig_status.emit(status)

        self.server_thread = threading.Thread(target=self._run_socket_server, daemon=True)
        self.server_thread.start()
        self.start_time = time.time()

    def _run_socket_server(self):
        try:
            self.server.start()
        except Exception as e:
            self.bridge.sig_log.emit(
                datetime.datetime.now().strftime("%H:%M:%S"),
                "ERROR",
                f"Không thể khởi động Socket Server: {e}"
            )
            self.bridge.sig_status.emit(False)

    def stop_all_servers(self):
        """Dừng an toàn máy chủ TCP Socket."""
        self.add_log_entry("STOP", "Đang dừng máy chủ TCP Socket...")

        if self.server:
            self.server.stop()
            self.server = None
        kill_port(5555)

        self.start_time = None
        self.on_status_changed(False)
        self.on_receive_clients([])
        self.add_log_entry("STOP", "Toàn bộ hệ thống máy chủ đã dừng hoàn toàn.")

    def on_status_changed(self, is_running: bool):
        """Cập nhật giao diện khi trạng thái Socket Server thay đổi."""
        self.btn_start.setEnabled(not is_running)
        self.btn_stop.setEnabled(is_running)

        if is_running:
            self.card_socket.lbl_val.setText("HOẠT ĐỘNG 🟢")
            self.card_socket.lbl_val.setStyleSheet("font-size: 15px; font-weight: 800; color: #15803d;")
            self.card_socket.setStyleSheet("""
                QFrame { background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 10px; padding: 6px 10px; }
            """)
            self.lbl_footer_status.setText("● Socket Server đang lắng nghe trên cổng 5555...")
            self.lbl_footer_status.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: bold;")
        else:
            self.card_socket.lbl_val.setText("ĐÃ DỪNG 🔴")
            self.card_socket.lbl_val.setStyleSheet("font-size: 15px; font-weight: 800; color: #991b1b;")
            self.card_socket.setStyleSheet("""
                QFrame { background-color: #fee2e2; border: 1px solid #fca5a5; border-radius: 10px; padding: 6px 10px; }
            """)
            self.lbl_footer_status.setText("● Server đã dừng")
            self.lbl_footer_status.setStyleSheet("color: #64748b; font-size: 12px;")

    def on_web_status_changed(self, is_running: bool):
        """Cập nhật giao diện khi trạng thái Web Server thay đổi."""
        if is_running:
            self.card_web.lbl_val.setText("HOẠT ĐỘNG 🟢")
            self.card_web.lbl_val.setStyleSheet("font-size: 15px; font-weight: 800; color: #15803d;")
            self.card_web.setStyleSheet("""
                QFrame { background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 10px; padding: 6px 10px; }
            """)
        else:
            self.card_web.lbl_val.setText("ĐÃ DỪNG ⚪")
            self.card_web.lbl_val.setStyleSheet("font-size: 15px; font-weight: 800; color: #475569;")
            self.card_web.setStyleSheet("""
                QFrame { background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 10px; padding: 6px 10px; }
            """)

    def on_receive_clients(self, clients: list):
        """Cập nhật bảng danh sách client và thẻ thống kê."""
        self.card_clients_count.lbl_val.setText(str(len(clients)))
        self.table_clients.setRowCount(len(clients))

        for row, info in enumerate(clients):
            nick = info.get("nickname", "Unknown")
            ip = str(info.get("ip", "127.0.0.1"))
            port = str(info.get("port", "0"))
            joined = str(info.get("joined_at", ""))

            item_nick = QTableWidgetItem(f"👤  {nick}")
            item_nick.setFont(QFont("-apple-system", 10, QFont.Weight.Bold))
            item_ip = QTableWidgetItem(ip)
            item_port = QTableWidgetItem(port)
            item_joined = QTableWidgetItem(joined)

            item_ip.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_port.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_joined.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_clients.setItem(row, 0, item_nick)
            self.table_clients.setItem(row, 1, item_ip)
            self.table_clients.setItem(row, 2, item_port)
            self.table_clients.setItem(row, 3, item_joined)

    def kick_selected_client(self):
        """Kick client đang chọn trong bảng."""
        if not self.server or not self.server.is_running:
            QMessageBox.warning(self, "Cảnh báo", "Máy chủ hiện chưa hoạt động.")
            return

        selected_row = self.table_clients.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "Chọn Client", "Vui lòng nhấp chọn một Client trong bảng để ngắt kết nối.")
            return

        nick_item = self.table_clients.item(selected_row, 0)
        if not nick_item:
            return

        nickname = nick_item.text().replace("👤  ", "").strip()
        reply = QMessageBox.question(
            self,
            "Xác nhận Kick Client",
            f"Bạn có chắc chắn muốn ngắt kết nối Client '{nickname}' khỏi máy chủ không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = self.server.kick_client(nickname, "Bị ngắt kết nối bởi Quản trị viên máy chủ.")
            if success:
                self.add_log_entry("KICK", f"Đã kick thành công client '{nickname}'.")
            else:
                QMessageBox.warning(self, "Lỗi", f"Không tìm thấy client '{nickname}' để kick.")

    def send_broadcast(self):
        """Phát thông báo từ máy chủ tới tất cả client."""
        if not self.server or not self.server.is_running:
            QMessageBox.warning(self, "Cảnh báo", "Máy chủ chưa khởi động. Vui lòng bật server trước.")
            return

        msg = self.txt_broadcast.text().strip()
        if not msg:
            return

        self.server.send_server_broadcast(msg)
        self.txt_broadcast.clear()
        self.add_log_entry("ADMIN", f"Phát thông báo: {msg}")

    def launch_desktop_client(self, profile="1"):
        """Mở nhanh 1 cửa sổ Zalo Desktop Native Window."""
        try:
            subprocess.Popen([sys.executable, "client_desktop.py", profile])
            self.add_log_entry("CLIENT", f"Đã khởi chạy Zalo Desktop Client (Profile {profile}).")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở Client: {e}")

    def launch_pyqt_client(self):
        """Mở cửa sổ Client PyQt6 thuần."""
        try:
            subprocess.Popen([sys.executable, "client_gui.py"])
            self.add_log_entry("CLIENT", "Đã khởi chạy 1 cửa sổ Client PyQt6.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể mở Client PyQt6: {e}")

    # ==========================================================================
    # QUẢN LÝ LOG VÀ HIỂN THỊ
    # ==========================================================================
    def on_receive_log(self, ts: str, tag: str, message: str):
        self.add_log_entry(tag, message, ts)

    def add_log_entry(self, tag: str, message: str, ts: str | None = None):
        if not ts:
            ts = datetime.datetime.now().strftime("%H:%M:%S")

        color_map = {
            "START": "#10b981",       # Xanh lá
            "STOP": "#ef4444",        # Đỏ
            "CONNECT": "#06b6d4",     # Xanh ngọc cyan
            "DISCONNECT": "#f97316",  # Cam
            "LEAVE": "#f97316",       # Cam
            "CHAT": "#3b82f6",        # Xanh dương
            "FILE": "#a855f7",        # Tím
            "CALL": "#ec4899",        # Hồng
            "KICK": "#dc2626",        # Đỏ đậm
            "ADMIN": "#eab308",       # Vàng gold
            "WEB": "#6366f1",         # Indigo
            "DB": "#14b8a6",          # Teal
            "SYSTEM": "#94a3b8",      # Xám
            "ERROR": "#f43f5e",       # Đỏ tươi
        }
        tag_color = color_map.get(tag, "#60a5fa")

        safe_msg = html.escape(message)
        html_line = (
            f"<div style='margin-bottom: 3px; font-family: monospace; font-size: 12px; line-height: 1.4;'>"
            f"<span style='color: #64748b;'>[{ts}]</span> "
            f"<b style='color: {tag_color};'>[{tag:<8}]</b> "
            f"<span style='color: #e2e8f0;'>{safe_msg}</span>"
            f"</div>"
        )
        self.log_viewer.append(html_line)
        self.log_viewer.moveCursor(QTextCursor.MoveOperation.End)

    def clear_logs(self):
        self.log_viewer.clear()
        self.add_log_entry("SYSTEM", "Đã dọn sạch nhật ký hoạt động.")

    def save_logs(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Lưu Nhật Ký Máy Chủ", f"server_log_{int(time.time())}.txt", "Text Files (*.txt)"
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.log_viewer.toPlainText())
                QMessageBox.information(self, "Thành công", f"Đã xuất log thành công ra file:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể lưu file: {e}")

    def update_uptime(self):
        if self.start_time and self.server and self.server.is_running:
            elapsed = int(time.time() - self.start_time)
            hrs = elapsed // 3600
            mins = (elapsed % 3600) // 60
            secs = elapsed % 60
            self.lbl_uptime.setText(f"⏱️ Thời gian hoạt động: {hrs:02d}:{mins:02d}:{secs:02d}")
        else:
            self.lbl_uptime.setText("⏱️ Thời gian hoạt động: 00:00:00")

    def closeEvent(self, event):
        """Xử lý khi tắt cửa sổ GUI."""
        if self.server and self.server.is_running:
            reply = QMessageBox.question(
                self,
                "Đóng Máy Chủ",
                "Máy chủ đang hoạt động. Bạn có chắc chắn muốn dừng toàn bộ server và thoát?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_all_servers()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    # ==========================================================================
    # ĐỊNH DẠNG CSS (STYLING)
    # ==========================================================================
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f1f5f9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
            }
            QLabel#lblHeaderTitle {
                font-size: 20px;
                font-weight: 800;
                color: #0f172a;
            }
            QLabel#lblHeaderSub {
                font-size: 13px;
                color: #64748b;
            }
            QFrame#controlCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QFrame#panelFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLabel#lblPanelTitle {
                font-size: 14px;
                font-weight: 700;
                color: #1e293b;
            }
            QPushButton#btnStart {
                background-color: #10b981;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 8px;
                border: none;
            }
            QPushButton#btnStart:hover {
                background-color: #059669;
            }
            QPushButton#btnStart:disabled {
                background-color: #94a3b8;
            }
            QPushButton#btnStop {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 8px;
                border: none;
            }
            QPushButton#btnStop:hover {
                background-color: #dc2626;
            }
            QPushButton#btnStop:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
            QPushButton#btnSecondary {
                background-color: #f8fafc;
                color: #0284c7;
                border: 1px solid #bae6fd;
                font-weight: 600;
                font-size: 12px;
                padding: 7px 14px;
                border-radius: 8px;
            }
            QPushButton#btnSecondary:hover {
                background-color: #e0f2fe;
            }
            QPushButton#btnClient {
                background-color: #0068ff;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 12px;
                padding: 7px 15px;
                border-radius: 8px;
            }
            QPushButton#btnClient:hover {
                background-color: #005ae0;
            }
            QPushButton#btnKick {
                background-color: #fef2f2;
                color: #ef4444;
                border: 1px solid #fecaca;
                font-size: 12px;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 6px;
            }
            QPushButton#btnKick:hover {
                background-color: #fee2e2;
            }
            QPushButton#btnSmall {
                background-color: #f8fafc;
                color: #475569;
                border: 1px solid #cbd5e1;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 6px;
            }
            QPushButton#btnSmall:hover {
                background-color: #f1f5f9;
            }
            QPushButton#btnBroadcast {
                background-color: #f59e0b;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton#btnBroadcast:hover {
                background-color: #d97706;
            }
            QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 7px 12px;
                font-size: 13px;
                background-color: #f8fafc;
            }
            QLineEdit:focus {
                border: 2px solid #0068ff;
                background-color: #ffffff;
            }
            QTableWidget {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: #ffffff;
                gridline-color: #f1f5f9;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: bold;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                padding: 6px;
            }
            QTextEdit#logViewer {
                background-color: #0f172a;
                color: #f8fafc;
                border-radius: 8px;
                border: 1px solid #1e293b;
                padding: 10px;
                font-family: "JetBrains Mono", Consolas, "Courier New", monospace;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e293b;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #475569;
                min-height: 20px;
                border-radius: 5px;
            }
        """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Zalo Server Dashboard")
    window = ServerMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
