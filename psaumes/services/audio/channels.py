import logging
import os
import subprocess
import tempfile

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q

from ...models import Partition, PartitionAudioTempoVariant
from ...models.partition import VOICE_FIELD_MAP
from .validator import validate_audio_file

logger = logging.getLogger(__name__)

NORMALIZABLE_PARTITION_AUDIO_FIELDS = tuple(
    field_name for voice_type, field_name in VOICE_FIELD_MAP.items() if voice_type != 'M'
)


class AudioNormalizationResult:
    def __init__(
        self,
        *,
        changed=False,
        skipped=False,
        missing_source=False,
        old_name='',
        new_name='',
        channels=None,
        delete_error='',
    ):
        self.changed = changed
        self.skipped = skipped
        self.missing_source = missing_source
        self.old_name = old_name
        self.new_name = new_name
        self.channels = channels
        self.delete_error = delete_error


def get_audio_channel_count(file_path):
    ffprobe_path = os.environ.get('FFPROBE_PATH', 'ffprobe')
    result = subprocess.run(
        [
            ffprobe_path,
            '-v',
            'error',
            '-select_streams',
            'a:0',
            '-show_entries',
            'stream=channels',
            '-of',
            'csv=p=0',
            file_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"ffprobe failed: {stderr}")
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned invalid channel count: {result.stdout!r}") from exc


def file_field_channel_count(file_field):
    if not file_field:
        return None
    if not file_field.name or not file_field.storage.exists(file_field.name):
        return None
    source_path = None
    try:
        source_path = _file_field_to_temp_path(file_field)
        return get_audio_channel_count(source_path)
    finally:
        if source_path and os.path.exists(source_path):
            os.unlink(source_path)


def _cached_partition_channel_count(partition, field_name):
    cache = partition.audio_channels or {}
    if not isinstance(cache, dict):
        return None
    value = cache.get(field_name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _persist_partition_channel_count(partition, field_name, channels):
    if partition.pk is None or channels is None:
        return
    cache = dict(partition.audio_channels or {})
    cache[field_name] = int(channels)
    partition.audio_channels = cache
    Partition.objects.filter(pk=partition.pk).update(audio_channels=cache)


def _persist_tempo_variant_channel_count(variant, channels):
    if variant.pk is None or channels is None:
        return
    variant.audio_channels = int(channels)
    PartitionAudioTempoVariant.objects.filter(pk=variant.pk).update(
        audio_channels=variant.audio_channels,
    )


def invalidate_partition_audio_channels(partition, field_name):
    if partition.pk is None:
        return
    cache = dict(partition.audio_channels or {})
    if field_name not in cache:
        return
    cache.pop(field_name, None)
    partition.audio_channels = cache
    Partition.objects.filter(pk=partition.pk).update(audio_channels=cache)


def invalidate_tempo_variant_audio_channels(variant):
    if variant.pk is None or variant.audio_channels is None:
        return
    variant.audio_channels = None
    PartitionAudioTempoVariant.objects.filter(pk=variant.pk).update(
        audio_channels=None,
    )


def partition_field_needs_mono_normalization(partition, field_name):
    if field_name not in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
        return False
    field = getattr(partition, field_name)
    if not field:
        return False
    cached = _cached_partition_channel_count(partition, field_name)
    if cached is not None:
        return cached > 1
    channels = file_field_channel_count(field)
    if channels is not None:
        _persist_partition_channel_count(partition, field_name, channels)
    return (channels or 0) > 1


def partition_field_cached_channel_count(partition, field_name):
    """Return cached channel count without R2 access, or None if unknown."""
    if field_name not in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
        return None
    return _cached_partition_channel_count(partition, field_name)


def tempo_variant_needs_mono_normalization(variant):
    if not variant.audio_file:
        return False
    cached = variant.audio_channels
    if cached is not None:
        return cached > 1
    channels = file_field_channel_count(variant.audio_file)
    if channels is not None:
        _persist_tempo_variant_channel_count(variant, channels)
    return (channels or 0) > 1


def tempo_variant_cached_channel_count(variant):
    """Return cached channel count without R2 access, or None if unknown."""
    return variant.audio_channels


def normalize_uploaded_partition_audio_fields(partition, field_names=None):
    field_names = field_names or NORMALIZABLE_PARTITION_AUDIO_FIELDS
    for field_name in field_names:
        if field_name in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
            _normalize_assigned_file_to_mono(partition, field_name)


def normalize_partition_audio_field(partition, field_name, *, delete_old=True):
    if field_name not in NORMALIZABLE_PARTITION_AUDIO_FIELDS:
        return AudioNormalizationResult(skipped=True)
    return _normalize_model_file_to_mono(partition, field_name, delete_old=delete_old)


def normalize_tempo_variant_audio_file(variant, *, delete_old=True):
    return _normalize_model_file_to_mono(variant, 'audio_file', delete_old=delete_old)


def _normalize_assigned_file_to_mono(instance, field_name):
    field = getattr(instance, field_name)
    if not field:
        return AudioNormalizationResult(skipped=True)

    source_path = None
    output_path = None
    try:
        source_path = _file_field_to_temp_path(field)
        channels = get_audio_channel_count(source_path)
        _populate_instance_audio_channels_cache(instance, field_name, channels)
        if channels <= 1:
            return AudioNormalizationResult(skipped=True, channels=channels)

        output_path = _temp_mp3_path()
        _run_ffmpeg_mono(source_path, output_path)
        _validate_generated_mp3(output_path)
        filename = _mono_filename(os.path.basename(field.name or 'audio.mp3'))
        with open(output_path, 'rb') as generated:
            setattr(
                instance,
                field_name,
                SimpleUploadedFile(filename, generated.read(), content_type='audio/mpeg'),
            )
        # After mono conversion the source is replaced in-memory; mark the new
        # file as mono (1 channel) so the eventual save persists correct cache.
        _populate_instance_audio_channels_cache(instance, field_name, 1)
        return AudioNormalizationResult(changed=True, channels=channels)
    finally:
        _cleanup_paths(source_path, output_path)


def _populate_instance_audio_channels_cache(instance, field_name, channels):
    """Populate the in-memory audio_channels cache for a not-yet-saved instance."""
    if channels is None:
        return
    if isinstance(instance, Partition):
        cache = dict(instance.audio_channels or {})
        cache[field_name] = int(channels)
        instance.audio_channels = cache
    else:
        instance.audio_channels = int(channels)


def _persist_model_audio_channels_cache(instance, field_name, channels):
    """Persist discovered channel count to DB without re-running model signals."""
    if channels is None or instance.pk is None:
        return
    if isinstance(instance, Partition):
        _persist_partition_channel_count(instance, field_name, channels)
    else:
        _persist_tempo_variant_channel_count(instance, channels)


def _normalize_model_file_to_mono(instance, field_name, *, delete_old):
    field = getattr(instance, field_name)
    if not field:
        return AudioNormalizationResult(skipped=True)

    old_name = field.name
    old_storage = field.storage
    if not old_name or not old_storage.exists(old_name):
        return AudioNormalizationResult(
            skipped=True,
            missing_source=True,
            old_name=old_name,
            delete_error='Source file missing from storage',
        )
    source_path = None
    output_path = None
    try:
        source_path = _file_field_to_temp_path(field)
        channels = get_audio_channel_count(source_path)
        _persist_model_audio_channels_cache(instance, field_name, channels)
        if channels <= 1:
            return AudioNormalizationResult(skipped=True, old_name=old_name, channels=channels)

        output_path = _temp_mp3_path()
        _run_ffmpeg_mono(source_path, output_path)
        _validate_generated_mp3(output_path)

        new_name = _mono_storage_name(old_name or f'{field_name}.mp3')
        with open(output_path, 'rb') as generated:
            new_name = old_storage.save(new_name, ContentFile(generated.read()))
        getattr(instance, field_name).name = new_name
        try:
            instance.save(update_fields=[field_name])
        except Exception:
            getattr(instance, field_name).name = old_name
            if new_name != old_name:
                try:
                    old_storage.delete(new_name)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Unable to clean failed mono audio save %s: %s",
                        new_name,
                        cleanup_exc,
                    )
            raise

        # The normalized file is now mono; persist the updated cache so future
        # scans skip R2 entirely.
        _persist_model_audio_channels_cache(instance, field_name, 1)

        delete_error = ''
        if delete_old:
            delete_error = _delete_old_audio_file_if_unreferenced(old_storage, old_name, new_name)
        return AudioNormalizationResult(
            changed=True,
            old_name=old_name,
            new_name=new_name,
            channels=channels,
            delete_error=delete_error,
        )
    finally:
        _cleanup_paths(source_path, output_path)


def _file_field_to_temp_path(file_field):
    ext = os.path.splitext(file_field.name or '')[1] or '.mp3'
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    with open(temp_path, 'wb') as destination:
        try:
            file_field.open('rb')
            for chunk in file_field.chunks():
                destination.write(chunk)
        finally:
            file_field.close()
    return temp_path


def _temp_mp3_path():
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    return path


def _run_ffmpeg_mono(source_path, output_path):
    ffmpeg_path = os.environ.get('FFMPEG_PATH', 'ffmpeg')
    result = subprocess.run(
        [
            ffmpeg_path,
            '-y',
            '-i',
            source_path,
            '-vn',
            '-ac',
            '1',
            '-acodec',
            'libmp3lame',
            '-b:a',
            '128k',
            output_path,
        ],
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors='ignore') if result.stderr else ''
        raise RuntimeError(f"ffmpeg mono conversion failed: {stderr[:500]}")


def _validate_generated_mp3(path):
    is_valid, error_msg = validate_audio_file(path)
    if not is_valid:
        raise RuntimeError(f"Generated mono MP3 invalid: {error_msg}")


def _mono_filename(filename):
    root, ext = os.path.splitext(filename)
    ext = ext or '.mp3'
    if root.endswith('_mono'):
        return f"{root}{ext}"
    return f"{root}_mono{ext}"


def _mono_storage_name(storage_name):
    folder, filename = os.path.split(storage_name)
    mono_filename = _mono_filename(filename)
    if folder:
        return f'{folder}/{mono_filename}'
    return mono_filename


def _delete_old_audio_file_if_unreferenced(storage, old_name, new_name):
    if not old_name or old_name == new_name:
        return ''
    if is_audio_file_referenced(old_name):
        return ''
    try:
        storage.delete(old_name)
    except Exception as exc:
        logger.warning("Unable to delete old stereo audio %s: %s", old_name, exc)
        return str(exc)
    return ''


def is_audio_file_referenced(name):
    if not name:
        return False

    partition_query = Q()
    for field_name in VOICE_FIELD_MAP.values():
        partition_query |= Q(**{field_name: name})

    return (
        Partition.objects.filter(partition_query).exists()
        or PartitionAudioTempoVariant.objects.filter(audio_file=name).exists()
    )


def _cleanup_paths(*paths):
    for path in paths:
        if path and os.path.exists(path):
            os.unlink(path)
