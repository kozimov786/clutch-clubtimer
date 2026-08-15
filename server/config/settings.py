import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Ishlab chiqarish (production) muhitida bu uchtasi DJANGO_SECRET_KEY,
# DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS muhit o'zgaruvchilari orqali
# sozlanishi kerak — pastdagilar faqat muhit o'zgaruvchisi
# o'rnatilmagan hollarda ishlatiladigan standart (fallback) qiymatlar.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    '1NhUaGjRqczYSQ8PehQxRH419jnhLKcrof4fclYM0B_TCgNj8WjMdOBLb9QyTMtsPcc'
)

# DEBUG=True bo'lganda, xatolik yuz berganda butun sozlamalar (SECRET_KEY,
# CLIENT_API_KEY va h.k.) xato sahifasida ochiq ko'rinadi — shuning uchun
# standart qiymat endi False. Xatolikni tekshirish kerak bo'lsa,
# `DJANGO_DEBUG=True` muhit o'zgaruvchisi bilan vaqtincha yoqish mumkin.
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

# Standart holatda hammasiga ochiq (LAN ichida turli IP/hostname orqali
# kirilishi mumkinligi uchun) — aniq IP/domenlaringizni bilsangiz,
# DJANGO_ALLOWED_HOSTS="192.168.88.100,localhost" kabi vergul bilan
# ajratib bering.
_allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS')
ALLOWED_HOSTS = _allowed_hosts_env.split(',') if _allowed_hosts_env else ['*']

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'channels',
    # Local apps
    'apps.billing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'apps' / 'billing' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# POSTGRES_DB muhit o'zgaruvchisi o'rnatilgan bo'lsa — PostgreSQL
# ishlatiladi (bir nechta yozuvchi bir vaqtda ishlashi mumkin, 40 PC
# uchun tavsiya etiladi). O'rnatilmagan bo'lsa — standart SQLite
# (bitta faylga asoslangan, kichik/sinov muhitlar uchun qulay, lekin
# bir vaqtning o'zida faqat BITTA yozuvchi ulanishga ruxsat beradi —
# yuqori yuklama ostida "database is locked" xatolariga sabab bo'ladi).
_pg_name = os.environ.get('POSTGRES_DB')
if _pg_name:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _pg_name,
            'USER': os.environ.get('POSTGRES_USER', 'clutchzone'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # 20 soniyagacha kutishga ruxsat berilyapti — real hayotda
            # bunday to'qnashuv juda qisqa (millisekundlar) davom etadi.
            'OPTIONS': {'timeout': 20},
        }
    }

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.billing.authentication.CsrfExemptSessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    # kiosk_login (mijoz o'z-o'ziga xizmat kirishi) uchun — bir xil IP'dan
    # (bitta kiosk PC) haddan tashqari ko'p urinishlarni cheklab, parolni
    # "qo'pol kuch" (brute-force) bilan topishga urinishning oldini oladi.
    'DEFAULT_THROTTLE_RATES': {
        'kiosk_login': '20/minute',
    },
}

# client_locker.py kiosk ilovalari shu kalitni X-API-Key header orqali
# yuboradi (foydalanuvchi hisobi bo'lmagani uchun login qila olmaydi).
# Har bir klub o'z serverida buni o'zgartirishi tavsiya etiladi.
CLIENT_API_KEY = 'AKiv9qEeJqBlO8Xa4HJfJ_ZmMig6c5srmY7Nr1c4oOw'

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'apps' / 'billing' / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Kiosk klientlari yuklaydigan ekran skrinshotlari shu yerda saqlanadi
# (masofadan monitoring uchun).
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
