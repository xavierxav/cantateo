import html

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from psaumes.models import Compositeur, MomentLiturgique, Partition, Psaume, SiteBanner
from psaumes.forms.editor import SimplifiedPartitionUploadForm
from psaumes.views.editor import MOMENT_ALREADY_EXISTS_MESSAGE, PARTITION_ALREADY_EXISTS_ERROR


def _user(username, *, is_staff=True, with_permission=False):
    user = get_user_model().objects.create_user(
        username=username,
        password='secret',
        is_staff=is_staff,
    )
    if with_permission:
        user.user_permissions.add(Permission.objects.get(codename='use_simplified_editor'))
    return user


def _use_local_file_storage(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
    storages._storages = {}


def _valid_pdf(name='partition.pdf'):
    return SimpleUploadedFile(name, b'%PDF-' + b'\x00' * 128, content_type='application/pdf')


def _invalid_pdf():
    return SimpleUploadedFile('partition.pdf', b'not a pdf', content_type='application/pdf')


def _moment_formset_payload(**first_form):
    payload = {
        'creation-TOTAL_FORMS': '3',
        'creation-INITIAL_FORMS': '0',
        'creation-MIN_NUM_FORMS': '0',
        'creation-MAX_NUM_FORMS': '1000',
    }
    for index in range(3):
        for field in ('type_moment', 'temps', 'semaine', 'jour', 'parite', 'annee', 'nom_fete'):
            payload[f'creation-{index}-{field}'] = ''
    for field, value in first_form.items():
        payload[f'creation-0-{field}'] = value
    return payload


@pytest.fixture
def editor_user(db):
    return _user('contributor', with_permission=True)


@pytest.mark.django_db
def test_simplified_editor_requires_admin_login_and_permission(client):
    response = client.get(reverse('simplified_dashboard'))
    assert response.status_code == 302
    assert '/admin/login/' in response['Location']

    staff_user = _user('staff-without-perm')
    client.force_login(staff_user)
    response = client.get(reverse('simplified_dashboard'))
    assert response.status_code == 403

    allowed_user = _user('staff-with-perm', with_permission=True)
    client.force_login(allowed_user)
    response = client.get(reverse('simplified_dashboard'))
    assert response.status_code == 200
    assert b'Messages du site' in response.content


@pytest.mark.django_db
def test_site_banner_enforces_single_active_banner():
    first = SiteBanner.objects.create(text='Premier', active=True)
    second = SiteBanner.objects.create(text='Deuxieme', active=True)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.active is False
    assert second.active is True

    with pytest.raises(IntegrityError), transaction.atomic():
        SiteBanner.objects.bulk_create([
            SiteBanner(text='A', active=True),
            SiteBanner(text='B', active=True),
        ])


@pytest.mark.django_db
def test_simplified_banner_form_rejects_inverted_dates(client, editor_user):
    client.force_login(editor_user)

    response = client.post(reverse('simplified_banner_create'), {
        'text': 'Message',
        'active': 'on',
        'start_date': '2026-05-02',
        'end_date': '2026-05-01',
    })

    assert response.status_code == 200
    assert SiteBanner.objects.count() == 0
    assert 'date de fin' in response.content.decode().lower()


@pytest.mark.django_db
def test_existing_moment_with_partition_blocks_step_one(client, editor_user):
    client.force_login(editor_user)
    psaume = Psaume.objects.create(nom_psaume='Psaume 23', titre='Berger')
    Partition.objects.create(psaume=psaume, titre='Berger')
    moment = MomentLiturgique.objects.create(
        psaume=psaume,
        temps='ORDINAIRE',
        semaine=3,
        jour=0,
        annee='A',
    )
    payload = {'selection-moments': [str(moment.pk)]}
    payload.update(_moment_formset_payload())

    response = client.post(reverse('simplified_partition_moments'), payload, follow=True)

    assert response.status_code == 200
    assert PARTITION_ALREADY_EXISTS_ERROR in html.unescape(response.content.decode())
    assert 'simplified_editor_moment_ids' not in client.session


@pytest.mark.django_db
def test_moment_selection_uses_searchable_checkboxes(client, editor_user):
    client.force_login(editor_user)
    MomentLiturgique.objects.create(nom_fete='Ascension')

    response = client.get(reverse('simplified_partition_moments'))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-moment-search' in content
    assert 'data-moment-picker' in content
    assert 'type="checkbox"' in content
    assert 'name="selection-moments"' in content
    assert 'simplified_moment_picker.js' in content


@pytest.mark.django_db
def test_creating_existing_moment_selects_it(client, editor_user):
    client.force_login(editor_user)
    moment = MomentLiturgique.objects.create(
        temps='ORDINAIRE',
        semaine=3,
        jour=0,
        annee='A',
    )
    payload = {'selection-moments': []}
    payload.update(_moment_formset_payload(
        type_moment='dimanche',
        temps='ORDINAIRE',
        semaine='3',
        annee='A',
    ))

    response = client.post(reverse('simplified_partition_moments'), payload, follow=True)

    assert response.status_code == 200
    assert MOMENT_ALREADY_EXISTS_MESSAGE in html.unescape(response.content.decode())
    assert client.session['simplified_editor_moment_ids'] == [moment.pk]


@pytest.mark.django_db
def test_simplified_partition_workflow_creates_one_psaume_partition_for_multiple_moments(
    client,
    editor_user,
    settings,
    tmp_path,
):
    _use_local_file_storage(settings, tmp_path)
    client.force_login(editor_user)
    existing = MomentLiturgique.objects.create(
        nom_fete='Sainte Trinite',
        annee='A',
    )
    payload = {'selection-moments': [str(existing.pk)]}
    payload.update(_moment_formset_payload(
        type_moment='semaine',
        temps='ORDINAIRE',
        semaine='4',
        jour='2',
        parite='P',
    ))
    response = client.post(reverse('simplified_partition_moments'), payload)
    assert response.status_code == 302

    response = client.post(
        reverse('simplified_partition_files'),
        {
            'nom_psaume': 'Psaume 23',
            'titre': 'Le Seigneur est mon berger',
            'partition_pdf': _valid_pdf(),
        },
    )

    assert response.status_code == 302
    partition = Partition.objects.select_related('psaume', 'compositeur').get()
    assert partition.psaume.nom_psaume == 'Psaume 23'
    assert partition.titre == 'Le Seigneur est mon berger'
    assert partition.compositeur.nom == 'Fonsalas'
    assert partition.mp3_synthetiques is False
    assert Compositeur.objects.filter(nom='Fonsalas').count() == 1
    assert Psaume.objects.count() == 1
    assert set(
        MomentLiturgique.objects
        .exclude(nom_fete__startswith='Séquence')
        .values_list('psaume_id', flat=True)
    ) == {partition.psaume_id}


@pytest.mark.django_db
def test_step_two_validation_failure_creates_no_psaume_or_partition(client, editor_user):
    client.force_login(editor_user)
    moment = MomentLiturgique.objects.create(nom_fete='Ascension')
    session = client.session
    session['simplified_editor_moment_ids'] = [moment.pk]
    session.save()

    response = client.post(reverse('simplified_partition_files'), {
        'nom_psaume': 'Psaume 24',
        'titre': 'Au Seigneur le monde',
    })

    assert response.status_code == 200
    assert Psaume.objects.count() == 0
    assert Partition.objects.count() == 0
    moment.refresh_from_db()
    assert moment.psaume is None


@pytest.mark.django_db
def test_step_two_rejects_invalid_pdf(client, editor_user, settings, tmp_path):
    _use_local_file_storage(settings, tmp_path)
    client.force_login(editor_user)
    moment = MomentLiturgique.objects.create(nom_fete='Toussaint')
    session = client.session
    session['simplified_editor_moment_ids'] = [moment.pk]
    session.save()

    response = client.post(
        reverse('simplified_partition_files'),
        {
            'nom_psaume': 'Psaume 24',
            'titre': 'Au Seigneur le monde',
            'partition_pdf': _invalid_pdf(),
        },
    )

    assert response.status_code == 200
    assert 'PDF valide' in response.content.decode()
    assert Psaume.objects.count() == 0


@pytest.mark.django_db
def test_simplified_partition_form_normalizes_voice_uploads_but_not_mix(monkeypatch):
    calls = []

    monkeypatch.setattr(
        'psaumes.forms.editor.normalize_uploaded_partition_audio_fields',
        lambda partition, field_names: calls.append(set(field_names)),
    )
    form = SimplifiedPartitionUploadForm(
        data={
            'nom_psaume': 'Psaume 23',
            'titre': 'Berger',
        },
        files={
            'partition_pdf': _valid_pdf(),
            'audio_soprano': SimpleUploadedFile('s.mp3', b'ID3' + b'\x00' * 2048),
            'audio_mix': SimpleUploadedFile('mix.mp3', b'ID3' + b'\x00' * 2048),
        },
    )

    assert form.is_valid(), form.errors
    form.save(commit=False)

    assert calls
    assert 'audio_soprano' in calls[0]
    assert 'audio_mix' in calls[0]
    assert Partition.objects.count() == 0


@pytest.mark.django_db
def test_step_two_without_session_redirects_to_step_one(client, editor_user):
    client.force_login(editor_user)

    response = client.get(reverse('simplified_partition_files'))

    assert response.status_code == 302
    assert response['Location'] == reverse('simplified_partition_moments')


@pytest.mark.django_db
def test_admin_index_shows_simplified_partition_quick_link_for_authorized_staff(client):
    user = _user('admin-authorized', with_permission=True)
    user.is_staff = True
    user.save()
    client.force_login(user)

    response = client.get(reverse('admin:index'))
    content = response.content.decode()
    expected_url = reverse('simplified_partition_moments')

    assert response.status_code == 200
    assert 'Nouvelle partition (saisie simplifiée)' in content
    assert expected_url in content


@pytest.mark.django_db
def test_admin_index_hides_simplified_partition_quick_link_for_unauthorized_staff(client):
    user = _user('admin-unauthorized')
    user.is_staff = True
    user.save()
    client.force_login(user)

    response = client.get(reverse('admin:index'))
    content = response.content.decode()
    expected_url = reverse('simplified_partition_moments')

    assert response.status_code == 200
    assert 'Nouvelle partition (saisie simplifiée)' not in content
    assert expected_url not in content
