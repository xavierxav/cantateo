# Vendored frontend assets

Cantateo serves third-party frontend assets from `static/vendor/` instead of public CDNs.
This keeps production independent from CDN availability and makes CSP simpler.

## Current assets

| Asset | Local path | Version source |
| --- | --- | --- |
| Bootstrap | `static/vendor/bootstrap/` | `bootstrap.min.css` header reports 5.3.0 |
| Bootstrap Icons | `static/vendor/bootstrap-icons/` | vendored CSS/font bundle |
| HTMX | `static/vendor/htmx/htmx.min.js` | bundle reports 1.9.10 |
| Flatpickr | `static/vendor/flatpickr/` | vendored JS/CSS plus French locale |
| PDF.js | `static/vendor/pdfjs/` | Mozilla PDF.js bundle |

## Maintenance

- Review these assets during dependency updates; `pip-audit` does not scan them.
- Prefer updating from upstream release artifacts and record the upstream version here.
- After updates, run `pytest`, browser smoke tests, and a manual check of search, date picker, PDF rendering, and audio controls.
