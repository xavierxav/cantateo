from django.db import models

class Compositeur(models.Model):
    """
    Compositeur d'arrangements de psaumes et cantiques.
    """
    nom = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['nom']
        verbose_name = "Compositeur"
        verbose_name_plural = "Compositeurs"

    def __str__(self):
        return self.nom
