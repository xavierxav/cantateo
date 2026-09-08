import os
import subprocess

import pytest

from psaumes.services.omr.backends.base import OmrBackendError, OmrOptions
from psaumes.services.omr.backends.homr_cli import HomrCliBackend
from psaumes.services.omr.pdf import PdfConversionError, convert_pdf_to_images


def _write_homr_script(path, body):
    path.write_text(body, encoding='utf-8')
    path.chmod(path.stat().st_mode | os.stat(path).st_mode | 0o111)
    return str(path)


def test_homr_cli_backend_creates_musicxml(tmp_path, settings):
    command = _write_homr_script(
        tmp_path / 'homr',
        """#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "homr test"
  exit 0
fi
base="${1%.*}"
printf '<score-partwise version="4.0"></score-partwise>' > "$base.musicxml"
""",
    )
    settings.HOMR_COMMAND = command
    image = tmp_path / 'page.png'
    image.write_bytes(b'png')

    result = HomrCliBackend().recognize(
        [image],
        tmp_path / 'out',
        OmrOptions(timeout_seconds=5, model_profile='test-profile'),
    )

    assert result.backend == 'homr_cli'
    assert result.backend_version == 'homr test'
    assert result.model_profile == 'test-profile'
    assert result.output_path.exists()


def test_homr_cli_backend_reports_missing_output(tmp_path, settings):
    command = _write_homr_script(tmp_path / 'homr', '#!/bin/sh\nexit 0\n')
    settings.HOMR_COMMAND = command
    image = tmp_path / 'page.png'
    image.write_bytes(b'png')

    with pytest.raises(OmrBackendError, match='did not create'):
        HomrCliBackend().recognize(
            [image],
            tmp_path / 'out',
            OmrOptions(timeout_seconds=5, model_profile='default'),
        )


def test_convert_pdf_to_images_rejects_too_many_pages(tmp_path, monkeypatch):
    pdf = tmp_path / 'score.pdf'
    pdf.write_bytes(b'%PDF-test')

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout='Pages: 2\n', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)

    with pytest.raises(PdfConversionError, match='maximum allowed is 1'):
        convert_pdf_to_images(pdf, tmp_path, max_pages=1)


def test_convert_pdf_to_images_cleansly_returns_pages(tmp_path, monkeypatch):
    pdf = tmp_path / 'score.pdf'
    pdf.write_bytes(b'%PDF-test')

    def fake_run(cmd, **kwargs):
        if cmd[0] == 'pdfinfo':
            return subprocess.CompletedProcess(cmd, 0, stdout='Pages: 1\n', stderr='')
        (tmp_path / 'page-1.png').write_bytes(b'png')
        return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)

    assert convert_pdf_to_images(pdf, tmp_path, max_pages=1) == [tmp_path / 'page-1.png']
