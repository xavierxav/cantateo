# Liturgical Calendar Service

## Overview

Computes the liturgical moment for any date (past or future) and queries the database for matching chants.

**Location**: `psaumes/services/liturgie/calendrier_liturgique.py`

## Usage

```python
from datetime import date
from psaumes.services.liturgie.calendrier_liturgique import (
    get_moment_liturgique,
    get_moment_liturgique_query_params
)
from psaumes.models import MomentLiturgique

# Returns dict matching MomentLiturgique model fields
moment = get_moment_liturgique(date(2025, 12, 25))
# {'type': 'FETE', 'nom_fete': 'Nativite du Seigneur', 'annee': None}

moment = get_moment_liturgique(date(2025, 2, 16))
# {'type': 'DIMANCHE', 'temps': 'ORDINAIRE', 'semaine': 6, 'jour': 0, 'annee': 'C'}

moment = get_moment_liturgique(date(2025, 2, 17))
# {'type': 'SEMAINE', 'temps': 'ORDINAIRE', 'semaine': 6, 'jour': 1, 'parite': 'I'}

# Query database for chant matching a specific date
moment_params = get_moment_liturgique_query_params(date(2025, 12, 25))
moment_obj = MomentLiturgique.objects.filter(**moment_params).select_related(
    'psaume', 'psaume__compositeur'
).prefetch_related('psaume__partitions', 'psaume__moments_liturgiques').first()
psaume = moment_obj.psaume if moment_obj else None
```

## Features

- Easter calculation via `python-dateutil`
- Mobile dates: Cendres, Rameaux, Ascension, Pentecote, Sainte Trinité, Fete-Dieu, Christ-Roi, etc.
- Epiphanie France: dimanche entre le 2 et 8 janvier
- Bapteme du Seigneur: handles edge case when Epiphanie is Jan 7-8
- Year A/B/C calculation (liturgical year starts at Advent)
- Parity P/I for weekdays

## Service Architecture

```
psaumes/services/liturgie/
├── calculs_paques.py      # Easter and moveable feast calculations
├── fetes.py               # Fixed and cyclic feast definitions
└── calendrier_liturgique.py  # Main service entry point
```

---

# AELF API Integration

## Overview

The application uses the AELF (Association Episcopale Liturgique pour les pays Francophones) API for:
- **Liturgical information display**: Colors, feast names, liturgical year
- **Fallback psalm text**: When no local PDF is available, displays psalm text from AELF
- **Caching**: Each date is cached separately for 12 hours, with stale data reused if AELF is temporarily unavailable

## Endpoints Used

```
https://api.aelf.org/v1/informations/{date}  # Liturgical info
https://api.aelf.org/v1/messes/{date}        # Mass readings (psalm text)
```

## Response Data

### `/v1/informations/{date}`

Returns liturgical metadata:
- `couleur`: Liturgical color (vert, violet, blanc, rouge, rose)
- `ligne1`: Primary feast/period name
- `ligne2`: Secondary description
- `annee`: Liturgical year (A, B, C)

### `/v1/messes/{date}`

Returns complete mass readings including:
- First reading
- **Psalm** (used as fallback when no local chant)
- Second reading (Sundays)
- Gospel

## Usage in Views

The homepage displays AELF liturgical info alongside the local chant. When no local chant exists for a date, it falls back to displaying the psalm text from AELF with a "Pas de chant pour l'instant" message.
