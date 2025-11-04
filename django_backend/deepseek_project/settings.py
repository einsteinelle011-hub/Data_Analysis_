import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-example-key-for-development-only'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['0.0.0.0', 'localhost', '127.0.0.1']
# ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ninja',
    'corsheaders',
    'deepseek_api',
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

ROOT_URLCONF = 'deepseek_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'deepseek_project.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# 允许前端域名（根据实际前端地址修改）
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8090",
    "http://127.0.0.1:8090",
]

# 允许请求头携带 Authorization
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 自定义配置
API_KEY_LENGTH = 32
TOKEN_EXPIRY_SECONDS = 360000
RATE_LIMIT_MAX = 5000  # 每分钟最大请求数
RATE_LIMIT_INTERVAL = 60
CACHE_MAX_SIZE = 200
CACHE_EXPIRY = 300

# === RAG / 知识库配置 ===
KB_DIR = BASE_DIR / "data" / "kb"           # 你把 PDF/MD/TXT 放这里
INDEX_DIR = BASE_DIR / "data" / "index"     # 构建出的索引会放这里
RAG_TOPK = 5                                # 每次检索返回的片段数
CHUNK_SIZE = 800                            # 简单按字符切分
CHUNK_OVERLAP = 150

# === Web RAG 开关与配置 ===
ENABLE_WEB_RAG = True
WEB_RAG_PROVIDER = "serpapi"   # 这个其实可以不需要了，但留着也没事
WEB_RAG_TOPK = 5
WEB_RAG_LANG = "zh-cn"
SERPAPI_API_KEY = "5a7a457b0b7579bfc321c5d509abcbd181a57b56e9cd3d82698dbe7a97ab8e61"

ENABLE_WORKFLOW = True
WORKFLOW_MAX_STEPS = 2   # 防止无限循环，先给 1~3 次
