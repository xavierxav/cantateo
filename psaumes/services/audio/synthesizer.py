import os
import tempfile
import logging
import subprocess
from django.conf import settings

logger = logging.getLogger(__name__)

def synthesize_voice_to_audio(voice_part, output_path, soundfont_path=None, tempo_factor=0.7):
    """
    Convert a music21 Part to an audio file using FluidSynth.

    Args:
        voice_part: music21 Part object
        output_path: Path for output audio file (wav or mp3)
        soundfont_path: Path to SoundFont file (optional, uses .env if not specified)
        tempo_factor: Factor to multiply tempo by (0.7, default)

    Returns:
        True if successful, False otherwise
    """
    try:
        from dotenv import load_dotenv
        from music21 import midi, tempo
    except ImportError as e:
        logger.error(f"Missing dependency: {e}. Run: pip install python-dotenv music21")
        raise

    # Always try to load .env vars (idempotent)
    load_dotenv()

    if soundfont_path is None:
        # Try to get from .env first, then settings
        soundfont_path = os.getenv('SOUNDFONT_PATH')
        if not soundfont_path:
            soundfont_path = getattr(settings, 'SOUNDFONT_PATH', None)

    if not soundfont_path or not os.path.exists(soundfont_path):
        logger.error(f"SoundFont not found at: {soundfont_path}")
        raise FileNotFoundError(f"SoundFont file not found: {soundfont_path}")

    # Get FluidSynth executable path (defaults to system PATH)
    fluidsynth_path = os.getenv('FLUIDSYNTH_PATH', 'fluidsynth')

    # Apply tempo factor to slow down the music
    existing_tempos = list(voice_part.recurse().getElementsByClass(tempo.MetronomeMark))
    if existing_tempos:
        for t in existing_tempos:
            t.number = t.number * tempo_factor
    else:
        # Add a slow tempo marking (60 BPM * 0.5 = 30 BPM for very slow playback)
        slow_tempo = tempo.MetronomeMark(number=60 * tempo_factor)
        voice_part.insert(0, slow_tempo)

    # Create temporary MIDI file
    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as midi_file:
        midi_path = midi_file.name

    try:
        # Write MIDI
        voice_part.write('midi', fp=midi_path)

        # Synthesize to audio using FluidSynth directly
        fluidsynth_cmd = fluidsynth_path if fluidsynth_path and os.path.exists(fluidsynth_path) else 'fluidsynth'

        # Determine output format
        if output_path.endswith('.mp3'):
            # FluidSynth outputs WAV, convert to MP3
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
                wav_path = wav_file.name

            logger.debug(f"Synthesizing MIDI to WAV using FluidSynth: {fluidsynth_cmd}")
            result = subprocess.run([
                fluidsynth_cmd, '-ni', '-F', wav_path, '-r', '44100',
                soundfont_path, midi_path
            ], capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                logger.error(f"✗ FluidSynth failed: {result.stderr}")
                raise RuntimeError(f"FluidSynth failed: {result.stderr}")

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1024:
                raise RuntimeError(f"WAV file invalid or too small: {wav_path}")

            logger.debug(f"✓ WAV synthesized: {os.path.getsize(wav_path)} bytes")

            # Convert WAV to MP3
            try:
                _convert_wav_to_mp3(wav_path, output_path)
            finally:
                if os.path.exists(wav_path):
                    os.unlink(wav_path)
        else:
            # Output directly as WAV
            logger.debug(f"Synthesizing MIDI to WAV using FluidSynth: {fluidsynth_cmd}")
            result = subprocess.run([
                fluidsynth_cmd, '-ni', '-F', output_path, '-r', '44100',
                soundfont_path, midi_path
            ], capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                logger.error(f"✗ FluidSynth failed: {result.stderr}")
                raise RuntimeError(f"FluidSynth failed: {result.stderr}")

            if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
                raise RuntimeError(f"Output audio file invalid or too small: {output_path}")

            logger.debug(f"✓ Audio synthesized: {os.path.getsize(output_path)} bytes")

        return True

    finally:
        if os.path.exists(midi_path):
            os.unlink(midi_path)


def _convert_wav_to_mp3(wav_path, mp3_path):
    """
    Convert WAV to MP3 using ffmpeg.
    """
    ffmpeg_path = os.environ.get('FFMPEG_PATH', 'ffmpeg')
    logger.debug(f"Converting {wav_path} to MP3 using ffmpeg: {ffmpeg_path}...")

    try:
        result = subprocess.run([
            ffmpeg_path, '-y', '-i', wav_path, '-acodec', 'libmp3lame',
            '-ac', '1', '-ab', '128k', mp3_path
        ], capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"ffmpeg failed: {result.stderr}")
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

        if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 1024:
            raise RuntimeError(f"MP3 file invalid or too small: {mp3_path}")

        logger.debug(f"✓ WAV to MP3 conversion successful: {mp3_path}")

    except FileNotFoundError:
        raise RuntimeError("FFmpeg not found. Install it: sudo apt install ffmpeg")
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg conversion timed out (exceeded 120s)")
    except Exception as e:
        raise RuntimeError(f"FFmpeg conversion failed: {e}")
