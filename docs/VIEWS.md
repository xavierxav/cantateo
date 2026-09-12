# Views Documentation

The `psaumes/views` directory contains the Django views for the Cantateo application, organized by functionality.

## Files Overview

### [base.py](../psaumes/views/base.py)
Main entry points and static-like pages.
- `index`: The homepage. Handles date selection via `?date=YYYY-MM-DD`, fetches liturgical data from the local DB and AELF API, and triggers background audio generation.
- `histoire`: About page for Cantateo.
- `blog`: Renders the article about psalm history and technique.
- `contact`: Dedicated contact page with form and email sending logic.
- `ecoute_aleatoire`: Random listening page. Plays a random Mix audio with custom player.
- `confidentialite`: Privacy page for contact form, local storage, Turnstile, and third-party services.
- `mentions_legales`: Legal notice page.

### Infrastructure
- `healthz`: Simple readiness endpoint at `/healthz/` for app, database, and cache checks.

### [details.py](../psaumes/views/details.py)
Detail views for psalms and canticles.
- `psaume_detail`: Displays a specific psalm. Handles multiple arrangements (partitions) and selects one via the `partition` query parameter. Enforces canonical URLs via 301 redirects if the slug is incorrect.
- `cantique_detail`: Legacy redirect. Now performs a 301 redirect to `psaume_detail` as canticles are integrated into the psalm model.

### [api.py](../psaumes/views/api.py)
JSON and HTMX endpoints.
- `audio_status`: Returns the generation status of synthetic voices for a given partition. Used by the frontend to show progress.
- `audio_variants`: Returns Apple/Safari tempo-variant stem URLs for `0.5x`, `1.0x`, and `1.5x`; missing `0.5x`/`1.5x` variants are generated asynchronously.
- `search_autocomplete`: HTMX endpoint for the search bar. Uses PostgreSQL `TrigramWordSimilarity` and a normalized `nom_complet_recherche` expression for unified fuzzy search on `Psaume` and `MomentLiturgique` labels.

Public audio/search endpoints are rate-limited. Autocomplete is also capped and briefly cached to avoid unbounded database work.

### [files.py](../psaumes/views/files.py)
Media file handling.
- `download_pdf`: Serves PDF scores. Supports both inline viewing (for iframes) and forced downloads. Handles proxying from Cloudflare R2 when necessary.

### [utils.py](../psaumes/views/utils.py)
Internal view utilities.
- `trigger_async_audio_generation`: Enqueues synthetic SATB voices for worker-side generation when they don't exist yet.

## Key Patterns

- **SEO Canonicalization**: Detail views redirect to the correct slug if accessed via an old or missing slug.
- **Lazy Audio Generation**: Audio is generated on-the-fly when a partition is viewed, then completed by the background worker queue.
- **Generation Guardrails**: Celery enqueueing uses the `psaumes.tasks` package so audio, normalization, and OMR jobs respect retry delay, max-attempt, priority-promotion, and stale-task guardrails.
- **HTMX Integration**: The search functionality uses HTMX for a reactive autocomplete experience.
- **AELF Integration**: The homepage combines local database records with real-time data from the AELF API for liturgical context.
- **Paris Date Semantics**: Homepage date fallback uses Django's local date, with `Europe/Paris` configured in settings.
