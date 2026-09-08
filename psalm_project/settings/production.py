import os
from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False

# Allowed hosts configuration
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must be set for production')

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured('CSRF_TRUSTED_ORIGINS must be set for production')

SECRET_KEY = required_env('DJANGO_SECRET_KEY')
CONTACT_EMAIL = required_env('CONTACT_EMAIL')
TURNSTILE_SITE_KEY = required_env('TURNSTILE_SITE_KEY')
TURNSTILE_SECRET_KEY = required_env('TURNSTILE_SECRET_KEY')

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or CONTACT_EMAIL

# Storage (Cloudflare R2 or WhiteNoise)
if os.environ.get('CLOUDFLARE_R2_BUCKET_NAME'):
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'bucket_name': os.environ.get('CLOUDFLARE_R2_BUCKET_NAME'),
                'access_key': os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID'),
                'secret_key': os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY'),
                'endpoint_url': os.environ.get('CLOUDFLARE_R2_ENDPOINT_URL'),
                'custom_domain': os.environ.get('CLOUDFLARE_R2_CUSTOM_DOMAIN'),
                'querystring_auth': False,
                'default_acl': None,
                'signature_version': 's3v4',
                'region_name': 'auto',
            },
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
    if os.environ.get('CLOUDFLARE_R2_CUSTOM_DOMAIN'):
        MEDIA_URL = f"https://{os.environ.get('CLOUDFLARE_R2_CUSTOM_DOMAIN')}/"
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

# Security
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = 'DENY'

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'nonce-{csp_nonce}' https://challenges.cloudflare.com; "
    "font-src 'self' data:; "
    "media-src 'self' https:; "
    "frame-src https://challenges.cloudflare.com; "
    "form-action 'self'; "
    "connect-src 'self' https:; "
    "upgrade-insecure-requests;"
)

# Increase upload limits for MP3 files (50MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(levelname)s] %(asctime)s %(name)s: %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
