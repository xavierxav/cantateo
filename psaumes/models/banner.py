from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q


class SiteBanner(models.Model):
    text = models.TextField(
        "Texte de la bannière",
        help_text=(
            "Markdown sécurisé autorisé : **gras**, *italique*, liens [texte](/url), "
            "et icônes :info:, :warning:, :music:, :calendar:, :check:. "
            "Le HTML dangereux est supprimé."
        ),
    )
    active = models.BooleanField("Actif", default=False)
    start_date = models.DateField("Date de début", null=True, blank=True)
    end_date = models.DateField("Date de fin", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bannière"
        verbose_name_plural = "Bannières"
        constraints = [
            models.UniqueConstraint(
                fields=['active'],
                condition=Q(active=True),
                name='unique_active_site_banner',
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("La date de fin doit etre posterieure ou egale a la date de debut.")

    def save(self, *args, **kwargs):
        self.clean()
        with transaction.atomic():
            if self.active:
                SiteBanner.objects.filter(active=True).exclude(pk=self.pk).update(active=False)
            super().save(*args, **kwargs)

    def __str__(self):
        prefix = "[ACTIF] " if self.active else ""
        return f"{prefix}{self.text[:50]}..."
