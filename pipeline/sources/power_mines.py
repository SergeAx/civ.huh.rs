"""Power plants and mines of Serbia, Kosovo and Metohija (KiM) included: OpenStreetMap sites, official figures.

Plants are OSM `power=plant` objects. A plant's capacity is the publisher's own figure where OFFICIAL lists it
(EPS's technical report, Kosovo's transmission operator KOSTT, the Serbian energy regulator AERS), otherwise
OSM's `plant:output:electricity`. Mines are the curated list MINES, since OSM cannot tell an operating pit from
an exhausted one: each is placed at its OSM outline (or, where OSM has none, at its Wikidata coordinates), and its
output comes only from the operator's or the regulator's published figures. The official figures were read off
the documents in DOCS, which fetch keeps a copy of so that the Almanac cites them.

Scope is the territory of the `boundaries` interim (its units' rings); a plant listed in OFFICIAL is kept even when
its OSM centre falls just across the border (the Danube and Drina dams).

Interim `power_mines` (data/interim/power_mines.json, under "data"):

  plants: [{                      # every plant of at least MIN_MW, and every fossil plant whose capacity is known
    "name": str,                  # English: the official document's name, else OSM name:en, name:sr-Latn, Latin script
    "name_sr": str | null,        # Serbian Cyrillic (official, OSM name:sr or a Cyrillic OSM name)
    "kind": "coal_plant" | "gas_plant" | "oil_plant" | "hydro" | "pumped_storage" | "wind" | "solar"
            | "waste" | "biomass",
    "capacity_mw": float,         # EPS: net output capacity; KOSTT: net rated capacity of the units in service;
                                  # AERS: installed capacity; OSM: as tagged (usually gross nameplate)
    "capacity_source": str,       # URL of that document, or of the OSM object
    "operator": str | null,       # OSM operator; EPS for a plant of its report that OSM gives none
    "lon": float, "lat": float,   # OSM centre
    "in_kim": bool,
    "osm": "way/123",             # for a farm OSM maps as turbines only (TURBINE_FARMS), its central turbine
  }]
  mines: [{
    "name": str, "name_sr": str,
    "kind": "coal_mine" | "copper" | "lead_zinc",
    "commodities": [str],
    "operator": str | null,       # as the production source names it, else OSM operator
    "production": float | null,   # the year's output as published: coal mined, or mine-produced copper
    "production_unit": str | null, "production_year": int | null, "production_source": str | null (URL),
    "lon": float, "lat": float, "in_kim": bool,
    "osm": "way/123" | null,      # null: placed by "wikidata" instead
    "wikidata": "Q123" | null,
  }]
  group_production: [{operator, mines: [name], production, production_unit, production_year, production_source}]
                                  # output an operator publishes only for all its mines, naming those placed above
  unplaced: [{layer: "plants" | "mines", name, name_sr, kind, value, unit, source, reason}]
                                  # officially reported sites that OSM does not map
"""

from __future__ import annotations

import json
import math
import re
import urllib.parse
from dataclasses import dataclass

from ..core.geo import Shape
from ..core.source import Source, SourceInfo
from ..core.store import load_interim
from . import _overpass
from .boundaries import latin

BBOX = (41.8, 18.8, 46.2, 23.1)  # south, west, north, east
MIN_MW = 10
FOSSIL = {"coal_plant", "gas_plant", "oil_plant"}
NOT_BUILT = re.compile(r"\b(planned|under construction|u izgradnji|у изградњи)\b", re.I)

PLANTS_FILE = "osm/plants.json"
SITES_FILE = "osm/sites.json"
WIKIDATA_FILE = "wikidata/mines.json"

DOCS = {
    "eps": ("https://www.eps.rs/eng/Documents/technicalreports/TEH_Godisnjak2025_web_en_s_Fin%201.pdf",
            "docs/eps_technical_report_2025.pdf"),
    "kostt": ("https://kostt.com/Content/ViewFiles/Transparency/BasicMarketDataOnGeneration/"
              "Kapacitetet%20e%20instaluara%20te%20njesive%20gjeneruese.pdf", "docs/kostt_installed_capacities_2026.pdf"),
    "aers": ("https://www.aers.rs/media/FILES/Izvestaji/Godisnji/Eng/2024%20Annual%20Report%20AERS.pdf",
             "docs/aers_annual_report_2024.pdf"),
    "ero": ("https://www.ero-ks.org/zrre/sites/default/files/Publikimet/Raportet%20Vjetor/"
            "ERO_Annual%20Report%202025%20-_0.pdf", "docs/ero_annual_report_2025.pdf"),
    "zijin": ("https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0322/2026032200055.pdf",
              "docs/zijin_annual_results_2025.pdf"),
}


@dataclass(frozen=True)
class Official:
    doc: str
    mw: float
    name: str
    name_sr: str


# EPS: "Generation capacities", net output capacity, EPS 2025 technical report p. 4. KOSTT: table 1 (sum of the
# units with a non-zero actual potential: Kosova A1 and A2 are out of service) and table 2, net. AERS: section 3.1.2.1.
OFFICIAL = {
    "way/180603115": Official("eps", 1594, "TPP Nikola Tesla A", "ТЕ Никола Тесла А"),
    "way/180603118": Official("eps", 1220, "TPP Nikola Tesla B", "ТЕ Никола Тесла Б"),
    "way/180603114": Official("eps", 216, "TPP Kolubara", "ТЕ Колубара"),
    "way/283182585": Official("eps", 108, "TPP Morava", "ТЕ Морава"),
    "way/174908973": Official("eps", 281, "TPP Kostolac A", "ТЕ Костолац А"),
    "way/150680543": Official("eps", 941, "TPP Kostolac B", "ТЕ Костолац Б"),
    "way/722226249": Official("eps", 208, "CHP Novi Sad", "ТЕ-ТО Нови Сад"),
    "way/92876879": Official("eps", 75, "CHP Zrenjanin", "ТЕ-ТО Зрењанин"),
    "relation/10245510": Official("eps", 1140, "HPP Đerdap 1", "ХЕ Ђердап 1"),
    "relation/6271685": Official("eps", 270, "HPP Đerdap 2", "ХЕ Ђердап 2"),
    "way/617222166": Official("eps", 80, "HPP Pirot", "ХЕ Пирот"),
    "way/753131895": Official("eps", 420, "HPP Bajina Bašta", "ХЕ Бајина Башта"),
    "way/753132440": Official("eps", 614, "PSHPP Bajina Bašta", "РХЕ Бајина Башта"),
    "way/753131894": Official("eps", 122, "HPP Zvornik", "ХЕ Зворник"),
    "way/419795913": Official("eps", 54, "HPP Potpeć", "ХЕ Потпећ"),
    "way/550078468": Official("eps", 36, "HPP Uvac", "ХЕ Увац"),
    "way/1475269409": Official("eps", 10, "Petka solar plant", "Соларна електрана Петка"),
    "way/317500085": Official("kostt", 414, "TPP Kosova A", "ТЕ Косово А"),
    "way/317499965": Official("kostt", 610, "TPP Kosova B", "ТЕ Косово Б"),
    "relation/16413656": Official("kostt", 103.41, "Selac wind farm (Bajgora)", "Ветропарк Бајгора"),
    "relation/10753835": Official("kostt", 32.4, "Kitka wind farm", "Ветропарк Китка"),
    "way/224463325": Official("kostt", 32, "HPP Ujmani (Gazivode)", "ХЕ Газиводе"),
    "way/1190922468": Official("aers", 197, "CHP Pančevo", "ТЕ-ТО Панчево"),
    "relation/11535245": Official("aers", 104.5, "Kovačica wind farm", "Ветропарк Ковачица"),
    "relation/11535243": Official("aers", 69, "Košava wind farm", "Ветропарк Кошава"),
    "relation/11535246": Official("aers", 42, "Alibunar wind farm", "Ветропарк Алибунар"),
    "way/107035473": Official("aers", 9.98, "Novi Sad heating plant Zapad", "Топлана Запад"),
}
# Wind farms that OSM maps as turbines only: the turbines in (south, west, north, east).
TURBINE_FARMS = [
    ((44.65, 21.15, 44.78, 21.35), Official("eps", 66, "Kostolac wind farm", "Ветропарк Костолац")),
]
# Officially reported plants that OSM does not map: (kind, MW, doc, name, name_sr).
UNMAPPED_PLANTS = [
    ("gas_plant", 14, "eps", "CHP Sremska Mitrovica", "ТЕ-ТО Сремска Митровица"),
    ("wind", 95, "aers", "Pupin wind farm", "Ветропарк Пупин"),
]


@dataclass(frozen=True)
class Output:
    value: float
    unit: str
    year: int
    doc: str


@dataclass(frozen=True)
class Mine:
    anchor: str  # OSM "way/123" or Wikidata "Q123"
    name: str
    name_sr: str
    kind: str
    commodities: tuple[str, ...]
    operator: str | None = None
    output: Output | None = None


LIGNITE = ("lignite",)
EPS = "Elektroprivreda Srbije (EPS)"
ZIJIN_COPPER = "Serbia Zijin Copper"
MT = "million t"  # coal mined: EPS 2025 technical report p. 12, ERO 2025 annual report section 6.2.1
CU = "t copper"  # mine-produced copper: Zijin 2025 annual results p. 52

MINES = [
    Mine("way/174402881", "Tamnava West Field", "Тамнава – Западно поље", "coal_mine", LIGNITE, EPS,
         Output(11.8, MT, 2025, "eps")),
    Mine("way/174402875", "Field E", "Поље Е", "coal_mine", LIGNITE, EPS, Output(5.8, MT, 2025, "eps")),
    Mine("way/174906688", "Drmno", "Дрмно", "coal_mine", LIGNITE, EPS, Output(10.2, MT, 2025, "eps")),
    Mine("way/195201002", "Kosovo lignite mines (Sibovc)", "Рудници лигнита Косово (Сибовац)", "coal_mine", LIGNITE,
         "Kosovo Energy Corporation (KEK)", Output(6.91, MT, 2025, "ero")),
    Mine("way/823076089", "Soko", "Рудник мрког угља „Соко”", "coal_mine", ("brown coal",)),
    Mine("way/256893913", "Rembas", "Рембас", "coal_mine", ("brown coal",)),
    Mine("way/1324949095", "Ibar mines (Baljevac)", "Ибарски рудници", "coal_mine", ("brown coal",)),
    Mine("way/1095485000", "Čukaru Peki", "Чукару Пеки", "copper", ("copper", "gold"), "Serbia Zijin Mining",
         Output(172_307, CU, 2025, "zijin")),
    Mine("way/209984061", "Veliki Krivelj", "Велики Кривељ", "copper", ("copper",), ZIJIN_COPPER),
    Mine("way/292379189", "Jama Bor", "Јама Бор", "copper", ("copper", "gold"), ZIJIN_COPPER),
    Mine("relation/11828998", "Majdanpek", "Мајданпек", "copper", ("copper", "gold"), ZIJIN_COPPER),
    Mine("way/199363318", "Trepča – Stari Trg", "Трепча – Стари трг", "lead_zinc", ("lead", "zinc", "silver")),
    Mine("node/13952826912", "Novo Brdo (Artana)", "Ново Брдо", "lead_zinc", ("lead", "zinc", "silver")),
    Mine("Q4884471", "Belo Brdo", "Бело Брдо", "lead_zinc", ("lead", "zinc")),
    Mine("Q115695292", "Crnac", "Црнац", "lead_zinc", ("lead", "zinc")),
    Mine("way/1469761091", "Lece", "Леце", "lead_zinc", ("lead", "zinc", "gold")),
    Mine("Q115995189", "Rudnik", "Рудник", "lead_zinc", ("lead", "zinc", "copper")),
    Mine("Q97124211", "Grot", "Грот", "lead_zinc", ("lead", "zinc")),
]
GROUP_PRODUCTION = [
    (ZIJIN_COPPER, ("Jama Bor", "Veliki Krivelj", "Majdanpek"), Output(123_286, CU, 2025, "zijin")),
]
UNMAPPED_MINES = [
    ("coal_mine", Output(4.3, MT, 2025, "eps"), "Field G", "Поље Г"),
    ("coal_mine", Output(0.7, MT, 2025, "eps"), "Radljevo", "Радљево"),
]

PLANTS_QUERY = f"[out:json][timeout:300][bbox:{','.join(map(str, BBOX))}];nwr[power=plant];out tags center;"


def sites_query() -> str:
    """The mines' OSM objects, then the turbines of TURBINE_FARMS."""
    ids: dict[str, list[str]] = {}
    for m in MINES:
        if "/" in m.anchor:
            kind, num = m.anchor.split("/")
            ids.setdefault(kind, []).append(num)
    mines = "".join(f"{k}(id:{','.join(v)});" for k, v in ids.items())
    turbines = "".join(
        f'node[power=generator]["generator:source"=wind]({",".join(map(str, box))});' for box, _ in TURBINE_FARMS
    )
    return f"[out:json][timeout:120];({mines});out tags center;({turbines});out;"


def wikidata_url() -> str:
    qids = "|".join(m.anchor for m in MINES if m.anchor.startswith("Q"))
    return ("https://www.wikidata.org/w/api.php?action=wbgetentities&props=claims&format=json&ids="
            + urllib.parse.quote(qids))


_CAPACITY = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(GW|MW|kW|W)\s*$", re.I)
_SCALE = {"gw": 1000.0, "mw": 1.0, "kw": 1e-3, "w": 1e-6}


def capacity_mw(value: str | None) -> float | None:
    """'1765.5 MW' → 1765.5, '12,5 MW' → 12.5, '910KW' → 0.91; 'yes', 'no' and bare numbers → None."""
    m = _CAPACITY.match(value or "")
    return None if m is None else round(float(m[1].replace(",", ".")) * _SCALE[m[2].lower()], 3)


_SOURCE_KIND = {"coal": "coal_plant", "lignite": "coal_plant", "gas": "gas_plant", "oil": "oil_plant",
                "diesel": "oil_plant", "wind": "wind", "solar": "solar", "waste": "waste", "biomass": "biomass",
                "biogas": "biomass", "biofuel": "biomass"}


def plant_kind(tags: dict) -> str | None:
    source = tags.get("plant:source", "").split(";")[0].strip()
    if source == "hydro":
        return "pumped_storage" if "pumped" in tags.get("plant:method", "") else "hydro"
    return _SOURCE_KIND.get(source)


def centre(e: dict) -> tuple[float, float]:
    c = e.get("center") or e
    return round(c["lon"], 5), round(c["lat"], 5)


def is_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def osm_names(tags: dict) -> tuple[str, str | None]:
    """(English or Latin display name, Serbian Cyrillic name or None) of an OSM object."""
    name = tags.get("name", "")
    sr = tags.get("name:sr") or (name if is_cyrillic(name) else None)
    display = tags.get("name:en") or tags.get("name:sr-Latn") or (latin(sr) if sr else name)
    return display, sr


class Territory:
    """Serbia with KiM as the `boundaries` interim draws it: which part ("rs" / "kim") holds a point."""

    def __init__(self, units: list[dict]):
        self.units = [(Shape(u["rings"]), u["part"]) for u in units]

    def part(self, lon: float, lat: float) -> str | None:
        return next((part for shape, part in self.units if shape.contains(lon, lat)), None)

    def nearest_part(self, lon: float, lat: float) -> str:
        kx = math.cos(math.radians(lat))
        return min(
            (((x - lon) * kx) ** 2 + (y - lat) ** 2, part)
            for shape, part in self.units for ring in shape.rings for x, y in ring
        )[1]


class PowerMines(Source):
    info = SourceInfo(
        id="power_mines",
        title="Power plants and mines of Serbia (incl. Kosovo and Metohija)",
        publisher=("OpenStreetMap contributors; Elektroprivreda Srbije (EPS); KOSTT; Agencija za energetiku (AERS); "
                   "Energy Regulatory Office of Kosovo (ERO); Zijin Mining Group; Wikidata"),
        homepage="https://www.openstreetmap.org/",
        license=("OSM: © OpenStreetMap contributors, ODbL 1.0. Wikidata: CC0. Figures quoted from the published "
                 "reports of EPS, KOSTT, AERS, ERO and Zijin Mining"),
        description=(
            f"Power plants (OSM power=plant) of at least {MIN_MW} MW, and every coal, gas or oil plant whose electric "
            "capacity is known, with the capacities that EPS (2025 technical report), KOSTT (installed capacities "
            "2026) and AERS (2024 annual report) publish for the plants they list. The operating coal, copper and "
            "lead-zinc mines, placed by their OSM outline or Wikidata, with 2025 output from EPS, the Kosovo energy "
            "regulator ERO and Zijin Mining's annual results where published."
        ),
        used_for=["Power plants and mines on the map (resources)"],
    )

    def fetch(self, force=False):
        _overpass.query(
            self, PLANTS_QUERY, PLANTS_FILE,
            lambda els: None if sum(e["type"] == "way" for e in els) >= 100 else "fewer than 100 plant outlines",
            force=force,
        )
        _overpass.query(self, sites_query(), SITES_FILE, lambda els: None if els else "no elements", force=force)
        self.download(wikidata_url(), WIKIDATA_FILE, force=force)
        for url, rel_path in DOCS.values():
            self.download(url, rel_path, force=force, expect_binary=True)

    # --- process -----------------------------------------------------------------

    def process(self):
        land = Territory(load_interim("boundaries")["units"])
        sites = {f"{e['type']}/{e['id']}": e for e in self._json(SITES_FILE)["elements"]}
        plants = self._plants(self._json(PLANTS_FILE)["elements"], sites, land)
        mines = self._mines(sites, self._json(WIKIDATA_FILE)["entities"], land)
        unplaced = [
            {"layer": "plants", "name": name, "name_sr": name_sr, "kind": kind, "value": mw, "unit": "MW",
             "source": DOCS[doc][0], "reason": "not mapped in OpenStreetMap"}
            for kind, mw, doc, name, name_sr in UNMAPPED_PLANTS
        ] + [
            {"layer": "mines", "name": name, "name_sr": name_sr, "kind": kind, "value": out.value, "unit": out.unit,
             "source": DOCS[out.doc][0], "reason": "not mapped in OpenStreetMap"}
            for kind, out, name, name_sr in UNMAPPED_MINES
        ]
        groups = [
            {"operator": op, "mines": list(names), "production": out.value, "production_unit": out.unit,
             "production_year": out.year, "production_source": DOCS[out.doc][0]}
            for op, names, out in GROUP_PRODUCTION
        ]
        self._report(plants, mines)
        return {
            "vintage": f"OpenStreetMap, Overpass API, retrieved {self._retrieved(PLANTS_FILE)}; EPS 2025, "
                       "KOSTT 2026, AERS 2024, ERO 2025, Zijin 2025",
            "_files": [PLANTS_FILE, SITES_FILE, WIKIDATA_FILE, *(rel for _, rel in DOCS.values())],
            "plants": plants,
            "mines": mines,
            "group_production": groups,
            "unplaced": unplaced,
        }

    def _plants(self, elements: list[dict], sites: dict, land: Territory) -> list[dict]:
        found = {f"{e['type']}/{e['id']}" for e in elements}
        if missing := sorted(set(OFFICIAL) - found):
            raise ValueError(f"OFFICIAL plants missing from OSM (deleted or renumbered?): {missing}")
        rows = []
        for e in elements:
            tags, key = e.get("tags", {}), f"{e['type']}/{e['id']}"
            kind, official = plant_kind(tags), OFFICIAL.get(key)
            if kind is None or NOT_BUILT.search(tags.get("name", "")):
                continue
            lon, lat = centre(e)
            part = land.part(lon, lat)
            if part is None and official is None:
                continue
            if official:
                mw, source, name, name_sr = official.mw, DOCS[official.doc][0], official.name, official.name_sr
            else:
                mw, source = capacity_mw(tags.get("plant:output:electricity")), f"https://www.openstreetmap.org/{key}"
                name, name_sr = osm_names(tags)
            if not mw or (mw < MIN_MW and kind not in FOSSIL):
                continue
            rows.append({
                "name": name, "name_sr": name_sr, "kind": kind, "capacity_mw": mw, "capacity_source": source,
                "operator": tags.get("operator") or (EPS if official and official.doc == "eps" else None),
                "lon": lon, "lat": lat, "in_kim": (part or land.nearest_part(lon, lat)) == "kim", "osm": key,
            })
        rows += [self._turbine_farm(box, official, sites, land) for box, official in TURBINE_FARMS]
        return self._dedupe(rows)

    @staticmethod
    def _turbine_farm(box: tuple, official: Official, sites: dict, land: Territory) -> dict:
        """A farm placed at its turbine nearest the turbines' mean position."""
        south, west, north, east = box
        turbines = [e for e in sites.values() if e["type"] == "node" and e.get("tags", {}).get("power") == "generator"
                    and south <= e["lat"] <= north and west <= e["lon"] <= east]
        if not turbines:
            raise ValueError(f"{official.name}: no OSM wind turbines in {box}")
        mx, my = sum(t["lon"] for t in turbines) / len(turbines), sum(t["lat"] for t in turbines) / len(turbines)
        hub = min(turbines, key=lambda t: (t["lon"] - mx) ** 2 + (t["lat"] - my) ** 2)
        lon, lat = centre(hub)
        return {
            "name": official.name, "name_sr": official.name_sr, "kind": "wind", "capacity_mw": official.mw,
            "capacity_source": DOCS[official.doc][0], "operator": EPS if official.doc == "eps" else None,
            "lon": lon, "lat": lat, "in_kim": land.part(lon, lat) == "kim", "osm": f"node/{hub['id']}",
        }

    @staticmethod
    def _dedupe(rows: list[dict]) -> list[dict]:
        """OSM sometimes maps one plant twice (a site and its outline): keep the official or larger one."""
        rows.sort(key=lambda r: ("openstreetmap" in r["capacity_source"], -r["capacity_mw"], r["osm"]))
        kept: list[dict] = []
        for r in rows:
            twin = any(
                k["kind"] == r["kind"] and (k["name_sr"] or k["name"]) == (r["name_sr"] or r["name"])
                and abs(k["lon"] - r["lon"]) < 0.02 and abs(k["lat"] - r["lat"]) < 0.02
                for k in kept
            )
            if not twin:
                kept.append(r)
        return sorted(kept, key=lambda r: (r["kind"], -r["capacity_mw"], r["name"]))

    @staticmethod
    def _mines(osm: dict, wikidata: dict, land: Territory) -> list[dict]:
        rows = []
        for m in MINES:
            if m.anchor.startswith("Q"):
                coords = [c["mainsnak"]["datavalue"]["value"] for c in wikidata[m.anchor]["claims"].get("P625", [])]
                if len(coords) != 1:
                    raise ValueError(f"{m.name}: Wikidata {m.anchor} has {len(coords)} coordinates, wanted one")
                lon, lat, tags, key = round(coords[0]["longitude"], 5), round(coords[0]["latitude"], 5), {}, None
            else:
                if m.anchor not in osm:
                    raise ValueError(f"{m.name}: OSM {m.anchor} is gone (deleted or renumbered?)")
                tags, key = osm[m.anchor].get("tags", {}), m.anchor
                lon, lat = centre(osm[m.anchor])
            part = land.part(lon, lat)
            if part is None:
                raise ValueError(f"{m.name} ({m.anchor}) lies outside Serbia")
            out = m.output
            rows.append({
                "name": m.name, "name_sr": m.name_sr, "kind": m.kind, "commodities": list(m.commodities),
                "operator": m.operator or tags.get("operator"),
                "production": out and out.value, "production_unit": out and out.unit,
                "production_year": out and out.year, "production_source": out and DOCS[out.doc][0],
                "lon": lon, "lat": lat, "in_kim": part == "kim",
                "osm": key, "wikidata": m.anchor if key is None else tags.get("wikidata"),
            })
        return rows

    @staticmethod
    def _report(plants: list[dict], mines: list[dict]) -> None:
        by_kind: dict[str, list] = {}
        for p in plants:
            by_kind.setdefault(p["kind"], []).append(p["capacity_mw"])
        print("    plants: " + ", ".join(f"{k} {len(v)} ({sum(v):,.0f} MW)" for k, v in sorted(by_kind.items())))
        print(f"    mines: {len(mines)}, {sum(m['production'] is not None for m in mines)} with output")

    def _json(self, rel_path: str):
        return json.loads((self.raw_dir / rel_path).read_text(encoding="utf-8"))

    def _retrieved(self, rel_path: str) -> str:
        manifest = json.loads((self.raw_dir / "manifest.json").read_text(encoding="utf-8"))
        return manifest[rel_path]["retrieved"][:10]
