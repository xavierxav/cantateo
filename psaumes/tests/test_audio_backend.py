from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from psaumes.models import Partition, PartitionAudioGenerationJob, PartitionAudioTempoVariant
from psaumes.models import PartitionAudioNormalizationJob
from psaumes.services.audio.channels import (
    normalize_partition_audio_field,
    partition_field_cached_channel_count,
    partition_field_needs_mono_normalization,
    tempo_variant_cached_channel_count,
    tempo_variant_needs_mono_normalization,
    invalidate_partition_audio_channels,
    invalidate_tempo_variant_audio_channels,
)
from psaumes.services.audio import synthesizer
from psaumes.services.audio.generator import generate_missing_voices_for_chant, get_missing_voices
from psaumes.services.audio import tempo_variants
from psaumes.services.audio.tempo_variants import generate_tempo_variants_for_partition
from psaumes.tasks import (
    AUDIO_QUEUE_PRIORITY_BULK,
    AUDIO_QUEUE_PRIORITY_USER,
    enqueue_partition_audio_field_normalization,
    enqueue_partition_audio_generation,
    enqueue_partition_tempo_variant_generation,
    normalize_partition_audio,
)


def _make_partition(**kwargs):
    defaults = {
        'titre': 'Partition de test',
        'partition_mxl': SimpleUploadedFile('score.mxl', b'<score-partwise/>'),
    }
    defaults.update(kwargs)
    return Partition.objects.create(**defaults)


def _make_partition_without_file(**kwargs):
    defaults = {'titre': 'Partition de test'}
    defaults.update(kwargs)
    return Partition.objects.create(**defaults)


def _use_local_file_storage(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
    storages._storages = {}


@pytest.mark.django_db
def test_generate_missing_voices_uses_temp_audio_path(tmp_path, monkeypatch, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition()
    calls = {}

    def fake_extract_voices(_mxl_path):
        return {'S': object()}

    def fake_synthesize_voice_to_audio(voice_part, output_path, *args, **kwargs):
        calls['voice_part'] = voice_part
        calls['output_path'] = output_path
        assert output_path.endswith('.mp3')
        Path(output_path).write_bytes(b'ID3' + b'\x00' * 2048)
        return True

    monkeypatch.setattr('psaumes.services.audio.generator.extract_voices_from_mxl', fake_extract_voices)
    monkeypatch.setattr('psaumes.services.audio.generator.synthesize_voice_to_audio', fake_synthesize_voice_to_audio)
    monkeypatch.setattr('psaumes.services.audio.generator.validate_audio_file', lambda path: (True, None))

    created = generate_missing_voices_for_chant(partition)

    assert created >= 1
    assert calls['output_path'].endswith('.mp3')

    partition.refresh_from_db()
    assert partition.audio_soprano
    assert partition.mp3_synthetiques is True


@pytest.mark.django_db
def test_synthetic_generation_targets_satb_only(tmp_path, monkeypatch, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition()
    synthesized = []

    def fake_extract_voices(_mxl_path):
        return {voice_type: object() for voice_type in ['S', 'A', 'T', 'B', 'I']}

    def fake_synthesize_voice_to_audio(voice_part, output_path, *args, **kwargs):
        synthesized.append(voice_part)
        Path(output_path).write_bytes(b'ID3' + b'\x00' * 2048)
        return True

    monkeypatch.setattr('psaumes.services.audio.generator.extract_voices_from_mxl', fake_extract_voices)
    monkeypatch.setattr('psaumes.services.audio.generator.synthesize_voice_to_audio', fake_synthesize_voice_to_audio)
    monkeypatch.setattr('psaumes.services.audio.generator.validate_audio_file', lambda path: (True, None))
    monkeypatch.setattr(
        'psaumes.services.audio.generator.generate_mix_track',
        lambda partition: pytest.fail('Synthetic generation must not create mix tracks'),
    )

    assert get_missing_voices(partition) == ['S', 'A', 'T', 'B']

    created = generate_missing_voices_for_chant(partition)

    partition.refresh_from_db()
    assert created == 4
    assert len(synthesized) == 4
    assert partition.audio_soprano
    assert partition.audio_alto
    assert partition.audio_tenor
    assert partition.audio_basse
    assert not partition.audio_instrumental
    assert not partition.audio_mix


@pytest.mark.django_db(transaction=True)
def test_enqueue_partition_audio_generation_is_idempotent(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition()
    delay_calls = []

    def fake_apply_async(args=None, priority=None, **kwargs):
        delay_calls.append((args, priority))
        return SimpleNamespace(id='task-123')

    monkeypatch.setattr('psaumes.tasks.generate_partition_audio.apply_async', fake_apply_async)

    job_1 = enqueue_partition_audio_generation(partition)
    job_2 = enqueue_partition_audio_generation(partition)

    assert job_1 is not None
    assert job_2 is not None
    assert delay_calls == [((partition.id,), 0)]

    job = PartitionAudioGenerationJob.objects.get(partition=partition)
    assert job.status == PartitionAudioGenerationJob.Status.QUEUED
    assert job.queue_priority == AUDIO_QUEUE_PRIORITY_USER
    assert job.task_id == 'task-123'
    assert job.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_user_audio_request_promotes_queued_bulk_job(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition()
    delay_calls = []

    def fake_apply_async(args=None, priority=None, **kwargs):
        delay_calls.append((args, priority))
        return SimpleNamespace(id=f'task-{len(delay_calls)}')

    monkeypatch.setattr('psaumes.tasks.generate_partition_audio.apply_async', fake_apply_async)

    enqueue_partition_audio_generation(partition, priority=AUDIO_QUEUE_PRIORITY_BULK)
    enqueue_partition_audio_generation(partition, priority=AUDIO_QUEUE_PRIORITY_USER)

    assert delay_calls == [((partition.id,), 9), ((partition.id,), 0)]
    job = PartitionAudioGenerationJob.objects.get(partition=partition)
    assert job.queue_priority == AUDIO_QUEUE_PRIORITY_USER
    assert job.task_id == 'task-2'
    assert job.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_audio_generation_not_enqueued_when_already_complete(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
        audio_instrumental='audios/test/i.mp3',
        audio_mix='audios/test/m.mp3',
        mp3_synthetiques=True,
    )
    delay_calls = []
    monkeypatch.setattr(
        'psaumes.tasks.generate_partition_audio.apply_async',
        lambda *args, **kwargs: delay_calls.append((args, kwargs)),
    )

    job = enqueue_partition_audio_generation(partition, priority=AUDIO_QUEUE_PRIORITY_BULK)

    assert delay_calls == []
    assert job.status == PartitionAudioGenerationJob.Status.SUCCEEDED
    assert job.queue_priority == AUDIO_QUEUE_PRIORITY_BULK


@pytest.mark.django_db(transaction=True)
def test_audio_generation_complete_with_satb_only(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
        mp3_synthetiques=True,
    )
    delay_calls = []
    monkeypatch.setattr(
        'psaumes.tasks.generate_partition_audio.apply_async',
        lambda *args, **kwargs: delay_calls.append((args, kwargs)),
    )

    job = enqueue_partition_audio_generation(partition, priority=AUDIO_QUEUE_PRIORITY_BULK)

    assert get_missing_voices(partition) == []
    assert delay_calls == []
    assert job.status == PartitionAudioGenerationJob.Status.SUCCEEDED


@pytest.mark.django_db(transaction=True)
def test_user_normalization_request_promotes_queued_bulk_job(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/stereo.mp3')
    calls = []

    def fake_apply_async(args=None, priority=None, **kwargs):
        calls.append((args, priority))
        return SimpleNamespace(id=f'normalize-task-{len(calls)}')

    monkeypatch.setattr('psaumes.tasks.normalize_partition_audio.apply_async', fake_apply_async)

    enqueue_partition_audio_field_normalization(
        partition,
        'audio_soprano',
        priority=AUDIO_QUEUE_PRIORITY_BULK,
    )
    enqueue_partition_audio_field_normalization(
        partition,
        'audio_soprano',
        priority=AUDIO_QUEUE_PRIORITY_USER,
    )

    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]
    assert [priority for _args, priority in calls] == [6, 0]
    job = PartitionAudioNormalizationJob.objects.get(partition=partition, field_name='audio_soprano')
    assert job.queue_priority == AUDIO_QUEUE_PRIORITY_USER
    assert job.task_id == 'normalize-task-2'


@pytest.mark.django_db(transaction=True)
def test_stale_normalization_task_is_ignored(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/stereo.mp3')
    job = PartitionAudioNormalizationJob.objects.create(
        target_type=PartitionAudioNormalizationJob.TargetType.PARTITION,
        partition=partition,
        field_name='audio_soprano',
        source_name=partition.audio_soprano.name,
        status=PartitionAudioNormalizationJob.Status.QUEUED,
        task_id='fresh-task',
    )
    calls = []
    monkeypatch.setattr(
        'psaumes.tasks.audio_normalization.normalize_partition_audio_field',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = normalize_partition_audio.apply(args=(job.pk,), task_id='stale-task').get()

    job.refresh_from_db()
    assert result['status'] == 'stale-task'
    assert calls == []
    assert job.status == PartitionAudioNormalizationJob.Status.QUEUED
    assert job.task_id == 'fresh-task'


@pytest.mark.django_db(transaction=True)
def test_normalization_not_requeued_after_max_attempts(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.AUDIO_NORMALIZATION_MAX_ATTEMPTS = 3
    partition = _make_partition_without_file(audio_soprano='audios/test/stereo.mp3')
    PartitionAudioNormalizationJob.objects.create(
        target_type=PartitionAudioNormalizationJob.TargetType.PARTITION,
        partition=partition,
        field_name='audio_soprano',
        source_name=partition.audio_soprano.name,
        status=PartitionAudioNormalizationJob.Status.FAILED,
        attempts=3,
        finished_at=timezone.now(),
        last_error='broken mp3',
    )
    calls = []
    monkeypatch.setattr(
        'psaumes.tasks.normalize_partition_audio.apply_async',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    job = enqueue_partition_audio_field_normalization(
        partition,
        'audio_soprano',
        priority=AUDIO_QUEUE_PRIORITY_USER,
    )

    assert calls == []
    assert job.status == PartitionAudioNormalizationJob.Status.FAILED
    assert job.attempts == 3


@pytest.mark.django_db(transaction=True)
def test_normalization_not_requeued_during_retry_backoff(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.AUDIO_NORMALIZATION_MAX_ATTEMPTS = 3
    settings.AUDIO_NORMALIZATION_RETRY_DELAY_SECONDS = 3600
    partition = _make_partition_without_file(audio_soprano='audios/test/stereo.mp3')
    PartitionAudioNormalizationJob.objects.create(
        target_type=PartitionAudioNormalizationJob.TargetType.PARTITION,
        partition=partition,
        field_name='audio_soprano',
        source_name=partition.audio_soprano.name,
        status=PartitionAudioNormalizationJob.Status.FAILED,
        attempts=1,
        finished_at=timezone.now(),
        last_error='broken mp3',
    )
    calls = []
    monkeypatch.setattr(
        'psaumes.tasks.normalize_partition_audio.apply_async',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    job = enqueue_partition_audio_field_normalization(
        partition,
        'audio_soprano',
        priority=AUDIO_QUEUE_PRIORITY_USER,
    )

    assert calls == []
    assert job.status == PartitionAudioNormalizationJob.Status.FAILED
    assert job.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_normalization_retry_guard_resets_when_source_changes(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.AUDIO_NORMALIZATION_MAX_ATTEMPTS = 3
    partition = _make_partition_without_file(audio_soprano='audios/test/new.mp3')
    PartitionAudioNormalizationJob.objects.create(
        target_type=PartitionAudioNormalizationJob.TargetType.PARTITION,
        partition=partition,
        field_name='audio_soprano',
        source_name='audios/test/old.mp3',
        status=PartitionAudioNormalizationJob.Status.FAILED,
        attempts=3,
        finished_at=timezone.now(),
        last_error='broken old mp3',
    )
    calls = []

    def fake_apply_async(args=None, priority=None, **kwargs):
        calls.append((args, priority))
        return SimpleNamespace(id='normalize-new-source')

    monkeypatch.setattr('psaumes.tasks.normalize_partition_audio.apply_async', fake_apply_async)

    job = enqueue_partition_audio_field_normalization(
        partition,
        'audio_soprano',
        priority=AUDIO_QUEUE_PRIORITY_USER,
    )

    job.refresh_from_db()
    assert calls == [((job.pk,), 0)]
    assert job.status == PartitionAudioNormalizationJob.Status.QUEUED
    assert job.source_name == partition.audio_soprano.name
    assert job.attempts == 1
    assert job.task_id == 'normalize-new-source'


@pytest.mark.django_db
def test_audio_status_includes_job_metadata(client):
    partition = _make_partition()
    partition.audio_soprano.save('soprano.mp3', SimpleUploadedFile('soprano.mp3', b'ID3' + b'\x00' * 2048), save=True)
    job = PartitionAudioGenerationJob.objects.create(
        partition=partition,
        status=PartitionAudioGenerationJob.Status.STARTED,
        task_id='task-456',
        attempts=2,
        generated_count=1,
        total_count=4,
        missing_voice_types=['A', 'T', 'B'],
        last_error='',
    )

    response = client.get(reverse('audio_status', kwargs={'partition_id': partition.id}))
    payload = response.json()

    assert response.status_code == 200
    assert payload['partition_id'] == partition.id
    assert payload['status'] == job.status
    assert payload['task_id'] == 'task-456'
    assert payload['attempts'] == 2
    assert payload['missing_voice_types'] == ['A', 'T', 'B']
    assert payload['is_generating'] is True
    assert payload['generation_complete'] is False
    assert payload['voices']
    assert payload['progress']['current'] == 1
    assert payload['progress']['total'] == 4


@pytest.mark.django_db
def test_download_audio_local_storage_streams_file(tmp_path, settings, client, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition()
    audio_path = tmp_path / 'soprano.mp3'
    audio_path.write_bytes(b'ID3' + b'\x00' * 2048)

    class DummyStorage:
        pass

    class DummyAudioField:
        name = 'soprano.mp3'
        storage = DummyStorage()

        def open(self, mode='rb'):
            return open(audio_path, mode)

    monkeypatch.setattr(Partition, 'get_audio_field', lambda self, voice_type: DummyAudioField())

    response = client.get(
        reverse('download_audio', kwargs={'partition_id': partition.id, 'voice_type': 'S'})
    )

    assert response.status_code == 200
    assert response['Content-Type'] == 'audio/mpeg'
    assert b''.join(response.streaming_content).startswith(b'ID3')


@pytest.mark.django_db
def test_tempo_variant_unique_per_partition_voice_and_tempo(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file()

    PartitionAudioTempoVariant.objects.create(partition=partition, voice_type='S', tempo='0.50')

    with pytest.raises(IntegrityError):
        PartitionAudioTempoVariant.objects.create(partition=partition, voice_type='S', tempo='0.50')


@pytest.mark.django_db
def test_audio_variants_one_x_returns_source_urls_without_rows(tmp_path, settings, client):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/soprano.mp3')

    response = client.get(reverse('audio_variants', kwargs={'partition_id': partition.id}), {'tempo': '1.0'})
    payload = response.json()

    assert response.status_code == 200
    assert payload['status'] == 'ready'
    assert payload['tempo'] == '1.0'
    assert payload['voices'][0]['id'] == f'{partition.id}_S_tempo_1_0'
    assert payload['voices'][0]['voice_type'] == 'S'
    assert PartitionAudioTempoVariant.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_audio_variants_missing_half_x_enqueues_generation(tmp_path, settings, client, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
        audio_instrumental='audios/test/i.mp3',
    )
    delay_calls = []

    def fake_apply_async(args=None, priority=None, **kwargs):
        delay_calls.append((args, priority))
        return SimpleNamespace(id='tempo-task-123')

    monkeypatch.setattr('psaumes.tasks.generate_partition_tempo_variants.apply_async', fake_apply_async)

    response = client.get(reverse('audio_variants', kwargs={'partition_id': partition.id}), {'tempo': '0.5'})
    payload = response.json()

    assert response.status_code == 200
    assert payload['status'] == 'generating'
    assert payload['tempo'] == '0.5'
    assert set(payload['missing_voice_types']) == {'S', 'A', 'T', 'B', 'I'}
    assert delay_calls == [((partition.id, '0.50'), 0)]
    assert PartitionAudioTempoVariant.objects.filter(partition=partition, tempo='0.50').count() == 5


@pytest.mark.django_db(transaction=True)
def test_user_tempo_request_promotes_queued_bulk_variants(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
        audio_instrumental='audios/test/i.mp3',
    )
    delay_calls = []

    def fake_apply_async(args=None, priority=None, **kwargs):
        delay_calls.append((args, priority))
        return SimpleNamespace(id=f'tempo-task-{len(delay_calls)}')

    monkeypatch.setattr('psaumes.tasks.generate_partition_tempo_variants.apply_async', fake_apply_async)

    enqueue_partition_tempo_variant_generation(partition, '0.5', priority=AUDIO_QUEUE_PRIORITY_BULK)
    enqueue_partition_tempo_variant_generation(partition, '0.5', priority=AUDIO_QUEUE_PRIORITY_USER)

    assert delay_calls == [((partition.id, '0.50'), 9), ((partition.id, '0.50'), 0)]
    assert set(
        PartitionAudioTempoVariant.objects
        .filter(partition=partition, tempo='0.50')
        .values_list('queue_priority', flat=True)
    ) == {AUDIO_QUEUE_PRIORITY_USER}


@pytest.mark.django_db
def test_audio_variants_ready_half_x_returns_variant_urls(tmp_path, settings, client):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    variant = PartitionAudioTempoVariant.objects.create(
        partition=partition,
        voice_type='S',
        tempo='0.50',
        status=PartitionAudioTempoVariant.Status.SUCCEEDED,
    )
    variant.audio_file.save(
        's_tempo_0_5.mp3',
        SimpleUploadedFile('s_tempo_0_5.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )

    response = client.get(reverse('audio_variants', kwargs={'partition_id': partition.id}), {'tempo': '0.5'})
    payload = response.json()

    assert response.status_code == 200
    assert payload['status'] == 'ready'
    assert payload['voices'][0]['id'] == f'{partition.id}_S_tempo_0_5'
    assert payload['voices'][0]['url'].endswith('.mp3')


@pytest.mark.django_db
def test_audio_variants_rejects_unsupported_tempo(client):
    partition = _make_partition_without_file()

    response = client.get(reverse('audio_variants', kwargs={'partition_id': partition.id}), {'tempo': '0.75'})

    assert response.status_code == 400
    assert response.json()['error'] == 'Tempo non supporté'


@pytest.mark.django_db
def test_audio_variants_rate_limited(client):
    cache.clear()
    partition = _make_partition_without_file()

    with override_settings(RATE_LIMITS={'audio_variants': (1, 60)}):
        first = client.get(reverse('audio_variants', kwargs={'partition_id': partition.id}), {'tempo': '1.0'})
        second = client.get(reverse('audio_variants', kwargs={'partition_id': partition.id}), {'tempo': '1.0'})

    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.django_db
def test_generate_tempo_variant_saves_rendered_audio(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/soprano.mp3')
    monkeypatch.setattr(
        'psaumes.services.audio.tempo_variants._render_tempo_variant',
        lambda source_field, tempo: b'ID3' + b'\x00' * 2048,
    )

    generated = generate_tempo_variants_for_partition(partition, '1.5')

    assert generated == 1
    variant = PartitionAudioTempoVariant.objects.get(partition=partition, voice_type='S', tempo='1.50')
    assert variant.status == PartitionAudioTempoVariant.Status.SUCCEEDED
    assert variant.audio_file


def test_synthetic_mp3_conversion_forces_mono(tmp_path, monkeypatch):
    wav_path = tmp_path / 'source.wav'
    mp3_path = tmp_path / 'target.mp3'
    wav_path.write_bytes(b'RIFF' + b'\x00' * 2048)
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        mp3_path.write_bytes(b'ID3' + b'\x00' * 2048)
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr('psaumes.services.audio.synthesizer.subprocess.run', fake_run)

    synthesizer._convert_wav_to_mp3(str(wav_path), str(mp3_path))

    assert '-ac' in commands[0]
    assert commands[0][commands[0].index('-ac') + 1] == '1'


def test_tempo_variant_render_forces_mono(tmp_path, monkeypatch):
    source_path = tmp_path / 'source.mp3'
    output_path = tmp_path / 'tempo.mp3'
    source_path.write_bytes(b'ID3' + b'\x00' * 2048)
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        output_path.write_bytes(b'ID3' + b'\x00' * 2048)
        return SimpleNamespace(returncode=0, stderr=b'')

    monkeypatch.setattr('psaumes.services.audio.tempo_variants.subprocess.run', fake_run)

    assert tempo_variants._run_ffmpeg_tempo(str(source_path), str(output_path), '1.5', 'atempo') is True
    assert '-ac' in commands[0]
    assert commands[0][commands[0].index('-ac') + 1] == '1'


@pytest.mark.django_db
def test_normalize_partition_audio_field_converts_and_deletes_old_file(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'stereo.mp3',
        SimpleUploadedFile('stereo.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    old_path = tmp_path / partition.audio_soprano.name

    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 2)
    monkeypatch.setattr(
        'psaumes.services.audio.channels._run_ffmpeg_mono',
        lambda source, output: Path(output).write_bytes(b'ID3' + b'\x00' * 2048),
    )
    monkeypatch.setattr('psaumes.services.audio.channels.validate_audio_file', lambda path: (True, None))

    result = normalize_partition_audio_field(partition, 'audio_soprano')

    partition.refresh_from_db()
    assert result.changed is True
    assert partition.audio_soprano.name.endswith('_mono.mp3')
    assert not old_path.exists()
    assert (tmp_path / partition.audio_soprano.name).exists()


@pytest.mark.django_db
def test_normalize_partition_audio_field_skips_mono_file(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'mono.mp3',
        SimpleUploadedFile('mono.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    old_name = partition.audio_soprano.name

    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 1)

    result = normalize_partition_audio_field(partition, 'audio_soprano')

    partition.refresh_from_db()
    assert result.skipped is True
    assert partition.audio_soprano.name == old_name


@pytest.mark.django_db
def test_normalize_partition_audio_field_ignores_mix(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_mix.save(
        'mix.mp3',
        SimpleUploadedFile('mix.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    old_name = partition.audio_mix.name
    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 2)

    result = normalize_partition_audio_field(partition, 'audio_mix')

    partition.refresh_from_db()
    assert result.skipped is True
    assert partition.audio_mix.name == old_name


@pytest.mark.django_db
def test_normalize_partition_audio_field_keeps_old_file_when_still_referenced(
    tmp_path,
    settings,
    monkeypatch,
):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'shared.mp3',
        SimpleUploadedFile('shared.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    old_name = partition.audio_soprano.name
    Partition.objects.create(titre='Autre', audio_alto=old_name)
    old_path = tmp_path / old_name

    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 2)
    monkeypatch.setattr(
        'psaumes.services.audio.channels._run_ffmpeg_mono',
        lambda source, output: Path(output).write_bytes(b'ID3' + b'\x00' * 2048),
    )
    monkeypatch.setattr('psaumes.services.audio.channels.validate_audio_file', lambda path: (True, None))

    normalize_partition_audio_field(partition, 'audio_soprano')

    assert old_path.exists()


def test_normalization_marks_missing_source_file_as_failed(monkeypatch):
    from contextlib import nullcontext

    job = SimpleNamespace(
        pk=123,
        partition=SimpleNamespace(),
        partition_id=1,
        tempo_variant_id=None,
        target_type=PartitionAudioNormalizationJob.TargetType.PARTITION,
        field_name='audio_soprano',
        source_name='audios/missing-source.mp3',
        status=PartitionAudioNormalizationJob.Status.QUEUED,
        task_id='task-missing-source',
        last_error='',
        finished_at=None,
        save=lambda *args, **kwargs: None,
    )

    class FakeJobManager:
        def select_for_update(self):
            return self

        def select_related(self, *args, **kwargs):
            return self

        def get(self, pk):
            return job

        def filter(self, *args, **kwargs):
            return self

        def update(self, **kwargs):
            return None

    monkeypatch.setattr(
        'psaumes.tasks.audio_normalization.PartitionAudioNormalizationJob.objects',
        FakeJobManager(),
    )
    monkeypatch.setattr(
        'psaumes.tasks.audio_normalization.normalize_partition_audio_field',
        lambda *args, **kwargs: SimpleNamespace(
            changed=False,
            skipped=True,
            missing_source=True,
            old_name='audios/missing-source.mp3',
            new_name='',
            channels=None,
            delete_error='Source file missing from storage',
        ),
    )
    monkeypatch.setattr(
        'psaumes.tasks.audio_normalization._normalization_current_source_name',
        lambda job: job.source_name,
    )
    monkeypatch.setattr('psaumes.tasks.audio_normalization.transaction.atomic', lambda: nullcontext())

    result = normalize_partition_audio.apply(args=(job.pk,), task_id='task-missing-source').get()

    assert result['status'] == PartitionAudioNormalizationJob.Status.FAILED
    assert result['missing_source'] is True
    assert job.status == PartitionAudioNormalizationJob.Status.FAILED
    assert job.last_error == 'Source file missing from storage'


@pytest.mark.django_db
def test_enqueue_missing_audio_dry_run_does_not_create_jobs(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    _make_partition()
    stdout = StringIO()

    call_command('enqueue_missing_audio', '--synthetic', '--dry-run', stdout=stdout)

    assert PartitionAudioGenerationJob.objects.count() == 0
    assert 'would enqueue: 1 job(s)' in stdout.getvalue()


@pytest.mark.django_db
def test_enqueue_missing_audio_limit_bounds_enqueues(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    first = _make_partition(titre='One')
    _make_partition(titre='Two')
    calls = []

    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_audio_generation',
        lambda partition, priority: calls.append((partition.id, priority)),
    )

    call_command('enqueue_missing_audio', '--synthetic', '--limit', '1', stdout=StringIO())

    assert calls == [(first.id, AUDIO_QUEUE_PRIORITY_BULK)]


@pytest.mark.django_db
def test_enqueue_missing_audio_skips_non_synthetic_partitions_with_audio(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    _make_partition(audio_soprano='audios/test/s.mp3', mp3_synthetiques=False)
    calls = []
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_audio_generation',
        lambda partition, priority: calls.append((partition.id, priority)),
    )

    call_command('enqueue_missing_audio', '--synthetic', stdout=StringIO())

    assert calls == []


@pytest.mark.django_db
def test_enqueue_missing_audio_enqueues_tempo_variants_for_complete_sources(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
        audio_instrumental='audios/test/i.mp3',
        mp3_synthetiques=False,
    )
    _make_partition_without_file(audio_soprano='audios/test/partial.mp3', mp3_synthetiques=False)
    calls = []
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_tempo_variant_generation',
        lambda partition, tempo, priority: calls.append((partition.id, str(tempo), priority)),
    )

    call_command(
        'enqueue_missing_audio',
        '--tempo-variants',
        '--upcoming-days',
        '0',
        '--limit',
        '10',
        stdout=StringIO(),
    )

    assert calls == [
        (partition.id, '0.50', AUDIO_QUEUE_PRIORITY_BULK),
        (partition.id, '1.50', AUDIO_QUEUE_PRIORITY_BULK),
    ]


@pytest.mark.django_db
def test_enqueue_missing_audio_limits_tempo_variants_to_upcoming_partitions(
    tmp_path,
    settings,
    monkeypatch,
):
    settings.MEDIA_ROOT = str(tmp_path)
    upcoming = _make_partition_without_file(
        audio_soprano='audios/test/up-s.mp3',
        audio_alto='audios/test/up-a.mp3',
        audio_tenor='audios/test/up-t.mp3',
        audio_basse='audios/test/up-b.mp3',
        audio_instrumental='audios/test/up-i.mp3',
        mp3_synthetiques=False,
    )
    _make_partition_without_file(
        audio_soprano='audios/test/late-s.mp3',
        audio_alto='audios/test/late-a.mp3',
        audio_tenor='audios/test/late-t.mp3',
        audio_basse='audios/test/late-b.mp3',
        audio_instrumental='audios/test/late-i.mp3',
        mp3_synthetiques=False,
    )
    calls = []
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.Command._upcoming_partition_ids',
        lambda self, days: {upcoming.id},
    )
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_tempo_variant_generation',
        lambda partition, tempo, priority: calls.append((partition.id, str(tempo), priority)),
    )

    call_command('enqueue_missing_audio', '--tempo-variants', '--limit', '10', stdout=StringIO())

    assert calls == [
        (upcoming.id, '0.50', AUDIO_QUEUE_PRIORITY_BULK),
        (upcoming.id, '1.50', AUDIO_QUEUE_PRIORITY_BULK),
    ]


@pytest.mark.django_db
def test_enqueue_missing_audio_prioritizes_normalization_then_tempo_then_synthetic(
    tmp_path,
    settings,
    monkeypatch,
):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/s.mp3')
    calls = []

    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.Command._normalization_candidates',
        lambda self, partition_ids=None: iter([
            {'type': 'partition', 'partition': partition, 'field_name': 'audio_soprano', 'label': 'normal'},
        ]),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.Command._synthetic_candidates',
        lambda self: iter([partition]),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.Command._tempo_variant_candidates',
        lambda self, partition_ids=None: iter([(partition, '0.50', ['S'])]),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_audio_field_normalization',
        lambda partition, field_name, priority, detect=False: calls.append(('normal', partition.id, field_name, priority, detect)),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_audio_generation',
        lambda partition, priority: calls.append(('synthetic', partition.id, priority)),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_tempo_variant_generation',
        lambda partition, tempo, priority: calls.append(('tempo', partition.id, str(tempo), priority)),
    )

    call_command(
        'enqueue_missing_audio',
        '--normalize-mono',
        '--synthetic',
        '--tempo-variants',
        '--limit',
        '3',
        stdout=StringIO(),
    )

    assert calls == [
        ('normal', partition.id, 'audio_soprano', AUDIO_QUEUE_PRIORITY_BULK, False),
        ('tempo', partition.id, '0.50', AUDIO_QUEUE_PRIORITY_BULK),
        ('synthetic', partition.id, AUDIO_QUEUE_PRIORITY_BULK),
    ]


def test_cleanup_missing_audio_references_dry_run_reports_without_changes(monkeypatch):
    from contextlib import nullcontext

    class FakeStorage:
        def __init__(self, exists_map):
            self.exists_map = exists_map

        def exists(self, name):
            return self.exists_map.get(name, False)

    def make_field(name, exists_map):
        return SimpleNamespace(name=name, storage=FakeStorage(exists_map))

    class FakePartitionManager:
        def __init__(self, partitions):
            self._partitions = partitions

        def order_by(self, *args, **kwargs):
            return self

        def iterator(self):
            return iter(self._partitions)

    class FakeVariantManager:
        def __init__(self, variants):
            self._variants = variants

        def exclude(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def iterator(self):
            return iter(self._variants)

    partition = SimpleNamespace(
        id=1,
        audio_soprano=make_field('audios/missing-soprano.mp3', {'audios/missing-soprano.mp3': False}),
        audio_alto=make_field('alto.mp3', {'alto.mp3': True}),
        audio_tenor=None,
        audio_basse=None,
        audio_instrumental=None,
        audio_mix=None,
        mp3_synthetiques=True,
        save=lambda *args, **kwargs: None,
    )
    variant = SimpleNamespace(
        id=2,
        partition_id=1,
        voice_type='S',
        tempo='0.50',
        audio_file=make_field(
            'audios/missing-variant.mp3',
            {'audios/missing-variant.mp3': False},
        ),
        status=PartitionAudioTempoVariant.Status.SUCCEEDED,
        last_error='',
        save=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'psaumes.management.commands.cleanup_missing_audio_references.Partition',
        SimpleNamespace(objects=FakePartitionManager([partition])),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.cleanup_missing_audio_references.PartitionAudioTempoVariant',
        SimpleNamespace(
            objects=FakeVariantManager([variant]),
            Status=PartitionAudioTempoVariant.Status,
        ),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.cleanup_missing_audio_references.transaction.atomic',
        lambda: nullcontext(),
    )
    stdout = StringIO()

    call_command('cleanup_missing_audio_references', '--dry-run', stdout=stdout)

    assert partition.audio_soprano.name == 'audios/missing-soprano.mp3'
    assert partition.audio_alto.name == 'alto.mp3'
    assert variant.audio_file.name == 'audios/missing-variant.mp3'
    assert variant.status == PartitionAudioTempoVariant.Status.SUCCEEDED
    output = stdout.getvalue()
    assert 'partition audio reference(s) and 1 tempo variant reference(s)' in output
    assert '[DRY RUN] Would clean up:' in output


def test_cleanup_missing_audio_references_clears_missing_rows(monkeypatch):
    from contextlib import nullcontext

    class FakeStorage:
        def __init__(self, exists_map):
            self.exists_map = exists_map

        def exists(self, name):
            return self.exists_map.get(name, False)

    def make_field(name, exists_map):
        return SimpleNamespace(name=name, storage=FakeStorage(exists_map))

    class FakePartitionManager:
        def __init__(self, partitions):
            self._partitions = partitions

        def order_by(self, *args, **kwargs):
            return self

        def iterator(self):
            return iter(self._partitions)

    class FakeVariantManager:
        def __init__(self, variants):
            self._variants = variants

        def exclude(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def iterator(self):
            return iter(self._variants)

    partition = SimpleNamespace(
        id=1,
        audio_soprano=make_field('audios/missing-soprano.mp3', {'audios/missing-soprano.mp3': False}),
        audio_alto=make_field('alto.mp3', {'alto.mp3': True}),
        audio_tenor=None,
        audio_basse=None,
        audio_instrumental=None,
        audio_mix=None,
        mp3_synthetiques=True,
        save=lambda *args, **kwargs: None,
    )
    variant = SimpleNamespace(
        id=2,
        partition_id=1,
        voice_type='S',
        tempo='0.50',
        audio_file=make_field(
            'audios/missing-variant.mp3',
            {'audios/missing-variant.mp3': False},
        ),
        status=PartitionAudioTempoVariant.Status.SUCCEEDED,
        last_error='',
        save=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'psaumes.management.commands.cleanup_missing_audio_references.Partition',
        SimpleNamespace(objects=FakePartitionManager([partition])),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.cleanup_missing_audio_references.PartitionAudioTempoVariant',
        SimpleNamespace(
            objects=FakeVariantManager([variant]),
            Status=PartitionAudioTempoVariant.Status,
        ),
    )
    monkeypatch.setattr(
        'psaumes.management.commands.cleanup_missing_audio_references.transaction.atomic',
        lambda: nullcontext(),
    )
    stdout = StringIO()

    call_command('cleanup_missing_audio_references', stdout=stdout)

    assert partition.audio_soprano is None
    assert partition.audio_alto.name == 'alto.mp3'
    assert partition.mp3_synthetiques is True
    assert variant.audio_file is None
    assert variant.status == PartitionAudioTempoVariant.Status.PENDING
    assert variant.last_error == 'Missing file in storage; cleared by cleanup.'
    assert 'Cleared 1 partition audio reference(s) and 1 tempo variant reference(s).' in stdout.getvalue()


@pytest.mark.django_db
def test_partition_field_needs_mono_uses_cache_and_avoids_r2(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'stereo.mp3',
        SimpleUploadedFile('stereo.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    # Seed the cache as mono (1 channel).
    partition.audio_channels = {'audio_soprano': 1}
    partition.save(update_fields=['audio_channels'])

    storage_calls = []
    field = partition.audio_soprano
    real_storage = field.storage

    class SpyingStorage(real_storage.__class__):
        def exists(self, name):
            storage_calls.append(('exists', name))
            return real_storage.exists(name)

        def open(self, name, mode='rb'):
            storage_calls.append(('open', name))
            return real_storage.open(name, mode)

    spy = SpyingStorage()
    monkeypatch.setattr(field, 'storage', spy)

    needs = partition_field_needs_mono_normalization(partition, 'audio_soprano')

    assert needs is False
    assert storage_calls == []
    assert partition_field_cached_channel_count(partition, 'audio_soprano') == 1


@pytest.mark.django_db
def test_partition_field_needs_mono_detects_and_persists_when_cache_missing(
    tmp_path, settings, monkeypatch
):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'stereo.mp3',
        SimpleUploadedFile('stereo.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    assert partition.audio_channels == {}

    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 2)

    needs = partition_field_needs_mono_normalization(partition, 'audio_soprano')

    assert needs is True
    partition.refresh_from_db()
    assert partition.audio_channels == {'audio_soprano': 2}

    # Second call must not re-detect (no ffprobe) since cache is now populated.
    called = []
    monkeypatch.setattr(
        'psaumes.services.audio.channels.get_audio_channel_count',
        lambda path: called.append(path) or 99,
    )
    needs_again = partition_field_needs_mono_normalization(partition, 'audio_soprano')
    assert needs_again is True
    assert called == []


@pytest.mark.django_db
def test_tempo_variant_needs_mono_uses_cache(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    variant = PartitionAudioTempoVariant.objects.create(
        partition=partition,
        voice_type='S',
        tempo='0.50',
    )
    variant.audio_file.save(
        'v.mp3',
        SimpleUploadedFile('v.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    # Seed cache AFTER the file is attached so the pre_save signal does not clear it.
    variant.audio_channels = 1
    variant.save(update_fields=['audio_channels'])

    called = []
    monkeypatch.setattr(
        'psaumes.services.audio.channels.file_field_channel_count',
        lambda field: called.append(field) or 99,
    )

    assert tempo_variant_needs_mono_normalization(variant) is False
    assert tempo_variant_cached_channel_count(variant) == 1
    assert called == []


@pytest.mark.django_db
def test_pre_save_signal_invalidates_partition_audio_channels_on_file_change(
    tmp_path, settings
):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'orig.mp3',
        SimpleUploadedFile('orig.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    partition.audio_channels = {'audio_soprano': 2}
    partition.save(update_fields=['audio_channels'])
    partition.refresh_from_db()
    assert partition.audio_channels == {'audio_soprano': 2}

    # Replace the file with a different name; cache for that field must clear.
    partition.audio_soprano.save(
        'replaced.mp3',
        SimpleUploadedFile('replaced.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    partition.refresh_from_db()
    assert 'audio_soprano' not in (partition.audio_channels or {})


@pytest.mark.django_db
def test_pre_save_signal_invalidates_tempo_variant_audio_channels_on_file_change(
    tmp_path, settings
):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    variant = PartitionAudioTempoVariant.objects.create(
        partition=partition,
        voice_type='S',
        tempo='0.50',
    )
    variant.audio_file.save(
        'orig.mp3',
        SimpleUploadedFile('orig.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    # Seed cache after the file is attached.
    variant.audio_channels = 2
    variant.save(update_fields=['audio_channels'])
    variant.refresh_from_db()
    assert variant.audio_channels == 2

    # Replace the file with a different name; cache must clear.
    variant.audio_file.save(
        'replaced.mp3',
        SimpleUploadedFile('replaced.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    variant.refresh_from_db()
    assert variant.audio_channels is None


@pytest.mark.django_db
def test_invalidate_helpers_clear_cache_directly(tmp_path, settings):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_channels = {'audio_soprano': 2, 'audio_alto': 1}
    partition.save(update_fields=['audio_channels'])

    invalidate_partition_audio_channels(partition, 'audio_soprano')

    partition.refresh_from_db()
    assert partition.audio_channels == {'audio_alto': 1}

    variant = PartitionAudioTempoVariant.objects.create(
        partition=partition,
        voice_type='S',
        tempo='0.50',
        audio_channels=2,
    )
    invalidate_tempo_variant_audio_channels(variant)
    variant.refresh_from_db()
    assert variant.audio_channels is None


@pytest.mark.django_db
def test_enqueue_missing_audio_uses_db_cache_for_normalization(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/s.mp3')

    # Seed cache: soprano is stereo -> must be enqueued WITHOUT detect.
    partition.audio_channels = {'audio_soprano': 2}
    partition.save(update_fields=['audio_channels'])

    calls = []
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_audio_field_normalization',
        lambda partition, field_name, priority, detect=False: calls.append(
            (partition.id, field_name, priority, detect)
        ),
    )
    # No R2 access should occur during the scan.
    monkeypatch.setattr(
        'psaumes.services.audio.channels.file_field_channel_count',
        lambda field: pytest.fail('R2 access during scan'),
    )

    call_command(
        'enqueue_missing_audio',
        '--normalize-mono',
        '--upcoming-days',
        '0',
        '--limit',
        '5',
        stdout=StringIO(),
    )

    assert calls == [(partition.id, 'audio_soprano', AUDIO_QUEUE_PRIORITY_BULK, False)]


@pytest.mark.django_db
def test_enqueue_missing_audio_enqueues_detect_when_cache_missing(
    tmp_path, settings, monkeypatch
):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_soprano='audios/test/s.mp3')
    assert partition.audio_channels == {}

    calls = []
    monkeypatch.setattr(
        'psaumes.management.commands.enqueue_missing_audio.enqueue_partition_audio_field_normalization',
        lambda partition, field_name, priority, detect=False: calls.append(
            (partition.id, field_name, priority, detect)
        ),
    )
    monkeypatch.setattr(
        'psaumes.services.audio.channels.file_field_channel_count',
        lambda field: pytest.fail('R2 access during scan'),
    )

    call_command(
        'enqueue_missing_audio',
        '--normalize-mono',
        '--upcoming-days',
        '0',
        '--limit',
        '5',
        stdout=StringIO(),
    )

    assert calls == [(partition.id, 'audio_soprano', AUDIO_QUEUE_PRIORITY_BULK, True)]


@pytest.mark.django_db
def test_backfill_audio_channels_persists_detected_count(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'stereo.mp3',
        SimpleUploadedFile('stereo.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 2)

    call_command('backfill_audio_channels', '--upcoming-days', '0', stdout=StringIO())

    partition.refresh_from_db()
    assert partition.audio_channels == {'audio_soprano': 2}


@pytest.mark.django_db
def test_backfill_audio_channels_dry_run_does_not_persist(tmp_path, settings, monkeypatch):
    _use_local_file_storage(settings, tmp_path)
    partition = _make_partition_without_file()
    partition.audio_soprano.save(
        'stereo.mp3',
        SimpleUploadedFile('stereo.mp3', b'ID3' + b'\x00' * 2048),
        save=True,
    )
    monkeypatch.setattr('psaumes.services.audio.channels.get_audio_channel_count', lambda path: 2)

    call_command('backfill_audio_channels', '--dry-run', '--upcoming-days', '0', stdout=StringIO())

    partition.refresh_from_db()
    assert partition.audio_channels == {}


@pytest.mark.django_db
def test_is_mix_only_true_when_only_mix_present(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(audio_mix='audios/test/mix.mp3')
    assert partition.is_mix_only is True


@pytest.mark.django_db
def test_is_mix_only_false_when_satb_and_mix_present(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
        audio_mix='audios/test/mix.mp3',
    )
    assert partition.is_mix_only is False


@pytest.mark.django_db
def test_is_mix_only_false_when_satb_only_no_mix(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(
        audio_soprano='audios/test/s.mp3',
        audio_alto='audios/test/a.mp3',
        audio_tenor='audios/test/t.mp3',
        audio_basse='audios/test/b.mp3',
    )
    assert partition.is_mix_only is False


@pytest.mark.django_db
def test_is_mix_only_false_when_no_audio(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file()
    assert partition.is_mix_only is False


@pytest.mark.django_db
def test_is_mix_only_false_when_instrumental_and_mix_no_satb(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    partition = _make_partition_without_file(
        audio_instrumental='audios/test/i.mp3',
        audio_mix='audios/test/mix.mp3',
    )
    assert partition.is_mix_only is False
