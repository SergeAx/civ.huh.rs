"""counties.json: one row per municipality (world.json `counties` order), column-oriented for the Explorer.

The lens columns use the very functions of lenses.py, so a municipality's row and its hexes agree. Areas are the
boundary source's, measured on the RGZ polygons.
"""

from __future__ import annotations

import json

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .cities import nearest_land
from .lenses import COUNTY_LENSES, VINTAGE
from .okruzi import OKRUZI
from .units import load_units, map_units

REQUIRES = ["_world", "boundaries", "rzs_census", "rzs_economy", "ask_kosovo", "cities.json"]
PRODUCES = ["counties.json"]


def _field(key, label, fmt, unit, higher_is, source, description):
    return {"key": key, "label": label, "format": fmt, "unit": unit, "higher_is": higher_is, "source": source,
            "description": description}


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("boundaries")
    units, _ = load_units(load_interim("rzs_census"), load_interim("rzs_economy"), load_interim("ask_kosovo"))
    cities = json.loads((WEB_DATA / "cities.json").read_text(encoding="utf-8"))
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner, pct, samples = world["owner"], world["pct"], world["county_samples"]
    abbr = {o["code"]: o["abbr"] for o in OKRUZI}
    okrug_index = {code: i for i, code in enumerate(world["states"])}
    poly = {u["code"]: u for u in map_units(bounds, units)}
    city_of = {code: c["id"] for c in cities for code in c["counties"]}

    lens_cols = list(COUNTY_LENSES)
    fields = [
        _field("geoid", "Code", "text", None, "neutral", "rzs_census", "RZS municipality code; KM01–KM38 for KiM (ASK numbering)."),
        _field("name", "Municipality", "text", None, "neutral", "rzs_census", "Name in Serbian Cyrillic."),
        _field("name_lat", "Municipality (Latin)", "text", None, "neutral", "rzs_census", "Name in Serbian Latin."),
        _field("state", "Okrug", "text", None, "neutral", "rzs_census", "The okrug, by the registration code of its seat."),
        _field("population", "Population", "int", "people", "neutral", "rzs_census", "Census population (2022; KiM 2024, with ASK's estimate for the north)."),
        _field("land_km2", "Area", "km2", "km²", "neutral", "boundaries", "Area of the municipality (RGZ register of spatial units)."),
        _field("density", "Density", "float", "people / km²", "neutral", "rzs_census", "Residents per km²."),
    ] + [
        _field(lid, meta["name"], "text" if meta["format"] == "category" else meta["format"], meta.get("unit"),
               meta["higher_is"], "rzs_census", meta["description"])
        for lid, (_, meta) in COUNTY_LENSES.items()
    ] + [
        _field("forest", "Forest", "pct", "share of land", "neutral", "landcover", "Mean forest share of the municipality's hex samples."),
        _field("crop", "Cropland", "pct", "share of land", "neutral", "landcover", "Mean cropland share of the municipality's hex samples."),
        _field("pasture", "Pasture", "pct", "share of land", "neutral", "landcover", "Mean pasture share of the municipality's hex samples."),
        _field("developed", "Built-up", "pct", "share of land", "neutral", "landcover", "Mean built-up share of the municipality's hex samples."),
        _field("cbsa", "City", "text", None, "neutral", "rzs_census", "cities.json id of the city the municipality belongs to."),
        _field("cell", "Hex", "int", None, "neutral", "boundaries", "A representative land hex: the one at the municipality's seat."),
    ]
    columns = [f["key"] for f in fields]

    shares: dict[int, dict[str, list[int]]] = {}
    for i, s in enumerate(samples):
        for k in s:
            if k >= 0:
                sh = shares.setdefault(k, {key: [] for key in ("forest", "crop", "pasture", "developed")})
                for key in sh:
                    sh[key].append(pct[key][i])

    rows = []
    for k, code in enumerate(world["counties"]):
        u, b = units[code], poly[code]
        area = b["area_km2"]
        x, y = proj(b["seat"]["lon"], b["seat"]["lat"])
        cell = grid.cell_at(x, y)
        if cell < 0 or owner[cell] < 0:
            cell = nearest_land(grid, owner, max(cell, 0), x, y, okrug_index[u["okrug_code"]])
        lens_vals = []
        for lid in lens_cols:
            f, meta = COUNTY_LENSES[lid]
            v = f(u)
            if meta["format"] == "category":
                v = None if v is None else meta["categories"][v]["id"]
            elif v is not None:
                v = round(v, 4) if meta["format"] == "pct" else round(v, 1)
            lens_vals.append(v)
        sh = shares.get(k)
        land = [round(sum(sh[key]) / len(sh[key]) / 100, 3) if sh else None for key in ("forest", "crop", "pasture", "developed")]
        rows.append([
            code, u["name_cyr"], u["name_lat"], abbr[u["okrug_code"]], u["population"], round(area, 1),
            round(u["population"] / area, 1) if area else None, *lens_vals, *land, city_of.get(code), cell,
        ])
    write_web("counties.json", {"vintage": VINTAGE, "fields": fields, "columns": columns, "rows": rows})
    print(f"    {len(rows)} municipalities, total area {sum(r[5] for r in rows):,.0f} km²")
