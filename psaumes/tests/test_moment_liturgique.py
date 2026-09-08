"""
Comprehensive tests for MomentLiturgique validation logic.

The MomentLiturgique model has complex validation with three distinct types:
1. FÊTE (Feast): nom_fete required, annee optional (for cyclic feasts); temps, semaine, jour, parite empty
   - Fixed feasts (Noël, Toussaint): nom_fete only
   - Cyclic feasts (Sainte Trinité, Christ-Roi): nom_fete + annee (A/B/C)
2. DIMANCHE (Sunday): temps, semaine, jour=0, annee filled; parite empty
3. SEMAINE (Weekday): temps, semaine, jour (1-6), parite filled; annee empty
"""
import pytest
from django.core.exceptions import ValidationError
from psaumes.models import MomentLiturgique, Psaume, Compositeur


@pytest.fixture
def psaume():
    """Create a test psalm for moments."""
    return Psaume.objects.create(
        nom_psaume="Psaume 23",
        titre="Le Seigneur est mon berger"
    )


@pytest.mark.django_db
class TestMomentLiturgiqueFeteValidation:
    """Tests for FÊTE type validation (fixed and cyclic feasts)."""

    def test_valid_fete_only_nom_fete(self, psaume):
        """Valid fixed FÊTE: only nom_fete filled (e.g., Noël)."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Nativité du Seigneur"
        )
        # Should not raise
        moment.clean()

    def test_valid_fete_with_annee(self, psaume):
        """Valid cyclic FÊTE: nom_fete + annee (e.g., Sainte Trinité année A)."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Sainte Trinité",
            annee="A"
        )
        # Should not raise - cyclic feasts can have annee
        moment.clean()

    def test_valid_fete_all_annee_options(self, psaume):
        """Valid cyclic FÊTE works with all annee choices (A, B, C)."""
        for annee in ['A', 'B', 'C']:
            moment = MomentLiturgique(
                psaume=psaume,
                nom_fete="Christ-Roi",
                annee=annee
            )
            moment.clean()  # Should not raise

    def test_fete_with_temps_should_fail(self, psaume):
        """FÊTE with temps field should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Ascension",
            temps="PASCAL"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Pour une FÊTE" in str(excinfo.value)

    def test_fete_with_semaine_should_fail(self, psaume):
        """FÊTE with semaine field should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Pentecôte",
            semaine=1
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Pour une FÊTE" in str(excinfo.value)

    def test_fete_with_jour_should_fail(self, psaume):
        """FÊTE with jour field should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Toussaint",
            jour=0
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Pour une FÊTE" in str(excinfo.value)

    def test_fete_with_parite_should_fail(self, psaume):
        """FÊTE with parite field should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Assomption",
            parite="P"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Pour une FÊTE" in str(excinfo.value)

    def test_fete_with_all_forbidden_fields_should_fail(self, psaume):
        """FÊTE with temps, semaine, jour, parite should fail (annee allowed)."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Noël",
            temps="NOEL",
            semaine=1,
            jour=0,
            parite="I"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Pour une FÊTE" in str(excinfo.value)

    def test_cyclic_fete_with_forbidden_fields_should_fail(self, psaume):
        """Cyclic FÊTE with annee but also temps/semaine/jour/parite should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            nom_fete="Sainte Trinité",
            annee="B",
            temps="PASCAL"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Pour une FÊTE" in str(excinfo.value)


@pytest.mark.django_db
class TestMomentLiturgiqueDimancheValidation:
    """Tests for DIMANCHE (Sunday) type validation."""

    def test_valid_dimanche_all_required_fields(self, psaume):
        """Valid DIMANCHE: temps, semaine, jour=0, annee filled."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=3,
            jour=0,
            annee="A"
        )
        # Should not raise
        moment.clean()

    def test_valid_dimanche_all_temps_options(self, psaume):
        """Valid DIMANCHE works with all temps choices."""
        temps_options = ['AVENT', 'NOEL', 'ORDINAIRE', 'CAREME', 'SAINT', 'PASCAL']
        for temps in temps_options:
            moment = MomentLiturgique(
                psaume=psaume,
                temps=temps,
                semaine=2,
                jour=0,
                annee="B"
            )
            moment.clean()  # Should not raise

    def test_valid_dimanche_all_annee_options(self, psaume):
        """Valid DIMANCHE works with all annee choices (A, B, C)."""
        for annee in ['A', 'B', 'C']:
            moment = MomentLiturgique(
                psaume=psaume,
                temps="PASCAL",
                semaine=4,
                jour=0,
                annee=annee
            )
            moment.clean()  # Should not raise

    def test_dimanche_missing_temps_should_fail(self, psaume):
        """DIMANCHE without temps should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            semaine=1,
            jour=0,
            annee="A"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "DIMANCHE" in str(excinfo.value)

    def test_dimanche_missing_semaine_should_fail(self, psaume):
        """DIMANCHE without semaine should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="AVENT",
            jour=0,
            annee="C"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "DIMANCHE" in str(excinfo.value)

    def test_dimanche_missing_annee_should_fail(self, psaume):
        """DIMANCHE without annee should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="CAREME",
            semaine=2,
            jour=0
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "DIMANCHE" in str(excinfo.value)

    def test_dimanche_with_parite_should_fail(self, psaume):
        """DIMANCHE with parite field should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=5,
            jour=0,
            annee="B",
            parite="P"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "laisser 'Parité' vide" in str(excinfo.value)

    def test_dimanche_semaine_zero_should_work(self, psaume):
        """DIMANCHE with semaine=0 should work (edge case)."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="NOEL",
            semaine=0,
            jour=0,
            annee="A"
        )
        moment.clean()  # Should not raise

    def test_dimanche_high_semaine_should_work(self, psaume):
        """DIMANCHE with high semaine number should work."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=34,
            jour=0,
            annee="C"
        )
        moment.clean()  # Should not raise


@pytest.mark.django_db
class TestMomentLiturgiqueSemaineValidation:
    """Tests for SEMAINE (Weekday) type validation."""

    def test_valid_semaine_lundi(self, psaume):
        """Valid SEMAINE: Monday with all required fields."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=10,
            jour=1,
            parite="P"
        )
        moment.clean()  # Should not raise

    def test_valid_semaine_all_weekdays(self, psaume):
        """Valid SEMAINE works for all weekdays (1-6)."""
        for jour in range(1, 7):
            moment = MomentLiturgique(
                psaume=psaume,
                temps="CAREME",
                semaine=3,
                jour=jour,
                parite="I"
            )
            moment.clean()  # Should not raise

    def test_valid_semaine_all_parite_options(self, psaume):
        """Valid SEMAINE works with both parite options (P, I)."""
        for parite in ['P', 'I']:
            moment = MomentLiturgique(
                psaume=psaume,
                temps="AVENT",
                semaine=2,
                jour=3,
                parite=parite
            )
            moment.clean()  # Should not raise

    def test_semaine_missing_temps_should_fail(self, psaume):
        """SEMAINE without temps should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            semaine=5,
            jour=2,
            parite="P"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "SEMAINE" in str(excinfo.value)

    def test_semaine_missing_semaine_should_fail(self, psaume):
        """SEMAINE without semaine should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="PASCAL",
            jour=4,
            parite="I"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "SEMAINE" in str(excinfo.value)

    def test_semaine_missing_parite_should_fail(self, psaume):
        """SEMAINE without parite should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=8,
            jour=5
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "SEMAINE" in str(excinfo.value)

    def test_semaine_with_annee_should_fail(self, psaume):
        """SEMAINE with annee field should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="CAREME",
            semaine=4,
            jour=3,
            parite="P",
            annee="A"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "laisser 'Année A/B/C' vide" in str(excinfo.value)

    def test_semaine_zero_value_should_work(self, psaume):
        """SEMAINE with semaine=0 should work (edge case)."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="NOEL",
            semaine=0,
            jour=2,
            parite="I"
        )
        moment.clean()  # Should not raise


@pytest.mark.django_db
class TestMomentLiturgiqueAmbiguousCases:
    """Tests for ambiguous or invalid cases."""

    def test_empty_moment_should_fail(self, psaume):
        """Completely empty moment should fail."""
        moment = MomentLiturgique(psaume=psaume)
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Choisir un type" in str(excinfo.value)

    def test_only_temps_should_fail(self, psaume):
        """Only temps field filled should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="ORDINAIRE"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Choisir un type" in str(excinfo.value)

    def test_only_semaine_should_fail(self, psaume):
        """Only semaine field filled should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            semaine=5
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Choisir un type" in str(excinfo.value)

    def test_temps_and_semaine_only_should_fail(self, psaume):
        """Only temps and semaine filled should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            temps="AVENT",
            semaine=3
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Choisir un type" in str(excinfo.value)

    def test_only_annee_should_fail(self, psaume):
        """Only annee field filled should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            annee="B"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Choisir un type" in str(excinfo.value)

    def test_only_parite_should_fail(self, psaume):
        """Only parite field filled should fail."""
        moment = MomentLiturgique(
            psaume=psaume,
            parite="I"
        )
        with pytest.raises(ValidationError) as excinfo:
            moment.clean()
        assert "Choisir un type" in str(excinfo.value)


@pytest.mark.django_db
class TestMomentLiturgiqueStrMethod:
    """Tests for the __str__ representation method."""

    def test_str_fete_fixed_representation(self, psaume):
        """Fixed FÊTE moments should display as feast name only."""
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Noël"
        )
        assert str(moment) == "Noël"

    def test_str_fete_cyclic_representation(self, psaume):
        """Cyclic FÊTE moments should display feast name with year."""
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Sainte Trinité",
            annee="A"
        )
        assert str(moment) == "Sainte Trinité de l'année A"

    def test_str_dimanche_representation(self, psaume):
        """DIMANCHE moments should display properly formatted."""
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=3,
            jour=0,
            annee="A"
        )
        assert "3ème dimanche" in str(moment)
        assert "Temps Ordinaire" in str(moment)
        assert "l'année A" in str(moment)

    def test_str_semaine_representation(self, psaume):
        """SEMAINE moments should display properly formatted."""
        moment = MomentLiturgique.objects.create(
            psaume=psaume,
            temps="CAREME",
            semaine=2,
            jour=3,
            parite="P"
        )
        result = str(moment)
        assert "Mercredi" in result
        assert "2ème semaine" in result
        assert "du Carême" in result
        assert "paire" in result


@pytest.mark.django_db
class TestMomentLiturgiqueUniquenessConstraints:
    """Tests for database uniqueness constraints."""

    def test_unique_dimanche_constraint(self, psaume):
        """Should not allow duplicate Sunday moments."""
        # Create first Sunday moment
        MomentLiturgique.objects.create(
            psaume=psaume,
            temps="ORDINAIRE",
            semaine=5,
            jour=0,
            annee="A"
        )

        # Create a second psalm for the duplicate
        psaume2 = Psaume.objects.create(nom_psaume="Psaume 24", titre="Test 2")

        # Attempt to create duplicate should raise IntegrityError
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            MomentLiturgique.objects.create(
                psaume=psaume2,
                temps="ORDINAIRE",
                semaine=5,
                jour=0,
                annee="A"
            )

    def test_unique_semaine_constraint(self, psaume):
        """Should not allow duplicate weekday moments."""
        # Create first weekday moment
        MomentLiturgique.objects.create(
            psaume=psaume,
            temps="CAREME",
            semaine=3,
            jour=2,
            parite="P"
        )

        # Create a second psalm for the duplicate
        psaume2 = Psaume.objects.create(nom_psaume="Psaume 25", titre="Test 3")

        # Attempt to create duplicate should raise IntegrityError
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            MomentLiturgique.objects.create(
                psaume=psaume2,
                temps="CAREME",
                semaine=3,
                jour=2,
                parite="P"
            )

    def test_unique_fete_fixed_constraint(self, psaume):
        """Should not allow duplicate fixed feast moments (same nom_fete, no annee)."""
        # Create first fixed feast moment
        MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Pentecôte"
        )

        # Create a second psalm for the duplicate
        psaume2 = Psaume.objects.create(nom_psaume="Psaume 26", titre="Test 4")

        # Attempt to create duplicate should raise IntegrityError
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            MomentLiturgique.objects.create(
                psaume=psaume2,
                nom_fete="Pentecôte"
            )

    def test_unique_fete_cyclic_constraint(self, psaume):
        """Should not allow duplicate cyclic feast moments (same nom_fete + annee)."""
        # Create first cyclic feast moment
        MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Sainte Trinité",
            annee="A"
        )

        # Create a second psalm for the duplicate
        psaume2 = Psaume.objects.create(nom_psaume="Psaume 27", titre="Test 5")

        # Attempt to create duplicate should raise IntegrityError
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            MomentLiturgique.objects.create(
                psaume=psaume2,
                nom_fete="Sainte Trinité",
                annee="A"
            )

    def test_same_fete_different_annee_allowed(self, psaume):
        """Same feast name with different annee should be allowed (cyclic feasts)."""
        MomentLiturgique.objects.create(
            psaume=psaume,
            nom_fete="Christ-Roi",
            annee="A"
        )

        psaume2 = Psaume.objects.create(nom_psaume="Psaume 28", titre="Test 6")

        # Different annee should work
        moment2 = MomentLiturgique.objects.create(
            psaume=psaume2,
            nom_fete="Christ-Roi",
            annee="B"
        )
        assert moment2.pk is not None

    def test_same_temps_semaine_different_jour_allowed(self, psaume):
        """Same temps/semaine with different jour should be allowed."""
        MomentLiturgique.objects.create(
            psaume=psaume,
            temps="CAREME",
            semaine=5,
            jour=2,
            parite="P"
        )

        psaume2 = Psaume.objects.create(nom_psaume="Psaume 29", titre="Test 7")

        # Different jour should work
        moment2 = MomentLiturgique.objects.create(
            psaume=psaume2,
            temps="CAREME",
            semaine=5,
            jour=3,  # Different jour
            parite="P"
        )
        assert moment2.pk is not None
