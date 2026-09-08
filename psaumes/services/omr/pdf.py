import subprocess
from pathlib import Path

from django.conf import settings


class PdfConversionError(RuntimeError):
    """Raised when a PDF cannot be converted to page images."""


def pdf_page_count(pdf_path: Path) -> int:
    try:
        completed = subprocess.run(
            ['pdfinfo', str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PdfConversionError('pdfinfo not found. Install poppler-utils.') from exc
    except subprocess.TimeoutExpired as exc:
        raise PdfConversionError('pdfinfo timed out.') from exc

    if completed.returncode != 0:
        raise PdfConversionError((completed.stderr or 'Unable to inspect PDF.').strip())

    for line in completed.stdout.splitlines():
        if line.startswith('Pages:'):
            try:
                return int(line.split(':', 1)[1].strip())
            except ValueError as exc:
                raise PdfConversionError('Unable to parse PDF page count.') from exc
    raise PdfConversionError('Unable to find PDF page count.')


def convert_pdf_to_images(pdf_path: Path, output_dir: Path, max_pages=None, dpi=None) -> list[Path]:
    max_pages = max_pages or getattr(settings, 'OMR_MAX_PAGES', 1)
    dpi = dpi or getattr(settings, 'OMR_PDF_DPI', 250)
    page_count = pdf_page_count(pdf_path)
    if page_count > max_pages:
        raise PdfConversionError(
            f'PDF has {page_count} pages, maximum allowed is {max_pages}.'
        )

    output_prefix = output_dir / 'page'
    try:
        completed = subprocess.run(
            [
                'pdftoppm',
                '-png',
                '-gray',
                '-r',
                str(dpi),
                str(pdf_path),
                str(output_prefix),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PdfConversionError('pdftoppm not found. Install poppler-utils.') from exc
    except subprocess.TimeoutExpired as exc:
        raise PdfConversionError('PDF conversion timed out.') from exc

    if completed.returncode != 0:
        raise PdfConversionError((completed.stderr or 'Unable to convert PDF.').strip())

    images = sorted(output_dir.glob('page-*.png'))
    if not images:
        raise PdfConversionError('PDF conversion did not produce any images.')
    return images
