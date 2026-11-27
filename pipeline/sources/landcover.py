"""CORINE Land Cover 2018, resampled (nearest neighbour) from 100 m LAEA Europe to a lon/lat raster over the map."""

from __future__ import annotations

import hashlib
import math
import struct
import zlib

from ..core.source import Source, SourceInfo

RECORD = "12696960"
FILE = "CLC_Annual_TS_2018.tif"
URL = f"https://zenodo.org/records/{RECORD}/files/{FILE}"
MD5 = "9a0276a2212c05bfe0c7675c0ede5274"  # as published in the Zenodo record

WEST, SOUTH, EAST, NORTH = 18.0, 41.4, 23.8, 46.6
DLON, DLAT = 1 / 400, 1 / 600  # 9″ × 6″: 0.19-0.21 km east-west, 0.185 km north-south

# Raster value v (1..44) is CODES[v - 1]; anything else (48 "no data", 255 outside Europe) is no data.
CODES = [
    111, 112, 121, 122, 123, 124, 131, 132, 133, 141, 142, 211, 212, 213, 221, 222, 223, 231, 241, 242, 243, 244,
    311, 312, 313, 321, 322, 323, 324, 331, 332, 333, 334, 335, 411, 412, 421, 422, 423, 511, 512, 521, 522, 523,
]
CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQR"
NODATA = "."
CLASSES = {
    111: "Continuous urban fabric", 112: "Discontinuous urban fabric", 121: "Industrial or commercial units",
    122: "Road and rail networks and associated land", 123: "Port areas", 124: "Airports",
    131: "Mineral extraction sites", 132: "Dump sites", 133: "Construction sites", 141: "Green urban areas",
    142: "Sport and leisure facilities", 211: "Non-irrigated arable land", 212: "Permanently irrigated land",
    213: "Rice fields", 221: "Vineyards", 222: "Fruit trees and berry plantations", 223: "Olive groves",
    231: "Pastures", 241: "Annual crops associated with permanent crops", 242: "Complex cultivation patterns",
    243: "Land principally occupied by agriculture, with significant areas of natural vegetation",
    244: "Agro-forestry areas", 311: "Broad-leaved forest", 312: "Coniferous forest", 313: "Mixed forest",
    321: "Natural grasslands", 322: "Moors and heathland", 323: "Sclerophyllous vegetation",
    324: "Transitional woodland-shrub", 331: "Beaches, dunes, sands", 332: "Bare rocks",
    333: "Sparsely vegetated areas", 334: "Burnt areas", 335: "Glaciers and perpetual snow", 411: "Inland marshes",
    412: "Peat bogs", 421: "Salt marshes", 422: "Salines", 423: "Intertidal flats", 511: "Water courses",
    512: "Water bodies", 521: "Coastal lagoons", 522: "Estuaries", 523: "Sea and ocean",
}

_TAG_TYPES = {1: "B", 2: "s", 3: "H", 4: "I", 7: "B", 11: "f", 12: "d", 16: "Q"}


class Laea:
    """Ellipsoidal Lambert azimuthal equal-area, EPSG:3035 defaults (ETRS89 / LAEA Europe), output in metres."""

    def __init__(self, lat0=52.0, lon0=10.0, fe=4321000.0, fn=3210000.0, a=6378137.0, inv_f=298.257222101):
        f = 1 / inv_f
        self.e2 = f * (2 - f)
        self.e = math.sqrt(self.e2)
        self.lon0, self.fe, self.fn = math.radians(lon0), fe, fn
        phi0 = math.radians(lat0)
        self.qp = self._q(math.pi / 2)
        b0 = math.asin(self._q(phi0) / self.qp)
        self.sb0, self.cb0 = math.sin(b0), math.cos(b0)
        self.rq = a * math.sqrt(self.qp / 2)
        self.d = a * math.cos(phi0) / math.sqrt(1 - self.e2 * math.sin(phi0) ** 2) / (self.rq * self.cb0)

    def _q(self, phi: float) -> float:
        s, e = math.sin(phi), self.e
        return (1 - self.e2) * (s / (1 - self.e2 * s * s) - math.log((1 - e * s) / (1 + e * s)) / (2 * e))

    def beta(self, lat: float) -> tuple[float, float]:
        b = math.asin(self._q(math.radians(lat)) / self.qp)
        return math.sin(b), math.cos(b)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        sb, cb = self.beta(lat)
        dl = math.radians(lon) - self.lon0
        k = self.rq * math.sqrt(2 / (1 + self.sb0 * sb + self.cb0 * cb * math.cos(dl)))
        return (self.fe + k * self.d * cb * math.sin(dl),
                self.fn + k / self.d * (self.cb0 * sb - self.sb0 * cb * math.cos(dl)))


def _read_tags(f) -> dict:
    """Tags of the first IFD of a classic (not Big) TIFF, as tuples (bytes for ASCII)."""
    head = f.read(8)
    bo = {b"II": "<", b"MM": ">"}.get(head[:2])
    if bo is None or struct.unpack(bo + "H", head[2:4])[0] != 42:
        raise ValueError("not a classic TIFF file")
    f.seek(struct.unpack(bo + "I", head[4:8])[0])
    entries = [struct.unpack(bo + "HHI4s", f.read(12)) for _ in range(struct.unpack(bo + "H", f.read(2))[0])]
    tags = {}
    for tag, typ, count, inline in entries:
        fmt = _TAG_TYPES.get(typ)
        if fmt is None:
            continue
        size = struct.calcsize(bo + fmt) * count
        if size <= 4:
            raw = inline[:size]
        else:
            f.seek(struct.unpack(bo + "I", inline)[0])
            raw = f.read(size)
        tags[tag] = raw if typ == 2 else struct.unpack(f"{bo}{count}{fmt}", raw)
    return tags


def _geokeys(tags: dict) -> dict:
    keys = tags.get(34735, ())
    return {keys[i]: keys[i + 3] for i in range(4, len(keys), 4) if keys[i + 1] == 0}


class Landcover(Source):
    info = SourceInfo(
        id="landcover",
        title="CORINE Land Cover 2018 (100 m)",
        publisher="European Environment Agency, Copernicus Land Monitoring Service; redistributed by the LAMASUS "
        "project on Zenodo",
        homepage="https://land.copernicus.eu/en/products/corine-land-cover",
        license="© European Union, Copernicus Land Monitoring Service 2018, European Environment Agency (EEA). Free, "
        "full and open access under the Copernicus data policy; this copy CC BY 4.0 (See et al. 2024, LAMASUS Annual "
        "Corine Land Cover Time Series, doi:10.5281/zenodo.12696960)",
        description="The 44 CORINE Land Cover classes, mapped from satellite imagery with a 25 ha minimum mapping "
        "unit (the 2018 accounting layer, 100 m raster in ETRS89 / LAEA Europe). Resampled by nearest neighbour to a "
        "9″ × 6″ (about 0.2 km) longitude/latitude raster over the map window, covering Serbia, Kosovo and Metohija and "
        "all the neighbours; the open Adriatic is no data. Each hex's land cover (forest, farmland, vineyards and "
        "orchards, pasture, urban, water…) and its land-cover shares come from the pixels inside it.",
        used_for=["Hex land cover (biomes)", "Forest / cropland / developed shares", "Inland water"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        path = self.raw_dir / FILE
        md5 = hashlib.md5(path.read_bytes()).hexdigest()
        if md5 != MD5:
            raise ValueError(f"{FILE} md5 {md5} differs from the Zenodo record's {MD5}: re-run fetch --force")
        laea = Laea()
        cols = round((EAST - WEST) / DLON)
        rows_n = round((NORTH - SOUTH) / DLAT)
        lons = [WEST + (c + 0.5) * DLON for c in range(cols)]
        lats = [NORTH - (r + 0.5) * DLAT for r in range(rows_n)]

        with open(path, "rb") as f:
            tags = _read_tags(f)
            width, height = tags[256][0], tags[257][0]
            compression = tags.get(259, (1,))[0]
            if tags.get(258, (8,))[0] != 8 or tags.get(277, (1,))[0] != 1 or compression not in (1, 8, 32946):
                raise ValueError(f"unsupported TIFF layout: bits {tags.get(258)}, samples {tags.get(277)}, "
                                 f"compression {compression}")
            if tags.get(317, (1,))[0] != 1 or 322 in tags:
                raise ValueError("unsupported TIFF layout: predictor or tiles")
            geokeys = _geokeys(tags)
            if geokeys.get(3072) != 3035:
                raise ValueError(f"expected EPSG:3035, got ProjectedCSTypeGeoKey {geokeys.get(3072)}")
            res_x, res_y = tags[33550][0], tags[33550][1]
            _, _, _, x_min, y_max, _ = tags[33922]
            if geokeys.get(1025) == 2:  # PixelIsPoint: the tie point is the first pixel's centre
                x_min, y_max = x_min - res_x / 2, y_max + res_y / 2

            edge = [(lon, lat) for lon in (WEST, EAST) for lat in lats] + [(lon, lat) for lat in (SOUTH, NORTH) for lon in lons]
            xs, ys = zip(*(laea(lon, lat) for lon, lat in edge))
            r0, r1 = max(0, int((y_max - max(ys)) / res_y) - 2), min(height - 1, int((y_max - min(ys)) / res_y) + 2)
            c0, c1 = max(0, int((min(xs) - x_min) / res_x) - 2), min(width - 1, int((max(xs) - x_min) / res_x) + 2)

            per_strip = tags.get(278, (height,))[0]
            offsets, counts = tags[273], tags[279]
            src = []  # source rows r0..r1, columns c0..c1
            for s in range(r0 // per_strip, r1 // per_strip + 1):
                f.seek(offsets[s])
                block = f.read(counts[s])
                if compression != 1:
                    block = zlib.decompress(block)
                for k in range(len(block) // width):
                    if r0 <= s * per_strip + k <= r1:
                        src.append(block[k * width + c0: k * width + c1 + 1])

        lut = bytearray(NODATA.encode() * 256)
        for v, ch in enumerate(CHARS, start=1):
            lut[v] = ord(ch)
        trig = [(math.cos(math.radians(lon) - laea.lon0), math.sin(math.radians(lon) - laea.lon0)) for lon in lons]
        sb0, cb0, rq, d, fe, fn = laea.sb0, laea.cb0, laea.rq, laea.d, laea.fe, laea.fn
        n_src, w_src = len(src), c1 - c0 + 1
        out_rows = []
        for lat in lats:
            sb, cb = laea.beta(lat)
            k1, k2, k3, k4 = sb0 * sb, cb0 * cb, cb0 * sb, sb0 * cb
            row = bytearray(cols)
            for c, (cl, sl) in enumerate(trig):
                t = rq * math.sqrt(2 / (1 + k1 + k2 * cl))
                sr = int((y_max - (fn + t / d * (k3 - k4 * cl))) / res_y) - r0
                sc = int((fe + t * d * cb * sl - x_min) / res_x) - c0
                row[c] = src[sr][sc] if 0 <= sr < n_src and 0 <= sc < w_src else 0
            out_rows.append(row.translate(lut).decode("ascii"))

        counts_by_char: dict[str, int] = {}
        for r in out_rows:
            for ch in set(r):
                counts_by_char[ch] = counts_by_char.get(ch, 0) + r.count(ch)
        total = cols * rows_n
        print(f"    {cols}×{rows_n} pixels, {100 * counts_by_char.get(NODATA, 0) / total:.1f}% no data; "
              f"{len(counts_by_char) - (NODATA in counts_by_char)} CLC classes present")
        legend = {NODATA: 0, **{ch: code for ch, code in zip(CHARS, CODES)}}
        return {
            "vintage": "CORINE Land Cover 2018 (accounting layer, 100 m), resampled to 9″ × 6″",
            "_files": [FILE],
            "crs": "EPSG:4326",
            # Pixel CENTRE of column 0 / row 0 and pixel size, in degrees (dy is negative: rows go south).
            "x0": lons[0], "dx": DLON,
            "y0": lats[0], "dy": -DLAT,
            "cols": cols, "rows_n": rows_n,
            "legend": legend,
            "classes": CLASSES,
            "rows": out_rows,
        }
