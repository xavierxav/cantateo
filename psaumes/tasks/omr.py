import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Partition, PartitionOmrJob
from ..services.omr import fingerprint_partition_omr_source, generate_musicxml_for_partition
from ..services.omr.sources import OmrSourceError
from .audio_generation import enqueue_partition_audio_generation
from .priorities import (
    OMR_QUEUE_PRIORITY_BULK,
    OMR_QUEUE_PRIORITY_USER,
    celery_priority_for_omr,
    normalize_omr_queue_priority,
)

logger = logging.getLogger(__name__)


def _dispatch_partition_omr_generation(partition_id, priority):
    return generate_partition_mxl.apply_async(
        args=(partition_id,),
        priority=celery_priority_for_omr(priority),
    )


def enqueue_partition_omr_generation(partition, priority=OMR_QUEUE_PRIORITY_USER, force=False):
    if partition is None or not partition.partition_pdf or partition.partition_mxl:
        return None

    priority = normalize_omr_queue_priority(priority)
    backend = settings.OMR_BACKEND
    model_profile = settings.OMR_MODEL_PROFILE

    try:
        fingerprint = fingerprint_partition_omr_source(partition)
    except OmrSourceError as exc:
        job, _ = PartitionOmrJob.objects.update_or_create(
            partition=partition,
            defaults={
                'status': PartitionOmrJob.Status.FAILED,
                'queue_priority': priority,
                'backend': backend,
                'model_profile': model_profile,
                'last_error': str(exc),
                'finished_at': timezone.now(),
            },
        )
        return job

    with transaction.atomic():
        job, _ = PartitionOmrJob.objects.select_for_update().get_or_create(
            partition=partition,
            defaults={
                'source_type': PartitionOmrJob.SourceType.PARTITION_PDF,
            },
        )

        source_changed = bool(job.source_sha256 and job.source_sha256 != fingerprint.sha256)
        if job.status in {PartitionOmrJob.Status.QUEUED, PartitionOmrJob.Status.STARTED}:
            if not source_changed:
                if (
                    priority == OMR_QUEUE_PRIORITY_USER
                    and job.status == PartitionOmrJob.Status.QUEUED
                    and job.queue_priority == OMR_QUEUE_PRIORITY_BULK
                ):
                    job.queue_priority = OMR_QUEUE_PRIORITY_USER
                    job.last_error = ''
                    job.save(update_fields=['queue_priority', 'last_error', 'updated_at'])

                    def _promote():
                        async_result = _dispatch_partition_omr_generation(
                            partition.id,
                            OMR_QUEUE_PRIORITY_USER,
                        )
                        PartitionOmrJob.objects.filter(pk=job.pk).update(
                            task_id=async_result.id,
                        )

                    transaction.on_commit(_promote)
                return job

            if job.status == PartitionOmrJob.Status.STARTED:
                return job

        max_attempts = settings.OMR_MAX_ATTEMPTS
        retry_delay = settings.OMR_RETRY_DELAY_SECONDS
        if job.status == PartitionOmrJob.Status.FAILED and not force and not source_changed:
            if job.attempts >= max_attempts:
                logger.info(
                    "Skipping OMR generation for partition %s: max attempts reached",
                    partition.id,
                )
                return job
            if job.finished_at and (timezone.now() - job.finished_at).total_seconds() < retry_delay:
                logger.info(
                    "Skipping OMR generation for partition %s: retry backoff active",
                    partition.id,
                )
                return job

        job.source_type = PartitionOmrJob.SourceType.PARTITION_PDF
        job.source_name = fingerprint.name
        job.source_sha256 = fingerprint.sha256
        job.backend = backend
        job.backend_version = ''
        job.model_profile = model_profile
        job.status = PartitionOmrJob.Status.QUEUED
        job.queue_priority = priority
        if source_changed or force:
            job.attempts = 0
        job.attempts = job.attempts + 1
        job.page_count = 0
        job.processed_pages = 0
        job.generated_file_name = ''
        job.last_error = ''
        job.started_at = None
        job.finished_at = None
        job.save()

        def _dispatch():
            async_result = _dispatch_partition_omr_generation(partition.id, priority)
            PartitionOmrJob.objects.filter(pk=job.pk).update(task_id=async_result.id)

        transaction.on_commit(_dispatch)

    return job


def reset_partition_omr_generation(partition):
    if partition is None:
        return None

    PartitionOmrJob.objects.update_or_create(
        partition=partition,
        defaults={
            'status': PartitionOmrJob.Status.PENDING,
            'queue_priority': OMR_QUEUE_PRIORITY_USER,
            'task_id': '',
            'attempts': 0,
            'page_count': 0,
            'processed_pages': 0,
            'generated_file_name': '',
            'last_error': '',
            'started_at': None,
            'finished_at': None,
        },
    )
    return enqueue_partition_omr_generation(partition, force=True)


def build_partition_omr_status(partition):
    try:
        job = partition.omr_job
    except PartitionOmrJob.DoesNotExist:
        job = None

    if not job:
        return {
            'partition_id': partition.id,
            'has_pdf': bool(partition.partition_pdf),
            'has_mxl': bool(partition.partition_mxl),
            'status': 'idle',
            'is_generating': False,
            'error': '',
        }

    is_generating = job.status in {PartitionOmrJob.Status.QUEUED, PartitionOmrJob.Status.STARTED}
    return {
        'partition_id': partition.id,
        'has_pdf': bool(partition.partition_pdf),
        'has_mxl': bool(partition.partition_mxl),
        'status': job.status,
        'is_generating': is_generating,
        'task_id': job.task_id,
        'backend': job.backend,
        'backend_version': job.backend_version,
        'model_profile': job.model_profile,
        'queue_priority': job.queue_priority,
        'attempts': job.attempts,
        'source_name': job.source_name,
        'generated_file_name': job.generated_file_name,
        'error': job.last_error,
        'queued_at': job.queued_at.isoformat() if job.queued_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'progress': {
            'current': job.processed_pages,
            'total': job.page_count,
        },
    }


@shared_task(bind=True, name='psaumes.generate_partition_mxl')
def generate_partition_mxl(self, partition_id):
    try:
        partition = Partition.objects.get(pk=partition_id)
    except Partition.DoesNotExist:
        logger.error("OMR job received unknown partition id=%s", partition_id)
        return {'partition_id': partition_id, 'status': 'missing-partition'}

    try:
        job = partition.omr_job
    except PartitionOmrJob.DoesNotExist:
        job = PartitionOmrJob.objects.create(
            partition=partition,
            status=PartitionOmrJob.Status.QUEUED,
            backend=settings.OMR_BACKEND,
            model_profile=settings.OMR_MODEL_PROFILE,
        )

    request_id = self.request.id
    if request_id and job.task_id and job.task_id != request_id:
        logger.info(
            "Skipping stale OMR task job=%s task=%s current_task=%s",
            job.pk,
            request_id,
            job.task_id,
        )
        return {'partition_id': partition_id, 'status': 'stale-task'}
    if request_id and not job.task_id:
        job.task_id = request_id
        job.save(update_fields=['task_id', 'updated_at'])

    if job.status != PartitionOmrJob.Status.QUEUED:
        return {'partition_id': partition_id, 'status': job.status}

    if partition.partition_mxl:
        job.status = PartitionOmrJob.Status.SUCCEEDED
        job.last_error = ''
        job.generated_file_name = partition.partition_mxl.name
        job.started_at = job.started_at or timezone.now()
        job.finished_at = timezone.now()
        job.save(update_fields=[
            'status',
            'last_error',
            'generated_file_name',
            'started_at',
            'finished_at',
            'updated_at',
        ])
        return {
            'partition_id': partition.id,
            'status': job.status,
            'skipped': True,
            'reason': 'partition-already-has-mxl',
        }

    try:
        current_source = fingerprint_partition_omr_source(partition, source_type=job.source_type)
    except Exception as exc:
        job.status = PartitionOmrJob.Status.FAILED
        job.last_error = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        raise

    if job.source_sha256 and current_source.sha256 != job.source_sha256:
        job.status = PartitionOmrJob.Status.FAILED
        job.last_error = 'Skipped: source file changed before OMR generation.'
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        return {
            'partition_id': partition.id,
            'status': job.status,
            'skipped': True,
            'reason': 'source-changed',
        }

    job.source_name = current_source.name
    job.source_sha256 = current_source.sha256
    job.status = PartitionOmrJob.Status.STARTED
    job.started_at = timezone.now()
    job.save(update_fields=[
        'source_name',
        'source_sha256',
        'status',
        'started_at',
        'updated_at',
    ])

    try:
        result = generate_musicxml_for_partition(partition, source_type=job.source_type)

        job.source_name = result.source_name
        job.source_sha256 = result.source_sha256
        job.backend = result.backend
        job.backend_version = result.backend_version
        job.model_profile = result.model_profile
        job.page_count = result.page_count
        job.processed_pages = result.processed_pages
        job.generated_file_name = result.generated_file_name
        job.status = PartitionOmrJob.Status.SUCCEEDED
        job.last_error = ''
        job.finished_at = timezone.now()
        job.save()

        partition.refresh_from_db()
        enqueue_partition_audio_generation(partition)
        return {
            'partition_id': partition.id,
            'status': job.status,
            'generated_file_name': job.generated_file_name,
            'backend': job.backend,
            'model_profile': job.model_profile,
        }
    except Exception as exc:
        logger.exception("OMR generation failed for partition %s", partition_id)
        job.status = PartitionOmrJob.Status.FAILED
        job.last_error = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'last_error', 'finished_at', 'updated_at'])
        raise
