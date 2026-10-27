from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Conversation, ConversationMember, Message
from django.utils import timezone
import datetime


def format_time_ago(dt):
    if not dt:
        return ""
    now = timezone.now()
    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "Vừa xong"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins} phút"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} giờ"
    elif seconds < 86400 * 2:
        return "Hôm qua"
    elif seconds < 86400 * 7:
        days = seconds // 86400
        return f"{days} ngày"
    else:
        return dt.strftime("%d/%m")


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    avatar_url = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id', 'username', 'email', 'display_name', 'avatar_url',
            'phone', 'bio', 'gender', 'date_of_birth', 'is_online', 'last_seen'
        ]

    def get_avatar_url(self, obj):
        return obj.get_avatar_url()

    def get_display_name(self, obj):
        return obj.get_display_name()


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_avatar = serializers.SerializerMethodField()
    sender_id = serializers.SerializerMethodField()
    is_me = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()
    formatted_time = serializers.SerializerMethodField()
    formatted_duration = serializers.SerializerMethodField()
    reply_to_details = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation_id', 'sender_id', 'sender_name', 'sender_avatar',
            'is_me', 'message_type', 'content', 'attachment_url', 'attachment_name',
            'attachment_size', 'code_language', 'call_duration', 'call_status',
            'formatted_duration', 'created_at', 'formatted_time',
            'is_recalled', 'reply_to_details', 'reactions'
        ]

    def get_formatted_duration(self, obj):
        if obj.message_type != 'call':
            return ""
        dur = obj.call_duration or 0
        mins = dur // 60
        secs = dur % 60
        return f"{mins:02d}:{secs:02d}"

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.is_recalled:
            ret['content'] = 'Tin nhắn đã được thu hồi'
            ret['attachment_url'] = None
        return ret

    def get_sender_id(self, obj):
        return obj.sender.id if obj.sender else None

    def get_sender_name(self, obj):
        if not obj.sender:
            return "Hệ thống"
        if hasattr(obj.sender, 'profile'):
            return obj.sender.profile.get_display_name()
        return obj.sender.username

    def get_sender_avatar(self, obj):
        if not obj.sender:
            return "https://ui-avatars.com/api/?name=Zalo&background=0068ff&color=ffffff"
        if hasattr(obj.sender, 'profile'):
            return obj.sender.profile.get_avatar_url()
        return f"https://ui-avatars.com/api/?name={obj.sender.username}&background=0068ff&color=ffffff"

    def get_is_me(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and obj.sender:
            return obj.sender_id == request.user.id
        return False

    def get_attachment_url(self, obj):
        if obj.is_recalled:
            return None
        if obj.attachment and hasattr(obj.attachment, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.attachment.url)
            return obj.attachment.url
        return None

    def get_formatted_time(self, obj):
        local_time = timezone.localtime(obj.created_at)
        return local_time.strftime("%H:%M")

    def get_reply_to_details(self, obj):
        if not obj.reply_to:
            return None
        r = obj.reply_to
        sender_name = "Hệ thống"
        if r.sender:
            sender_name = r.sender.profile.get_display_name() if hasattr(r.sender, 'profile') else r.sender.username
        snippet = r.content
        if r.is_recalled:
            snippet = "Tin nhắn đã được thu hồi"
        elif r.message_type == 'image':
            snippet = "[Hình ảnh]"
        elif r.message_type == 'audio':
            snippet = "[Tin nhắn thoại]"
        elif r.message_type == 'file':
            snippet = f"[Tệp tin] {r.attachment_name or ''}"
        elif r.message_type == 'code':
            snippet = f"[Đoạn mã {r.code_language.upper()}]"

        return {
            'id': r.id,
            'sender_name': sender_name,
            'content': snippet,
            'message_type': r.message_type
        }

    def get_reactions(self, obj):
        request = self.context.get('request')
        current_user = request.user if request and request.user.is_authenticated else None

        reactions_qs = getattr(obj, '_prefetched_reactions', None)
        if reactions_qs is None:
            reactions_qs = obj.reactions.select_related('user__profile').all()

        counts = {}
        for r in reactions_qs:
            user_name = r.user.profile.get_display_name() if hasattr(r.user, 'profile') else r.user.username
            if r.emoji not in counts:
                counts[r.emoji] = {
                    'emoji': r.emoji,
                    'count': 0,
                    'users': [],
                    'has_reacted': False
                }
            counts[r.emoji]['count'] += 1
            counts[r.emoji]['users'].append(user_name)
            if current_user and r.user_id == current_user.id:
                counts[r.emoji]['has_reacted'] = True

        return list(counts.values())



class ConversationListSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    time_label = serializers.SerializerMethodField()
    is_pinned = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    is_priority = serializers.SerializerMethodField()
    pinned_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'avatar_url', 'is_group', 'member_count',
            'last_message', 'unread_count', 'updated_at', 'time_label',
            'is_pinned', 'is_muted', 'is_priority', 'pinned_message'
        ]

    def _get_user_membership(self, obj):
        user = self.context.get('user')
        if not user or not user.is_authenticated:
            return None
        cache_attr = f'_membership_user_{user.id}'
        if not hasattr(obj, cache_attr):
            m = obj.memberships.filter(user=user).first()
            setattr(obj, cache_attr, m)
        return getattr(obj, cache_attr)

    def get_is_pinned(self, obj):
        m = self._get_user_membership(obj)
        return m.is_pinned if m else False

    def get_is_muted(self, obj):
        m = self._get_user_membership(obj)
        return m.is_muted if m else False

    def get_is_priority(self, obj):
        m = self._get_user_membership(obj)
        return m.is_priority if m else True

    def get_pinned_message(self, obj):
        if not obj.pinned_message:
            return None
        pm = obj.pinned_message
        sender_name = "Hệ thống"
        if pm.sender:
            sender_name = pm.sender.profile.get_display_name() if hasattr(pm.sender, 'profile') else pm.sender.username
        snippet = pm.content
        if pm.is_recalled:
            snippet = "Tin nhắn đã được thu hồi"
        elif pm.message_type == 'image':
            snippet = "[Hình ảnh]"
        elif pm.message_type == 'audio':
            snippet = "[Tin nhắn thoại]"
        elif pm.message_type == 'file':
            snippet = f"[Tệp tin] {pm.attachment_name or ''}"
        elif pm.message_type == 'code':
            snippet = f"[Đoạn mã {pm.code_language.upper()}]"
        return {
            'id': pm.id,
            'sender_name': sender_name,
            'snippet': snippet,
            'type': pm.message_type
        }


    def get_title(self, obj):
        user = self.context.get('user')
        return obj.get_title_for_user(user)

    def get_avatar_url(self, obj):
        user = self.context.get('user')
        return obj.get_avatar_for_user(user)

    def get_member_count(self, obj):
        return obj.get_member_count()

    def get_unread_count(self, obj):
        user = self.context.get('user')
        return obj.get_unread_count_for_user(user)

    def get_last_message(self, obj):
        msg = obj.get_last_message()
        if not msg:
            return None
        user = self.context.get('user')
        is_me = user and msg.sender_id == user.id

        sender_prefix = "Bạn: " if is_me else (f"{msg.sender.profile.get_display_name()}: " if msg.sender and hasattr(msg.sender, 'profile') else "")

        snippet = msg.content
        if msg.message_type == 'image':
            snippet = f"{sender_prefix}[Hình ảnh]"
        elif msg.message_type == 'audio':
            snippet = f"{sender_prefix}[Tin nhắn thoại]"
        elif msg.message_type == 'file':
            snippet = f"{sender_prefix}[Tệp tin] {msg.attachment_name or ''}"
        elif msg.message_type == 'code':
            snippet = f"{sender_prefix}[Đoạn mã {msg.code_language.upper()}]"
        elif msg.message_type == 'call':
            icon = "📹" if msg.code_language == 'video' else "📞"
            snippet = f"{icon} {msg.content}"
        else:
            snippet = f"{sender_prefix}{msg.content}"

        return {
            'id': msg.id,
            'type': msg.message_type,
            'preview': snippet,
            'time_ago': format_time_ago(msg.created_at),
            'created_at': msg.created_at.isoformat(),
        }

    def get_time_label(self, obj):
        msg = obj.get_last_message()
        if msg:
            return format_time_ago(msg.created_at)
        return format_time_ago(obj.updated_at)
