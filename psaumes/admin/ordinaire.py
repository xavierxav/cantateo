from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from ..models import Ordinaire
from ..models.partition import Partition


class OrdinairePartitionInline(admin.StackedInline):
    model = Partition
    extra = 1
    autocomplete_fields = ['compositeur']
    fields = ('partie_messe', 'titre', 'compositeur', 'partition_pdf', 'partition_mxl')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        titre_field = formset.form.base_fields.get('titre')
        if titre_field is not None:
            ordinaire_titre = obj.titre if obj else "Messe ..."
            titre_field.help_text = format_html(
                "Laisser vide pour générer automatiquement « {} — <Partie> ».",
                ordinaire_titre,
            )
        return formset


@admin.register(Ordinaire)
class OrdinaireAdmin(admin.ModelAdmin):
    list_display = ('titre', 'get_partitions_count', 'compositeur')
    search_fields = ('titre', 'description')
    prepopulated_fields = {'slug': ('titre',)}
    inlines = [OrdinairePartitionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'compositeur',
        ).annotate(
            partitions_total=Count('partitions_messe', distinct=True),
        )

    @admin.display(description='Partitions')
    def get_partitions_count(self, obj):
        return getattr(obj, 'partitions_total', obj.partitions_messe.count())
