#!/usr/bin/env python3
"""
client_desktop.py - Ứng dụng Zalo Desktop (Zalo PC Native Window).
Đồ án Lập trình Mạng - SV: Phạm Huỳnh Quân & Lê Phú Bảo.

Chạy toàn bộ Giao diện Zalo Web pixel-perfect dưới dạng một CỬA SỔ PHẦN MỀM DESKTOP độc lập:
- Hoàn toàn KHÔNG CÓ thanh URL, KHÔNG CÓ tab trình duyệt, KHÔNG CÓ nút back/forward.
- Giữ nguyên 100% đồ họa siêu đẹp: Dark Mode, Bong bóng chat, Emojis, Thả tim, Voice note sóng âm, To-do, Cloud.
- Tích hợp cuộc gọi WebRTC P2P Video Call mở Camera trực tiếp.
- Dữ liệu đồng bộ bền vững với CSDL PostgreSQL.
"""

import os
import socket
import subprocess
import sys
import time

TARGET_URL = "http://127.0.0.1:8000"


def is_port_open(host="127.0.0.1", port=8000):
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except Exception:
        return False


def ensure_backend_running():
    """Kiểm tra và tự động khởi động Server ngầm nếu chưa chạy."""
    if is_port_open("127.0.0.1", 8000):
        return

    print("[*] Phát hiện Server chưa chạy. Đang tự động bật Máy chủ Zalo...")
    # Bật Daphne ASGI Server (:8000)
    subprocess.Popen([
        sys.executable, "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "zalo_project.asgi:application"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Bật TCP Socket Server (:5555) nếu chưa chạy
    if not is_port_open("127.0.0.1", 5555):
        subprocess.Popen([sys.executable, "server.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Đợi máy chủ sẵn sàng
    for _ in range(25):
        time.sleep(0.3)
        if is_port_open("127.0.0.1", 8000):
            print("✅ Máy chủ Zalo đã sẵn sàng!")
            return

    print("⚠️ Cảnh báo: Server đang khởi động...")


def launch_zalo_desktop():
    print("=" * 70)
    print("🚀 KHỞI ĐỘNG ZALO DESKTOP APPLICATION (NATIVE WINDOW)")
    print("=" * 70)

    # Tự động đảm bảo Server luôn hoạt động trước khi mở cửa sổ Desktop
    ensure_backend_running()

    # 1. Chế độ Application Mode độc lập (Native Desktop Window không dính vào trình duyệt đang mở)
    chrome_bin = "/usr/bin/google-chrome"
    profile_num = sys.argv[1] if len(sys.argv) > 1 else "1"
    profile_dir = os.path.expanduser(f"~/.config/zalo_desktop_profile_{profile_num}")
    os.makedirs(profile_dir, exist_ok=True)

    if os.path.exists(chrome_bin):
        try:
            print("[*] Đang mở Cửa sổ Desktop Zalo PC (Native App Window)...")
            cmd = [
                chrome_bin,
                f"--app={TARGET_URL}",
                f"--user-data-dir={profile_dir}",
                "--window-size=1260,840",
                "--window-position=80,40",
                "--app-id=zalo-desktop-ltm",
                "--class=ZaloPC",
                "--autoplay-policy=no-user-gesture-required",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            subprocess.run(cmd)
            return
        except Exception as e:
            print(f"[!] Lỗi khởi chạy Chrome App Mode: {e}")

    # 2. Phương án dự phòng qua PyWebView
    try:
        import webview
        print("[*] Khởi tạo cửa sổ Desktop qua PyWebView Engine...")
        window = webview.create_window(
            title="Zalo PC - Hệ thống Chat Room & WebRTC Video Call (Lập trình Mạng)",
            url=TARGET_URL,
            width=1240,
            height=820,
            resizable=True
        )
        webview.start()
        return
    except Exception as e:
        print(f"[!] Lỗi PyWebView: {e}")

    # 3. Fallback cuối cùng: Trình duyệt mặc định
    import webbrowser
    print("[*] Mở cửa sổ ứng dụng...")
    webbrowser.open(TARGET_URL)


if __name__ == "__main__":
    launch_zalo_desktop()
