from django.contrib import messages
from django.contrib import admin
from django import forms
from django.db.models import Case, FloatField, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.urls import reverse
from django.utils.html import format_html

from ..models import Partition
from ..models import Ordinaire
from ..services.search import annotate_trigram_similarity, normalize_search_query
from ..services.audio import get_missing_voices
from ..services.audio.channels import normalize_uploaded_partition_audio_fields
from ..tasks import reset_partition_audio_generation


SATB_AUDIO_FIELDS = ('audio_soprano', 'audio_alto', 'audio_tenor', 'audio_basse')
OPTIONAL_AUDIO_FIELDS = ('audio_instrumental', 'audio_mix')
SEARCH_SIMILARITY_THRESHOLD = 0.3


class PartitionAdminForm(forms.ModelForm):
    class Meta:
        model = Partition
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        titre_field = self.fields.get('titre')
        if titre_field is not None:
            ordinaire = self.initial.get('ordinaire')
            if ordinaire:
                try:
                    ordinaire_obj = Ordinaire.objects.get(pk=ordinaire)
                    titre_field.help_text = (
                        f"Laisser vide pour générer automatiquement « {ordinaire_obj.titre} — <Partie> »."
                    )
                except (Ordinaire.DoesNotExist, ValueError, TypeError):
                    pass
            else:
                titre_field.help_text = (
                    "Laisser vide pour générer automatiquement « <Messe> — <Partie> » "
                    "pour une partition d'ordinaire."
                )

    def save(self, commit=True):
        partition = super().save(commit=False)
        normalize_uploaded_partition_audio_fields(partition, self.changed_data)
        if commit:
            partition.save()
            self.save_m2m()
        return partition


def _has_file(obj, field_name):
    return bool(getattr(obj, field_name))


def _file_missing_q(field_name):
    return Q(**{field_name: ''}) | Q(**{f'{field_name}__isnull': True})


class MissingPdfFilter(admin.SimpleListFilter):
    title = 'PDF'
    parameter_name = 'pdf_status'

    def lookups(self, request, model_admin):
        return (
            ('present', 'Avec PDF'),
            ('missing', 'Sans PDF'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'present':
            return queryset.exclude(_file_missing_q('partition_pdf'))
        if self.value() == 'missing':
            return queryset.filter(_file_missing_q('partition_pdf'))
        return queryset


class MissingMxlFilter(admin.SimpleListFilter):
    title = 'MXL'
    parameter_name = 'mxl_status'

    def lookups(self, request, model_admin):
        return (
            ('present', 'Avec MXL'),
            ('missing', 'Sans MXL'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'present':
            return queryset.exclude(_file_missing_q('partition_mxl'))
        if self.value() == 'missing':
            return queryset.filter(_file_missing_q('partition_mxl'))
        return queryset


class SatbCompletenessFilter(admin.SimpleListFilter):
    title = 'Voix SATB'
    parameter_name = 'satb_status'

    def lookups(self, request, model_admin):
        return (
            ('complete', 'SATB complet'),
            ('partial', 'SATB incomplet'),
            ('none', 'Aucune voix'),
        )

    def queryset(self, request, queryset):
        missing_any = Q()
        present_any = Q()
        for field_name in SATB_AUDIO_FIELDS:
            missing_any |= _file_missing_q(field_name)
            present_any |= ~_file_missing_q(field_name)

        if self.value() == 'complete':
            for field_name in SATB_AUDIO_FIELDS:
                queryset = queryset.exclude(_file_missing_q(field_name))
            return queryset
        if self.value() == 'partial':
            return queryset.filter(missing_any & present_any)
        if self.value() == 'none':
            for field_name in SATB_AUDIO_FIELDS:
                queryset = queryset.filter(_file_missing_q(field_name))
            return queryset
        return queryset


class AudioGenerationStatusFilter(admin.SimpleListFilter):
    title = 'Generation audio'
    parameter_name = 'audio_job_status'

    def lookups(self, request, model_admin):
        return (
            ('none', 'Aucun job'),
            ('pending', 'Pending'),
            ('queued', 'Queued'),
            ('started', 'Started'),
            ('succeeded', 'Succeeded'),
            ('failed', 'Failed'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'none':
            return queryset.filter(audio_generation_job__isnull=True)
        if self.value():
            return queryset.filter(audio_generation_job__status=self.value())
        return queryset


class OmrGenerationStatusFilter(admin.SimpleListFilter):
    title = 'Reconnaissance OMR'
    parameter_name = 'omr_job_status'

    def lookups(self, request, model_admin):
        return (
            ('none', 'Aucun job'),
            ('pending', 'Pending'),
            ('queued', 'Queued'),
            ('started', 'Started'),
            ('succeeded', 'Succeeded'),
            ('failed', 'Failed'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'none':
            return queryset.filter(omr_job__isnull=True)
        if self.value():
            return queryset.filter(omr_job__status=self.value())
        return queryset


class PartitionInline(admin.StackedInline):
    model = Partition
    extra = 1
    autocomplete_fields = ['compositeur']
    show_change_link = True
    fieldsets = [
        ('Partition', {
            'fields': (
                'titre',
                'compositeur',
                'partition_pdf',
                'partition_mxl',
            ),
            'description': (
                "Un psaume peut avoir plusieurs partitions. Ajouter ici les sources, "
                "puis ouvrir la fiche partition pour les textes, audios et diagnostics complets."
            ),
        }),
        ('Diagnostic', {
            'fields': (
                'source_status',
                'audio_status',
                'partition_edit_link',
            ),
            'classes': ('collapse',),
        }),
    ]
    readonly_fields = (
        'source_status',
        'audio_status',
        'partition_edit_link',
    )
    can_delete = False

    @admin.display(description='Sources')
    def source_status(self, obj):
        return format_html(
            '{} / {}',
            self._status_text(obj.partition_pdf, 'PDF'),
            self._status_text(obj.partition_mxl, 'MXL'),
        )

    @admin.display(description='Audio')
    def audio_status(self, obj):
        satb_count = sum(1 for field_name in SATB_AUDIO_FIELDS if _has_file(obj, field_name))
        optional = [
            label
            for label, field_name in (('Instrumental', 'audio_instrumental'), ('Mix', 'audio_mix'))
            if _has_file(obj, field_name)
        ]
        suffix = f" + {', '.join(optional)}" if optional else ''
        synth = ' synth' if obj.mp3_synthetiques else ''
        return f'{satb_count}/4 SATB{suffix}{synth}'

    @admin.display(description='Modifier')
    def partition_edit_link(self, obj):
        if not obj.pk:
            return '-'
        url = reverse('admin:psaumes_partition_change', args=[obj.pk])
        return format_html('<a href="{}">Ouvrir</a>', url)

    def _status_text(self, file_field, label):
        return format_html(
            '<span style="color: {};">{}</span>',
            '#198754' if file_field else '#b42318',
            label if file_field else f'{label} manquant',
        )


@admin.register(Partition)
class PartitionAdmin(admin.ModelAdmin):
    """Admin for standalone musical partitions."""
    form = PartitionAdminForm
    autocomplete_fields = ['compositeur', 'psaume', 'ordinaire']
    list_display = (
        'titre',
        'psaume',
        'compositeur',
        'source_summary',
        'satb_summary',
        'optional_audio_summary',
        'synthetic_summary',
        'omr_job_summary',
        'audio_job_summary',
        'get_status',
    )
    list_filter = (
        MissingPdfFilter,
        MissingMxlFilter,
        SatbCompletenessFilter,
        'mp3_synthetiques',
        'partie_messe',
        OmrGenerationStatusFilter,
        AudioGenerationStatusFilter,
        'compositeur',
    )
    search_fields = (
        'titre',
        'refrain',
        'versets',
        'psaume__nom_psaume',
        'psaume__titre',
        'compositeur__nom',
    )
    actions = ['queue_audio_generation']
    readonly_fields = ('omr_job_detail', 'audio_job_detail', 'tempo_variants_link')
    fieldsets = [
        ('Identite', {'fields': ('psaume', 'ordinaire', 'partie_messe', 'titre', 'compositeur', 'slug')}),
        ('Textes', {'fields': ('refrain', 'versets'), 'classes': ('collapse',)}),
        ('Sources', {'fields': ('partition_pdf', 'partition_mxl')}),
        ('Reconnaissance OMR', {
            'fields': ('omr_job_detail',),
            'classes': ('collapse',),
        }),
        ('Audios MP3', {'fields': (
            'audio_soprano', 'audio_alto', 'audio_tenor', 'audio_basse', 
            'audio_instrumental', 'audio_mix'
        )}),
        ('Generation audio', {
            'fields': ('mp3_synthetiques', 'audio_job_detail', 'tempo_variants_link'),
            'classes': ('collapse',),
        }),
    ]
    prepopulated_fields = {'slug': ('titre',)}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'psaume',
            'compositeur',
            'audio_generation_job',
            'omr_job',
        )

    def get_search_results(self, request, queryset, search_term):
        use_distinct = False
        term_clean = normalize_search_query(search_term)
        if not term_clean:
            return queryset, use_distinct

        ranked = annotate_trigram_similarity(queryset, term_clean, 'titre', 'titre_similarity')
        ranked = annotate_trigram_similarity(
            ranked,
            term_clean,
            'psaume__nom_psaume',
            'psaume_nom_similarity',
        )
        ranked = annotate_trigram_similarity(
            ranked,
            term_clean,
            'psaume__titre',
            'psaume_titre_similarity',
        )
        ranked = annotate_trigram_similarity(ranked, term_clean, 'refrain', 'refrain_similarity')
        ranked = annotate_trigram_similarity(ranked, term_clean, 'versets', 'versets_similarity')
        ranked = annotate_trigram_similarity(
            ranked,
            term_clean,
            'compositeur__nom',
            'compositeur_similarity',
        )

        ranked = ranked.annotate(
            psaume_similarity=Greatest(
                Coalesce(F('psaume_nom_similarity'), Value(0.0)),
                Coalesce(F('psaume_titre_similarity'), Value(0.0)),
            ),
        ).annotate(
            search_priority=Case(
                When(titre_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=Value(1)),
                When(psaume_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=Value(2)),
                When(refrain_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=Value(3)),
                When(versets_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=Value(4)),
                When(compositeur_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=Value(5)),
                default=Value(99),
                output_field=IntegerField(),
            ),
            search_similarity=Case(
                When(titre_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=F('titre_similarity')),
                When(psaume_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=F('psaume_similarity')),
                When(refrain_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=F('refrain_similarity')),
                When(versets_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=F('versets_similarity')),
                When(compositeur_similarity__gte=SEARCH_SIMILARITY_THRESHOLD, then=F('compositeur_similarity')),
                default=Value(0.0),
                output_field=FloatField(),
            ),
        )

        return (
            ranked.filter(search_priority__lt=99).order_by(
                'search_priority',
                '-search_similarity',
                'titre',
                'pk',
            ),
            use_distinct,
        )

    @admin.display(description='Sources')
    def source_summary(self, obj):
        return format_html(
            '{} {}',
            self._badge('PDF', bool(obj.partition_pdf)),
            self._badge('MXL', bool(obj.partition_mxl)),
        )

    @admin.display(description='SATB')
    def satb_summary(self, obj):
        count = self._satb_count(obj)
        color = '#198754' if count == 4 else '#fd7e14' if count else '#b42318'
        return format_html('<strong style="color: {};">{}/4</strong>', color, count)

    @admin.display(description='Instr./Mix')
    def optional_audio_summary(self, obj):
        labels = []
        if obj.audio_instrumental:
            labels.append('Inst.')
        if obj.audio_mix:
            labels.append('Mix')
        return ', '.join(labels) if labels else '-'

    @admin.display(description='Synth.')
    def synthetic_summary(self, obj):
        return 'Oui' if obj.mp3_synthetiques else '-'

    @admin.display(description='Job OMR')
    def omr_job_summary(self, obj):
        job = getattr(obj, 'omr_job', None)
        if not job:
            return '-'
        color = {
            'succeeded': '#198754',
            'failed': '#b42318',
            'queued': '#0d6efd',
            'started': '#0d6efd',
            'pending': '#6c757d',
        }.get(job.status, '#6c757d')
        url = reverse('admin:psaumes_partitionomrjob_change', args=[job.pk])
        return format_html('<a href="{}" style="color: {}; font-weight: 600;">{}</a>', url, color, job.status)

    @admin.display(description='Job OMR')
    def omr_job_detail(self, obj):
        job = getattr(obj, 'omr_job', None)
        if not obj.pk:
            return '-'
        if not job:
            return 'Aucun job OMR.'
        url = reverse('admin:psaumes_partitionomrjob_change', args=[job.pk])
        progress = f'{job.processed_pages}/{job.page_count}' if job.page_count else '-'
        error = f' - erreur: {job.last_error}' if job.last_error else ''
        return format_html(
            '<a href="{}">{} #{}</a> - backend: {} - pages: {}{}',
            url,
            job.status,
            job.pk,
            job.backend or '-',
            progress,
            error,
        )

    @admin.display(description='Job audio')
    def audio_job_summary(self, obj):
        job = getattr(obj, 'audio_generation_job', None)
        if not job:
            return '-'
        color = {
            'succeeded': '#198754',
            'failed': '#b42318',
            'queued': '#0d6efd',
            'started': '#0d6efd',
            'pending': '#6c757d',
        }.get(job.status, '#6c757d')
        url = reverse('admin:psaumes_partitionaudiogenerationjob_change', args=[job.pk])
        return format_html('<a href="{}" style="color: {}; font-weight: 600;">{}</a>', url, color, job.status)

    @admin.display(description='Job audio')
    def audio_job_detail(self, obj):
        job = getattr(obj, 'audio_generation_job', None)
        if not obj.pk:
            return '-'
        if not job:
            return 'Aucun job audio.'
        url = reverse('admin:psaumes_partitionaudiogenerationjob_change', args=[job.pk])
        missing = ', '.join(job.missing_voice_types or []) or '-'
        return format_html(
            '<a href="{}">{} #{}</a> - tentatives: {} - voix manquantes: {}',
            url,
            job.status,
            job.pk,
            job.attempts,
            missing,
        )

    @admin.display(description='Variantes tempo')
    def tempo_variants_link(self, obj):
        if not obj.pk:
            return '-'
        url = (
            reverse('admin:psaumes_partitionaudiotempovariant_changelist')
            + f'?partition_id={obj.pk}'
        )
        return format_html('<a href="{}">Voir les variantes Apple/Safari</a>', url)

    @admin.display(description='Statut')
    def get_status(self, obj):
        voix_count = self._satb_count(obj)
        is_synth = obj.mp3_synthetiques
        has_pdf = bool(obj.partition_pdf)
        has_mxl = bool(obj.partition_mxl)

        if voix_count >= 4 and has_pdf and has_mxl:
            status = '✅ Complet'
            if is_synth: status += ' (synth)'
            return format_html('<span style="color: #28a745; font-weight: bold;">{}</span>', status)
        
        missing = []
        if voix_count < 4: missing.append(f'{voix_count}/4 voix')
        if not has_pdf: missing.append('PDF')
        if not has_mxl: missing.append('MXL')
        return format_html('<span style="color: #fd7e14; font-weight: bold;">⚠️ {}</span>', ', '.join(missing))

    @admin.action(description='Relancer la génération audio synthétique')
    def queue_audio_generation(self, request, queryset):
        queued = 0
        skipped_no_mxl = 0
        skipped_complete = 0
        skipped_other = 0
        for partition in queryset:
            if not partition.partition_mxl:
                skipped_no_mxl += 1
                continue
            if not get_missing_voices(partition):
                skipped_complete += 1
                continue
            job = reset_partition_audio_generation(partition)
            if job:
                queued += 1
            else:
                skipped_other += 1
        self.message_user(
            request,
            (
                f'{queued} partition(s) mises en file. '
                f'{skipped_no_mxl} sans MXL, {skipped_complete} deja completes, '
                f'{skipped_other} ignorees.'
            ),
            level=messages.INFO,
        )

    def _satb_count(self, obj):
        return sum(1 for field in SATB_AUDIO_FIELDS if getattr(obj, field))

    def _badge(self, label, present):
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            '#198754' if present else '#b42318',
            label if present else f'{label} -',
        )
