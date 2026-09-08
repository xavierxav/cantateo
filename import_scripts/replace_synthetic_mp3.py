#!/usr/bin/env python3
"""Remplace les MP3 synthétiques par les enregistrements réels des dossiers Année B et C."""

import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'psalm_project.settings')

from import_scripts.import_base import copy_file_to_media
from psaumes.models.psaume import Psaume
from psaumes.models.partition import Partition, VOICE_FIELD_MAP, VOIX_LABELS


def _identify_voix_from_filename_local(filename: str) -> Optional[str]:
    filename_lower = filename.lower()
    parts = filename_lower.rsplit('-', 1)
    voice_part = parts[-1] if len(parts) > 1 else filename_lower
    if 'soprane' in voice_part or 'soprano' in voice_part or 'soprand' in voice_part:
        return 'S'
    if 'alto' in voice_part or 'alti' in voice_part:
        return 'A'
    if 'tenor' in voice_part or 'ténor' in voice_part:
        return 'T'
    if 'basse' in voice_part or 'bass' in voice_part:
        return 'B'
    if 'inst' in voice_part or 'instrument' in voice_part or 'instru' in voice_part:
        return 'I'
    if 'complet' in voice_part or 'mix' in voice_part:
        return 'M'
    for code, label in VOIX_LABELS.items():
        if label.lower() in filename_lower:
            return code
    return None


def get_year_base(path_glob: str) -> Optional[Path]:
    """Use shell glob to handle WSL encoding issues with accented chars."""
    result = subprocess.run(
        f'ls -d {path_glob} 2>/dev/null | head -1',
        shell=True, capture_output=True, text=True
    )
    line = result.stdout.strip()
    return Path(line) if line else None


def parse_psalm_name_from_folder(folder_name: str) -> str:
    parts = folder_name.split('-', 1)
    if len(parts) > 1:
        return parts[1].strip()
    return folder_name


def find_psaumes_with_synthetic(psalm_name: str):
    psaumes = list(Psaume.objects.filter(nom_psaume__iexact=psalm_name))
    if not psaumes:
        for cand in ['Isaie', 'Isaïe']:
            if cand in psalm_name:
                psaumes = list(Psaume.objects.filter(nom_psaume='Cantique Is 12'))
                break
    if not psaumes and 'Luc' in psalm_name:
        psaumes = list(Psaume.objects.filter(nom_psaume='Cantique Lc1'))
    if not psaumes and 'Exode' in psalm_name:
        psaumes = list(Psaume.objects.filter(nom_psaume='Cantique Exode 15'))
    if not psaumes:
        nums = re.findall(r'\d+', psalm_name)
        for num in nums:
            chk = Psaume.objects.filter(nom_psaume__endswith=f' {num}')
            if chk.exists():
                psaumes = list(chk)
                break
    result = []
    for p in psaumes:
        synth_parts = list(p.partitions.filter(mp3_synthetiques=True))
        if synth_parts:
            result.append((p, synth_parts))
    return result


def replace_synthetic_audio(folder_path: Path, partitions) -> int:
    mp3_files = list(folder_path.glob('*.mp3'))
    if not mp3_files:
        return 0
    voice_mapping = {f: _identify_voix_from_filename_local(f.name) for f in mp3_files}
    replaced = 0
    any_ok = False
    for partition in partitions:
        print(f"      Partition {partition.pk} ({partition.titre})")
        for mp3_file in mp3_files:
            voice_code = voice_mapping.get(mp3_file)
            if not voice_code:
                continue
            field_name = VOICE_FIELD_MAP.get(voice_code)
            if not field_name:
                continue
            mp3_dest = f"audios/{mp3_file.name}"
            try:
                copy_file_to_media(mp3_file, mp3_dest)
                setattr(partition, field_name, mp3_dest)
                partition.mp3_synthetiques = False
                partition.save()
                print(f"        {mp3_file.name} -> {voice_code} ({VOIX_LABELS[voice_code]}) OK")
                replaced += 1
                any_ok = True
            except Exception as e:
                print(f"        ERROR {mp3_file.name}: {e}")
    return replaced


def main():
    b_base = get_year_base('/mnt/c/Users/xavde/Downloads/wetransfer_annee-b-xavier_2026-05-26_0822/*/')
    c_base = get_year_base('/mnt/c/Users/xavde/Downloads/wetransfer_annee-c_2026-05-26_0831/*/')
    if not b_base:
        print("ERROR: Année B folder not found"); sys.exit(1)
    if not c_base:
        print("ERROR: Année C folder not found"); sys.exit(1)
    print(f"Année B: {b_base}")
    print(f"Année C: {c_base}")

    synth_before = Partition.objects.filter(mp3_synthetiques=True).count()
    print(f"\nSynthetic partitions before: {synth_before}")

    total_replaced = 0
    matched_folders = 0

    for base in [b_base, c_base]:
        year = 'B' if 'annee-b' in str(base).lower() else 'C'
        print(f"\n=== Année {year} ===")
        for folder in sorted(base.iterdir()):
            if not folder.is_dir():
                continue
            folder_name = folder.name
            psalm_name = parse_psalm_name_from_folder(folder_name)
            matches = find_psaumes_with_synthetic(psalm_name)
            if not matches:
                continue
            print(f"\n  [{year}] {folder_name} -> {psalm_name}")
            for psaume, synth_parts in matches:
                print(f"    Psaume: {psaume.nom_psaume} (id={psaume.pk}) - {len(synth_parts)} synth part(s)")
                count = replace_synthetic_audio(folder, synth_parts)
                total_replaced += count
            if any(list(folder.glob('*.mp3'))):
                matched_folders += 1

    synth_after = Partition.objects.filter(mp3_synthetiques=True).count()
    print(f"\n{'='*50}")
    print(f"  Synthetic before: {synth_before}")
    print(f"  Synthetic after:  {synth_after}")
    print(f"  Replaced:         {synth_before - synth_after}")
    print(f"  Files copied:     {total_replaced}")
    print(f"  Folders matched:  {matched_folders}")
    print(f"{'='*50}")

    if synth_after > 0:
        print(f"\nRemaining synthetic partitions ({synth_after}):")
        for p in Partition.objects.filter(mp3_synthetiques=True).select_related('psaume'):
            ps = p.psaume
            print(f"  id={p.pk:>3} | {(ps.nom_psaume if ps else 'NONE'):<20} | {p.titre}")


if __name__ == '__main__':
    main()
