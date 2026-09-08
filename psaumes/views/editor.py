from functools import wraps

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from psaumes.forms.editor import (
    ExistingMomentSelectionForm,
    MomentCreationFormSet,
    SimplifiedPartitionUploadForm,
    SimplifiedSiteBannerForm,
)
from psaumes.models import Compositeur, MomentLiturgique, Partition, Psaume, SiteBanner
from psaumes.tasks import enqueue_partition_omr_generation


SESSION_MOMENT_IDS_KEY = 'simplified_editor_moment_ids'
PARTITION_ALREADY_EXISTS_ERROR = "Ce moment liturgique a déjà une partition, contacter l'administrateur"
MOMENT_ALREADY_EXISTS_MESSAGE = 'Moment liturgique déjà existant sélectionné'


def simplified_editor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect_to_login(request.get_full_path(), reverse('admin:login'))
        if not (request.user.is_superuser or request.user.has_perm('psaumes.use_simplified_editor')):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return staff_member_required(_wrapped, login_url='admin:login')


@simplified_editor_required
def simplified_dashboard(request):
    return render(request, 'editor/dashboard.html')


@simplified_editor_required
def simplified_banner_list(request):
    today = timezone.localdate()
    banners = SiteBanner.objects.order_by('-active', '-updated_at')
    return render(request, 'editor/banner_list.html', {'banners': banners, 'today': today})


@simplified_editor_required
def simplified_banner_create(request):
    return _save_banner(request, None)


@simplified_editor_required
def simplified_banner_update(request, banner_id):
    banner = get_object_or_404(SiteBanner, pk=banner_id)
    return _save_banner(request, banner)


@simplified_editor_required
def simplified_banner_delete(request, banner_id):
    banner = get_object_or_404(SiteBanner, pk=banner_id)
    if request.method == 'POST':
        banner.delete()
        messages.success(request, 'Message du site supprimé.')
        return redirect('simplified_banner_list')
    return render(request, 'editor/banner_confirm_delete.html', {'banner': banner})


def _save_banner(request, banner):
    form = SimplifiedSiteBannerForm(request.POST or None, instance=banner)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if form.cleaned_data.get('active'):
            messages.success(request, 'Message enregistré. Les autres messages actifs ont été désactivés.')
        else:
            messages.success(request, 'Message enregistré.')
        return redirect('simplified_banner_list')
    return render(request, 'editor/banner_form.html', {'form': form, 'banner': banner})


@simplified_editor_required
def simplified_partition_moments(request):
    if request.method == 'POST':
            selection_form = ExistingMomentSelectionForm(request.POST, prefix='selection')
            creation_formset = MomentCreationFormSet(request.POST, prefix='creation')
            if selection_form.is_valid() and creation_formset.is_valid():
                selected_moments = list(selection_form.cleaned_data['moments'])
                new_moments_by_key = {}

                for form in creation_formset:
                    if not form.cleaned_data or form.cleaned_data.get('empty'):
                        continue
                    moment = form.cleaned_data['moment']
                    existing = _find_existing_moment(moment)
                    if existing:
                        selected_moments.append(existing)
                        messages.info(request, MOMENT_ALREADY_EXISTS_MESSAGE)
                    else:
                        new_moments_by_key.setdefault(_moment_key(moment), moment)

                new_moments = list(new_moments_by_key.values())
                selected_moments = _unique_moments(selected_moments)
            blocking_error = _get_moment_selection_error(selected_moments)
            if blocking_error:
                messages.error(request, blocking_error)
            elif not selected_moments and not new_moments:
                messages.error(request, 'Choisir ou créer au moins un moment liturgique.')
            else:
                for moment in new_moments:
                    moment.save()
                    selected_moments.append(moment)
                selected_moments = _unique_moments(selected_moments)
                request.session[SESSION_MOMENT_IDS_KEY] = [moment.pk for moment in selected_moments]
                request.session.modified = True
                return redirect('simplified_partition_files')
    else:
        selection_form = ExistingMomentSelectionForm(prefix='selection')
        creation_formset = MomentCreationFormSet(prefix='creation')

    return render(
        request,
        'editor/partition_moments.html',
        {
            'selection_form': selection_form,
            'creation_formset': creation_formset,
        },
    )


@simplified_editor_required
def simplified_partition_files(request):
    moment_ids = request.session.get(SESSION_MOMENT_IDS_KEY)
    if not moment_ids:
        messages.warning(request, 'Choisir un ou plusieurs moments liturgiques avant de saisir la partition.')
        return redirect('simplified_partition_moments')

    moments = list(MomentLiturgique.objects.filter(pk__in=moment_ids).select_related('psaume'))
    if len(moments) != len(set(moment_ids)):
        messages.error(request, 'Un moment liturgique sélectionné est introuvable.')
        request.session.pop(SESSION_MOMENT_IDS_KEY, None)
        return redirect('simplified_partition_moments')

    if request.method == 'POST':
        form = SimplifiedPartitionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            partition = _create_partition_for_moments(form, moment_ids)
            if partition is None:
                messages.error(request, PARTITION_ALREADY_EXISTS_ERROR)
            else:
                enqueue_partition_omr_generation(partition)
                request.session.pop(SESSION_MOMENT_IDS_KEY, None)
                messages.success(request, 'Partition enregistrée.')
                return redirect('simplified_partition_done', partition_id=partition.pk)
    else:
        form = SimplifiedPartitionUploadForm()

    return render(
        request,
        'editor/partition_files.html',
        {
            'form': form,
            'moments': moments,
        },
    )


@simplified_editor_required
def simplified_partition_done(request, partition_id):
    partition = get_object_or_404(
        Partition.objects.select_related('psaume', 'omr_job'),
        pk=partition_id,
    )
    return render(request, 'editor/partition_done.html', {'partition': partition})


def _create_partition_for_moments(form, moment_ids):
    with transaction.atomic():
        moments = list(
            MomentLiturgique.objects.select_for_update()
            .filter(pk__in=moment_ids)
            .order_by('pk')
        )
        if len(moments) != len(set(moment_ids)):
            return None
        if _get_moment_selection_error(moments):
            return None

        linked_psaume_ids = {moment.psaume_id for moment in moments if moment.psaume_id}
        data = form.cleaned_data
        psaume_type = 'cantique' if data['nom_psaume'].strip().lower().startswith('cantique') else 'psaume'

        if linked_psaume_ids:
            psaume = Psaume.objects.select_for_update().get(pk=linked_psaume_ids.pop())
            psaume.psaume_or_cantique = psaume_type
            psaume.nom_psaume = data['nom_psaume']
            psaume.titre = data['titre']
            psaume.save()
        else:
            psaume = Psaume.objects.create(
                psaume_or_cantique=psaume_type,
                nom_psaume=data['nom_psaume'],
                titre=data['titre'],
            )

        compositeur, _ = Compositeur.objects.get_or_create(nom='Fonsalas')
        partition = form.save(commit=False)
        partition.psaume = psaume
        partition.compositeur = compositeur
        partition.titre = data['titre']
        partition.mp3_synthetiques = False
        partition.save()

        for moment in moments:
            if moment.psaume_id != psaume.pk:
                moment.psaume = psaume
                moment.save()

    return partition


def _unique_moments(moments):
    seen = set()
    unique = []
    for moment in moments:
        if moment.pk and moment.pk not in seen:
            unique.append(moment)
            seen.add(moment.pk)
    return unique


def _get_moment_selection_error(moments):
    linked_psaume_ids = set()
    for moment in moments:
        if moment.psaume_id:
            linked_psaume_ids.add(moment.psaume_id)
            if moment.psaume.partitions.exists():
                return PARTITION_ALREADY_EXISTS_ERROR
    if len(linked_psaume_ids) > 1:
        return "Ces moments liturgiques sont liés à plusieurs psaumes, contacter l'administrateur"
    return None


def _find_existing_moment(moment):
    if moment.nom_fete:
        return MomentLiturgique.objects.filter(nom_fete=moment.nom_fete, annee=moment.annee).first()
    if moment.jour == 0:
        return MomentLiturgique.objects.filter(
            temps=moment.temps,
            semaine=moment.semaine,
            jour=0,
            annee=moment.annee,
        ).first()
    return MomentLiturgique.objects.filter(
        temps=moment.temps,
        semaine=moment.semaine,
        jour=moment.jour,
        parite=moment.parite,
    ).first()


def _moment_key(moment):
    if moment.nom_fete:
        return ('fete', moment.nom_fete, moment.annee)
    if moment.jour == 0:
        return ('dimanche', moment.temps, moment.semaine, moment.annee)
    return ('semaine', moment.temps, moment.semaine, moment.jour, moment.parite)
