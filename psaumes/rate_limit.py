import hashlib

from django.conf import settings
from django.core.cache import cache


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',', 1)[0].strip()
    return request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')


def is_rate_limited(request, scope):
    limit, window = settings.RATE_LIMITS.get(scope, (0, 0))
    if limit <= 0 or window <= 0:
        return False

    identity = get_client_ip(request) or 'unknown'
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
    key = f'rate-limit:{scope}:{digest}'

    added = cache.add(key, 1, timeout=window)
    if added:
        return False

    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False

    return count > limit
