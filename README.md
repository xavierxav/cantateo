# Cantateo — Psaumes du jour

[![CI](https://github.com/xavierxav/cantateo/actions/workflows/ci.yml/badge.svg)](https://github.com/xavierxav/cantateo/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](pyproject.toml)
[![Django 5.2](https://img.shields.io/badge/django-5.2-green)](requirements-lock.txt)
[![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-orange)](LICENSE)

Live: **https://www.cantateo.fr**

French Django app serving the daily liturgical psalm with PDF score and multi-track SATB audio (Soprano, Alto, Tenor, Bass + instrumental), backed by PostgreSQL full-text search and a computed liturgical calendar with AELF fallback.

## Features

- **Daily chant** — psalm/canticle of the day with PDF partition and 5 audio tracks
- **Calendar navigation** — any date, next-Sunday jump, liturgical year view
- **Search** — accent-insensitive fuzzy search (PostgreSQL `pg_trgm` + `unaccent`)
- **Audio engine** — Web Audio multitrack mixer, tempo variants, Safari-safe playback
- **Production guardrails** — CSP nonces, rate limits, upload validators, health checks

## Stack

Django 5.2 · PostgreSQL (`pg_trgm`) · Redis + Celery · Cloudflare R2 · WhiteNoise · Gunicorn + Nginx · Hetzner VPS

## Quick start

```bash
source venv/bin/activate
pip install -r requirements.txt -c requirements-lock.txt
cp .env.example .env   # fill credentials
python manage.py migrate
python manage.py runserver  # http://127.0.0.1:8000/
```

## Verify

```bash
pytest
ruff check .
python manage.py check
python manage.py check --deploy
pip-audit -r requirements.txt
```

## Docs

Full map in [`docs/README.md`](docs/README.md): models, views, templates, static/audio architecture, liturgical calendar + AELF, local setup, Hetzner deploy, media layout, vendored assets.

## Project layout

```
psalm_project/    Django settings (base / development / production / ci)
psaumes/          Main app: models (Psaume, Partition, MomentLiturgique), views, services, admin
static/js/        audio-engine/ (Web Audio multitrack) + audio-player/ (UI)
deploy/           Hetzner VPS scripts, systemd units, nginx.conf
docs/             Architecture and operations documentation
```

`templates/admin/base_site.html` is an intentional Django admin branding override; app templates live in `psaumes/templates/`. `import_scripts/` holds one-shot data imports (excluded from lint).

## License

Non-commercial use only — see [LICENSE](LICENSE). No commercial use without prior written permission.

---

**Cantateo** — *singing psalms together*
