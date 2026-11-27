"""Planar polygon helpers for the boundaries source, standard library only.

Coordinates are integers (projected metres × a scale), so a vertex shared by two neighbouring
polygons compares equal exactly: dissolve() and simplify_coverage() rely on that. Rings are
closed (ring[0] == ring[-1]); oriented() makes outers counter-clockwise and holes clockwise.

Not a source itself (no Source subclass), so the registry ignores it.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Hashable, Iterable

Point = tuple[int, int]
Ring = list[Point]

_PAREN = re.compile(r"[()]")


# --- reading -----------------------------------------------------------------


def _ring(text: str, scale: float) -> Ring:
    pts: Ring = []
    for tok in text.split(","):
        x, y = tok.split()[:2]
        p = (round(float(x) * scale), round(float(y) * scale))
        if not pts or p != pts[-1]:
            pts.append(p)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def wkt_polygons(wkt: str, scale: float) -> list[list[Ring]]:
    """A WKT POLYGON or MULTIPOLYGON as [[outer, hole, ...], ...]."""
    ring_depth = 3 if wkt.lstrip().upper().startswith("MULTI") else 2
    polys: list[list[Ring]] = []
    depth, start = 0, 0
    for m in _PAREN.finditer(wkt):
        if m.group() == "(":
            depth += 1
            if depth == ring_depth - 1:
                polys.append([])
            start = m.end()
        else:
            if depth == ring_depth:
                polys[-1].append(_ring(wkt[start:m.start()], scale))
            depth -= 1
    return polys


def join_ways(ways: Iterable[list[Point]]) -> list[Ring]:
    """Chain OSM way geometries into closed rings by their end points (roles are not needed under even-odd)."""
    rings, pool = [], []
    for w in ways:
        if len(w) >= 4 and w[0] == w[-1]:
            rings.append(list(w))
        elif len(w) >= 2:
            pool.append(list(w))
    while pool:
        cur = pool.pop()
        while cur[0] != cur[-1]:
            for i, w in enumerate(pool):
                if w[0] == cur[-1]:
                    cur += w[1:]
                elif w[-1] == cur[-1]:
                    cur += w[-2::-1]
                else:
                    continue
                pool.pop(i)
                break
            else:
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
    return rings


# --- rings -------------------------------------------------------------------


def area2(ring: Ring) -> int:
    """Twice the signed area (positive = counter-clockwise)."""
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))


def oriented(polys: list[list[Ring]]) -> list[Ring]:
    out = []
    for poly in polys:
        for k, r in enumerate(poly):
            a = area2(r) if len(r) >= 4 else 0
            if a:
                out.append(r if (a > 0) == (k == 0) else r[::-1])
    return out


def contains(rings: list[Ring], x: float, y: float) -> bool:
    inside = False
    for r in rings:
        for (xa, ya), (xb, yb) in zip(r, r[1:]):
            if (ya > y) != (yb > y) and x < (xb - xa) * (y - ya) / (yb - ya) + xa:
                inside = not inside
    return inside


def bbox(rings: list[Ring]) -> tuple[int, int, int, int]:
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    return min(xs), min(ys), max(xs), max(ys)


def _chain(succ: dict[Point, list[Point]]) -> list[Ring]:
    rings = []
    for start in list(succ):
        while succ[start]:
            ring, cur = [start], start
            while succ[cur]:
                cur = succ[cur].pop()
                ring.append(cur)
                if cur == start:
                    break
            if cur == start and len(ring) >= 4:
                rings.append(ring)
    return rings


def dissolve(rings: Iterable[Ring]) -> list[Ring]:
    """Union of oriented, non-overlapping polygons that share boundary vertices exactly.

    An edge walked both ways (a boundary between two members) cancels; what is left is
    chained back into rings, so the signed area is preserved."""
    net: Counter = Counter()
    for r in rings:
        for a, b in zip(r, r[1:]):
            if a != b:
                net[(a, b)] += 1
    succ: dict[Point, list[Point]] = defaultdict(list)
    for (a, b), n in net.items():
        for _ in range(n - net.get((b, a), 0)):
            succ[a].append(b)
    return _chain(succ)


def intersect(subject: Ring, clip: Ring) -> tuple[Ring, list[Ring], dict[tuple[Point, Point], list[Point]]]:
    """subject ∩ clip for two simple counter-clockwise rings (Greiner-Hormann).

    Returns the subject with the crossing points inserted (so dissolve() can subtract the
    pieces from it), the pieces, and {subject edge: crossing points on it, in order} so the
    neighbours' copies of those edges can be split the same way. The clip is nudged off the
    integer grid, which keeps vertices off the other ring's edges."""
    s = subject[:-1]
    c = [(x + 0.31, y + 0.17) for x, y in clip[:-1]]
    c_boxes = [(min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])) for p, q in zip(c, c[1:] + c[:1])]
    on_s, on_c = defaultdict(list), defaultdict(list)
    points = []
    for i, (p0, p1) in enumerate(zip(s, s[1:] + s[:1])):
        x0, x1, y0, y1 = min(p0[0], p1[0]), max(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[1], p1[1])
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        for j, (bx0, bx1, by0, by1) in enumerate(c_boxes):
            if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                continue
            q0, q1 = c[j], c[(j + 1) % len(c)]
            ex, ey = q1[0] - q0[0], q1[1] - q0[1]
            d = dx * ey - dy * ex
            if d == 0:
                continue
            a = ((q0[0] - p0[0]) * ey - (q0[1] - p0[1]) * ex) / d
            b = ((q0[0] - p0[0]) * dy - (q0[1] - p0[1]) * dx) / d
            if 0 < a < 1 and 0 < b < 1:
                h = len(points)
                points.append((round(p0[0] + a * dx), round(p0[1] + a * dy)))
                on_s[i].append((a, h))
                on_c[j].append((b, h))
    c_closed = c + c[:1]
    if not points:
        if contains([c_closed], *s[0]):
            return subject, [subject], {}
        return subject, [clip] if contains([subject], *c[0]) else [], {}

    def walk(ring, inside, hits):
        nodes, entry, pos = [], {}, {}
        for i, p in enumerate(ring):
            nodes.append((p, None))
            for _, h in sorted(hits.get(i, ())):
                entry[h], inside = not inside, not inside
                pos[h] = len(nodes)
                nodes.append((points[h], h))
        return nodes, entry, pos

    s_nodes, s_entry, s_pos = walk(s, contains([c_closed], *s[0]), on_s)
    c_nodes, c_entry, c_pos = walk(clip[:-1], contains([subject], *c[0]), on_c)
    lists = ((s_nodes, s_entry, s_pos), (c_nodes, c_entry, c_pos))
    pieces, done = [], set()
    for start in range(len(points)):
        if start in done:
            continue
        ring, side, h = [], 0, start
        while True:
            nodes, entry, pos = lists[side]
            done.add(h)
            ring.append(points[h])
            step, k = (1 if entry[h] else -1), pos[h]
            while True:
                k = (k + step) % len(nodes)
                p, nxt = nodes[k]
                if nxt is not None:
                    break
                ring.append(p)
            if nxt == start:
                break
            h, side = nxt, 1 - side
        ring.append(ring[0])
        pieces.append(ring if area2(ring) > 0 else ring[::-1])
    split = {}
    for i, hits in on_s.items():
        split[(s[i], s[(i + 1) % len(s)])] = [points[h] for _, h in sorted(hits)]
    with_hits = [p for p, _ in s_nodes] + [s[0]]
    return with_hits, pieces, split


def split_edges(rings: list[Ring], split: dict[tuple[Point, Point], list[Point]]) -> list[Ring]:
    """Insert the points of `split` (edge a→b: points from a to b) into these rings' edges, either way round."""
    if not split:
        return rings
    out = []
    for r in rings:
        ring = [r[0]]
        for a, b in zip(r, r[1:]):
            if (a, b) in split:
                ring += split[(a, b)]
            elif (b, a) in split:
                ring += split[(b, a)][::-1]
            ring.append(b)
        out.append(ring)
    return out


# --- topology-preserving simplification ----------------------------------------


def _douglas_peucker(pts: list[Point], tol2: float) -> list[Point]:
    n = len(pts)
    if n <= 2:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        (x0, y0), (x1, y1) = pts[i], pts[j]
        dx, dy = x1 - x0, y1 - y0
        seg2 = dx * dx + dy * dy
        best, best_k = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / seg2))
            ex, ey = x0 + t * dx - px, y0 + t * dy - py
            d = ex * ex + ey * ey
            if d > best:
                best, best_k = d, k
        if best > tol2:
            keep[best_k] = True
            stack += [(i, best_k), (best_k, j)]
    return [p for p, k in zip(pts, keep) if k]


def _simplify_arc(arc: tuple[Point, ...], tol2: float) -> list[Point]:
    if arc[0] != arc[-1]:
        return _douglas_peucker(list(arc), tol2)
    x0, y0 = arc[0]
    far = max(range(len(arc)), key=lambda k: (arc[k][0] - x0) ** 2 + (arc[k][1] - y0) ** 2)
    return _douglas_peucker(list(arc[: far + 1]), tol2) + _douglas_peucker(list(arc[far:]), tol2)[1:]


def simplify_coverage(shapes: dict[Hashable, list[Ring]], tol: float) -> dict[Hashable, list[Ring]]:
    """Douglas-Peucker every shared boundary once, so neighbours stay seamless.

    Rings are cut into arcs at junctions (vertices whose neighbours differ between the rings
    passing through them); each distinct arc is simplified once and the rings are rebuilt from
    the simplified arcs. Rings that collapse (fewer than 3 vertices, or no area) are dropped."""
    first_pair: dict[Point, tuple[Point, Point]] = {}
    junctions: set[Point] = set()
    for rings in shapes.values():
        for r in rings:
            n = len(r) - 1
            for i in range(n):
                a, b = r[i - 1] if i else r[n - 1], r[i + 1]
                pair = (a, b) if a < b else (b, a)
                if first_pair.setdefault(r[i], pair) != pair:
                    junctions.add(r[i])

    arc_ids: dict[tuple[Point, ...], int] = {}
    plans: dict[Hashable, list[list[tuple[int, bool]]]] = {}
    for key, rings in shapes.items():
        plans[key] = []
        for r in rings:
            n = len(r) - 1
            cuts = [i for i in range(n) if r[i] in junctions]
            if cuts:
                seq = r[cuts[0]:n] + r[: cuts[0] + 1]
                cuts = [c - cuts[0] for c in cuts] + [n]
                pieces = [tuple(seq[s : e + 1]) for s, e in zip(cuts, cuts[1:])]
            else:
                k = min(range(n), key=r.__getitem__)
                pieces = [tuple(r[k:n] + r[: k + 1])]
            plan = []
            for arc in pieces:
                rev = arc[::-1]
                backwards = rev < arc
                plan.append((arc_ids.setdefault(rev if backwards else arc, len(arc_ids)), backwards))
            plans[key].append(plan)

    tol2 = tol * tol
    simple = [None] * len(arc_ids)
    for arc, i in arc_ids.items():
        simple[i] = _simplify_arc(arc, tol2)

    out: dict[Hashable, list[Ring]] = {}
    for key, plan_rings in plans.items():
        out[key] = []
        for plan in plan_rings:
            ring: Ring = []
            for i, backwards in plan:
                pts = simple[i][::-1] if backwards else simple[i]
                ring += pts if not ring else pts[1:]
            if len(set(ring)) >= 3 and area2(ring):
                out[key].append(ring)
    return out


# --- scanline overlay -----------------------------------------------------------


def _crossings(shapes: dict[Hashable, list[Ring]], y0: float, step: float, lines: int):
    """Per scanline y = y0 + (k + 0.5)·step: {key: sorted x where the key's rings cross it}."""
    cross = [defaultdict(list) for _ in range(lines)]
    for key, rings in shapes.items():
        for r in rings:
            for (xa, ya), (xb, yb) in zip(r, r[1:]):
                if ya == yb:
                    continue
                lo, hi = (ya, yb) if ya < yb else (yb, ya)
                k0 = max(0, math.ceil((lo - y0) / step - 0.5))
                k1 = min(lines, math.ceil((hi - y0) / step - 0.5))
                slope = (xb - xa) / (yb - ya)
                for k in range(k0, k1):
                    cross[k][key].append(xa + (y0 + (k + 0.5) * step - ya) * slope)
    for line in cross:
        for xs in line.values():
            xs.sort()
    return cross


def overlay(layers: list[dict[Hashable, list[Ring]]], step: float):
    """Sample the plane along horizontal lines `step` apart (even-odd per key).

    Returns one list per scanline of runs (x_from, x_to, state), state being a tuple with the
    frozenset of keys of each layer covering that run. Run length × step is its area."""
    ys = [y for layer in layers for rings in layer.values() for r in rings for _, y in r]
    y0 = min(ys)
    lines = int((max(ys) - y0) / step) + 1
    per_layer = [_crossings(layer, y0, step, lines) for layer in layers]
    result = []
    for k in range(lines):
        events = []
        for li, cross in enumerate(per_layer):
            for key, xs in cross[k].items():
                for a, b in zip(xs[::2], xs[1::2]):
                    events += [(a, 1, li, key), (b, -1, li, key)]
        events.sort(key=lambda e: e[0])
        active: list[Counter] = [Counter() for _ in layers]
        runs, x_prev = [], None
        for x, d, li, key in events:
            if x_prev is not None and x > x_prev:
                runs.append((x_prev, x, tuple(frozenset(+a) for a in active)))
            active[li][key] += d
            x_prev = x
        result.append(runs)
    return result


# --- projection -------------------------------------------------------------------


class UTM:
    """Transverse Mercator in the Krüger series form (Karney 2011), WGS84/GRS80, metres."""

    def __init__(self, zone: int, a: float = 6378137.0, f: float = 1 / 298.257223563, k0: float = 0.9996):
        n = f / (2 - f)
        self.k0a = k0 * a / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
        self.alpha = (n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16, 13 * n**2 / 48 - 3 * n**3 / 5, 61 * n**3 / 240)
        self.beta = (n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96, n**2 / 48 + n**3 / 15, 17 * n**3 / 480)
        self.delta = (2 * n - 2 * n**2 / 3 - 2 * n**3, 7 * n**2 / 3 - 8 * n**3 / 5, 56 * n**3 / 15)
        self.c = 2 * math.sqrt(n) / (1 + n)
        self.lon0 = math.radians(zone * 6 - 183)

    def forward(self, lon: float, lat: float) -> tuple[float, float]:
        s = math.sin(math.radians(lat))
        t = math.sinh(math.atanh(s) - self.c * math.atanh(self.c * s))
        dl = math.radians(lon) - self.lon0
        xi, eta = math.atan2(t, math.cos(dl)), math.atanh(math.sin(dl) / math.sqrt(1 + t * t))
        e = eta + sum(a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(self.alpha, 1))
        n = xi + sum(a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(self.alpha, 1))
        return 500000 + self.k0a * e, self.k0a * n

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        xi, eta = y / self.k0a, (x - 500000) / self.k0a
        xi_ = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(self.beta, 1))
        eta_ = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(self.beta, 1))
        chi = math.asin(math.sin(xi_) / math.cosh(eta_))
        lat = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(self.delta, 1))
        return math.degrees(self.lon0 + math.atan2(math.sinh(eta_), math.cos(xi_))), math.degrees(lat)
