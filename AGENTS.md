# Cantateo Project Instructions

French Django app for daily liturgical psalms with PDF scores and multi-track SATB audio.

## Working Style

- Sacrifice grammar for concision.
- Read `docs/` before deep code exploration.
- Prefer targeted reads with `rg`, specific functions, and documentation summaries over whole-file scans.
- Challenge weak assumptions and ask for clarification when implementation intent is ambiguous.
- For complex refactors or broad processing work, use a modular strategy with clear task boundaries.
- Subagents can be valuable for parallel, clearly bounded exploration or implementation; define ownership to avoid overlap.

## Canonical Naming

- Use `Psaume` for the liturgical entity.
- Use `Partition` for musical arrangements.
- Avoid introducing the generic term `Chant` in code implementations.

## Search

- For search-related tasks, inspect `nom_complet_recherche` fields.
- Check PostgreSQL `pg_trgm` and `unaccent` behavior when fuzzy matching is involved.

## Tech Stack

Django 5.2+ | PostgreSQL with `pg_trgm` search | Redis/Celery | Cloudflare R2 | WhiteNoise | Gunicorn + Nginx | Hetzner VPS

## Commands

Activate the virtualenv first:

```bash
source venv/bin/activate
pytest
pytest path/to/test.py -v
ruff check .
python manage.py check
python manage.py check --deploy
pip-audit -r requirements.txt
```

## Quick Paths

- Models: `psaumes/models/`
- Celery tasks: `psaumes/tasks/`
- Liturgy service: `psaumes/services/liturgie/calendrier_liturgique.py`
- Audio engine: `static/js/audio-engine/`
- Audio UI: `static/js/audio-player/`
- Templates: `psaumes/templates/`
- Deployment: `deploy/`
- Documentation: `docs/`

## Skills

- Use `audio-engine` for multi-track Web Audio, Safari playback, and synthetic audio UI work.
- Use `cantateo-hardening` for CSP, rate limits, deploy checks, upload validators, and production guardrails.
- Use `cantateo-browser-checks` for Playwright UI validation, Safari tempo controls, and audio-player regression checks.

## Core Concepts

- `Psaume` is the liturgical entity.
- Each `Psaume` can have multiple `Partition` entries for musical arrangements.
- `Partition` holds SATB and instrumental audio tracks plus PDF/MXL scores.
- `MomentLiturgique` links a date to a `Psaume`.
- `get_moment_liturgique(date)` returns the liturgical context for a date and powers the homepage chant selection.
- AELF provides external liturgical information such as colors, feast names, and fallback psalm text.

## Routes

- `/`: Homepage with date selector, PDF viewer, audio player.
- `/?date=YYYY-MM-DD`: Chant for a specific date.
- `/qui-sommes-nous/`: About page.
- `/histoire-technique/`: Technical history article.
- `/ecoute-aleatoire/`: Random shuffle player.
- `/healthz/`: App/database/cache health check.

See `docs/README.md` for the full documentation map.
