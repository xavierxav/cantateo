import pytest
from django.urls import reverse

from psaumes.models import Ordinaire, Partition, PartieMesse


@pytest.mark.django_db
def test_ordinaire_list_and_detail_smoke(client):
    ordinaire = Ordinaire.objects.create(titre="Messe de test orchestrateur")
    Partition.objects.create(
        ordinaire=ordinaire,
        partie_messe=PartieMesse.SANCTUS,
        titre="Messe de test orchestrateur — Sanctus",
    )
    Partition.objects.create(
        ordinaire=ordinaire,
        partie_messe=PartieMesse.KYRIE,
        titre="Messe de test orchestrateur — Kyrie",
    )

    r = client.get("/ordinaires-de-messe/")
    assert r.status_code == 200
    body = r.content.decode("utf-8", "ignore")
    assert "Ordinaires de messe" in body
    assert "Messe de test orchestrateur" in body

    r2 = client.get(ordinaire.get_absolute_url())
    assert r2.status_code == 200
    body2 = r2.content.decode("utf-8", "ignore")
    assert "Kyrie" in body2
    assert "Sanctus" in body2
    assert body2.index("Kyrie") < body2.index("Sanctus")

    bad = client.get(
        f"/ordinaires-de-messe/{ordinaire.pk}-mauvais-slug/", HTTP_HOST="localhost"
    )
    assert bad.status_code in (301, 308)


@pytest.mark.django_db
def test_ordinaire_partie_detail_and_slug_redirect(client):
    o = Ordinaire.objects.create(titre="Messe test partie")
    p = Partition.objects.create(ordinaire=o, partie_messe=PartieMesse.KYRIE, titre="Messe test partie — Kyrie")
    url = reverse('ordinaire_partie_detail', kwargs={'pk': o.pk, 'slug': o.slug, 'partie': p.partie_slug})
    r = client.get(url); assert r.status_code == 200
    assert 'Kyrie' in r.content.decode('utf-8', 'ignore')
    bad = client.get(reverse('ordinaire_partie_detail', kwargs={'pk': o.pk, 'slug': 'mauvais', 'partie': p.partie_slug}))
    assert bad.status_code in (301, 308)
    missing = client.get(reverse('ordinaire_partie_detail', kwargs={'pk': o.pk, 'slug': o.slug, 'partie': 'inconnu'}))
    assert missing.status_code == 404


@pytest.mark.django_db
def test_ordinaire_partition_auto_named_when_titre_blank():
    """A partition with no titre gets 'Messe... — <Partie>' automatically."""
    o = Ordinaire.objects.create(titre="Messe du Bienheureux Carlo Acutis")
    p = Partition.objects.create(
        ordinaire=o,
        partie_messe=PartieMesse.AGNUS_DEI,
        titre="",
    )
    p.refresh_from_db()
    assert p.titre == "Messe du Bienheureux Carlo Acutis — Agnus Dei"
    assert p.slug == "messe-du-bienheureux-carlo-acutis-agnus-dei"


@pytest.mark.django_db
def test_ordinaire_partition_auto_name_all_parties():
    """Auto-naming works for every PartieMesse choice."""
    o = Ordinaire.objects.create(titre="Messe test")
    for code, label in PartieMesse.choices:
        p = Partition.objects.create(
            ordinaire=o,
            partie_messe=code,
            titre="",
        )
        p.refresh_from_db()
        assert p.titre == f"Messe test — {label}", f"Failed for {code}"


@pytest.mark.django_db
def test_ordinaire_partition_keeps_explicit_titre():
    """An explicitly set titre is never overwritten."""
    o = Ordinaire.objects.create(titre="Messe du Bienheureux Carlo Acutis")
    p = Partition.objects.create(
        ordinaire=o,
        partie_messe=PartieMesse.AGNUS_DEI,
        titre="Mon Agnus personnalisé",
    )
    p.refresh_from_db()
    assert p.titre == "Mon Agnus personnalisé"


@pytest.mark.django_db
def test_psaume_partition_not_auto_named():
    """Auto-naming only applies to ordinaire partitions, not psaume partitions."""
    from psaumes.models import Psaume
    psaume = Psaume.objects.create(nom_psaume="Psaume 23", titre="Le Seigneur est mon berger")
    p = Partition.objects.create(
        psaume=psaume,
        titre="",
    )
    p.refresh_from_db()
    assert p.titre == ""
