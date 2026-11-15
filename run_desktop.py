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
    """Giải phóng cưỡng chế cổng mạng, đảm bảo không bao giờ bị Address already in use."""
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
                        os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass
    time.sleep(0.3)


def get_lan_ip() -> str:
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    lan_ip = get_lan_ip()
    print("=" * 72)
    print("  🚀 ZALO CHAT ROOM - HỆ THỐNG CLIENT - SERVER SOCKET TCP ĐA LUỒNG")
    print("  🎓 Đề tài Đồ án Lập trình Mạng (SV: Phạm Huỳnh Quân & Lê Phú Bảo)")
    print(f"  📡 IP MÁY CHỦ CỦA BẠN (LAN / Wi-Fi): {lan_ip}")
    print(f"  ⚙️ CỔNG MÁY CHỦ TCP SOCKET: 5555")
    print(f"  👉 Lệnh chạy trên Máy 2 (Bạn bè): python3 client_desktop.py {lan_ip}")
    print("  🗄️ Cơ sở dữ liệu: PostgreSQL (zalo_chat)")
    print("=" * 72)

    # 1. Giải phóng cổng 5555 nếu bận
    free_port(5555)
    time.sleep(0.3)

    processes = []

    try:
        # 2. Khởi động TCP Socket Server (server.py:5555)
        print("[1/2] ⚙️ Đang khởi động TCP Multi-threaded Socket Server (:5555)...")
        p_server = subprocess.Popen([sys.executable, "server.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(p_server)
        time.sleep(1)

        # In thông báo tài khoản demo
        print("\n" + "-" * 72)
        print("  🔑 TÀI KHOẢN MẪU ĐÃ CÓ SẴN TRONG POSTGRESQL (Mật khẩu: 123456 hoặc password123):")
        print("     • quan  (Phạm Huỳnh Quân - Client 1)")
        print("     • bao   (Lê Phú Bảo     - Client 2)")
        print("     • camnt (Cô Camnt        - Giảng viên)")
        print("     • phuc  (Nguyễn Hoàng Phúc)")
        print("-" * 72 + "\n")

        # 3. Khởi chạy Ứng dụng Desktop Zalo (Native Window - Giao diện Zalo PC tuyệt đẹp)
        print("[2/2] 💬 Đang mở Cửa sổ Ứng dụng Zalo Desktop kết nối Socket TCP :5555...")
        print(f"👉 Muốn mở thêm Client 2 để chat thử, mở thêm Terminal và gõ: python3 client_desktop.py 2")
        print("👉 Nhấn Ctrl+C trong Terminal này khi muốn dừng toàn bộ Server.\n")
        
        p_client = subprocess.Popen([sys.executable, "client_desktop.py", "1"])
        p_client.wait()

        # Giữ Server chạy tiếp cho các Client khác (như Client 2) cho đến khi bấm Ctrl+C
        print("[*] Cửa sổ Client 1 đã đóng. Máy chủ TCP Socket vẫn đang chạy ngầm cho Client khác.")
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
                p.wait(timeout=1.5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        free_port(5555)
        print("✅ Toàn bộ hệ thống đã dừng an toàn và giải phóng cổng 5555.")


if __name__ == "__main__":
    main()
