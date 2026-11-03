#!/usr/bin/env python3
"""
run_desktop.py - Khởi chạy trọn bộ Ứng dụng Zalo Desktop môn Lập trình Mạng.
1. Khởi động Máy chủ TCP Socket Server lõi (server.py:5555).
2. Khởi động Máy chủ Báo hiệu WebRTC P2P (Daphne ASGI:8000).
3. Tự động bật Giao diện Desktop Client Zalo (PyQt6).
"""

import os
import signal
import subprocess
import sys
import time


def free_port(port):
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    except Exception:
        pass


def main():
    print("=" * 72)
    print("  🚀 ZALO DESKTOP - HỆ THỐNG CHAT ROOM SOCKET TCP & WEBRTC P2P")
    print("  🎓 Đề tài Đồ án Lập trình Mạng (SV: Phạm Huỳnh Quân & Lê Phú Bảo)")
    print("  ⚙️ Mô hình Client - Server Socket TCP Đa luồng (Port: 5555)")
    print("  🗄️ Cơ sở dữ liệu bền vững: PostgreSQL (zalo_chat)")
    print("  📹 Cuộc gọi Video: WebRTC P2P Video Call (chỉ mở Camera khi gọi điện)")
    print("=" * 72)

    # 1. Giải phóng cổng 5555 và 8000 nếu bận
    free_port(5555)
    free_port(8000)
    time.sleep(0.5)

    processes = []

    try:
        # 2. Khởi động Daphne ASGI (WebRTC Signaling & Media Server)
        print("[1/3] 🌐 Đang khởi động WebRTC Signaling Server (Daphne ASGI :8000)...")
        daphne_cmd = [sys.executable, "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "zalo_project.asgi:application"]
        p_daphne = subprocess.Popen(daphne_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(p_daphne)
        time.sleep(1)

        # 3. Khởi động TCP Socket Server (server.py:5555)
        print("[2/3] ⚙️ Đang khởi động TCP Multi-threaded Socket Server (:5555)...")
        p_server = subprocess.Popen([sys.executable, "server.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(p_server)
        time.sleep(1)

        # In thông báo tài khoản demo
        print("\n" + "-" * 72)
        print("  🔑 TÀI KHOẢN MẪU ĐÃ CÓ SẴN TRONG POSTGRESQL (Mật khẩu: password123 hoặc 123456):")
        print("     • quan  (Phạm Huỳnh Quân - Client 1)")
        print("     • bao   (Lê Phú Bảo     - Client 2)")
        print("     • camnt (Cô Camnt        - Giảng viên)")
        print("     • phuc  (Nguyễn Hoàng Phúc)")
        print("-" * 72 + "\n")

        # 4. Khởi chạy Ứng dụng Desktop Zalo (Native Window - Giao diện Zalo PC tuyệt đẹp)
        print("[3/3] 💬 Đang mở Cửa sổ Ứng dụng Zalo Desktop (Giao diện chuẩn Zalo PC)...")
        print("👉 Muốn mở thêm Client 2 để chat và gọi video thử, mở thêm Terminal và gõ: python3 client_desktop.py 2")
        print("👉 Nhấn Ctrl+C trong Terminal này khi muốn dừng toàn bộ Server.\n")
        
        p_client = subprocess.Popen([sys.executable, "client_desktop.py", "1"])
        p_client.wait()

        # Giữ Server chạy tiếp cho các Client khác (như Client 2) cho đến khi bấm Ctrl+C
        print("[*] Cửa sổ Client 1 đã đóng. Server vẫn đang chạy ngầm cho Client khác.")
        print("👉 Nhấn Ctrl+C để tắt hoàn toàn hệ thống.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[!] Đang tắt hệ thống...")
    finally:
        print("🛑 Đang đóng các tiến trình máy chủ...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print("✅ Toàn bộ hệ thống đã dừng an toàn.")


if __name__ == "__main__":
    main()
