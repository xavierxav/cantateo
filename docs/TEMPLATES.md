# Templates Documentation

Cantateo uses Django templates with Bootstrap 5 for a responsive, mobile-first UI.

## Structure

- `base.html`: Main layout containing the HTML skeleton, SEO meta tags, and common assets (Bootstrap, Inter font, custom CSS). Inlines the global search bar.
- `index.html`: The main entry point. Displays the selective partition for a given date (defaults to today) or a search interface. Uses `_psaume.html` for rendering.

## Detail Pages

- `psaume_detail.html`: Dedicated page for a specific Psaume or Canticle. Extends `base.html` directly and handles metadata and arrangement switching.

## Partials and Components

- `_psaume.html`: Main wrapper for rendering a chant. It handles both local partitions (PDF/Audio) and fallback text from the AELF API.
- `_autocomplete_results.html`: Used for the AJAX search dropdown.

### Reusable Components (`templates/components/`)
- `audio_player.html`: Multi-track SATB player with volume controls.
- `pdf_viewer.html`: PDF rendering via PDF.js with zoom and pagination.
- `liturgical_header.html`: Sticky header with date navigation and current chant title.
- `holy_saturday_special.html`: Special message for Holy Saturday (silence of the Church).
- `easter_sunday_special.html`: Accordion for Easter (Vigil and Day Mass) linking to various moments.
- `chant_header.html`: Standardized title and arrangement dropdown for various chant views.
- `liturgical_indicators.html`: Small helper for displaying liturgical colors and seasons.

### Partials (`templates/partials/`)
- `_seo_meta.html`: Consolidated logic for OpenGraph tags, Twitter cards, and audio preloading.

## Static Pages

- `histoire.html`: About page / Group history.
- `blog.html`: Technical background and project history about psalms.
- `contact.html`: Contact form page.

## Custom Tags

The project uses custom template tags located in `psaumes/templatetags/`, notably for liturgical date formatting and search highlighting.
