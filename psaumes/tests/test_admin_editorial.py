from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.utils import timezone

from psaumes.admin.audio import (
    PartitionAudioGenerationJobAdmin,
    PartitionAudioNormalizationJobAdmin,
    PartitionAudioTempoVariantAdmin,
)
from psaumes.admin.banner import SiteBannerAdmin, SiteBannerAdminForm
from psaumes.admin.moment_liturgique import MomentLiturgiqueAdmin, MomentLiturgiqueAdminForm, MomentLiturgiqueInline
from psaumes.admin.partition import MissingMxlFilter, PartitionAdmin, PartitionAdminForm, PartitionInline, SatbCompletenessFilter
from psaumes.models import (
    Compositeur,
    MomentLiturgique,
    Partition,
    PartitionAudioGenerationJob,
    PartitionAudioNormalizationJob,
    PartitionAudioTempoVariant,
    Psaume,
    SiteBanner,
)


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def request_factory():
    return RequestFactory()


def _request(request_factory, **params):
    request = request_factory.get('/admin/psaumes/partition/', params)
    request.user = SimpleNamespace(has_perm=lambda perm: True)
    return request


@pytest.fixture
def psaume():
    return Psaume.objects.create(nom_psaume='Psaume 23', titre='Le Seigneur est mon berger')


@pytest.fixture
def compositeur():
    return Compositeur.objects.create(nom='Jean Dupont')


@pytest.mark.django_db
def test_partition_admin_search_finds_related_psaume_and_compositeur(admin_site, request_factory, psaume, compositeur):
    partition = Partition.objects.create(
        psaume=psaume,
        compositeur=compositeur,
        titre='Arrangement pastoral',
        refrain='Rien ne saurait me manquer',
        versets='Verts paturages',
    )
    partition_admin = PartitionAdmin(Partition, admin_site)
    request = _request(request_factory)

    by_psaume, _ = partition_admin.get_search_results(request, Partition.objects.all(), 'berger')
    by_compositeur, _ = partition_admin.get_search_results(request, Partition.objects.all(), 'Dupont')
    by_versets, _ = partition_admin.get_search_results(request, Partition.objects.all(), 'paturages')

    assert partition in by_psaume
    assert partition in by_compositeur
    assert partition in by_versets


@pytest.mark.django_db
def test_partition_admin_search_orders_title_psaume_refrain_then_versets(admin_site, request_factory):
    title_psaume = Psaume.objects.create(nom_psaume='Psaume 1', titre='Titre sans mot cle')
    linked_psaume = Psaume.objects.create(nom_psaume='Psaume 2', titre='Le Seigneur guide')
    refrain_psaume = Psaume.objects.create(nom_psaume='Psaume 3', titre='Autre titre')
    versets_psaume = Psaume.objects.create(nom_psaume='Psaume 4', titre='Encore un titre')

    title_match = Partition.objects.create(
        psaume=title_psaume,
        titre='Le Seigneur est ici',
    )
    psaume_match = Partition.objects.create(
        psaume=linked_psaume,
        titre='Arrangement lie',
    )
    refrain_match = Partition.objects.create(
        psaume=refrain_psaume,
        titre='Arrangement refrain',
        refrain='Seigneur, prends pitié',
    )
    versets_match = Partition.objects.create(
        psaume=versets_psaume,
        titre='Arrangement versets',
        versets='Le Seigneur nous parle',
    )

    partition_admin = PartitionAdmin(Partition, admin_site)
    request = _request(request_factory)

    result, use_distinct = partition_admin.get_search_results(
        request,
        Partition.objects.all(),
        'seigneur',
    )

    assert list(result) == [title_match, psaume_match, refrain_match, versets_match]
    assert use_distinct is False


@pytest.mark.django_db
def test_partition_admin_filters_missing_mxl_and_satb_completeness(admin_site, request_factory):
    complete = Partition.objects.create(
        titre='Complet',
        partition_mxl='partitions/mxl/complet.mxl',
        audio_soprano='audios/complet/s.mp3',
        audio_alto='audios/complet/a.mp3',
        audio_tenor='audios/complet/t.mp3',
        audio_basse='audios/complet/b.mp3',
    )
    missing_mxl = Partition.objects.create(titre='Sans MXL')
    partial = Partition.objects.create(
        titre='Partiel',
        partition_mxl='partitions/mxl/partiel.mxl',
        audio_soprano='audios/partiel/s.mp3',
    )
    partition_admin = PartitionAdmin(Partition, admin_site)

    mxl_request = _request(request_factory, mxl_status='missing')
    mxl_filter = MissingMxlFilter(mxl_request, {'mxl_status': ['missing']}, Partition, partition_admin)
    assert list(mxl_filter.queryset(mxl_request, Partition.objects.all())) == [missing_mxl]

    complete_request = _request(request_factory, satb_status='complete')
    complete_filter = SatbCompletenessFilter(
        complete_request,
        {'satb_status': ['complete']},
        Partition,
        partition_admin,
    )
    assert list(complete_filter.queryset(complete_request, Partition.objects.all())) == [complete]

    partial_request = _request(request_factory, satb_status='partial')
    partial_filter = SatbCompletenessFilter(
        partial_request,
        {'satb_status': ['partial']},
        Partition,
        partition_admin,
    )
    assert list(partial_filter.queryset(partial_request, Partition.objects.all())) == [partial]


@pytest.mark.django_db
def test_psaume_admin_inlines_allow_adding_partitions_and_moments(admin_site, request_factory, psaume):
    request = _request(request_factory)
    partition_inline = PartitionInline(Psaume, admin_site)
    moment_inline = MomentLiturgiqueInline(Psaume, admin_site)

    assert partition_inline.extra == 1
    assert partition_inline.has_add_permission(request, psaume) is True
    assert 'partition_pdf' in partition_inline.fieldsets[0][1]['fields']
    assert 'partition_mxl' in partition_inline.fieldsets[0][1]['fields']

    assert moment_inline.extra == 1
    assert moment_inline.has_add_permission(request, psaume) is True
    assert moment_inline.form is MomentLiturgiqueAdminForm
    assert 'type_moment' in moment_inline.fields


@pytest.mark.django_db
def test_moment_admin_search_finds_linked_psaume(admin_site, request_factory, psaume):
    moment = MomentLiturgique.objects.create(
        psaume=psaume,
        temps='ORDINAIRE',
        semaine=3,
        jour=0,
        annee='A',
    )
    Partition.objects.create(
        psaume=psaume,
        titre='Arrangement test',
        refrain='Mot uniquement dans le refrain',
    )
    other_psaume = Psaume.objects.create(nom_psaume='Psaume 42', titre='Comme un cerf assoiffe')
    MomentLiturgique.objects.create(
        psaume=other_psaume,
        temps='ORDINAIRE',
        semaine=4,
        jour=0,
        annee='A',
    )
    moment_admin = MomentLiturgiqueAdmin(MomentLiturgique, admin_site)
    request = _request(request_factory)

    by_nom_psaume, _ = moment_admin.get_search_results(request, MomentLiturgique.objects.all(), 'Psaume 23')
    by_titre, _ = moment_admin.get_search_results(request, MomentLiturgique.objects.all(), 'berger')
    by_liturgical_label, _ = moment_admin.get_search_results(
        request,
        MomentLiturgique.objects.all(),
        'troisieme dimanche',
    )
    by_refrain, _ = moment_admin.get_search_results(
        request,
        MomentLiturgique.objects.all(),
        'uniquement refrain',
    )

    assert moment in by_nom_psaume
    assert moment in by_titre
    assert moment in by_liturgical_label
    assert moment not in by_refrain


@pytest.mark.django_db
def test_moment_admin_search_prioritizes_liturgical_matches_over_linked_psaume(admin_site, request_factory, psaume):
    liturgical = MomentLiturgique.objects.create(nom_fete='Psaume 23')
    linked = MomentLiturgique.objects.create(
        psaume=psaume,
        temps='ORDINAIRE',
        semaine=3,
        jour=0,
        annee='A',
    )

    moment_admin = MomentLiturgiqueAdmin(MomentLiturgique, admin_site)
    request = _request(request_factory)

    results, _ = moment_admin.get_search_results(request, MomentLiturgique.objects.all(), 'Psaume 23')

    assert list(results) == [liturgical, linked]


@pytest.mark.django_db
def test_moment_admin_form_accepts_three_valid_workflows():
    dimanche = MomentLiturgiqueAdminForm(data={
        'type_moment': 'dimanche',
        'temps': 'ORDINAIRE',
        'semaine': '3',
        'jour': '0',
        'annee': 'A',
        'parite': '',
        'nom_fete': '',
    })
    semaine = MomentLiturgiqueAdminForm(data={
        'type_moment': 'semaine',
        'temps': 'ORDINAIRE',
        'semaine': '3',
        'jour': '2',
        'parite': 'P',
        'annee': '',
        'nom_fete': '',
    })
    fete = MomentLiturgiqueAdminForm(data={
        'type_moment': 'fete',
        'temps': '',
        'semaine': '',
        'jour': '',
        'parite': '',
        'annee': 'B',
        'nom_fete': 'Sainte Trinite',
    })

    assert dimanche.is_valid(), dimanche.errors
    assert semaine.is_valid(), semaine.errors
    assert fete.is_valid(), fete.errors


@pytest.mark.django_db
def test_moment_admin_form_rejects_mixed_fete_fields():
    form = MomentLiturgiqueAdminForm(data={
        'type_moment': 'fete',
        'temps': 'PASCAL',
        'semaine': '',
        'jour': '',
        'parite': '',
        'annee': '',
        'nom_fete': 'Ascension',
    })

    assert not form.is_valid()
    assert 'Pour une F' in str(form.errors)


@pytest.mark.django_db
def test_audio_operation_admins_are_read_only(admin_site, request_factory):
    request = _request(request_factory)
    job_admin = PartitionAudioGenerationJobAdmin(PartitionAudioGenerationJob, admin_site)
    normalization_admin = PartitionAudioNormalizationJobAdmin(PartitionAudioNormalizationJob, admin_site)
    variant_admin = PartitionAudioTempoVariantAdmin(PartitionAudioTempoVariant, admin_site)

    for model_admin in (job_admin, normalization_admin, variant_admin):
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
        assert model_admin.has_view_permission(request) is True


@pytest.mark.django_db
def test_partition_admin_form_normalizes_voice_uploads(monkeypatch):
    calls = []
    monkeypatch.setattr(
        'psaumes.admin.partition.normalize_uploaded_partition_audio_fields',
        lambda partition, field_names: calls.append(set(field_names)),
    )
    form = PartitionAdminForm(
        data={'titre': 'Partition'},
        files={
            'audio_soprano': SimpleUploadedFile('s.mp3', b'ID3' + b'\x00' * 2048),
        },
    )

    assert form.is_valid(), form.errors
    form.save(commit=False)
    assert calls
    assert 'audio_soprano' in calls[0]


@pytest.mark.django_db
def test_site_banner_admin_rejects_inverted_dates_and_reports_effective_state(admin_site):
    today = timezone.localdate()
    form = SiteBannerAdminForm(data={
        'text': 'Annonce',
        'active': 'on',
        'start_date': str(today + timedelta(days=2)),
        'end_date': str(today + timedelta(days=1)),
    })
    assert not form.is_valid()
    assert 'date de fin' in str(form.errors).lower()

    banner = SiteBanner.objects.create(text='Visible', active=True)
    banner_admin = SiteBannerAdmin(SiteBanner, admin_site)

    assert 'Visible' in str(banner_admin.effective_status(banner))
