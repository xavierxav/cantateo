# Development Setup (WSL)

## Prerequisites

```bash
# Install PostgreSQL 16
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt update
sudo apt install postgresql-16 redis-server fluidsynth ffmpeg poppler-utils nodejs npm -y

# Start services
sudo service postgresql start
sudo service redis-server start

# Create database
sudo -u postgres psql -c "CREATE USER cantateo WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "CREATE DATABASE cantateo OWNER cantateo;"
```

## Environment File (.env)

Create `.env` at project root:

```bash
DJANGO_DEBUG=True
DJANGO_ENV=development
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# PostgreSQL
DATABASE_URL=postgresql://cantateo:your_password@localhost:5432/cantateo

# Audio generation
SOUNDFONT_PATH=/home/xavier/Psalms/soundfonts/UprightPianoKW-20220221.sf2

# OMR generation
OMR_BACKEND=homr_cli
OMR_MODEL_PROFILE=default
HOMR_COMMAND=/opt/omr/homr/.venv/bin/homr
OMR_MAX_PAGES=1
```

## Running the Application

```bash
source venv/bin/activate
python manage.py runserver
```

For browser testing that should behave like production background jobs, disable Celery eager mode and run a worker in a second terminal:

```bash
source venv/bin/activate
CELERY_TASK_ALWAYS_EAGER=False python manage.py runserver
```

```bash
source venv/bin/activate
CELERY_TASK_ALWAYS_EAGER=False celery -A psalm_project worker -Q audio -l info
```

This is useful for Apple/WebKit tempo variants: the HTTP request returns a `generating` status quickly while FFmpeg creates the `0.5x` or `1.5x` stems in the worker.

For OMR/MusicXML generation, run the dedicated queue separately:

```bash
source venv/bin/activate
CELERY_TASK_ALWAYS_EAGER=False celery -A psalm_project worker -Q omr -l info --concurrency=1 --prefetch-multiplier=1
```

`homr` is intentionally installed outside the Django virtualenv. Example setup:

```bash
mkdir -p /opt/omr
git clone https://github.com/liebharc/homr /opt/omr/homr
cd /opt/omr/homr
python3.11 -m venv .venv
.venv/bin/pip install poetry
.venv/bin/poetry install --only main
.venv/bin/poetry run homr --init
```

## JavaScript Checks

Node.js is used only for development/CI syntax checks of plain static JavaScript:

```bash
npm run js:check
```

The production server does not need Node unless the deploy process later starts building frontend assets.

---

# Environment Variables Reference

## Required (all environments)

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Django secret key (generate with `get_random_secret_key()`) |
| `DATABASE_URL` | PostgreSQL connection string |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins |

## Optional (development)

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_DEBUG` | False | Enable debug mode |
| `CELERY_TASK_ALWAYS_EAGER` | True | Run Celery tasks inside the current process instead of sending them to Redis |
| `CELERY_TASK_EAGER_PROPAGATES` | Same as `CELERY_TASK_ALWAYS_EAGER` | Propagate Celery task exceptions in eager mode |
| `SOUNDFONT_PATH` | None | Path to .sf2 file for audio generation |
| `OMR_BACKEND` | `homr_cli` | OMR backend implementation selected by registry |
| `OMR_MODEL_PROFILE` | `default` | Logical model profile recorded on OMR jobs |
| `HOMR_COMMAND` | `homr` | homr executable used by the `homr_cli` backend |
| `OMR_MAX_PAGES` | `1` | Maximum PDF pages allowed per OMR job |
| `OMR_TASK_TIMEOUT_SECONDS` | `600` | Per-page OMR subprocess timeout |

## Production only

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Redis connection for caching |
| `CLOUDFLARE_R2_BUCKET_NAME` | R2 bucket name |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | R2 access key |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | R2 secret key |
| `CLOUDFLARE_R2_ENDPOINT_URL` | R2 endpoint |
| `CLOUDFLARE_R2_CUSTOM_DOMAIN` | Optional custom domain for R2 |
| `SENTRY_DSN` | Optional Sentry DSN |

See `docs/HETZNER.md` for complete production environment setup.
