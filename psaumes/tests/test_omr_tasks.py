import pytest
from types import SimpleNamespace
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from psaumes.models import Partition, PartitionOmrJob, Psaume
from psaumes.services.omr.pipeline import OmrPipelineResult
from psaumes.tasks import (
    enqueue_partition_omr_generation,
    generate_partition_mxl,
)


def _use_local_file_storage(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
    storages._storages = {}


def _partition_with_pdf():
    psaume = Psaume.objects.create(nom_psaume='Psaume 1', titre='Heureux est l homme')
    return Partition.objects.create(
        psaume=psaume,
        titre='Heureux est l homme',
        partition_pdf=SimpleUploadedFile(
            'score.pdf',
            b'%PDF-' + b'a' * 32,
            content_type='application/pdf',
        ),
    )


@pytest.mark.django_db(transaction=True)
def test_enqueue_partition_omr_generation_creates_idempotent_job(settings, tmp_path, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    settings.CELERY_TASK_ALWAYS_EAGER = False
    dispatched = []
    monkeypatch.setattr(
        'psaumes.tasks.omr._dispatch_partition_omr_generation',
        lambda partition_id, priority: (
            dispatched.append((partition_id, priority)) or SimpleNamespace(id='task-1')
        ),
    )
    partition = _partition_with_pdf()

    first = enqueue_partition_omr_generation(partition)
    second = enqueue_partition_omr_generation(partition)

    assert first.pk == second.pk
    assert first.status == PartitionOmrJob.Status.QUEUED
    assert first.backend == 'homr_cli'
    assert first.model_profile == 'default'
    assert first.source_sha256
    assert dispatched == [(partition.id, PartitionOmrJob.QueuePriority.USER)]


@pytest.mark.django_db(transaction=True)
def test_generate_partition_mxl_detects_changed_pdf(settings, tmp_path, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    monkeypatch.setattr(
        'psaumes.tasks.omr._dispatch_partition_omr_generation',
        lambda partition_id, priority: SimpleNamespace(id='task-1'),
    )
    partition = _partition_with_pdf()
    job = enqueue_partition_omr_generation(partition)
    partition.partition_pdf.save('score-new.pdf', ContentFile(b'%PDF-' + b'b' * 32), save=True)
    monkeypatch.setattr(
        'psaumes.tasks.omr.generate_musicxml_for_partition',
        lambda *args, **kwargs: pytest.fail('Pipeline must not run for stale source'),
    )

    result = generate_partition_mxl(partition.id)

    job.refresh_from_db()
    assert result['reason'] == 'source-changed'
    assert job.status == PartitionOmrJob.Status.FAILED
    assert 'source file changed' in job.last_error


@pytest.mark.django_db(transaction=True)
def test_generate_partition_mxl_saves_musicxml_and_enqueues_audio(settings, tmp_path, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    monkeypatch.setattr(
        'psaumes.tasks.omr._dispatch_partition_omr_generation',
        lambda partition_id, priority: SimpleNamespace(id='task-1'),
    )
    partition = _partition_with_pdf()
    job = enqueue_partition_omr_generation(partition)
    audio_enqueues = []

    def fake_pipeline(partition, source_type=None):
        partition.partition_mxl.save(
            'score.musicxml',
            ContentFile(b'<score-partwise version="4.0"></score-partwise>'),
            save=True,
        )
        return OmrPipelineResult(
            source_name=partition.partition_pdf.name,
            source_sha256=job.source_sha256,
            backend='fake_backend',
            backend_version='fake 1',
            model_profile='fake-profile',
            page_count=1,
            processed_pages=1,
            generated_file_name=partition.partition_mxl.name,
        )

    monkeypatch.setattr('psaumes.tasks.omr.generate_musicxml_for_partition', fake_pipeline)
    monkeypatch.setattr(
        'psaumes.tasks.omr.enqueue_partition_audio_generation',
        lambda partition: audio_enqueues.append(partition.id),
    )

    result = generate_partition_mxl(partition.id)

    partition.refresh_from_db()
    job.refresh_from_db()
    assert result['status'] == PartitionOmrJob.Status.SUCCEEDED
    assert partition.partition_mxl
    assert job.backend == 'fake_backend'
    assert job.backend_version == 'fake 1'
    assert job.model_profile == 'fake-profile'
    assert job.processed_pages == 1
    assert audio_enqueues == [partition.id]


@pytest.mark.django_db(transaction=True)
def test_enqueue_partition_omr_generation_respects_retry_backoff(settings, tmp_path, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    settings.OMR_RETRY_DELAY_SECONDS = 3600
    dispatched = []
    monkeypatch.setattr(
        'psaumes.tasks.omr._dispatch_partition_omr_generation',
        lambda partition_id, priority: dispatched.append(partition_id) or SimpleNamespace(id='task-1'),
    )
    partition = _partition_with_pdf()
    job = enqueue_partition_omr_generation(partition)
    job.status = PartitionOmrJob.Status.FAILED
    job.finished_at = timezone.now()
    job.save()

    skipped = enqueue_partition_omr_generation(partition)

    assert skipped.pk == job.pk
    assert dispatched == [partition.id]
