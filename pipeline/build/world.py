"""The map itself: hex grid, land/water, relief, land cover, okruzi, municipalities, rivers.

Also saves interim "_world" (grid + projection + per-cell okrug/municipality/water/cover)
so the other builders can drop their data onto the same hexes. world.json keeps the
upstream key names: its "states" are the okruzi and its "counties" the municipalities.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import KM_PER_UNIT, MapProjection, Shape, ShapeIndex
from ..core.hexgrid import SQRT3, HexGrid
from ..core.store import load_interim, save_interim, write_web
from .okruzi import OKRUZI
from .units import map_units, stat_codes

REQUIRES = ["boundaries", "natural_earth", "etopo", "landcover", "osm_rivers", "rzs_census", "ask_kosovo"]
PRODUCES = ["_world", "world.json"]

HEX_RADIUS = 25.0  # map units: 3 km
MARGIN = 250.0  # map units of neighbouring land around Serbia: 30 km

# Cell owner codes (besides okrug index >= 0)
WATER, FOREIGN = -1, -2

# --- tables (written to world.json so the frontend and Almanac read one definition) ---------

LAND, OCEAN, COAST, LAKE = range(4)
LAKE_MIN_SHARE = 0.5  # CORINE water share that makes a hex a lake: reservoirs and the Danube's widest reaches
WATER_TABLE = [
    {"id": LAND, "name": "Land", "rule": "At least 4 of the hex's 7 sample points (centre + 6) fall on land, and CORINE water covers less than half of it."},
    {"id": LAKE, "name": "Lake", "color": "#3a80b0", "rule": "CORINE inland water (water courses and bodies) covers at least half of the hex, or most of its 7 sample points fall in Natural Earth lakes: reservoirs such as Đerdap and Vlasina, and the Danube where it is wider than about 1.5 km."},
]
WATER_NOTE = (
    "Serbia has no coast, so every hex is land or lake. Rivers narrower than about 2 km are drawn as lines over land "
    "hexes; where the Danube widens (Đerdap, Golubac, below Belgrade) its hexes become water."
)

FLAT, HILLS, MOUNTAINS, PEAKS = range(4)
HILLS_STD_M, MOUNTAINS_STD_M = 30, 110
MOUNTAINS_MEAN_M, PEAKS_MEAN_M = 1400, 1900
RELIEF_TABLE = [
    {"id": FLAT, "name": "Flat", "rule": f"Elevation standard deviation inside the hex under {HILLS_STD_M} m."},
    {"id": HILLS, "name": "Hills", "rule": f"Elevation standard deviation ≥ {HILLS_STD_M} m."},
    {"id": MOUNTAINS, "name": "Mountains", "rule": f"Elevation standard deviation ≥ {MOUNTAINS_STD_M} m, or mean elevation ≥ {MOUNTAINS_MEAN_M:,} m."},
    {"id": PEAKS, "name": "Peaks", "rule": f"Mean elevation ≥ {PEAKS_MEAN_M:,} m (alpine: Šar, Prokletije, the top of Kopaonik)."},
]
RELIEF_NOTE = (
    "From the elevation samples inside each 3 km hex. A hex whose lower 60% of samples is flat lowland is eased one "
    "class (valley floors). Water hexes are always flat."
)

URBAN_MIN_PCT = 30
# id, key, name, colour, CORINE codes, rule. Ids are fixed by docs/DATA_CONTRACTS.md.
COVER = [
    (1, "forest_deciduous", "Deciduous forest", "#4f7a35", [311], "Forest is the largest group and broad-leaved (311) the largest forest type."),
    (2, "forest_evergreen", "Conifer forest", "#2f5a3a", [312], "Forest is the largest group and coniferous (312) the largest forest type."),
    (3, "forest_mixed", "Mixed forest", "#43703f", [313, 324, 244], "Forest is the largest group and mixed forest (313), woodland-shrub (324) or agro-forestry (244) the largest type."),
    (4, "scrub", "Scrub", "#c9b07a", [323, 334], "Sclerophyllous vegetation (323) or burnt areas (334) are the largest group."),
    (5, "grassland", "Grassland", "#a9b35a", [321, 322, 333, 141, 142], "Natural grassland (321), heath (322), sparse vegetation (333) and urban green or sports grounds (141, 142) are the largest group."),
    (6, "pasture", "Pasture", "#8fb04e", [231, 243], "Pastures (231) and farmland mixed with natural vegetation (243) are the largest group."),
    (7, "cropland", "Cropland", "#c2b84e", [211, 212, 213, 221, 222, 223, 241, 242], "Arable land, vineyards, orchards and mixed cultivation (211–242) are the largest group."),
    (8, "wetland", "Wetland", "#4f8a6e", [411, 412], "Inland marshes and peat bogs (411, 412) are the largest group."),
    (9, "urban", "Urban", "#8a8378", [111, 112, 121, 122, 123, 124, 133], f"Urban fabric, industry, transport and construction sites (111–124, 133) are ≥ {URBAN_MIN_PCT}% of the hex's land, whatever else is there."),
    (10, "barren", "Barren", "#bfae95", [131, 132, 331, 332], "Mines, dumps, sand and bare rock (131, 132, 331, 332) are the largest group: the open-pit mines of Kolubara, Kostolac and Bor show up here."),
    (11, "ice", "Ice & snow", "#e8eef2", [335], "Glaciers and perpetual snow (335) are the largest group."),
]
COVER_NOTE = (
    "From CORINE Land Cover 2018 (100 m), sampled on a 240 m lattice inside each hex (about 400 points). Water (511, "
    "512) and no-data points are ignored; shares are of the remaining land points, rounded to whole percent, and the "
    "urban threshold is applied to the rounded developed share."
)
CLC_WATER = (511, 512)
CLC_DEVELOPED = tuple(COVER[8][4])
# Groups competing for the dominant cover (urban is decided by its threshold first).
GROUPS = {
    "forest": (311, 312, 313, 324, 244), "scrub": tuple(COVER[3][4]), "grassland": tuple(COVER[4][4]),
    "pasture": tuple(COVER[5][4]), "cropland": tuple(COVER[6][4]), "wetland": tuple(COVER[7][4]),
    "barren": tuple(COVER[9][4]), "ice": tuple(COVER[10][4]),
}
FOREST_ID = {311: 1, 312: 2, 313: 3, 324: 3, 244: 3}
GROUP_ID = {"scrub": 4, "grassland": 5, "pasture": 6, "cropland": 7, "wetland": 8, "barren": 10, "ice": 11}
URBAN_ID = 9
PCT = {
    "forest": GROUPS["forest"], "crop": GROUPS["cropland"], "pasture": GROUPS["pasture"],
    "grass": GROUPS["grassland"], "shrub": GROUPS["scrub"], "wetland": GROUPS["wetland"], "developed": CLC_DEVELOPED,
}
COVER_STEP = 2.0  # map units


def classify_relief(mean: float, std: float) -> int:
    if mean >= PEAKS_MEAN_M:
        return PEAKS
    if std >= MOUNTAINS_STD_M or mean >= MOUNTAINS_MEAN_M:
        return MOUNTAINS
    if std >= HILLS_STD_M:
        return HILLS
    return FLAT


def is_valley_floor(samples: list) -> bool:
    """True when the lower 60% of a hex's samples is flat lowland (within 25 m, under 400 m): the hex is mostly
    valley floor even if a ridge at its edge makes the whole hex's spread look hilly."""
    if len(samples) < 6:
        return False
    v = sorted(samples)
    lo = v[: max(3, int(len(v) * 0.6))]
    return lo[-1] < 400 and lo[-1] - lo[0] < 25


def dominant_cover(counts: Counter, land: int) -> int:
    """Cover id for a hex from its CORINE class counts (land = points that are not water or no-data)."""
    if not land:
        return 0
    if round(100 * sum(counts[c] for c in CLC_DEVELOPED) / land) >= URBAN_MIN_PCT:  # same rounding as pct.developed
        return URBAN_ID
    best, best_n = None, 0
    for g, codes in GROUPS.items():  # dict order breaks ties
        n = sum(counts[c] for c in codes)
        if n > best_n:
            best, best_n = g, n
    if best is None:
        return 0  # only developed land below the urban threshold
    if best == "forest":
        kind = max(FOREST_ID, key=lambda c: counts[c])
        return FOREST_ID[kind]
    return GROUP_ID[best]


def simplify(points: list[tuple[float, float]], min_km: float) -> list[tuple[float, float]]:
    out = [points[0]]
    for p in points[1:-1]:
        if math.dist(p, out[-1]) >= min_km:
            out.append(p)
    out.append(points[-1])
    return out


def clip_segment(p, q, w, h):
    """Liang–Barsky: the part of segment p→q inside [0,w]×[0,h], or None."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, x0), (dx, w - x0), (-dy, y0), (dy, h - y0)):
        if pk == 0:
            if qk < 0:
                return None
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def clip_polyline(pts, w, h) -> list[list[tuple[float, float]]]:
    """Split a polyline into the pieces that lie inside the map rectangle."""
    pieces, cur = [], []
    for p, q in zip(pts, pts[1:]):
        seg = clip_segment(p, q, w, h)
        if seg is None:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = []
            continue
        a, b = seg
        if cur and math.dist(cur[-1], a) < 1e-9:
            cur.append(b)
        else:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = [a, b]
        if b != q:  # left the map inside this segment
            pieces.append(cur)
            cur = []
    if len(cur) >= 2:
        pieces.append(cur)
    return pieces


def land_runs(pts, is_land, step: float = 2.0) -> list[list[tuple[float, float]]]:
    """Split a projected polyline (densified every `step` units) into the runs whose points satisfy is_land."""
    runs, cur = [], []
    for k, (p, q) in enumerate(zip(pts, pts[1:])):
        n = max(1, math.ceil(math.dist(p, q) / step))
        for j in range(0 if k == 0 else 1, n + 1):
            t = j / n
            pt = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
            if is_land(pt):
                cur.append(pt)
            else:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def join_lines(lines: list[list[tuple[float, float]]], tol: float = 0.5) -> list[list[tuple[float, float]]]:
    """Greedily join polylines whose ends meet (within `tol` units), reversing pieces as needed."""
    lines = [list(l) for l in lines]
    joined = True
    while joined:
        joined = False
        for a in range(len(lines)):
            for b in range(len(lines)):
                if a == b or not lines[a] or not lines[b]:
                    continue
                la, lb = lines[a], lines[b]
                for la2, lb2 in ((la, lb), (la, lb[::-1]), (la[::-1], lb), (la[::-1], lb[::-1])):
                    if math.dist(la2[-1], lb2[0]) <= tol:
                        lines[a] = la2 + lb2[1:]
                        lines[b] = []
                        joined = True
                        break
        lines = [l for l in lines if l]
    return lines


def hex_lattice(radius: float, step: float) -> list[tuple[float, float]]:
    """Offsets of a square lattice (spacing `step`) that fall inside a pointy-top hex."""
    half_w = SQRT3 / 2 * radius
    n = int(radius // step) + 1
    out = []
    for iy in range(-n, n + 1):
        for ix in range(-n, n + 1):
            x, y = (ix + 0.5) * step, (iy + 0.5) * step
            if abs(x) <= half_w and abs(y) <= radius - abs(x) / SQRT3:
                out.append((x, y))
    return out


def majority(values: list, centre) -> object:
    """Most common value; ties go to `centre` if it is among the tied, else to the first seen."""
    counts = Counter(values)
    top = max(counts.values())
    tied = [v for v in counts if counts[v] == top]
    return centre if centre in tied else tied[0]


def elevation_samples(etopo: dict):
    """(lat, lon, alt) for every sample, from either the list form or the compact row-major lattice."""
    if "alt" in etopo and "lat" in etopo and isinstance(etopo["lat"], list):
        yield from zip(etopo["lat"], etopo["lon"], etopo["alt"])
        return
    lat0, dlat, lon0, dlon, cols = etopo["lat0"], etopo["dlat"], etopo["lon0"], etopo["dlon"], etopo["cols"]
    for k, alt in enumerate(etopo["alt"]):
        if alt is not None:
            r, c = divmod(k, cols)
            yield lat0 + r * dlat, lon0 + c * dlon, alt


def build() -> None:
    bounds = load_interim("boundaries")
    ne = load_interim("natural_earth")
    etopo = load_interim("etopo")
    lc = load_interim("landcover")
    osm_rivers = load_interim("osm_rivers")

    okruzi = sorted(OKRUZI, key=lambda o: o["code"])
    okrug_index = {o["code"]: k for k, o in enumerate(okruzi)}
    units = map_units(bounds, stat_codes(load_interim("rzs_census"), load_interim("ask_kosovo")))
    unit_okrug = [okrug_index[u["okrug_code"]] for u in units]

    # Projection: fit Serbia with a margin.
    probe = MapProjection(0, 0, 0)
    xs, ys = [], []
    for u in units:
        for ring in u["rings"]:
            for lon, lat in ring:
                x, y = probe.units(lon, lat)
                xs.append(x)
                ys.append(y)
    proj = MapProjection(min(xs), max(ys), MARGIN)
    width = max(xs) - min(xs) + 2 * MARGIN
    height = max(ys) - min(ys) + 2 * MARGIN
    grid = HexGrid.covering(width, height, HEX_RADIUS)
    print(f"    grid {grid.cols}×{grid.rows} = {grid.size} hexes of {HEX_RADIUS * KM_PER_UNIT:g} km")

    def shape(rings):
        return Shape([[proj(lon, lat) for lon, lat in r] for r in rings])

    unit_idx = ShapeIndex([shape(u["rings"]) for u in units], cell_km=100)
    serbia_idx = ShapeIndex([shape(ne["serbia"]["rings"])], cell_km=200)
    lake_idx = ShapeIndex([shape(l["rings"]) for l in ne["lakes"]])

    # --- land cover: CORINE class counts per hex (also the lake test) ------------------------------
    rows, legend = lc["rows"], lc["legend"]
    x0, dx, y0, dy = lc["x0"], lc["dx"], lc["y0"], lc["dy"]
    ncols, nrows = lc["cols"], len(rows)
    lattice = hex_lattice(HEX_RADIUS, COVER_STEP)
    cover_counts: list[Counter] = []
    for i in range(grid.size):
        cx, cy = grid.center(*grid.col_row(i))
        counts: Counter = Counter()
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            c, r = int((lon - x0) / dx), int((lat - y0) / dy)
            if 0 <= c < ncols and 0 <= r < nrows:
                counts[rows[r][c]] += 1
        cover_counts.append(Counter({int(legend[ch]): n for ch, n in counts.items() if legend.get(ch) is not None}))
    water_share = [sum(c[k] for k in CLC_WATER) / len(lattice) for c in cover_counts]

    # --- elevation statistics per hex --------------------------------------------------------------
    stats = [[0, 0.0, 0.0] for _ in range(grid.size)]
    samples = [[] for _ in range(grid.size)]
    for lat, lon, alt in elevation_samples(etopo):
        i = grid.cell_at(*proj(lon, lat))
        if i < 0:
            continue
        st = stats[i]
        st[0] += 1
        st[1] += alt
        st[2] += alt * alt
        samples[i].append(alt)

    def mean_std(st):
        n, s1, s2 = st
        if not n:
            return None, None
        m = s1 / n
        return m, math.sqrt(max(0.0, s2 / n - m * m))

    # --- ownership: majority of 7 sample points --------------------------------------------------
    # The centre plus six points 60% of the way to each corner. Each point is lake, a municipality, Serbia without a
    # municipality (a gap between the two boundary sets), or foreign land; the majority decides (the centre breaks
    # ties). All seven also give an area-weighted municipality mix for lenses.
    offsets = [(0.0, 0.0)] + [
        (0.6 * HEX_RADIUS * math.cos(math.radians(60 * k - 30)), 0.6 * HEX_RADIUS * math.sin(math.radians(60 * k - 30)))
        for k in range(6)
    ]
    GAP = "gap"
    owner = [FOREIGN] * grid.size
    water = [LAND] * grid.size
    county_samples: list[list[int]] = [[] for _ in range(grid.size)]
    for i in range(grid.size):
        cx, cy = grid.center(*grid.col_row(i))
        kinds, smp = [], []
        for ox, oy in offsets:
            x, y = cx + ox, cy + oy
            u = unit_idx.locate(x, y)
            smp.append(u)
            if lake_idx.locate(x, y) >= 0:
                kinds.append("lake")
            elif u >= 0:
                kinds.append(unit_okrug[u])
            elif serbia_idx.locate(x, y) >= 0:
                kinds.append(GAP)
            else:
                kinds.append(FOREIGN)
        if water_share[i] >= LAKE_MIN_SHARE or kinds.count("lake") * 2 > len(kinds):
            owner[i], water[i] = WATER, LAKE
            continue
        land = [k for k in kinds if k != "lake"]
        home = [k for k in land if k != FOREIGN]
        if len(home) * 2 > len(land) or (len(home) * 2 == len(land) and kinds[0] != FOREIGN):
            okr = [k for k in home if k != GAP]
            owner[i] = majority(okr, kinds[0]) if okr else GAP
            county_samples[i] = smp
    # Hexes inside Serbia whose samples all miss the municipalities borrow the most common municipality of their
    # neighbours for the centre sample, and its okrug.
    borrowed = 0
    for i in range(grid.size):
        smp = county_samples[i]
        if smp and max(smp) < 0:
            nb = [k for j in grid.neighbours(i) for k in county_samples[j] if k >= 0]
            if nb:
                smp[0] = Counter(nb).most_common(1)[0][0]
                borrowed += 1
        if owner[i] == GAP:
            valid = [k for k in smp if k >= 0]
            owner[i] = unit_okrug[Counter(valid).most_common(1)[0][0]] if valid else FOREIGN
            if owner[i] == FOREIGN:
                county_samples[i] = []

    # The hex's municipality must lie in its okrug: the centre if it does, else the most common in-okrug sample.
    county = [-1] * grid.size
    for i, smp in enumerate(county_samples):
        valid = [k for k in smp if k >= 0]
        if not valid:
            continue
        same = [k for k in valid if unit_okrug[k] == owner[i]] or valid
        county[i] = smp[0] if smp[0] in same else Counter(same).most_common(1)[0][0]
    print(f"    {borrowed} hexes borrowed a neighbour's municipality")

    # --- elevation and relief --------------------------------------------------------------------
    elev = [0] * grid.size
    relief = [FLAT] * grid.size
    elev_max = [0] * grid.size
    valley_floor = no_elev = 0
    for i in range(grid.size):
        m, sd = mean_std(stats[i])
        if m is None:
            no_elev += 1
            continue
        elev[i] = round(m)
        if water[i] != LAND:
            continue
        relief[i] = classify_relief(m, sd)
        if relief[i] in (HILLS, MOUNTAINS) and is_valley_floor(samples[i]):
            relief[i] -= 1
            valley_floor += 1
        elev_max[i] = max(0, round(max(samples[i])))
    print(f"    {no_elev} hexes without elevation samples; {valley_floor} valley-floor hexes eased one relief class")

    # --- land cover ------------------------------------------------------------------------------
    cover = [0] * grid.size
    pct = {k: [0] * grid.size for k in PCT}
    no_cover = 0
    for i, counts in enumerate(cover_counts):
        if water[i] != LAND:
            continue
        land = sum(n for code, n in counts.items() if code not in CLC_WATER)
        cover[i] = dominant_cover(counts, land)
        if not land:
            no_cover += 1
            continue
        for k, codes in PCT.items():
            pct[k][i] = round(100 * sum(counts[c] for c in codes) / land)
    print(f"    {len(lattice)} CORINE points per hex; {no_cover} land hexes without land-cover samples")

    # --- rivers ----------------------------------------------------------------------------------
    def on_land(pt):
        c = grid.cell_at(*pt)
        return c >= 0 and water[c] == LAND

    # Rivers are drawn over land only: across a lake hex (Đerdap, the Danube's widest reaches) the water is the river.
    by_river: dict[tuple, list] = {}
    for r in osm_rivers["rivers"]:
        line = [proj(lon, lat) for lon, lat in r["line"]]
        parts = [run for p in clip_polyline(line, width, height) for run in land_runs(p, on_land)]
        by_river.setdefault((r["name"], r["name_lat"], r["rank"]), []).extend(parts)
    rivers = []
    for (name, name_lat, rank), parts in by_river.items():
        for piece in join_lines(parts, tol=4.0):
            if sum(math.dist(a, b) for a, b in zip(piece, piece[1:])) < 8.0:
                continue  # a corner clipped down to nothing
            pts = simplify(piece, 4.0)
            if len(pts) >= 2:
                rivers.append({"name": name, "name_lat": name_lat, "rank": rank,
                               "pts": [round(v, 1) for p in pts for v in p]})

    cover_table = [{"id": 0, "key": "none", "name": "None", "rule": "Water, or no CORINE land pixels."}] + [
        {"id": cid, "key": key, "name": name, "color": color, "clc": codes, "rule": rule}
        for cid, key, name, color, codes, rule in COVER
    ]
    tables = {
        "water": WATER_TABLE,
        "relief": RELIEF_TABLE,
        "cover": cover_table,
        "notes": {"water": WATER_NOTE, "relief": RELIEF_NOTE, "cover": COVER_NOTE},
    }
    write_web(
        "world.json",
        {
            "version": 2,
            "km_per_unit": KM_PER_UNIT,
            "grid": grid.to_dict(),
            "width": round(width, 1),
            "height": round(height, 1),
            "margin": MARGIN,
            "owner": owner,
            "county": county,
            "elev": elev,
            "elev_max": elev_max,
            "water": water,
            "relief": relief,
            "cover": cover,
            "pct": pct,
            "tables": tables,
            "states": [{"fips": o["code"], "abbr": o["abbr"], "name": o["name_cyr"], "name_lat": o["name_lat"]} for o in okruzi],
            "counties": [{"geoid": u["code"], "name": u["name_cyr"], "name_lat": u["name_lat"]} for u in units],
            "rivers": rivers,
        },
    )
    save_interim(
        "_world",
        {
            "grid": grid.to_dict(),
            "projection": proj.to_dict(),
            "owner": owner,
            "county": county,
            "county_samples": county_samples,
            "states": [o["code"] for o in okruzi],
            "counties": [u["code"] for u in units],
            "water": water,
            "cover": cover,
            "pct": pct,
        },
    )
