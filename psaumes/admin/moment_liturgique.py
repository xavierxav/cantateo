from django import forms
from django.contrib import admin
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.urls import reverse
from django.utils.html import format_html

from ..models import MomentLiturgique
from ..services.search import normalize_search_query, normalized_trigram_expression

MOMENT_HELP_TEXT = """
<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 4px solid #007bff;">
    <strong>📅 Comment remplir :</strong><br>
    • <strong>DIMANCHE</strong> : Temps + Semaine + Jour=Dimanche + Année A/B/C (laisser Parité vide)<br>
    • <strong>SEMAINE</strong> : Temps + Semaine + Jour (Lun-Sam) + Parité (laisser Année vide)<br>
    • <strong>FÊTE</strong> : Nom de la fête + Année A/B/C seulement si fête cyclique
</div>
"""


class MomentLiturgiqueAdminForm(forms.ModelForm):
    TYPE_CHOICES = (
        ('dimanche', 'Dimanche'),
        ('semaine', 'Semaine'),
        ('fete', 'Fete'),
    )

    type_moment = forms.ChoiceField(
        choices=TYPE_CHOICES,
        required=False,
        label='Type de moment',
        help_text='Guide uniquement le formulaire admin. La validation du modele reste la reference.',
    )

    class Meta:
        model = MomentLiturgique
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['type_moment'].initial = self._infer_type(self.instance)
        else:
            self.fields['type_moment'].initial = 'dimanche'

    def _infer_type(self, instance):
        if instance.nom_fete:
            return 'fete'
        if instance.jour == 0:
            return 'dimanche'
        if instance.jour is not None and instance.jour > 0:
            return 'semaine'
        return 'dimanche'


class TypeMomentFilter(admin.SimpleListFilter):
    """Filtre personnalisé pour le type de moment liturgique."""
    title = 'Type de moment'
    parameter_name = 'type_moment'

    def lookups(self, request, model_admin):
        return (
            ('dimanche', 'Dimanche'),
            ('semaine', 'Semaine'),
            ('fete', 'Fête'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'dimanche':
            return queryset.filter(jour=0, nom_fete='')
        elif self.value() == 'semaine':
            return queryset.filter(jour__gt=0, nom_fete='')
        elif self.value() == 'fete':
            return queryset.exclude(nom_fete='')

class SansPsaumeFilter(admin.SimpleListFilter):
    """Filtre pour voir les moments avec ou sans psaume assigné."""
    title = 'Assignation'
    parameter_name = 'has_psaume'

    def lookups(self, request, model_admin):
        return (
            ('with', 'Avec psaume'),
            ('without', 'Sans psaume'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'with':
            return queryset.filter(psaume__isnull=False)
        elif self.value() == 'without':
            return queryset.filter(psaume__isnull=True)

class MomentLiturgiqueInline(admin.TabularInline):
    model = MomentLiturgique
    form = MomentLiturgiqueAdminForm
    extra = 1
    fields = (
        'type_moment',
        'temps',
        'semaine',
        'jour',
        'parite',
        'annee',
        'nom_fete',
        'moment_label',
        'assignment_status',
        'moment_edit_link',
    )
    readonly_fields = ('moment_label', 'assignment_status', 'moment_edit_link')
    can_delete = False
    show_change_link = True

    class Media:
        js = ('admin/js/moment_liturgique_type.js',)

    @admin.display(description='Moment')
    def moment_label(self, obj):
        return obj.nom_complet

    @admin.display(description='Type de moment')
    def get_type(self, obj):
        if obj.nom_fete:
            return format_html('<span style="color: {};">{}</span>', '#dc3545', 'Fete')
        if obj.jour == 0:
            return format_html('<span style="color: {};">{}</span>', '#007bff', 'Dimanche')
        return format_html('<span style="color: {};">{}</span>', '#28a745', 'Semaine')

    @admin.display(description='Assignation')
    def assignment_status(self, obj):
        return 'Avec psaume' if obj.psaume_id else 'Sans psaume'

    @admin.display(description='Modifier')
    def moment_edit_link(self, obj):
        if not obj.pk:
            return '-'
        url = reverse('admin:psaumes_momentliturgique_change', args=[obj.pk])
        return format_html('<a href="{}">Ouvrir</a>', url)

@admin.register(MomentLiturgique)
class MomentLiturgiqueAdmin(admin.ModelAdmin):
    form = MomentLiturgiqueAdminForm
    list_display = (
        'moment_label',
        'get_type',
        'get_psaume_link',
        'assignment_status',
        'get_partitions_count',
    )
    list_filter = ('temps', 'annee', 'parite', 'jour', TypeMomentFilter, SansPsaumeFilter)
    search_fields = ('nom_complet_recherche',)
    autocomplete_fields = ['psaume']
    ordering = ('temps', 'semaine', 'jour')

    fieldsets = (
        ('Psaume / Cantique', {
            'fields': ('psaume', 'get_psaume_edit_button'),
        }),
        ('Type de moment', {
            'description': MOMENT_HELP_TEXT,
            'fields': ('type_moment', 'temps', 'semaine', 'jour', 'parite', 'annee', 'nom_fete'),
        }),
        ('Administration', {
            'fields': ('nom_complet_recherche',),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('get_psaume_edit_button', 'nom_complet_recherche')

    class Media:
        js = ('admin/js/moment_liturgique_type.js',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('psaume').annotate(
            partitions_total=Count('psaume__partitions', distinct=True),
        )

    def get_search_results(self, request, queryset, search_term):
        use_distinct = False
        if not search_term:
            return queryset, use_distinct

        term_clean = normalize_search_query(search_term)
        if not term_clean:
            return queryset.none(), use_distinct

        queryset = queryset.annotate(
            moment_search=normalized_trigram_expression('nom_complet_recherche'),
            psaume_nom_search=normalized_trigram_expression('psaume__nom_psaume'),
            psaume_titre_search=normalized_trigram_expression('psaume__titre'),
        ).annotate(
            moment_similarity=TrigramWordSimilarity(term_clean, F('moment_search')),
            psaume_nom_similarity=TrigramWordSimilarity(term_clean, F('psaume_nom_search')),
            psaume_titre_similarity=TrigramWordSimilarity(term_clean, F('psaume_titre_search')),
        ).annotate(
            psaume_similarity=Greatest(
                Coalesce('psaume_nom_similarity', Value(0.0)),
                Coalesce('psaume_titre_similarity', Value(0.0)),
            ),
        ).annotate(
            search_priority=Case(
                When(moment_search__contains=term_clean, then=Value(0)),
                When(psaume_nom_search__contains=term_clean, then=Value(1)),
                When(psaume_titre_search__contains=term_clean, then=Value(1)),
                When(moment_similarity__gt=0.35, then=Value(2)),
                When(psaume_similarity__gt=0.35, then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            ),
            search_score=Greatest(
                Coalesce('moment_similarity', Value(0.0)),
                Coalesce('psaume_similarity', Value(0.0)),
            ),
        ).filter(
            Q(moment_search__contains=term_clean)
            | Q(psaume_nom_search__contains=term_clean)
            | Q(psaume_titre_search__contains=term_clean)
            | Q(moment_similarity__gt=0.35)
            | Q(psaume_similarity__gt=0.35)
        ).order_by(
            'search_priority',
            '-search_score',
            '-moment_similarity',
            '-psaume_nom_similarity',
            '-psaume_titre_similarity',
            'temps',
            'semaine',
            'jour',
            'pk',
        )

        return queryset, use_distinct

    @admin.display(description='Moment')
    def moment_label(self, obj):
        return obj.nom_complet

    @admin.display(description='Psaume')
    def get_psaume_link(self, obj):
        if not obj.psaume: return "-"
        url = reverse('admin:psaumes_psaume_change', args=[obj.psaume.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.psaume))

    @admin.display(description='Modifier')
    def get_psaume_edit_button(self, obj):
        if not obj.psaume: return "-"
        url = reverse('admin:psaumes_psaume_change', args=[obj.psaume.id])
        return format_html('<a href="{}" class="button">Modifier le psaume</a>', url)

    @admin.display(description='Partitions')
    def get_partitions_count(self, obj):
        if not obj.psaume: return "-"
        return getattr(obj, 'partitions_total', obj.psaume.partitions.count())

    @admin.display(description='Assignation')
    def assignment_status(self, obj):
        return 'Avec psaume' if obj.psaume_id else format_html('<span style="color: {};">{}</span>', '#b42318', 'Sans psaume')

    @admin.display(description='Type de moment')
    def get_type(self, obj):
        if obj.nom_fete:
            return format_html('<span style="color: {};">{}</span>', '#dc3545', 'Fete')
        if obj.jour == 0:
            return format_html('<span style="color: {};">{}</span>', '#007bff', 'Dimanche')
        return format_html('<span style="color: {};">{}</span>', '#28a745', 'Semaine')
