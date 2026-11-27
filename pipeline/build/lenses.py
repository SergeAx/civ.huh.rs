"""Lenses = per-hex map overlays built from municipality data (and land cover).

Each hex is sampled at 7 points (see world.py). A municipality's population is spread over the hexes in
proportion to how many of all its sample points fall in each hex, so everyone is counted exactly once.
Municipalities smaller than a hex that no sample hits (Vračar, Stari grad) are added in full to the hex holding
their seat. Density = people ÷ the hex's land area; every other municipal lens is the mean of the municipalities
in the hex, weighted by those people.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import KM_PER_UNIT, MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .cities import nearest_land
from .units import ETHNICITY, RELIGION, load_units, map_units

REQUIRES = ["_world", "boundaries", "rzs_census", "rzs_economy", "ask_kosovo"]
PRODUCES = ["lenses.json"]

VINTAGE = "Census 2022 · KiM: Census 2024"
GROUPS = [
    {"id": "people", "name": "People"},
    {"id": "prosperity", "name": "Prosperity"},
    {"id": "knowledge", "name": "Knowledge"},
    {"id": "faith", "name": "Faith"},
    {"id": "land", "name": "Land"},
]
KIM_NORTH_NOTE = (
    "In Leposavić, Zvečan, Zubin Potok and Severna Kosovska Mitrovica most Serbs boycotted the 2024 census, so "
    "only population, age and ethnicity (which include the statisticians' estimate) are shown there."
)
SERBIA_ONLY_NOTE = "Kosovo and Metohija has no municipal figure for this: its hexes are blank."


def share(d: dict | None, keys: list[str], exclude: tuple = ()) -> float | None:
    if not d or any(d.get(k) is None for k in keys):
        return None
    total = sum(v for k, v in d.items() if v is not None and k not in exclude)
    return sum(d[k] for k in keys) / total if total else None


def largest(d: dict | None, order: list[str], skip: tuple = ("undeclared", "other")) -> int | None:
    if not d:
        return None
    cands = [k for k in order if k not in skip and d.get(k)]
    return order.index(max(cands, key=lambda k: d[k])) if cands else None


def seniors(u):
    a = u["age"]
    return sum(a[g] for g in ("65-69", "70-74", "75-79", "80-84", "85+")) / u["population"] if a and u["population"] else None


def believers(u):
    s = share(u["religion"], ["orthodox", "catholic", "protestant", "islam", "other"])
    return None if s is None else 100 * s


FAITHS = ["orthodox", "catholic", "protestant", "islam"]
PEOPLES = ["serbs", "albanians", "hungarians", "bosniaks", "slovaks", "bulgarians", "romanians", "croats", "roma", "turks", "vlachs", "montenegrins"]
PEOPLE_COLORS = ["#c0392b", "#2c6fb7", "#3a9a5b", "#1f8f8a", "#7b5bb5", "#d98c2b", "#b5a033", "#5a7fd0", "#9a5a3a", "#d0508a", "#6c8a3a", "#8a6a9a"]
FAITH_COLORS = ["#d4a42c", "#4f7fd0", "#8a5ab8", "#2f9a6a"]

# Municipal lenses: id → (value of one municipality, lens metadata). counties.json uses the same functions.
COUNTY_LENSES = {
    "age": (
        lambda u: u["mean_age"],
        {
            "group": "people", "name": "Mean age", "icon": "l-age", "emoji": "🎂", "unit": "years",
            "format": "years", "scale": "linear", "higher_is": "neutral",
            "ramp": ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"],
            "description": "Mean age of residents, from the census 5-year age groups (group midpoints; 85+ counted "
            "as 90): the one measure both censuses allow.",
        },
    ),
    "seniors": (
        seniors,
        {
            "group": "people", "name": "Aged 65+", "icon": "l-age", "emoji": "👵", "unit": "share of residents aged 65+",
            "format": "pct", "scale": "linear", "higher_is": "neutral",
            "ramp": ["#0b1d2e", "#20476b", "#3f77a0", "#7aa9c7", "#c1dbe8", "#fff6e0"],
            "description": "Share of residents aged 65 and over.",
        },
    ),
    "growth": (
        lambda u: u["growth"],
        {
            "group": "people", "name": "Growth", "icon": "l-growth", "emoji": "📈", "unit": "population change since 2011",
            "format": "pct", "scale": "linear", "higher_is": "good",
            "ramp": ["#67001f", "#d6604d", "#fddbc7", "#d1e5f0", "#4393c3", "#053061"],
            "description": "Population change from the 2011 census to the latest one (2022; 2024 in KiM), on "
            "today's municipal borders.",
            "note": "Blank where the 2011 count is not usable: Preševo and Bujanovac (most Albanians boycotted "
            "it) and KiM's four northern municipalities (not enumerated).",
        },
    ),
    "unemployment": (
        lambda u: u["unemployed"] / u["active"] if u["active"] and u["unemployed"] is not None else None,
        {
            "group": "prosperity", "name": "Unemployment", "icon": "l-poverty", "emoji": "📉",
            "unit": "unemployed share of the labour force", "format": "pct", "scale": "linear", "higher_is": "bad",
            "ramp": ["#03051a", "#4c1d4b", "#a11a5b", "#e83f3f", "#f69c73", "#faebdd"],
            "description": "Unemployed ÷ economically active residents at the census (15+ in Serbia, 15–64 in KiM).",
            "note": KIM_NORTH_NOTE,
        },
    ),
    "income": (
        lambda u: u["wage_net_eur"],
        {
            "group": "prosperity", "name": "Wages", "icon": "l-income", "emoji": "💶", "unit": "average net monthly wage, €",
            "format": "eur", "scale": "linear", "higher_is": "good",
            "ramp": ["#3a1c0b", "#7a4413", "#b8781f", "#e3b23c", "#f6e27f", "#fffbe0"],
            "description": "Average net monthly wage of employees living in the municipality (RZS), converted at the "
            "year's average exchange rate (GDP in dinars ÷ GDP in euros).",
            "note": SERBIA_ONLY_NOTE,
        },
    ),
    "gdp_per_capita": (
        lambda u: u["gdp"] / u["population"] if u["gdp"] is not None and u["population"] else None,
        {
            "group": "prosperity", "name": "GDP per person", "icon": "l-income", "emoji": "💰",
            "unit": "GDP per resident, €", "format": "eur", "scale": "log", "higher_is": "good",
            "ramp": ["#1a1405", "#4d3b0c", "#86671a", "#c19a2e", "#ead27a", "#fff8d8"],
            "description": "GDP per resident. Statistics publish value added per okrug (Serbia) and for KiM as a "
            "whole; each municipality's share is estimated from its employees by activity, so this is an "
            "estimate (≈), and it is counted where the work is done while residents are counted where they live.",
        },
    ),
    "tertiary": (
        lambda u: share(u["education"], ["tertiary"], exclude=("unknown",)),
        {
            "group": "knowledge", "name": "Degrees", "icon": "l-degrees", "emoji": "🎓",
            "unit": "residents 15+ with a college or university degree", "format": "pct", "scale": "linear",
            "higher_is": "good",
            "ramp": ["#08203e", "#0f4c81", "#2a7fc1", "#5fa8e0", "#a6d1f2", "#eaf5ff"],
            "description": "Share of residents aged 15 and over whose highest finished school is a college (više) or "
            "university (visoko), of those whose education is known.",
            "note": KIM_NORTH_NOTE,
        },
    ),
    "no_school": (
        lambda u: share(u["education"], ["none"], exclude=("unknown",)),
        {
            "group": "knowledge", "name": "No primary school", "icon": "l-degrees", "emoji": "✏️",
            "unit": "residents 15+ without finished primary school", "format": "pct", "scale": "linear",
            "higher_is": "bad",
            "ramp": ["#0b0405", "#382a54", "#395d9c", "#3497a9", "#60ceac", "#def5e5"],
            "description": "Share of residents aged 15 and over with no schooling or unfinished primary school "
            "(in KiM: no schooling or only the first five grades).",
            "note": KIM_NORTH_NOTE,
        },
    ),
    "ethnicity": (
        lambda u: largest(u["ethnicity"], PEOPLES),
        {
            "group": "people", "name": "Largest people", "icon": "l-foreign-born", "emoji": "🧑‍🤝‍🧑", "unit": None,
            "format": "category", "scale": "linear", "higher_is": "neutral",
            "categories": [{"id": k, "name": ETHNICITY[k][0], "color": c} for k, c in zip(PEOPLES, PEOPLE_COLORS)],
            "description": "The largest national community of the municipality by the census declaration "
            "(\"other\" and undeclared left out).",
            "note": "A census declaration, voluntary and self-chosen. KiM figures are ASK's 2024 census.",
        },
    ),
    "faith_tradition": (
        lambda u: largest(u["religion"], FAITHS),
        {
            "group": "faith", "name": "Largest faith", "icon": "l-faith-tradition", "emoji": "⛪", "unit": None,
            "format": "category", "scale": "linear", "higher_is": "neutral",
            "categories": [{"id": k, "name": RELIGION[k][0], "color": c} for k, c in zip(FAITHS, FAITH_COLORS)],
            "description": "The religion most residents of the municipality declared at the census.",
            "note": "A census declaration of religious affiliation, not practice. " + KIM_NORTH_NOTE,
        },
    ),
    "faith": (
        believers,
        {
            "group": "faith", "name": "Believers", "icon": "l-faith", "emoji": "🕍", "unit": "per 100 residents",
            "format": "float", "scale": "linear", "higher_is": "neutral", "domain": [50, 100],
            "ramp": ["#1a1030", "#3d2a6b", "#6a4fa0", "#9c82c9", "#cdbce6", "#f6f0ff"],
            "description": "Residents who declared a religion, per 100 (those who did not answer count as not declaring one).",
            "note": "A census declaration of religious affiliation, not practice. " + KIM_NORTH_NOTE,
        },
    ),
}
for _lid in ("ethnicity", "faith_tradition"):
    _m = COUNTY_LENSES[_lid][1]
    _m["ramp"] = [c["color"] for c in _m["categories"]]
    _m["domain"] = [0, len(_m["categories"]) - 1]

LAND_LENSES = {
    "forest": (["forest"], {
        "name": "Forest", "icon": "l-forest", "emoji": "🌲",
        "ramp": ["#0b1f0f", "#14401c", "#1f6b2b", "#3a9443", "#7fc07a", "#d5efcd"],
        "description": "Share of the hex's land covered by forest or woodland (CORINE 311–313, 324, 244).",
    }),
    "farmland": (["crop", "pasture"], {
        "name": "Farmland", "icon": "l-farmland", "emoji": "🌾",
        "ramp": ["#1d1405", "#4a3510", "#7d5e1c", "#b38f32", "#dcc56a", "#fbf2c7"],
        "description": "Share of the hex's land that is arable land, vineyards, orchards or pasture (CORINE 211–243).",
    }),
    "developed": (["developed"], {
        "name": "Built-up", "icon": "l-developed", "emoji": "🏙️",
        "ramp": ["#121218", "#2c2c3c", "#4b4b66", "#727294", "#a3a3c2", "#e2e2f0"],
        "description": "Share of the hex's land that is urban fabric, industry or transport (CORINE 111–124, 133).",
    }),
}


def nice(v: float, up: bool) -> float:
    """v rounded outward (up or down) to 2 significant digits."""
    if v == 0:
        return 0
    mag = 10 ** (math.floor(math.log10(abs(v))) - 1)
    return round((math.ceil if up else math.floor)(v / mag) * mag, 10)


def percentile_domain(values: list, log: bool) -> list[float] | None:
    """[2nd, 98th] percentile of the non-null hex values, rounded outward; positive values only on a log scale."""
    vals = sorted(v for v in values if v is not None and (v > 0 or not log))
    if not vals:
        return None
    lo, hi = vals[int(0.02 * (len(vals) - 1))], vals[int(0.98 * (len(vals) - 1))]
    lo, hi = nice(lo, False), nice(hi, True)
    return [lo, hi] if hi > lo else [lo, nice(vals[-1], True)]


DOMAIN_NOTE = " Colours span the 2nd–98th percentile of hexes; values beyond are drawn at the end colours."


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("boundaries")
    units, _ = load_units(load_interim("rzs_census"), load_interim("rzs_economy"), load_interim("ask_kosovo"))
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    samples = world["county_samples"]
    hex_area_km2 = 1.5 * math.sqrt(3) * (grid.radius * KM_PER_UNIT) ** 2
    okrug_index = {code: i for i, code in enumerate(world["states"])}
    seats = {u["code"]: u["seat"] for u in map_units(bounds, units)}

    total_hits = Counter(k for s in samples for k in s if k >= 0)
    county = [units[code] for code in world["counties"]]

    small_by_cell: dict[int, list[int]] = {}
    for k, u in enumerate(county):
        if total_hits[k]:
            continue
        seat = seats.get(u["code"])
        x, y = proj(seat["lon"], seat["lat"])
        cell = grid.cell_at(x, y)
        if cell < 0 or not samples[cell]:
            cell = nearest_land(grid, owner, max(cell, 0), x, y, okrug_index[u["okrug_code"]])
        small_by_cell.setdefault(cell, []).append(k)
    if small_by_cell:
        print(f"    {sum(map(len, small_by_cell.values()))} municipalities smaller than any sample, placed at their seat")

    weights: list[list[tuple[int, float]]] = [[] for _ in range(grid.size)]
    density = [None] * grid.size
    for i, s in enumerate(samples):
        if not s:
            continue
        parts = [(k, county[k]["population"] * hits / total_hits[k]) for k, hits in Counter(x for x in s if x >= 0).items()]
        parts += [(k, county[k]["population"]) for k in small_by_cell.get(i, [])]
        land = sum(1 for x in s if x >= 0) or 1
        weights[i] = parts
        if parts:
            density[i] = round(sum(p for _, p in parts) / (hex_area_km2 * land / len(s)), 2)
    total = sum(u["population"] for u in county)
    on_map = sum(p for parts in weights for _, p in parts)
    print(f"    population on hexes {on_map:,.0f} of {total:,.0f} ({on_map / total:.4%})")

    lenses = [{
        "id": "density", "group": "people", "name": "Population", "icon": "l-people", "emoji": "👥",
        "unit": "people / km²", "format": "int", "scale": "log", "higher_is": "neutral",
        "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"],
        "source": "rzs_census",
        "description": "Residents per km² of land. Each municipality's population is spread over its hexes in "
        "proportion to how much of the municipality each hex covers.",
        "values": density,
    }]
    for lid, (f, meta) in COUNTY_LENSES.items():
        vals_u = [f(u) for u in county]
        values = [None] * grid.size
        for i, parts in enumerate(weights):
            if meta["format"] == "category":
                votes = Counter()
                for k, p in parts:
                    if vals_u[k] is not None:
                        votes[vals_u[k]] += p
                values[i] = votes.most_common(1)[0][0] if votes else None
                continue
            vals = [(vals_u[k], p) for k, p in parts if vals_u[k] is not None]
            wsum = sum(p for _, p in vals)
            if wsum:
                v = sum(v * p for v, p in vals) / wsum
                values[i] = round(v, 4) if meta["format"] == "pct" else round(v, 1 if v < 1000 else 0)
        lenses.append({"id": lid, **meta, "source": "rzs_census", "values": values})

    pct, cover = world["pct"], world["cover"]
    for lid, (keys, meta) in LAND_LENSES.items():
        values = [round(sum(pct[k][i] for k in keys) / 100, 2) if owner[i] >= 0 and cover[i] else None for i in range(grid.size)]
        lenses.append({
            "id": lid, "group": "land", **meta, "unit": "share of land", "format": "pct", "scale": "linear",
            "higher_is": "neutral", "source": "landcover", "values": values,
        })

    for lens in lenses:
        if "domain" in lens:
            continue
        lens["domain"] = percentile_domain(lens["values"], lens["scale"] == "log")
        lens["description"] += DOMAIN_NOTE
    groups = [g for g in GROUPS if any(l["group"] == g["id"] for l in lenses)]
    write_web("lenses.json", {"vintage": VINTAGE, "groups": groups, "lenses": lenses})
