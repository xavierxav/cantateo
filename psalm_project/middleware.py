from django.conf import settings
from django.http import HttpResponsePermanentRedirect


DEV_REDIRECT_HOST = 'dev.cantateo.fr'


class RedirectLegacyHostsMiddleware:
    """Redirect legacy hostnames to the canonical site root."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '').split(':', 1)[0].lower()
        if host == DEV_REDIRECT_HOST:
            target = f'{settings.SITE_SCHEME}://{settings.SITE_DOMAIN}{request.get_full_path()}'
            return HttpResponsePermanentRedirect(target)

        return self.get_response(request)
