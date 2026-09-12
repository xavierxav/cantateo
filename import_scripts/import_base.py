"""
Module commun pour les scripts d'import de psaumes et cantiques.

Contient les fonctions et classes partagées entre import_psaumes.py et import_fonsalas.py.
"""

import os
import sys
import json
import shutil
import time
import logging
import glob as glob_module
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'psalm_project.settings')
import django
django.setup()

from django.conf import settings
from psaumes.models import Compositeur, Psaume, MomentLiturgique

# Import des dépendances optionnelles
try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    import fitz
    HAS_FIZZ = True
except ImportError:
    HAS_FIZZ = False


# Mapping des temps liturgiques
TEMPS_MAPPING = {
    "avent": "AVENT",
    "noël": "NOEL",
    "noel": "NOEL",
    "ordinaire": "ORDINAIRE",
    "carême": "CAREME",
    "careme": "CAREME",
    "sainte": "SAINT",
    "pascal": "PASCAL",
}


def check_dependencies():
    """Vérifie que les dépendances requises sont installées."""
    missing = []
    if not HAS_GENAI:
        missing.append("google-genai")
    if not HAS_FIZZ:
        missing.append("pymupdf")

    if missing:
        print("Erreur: Dépendances manquantes:")
        for dep in missing:
            print(f"   - {dep} (pip install {dep})")
        sys.exit(1)


def setup_logging(log_dir: Path = None, script_name: str = "import") -> logging.Logger:
    """Configure logging to file and console."""
    if log_dir is None:
        log_dir = Path.cwd() / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{script_name}_{timestamp}.log"

    logger = logging.getLogger(script_name)
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers.clear()

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_latest_log_file(log_dir: Path, script_name: str) -> Optional[Path]:
    """Trouve le fichier log le plus récent pour un script donné."""
    pattern = str(log_dir / f"{script_name}_*.log")
    log_files = glob_module.glob(pattern)
    if not log_files:
        return None
    # Trier par date de modification (le plus récent en dernier)
    return Path(max(log_files, key=lambda f: Path(f).stat().st_mtime))


def extract_failed_folders_from_log(log_file: Path) -> Set[str]:
    """Extrait les noms des dossiers en erreur depuis un fichier log.

    Cherche la ligne "Failed folders: folder1, folder2, folder3" dans le log.
    """
    failed_folders = set()

    if not log_file.exists():
        print(f"Erreur: Le fichier log {log_file} n'existe pas")
        return failed_folders

    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Cherche "Failed folders: folder1, folder2, folder3"
    match = re.search(r'Failed folders: (.+)$', content, re.MULTILINE)
    if match:
        folders_str = match.group(1)
        for folder in folders_str.split(', '):
            folder = folder.strip()
            if folder:
                failed_folders.add(folder)

    return failed_folders


class GemmaClient:
    """Client pour l'API Google AI (Gemini / Gemma) via google-genai.

    Limite free tier : 15 RPM (4 secondes entre appels), 500 RPD par defaut.
    """

    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model or os.environ.get('GEMMA_MODEL') or os.environ.get('AI_MODEL') or 'gemini-3.1-flash-lite'
        self.client = genai.Client(api_key=api_key)
        self.last_call_time = 0
        self.min_interval = 4.0  # 15 RPM
        self.daily_call_count = 0
        self.max_rpd = int(os.environ.get('GEMMA_MAX_RPD', '500'))

    def _wait_if_needed(self):
        """Attend si nécessaire pour respecter le rate limit (15 RPM)."""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            time.sleep(wait_time)

    def call_gemma(self, prompt: str) -> Optional[str]:
        """Appelle l'API Google AI avec le modele configure."""
        if self.daily_call_count >= self.max_rpd:
            print(f"  Limite RPD atteinte ({self.max_rpd} appels/jour). Reessayez demain avec --retry-errors.")
            return None
        self._wait_if_needed()
        self.last_call_time = time.time()

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            self.daily_call_count += 1
            return response.text.strip()
        except Exception as e:
            print(f"  Erreur lors de l'appel a l'API: {e}")
            return None


def extract_text_from_pdf(
    pdf_path: Path,
    folder_name: str = "",
    logger=None,
    max_pages: int = 3
) -> str:
    """Extrait tout le texte d'un PDF de partitions, sans perte de syllabes ni de chiffres,
    avec logging en cas d'erreur."""

    text_parts = []

    try:
        with fitz.open(pdf_path) as doc:
            for i in range(min(max_pages, doc.page_count)):
                page = doc.load_page(i)
                raw_text = page.get_text("text")

                for line in raw_text.splitlines():
                    # ne garder que lettres, chiffres, accents, ponctuation et espaces
                    cleaned = "".join(
                        c for c in line if c.isalnum() or c in " -'',.!?:;°"
                    ).strip()

                    if cleaned:  # on ignore les lignes complètement vides
                        text_parts.append(cleaned)

        return "\n".join(text_parts)

    except Exception as e:
        error_msg = (
            f"PDF extraction failed for {pdf_path.name} in folder '{folder_name}': {e}"
        )
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        return ""

def analyze_pdf_with_gemma(
    gemma_client: GemmaClient,
    text: str,
    folder_name: str = "",
    logger: logging.Logger = None
) -> Optional[Dict]:
    """Analyse le texte extrait avec Gemma pour identifier les informations du psaume ou cantique."""
    prompt = f"""Analyse ce texte extrait d'une partition de chant liturgique (psaume ou cantique).
Le texte est "sale" car extrait d'un PDF de partition : il peut contenir des sauts de ligne au milieu des mots, des caractères manquants, etc.

TEXTE EXTRAIT :
{text}

NOM DU DOSSIER SOURCE (contient un code liturgique obligatoire) :
{folder_name}

IMPORTANT : Le nom du dossier encode AU MOINS UN moment liturgique que tu DOIS inclure dans ta reponse. Le prefixe B ou C indique l'annee liturgique. Exemples de decodage :
- "BAv1" = Avent semaine 1 annee B
- "BAv2" = Avent semaine 2 annee B
- "BCe" = Mercredi des Cendres (FETE)
- "BPent" = Pentecote (FETE)
- "BSF" = Sainte Famille (FETE, annee B)
- "BO10" = 10eme dimanche Ordinaire annee B
- "BAsc" = Ascension (FETE, annee B)
- "BAssomption" = Assomption de la Vierge Marie (FETE, annee B)
- "BStri" = Sainte Trinite (FETE, annee B)
- "CStri" = Sainte Trinite (FETE, annee C)

CRITICAL : L'annee liturgique du dossier (premiere lettre : B ou C) EST l'annee correcte. Le texte du PDF peut mentionner d'autres annees (ex: "Année B : 30e dimanche TO" dans un dossier C). Tu dois TOUJOURS utiliser l'annee du dossier pour les moments que tu extrais, SAUF si le PDF mentionne explicitement une autre annee pour un moment specifique different. Par exemple, un dossier C peut contenir un psaume utilise en annee C pour l'Avent ET en annee B pour le Temps Ordinaire - dans ce cas, extrais les deux moments avec leurs annees respectives.

Tu DOIS inclure le moment du dossier dans moments_liturgiques. Extrais ENSUITE tous les AUTRES moments mentionnes dans le texte du PDF. Un psaume peut avoir plusieurs moments liturgiques pour des annees differentes.

STRUCTURE TYPIQUE D'UNE PARTITION :
1. EN-TÊTE : numéro du psaume (ex: "Ps 024") ou référence du cantique (ex: "Is 12,1-6"), puis les moments liturgiques
2. REFRAIN : texte chanté par l'assemblée, souvent fragmenté/sale dans l'extraction
3. VERSETS : corps du texte, généralement plus propre que le refrain

COMMENT IDENTIFIER LE REFRAIN vs LES VERSETS :
- Le REFRAIN apparaît en premier, souvent avant l'en-tête, il est souvent fragmenté avec des syllabes séparées
- Les VERSETS suivent le refrain, ils sont généralement plus lisibles
- Reconstitue le refrain en nettoyant les fragments (ex: "Sei- gneur" → "Seigneur")

EXTRAIS ces informations au format JSON strict :

1. TYPE : "psaume" (avec numéro) ou "cantique" (avec référence biblique comme "Is 12,1-6")

2. REFRAIN : Le texte complet du refrain, nettoyé et reconstitué. Corrige les coupures de mots.

3. VERSETS : Le corps du texte (les strophes numérotées), nettoyé. Sépare chaque verset par un saut de ligne.

4. TITRE : Un titre court et élégant dérivé du début du refrain, avec les espaces, accents et ponctuation nécessaires. Exemples :
   - Refrain "Le Seigneur est mon berger, je ne manque de rien" → Titre "Le Seigneur est mon berger"
   - Refrain "Goûtez et voyez comme est bon le Seigneur" → Titre "Goûtez et voyez"
   - Refrain "Tu es mon Dieu, toi seul es mon bonheur" → Titre "Tu es mon Dieu"
   - Refrain "Béni soit le Seigneur, le Dieu d'Israël" → Titre "Béni soit le Seigneur"

5. MOMENTS LITURGIQUES : Sur une ligne d'en-tête, l'année (A, B, C) s'applique à tous les moments de cette ligne.
   Exemple : "Année B : Trinité, 12ème dimanche ordinaire" → 2 moments pour l'année B

FORMAT JSON (pas de markdown, pas de code blocks) :

Pour un PSAUME :
{{
  "type": "psaume",
  "numero": 24,
  "titre": "Rappelle-toi, Seigneur",
  "refrain": "Rappelle-toi, Seigneur, ta tendresse et ton amour.",
  "versets": "Seigneur, enseigne-moi tes voies,\\nfais-moi connaître ta route.\\n\\n Dirige-moi par ta vérité,\\nenseigne-moi, car tu es le Dieu qui me sauve.",
  "moments_liturgiques": [
    {{
      "type": "DIMANCHE",
      "annee": "A",
      "semaine": 26,
      "temps": "ORDINAIRE"
    }}
  ]
}}

Pour un CANTIQUE :
{{
  "type": "cantique",
  "reference_biblique": "Is 12,1-6",
  "titre": "Exultant de joie",
  "refrain": "Exultant de joie, vous puiserez les eaux aux sources du salut.",
  "versets": "1. Voici le Dieu qui me sauve :\\nj'ai confiance, je n'ai plus de crainte.",
  "moments_liturgiques": [
    {{
      "type": "DIMANCHE",
      "annee": "C",
      "semaine": 3,
      "temps": "AVENT"
    }}
  ]
}}

TYPES DE MOMENTS LITURGIQUES :
- DIMANCHE : annee (A/B/C), semaine (entier), temps (AVENT/NOEL/ORDINAIRE/CAREME/SAINT/PASCAL)
- SEMAINE : semaine (entier), jour (1-6 pour Lundi-Samedi), parite (P pour paire, I pour impaire), temps
- FETE : nom_fete exact (voir liste ci-dessous), et annee (A/B/C) si fête cyclique

Fêtes cycliques (ajouter annee A/B/C) : "Trinité", "Christ-Roi", "Sainte Famille", "Baptême du Seigneur", "Sacré-Cœur"
Fêtes fixes SANS annee (ne pas ajouter annee A/B/C) : "Mercredi des Cendres", "Vendredi Saint", "Dimanche des Rameaux". Ces fetes utilisent les memes lectures chaque annee.
Liste des noms de fêtes fixes à utiliser exactement si possible : "Nativité du Seigneur", "Sainte Marie Mère de Dieu", "Annonciation du Seigneur", "Assomption de la Vierge Marie", "Immaculée Conception", "Toussaint", "Nativité de Saint Jean Baptiste", "Saints Pierre et Paul", "Transfiguration du Seigneur", "Exaltation de la Sainte Croix", "Commémoration des fidèles défunts", "Trinité", "Christ-Roi", "Sainte Famille", "Mercredi des Cendres", "Dimanche des Rameaux", "Jeudi Saint", "Vendredi Saint", "Pâques", "Ascension", "Pentecôte", "Saint-Sacrement", "Sacré-Cœur", "Baptême du Seigneur", "Épiphanie"

IMPORTANT - VIGILE PASCALE : La Veillee Pascale a 7 lectures de l'Ancien Testament, chacune avec son propre psaume. Ces lectures sont IDENTIQUES pour les 3 annees (A, B, C).

REGLES POUR LES MOMENTS VIGILE PASCALE :
1. EXTRAIRE un moment Vigile Pascale UNIQUEMENT si le nom du dossier contient "VP" suivi d'un numero (ex: VP2, VP4, VP6). Si le dossier ne contient pas "VP", NE PAS extraire de moment Vigile Pascale, meme si le texte du PDF le mentionne.
2. Le numero de lecture vient EXCLUSIVEMENT du nom du dossier (VP2 = lecture 2, VP6 = lecture 6). NE JAMAIS utiliser un numero provenant du texte du PDF (ex: "3eme dimanche du Careme" ne veut PAS dire lecture 3).
3. Le format OBLIGATOIRE est : nom_fete = "Vigile Pascale N" (ou N est le numero du dossier), annee = "" (chaine vide). Exemple : {"type": "FETE", "nom_fete": "Vigile Pascale 6", "annee": ""}.
4. NE JAMAIS utiliser un champ "numero" separe. Le numero doit etre dans nom_fete.
5. NE JAMAIS utiliser "Vigile Pascale" sans numero.

NE PAS extraire "octave de la Nativite" ou "octave de Paques" comme un moment separe. Ces expressions decrivent le contexte d'une fete, pas un moment liturgique distinct.

RÈGLES IMPORTANTES :
- Si plusieurs années sont mentionnées (ex: "Année A et B"), crée un moment pour chaque année
- Nettoie le tritre, refrain et les versets des artefacts de l'extraction PDF
- Le titre doit être court (3-7 mots), élégant, et commencer par une majuscule"""

    response_text = gemma_client.call_gemma(prompt)

    if not response_text:
        return None

    try:
        # Nettoyer la réponse si elle contient des markdown code blocks
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        # Parser le JSON
        data = json.loads(response_text)

    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing failed for folder '{folder_name}': {str(e)} | Response: {response_text[:200]}"
        if logger:
            logger.error(error_msg)
        print(f"  Erreur de parsing JSON: {e}")
        print(f"   Reponse recue: {response_text[:200]}...")
        return None

    # Log pour debug - afficher les moments liturgiques parsés
    if logger:
        moments = data.get('moments_liturgiques', [])
        logger.debug(f"Parsed JSON for '{folder_name}': type={data.get('type')}, numero={data.get('numero')}, ref={data.get('reference_biblique')}")
        for i, m in enumerate(moments):
            logger.debug(f"  Moment {i+1}: {m}")

    return data


def normalize_temps(temps_str: str) -> str:
    """Normalise le nom du temps liturgique."""
    temps_lower = temps_str.lower().strip()
    return TEMPS_MAPPING.get(temps_lower, temps_str.upper())


def create_or_get_compositeur(nom: str = "Fonsalas") -> Compositeur:
    """Crée ou récupère le compositeur."""
    compositeur, created = Compositeur.objects.get_or_create(nom=nom)
    return compositeur


def copy_file_to_media(source: Path, dest_relative: str) -> Path:
    """Copie un fichier vers MEDIA_ROOT."""
    media_root = Path(settings.MEDIA_ROOT)
    dest_path = media_root / dest_relative
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest_path)
    return dest_path


def _parse_int(value) -> Optional[int]:
    """Convertit une valeur en entier, retourne None si impossible."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def build_moment_query(moment_data: Dict) -> Optional[Dict]:
    """Construit les paramètres de requête pour trouver un MomentLiturgique (sans chant FK)."""
    moment_type = (moment_data.get('type') or '').upper()

    if moment_type == 'DIMANCHE':
        temps = normalize_temps(moment_data.get('temps') or '')
        semaine = _parse_int(moment_data.get('semaine'))
        annee = (moment_data.get('annee') or '').upper()

        if not temps or semaine is None or not annee:
            print(f"     build_moment_query DIMANCHE: donnees incompletes - temps={temps}, semaine={semaine}, annee={annee}")
            return None

        return {
            'temps': temps,
            'semaine': semaine,
            'jour': 0,
            'annee': annee,
        }

    elif moment_type == 'SEMAINE':
        temps = normalize_temps(moment_data.get('temps') or '')
        semaine = _parse_int(moment_data.get('semaine'))
        jour = _parse_int(moment_data.get('jour'))
        parite = (moment_data.get('parite') or '').upper()

        if not temps or semaine is None or jour is None or not parite:
            print(f"     build_moment_query SEMAINE: donnees incompletes - temps={temps}, semaine={semaine}, jour={jour}, parite={parite}")
            return None

        return {
            'temps': temps,
            'semaine': semaine,
            'jour': jour,
            'parite': parite,
        }

    elif moment_type in ('FÊTE', 'FETE'):
        nom_fete = (moment_data.get('nom_fete') or '').strip()
        annee = (moment_data.get('annee') or '').upper()

        if not nom_fete:
            return None

        query = {'nom_fete': nom_fete}
        if annee:
            query['annee'] = annee
        return query

    return None


def find_existing_chant_with_common_moments(
    chant_type: str,
    chant_identifier,
    moments_data: List[Dict]
) -> Optional[Psaume]:
    """
    Cherche un chant existant qui partage au moins un moment liturgique.

    Args:
        chant_type: 'psaume' ou 'cantique'
        chant_identifier: numero (pour psaume) ou reference_biblique (pour cantique)
        moments_data: Liste des moments liturgiques à importer

    Returns:
        Le chant existant si un moment commun est trouvé, None sinon
    """
    if chant_type == 'psaume':
        label = f"Psaume {chant_identifier}"
    else:
        label = f"Cantique {chant_identifier}"
    
    existing_chants = Psaume.objects.filter(nom_psaume=label)

    for psaume in existing_chants:
        for moment_data in moments_data:
            query = build_moment_query(moment_data)
            if query and MomentLiturgique.objects.filter(psaume=psaume, **query).exists():
                return psaume  # Moment commun trouvé

    return None  # Aucun moment commun





def normalize_moments_for_comparison(moments_data: List[Dict]) -> Set[tuple]:
    """
    Normalise une liste de moments liturgiques pour la comparaison.
    
    Convertit chaque moment en tuple de paramètres normalisés pour permettre
    une comparaison facile entre deux listes de moments.
    
    Args:
        moments_data: Liste de dictionnaires de moments liturgiques
        
    Returns:
        Set de tuples représentant les moments normalisés
    """
    normalized = set()
    
    for moment_data in moments_data:
        query = build_moment_query(moment_data)
        if query:
            # Créer un tuple trié pour la comparaison
            # Trier les clés pour avoir un ordre cohérent
            sorted_items = tuple(sorted(query.items()))
            normalized.add(sorted_items)
    
    return normalized


def compare_moments_liturgiques(
    moments_data_1: List[Dict],
    moments_data_2: List[Dict]
) -> bool:
    """
    Compare deux listes de moments liturgiques pour vérifier qu'elles sont identiques.
    
    Args:
        moments_data_1: Première liste de moments
        moments_data_2: Deuxième liste de moments
        
    Returns:
        True si les deux listes contiennent exactement les mêmes moments, False sinon
    """
    normalized_1 = normalize_moments_for_comparison(moments_data_1)
    normalized_2 = normalize_moments_for_comparison(moments_data_2)
    
    return normalized_1 == normalized_2


def check_moments_existence(moments_data: List[Dict]) -> Dict:
    """
    Vérifie quels moments liturgiques existent déjà dans la base de données.

    Returns:
        Dict avec:
        - 'existing': liste de tuples (moment_data, psaume_id, moment_str, psaume) pour les moments avec psaume
        - 'orphans': liste de tuples (moment_data, moment_str, moment) pour les moments orphelins
        - 'not_existing': liste de moment_data pour les moments qui n'existent pas
    """
    existing = []
    orphans = []
    not_existing = []

    for moment_data in moments_data:
        query_params = build_moment_query(moment_data)

        if query_params is None:
            print(f"     Donnees de moment incompletes: {moment_data}")
            continue

        try:
            moment = MomentLiturgique.objects.filter(**query_params).first()

            if moment:
                if moment.psaume:
                    existing.append((
                        moment_data,
                        moment.psaume_id,
                        str(moment),
                        moment.psaume
                    ))
                else:
                    # Moment orphelin (existe mais sans chant)
                    orphans.append((
                        moment_data,
                        str(moment),
                        moment
                    ))
            else:
                not_existing.append(moment_data)

        except Exception as e:
            print(f"     Erreur lors de la recherche du moment: {e}")
            not_existing.append(moment_data)

    return {
        'existing': existing,
        'orphans': orphans,
        'not_existing': not_existing,
    }


def link_orphan_moments_to_chant(psaume: Psaume, moments_data: List[Dict]) -> int:
    """
    Lie les moments orphelins (sans chant) aux données fournies au chant.

    Returns:
        Nombre de moments orphelins liés au chant
    """
    linked_count = 0

    for moment_data in moments_data:
        query_params = build_moment_query(moment_data)

        if query_params is None:
            continue

        try:
            moment = MomentLiturgique.objects.filter(**query_params).first()

            # Si le moment existe mais est orphelin (pas de chant), le lier
            if moment and not moment.psaume:
                moment.psaume = psaume
                moment.save()
                linked_count += 1
                print(f"    Moment orphelin lie au {get_psaume_label_safe(psaume)}")
        except Exception as e:
            print(f"     Erreur lors de la liaison du moment orphelin: {e}")

    return linked_count


def create_moment_liturgique(psaume: Psaume, moment_data: Dict, dry_run: bool = False, force: bool = False) -> Optional[MomentLiturgique]:
    """Crée ou lie un moment liturgique à partir des données extraites.

    Si le moment existe déjà :
    - S'il est orphelin (psaume=None) : le lie au chant fourni
    - S'il est déjà lié au même chant : retourne le moment existant
    - S'il est lié à un autre chant : 
      * Si force=True : réassigne au nouveau chant (avec avertissement)
      * Si force=False : retourne None et affiche un avertissement

    Si le moment n'existe pas, il est créé avec le chant.

    Returns:
        Le MomentLiturgique créé ou existant, ou None en cas de conflit (sauf si force=True)
    """
    moment_type = (moment_data.get('type') or '').upper()

    if moment_type == 'DIMANCHE':
        temps = normalize_temps(moment_data.get('temps') or '')
        semaine = _parse_int(moment_data.get('semaine'))
        annee = (moment_data.get('annee') or '').upper()

        if not temps or semaine is None or not annee:
            print(f"     Donnees incompletes pour DIMANCHE: temps={temps}, semaine={semaine}, annee={annee}")
            return None

        if dry_run:
            print(f"    Creerait MomentLiturgique: Dimanche {semaine} - {temps} (Annee {annee})")
            return None

        # Chercher d'abord si le moment existe (sans filtre sur chant)
        lookup_params = {'temps': temps, 'semaine': semaine, 'jour': 0, 'annee': annee}
        existing = MomentLiturgique.objects.filter(**lookup_params).first()

        if existing:
            if existing.psaume_id == psaume.pk:
                # Déjà lié au même chant
                return existing
            elif existing.psaume_id is None:
                # Moment orphelin : le lier au chant
                existing.psaume = psaume
                existing.save()
                print(f"      Moment orphelin lie au chant")
                return existing
            else:
                # Moment déjà lié à un autre chant
                if force:
                    old_chant_label = get_psaume_label_safe(existing.psaume)
                    existing.psaume = psaume
                    existing.save()
                    print(f"      ATTENTION: Moment reattribue depuis {old_chant_label} vers {get_psaume_label_safe(psaume)} (--force)")
                    return existing
                else:
                    old_chant_label = get_psaume_label_safe(existing.psaume)
                    print(f"      CONFLIT: Moment deja lie a {old_chant_label} (utilisez --force pour reattribuer)")
                    return None

        return MomentLiturgique.objects.create(psaume=psaume, **lookup_params)

    elif moment_type == 'SEMAINE':
        temps = normalize_temps(moment_data.get('temps') or '')
        semaine = _parse_int(moment_data.get('semaine'))
        jour = _parse_int(moment_data.get('jour'))
        parite = (moment_data.get('parite') or '').upper()

        if not temps or semaine is None or jour is None or not parite:
            print(f"     Donnees incompletes pour SEMAINE: temps={temps}, semaine={semaine}, jour={jour}, parite={parite}")
            return None

        if dry_run:
            jour_names = ['', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi']
            print(f"    Creerait MomentLiturgique: {jour_names[jour]} - Semaine {semaine} - {temps} (Annee {'paire' if parite == 'P' else 'impaire'})")
            return None

        # Chercher d'abord si le moment existe (sans filtre sur chant)
        lookup_params = {'temps': temps, 'semaine': semaine, 'jour': jour, 'parite': parite}
        existing = MomentLiturgique.objects.filter(**lookup_params).first()

        if existing:
            if existing.psaume_id == psaume.pk:
                # Déjà lié au même chant
                return existing
            elif existing.psaume_id is None:
                # Moment orphelin : le lier au chant
                existing.psaume = psaume
                existing.save()
                print(f"      Moment orphelin lie au chant")
                return existing
            else:
                # Moment déjà lié à un autre chant
                if force:
                    old_chant_label = get_psaume_label_safe(existing.psaume)
                    existing.psaume = psaume
                    existing.save()
                    print(f"      ATTENTION: Moment reattribue depuis {old_chant_label} vers {get_psaume_label_safe(psaume)} (--force)")
                    return existing
                else:
                    old_chant_label = get_psaume_label_safe(existing.psaume)
                    print(f"      CONFLIT: Moment deja lie a {old_chant_label} (utilisez --force pour reattribuer)")
                    return None

        return MomentLiturgique.objects.create(psaume=psaume, **lookup_params)

    elif moment_type == 'FÊTE' or moment_type == 'FETE':
        nom_fete = (moment_data.get('nom_fete') or '').strip()
        annee = (moment_data.get('annee') or '').upper()  # Optionnel pour fêtes cycliques

        if not nom_fete:
            print(f"     Nom de fete manquant")
            return None

        if dry_run:
            if annee:
                print(f"    Creerait MomentLiturgique: Fete - {nom_fete} (Annee {annee})")
            else:
                print(f"    Creerait MomentLiturgique: Fete - {nom_fete}")
            return None

        # Chercher d'abord si le moment existe (sans filtre sur chant)
        lookup_params = {'nom_fete': nom_fete}
        if annee:
            lookup_params['annee'] = annee

        existing = MomentLiturgique.objects.filter(**lookup_params).first()

        if existing:
            if existing.psaume_id == psaume.pk:
                # Déjà lié au même chant
                return existing
            elif existing.psaume_id is None:
                # Moment orphelin : le lier au chant
                existing.psaume = psaume
                existing.save()
                print(f"      Moment orphelin lie au chant")
                return existing
            else:
                # Moment déjà lié à un autre chant
                if force:
                    old_chant_label = get_psaume_label_safe(existing.psaume)
                    existing.psaume = psaume
                    existing.save()
                    print(f"      ATTENTION: Moment reattribue depuis {old_chant_label} vers {get_psaume_label_safe(psaume)} (--force)")
                    return existing
                else:
                    old_chant_label = get_psaume_label_safe(existing.psaume)
                    print(f"      CONFLIT: Moment deja lie a {old_chant_label} (utilisez --force pour reattribuer)")
                    return None

        return MomentLiturgique.objects.create(psaume=psaume, **lookup_params)

    else:
        print(f"     Type de moment inconnu: {moment_type}")
        return None


def get_psaume_label_safe(psaume: Optional[Psaume]) -> str:
    """Retourne un label descriptif pour un psaume/cantique, gère le cas None."""
    if psaume is None:
        return "aucun psaume/cantique"
    
    return psaume.nom_psaume
