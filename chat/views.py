import re
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q, Count, Subquery, OuterRef
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import UserProfile, Conversation, ConversationMember, Message, Task, MessageReaction
from .serializers import UserProfileSerializer, MessageSerializer, ConversationListSerializer


@ensure_csrf_cookie
def index_view(request):
    """Giao diện chính Zalo Web."""
    return render(request, 'index.html', {
        'user': request.user,
        'is_authenticated': request.user.is_authenticated
    })


def auth_view(request):
    """Trang Đăng ký / Đăng nhập chuyên biệt."""
    if request.user.is_authenticated:
        return redirect('/')
    return render(request, 'auth.html')


# ==============================================================================
# AUTHENTICATION APIs
# ==============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def api_register(request):
    """Đăng ký tài khoản mới kèm họ tên, số điện thoại và tải ảnh đại diện."""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()
    display_name = request.data.get('display_name', '').strip() or username
    phone = request.data.get('phone', '').strip()
    bio = request.data.get('bio', '').strip() or "Xin chào, tôi đang sử dụng Zalo!"
    gender = request.data.get('gender', 'nam')

    if not username or not password:
        return Response({'error': 'Vui lòng nhập tên đăng nhập và mật khẩu!'}, status=status.HTTP_400_BAD_REQUEST)

    if len(password) < 4:
        return Response({'error': 'Mật khẩu phải có ít nhất 4 ký tự!'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username__iexact=username).exists():
        return Response({'error': 'Tên đăng nhập này đã được sử dụng! Vui lòng chọn tên khác.'}, status=status.HTTP_400_BAD_REQUEST)

    # Tạo User
    user = User.objects.create_user(username=username, password=password)
    
    # Cập nhật hoặc tạo Profile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.display_name = display_name
    profile.phone = phone
    profile.bio = bio
    profile.gender = gender
    profile.is_online = True

    if 'avatar' in request.FILES:
        profile.avatar = request.FILES['avatar']

    profile.save()

    # Tự động đăng nhập
    login(request, user)

    serializer = UserProfileSerializer(profile)
    return Response({
        'message': 'Đăng ký thành công!',
        'user': serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """Đăng nhập tài khoản bằng Username hoặc Số điện thoại."""
    username_or_phone = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not username_or_phone or not password:
        return Response({'error': 'Vui lòng nhập tài khoản và mật khẩu!'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username_or_phone, password=password)
    if not user:
        # Thử tìm theo số điện thoại
        profile = UserProfile.objects.filter(phone=username_or_phone).first()
        if profile:
            user = authenticate(request, username=profile.user.username, password=password)

    if user is not None:
        login(request, user)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_online = True
        profile.save(update_fields=['is_online', 'last_seen'])

        serializer = UserProfileSerializer(profile)
        return Response({
            'message': 'Đăng nhập thành công!',
            'user': serializer.data
        })
    else:
        return Response({'error': 'Sai tên đăng nhập hoặc mật khẩu!'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST', 'GET'])
def api_logout(request):
    """Đăng xuất tài khoản."""
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile'):
            request.user.profile.is_online = False
            request.user.profile.save(update_fields=['is_online', 'last_seen'])
        logout(request)
    return Response({'message': 'Đã đăng xuất thành công!'})


@api_view(['GET'])
def api_me(request):
    """Lấy thông tin tài khoản hiện tại."""
    if not request.user.is_authenticated:
        return Response({'authenticated': False, 'user': None})

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    serializer = UserProfileSerializer(profile)
    return Response({
        'authenticated': True,
        'user': serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def api_update_profile(request):
    """Cập nhật thông tin cá nhân và tải ảnh đại diện / ảnh bìa mới."""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if 'display_name' in request.data:
        profile.display_name = request.data.get('display_name', '').strip()
    if 'bio' in request.data:
        profile.bio = request.data.get('bio', '').strip()
    if 'phone' in request.data:
        profile.phone = request.data.get('phone', '').strip()
    if 'gender' in request.data:
        profile.gender = request.data.get('gender', 'nam')
    if 'date_of_birth' in request.data and request.data.get('date_of_birth'):
        profile.date_of_birth = request.data.get('date_of_birth')

    # Cập nhật Avatar
    if 'avatar' in request.FILES:
        profile.avatar = request.FILES['avatar']

    # Cập nhật Cover
    if 'cover_image' in request.FILES:
        profile.cover_image = request.FILES['cover_image']

    profile.save()

    serializer = UserProfileSerializer(profile)
    return Response({
        'message': 'Cập nhật hồ sơ thành công!',
        'user': serializer.data
    })


# ==============================================================================
# CONVERSATIONS & MESSAGING APIs
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_conversations(request):
    """
    Lấy danh sách các cuộc hội thoại của người dùng.
    Chỉ hiển thị:
    - Cuộc trò chuyện đã có tin nhắn được trao đổi (num_messages > 0)
    - Hoặc 'Cloud của tôi' (lưu trữ cá nhân)
    - Hoặc nhóm do người dùng tạo (is_group=True, created_by=user)
    """
    user = request.user
    query = request.GET.get('q', '').strip()

    # Chỉ hiển thị cuộc trò chuyện có tin nhắn thực tế hoặc là Cloud cá nhân
    pinned_subquery = ConversationMember.objects.filter(
        conversation=OuterRef('pk'), user=user
    ).values('is_pinned')[:1]

    conversations = Conversation.objects.filter(memberships__user=user).annotate(
        num_messages=Count('messages'),
        is_pinned_flag=Subquery(pinned_subquery)
    ).filter(
        Q(num_messages__gt=0) | Q(name='Cloud của tôi') | Q(is_group=True, created_by=user)
    ).distinct().order_by('-is_pinned_flag', '-updated_at')

    if query:
        conversations = conversations.filter(
            Q(name__icontains=query) |
            Q(memberships__user__username__icontains=query) |
            Q(memberships__user__profile__display_name__icontains=query)
        ).distinct()

    serializer = ConversationListSerializer(conversations, many=True, context={'user': user})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_conversation_detail(request, conversation_id):
    """Lấy thông tin chi tiết một cuộc hội thoại."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    
    # Lấy thông tin membership của user hiện tại
    membership = conversation.memberships.filter(user=user).first()

    # Lấy danh sách thành viên
    members = []
    for m in conversation.memberships.select_related('user__profile').all():
        profile = getattr(m.user, 'profile', None)
        members.append({
            'id': m.user.id,
            'username': m.user.username,
            'display_name': profile.get_display_name() if profile else m.user.username,
            'avatar_url': profile.get_avatar_url() if profile else None,
            'role': m.role,
            'is_online': profile.is_online if profile else False,
            'last_read_message_id': m.last_read_message_id
        })

    # Lấy media chia sẻ (hình ảnh & audio)
    media_messages = conversation.messages.filter(message_type__in=['image', 'audio']).order_by('-created_at')[:20]
    shared_media = []
    for m in media_messages:
        url = request.build_absolute_uri(m.attachment.url) if m.attachment and hasattr(m.attachment, 'url') else ''
        shared_media.append({
            'id': m.id,
            'type': m.message_type,
            'url': url,
            'name': m.attachment_name or m.content,
            'sender': m.sender.profile.get_display_name() if m.sender and hasattr(m.sender, 'profile') else 'System',
            'created_at': m.created_at.strftime("%d/%m")
        })

    # Lấy tệp tin chia sẻ
    file_messages = conversation.messages.filter(message_type='file').order_by('-created_at')[:20]
    shared_files = []
    for m in file_messages:
        url = request.build_absolute_uri(m.attachment.url) if m.attachment and hasattr(m.attachment, 'url') else ''
        shared_files.append({
            'id': m.id,
            'name': m.attachment_name or 'Tệp tin',
            'size': m.attachment_size or '0 B',
            'url': url,
            'sender': m.sender.profile.get_display_name() if m.sender and hasattr(m.sender, 'profile') else 'System',
            'created_at': m.created_at.strftime("%d/%m")
        })

    # Lấy thông tin tin nhắn ghim nếu có
    pinned_info = None
    if conversation.pinned_message:
        pm = conversation.pinned_message
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
        pinned_info = {
            'id': pm.id,
            'sender_name': sender_name,
            'snippet': snippet,
            'type': pm.message_type
        }

    return Response({
        'id': conversation.id,
        'title': conversation.get_title_for_user(user),
        'avatar_url': conversation.get_avatar_for_user(user),
        'is_group': conversation.is_group,
        'member_count': conversation.get_member_count(),
        'members': members,
        'shared_media': shared_media,
        'shared_files': shared_files,
        'created_at': conversation.created_at,
        'is_pinned': membership.is_pinned if membership else False,
        'is_muted': membership.is_muted if membership else False,
        'is_priority': membership.is_priority if membership else True,
        'my_role': membership.role if membership else 'member',
        'created_by_id': conversation.created_by_id,
        'pinned_message': pinned_info,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_messages(request, conversation_id):
    """Lấy danh sách tin nhắn trong một cuộc hội thoại và đánh dấu đã đọc."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)

    messages = conversation.messages.exclude(deleted_by=user).select_related(
        'sender__profile', 'reply_to__sender__profile'
    ).prefetch_related('reactions__user__profile').order_by('created_at')
    
    # Cập nhật last_read_message_id
    last_msg = messages.last()
    if last_msg:
        ConversationMember.objects.filter(conversation=conversation, user=user).update(last_read_message_id=last_msg.id)

    serializer = MessageSerializer(messages, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def api_send_message(request, conversation_id):
    """
    Gửi tin nhắn mới (Văn bản, Hình ảnh, Ghi âm audio, Tệp tin tài liệu, Đoạn code, Trả lời tin nhắn).
    """
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)

    message_type = request.data.get('message_type', 'text')
    content = request.data.get('content', '').strip()
    code_language = request.data.get('code_language', 'java')
    reply_to_id = request.data.get('reply_to_id')

    reply_to = None
    if reply_to_id:
        try:
            reply_to = Message.objects.filter(id=int(reply_to_id), conversation=conversation).first()
        except (ValueError, TypeError):
            reply_to = None

    attachment = None
    attachment_name = ''
    attachment_size = ''

    if 'attachment' in request.FILES:
        attachment = request.FILES['attachment']
        attachment_name = attachment.name
        size_bytes = attachment.size
        if size_bytes < 1024:
            attachment_size = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            attachment_size = f"{size_bytes / 1024:.1f} KB"
        else:
            attachment_size = f"{size_bytes / (1024 * 1024):.1f} MB"

    if not content and not attachment:
        return Response({'error': 'Nội dung tin nhắn hoặc tệp đính kèm không được để trống!'}, status=status.HTTP_400_BAD_REQUEST)

    msg = Message.objects.create(
        conversation=conversation,
        sender=user,
        message_type=message_type,
        content=content,
        attachment=attachment,
        attachment_name=attachment_name,
        attachment_size=attachment_size,
        code_language=code_language,
        reply_to=reply_to
    )

    # Cập nhật thời gian hội thoại
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=['updated_at'])

    # Cập nhật đọc cho người gửi
    ConversationMember.objects.filter(conversation=conversation, user=user).update(last_read_message_id=msg.id)

    serializer = MessageSerializer(msg, context={'request': request})

    # Broadcast qua WebSocket (Channels Layer) tới tất cả client đang mở cuộc trò chuyện (0ms)
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_message',
                    'message': serializer.data
                }
            )
    except Exception:
        pass

    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_sync_messages(request, conversation_id):
    """Đồng bộ tin nhắn mới kể từ after_id phục vụ live-polling thời gian thực."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)

    after_id = request.GET.get('after_id', 0)
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    new_messages = conversation.messages.filter(id__gt=after_id).exclude(deleted_by=user).select_related(
        'sender__profile', 'reply_to__sender__profile'
    ).prefetch_related('reactions__user__profile').order_by('created_at')

    # Đánh dấu đã đọc
    last_msg = new_messages.last()
    if last_msg:
        ConversationMember.objects.filter(conversation=conversation, user=user).update(last_read_message_id=last_msg.id)

    serializer = MessageSerializer(new_messages, many=True, context={'request': request})
    return Response(serializer.data)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_search_users(request):
    """Tìm kiếm người dùng để nhắn tin 1-1 hoặc thêm vào nhóm."""
    query = request.GET.get('q', '').strip()
    if not query:
        users = User.objects.exclude(id=request.user.id)[:20]
    else:
        digits_only = re.sub(r'\D', '', query)
        q_filter = (
            models.Q(username__icontains=query) |
            models.Q(profile__display_name__icontains=query) |
            models.Q(profile__phone__icontains=query)
        )
        if digits_only:
            normalized = digits_only
            if digits_only.startswith('84') and len(digits_only) >= 10:
                normalized = '0' + digits_only[2:]
            suffix = normalized[-9:] if len(normalized) >= 9 else normalized
            q_filter |= models.Q(profile__phone__icontains=normalized)
            q_filter |= models.Q(profile__phone__endswith=suffix)

        users = User.objects.exclude(id=request.user.id).filter(q_filter)[:20]

    result = []
    for u in users:
        profile = getattr(u, 'profile', None)
        result.append({
            'id': u.id,
            'username': u.username,
            'display_name': profile.get_display_name() if profile else u.username,
            'avatar_url': profile.get_avatar_url() if profile else None,
            'phone': profile.phone if profile else '',
            'bio': profile.bio if profile else '',
            'is_online': profile.is_online if profile else False
        })
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_search_by_phone(request):
    """Tìm kiếm bạn mới chính xác bằng số điện thoại (Chuẩn Zalo Web)."""
    phone_raw = request.GET.get('phone', '').strip()
    if not phone_raw:
        return Response({
            'status': 'error',
            'message': 'Vui lòng nhập số điện thoại cần tìm.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Chuẩn hóa số điện thoại: loại bỏ ký tự không phải số
    digits_only = re.sub(r'\D', '', phone_raw)
    normalized = digits_only
    if digits_only.startswith('84') and len(digits_only) >= 10:
        normalized = '0' + digits_only[2:]

    # Kiểm tra xem có phải số điện thoại của chính mình không
    my_profile = getattr(request.user, 'profile', None)
    my_digits = re.sub(r'\D', '', my_profile.phone) if my_profile and my_profile.phone else ''
    if my_digits and (my_digits == normalized or my_digits == digits_only):
        return Response({
            'status': 'self',
            'message': 'Đây là số điện thoại của chính bạn.',
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'display_name': my_profile.get_display_name() if my_profile else request.user.username,
                'avatar_url': my_profile.get_avatar_url() if my_profile else None,
                'phone': my_profile.phone if my_profile else '',
                'bio': my_profile.bio if my_profile else '',
                'is_online': True
            }
        })

    # Tìm user theo số điện thoại
    suffix = normalized[-9:] if len(normalized) >= 9 else normalized
    target_user = User.objects.filter(
        models.Q(profile__phone__iexact=normalized) |
        models.Q(profile__phone__iexact=phone_raw) |
        models.Q(profile__phone__endswith=suffix)
    ).exclude(id=request.user.id).select_related('profile').first()

    if not target_user:
        return Response({
            'status': 'not_found',
            'message': f'Không tìm thấy người dùng với số điện thoại "{phone_raw}".'
        }, status=status.HTTP_404_NOT_FOUND)

    p = getattr(target_user, 'profile', None)
    existing_conv = Conversation.objects.filter(
        is_group=False,
        memberships__user=request.user
    ).filter(
        memberships__user=target_user
    ).first()

    return Response({
        'status': 'found',
        'user': {
            'id': target_user.id,
            'username': target_user.username,
            'display_name': p.get_display_name() if p else target_user.username,
            'avatar_url': p.get_avatar_url() if p else None,
            'phone': p.phone if p else '',
            'bio': p.bio if p else '',
            'gender': p.get_gender_display() if p and hasattr(p, 'get_gender_display') else 'Nam',
            'is_online': p.is_online if p else False,
            'has_conversation': existing_conv is not None,
            'conversation_id': existing_conv.id if existing_conv else None
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_conversation(request):
    """Tạo hội thoại 1-1 hoặc nhóm mới."""
    user = request.user
    is_group = request.data.get('is_group', False)
    target_user_id = request.data.get('user_id')
    group_name = (request.data.get('name') or request.data.get('title') or '').strip()
    member_ids = request.data.get('members') or request.data.get('member_ids') or []

    if not is_group and target_user_id:
        target_user = get_object_or_404(User, id=target_user_id)
        # Kiểm tra xem đã có hội thoại 1-1 giữa 2 người chưa
        existing = Conversation.objects.filter(is_group=False, memberships__user=user).filter(memberships__user=target_user).first()
        if existing:
            return Response({'id': existing.id, 'title': existing.get_title_for_user(user)})

        # Tạo mới 1-1
        conv = Conversation.objects.create(is_group=False, created_by=user)
        ConversationMember.objects.create(conversation=conv, user=user)
        ConversationMember.objects.create(conversation=conv, user=target_user)
        return Response({'id': conv.id, 'title': conv.get_title_for_user(user)}, status=status.HTTP_201_CREATED)

    elif is_group:
        if not group_name:
            return Response({'error': 'Vui lòng nhập tên nhóm!'}, status=status.HTTP_400_BAD_REQUEST)

        conv = Conversation.objects.create(name=group_name, is_group=True, created_by=user)
        ConversationMember.objects.create(conversation=conv, user=user, role='admin')

        if isinstance(member_ids, list):
            for mid in member_ids:
                if mid != user.id:
                    u = User.objects.filter(id=mid).first()
                    if u:
                        ConversationMember.objects.create(conversation=conv, user=u, role='member')

        return Response({'id': conv.id, 'title': conv.name}, status=status.HTTP_201_CREATED)

    return Response({'error': 'Yêu cầu không hợp lệ!'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_cloud(request):
    """Lấy hoặc tạo hội thoại 'Cloud của tôi' dành cho lưu trữ cá nhân."""
    user = request.user
    cloud_conv = Conversation.objects.filter(is_group=False, memberships__user=user, name='Cloud của tôi').first()
    if not cloud_conv:
        cloud_conv = Conversation.objects.create(name='Cloud của tôi', is_group=False, created_by=user)
        ConversationMember.objects.create(conversation=cloud_conv, user=user, role='admin')
        # Thêm tin nhắn chào mừng mặc định
        Message.objects.create(
            conversation=cloud_conv,
            sender=user,
            message_type='text',
            content='Chào mừng đến với Cloud của tôi! Nơi lưu trữ an toàn các văn bản, tệp tin và đoạn code của riêng bạn.'
        )

    # Tính toán dung lượng lưu trữ Cloud thực tế
    total_bytes = 0
    for m in cloud_conv.messages.all():
        if m.attachment:
            try:
                total_bytes += m.attachment.size
            except Exception:
                pass
        if m.content:
            total_bytes += len(m.content.encode('utf-8'))

    storage_mb = round(total_bytes / (1024 * 1024), 2)
    storage_percent = round((storage_mb / 1024.0) * 100, 1)

    return Response({
        'id': cloud_conv.id,
        'title': 'Cloud của tôi',
        'is_cloud': True,
        'avatar_url': cloud_conv.get_avatar_for_user(user),
        'storage_used_bytes': total_bytes,
        'storage_used_mb': storage_mb,
        'storage_limit_mb': 1024,
        'storage_percent': max(storage_percent, 0.1) if total_bytes > 0 else 0
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_contacts(request):
    """Lấy danh bạ người dùng và danh sách các nhóm đã tham gia."""
    user = request.user
    users = User.objects.exclude(id=user.id).select_related('profile').order_by('profile__display_name', 'username')
    contacts = []
    for u in users:
        p = getattr(u, 'profile', None)
        contacts.append({
            'id': u.id,
            'username': u.username,
            'display_name': p.get_display_name() if p else u.username,
            'avatar_url': p.get_avatar_url() if p else None,
            'phone': p.phone if p else '',
            'bio': p.bio if p else '',
            'is_online': p.is_online if p else False,
        })

    groups = Conversation.objects.filter(is_group=True, memberships__user=user).order_by('name')
    group_list = []
    for g in groups:
        group_list.append({
            'id': g.id,
            'name': g.name,
            'avatar_url': g.get_avatar_for_user(user),
            'member_count': g.get_member_count(),
        })

    return Response({
        'contacts': contacts,
        'groups': group_list
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_tasks(request):
    """Quản lý danh sách việc cần làm / To-do & nhắc hẹn lưu bền vững trong CSDL (Task model)."""
    user = request.user

    # Khởi tạo công việc mẫu nếu người dùng chưa có công việc nào trong database
    if not Task.objects.filter(user=user).exists():
        Task.objects.create(user=user, title='Hoàn thành bài tập lớn Lập trình Mạng: Zalo Web Full-Stack', due='23:59 Hôm nay', priority='high', done=False)
        Task.objects.create(user=user, title='Ôn tập kiến thức Socket TCP/IP và UDP Multicast (Lab 6)', due='Ngày mai', priority='medium', done=False)
        Task.objects.create(user=user, title='Nộp báo cáo giữa kỳ môn LTM cho cô Camnt', due='25/10/2026', priority='high', done=False)
        Task.objects.create(user=user, title='Chuẩn bị slide thuyết trình demo ứng dụng', due='Tuần tới', priority='normal', done=True)

    if request.method == 'POST':
        action = request.data.get('action')
        if action == 'toggle':
            task_id = request.data.get('id')
            task = Task.objects.filter(id=task_id, user=user).first()
            if task:
                task.done = not task.done
                task.save(update_fields=['done', 'updated_at'])
        elif action == 'create':
            title = request.data.get('title', '').strip()
            due = request.data.get('due', 'Sắp tới').strip() or 'Sắp tới'
            priority = request.data.get('priority', 'medium')
            conv_id = request.data.get('conversation_id')
            conv = Conversation.objects.filter(id=conv_id, memberships__user=user).first() if conv_id else None
            if title:
                Task.objects.create(user=user, title=title, due=due, priority=priority, conversation=conv)
        elif action == 'delete':
            task_id = request.data.get('id')
            Task.objects.filter(id=task_id, user=user).delete()

    tasks = Task.objects.filter(user=user).order_by('done', '-created_at')
    data = [{
        'id': t.id,
        'title': t.title,
        'due': t.due,
        'priority': t.priority,
        'done': t.done,
        'conversation_id': t.conversation_id,
        'conversation_title': t.conversation.name if t.conversation else None,
        'created_at': t.created_at.strftime("%d/%m/%Y %H:%M")
    } for t in tasks]
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_search_messages(request, conversation_id):
    """Tìm kiếm tin nhắn theo từ khóa trong một cuộc hội thoại."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    query = request.GET.get('q', '').strip()
    if not query:
        return Response([])

    messages = conversation.messages.filter(content__icontains=query).select_related('sender__profile').order_by('-created_at')[:30]
    serializer = MessageSerializer(messages, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_group_member(request, conversation_id):
    """Thêm thành viên mới vào nhóm chat."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user, is_group=True)
    target_user_id = request.data.get('user_id')
    target_user = get_object_or_404(User, id=target_user_id)
    member, created = ConversationMember.objects.get_or_create(conversation=conversation, user=target_user, defaults={'role': 'member'})
    
    # Tạo tin nhắn hệ thống thông báo thêm thành viên
    if created:
        inviter_name = user.profile.get_display_name() if hasattr(user, 'profile') else user.username
        target_name = target_user.profile.get_display_name() if hasattr(target_user, 'profile') else target_user.username
        Message.objects.create(
            conversation=conversation,
            sender=None,
            message_type='system',
            content=f"{inviter_name} đã thêm {target_name} vào nhóm."
        )

    return Response({
        'message': f'Đã thêm {target_user.username} vào nhóm thành công!',
        'user_id': target_user.id
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_toggle_pin(request, conversation_id):
    """Ghim hoặc bỏ ghim cuộc hội thoại lên đầu danh sách."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    membership = ConversationMember.objects.filter(conversation=conversation, user=user).first()
    if not membership:
        return Response({'error': 'Không tìm thấy tư cách thành viên!'}, status=status.HTTP_404_NOT_FOUND)

    membership.is_pinned = not membership.is_pinned
    membership.pinned_at = timezone.now() if membership.is_pinned else None
    membership.save(update_fields=['is_pinned', 'pinned_at'])

    return Response({
        'id': conversation.id,
        'is_pinned': membership.is_pinned,
        'message': 'Đã ghim cuộc trò chuyện lên đầu danh sách.' if membership.is_pinned else 'Đã bỏ ghim cuộc trò chuyện.'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_toggle_mute(request, conversation_id):
    """Bật / Tắt thông báo cuộc hội thoại."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    membership = ConversationMember.objects.filter(conversation=conversation, user=user).first()
    if not membership:
        return Response({'error': 'Không tìm thấy tư cách thành viên!'}, status=status.HTTP_404_NOT_FOUND)

    membership.is_muted = not membership.is_muted
    membership.save(update_fields=['is_muted'])

    return Response({
        'id': conversation.id,
        'is_muted': membership.is_muted,
        'message': 'Đã tắt chuông thông báo cho cuộc trò chuyện này.' if membership.is_muted else 'Đã bật lại thông báo cho cuộc trò chuyện.'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_toggle_priority(request, conversation_id):
    """Chuyển đổi hội thoại giữa tab 'Ưu tiên' và 'Khác'."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    membership = ConversationMember.objects.filter(conversation=conversation, user=user).first()
    if not membership:
        return Response({'error': 'Không tìm thấy tư cách thành viên!'}, status=status.HTTP_404_NOT_FOUND)

    membership.is_priority = not membership.is_priority
    membership.save(update_fields=['is_priority'])

    return Response({
        'id': conversation.id,
        'is_priority': membership.is_priority,
        'message': 'Đã chuyển vào tab Ưu tiên' if membership.is_priority else 'Đã chuyển vào tab Khác'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_recall_message(request, message_id):
    """Thu hồi tin nhắn đối với cả 2 bên (Recall Message)."""
    user = request.user
    msg = get_object_or_404(Message, id=message_id, sender=user)
    msg.is_recalled = True
    msg.content = "Tin nhắn đã được thu hồi"
    msg.save(update_fields=['is_recalled', 'content'])
    serializer = MessageSerializer(msg, context={'request': request})

    # Broadcast qua WebSocket
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{msg.conversation_id}",
                {
                    'type': 'broadcast_recall',
                    'message_id': msg.id
                }
            )
    except Exception:
        pass

    return Response({
        'message': 'Đã thu hồi tin nhắn thành công!',
        'msg': serializer.data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_delete_message(request, message_id):
    """Xóa tin nhắn ở phía tôi (Delete for me)."""
    user = request.user
    msg = get_object_or_404(Message, id=message_id, conversation__memberships__user=user)
    msg.deleted_by.add(user)
    return Response({
        'message': 'Đã xóa tin nhắn ở phía bạn.',
        'id': msg.id
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_react_message(request, message_id):
    """Thả hoặc đổi biểu cảm Emoji (❤️ 👍 😂 😮 😢 😡) vào tin nhắn."""
    user = request.user
    msg = get_object_or_404(Message, id=message_id, conversation__memberships__user=user)
    emoji = request.data.get('emoji', '').strip()
    if not emoji:
        return Response({'error': 'Vui lòng chọn biểu cảm Emoji!'}, status=status.HTTP_400_BAD_REQUEST)

    existing = MessageReaction.objects.filter(message=msg, user=user).first()
    if existing:
        if existing.emoji == emoji:
            # Nhấn lại cùng emoji để hủy cảm xúc
            existing.delete()
        else:
            existing.emoji = emoji
            existing.save(update_fields=['emoji'])
    else:
        MessageReaction.objects.create(message=msg, user=user, emoji=emoji)

    serializer = MessageSerializer(msg, context={'request': request})

    # Broadcast qua WebSocket
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{msg.conversation_id}",
                {
                    'type': 'broadcast_reaction',
                    'message_id': msg.id,
                    'reactions': serializer.data['reactions']
                }
            )
    except Exception:
        pass

    return Response({
        'id': msg.id,
        'reactions': serializer.data['reactions']
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_pin_message(request, conversation_id):
    """Ghim hoặc bỏ ghim một tin nhắn lên thanh tiêu đề cuộc trò chuyện."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    message_id = request.data.get('message_id')

    if message_id is None or message_id == 0 or message_id == '':
        conversation.pinned_message = None
        conversation.save(update_fields=['pinned_message'])

        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"chat_{conversation.id}",
                    {
                        'type': 'broadcast_pin',
                        'pinned_message': None
                    }
                )
        except Exception:
            pass

        return Response({'message': 'Đã bỏ ghim tin nhắn.', 'pinned_message': None})

    msg = get_object_or_404(Message, id=message_id, conversation=conversation)
    conversation.pinned_message = msg
    conversation.save(update_fields=['pinned_message'])

    sender_name = "Hệ thống"
    if msg.sender:
        sender_name = msg.sender.profile.get_display_name() if hasattr(msg.sender, 'profile') else msg.sender.username
    snippet = msg.content
    if msg.is_recalled:
        snippet = "Tin nhắn đã được thu hồi"
    elif msg.message_type == 'image':
        snippet = "[Hình ảnh]"
    elif msg.message_type == 'audio':
        snippet = "[Tin nhắn thoại]"
    elif msg.message_type == 'file':
        snippet = f"[Tệp tin] {msg.attachment_name or ''}"
    elif msg.message_type == 'code':
        snippet = f"[Đoạn mã {msg.code_language.upper()}]"

    pinned_info = {
        'id': msg.id,
        'sender_name': sender_name,
        'snippet': snippet,
        'type': msg.message_type
    }

    # Broadcast qua WebSocket
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_pin',
                    'pinned_message': pinned_info
                }
            )
    except Exception:
        pass

    return Response({
        'message': 'Đã ghim tin nhắn lên đầu cuộc trò chuyện!',
        'pinned_message': pinned_info
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_log_call(request, conversation_id):
    """
    Lưu lịch sử cuộc gọi thoại / video vào hội thoại chat (Completed, Missed, Rejected).
    """
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)

    call_type = request.data.get('call_type', 'voice')
    call_status = request.data.get('call_status', 'completed')
    duration = int(request.data.get('duration', 0))

    mins = duration // 60
    secs = duration % 60
    formatted_dur = f"{mins:02d}:{secs:02d}"

    if call_status == 'completed':
        if call_type == 'video':
            content = f"Cuộc gọi video ({formatted_dur})"
        else:
            content = f"Cuộc gọi thoại ({formatted_dur})"
    elif call_status == 'missed':
        content = "Cuộc gọi nhỡ"
    elif call_status == 'rejected':
        content = "Cuộc gọi bị từ chối"
    else:
        content = "Cuộc gọi kết thúc"

    caller_id = request.data.get('caller_id')
    sender = user
    if caller_id:
        try:
            caller = User.objects.filter(id=int(caller_id)).first()
            if caller:
                sender = caller
        except (ValueError, TypeError):
            pass

    msg = Message.objects.create(
        conversation=conversation,
        sender=sender,
        message_type='call',
        content=content,
        code_language=call_type,
        call_duration=duration,
        call_status=call_status
    )

    conversation.updated_at = timezone.now()
    conversation.save(update_fields=['updated_at'])

    serializer = MessageSerializer(msg, context={'request': request})

    # Broadcast qua WebSocket (Channels Layer) tới tất cả client (0ms)
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_message',
                    'message': serializer.data
                }
            )
    except Exception:
        pass

    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_mark_read(request, conversation_id):
    """Đánh dấu đã đọc tin nhắn trong cuộc trò chuyện."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, memberships__user=user)
    last_msg_id = request.data.get('last_message_id')
    
    membership = conversation.memberships.filter(user=user).first()
    if membership:
        if last_msg_id:
            try:
                membership.last_read_message_id = max(membership.last_read_message_id, int(last_msg_id))
            except (ValueError, TypeError):
                pass
        else:
            latest = conversation.messages.last()
            if latest:
                membership.last_read_message_id = latest.id
        membership.save(update_fields=['last_read_message_id'])

        # Broadcast qua WebSocket để người gửi thấy trạng thái "Đã xem" tức thì
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                profile = getattr(user, 'profile', None)
                async_to_sync(channel_layer.group_send)(
                    f"chat_{conversation.id}",
                    {
                        'type': 'broadcast_read_receipt',
                        'user_id': user.id,
                        'username': user.username,
                        'display_name': profile.get_display_name() if profile else user.username,
                        'avatar_url': profile.get_avatar_url() if profile else None,
                        'last_read_message_id': membership.last_read_message_id,
                        'sender_channel_name': ''
                    }
                )
        except Exception:
            pass

    return Response({
        'success': True,
        'last_read_message_id': membership.last_read_message_id if membership else 0
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_forward_message(request, message_id):
    """Chuyển tiếp một tin nhắn sang các cuộc hội thoại khác."""
    user = request.user
    original_msg = get_object_or_404(Message, id=message_id)
    conversation_ids = request.data.get('conversation_ids', [])

    if not conversation_ids or not isinstance(conversation_ids, list):
        return Response({'error': 'Vui lòng chọn ít nhất một cuộc hội thoại để chuyển tiếp!'}, status=status.HTTP_400_BAD_REQUEST)

    forwarded_count = 0
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()

    for conv_id in conversation_ids:
        conv = Conversation.objects.filter(id=conv_id, memberships__user=user).first()
        if not conv:
            continue

        new_msg = Message.objects.create(
            conversation=conv,
            sender=user,
            message_type=original_msg.message_type,
            content=original_msg.content,
            attachment=original_msg.attachment,
            attachment_name=original_msg.attachment_name,
            attachment_size=original_msg.attachment_size,
            code_language=original_msg.code_language
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])
        forwarded_count += 1

        # Broadcast realtime
        if channel_layer:
            try:
                serializer = MessageSerializer(new_msg, context={'request': request})
                async_to_sync(channel_layer.group_send)(
                    f"chat_{conv.id}",
                    {
                        'type': 'broadcast_message',
                        'message': serializer.data
                    }
                )
            except Exception:
                pass

    return Response({
        'message': f'Đã chuyển tiếp tin nhắn tới {forwarded_count} cuộc trò chuyện!',
        'forwarded_count': forwarded_count
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def api_update_group(request, conversation_id):
    """Cập nhật tên hoặc ảnh đại diện của nhóm chat."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, is_group=True, memberships__user=user)

    membership = conversation.memberships.filter(user=user).first()
    if not membership:
        return Response({'error': 'Bạn không có quyền quản trị nhóm này!'}, status=status.HTTP_403_FORBIDDEN)

    name = request.data.get('name') or request.data.get('title')
    if name and name.strip():
        conversation.name = name.strip()

    if 'avatar' in request.FILES:
        conversation.avatar = request.FILES['avatar']

    conversation.updated_at = timezone.now()
    conversation.save()

    user_name = user.profile.get_display_name() if hasattr(user, 'profile') else user.username
    sys_msg = Message.objects.create(
        conversation=conversation,
        sender=None,
        message_type='system',
        content=f"{user_name} đã cập nhật thông tin nhóm."
    )

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            serializer = MessageSerializer(sys_msg, context={'request': request})
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_message',
                    'message': serializer.data
                }
            )
    except Exception:
        pass

    return Response({
        'message': 'Đã cập nhật thông tin nhóm thành công!',
        'title': conversation.name,
        'avatar_url': conversation.get_avatar_for_user(user)
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_remove_group_member(request, conversation_id):
    """Trưởng nhóm xóa thành viên khỏi nhóm chat."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, is_group=True, memberships__user=user)

    my_membership = conversation.memberships.filter(user=user).first()
    if not my_membership or my_membership.role != 'admin':
        return Response({'error': 'Chỉ có Trưởng nhóm mới có quyền xóa thành viên!'}, status=status.HTTP_403_FORBIDDEN)

    target_user_id = request.data.get('user_id')
    if not target_user_id or int(target_user_id) == user.id:
        return Response({'error': 'Yêu cầu không hợp lệ!'}, status=status.HTTP_400_BAD_REQUEST)

    target_membership = conversation.memberships.filter(user_id=target_user_id).first()
    if not target_membership:
        return Response({'error': 'Thành viên không tồn tại trong nhóm!'}, status=status.HTTP_404_NOT_FOUND)

    target_user = target_membership.user
    target_name = target_user.profile.get_display_name() if hasattr(target_user, 'profile') else target_user.username
    admin_name = user.profile.get_display_name() if hasattr(user, 'profile') else user.username
    target_membership.delete()

    sys_msg = Message.objects.create(
        conversation=conversation,
        sender=None,
        message_type='system',
        content=f"{admin_name} đã xóa {target_name} khỏi nhóm."
    )

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            serializer = MessageSerializer(sys_msg, context={'request': request})
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_message',
                    'message': serializer.data
                }
            )
    except Exception:
        pass

    return Response({'message': f'Đã xóa {target_name} khỏi nhóm!'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_leave_group(request, conversation_id):
    """Rời khỏi nhóm trò chuyện."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, is_group=True, memberships__user=user)

    my_membership = conversation.memberships.filter(user=user).first()
    if not my_membership:
        return Response({'error': 'Bạn không phải thành viên của nhóm!'}, status=status.HTTP_400_BAD_REQUEST)

    is_admin = (my_membership.role == 'admin')
    user_name = user.profile.get_display_name() if hasattr(user, 'profile') else user.username
    my_membership.delete()

    remaining_members = conversation.memberships.all()
    if not remaining_members.exists():
        conversation.delete()
        return Response({'message': 'Bạn đã rời nhóm. Nhóm đã được giải tán do không còn thành viên.'})

    if is_admin:
        new_admin_m = remaining_members.first()
        new_admin_m.role = 'admin'
        new_admin_m.save(update_fields=['role'])
        new_admin_name = new_admin_m.user.profile.get_display_name() if hasattr(new_admin_m.user, 'profile') else new_admin_m.user.username
        sys_msg = Message.objects.create(
            conversation=conversation,
            sender=None,
            message_type='system',
            content=f"{user_name} đã rời nhóm. {new_admin_name} được chỉ định làm Trưởng nhóm mới."
        )
    else:
        sys_msg = Message.objects.create(
            conversation=conversation,
            sender=None,
            message_type='system',
            content=f"{user_name} đã rời khỏi nhóm."
        )

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            serializer = MessageSerializer(sys_msg, context={'request': request})
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_message',
                    'message': serializer.data
                }
            )
    except Exception:
        pass

    return Response({'message': 'Đã rời khỏi nhóm thành công!'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_change_member_role(request, conversation_id):
    """Trưởng nhóm phân quyền hoặc chuyển quyền trưởng nhóm."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, is_group=True, memberships__user=user)

    my_membership = conversation.memberships.filter(user=user).first()
    if not my_membership or my_membership.role != 'admin':
        return Response({'error': 'Chỉ có Trưởng nhóm mới có quyền phân quyền!'}, status=status.HTTP_403_FORBIDDEN)

    target_user_id = request.data.get('user_id')
    new_role = request.data.get('role', 'admin')

    target_membership = conversation.memberships.filter(user_id=target_user_id).first()
    if not target_membership:
        return Response({'error': 'Không tìm thấy thành viên!'}, status=status.HTTP_404_NOT_FOUND)

    target_membership.role = new_role
    target_membership.save(update_fields=['role'])

    target_name = target_membership.user.profile.get_display_name() if hasattr(target_membership.user, 'profile') else target_membership.user.username
    admin_name = user.profile.get_display_name() if hasattr(user, 'profile') else user.username

    role_label = "Trưởng nhóm" if new_role == 'admin' else "Thành viên"
    sys_msg = Message.objects.create(
        conversation=conversation,
        sender=None,
        message_type='system',
        content=f"{admin_name} đã chỉ định {target_name} làm {role_label}."
    )

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            serializer = MessageSerializer(sys_msg, context={'request': request})
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation.id}",
                {
                    'type': 'broadcast_message',
                    'message': serializer.data
                }
            )
    except Exception:
        pass

    return Response({'message': f'Đã cập nhật vai trò của {target_name} thành {role_label}!'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_disband_group(request, conversation_id):
    """Trưởng nhóm giải tán nhóm chat."""
    user = request.user
    conversation = get_object_or_404(Conversation, id=conversation_id, is_group=True, memberships__user=user)

    my_membership = conversation.memberships.filter(user=user).first()
    if not my_membership or my_membership.role != 'admin':
        return Response({'error': 'Chỉ có Trưởng nhóm mới có quyền giải tán nhóm!'}, status=status.HTTP_403_FORBIDDEN)

    conversation_name = conversation.name or "Nhóm chat"
    conversation.delete()
    return Response({'message': f'Đã giải tán nhóm "{conversation_name}" thành công!'})






