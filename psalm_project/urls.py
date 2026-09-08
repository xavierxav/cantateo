"""
URL configuration for psalm_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.core.cache import caches
from django.db import connections
from django.contrib.sitemaps.views import sitemap
from django.http import JsonResponse
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.http import require_GET
import os

from psaumes.sitemaps import StaticPagesSitemap, PsaumeSitemap, OrdinaireSitemap, OrdinairePartieSitemap
from psaumes import views as psaumes_views

sitemaps = {
    'static': StaticPagesSitemap,
    'psaumes': PsaumeSitemap,
    'ordinaires': OrdinaireSitemap,
    'ordinaires_parties': OrdinairePartieSitemap,
}


@require_GET
def healthz(request):
    database_ok = True
    cache_ok = True

    try:
        connections['default'].ensure_connection()
    except Exception:
        database_ok = False

    try:
        cache = caches['default']
        cache_key = 'healthz-check'
        cache.set(cache_key, 'ok', 5)
        if cache.get(cache_key) != 'ok':
            cache_ok = False
    except Exception:
        cache_ok = False

    payload = {
        'status': 'ok' if database_ok and cache_ok else 'degraded',
        'database': 'ok' if database_ok else 'error',
        'cache': 'ok' if cache_ok else 'error',
    }
    return JsonResponse(payload, status=200 if payload['status'] == 'ok' else 503)


urlpatterns = [
    path('admin/saisie/', psaumes_views.simplified_dashboard, name='simplified_dashboard'),
    path('admin/saisie/messages/', psaumes_views.simplified_banner_list, name='simplified_banner_list'),
    path('admin/saisie/messages/nouveau/', psaumes_views.simplified_banner_create, name='simplified_banner_create'),
    path('admin/saisie/messages/<int:banner_id>/modifier/', psaumes_views.simplified_banner_update, name='simplified_banner_update'),
    path('admin/saisie/messages/<int:banner_id>/supprimer/', psaumes_views.simplified_banner_delete, name='simplified_banner_delete'),
    path('admin/saisie/partitions/nouvelle/moments/', psaumes_views.simplified_partition_moments, name='simplified_partition_moments'),
    path('admin/saisie/partitions/nouvelle/fichiers/', psaumes_views.simplified_partition_files, name='simplified_partition_files'),
    path('admin/saisie/partitions/nouvelle/termine/<int:partition_id>/', psaumes_views.simplified_partition_done, name='simplified_partition_done'),
    path('admin/', admin.site.urls),
    path('healthz/', healthz, name='healthz'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('', include('psaumes.urls')),
]

# Gestion des fichiers statiques racines et media en développement
if settings.DEBUG:
    from django.views.static import serve
    
    urlpatterns += [
        path('robots.txt', serve, {'document_root': os.path.join(settings.BASE_DIR, 'static'), 'path': 'robots.txt'}),
        path('favicon.ico', RedirectView.as_view(url='/static/icons/icon-192.png', permanent=True)),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
