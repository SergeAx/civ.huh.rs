"""The game-concept → real-data mapping, in one place.

Each yield is defined once here and exported to the browser, so the UI and the
Almanac always describe exactly what was computed. Gold is GDP (see units.add_gva); the
other yields count employed residents by NACE Rev. 2 section at the census (2022;
KiM 2024), where they live, as upstream counted ACS workers.
"""

from __future__ import annotations

# key → (NACE Rev. 2 sections, label)
INDUSTRIES = {
    "agriculture": ("A", "Agriculture, forestry & fishing"),
    "mining": ("B", "Mining & quarrying"),
    "manufacturing": ("C", "Manufacturing"),
    "utilities": ("DE", "Electricity, gas, water & waste"),
    "construction": ("F", "Construction"),
    "trade": ("G", "Wholesale & retail trade"),
    "transportation": ("H", "Transportation & storage"),
    "accommodation": ("I", "Accommodation & food services"),
    "information": ("J", "Information & communication"),
    "finance": ("K", "Finance & insurance"),
    "real_estate": ("L", "Real estate"),
    "professional": ("M", "Professional, scientific & technical"),
    "admin": ("N", "Administrative & support services"),
    "public_admin": ("O", "Public administration & defence"),
    "education": ("P", "Education"),
    "health": ("Q", "Health & social work"),
    "arts": ("R", "Arts, entertainment & recreation"),
    "other": ("STU", "Other services"),
}
INDUSTRY_LABELS = {k: label for k, (_, label) in INDUSTRIES.items()}

YIELDS = [
    {
        "key": "food",
        "icon": "y-food",
        "emoji": "🌾",
        "label": "Food",
        "color": "#7fbf3f",
        "unit": "workers",
        "industries": ["agriculture"],
        "description": "Employed residents in agriculture, forestry & fishing (NACE A) at the census, counted where "
        "they live; farmers working their own land count.",
    },
    {
        "key": "production",
        "icon": "y-production",
        "emoji": "⚙️",
        "label": "Production",
        "color": "#d9823b",
        "unit": "workers",
        "industries": ["manufacturing", "construction", "mining"],
        "description": "Employed residents in manufacturing, construction and mining (NACE C, F, B) at the census, "
        "counted where they live.",
    },
    {
        "key": "gold",
        "icon": "y-gold",
        "emoji": "💰",
        "label": "Gold",
        "color": "#f2c94c",
        "unit": "eur",
        "industries": [],
        "description": "Gross domestic product per year, in euros. RZS publishes gross value added per okrug and "
        "by ten activity groups, ASK for KiM as a whole; it is scaled to GDP by the national ratio of GDP to value "
        "added, and a city's share is estimated (≈) from its employees in each activity group.",
    },
    {
        "key": "science",
        "icon": "y-science",
        "emoji": "🔬",
        "label": "Science",
        "color": "#4fa3e0",
        "unit": "workers",
        "industries": ["professional", "information"],
        "description": "Employed residents in information & communication and in professional, scientific & "
        "technical services (NACE J, M) at the census, counted where they live.",
    },
    {
        "key": "culture",
        "icon": "y-culture",
        "emoji": "🎭",
        "label": "Culture",
        "color": "#b07ce0",
        "unit": "workers",
        "industries": ["arts"],
        "description": "Employed residents in arts, entertainment & recreation (NACE R) at the census, counted where "
        "they live.",
    },
]


def yields_of(jobs: dict, gdp: float | None) -> dict:
    out = {}
    for y in YIELDS:
        if y["key"] == "gold":
            out["gold"] = gdp
        else:
            vals = [jobs.get(k) for k in y["industries"]]
            out[y["key"]] = None if any(v is None for v in vals) else sum(vals)
    return out
