#!/usr/bin/env python3
"""
view_db.py - Xem trực quan dữ liệu trong Cơ Sở Dữ Liệu (PostgreSQL / SQLite).
Hỗ trợ kiểm tra nhanh các bảng: Users, UserProfiles, Conversations, Messages.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalo_project.settings')
django.setup()

from django.conf import settings
from django.contrib.auth.models import User
from chat.models import UserProfile, Conversation, ConversationMember, Message, Task

def show_database_info():
    db_config = settings.DATABASES['default']
    engine = db_config['ENGINE'].split('.')[-1]

    print("=" * 72)
    print("📊 THÔNG TIN CƠ SỞ DỮ LIỆU ĐANG KẾT NỐI")
    print("=" * 72)
    print(f"  • Loại CSDL (Engine): {engine.upper()}")
    if 'postgresql' in engine.lower():
        print(f"  • Database Name:     {db_config.get('NAME')}")
        print(f"  • User:              {db_config.get('USER')}")
        print(f"  • Host:Port:         {db_config.get('HOST')}:{db_config.get('PORT')}")
    else:
        print(f"  • File CSDL SQLite:  {db_config.get('NAME')}")
    print("=" * 72)

    # 1. Danh sách Users & Profiles
    print("\n👥 1. DANH SÁCH TÀI KHOẢN (auth_user & chat_userprofile):")
    print(f"  {'ID':<4} | {'Username':<12} | {'Tên hiển thị':<24} | {'Số ĐT':<12} | {'Admin':<6}")
    print("  " + "-" * 66)
    for u in User.objects.all().order_by('id'):
        p = getattr(u, 'profile', None)
        disp = p.get_display_name() if p else u.username
        phone = p.phone if p else ''
        is_adm = "✓" if u.is_superuser else ""
        print(f"  {u.id:<4} | {u.username:<12} | {disp:<24} | {phone:<12} | {is_adm:<6}")

    # 2. Danh sách Hội thoại (Conversations)
    print("\n💬 2. DANH SÁCH CUỘC HỘI THOẠI (chat_conversation):")
    print(f"  {'ID':<4} | {'Tên hội thoại':<30} | {'Loại':<12} | {'Số TV':<6}")
    print("  " + "-" * 58)
    for c in Conversation.objects.all().order_by('id'):
        ctype = "Nhóm" if c.is_group else "1-1 / Cloud"
        cnt = c.memberships.count()
        print(f"  {c.id:<4} | {c.name or 'Hội thoại 1-1':<30} | {ctype:<12} | {cnt:<6}")

    # 3. Thống kê tin nhắn
    total_msgs = Message.objects.count()
    print(f"\n📩 3. TỔNG SỐ TIN NHẮN (chat_message): {total_msgs} tin nhắn đã lưu.")

    # 5 tin nhắn gần nhất
    print("  Trích đoạn 5 tin nhắn gần nhất:")
    for m in Message.objects.order_by('-created_at')[:5]:
        sender = m.sender.username if m.sender else "System"
        print(f"    • [{m.created_at.strftime('%H:%M:%S')}] {sender} ({m.message_type}): {m.content[:45]}")

    # 4. Thống kê việc cần làm (Tasks)
    total_tasks = Task.objects.count()
    done_tasks = Task.objects.filter(done=True).count()
    print(f"\n📋 4. VIỆC CẦN LÀM / TO-DO (chat_task): {total_tasks} công việc ({done_tasks} đã xong, {total_tasks - done_tasks} đang làm).")
    for t in Task.objects.order_by('done', '-created_at')[:4]:
        status_sym = "✅" if t.done else "⏳"
        print(f"    • {status_sym} [{t.priority.upper()}] {t.user.username}: {t.title[:45]} (Hạn: {t.due})")

    print("\n" + "=" * 72)
    print("💡 Mẹo: Bạn cũng có thể xem và chỉnh sửa toàn bộ dữ liệu trên giao diện Web:")
    print("👉 Mở trình duyệt: http://127.0.0.1:8000/admin/ (admin / admin123)")
    print("=" * 72)

if __name__ == '__main__':
    show_database_info()
