import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Partition, PartitionAudioGenerationJob
from ..services.audio import generate_missing_voices_for_chant, get_missing_voices
from .priorities import (
    AUDIO_QUEUE_PRIORITY_BULK,
    AUDIO_QUEUE_PRIORITY_USER,
    celery_priority_for,
    normalize_audio_queue_priority,
)

logger = logging.getLogger(__name__)


def _dispatch_partition_audio_generation(partition_id, priority):
    return generate_partition_audio.apply_async(
        args=(partition_id,),
        priority=celery_priority_for(priority),
    )


def build_partition_audio_status(partition):
    voices = partition.get_audio_list()
    missing_voice_types = get_missing_voices(partition) if partition.partition_mxl else []

    try:
        job = partition.audio_generation_job
    except PartitionAudioGenerationJob.DoesNotExist:
        job = None

    running_statuses = {
        PartitionAudioGenerationJob.Status.QUEUED,
        PartitionAudioGenerationJob.Status.STARTED,
    }
    terminal_statuses = {
        PartitionAudioGenerationJob.Status.SUCCEEDED,
        PartitionAudioGenerationJob.Status.FAILED,
    }
    is_generating = bool(job and job.status in running_statuses)

    current = job.generated_count if job else len(voices)
    total = job.total_count if job else (4 if partition.partition_mxl else len(voices))
    status = job.status if job else ('idle' if missing_voice_types else 'succeeded')
    attempts = job.attempts if job else 0
    task_id = job.task_id if job else ''
    error = job.last_error if job else ''
    queued_at = job.queued_at if job else None
    started_at = job.started_at if job else None
    finished_at = job.finished_at if job else None
    job_missing = job.missing_voice_types if job and job.missing_voice_types is not None else missing_voice_types

    generation_complete = (
        status in terminal_statuses
        or (not missing_voice_types and not is_generating)
        or not partition.partition_mxl
    )

    return {
        'partition_id': partition.id,
        'voices': voices,
        'is_generating': is_generating,
        'has_mxl': bool(partition.partition_mxl),
        'has_non_synthetic': bool(voices) and not partition.mp3_synthetiques,
        'generation_complete': generation_complete,
        'status': status,
        'task_id': task_id,
        'queue_priority': job.queue_priority if job else None,
        'attempts': attempts,
        'missing_voice_types': list(job_missing),
        'error': error,
        'queued_at': queued_at.isoformat() if queued_at else None,
        'started_at': started_at.isoformat() if started_at else None,
        'finished_at': finished_at.isoformat() if finished_at else None,
        'progress': {
            'current': current,
            'total': total,
            'label': f"{current}/{total} voix" if is_generating else None,
        },
    }


def enqueue_partition_audio_generation(partition, priority=AUDIO_QUEUE_PRIORITY_USER):
    if partition is None or not partition.partition_mxl:
        return None

    priority = normalize_audio_queue_priority(priority)
    missing_voice_types = get_missing_voices(partition)
    voices = partition.get_audio_list()

    if not missing_voice_types:
        job, _ = PartitionAudioGenerationJob.objects.update_or_create(
            partition=partition,
            defaults={
                'status': PartitionAudioGenerationJob.Status.SUCCEEDED,
                'queue_priority': priority,
                'task_id': '',
                'generated_count': len(voices),
                'total_count': len(voices),
                'missing_voice_types': [],
                'last_error': '',
                'started_at': timezone.now(),
                'finished_at': timezone.now(),
            },
        )
        return job

    if not partition.mp3_synthetiques and voices:
        return None

    with transaction.atomic():
        job, _ = PartitionAudioGenerationJob.objects.select_for_update().get_or_create(
            partition=partition,
        )

        if job.status in {
            PartitionAudioGenerationJob.Status.QUEUED,
            PartitionAudioGenerationJob.Status.STARTED,
        }:
            if (
                priority == AUDIO_QUEUE_PRIORITY_USER
                and job.status == PartitionAudioGenerationJob.Status.QUEUED
                and job.queue_priority == AUDIO_QUEUE_PRIORITY_BULK
            ):
                job.queue_priority = AUDIO_QUEUE_PRIORITY_USER
                job.last_error = ''
                job.save(update_fields=['queue_priority', 'last_error', 'updated_at'])

                def _promote():
                    async_result = _dispatch_partition_audio_generation(
                        partition.id,
                        AUDIO_QUEUE_PRIORITY_USER,
                    )
                    PartitionAudioGenerationJob.objects.filter(pk=job.pk).update(
                        task_id=async_result.id,
                    )

                transaction.on_commit(_promote)
            return job

        max_attempts = settings.AUDIO_GENERATION_MAX_ATTEMPTS
        retry_delay = settings.AUDIO_GENERATION_RETRY_DELAY_SECONDS
        if job.status == PartitionAudioGenerationJob.Status.FAILED:
            if job.attempts >= max_attempts:
                logger.info(
                    "Skipping audio generation for partition %s: max attempts reached",
                    partition.id,
                )
                return job
            if job.finished_at and (timezone.now() - job.finished_at).total_seconds() < retry_delay:
                logger.info(
                    "Skipping audio generation for partition %s: retry backoff active",
                    partition.id,
                )
                return job

        job.status = PartitionAudioGenerationJob.Status.QUEUED
        job.queue_priority = priority
        job.attempts = job.attempts + 1
        job.generated_count = 0
        job.total_count = len(missing_voice_types)
        job.missing_voice_types = list(missing_voice_types)
        job.last_error = ''
        job.started_at = None
        job.finished_at = None
        job.save()

        def _dispatch():
            async_result = _dispatch_partition_audio_generation(partition.id, priority)
            PartitionAudioGenerationJob.objects.filter(pk=job.pk).update(task_id=async_result.id)

        transaction.on_commit(_dispatch)

    return job


def reset_partition_audio_generation(partition):
    """Reset generation guardrails so an admin can manually retry a partition."""
    if partition is None:
        return None

    PartitionAudioGenerationJob.objects.update_or_create(
        partition=partition,
        defaults={
            'status': PartitionAudioGenerationJob.Status.PENDING,
            'queue_priority': AUDIO_QUEUE_PRIORITY_USER,
            'task_id': '',
            'attempts': 0,
            'generated_count': 0,
            'total_count': 0,
            'missing_voice_types': [],
            'last_error': '',
            'started_at': None,
            'finished_at': None,
        },
    )
    return enqueue_partition_audio_generation(partition)


@shared_task(bind=True, name='psaumes.generate_partition_audio')
def generate_partition_audio(self, partition_id):
    try:
        partition = Partition.objects.get(pk=partition_id)
    except Partition.DoesNotExist:
        logger.error("Audio job received unknown partition id=%s", partition_id)
        return {'partition_id': partition_id, 'status': 'missing-partition'}

    try:
        job = partition.audio_generation_job
    except PartitionAudioGenerationJob.DoesNotExist:
        job = PartitionAudioGenerationJob.objects.create(
            partition=partition,
            status=PartitionAudioGenerationJob.Status.QUEUED,
        )

    if self.request.id and job.task_id != self.request.id:
        job.task_id = self.request.id
        job.save(update_fields=['task_id', 'updated_at'])

    missing_voice_types = get_missing_voices(partition) if partition.partition_mxl else []
    if not missing_voice_types:
        voices = partition.get_audio_list()
        job.status = PartitionAudioGenerationJob.Status.SUCCEEDED
        job.generated_count = len(voices)
        job.total_count = len(voices)
        job.missing_voice_types = []
        job.last_error = ''
        job.started_at = job.started_at or timezone.now()
        job.finished_at = timezone.now()
        job.save()
        return {
            'partition_id': partition.id,
            'generated_count': 0,
            'missing_voice_types': [],
            'status': job.status,
        }

    job.status = PartitionAudioGenerationJob.Status.STARTED
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at', 'updated_at'])

    try:
        generated_count = generate_missing_voices_for_chant(partition)
        partition.refresh_from_db()
        missing_voice_types = get_missing_voices(partition) if partition.partition_mxl else []

        job.generated_count = generated_count
        job.total_count = max(job.total_count, generated_count + len(missing_voice_types))
        job.missing_voice_types = list(missing_voice_types)
        job.last_error = ''
        job.finished_at = timezone.now()
        job.status = (
            PartitionAudioGenerationJob.Status.SUCCEEDED
            if not missing_voice_types
            else PartitionAudioGenerationJob.Status.FAILED
        )
        job.save()

        return {
            'partition_id': partition.id,
            'generated_count': generated_count,
            'missing_voice_types': missing_voice_types,
            'status': job.status,
        }
    except Exception as exc:
        logger.exception("Audio generation failed for partition %s", partition_id)
        job.status = PartitionAudioGenerationJob.Status.FAILED
        job.last_error = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        raise
