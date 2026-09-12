from django.template import Context, Template

from psaumes.templatetags.banner_tags import banner_rich_text


def render_banner(value):
    template = Template('{% load banner_tags %}{{ value|banner_rich_text }}')
    return template.render(Context({'value': value}))


def test_banner_rich_text_supports_safe_markdown_and_icons():
    html = render_banner(':info: **Important** *messe* [Voir](/psaumes/289-tu-mapprends-le-chemin/)')

    assert 'bi-info-circle-fill' in html
    assert '<strong>Important</strong>' in html
    assert '<em>messe</em>' in html
    assert '<a href="/psaumes/289-tu-mapprends-le-chemin/">Voir</a>' in html


def test_banner_rich_text_preserves_line_breaks():
    html = render_banner('Première ligne\nDeuxième ligne')

    assert 'Première ligne<br>Deuxième ligne' in html


def test_banner_rich_text_rejects_script_tags_and_handlers():
    html = render_banner('<script>alert(1)</script>\n[attaque](javascript:alert(1))\n:info:')

    assert '<script>' not in html
    assert 'javascript:' not in html
    assert 'alert(1)' in html
    assert 'bi-info-circle-fill' in html


def test_banner_rich_text_escapes_raw_html_instead_of_trusting_it():
    html = banner_rich_text('<b>Important</b> <img src=x onerror=alert(1)>')

    assert '<b>' not in html
    assert '<img' not in html
    assert '&lt;b&gt;Important&lt;/b&gt;' in html
