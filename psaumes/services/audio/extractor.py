import logging

logger = logging.getLogger(__name__)

def extract_voices_from_mxl(mxl_path):
    """
    Parse MXL file and extract individual voice parts.

    MXL structure (typical SATB arrangement):
    - Part 0 (Treble): Contains Soprano and Alto on same staff
    - Part 1 (Bass): Contains Tenor and Bass on same staff

    For each chord, top note goes to S/T, bottom note goes to A/B.

    Args:
        mxl_path: Path to the MXL file

    Returns:
        Dict with voice codes as keys and music21 Part objects as values
        e.g., {'S': soprano_part, 'A': alto_part, 'T': tenor_part, 'B': bass_part}
    """
    try:
        from music21 import converter, stream
    except ImportError:
        logger.error("music21 is not installed. Run: pip install music21")
        raise

    score = converter.parse(mxl_path)

    voices = {}
    parts = list(score.parts)

    if len(parts) < 2:
        logger.warning(f"MXL has only {len(parts)} part(s), expected 2 (treble+bass)")
        return voices

    # Part 0: Treble clef (Soprano + Alto)
    treble_part = parts[0]
    soprano_part = stream.Part()
    alto_part = stream.Part()

    # Part 1: Bass clef (Tenor + Bass)
    bass_part = parts[1]
    tenor_part = stream.Part()
    bass_voice_part = stream.Part()

    # Copy time signature and key signature to new parts
    for part in [soprano_part, alto_part, tenor_part, bass_voice_part]:
        for element in treble_part.recurse().getElementsByClass(['TimeSignature', 'KeySignature']):
            part.insert(0, element)

    # Extract Soprano and Alto from treble staff
    _split_staff_to_voices(treble_part, soprano_part, alto_part)

    # Extract Tenor and Bass from bass staff
    _split_staff_to_voices(bass_part, tenor_part, bass_voice_part)

    voices['S'] = soprano_part
    voices['A'] = alto_part
    voices['T'] = tenor_part
    voices['B'] = bass_voice_part

    return voices


def _split_staff_to_voices(source_part, high_voice, low_voice):
    """
    Split a staff containing 2 voices into separate parts.

    For each chord: top note -> high_voice, bottom note -> low_voice
    For single notes: duplicate to both voices

    Args:
        source_part: music21 Part with combined voices
        high_voice: Part to receive high notes (Soprano or Tenor)
        low_voice: Part to receive low notes (Alto or Bass)
    """
    from music21 import note, chord, stream

    for measure in source_part.getElementsByClass('Measure'):
        high_measure = stream.Measure(number=measure.number)
        low_measure = stream.Measure(number=measure.number)

        for element in measure.notesAndRests:
            if isinstance(element, chord.Chord):
                # Sort pitches high to low
                pitches = sorted(element.pitches, reverse=True)
                if len(pitches) >= 2:
                    # Top note to high voice
                    high_note = note.Note(pitches[0])
                    high_note.duration = element.duration
                    high_note.offset = element.offset
                    high_measure.insert(element.offset, high_note)

                    # Bottom note to low voice
                    low_note = note.Note(pitches[-1])
                    low_note.duration = element.duration
                    low_note.offset = element.offset
                    low_measure.insert(element.offset, low_note)
                else:
                    # Single note chord - duplicate to both
                    n = note.Note(pitches[0])
                    n.duration = element.duration
                    high_measure.insert(element.offset, n)
                    n2 = note.Note(pitches[0])
                    n2.duration = element.duration
                    low_measure.insert(element.offset, n2)

            elif isinstance(element, note.Note):
                # Single note - duplicate to both voices
                high_note = note.Note(element.pitch)
                high_note.duration = element.duration
                high_measure.insert(element.offset, high_note)

                low_note = note.Note(element.pitch)
                low_note.duration = element.duration
                low_measure.insert(element.offset, low_note)

            elif isinstance(element, note.Rest):
                # Rest - add to both voices
                high_rest = note.Rest()
                high_rest.duration = element.duration
                high_measure.insert(element.offset, high_rest)

                low_rest = note.Rest()
                low_rest.duration = element.duration
                low_measure.insert(element.offset, low_rest)

        high_voice.append(high_measure)
        low_voice.append(low_measure)
