from django.contrib import admin
from .models import UserProfile, Conversation, ConversationMember, Message

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'display_name', 'phone', 'gender', 'is_online', 'last_seen')
    search_fields = ('user__username', 'display_name', 'phone')
    list_filter = ('gender', 'is_online')

class ConversationMemberInline(admin.TabularInline):
    model = ConversationMember
    extra = 1

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_group', 'created_by', 'created_at', 'updated_at')
    search_fields = ('name',)
    list_filter = ('is_group',)
    inlines = [ConversationMemberInline]

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'message_type', 'created_at')
    list_filter = ('message_type', 'created_at')
    search_fields = ('content', 'attachment_name')
