from .audio import (
    PartitionAudioGenerationJobAdmin,
    PartitionAudioNormalizationJobAdmin,
    PartitionAudioTempoVariantAdmin,
    PartitionOmrJobAdmin,
)
from .compositeur import CompositeurAdmin
from .moment_liturgique import MomentLiturgiqueAdmin
from .psaume import PsaumeAdmin
from .partition import PartitionAdmin
from .ordinaire import OrdinaireAdmin
from .banner import SiteBannerAdmin

__all__ = [
    'PartitionAudioGenerationJobAdmin',
    'PartitionAudioNormalizationJobAdmin',
    'PartitionAudioTempoVariantAdmin',
    'PartitionOmrJobAdmin',
    'CompositeurAdmin',
    'MomentLiturgiqueAdmin',
    'PsaumeAdmin',
    'PartitionAdmin',
    'OrdinaireAdmin',
    'SiteBannerAdmin',
]
