import re
from django.contrib import admin
from django.db.models import Q, Count
from ..models import Psaume
from .partition import PartitionInline
from .moment_liturgique import MomentLiturgiqueInline
from ..services.search import annotate_trigram_similarity, normalize_search_query

@admin.register(Psaume)
class PsaumeAdmin(admin.ModelAdmin):
    list_display = ('nom_psaume', 'titre', 'psaume_or_cantique', 'get_partitions_count', 'get_moments_count')
    list_filter = ('psaume_or_cantique',)
    search_fields = ('nom_complet_recherche',)
    inlines = [PartitionInline, MomentLiturgiqueInline]
    
    fieldsets = (
        ('Informations liturgiques', {
            'fields': ('psaume_or_cantique', 'nom_psaume', 'titre')
        }),
        ('Administration', {
            'fields': ('slug', 'nom_complet_recherche'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('slug', 'nom_complet_recherche')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            partitions_total=Count('partitions', distinct=True),
            moments_total=Count('moments_liturgiques', distinct=True),
        )

    def get_search_results(self, request, queryset, search_term):
        use_distinct = False
        if not search_term:
            return queryset, use_distinct

        term_clean = normalize_search_query(search_term)
        
        # 1. Recherche par numéro dans le nom (ex: "ps 12" ou "12")
        if term_clean.isdigit() or (re.match(r'^(?:psaume?|ps\.?|psalm)\s*\d+$', term_clean)):
            numero_match = re.search(r'(\d+)', term_clean)
            if numero_match:
                # On cherche à la fois le numéro seul et avec le préfixe "Psaume"
                nb = numero_match.group(1)
                return queryset.filter(
                    Q(nom_psaume__icontains=f"Psaume {nb}") | 
                    Q(nom_psaume__icontains=nb)
                ), False

        # 2. Recherche Trigram sur le champ consolidé
        queryset = annotate_trigram_similarity(
            queryset,
            term_clean,
        ).filter(similarity__gt=0.3).order_by('-similarity')
        
        return queryset, False

    @admin.display(description='Partitions')
    def get_partitions_count(self, obj):
        return getattr(obj, 'partitions_total', obj.partitions.count())

    @admin.display(description='Moments')
    def get_moments_count(self, obj):
        total = getattr(obj, 'moments_total', obj.moments_liturgiques.count())
        return total if total > 0 else "-"
