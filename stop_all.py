#!/usr/bin/env python3
"""
stop_all.py - Dừng cưỡng chế toàn bộ các tiến trình Server và giải phóng các cổng mạng (:8000, :5555).
Dùng khi máy báo lỗi 'Address already in use' hoặc khi muốn tắt sạch hệ thống để khởi động lại.
"""

import os
import signal
import subprocess
import sys
import time


def kill_port(port: int):
    print(f"[*] Đang giải phóng cổng {port}...")
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
                        print(f"    -> Đã buộc dừng tiến trình PID: {pid}")
                except Exception:
                    pass
    except Exception:
        pass


def kill_process_by_name(pattern: str):
    try:
        res = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=2)
        if res.stdout.strip():
            my_pid = os.getpid()
            for pid_str in res.stdout.strip().split():
                try:
                    pid = int(pid_str)
                    if pid != my_pid:
                        os.kill(pid, signal.SIGKILL)
                        print(f"    -> Đã tắt tiến trình {pattern} (PID {pid})")
                except Exception:
                    pass
    except Exception:
        pass


def main():
    print("=" * 65)
    print("🛑 DỌN DẸP TIẾN TRÌNH & GIẢI PHÓNG CỔNG MÁY CHỦ TCP SOCKET")
    print("=" * 65)

    kill_port(5555)

    # Dừng các tiến trình server nếu còn chạy ngầm
    kill_process_by_name("[s]erver.py")
    kill_process_by_name("client_desktop.py")
    kill_process_by_name("zalo_desktop_profile")

    time.sleep(0.3)
    print("=" * 65)
    print("✅ ĐÃ GIẢI PHÓNG TOÀN BỘ CỔNG TCP SOCKET 5555 THÀNH CÔNG!")
    print("👉 Bây giờ bạn có thể khởi động lại Server mà không bị lỗi.")
    print("=" * 65)


if __name__ == "__main__":
    main()

