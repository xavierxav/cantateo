from django.conf import settings

from .backends.base import OmrBackendError
from .backends.homr_cli import HomrCliBackend


def get_omr_backend():
    backend_name = getattr(settings, 'OMR_BACKEND', 'homr_cli')
    if backend_name == HomrCliBackend.name:
        return HomrCliBackend()
    raise OmrBackendError(f'Unknown OMR backend: {backend_name}')
