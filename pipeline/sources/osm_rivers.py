"""Serbia's main rivers from OpenStreetMap (Overpass API): joined, clipped to the map window and simplified."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse

from ..core.source import Source, SourceInfo

WINDOW = (18.0, 41.4, 23.8, 46.6)  # west, south, east, north
TOLERANCE_KM = 0.1  # Douglas-Peucker
JOIN_GAP_KM = 1.0
MIN_LINE_KM = 2.0  # braid fragments and side arms shorter than this are dropped
OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
FILE = "overpass_rivers.json"

# Serbian name, rank (drawn width ∝ 10 - rank), Wikidata id, OSM selector: the river relation tagged with that
# Wikidata id, a relation id where OSM's relation has no Wikidata tag, or (south, west, north, east) to collect
# the named river ways in that box where OSM has no relation.
RIVERS = [
    ("Дунав", 1, "Q1653", "wikidata"),
    ("Сава", 2, "Q14383", "wikidata"),
    ("Тиса", 2, "Q134350", "wikidata"),
    ("Велика Морава", 3, "Q211328", "wikidata"),
    ("Дрина", 3, "Q186901", "wikidata"),
    ("Западна Морава", 4, "Q378985", "wikidata"),
    ("Јужна Морава", 4, "Q591974", "wikidata"),
    ("Ибар", 4, "Q392840", "wikidata"),
    ("Тимок", 5, "Q753919", "wikidata"),
    ("Лим", 5, "Q167916", "wikidata"),
    ("Колубара", 5, "Q120179", "wikidata"),
    ("Нишава", 5, "Q583062", "wikidata"),
    ("Тамиш", 5, "Q214894", "wikidata"),
    ("Бегеј", 5, "Q615051", "wikidata"),
    ("Бели Дрим", 5, "Q252385", "wikidata"),
    ("Ситница", 5, "Q1066857", 6148073),
    ("Млава", 5, "Q1468206", "wikidata"),
    ("Пек", 5, "Q1318012", (44.0, 21.4, 44.8, 22.2)),
    ("Топлица", 6, "Q2665686", "wikidata"),
    ("Пчиња", 6, "Q522077", (41.7, 21.5, 42.5, 22.3)),
    ("Јадар", 6, "Q2562056", "wikidata"),
    ("Расина", 6, "Q1752429", 16713536),
    ("Јабланица", 6, "Q1288026", (42.75, 21.3, 43.1, 22.0)),
    ("Ветерница", 6, "Q1279915", (42.5, 21.7, 43.05, 22.3)),
    ("Студеница", 6, "Q1267558", "wikidata"),
    ("Рзав", 6, "Q12749656", (43.5, 19.7, 43.85, 20.15)),
    ("Голијска Моравица", 6, "Q2510499", 16707450),
    ("Сокобањска Моравица", 6, "Q1279885", "wikidata"),
    ("Црни Тимок", 6, "Q1267588", "wikidata"),
    ("Бели Тимок", 6, "Q1564775", "wikidata"),
    ("Лепенац", 6, "Q674219", "wikidata"),
    ("Љубовиђа", 6, "Q3257455", (44.0, 19.3, 44.3, 19.8)),
    ("Увац", 6, "Q978571", "wikidata"),
    ("Рашка", 6, "Q1265868", "wikidata"),
    ("Ђетиња", 6, "Q1279841", "wikidata"),
    ("Ресава", 6, "Q1554773", "wikidata"),
    ("Јасеница", 6, "Q2562033", "wikidata"),
    ("Тамнава", 6, "Q3102812", "wikidata"),
    ("Гружа", 6, "Q3118267", "wikidata"),
    ("Биначка Морава", 6, "Q13043065", "wikidata"),
    ("Ереник", 6, "Q3299072", "wikidata"),
    ("Власина", 6, "Q1279852", "wikidata"),
    ("Босут", 6, "Q2911647", "wikidata"),
    ("Криваја", 6, "Q155657", "wikidata"),
    ("Златица", 6, "Q429217", "wikidata"),
    ("Караш", 6, "Q1104502", "wikidata"),
    ("Нера", 6, "Q571214", "wikidata"),
    ("Брзава", 6, "Q793845", "wikidata"),
]
NAME_VARIANTS = {"Рзав": ("Велики Рзав",)}  # OSM names the Arilje Rzav "Рзав" only below its last tributary

_LATIN = dict(zip(
    "абвгдђежзијклљмнњопрстћуфхцчџшАБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ",
    "a b v g d đ e ž z i j k l lj m n nj o p r s t ć u f h c č dž š "
    "A B V G D Đ E Ž Z I J K L Lj M N Nj O P R S T Ć U F H C Č Dž Š".split(),
))


def latin(cyr: str) -> str:
    return "".join(_LATIN.get(ch, ch) for ch in cyr)


def query() -> str:
    """One Overpass query: every river is a marker element followed by its ways (geometry, no tags)."""
    west, south, east, north = WINDOW
    tagged = "|".join(qid for _, _, qid, sel in RIVERS if sel == "wikidata")
    rel_ids = ",".join(str(sel) for *_, sel in RIVERS if isinstance(sel, int))
    parts = [
        f"[out:json][timeout:300][bbox:{south},{west},{north},{east}];",
        f'(rel[waterway=river][wikidata~"^({tagged})$"];rel(id:{rel_ids}););',
        'foreach->.r{.r out tags;(way(r.r:"main_stream");way(r.r:""););out skel geom;}',
    ]
    for name, _, qid, sel in RIVERS:
        if isinstance(sel, tuple):
            box = ",".join(map(str, sel))
            names = "|".join((name, latin(name), *NAME_VARIANTS.get(name, ())))
            parts.append(
                f'make river wikidata="{qid}";out;'
                f'(way[waterway=river][name~"^({names})$"]({box});way[waterway=river]["name:sr"~"^({names})$"]({box}););'
                "out skel geom;"
            )
    return "".join(parts)


def group_ways(elements: list[dict]) -> dict[str, list[list[tuple[int, float, float]]]]:
    """Ways (as [(node id, lon, lat)]) per Wikidata id of RIVERS, from the marker-then-ways element stream."""
    by_rel_id = {sel: qid for _, _, qid, sel in RIVERS if isinstance(sel, int)}
    out: dict[str, list] = {qid: [] for _, _, qid, _ in RIVERS}
    current = None
    for e in elements:
        if e["type"] == "relation":
            current = by_rel_id.get(e["id"], e.get("tags", {}).get("wikidata"))
        elif e["type"] == "river":
            current = e["tags"]["wikidata"]
        elif e["type"] == "way" and current in out:
            out[current].append([(n, p["lon"], p["lat"]) for n, p in zip(e["nodes"], e["geometry"]) if p])
    return out


def join_lines(ways: list[list]) -> list[list]:
    """Chain ways that share end nodes into as few polylines as possible (greedy at braids and confluences)."""
    pool = {i: w for i, w in enumerate(ways) if len(w) >= 2}
    ends: dict[int, set[int]] = {}
    for i, w in pool.items():
        ends.setdefault(w[0][0], set()).add(i)
        ends.setdefault(w[-1][0], set()).add(i)

    def take(node):
        for j in sorted(ends.get(node, ())):
            if j in pool:
                w = pool.pop(j)
                ends[w[0][0]].discard(j)
                ends[w[-1][0]].discard(j)
                return w if w[0][0] == node else w[::-1]
        return None

    lines = []
    while pool:
        i = min(pool)
        line = pool.pop(i)
        ends[line[0][0]].discard(i)
        ends[line[-1][0]].discard(i)
        while (nxt := take(line[-1][0])) is not None:
            line += nxt[1:]
        while (prv := take(line[0][0])) is not None:
            line = prv[::-1] + line[1:]
        lines.append(line)
    return lines


def _km(a, b) -> float:
    kx = 111.32 * math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * 110.57)


def length_km(line) -> float:
    return sum(_km(a, b) for a, b in zip(line, line[1:]))


def join_gaps(lines: list[list[tuple[float, float]]], max_km: float) -> list[list[tuple[float, float]]]:
    """Join line ends closer than max_km: OSM often breaks a river at a dam or lake with two separate nodes."""
    lines = [list(line) for line in lines]
    while True:
        best = None
        for i, a in enumerate(lines):
            for j in range(i + 1, len(lines)):
                b = lines[j]
                for flip_a, flip_b in ((False, False), (False, True), (True, False), (True, True)):
                    d = _km(a[0] if flip_a else a[-1], b[-1] if flip_b else b[0])
                    if d <= max_km and (best is None or d < best[0]):
                        best = (d, i, j, flip_a, flip_b)
        if best is None:
            return lines
        _, i, j, flip_a, flip_b = best
        a = lines[i][::-1] if flip_a else lines[i]
        b = lines[j][::-1] if flip_b else lines[j]
        lines[i] = a + b
        del lines[j]


def _edge(inside, outside) -> tuple[float, float]:
    """Where the segment from a point inside WINDOW to one outside it leaves the window (Liang-Barsky)."""
    west, south, east, north = WINDOW
    (x0, y0), (x1, y1) = inside, outside
    dx, dy = x1 - x0, y1 - y0
    t = min([1.0] + [q / p for p, q in ((-dx, x0 - west), (dx, east - x0), (-dy, y0 - south), (dy, north - y0)) if p > 0])
    return x0 + t * dx, y0 + t * dy


def clip(line: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Runs of the line inside WINDOW, cut where they cross its edge."""
    west, south, east, north = WINDOW
    inside = [west <= x <= east and south <= y <= north for x, y in line]
    runs, k = [], 0
    while k < len(line):
        if not inside[k]:
            k += 1
            continue
        start = k
        while k < len(line) and inside[k]:
            k += 1
        run = line[start:k]
        if start > 0:
            run.insert(0, _edge(line[start], line[start - 1]))
        if k < len(line):
            run.append(_edge(line[k - 1], line[k]))
        if len(run) >= 2:
            runs.append(run)
    return runs


def simplify(line: list[tuple[float, float]], tol_km: float) -> list[tuple[float, float]]:
    """Douglas-Peucker on a local equirectangular km plane (iterative, so long rivers don't hit the recursion limit)."""
    if len(line) < 3:
        return line
    kx = 111.32 * math.cos(math.radians(sum(y for _, y in line) / len(line)))
    pts = [(x * kx, y * 110.57) for x, y in line]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        far, far_d = None, tol_km
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm if norm else math.hypot(px - ax, py - ay)
            if d > far_d:
                far, far_d = i, d
        if far is not None:
            keep[far] = True
            stack += [(a, far), (far, b)]
    return [p for p, k in zip(line, keep) if k]


class OsmRivers(Source):
    info = SourceInfo(
        id="osm_rivers",
        title="OpenStreetMap rivers of Serbia",
        publisher="OpenStreetMap contributors (via the Overpass API)",
        homepage="https://www.openstreetmap.org/",
        license="© OpenStreetMap contributors, Open Database License (ODbL) 1.0",
        description="The main rivers of Serbia, Kosovo and Metohija and the rivers they share with the neighbours, "
        "from OpenStreetMap: each river's waterway relation (main stream), picked by its Wikidata id, or its named "
        "river ways where OSM has no relation. Ways are joined end to end, clipped to the map window and simplified "
        f"to {TOLERANCE_KM * 1000:.0f} m. Names are the Serbian (Cyrillic) names; the rank sets the drawn width.",
        used_for=["Rivers on the map", "River names"],
    )

    def fetch(self, force=False):
        q = query()
        last = None
        for endpoint in OVERPASS:
            try:
                path = self.download(endpoint, FILE, force=force, data=urllib.parse.urlencode({"data": q}).encode())
            except urllib.error.URLError as exc:
                last = exc
                print(f"      {endpoint} failed: {exc}")
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            missing = [qid for qid, ways in group_ways(doc.get("elements", [])).items() if not ways]
            if "error" not in doc.get("remark", "") and not missing:
                return
            last = RuntimeError(f"{endpoint}: incomplete answer ({doc.get('remark') or f'no ways for {missing}'})")
            print(f"      {last}")
            self.discard(FILE)
            force = True
        raise RuntimeError("the Overpass river query failed on every mirror") from last

    def process(self):
        elements = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))["elements"]
        ways = group_ways(elements)
        rivers, report = [], []
        for name, rank, qid, _ in RIVERS:
            joined = join_gaps([[(x, y) for _, x, y in line] for line in join_lines(ways[qid])], JOIN_GAP_KM)
            lines = [run for line in joined for run in clip(line) if length_km(run) >= MIN_LINE_KM]
            km = sum(length_km(line) for line in lines)
            if km < 5:
                raise ValueError(f"{name} ({qid}): only {km:.1f} km of OSM river inside the map window")
            simple = [[(round(x, 5), round(y, 5)) for x, y in simplify(line, TOLERANCE_KM)] for line in lines]
            rivers += [{"name": name, "name_lat": latin(name), "rank": rank, "wikidata": qid, "line": s} for s in simple]
            report.append(f"{latin(name)} {km:.0f} km/{len(lines)}")
        print(f"    {len(RIVERS)} rivers, {len(rivers)} lines in the window: " + ", ".join(report))
        return {
            "vintage": f"OpenStreetMap, Overpass API, retrieved {self._retrieved()}",
            "_files": [FILE],
            "rivers": rivers,
        }

    def _retrieved(self) -> str:
        manifest = json.loads((self.raw_dir / "manifest.json").read_text(encoding="utf-8"))
        return manifest[FILE]["retrieved"][:10]
