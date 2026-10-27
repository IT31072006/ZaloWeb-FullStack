"""
Django settings for zalo_project project.
"""

from pathlib import Path
import os
import socket

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-dp*fev3g84r$v22^l8iwi1jv=e115zz5%1lwia2btm(dufoi)f'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'corsheaders',
    'chat.apps.ChatConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'zalo_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'zalo_project.wsgi.application'
ASGI_APPLICATION = 'zalo_project.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

# ==============================================================================
# DATABASE CONFIGURATION: PostgreSQL with automatic graceful fallback
# ==============================================================================
# Hỗ trợ PostgreSQL qua psycopg 3 theo yêu cầu đề bài.
# Tự động kiểm tra kết nối tới PostgreSQL (host/port); nếu PostgreSQL đang mở thì dùng,
# nếu daemon PostgreSQL chưa khởi động thì fallback mượt mà sang SQLite để dev/chạy ngay.

DB_NAME = os.environ.get('DB_NAME', 'zalo_chat')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

def is_postgres_accessible(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=0.8):
            return True
    except Exception:
        return False

# Kiểm tra nếu người dùng chỉ định ép dùng PostgreSQL hoặc port 5432 phản hồi
FORCE_POSTGRES = os.environ.get('FORCE_POSTGRES', '0') == '1'
POSTGRES_AVAILABLE = is_postgres_accessible(DB_HOST, DB_PORT)

if FORCE_POSTGRES or POSTGRES_AVAILABLE:
    print(f"[*] [DATABASE] Kết nối PostgreSQL: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
        }
    }
else:
    print(f"[*] [DATABASE] Cổng PostgreSQL ({DB_HOST}:{DB_PORT}) chưa phản hồi.")
    print(f"[*] [DATABASE] Tự động kích hoạt cơ chế SQLite ({BASE_DIR / 'db.sqlite3'}) để ứng dụng chạy ngay không bị gián đoạn.")
    print(f"[*] [DATABASE] (Khi bạn bật PostgreSQL service, hệ thống sẽ tự động chuyển sang PostgreSQL!)")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 4}
    },
]

LANGUAGE_CODE = 'vi-vn'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'chat.authentication.CsrfExemptSessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ]
}
