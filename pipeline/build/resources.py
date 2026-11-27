"""Tile resources: Serbia's real power plants and mines, placed on the hex map.

Like strategic resources on a Civ tile, but only meaningful sites: every lignite and gas plant, the hydro, wind and
solar plants of 10 MW or more, and the working lignite, copper and lead-zinc mines (power_mines). Capacities are the
operators' or the regulators' published figures where they exist, else OpenStreetMap's; mine output only where it is
published per mine.

Each item is tagged with its okrug and (if any) the cities.json city whose municipalities hold its hex, and `summary`
totals the mapped sites per type, nationally and per okrug. `types` is listed in rank order; the frontend uses that
order when only one icon fits a cell.
"""

from __future__ import annotations

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .infrastructure import Locator

REQUIRES = ["_world", "power_mines", "cities.json"]
PRODUCES = ["resources.json"]

SITE_RINGS = 2  # Đerdap's dams sit on the border river
SRC = "power_mines"


def _t(id, name, category, emoji, color, unit, description):
    return {"id": id, "name": name, "category": category, "emoji": emoji, "icon": f"r-{id}", "color": color,
            "unit": unit, "description": description, "source": SRC}


TYPES = [
    _t("hydro", "Hydroelectric plant", "energy", "💧", "#3fa7d6", "MW",
       "Hydro plants of 10 MW or more. Capacities are EPS's net figures (KOSTT's in Kosovo and Metohija), else "
       "OpenStreetMap's; Đerdap counts the Serbian half of the dam."),
    _t("coal_mine", "Coal mine", "mineral", "⛏️", "#4a4038", "t/yr",
       "Lignite open pits and underground brown-coal mines. Value: the year's output where EPS (or, for Kosovo's "
       "pits together, ERO) publishes it per mine."),
    _t("copper", "Copper mine", "mineral", "🥉", "#b87333", "t/yr",
       "The copper mines of Bor and Majdanpek. Value: copper in concentrate for the year, where Zijin publishes it per "
       "mine; it reports Jama Bor, Veliki Krivelj and Majdanpek only together."),
    _t("lead_zinc", "Lead-zinc mine", "mineral", "🪨", "#7d8a99", "t/yr",
       "Working lead-zinc mines. No official output is published per mine."),
    _t("coal_plant", "Lignite power plant", "energy", "🏭", "#5a5a5a", "MW",
       "Every lignite-fired power plant, with its net capacity (EPS; KOSTT in Kosovo and Metohija)."),
    _t("gas_plant", "Gas power plant", "energy", "⚡", "#f08a24", "MW",
       "Gas-fired combined heat and power plants, with their electric capacity (EPS, AERS)."),
    _t("pumped_storage", "Pumped-storage hydro", "energy", "🔄", "#2f7fb8", "MW",
       "Bajina Bašta's reversible plant: a grid battery made of two reservoirs (EPS)."),
    _t("wind", "Wind farm", "energy", "🌬️", "#9fd8cb", "MW",
       "Wind farms of 10 MW or more (AERS, KOSTT, EPS, else OpenStreetMap)."),
    _t("solar", "Solar farm", "energy", "☀️", "#ffc93c", "MW", "Solar farms of 10 MW or more."),
]
RANK = {t["id"]: i for i, t in enumerate(TYPES)}
TONNES = {"million t": 1e6, "t": 1, "t copper": 1}
SUMMARY_NOTE = ("Totals of the mapped sites only: each type has a size threshold (see its description), and mine "
                "output is missing where it is not published per mine, so these are not Serbia's full capacity or output.")


def _value(rec: dict) -> float | None:
    if "capacity_mw" in rec:
        return rec["capacity_mw"]
    if rec.get("production") is None:
        return None
    return round(rec["production"] * TONNES[rec["production_unit"]])


def _detail(rec: dict, groups: dict) -> str:
    parts = [rec.get("operator") or ""]
    if rec.get("production_year"):
        parts.append(str(rec["production_year"]))
    g = groups.get(rec["name"])
    if g:
        parts.append(f"{' + '.join(g['mines'])}: {g['production']:,} {g['production_unit']} ({g['production_year']})")
    return " · ".join(p for p in parts if p)


def _settle(items: list[dict], grid: HexGrid) -> int:
    """Move any point whose position is not in its cell (snapped sites) to the cell's centre, so x/y and cell agree."""
    moved = 0
    for it in items:
        if grid.cell_at(it["x"], it["y"]) != it["cell"]:
            it["x"], it["y"] = (round(v, 1) for v in grid.center(*grid.col_row(it["cell"])))
            moved += 1
    return moved


def summarize(items: list[dict], types: list[dict]) -> dict:
    def blank(t):
        return {"count": 0, "value": 0, "unit": t["unit"]}

    by_id = {t["id"]: t for t in types}
    national = {t["id"]: blank(t) for t in types}
    states: dict[str, dict] = {}
    for it in items:
        t = by_id[it["type"]]
        for row in (national[t["id"]], states.setdefault(it["state"], {}).setdefault(t["id"], blank(t))):
            row["count"] += 1
            row["value"] += it["value"] or 0
    for row in [*national.values(), *(r for st in states.values() for r in st.values())]:
        row["value"] = round(row["value"])
    return {"note": SUMMARY_NOTE, "national": national, "states": dict(sorted(states.items()))}


def build() -> None:
    world = load_interim("_world")
    grid, proj = HexGrid(**world["grid"]), MapProjection(**world["projection"])
    src = load_interim_payload(SRC)["data"]
    loc = Locator(world, grid, proj)
    groups = {m: g for g in src["group_production"] for m in g["mines"]}
    items, skipped = [], []
    for rec in src["plants"] + src["mines"]:
        if rec["kind"] not in RANK:
            skipped.append(f"{rec['name']} ({rec['kind']})")
            continue
        x, y = proj(rec["lon"], rec["lat"])
        cell = loc.land_cell(x, y, SITE_RINGS)
        if cell < 0:
            skipped.append(f"{rec['name']} (off the map)")
            continue
        ci = world["county"][cell]
        code = world["counties"][ci] if ci >= 0 else None
        items.append({
            "type": rec["kind"], "name": rec.get("name_sr") or rec["name"], "name_lat": rec["name"],
            "x": round(x, 1), "y": round(y, 1), "cell": cell, "value": _value(rec), "detail": _detail(rec, groups),
            "state": loc.abbrs[world["owner"][cell]], "cbsa": loc.city_of.get(code) if code else None,
        })
    items.sort(key=lambda it: (RANK[it["type"]], -(it["value"] or 0)))
    moved = _settle(items, grid)
    present = {it["type"] for it in items}
    types = [t for t in TYPES if t["id"] in present]
    write_web("resources.json", {"types": types, "items": items, "summary": summarize(items, types)})
    counts = defaultdict(int)
    for it in items:
        counts[it["type"]] += 1
    print("    " + ", ".join(f"{t['id']} {counts[t['id']]}" for t in types) + f"; {moved} moved to their cell's centre")
    if skipped:
        print(f"    {len(skipped)} left out: {', '.join(skipped)}")

