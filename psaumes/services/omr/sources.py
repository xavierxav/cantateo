import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...models import PartitionOmrJob


class OmrSourceError(ValueError):
    """Raised when an OMR source is missing or unsupported."""


@dataclass(frozen=True)
class SourceFingerprint:
    name: str
    sha256: str
    extension: str


def fingerprint_partition_omr_source(partition, source_type=None) -> SourceFingerprint:
    field = _source_field(partition, source_type)
    digest = hashlib.sha256()
    name = field.name or ''

    try:
        with field.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise OmrSourceError('OMR source file is missing from storage.') from exc

    extension = os.path.splitext(name)[1].lower()
    return SourceFingerprint(name=name, sha256=digest.hexdigest(), extension=extension)


def copy_partition_omr_source(partition, destination_dir: Path, source_type=None) -> Path:
    field = _source_field(partition, source_type)
    source_name = os.path.basename(field.name or 'partition.pdf')
    output_path = destination_dir / source_name

    with field.open('rb') as source, output_path.open('wb') as output:
        shutil.copyfileobj(source, output)

    return output_path


def _source_field(partition, source_type=None):
    source_type = source_type or PartitionOmrJob.SourceType.PARTITION_PDF
    if source_type == PartitionOmrJob.SourceType.PARTITION_PDF:
        field = partition.partition_pdf
    else:
        job = getattr(partition, 'omr_job', None)
        field = job.source_file if job else None

    if not field:
        raise OmrSourceError('Partition has no OMR source file.')
    return field
