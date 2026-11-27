"""Serbia's roads, railways, airports and river ports from OpenStreetMap (Overpass API), with airport passengers.

Roads and railways are the OSM ways that touch Serbia or Kosovo (their admin areas, so KiM is included), whole,
within the map window. Ways that agree on the merge key and share an end node are joined into one polyline,
then clipped to the window and simplified like the rivers; attributes outside the key take the value of at
least half the line's length, else null. Dual carriageways and double track stay two lines.

Interim `osm_transport` (data/interim/osm_transport.json, under "data"):

  roads: [{
    "class": "motorway" | "trunk" | "primary",   # OSM highway=*; *_link ramps are left out
    "ref": str | null,          # route number(s), ";"-separated: "A1", "22", "M7"; in KiM "R7", "N9", "N25.3"
                                # (merge key with class; Cyrillic look-alikes made Latin, "N-9"/"R 7" → "N9"/"R7")
    "int_ref": str | null,      # E-road(s) as tagged, e.g. "E 75" or "E 761;E 763"
    "name": str | null,
    "line": [[lon, lat], ...],
  }]                            # sorted by class, then ref
  rail: [{                      # railway=rail, usage=main|branch, no service=* (sidings, yards, spurs, crossovers)
    "usage": "main" | "branch",
    "ref": str | null,          # line number as tagged: "105", "10-B"...
    "electrified": bool | null, # electrified=no is false, any other value true
    "highspeed": bool,          # highspeed=yes
    "maxspeed": int | null,     # km/h (merge key: usage, ref, electrified, highspeed, maxspeed)
    "name": str | null,
    "line": [[lon, lat], ...],
  }]                            # sorted by usage, then ref
  airports: [{                  # aerodromes with an IATA code, military-only airfields left out
    "iata": str, "icao": str | null,
    "name": str | null,         # as tagged
    "name_sr": str | null,      # Serbian Cyrillic: name:sr, or the name if it is Cyrillic
    "name_lat": str | null,     # Serbian Latin: name:sr-Latn, or name_sr transliterated
    "lon": float, "lat": float, # centroid
    "passengers": int | null,   # in passengers_year, see PASSENGERS; null where no official figure is published
    "passengers_year": int | null,
    "osm": "way/<id>" | "relation/<id>",
  }]                          # sorted by passengers (desc, nulls last), then IATA
  ports: [{                     # the Port Governance Agency's port areas that OSM maps (PORTS)
    "name": str | null,         # as tagged in OSM; null where the OSM area is unnamed
    "name_sr": str,             # Serbian Cyrillic name of the port
    "name_lat": str,            # the same in Serbian Latin
    "river": str,               # Cyrillic, as in osm_rivers
    "lon": float, "lat": float, # centroid of the OSM port area
    "cargo_t": null, "cargo_year": null,   # no official per-port tonnage is published (see PORTS)
    "osm": "way/<id>" | "relation/<id>",
  }]

Coordinates are WGS84 lon/lat rounded to 5 decimals.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from ..core.source import Source, SourceInfo
from . import _overpass
from ._pxweb import PxTable, download_table
from ._rzs import Pdf
from .osm_rivers import WINDOW, clip, join_lines, latin, length_km, simplify

TOLERANCE_KM = 0.1  # Douglas-Peucker, as for the rivers
ROADS, RAIL, SITES = "overpass_roads.json", "overpass_rail.json", "overpass_sites.json"
ROAD_CLASSES = ("motorway", "trunk", "primary")
USAGES = ("main", "branch")

_HEAD = (
    f"[out:json][timeout:300][bbox:{WINDOW[1]},{WINDOW[0]},{WINDOW[3]},{WINDOW[2]}];"
    '(area["ISO3166-1"="RS"][admin_level=2];area["ISO3166-1"="XK"][admin_level=2];)->.s;'
)
ROADS_QL = _HEAD + f'way[highway~"^({"|".join(ROAD_CLASSES)})$"](area.s);out body geom;'
RAIL_QL = _HEAD + f'way[railway=rail][usage~"^({"|".join(USAGES)})$"][!service](area.s);out body geom;'

# The port areas (лучка подручја) the Port Governance Agency lists at https://www.aul.gov.rs/luke-i-pristanista
# (and Apatin, which it lists no more), each at the OSM area that maps it; OSM maps none at Šabac. The Agency and
# RZS publish cargo handled only as national totals (RZS bulletin "Саобраћај и телекомуникације", AUL bulletins).
PORTS = (
    ("Лука Београд", "Дунав", "relation", 18962990),
    ("Лука Нови Сад", "Дунав", "relation", 20451411),
    ("Лука Панчево", "Дунав", "way", 966211911),
    ("Лука Смедерево", "Дунав", "way", 537477193),
    ("Лука Прахово", "Дунав", "way", 326363443),
    ("Лука Бачка Паланка", "Дунав", "way", 817757373),
    ("Лука Богојево", "Дунав", "relation", 9478866),
    ("Лука Беочин", "Дунав", "way", 872343045),
    ("Лука Апатин", "Дунав", "way", 307135280),
    ("Лука Сента", "Тиса", "way", 114714125),
    ("Лука Сремска Митровица", "Сава", "way", 1499864780),
)
SITES_QL = (
    _HEAD + "nwr[aeroway=aerodrome][iata](area.s);out tags center;"
    + "(" + "".join(f"{kind}(id:{osm_id});" for *_, kind, osm_id in PORTS) + ");out tags center;"
)
REQUIRED_AIRPORTS = ("BEG", "INI", "KVO", "PRN")

# PASSENGERS in the latest full year, from official publications only:
# PRN: the Kosovo Agency of Statistics' monthly air passengers (Priština is Kosovo's only passenger airport);
# BEG: VINCI Airports' network traffic report (the airport's concessionaire), published in thousands.
# Niš, Kraljevo and Užice publish no machine-readable traffic figures; RZS publishes the national total only.
ASK_API = "https://askdata.rks-gov.net/api/v1/en/ASKdata"
ASK_TABLE = "Transport/Monthly indicators/7.numri total i udhetareve.px"
ASK_FILE = "ask/air_passengers_monthly.px"
VINCI_PDF = ("https://www.vinci.com/sites/default/files/medias/communiques/file/2026-01/"
             "vinci-airports-traffic-as-of-december-31-2025_1.pdf")
VINCI_YEAR = 2025
VINCI_FILE = "vinci/traffic_2025.pdf"

# Stations (lon, lat) each corridor must link through the selected rail network. Belgrade – Bar leaves the query
# for 9 km in Bosnia (Štrpci), and OSM has the line through Kosovska Mitrovica as disused, so those are two parts.
BEOGRAD, LAPOVO, NIS, KOSOVO_POLJE = (20.4572, 44.7866), (21.1029, 44.1829), (21.8854, 43.3283), (21.0871, 42.6436)
CORRIDORS = {
    "Београд – Нови Сад – Суботица": [BEOGRAD, (19.8297, 45.2649), (19.6743, 46.0966)],
    "Београд – Шид": [BEOGRAD, (19.2259, 45.1153)],
    "Београд – Вршац": [BEOGRAD, (20.6589, 44.8644), (21.2809, 45.1120)],
    "Београд – Ниш – Прешево": [BEOGRAD, LAPOVO, NIS, (21.6817, 42.3100)],
    "Ниш – Димитровград": [NIS, (22.5921, 43.1655), (22.7817, 43.0164)],
    "Београд – Бар: Београд – Ужице": [BEOGRAD, (19.8939, 44.2666), (20.0277, 43.8416), (19.8436, 43.8541)],
    "Београд – Бар: Прибој – Пријепоље": [(19.5306, 43.5789), (19.6403, 43.3899)],
    "Лапово – Краљево – Звечан": [LAPOVO, (20.6887, 43.7262), (20.6173, 43.2901), (20.8347, 42.9095)],
    "Косовска Митровица – Косово Поље – Ђенерал Јанковић": [
        (20.8733, 42.8849), KOSOVO_POLJE, (21.1536, 42.3687), (21.2982, 42.1519)],
    "Косово Поље – Пећ": [KOSOVO_POLJE, (20.5794, 42.6187), (20.3060, 42.6583)],
}
STATION_KM = 2.0
GAP_KM = 0.1  # OSM topology slips (way ends a few metres apart) that still count as connected
HIGHSPEED_MIN_KM = 150  # Belgrade – Subotica is 184 km

_HOMOGLYPHS = str.maketrans("АВЕКМНОРСТХ", "ABEKMHOPCTX")
_CYRILLIC = re.compile(f"[{chr(0x400)}-{chr(0x4FF)}]")


def _tag(tags: dict, key: str) -> str | None:
    return (tags.get(key) or "").strip() or None


def _cyrillic(text: str | None) -> bool:
    return bool(text and _CYRILLIC.search(text))


def _military_only(tags: dict) -> bool:
    return tags.get("military") == "airfield" and "public" not in tags.get("aerodrome:type", "")


def road_ref(tags: dict) -> str | None:
    ref = _tag(tags, "ref")
    if ref is None:
        return None
    parts = (re.sub(r"^([A-Z]+)[ -](?=\d)", r"\1", p.strip().translate(_HOMOGLYPHS).upper()) for p in ref.split(";"))
    return ";".join(p for p in parts if p) or None


def electrified(tags: dict) -> bool | None:
    value = _tag(tags, "electrified")
    return None if value is None else value != "no"


def maxspeed(tags: dict) -> int | None:
    m = re.match(r"\d+", _tag(tags, "maxspeed") or "")
    return int(m.group()) if m else None


def _road_key(tags: dict) -> dict:
    return {"class": tags["highway"], "ref": road_ref(tags)}


def _rail_key(tags: dict) -> dict:
    return {
        "usage": tags["usage"], "ref": _tag(tags, "ref"), "electrified": electrified(tags),
        "highspeed": tags.get("highspeed") == "yes", "maxspeed": maxspeed(tags),
    }


def _ways(path) -> list[tuple[dict, list[tuple[int, float, float]]]]:
    """(tags, [(node id, lon, lat)]) of every way in an Overpass answer."""
    elements = json.loads(path.read_text(encoding="utf-8"))["elements"]
    return [
        (e.get("tags", {}), [(n, p["lon"], p["lat"]) for n, p in zip(e["nodes"], e["geometry"]) if p])
        for e in elements if e["type"] == "way"
    ]


def dominant(values: list[tuple[str | None, float]]) -> str | None:
    """The value of at least half the total length in [(value, length)], else None."""
    by_value: dict = defaultdict(float)
    for v, km in values:
        by_value[v] += km
    total = sum(by_value.values())
    value, km = max(by_value.items(), key=lambda kv: kv[1], default=(None, 0.0))
    return value if total and km >= total / 2 else None


def merge(ways, key, extra: dict) -> list[dict]:
    """Polylines of the ways grouped by `key(tags)` (a dict) and joined on shared end nodes. `extra` maps the
    other fields to their tag readers; each field gets its dominant value along the line."""
    groups: dict = defaultdict(list)
    for i, (tags, pts) in enumerate(ways):
        if len(pts) >= 2:
            groups[tuple(key(tags).items())].append([(n, x, y, i) for n, x, y in pts])
    km = [length_km([(x, y) for _, x, y in pts]) for _, pts in ways]
    out = []
    for k, members in groups.items():
        for line in join_lines(members):
            used = {p[3] for p in line}
            attrs = {f: dominant([(read(ways[i][0]), km[i]) for i in used]) for f, read in extra.items()}
            for run in clip([(x, y) for _, x, y, _ in line]):
                pts = [[round(x, 5), round(y, 5)] for x, y in simplify(run, TOLERANCE_KM)]
                out.append({**dict(k), **attrs, "line": pts})
    return out


def _km(a, b) -> float:
    return length_km([a, b])


def check_corridors(ways) -> list[str]:
    """Corridors whose stations are not all within STATION_KM of one connected piece of the network."""
    parent: dict[int, int] = {}

    def root(n):
        while parent.setdefault(n, n) != n:
            parent[n] = n = parent[parent[n]]
        return n

    where: dict[int, tuple[float, float]] = {}
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for _, pts in ways:
        for (a, *pa), (b, *pb) in zip(pts, pts[1:]):
            parent[root(a)] = root(b)
            where[a], where[b] = tuple(pa), tuple(pb)
    for n, (x, y) in where.items():
        cells[(int(x * 500), int(y * 500))].append(n)  # 0.002° cells, wider than GAP_KM
    for _, pts in ways:
        for n, x, y in (pts[0], pts[-1]) if pts else ():
            cx, cy = int(x * 500), int(y * 500)
            for m in (m for dx in (-1, 0, 1) for dy in (-1, 0, 1) for m in cells[(cx + dx, cy + dy)]):
                if _km(where[m], (x, y)) <= GAP_KM:
                    parent[root(m)] = root(n)
    broken = []
    for name, stations in CORRIDORS.items():
        near = [min(where, key=lambda n: _km(where[n], s)) for s in stations]
        far = [s for s, n in zip(stations, near) if _km(where[n], s) > STATION_KM]
        if far or len({root(n) for n in near}) > 1:
            broken.append(f"{name} ({'stations off the network: ' + str(far) if far else 'not connected'})")
    return broken


def ask_passengers(path) -> tuple[int, int]:
    """(year, passengers) of the latest full year in ASK's monthly table."""
    px = PxTable(path)
    (months,) = px.variables
    by_year: dict[str, list] = defaultdict(list)
    for month, v in zip(px.values[months], px.data):
        by_year[month[:4]].append(v)
    year = max(y for y, vs in by_year.items() if len(vs) == 12 and None not in vs)
    return int(year), sum(by_year[year])


def vinci_passengers(path, label: str = "Belgrade (BEG)") -> int:
    """Full-year passengers of one airport in VINCI Airports' traffic report: its row holds the stake (%), the
    quarter and the year, in thousands, each but the stake followed by a % change."""
    pdf = Pdf(path)
    for i in range(len(pdf.pages())):
        rows: dict[int, list] = defaultdict(list)
        for x, y, text in pdf.runs(i):
            rows[round(y)].append((x, text))
        for parts in rows.values():
            text = " ".join(t for _, t in sorted(parts))
            if label in text:
                numbers = [t for t in text.split(label, 1)[1].split() if re.fullmatch(r"\d{1,3}(,\d{3})*", t)]
                if len(numbers) != 3:
                    raise ValueError(f"{path.name}: unexpected row {text!r}")
                return int(numbers[2].replace(",", "")) * 1000
    raise ValueError(f"{path.name}: no row for {label}")


def _centre(e: dict) -> tuple[float, float]:
    c = e.get("center") or e
    return round(c["lon"], 5), round(c["lat"], 5)


class OsmTransport(Source):
    info = SourceInfo(
        id="osm_transport",
        title="OpenStreetMap roads, railways, airports and ports of Serbia",
        publisher="OpenStreetMap contributors (via the Overpass API); Kosovo Agency of Statistics; VINCI Airports",
        homepage="https://www.openstreetmap.org/",
        license="© OpenStreetMap contributors, Open Database License (ODbL) 1.0; passenger counts as published by "
        "the Kosovo Agency of Statistics and VINCI Airports",
        description="Motorways, trunk and primary roads and the main and branch railway lines of Serbia, Kosovo and "
        "Metohija included, from OpenStreetMap: every way touching Serbia or Kosovo, joined into lines by route "
        f"number (roads) or line number and track attributes (rail) and simplified to {TOLERANCE_KM * 1000:.0f} m. "
        "Airports are the IATA-coded civil aerodromes; ports are the Port Governance Agency's port areas that OSM "
        "maps, at their centroid. Passengers in the latest full year come from the Kosovo Agency of Statistics "
        "(Priština) and VINCI Airports' traffic report (Belgrade, in thousands); the other airports publish no "
        "figures, and there are no official per-port cargo figures.",
        used_for=["Roads and railways on the map", "Airports and river ports"],
    )

    def fetch(self, force=False):
        _overpass.query(self, ROADS_QL, ROADS, self._lacks("highway", ROAD_CLASSES), force=force)
        _overpass.query(self, RAIL_QL, RAIL, self._lacks("usage", USAGES), force=force)
        _overpass.query(self, SITES_QL, SITES, self._sites_problem, force=force)
        download_table(self, ASK_API, ASK_TABLE, ASK_FILE, force=force)
        self.download(VINCI_PDF, VINCI_FILE, force=force, expect_binary=True)

    @staticmethod
    def _lacks(key: str, wanted: tuple[str, ...]):
        def problem(elements):
            missing = set(wanted) - {e.get("tags", {}).get(key) for e in elements}
            return f"no {key}={'|'.join(sorted(missing))}" if missing else None
        return problem

    @staticmethod
    def _sites_problem(elements):
        found = {(e["type"], e["id"]) for e in elements} | {e.get("tags", {}).get("iata") for e in elements}
        missing = [i for i in REQUIRED_AIRPORTS if i not in found]
        missing += [f"{k}/{i}" for *_, k, i in PORTS if (k, i) not in found]
        return f"missing {missing}" if missing else None

    def process(self):
        road_ways, rail_ways = _ways(self.raw_dir / ROADS), _ways(self.raw_dir / RAIL)
        if broken := check_corridors(rail_ways):
            raise ValueError(f"rail corridors broken in OSM: {broken}")
        highspeed = sum(length_km([(x, y) for _, x, y in pts]) for t, pts in rail_ways if t.get("highspeed") == "yes")
        if highspeed < HIGHSPEED_MIN_KM:
            raise ValueError(f"only {highspeed:.0f} km of high-speed rail")

        named = {"name": lambda t: _tag(t, "name")}
        roads = merge(road_ways, _road_key, {"int_ref": lambda t: _tag(t, "int_ref"), **named})
        roads.sort(key=lambda r: (ROAD_CLASSES.index(r["class"]), r["ref"] is None, r["ref"] or ""))
        rail = merge(rail_ways, _rail_key, named)
        rail.sort(key=lambda r: (USAGES.index(r["usage"]), r["ref"] is None, r["ref"] or ""))

        sites = json.loads((self.raw_dir / SITES).read_text(encoding="utf-8"))["elements"]
        airports, ports = self._airports(sites), self._ports(sites)
        years = sorted({a["passengers_year"] for a in airports if a["passengers_year"]})

        print(f"    roads: {len(roads)} lines, " + ", ".join(
            f"{c} {sum(length_km(r['line']) for r in roads if r['class'] == c):.0f} km" for c in ROAD_CLASSES))
        print(f"    rail: {len(rail)} lines, " + ", ".join(
            f"{u} {sum(length_km(r['line']) for r in rail if r['usage'] == u):.0f} km" for u in USAGES)
            + f" ({highspeed:.0f} km high-speed); {len(CORRIDORS)} corridors connected")
        print("    airports: " + ", ".join(f"{a['iata']} {a['passengers']}" for a in airports))
        print(f"    ports: {len(ports)}")
        return {
            "vintage": f"OpenStreetMap (Overpass API, retrieved {self._retrieved()}); "
            f"airport passengers {', '.join(map(str, years))} (ASK, VINCI Airports)",
            "_files": [ROADS, RAIL, SITES, ASK_FILE, VINCI_FILE],
            "roads": roads,
            "rail": rail,
            "airports": airports,
            "ports": ports,
        }

    def _airports(self, elements) -> list[dict]:
        year, prn = ask_passengers(self.raw_dir / ASK_FILE)
        counts = {"PRN": (prn, year), "BEG": (vinci_passengers(self.raw_dir / VINCI_FILE), VINCI_YEAR)}
        out = []
        for e in elements:
            t = e.get("tags", {})
            if t.get("aeroway") != "aerodrome" or _military_only(t):
                continue
            iata = t["iata"].strip()
            name, sr = _tag(t, "name"), _tag(t, "name:sr")
            sr = sr if _cyrillic(sr) else name if _cyrillic(name) else None
            passengers, passengers_year = counts.get(iata, (None, None))
            lon, lat = _centre(e)
            out.append({
                "iata": iata, "icao": _tag(t, "icao"), "name": name, "name_sr": sr,
                "name_lat": _tag(t, "name:sr-Latn") or (latin(sr) if sr else None),
                "lon": lon, "lat": lat, "passengers": passengers, "passengers_year": passengers_year,
                "osm": f"{e['type']}/{e['id']}",
            })
        return sorted(out, key=lambda a: (a["passengers"] is None, -(a["passengers"] or 0), a["iata"]))

    @staticmethod
    def _ports(elements) -> list[dict]:
        by_ref = {(e["type"], e["id"]): e for e in elements}
        out = []
        for name_sr, river, kind, osm_id in PORTS:
            e = by_ref[(kind, osm_id)]
            lon, lat = _centre(e)
            out.append({
                "name": _tag(e.get("tags", {}), "name"), "name_sr": name_sr, "name_lat": latin(name_sr),
                "river": river, "lon": lon, "lat": lat, "cargo_t": None, "cargo_year": None, "osm": f"{kind}/{osm_id}",
            })
        return out

    def _retrieved(self) -> str:
        manifest = json.loads((self.raw_dir / "manifest.json").read_text(encoding="utf-8"))
        return min(manifest[f]["retrieved"] for f in (ROADS, RAIL, SITES))[:10]
