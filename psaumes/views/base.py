import datetime
import logging
import random
import urllib.request
import urllib.parse
import json
from django.shortcuts import render
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .utils import trigger_async_audio_generation
from ..models import MomentLiturgique, Partition
from ..forms import ContactForm
from ..services.liturgie.calendrier_liturgique import get_moment_liturgique_query_params
from ..services.liturgie.fetes import get_fete, get_fete_query_names
from ..services.liturgie.calculs_paques import annee_liturgique
from ..services.aelf import get_aelf_data

logger = logging.getLogger(__name__)

def index(request):
    # Allow `date` query parameter so the index can show any date without redirection
    date_param = request.GET.get('date')
    if date_param:
        try:
            today = datetime.date.fromisoformat(date_param)
        except Exception:
            today = timezone.localdate()
    else:
        today = timezone.localdate()

    # Query local database for psaume matching liturgical moment
    psaume = None
    partition = None
    moment = None
    try:
        moment_params = get_moment_liturgique_query_params(today)
        moment = MomentLiturgique.objects.filter(**moment_params).select_related(
            'psaume'
        ).prefetch_related(
            'psaume__partitions',
            'psaume__partitions__compositeur'
        ).first()

        if moment and moment.psaume:
            psaume = moment.psaume
            partition = psaume.partitions.first()
            if partition:
                trigger_async_audio_generation(partition)

    except Exception as e:
        logger.exception("Error querying liturgical moment for date %s", today)
        moment = None

    # Récupérer les données AELF (infos liturgiques et texte du psaume)
    aelf_data = get_aelf_data(today)
    aelf_info = aelf_data['info']
    aelf_psalm = aelf_data['psalm']

    # Special handling for Holy Saturday and Easter Sunday
    is_samedi_saint = False
    is_paques = False
    vigile_moments = []
    messe_moments = []
    from ..services.liturgie.calculs_paques import date_paques as calc_date_paques
    paques_date = calc_date_paques(today.year)
    
    if today == paques_date - datetime.timedelta(days=1):
        is_samedi_saint = True
    elif today == paques_date:
        is_paques = True
        vigile_moments = MomentLiturgique.objects.filter(
            nom_fete__startswith="Vigile Pascale"
        ).select_related('psaume').order_by('nom_fete')
        messe_moments = MomentLiturgique.objects.filter(
            nom_fete="Pâques"
        ).select_related('psaume')

    # Special handling for Christmas
    is_noel = False
    noel_moments = []
    if today.month == 12 and today.day == 25:
        is_noel = True
        noms_noel = [
            "Noël : Messe de la veille au soir",
            "Noël : Messe de la Nuit",
            "Noël : Messe du jour"
        ]
        moments_db = MomentLiturgique.objects.filter(nom_fete__in=noms_noel).select_related('psaume')
        moment_dict = {m.nom_fete: m for m in moments_db}
        noel_moments = [moment_dict[nom] for nom in noms_noel if nom in moment_dict]

    # Special handling for Saint-Sacrement (Corpus Christi) & Sainte Trinité
    is_saint_sacrement = False
    is_trinite = False
    saint_sacrement_moments = []
    trinite_moments = []
    nom_fete_today = get_fete(today)
    if nom_fete_today == "Saint-Sacrement":
        is_saint_sacrement = True
        annee = annee_liturgique(today)
        noms_ss = get_fete_query_names("Saint-Sacrement") + ["Séquence Saint-Sacrement"]
        moments_db = MomentLiturgique.objects.filter(
            nom_fete__in=noms_ss, annee=annee
        ).select_related('psaume')
        moment_dict = {m.nom_fete: m for m in moments_db}
        saint_sacrement_moments = [moment_dict[n] for n in noms_ss if n in moment_dict]
    elif nom_fete_today == "Sainte Trinité":
        is_trinite = True
        annee = annee_liturgique(today)
        noms_tr = get_fete_query_names("Sainte Trinité") + ["Séquence Sainte Trinité"]
        moments_db = MomentLiturgique.objects.filter(
            nom_fete__in=noms_tr, annee=annee
        ).select_related('psaume')
        moment_dict = {m.nom_fete: m for m in moments_db}
        trinite_moments = [moment_dict[n] for n in noms_tr if n in moment_dict]

    # Check if any non-synthetic audio exists for this partition
    has_non_synthetic_audio = False
    if partition:
        # If any of the audio fields is populated and mp3_synthetiques is False
        has_audio = any([
            partition.audio_soprano, partition.audio_alto, partition.audio_tenor, 
            partition.audio_basse, partition.audio_instrumental, partition.audio_mix
        ])
        has_non_synthetic_audio = has_audio and not partition.mp3_synthetiques

    structured_data = []
    if partition:
        composition = {
            '@context': 'https://schema.org',
            '@type': 'MusicComposition',
            'name': partition.titre,
            'description': psaume.nom_psaume if psaume else '',
            'inLanguage': 'fr-FR',
        }
        if partition.compositeur:
            composition['composer'] = {
                '@type': 'Person',
                'name': str(partition.compositeur),
            }
        structured_data.append(composition)

    return render(request, 'index.html', {
        'psaume': psaume,
        'partition': partition,
        'moment_liturgique': moment,
        'aelf_info': aelf_info,
        'aelf_psalm': aelf_psalm,
        'date': today.isoformat(),
        'has_non_synthetic_audio': has_non_synthetic_audio,
        'is_samedi_saint': is_samedi_saint,
        'is_paques': is_paques,
        'vigile_moments': vigile_moments,
        'messe_moments': messe_moments,
        'date_paques': paques_date,
        'is_noel': is_noel,
        'noel_moments': noel_moments,
        'is_saint_sacrement': is_saint_sacrement,
        'saint_sacrement_moments': saint_sacrement_moments,
        'is_trinite': is_trinite,
        'trinite_moments': trinite_moments,
        'structured_data': structured_data,
    })

def blog(request):
    return render(request, 'blog.html')

def histoire(request):
    return render(request, 'histoire.html')


def confidentialite(request):
    return render(request, 'confidentialite.html')


def mentions_legales(request):
    return render(request, 'mentions_legales.html')

def _verify_turnstile(token, remote_ip):
    """Vérifie le token Turnstile auprès de l'API Cloudflare. Retourne True si valide."""
    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        # Pas de clé configurée → on laisse passer (ex. en dev local)
        return True
    try:
        payload = urllib.parse.urlencode({
            'secret': secret,
            'response': token,
            'remoteip': remote_ip,
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=payload,
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        return result.get('success', False)
    except Exception:
        logger.exception('Turnstile verification error')
        return False


def contact(request):
    sent = False
    error = None
    form = ContactForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        from ..rate_limit import is_rate_limited

        if is_rate_limited(request, 'contact'):
            error = 'Trop de messages envoyés. Veuillez réessayer un peu plus tard.'
            return render(request, 'contact.html', {
                'sent': sent,
                'error': error,
                'form': form,
                'turnstile_site_key': settings.TURNSTILE_SITE_KEY,
            }, status=429)

        data = form.cleaned_data
        # Honeypot : si le champ caché est rempli, c'est un bot → faux succès silencieux
        if data.get('website'):
            logger.warning('Contact honeypot triggered — bot submission ignored')
            sent = True
        else:
            # Vérification Turnstile
            turnstile_token = request.POST.get('cf-turnstile-response', '')
            remote_ip = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')
            if not _verify_turnstile(turnstile_token, remote_ip):
                error = 'Vérification anti-bot échouée. Veuillez réessayer.'
            else:
                try:
                    send_mail(
                        subject=f'Contact Cantateo de {data["nom"]}',
                        message=data['message'] + f"\n\nEmail: {data['email']}",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=settings.CONTACT_EMAIL.split(','),
                    )
                    sent = True
                except Exception:
                    logger.exception('Error sending contact email')
                    error = "Erreur lors de l'envoi. Merci de réessayer."
    elif request.method == 'POST':
        # form invalid
        error = 'Tous les champs sont obligatoires et doivent être valides.'
    return render(request, 'contact.html', {
        'sent': sent,
        'error': error,
        'form': form,
        'turnstile_site_key': settings.TURNSTILE_SITE_KEY,
    })

def ecoute_aleatoire(request):
    partitions = Partition.objects.filter(
        audio_mix__isnull=False,
        psaume__isnull=False,
        mp3_synthetiques=False,
    ).exclude(audio_mix='').select_related('psaume')
    count = partitions.count()
    partition = partitions[random.randrange(count)] if count else None
    if partition:
        return render(request, 'ecoute_aleatoire.html', {
            'psaume': partition.psaume,
            'partition': partition,
            'audio_url': partition.audio_mix.url,
        })
    return render(request, 'ecoute_aleatoire.html', {'psaume': None})
