import hashlib
import json
import re
import struct
import urllib.parse

from ..core.geo import bbox_intersects
from ..core.source import Source, SourceInfo

# Pinned to a release tag so the content (and sha256) cannot change under the same URL.
TAG = "v5.1.2"
REPO = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{TAG}"
BBOX = (17.5, 40.9, 24.3, 47.1)  # the map window (18.0-23.8 °E, 41.4-46.6 °N) plus half a degree
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_BATCH = 50  # wbgetentities' limit per request


def read_dbf(path) -> list[dict]:
    """dBASE III attribute table: one dict per record; numeric fields as int/float, blanks as None."""
    data = path.read_bytes()
    n, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        fields.append((data[pos:pos + 11].split(b"\0")[0].decode("ascii"), chr(data[pos + 11]), data[pos + 16]))
        pos += 32
    records = []
    for k in range(n):
        start = header_len + k * record_len + 1  # skip the deletion flag
        record = {}
        for name, kind, size in fields:
            text = data[start:start + size].replace(b"\0", b" ").decode("utf-8", "replace").strip()
            start += size
            if kind in "NF" and text and text.strip("*"):
                record[name] = float(text) if any(ch in text for ch in ".eE") else int(text)
            else:
                record[name] = text or None
        records.append(record)
    return records


def read_shp(path) -> list[list[list[tuple[float, float]]]]:
    """Parts (polyline paths or polygon rings) of every record of a polyline/polygon shapefile, as (lon, lat)."""
    data = path.read_bytes()
    pos, shapes = 100, []
    while pos < len(data):
        words = struct.unpack(">i", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + 2 * words]
        pos += 8 + 2 * words
        if struct.unpack("<i", body[:4])[0] == 0:  # null shape
            shapes.append([])
            continue
        n_parts, n_points = struct.unpack("<ii", body[36:44])
        starts = struct.unpack(f"<{n_parts}i", body[44:44 + 4 * n_parts]) + (n_points,)
        xy = struct.unpack(f"<{2 * n_points}d", body[44 + 4 * n_parts:44 + 4 * n_parts + 16 * n_points])
        shapes.append([[(round(xy[2 * k], 5), round(xy[2 * k + 1], 5)) for k in range(a, b)]
                       for a, b in zip(starts, starts[1:])])
    return shapes


def is_cyrillic(text: str | None) -> bool:
    return bool(text) and any(0x400 <= ord(ch) <= 0x4FF for ch in text)


class NaturalEarth(Source):
    info = SourceInfo(
        id="natural_earth",
        title="Natural Earth 1:10m (countries, lakes, rivers), with Serbian names from Wikidata",
        publisher="Natural Earth; names: Wikidata",
        homepage="https://www.naturalearthdata.com/",
        license="Natural Earth: public domain. Wikidata labels: CC0",
        description="Serbia's outline and the neighbouring countries (shown fogged) from the 1:10m admin-0 countries "
        "in the ISO 3166 point of view, which keeps Kosovo and Metohija within Serbia (Natural Earth publishes no "
        "Serbian point of view; ISO 3166-1 has no Kosovo entry). Lakes and rivers are the 1:10m global layers plus "
        "the 1:10m Europe supplement. Read from the shapefiles of the natural-earth-vector release "
        f"{TAG} (its GeoJSON export of the river centerlines is older and lacks Wikidata ids). Serbian (Cyrillic) "
        "names are the Wikidata labels of each feature's Wikidata id.",
        used_for=["Serbia's outline", "Foreign land (the neighbouring countries)", "Lakes", "Rivers", "Serbian names"],
    )

    COUNTRIES = "10m_cultural/ne_10m_admin_0_countries_iso"
    LAKES = ["10m_physical/ne_10m_lakes", "10m_physical/ne_10m_lakes_europe"]
    RIVERS = ["10m_physical/ne_10m_rivers_lake_centerlines", "10m_physical/ne_10m_rivers_europe"]
    LAYERS = [COUNTRIES, *LAKES, *RIVERS]

    def _path(self, layer, ext):
        return f"{TAG}/{layer.rsplit('/', 1)[1]}.{ext}"

    def _layer(self, layer):
        shapes = read_shp(self.raw_dir / self._path(layer, "shp"))
        records = read_dbf(self.raw_dir / self._path(layer, "dbf"))
        if len(shapes) != len(records):
            raise ValueError(f"{layer}: {len(shapes)} shapes but {len(records)} attribute records")
        return zip(records, shapes)

    def _in_window(self):
        """(kind, record, parts in the window) for every feature the interim keeps."""
        for rec, parts in self._layer(self.COUNTRIES):
            keep = parts if rec["ADM0_A3"] == "SRB" else [r for r in parts if bbox_intersects(r, BBOX)]
            if keep:
                yield "country", rec, keep
        for layer in self.LAKES:
            for rec, parts in self._layer(layer):
                if parts and bbox_intersects(parts[0], BBOX):
                    yield "lake", rec, parts
        for layer in self.RIVERS:
            for rec, parts in self._layer(layer):
                if keep := [line for line in parts if bbox_intersects(line, BBOX)]:
                    yield "river", rec, keep

    @staticmethod
    def _wikidata_files(features) -> list[tuple[str, list[str]]]:
        ids = sorted({rec.get("WIKIDATAID") or rec.get("wikidataid") for _, rec, _ in features} - {None})
        batches = [ids[k:k + WIKIDATA_BATCH] for k in range(0, len(ids), WIKIDATA_BATCH)]
        return [(f"wikidata/labels_sr_{hashlib.sha1('|'.join(b).encode()).hexdigest()[:12]}.json", b) for b in batches]

    def fetch(self, force=False):
        for layer in self.LAYERS:
            for ext in ("shp", "dbf"):
                self.download(f"{REPO}/{layer}.{ext}", self._path(layer, ext), force=force)
        for rel, ids in self._wikidata_files(list(self._in_window())):
            query = urllib.parse.urlencode({
                "action": "wbgetentities", "format": "json", "props": "labels", "languages": "sr|sr-ec", "ids": "|".join(ids),
            })
            self.download(f"{WIKIDATA_API}?{query}", rel, force=force)

    def process(self):
        features = list(self._in_window())
        files = [self._path(layer, ext) for layer in self.LAYERS for ext in ("shp", "dbf")]
        name_sr = {}
        for rel, _ in self._wikidata_files(features):
            files.append(rel)
            for qid, entity in json.loads((self.raw_dir / rel).read_text(encoding="utf-8"))["entities"].items():
                values = [entity.get("labels", {}).get(lang, {}).get("value") for lang in ("sr-ec", "sr")]
                label = next((v for v in values if is_cyrillic(v)), None)
                label = label and re.sub(r"\s*\([^)]*\)$", "", label)  # "Шио (река)": a disambiguator, not the name
                name_sr[qid] = name_sr[entity.get("id", qid)] = label
                if "redirects" in entity:
                    name_sr[entity["redirects"]["from"]] = label

        serbia, countries, lakes, rivers = None, [], [], []
        for kind, rec, parts in features:
            qid = rec.get("WIKIDATAID") or rec.get("wikidataid")
            if kind == "country":
                if rec["ADM0_A3"] in ("KOS", "XKX"):
                    raise ValueError(f"{self.COUNTRIES} maps Kosovo as a separate country")
                item = {"name": rec["ADMIN"], "name_sr": name_sr.get(qid), "iso_a3": rec["ADM0_A3"], "wikidata": qid, "rings": parts}
                if rec["ADM0_A3"] == "SRB":
                    serbia = item
                else:
                    countries.append(item)
            elif kind == "lake":
                lakes.append({"name": rec.get("name"), "name_sr": name_sr.get(qid), "rank": rec.get("scalerank"),
                              "featurecla": rec.get("featurecla"), "wikidata": qid, "rings": parts})
            else:
                for line in parts:
                    rivers.append({"name": rec.get("name"), "name_en": rec.get("name_en"), "name_sr": name_sr.get(qid),
                                   "rank": rec.get("scalerank", 10), "featurecla": rec.get("featurecla"), "wikidata": qid,
                                   "line": line})
        if serbia is None:
            raise ValueError(f"no Serbia (ADM0_A3 SRB) in {self.COUNTRIES}")
        named = sum(1 for f in [serbia, *countries, *lakes, *rivers] if f["name_sr"])
        print(f"    Serbia + {len(countries)} neighbours, {len(lakes)} lakes, {len(rivers)} river lines; "
              f"{named} of {1 + len(countries) + len(lakes) + len(rivers)} with a Serbian name")
        return {
            "vintage": f"Natural Earth {TAG} (1:10m, ISO 3166 point of view)",
            "_files": files,
            "serbia": serbia,
            "countries": countries,
            "lakes": lakes,
            "rivers": rivers,
        }
