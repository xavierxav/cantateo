import os


def _partition_slug(instance):
    """Préfixe de stockage d'une Partition.

    Psaume: ``{psaume.slug}`` (inchangé).
    Ordinaire: ``{ordinaire.slug}/{partie_messe.lower()}`` — la partie de messe
    évite la collision entre les différentes partitions d'un même ordinaire
    (Kyrie, Sanctus, ... partageaient autrefois la même clé R2).
    Sans parent: ``partition_{pk}`` (fallback inchangé).
    """
    if instance.psaume_id:
        psaume = instance.psaume
        if psaume and psaume.slug:
            return psaume.slug
    if instance.ordinaire_id or instance.ordinaire:
        ordinaire = instance.ordinaire
        if ordinaire and ordinaire.slug:
            base = ordinaire.slug
            partie = (instance.partie_messe or '').strip().lower()
            if partie:
                return f'{base}/{partie}'
            # Défensif: une partition d'ordinaire sans partie_messe ne devrait
            # pas exister (clean() l'interdit), mais on évite la collision.
            return f'{base}/partition_{instance.pk or "temp"}'
    return f'partition_{instance.pk or "temp"}'


def partition_format_path(instance, filename, format_type):
    """
    Generate upload path for partition files (PDF or MXL).
    Organizes by psalm slug.
    """
    ext = os.path.splitext(filename)[1]
    slug = _partition_slug(instance)
    return f'partitions/{format_type}/{slug}{ext}'


def partition_pdf_path(instance, filename):
    """Generate upload path for PDF partitions."""
    return partition_format_path(instance, filename, 'pdf')


def partition_mxl_path(instance, filename):
    """Generate upload path for MXL partitions."""
    return partition_format_path(instance, filename, 'mxl')


def partition_omr_source_path(instance, filename):
    """Generate upload path for optional uploaded OMR source images."""
    partition = instance.partition
    ext = os.path.splitext(filename)[1]

    if not partition:
        return f'partitions/omr-source/partition_temp{ext}'

    slug = _partition_slug(partition)
    return f'partitions/omr-source/{slug}{ext}'


def partition_audio_path(instance, filename, voice_name=None):
    """
    Generate upload path for audio files organized by partition.
    Organizes by psalm slug of the parent Psaume.
    """
    folder = _partition_slug(instance)
    ext = os.path.splitext(filename)[1]

    if not voice_name:
        voice_name = 'audio'

    return f'audios/{folder}/{voice_name}{ext}'


def partition_audio_soprano_path(instance, filename):
    return partition_audio_path(instance, filename, 'soprano')

def partition_audio_alto_path(instance, filename):
    return partition_audio_path(instance, filename, 'alto')

def partition_audio_tenor_path(instance, filename):
    return partition_audio_path(instance, filename, 'tenor')

def partition_audio_basse_path(instance, filename):
    return partition_audio_path(instance, filename, 'basse')

def partition_audio_instrumental_path(instance, filename):
    return partition_audio_path(instance, filename, 'instrumental')

def partition_audio_mix_path(instance, filename):
    return partition_audio_path(instance, filename, 'mix')


def partition_audio_tempo_variant_path(instance, filename):
    """Generate upload path for generated Apple/Safari tempo variants."""
    partition = instance.partition
    folder = _partition_slug(partition) if partition else 'partition_temp'

    voice_names = {
        'S': 'soprano',
        'A': 'alto',
        'T': 'tenor',
        'B': 'basse',
        'I': 'instrumental',
    }
    voice_name = voice_names.get(instance.voice_type, 'audio')
    tempo = str(instance.tempo).replace('.', '_')
    ext = os.path.splitext(filename)[1] or '.mp3'

    return f'audios/{folder}/tempo_{tempo}/{voice_name}{ext}'
