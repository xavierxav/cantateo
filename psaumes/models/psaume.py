from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify

class Psaume(models.Model):
    """
    Un psaume ou cantique liturgique (entité liturgique).
    """
    TYPE_CHOICES = [
        ('psaume', 'Psaume'),
        ('cantique', 'Cantique'),
    ]

    psaume_or_cantique = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='psaume'
    )
    nom_psaume = models.CharField(
        max_length=250,
        db_index=True,
        null=True,
        blank=True,
        help_text="Ex: 'Psaume 23' ou 'Cantique AT 41'"
    )
    titre = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=250, blank=True, db_index=True)

    # Champ auto-généré pour recherche trigram
    nom_complet_recherche = models.TextField(
        blank=True,
        db_index=True,
        help_text="Auto-généré pour recherche trigram (Titre + Refrain)"
    )

    class Meta:
        ordering = ['nom_psaume']
        verbose_name = "Psaume/Cantique"
        verbose_name_plural = "Psaumes et Cantiques"
        permissions = [
            ('use_simplified_editor', 'Peut utiliser la saisie simplifiée Cantateo'),
        ]

    def save(self, *args, **kwargs):
        """Override save to auto-generate slug."""
        if not self.slug:
            base = self.titre or self.nom_psaume or "psaume"
            self.slug = slugify(base)
        
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return the canonical URL."""
        return reverse('psaume_detail', kwargs={
            'pk': self.pk,
            'slug': self.slug or 'psaume'
        })

    def __str__(self):
        return self.nom_psaume or self.titre or f"Psaume {self.pk or ''}".strip()

    @property
    def nom_complet(self):
        """Nom complet pour affichage: Psaume n - titre."""
        if self.titre:
            return f"{self.nom_psaume} - {self.titre}"
        return self.nom_psaume


@receiver(pre_save, sender=Psaume)
def update_psaume_nom_complet_recherche(sender, instance, **kwargs):
    """Auto-génère nom_complet_recherche (Nom, Titre + Refrains des partitions)."""
    parts = []
    if instance.nom_psaume:
        parts.append(str(instance.nom_psaume))
    if instance.titre:
        parts.append(str(instance.titre))
    
    if instance.pk:
        refrains = list(instance.partitions.values_list('refrain', flat=True))
        for r in refrains:
            if r and r not in parts:
                parts.append(str(r))
    
    instance.nom_complet_recherche = " - ".join(parts)
