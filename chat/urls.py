from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.index_view, name='index'),
    path('auth/', views.auth_view, name='auth'),

    # Auth APIs
    path('api/register/', views.api_register, name='api_register'),
    path('api/login/', views.api_login, name='api_login'),
    path('api/logout/', views.api_logout, name='api_logout'),
    path('api/me/', views.api_me, name='api_me'),
    path('api/profile/update/', views.api_update_profile, name='api_update_profile'),

    # Chat & Messaging APIs
    path('api/conversations/', views.api_conversations, name='api_conversations'),
    path('api/conversations/create/', views.api_create_conversation, name='api_create_conversation'),
    path('api/conversations/<int:conversation_id>/', views.api_conversation_detail, name='api_conversation_detail'),
    path('api/conversations/<int:conversation_id>/messages/', views.api_get_messages, name='api_get_messages'),
    path('api/conversations/<int:conversation_id>/send/', views.api_send_message, name='api_send_message'),
    path('api/conversations/<int:conversation_id>/log_call/', views.api_log_call, name='api_log_call'),
    path('api/conversations/<int:conversation_id>/sync/', views.api_sync_messages, name='api_sync_messages'),
    path('api/conversations/<int:conversation_id>/search/', views.api_search_messages, name='api_search_messages'),
    path('api/conversations/<int:conversation_id>/add_member/', views.api_add_group_member, name='api_add_group_member'),
    path('api/conversations/<int:conversation_id>/toggle_pin/', views.api_toggle_pin, name='api_toggle_pin'),
    path('api/conversations/<int:conversation_id>/toggle_mute/', views.api_toggle_mute, name='api_toggle_mute'),
    path('api/conversations/<int:conversation_id>/toggle_priority/', views.api_toggle_priority, name='api_toggle_priority'),
    path('api/conversations/<int:conversation_id>/pin_message/', views.api_pin_message, name='api_pin_message'),
    path('api/conversations/<int:conversation_id>/mark_read/', views.api_mark_read, name='api_mark_read'),
    path('api/messages/<int:message_id>/recall/', views.api_recall_message, name='api_recall_message'),
    path('api/messages/<int:message_id>/delete/', views.api_delete_message, name='api_delete_message'),
    path('api/messages/<int:message_id>/react/', views.api_react_message, name='api_react_message'),
    path('api/messages/<int:message_id>/forward/', views.api_forward_message, name='api_forward_message'),
    path('api/users/search/', views.api_search_users, name='api_search_users'),
    path('api/users/search_by_phone/', views.api_search_by_phone, name='api_search_by_phone'),

    # Extended Features
    path('api/cloud/', views.api_cloud, name='api_cloud'),
    path('api/contacts/', views.api_contacts, name='api_contacts'),
    path('api/tasks/', views.api_tasks, name='api_tasks'),
]
