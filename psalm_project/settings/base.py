import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Adjusted for being in psalm_project/settings/base.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_list(name, default=None):
    raw = os.environ.get(name, '')
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(',') if item.strip()]


def required_env(name):
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(f'{name} must be set')
    return value.strip()


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-7(i^!@3q)8d*z*cw#@j+y51+*#uan35+$4m*_5l$f-qk$i@0u0')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django.contrib.postgres',
    'storages',
    'psaumes',
]

MIDDLEWARE = [
    'psalm_project.middleware.RedirectLegacyHostsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'psalm_project.security.ContentSecurityPolicyMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'psalm_project.urls'

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
                'psaumes.context_processors.banner',
                'psaumes.context_processors.site_url',
            ],
        },
    },
]

WSGI_APPLICATION = 'psalm_project.wsgi.application'

# Database
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'cantateo'),
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cache
if os.environ.get('REDIS_URL'):
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': os.environ.get('REDIS_URL'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {'max_connections': 50, 'retry_on_timeout': True},
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            },
            'KEY_PREFIX': 'psalm',
            'TIMEOUT': 900,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-sessions',
            'TIMEOUT': 900,
        }
    }

# SEO & Contact
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_HOST_USER') or os.environ.get('CONTACT_EMAIL', 'webmaster@localhost')
CONTACT_EMAIL = os.environ.get('CONTACT_EMAIL', '')
SITE_ID = 1
SITE_DOMAIN = os.environ.get('SITE_DOMAIN', 'www.cantateo.fr')
SITE_SCHEME = os.environ.get('SITE_SCHEME', 'https')

# Cloudflare Turnstile anti-bot
TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')

# Optional Sentry instrumentation
SENTRY_DSN = os.environ.get('SENTRY_DSN', '').strip()
if SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.environ.get('SENTRY_ENVIRONMENT', os.environ.get('DJANGO_ENV', 'development')),
            send_default_pii=False,
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0')),
        )
    except ImportError:
        pass

# Audio
SOUNDFONT_PATH = os.environ.get('SOUNDFONT_PATH', str(BASE_DIR / 'soundfonts' / 'SalamanderGrandPiano.sf2'))

# Celery
CELERY_BROKER_URL = os.environ.get(
    'CELERY_BROKER_URL',
    os.environ.get('REDIS_URL', 'redis://localhost:6379/1'),
)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.environ.get('CELERY_WORKER_PREFETCH_MULTIPLIER', '1'))
CELERY_TASK_DEFAULT_PRIORITY = int(os.environ.get('CELERY_TASK_DEFAULT_PRIORITY', '0'))
CELERY_TASK_QUEUE_MAX_PRIORITY = int(os.environ.get('CELERY_TASK_QUEUE_MAX_PRIORITY', '9'))
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'priority_steps': list(range(CELERY_TASK_QUEUE_MAX_PRIORITY + 1)),
    'queue_order_strategy': 'priority',
}
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get('CELERY_TASK_SOFT_TIME_LIMIT', '1500'))
CELERY_TASK_TIME_LIMIT = int(os.environ.get('CELERY_TASK_TIME_LIMIT', '1800'))
CELERY_TASK_ROUTES = {
    'psaumes.normalize_partition_audio': {'queue': 'audio'},
    'psaumes.generate_partition_audio': {'queue': 'audio'},
    'psaumes.generate_partition_tempo_variants': {'queue': 'audio'},
    'psaumes.generate_partition_mxl': {'queue': 'omr'},
}

# Runtime guardrails
AUDIO_GENERATION_MAX_ATTEMPTS = int(os.environ.get('AUDIO_GENERATION_MAX_ATTEMPTS', '3'))
AUDIO_GENERATION_RETRY_DELAY_SECONDS = int(os.environ.get('AUDIO_GENERATION_RETRY_DELAY_SECONDS', '3600'))
AUDIO_NORMALIZATION_MAX_ATTEMPTS = int(
    os.environ.get('AUDIO_NORMALIZATION_MAX_ATTEMPTS', AUDIO_GENERATION_MAX_ATTEMPTS)
)
AUDIO_NORMALIZATION_RETRY_DELAY_SECONDS = int(
    os.environ.get('AUDIO_NORMALIZATION_RETRY_DELAY_SECONDS', AUDIO_GENERATION_RETRY_DELAY_SECONDS)
)
OMR_BACKEND = os.environ.get('OMR_BACKEND', 'homr_cli')
OMR_MODEL_PROFILE = os.environ.get('OMR_MODEL_PROFILE', 'default')
HOMR_COMMAND = os.environ.get('HOMR_COMMAND', 'homr')
OMR_MAX_PAGES = int(os.environ.get('OMR_MAX_PAGES', '1'))
OMR_PDF_DPI = int(os.environ.get('OMR_PDF_DPI', '250'))
OMR_TASK_TIMEOUT_SECONDS = int(os.environ.get('OMR_TASK_TIMEOUT_SECONDS', '600'))
OMR_MAX_ATTEMPTS = int(os.environ.get('OMR_MAX_ATTEMPTS', '2'))
OMR_RETRY_DELAY_SECONDS = int(os.environ.get('OMR_RETRY_DELAY_SECONDS', '3600'))

RATE_LIMITS = {
    'search_autocomplete': (
        int(os.environ.get('RATE_LIMIT_SEARCH_AUTOCOMPLETE_LIMIT', '60')),
        int(os.environ.get('RATE_LIMIT_SEARCH_AUTOCOMPLETE_WINDOW', '60')),
    ),
    'audio_status': (
        int(os.environ.get('RATE_LIMIT_AUDIO_STATUS_LIMIT', '120')),
        int(os.environ.get('RATE_LIMIT_AUDIO_STATUS_WINDOW', '60')),
    ),
    'audio_variants': (
        int(os.environ.get('RATE_LIMIT_AUDIO_VARIANTS_LIMIT', '120')),
        int(os.environ.get('RATE_LIMIT_AUDIO_VARIANTS_WINDOW', '60')),
    ),
    'contact': (
        int(os.environ.get('RATE_LIMIT_CONTACT_LIMIT', '5')),
        int(os.environ.get('RATE_LIMIT_CONTACT_WINDOW', '600')),
    ),
}

CONTENT_SECURITY_POLICY = os.environ.get('CONTENT_SECURITY_POLICY', '').strip()
