from .production import *

SECURE_SSL_REDIRECT = False

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
TURNSTILE_SITE_KEY = ''
TURNSTILE_SECRET_KEY = ''

STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'
