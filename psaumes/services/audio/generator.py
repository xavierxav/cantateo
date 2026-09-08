import os
import tempfile
import logging
import subprocess

from django.core.files.uploadedfile import SimpleUploadedFile

from .extractor import extract_voices_from_mxl
from .synthesizer import synthesize_voice_to_audio
from .validator import validate_audio_file

logger = logging.getLogger(__name__)

# Individual voice types from MXL
SATB_VOICES = ['S', 'A', 'T', 'B']
# Existing non-synthetic audio in any player field should block synthetic generation.
PARTITION_AUDIO_VOICES = ['S', 'A', 'T', 'B', 'I', 'M']


def get_voice_name(type_voix):
    mapping = {'S': 'soprano', 'A': 'alto', 'T': 'tenor', 'B': 'basse', 'I': 'instrumental', 'M': 'mix'}
    return mapping.get(type_voix)


def missing_satb_of_partition(partition):
    """Check if any SATB voice is missing."""
    return [v for v in SATB_VOICES if not getattr(partition, f'audio_{get_voice_name(v)}')]


def get_missing_voices(partition):
    """
    Return missing synthetic voice types for a partition that has an MXL file.
    Synthetic MXL generation intentionally creates SATB voices only.
    """
    if not partition.partition_mxl:
        return []

    # Map voice type to field name
    VOICE_FIELD_MAP = {
        'S': 'audio_soprano',
        'A': 'audio_alto',
        'T': 'audio_tenor',
        'B': 'audio_basse',
    }

    missing = []
    for voice_type in SATB_VOICES:
        field_name = VOICE_FIELD_MAP[voice_type]
        if not getattr(partition, field_name):
            missing.append(voice_type)

    return missing


def should_generate_synthetic_voices(partition):
    """
    Check if synthetic voice generation should proceed.
    Only proceed if NO non-synthetic voice exists.
    """
    if not partition.mp3_synthetiques:
        # Check if any audio field is populated
        for v in PARTITION_AUDIO_VOICES:
            if getattr(partition, f'audio_{get_voice_name(v)}'):
                return False
    return True


def generate_mix_track(partition):
    """
    Generate a mix track combining all SATB voices using FFmpeg.
    Saves to partition.audio_mix and returns True if successful.
    """
    # Get all SATB audio files
    satb_fields = ['audio_soprano', 'audio_alto', 'audio_tenor', 'audio_basse']
    if any(not getattr(partition, f) for f in satb_fields):
        logger.warning(f"[{partition.id}] Cannot generate mix: missing SATB voices")
        return None

    temp_files = []
    mix_path = None
    temp_dir = None

    try:
        # Download SATB files to temp directory
        temp_dir = tempfile.mkdtemp()
        input_paths = []

        for field_name in satb_fields:
            audio_field = getattr(partition, field_name)
            ext = os.path.splitext(audio_field.name)[1] or '.mp3'
            temp_path = os.path.join(temp_dir, f"{field_name}{ext}")
            temp_files.append(temp_path)

            with open(temp_path, 'wb') as f:
                audio_field.seek(0)
                f.write(audio_field.read())
            input_paths.append(temp_path)

        # Generate mix with FFmpeg
        mix_path = os.path.join(temp_dir, "mix.mp3")
        temp_files.append(mix_path)

        cmd = [
            os.environ.get('FFMPEG_PATH', 'ffmpeg'), '-y',
            '-i', input_paths[0],
            '-i', input_paths[1],
            '-i', input_paths[2],
            '-i', input_paths[3],
            '-filter_complex', 'amix=inputs=4:duration=longest:normalize=0',
            '-ab', '192k',
            mix_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"[{partition.id}] FFmpeg mix failed: {result.stderr.decode()}")
            return None

        # Validate generated mix
        is_valid, error_msg = validate_audio_file(mix_path)
        if not is_valid:
            logger.error(f"[{partition.id}] ✗ Generated mix invalid: {error_msg}")
            return None

        # Save to database
        with open(mix_path, 'rb') as f:
            audio_content = f.read()

        audio_file = SimpleUploadedFile(
            "mix_synth.mp3",
            audio_content,
            content_type='audio/mpeg'
        )
        partition.audio_mix.save("mix_synth.mp3", audio_file, save=False)
        partition.mp3_synthetiques = True
        partition.save()

        logger.info(f"[{partition.id}] ✓ Mix generated successfully")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"[{partition.id}] FFmpeg mix timeout")
        return None
    except Exception as e:
        logger.exception(f"[{partition.id}] ✗ Failed to generate mix: {e}")
        return None
    finally:
        # Cleanup temp files
        for path in temp_files:
            if path and os.path.exists(path):
                os.unlink(path)
        if temp_dir and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass


def generate_missing_voices_for_chant(partition):
    """
    Generate all missing voice audio files for a partition from its MXL file.
    Generates SATB voices only.
    """
    if not partition.partition_mxl:
        logger.debug(f"Partition {partition.id} has no MXL file")
        return 0

    if not should_generate_synthetic_voices(partition):
        logger.info(f"[{partition.id}] Non-synthetic audio exists - skipping synthetic generation")
        return 0

    missing = get_missing_voices(partition)
    if not missing:
        logger.debug(f"Partition {partition.id} has all voices")
        return 0

    missing_satb = [v for v in missing if v in SATB_VOICES]

    logger.info(f"[{partition.id}] Generating {len(missing)} missing voices: {missing}")

    created_count = 0

    if missing_satb:
        mxl_temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mxl', delete=False) as mxl_tmp:
                mxl_temp_path = mxl_tmp.name
                with partition.partition_mxl.open('rb') as mxl_file:
                    mxl_tmp.write(mxl_file.read())
        except Exception as e:
            logger.exception(f"[{partition.id}] ✗ Failed to download MXL file: {e}")
            if mxl_temp_path and os.path.exists(mxl_temp_path):
                os.unlink(mxl_temp_path)
            return 0

        try:
            voices = extract_voices_from_mxl(mxl_temp_path)

            to_generate = [v for v in missing_satb if v in voices]
            for voice_type in to_generate:
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_audio:
                        tmp_path = tmp_audio.name

                    synthesize_voice_to_audio(voices[voice_type], tmp_path)
                    is_valid, error_msg = validate_audio_file(tmp_path)
                    if not is_valid:
                        logger.error(f"[{partition.id}] ✗ Generated {voice_type} invalid: {error_msg}")
                        continue

                    with open(tmp_path, 'rb') as f:
                        audio_content = f.read()

                    audio_file = SimpleUploadedFile(
                        f"{voice_type.lower()}_synth.mp3",
                        audio_content,
                        content_type='audio/mpeg'
                    )
                    
                    field_name = f'audio_{get_voice_name(voice_type)}'
                    getattr(partition, field_name).save(f"{voice_type.lower()}_synth.mp3", audio_file, save=False)
                    created_count += 1
                    logger.info(f"[{partition.id}] ✓ {voice_type} generated")

                except Exception as e:
                    logger.exception(f"[{partition.id}] ✗ Failed to generate {voice_type}: {e}")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

        except Exception as e:
            logger.exception(f"[{partition.id}] ✗ Failed during SATB extraction/synthesis: {e}")
        finally:
            if mxl_temp_path and os.path.exists(mxl_temp_path):
                os.unlink(mxl_temp_path)
            
        partition.mp3_synthetiques = partition.mp3_synthetiques or created_count > 0
        partition.save()

    return created_count


def ensure_voices_for_chant(partition, timeout_seconds=300):
    """
    Lazy generation entry point: ensure a partition has all voice audio files.
    """
    if not partition.partition_mxl:
        return False

    missing = get_missing_voices(partition)
    if not missing:
        return True

    logger.info(f"Starting voice generation for partition {partition.id} (missing: {missing})")

    try:
        generate_missing_voices_for_chant(partition)
        partition.refresh_from_db()
        return len(get_missing_voices(partition)) == 0

    except Exception as e:
        logger.exception(f"✗ Failed to generate voices for partition {partition.id}: {e}")
        return False
