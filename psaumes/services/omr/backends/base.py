from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class OmrBackendError(RuntimeError):
    """Raised when an OMR backend cannot produce MusicXML."""


@dataclass(frozen=True)
class OmrOptions:
    timeout_seconds: int
    model_profile: str


@dataclass(frozen=True)
class OmrResult:
    output_path: Path
    backend: str
    backend_version: str
    model_profile: str
    processed_pages: int


class OmrBackend(Protocol):
    name: str

    def recognize(
        self,
        input_image_paths: list[Path],
        output_dir: Path,
        options: OmrOptions,
    ) -> OmrResult:
        """Recognize music notation images and return a MusicXML file."""
