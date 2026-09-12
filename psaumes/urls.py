from django.urls import path, re_path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('histoire/', views.histoire, name='histoire'),
    path('blog/', views.blog, name='blog'),
    path('contact/', views.contact, name='contact'),
    path('confidentialite/', views.confidentialite, name='confidentialite'),
    path('mentions-legales/', views.mentions_legales, name='mentions_legales'),
    
    # Old redirects
    path('qui-sommes-nous/', RedirectView.as_view(pattern_name='histoire', permanent=True)),
    path('histoire-technique/', RedirectView.as_view(pattern_name='blog', permanent=True)),
    re_path(r'^psaumes/14[56]-beni-sois-tu-seigneur/?$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^book-online/?$', RedirectView.as_view(url='/', permanent=True)),
    
    # Bulk redirects for old site URLs (Wix, etc.) - Moved to end of file to avoid collisions

    path('ecoute-aleatoire/', views.ecoute_aleatoire, name='ecoute_aleatoire'),
    path('download/pdf/<int:partition_id>/', views.download_pdf, name='download_pdf'),
    path('download/audio/<int:partition_id>/<str:voice_type>/', views.download_audio, name='download_audio'),
    path('api/audio-status/<int:partition_id>/', views.audio_status, name='audio_status'),
    path('api/audio-variants/<int:partition_id>/', views.audio_variants, name='audio_variants'),

    # Canonical detail pages (SEO)
    path('psaumes/<int:pk>-<slug:slug>/', views.psaume_detail, name='psaume_detail'),
    path('cantiques/<int:pk>-<slug:slug>/', views.cantique_detail, name='cantique_detail'),

    # Ordinaires de messe (Kyrie, Gloria, Sanctus, Agnus Dei...)
    path('ordinaires-de-messe/', views.ordinaire_list, name='ordinaire_list'),
    path('ordinaires-de-messe/<int:pk>-<slug:slug>/', views.ordinaire_detail, name='ordinaire_detail'),
    path('ordinaires-de-messe/<int:pk>-<slug:slug>/<slug:partie>/',
         views.ordinaire_partie_detail, name='ordinaire_partie_detail'),

    # Autocomplete search API
    path('api/search-autocomplete/', views.search_autocomplete, name='search_autocomplete'),

    # Index pages for SEO internal linking
    path('toutes-les-partitions/', views.toutes_les_partitions, name='toutes_les_partitions'),
    path('calendrier-liturgique/', views.calendrier_liturgique, name='calendrier_liturgique'),

    # Bulk redirects for old site URLs (Wix, etc.)
    # Placed at the end to ensure canonical pages (above) take precedence.
    re_path(r'^psaume-[ac]-dimanche-et-fete(-[12])?(/.*)?$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^psaumes-[abc]-dimanche-fetes?(/.*)?$', RedirectView.as_view(url='/', permanent=True)),
    # Specifically catch Wix-style psaumes (ps-xxx or ex-xxx) and the old index
    re_path(r'^psaumes/(ps-|ex-|[0-9]{2,}-).*$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^psaumes/?$', RedirectView.as_view(url='/', permanent=True)), # Root of old psaumes (safe as we have no index there)
    re_path(r'^properties(/.*)?$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^album(/.*)?$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^_files(/.*)?$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^copie-de-menu-.*$', RedirectView.as_view(url='/', permanent=True)),
    re_path(r'^fil-actualit.+-cantateo$', RedirectView.as_view(url='/', permanent=True)),
]
