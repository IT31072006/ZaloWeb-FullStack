from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import urllib.parse


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ('nam', 'Nam'),
        ('nu', 'Nữ'),
        ('khac', 'Khác'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=150, blank=True, verbose_name="Tên hiển thị")
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name="Ảnh đại diện")
    cover_image = models.ImageField(upload_to='covers/', null=True, blank=True, verbose_name="Ảnh bìa")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Số điện thoại")
    bio = models.CharField(max_length=255, blank=True, default="Xin chào, tôi đang sử dụng Zalo!", verbose_name="Tiểu sử / Trạng thái")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='nam', verbose_name="Giới tính")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Ngày sinh")
    is_online = models.BooleanField(default=True, verbose_name="Đang trực tuyến")
    last_seen = models.DateTimeField(auto_now=True, verbose_name="Lần cuối hoạt động")

    def get_display_name(self):
        if self.display_name and self.display_name.strip():
            return self.display_name.strip()
        full_name = f"{self.user.first_name} {self.user.last_name}".strip()
        if full_name:
            return full_name
        return self.user.username

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        # Fallback to SVG / UI Avatar with user initials
        name = self.get_display_name()
        encoded = urllib.parse.quote(name)
        return f"https://ui-avatars.com/api/?name={encoded}&background=0068ff&color=ffffff&bold=true&size=128"

    def __str__(self):
        return self.get_display_name()


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance, display_name=instance.first_name or instance.username)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()


class Conversation(models.Model):
    name = models.CharField(max_length=255, blank=True, verbose_name="Tên hội thoại")
    is_group = models.BooleanField(default=False, verbose_name="Là nhóm chat")
    avatar = models.ImageField(upload_to='group_avatars/', null=True, blank=True, verbose_name="Ảnh nhóm")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_conversations')
    pinned_message = models.ForeignKey('Message', on_delete=models.SET_NULL, null=True, blank=True, related_name='pinned_in_conversations', verbose_name="Tin nhắn đã ghim")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def get_other_member(self, user):
        """Dành cho chat 1-1: lấy thành viên đối thoại còn lại."""
        if self.is_group:
            return None
        membership = self.memberships.exclude(user=user).select_related('user__profile').first()
        return membership.user if membership else None

    def get_title_for_user(self, user):
        if self.name == "Cloud của tôi":
            return "Cloud của tôi"
        if self.is_group:
            return self.name or "Nhóm chưa đặt tên"
        other = self.get_other_member(user)
        if other and hasattr(other, 'profile'):
            return other.profile.get_display_name()
        elif other:
            return other.username
        return self.name or "Hội thoại"

    def get_avatar_for_user(self, user):
        if self.name == "Cloud của tôi":
            return "https://ui-avatars.com/api/?name=Cloud&background=0068ff&color=ffffff&bold=true"
        if self.is_group:
            if self.avatar and hasattr(self.avatar, 'url'):
                return self.avatar.url
            encoded = urllib.parse.quote(self.name or "Group")
            return f"https://ui-avatars.com/api/?name={encoded}&background=0288d1&color=ffffff&bold=true&size=128"
        other = self.get_other_member(user)
        if other and hasattr(other, 'profile'):
            return other.profile.get_avatar_url()
        return f"https://ui-avatars.com/api/?name={urllib.parse.quote(self.name or 'Chat')}&background=0068ff&color=ffffff"

    def get_member_count(self):
        return self.memberships.count()

    def get_last_message(self):
        return self.messages.order_by('-created_at').first()

    def get_unread_count_for_user(self, user):
        membership = self.memberships.filter(user=user).first()
        if not membership:
            return 0
        return self.messages.filter(id__gt=membership.last_read_message_id).exclude(sender=user).count()

    def __str__(self):
        return self.name or f"Conversation #{self.id}"


class ConversationMember(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Trưởng nhóm'),
        ('member', 'Thành viên'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_message_id = models.IntegerField(default=0)
    is_pinned = models.BooleanField(default=False, verbose_name="Đã ghim")
    pinned_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm ghim")
    is_muted = models.BooleanField(default=False, verbose_name="Tắt thông báo")
    is_priority = models.BooleanField(default=True, verbose_name="Hội thoại ưu tiên")

    class Meta:
        unique_together = ('conversation', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.conversation.name}"


class Message(models.Model):
    MESSAGE_TYPES = [
        ('text', 'Văn bản'),
        ('image', 'Hình ảnh'),
        ('audio', 'Tin nhắn thoại'),
        ('file', 'Tệp tin'),
        ('code', 'Đoạn mã lập trình'),
        ('call', 'Lịch sử cuộc gọi'),
        ('system', 'Hệ thống'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    content = models.TextField(blank=True, verbose_name="Nội dung")
    attachment = models.FileField(upload_to='attachments/%Y/%m/', null=True, blank=True, verbose_name="Tệp đính kèm / Ảnh / Audio")
    attachment_name = models.CharField(max_length=255, blank=True, verbose_name="Tên file gốc")
    attachment_size = models.CharField(max_length=50, blank=True, verbose_name="Kích thước file")
    code_language = models.CharField(max_length=50, blank=True, default='java', verbose_name="Ngôn ngữ code")
    call_duration = models.IntegerField(default=0, verbose_name="Thời lượng cuộc gọi (giây)")
    call_status = models.CharField(max_length=30, blank=True, default='completed', verbose_name="Trạng thái cuộc gọi (completed/missed/rejected)")
    is_recalled = models.BooleanField(default=False, verbose_name="Đã thu hồi")
    deleted_by = models.ManyToManyField(User, blank=True, related_name='deleted_messages', verbose_name="Người đã xóa tin nhắn")
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies', verbose_name="Trả lời tin nhắn")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        sender_name = self.sender.username if self.sender else "System"
        return f"[{self.message_type}] {sender_name}: {self.content[:30]}"


class MessageReaction(models.Model):
    REACTION_CHOICES = [
        ('❤️', 'Tim'),
        ('👍', 'Thích'),
        ('😂', 'Haha'),
        ('😮', 'Wow'),
        ('😢', 'Buồn'),
        ('😡', 'Phẫn nộ'),
    ]

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_reactions')
    emoji = models.CharField(max_length=10, choices=REACTION_CHOICES, verbose_name="Biểu tượng cảm xúc")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')

    def __str__(self):
        return f"{self.user.username} {self.emoji} Msg #{self.message_id}"



class Task(models.Model):
    PRIORITY_CHOICES = [
        ('high', 'Khẩn cấp / Ưu tiên cao'),
        ('medium', 'Trung bình'),
        ('normal', 'Bình thường'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks', verbose_name="Người thực hiện")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', verbose_name="Hội thoại liên quan")
    title = models.CharField(max_length=255, verbose_name="Nội dung công việc")
    due = models.CharField(max_length=100, default='Sắp tới', verbose_name="Hạn hoàn thành")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', verbose_name="Độ ưu tiên")
    done = models.BooleanField(default=False, verbose_name="Đã hoàn thành")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['done', '-created_at']

    def __str__(self):
        return f"{self.title} ({'Đã xong' if self.done else 'Đang làm'})"

