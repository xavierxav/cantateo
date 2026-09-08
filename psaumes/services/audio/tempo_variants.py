from decimal import Decimal, InvalidOperation
import logging
import os
import subprocess
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile

from ...models.audio_variant import (
    APPLE_GENERATED_TEMPO_VALUES,
    APPLE_TEMPO_VALUES,
    PartitionAudioTempoVariant,
    TEMPO_VARIANT_VOICE_CHOICES,
)
from ...models.partition import VOICE_FIELD_MAP, VOIX_LABELS
from .validator import validate_audio_file

logger = logging.getLogger(__name__)

APPLE_TEMPO_LABELS = {
    Decimal('0.50'): '0.5',
    Decimal('1.00'): '1.0',
    Decimal('1.50'): '1.5',
}
TEMPO_VARIANT_VOICES = tuple(choice[0] for choice in TEMPO_VARIANT_VOICE_CHOICES)


def parse_apple_tempo(value):
    try:
        tempo = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Unsupported tempo') from exc

    if tempo not in APPLE_TEMPO_VALUES:
        raise ValueError('Unsupported tempo')
    return tempo


def format_apple_tempo(tempo):
    return APPLE_TEMPO_LABELS[parse_apple_tempo(tempo)]


def tempo_id_fragment(tempo):
    return format_apple_tempo(tempo).replace('.', '_')


def get_partition_source_voice_field(partition, voice_type):
    if voice_type not in TEMPO_VARIANT_VOICES:
        return None
    field_name = VOICE_FIELD_MAP.get(voice_type)
    if not field_name:
        return None
    field = getattr(partition, field_name)
    return field if field else None


def build_source_voice_manifest(partition):
    voices = []
    for voice_type in TEMPO_VARIANT_VOICES:
        audio_field = get_partition_source_voice_field(partition, voice_type)
        if not audio_field:
            continue
        voices.append({
            'id': f"{partition.pk}_{voice_type}_tempo_1_0",
            'voice_type': voice_type,
            'label': VOIX_LABELS[voice_type],
            'url': audio_field.url,
        })
    return voices


def get_missing_source_voice_types(partition):
    return [
        voice_type for voice_type in TEMPO_VARIANT_VOICES
        if not get_partition_source_voice_field(partition, voice_type)
    ]


def get_ready_tempo_variant_voices(partition, tempo):
    tempo = parse_apple_tempo(tempo)
    if tempo == Decimal('1.00'):
        return build_source_voice_manifest(partition)

    variants = PartitionAudioTempoVariant.objects.filter(
        partition=partition,
        tempo=tempo,
        status=PartitionAudioTempoVariant.Status.SUCCEEDED,
    ).exclude(audio_file='')
    by_voice = {variant.voice_type: variant for variant in variants if variant.audio_file}

    voices = []
    for voice_type in TEMPO_VARIANT_VOICES:
        variant = by_voice.get(voice_type)
        if not variant:
            continue
        voices.append({
            'id': f"{partition.pk}_{voice_type}_tempo_{tempo_id_fragment(tempo)}",
            'voice_type': voice_type,
            'label': VOIX_LABELS[voice_type],
            'url': variant.audio_file.url,
        })
    return voices


def get_missing_tempo_variant_voice_types(partition, tempo):
    tempo = parse_apple_tempo(tempo)
    if tempo == Decimal('1.00'):
        return []

    ready = set(
        PartitionAudioTempoVariant.objects.filter(
            partition=partition,
            tempo=tempo,
            status=PartitionAudioTempoVariant.Status.SUCCEEDED,
        ).exclude(audio_file='').values_list('voice_type', flat=True)
    )
    return [
        voice_type for voice_type in TEMPO_VARIANT_VOICES
        if get_partition_source_voice_field(partition, voice_type) and voice_type not in ready
    ]


def build_partition_tempo_variant_status(partition, tempo):
    tempo = parse_apple_tempo(tempo)
    voices = get_ready_tempo_variant_voices(partition, tempo)
    source_missing = get_missing_source_voice_types(partition)

    if tempo == Decimal('1.00'):
        return {
            'status': 'ready' if voices else 'source_missing',
            'tempo': format_apple_tempo(tempo),
            'voices': voices,
            'missing_voice_types': source_missing,
        }

    missing_voice_types = get_missing_tempo_variant_voice_types(partition, tempo)
    variant_statuses = list(
        PartitionAudioTempoVariant.objects.filter(
            partition=partition,
            tempo=tempo,
        ).values_list('voice_type', 'status', 'last_error')
    )
    errors = [
        {'voice_type': voice_type, 'error': error}
        for voice_type, status, error in variant_statuses
        if status == PartitionAudioTempoVariant.Status.FAILED and error
    ]

    if not missing_voice_types and voices:
        status = 'ready'
    elif errors:
        status = 'failed'
    elif source_missing and not voices:
        status = 'source_missing'
    else:
        status = 'generating'

    return {
        'status': status,
        'tempo': format_apple_tempo(tempo),
        'voices': voices,
        'missing_voice_types': missing_voice_types or source_missing,
        'errors': errors,
    }


def ensure_tempo_variant_rows(partition, tempo, queue_priority='user'):
    tempo = parse_apple_tempo(tempo)
    if tempo not in APPLE_GENERATED_TEMPO_VALUES:
        return []

    variants = []
    for voice_type in TEMPO_VARIANT_VOICES:
        if not get_partition_source_voice_field(partition, voice_type):
            continue
        variant, _ = PartitionAudioTempoVariant.objects.get_or_create(
            partition=partition,
            voice_type=voice_type,
            tempo=tempo,
        )
        if variant.status not in {
            PartitionAudioTempoVariant.Status.STARTED,
            PartitionAudioTempoVariant.Status.SUCCEEDED,
        }:
            variant.status = PartitionAudioTempoVariant.Status.QUEUED
            variant.queue_priority = queue_priority
            variant.last_error = ''
            variant.save(update_fields=['status', 'queue_priority', 'last_error', 'updated_at'])
        variants.append(variant)
    return variants


def generate_tempo_variants_for_partition(partition, tempo):
    tempo = parse_apple_tempo(tempo)
    if tempo not in APPLE_GENERATED_TEMPO_VALUES:
        return 0

    generated_count = 0
    variants = ensure_tempo_variant_rows(partition, tempo)

    for variant in variants:
        if variant.status == PartitionAudioTempoVariant.Status.SUCCEEDED and variant.audio_file:
            continue

        variant.status = PartitionAudioTempoVariant.Status.STARTED
        variant.last_error = ''
        variant.save(update_fields=['status', 'last_error', 'updated_at'])

        try:
            source_field = get_partition_source_voice_field(partition, variant.voice_type)
            if not source_field:
                raise RuntimeError(f"Missing source audio for {variant.voice_type}")

            content = _render_tempo_variant(source_field, tempo)
            filename = f"{variant.voice_type.lower()}_tempo_{tempo_id_fragment(tempo)}.mp3"
            audio_file = SimpleUploadedFile(filename, content, content_type='audio/mpeg')
            variant.audio_file.save(filename, audio_file, save=False)
            variant.status = PartitionAudioTempoVariant.Status.SUCCEEDED
            variant.last_error = ''
            variant.save()
            generated_count += 1
        except Exception as exc:
            logger.exception(
                "Failed to generate tempo variant partition=%s voice=%s tempo=%s",
                partition.id,
                variant.voice_type,
                tempo,
            )
            variant.status = PartitionAudioTempoVariant.Status.FAILED
            variant.last_error = str(exc)
            variant.save(update_fields=['status', 'last_error', 'updated_at'])

    return generated_count


def _render_tempo_variant(source_field, tempo):
    temp_dir = tempfile.mkdtemp()
    source_path = None
    output_path = None

    try:
        ext = os.path.splitext(source_field.name)[1] or '.mp3'
        source_path = os.path.join(temp_dir, f"source{ext}")
        output_path = os.path.join(temp_dir, 'tempo.mp3')

        with open(source_path, 'wb') as destination:
            source_field.open('rb')
            for chunk in source_field.chunks():
                destination.write(chunk)

        if not _run_ffmpeg_tempo(source_path, output_path, tempo, 'rubberband'):
            logger.info("Falling back to FFmpeg atempo for tempo %s", tempo)
            if not _run_ffmpeg_tempo(source_path, output_path, tempo, 'atempo'):
                raise RuntimeError('FFmpeg tempo rendering failed')

        is_valid, error_msg = validate_audio_file(output_path)
        if not is_valid:
            raise RuntimeError(f"Generated tempo variant invalid: {error_msg}")

        with open(output_path, 'rb') as generated:
            return generated.read()
    finally:
        for path in (source_path, output_path):
            if path and os.path.exists(path):
                os.unlink(path)
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass


def _run_ffmpeg_tempo(source_path, output_path, tempo, engine):
    ffmpeg_path = os.environ.get('FFMPEG_PATH', 'ffmpeg')
    tempo_label = format_apple_tempo(tempo)
    filter_name = f"rubberband=tempo={tempo_label}" if engine == 'rubberband' else f"atempo={tempo_label}"

    cmd = [
        ffmpeg_path,
        '-y',
        '-i',
        source_path,
        '-filter:a',
        filter_name,
        '-vn',
        '-ac',
        '1',
        '-acodec',
        'libmp3lame',
        '-b:a',
        '128k',
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("FFmpeg %s tempo render could not run: %s", engine, exc)
        if os.path.exists(output_path):
            os.unlink(output_path)
        return False

    if result.returncode == 0 and os.path.exists(output_path):
        return True

    stderr = result.stderr.decode(errors='ignore') if result.stderr else ''
    logger.warning("FFmpeg %s tempo render failed: %s", engine, stderr[:500])
    if os.path.exists(output_path):
        os.unlink(output_path)
    return False
