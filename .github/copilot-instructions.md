# Cantateo - Project Reference

French Django app for daily liturgical psalms with PDF scores and multi-track SATB audio.

INSTRUCTIONS:
1. Sacrifice grammar for the sake of concision
2. take care of context usage, be lean. Try to use docs of folder to avoid reading whole files unnecessarily. Use cheap gemini 3 flash subagents if possible for exploration.
3. Use docs to avoid unnecessary exploration. First read the doc of a folder before reading files. Read ONLY RELEVANT FILES

## Tech Stack

Django 5.2+ | PostgreSQL (pg_trgm search) | Redis + Celery | Cloudflare R2 | WhiteNoise | Gunicorn + Nginx | Hetzner VPS

## Commands

```bash
source venv/bin/activate    # Always activate venv first
pytest                      # Run all tests
pytest path/to/test.py -v   # Run specific test file
```

## Project Structure

```
psalm_project/           # Django settings (base, development, production)
psaumes/                 # Main app
  models/                # Psaume (liturgical), Partition (musical), MomentLiturgique, Compositeur, SiteBanner
  views/                 # base.py, details.py, api.py, files.py
  services/liturgie/     # Liturgical calendar computation (get_moment_liturgique)
  services/audio/        # MXL to MP3 synthesis (FluidSynth + FFmpeg)
  admin/                 # Django admin customizations
  templates/             # Homepage, detail pages, partials
  tests/                 # pytest test suite
static/                  # CSS, JS
deploy/                  # Hetzner deployment scripts
docs/                    # Detailed documentation
```

## Core Concepts

**Models**: `Psaume` is the liturgical entity (handling both psalms and canticles). Each `Psaume` can have multiple `Partition` entries (musical arrangements). `Partition` holds the SATB + instrumental audio tracks and the PDF/MXL scores. `MomentLiturgique` links a date to a `Psaume`.

**Liturgical Calendar**: `get_moment_liturgique(date)` returns the liturgical context for any date. Used to display the correct chant on the homepage.

**AELF API**: External API for liturgical info (colors, feast names) and fallback psalm text when no local chant exists.

**Search**: PostgreSQL `pg_trgm` + `unaccent` for fuzzy, accent-insensitive search using `nom_complet_recherche` fields (auto-populated via signals).

## URL Routes

| Route | Description |
|-------|-------------|
| `/` | Homepage with date selector, PDF viewer, audio player |
| `/?date=YYYY-MM-DD` | Chant for specific date |
| `/qui-sommes-nous/` | About page |
| `/histoire-technique/` | Technical history article |

## Documentation Index

| Document | Content |
|----------|---------|
| `docs/MODELS.md` | Database schema, MomentLiturgique types and validation rules |
| `docs/VIEWS.md` | View organization (base, details, api, files) and logic |
| `docs/TEMPLATES.md` | Template structure, partials and custom tags |
| `docs/LITURGICAL_CALENDAR.md` | Calendar service usage, AELF API integration |
| `docs/DEVELOPMENT_SETUP.md` | WSL setup, environment variables |
| `docs/HETZNER.md` | Production deployment guide |
| `docs/MEDIA_ORGANIZATION.md` | Media file structure (audios, partitions) |
| `docs/STATIC.md` | Frontend JS (Web Audio API, SATB) and CSS |
