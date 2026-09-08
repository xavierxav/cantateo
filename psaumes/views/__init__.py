from .base import (
    index,
    blog,
    histoire,
    contact,
    confidentialite,
    mentions_legales,
    ecoute_aleatoire,
)
from .details import psaume_detail, cantique_detail
from .ordinaire import ordinaire_list, ordinaire_detail, ordinaire_partie_detail
from .api import audio_status, audio_variants, search_autocomplete
from .files import download_pdf, download_audio
from .listing import toutes_les_partitions, calendrier_liturgique
from .editor import (
    simplified_banner_create,
    simplified_banner_delete,
    simplified_banner_list,
    simplified_banner_update,
    simplified_dashboard,
    simplified_partition_done,
    simplified_partition_files,
    simplified_partition_moments,
)
