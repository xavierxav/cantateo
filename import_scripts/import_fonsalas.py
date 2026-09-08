#!/usr/bin/env python
"""
Script standalone pour importer les psaumes et cantiques Fonsalas depuis un dossier contenant des PDFs et MXLs.

Usage:
    python import_scripts/import_fonsalas.py --dossier "C:/path/to/fonsalas" --dry-run
    python import_scripts/import_fonsalas.py --dossier "C:/path/to/fonsalas"

Le script:
1. Parcourt les sous-dossiers contenant "fonsalas" et "aelf" dans leur nom
2. Extrait le texte du PDF et utilise Gemma pour identifier les moments liturgiques
3. Vérifie si les moments liturgiques existent déjà dans la base de données
4. Crée ou met à jour le psaume/cantique selon la logique définie

Dépendances nécessaires (installer avec pip):
    - google-generativeai
    - pymupdf
"""

import os
import sys
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
    build_moment_query,
    find_existing_chant_with_common_moments,
    create_moment_liturgique,
    check_moments_existence,
    link_orphan_moments_to_chant,
)

from psaumes.models import Psaume, Partition, MomentLiturgique
from django.db import transaction


# Global instances
logger = None
gemma_client = None


def matches_fonsalas_and_aelf(folder_name: str) -> bool:
    """Vérifie si le nom du dossier contient 'fonsalas' et 'aelf' (insensible à la casse, ignore les espaces)."""
    normalized = folder_name.lower().replace(" ", "")
    return ("fonsalas" in normalized) and ("aelf" in normalized)


def find_fonsalas_files(folder: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Trouve le PDF et le fichier MXL dans un dossier Fonsalas."""
    pdf_file = None
    mxl_file = None

    for file in folder.iterdir():
        if file.is_file():
            suffix_lower = file.suffix.lower()
            if suffix_lower == '.pdf':
                pdf_file = file
            elif suffix_lower == '.mxl':
                mxl_file = file

    return pdf_file, mxl_file


def format_moment_description(moment_data: Dict) -> str:
    """Formate un moment liturgique pour l'affichage."""
    moment_type = moment_data.get('type', '').upper()

    if moment_type == 'DIMANCHE':
        temps = moment_data.get('temps', '')
        semaine = moment_data.get('semaine', '')
        annee = moment_data.get('annee', '')
        return f"{semaine}eme Dimanche - {temps} (Annee {annee})"

    elif moment_type == 'SEMAINE':
        temps = moment_data.get('temps', '')
        semaine = moment_data.get('semaine', '')
        jour = moment_data.get('jour', '')
        parite = moment_data.get('parite', '')
        jour_names = ['', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi']
        jour_str = jour_names[jour] if isinstance(jour, int) and 1 <= jour <= 6 else str(jour)
        parite_str = "paire" if parite == 'P' else "impaire"
        return f"{jour_str} - {semaine}eme sem. - {temps} (annee {parite_str})"

    elif moment_type in ('FÊTE', 'FETE'):
        nom_fete = moment_data.get('nom_fete', 'Fete inconnue')
        annee = moment_data.get('annee', '')
        if annee:
            return f"{nom_fete} (Annee {annee})"
        return nom_fete

    return str(moment_data)


# use shared helpers `check_moments_existence` from `scripts.import_base`


# use shared helper `link_orphan_moments_to_chant` from `scripts.import_base`


def get_chant_label(psaume: Psaume) -> str:
    """Retourne un label descriptif pour un chant."""
    return psaume.nom_psaume


def create_new_chant(
    chant_type: str,
    chant_identifier,
    analysis: Dict,
    moments_data: List[Dict],
    pdf_file: Path,
    mxl_file: Path,
    dry_run: bool,
    force: bool
) -> bool:
    """Crée un nouveau psaume ou cantique avec ses moments liturgiques."""
    titre = analysis.get('titre') or ''
    refrain = analysis.get('refrain') or ''
    versets = analysis.get('versets') or ''

    if dry_run:
        print(f"    DRY RUN - Creerait:")
        if chant_type == 'cantique':
            print(f"      - Cantique {chant_identifier}")
        else:
            print(f"      - Psaume {chant_identifier}")
        print(f"      - Titre: {titre}")
        if refrain:
            print(f"      - Refrain: {refrain[:60]}...")
        if pdf_file:
            print(f"      - PDF: {pdf_file.name}")
        if mxl_file:
            print(f"      - MXL: {mxl_file.name}")
        return True

    try:
        with transaction.atomic():
            # Créer ou récupérer le compositeur
            compositeur = create_or_get_compositeur()

            # Créer le chant (avec vérification des moments communs)
            chant_label = f"Cantique {chant_identifier}" if chant_type == 'cantique' else f"Psaume {chant_identifier}"
            
            # Chercher un psaume existant
            psaume, created_psaume = Psaume.objects.get_or_create(
                nom_psaume=chant_label,
                defaults={
                    'psaume_or_cantique': chant_type,
                    'titre': titre,
                }
            )
            
            if created_psaume:
                print(f"    {chant_label} cree")
            else:
                print(f"    {chant_label} existant trouve")

            # Toujours créer une nouvelle partition pour cet arrangement
            partition = Partition.objects.create(
                psaume=psaume,
                titre=titre or f"Arrangement {chant_label}",
                compositeur=compositeur,
                refrain=refrain,
                versets=versets,
            )
            print(f"    Partition creee pour {chant_label}")

            # Copier le PDF
            if pdf_file:
                pdf_dest = f"partitions/pdf/{pdf_file.name}"
                copy_file_to_media(pdf_file, pdf_dest)
                partition.partition_pdf = pdf_dest
            
            # Copier le MXL
            if mxl_file:
                mxl_dest = f"partitions/mxl/{mxl_file.name}"
                copy_file_to_media(mxl_file, mxl_dest)
                partition.partition_mxl = mxl_dest
            
            partition.save()

            # Lier les moments orphelins et créer les nouveaux
            link_orphan_moments_to_chant(psaume, moments_data)

            # Créer les moments qui n'existent pas
            for moment_data in moments_data:
                query_params = build_moment_query(moment_data)
                if query_params and not MomentLiturgique.objects.filter(**query_params).exists():
                    create_moment_liturgique(psaume, moment_data, dry_run=False, force=force)
            
            return True
    except Exception as e:
        logger.exception(f"Error creating/updating chant {chant_identifier}: {e}")
        print(f"    Erreur lors de la creation/mise a jour du chant: {e}")
        return False


def process_fonsalas_folder(folder: Path, dry_run: bool = False, force: bool = False) -> bool:
    """Traite un dossier Fonsalas contenant PDF et MXL."""
    folder_name = folder.name
    logger.info(f"Processing folder: {folder_name}")
    print(f"\n Traitement du dossier: {folder_name}")

    # Trouver les fichiers
    pdf_file, mxl_file = find_fonsalas_files(folder)

    if not pdf_file:
        error_msg = f"No PDF found in folder '{folder_name}'"
        logger.warning(error_msg)
        print(f"    Aucun PDF trouve dans {folder}")
        return False

    if not mxl_file:
        error_msg = f"No MXL found in folder '{folder_name}'"
        logger.warning(error_msg)
        print(f"    Aucun MXL trouve dans {folder}")
        return False

    print(f"    PDF trouve: {pdf_file.name}")
    print(f"    MXL trouve: {mxl_file.name}")

    # Extraire le texte du PDF
    print(f"    Extraction du texte du PDF...")
    pdf_text = extract_text_from_pdf(pdf_file, folder_name, logger)

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
    chant_type = (analysis.get('type') or 'psaume').lower()

    if chant_type == 'cantique':
        ref_biblique = analysis.get('reference_biblique')
        if not ref_biblique:
            error_msg = f"No biblical reference found for canticle in folder '{folder_name}'"
            logger.error(error_msg)
            print(f"    Reference biblique non trouvee pour le cantique")
            return False
        logger.info(f"Canticle identified: {ref_biblique} in folder '{folder_name}'")
        print(f"    Cantique {ref_biblique} identifie")
        chant_identifier = ref_biblique
    else:
        numero = analysis.get('numero')
        if not numero:
            error_msg = f"No psalm number found in analysis for folder '{folder_name}'"
            logger.error(error_msg)
            print(f"    Numero de psaume non trouve dans l'analyse")
            return False
        logger.info(f"Psalm identified: {numero} in folder '{folder_name}'")
        print(f"    Psaume {numero} identifie")
        chant_identifier = numero

    if analysis.get('titre'):
        print(f"    Titre: {analysis.get('titre')}")

    moments_data = analysis.get('moments_liturgiques', [])
    print(f"    {len(moments_data)} moment(s) liturgique(s) trouve(s)")

    if not moments_data:
        error_msg = f"No liturgical moments found for folder '{folder_name}'"
        logger.warning(error_msg)
        print(f"    Aucun moment liturgique trouve, impossible de continuer")
        return False

    # Récupérer les données analysées
    titre = analysis.get('titre') or ''
    refrain = analysis.get('refrain') or ''
    versets = analysis.get('versets') or ''

    # DECISION TREE based on moments (restore previous logic)
    existence_check = check_moments_existence(moments_data)
    existing = existence_check['existing']
    orphans = existence_check['orphans']
    not_existing = existence_check['not_existing']

    print(f"    Moments existants: {len(existing)}, orphelins: {len(orphans)}, non existants: {len(not_existing)}")

    # Case 1: ALL moments DON'T exist -> create new chant
    if len(existing) == 0 and len(orphans) == 0:
        return create_new_chant(chant_type, chant_identifier, analysis, moments_data, pdf_file, mxl_file, dry_run, force)

    # Case 2: ALL moments exist (linked to chants)
    elif len(not_existing) == 0 and len(orphans) == 0:
        chant_ids = set(item[1] for item in existing)
        if len(chant_ids) == 1:
            chant = existing[0][3]
            print(f"    Tous les moments lies au meme chant: {get_chant_label(chant)} (id={chant.pk})")
            # Copier le MXL si manquant ou force
            if not chant.partition_mxl or force:
                if dry_run:
                    print(f"    DRY RUN - Ajouterait MXL: {mxl_file.name}")
                else:
                    mxl_dest = f"partitions/mxl/{mxl_file.name}"
                    copy_file_to_media(mxl_file, mxl_dest)
                    chant.partition_mxl = mxl_dest
                    chant.save()
                    print(f"    MXL copie vers media/{mxl_dest}")
            else:
                print(f"    MXL existe deja (utilisez --force pour remplacer)")
        else:
            print(f"    Erreur: Les moments liturgiques sont lies a des chants differents:")
            for moment_data, chant_id, moment_str, chant in existing:
                print(f"      - \"{moment_str}\" -> {get_chant_label(chant)} (id={chant_id})")
            return False

    # Case 3: SOME exist, SOME don't, or there are orphans -> ERROR
    else:
        error_msg = f"Inconsistent liturgical moments in folder '{folder_name}': some exist, some don't or orphans present"
        logger.error(error_msg)
        print(f"    Erreur: Certains moments liturgiques existent, d'autres non ou il y a des moments orphelins:")
        if existing:
            print(f"   Existants:")
            for moment_data, chant_id, moment_str, chant in existing:
                print(f"      - \"{moment_str}\" -> {get_chant_label(chant)} (id={chant_id})")
        if orphans:
            print(f"   Orphelins:")
            for moment_data, moment_str, moment in orphans:
                print(f"      - \"{moment_str}\"")
        if not_existing:
            print(f"   Non existants:")
            for moment_data in not_existing:
                print(f"      - \"{format_moment_description(moment_data)}\"")
        return False
    
    return True


def main():
    global logger, gemma_client

    parser = argparse.ArgumentParser(
        description='Importe les psaumes et cantiques Fonsalas depuis un dossier contenant des PDFs et MXLs'
    )
    parser.add_argument(
        '--dossier',
        type=str,
        required=True,
        help='Chemin vers le dossier racine contenant les sous-dossiers Fonsalas'
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
        help='Cle API Gemma (ou utilise la variable d\'environnement GEMMA_API_KEY)'
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

    args = parser.parse_args()

    log_dir_path = Path(args.log_dir)

    # Gérer --retry-errors
    failed_folders_filter = None
    if args.retry_errors:
        if args.retry_errors == 'latest':
            log_file = get_latest_log_file(log_dir_path, "import_fonsalas")
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
    logger = setup_logging(log_dir_path, "import_fonsalas")
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

    # Parcourir les sous-dossiers contenant "fonsalas" et "aelf"
    fonsalas_dirs = [d for d in dossier_path.iterdir() if d.is_dir() and matches_fonsalas_and_aelf(d.name)]

    # Filtrer si --retry-errors est actif
    if failed_folders_filter:
        fonsalas_dirs = [d for d in fonsalas_dirs if d.name in failed_folders_filter]
        logger.info(f"Filtered to {len(fonsalas_dirs)} folder(s) from error list")

    if not fonsalas_dirs:
        logger.warning(f"No Fonsalas folders found in {dossier_path}")
        print(f" Aucun sous-dossier Fonsalas trouve dans {dossier_path}")
        sys.exit(0)

    logger.info(f"Found {len(fonsalas_dirs)} Fonsalas folder(s)")
    print(f" {len(fonsalas_dirs)} dossier(s) Fonsalas trouve(s)\n")

    success_count = 0
    error_count = 0
    failed_folders = []

    for fonsalas_dir in fonsalas_dirs:
        try:
            if process_fonsalas_folder(fonsalas_dir, args.dry_run, args.force):
                success_count += 1
            else:
                error_count += 1
                failed_folders.append(fonsalas_dir.name)
        except Exception as e:
            error_msg = f"Exception processing folder '{fonsalas_dir.name}': {str(e)}"
            logger.exception(error_msg)
            print(f"    Erreur lors du traitement de {fonsalas_dir.name}: {e}")
            error_count += 1
            failed_folders.append(fonsalas_dir.name)

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
    print(f"\n Log file: see logs/import_fonsalas_*.log for details")


if __name__ == '__main__':
    main()
