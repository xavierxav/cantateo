import datetime
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils.text import slugify
from psaumes.models import Ordinaire, Partition, Psaume
from psaumes.models.partition import PartieMesse


class StaticPagesSitemap(Sitemap):
    """Sitemap for static pages (excluding homepage which now has date-specific noindex)."""
    changefreq = 'monthly'
    priority = 0.8

    def items(self):
        return [
            {'name': 'index', 'priority': 1.0, 'changefreq': 'daily'},
            {'name': 'histoire', 'priority': 0.7, 'changefreq': 'monthly'},
            {'name': 'blog', 'priority': 0.7, 'changefreq': 'monthly'},
            {'name': 'contact', 'priority': 0.6, 'changefreq': 'monthly'},
            {'name': 'confidentialite', 'priority': 0.4, 'changefreq': 'yearly'},
            {'name': 'mentions_legales', 'priority': 0.4, 'changefreq': 'yearly'},
            {'name': 'toutes_les_partitions', 'priority': 0.6, 'changefreq': 'weekly'},
            {'name': 'calendrier_liturgique', 'priority': 0.6, 'changefreq': 'weekly'},
        ]

    def location(self, item):
        return reverse(item['name'])

    def priority(self, item):
        return item.get('priority', 0.8)

    def changefreq(self, item):
        return item.get('changefreq', 'monthly')

    def lastmod(self, item):
        # La page d'accueil change quotidiennement (psaume du jour)
        if item['name'] == 'index':
            return datetime.date.today()
        return None


class PsaumeSitemap(Sitemap):
    """Sitemap for Psalms and Canticles with canonical URLs."""
    changefreq = 'yearly'
    priority = 0.8

    def items(self):
        return Psaume.objects.all()

    def location(self, obj):
        return obj.get_absolute_url()


class OrdinaireSitemap(Sitemap):
    """Sitemap for Ordinaires de messe with canonical URLs."""
    changefreq = 'yearly'
    priority = 0.8

    def items(self):
        return Ordinaire.objects.all()

    def location(self, obj):
        return obj.get_absolute_url()


class OrdinairePartieSitemap(Sitemap):
    """Sitemap des pages par partie d'ordinaire (une partition par URL)."""
    changefreq = 'yearly'
    priority = 0.7

    def items(self):
        return Partition.objects.filter(ordinaire__isnull=False, partie_messe__in=[
            c for c, _ in PartieMesse.choices]).select_related('ordinaire')

    def location(self, obj):
        return reverse('ordinaire_partie_detail', kwargs={
            'pk': obj.ordinaire_id, 'slug': obj.ordinaire.slug, 'partie': obj.partie_slug})
