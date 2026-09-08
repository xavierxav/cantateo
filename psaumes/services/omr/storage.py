from pathlib import Path

from django.core.files import File


def save_musicxml_to_partition(partition, musicxml_path: Path) -> str:
    filename = _musicxml_filename(partition)
    with musicxml_path.open('rb') as handle:
        partition.partition_mxl.save(filename, File(handle), save=False)
    partition.save(update_fields=['partition_mxl'])
    return partition.partition_mxl.name


def _musicxml_filename(partition):
    if partition.psaume and partition.psaume.slug:
        return f'{partition.psaume.slug}.musicxml'
    return f'partition_{partition.pk}.musicxml'
