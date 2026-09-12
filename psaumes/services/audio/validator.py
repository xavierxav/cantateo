import os
import logging

logger = logging.getLogger(__name__)

def validate_audio_file(file_path):
    """
    Validate audio file before saving to database.
    """
    try:
        # Check file exists
        if not os.path.exists(file_path):
            return False, "File not found"

        # Check file size (must be at least 1KB)
        file_size = os.path.getsize(file_path)
        if file_size < 1024:
            return False, f"File too small ({file_size} bytes)"

        # Check for MP3 frame header (0xFFF sync bytes)
        with open(file_path, 'rb') as f:
            header = f.read(4)
            if not header.startswith(b'\xff'):
                logger.warning(f"MP3 file has no sync bytes at start: {header[:2].hex()}")
                # Some MP3s have ID3 tags at start, try searching
                f.seek(0)
                first_kb = f.read(1024)
                if b'\xff\xfb' not in first_kb and b'\xff\xfa' not in first_kb:
                    return False, "Not a valid MP3 file (no sync bytes found)"

        # Try to parse with mutagen if available
        try:
            from mutagen.mp3 import MP3
            audio = MP3(file_path)
            if audio.info.length <= 0:
                return False, f"Zero duration ({audio.info.length}s)"

            logger.debug(f"MP3 validated: {file_size:,} bytes, {audio.info.length:.2f}s, {audio.info.bitrate} bps")
            return True, None
        except ImportError:
            logger.warning("mutagen not installed, skipping MP3 structure validation")
            return True, None

    except Exception as e:
        return False, f"Validation error: {type(e).__name__}: {str(e)}"


def validate_saved_audio(partition, voice_type):
    """
    Validate a specific audio file on a Partition.
    """
    try:
        field_val = partition.get_audio_field(voice_type)
        if not field_val:
            return False, f"No audio for voice {voice_type} attached"

        file_size = field_val.size
        if file_size < 1024:
            return False, f"Saved file too small ({file_size} bytes)"

        # Try to read a bit from the file to ensure it's accessible
        try:
            with field_val.open('rb') as f:
                header = f.read(4)
                if not header:
                    return False, "File is empty"
                logger.debug(f"File header: {header[:4].hex()}")
        except Exception as e:
            logger.warning(f"Could not verify file accessibility: {e}")

        logger.info(f"✓ Saved audio validated for {partition} ({voice_type}): {file_size:,} bytes")
        return True, None

    except Exception as e:
        return False, f"Saved validation error: {type(e).__name__}: {str(e)}"
