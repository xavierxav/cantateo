from django.conf import settings
from django.utils.crypto import get_random_string


class ContentSecurityPolicyMiddleware:
    """Attach a project-owned CSP header when configured.

    Django 5.2 in this environment does not ship the built-in CSP middleware,
    so keep the behavior small and explicit until the project can move to the
    framework implementation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = get_random_string(24)
        response = self.get_response(request)
        policy = getattr(settings, 'CONTENT_SECURITY_POLICY', '').strip()
        if policy and 'Content-Security-Policy' not in response:
            policy = policy.replace('{csp_nonce}', request.csp_nonce)
            response['Content-Security-Policy'] = policy
        return response
