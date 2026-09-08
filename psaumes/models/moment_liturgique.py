from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .psaume import Psaume

# Mapping numérique → texte ordinal pour recherche (forme texte seulement, numérique déjà dans nom_complet)
ORDINAL_TEXT = {
    1: 'premier première',
    2: 'deuxième', 3: 'troisième', 4: 'quatrième',
    5: 'cinquième', 6: 'sixième', 7: 'septième',
    8: 'huitième', 9: 'neuvième', 10: 'dixième',
    11: 'onzième', 12: 'douzième', 13: 'treizième',
    14: 'quatorzième', 15: 'quinzième', 16: 'seizième',
    17: 'dix-septième', 18: 'dix-huitième', 19: 'dix-neuvième',
    20: 'vingtième', 21: 'vingt-et-unième', 22: 'vingt-deuxième',
    23: 'vingt-troisième', 24: 'vingt-quatrième', 25: 'vingt-cinquième',
    26: 'vingt-sixième', 27: 'vingt-septième', 28: 'vingt-huitième',
    29: 'vingt-neuvième', 30: 'trentième', 31: 'trente-et-unième',
    32: 'trente-deuxième', 33: 'trente-troisième', 34: 'trente-quatrième',
}

class MomentLiturgique(models.Model):
    """
    Moment liturgique où ce chant (psaume ou cantique) est utilisé.

    3 cas possibles :
    - DIMANCHE : remplir temps, semaine, annee. Laisser jour et parite vides.
    - SEMAINE : remplir temps, semaine, jour, parite. Laisser annee vide.
    - FÊTE : remplir nom_fete, et optionnellement annee (A/B/C) pour les fêtes cycliques.
             Laisser temps, semaine, jour et parite vides.
             - Fête fixe (ex: Noël) : nom_fete seul
             - Fête cyclique (ex: Sainte Trinité) : nom_fete + annee
    """
    TEMPS_CHOICES = [
        ('AVENT', "Temps de l'Avent"),
        ('NOEL', 'Temps de Noël'),
        ('ORDINAIRE', 'Temps Ordinaire'),
        ('CAREME', 'Temps de Carême'),
        ('SAINT', 'Semaine Sainte'),
        ('PASCAL', 'Temps Pascal'),
    ]

    JOUR_CHOICES = [
        (0, 'Dimanche'),
        (1, 'Lundi'),
        (2, 'Mardi'),
        (3, 'Mercredi'),
        (4, 'Jeudi'),
        (5, 'Vendredi'),
        (6, 'Samedi'),
    ]

    ANNEE_CHOICES = [
        ('A', 'Année A'),
        ('B', 'Année B'),
        ('C', 'Année C'),
    ]

    PARITE_CHOICES = [
        ('P', 'Année paire'),
        ('I', 'Année impaire'),
    ]

    psaume = models.ForeignKey(
        Psaume,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='moments_liturgiques'
    )

    # Champs communs (semaine et dimanche)
    temps = models.CharField(
        max_length=20,
        choices=TEMPS_CHOICES,
        blank=True,
        help_text="Temps liturgique (vide si fête spéciale)"
    )
    semaine = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Numéro de semaine (vide si fête spéciale)"
    )

    # Jour de la semaine (0=Dimanche, 1-6=Lundi-Samedi)
    jour = models.PositiveSmallIntegerField(
        choices=JOUR_CHOICES,
        null=True,
        blank=True,
        help_text="Jour (Dimanche ou Lundi-Samedi)"
    )
    
    # Pour SEMAINE (Lundi-Samedi) uniquement
    parite = models.CharField(
        max_length=1,
        choices=PARITE_CHOICES,
        blank=True,
        help_text="Année paire/impaire - jours Lundi-Samedi uniquement"
    )

    # Pour DIMANCHE uniquement
    annee = models.CharField(
        max_length=1,
        choices=ANNEE_CHOICES,
        blank=True,
        help_text="Année A/B/C - Dimanche uniquement"
    )

    # Champs FÊTE (nom_fete requis, annee optionnel pour fêtes cycliques)
    nom_fete = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nom de la fête - FÊTE uniquement (ex: Nativité, Ascension, Sainte Trinité...). "
                  "Pour les fêtes cycliques (Sainte Trinité...), ajouter aussi l'année A/B/C."
    )

    # Champ auto-généré pour recherche trigram
    nom_complet_recherche = models.TextField(
        blank=True,
        db_index=True,
        help_text="Auto-généré pour recherche trigram"
    )

    class Meta:
        ordering = ['temps', 'semaine', 'jour']
        verbose_name = "Moment liturgique"
        verbose_name_plural = "Moments liturgiques"
        # Contraintes d'unicité selon le type
        constraints = [
            # Un seul psaume par dimanche (avec année A/B/C)
            models.UniqueConstraint(
                fields=['temps', 'semaine', 'jour', 'annee'],
                condition=models.Q(jour=0) & models.Q(annee__isnull=False) & ~models.Q(annee=''),
                name='unique_dimanche'
            ),
            # Un seul psaume par jour de semaine (lundi-samedi)
            models.UniqueConstraint(
                fields=['temps', 'semaine', 'jour', 'parite'],
                condition=models.Q(jour__gt=0),
                name='unique_semaine'
            ),
            # Un seul psaume par fête (avec année optionnelle pour fêtes cycliques)
            # Fête fixe : nom_fete unique avec annee vide
            # Fête cyclique : (nom_fete, annee) unique
            models.UniqueConstraint(
                fields=['nom_fete', 'annee'],
                condition=~models.Q(nom_fete=''),
                name='unique_fete'
            ),
        ]

    def clean(self):
        """Validation des champs selon le type de moment."""
        super().clean()
        
        is_fete = bool(self.nom_fete)
        is_dimanche = self.jour == 0  # Dimanche sélectionné
        is_semaine = self.jour is not None and self.jour > 0  # Lundi-Samedi
        
        # Cas FÊTE : nom_fete requis, annee optionnel (pour fêtes cycliques)
        # Les autres champs (temps, semaine, jour, parite) doivent être vides
        if is_fete:
            if self.temps or self.semaine is not None or self.jour is not None or self.parite:
                raise ValidationError(
                    "Pour une FÊTE : remplir 'Nom de la fête' et optionnellement 'Année A/B/C' "
                    "(pour les fêtes cycliques comme Sainte Trinité). "
                    "Laisser 'Temps', 'Semaine', 'Jour' et 'Parité' vides."
                )
            return
        
        # Cas DIMANCHE : temps, semaine, jour=Dimanche, annee requis. parite doit être vide.
        if is_dimanche:
            if not self.temps or self.semaine is None or not self.annee:
                raise ValidationError(
                    "Pour un DIMANCHE : remplir 'Temps', 'Semaine', 'Jour=Dimanche' et 'Année A/B/C'."
                )
            if self.parite:
                raise ValidationError(
                    "Pour un DIMANCHE : laisser 'Parité' vide."
                )
            return
        
        # Cas SEMAINE : temps, semaine, jour (Lundi-Samedi), parite requis. annee doit être vide.
        if is_semaine:
            if not self.temps or self.semaine is None or not self.parite:
                raise ValidationError(
                    "Pour un jour de SEMAINE : remplir 'Temps', 'Semaine', 'Jour' et 'Parité'."
                )
            if self.annee:
                raise ValidationError(
                    "Pour un jour de SEMAINE : laisser 'Année A/B/C' vide."
                )
            return
        
        # Aucun type détecté
        raise ValidationError(
            "Choisir un type :\n"
            "• DIMANCHE : Temps + Semaine + Jour=Dimanche + Année A/B/C\n"
            "• SEMAINE : Temps + Semaine + Jour (Lun-Sam) + Parité\n"
            "• FÊTE : Nom de la fête (+ optionnellement Année A/B/C pour fêtes cycliques comme Sainte Trinité)"
        )

    def __str__(self):
        return self.nom_complet

    @property
    def nom_complet(self):
        """Nom complet lisible pour recherche/affichage."""
        if self.nom_fete:
            return f"{self.nom_fete} de l'année {self.annee}" if self.annee else self.nom_fete

        temps_map = {
            'AVENT': "de l'Avent",
            'NOEL': "de Noël",
            'ORDINAIRE': "du Temps Ordinaire",
            'CAREME': "du Carême",
            'SAINT': "de la Semaine Sainte",
            'PASCAL': "du Temps Pascal",
        }
        temps_str = temps_map.get(self.temps, self.get_temps_display())

        if self.jour == 0:  # Dimanche
            ordinal = "1er" if self.semaine == 1 else f"{self.semaine}ème"
            return f"{ordinal} dimanche {temps_str} de l'année {self.annee}"

        if self.jour and self.jour > 0:  # Semaine
            ordinal = "1ère" if self.semaine == 1 else f"{self.semaine}ème"
            parite = "paire" if self.parite == 'P' else "impaire"
            return f"{self.get_jour_display()} de la {ordinal} semaine {temps_str} (année {parite})"

        return f"Moment {self.pk}"


@receiver(pre_save, sender=MomentLiturgique)
def update_moment_nom_complet_recherche(sender, instance, **kwargs):
    """Auto-génère nom_complet_recherche avec ordinaux texte pour trigram."""
    base = instance.nom_complet
    if instance.semaine:
        ordinal = ORDINAL_TEXT.get(instance.semaine, '')
        instance.nom_complet_recherche = f"{ordinal} {base}"
    else:
        instance.nom_complet_recherche = base
