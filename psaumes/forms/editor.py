from django import forms
from django.forms import formset_factory

from psaumes.models import MomentLiturgique, Partition, SiteBanner
from psaumes.services.audio.channels import normalize_uploaded_partition_audio_fields


EDITOR_WIDGET_CLASS = 'vTextField'


def _with_class(attrs=None):
    attrs = dict(attrs or {})
    attrs['class'] = attrs.get('class', EDITOR_WIDGET_CLASS)
    return attrs


class SimplifiedSiteBannerForm(forms.ModelForm):
    class Meta:
        model = SiteBanner
        fields = ('text', 'active', 'start_date', 'end_date')
        widgets = {
            'text': forms.Textarea(attrs=_with_class({'rows': 5})),
            'start_date': forms.DateInput(attrs=_with_class({'type': 'date'})),
            'end_date': forms.DateInput(attrs=_with_class({'type': 'date'})),
        }


class ExistingMomentSelectionForm(forms.Form):
    moments = forms.ModelMultipleChoiceField(
        queryset=MomentLiturgique.objects.none(),
        required=False,
        label='Moments liturgiques existants',
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['moments'].queryset = MomentLiturgique.objects.select_related('psaume').order_by(
            'nom_fete',
            'temps',
            'semaine',
            'jour',
            'annee',
            'parite',
        )


class MomentCreationForm(forms.Form):
    TYPE_CHOICES = (
        ('', '---'),
        ('dimanche', 'Dimanche'),
        ('semaine', 'Semaine'),
        ('fete', 'Fête'),
    )

    type_moment = forms.ChoiceField(
        choices=TYPE_CHOICES,
        required=False,
        label='Type',
    )
    temps = forms.ChoiceField(
        choices=(('', '---'),) + tuple(MomentLiturgique.TEMPS_CHOICES),
        required=False,
        label='Temps',
    )
    semaine = forms.IntegerField(required=False, min_value=1, label='Semaine')
    jour = forms.ChoiceField(
        choices=(('', '---'),) + tuple(MomentLiturgique.JOUR_CHOICES),
        required=False,
        label='Jour',
    )
    parite = forms.ChoiceField(
        choices=(('', '---'),) + tuple(MomentLiturgique.PARITE_CHOICES),
        required=False,
        label='Parité',
    )
    annee = forms.ChoiceField(
        choices=(('', '---'),) + tuple(MomentLiturgique.ANNEE_CHOICES),
        required=False,
        label='Année',
    )
    nom_fete = forms.CharField(required=False, max_length=200, label='Nom de fête')

    def clean(self):
        cleaned_data = super().clean()
        if not self.has_any_value(cleaned_data):
            cleaned_data['empty'] = True
            return cleaned_data

        type_moment = cleaned_data.get('type_moment')
        if not type_moment:
            raise forms.ValidationError('Choisir un type de moment liturgique.')

        if type_moment == 'dimanche':
            moment = MomentLiturgique(
                temps=cleaned_data.get('temps') or '',
                semaine=cleaned_data.get('semaine'),
                jour=0,
                annee=cleaned_data.get('annee') or '',
                parite='',
                nom_fete='',
            )
        elif type_moment == 'semaine':
            jour = cleaned_data.get('jour')
            moment = MomentLiturgique(
                temps=cleaned_data.get('temps') or '',
                semaine=cleaned_data.get('semaine'),
                jour=int(jour) if str(jour).isdigit() else None,
                parite=cleaned_data.get('parite') or '',
                annee='',
                nom_fete='',
            )
        else:
            moment = MomentLiturgique(
                temps='',
                semaine=None,
                jour=None,
                parite='',
                annee=cleaned_data.get('annee') or '',
                nom_fete=(cleaned_data.get('nom_fete') or '').strip(),
            )

        try:
            moment.clean()
        except Exception as exc:
            raise forms.ValidationError(exc.messages if hasattr(exc, 'messages') else str(exc)) from exc

        cleaned_data['moment'] = moment
        cleaned_data['empty'] = False
        return cleaned_data

    def has_any_value(self, cleaned_data):
        fields = ('type_moment', 'temps', 'semaine', 'jour', 'parite', 'annee', 'nom_fete')
        return any(cleaned_data.get(field) not in (None, '') for field in fields)


MomentCreationFormSet = formset_factory(MomentCreationForm, extra=3, can_delete=False)


class SimplifiedPartitionUploadForm(forms.ModelForm):
    nom_psaume = forms.CharField(
        max_length=250,
        label='Nom du psaume',
        help_text='Ex: Psaume 23 ou Cantique de Daniel',
        widget=forms.TextInput(attrs=_with_class()),
    )

    class Meta:
        model = Partition
        fields = (
            'nom_psaume',
            'titre',
            'partition_pdf',
            'partition_mxl',
            'audio_soprano',
            'audio_alto',
            'audio_tenor',
            'audio_basse',
            'audio_instrumental',
            'audio_mix',
        )
        widgets = {
            'titre': forms.TextInput(attrs=_with_class()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['partition_pdf'].required = True
        self.fields['partition_mxl'].required = False
        for field_name in (
            'audio_soprano',
            'audio_alto',
            'audio_tenor',
            'audio_basse',
            'audio_instrumental',
            'audio_mix',
        ):
            self.fields[field_name].required = False

    def save(self, commit=True):
        partition = super().save(commit=False)
        normalize_uploaded_partition_audio_fields(partition, self.changed_data)
        if commit:
            partition.save()
            self.save_m2m()
        return partition
