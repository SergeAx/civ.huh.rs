"""Tile improvements: motorways, state roads and railways rasterised onto hex links, plus airports and river ports.

Lines are never shipped as polylines. Each OpenStreetMap line is sampled every SAMPLE step along its length, each
sample is mapped to its hex, repeats in a row are dropped, a cell whose neighbours on the line already touch is
dropped (the line only clipped its corner; this keeps a road along a row boundary from zigzagging), and every step
between two cells becomes a link between neighbouring cells (a step that skips cells is filled with a hex line walk).
The browser draws a link as a road or rail segment from hex centre to hex centre. A link needs one end on Serbian land
and neither in a neighbouring country.

A site's `cell` is the Serbian land cell at its point, or the nearest one up to SITE_RINGS hexes away (river ports);
x/y stay the true position.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web
from .okruzi import KIM_OKRUZI, OKRUZI

REQUIRES = ["_world", "osm_transport", "cities.json"]
PRODUCES = ["infrastructure.json"]

SAMPLE = 4.0  # map units (480 m)
SITE_RINGS = 2
FOREIGN = -2
ROAD_CLASSES = [{"id": "motorway", "name": "Motorway"}, {"id": "major", "name": "State road"}]
ROAD_CLASS = {"motorway": 0, "trunk": 1, "primary": 1}
RAIL_TIERS = [{"id": "high_speed", "name": "High-speed line"}, {"id": "main", "name": "Main line"},
              {"id": "secondary", "name": "Branch line"}]
RAIL_TIER = {"main": 1, "branch": 2}
HIGH_SPEED_KMH = 160
HUBS = {}
# Serbian usage names Priština's airport after the city alone; "Adem Jashari" is the Kosovo authorities' dedication.
AIRPORT_NAMES = {"PRN": ("Аеродром Приштина", "Aerodrom Priština")}

RULES = {
    "roads": "OpenStreetMap roads sampled every 480 m and snapped to hex-centre links. Class 0: motorways. Class 1: "
             "trunk and primary roads (Serbia's state roads of class IA, IB and IIA), where no motorway already joins "
             "the same two hexes. Route numbers are Serbia's; Kosovo and Metohija's roads are shown unnumbered.",
    "rail": "OpenStreetMap railways in use for main and branch lines (no sidings, yards or industrial track), sampled "
            "every 480 m and snapped to hex-centre links. Tier 0 is high-speed track (tagged high-speed, or 160 km/h "
            "and faster: Belgrade–Novi Sad–Subotica), tier 1 the other main lines, tier 2 the branch lines.",
    "ports": "Cargo ports on the Danube, Sava and Tisa mapped in OpenStreetMap, at the port area's centre.",
    "airports": "Airports with an IATA code, with their passengers where an official figure is published.",
}

# ------------------------------------------------------------------ hex helpers


def _axial(grid: HexGrid, cell: int) -> tuple[int, int]:
    col, row = grid.col_row(cell)
    return col - (row - (row & 1)) // 2, row


def _from_axial(grid: HexGrid, q: int, r: int) -> int:
    col = q + (r - (r & 1)) // 2
    if 0 <= col < grid.cols and 0 <= r < grid.rows:
        return grid.index(col, r)
    return -1


def hex_distance(grid: HexGrid, a: int, b: int) -> int:
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    return (abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2


def hex_walk(grid: HexGrid, a: int, b: int) -> list[int]:
    """Cells on the hex line from a to b, both included (cube lerp with a tiny nudge to break ties)."""
    n = hex_distance(grid, a, b)
    if n <= 1:
        return [a, b] if a != b else [a]
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    out = []
    for i in range(n + 1):
        t = i / n
        x = q1 + (q2 - q1) * t + 1e-6
        z = r1 + (r2 - r1) * t + 1e-6
        y = -x - z
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        c = _from_axial(grid, rx, rz)
        if c >= 0 and (not out or out[-1] != c):
            out.append(c)
    return out


def sample_cells(grid: HexGrid, pts: list[tuple[float, float]], keep=None) -> list[list[int]]:
    """Runs of distinct consecutive cells along a projected line, sampled every SAMPLE. `keep(x, y)` False
    breaks the run (the sample is dropped)."""
    runs, run = [], []

    def add(x, y):
        nonlocal run
        if keep is not None and not keep(x, y):
            if len(run) > 1:
                runs.append(run)
            run = []
            return
        c = grid.cell_at(x, y)
        if c < 0:
            return
        if not run or run[-1] != c:
            run.append(c)

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / SAMPLE))
        for i in range(steps):
            t = i / steps
            add(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    if pts:
        add(*pts[-1])
    if len(run) > 1:
        runs.append(run)
    return runs


def straighten(grid: HexGrid, run: list[int]) -> list[int]:
    """Drop detour cells: where the cells before and after a cell are neighbours themselves, the line only clipped
    that cell's corner. Without this, a road running along a row boundary zigzags between two rows."""
    out = []
    for c in run:
        while len(out) >= 2 and c in grid.neighbours(out[-2]):
            out.pop()
        if not out or out[-1] != c:
            out.append(c)
    return out


def links_of(grid: HexGrid, run: list[int]) -> list[tuple[int, int]]:
    out = []
    run = straighten(grid, [c for path in ([run[0]], *(hex_walk(grid, a, b)[1:] for a, b in zip(run, run[1:])))
                            for c in path])
    for a, b in zip(run, run[1:]):
        path = hex_walk(grid, a, b)
        for u, v in zip(path, path[1:]):
            if u != v:
                out.append((u, v) if u < v else (v, u))
    return out


# ------------------------------------------------------------------ roads and rail


def _route_key(name: str) -> tuple:
    digits = "".join(ch for ch in name if ch.isdigit())
    return (not name.startswith("A"), len(digits) or 9, int(digits) if digits else 999, name)


def _links(grid, proj, owner, lines, keep=None):
    for line in lines:
        pts = [proj(lon, lat) for lon, lat in line]
        for run in sample_cells(grid, pts, keep):
            for a, b in links_of(grid, run):
                if owner[a] == FOREIGN or owner[b] == FOREIGN or (owner[a] < 0 and owner[b] < 0):
                    continue
                yield a, b


def build_roads(grid, proj, owner, roads, kim: set[int]):
    cls_of = defaultdict(lambda: 9)
    names = defaultdict(Counter)
    for f in roads:
        cls = ROAD_CLASS.get(f["class"])
        if cls is None:
            continue
        name = f.get("ref") or None
        for a, b in _links(grid, proj, owner, [f["line"]]):
            if cls < cls_of[(a, b)]:
                cls_of[(a, b)] = cls
                names[(a, b)].clear()
            if cls == cls_of[(a, b)] and name and owner[a] not in kim and owner[b] not in kim:
                names[(a, b)][name] += 1
    out = []
    for (a, b), cls in sorted(cls_of.items()):
        nm = min(names[(a, b)], key=_route_key) if names[(a, b)] else None
        out.append([a, b, cls, nm])
    return out


def build_rail(grid, proj, owner, rail):
    def keep(x, y):
        c = grid.cell_at(x, y)
        return c < 0 or owner[c] != FOREIGN

    tier_of = {}
    for f in rail:
        tier = RAIL_TIER.get(f["usage"])
        if tier is None:
            continue
        if f.get("highspeed") or (f.get("maxspeed") or 0) >= HIGH_SPEED_KMH:
            tier = 0
        for a, b in _links(grid, proj, owner, [f["line"]], keep):
            tier_of[(a, b)] = min(tier, tier_of.get((a, b), 9))
    return [[a, b, t] for (a, b), t in sorted(tier_of.items())]


class Locator:
    def __init__(self, world, grid, proj):
        self.grid, self.proj = grid, proj
        self.owner, self.county, self.codes = world["owner"], world["county"], world["counties"]
        abbr = {o["code"]: o["abbr"] for o in OKRUZI}
        self.abbrs = [abbr[code] for code in world["states"]]
        cities = json.loads((WEB_DATA / "cities.json").read_text(encoding="utf-8"))
        self.city_of = {code: c["id"] for c in cities for code in c["counties"]}

    def land_cell(self, x, y, rings=SITE_RINGS) -> int:
        grid, owner = self.grid, self.owner
        cell = grid.cell_at(x, y)
        if cell < 0:
            return -1
        if owner[cell] >= 0:
            return cell
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = list(dict.fromkeys(n for c in frontier for n in grid.neighbours(c) if n not in seen))
            seen.update(ring)
            land = [n for n in ring if owner[n] >= 0]
            if land:
                return min(land, key=lambda n: math.dist(grid.center(*grid.col_row(n)), (x, y)))
            frontier = ring
        return -1

    def place(self, lon, lat) -> dict | None:
        x, y = self.proj(lon, lat)
        cell = self.land_cell(x, y)
        if cell < 0:
            return None
        ci = self.county[cell]
        code = self.codes[ci] if ci >= 0 else None
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": code,
                "cbsa": self.city_of.get(code) if code else None, "state": self.abbrs[self.owner[cell]]}


def build_ports(loc: Locator, ports: list[dict]) -> list[dict]:
    out = []
    for p in ports:
        at = loc.place(p["lon"], p["lat"])
        if at is None:
            continue
        out.append({"id": f"port-{len(out) + 1}", "name": p["name_sr"], "name_lat": p["name_lat"],
                    "type": "inland", "river": p.get("river"), "rank": None, "tons": p.get("cargo_t"),
                    "domestic": None, "foreign": None, "imports": None, "exports": None, "year": p.get("cargo_year"), **at})
    ranked = sorted((p for p in out if p["tons"] is not None), key=lambda p: -p["tons"])
    for r, p in enumerate(ranked, 1):
        p["rank"] = r
    out.sort(key=lambda p: (p["rank"] is None, p["rank"] or 0, p["name"]))
    return out


def build_airports(loc: Locator, airports: list[dict]) -> list[dict]:
    out = []
    for a in airports:
        at = loc.place(a["lon"], a["lat"])
        if at is None:
            continue
        name, name_lat = AIRPORT_NAMES.get(a["iata"], (a["name_sr"], a["name_lat"]))
        out.append({"id": a["iata"], "name": name, "name_lat": name_lat, "city": None,
                    "hub": None, "enplanements": a.get("passengers"), "enplanements_prev": None, "cargo_lbs": None,
                    "year": a.get("passengers_year"), **at})
    out.sort(key=lambda a: -(a["enplanements"] or 0))
    return out


def build() -> None:
    world = load_interim("_world")
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    osm = load_interim_payload("osm_transport")
    data = osm["data"]
    kim = {i for i, code in enumerate(world["states"]) if code in KIM_OKRUZI}
    roads = build_roads(grid, proj, owner, data["roads"], kim)
    rail = build_rail(grid, proj, owner, data["rail"])
    loc = Locator(world, grid, proj)
    ports = build_ports(loc, data["ports"])
    airports = build_airports(loc, data["airports"])
    vintage = osm["vintage"]
    write_web("infrastructure.json", {
        "version": 1,
        "vintage": {"roads": vintage, "rail": vintage, "ports": vintage, "airports": vintage},
        "sources": ["osm_transport"],
        "rules": RULES,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    })
    road_cells = {c for a, b, *_ in roads for c in (a, b) if owner[c] >= 0}
    rail_cells = {c for a, b, _ in rail for c in (a, b) if owner[c] >= 0}
    land = sum(1 for o in owner if o >= 0)
    n0 = sum(1 for r in roads if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} state-road links on {len(road_cells)} of {land} land hexes; "
          f"rail: {len(rail)} links on {len(rail_cells)} hexes; {len(ports)} ports, {len(airports)} airports")


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "infrastructure.json"
    if not path.exists():
        return [("NOTE", "infrastructure.json not built (optional; run: build infrastructure --deps)")]
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = [("FAIL", f"infrastructure.json lacks '{k}'") for k in
           ("version", "vintage", "sources", "road_classes", "rail_tiers", "roads", "rail", "ports", "airports")
           if k not in doc]
    if out:
        return out
    wpath = Path(web_dir) / "world.json"
    if not wpath.exists():
        return [("NOTE", "infrastructure.json: world.json unavailable, cell checks skipped")]
    world = json.loads(wpath.read_text(encoding="utf-8"))
    grid = HexGrid(world["grid"]["radius"], world["grid"]["cols"], world["grid"]["rows"])
    owner, n = world["owner"], grid.size

    def bad_link(link, ncls):
        if not isinstance(link, list) or len(link) < 3 or not all(isinstance(v, int) for v in link[:3]):
            return "shape"
        a, b, c = link[:3]
        if not 0 <= a < b < n:
            return "order/range"
        if b not in grid.neighbours(a):
            return "not neighbours"
        if (owner[a] < 0 and owner[b] < 0) or FOREIGN in (owner[a], owner[b]):
            return "not on Serbian land"
        return None if 0 <= c < ncls else "class"

    for key, ncls in (("roads", len(doc["road_classes"])), ("rail", len(doc["rail_tiers"]))):
        links = doc[key]
        bad = [(l, why) for l in links if (why := bad_link(l, ncls))]
        dup = len(links) - len({tuple(l[:2]) for l in links})
        if bad or dup:
            out.append(("FAIL", f"infrastructure.json {key}: {len(bad)} bad links (e.g. {bad[:2]}), {dup} duplicates"))
        else:
            out.append(("PASS", f"infrastructure.json {key}: {len(links)} neighbour links on "
                                f"{len({c for l in links for c in l[:2]})} hexes"))
    for key in ("ports", "airports"):
        probs = [s.get("id") for s in doc[key] if not (isinstance(s.get("cell"), int) and owner[s["cell"]] >= 0)]
        out.append(("FAIL", f"infrastructure.json {key}: cells not on Serbian land: {probs[:3]}") if probs
                   else ("PASS", f"infrastructure.json {key}: {len(doc[key])} sites"))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"infrastructure.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
