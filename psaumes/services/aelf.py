import logging
import re
import time
from typing import Optional, Dict, Any
from datetime import date
import requests
from django.core.cache import cache
from django.utils.html import strip_tags, escape
from django.utils.safestring import mark_safe

try:
    import bleach
except ImportError:
    bleach = None

logger = logging.getLogger(__name__)

AELF_API_BASE = "https://api.aelf.org/v1"
AELF_CACHE_TTL_SECONDS = 60 * 60 * 12
AELF_CACHE_STALE_TTL_SECONDS = 60 * 60 * 24 * 7


def _cache_key(kind: str, target_date: date) -> str:
    return f"aelf_{kind}_{target_date.isoformat()}"


def _read_cache_entry(kind: str, target_date: date):
    cached = cache.get(_cache_key(kind, target_date))
    if cached is None:
        return None, None

    if isinstance(cached, dict) and "data" in cached:
        return cached.get("data"), cached.get("cached_at")

    # Backward compatibility for older cache entries/tests that stored the payload directly.
    return cached, None


def _store_cache_entry(kind: str, target_date: date, data: Any) -> None:
    cache.set(
        _cache_key(kind, target_date),
        {
            "data": data,
            "cached_at": time.time(),
        },
        timeout=AELF_CACHE_STALE_TTL_SECONDS,
    )


def _is_fresh(cached_at: Optional[float]) -> bool:
    if cached_at is None:
        return True
    return (time.time() - cached_at) <= AELF_CACHE_TTL_SECONDS


def _fetch_aelf_info(date_str: str) -> Optional[Dict[str, Any]]:
    response = requests.get(f"{AELF_API_BASE}/informations/{date_str}", timeout=5)
    if response.status_code == 200:
        return response.json().get("informations")
    return None


def _fetch_aelf_messes(date_str: str) -> Optional[Dict[str, Any]]:
    response = requests.get(f"{AELF_API_BASE}/messes/{date_str}/france", timeout=5)
    if response.status_code == 200:
        return response.json()
    return None


def _get_cached_or_fresh(kind: str, target_date: date, fetcher):
    cached_data, cached_at = _read_cache_entry(kind, target_date)
    if cached_data is not None and _is_fresh(cached_at):
        return cached_data

    date_str = target_date.isoformat()
    try:
        fresh_data = fetcher(date_str)
    except Exception as e:
        logger.warning("Failed to fetch AELF %s for %s: %s", kind, date_str, e)
        return cached_data

    if fresh_data is not None:
        _store_cache_entry(kind, target_date, fresh_data)
        return fresh_data

    return cached_data

def get_aelf_data(target_date: date) -> Dict[str, Any]:
    """
    Fetch both liturgical info and messes (psalm text) from AELF API.
    """
    info = _get_cached_or_fresh("infos", target_date, _fetch_aelf_info)
    messes = _get_cached_or_fresh("messes", target_date, _fetch_aelf_messes)

    return {
        "info": info,
        "psalm": extract_psalm_from_messes(messes) if messes else None,
    }

def extract_psalm_from_messes(messes_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract psalm or canticle content from AELF messes JSON.
    """
    if not messes_data:
        return None

    try:
        for messe in messes_data.get('messes', []):
            for lecture in messe.get('lectures', []):
                t = (lecture.get('type') or '').lower()
                titre = lecture.get('titre') or ''
                contenu = lecture.get('contenu') or lecture.get('texte') or lecture.get('texte_html') or lecture.get('titre')
                refrain = lecture.get('refrain_psalmique')
                ref_refrain = lecture.get('ref_refrain') or lecture.get('refRefrain')
                ref = lecture.get('ref') or lecture.get('reference') or lecture.get('ref_psaume')

                # Prepare HTML content
                contenu_html = _prepare_html_content(contenu)

                # If it's a cantique
                if 'cantique' in t or (titre and 'cantique' in titre.lower()):
                    return {
                        'kind': 'cantique',
                        'titre': titre,
                        'refrain_psalmique': refrain,
                        'ref_refrain': ref_refrain,
                        'ref': ref,
                        'contenu': contenu_html,
                    }

                # If it's a psaume
                if 'psaume' in t or 'psalm' in t or (titre and 'psaume' in titre.lower()):
                    return {
                        'kind': 'psaume',
                        'titre': titre,
                        'contenu': contenu_html,
                        'ref': ref,
                        'refrain_psalmique': refrain,
                        'ref_refrain': ref_refrain,
                    }

                # Fallback: refrain may indicate psalmic content
                if refrain:
                    return {
                        'kind': 'psaume',
                        'titre': titre,
                        'refrain_psalmique': refrain,
                        'ref_refrain': ref_refrain,
                        'ref': ref,
                        'contenu': contenu_html,
                    }
    except Exception as e:
        logger.exception("Error while extracting psalm from AELF messes: %s", e)
    return None

def _prepare_html_content(contenu: Any) -> Any:
    """Helper to sanitize and format content for HTML display."""
    if not isinstance(contenu, str):
        return contenu

    try:
        # Detect if it already contains HTML tags
        if re.search(r"<[^>]+>", contenu):
            if bleach:
                allowed = ['br', 'p', 'strong', 'em', 'b', 'i', 'u', 'span', 'div', 'blockquote', 'ul', 'ol', 'li']
                cleaned = bleach.clean(contenu, tags=allowed, strip=True)
                return mark_safe(cleaned)

            logger.error("bleach is not installed; escaping AELF HTML fallback content")
            return escape(contenu)
        else:
            # Escape content and transform newlines into HTML <br/>
            normalized = contenu.replace('\r\n', '\n').replace('\r', '\n')
            escaped = escape(normalized)
            with_breaks = escaped.replace('\n', '<br/>')
            return mark_safe(with_breaks)
    except Exception:
        return contenu
