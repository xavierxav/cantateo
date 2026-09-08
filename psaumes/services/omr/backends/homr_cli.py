import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

from .base import OmrBackendError, OmrOptions, OmrResult
from ..validation import validate_musicxml_file


class HomrCliBackend:
    name = 'homr_cli'

    def recognize(
        self,
        input_image_paths: list[Path],
        output_dir: Path,
        options: OmrOptions,
    ) -> OmrResult:
        if len(input_image_paths) != 1:
            raise OmrBackendError('homr_cli supports exactly one page in this integration.')

        command = getattr(settings, 'HOMR_COMMAND', 'homr')
        output_dir.mkdir(parents=True, exist_ok=True)
        source_image = input_image_paths[0]
        working_image = output_dir / source_image.name
        if source_image != working_image:
            shutil.copy2(source_image, working_image)

        try:
            completed = subprocess.run(
                [command, str(working_image)],
                capture_output=True,
                text=True,
                timeout=options.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OmrBackendError(f'OMR command not found: {command}') from exc
        except subprocess.TimeoutExpired as exc:
            raise OmrBackendError(
                f'OMR backend timed out after {options.timeout_seconds}s'
            ) from exc

        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or '').strip()
            raise OmrBackendError(error or f'OMR backend exited with {completed.returncode}')

        output_path = working_image.with_suffix('.musicxml')
        if not output_path.exists():
            raise OmrBackendError('OMR backend did not create a MusicXML file.')

        validate_musicxml_file(output_path)
        return OmrResult(
            output_path=output_path,
            backend=self.name,
            backend_version=_backend_version(command),
            model_profile=options.model_profile,
            processed_pages=1,
        )


def _backend_version(command):
    try:
        completed = subprocess.run(
            [command, '--version'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return os.path.basename(command)

    version = (completed.stdout or completed.stderr or '').strip().splitlines()
    return version[0][:120] if version else os.path.basename(command)
