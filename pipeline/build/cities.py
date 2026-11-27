"""Cities: one per municipality, placed at its seat. The exceptions are Belgrade, whose eleven urban gradske
opštine form one city (its six outer ones, from Lazarevac to Grocka, are towns of their own), and Niš, Požarevac,
Vranje and Užice, whose gradske opštine are joined back into the city they divide.

Each city keeps its seat's true position (x, y) and gets one land cell for its banner: the cell under the seat,
snapped to the nearest Serbian land cell when that is water or foreign, and nudged up to 2 rings away when a bigger
city already holds it. Its figures are the sums of its municipalities (see units.py).
"""

from __future__ import annotations

import math

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .okruzi import OKRUZI
from .units import GVA_GROUPS, economy, growth_of, load_units, map_units, plain_name
from .yields import INDUSTRY_LABELS, YIELDS

REQUIRES = ["_world", "boundaries", "rzs_census", "rzs_economy", "ask_kosovo"]
PRODUCES = ["cities.json", "nation.json"]

BELGRADE = "79014"
BELGRADE_URBAN = ["70106", "70114", "70149", "70157", "70181", "70203", "70211", "70220", "70246", "70254", "71293"]
BELGRADE_SEAT = "70246"  # Stari grad
METRO_MIN_POP = 50_000
GVA_GROUP_LABELS = {
    "A": "Agriculture, forestry & fishing", "B-E": "Industry & energy", "F": "Construction",
    "G-I": "Trade, transport, hotels & restaurants", "J": "Information & communication", "K": "Finance & insurance",
    "L": "Real estate", "M-N": "Professional & support services", "O-Q": "Public administration, education & health",
    "R-U": "Arts & other services",
}


def ring_search(grid: HexGrid, start: int, max_rings: int):
    """Yield (ring, cell) for every cell within `max_rings` steps of `start`, nearest rings first."""
    seen = {start}
    frontier = [start]
    yield 0, start
    for ring in range(1, max_rings + 1):
        nxt = []
        for c in frontier:
            for n in grid.neighbours(c):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
                    yield ring, n
        frontier = nxt


def nearest_land(grid: HexGrid, owner: list[int], cell: int, x: float, y: float, state: int, max_rings=8):
    """Nearest Serbian land cell to (x, y), preferring `state`: the first ring with land, plus one more."""
    found_ring = None
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if found_ring is not None and ring > found_ring + 1:
            break
        if owner[c] < 0:
            continue
        found_ring = ring if found_ring is None else found_ring
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else -1


def free_cell(grid: HexGrid, owner, taken: set, cell: int, x: float, y: float, state: int, max_rings=2):
    """Nearest untaken land cell within `max_rings`, preferring `state`; None if there is none."""
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if owner[c] < 0 or c in taken:
            continue
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else None


FOOTPRINT_MAJORITY = 4  # of a cell's 7 municipality samples
PEERS = 5
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + [y["key"] for y in YIELDS]


def footprints(world: dict, members: dict[str, list[str]]) -> dict[str, set[int]]:
    """City id → land cells where at least FOOTPRINT_MAJORITY of the 7 municipality samples are its members."""
    city_of = {g: cid for cid, codes in members.items() for g in codes}
    by_index = [city_of.get(g) for g in world["counties"]]
    out: dict[str, set[int]] = {}
    for cell, s in enumerate(world["county_samples"]):
        if not s or world["owner"][cell] < 0:
            continue
        votes: dict[str, int] = {}
        for k in s:
            cid = by_index[k] if k >= 0 else None
            if cid:
                votes[cid] = votes.get(cid, 0) + 1
        for cid, n in votes.items():
            if n >= FOOTPRINT_MAJORITY:
                out.setdefault(cid, set()).add(cell)
    return out


def add_ranks(cities: list[dict]) -> None:
    """ranks: 1 = highest among all cities, null where the value is null (cities are sorted by population,
    so ties keep population order). peers: the PEERS cities closest in population (by ratio)."""

    def value(c, key):
        if key == "gdp_per_capita":
            return c["gdp"] / c["population"] if c.get("gdp") is not None and c.get("population") else None
        if key in ("population", "gdp", "growth"):
            return c.get(key)
        return c["yields"].get(key)

    for c in cities:
        c["ranks"] = {}
    for key in RANK_KEYS:
        have = [c for c in cities if value(c, key) is not None]
        have.sort(key=lambda c: -value(c, key))
        for r, c in enumerate(have, 1):
            c["ranks"][key] = r
        for c in cities:
            c["ranks"].setdefault(key, None)
    for i, c in enumerate(cities):
        lp = math.log(c["population"])
        near = sorted((abs(math.log(o["population"]) - lp), j) for j, o in enumerate(cities) if j != i)
        c["peers"] = [cities[j]["id"] for _, j in near[:PEERS]]


def city_groups(units: dict[str, dict], census: dict) -> list[tuple[str, str, str, list[str]]]:
    """(city id, name_cyr, name_lat, member codes) for every city; the seat is the first member's."""
    grads = {code: u for code, u in census["units"].items() if u.get("aggregate")}
    joined: dict[str, list[str]] = {}
    for code, u in units.items():
        g = u["grad_code"]
        if g and g != BELGRADE:
            joined.setdefault(g, []).append(code)
    out = [(BELGRADE, "Београд", "Beograd", [BELGRADE_SEAT] + [c for c in BELGRADE_URBAN if c != BELGRADE_SEAT])]
    for g, codes in joined.items():
        grad = grads[g]
        seat = next((c for c in codes if units[c]["name_lat"] == plain_name(grad["name_lat"])), codes[0])
        out.append((g, plain_name(grad["name_cyr"]), plain_name(grad["name_lat"]), [seat] + sorted(c for c in codes if c != seat)))
    grouped = {c for _, _, _, codes in out for c in codes}
    for code, u in units.items():
        if code not in grouped:
            out.append((code, u["name_cyr"], u["name_lat"], [code]))
    return out


def pop_series(census: dict, ask: dict, codes: list[str]) -> dict | None:
    """Every census on today's borders (RZS, 1948–2022) or ASK's yearly estimates (2012–2025) for KiM."""
    series: dict[str, int] = {}
    for code in codes:
        if code.startswith("KM"):
            src = ask["municipalities"][code].get("pop_estimate")
        else:
            src = census["units"][code].get("pop_census")
        if not src:
            return None
        for y, v in src.items():
            if v is None:
                return None
            series[y] = series.get(y, 0) + v
    return dict(sorted(series.items())) or None


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("boundaries")
    census = load_interim("rzs_census")
    econ = load_interim("rzs_economy")
    ask = load_interim("ask_kosovo")
    units, gva = load_units(census, econ, ask)
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    okrug_index = {code: i for i, code in enumerate(world["states"])}
    seats = {u["code"]: u["seat"] for u in map_units(bounds, units)}
    abbr = {o["code"]: o["abbr"] for o in OKRUZI}

    cities = []
    no_seat = []
    for cid, name_cyr, name_lat, codes in city_groups(units, census):
        members = [units[c] for c in codes]
        seat = seats.get(codes[0])
        if not seat:
            no_seat.append(name_lat)
            continue
        x, y = proj(seat["lon"], seat["lat"])
        g, g_years = growth_of(members)
        pop = sum(m["population"] for m in members)
        cities.append(
            {
                "id": cid,
                "name": name_cyr,
                "name_lat": name_lat,
                "full": name_cyr,
                "states": sorted({abbr[m["okrug_code"]] for m in members}),
                "metro": pop >= METRO_MIN_POP or cid in census["units"] and census["units"][cid].get("level") == "grad",
                "capital": cid == BELGRADE,
                "kim": members[0]["kim"],
                "reliable": all(m["reliable"] for m in members),
                "x": round(x, 1),
                "y": round(y, 1),
                "cell": grid.cell_at(x, y),
                **economy(members),
                "gdp_year": gva["kim_year"] if members[0]["kim"] else gva["year"],
                "growth": g,
                "growth_years": g_years,
                "pop_year": members[0]["pop_year"],
                "counties": sorted(codes),
                "pop_series": pop_series(census, ask, codes),
            }
        )
    cities.sort(key=lambda c: -c["population"])

    taken: set[int] = set()
    snapped, moved, shared = [], [], []
    for c in cities:
        state = okrug_index[units[c["counties"][0]]["okrug_code"]]
        cell = c["cell"]
        if cell < 0 or owner[cell] < 0:
            cell = nearest_land(grid, owner, max(cell, 0), c["x"], c["y"], state)
            snapped.append(c["name_lat"])
        if cell in taken:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is None:
                shared.append(c["name_lat"])
            else:
                cell = alt
                moved.append(c["name_lat"])
        taken.add(cell)
        c["cell"] = cell

    feet = footprints(world, {c["id"]: c["counties"] for c in cities})
    for c in cities:
        c["footprint"] = sorted(feet.get(c["id"], set()) | {c["cell"]})
    add_ranks(cities)

    print(f"    {len(cities)} cities")
    for label, items in (
        ("without a seat (left out)", no_seat),
        ("snapped off water/foreign cells", snapped),
        ("moved to a free neighbouring cell", moved),
        ("still sharing a cell", shared),
    ):
        if items:
            print(f"    {len(items)} {label}: {', '.join(items[:8])}{' …' if len(items) > 8 else ''}")

    all_units = list(units.values())
    nation = economy(all_units, partial=True)
    nation["population"] = sum(u["population"] for u in all_units)
    nation["gdp_year"] = gva["year"]
    nation["growth"], nation["growth_years"] = growth_of(all_units)
    write_web("cities.json", cities)
    write_web(
        "nation.json",
        {
            "vintage": "Census 2022 · KiM: Census 2024",
            "year": 2022,
            "gdp_vintage": f"GDP {gva['year']}: RZS value added by okrug, ASK for KiM",
            "rsd_per_eur": gva["rsd_per_eur"],
            "nation": nation,
            "yields": YIELDS,
            "industries": INDUSTRY_LABELS,
            "gdp_industries": {g: GVA_GROUP_LABELS[g] for g in GVA_GROUPS},
        },
    )
