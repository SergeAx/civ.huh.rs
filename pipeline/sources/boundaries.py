"""Administrative boundaries of Serbia, Kosovo and Metohija (KiM) included, and municipal seats.

Outside KiM the units are the finest level the Statistical Office (RZS) reports: opštine,
gradovi and the gradske opštine of the six cities that have them, keyed by the RZS code.
Their polygons are the Republic Geodetic Authority's register of spatial units (RGZ RPJ),
where Novi Sad is one polygon; it is split into its two gradske opštine from the RPJ settlements.
KiM is divided into Kosovo's 38 current municipalities (the unit its statistics use), built
from the RPJ cadastral municipalities (KO): each KO goes to the OSM municipality that holds
most of its area, and the town KO of Kosovska Mitrovica is cut along OSM's outline of Mitrovica
North. KiM and the rest of Serbia therefore share the RPJ line vertex for vertex. KiM units are
keyed "KM01".."KM38" by the Kosovo Agency of Statistics (ASK) municipality number.

All polygons are simplified together, shared boundaries once (Douglas-Peucker, 50 m), so
neighbours stay seamless; okruzi are dissolved from the simplified units. Seats come from OSM.

Interim `boundaries` (data/interim/boundaries.json, under "data"):

  units: [{                       # 169 outside KiM + 38 in KiM; every hex belongs to one
    "code": str,                  # RZS 5-digit municipality code; "KM01".."KM38" in KiM
    "part": "rs" | "kim",
    "kind": "grad" | "opština" | "gradska opština",   # in KiM: "grad" for Priština only
    "name_cyr": str, "name_lat": str,   # RZS names outside KiM; Serbian names in KiM
    "name_sq": str | null,        # KiM: official Albanian name, the join key with Kosovo statistics
    "name_sq_alt": [str],         # KiM: other spellings met in statistics ([] if none)
    "grad_code": str | null,      # parent city of a gradska opština (e.g. "79014" Grad Beograd)
    "okrug_code": "00".."29",     # Grad Beograd "00"
    "rs_codes": [str],            # KiM: RZS codes of the Serbian municipalities its KOs belong to
    "area_km2": float,            # unsimplified polygon, UTM 34N planar
    "seat": {
      "name_cyr": str, "name_lat": str, "name_sq": str | null,
      "lon": float, "lat": float,
      "place": str | null,        # OSM place=* of the seat node (city, town, village, suburb) or null
      "population": int | null, "population_date": str | null,   # OSM population, its date if tagged
      "osm": "node/<id>",
      "naselje": {"code": str, "name_cyr": str, "name_lat": str} | null,
                                  # RPJ settlement containing the seat (in KiM: the KO)
    } | null,
    "rings": [[[lon, lat], ...], ...],   # closed; outers counter-clockwise, holes clockwise
  }]                              # sorted by code
  gradovi: [{"code", "name_cyr", "name_lat", "okrug_code", "members": [unit code]}]   # all 29
  okruzi: [{"code": "00".."29", "name_cyr", "name_lat", "units": [unit code], "area_km2", "rings"}]
  quality: {...}                  # code checks, KO assignment, seam and coverage measurements
                                  # ("kim-rs" in a coverage key: across the KiM line)

Coordinates are WGS84 lon/lat rounded to 5 decimals.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import Counter, defaultdict

from ..core import fetch
from ..core.source import Source, SourceInfo
from . import _overpass
from ._topology import (
    UTM, area2, bbox, contains, dissolve, intersect, join_ways, oriented, overlay, simplify_coverage, split_edges,
    wkt_polygons,
)

RPJ = "https://download.geosrbija.rs/download-api/opendata-proxy/export?category=rpj&layer={0}_rpj&geometry=true&fileName={0}&format=csv"
RPJ_LAYERS = ("opstina", "okrug", "naselje", "katastarska_opstina")
RZS = "https://opendata.stat.gov.rs/data/WcfJsonRestService.Service1.svc/dataset/SIFOPS/{}/csv"
OSM_KIM = (
    '[out:json][timeout:180];area["ISO3166-1"="XK"][admin_level=2]->.k;'
    'rel(area.k)[boundary=administrative][admin_level=6][!"ref:RS:okrug"]->.m;'
    '.m out geom;node(r.m:"admin_centre");out;'
)
OSM_RS = (
    "[out:json][timeout:180][bbox:41.8,18.8,46.2,23.1];"
    '(rel[boundary=administrative]["ref:RS:opstina"];rel[boundary=administrative]["ref:RS:grad"];)->.m;'
    '.m out body;(node(r.m:"admin_centre");node(r.m:"label");node[place~"^(city|town|suburb)$"];);out;'
)

SCALE = 100  # integer centimetres in UTM 34N, where RPJ is published
TOLERANCE_M = 50
COVERAGE_STEP_M = 50

GRAD_PARTS = {
    "79014": ("70092", "70106", "70114", "70122", "70149", "70157", "70165", "70173", "70181",
              "70190", "70203", "70211", "70220", "70238", "70246", "70254", "71293"),
    "79022": ("71285", "71307", "71315", "71323", "71331"),
    "79049": ("70947", "71340"),
    "79057": ("70432", "71358"),
    "79065": ("71145", "71366"),
    "89010": ("80284", "80519"),
}
GRADOVI = ("70327", "70360", "70556", "70645", "70653", "70670", "70726", "70734", "70874", "70939", "70998",
           "71048", "71099", "71242", "71269", "80128", "80152", "80209", "80314", "80381", "80403", "80438")
NOVI_SAD, PETROVARADIN = "80284", "80519"
PETROVARADIN_NASELJA = {"ПЕТРОВАРАДИН", "СРЕМСКА КАМЕНИЦА", "БУКОВАЦ", "ЛЕДИНЦИ", "СТАРИ ЛЕДИНЦИ"}

# Kosovo's 38 municipalities: ASK number, Serbian name, official Albanian name, okrug, OSM wikidata, other Albanian spellings.
KIM = (
    (19, "Приштина", "Prishtinë", "25", "Q3625575", ()),
    (34, "Грачаница", "Graçanicë", "25", "Q3655958", ("Graçanica",)),
    (3, "Глоговац", "Drenas", "25", "Q1008042", ("Gllogoc",)),
    (9, "Косово Поље", "Fushë Kosovë", "25", "Q2447449", ("Fushë-Kosovë",)),
    (13, "Липљан", "Lipjan", "25", "Q16036965", ()),
    (15, "Обилић", "Obiliq", "25", "Q4329229", ()),
    (18, "Подујево", "Podujevë", "25", "Q860399", ()),
    (25, "Урошевац", "Ferizaj", "25", "Q868964", ()),
    (22, "Штимље", "Shtime", "25", "Q4526883", ()),
    (23, "Штрпце", "Shtërpcë", "25", "Q2043155", ()),
    (7, "Качаник", "Kaçanik", "25", "Q2043130", ()),
    (33, "Елез Хан", "Hani i Elezit", "25", "Q2347012", ("Han i Elezit",)),
    (17, "Пећ", "Pejë", "26", "Q2507287", ()),
    (1, "Дечани", "Deçan", "26", "Q860148", ()),
    (31, "Јуник", "Junik", "26", "Q794068", ()),
    (2, "Ђаковица", "Gjakovë", "26", "Q3656386", ()),
    (6, "Исток", "Istog", "26", "Q2043104", ()),
    (8, "Клина", "Klinë", "26", "Q860157", ()),
    (20, "Призрен", "Prizren", "27", "Q2507200", ()),
    (32, "Мамуша", "Mamushë", "27", "Q794116", ()),
    (16, "Ораховац", "Rahovec", "27", "Q794039", ()),
    (24, "Сува Река", "Suharekë", "27", "Q794044", ()),
    (5, "Драгаш", "Dragash", "27", "Q3191420", ()),
    (30, "Малишево", "Malishevë", "27", "Q794063", ()),
    (11, "Косовска Митровица", "Mitrovicë", "28", "Q3657448", ("Mitrovicë e Jugut", "Mitrovica e Jugut")),
    (38, "Северна Косовска Митровица", "Mitrovicë e Veriut", "28", "Q12756670", ("Mitrovica e Veriut", "Mitrovicë Veriore")),
    (27, "Вучитрн", "Vushtrri", "28", "Q3657833", ()),
    (29, "Звечан", "Zveçan", "28", "Q2048373", ()),
    (28, "Зубин Поток", "Zubin Potok", "28", "Q2500688", ()),
    (12, "Лепосавић", "Leposaviq", "28", "Q2048354", ()),
    (21, "Србица", "Skenderaj", "28", "Q2043122", ("Skënderaj",)),
    (4, "Гњилане", "Gjilan", "29", "Q2513453", ()),
    (36, "Партеш", "Partesh", "29", "Q2605602", ()),
    (10, "Косовска Каменица", "Kamenicë", "29", "Q2043136", ()),
    (35, "Ранилуг", "Ranillug", "29", "Q15529552", ()),
    (14, "Ново Брдо", "Novobërdë", "29", "Q6081267", ()),
    (26, "Витина", "Viti", "29", "Q860303", ()),
    (37, "Клокот", "Kllokot", "29", "Q860171", ("Kllokot-Vërboc",)),
)
KIM_GRAD = "Приштина"
# RPJ keeps the town of Kosovska Mitrovica one KO; Mitrovica North is the part north of the Ibar,
# so that KO is cut along OSM's outline of the North (slivers under MIN_PIECE_KM2 stay south).
SPLIT_KO = ("90298", "КОСОВСКА МИТРОВИЦА", 38)
MIN_PIECE_KM2 = 0.05
# Neighbouring RPJ opštine do not always share vertices: dissolving them into okruzi leaves slivers.
MIN_OKRUG_RING_KM2 = 0.25

_CYR = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџш",
                "a b v g d đ e ž z i j k l lj m n nj o p r s t ć u f h c č dž š".split()))
_SMALL_WORDS = {"на", "код", "у", "до", "и", "над", "под", "варош", "варошица", "село", "насеље"}


def latin(text: str) -> str:
    out = []
    for ch in text:
        t = _CYR.get(ch.lower())
        out.append(ch if t is None else t if ch.islower() else t.capitalize())
    return "".join(out)


def proper(upper: str, known: dict[str, str] | None = None) -> str:
    """An RPJ name (upper case) in normal case: 'ЛАПОВО (ВАРОШИЦА)' → 'Лапово (варошица)'.

    A parenthesised part found in `known` (upper case → as written) takes that spelling:
    'БЕОГРАД (САВСКИ ВЕНАЦ)' → 'Београд (Савски венац)'."""
    parts = re.split(r"([\s()]+)", upper.strip().lower())
    name = "".join(p if not p.strip(" ()") or (i and p in _SMALL_WORDS) else p.capitalize() for i, p in enumerate(parts))
    return re.sub(r"\(([^)]*)\)", lambda m: f"({(known or {}).get(m[1].upper(), m[1])})", name)


def plain(name: str) -> str:
    """Without the disambiguation: 'Палилула (Београд)' → 'Палилула'."""
    return re.sub(r"\s*\(.*\)$", "", name)


def _csv_rows(path):
    csv.field_size_limit(1 << 30)
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def _km2(rings) -> float:
    return round(sum(area2(r) for r in rings) / 2 / SCALE**2 / 1e6, 3)


class Boundaries(Source):
    info = SourceInfo(
        id="boundaries",
        title="Municipalities, okruzi and municipal seats of Serbia (incl. Kosovo and Metohija)",
        publisher="Republički geodetski zavod (RGZ); Republički zavod za statistiku (RZS); OpenStreetMap contributors",
        homepage="https://opendata.geosrbija.rs/",
        license=(
            "RGZ register of spatial units and RZS municipality list: Serbian Open Data Licence 1.0 "
            "(Српска лиценца за отворене податке; credit RGZ and RZS). OSM municipalities of Kosovo "
            "and seats: © OpenStreetMap contributors, ODbL 1.0"
        ),
        description=(
            "Municipality polygons from RGZ's register of spatial units (RPJ), keyed by the RZS "
            "municipality code. Kosovo and Metohija is split into Kosovo's 38 municipalities, built "
            "from RPJ cadastral municipalities assigned by OSM's municipal outlines. Seats and their "
            "populations are OSM place nodes."
        ),
        used_for=["Municipality and okrug lookup for every hex", "Okrug borders", "Municipal seats"],
    )

    # --- fetch -------------------------------------------------------------------

    def fetch(self, force=False):
        for layer in RPJ_LAYERS:
            self.download(RPJ.format(layer), f"rpj/{layer}.zip", force=force, expect_binary=True)
        for lang, script in ((1, "cyr"), (2, "lat")):
            self.download(RZS.format(lang), f"rzs/sifops_{script}.csv", force=force)
        _overpass.query(
            self, OSM_KIM, "osm/kim_municipalities.json",
            lambda d: None if self._kim_relations(d) else "not all 38 Kosovo municipalities", force=force,
        )
        _overpass.query(
            self, OSM_RS, "osm/rs_seats.json",
            lambda d: None if sum(e["type"] == "relation" for e in d) >= 150 else "fewer than 150 municipalities",
            force=force,
        )

    # --- readers -----------------------------------------------------------------

    def _rzs(self) -> dict:
        names = {}
        for script in ("cyr", "lat"):
            with open(self.raw_dir / f"rzs/sifops_{script}.csv", encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    names.setdefault(r["MBOPS"], {"nuts3": r["IDNSTJ"].strip() or None})[script] = r["nOPS"].strip()
        return names

    @staticmethod
    def _kim_relations(elements) -> dict:
        """Kosovo municipality relations by KIM row index, all 38 or {} (OSM wikidata, then Serbian name)."""
        rels = [e for e in elements if e["type"] == "relation"]
        found = {}
        for i, (_ask, cyr, _sq, _okrug, qid, _alt) in enumerate(KIM):
            match = [e for e in rels if e["tags"].get("wikidata") == qid] or [
                e for e in rels if e["tags"].get("name:sr", "").removeprefix("Општина ") == cyr
            ]
            if len(match) == 1:
                found[i] = match[0]
        return found if len(found) == len(KIM) else {}

    # --- process -----------------------------------------------------------------

    def process(self):
        utm = UTM(34)
        rzs = self._rzs()
        quality: dict = {}

        rpj = {}
        for r in _csv_rows(self.raw_dir / "rpj/opstina.zip"):
            rpj[r["opstina_maticni_broj"]] = {
                "okrug": f"{int(r['okrug_sifra']):02d}",
                "name": r["opstina_ime"],
                "rings": oriented(wkt_polygons(r["geometry"], SCALE)),
            }
        okrug_rows = {
            f"{int(r['okrug_sifra']):02d}": (r["okrug_ime"], r["okrug_imel"], oriented(wkt_polygons(r["geometry"], SCALE)))
            for r in _csv_rows(self.raw_dir / "rpj/okrug.zip")
        }

        # Units outside KiM: every RZS municipality code that is neither a city with parts nor in KiM.
        rs_codes = sorted(c for c in rzs if c[:2] in ("70", "71", "80"))
        shapes: dict[str, list] = {}
        for code in rs_codes:
            if code in rpj:
                shapes[code] = rpj[code]["rings"]
        parts = {NOVI_SAD: [], PETROVARADIN: []}
        for r in _csv_rows(self.raw_dir / "rpj/naselje.zip"):
            if r["opstina_maticni_broj"] == "89010":
                part = PETROVARADIN if r["naselje_ime"] in PETROVARADIN_NASELJA else NOVI_SAD
                parts[part] += oriented(wkt_polygons(r["wkt"], SCALE))
        for code, rings in parts.items():
            shapes[code] = dissolve(rings)
        split_ok = abs(sum(map(area2, shapes[NOVI_SAD] + shapes[PETROVARADIN])) - sum(map(area2, rpj["89010"]["rings"]))) == 0
        missing = [c for c in rs_codes if c not in shapes]
        if missing or not split_ok:
            raise RuntimeError(f"RPJ polygons missing for {missing} or Novi Sad split lost area")
        okrug_of = {c: rpj[c]["okrug"] for c in rs_codes if c in rpj}
        okrug_of[NOVI_SAD] = okrug_of[PETROVARADIN] = rpj["89010"]["okrug"]
        quality["codes"] = self._check_codes(rzs, rpj, okrug_of)

        # KiM: RPJ cadastral municipalities assigned to Kosovo's municipalities by OSM outlines.
        kos = {}
        for r in _csv_rows(self.raw_dir / "rpj/katastarska_opstina.zip"):
            if r["opstina_maticni_broj"].startswith("90"):
                kos[r["kat_opstina_maticni_broj"]] = (
                    r["kat_opstina_ime"], r["opstina_maticni_broj"], oriented(wkt_polygons(r["wkt"], SCALE))
                )
        osm_kim = json.loads((self.raw_dir / "osm/kim_municipalities.json").read_text(encoding="utf-8"))
        kim_rel = self._kim_relations(osm_kim["elements"])
        if not kim_rel:
            raise RuntimeError("OSM answer lacks some of Kosovo's 38 municipalities")
        kim_nodes = {e["id"]: e for e in osm_kim["elements"] if e["type"] == "node"}
        kim_ids = [f"KM{row[0]:02d}" for row in KIM]
        osm_shapes = {}
        for i, rel in kim_rel.items():
            ways = [
                [tuple(round(c * SCALE) for c in utm.forward(g["lon"], g["lat"])) for g in m["geometry"]]
                for m in rel["members"] if m["type"] == "way"
            ]
            osm_shapes[kim_ids[i]] = join_ways(ways)
        split = self._split_ko(kos, osm_shapes)
        for code in shapes:
            shapes[code] = split_edges(shapes[code], split)
        ko_unit, quality["kim_assignment"] = self._assign(kos, osm_shapes)
        members = defaultdict(list)
        for ko, uid in ko_unit.items():
            members[uid].append(ko)
        for i, uid in enumerate(kim_ids):
            if not members[uid]:
                raise RuntimeError(f"no cadastral municipality fell into {KIM[i][1]}")
            shapes[uid] = dissolve(r for ko in members[uid] for r in kos[ko][2])
            if sum(map(area2, shapes[uid])) != sum(area2(r) for ko in members[uid] for r in kos[ko][2]):
                raise RuntimeError(f"dissolving the KOs of {KIM[i][1]} lost area")
        osm_area = quality["kim_assignment"].pop("osm_area_km2")
        quality["kim_assignment"]["unit_vs_osm_km2"] = {uid: [_km2(shapes[uid]), osm_area[uid]] for uid in sorted(kim_ids)}
        quality["kim_line_shared_km"] = self._shared_line(shapes, set(kim_ids))

        simple = simplify_coverage(shapes, TOLERANCE_M * SCALE)
        reference = {"RPJ": [r for _, _, rings in okrug_rows.values() for r in rings]}
        quality["coverage_raw"] = self._coverage(shapes, reference, set(kim_ids))
        quality["coverage"] = self._coverage(simple, reference, set(kim_ids))

        to_ll = self._lonlat(utm)
        units = []
        for code in rs_codes:
            parent = next((g for g, ps in GRAD_PARTS.items() if code in ps), None)
            units.append({
                "code": code, "part": "rs",
                "kind": "gradska opština" if parent else "grad" if code in GRADOVI else "opština",
                "name_cyr": rzs[code]["cyr"], "name_lat": rzs[code]["lat"], "name_sq": None, "name_sq_alt": [],
                "grad_code": parent, "okrug_code": okrug_of[code], "rs_codes": [],
                "area_km2": _km2(shapes[code]), "seat": None, "rings": to_ll(simple[code]),
            })
        for i, uid in enumerate(kim_ids):
            _, cyr, sq, okrug, _, alt = KIM[i]
            units.append({
                "code": uid, "part": "kim", "kind": "grad" if cyr == KIM_GRAD else "opština",
                "name_cyr": cyr, "name_lat": latin(cyr), "name_sq": sq, "name_sq_alt": list(alt),
                "grad_code": None, "okrug_code": okrug, "rs_codes": sorted({kos[ko][1] for ko in members[uid]}),
                "area_km2": _km2(shapes[uid]), "seat": None, "rings": to_ll(simple[uid]),
            })
        units.sort(key=lambda u: u["code"])
        by_id = {u["code"]: u for u in units}

        quality["seats"] = self._seats(by_id, shapes, kos, kim_rel, kim_nodes, kim_ids, utm)

        okruzi = []
        okrug_units = defaultdict(list)
        for u in units:
            okrug_units[u["okrug_code"]].append(u["code"])
        okrug_area, slivers = {}, Counter()
        for code in sorted(okrug_rows):
            name_cyr, name_lat, raw = okrug_rows[code]
            rings = []
            for r in dissolve(r for uid in okrug_units[code] for r in simple[uid]):
                km2 = abs(area2(r)) / 2 / SCALE**2 / 1e6
                if km2 >= MIN_OKRUG_RING_KM2:
                    rings.append(r)
                else:
                    slivers["rings"] += 1
                    slivers["km2"] += km2
            okruzi.append({
                "code": code, "name_cyr": self._okrug_name(name_cyr), "name_lat": self._okrug_name(name_lat),
                "units": okrug_units[code], "area_km2": round(sum(by_id[uid]["area_km2"] for uid in okrug_units[code]), 3),
                "rings": to_ll(rings),
            })
            okrug_area[code] = [okruzi[-1]["area_km2"], _km2(raw)]
        quality["okrug_vs_rpj_km2"] = okrug_area
        quality["okrug_slivers_dropped"] = {"rings": slivers["rings"], "km2": round(slivers["km2"], 3)}

        gradovi = []
        for code in sorted({*GRADOVI, *GRAD_PARTS}):
            members_ = list(GRAD_PARTS.get(code, (code,)))
            gradovi.append({"code": code, "name_cyr": rzs[code]["cyr"], "name_lat": rzs[code]["lat"],
                            "okrug_code": okrug_of[members_[0]], "members": members_})
        pristina = kim_ids[[row[1] for row in KIM].index(KIM_GRAD)]
        gradovi.append({"code": "90263", "name_cyr": "Град Приштина", "name_lat": "Grad Priština",
                        "okrug_code": "25", "members": [pristina]})

        manifest = fetch.read_manifest(self.id)
        retrieved = manifest.get("rpj/opstina.zip", {}).get("retrieved", "")[:10]
        return {
            "vintage": f"RGZ RPJ retrieved {retrieved}; OSM {osm_kim['osm3s']['timestamp_osm_base'][:10]}",
            "_files": [f"rpj/{layer}.zip" for layer in RPJ_LAYERS]
            + ["rzs/sifops_cyr.csv", "rzs/sifops_lat.csv", "osm/kim_municipalities.json", "osm/rs_seats.json"],
            "units": units,
            "gradovi": gradovi,
            "okruzi": okruzi,
            "quality": quality,
        }

    # --- steps ---------------------------------------------------------------------

    @staticmethod
    def _okrug_name(upper: str) -> str:
        name = upper.strip().capitalize()
        return re.sub(r"^(Град|Grad) (\w)", lambda m: f"{m[1]} {m[2].upper()}", name)

    @staticmethod
    def _check_codes(rzs, rpj, okrug_of) -> dict:
        """RPJ codes and names against the RZS list, and RZS NUTS3 regions against RPJ okruzi."""
        out = {
            "rzs_not_in_rpj": sorted(c for c in rzs if c not in rpj),
            "rpj_not_in_rzs": sorted(c for c in rpj if c not in rzs),
            "name_mismatch": sorted(
                [c, rpj[c]["name"], rzs[c]["cyr"]] for c in rpj
                if c in rzs and plain(rpj[c]["name"]) != plain(rzs[c]["cyr"]).upper()
            ),
        }
        nuts = defaultdict(set)
        for c, okrug in okrug_of.items():
            nuts[rzs[c]["nuts3"]].add(okrug)
        out["nuts3_to_okrug"] = {n: sorted(o) for n, o in sorted(nuts.items())}
        out["nuts3_one_to_one"] = all(len(o) == 1 for o in nuts.values()) and len(nuts) == len(set(okrug_of.values()))
        return out

    @staticmethod
    def _split_ko(kos, osm_shapes) -> dict:
        """Cut SPLIT_KO along OSM's outline (in place); returns the split edges for its neighbours."""
        op, name, ask = SPLIT_KO
        ko = next(k for k, (n, o, _) in kos.items() if (o, n) == (op, name))
        _, _, rings = kos[ko]
        clip = max(osm_shapes[f"KM{ask:02d}"], key=lambda r: abs(area2(r)))
        with_hits, pieces, split = intersect(max(rings, key=area2), clip if area2(clip) > 0 else clip[::-1])
        pieces = [r for r in pieces if area2(r) / 2 / SCALE**2 / 1e6 >= MIN_PIECE_KM2]
        rest = [r for r in rings if r is not max(rings, key=area2)]
        kos[ko] = (name, op, dissolve([with_hits, *rest] + [r[::-1] for r in pieces]))
        kos[f"{ko}-{ask}"] = (name, op, pieces)
        for k, (n, o, rs) in kos.items():
            kos[k] = (n, o, split_edges(rs, split))
        return split

    @staticmethod
    def _assign(kos, osm_shapes):
        """Each KO goes to the OSM municipality covering most of it (scanlines 100 m apart)."""
        runs = overlay([{ko: v[2] for ko, v in kos.items()}, osm_shapes], 100 * SCALE)
        share, osm_area = defaultdict(Counter), Counter()
        for line in runs:
            for xa, xb, (ko_set, osm_set) in line:
                osm_area.update(dict.fromkeys(osm_set, xb - xa))
                for ko in ko_set:
                    share[ko][next(iter(osm_set)) if len(osm_set) == 1 else None] += xb - xa
        to_km2 = 100 * SCALE / SCALE**2 / 1e6
        assign, disputed, outside = {}, [], 0.0
        for ko, (name, op, rings) in kos.items():
            got = share.get(ko, Counter())
            candidates = Counter({k: v for k, v in got.items() if k is not None})
            if not candidates:
                raise RuntimeError(f"cadastral municipality {ko} {name} lies outside every OSM municipality")
            best, best_len = candidates.most_common(1)[0]
            assign[ko] = best
            outside += got.get(None, 0) * to_km2
            total = sum(got.values())
            if best_len < 0.75 * total:
                disputed.append([ko, proper(name), op, round(total * to_km2, 2),
                                 {k: round(v * to_km2, 2) for k, v in candidates.most_common()}])
        minority = sum(sum(v for k, v in share[ko].items() if k not in (None, assign[ko])) for ko in kos) * to_km2
        return assign, {
            "kos": len(kos),
            "minority_area_km2": round(minority, 1),
            "outside_osm_km2": round(outside, 2),
            "disputed_kos": sorted(disputed, key=lambda d: -d[3]),
            "osm_area_km2": {k: round(v * to_km2, 3) for k, v in sorted(osm_area.items())},
        }

    @staticmethod
    def _shared_line(shapes, kim_ids) -> dict:
        """Length of KiM's boundary walked the other way by a unit outside KiM (exactly shared) or not."""
        rs_edges = {(a, b) for uid, rings in shapes.items() if uid not in kim_ids for r in rings for a, b in zip(r, r[1:])}
        kim_edges = Counter((a, b) for uid in kim_ids for r in shapes[uid] for a, b in zip(r, r[1:]))
        km = Counter()
        for (a, b), n in kim_edges.items():
            if kim_edges.get((b, a)):
                continue
            length = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / SCALE / 1000
            km["shared_with_rs" if (b, a) in rs_edges else "not_shared"] += length * n
        return {k: round(v, 1) for k, v in km.items()}

    @staticmethod
    def _coverage(units, reference, kim_ids) -> dict:
        """Overlaps and gaps between units, and where they leave the RPJ outline of Serbia (`border`).

        Sampled along east-west lines COVERAGE_STEP_M apart; "widest_m" is the longest such run."""
        step = COVERAGE_STEP_M * SCALE
        to_km2 = step / SCALE**2 / 1e6
        part = lambda us: "-".join(sorted({"kim" if u in kim_ids else "rs" for u in us}))
        keys = [f"{kind}_{p}" for kind in ("overlap", "gap") for p in ("rs", "kim", "kim-rs")] + ["border_gap", "border_spill"]
        area, widest = Counter(dict.fromkeys(keys, 0)), Counter()
        for line in overlay([units, reference], step):
            runs = []
            for xa, xb, state in line:
                if runs and runs[-1][2] == state and runs[-1][1] == xa:
                    runs[-1][1] = xb
                else:
                    runs.append([xa, xb, state])
            for k, (xa, xb, (inside, ref)) in enumerate(runs):
                if len(inside) >= 2:
                    key = f"overlap_{part(inside)}"
                elif inside and not ref:
                    key = "border_spill"
                elif not inside and ref:
                    sides = [runs[j][2][0] for j in (k - 1, k + 1) if 0 <= j < len(runs)]
                    if len(sides) < 2 or not all(sides):
                        key = "border_gap"
                    else:
                        key = f"gap_{part(sides[0] | sides[1])}"
                else:
                    continue
                area[key] += (xb - xa) * to_km2
                widest[key] = max(widest[key], (xb - xa) / SCALE)
        return {k: {"km2": round(area[k], 3), "widest_m": round(widest[k])} for k in sorted(area)}

    @staticmethod
    def _lonlat(utm: UTM):
        cache: dict = {}

        def convert(rings):
            out = []
            for r in rings:
                ring = []
                for p in r:
                    q = cache.get(p)
                    if q is None:
                        lon, lat = utm.inverse(p[0] / SCALE, p[1] / SCALE)
                        q = cache[p] = [round(lon, 5), round(lat, 5)]
                    if not ring or q != ring[-1]:
                        ring.append(q)
                if len(ring) >= 4:
                    out.append(ring)
            return out

        return convert

    def _seats(self, by_id, shapes, kos, kim_rel, kim_nodes, kim_ids, utm) -> dict:
        osm = json.loads((self.raw_dir / "osm/rs_seats.json").read_text(encoding="utf-8"))
        nodes = {e["id"]: e for e in osm["elements"] if e["type"] == "node"}
        rels = {}
        for e in osm["elements"]:
            if e["type"] != "relation":
                continue
            for tag in ("ref:RS:grad", "ref:RS:opstina"):
                if re.fullmatch(r"\d{5}", e["tags"].get(tag, "")):
                    rels[e["tags"][tag]] = e
        places = defaultdict(list)
        for n in nodes.values():
            if n.get("tags", {}).get("place"):
                places[n["tags"].get("name:sr", n["tags"].get("name", "")).lower()].append(n)

        def xy(node):
            return tuple(c * SCALE for c in utm.forward(node["lon"], node["lat"]))

        def inside(node, uid):
            return contains(shapes[uid], *xy(node))

        def members(rel, role):
            return [nodes[m["ref"]] for m in (rel or {}).get("members", []) if m["role"] == role and m["ref"] in nodes]

        report = {"source": Counter(), "missing": [], "outside_unit": []}
        known = {plain(u["name_cyr"]).upper(): plain(u["name_cyr"]) for u in by_id.values()}
        for uid, u in by_id.items():
            if u["part"] == "kim":
                continue
            rel = rels.get(uid)
            centre = members(rel, "admin_centre")
            named = [n for n in places.get(plain(u["name_cyr"]).lower(), []) if inside(n, uid)]
            parent = rels.get(u["grad_code"]) if u["grad_code"] else None
            options = (
                ("admin_centre", [n for n in centre if n["tags"].get("place")]),
                ("named_place", named),
                ("admin_centre", centre),
                ("label", members(rel, "label")),
                ("grad_admin_centre", [n for n in members(parent, "admin_centre") if inside(n, uid)]),
            )
            how, node = next(((how, ns[0]) for how, ns in options if ns), (None, None))
            if node is None:
                report["missing"].append(uid)
                continue
            report["source"][how] += 1
            u["seat"] = self._seat(node, None)
            if not inside(node, uid):
                report["outside_unit"].append(uid)
        self._naselje_of_seats(by_id, xy, known)

        for i, uid in enumerate(kim_ids):
            centre = [kim_nodes[m["ref"]] for m in kim_rel[i]["members"] if m["role"] == "admin_centre" and m["ref"] in kim_nodes]
            if not centre:
                report["missing"].append(uid)
                continue
            node = centre[0]
            u = by_id[uid]
            u["seat"] = self._seat(node, node["tags"].get("name:sq"))
            report["source"]["admin_centre"] += 1
            p = xy(node)
            ko = next((k for k, (_, _, rings) in kos.items() if contains(rings, *p)), None)
            if ko:
                name = proper(kos[ko][0])
                u["seat"]["naselje"] = {"code": ko.split("-")[0], "name_cyr": name, "name_lat": latin(name)}
            if not contains(shapes[uid], *p):
                report["outside_unit"].append(uid)
        report["source"] = dict(report["source"])
        return report

    @staticmethod
    def _seat(node, name_sq) -> dict:
        t = node["tags"]
        name = t.get("name:sr") or t.get("name")
        pop = t.get("population", "").replace(" ", "")
        return {
            "name_cyr": name, "name_lat": latin(name), "name_sq": name_sq,
            "lon": round(node["lon"], 5), "lat": round(node["lat"], 5),
            "place": t.get("place"),
            "population": int(pop) if pop.isdigit() else None,
            "population_date": t.get("population:date"),
            "osm": f"node/{node['id']}",
            "naselje": None,
        }

    def _naselje_of_seats(self, by_id, xy, known):
        """The RPJ settlement each seat lies in; settlements are streamed, not kept (the layer is big)."""
        want = defaultdict(list)
        for code, u in by_id.items():
            if u["part"] == "rs" and u["seat"]:
                want["89010" if code in GRAD_PARTS["89010"] else code].append((u, xy(u["seat"])))
        for r in _csv_rows(self.raw_dir / "rpj/naselje.zip"):
            pending = [(u, p) for u, p in want.get(r["opstina_maticni_broj"], ()) if not u["seat"]["naselje"]]
            if not pending:
                continue
            rings = [ring for poly in wkt_polygons(r["wkt"], SCALE) for ring in poly]
            x0, y0, x1, y1 = bbox(rings)
            for u, (x, y) in pending:
                if x0 <= x <= x1 and y0 <= y <= y1 and contains(rings, x, y):
                    name = proper(r["naselje_ime"], known)
                    u["seat"]["naselje"] = {"code": r["naselje_maticni_broj"], "name_cyr": name, "name_lat": latin(name)}
