#!/usr/bin/env python
"""
Script standalone pour importer les psaumes et cantiques depuis un dossier contenant des PDFs et MP3s.

Usage:
    python import_scripts/import_psaumes.py --dossier "C:/path/to/chants_annee_A" --dry-run
    python import_scripts/import_psaumes.py --dossier "C:/path/to/chants_annee_A"

Le script détecte automatiquement si le PDF est un psaume (avec numéro) ou un cantique
(avec référence biblique comme "Is 12,1-6").

Les fichiers MP3 sont analysés en batch pour identifier les voix (S/A/T/B/I),
ce qui permet une meilleure détection contextuelle.

Dépendances nécessaires (installer avec pip):
    - google-generativeai
    - fitz
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import du module commun
from import_scripts.import_base import (
    setup_logging,
    get_latest_log_file,
    extract_failed_folders_from_log,
    GemmaClient,
    extract_text_from_pdf,
    analyze_pdf_with_gemma,
    create_or_get_compositeur,
    copy_file_to_media,
    create_moment_liturgique,
    get_psaume_label_safe,
    check_moments_existence,
    check_dependencies,
)

check_dependencies()

from psaumes.models import Psaume, Partition, MomentLiturgique
from django.db import transaction


from psaumes.models.partition import VOIX_LABELS, VOICE_FIELD_MAP


# Global instances
logger = None
gemma_client = None


# use shared helpers from import_base: check_moments_existence, link_orphan_moments_to_chant


def _identify_voix_from_filename_local(filename: str) -> Optional[str]:
    """Identifie le type de voix depuis le nom du fichier (mapping local, sans API)."""
    import unicodedata
    filename_lower = unicodedata.normalize('NFC', filename).lower()
    # Extract voice label from the last dash-separated component
    # This avoids false matches from folder name prefixes (e.g., "BAssomption" contains "bass")
    parts = filename_lower.rsplit('-', 1)
    voice_part = parts[-1] if len(parts) > 1 else filename_lower

    if 'soprane' in voice_part or 'soprano' in voice_part:
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
    # Fallback: check VOIX_LABELS (English labels) on full filename
    for code, label in VOIX_LABELS.items():
        if label.lower() in filename_lower:
            return code
    return None


def analyze_mp3_batch_with_gemma(filenames: List[str]) -> Dict[str, str]:
    """Analyse tous les noms de fichiers MP3 en une seule requête Gemma.

    Args:
        filenames: Liste des noms de fichiers MP3

    Returns:
        Dict mapping filename -> voice_code (S/A/T/B/I)
    """
    if not filenames:
        return {}

    # Construire la liste numérotée des fichiers
    files_list = "\n".join(f"{i+1}. {f}" for i, f in enumerate(filenames))

    prompt = f"""Analyse cette liste de noms de fichiers audio d'un même chant liturgique.
Chaque fichier correspond à une voix différente parmi : Soprano (S), Alto (A), Ténor (T), Basse (B), Instrumental (I), Mix (M).

Fichiers à analyser :
{files_list}

Important :
- Utilise le contexte : si tu identifies 3 voix clairement nommées (ex: alto, tenor, basse), la 4ème est probablement celle qui manque (soprano)
- "intru", "intro" ou un fichier sans indication vocale dans un groupe SATB est souvent Instrumental (I)
- Les fichiers sans nom de voix explicite mais dans un groupe où ATB sont identifiés sont souvent Soprano (S) ou Instrumental (I)
- Un fichier nommé "mix", "complet" ou "all" est probablement un Mix (M)

Réponds en JSON strict (pas de markdown, pas de code blocks) :
{{
  "nom_fichier1.mp3": "S",
  "nom_fichier2.mp3": "A"
}}"""

    response_text = gemma_client.call_gemma(prompt)

    if not response_text:
        # Fallback sur le mapping local pour chaque fichier
        print("     Echec de l'analyse batch, utilisation du fallback local")
        return {f: _identify_voix_from_filename_local(f) for f in filenames}

    try:
        # Nettoyer la réponse si elle contient des markdown code blocks
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        result = json.loads(response_text)

        # Valider et compléter avec le fallback local si nécessaire
        validated_result = {}
        for filename in filenames:
            voix_code = result.get(filename, '').upper()
            if voix_code in ['S', 'A', 'T', 'B', 'I', 'M']:
                validated_result[filename] = voix_code
            else:
                # Fallback local pour ce fichier
                local_code = _identify_voix_from_filename_local(filename)
                if local_code:
                    validated_result[filename] = local_code
                    print(f"     Fallback local utilise pour {filename}: {local_code}")

        return validated_result

    except json.JSONDecodeError as e:
        print(f"     Erreur de parsing JSON pour l'analyse batch: {e}")
        # Fallback sur le mapping local pour chaque fichier
        return {f: _identify_voix_from_filename_local(f) for f in filenames if _identify_voix_from_filename_local(f)}


def find_psalm_files(psalm_dir: Path) -> Tuple[Optional[Path], List[Path]]:
    """Trouve le PDF et les fichiers MP3 dans un dossier de psaume."""
    pdf_file = None
    mp3_files = []

    for file in psalm_dir.iterdir():
        if file.is_file():
            if file.suffix.lower() == '.pdf':
                pdf_file = file
            elif file.suffix.lower() == '.mp3':
                mp3_files.append(file)

    return pdf_file, mp3_files


def import_psalm_directory(psalm_dir: Path, dry_run: bool = False, force: bool = False):
    """Importe un psaume ou cantique depuis un dossier."""
    folder_name = psalm_dir.name
    logger.info(f"Processing folder: {folder_name}")
    print(f"\n Traitement du dossier: {folder_name}")

    # Trouver les fichiers
    pdf_file, mp3_files = find_psalm_files(psalm_dir)

    if not pdf_file:
        error_msg = f"No PDF found in folder '{folder_name}'"
        logger.warning(error_msg)
        print(f"    Aucun PDF trouve dans {psalm_dir}")
        return False

    print(f"    PDF trouve: {pdf_file.name}")
    if mp3_files:
        print(f"    {len(mp3_files)} fichier(s) MP3 trouve(s)")

    # Extraire le texte du PDF
    print(f"    Extraction du texte du PDF...")
    pdf_text = extract_text_from_pdf(pdf_file, folder_name, logger)
    # logger.debug(f"PDF text extracted: {pdf_text}")

    if not pdf_text.strip():
        error_msg = f"Failed to extract text from PDF in folder '{folder_name}'"
        logger.error(error_msg)
        print(f"    Impossible d'extraire le texte du PDF")
        return False

    # Analyser avec Gemma
    print(f"    Analyse avec Gemma...")
    analysis = analyze_pdf_with_gemma(gemma_client, pdf_text, folder_name, logger)

    if not analysis:
        error_msg = f"Gemma analysis failed for folder '{folder_name}'"
        logger.error(error_msg)
        print(f"    Echec de l'analyse Gemma")
        return False

    # Déterminer le type de chant (psaume ou cantique)
    chant_type = analysis.get('type', 'psaume').lower()

    if chant_type == 'cantique':
        ref_biblique = analysis.get('reference_biblique')
        if not ref_biblique:
            error_msg = f"No biblical reference found for canticle in folder '{folder_name}'"
            logger.error(error_msg)
            print(f"    Reference biblique non trouvee pour le cantique")
            return False
        logger.info(f"Canticle identified: {ref_biblique} in folder '{folder_name}'")
        print(f"    Cantique {ref_biblique} identifie")
    else:
        numero = analysis.get('numero')
        if not numero:
            error_msg = f"No psalm number found in analysis for folder '{folder_name}'"
            logger.error(error_msg)
            print(f"    Numero de psaume non trouve dans l'analyse")
            return False
        logger.info(f"Psalm identified: {numero} in folder '{folder_name}'")
        print(f"    Psaume {numero} identifie")

    if analysis.get('titre'):
        print(f"    Titre: {analysis.get('titre')}")

    if dry_run:
        print(f"    DRY RUN - Aucune modification ne sera effectuee")
        print(f"    Moments liturgiques trouves: {len(analysis.get('moments_liturgiques', []))}")
        # Analyse batch des MP3 en dry run pour information
        if mp3_files:
            filenames = [f.name for f in mp3_files]
            local_mapping = {f: _identify_voix_from_filename_local(f) for f in filenames}
            if all(local_mapping.values()):
                print(f"    Voix identifiees localement (pas d'appel API):")
                voix_mapping = local_mapping
            else:
                print(f"    Analyse groupee de {len(filenames)} fichiers MP3...")
                voix_mapping = analyze_mp3_batch_with_gemma(filenames)
            for filename, voix_code in voix_mapping.items():
                print(f"      - {filename} -> {voix_code} ({VOIX_LABELS.get(voix_code, 'Inconnu')})")
        return True

    # Récupérer les données analysées
    titre = analysis.get('titre') or ''
    refrain = analysis.get('refrain') or ''
    versets = analysis.get('versets') or ''
    moments_data = analysis.get('moments_liturgiques', [])

    # DECISION TREE based on moments (restore previous logic)
    existence_check = check_moments_existence(moments_data)
    existing = existence_check['existing']
    orphans = existence_check['orphans']
    not_existing = existence_check['not_existing']

    print(f"    Moments existants: {len(existing)}, orphelins: {len(orphans)}, non existants: {len(not_existing)}")

    # Case 1: ALL moments DON'T exist -> create new chant
    if len(existing) == 0 and len(orphans) == 0:
        compositeur = create_or_get_compositeur()
        copied_files = []
        try:
            with transaction.atomic():
                chant_label = f"Cantique {ref_biblique}" if chant_type == 'cantique' else f"Psaume {numero}"
                psaume = Psaume.objects.create(
                    psaume_or_cantique=chant_type,
                    nom_psaume=chant_label,
                    titre=titre,
                )

                print(f"    {chant_label} cree")
                
                # Créer la partition
                partition = Partition.objects.create(
                    psaume=psaume,
                    titre=titre or f"Arrangement {chant_label}",
                    compositeur=compositeur,
                    refrain=refrain,
                    versets=versets,
                )

                # Copier le PDF
                pdf_dest = f"partitions/pdf/{pdf_file.name}"
                pdf_path = copy_file_to_media(pdf_file, pdf_dest)
                copied_files.append(pdf_path)
                partition.partition_pdf = pdf_dest
                partition.save()
                print(f"    PDF copie vers media/{pdf_dest}")

                # Créer les moments liturgiques
                for moment_data in moments_data:
                    create_moment_liturgique(psaume, moment_data, dry_run=False, force=force)

                if moments_data:
                    print(f"    {len(moments_data)} moment(s) liturgique(s) cree(s)")

        except Exception as e:
            for p in copied_files:
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            logger.exception(f"Error creating chant for folder {folder_name}: {e}")
            print(f"    Erreur lors de la creation du chant: {e}")
            return False

    # Case 2: ALL moments exist (linked to chants)
    elif len(not_existing) == 0 and len(orphans) == 0:
        chant_ids = set(item[1] for item in existing)
        if len(chant_ids) == 1:
            psaume = existing[0][3]
            print(f"    Tous les moments lies au meme chant: {get_psaume_label_safe(psaume)} (id={psaume.pk})")
            # Update partition if needed
            partition = psaume.partitions.first()
            updated = False
            if partition:
                if force or not partition.refrain:
                    partition.refrain = refrain or partition.refrain
                    updated = True
                if force or not partition.versets:
                    partition.versets = versets or partition.versets
                if updated:
                    partition.save()
                    print(f"    Partition mise a jour pour {get_psaume_label_safe(psaume)}")
        else:
            print(f"    Erreur: Les moments liturgiques sont lies a des chants differents:")
            for moment_data, chant_id, moment_str, chant in existing:
                print(f"      - \"{moment_str}\" -> {get_psaume_label_safe(chant)} (id={chant_id})")
            return False

    # Case 3: SOME exist, SOME don't, or there are orphans -> ERROR
    else:
        error_msg = f"Inconsistent liturgical moments in folder '{folder_name}': some exist, some don't or orphans present"
        logger.error(error_msg)
        print(f"    Erreur: Certains moments liturgiques existent, d'autres non ou il y a des moments orphelins:")
        if existing:
            print(f"   Existants:")
            for moment_data, chant_id, moment_str, chant in existing:
                print(f"      - \"{moment_str}\" -> {get_psaume_label_safe(chant)} (id={chant_id})")
        if orphans:
            print(f"   Orphelins:")
            for moment_data, moment_str, moment in orphans:
                print(f"      - \"{moment_str}\"")
        if not_existing:
            print(f"   Non existants:")
            for moment_data in not_existing:
                print(f"      - \"{moment_data}\"")
        return False

    # Traiter les fichiers MP3 avec analyse groupée
    if mp3_files:
        filenames = [f.name for f in mp3_files]
        local_mapping = {f: _identify_voix_from_filename_local(f) for f in filenames}
        if all(local_mapping.values()):
            print(f"    Voix identifiees localement (pas d'appel API)")
            voix_mapping = local_mapping
        else:
            print(f"    Analyse groupee de {len(filenames)} fichiers MP3...")
            voix_mapping = analyze_mp3_batch_with_gemma(filenames)

        for mp3_file in mp3_files:
            voix_code = voix_mapping.get(mp3_file.name)

            if not voix_code:
                print(f"    Impossible d'identifier la voix pour {mp3_file.name}")
                continue

            print(f"    {mp3_file.name} -> {voix_code} ({VOIX_LABELS.get(voix_code, 'Inconnu')})")

            # Determine partition
            partition = None
            if hasattr(psaume, 'partitions'):
                partition = psaume.partitions.first()
            
            if not partition:
                compositeur = create_or_get_compositeur()
                partition = Partition.objects.create(
                    psaume=psaume,
                    titre=titre or f"Arrangement {psaume.nom_psaume}",
                    compositeur=compositeur,
                    refrain=refrain,
                    versets=versets,
                )
                print(f"    Partition creee pour {get_psaume_label_safe(psaume)}")

            was_synthetic = partition.mp3_synthetiques

            field_name = VOICE_FIELD_MAP.get(voix_code)
            if not field_name:
                continue

            # Check if audio exists
            field_val = getattr(partition, field_name) if partition else None
            audio_exists = bool(field_val)

            if audio_exists and not force:
                # Replace synthetic audio with real recordings
                if was_synthetic:
                    print(f"    Audio synthetique {voix_code} remplace par enregistrement reel")
                else:
                    print(f"    Fichier audio {voix_code} existe deja (utilisez --force pour remplacer)")
                    continue

            # Copier le fichier MP3 et mettre à jour la partition
            mp3_dest = f"audios/{mp3_file.name}"
            try:
                copied_mp3 = copy_file_to_media(mp3_file, mp3_dest)
                if partition:
                    setattr(partition, field_name, mp3_dest)
                    partition.mp3_synthetiques = False
                    partition.save()
                    print(f"    Fichier audio {voix_code} mis a jour/cree")
            except Exception as e:
                logger.error(f"Error copying MP3 {mp3_file.name}: {e}")
                # Nettoyer le mp3 copié en cas d'erreur
                try:
                    if copied_mp3 and copied_mp3.exists():
                        copied_mp3.unlink()
                except Exception:
                    pass
                logger.exception(f"Error processing mp3 {mp3_file.name} for {folder_name}: {e}")
                print(f"    Erreur lors du traitement du MP3 {mp3_file.name}: {e}")

    return True


def main():
    global logger, gemma_client

    parser = argparse.ArgumentParser(
        description='Importe les psaumes et cantiques depuis un dossier contenant des PDFs et MP3s'
    )
    parser.add_argument(
        '--dossier',
        type=str,
        required=True,
        help='Chemin vers le dossier racine contenant les psaumes/cantiques'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Affiche ce qui serait importe sans modifier la base de donnees'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Met a jour les psaumes existants'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        help='Cle API Gemini (ou utilise la variable d\'environnement GEMMA_API_KEY)'
    )
    parser.add_argument(
        '--log-dir',
        type=str,
        default='logs',
        help='Directory to store log files (default: logs/)'
    )
    parser.add_argument(
        '--retry-errors',
        nargs='?',
        const='latest',
        metavar='LOG_FILE',
        help='Relance uniquement les dossiers en erreur. Sans argument: utilise le dernier log. Avec argument: utilise le fichier log specifie.'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Limite le nombre de dossiers traites (0 = pas de limite)'
    )

    args = parser.parse_args()

    log_dir_path = Path(args.log_dir)

    # Gérer --retry-errors
    failed_folders_filter = None
    if args.retry_errors:
        if args.retry_errors == 'latest':
            log_file = get_latest_log_file(log_dir_path, "import_psaumes")
            if not log_file:
                print(f"Erreur: Aucun fichier log trouve dans {log_dir_path}")
                sys.exit(1)
            print(f"Utilisation du dernier log: {log_file.name}")
        else:
            log_file = Path(args.retry_errors)
            if not log_file.exists():
                # Essayer dans le répertoire des logs
                log_file = log_dir_path / args.retry_errors
            if not log_file.exists():
                print(f"Erreur: Le fichier log {args.retry_errors} n'existe pas")
                sys.exit(1)
            print(f"Utilisation du log: {log_file}")

        failed_folders_filter = extract_failed_folders_from_log(log_file)
        if not failed_folders_filter:
            print("Aucun dossier en erreur trouve dans le log. Rien a faire.")
            sys.exit(0)
        print(f"{len(failed_folders_filter)} dossier(s) en erreur a retraiter:")
        for folder in sorted(failed_folders_filter):
            print(f"  - {folder}")
        print()

    # Initialize logging
    logger = setup_logging(log_dir_path, "import_psaumes")
    logger.info(f"Import script started with arguments: dossier={args.dossier}, dry_run={args.dry_run}, force={args.force}, retry_errors={args.retry_errors}")

    # Récupérer la clé API et initialiser le client Gemma
    api_key = args.api_key or os.environ.get('GEMMA_API_KEY')
    if not api_key:
        logger.error("Gemma API key required but not provided")
        print("Erreur: Cle API Gemma requise")
        print("   Fournissez-la avec --api-key ou definissez GEMMA_API_KEY")
        sys.exit(1)

    gemma_client = GemmaClient(api_key)

    # Vérifier le dossier
    dossier_path = Path(args.dossier)
    if not dossier_path.exists():
        logger.error(f"Folder does not exist: {dossier_path}")
        print(f"Erreur: Le dossier {dossier_path} n'existe pas")
        sys.exit(1)

    if not dossier_path.is_dir():
        logger.error(f"Path is not a directory: {dossier_path}")
        print(f"Erreur: {dossier_path} n'est pas un dossier")
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN mode enabled - no modifications will be made")
        print("MODE DRY RUN - Aucune modification ne sera effectuee\n")

    # Parcourir les sous-dossiers
    psalm_dirs = [d for d in dossier_path.iterdir() if d.is_dir()]

    if args.limit and args.limit > 0:
        psalm_dirs = psalm_dirs[:args.limit]
        logger.info(f"Limited to {len(psalm_dirs)} folder(s) (--limit {args.limit})")
        print(f" Limite a {len(psalm_dirs)} dossier(s)\n")

    # Filtrer si --retry-errors est actif
    if failed_folders_filter:
        psalm_dirs = [d for d in psalm_dirs if d.name in failed_folders_filter]
        logger.info(f"Filtered to {len(psalm_dirs)} folder(s) from error list")

    if not psalm_dirs:
        logger.warning(f"No subdirectories found in {dossier_path}")
        print(f" Aucun sous-dossier trouve dans {dossier_path}")
        sys.exit(0)

    logger.info(f"Found {len(psalm_dirs)} psalm/canticle folder(s)")
    print(f" {len(psalm_dirs)} dossier(s) de chant(s) trouve(s)\n")

    success_count = 0
    error_count = 0
    failed_folders = []

    for psalm_dir in psalm_dirs:
        try:
            if import_psalm_directory(psalm_dir, args.dry_run, args.force):
                success_count += 1
            else:
                error_count += 1
                failed_folders.append(psalm_dir.name)
        except Exception as e:
            error_msg = f"Exception processing folder '{psalm_dir.name}': {str(e)}"
            logger.exception(error_msg)
            print(f"    Erreur lors du traitement de {psalm_dir.name}: {e}")
            error_count += 1
            failed_folders.append(psalm_dir.name)

    # Résumé
    print("\n" + "=" * 50)
    if args.dry_run:
        print("RESUME DRY RUN:")
    else:
        print("RESUME:")
    print(f"  Succes: {success_count}")
    print(f"  Erreurs: {error_count}")
    if failed_folders:
        print(f"\n  Dossiers en erreur:")
        for folder in failed_folders:
            print(f"    - {folder}")
    print("=" * 50)

    logger.info(f"Import completed: {success_count} successes, {error_count} errors")
    if failed_folders:
        logger.info(f"Failed folders: {', '.join(failed_folders)}")
    print(f"\n Log file: see logs/import_psaumes_*.log for details")


if __name__ == '__main__':
    main()
