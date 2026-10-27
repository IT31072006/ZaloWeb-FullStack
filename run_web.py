#!/usr/bin/env python3
"""
run_web.py - Khởi chạy nhanh máy chủ Zalo Web (Django + PostgreSQL / SQLite).
Hỗ trợ mở trình duyệt tự động hoặc in đường dẫn truy cập rõ ràng.
"""

import os
import sys
import subprocess
import webbrowser
import time

def ensure_admin_and_port():
    # 1. Giải phóng cổng 8000 nếu có tiến trình khác đang chiếm giữ
    try:
        check_port = subprocess.run(["fuser", "8000/tcp"], capture_output=True, text=True)
        if check_port.stdout.strip():
            print("[*] Phát hiện cổng 8000 đang bận. Đang tự động giải phóng cổng...")
            subprocess.run(["fuser", "-k", "8000/tcp"], capture_output=True)
            time.sleep(1)
    except Exception:
        pass

    # 2. Đảm bảo migrations và tài khoản admin luôn tồn tại
    try:
        subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], check=False)
        
        # Đảm bảo tài khoản admin / admin123
        create_admin_code = """
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalo_project.settings')
django.setup()
from django.contrib.auth.models import User
admin_u = User.objects.filter(username='admin').first()
if not admin_u:
    User.objects.create_superuser('admin', 'admin@vku.udn.vn', 'admin123')
else:
    admin_u.set_password('admin123')
    admin_u.is_superuser = True
    admin_u.is_staff = True
    admin_u.save()
"""
        subprocess.run([sys.executable, "-c", create_admin_code], capture_output=True)
    except Exception as e:
        print(f"[!] Lỗi chuẩn bị cơ sở dữ liệu: {e}")

def main():
    print("=" * 68)
    print("  🚀 ZALO WEB CLONE - DJANGO BACKEND & POSTGRESQL / SQLITE")
    print("  🎨 Giao diện Zalo Web chuẩn xác: Tin nhắn, Danh bạ, Giao việc, Cloud")
    print("  👥 Đăng ký, Đăng nhập, Hồ sơ, Đổi ảnh đại diện, Gửi ảnh & Voice Note")
    print("=" * 68)
    print("  🌐 Địa chỉ Web: http://127.0.0.1:8000/")
    print("  🛡️ Trang Quản trị Admin: http://127.0.0.1:8000/admin/ (admin / admin123)")
    print("  🔑 Tài khoản mẫu (Mật khẩu: 123456):")
    print("     • quan (Phạm Huỳnh Quân)")
    print("     • camnt (Cô Camnt - GV LTM)")
    print("     • bao (Bảo)")
    print("     • phuc (Nguyễn Hoàng Phúc)")
    print("=" * 68)

    ensure_admin_and_port()

    # Khởi động máy chủ Django
    cmd = [sys.executable, "manage.py", "runserver", "0.0.0.0:8000"]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n[*] Đã dừng máy chủ Zalo Web.")

if __name__ == '__main__':
    main()

