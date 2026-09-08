import logging
import os
from django.shortcuts import get_object_or_404, redirect
from django.http import FileResponse, Http404
from django.utils.text import slugify
from ..models import Partition

logger = logging.getLogger(__name__)

def download_pdf(request, partition_id):
    """Serve PDF with Content-Disposition: attachment to force download, or inline for iframe viewing."""
    partition = get_object_or_404(Partition, pk=partition_id)
    if not partition.partition_pdf:
        raise Http404("PDF non disponible")

    # Check if inline viewing is requested (for iframe)
    inline = request.GET.get('inline', 'false').lower() == 'true'
    
    # Check storage backend type
    storage_backend = partition.partition_pdf.storage.__class__.__name__
    logger.debug(f"Serving PDF for partition {partition_id}, storage: {storage_backend}, inline: {inline}")
    
    # If using R2 storage and inline viewing, try to use R2 URL directly first
    if inline and 'S3' in storage_backend and os.environ.get('CLOUDFLARE_R2_BUCKET_NAME'):
        try:
            # Get the signed URL from R2
            pdf_url = partition.partition_pdf.url
            logger.debug(f"Redirecting to R2 URL: {pdf_url}")
            return redirect(pdf_url)
        except Exception as e:
            logger.warning(f"Could not get R2 URL for partition {partition_id}: {e}, proxying through Django instead")
            # Fall through to proxy mode
    
    try:
        logger.debug(f"Streaming PDF file for partition {partition_id} from storage")
        pdf_file = partition.partition_pdf.open('rb')
    except Exception as e:
        logger.error(f"Error reading PDF file for partition {partition_id}: {e}", exc_info=True)
        raise Http404("PDF non disponible")

    filename = f"{slugify(partition.titre or f'partition-{partition_id}')}.pdf"
    return FileResponse(
        pdf_file,
        content_type='application/pdf',
        as_attachment=not inline,
        filename=filename,
    )


def download_audio(request, partition_id, voice_type):
    """Serve audio file (S/A/T/B/I/M) by redirecting to storage if available, or serving content."""
    partition = get_object_or_404(Partition, pk=partition_id)
    audio_field = partition.get_audio_field(voice_type)
    
    if not audio_field:
        raise Http404("Fichier audio non disponible")

    storage_backend = audio_field.storage.__class__.__name__
    logger.debug(f"Serving audio for partition {partition_id} voice {voice_type}, storage: {storage_backend}")

    # If using R2 storage, try to use R2 URL directly first
    if 'S3' in storage_backend and os.environ.get('CLOUDFLARE_R2_BUCKET_NAME'):
        try:
            # Generate filename
            partition_slug = slugify(partition.titre or f"partition-{partition_id}")
            VOIX_NAMES = {
                'S': 'soprano', 'A': 'alto', 'T': 'tenor', 'B': 'basse', 
                'I': 'instrumental', 'M': 'mix'
            }
            voix = VOIX_NAMES.get(voice_type, 'audio')
            filename = f"{partition_slug}-{voix}.mp3"

            # Generate presigned URL with Content-Disposition to force download
            storage = audio_field.storage
            client = storage.connection.meta.client
            bucket_name = storage.bucket_name
            
            params = {
                'Bucket': bucket_name,
                'Key': audio_field.name,
                'ResponseContentDisposition': f'attachment; filename="{filename}"'
            }
            
            # Use a relatively short expiration (1 hour)
            audio_url = client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=3600
            )
            
            logger.debug(f"Redirecting audio for partition {partition_id} to presigned R2 URL: {audio_url}")
            return redirect(audio_url)
        except Exception as e:
            logger.warning(f"Could not generate presigned R2 URL for partition {partition_id}: {e}, proxying instead")
            # Fall through to proxy mode

    try:
        logger.debug(f"Streaming audio file for partition {partition_id} from storage")
        audio_file = audio_field.open('rb')
    except Exception as e:
        logger.error(f"Error reading audio file for partition {partition_id}: {e}", exc_info=True)
        raise Http404("Fichier audio non disponible")

    partition_slug = slugify(partition.titre or f"partition-{partition_id}")
    VOIX_NAMES = {
        'S': 'soprano', 'A': 'alto', 'T': 'tenor', 'B': 'basse', 
        'I': 'instrumental', 'M': 'mix'
    }
    voix = VOIX_NAMES.get(voice_type, 'audio')
    filename = f"{partition_slug}-{voix}.mp3"

    return FileResponse(
        audio_file,
        content_type='audio/mpeg',
        as_attachment=True,
        filename=filename,
    )
