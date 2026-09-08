from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify


class Ordinaire(models.Model):
    """Un ordinaire de messe (ensemble des pièces fixes : Kyrie, Gloria, Sanctus, Agnus Dei...)."""

    titre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    compositeur = models.ForeignKey(
        'psaumes.Compositeur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordinaires',
    )
    description = models.TextField(blank=True)

    # Champ auto-généré pour recherche trigram
    nom_complet_recherche = models.TextField(
        blank=True,
        db_index=True,
        help_text="Auto-généré pour recherche trigram (Titre + Compositeur + Partitions)"
    )

    class Meta:
        ordering = ['titre']
        verbose_name = "Ordinaire"
        verbose_name_plural = "Ordinaires"

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        """Auto-génère le slug à partir du titre si vide."""
        if not self.slug:
            self.slug = slugify(self.titre)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return the canonical URL."""
        return reverse('ordinaire_detail', kwargs={'pk': self.pk, 'slug': self.slug})


@receiver(pre_save, sender=Ordinaire)
def update_ordinaire_nom_complet_recherche(sender, instance, **kwargs):
    """Auto-génère nom_complet_recherche (Titre + Compositeur + Titres/Parties des partitions)."""
    from .partition import PartieMesse

    parts = []
    if instance.titre:
        parts.append(str(instance.titre))

    if instance.compositeur_id:
        comp = instance.compositeur
        if comp and comp.nom:
            parts.append(str(comp.nom))

    if instance.pk:
        for p in instance.partitions_messe.only('titre', 'partie_messe', 'refrain', 'versets'):
            if p.partie_messe:
                parts.append(PartieMesse(p.partie_messe).label)
            if p.titre:
                parts.append(str(p.titre))
            if p.refrain:
                parts.append(str(p.refrain))
            if p.versets:
                parts.append(str(p.versets))

    instance.nom_complet_recherche = " - ".join(parts)
