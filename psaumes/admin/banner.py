from django import forms
from django.contrib import admin
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html

from psaumes.models import SiteBanner
from psaumes.templatetags.banner_tags import banner_rich_text


class SiteBannerAdminForm(forms.ModelForm):
    class Meta:
        model = SiteBanner
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("La date de fin doit etre posterieure ou egale a la date de debut.")
        return cleaned_data


@admin.register(SiteBanner)
class SiteBannerAdmin(admin.ModelAdmin):
    form = SiteBannerAdminForm
    list_display = (
        'text_preview',
        'active',
        'effective_status',
        'start_date',
        'end_date',
        'updated_at',
    )
    list_editable = ('active',)
    list_filter = ('active', 'start_date', 'end_date')
    readonly_fields = ('rendered_preview', 'active_window_conflicts', 'updated_at')
    ordering = ('-updated_at',)
    fieldsets = (
        (None, {
            'fields': ('text', 'rendered_preview', 'active'),
            'description': (
                "Markdown sécurisé autorisé : **gras**, *italique*, liens [texte](/url), "
                "et icônes :info:, :warning:, :music:, :calendar:, :check:. "
                "Le HTML dangereux est supprimé."
            ),
        }),
        ('Periode (optionnel)', {'fields': (('start_date', 'end_date'), 'active_window_conflicts', 'updated_at')}),
    )

    def text_preview(self, obj):
        return obj.text[:80] + '...' if len(obj.text) > 80 else obj.text
    text_preview.short_description = 'Texte'

    @admin.display(description='Statut effectif')
    def effective_status(self, obj):
        if not obj.active:
            return self._colored_status('#6c757d', 'Inactif')
        today = timezone.localdate()
        if obj.start_date and obj.start_date > today:
            return self._colored_status('#0d6efd', 'Planifie')
        if obj.end_date and obj.end_date < today:
            return self._colored_status('#6c757d', 'Expire')
        return self._colored_status('#198754', 'Visible', bold=True)

    @admin.display(description='Apercu rendu')
    def rendered_preview(self, obj):
        if not obj or not obj.text:
            return '-'
        return format_html('<div style="padding: 8px; border-left: 4px solid #0d6efd;">{}</div>', banner_rich_text(obj.text))

    @admin.display(description='Conflits de periode active')
    def active_window_conflicts(self, obj):
        if not obj or not obj.pk or not obj.active:
            return '-'
        conflicts = SiteBanner.objects.filter(active=True).exclude(pk=obj.pk)
        if obj.start_date:
            conflicts = conflicts.filter(Q(end_date__isnull=True) | Q(end_date__gte=obj.start_date))
        if obj.end_date:
            conflicts = conflicts.filter(Q(start_date__isnull=True) | Q(start_date__lte=obj.end_date))
        count = conflicts.count()
        if not count:
            return 'Aucun conflit actif.'
        return format_html('<span style="color: #b42318;">{} autre(s) banniere(s) active(s) chevauchent cette periode.</span>', count)

    def _colored_status(self, color, label, bold=False):
        weight = '600' if bold else '400'
        return format_html('<span style="color: {}; font-weight: {};">{}</span>', color, weight, label)
