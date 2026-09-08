import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from .backends.base import OmrOptions
from .pdf import convert_pdf_to_images
from .registry import get_omr_backend
from .sources import copy_partition_omr_source, fingerprint_partition_omr_source
from .storage import save_musicxml_to_partition


@dataclass(frozen=True)
class OmrPipelineResult:
    source_name: str
    source_sha256: str
    backend: str
    backend_version: str
    model_profile: str
    page_count: int
    processed_pages: int
    generated_file_name: str


def generate_musicxml_for_partition(partition, source_type=None) -> OmrPipelineResult:
    fingerprint = fingerprint_partition_omr_source(partition, source_type=source_type)

    with tempfile.TemporaryDirectory(prefix='cantateo-omr-') as tmp:
        tmp_dir = Path(tmp)
        source_path = copy_partition_omr_source(partition, tmp_dir, source_type=source_type)
        image_dir = tmp_dir / 'images'
        output_dir = tmp_dir / 'output'
        image_dir.mkdir()
        output_dir.mkdir()

        if fingerprint.extension == '.pdf':
            image_paths = convert_pdf_to_images(
                source_path,
                image_dir,
                max_pages=getattr(settings, 'OMR_MAX_PAGES', 1),
                dpi=getattr(settings, 'OMR_PDF_DPI', 250),
            )
        elif fingerprint.extension in {'.png', '.jpg', '.jpeg'}:
            image_path = image_dir / f'page-1{fingerprint.extension}'
            os.replace(source_path, image_path)
            image_paths = [image_path]
        else:
            raise ValueError(f'Unsupported OMR source extension: {fingerprint.extension}')

        backend = get_omr_backend()
        result = backend.recognize(
            image_paths,
            output_dir,
            OmrOptions(
                timeout_seconds=getattr(settings, 'OMR_TASK_TIMEOUT_SECONDS', 600),
                model_profile=getattr(settings, 'OMR_MODEL_PROFILE', 'default'),
            ),
        )
        generated_name = save_musicxml_to_partition(partition, result.output_path)

    return OmrPipelineResult(
        source_name=fingerprint.name,
        source_sha256=fingerprint.sha256,
        backend=result.backend,
        backend_version=result.backend_version,
        model_profile=result.model_profile,
        page_count=len(image_paths),
        processed_pages=result.processed_pages,
        generated_file_name=generated_name,
    )
