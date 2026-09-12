from django.db.models import Q
from django.utils import timezone

from psaumes.models import SiteBanner


def banner(request):
    today = timezone.localdate()
    try:
        active_banner = SiteBanner.objects.filter(
            active=True
        ).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=today)
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).get()
    except SiteBanner.DoesNotExist:
        active_banner = None
    return {'site_banner': active_banner}


def site_url(request):
    """Context processor to provide the full site URL."""
    from django.conf import settings
    return {
        'site_url': f"{settings.SITE_SCHEME}://{settings.SITE_DOMAIN}"
    }
