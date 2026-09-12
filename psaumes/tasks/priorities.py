from ..models import PartitionAudioGenerationJob, PartitionOmrJob

AUDIO_QUEUE_PRIORITY_USER = PartitionAudioGenerationJob.QueuePriority.USER
AUDIO_QUEUE_PRIORITY_BULK = PartitionAudioGenerationJob.QueuePriority.BULK
OMR_QUEUE_PRIORITY_USER = PartitionOmrJob.QueuePriority.USER
OMR_QUEUE_PRIORITY_BULK = PartitionOmrJob.QueuePriority.BULK
AUDIO_CELERY_PRIORITY = {
    AUDIO_QUEUE_PRIORITY_USER: 0,
    AUDIO_QUEUE_PRIORITY_BULK: 9,
}
OMR_CELERY_PRIORITY = {
    OMR_QUEUE_PRIORITY_USER: 0,
    OMR_QUEUE_PRIORITY_BULK: 9,
}
NORMALIZATION_CELERY_PRIORITY = {
    AUDIO_QUEUE_PRIORITY_USER: 0,
    AUDIO_QUEUE_PRIORITY_BULK: 6,
}


def normalize_audio_queue_priority(priority):
    if priority == AUDIO_QUEUE_PRIORITY_BULK:
        return AUDIO_QUEUE_PRIORITY_BULK
    return AUDIO_QUEUE_PRIORITY_USER


def normalize_omr_queue_priority(priority):
    if priority == OMR_QUEUE_PRIORITY_BULK:
        return OMR_QUEUE_PRIORITY_BULK
    return OMR_QUEUE_PRIORITY_USER


def celery_priority_for(priority):
    return AUDIO_CELERY_PRIORITY[normalize_audio_queue_priority(priority)]


def celery_priority_for_omr(priority):
    return OMR_CELERY_PRIORITY[normalize_omr_queue_priority(priority)]


def celery_priority_for_normalization(priority):
    return NORMALIZATION_CELERY_PRIORITY[normalize_audio_queue_priority(priority)]
