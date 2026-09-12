import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

COULEURS_CSS = {
    'blanc': '#FFFFFF',
    'vert': '#228B22',
    'violet': '#8B008B',
    'rouge': '#DC143C',
    'rose': '#FFB6C1',
    'noir': '#000000',
    'or': '#FFD700',
}


@register.filter
def liturgical_color(color_name):
    """Convertit le nom de couleur AELF en code CSS."""
    if not color_name:
        return '#CCCCCC'
    return COULEURS_CSS.get(color_name.lower(), '#CCCCCC')


@register.filter
def json_ld(value):
    """Serialize controlled structured data for application/ld+json."""
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return mark_safe(payload.replace('</', '<\\/'))
