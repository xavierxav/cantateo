from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.test import override_settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from psaumes.models import Partition, Psaume


def test_main_css_keeps_imports_before_style_rules():
    css_path = Path('static/css/main.css')
    css = css_path.read_text(encoding='utf-8')

    in_block_comment = False
    seen_style_rule = False

    for raw_line in css.splitlines():
        line = raw_line.strip()

        if in_block_comment:
            if '*/' in line:
                line = line.split('*/', 1)[1].strip()
                in_block_comment = False
            else:
                continue

        while line.startswith('/*'):
            if '*/' not in line:
                in_block_comment = True
                line = ''
                break
            line = line.split('*/', 1)[1].strip()

        if not line or line.startswith('//'):
            continue

        if line.startswith('@import'):
            assert not seen_style_rule, '@import rules must stay before CSS rules in main.css'
            continue

        seen_style_rule = True


def test_mobile_search_dropdown_stays_anchored_to_search_shell():
    css = Path('static/css/components/search.css').read_text(encoding='utf-8')

    assert '.navbar-search-shell' in css
    assert 'position: fixed' not in css
    assert 'max-height: min(50vh, 24rem)' in css


def test_audio_controls_support_apple_buttons_and_non_apple_slider():
    controls = Path('static/js/audio-player/controls.js').read_text(encoding='utf-8')
    ui = Path('static/js/audio-player/ui.js').read_text(encoding='utf-8')

    assert 'speed-slider-shell-' in controls
    assert 'apple-speed-controls-' in controls
    assert 'control.dataset.speedValue' in controls
    assert 'USE_APPLE_TEMPO_VARIANTS' in controls
    assert 'aria-pressed' in ui


class FrontendTemplateTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/')

    def test_base_uses_local_vendor_assets_and_combobox_markup(self):
        with patch('psaumes.context_processors.banner', return_value={'site_banner': None}):
            html = render_to_string(
                'base.html',
                {
                    'site_url': 'https://cantateo.test',
                    'site_banner': None,
                },
                request=self.request,
            )
        self.assertIn('static/vendor/bootstrap/bootstrap.min.css', html)
        self.assertIn('static/vendor/bootstrap/bootstrap.bundle.min.js', html)
        self.assertIn('static/vendor/htmx/htmx.min.js', html)
        self.assertIn('static/vendor/flatpickr/flatpickr.min.css', html)
        self.assertNotIn('cdn.jsdelivr.net', html)
        self.assertNotIn('unpkg.com', html)
        self.assertNotIn('cdnjs.cloudflare.com', html)
        self.assertNotIn('fonts.googleapis.com', html)
        self.assertIn('navbar-search-shell', html)
        self.assertIn('role="combobox"', html)
        self.assertIn('aria-controls="autocomplete-dropdown"', html)
        self.assertIn('skip-link visually-hidden-focusable', html)

    def test_liturgical_indicator_uses_non_input_color_dot(self):
        html = render_to_string(
            'components/liturgical_indicators.html',
            {
                'aelf_info': {
                    'couleur': 'blanc',
                    'ligne1': '3ème Dimanche de Pâques',
                    'annee': 'A',
                },
            },
        )

        self.assertIn('liturgical-color-dot', html)
        self.assertNotIn('type="checkbox"', html)

    def test_base_renders_sanitized_banner_rich_text(self):
        banner = SimpleNamespace(
            text=':info: **Important**\n<script>alert(1)</script>\n[Voir](/contact/)',
            updated_at=timezone.now(),
        )
        html = render_to_string(
            'base.html',
            {
                'site_url': 'https://cantateo.test',
                'site_banner': banner,
            },
            request=self.request,
        )
        self.assertIn('bi-info-circle-fill', html)
        self.assertIn('<strong>Important</strong>', html)
        self.assertIn('<a href="/contact/">Voir</a>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_autocomplete_fragment_has_listbox_options(self):
        html = render_to_string(
            '_autocomplete_results.html',
            {
                'results': [
                    {
                        'title': 'Psaume 150 - Louez le Seigneur',
                        'subtitle': 'Carême',
                        'type': 'psaume',
                        'url': '/psaumes/1-louez-le-seigneur/',
                    }
                ],
                'query': '150',
            },
        )
        self.assertIn('aria-label="Suggestions de recherche"', html)
        self.assertIn('data-autocomplete-option="true"', html)
        self.assertIn('role="option"', html)
        self.assertIn('aria-selected="false"', html)

    def test_audio_player_has_accessible_controls(self):
        partition = SimpleNamespace(
            id=1,
            partition_mxl=True,
            audio_count=1,
            get_audio_list=lambda: [
                {
                    'id': '1_S',
                    'voice_type': 'S',
                    'label': 'Soprano',
                    'url': '/media/soprano.mp3',
                    'download_url': '/download/audio/1/S/',
                    'est_synthetique': True,
                },
                {
                    'id': '1_M',
                    'voice_type': 'M',
                    'label': 'Mix',
                    'url': '/media/mix.mp3',
                    'download_url': '/download/audio/1/M/',
                    'est_synthetique': True,
                },
            ],
        )
        html = render_to_string(
            'components/audio_player.html',
            {
                'partition': partition,
                'has_non_synthetic_audio': False,
            },
        )
        self.assertIn("aria-label=\"Lire l'audio\"", html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('aria-label="Télécharger le mix"', html)
        self.assertIn('aria-label="Couper le son de Soprano"', html)
        self.assertIn('data-voice-label="Soprano"', html)
        self.assertIn('audio-unsupported-', html)
        self.assertIn('tempo-status-1', html)
        self.assertIn('speed-slider-shell-1', html)
        self.assertIn('apple-speed-controls-1', html)
        self.assertIn('data-speed-value="0.5"', html)
        self.assertIn('data-speed-value="1.5"', html)

    def test_audio_player_mix_only_includes_mix_in_registry_and_controls(self):
        partition = SimpleNamespace(
            id=1,
            partition_mxl=True,
            audio_count=0,
            is_mix_only=True,
            get_audio_list=lambda: [
                {
                    'id': '1_M',
                    'voice_type': 'M',
                    'label': 'Mix',
                    'url': '/media/mix.mp3',
                    'download_url': '/download/audio/1/M/',
                    'est_synthetique': True,
                },
            ],
        )
        html = render_to_string(
            'components/audio_player.html',
            {
                'partition': partition,
                'has_non_synthetic_audio': False,
            },
        )
        self.assertIn('data-audio-count="1"', html)
        self.assertIn('data-mix-only="true"', html)
        self.assertIn('id="audio-1_M"', html)
        self.assertIn('data-voice-type="M"', html)
        self.assertIn('data-voice-label="Mix"', html)
        self.assertIn('aria-label="Couper le son de Mix"', html)

    def test_audio_player_satb_with_mix_excludes_mix_from_registry_and_controls(self):
        partition = SimpleNamespace(
            id=1,
            partition_mxl=True,
            audio_count=4,
            is_mix_only=False,
            get_audio_list=lambda: [
                {
                    'id': '1_S',
                    'voice_type': 'S',
                    'label': 'Soprano',
                    'url': '/media/soprano.mp3',
                    'download_url': '/download/audio/1/S/',
                    'est_synthetique': True,
                },
                {
                    'id': '1_M',
                    'voice_type': 'M',
                    'label': 'Mix',
                    'url': '/media/mix.mp3',
                    'download_url': '/download/audio/1/M/',
                    'est_synthetique': True,
                },
            ],
        )
        html = render_to_string(
            'components/audio_player.html',
            {
                'partition': partition,
                'has_non_synthetic_audio': False,
            },
        )
        self.assertIn('data-mix-only="false"', html)
        self.assertIn('data-audio-count="4"', html)
        self.assertIn('id="audio-1_S"', html)
        self.assertNotIn('id="audio-1_M"', html)
        self.assertIn('data-voice-label="Soprano"', html)
        self.assertNotIn('data-voice-label="Mix"', html)
        self.assertIn('aria-label="Couper le son de Soprano"', html)
        self.assertNotIn('aria-label="Couper le son de Mix"', html)
        self.assertIn('aria-label="Télécharger le mix"', html)

    def test_pdf_viewer_has_accessible_controls(self):
        partition = SimpleNamespace(
            id=1,
            partition_pdf=True,
            titre='Partition test',
        )
        html = render_to_string(
            'components/pdf_viewer.html',
            {
                'partition': partition,
                'hide_pdf_toggle': False,
            },
        )
        self.assertIn('aria-label="Afficher la partition"', html)
        self.assertIn('aria-label="Télécharger la partition"', html)
        self.assertIn('aria-label="Page suivante"', html)
        self.assertIn('data-auto-open="true"', html)

    def test_psaume_detail_renders_pdf_viewer_without_extra_auto_render_script(self):
        pdf_file = SimpleUploadedFile(
            'partition.pdf',
            b'%PDF-' + b'\x00' * 128,
            content_type='application/pdf',
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            psaume = Psaume.objects.create(nom_psaume='Psaume 23', titre='Berger')
            partition = Partition.objects.create(
                psaume=psaume,
                titre='Partition test',
                partition_pdf=pdf_file,
            )

            with patch('psaumes.views.details.trigger_async_audio_generation'):
                response = self.client.get(reverse('psaume_detail', kwargs={
                    'pk': psaume.pk,
                    'slug': psaume.slug,
                }))

        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'id="pdf-viewer-{partition.id}"', html)
        self.assertIn('data-auto-open="true"', html)
        self.assertNotIn('pdf-auto-render.js', html)
