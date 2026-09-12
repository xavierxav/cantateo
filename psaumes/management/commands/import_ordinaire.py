"""Importe un ordinaire de messe depuis un dossier de fichiers MP3 (et PDF/MXL).

Le parcours du dossier détecte la partie de messe et la voix d'après le nom
de chaque fichier, puis crée un ``Ordinaire`` et ses ``Partition`` associées
avec les pistes audio attachées.
"""

import logging
import os
import re
import unicodedata
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from psaumes.models import Compositeur, Ordinaire, Partition, PartieMesse
from psaumes.models.partition import VOICE_FIELD_MAP

AUDIO_EXT = {'.mp3'}
PDF_EXT = {'.pdf'}
MXL_EXT = {'.mxl', '.musicxml', '.xml'}

# Mot-clé (normalisé, sans accent, minuscule) -> code de PartieMesse.
# Aucune collision entre ces jetons : l'ordre est ici purement lisibilité.
_PARTIE_RULES = [
    ('kyrie', PartieMesse.KYRIE.value),
    ('gloria', PartieMesse.GLORIA.value),
    ('sanctus', PartieMesse.SANCTUS.value),
    ('agnus', PartieMesse.AGNUS_DEI.value),
    ('alleluia', PartieMesse.ALLELUIA.value),
    ('anamnese', PartieMesse.ANAMNESE.value),
    ('memorial', PartieMesse.ANAMNESE.value),
    ('mystere', PartieMesse.ANAMNESE.value),
    ('priere universelle', PartieMesse.PRIERE_UNIVERSELLE.value),
    ('universelle', PartieMesse.PRIERE_UNIVERSELLE.value),
]

# Mot-clé -> code voix. On liste les jetons longs/spécifiques avant les
# raccourcis ambigus ('soprano' et 'soprane' avant 'sop', 'basse' avant 'bas',
# 'instrumental' puis 'instru' puis 'inst') afin que la première
# correspondance soit la bonne. 'musique' et 'inst' couvrent les conventions
# de nommage réelles des dossiers de l'utilisateur.
_VOICE_RULES = [
    ('soprano', 'S'),
    ('soprane', 'S'),
    ('sop', 'S'),
    ('s.', 'S'),
    ('-s', 'S'),
    ('_s', 'S'),
    ('alto', 'A'),
    ('tenor', 'T'),
    ('ten', 'T'),
    ('basse', 'B'),
    ('bas', 'B'),
    ('instrumental', 'I'),
    ('instru', 'I'),
    ('inst', 'I'),
    ('musique', 'I'),
    ('mix', 'M'),
]


def _normalize(text):
    """Minuscule + suppression des accents pour une comparaison insensible."""
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return ascii_text.lower()


def detect_partie_et_voix(filename):
    """Analyse un nom de fichier et renvoie (partie_messe, voix).

    Returns:
        (partie_messe_code_or_None, voice_code_or_None)
    où ``partie_messe_code`` est l'une des valeurs de ``PartieMesse``
    ('KYRIE','GLORIA','SANCTUS','AGNUS_DEI','ALLELUIA','ANAMNESE',
     'PRIERE_UNIVERSELLE') et
    ``voice_code`` est l'un de 'S','A','T','B','I','M' (ou None si la voix
    n'est pas précisée — typiquement un fichier mix/non spécifié).
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    name = _normalize(stem)

    partie = None
    for keyword, code in _PARTIE_RULES:
        if keyword in name:
            partie = code
            break

    voice = None
    for keyword, code in _VOICE_RULES:
        if keyword in name:
            voice = code
            break

    return partie, voice


def _parse_version(filename):
    """Extrait le numéro de version d'un nom de fichier.

    'Gloria v3 alto.mp3' -> 3, 'Sanctus.mp3' -> 0. La recherche est insensible
    à la casse/accents via ``_normalize`` et s'appuie sur une frontière de mot
    afin que 'v2' dans 'v2n' ou 'v2-2' donne 2.
    """
    m = re.search(r'\bv(\d+)', _normalize(filename))
    return int(m.group(1)) if m else 0


# Ordre d'affichage/attachement des voix : SATB puis instrumental puis mix.
_VOICE_ORDER = {'S': 0, 'A': 1, 'T': 2, 'B': 3, 'I': 4, 'M': 5}


class Command(BaseCommand):
    help = 'Importe un ordinaire de messe depuis un dossier de fichiers MP3 (et PDF/MXL).'

    def add_arguments(self, parser):
        parser.add_argument('folder', type=str, help="Chemin du dossier contenant les fichiers de la messe.")
        parser.add_argument('--titre', required=True, help="Titre de l'ordinaire (ex: Messe du Bienheureux Carlo Acutis).")
        parser.add_argument('--compositeur', default=None, help="Nom du compositeur (créé s'il n'existe pas).")
        parser.add_argument('--description', default='', help='Description optionnelle.')
        parser.add_argument('--dry-run', action='store_true', help="Afficher ce qui serait importé sans rien écrire.")
        parser.add_argument('--force', action='store_true', help="Écraser un ordinaire existant avec ce slug.")

    def handle(self, *args, **options):
        # Les sauvegardes de FileField transitent par boto3 vers R2 : on coupe
        # le bruit de botocore (convention des autres commandes R2 du projet).
        logging.getLogger('botocore').setLevel(logging.WARNING)

        folder = Path(options['folder'])
        titre = options['titre']
        compositeur_nom = options['compositeur']
        description = options['description']
        dry_run = options['dry_run']
        force = options['force']

        if not folder.is_dir():
            msg = f"Le dossier n'existe pas ou n'est pas un dossier: {folder}"
            self.stdout.write(self.style.ERROR(msg))
            raise CommandError(msg)

        parties, shared_pdfs, shared_mxls, skipped, discarded = self._scan_folder(folder)
        slug = slugify(titre)

        if not parties:
            self.stdout.write(self.style.WARNING('Aucune partie de messe détectée dans le dossier.'))

        for path, reason in skipped:
            self.stdout.write(self.style.WARNING(f"Fichier ignoré ({reason}): {path.name}"))
        for path, reason in discarded:
            self.stdout.write(self.style.NOTICE(f"Fichier écarté ({reason}): {path.name}"))

        if dry_run:
            self._print_plan(titre, slug, compositeur_nom, parties, shared_pdfs, shared_mxls, discarded)
            return

        # --- Exécution réelle (écritures DB + stockage) ---
        compositeur = None
        if compositeur_nom:
            compositeur, _created = Compositeur.objects.get_or_create(
                nom__iexact=compositeur_nom,
                defaults={'nom': compositeur_nom},
            )

        existing = Ordinaire.objects.filter(slug=slug).first()
        if existing:
            if not force:
                raise CommandError(
                    f"Un ordinaire avec le slug '{slug}' existe déjà (id={existing.pk}). "
                    "Utilisez --force pour écraser ses partitions."
                )
            self.stdout.write(self.style.WARNING(
                f"Ordinaire existant '{existing}' trouvé: ses partitions seront remplacées."
            ))
            existing.partitions_messe.all().delete()
            existing.titre = titre
            existing.compositeur = compositeur
            existing.description = description
            existing.save()
            ordinaire = existing
        else:
            ordinaire = Ordinaire(titre=titre, compositeur=compositeur, description=description)
            ordinaire.save()
            self.stdout.write(self.style.SUCCESS(f"Ordinaire créé: {ordinaire} (slug={ordinaire.slug})."))

        parts_created = 0
        files_attached = 0
        warnings = len(skipped)

        for code in sorted(parties):
            group = parties[code]
            label = PartieMesse(code).label
            partition = Partition(
                psaume=None,
                ordinaire=ordinaire,
                partie_messe=code,
                titre=f"{ordinaire.titre} — {label}",
                compositeur=compositeur,
            )

            for path, voice in group['audios']:
                # Voix non détectée -> piste mix par défaut (choix conservateur).
                field_name = VOICE_FIELD_MAP[voice] if voice else VOICE_FIELD_MAP['M']
                with open(path, 'rb') as fh:
                    getattr(partition, field_name).save(path.name, File(fh), save=False)
                files_attached += 1

            pdfs = group['pdfs'] + shared_pdfs
            if pdfs:
                if len(pdfs) > 1:
                    self.stdout.write(self.style.WARNING(
                        f"[{code}] Plusieurs PDF trouvés, seul le premier est utilisé."
                    ))
                with open(pdfs[0], 'rb') as fh:
                    partition.partition_pdf.save(pdfs[0].name, File(fh), save=False)
                files_attached += 1

            mxls = group['mxls'] + shared_mxls
            if mxls:
                if len(mxls) > 1:
                    self.stdout.write(self.style.WARNING(
                        f"[{code}] Plusieurs MXL trouvés, seul le premier est utilisé."
                    ))
                with open(mxls[0], 'rb') as fh:
                    partition.partition_mxl.save(mxls[0].name, File(fh), save=False)
                files_attached += 1

            try:
                partition.full_clean(exclude=['psaume'])
            except ValidationError as exc:
                warnings += 1
                self.stdout.write(self.style.ERROR(f"[{code}] Partition invalide, ignorée: {exc}"))
                continue

            partition.save()
            parts_created += 1
            self.stdout.write(self.style.SUCCESS(f"[{code}] Partition créée ({label})."))

        self.stdout.write(self.style.SUCCESS(
            f"Terminé: ordinaire '{ordinaire}', {parts_created} partition(s), "
            f"{files_attached} fichier(s) attaché(s), {warnings} avertissement(s), "
            f"{len(discarded)} écarté(s)."
        ))

    def _scan_folder(self, folder):
        """Parcourt le dossier et regroupe les fichiers par partie détectée.

        Plusieurs versions d'une même (partie, voix) peuvent coexister : on ne
        conserve que la version la plus élevée (voir ``_resolve_versions``).
        """
        raw = {}
        shared_pdfs = []
        shared_mxls = []
        skipped = []
        discarded = []

        for path in sorted(folder.rglob('*')):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext in AUDIO_EXT:
                kind = 'audio'
            elif ext in PDF_EXT:
                kind = 'pdf'
            elif ext in MXL_EXT:
                kind = 'mxl'
            else:
                continue

            partie, voice = detect_partie_et_voix(path.name)
            if partie is None:
                if kind == 'audio':
                    skipped.append((path, 'partie non détectée'))
                elif kind == 'pdf':
                    shared_pdfs.append(path)
                else:
                    shared_mxls.append(path)
                continue

            group = raw.setdefault(partie, {'audios': [], 'pdfs': [], 'mxls': []})
            if kind == 'audio':
                group['audios'].append((path, voice))
            elif kind == 'pdf':
                group['pdfs'].append(path)
            else:
                group['mxls'].append(path)

        parties = {}
        for code, group in raw.items():
            audios = self._resolve_versions(group['audios'], discarded)
            parties[code] = {'audios': audios, 'pdfs': group['pdfs'], 'mxls': group['mxls']}

        return parties, shared_pdfs, shared_mxls, skipped, discarded

    @staticmethod
    def _resolve_versions(audios, discarded):
        """Garde un seul fichier par voix : numéro de version le plus élevé.

        Les fichiers sans voix détectée sont traités comme voix mix (M) et
        entrent en concurrence avec les fichiers ``mix`` explicites. En cas
        d'égalité de version, le premier nom alphabétique est conservé ; les
        fichiers écartés sont ajoutés à ``discarded`` avec la raison.
        """
        by_voice = {}
        for path, voice in audios:
            effective = voice or 'M'
            version = _parse_version(path.name)
            name = path.name
            current = by_voice.get(effective)
            if current is None:
                by_voice[effective] = (version, path, voice, name)
                continue
            cur_version, cur_path, _cur_voice, cur_name = current
            if version > cur_version or (version == cur_version and name < cur_name):
                reason = (f"version {cur_version} = {version}, ordre alphabétique"
                          if version == cur_version
                          else f"version {cur_version} < {version}")
                discarded.append((cur_path, reason))
                by_voice[effective] = (version, path, voice, name)
            else:
                reason = (f"version {version} = {cur_version}, ordre alphabétique"
                          if version == cur_version
                          else f"version {version} < {cur_version}")
                discarded.append((path, reason))
        return [
            (path, voice)
            for _version, path, voice, _name in sorted(
                by_voice.values(),
                key=lambda item: _VOICE_ORDER.get(item[2] or 'M', 99),
            )
        ]

    def _print_plan(self, titre, slug, compositeur_nom, parties, shared_pdfs, shared_mxls, discarded):
        """Affiche le plan d'import sans toucher à la base ni aux fichiers."""
        self.stdout.write(self.style.NOTICE(f"Plan d'import (dry-run) pour: {titre}"))
        self.stdout.write(f"Slug prévu: {slug}")
        if compositeur_nom:
            self.stdout.write(f"Compositeur: {compositeur_nom} (créé s'il n'existe pas)")
        if shared_pdfs:
            self.stdout.write(f"PDF partagés (appliqués à chaque partie): {[p.name for p in shared_pdfs]}")
        if shared_mxls:
            self.stdout.write(f"MXL partagés (appliqués à chaque partie): {[p.name for p in shared_mxls]}")

        for code in sorted(parties):
            group = parties[code]
            label = PartieMesse(code).label
            self.stdout.write(f"  [{code}] {label}:")
            for path, voice in group['audios']:
                field = VOICE_FIELD_MAP[voice] if voice else VOICE_FIELD_MAP['M']
                self.stdout.write(f"    - audio {voice or 'mix'} -> {field}: {path.name}")
            for path in group['pdfs']:
                self.stdout.write(f"    - partition_pdf: {path.name}")
            for path in group['mxls']:
                self.stdout.write(f"    - partition_mxl: {path.name}")

        if discarded:
            self.stdout.write(self.style.NOTICE("Fichiers écartés (version inférieure):"))
            for path, reason in discarded:
                self.stdout.write(f"  - {path.name} ({reason})")

        self.stdout.write(self.style.SUCCESS("Dry-run terminé: aucune écriture."))
