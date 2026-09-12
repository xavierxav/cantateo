# Cantateo - Psaumes du Jour

A French Django web application for displaying daily psalms with music sheets and multi-track audio recordings (Soprano, Alto, Tenor, Bass, Instrumental).

## Features

- **Daily Chant**: Psalm or canticle of the day with PDF partition and 5 audio tracks
- **AELF Integration**: Liturgical data from the French Episcopal Liturgical Association
- **Calendar Navigation**: Select any date or jump to next Sunday
- **Search**: Find psalms by number, canticles by reference, or text content

## Quick Start

```bash
# Activate environment
source venv/bin/activate

# Install dependencies (pinned)
pip install -r requirements.txt -c requirements-lock.txt

# Setup
cp .env.example .env   # Configure your credentials
python manage.py migrate
python manage.py runserver

# Open http://127.0.0.1:8000/
```

## Testing

```bash
pytest
ruff check .
python manage.py check
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Django 5.2+ |
| Database | PostgreSQL |
| Search | PostgreSQL Full-Text Search (French) |
| Async jobs | Redis + Celery |
| Media Storage | Cloudflare R2 |
| Hosting | Hetzner VPS |
| Static assets | WhiteNoise + manually vendored JS libraries |

## Deployment

See the `deploy/` folder for Hetzner VPS deployment scripts:
- `setup-server.sh` - Initial server setup
- `deploy.sh` - Deploy updates
- `backup.sh` - Database backups
- `cantateo.service` - Systemd service
- `cantateo-worker.service` - Celery worker service
- `nginx.conf` - Nginx configuration

Full deployment documentation: `HETZNER.md`

## Documentation

- `MODELS.md` - Schema, relationships, and signals
- `VIEWS.md` - Routes, view responsibilities, API endpoints
- `TEMPLATES.md` - Template structure and custom tags
- `STATIC.md` - CSS, JavaScript, PDF viewer, and audio player architecture
- `LITURGICAL_CALENDAR.md` - Calendar computation and AELF integration
- `DEVELOPMENT_SETUP.md` - Local setup and environment variables
- `HETZNER.md` - Production deployment and operations
- `MEDIA_ORGANIZATION.md` - Media file structure
- `VENDORED_ASSETS.md` - Vendored frontend dependencies and audit cadence

## Production Guardrails

- Date-sensitive liturgy logic uses the Paris timezone; prefer `timezone.localdate()` for "today".
- CSP is emitted by Django so inline scripts need a nonce and event handlers should live in static JS.
- Public contact/search/audio polling endpoints are rate-limited.
- Deploys install with `requirements-lock.txt` constraints and run `migrate --check` before applying migrations.
- Uploaded PDF/MXL/MP3 files are validated on `Partition` fields.

## Contributing

Open an issue or pull request. Test your changes locally before submitting.

---

**Cantateo** - *Singing psalms together*
