import logging

from celery import shared_task
from django.db import transaction

from ..models import Partition
from ..models.audio_variant import PartitionAudioTempoVariant
from ..services.audio.tempo_variants import (
    build_partition_tempo_variant_status,
    ensure_tempo_variant_rows,
    generate_tempo_variants_for_partition,
    get_missing_source_voice_types,
    get_missing_tempo_variant_voice_types,
    parse_apple_tempo,
)
from .priorities import (
    AUDIO_QUEUE_PRIORITY_BULK,
    AUDIO_QUEUE_PRIORITY_USER,
    celery_priority_for,
    normalize_audio_queue_priority,
)

logger = logging.getLogger(__name__)


def _dispatch_partition_tempo_variants(partition_id, tempo, priority):
    return generate_partition_tempo_variants.apply_async(
        args=(partition_id, str(parse_apple_tempo(tempo))),
        priority=celery_priority_for(priority),
    )


def enqueue_partition_tempo_variant_generation(partition, tempo, priority=AUDIO_QUEUE_PRIORITY_USER):
    if partition is None:
        return None

    tempo = parse_apple_tempo(tempo)
    priority = normalize_audio_queue_priority(priority)
    if not get_missing_tempo_variant_voice_types(partition, tempo):
        return build_partition_tempo_variant_status(partition, tempo)

    if get_missing_source_voice_types(partition):
        return build_partition_tempo_variant_status(partition, tempo)

    running_variants = PartitionAudioTempoVariant.objects.filter(
        partition=partition,
        tempo=tempo,
        status__in=[
            PartitionAudioTempoVariant.Status.QUEUED,
            PartitionAudioTempoVariant.Status.STARTED,
        ],
    )
    if running_variants.exists():
        if (
            priority == AUDIO_QUEUE_PRIORITY_USER
            and not running_variants.filter(status=PartitionAudioTempoVariant.Status.STARTED).exists()
            and running_variants.filter(queue_priority=AUDIO_QUEUE_PRIORITY_BULK).exists()
        ):
            with transaction.atomic():
                running_variants.select_for_update().update(
                    queue_priority=AUDIO_QUEUE_PRIORITY_USER,
                    last_error='',
                )

                def _promote():
                    _dispatch_partition_tempo_variants(partition.id, tempo, AUDIO_QUEUE_PRIORITY_USER)

                transaction.on_commit(_promote)
        return build_partition_tempo_variant_status(partition, tempo)

    with transaction.atomic():
        ensure_tempo_variant_rows(partition, tempo, queue_priority=priority)

        def _dispatch():
            _dispatch_partition_tempo_variants(partition.id, tempo, priority)

        transaction.on_commit(_dispatch)

    return build_partition_tempo_variant_status(partition, tempo)


@shared_task(bind=True, name='psaumes.generate_partition_tempo_variants')
def generate_partition_tempo_variants(self, partition_id, tempo):
    try:
        partition = Partition.objects.get(pk=partition_id)
    except Partition.DoesNotExist:
        logger.error("Tempo variant job received unknown partition id=%s", partition_id)
        return {'partition_id': partition_id, 'status': 'missing-partition'}

    generated_count = generate_tempo_variants_for_partition(partition, tempo)
    return {
        'partition_id': partition.id,
        'tempo': str(parse_apple_tempo(tempo)),
        'generated_count': generated_count,
        'status': build_partition_tempo_variant_status(partition, tempo)['status'],
    }
