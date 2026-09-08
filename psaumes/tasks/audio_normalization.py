import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Partition, PartitionAudioNormalizationJob
from ..models.audio_variant import PartitionAudioTempoVariant
from ..services.audio.channels import (
    NORMALIZABLE_PARTITION_AUDIO_FIELDS,
    normalize_partition_audio_field,
    normalize_tempo_variant_audio_file,
    partition_field_needs_mono_normalization,
    tempo_variant_needs_mono_normalization,
)
from ..services.audio.tempo_variants import parse_apple_tempo
from .priorities import (
    AUDIO_QUEUE_PRIORITY_BULK,
    AUDIO_QUEUE_PRIORITY_USER,
    celery_priority_for_normalization,
    normalize_audio_queue_priority,
)

logger = logging.getLogger(__name__)


def _dispatch_audio_normalization(job_id, priority):
    return normalize_partition_audio.apply_async(
        args=(job_id,),
        priority=celery_priority_for_normalization(priority),
    )


def enqueue_partition_audio_normalization(partition, priority=AUDIO_QUEUE_PRIORITY_USER, detect=False):
    jobs = []
    for field_name in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
        job = enqueue_partition_audio_field_normalization(
            partition,
            field_name,
            priority=priority,
            detect=detect,
        )
        if job:
            jobs.append(job)
    return jobs


def enqueue_partition_audio_field_normalization(
    partition,
    field_name,
    priority=AUDIO_QUEUE_PRIORITY_USER,
    detect=False,
):
    if partition is None or field_name not in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
        return None
    field = getattr(partition, field_name)
    if not field:
        return None
    if detect and not partition_field_needs_mono_normalization(partition, field_name):
        return None
    return _enqueue_audio_normalization_job(
        target_type=PartitionAudioNormalizationJob.TargetType.PARTITION,
        source_name=field.name,
        priority=priority,
        partition=partition,
        field_name=field_name,
    )


def enqueue_tempo_variant_audio_normalization(
    variant,
    priority=AUDIO_QUEUE_PRIORITY_USER,
    detect=False,
):
    if variant is None or not variant.audio_file:
        return None
    if detect and not tempo_variant_needs_mono_normalization(variant):
        return None
    return _enqueue_audio_normalization_job(
        target_type=PartitionAudioNormalizationJob.TargetType.TEMPO_VARIANT,
        source_name=variant.audio_file.name,
        priority=priority,
        tempo_variant=variant,
        field_name='audio_file',
    )


def enqueue_partition_tempo_variant_normalizations(
    partition,
    tempo=None,
    priority=AUDIO_QUEUE_PRIORITY_USER,
    detect=False,
):
    queryset = PartitionAudioTempoVariant.objects.filter(partition=partition).exclude(audio_file='')
    if tempo is not None:
        queryset = queryset.filter(tempo=parse_apple_tempo(tempo))
    jobs = []
    for variant in queryset:
        job = enqueue_tempo_variant_audio_normalization(variant, priority=priority, detect=detect)
        if job:
            jobs.append(job)
    return jobs


def _enqueue_audio_normalization_job(
    *,
    target_type,
    source_name,
    priority,
    field_name,
    partition=None,
    tempo_variant=None,
):
    priority = normalize_audio_queue_priority(priority)
    lookup = (
        {'partition': partition, 'field_name': field_name}
        if target_type == PartitionAudioNormalizationJob.TargetType.PARTITION
        else {'tempo_variant': tempo_variant}
    )

    with transaction.atomic():
        job, _ = PartitionAudioNormalizationJob.objects.select_for_update().get_or_create(
            target_type=target_type,
            defaults={
                'partition': partition,
                'tempo_variant': tempo_variant,
                'field_name': field_name,
            },
            **lookup,
        )

        if (
            job.status == PartitionAudioNormalizationJob.Status.SUCCEEDED
            and job.source_name == source_name
        ):
            return None

        source_changed = bool(job.source_name and job.source_name != source_name)
        if job.status in {
            PartitionAudioNormalizationJob.Status.QUEUED,
            PartitionAudioNormalizationJob.Status.STARTED,
        }:
            update_fields = []
            if source_changed and job.status == PartitionAudioNormalizationJob.Status.QUEUED:
                job.source_name = source_name
                job.last_error = ''
                update_fields.extend(['source_name', 'last_error'])
            if (
                priority == AUDIO_QUEUE_PRIORITY_USER
                and job.status == PartitionAudioNormalizationJob.Status.QUEUED
                and job.queue_priority == AUDIO_QUEUE_PRIORITY_BULK
            ):
                job.queue_priority = AUDIO_QUEUE_PRIORITY_USER
                job.last_error = ''
                update_fields.extend(['queue_priority', 'last_error'])
            if update_fields:
                job.save(update_fields=[*set(update_fields), 'updated_at'])

                def _promote():
                    async_result = _dispatch_audio_normalization(job.pk, AUDIO_QUEUE_PRIORITY_USER)
                    PartitionAudioNormalizationJob.objects.filter(
                        pk=job.pk,
                        status=PartitionAudioNormalizationJob.Status.QUEUED,
                    ).update(
                        task_id=async_result.id,
                    )

                if priority == AUDIO_QUEUE_PRIORITY_USER:
                    transaction.on_commit(_promote)
            return job

        max_attempts = settings.AUDIO_NORMALIZATION_MAX_ATTEMPTS
        retry_delay = settings.AUDIO_NORMALIZATION_RETRY_DELAY_SECONDS
        if job.status == PartitionAudioNormalizationJob.Status.FAILED and not source_changed:
            if job.attempts >= max_attempts:
                logger.info(
                    "Skipping audio normalization job %s: max attempts reached",
                    job.pk,
                )
                return job
            if job.finished_at and (timezone.now() - job.finished_at).total_seconds() < retry_delay:
                logger.info(
                    "Skipping audio normalization job %s: retry backoff active",
                    job.pk,
                )
                return job

        job.target_type = target_type
        job.partition = partition
        job.tempo_variant = tempo_variant
        job.field_name = field_name
        job.source_name = source_name
        job.status = PartitionAudioNormalizationJob.Status.QUEUED
        job.queue_priority = priority
        if source_changed:
            job.attempts = 0
        job.attempts = job.attempts + 1
        job.last_error = ''
        job.started_at = None
        job.finished_at = None
        job.save()

        def _dispatch():
            async_result = _dispatch_audio_normalization(job.pk, priority)
            PartitionAudioNormalizationJob.objects.filter(pk=job.pk).update(task_id=async_result.id)

        transaction.on_commit(_dispatch)

    return job


@shared_task(bind=True, name='psaumes.normalize_partition_audio')
def normalize_partition_audio(self, job_id):
    request_id = self.request.id
    try:
        with transaction.atomic():
            job = PartitionAudioNormalizationJob.objects.select_for_update().get(pk=job_id)
            if request_id and job.task_id and job.task_id != request_id:
                logger.info(
                    "Skipping stale audio normalization task job=%s task=%s current_task=%s",
                    job_id,
                    request_id,
                    job.task_id,
                )
                return {'job_id': job_id, 'status': 'stale-task'}

            if job.status != PartitionAudioNormalizationJob.Status.QUEUED:
                return {'job_id': job_id, 'status': job.status}

            if request_id and not job.task_id:
                job.task_id = request_id

            current_source_name = _normalization_current_source_name(job)
            if job.source_name and current_source_name != job.source_name:
                job.status = PartitionAudioNormalizationJob.Status.SUCCEEDED
                job.last_error = 'Skipped: source file changed before normalization.'
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'task_id', 'last_error', 'finished_at', 'updated_at'])
                return {'job_id': job_id, 'status': job.status, 'skipped': True}

            job.status = PartitionAudioNormalizationJob.Status.STARTED
            job.started_at = timezone.now()
            job.save(update_fields=['status', 'task_id', 'started_at', 'updated_at'])
    except PartitionAudioNormalizationJob.DoesNotExist:
        logger.error("Audio normalization received unknown job id=%s", job_id)
        return {'job_id': job_id, 'status': 'missing-job'}

    job = PartitionAudioNormalizationJob.objects.select_related(
        'partition',
        'tempo_variant',
    ).get(pk=job_id)

    try:
        if job.target_type == PartitionAudioNormalizationJob.TargetType.PARTITION:
            if not job.partition_id:
                raise RuntimeError('Missing partition target')
            result = normalize_partition_audio_field(job.partition, job.field_name)
        else:
            if not job.tempo_variant_id:
                raise RuntimeError('Missing tempo variant target')
            result = normalize_tempo_variant_audio_file(job.tempo_variant)

        if result.missing_source:
            job.status = PartitionAudioNormalizationJob.Status.FAILED
            job.last_error = result.delete_error or 'Source file missing from storage.'
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
            return {
                'job_id': job.pk,
                'status': job.status,
                'missing_source': True,
                'old_name': result.old_name,
                'error': job.last_error,
            }

        job.status = PartitionAudioNormalizationJob.Status.SUCCEEDED
        job.last_error = result.delete_error or ''
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        return {
            'job_id': job.pk,
            'changed': result.changed,
            'skipped': result.skipped,
            'old_name': result.old_name,
            'new_name': result.new_name,
            'channels': result.channels,
            'delete_error': result.delete_error,
            'status': job.status,
        }
    except Exception as exc:
        logger.exception("Audio normalization failed for job %s", job_id)
        job.status = PartitionAudioNormalizationJob.Status.FAILED
        job.last_error = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        raise


def _normalization_current_source_name(job):
    if job.target_type == PartitionAudioNormalizationJob.TargetType.PARTITION:
        if not job.partition_id or not job.field_name:
            return ''
        value = (
            Partition.objects
            .filter(pk=job.partition_id)
            .values_list(job.field_name, flat=True)
            .first()
        )
        return value or ''
    if not job.tempo_variant_id:
        return ''
    value = (
        PartitionAudioTempoVariant.objects
        .filter(pk=job.tempo_variant_id)
        .values_list('audio_file', flat=True)
        .first()
    )
    return value or ''
