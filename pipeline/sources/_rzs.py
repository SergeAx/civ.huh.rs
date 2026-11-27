"""Helpers shared by the RZS sources (Statistical Office of the Republic of Serbia, stat.gov.rs).

Not a source itself (no SourceInfo), so the registry ignores it.

* Tables come from RZS's open-data service: ``<ODATA>/<table id>/<language>/csv``, one flat CSV per
  table with one row per cell (``IDTer`` territory, one ``ID…``/``n…`` column pair per dimension, ``god``
  year, ``vrednost`` value, ``IDStatusPodatka`` status). Big tables arrive as a zip holding that CSV.
* Territories are RZS's own codes: 5-digit municipality codes (SIFOPS code list) and NSTJ codes
  (``RS`` nation, ``RS11`` regions, ``RS110`` oblasti = okruzi). RZS has published nothing on
  Kosovo and Metohija (``RS23*``, municipality codes ``9xxxx``) since 1999; those are left out here.
* A small PDF text extractor reads the tables RZS publishes only as PDF (regional GVA by oblast).
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
import zlib
from pathlib import Path
from typing import Iterator

from ..core.source import Source

ODATA = "https://opendata.stat.gov.rs/data/WcfJsonRestService.Service1.svc/dataset"
CYR, LAT = 1, 2  # the service's language ids (3 = English)


def dataset_url(table: str, lang: int = CYR) -> str:
    return f"{ODATA}/{table}/{lang}/csv"


def read_table(path: Path) -> Iterator[dict[str, str]]:
    """Rows of an RZS CSV (plain or zipped) with keys and values stripped."""
    with open(path, "rb") as f:
        zipped = f.read(2) == b"PK"
    if zipped:
        with zipfile.ZipFile(path) as z:
            with z.open(z.namelist()[0]) as raw:
                yield from _rows(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
    else:
        with open(path, encoding="utf-8-sig", newline="") as f:
            yield from _rows(f)


def _rows(f) -> Iterator[dict[str, str]]:
    for row in csv.DictReader(f):
        yield {k.strip(): (v or "").strip() for k, v in row.items() if k}


def value(row: dict[str, str], *, m_as_zero: bool = True) -> float | None:
    """The cell's number. Status M ("data cannot exist") is RZS's "-", i.e. no occurrence: 0 for counts.
    Status O ("not available") and any other empty cell is None."""
    v = row.get("vrednost", "")
    if v:
        return float(v)
    return 0.0 if m_as_zero and row.get("IDStatusPodatka") == "M" else None


def pivot(path: Path, codes, dims: str | tuple[str, ...], fixed: dict[str, str] | None = None,
          year: str | None = None, m_as_zero: bool = True) -> tuple[dict, dict]:
    """({territory: {category: value}}, {category: label}) for the rows of the territories in `codes`
    whose other dimensions equal `fixed` (e.g. {"IDPol": "0"}). With several `dims` the category is a tuple."""
    multi = not isinstance(dims, str)
    out: dict[str, dict] = {}
    labels: dict = {}
    for r in read_table(path):
        t = r["IDTer"]
        if t not in codes or (year is not None and r["god"] != year):
            continue
        if fixed and any(r.get(k) != v for k, v in fixed.items()):
            continue
        cat = tuple(r[d] for d in dims) if multi else r[dims]
        out.setdefault(t, {})[cat] = value(r, m_as_zero=m_as_zero)
        if not multi:
            labels.setdefault(cat, r.get("n" + dims[2:]) or r.get("n" + dims[2:].lower()) or "")
    return out, labels


def latest_year(path: Path, territory: str = "RS", **fixed: str) -> str:
    """Newest year (``god``) with a value for `territory` among rows matching `fixed`."""
    years = [r["god"] for r in read_table(path)
             if r["IDTer"] == territory and r["vrednost"] and all(r.get(k) == v for k, v in fixed.items())]
    if not years:
        raise ValueError(f"{path.name}: no values for {territory}")
    return max(years)


def as_int(v: float | None) -> int | None:
    return None if v is None else int(round(v))


_LAT = str.maketrans({
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J",
    "К": "K", "Л": "L", "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Џ": "Dž", "Ш": "Š",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i", "ј": "j",
    "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "ћ": "ć", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "č", "џ": "dž", "ш": "š",
})


def to_latin(s: str) -> str:
    return s.translate(_LAT)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# --- territory ----------------------------------------------------------------

# Cities with gradske opštine that RZS reports separately (statutes of the cities).
GRAD_PARTS = {
    "79014": ("70092", "70106", "70114", "70122", "70149", "70157", "70165", "70173", "70181", "70190", "70203",
              "70211", "70220", "70238", "70246", "70254", "71293"),  # Beograd
    "79022": ("71285", "71307", "71315", "71323", "71331"),  # Niš
    "79049": ("70947", "71340"),  # Požarevac
    "79057": ("70432", "71358"),  # Vranje
    "79065": ("71145", "71366"),  # Užice
    "89010": ("80284", "80519"),  # Novi Sad
}
# Local self-government units with city status (Zakon o teritorijalnoj organizaciji), outside KiM.
GRADOVI = frozenset({
    *GRAD_PARTS, "70327", "70360", "80128", "70556", "80152", "71048", "80209", "70645", "70653", "70670",
    "70726", "70734", "70874", "80314", "70939", "70998", "71099", "80381", "80403", "80438", "71242", "71269",
})
# NSTJ oblast -> administrative okrug code (Uredba o upravnim okruzima; Grad Beograd = "00").
OKRUG = {
    "RS110": "00", "RS125": "01", "RS126": "02", "RS124": "03", "RS122": "04", "RS121": "05", "RS123": "06",
    "RS127": "07", "RS213": "08", "RS212": "09", "RS227": "10", "RS222": "11", "RS218": "12", "RS215": "13",
    "RS221": "14", "RS223": "15", "RS211": "16", "RS214": "17", "RS217": "18", "RS216": "19", "RS225": "20",
    "RS229": "21", "RS226": "22", "RS224": "23", "RS228": "24",
}
REGIONS = ("RS11", "RS12", "RS21", "RS22")


class Territory:
    """RZS municipality codes (SIFOPS) and NSTJ areas, outside Kosovo and Metohija."""

    def __init__(self, sifops_cyr: Path, sifops_lat: Path, nstj_cyr: Path, nstj_lat: Path):
        lat = {r["MBOPS"]: clean(r["nOPS"]) for r in read_table(sifops_lat)}
        self.municipalities: dict[str, dict] = {}
        for r in read_table(sifops_cyr):
            if r["IDNSTJ"] in OKRUG:
                self.municipalities[r["MBOPS"]] = {"name_cyr": clean(r["nOPS"]), "name_lat": lat[r["MBOPS"]],
                                                   "oblast": r["IDNSTJ"]}
        nlat = {r["IDNSTJ"]: clean(r["nNSTJ"]) for r in read_table(nstj_lat)}
        self.areas = {r["IDNSTJ"]: {"name_cyr": clean(r["nNSTJ"]), "name_lat": nlat[r["IDNSTJ"]]}
                      for r in read_table(nstj_cyr) if r["IDNSTJ"] in ("RS", *REGIONS, *OKRUG)}
        self.parent = {go: grad for grad, parts in GRAD_PARTS.items() for go in parts}
        self.codes = set(self.municipalities) | set(self.areas)

    def unit(self, code: str, present) -> dict:
        """Descriptive fields of a municipality-level unit; `present` = codes of all units in the output."""
        m = self.municipalities[code]
        oblast, region = m["oblast"], m["oblast"][:4]
        level = "gradska_opstina" if code in self.parent else "grad" if code in GRADOVI else "opstina"
        return {
            "name_cyr": m["name_cyr"], "name_lat": m["name_lat"], "level": level,
            "grad_code": self.parent.get(code),
            "aggregate": any(p in present for p in GRAD_PARTS.get(code, ())),
            "okrug_code": OKRUG[oblast], "oblast_code": oblast,
            "okrug_name_cyr": self.areas[oblast]["name_cyr"], "okrug_name_lat": self.areas[oblast]["name_lat"],
            "region_code": region,
            "region_name_cyr": self.areas[region]["name_cyr"], "region_name_lat": self.areas[region]["name_lat"],
        }

    def oblast(self, nstj: str) -> dict:
        region = nstj[:4]
        return {
            "nstj_code": nstj, "name_cyr": self.areas[nstj]["name_cyr"], "name_lat": self.areas[nstj]["name_lat"],
            "region_code": region,
            "region_name_cyr": self.areas[region]["name_cyr"], "region_name_lat": self.areas[region]["name_lat"],
        }

    def region(self, nstj: str) -> dict:
        return {"name_cyr": self.areas[nstj]["name_cyr"], "name_lat": self.areas[nstj]["name_lat"]}

    def assemble(self, per_code: dict[str, dict]) -> dict:
        """{"units", "okruzi", "regions", "nation"} from {RZS territory code: fields}. Okruzi are keyed by
        okrug code; units are only the municipality-level codes that appear in `per_code`."""
        present = {c for c in per_code if c in self.municipalities}
        return {
            "units": {c: {**self.unit(c, present), **per_code[c]} for c in sorted(present)},
            "okruzi": {OKRUG[o]: {**self.oblast(o), **per_code[o]} for o in sorted(OKRUG, key=OKRUG.get)
                       if o in per_code},
            "regions": {r: {**self.region(r), **per_code[r]} for r in REGIONS if r in per_code},
            "nation": per_code.get("RS", {}),
        }


class RzsSource(Source):
    """Fetches the territory code lists plus `tables` ({table id: "csv" or "zip"}) from the open-data service."""

    tables: dict[str, str] = {}
    CODE_LISTS = {"SIFOPS_cyr.csv": ("SIFOPS", CYR), "SIFOPS_lat.csv": ("SIFOPS", LAT),
                  "NSTJ_cyr.csv": ("NSTJ", CYR), "NSTJ_lat.csv": ("NSTJ", LAT)}

    def rel(self, table: str) -> str:
        return f"{table}.{self.tables[table]}"

    def path(self, table: str) -> Path:
        return self.raw_dir / self.rel(table)

    def fetch(self, force: bool = False) -> None:
        for rel, (table, lang) in self.CODE_LISTS.items():
            self.download(dataset_url(table, lang), rel, force=force, expect_binary=True)
        for table in self.tables:
            self.download(dataset_url(table), self.rel(table), force=force, expect_binary=True)

    def territory(self) -> Territory:
        return Territory(*(self.raw_dir / rel for rel in self.CODE_LISTS))

    def files(self) -> list[str]:
        return [*self.CODE_LISTS, *(self.rel(t) for t in self.tables)]


def categorize(values: dict | None, cats: dict[str, str], total: str | None) -> dict[str, int | None] | None:
    """{key: count} for RZS category codes `cats` ({code: key}). A category with no row is 0 when the unit
    has a total (RZS leaves out empty cells; the categories add up to the total), else None."""
    if not values:
        return None
    known = total is None or values.get(total) is not None
    return {key: as_int(values.get(code, 0.0 if known else None)) for code, key in cats.items()}


def category_list(cats: dict[str, str], labels: dict[str, str], notes: dict[str, str] | None = None) -> list[dict]:
    out = []
    for code, key in cats.items():
        name = clean(labels.get(code, ""))
        item = {"key": key, "rzs_code": code, "name_cyr": name, "name_lat": to_latin(name)}
        if notes and key in notes:
            item["note"] = notes[key]
        out.append(item)
    return out


# --- PDF tables -----------------------------------------------------------------

_TOKEN = re.compile(
    rb"\s+|%[^\r\n]*"
    rb"|(?P<name>/[^\s()<>\[\]{}/%]*)"
    rb"|(?P<dict><<|>>)"
    rb"|(?P<arr>[\[\]{}])"
    rb"|(?P<hex><[0-9A-Fa-f\s]*>)"
    rb"|(?P<str>\()"
    rb"|(?P<word>[^\s()<>\[\]{}/%]+)"
)
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}


class _Ref(int):
    pass


class _Op(str):
    pass


def _literal(data: bytes, i: int) -> tuple[bytes, int]:
    depth, out = 1, bytearray()
    while True:
        ch = data[i]
        if ch == 0x5C:
            nxt = data[i + 1:i + 2]
            if nxt in _ESC:
                out += _ESC[nxt]
                i += 2
            elif nxt.isdigit():
                octal = re.match(rb"[0-7]{1,3}", data[i + 1:i + 4]).group(0)
                out.append(int(octal, 8) & 0xFF)
                i += 1 + len(octal)
            else:
                i += 3 if data[i + 1:i + 3] == b"\r\n" else 2
            continue
        if ch == 0x28:
            depth += 1
        elif ch == 0x29:
            depth -= 1
            if not depth:
                return bytes(out), i + 1
        out.append(ch)
        i += 1


def _tokens(data: bytes, i: int = 0, end: int | None = None):
    end = len(data) if end is None else end
    while i < end:
        m = _TOKEN.match(data, i)
        if not m:
            raise ValueError(f"bad PDF token at byte {i}")
        i = m.end()
        kind = m.lastgroup
        if kind is None:
            continue
        tok = m.group(kind)
        if kind == "name":
            yield re.sub(rb"#([0-9A-Fa-f]{2})", lambda x: bytes([int(x.group(1), 16)]), tok[1:]).decode("latin-1"), i
        elif kind in ("dict", "arr"):
            yield _Op(tok.decode()), i
        elif kind == "hex":
            hx = re.sub(rb"\s", b"", tok[1:-1])
            yield bytes.fromhex((hx + b"0" * (len(hx) % 2)).decode()), i
        elif kind == "str":
            s, i = _literal(data, i)
            yield s, i
        else:
            w = tok.decode("latin-1")
            if re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)", w):
                yield (float(w) if "." in w else int(w)), i
            else:
                yield _Op(w), i


def _parse(toks: list, k: int = 0):
    t = toks[k]
    if t == "<<":
        d, k = {}, k + 1
        while toks[k] != ">>":
            d[toks[k]], k = _parse(toks, k + 1)
        return d, k + 1
    if t == "[":
        a, k = [], k + 1
        while toks[k] != "]":
            v, k = _parse(toks, k)
            a.append(v)
        return a, k + 1
    if type(t) is int and k + 2 < len(toks) and type(toks[k + 1]) is int and toks[k + 2] == "R":
        return _Ref(t), k + 3
    return t, k + 1


def _mul(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2],
            a[2] * b[1] + a[3] * b[3], a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


class Pdf:
    """Just enough of PDF to read the text of a born-digital report: objects and object streams,
    Flate streams, the page tree, ToUnicode maps and the text-positioning operators."""

    def __init__(self, path: Path):
        self.data = data = path.read_bytes()
        self.objs: dict[int, tuple] = {}
        for m in re.finditer(rb"(?<![0-9])(\d+)\s+\d+\s+obj\b", data):
            try:
                self._read(int(m.group(1)), m.end())
            except (ValueError, IndexError, KeyError):
                continue
        for val, raw in list(self.objs.values()):
            if isinstance(val, dict) and val.get("Type") == "ObjStm":
                self._expand(val, raw)

    def _read(self, num: int, pos: int) -> None:
        toks, tok, after = [], None, pos
        for tok, after in _tokens(self.data, pos):
            if tok in ("endobj", "stream"):
                break
            toks.append(tok)
        val = _parse(toks)[0]
        raw = None
        if tok == "stream":
            p = after + (2 if self.data[after:after + 2] == b"\r\n" else 1)
            length = val.get("Length")
            if isinstance(length, _Ref):
                length = self.objs.get(length, (None,))[0]
            if not isinstance(length, int):
                length = self.data.index(b"endstream", p) - p
            raw = self.data[p:p + length]
        self.objs[num] = (val, raw)

    def _expand(self, d: dict, raw: bytes) -> None:
        s = self._decode(d, raw)
        first = d["First"]
        hdr = [t for t, _ in _tokens(s, 0, first)]
        for k in range(d["N"]):
            num, off = hdr[2 * k], hdr[2 * k + 1]
            end = hdr[2 * k + 3] if k + 1 < d["N"] else len(s) - first
            toks = [t for t, _ in _tokens(s, first + off, first + end)]
            if toks:
                self.objs.setdefault(num, (_parse(toks)[0], None))

    @staticmethod
    def _decode(d: dict, raw: bytes) -> bytes:
        f = d.get("Filter")
        f = f[0] if isinstance(f, list) and len(f) == 1 else f
        if f == "FlateDecode":
            return zlib.decompressobj().decompress(raw)
        if f is None:
            return raw
        raise ValueError(f"unsupported PDF filter {f}")

    def get(self, x):
        while isinstance(x, _Ref):
            x = self.objs.get(x, (None,))[0]
        return x

    def stream(self, ref) -> bytes:
        val, raw = self.objs[ref]
        return self._decode(val, raw)

    def pages(self) -> list[tuple[dict, dict]]:
        root = next(v for v, _ in self.objs.values() if isinstance(v, dict) and v.get("Type") == "Catalog")
        out = []

        def walk(node, inherited):
            node = self.get(node)
            res = node.get("Resources", inherited)
            if node.get("Type") == "Pages":
                for kid in node["Kids"]:
                    walk(kid, res)
            else:
                out.append((node, self.get(res) or {}))

        walk(root["Pages"], None)
        return out

    def _font(self, ref) -> tuple[dict[int, str], int]:
        def utf16(h: bytes) -> str:
            return bytes.fromhex(h.decode()).decode("utf-16-be")

        font = self.get(ref)
        width = 2 if font.get("Subtype") == "Type0" else 1
        cmap: dict[int, str] = {}
        if font.get("ToUnicode") is None:
            return cmap, width
        s = self.stream(font["ToUnicode"])
        for block in re.findall(rb"beginbfchar(.*?)endbfchar", s, re.S):
            for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
                cmap[int(src, 16)] = utf16(dst)
        for block in re.findall(rb"beginbfrange(.*?)endbfrange", s, re.S):
            for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])", block):
                lo, hi = int(lo, 16), int(hi, 16)
                if dst.startswith(b"["):
                    for k, h in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", dst)):
                        cmap[lo + k] = utf16(h)
                else:
                    base = utf16(dst[1:-1])
                    for k in range(hi - lo + 1):
                        cmap[lo + k] = base[:-1] + chr(ord(base[-1]) + k)
        return cmap, width

    def runs(self, page_index: int) -> list[tuple[float, float, str]]:
        """[(x, y, text)] of every text-showing operator on a page, in content order (y grows upwards)."""
        page, res = self.pages()[page_index]
        fonts = {name: self._font(ref) for name, ref in (self.get(res.get("Font")) or {}).items()}
        contents = page.get("Contents")
        if isinstance(self.get(contents), list):
            contents = self.get(contents)
        if contents is None:
            return []
        data = b"\n".join(self.stream(c) for c in (contents if isinstance(contents, list) else [contents]))
        toks = [t for t, _ in _tokens(data)]
        out, operands, stack = [], [], []
        ident = [1, 0, 0, 1, 0, 0]
        ctm, tm, lm, leading, font = ident, ident, ident, 0, ({}, 1)

        def show(s: bytes) -> None:
            cmap, w = font
            codes = (int.from_bytes(s[i:i + w], "big") for i in range(0, len(s), w))
            full = _mul(tm, ctm)
            out.append((round(full[4], 1), round(full[5], 1), "".join(cmap.get(c, chr(c) if w == 1 else "�") for c in codes)))

        k = 0
        while k < len(toks):
            t = toks[k]
            if t in ("[", "<<"):
                v, k = _parse(toks, k)
                operands.append(v)
                continue
            k += 1
            if not isinstance(t, _Op):
                operands.append(t)
                continue
            if t == "BI":
                while k < len(toks) and toks[k] != "EI":
                    k += 1
                k += 1
            elif t == "q":
                stack.append(ctm)
            elif t == "Q":
                ctm = stack.pop() if stack else ident
            elif t == "cm":
                ctm = _mul(operands[-6:], ctm)
            elif t == "BT":
                tm = lm = ident
            elif t == "Tf":
                font = fonts.get(operands[-2], ({}, 1))
            elif t == "TL":
                leading = operands[-1]
            elif t in ("Td", "TD"):
                if t == "TD":
                    leading = -operands[-1]
                tm = lm = _mul([1, 0, 0, 1, operands[-2], operands[-1]], lm)
            elif t == "Tm":
                tm = lm = list(operands[-6:])
            elif t in ("T*", "'", '"'):
                tm = lm = _mul([1, 0, 0, 1, 0, -leading], lm)
                if t != "T*":
                    show(operands[-1])
            elif t == "Tj":
                show(operands[-1])
            elif t == "TJ":
                show(b"".join(x for x in operands[-1] if isinstance(x, bytes)))
            operands = []
        return out

    def cells(self, page_index: int) -> list[tuple[float, float, str]]:
        """Text runs joined into table cells: the report ends every cell with a whitespace-only run."""
        cells, cur = [], None
        for x, y, text in self.runs(page_index):
            if not text.strip() or (cur and abs(cur[1] - y) > 1.5):
                if cur and cur[2].strip():
                    cells.append((cur[0], cur[1], clean(cur[2])))
                cur = None
                if not text.strip():
                    continue
            cur = (cur[0], cur[1], cur[2] + text) if cur else (x, y, text)
        if cur and cur[2].strip():
            cells.append((cur[0], cur[1], clean(cur[2])))
        return cells
