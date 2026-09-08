#!/usr/bin/env python3
"""Repare les partitions mixtes (voix synthetiques + voix reelles).

Scanne les dossiers Annee A, B, C pour trouver les MP3 reels
et remplace toutes les voix synthetiques restantes.
"""

import glob
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'psalm_project.settings')
django.setup()

from psaumes.models.partition import Partition, VOICE_FIELD_MAP, VOIX_LABELS
from import_scripts.import_base import copy_file_to_media
from import_scripts.import_psaumes import _identify_voix_from_filename_local


def get_year_base(pattern: str) -> Optional[Path]:
    dirs = glob.glob(pattern)
    return Path(dirs[0]) if dirs else None


def parse_psalm_name_from_folder(folder_name: str) -> str:
    parts = folder_name.split('-', 1)
    return parts[1].strip() if len(parts) > 1 else folder_name


def find_mp3s_for_psalm(psalm_name: str, all_folders: List[Tuple[str, Path]]) -> Dict[str, Path]:
    """Find all MP3 files matching a psalm name across all year folders.

    Returns dict of {voice_code: mp3_path}.
    """
    # Normalize psalm name for comparison
    target = psalm_name.lower().replace(' ', '').replace('psaume', '').replace('cantique', '')

    # Build alternative targets for cantiques
    alt_targets = []
    if 'is12' in target or 'isaie12' in target:
        alt_targets.extend(['isaie12', 'is12'])
    if 'lc1' in target or 'luc1' in target:
        alt_targets.extend(['luc1', 'lc1'])
    if 'daniel' in target or 'dn3' in target:
        alt_targets.extend(['daniel3', 'dn3'])
    if 'exode' in target:
        alt_targets.extend(['exode15', 'ex15'])

    candidates: List[Path] = []

    for folder_name, folder_path in all_folders:
        parsed = parse_psalm_name_from_folder(folder_name)
        parsed_norm = parsed.lower().replace(' ', '').replace('psaume', '').replace('cantique', '')

        if parsed_norm == target or parsed_norm in alt_targets:
            candidates.extend(folder_path.glob('*.mp3'))

    result = {}
    for mp3 in candidates:
        voice = _identify_voix_from_filename_local(mp3.name)
        if voice and voice not in result:
            result[voice] = mp3

    return result


def is_synthetic_path(name: str) -> bool:
    """Check if an audio file path is synthetic (in a subdirectory)."""
    return '/' in name.replace('audios/', '', 1)


def main():
    # Find all year folders
    a_base = Path('/mnt/c/Users/xavde/Data Xavier perso/Année A')
    b_base = get_year_base('/mnt/c/Users/xavde/Downloads/wetransfer_annee-b-xavier_2026-05-26_0822/*/')
    c_base = get_year_base('/mnt/c/Users/xavde/Downloads/wetransfer_annee-c_2026-05-26_0831/*/')

    if not a_base.exists():
        print(f"ERROR: Année A not found: {a_base}")
        sys.exit(1)
    if not b_base:
        print("ERROR: Année B not found")
        sys.exit(1)
    if not c_base:
        print("ERROR: Année C not found")
        sys.exit(1)

    print(f"Année A: {a_base}")
    print(f"Année B: {b_base}")
    print(f"Année C: {c_base}")

    # Build index of all folders across all years
    all_folders: List[Tuple[str, Path]] = []
    for base in [a_base, b_base, c_base]:
        for folder in sorted(base.iterdir()):
            if folder.is_dir():
                all_folders.append((folder.name, folder))

    print(f"Total folders indexed: {len(all_folders)}")

    # Find all mixed partitions
    partitions = Partition.objects.all().prefetch_related('psaume')
    mixed = []
    for p in partitions:
        synth_voices = []
        for v, f in VOICE_FIELD_MAP.items():
            val = getattr(p, f)
            if val and is_synthetic_path(val.name):
                synth_voices.append((v, f))
        if synth_voices:
            mixed.append((p, synth_voices))

    print(f"\nMixed partitions to repair: {len(mixed)}")

    repaired = 0
    skipped = 0
    not_found = 0

    for partition, synth_voices in mixed:
        psaume = partition.psaume
        if not psaume:
            print(f"  SKIP partition {partition.pk}: no psaume")
            skipped += 1
            continue

        psalm_name = psaume.nom_psaume
        print(f"\n  Partition {partition.pk} | {psalm_name} | {partition.titre}")
        print(f"    Synthetic voices: {[v for v, _ in synth_voices]}")

        # Find real MP3s for this psalm
        real_mp3s = find_mp3s_for_psalm(psalm_name, all_folders)
        if not real_mp3s:
            print(f"    No real MP3s found in any year folder")
            not_found += 1
            continue

        print(f"    Found real MP3s: {list(real_mp3s.keys())}")

        # Replace each synthetic voice
        updated_fields = []
        for voice_code, field_name in synth_voices:
            mp3_path = real_mp3s.get(voice_code)
            if not mp3_path:
                print(f"    {voice_code}: no real file found")
                continue

            mp3_dest = f"audios/{mp3_path.name}"
            try:
                copy_file_to_media(mp3_path, mp3_dest)
                setattr(partition, field_name, mp3_dest)
                updated_fields.append(field_name)
                print(f"    {voice_code}: {mp3_path.name} -> {mp3_dest}")
            except Exception as e:
                print(f"    {voice_code}: ERROR {e}")

        if updated_fields:
            partition.mp3_synthetiques = False
            updated_fields.append('mp3_synthetiques')
            partition.save(update_fields=updated_fields)
            repaired += 1
            print(f"    Saved {len(updated_fields) - 1} voices")

    # Summary
    print(f"\n{'='*50}")
    print(f"  Mixed partitions: {len(mixed)}")
    print(f"  Repaired:         {repaired}")
    print(f"  No MP3s found:    {not_found}")
    print(f"  Skipped:          {skipped}")

    # Count remaining synthetic-voiced partitions
    remaining = 0
    for p in Partition.objects.all():
        for v, f in VOICE_FIELD_MAP.items():
            val = getattr(p, f)
            if val and is_synthetic_path(val.name):
                remaining += 1
                break
    print(f"  Remaining mixed:  {remaining}")


if __name__ == '__main__':
    main()
