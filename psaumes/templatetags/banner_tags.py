import html
import re
from urllib.parse import urlparse

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

try:
    import bleach
except ImportError:  # pragma: no cover - exercised only if dependency is missing
    bleach = None


register = template.Library()

ICON_CLASSES = {
    ':info:': 'bi bi-info-circle-fill text-primary me-1',
    ':warning:': 'bi bi-exclamation-triangle-fill text-warning me-1',
    ':music:': 'bi bi-music-note-beamed text-primary me-1',
    ':calendar:': 'bi bi-calendar-event text-primary me-1',
    ':check:': 'bi bi-check-circle-fill text-success me-1',
}

ALLOWED_ICON_CLASS_NAMES = {
    class_name
    for classes in ICON_CLASSES.values()
    for class_name in classes.split()
}

LINK_RE = re.compile(r'\[([^\]\n]+)\]\(([^)\s]+)\)')
BOLD_RE = re.compile(r'\*\*([^*\n][\s\S]*?[^*\n])\*\*')
ITALIC_RE = re.compile(r'(?<!\*)\*([^*\n][^*\n]*?[^*\n])\*(?!\*)')


def _safe_url(url):
    raw_url = html.unescape(url).strip()
    if not raw_url or any(char.isspace() for char in raw_url):
        return ''
    if raw_url.startswith('/') and not raw_url.startswith('//'):
        return raw_url
    if raw_url.startswith('#'):
        return raw_url
    parsed = urlparse(raw_url)
    if parsed.scheme in {'http', 'https', 'mailto'}:
        return raw_url
    return ''


def _render_link(match):
    label = match.group(1)
    url = _safe_url(match.group(2))
    if not url:
        return label
    return f'<a href="{escape(url)}">{label}</a>'


def _allow_banner_attribute(tag, name, value):
    if tag == 'a' and name == 'href':
        return bool(_safe_url(value))
    if tag == 'i' and name == 'class':
        return all(class_name in ALLOWED_ICON_CLASS_NAMES for class_name in value.split())
    if tag == 'i' and name == 'aria-hidden':
        return value == 'true'
    return False


def _plain_text_with_breaks(value):
    return mark_safe(escape(value).replace('\n', '<br>'))


@register.filter
def banner_rich_text(value):
    """Render a tiny, sanitized banner markup language."""
    if not value:
        return ''

    if bleach is None:
        return _plain_text_with_breaks(str(value))

    rendered = escape(str(value))

    for shortcode, classes in ICON_CLASSES.items():
        rendered = rendered.replace(
            shortcode,
            f'<i class="{classes}" aria-hidden="true"></i>',
        )

    rendered = LINK_RE.sub(_render_link, rendered)
    rendered = BOLD_RE.sub(r'<strong>\1</strong>', rendered)
    rendered = ITALIC_RE.sub(r'<em>\1</em>', rendered)
    rendered = rendered.replace('\n', '<br>')

    cleaned = bleach.clean(
        rendered,
        tags={'a', 'br', 'em', 'i', 'strong'},
        attributes=_allow_banner_attribute,
        protocols={'http', 'https', 'mailto'},
        strip=True,
    )
    return mark_safe(cleaned)
