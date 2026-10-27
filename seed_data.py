import os
import sys
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalo_project.settings')
django.setup()

from django.contrib.auth.models import User
from chat.models import UserProfile, Conversation, ConversationMember, Message

def seed():
    print("[*] Bắt đầu khởi tạo tài khoản và danh bạ hệ thống Zalo Web...")

    # 1. Tạo các Users & Profiles (phục vụ Danh bạ và Đăng nhập)
    users_data = [
        {'username': 'quan', 'name': 'Phạm Huỳnh Quân', 'phone': '0901234567', 'bio': 'Lập trình mạng VKU 🚀', 'gender': 'nam'},
        {'username': 'camnt', 'name': 'Cô Camnt', 'phone': '0912345678', 'bio': 'Giảng viên Lập trình Mạng', 'gender': 'nu'},
        {'username': 'phuc', 'name': 'Nguyễn Hoàng Phúc', 'phone': '0923456789', 'bio': 'CG Developer', 'gender': 'nam'},
        {'username': 'bao', 'name': 'Bảo', 'phone': '0934567890', 'bio': 'Backend Python & Java', 'gender': 'nam'},
        {'username': 'baominh', 'name': 'Bảo Minhh', 'phone': '0945678901', 'bio': 'Ready to code', 'gender': 'nam'},
        {'username': 'loi', 'name': 'Nguyễn Văn Lợi', 'phone': '0956789012', 'bio': 'Lớp 24SE3 VKU', 'gender': 'nam'},
        {'username': 'minhlam', 'name': 'Minh Lâm', 'phone': '0967890123', 'bio': 'KOI dn', 'gender': 'nam'},
        {'username': 'thang', 'name': 'Trần Thắng', 'phone': '0978901234', 'bio': 'Photographer & Dev', 'gender': 'nam'},
        {'username': 'tri', 'name': 'trần văn tri', 'phone': '0989012345', 'bio': 'Sinh viên VKU', 'gender': 'nam'},
        {'username': 'nga', 'name': 'Dương Thị Mai Nga', 'phone': '0990123456', 'bio': 'TTTT HK1', 'gender': 'nu'},
    ]

    user_objs = {}
    for udata in users_data:
        user, created = User.objects.get_or_create(username=udata['username'])
        if created:
            user.set_password('123456')
            user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.display_name = udata['name']
        profile.phone = udata['phone']
        profile.bio = udata['bio']
        profile.gender = udata['gender']
        profile.is_online = True
        profile.save()
        user_objs[udata['username']] = user
        print(f"  + User: {udata['name']} (@{udata['username']}) - Mật khẩu: 123456")

    # Tạo hoặc đồng bộ Superuser Admin
    admin_user, _ = User.objects.get_or_create(username='admin', defaults={'email': 'admin@vku.udn.vn'})
    admin_user.set_password('admin123')
    admin_user.is_superuser = True
    admin_user.is_staff = True
    admin_user.save()
    admin_profile, _ = UserProfile.objects.get_or_create(user=admin_user)
    admin_profile.display_name = 'Quản trị viên (Admin)'
    admin_profile.bio = 'Hệ thống Quản trị Zalo Web VKU'
    admin_profile.save()
    print("  + Superuser: Quản trị viên (@admin) - Mật khẩu: admin123")

    quan = user_objs['quan']

    # 2. Tạo 'Cloud của tôi' cho quan nếu chưa có
    cloud_conv = Conversation.objects.filter(is_group=False, memberships__user=quan, name='Cloud của tôi').first()
    if not cloud_conv:
        cloud_conv = Conversation.objects.create(name='Cloud của tôi', is_group=False, created_by=quan)
        ConversationMember.objects.create(conversation=cloud_conv, user=quan, role='admin')
        Message.objects.create(
            conversation=cloud_conv,
            sender=quan,
            message_type='text',
            content='Chào mừng đến với Cloud của tôi! Nơi lưu trữ an toàn các văn bản, tệp tin và đoạn code của riêng bạn.'
        )
        print("  + Tạo hội thoại Cloud của tôi cho @quan")

    print("[*] Đã khởi tạo hoàn tất tài khoản sạch! Các cuộc trò chuyện sẽ tự động xuất hiện khi người dùng thực tế nhắn tin qua lại.")

if __name__ == '__main__':
    seed()
