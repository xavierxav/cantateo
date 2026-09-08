from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify
from typing import Optional
import os
from .compositeur import Compositeur
from .utils import (
    partition_pdf_path, partition_mxl_path,
    partition_audio_soprano_path, partition_audio_alto_path,
    partition_audio_tenor_path, partition_audio_basse_path,
    partition_audio_instrumental_path, partition_audio_mix_path
)
from .validators import validate_mxl_upload, validate_mp3_upload, validate_pdf_upload

VOIX_CHOICES = [
    ('S', 'Soprano'),
    ('A', 'Alto'),
    ('T', 'Ténor'),
    ('B', 'Basse'),
    ('I', 'Instrumental'),
    ('M', 'Mix'),
]

VOIX_LABELS = dict(VOIX_CHOICES)

VOICE_FIELD_MAP = {
    'S': 'audio_soprano',
    'A': 'audio_alto',
    'T': 'audio_tenor',
    'B': 'audio_basse',
    'I': 'audio_instrumental',
    'M': 'audio_mix',
}

SATB_VOICES = ['S', 'A', 'T', 'B']


class PartieMesse(models.TextChoices):
    KYRIE = 'KYRIE', 'Kyrie'
    GLORIA = 'GLORIA', 'Gloria'
    SANCTUS = 'SANCTUS', 'Sanctus'
    AGNUS_DEI = 'AGNUS_DEI', 'Agnus Dei'
    ALLELUIA = 'ALLELUIA', 'Alléluia'
    ANAMNESE = 'ANAMNESE', 'Anamnèse'
    PRIERE_UNIVERSELLE = 'PRIERE_UNIVERSELLE', 'Prière Universelle'


class Partition(models.Model):
    """
    Une partition musicale (arrangement) d'un psaume ou cantique.
    """
    psaume = models.ForeignKey(
        'Psaume',
        on_delete=models.CASCADE,
        related_name='partitions',
        null=True,
        blank=True
    )
    ordinaire = models.ForeignKey(
        'psaumes.Ordinaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partitions_messe',
    )
    partie_messe = models.CharField(
        max_length=20,
        choices=PartieMesse.choices,
        blank=True,
        default='',
    )
    titre = models.CharField(max_length=200, blank=True)
    compositeur = models.ForeignKey(
        Compositeur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partitions'
    )
    refrain = models.TextField(blank=True, help_text="Refrain chanté par l'assemblée")
    versets = models.TextField(blank=True)

    # Partitions
    partition_pdf = models.FileField(
        upload_to=partition_pdf_path,
        validators=[validate_pdf_upload],
        blank=True,
        null=True,
        verbose_name="Partition PDF"
    )
    partition_mxl = models.FileField(
        upload_to=partition_mxl_path,
        validators=[validate_mxl_upload],
        blank=True,
        null=True,
        verbose_name="Partition MXL"
    )

    # Audio files per voice
    audio_soprano = models.FileField(
        upload_to=partition_audio_soprano_path,
        validators=[validate_mp3_upload],
        blank=True, null=True, verbose_name="Audio Soprano"
    )
    audio_alto = models.FileField(
        upload_to=partition_audio_alto_path,
        validators=[validate_mp3_upload],
        blank=True, null=True, verbose_name="Audio Alto"
    )
    audio_tenor = models.FileField(
        upload_to=partition_audio_tenor_path,
        validators=[validate_mp3_upload],
        blank=True, null=True, verbose_name="Audio Ténor"
    )
    audio_basse = models.FileField(
        upload_to=partition_audio_basse_path,
        validators=[validate_mp3_upload],
        blank=True, null=True, verbose_name="Audio Basse"
    )
    audio_instrumental = models.FileField(
        upload_to=partition_audio_instrumental_path,
        validators=[validate_mp3_upload],
        blank=True, null=True, verbose_name="Audio Instrumental"
    )
    audio_mix = models.FileField(
        upload_to=partition_audio_mix_path,
        validators=[validate_mp3_upload],
        blank=True, null=True, verbose_name="Audio Mix"
    )
    mp3_synthetiques = models.BooleanField(
        default=False,
        help_text="MP3 générés automatiquement à partir du fichier MXL"
    )
    audio_channels = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Cache du nombre de canaux audio par champ (ex. "
            "{\"audio_soprano\": 1}). Invalide les requêtes R2 HEAD/GET."
        ),
    )

    # Slug for SEO-friendly URLs
    slug = models.SlugField(max_length=250, blank=True, db_index=True)

    class Meta:
        ordering = ['titre']
        verbose_name = "Partition"
        verbose_name_plural = "Partitions"

    def save(self, *args, **kwargs):
        """Override save to auto-generate title and slug for ordinaire partitions."""
        if not self.titre and self.ordinaire_id and self.partie_messe:
            label = PartieMesse(self.partie_messe).label
            ordinaire_titre = ''
            if self.ordinaire_id:
                try:
                    ordinaire_titre = self.ordinaire.titre
                except Exception:
                    ordinaire_titre = ''
            if ordinaire_titre:
                self.titre = f"{ordinaire_titre} — {label}"
        if not self.slug and self.titre:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    def clean(self):
        """Validation : exclusivité psaume/ordinaire et cohérence de partie_messe."""
        super().clean()
        has_psaume = self.psaume_id is not None
        has_ordinaire = self.ordinaire_id is not None
        if has_psaume and has_ordinaire:
            raise ValidationError("Une partition ne peut pas être liée à la fois à un psaume et à un ordinaire.")
        if has_ordinaire and not self.partie_messe:
            raise ValidationError({"partie_messe": "Une partition d'ordinaire doit préciser la partie de messe."})
        if has_psaume and self.partie_messe:
            raise ValidationError({"partie_messe": "La partie de messe ne s'applique qu'aux partitions d'ordinaire."})

    def get_pdf_filename(self) -> Optional[str]:
        if not self.partition_pdf:
            return None
        return os.path.basename(self.partition_pdf.name)

    def get_audio_field(self, voice_type):
        """Return the FileField value for a given voice type code."""
        field_name = VOICE_FIELD_MAP.get(voice_type)
        if not field_name:
            return None
        return getattr(self, field_name)

    def get_audio_list(self):
        """Return list of dicts for all non-empty audio fields."""
        result = []
        for voice_type, field_name in VOICE_FIELD_MAP.items():
            field_val = getattr(self, field_name)
            if field_val:
                result.append({
                    'id': f"{self.pk}_{voice_type}",
                    'voice_type': voice_type,
                    'label': VOIX_LABELS[voice_type],
                    'url': field_val.url,
                    'download_url': reverse('download_audio', kwargs={
                        'partition_id': self.pk, 'voice_type': voice_type
                    }),
                    'est_synthetique': self.mp3_synthetiques,
                })
        return result

    def get_satb_audios(self):
        """Return dict of voice_type -> FileField for existing SATB voices."""
        result = {}
        for v in SATB_VOICES:
            field_val = getattr(self, VOICE_FIELD_MAP[v])
            if field_val:
                result[v] = field_val
        return result

    def has_audio(self):
        """True if any audio field is populated."""
        return any(
            getattr(self, fname) for fname in VOICE_FIELD_MAP.values()
        )

    @property
    def partie_slug(self):
        """Slug URL d'une partie de messe (ex. 'agnus-dei', 'alleluia')."""
        if self.partie_messe:
            return slugify(PartieMesse(self.partie_messe).label)
        return ''

    def get_absolute_url(self):
        """URL canonique : page de la partie pour un ordinaire, page du psaume sinon."""
        if self.ordinaire_id and self.partie_messe:
            try:
                return reverse('ordinaire_partie_detail',
                    kwargs={'pk': self.ordinaire_id, 'slug': self.ordinaire.slug, 'partie': self.partie_slug})
            except Exception:
                pass
        if self.psaume_id:
            return self.psaume.get_absolute_url()
        return '/'

    @property
    def audio_count(self):
        """Count of non-empty audio fields (excluding mix)."""
        return sum(
            1 for v, fname in VOICE_FIELD_MAP.items()
            if v != 'M' and getattr(self, fname)
        )

    @property
    def is_mix_only(self):
        """True when no SATB/Instrumental voices exist but mix is present."""
        non_mix_fields = [f for v, f in VOICE_FIELD_MAP.items() if v != 'M']
        return (not any(getattr(self, f) for f in non_mix_fields)
                and bool(self.audio_mix))

    def __str__(self):
        comp = f" ({self.compositeur.nom})" if self.compositeur else ""
        return f"{self.titre}{comp}" or f"Partition {self.pk}"


@receiver(post_save, sender=Partition)
@receiver(post_delete, sender=Partition)
def trigger_parent_index_update(sender, instance, **kwargs):
    """Force update of parent Psaume/Ordinaire search index when a partition changes."""
    if instance.psaume_id:
        instance.psaume.save()
    if instance.ordinaire_id:
        instance.ordinaire.save()


@receiver(pre_save, sender=Partition)
def invalidate_audio_channels_on_file_change(sender, instance, **kwargs):
    """Clear cached channel counts for audio fields whose file has changed.

    Avoids serving stale mono/stereo flags after an upload or file replacement.
    Compares the incoming instance's file names against the DB-stored values.
    """
    if not instance.pk:
        return
    try:
        previous = Partition.objects.filter(pk=instance.pk).only(
            *VOICE_FIELD_MAP.values(), 'audio_channels'
        ).first()
    except Partition.DoesNotExist:
        return
    if previous is None:
        return
    cache = dict(instance.audio_channels or {})
    changed = False
    for field_name in VOICE_FIELD_MAP.values():
        new_name = getattr(instance, field_name).name if getattr(instance, field_name) else ''
        old_name = getattr(previous, field_name).name if getattr(previous, field_name) else ''
        if new_name != old_name and field_name in cache:
            cache.pop(field_name, None)
            changed = True
    if changed:
        instance.audio_channels = cache
