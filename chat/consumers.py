import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Conversation, ConversationMember, Message, MessageReaction
from .serializers import MessageSerializer


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket Consumer cho Zalo Web:
    - Trao đổi tin nhắn thời gian thực 0ms (Chat Messaging).
    - Cập nhật trạng thái "Đang soạn tin nhắn..." (Typing Indicator).
    - Trạng thái người dùng Online/Offline (Presence).
    - Kênh truyền tín hiệu WebRTC P2P (Signaling: Offer, Answer, ICE Candidates cho Video & Voice Call).
    - Đồng bộ biểu cảm cảm xúc (Reactions), Thu hồi (Recall) & Ghim tin nhắn (Pin).
    """

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f"chat_{self.conversation_id}"
        self.user = self.scope.get('user')

        # Kiểm tra xác thực người dùng
        if not self.user or not self.user.is_authenticated:
            # Cho phép kiểm tra qua query string nếu cần (token hoặc dev session)
            query_string = self.scope.get('query_string', b'').decode('utf-8')
            if 'user_id=' in query_string:
                try:
                    uid = int(query_string.split('user_id=')[1].split('&')[0])
                    self.user = await self.get_user_by_id(uid)
                except Exception:
                    pass

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        # Kiểm tra tư cách thành viên trong cuộc hội thoại
        is_member = await self.check_membership(self.conversation_id, self.user)
        if not is_member:
            await self.close(code=4403)
            return

        self.user_display_name = await self.get_display_name(self.user)
        self.user_avatar = await self.get_avatar_url(self.user)

        # Tham gia vào nhóm WebSocket của cuộc trò chuyện
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Cập nhật trạng thái Online cho thành viên khác trong phòng
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_user_status',
                'user_id': self.user.id,
                'username': self.user.username,
                'display_name': self.user_display_name,
                'status': 'online',
                'sender_channel_name': self.channel_name
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and hasattr(self, 'user') and self.user.is_authenticated:
            # Thông báo trạng thái Offline
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_user_status',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'display_name': getattr(self, 'user_display_name', self.user.username),
                    'status': 'offline',
                    'sender_channel_name': self.channel_name
                }
            )
            # Rời khỏi nhóm WebSocket
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type')

        # 1. Gửi tin nhắn trực tiếp qua WebSocket (0ms Latency)
        if msg_type == 'chat_message':
            content = data.get('content', '').strip()
            reply_to_id = data.get('reply_to_id')
            code_language = data.get('code_language', 'java')
            sub_type = data.get('message_type', 'text')

            if content:
                msg_data = await self.save_message(
                    conv_id=self.conversation_id,
                    sender=self.user,
                    content=content,
                    message_type=sub_type,
                    code_language=code_language,
                    reply_to_id=reply_to_id
                )
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'broadcast_message',
                        'message': msg_data
                    }
                )

        # 2. Typing Indicator: Đang soạn tin nhắn...
        elif msg_type == 'typing':
            is_typing = data.get('is_typing', False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_typing',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'display_name': self.user_display_name,
                    'is_typing': is_typing,
                    'sender_channel_name': self.channel_name
                }
            )

        # 3. Thả / Đổi biểu cảm cảm xúc (Reaction)
        elif msg_type == 'reaction':
            message_id = data.get('message_id')
            emoji = data.get('emoji', '').strip()
            if message_id and emoji:
                reactions = await self.toggle_reaction(message_id, self.user, emoji)
                if reactions is not None:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'broadcast_reaction',
                            'message_id': message_id,
                            'reactions': reactions
                        }
                    )

        # 4. Thu hồi tin nhắn (Recall)
        elif msg_type == 'recall':
            message_id = data.get('message_id')
            if message_id:
                recalled = await self.recall_message(message_id, self.user)
                if recalled:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'broadcast_recall',
                            'message_id': message_id
                        }
                    )

        # 5. Ghim tin nhắn (Pin)
        elif msg_type == 'pin':
            message_id = data.get('message_id')
            pinned_info = await self.pin_message(self.conversation_id, message_id)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_pin',
                    'pinned_message': pinned_info
                }
            )

        # 6. WebRTC Signaling (Call Request, Offer, Answer, ICE Candidates, Call End)
        elif msg_type == 'webrtc_signal':
            action = data.get('action')
            call_type = data.get('call_type', 'video')  # 'voice' hoặc 'video'
            target_user_id = data.get('target_user_id')

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_webrtc_signal',
                    'action': action,
                    'call_type': call_type,
                    'sdp': data.get('sdp'),
                    'candidate': data.get('candidate'),
                    'is_muted': data.get('is_muted'),
                    'is_cam_off': data.get('is_cam_off'),
                    'target_user_id': target_user_id,
                    'sender_id': self.user.id,
                    'sender_name': self.user_display_name,
                    'sender_avatar': self.user_avatar,
                    'sender_channel_name': self.channel_name
                }
            )

        # 7. Call Log: Lưu lịch sử cuộc gọi tự động khi kết thúc hoặc nhỡ
        elif msg_type == 'call_log':
            call_type = data.get('call_type', 'voice')
            call_status = data.get('call_status', 'completed')
            duration = int(data.get('duration', 0))
            caller_id = data.get('caller_id')

            sender = self.user
            if caller_id:
                try:
                    if int(caller_id) != self.user.id:
                        caller = await self.get_user_by_id(int(caller_id))
                        if caller:
                            sender = caller
                except (ValueError, TypeError):
                    pass

            msg_data = await self.save_call_message(
                conv_id=self.conversation_id,
                sender=sender,
                call_type=call_type,
                call_status=call_status,
                duration=duration
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_message',
                    'message': msg_data
                }
            )

    # =========================================================================
    # CÁC BỘ PHÁT SỰ KIỆN BROADCAST TỚI CLIENT QUA WEBSOCKET
    # =========================================================================

    async def broadcast_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))

    async def broadcast_typing(self, event):
        if self.channel_name != event.get('sender_channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'username': event['username'],
                'display_name': event['display_name'],
                'is_typing': event['is_typing']
            }))

    async def broadcast_reaction(self, event):
        await self.send(text_data=json.dumps({
            'type': 'reaction_update',
            'message_id': event['message_id'],
            'reactions': event['reactions']
        }))

    async def broadcast_recall(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_recalled',
            'message_id': event['message_id'],
            'content': 'Tin nhắn đã được thu hồi'
        }))

    async def broadcast_pin(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_pinned',
            'pinned_message': event['pinned_message']
        }))

    async def broadcast_user_status(self, event):
        if self.channel_name != event.get('sender_channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'user_status',
                'user_id': event['user_id'],
                'username': event['username'],
                'display_name': event['display_name'],
                'status': event['status']
            }))

    async def broadcast_webrtc_signal(self, event):
        # Không gửi lại cho chính người gửi tín hiệu signaling
        if self.channel_name == event.get('sender_channel_name'):
            return

        # Nếu có target_user_id, chỉ gửi cho user mục tiêu
        target_uid = event.get('target_user_id')
        if target_uid and target_uid != self.user.id:
            return

        payload = {
            'type': 'webrtc_signal',
            'action': event['action'],
            'call_type': event.get('call_type', 'video'),
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'sender_avatar': event['sender_avatar']
        }
        if 'sdp' in event and event['sdp'] is not None:
            payload['sdp'] = event['sdp']
        if 'candidate' in event and event['candidate'] is not None:
            payload['candidate'] = event['candidate']
        if 'is_muted' in event and event['is_muted'] is not None:
            payload['is_muted'] = event['is_muted']
        if 'is_cam_off' in event and event['is_cam_off'] is not None:
            payload['is_cam_off'] = event['is_cam_off']

        await self.send(text_data=json.dumps(payload))

    # =========================================================================
    # DATABASE ASYNC HELPERS (Django ORM qua database_sync_to_async)
    # =========================================================================

    @database_sync_to_async
    def get_user_by_id(self, user_id):
        return User.objects.filter(id=user_id).first()

    @database_sync_to_async
    def get_display_name(self, user):
        if hasattr(user, 'profile'):
            return user.profile.get_display_name()
        return user.username

    @database_sync_to_async
    def get_avatar_url(self, user):
        if hasattr(user, 'profile'):
            return user.profile.get_avatar_url()
        return f"https://ui-avatars.com/api/?name={user.username}&background=0068ff&color=ffffff"

    @database_sync_to_async
    def check_membership(self, conv_id, user):
        try:
            return ConversationMember.objects.filter(conversation_id=conv_id, user=user).exists()
        except Exception:
            return False

    @database_sync_to_async
    def save_message(self, conv_id, sender, content, message_type='text', code_language='java', reply_to_id=None):
        conv = Conversation.objects.get(id=conv_id)
        reply_to = None
        if reply_to_id:
            try:
                reply_to = Message.objects.filter(id=int(reply_to_id), conversation=conv).first()
            except (ValueError, TypeError):
                reply_to = None

        msg = Message.objects.create(
            conversation=conv,
            sender=sender,
            message_type=message_type,
            content=content,
            code_language=code_language,
            reply_to=reply_to
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])

        # Cập nhật trạng thái đã đọc
        ConversationMember.objects.filter(conversation=conv, user=sender).update(last_read_message_id=msg.id)

        # Fake context with current user to format serializer
        class DummyRequest:
            def __init__(self, user):
                self.user = user
            def build_absolute_uri(self, location):
                return location

        serializer = MessageSerializer(msg, context={'request': DummyRequest(sender)})
        return serializer.data

    @database_sync_to_async
    def save_call_message(self, conv_id, sender, call_type, call_status, duration):
        conv = Conversation.objects.get(id=conv_id)
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

        msg = Message.objects.create(
            conversation=conv,
            sender=sender,
            message_type='call',
            content=content,
            code_language=call_type,
            call_duration=duration,
            call_status=call_status
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])

        class DummyRequest:
            def __init__(self, user):
                self.user = user
            def build_absolute_uri(self, location):
                return location

        serializer = MessageSerializer(msg, context={'request': DummyRequest(sender)})
        return serializer.data

    @database_sync_to_async
    def toggle_reaction(self, message_id, user, emoji):
        msg = Message.objects.filter(id=message_id).first()
        if not msg:
            return None
        existing = MessageReaction.objects.filter(message=msg, user=user).first()
        if existing:
            if existing.emoji == emoji:
                existing.delete()
            else:
                existing.emoji = emoji
                existing.save(update_fields=['emoji'])
        else:
            MessageReaction.objects.create(message=msg, user=user, emoji=emoji)

        class DummyRequest:
            def __init__(self, user):
                self.user = user
            def build_absolute_uri(self, location):
                return location

        serializer = MessageSerializer(msg, context={'request': DummyRequest(user)})
        return serializer.data['reactions']

    @database_sync_to_async
    def recall_message(self, message_id, user):
        msg = Message.objects.filter(id=message_id, sender=user).first()
        if not msg:
            return False
        msg.is_recalled = True
        msg.content = "Tin nhắn đã được thu hồi"
        msg.save(update_fields=['is_recalled', 'content'])
        return True

    @database_sync_to_async
    def pin_message(self, conv_id, message_id):
        conv = Conversation.objects.filter(id=conv_id).first()
        if not conv:
            return None
        if not message_id:
            conv.pinned_message = None
            conv.save(update_fields=['pinned_message'])
            return None

        msg = Message.objects.filter(id=message_id, conversation=conv).first()
        if not msg:
            return None
        conv.pinned_message = msg
        conv.save(update_fields=['pinned_message'])

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

        return {
            'id': msg.id,
            'sender_name': sender_name,
            'snippet': snippet,
            'type': msg.message_type
        }
