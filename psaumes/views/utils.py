import logging
from ..tasks import enqueue_partition_audio_generation, enqueue_partition_audio_normalization

logger = logging.getLogger(__name__)

def trigger_async_audio_generation(partition):
    """Trigger lazy audio generation in background (non-blocking)."""
    if not partition:
        return

    try:
        enqueue_partition_audio_normalization(partition)
        enqueue_partition_audio_generation(partition)
    except Exception:
        logger.exception('Unable to start background audio generation for partition %s', getattr(partition, 'id', None))
