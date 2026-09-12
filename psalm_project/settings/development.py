from .base import *
import sys

DEBUG = env_bool('DJANGO_DEBUG', True)

CELERY_TASK_ALWAYS_EAGER = env_bool('CELERY_TASK_ALWAYS_EAGER', True)
CELERY_TASK_EAGER_PROPAGATES = env_bool('CELERY_TASK_EAGER_PROPAGATES', CELERY_TASK_ALWAYS_EAGER)

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Storage - use R2 if credentials available, otherwise local filesystem
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
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
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
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

# Override for tests
if 'pytest' in sys.argv[0] or os.environ.get('PYTEST_CURRENT_TEST'):
    STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'

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
        'level': 'DEBUG',
    },
}
