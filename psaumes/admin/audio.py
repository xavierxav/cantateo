from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from ..models import (
    PartitionAudioGenerationJob,
    PartitionAudioNormalizationJob,
    PartitionAudioTempoVariant,
    PartitionOmrJob,
)


class PartitionIdFilter(admin.SimpleListFilter):
    title = 'Partition'
    parameter_name = 'partition_id'

    def lookups(self, request, model_admin):
        return ()

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(partition_id=self.value())
        return queryset


class ReadOnlyOperationsAdmin(admin.ModelAdmin):
    """Read-only admin base for generated audio operational state."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return (
            super().has_view_permission(request, obj)
            or super().has_change_permission(request, obj)
        )


@admin.register(PartitionAudioGenerationJob)
class PartitionAudioGenerationJobAdmin(ReadOnlyOperationsAdmin):
    list_display = (
        'id',
        'partition_link',
        'status',
        'queue_priority',
        'attempts',
        'generated_count',
        'total_count',
        'missing_summary',
        'updated_at',
    )
    list_filter = (PartitionIdFilter, 'status', 'queue_priority', 'updated_at', 'queued_at')
    search_fields = (
        'partition__titre',
        'partition__psaume__nom_psaume',
        'partition__psaume__titre',
        'task_id',
        'last_error',
    )
    readonly_fields = (
        'partition_link',
        'status',
        'queue_priority',
        'task_id',
        'attempts',
        'generated_count',
        'total_count',
        'missing_voice_types',
        'last_error',
        'queued_at',
        'started_at',
        'finished_at',
        'updated_at',
    )
    fieldsets = (
        ('Partition', {'fields': ('partition_link',)}),
        ('Etat', {
            'fields': (
                'status',
                'queue_priority',
                'task_id',
                ('attempts', 'generated_count', 'total_count'),
                'missing_voice_types',
                'last_error',
            )
        }),
        ('Dates', {'fields': ('queued_at', 'started_at', 'finished_at', 'updated_at')}),
    )
    ordering = ('-updated_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('partition', 'partition__psaume')

    @admin.display(description='Partition')
    def partition_link(self, obj):
        if not obj.partition_id:
            return '-'
        url = reverse('admin:psaumes_partition_change', args=[obj.partition_id])
        return format_html('<a href="{}">{}</a>', url, obj.partition)

    @admin.display(description='Voix manquantes')
    def missing_summary(self, obj):
        return ', '.join(obj.missing_voice_types or []) or '-'


@admin.register(PartitionOmrJob)
class PartitionOmrJobAdmin(ReadOnlyOperationsAdmin):
    list_display = (
        'id',
        'partition_link',
        'status',
        'queue_priority',
        'backend',
        'model_profile',
        'attempts',
        'page_progress',
        'updated_at',
    )
    list_filter = (
        PartitionIdFilter,
        'status',
        'queue_priority',
        'backend',
        'model_profile',
        'updated_at',
        'queued_at',
    )
    search_fields = (
        'partition__titre',
        'partition__psaume__nom_psaume',
        'partition__psaume__titre',
        'source_name',
        'generated_file_name',
        'task_id',
        'last_error',
    )
    readonly_fields = (
        'partition_link',
        'source_type',
        'source_file',
        'source_name',
        'source_sha256',
        'backend',
        'backend_version',
        'model_profile',
        'status',
        'queue_priority',
        'task_id',
        'attempts',
        'page_count',
        'processed_pages',
        'generated_file_name',
        'last_error',
        'queued_at',
        'started_at',
        'finished_at',
        'updated_at',
    )
    fieldsets = (
        ('Partition', {'fields': ('partition_link',)}),
        ('Source', {'fields': ('source_type', 'source_file', 'source_name', 'source_sha256')}),
        ('Backend', {'fields': ('backend', 'backend_version', 'model_profile')}),
        ('Etat', {
            'fields': (
                'status',
                'queue_priority',
                'task_id',
                'attempts',
                ('processed_pages', 'page_count'),
                'generated_file_name',
                'last_error',
            )
        }),
        ('Dates', {'fields': ('queued_at', 'started_at', 'finished_at', 'updated_at')}),
    )
    ordering = ('-updated_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('partition', 'partition__psaume')

    @admin.display(description='Partition')
    def partition_link(self, obj):
        if not obj.partition_id:
            return '-'
        url = reverse('admin:psaumes_partition_change', args=[obj.partition_id])
        return format_html('<a href="{}">{}</a>', url, obj.partition)

    @admin.display(description='Pages')
    def page_progress(self, obj):
        if not obj.page_count:
            return '-'
        return f'{obj.processed_pages}/{obj.page_count}'


@admin.register(PartitionAudioTempoVariant)
class PartitionAudioTempoVariantAdmin(ReadOnlyOperationsAdmin):
    list_display = (
        'id',
        'partition_link',
        'voice_type',
        'tempo',
        'status',
        'queue_priority',
        'has_audio_file',
        'updated_at',
    )
    list_filter = (
        PartitionIdFilter,
        'status',
        'queue_priority',
        'tempo',
        'voice_type',
        'updated_at',
        'created_at',
    )
    search_fields = (
        'partition__titre',
        'partition__psaume__nom_psaume',
        'partition__psaume__titre',
        'last_error',
    )
    readonly_fields = (
        'partition_link',
        'voice_type',
        'tempo',
        'audio_file',
        'status',
        'queue_priority',
        'last_error',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        ('Partition', {'fields': ('partition_link',)}),
        ('Variante', {
            'fields': ('voice_type', 'tempo', 'audio_file', 'status', 'queue_priority', 'last_error'),
        }),
        ('Dates', {'fields': ('created_at', 'updated_at')}),
    )
    ordering = ('-updated_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('partition', 'partition__psaume')

    @admin.display(description='Partition')
    def partition_link(self, obj):
        if not obj.partition_id:
            return '-'
        url = reverse('admin:psaumes_partition_change', args=[obj.partition_id])
        return format_html('<a href="{}">{}</a>', url, obj.partition)

    @admin.display(description='Fichier')
    def has_audio_file(self, obj):
        return 'Oui' if obj.audio_file else '-'


@admin.register(PartitionAudioNormalizationJob)
class PartitionAudioNormalizationJobAdmin(ReadOnlyOperationsAdmin):
    list_display = (
        'id',
        'target_summary',
        'field_name',
        'status',
        'queue_priority',
        'attempts',
        'updated_at',
    )
    list_filter = (
        PartitionIdFilter,
        'target_type',
        'status',
        'queue_priority',
        'field_name',
        'updated_at',
        'queued_at',
    )
    search_fields = (
        'partition__titre',
        'partition__psaume__nom_psaume',
        'partition__psaume__titre',
        'tempo_variant__partition__titre',
        'source_name',
        'task_id',
        'last_error',
    )
    readonly_fields = (
        'target_summary',
        'target_type',
        'partition',
        'tempo_variant',
        'field_name',
        'source_name',
        'status',
        'queue_priority',
        'task_id',
        'attempts',
        'last_error',
        'queued_at',
        'started_at',
        'finished_at',
        'updated_at',
    )
    fieldsets = (
        ('Cible', {'fields': ('target_summary', 'target_type', 'partition', 'tempo_variant', 'field_name')}),
        ('Etat', {'fields': ('source_name', 'status', 'queue_priority', 'task_id', 'attempts', 'last_error')}),
        ('Dates', {'fields': ('queued_at', 'started_at', 'finished_at', 'updated_at')}),
    )
    ordering = ('-updated_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'partition',
            'partition__psaume',
            'tempo_variant',
            'tempo_variant__partition',
        )

    @admin.display(description='Cible')
    def target_summary(self, obj):
        if obj.partition_id:
            url = reverse('admin:psaumes_partition_change', args=[obj.partition_id])
            return format_html('<a href="{}">Partition {}</a>', url, obj.partition_id)
        if obj.tempo_variant_id:
            url = reverse('admin:psaumes_partitionaudiotempovariant_change', args=[obj.tempo_variant_id])
            return format_html('<a href="{}">Variante {}</a>', url, obj.tempo_variant_id)
        return '-'
