from pathlib import Path

import pytest


STALE_REFERENCE_FILES = [
    Path('docs/README.md'),
    Path('docs/STATIC.md'),
    Path('docs/HETZNER.md'),
    Path('deploy/nginx.conf'),
]


@pytest.mark.parametrize('path', STALE_REFERENCE_FILES)
def test_no_stale_pwa_or_offline_references(path):
    text = path.read_text(encoding='utf-8').lower()

    assert 'pwa' not in text
    assert 'offline' not in text
    assert 'sw.js' not in text
    assert 'manifest.json' not in text
