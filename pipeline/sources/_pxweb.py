"""PxWeb helpers: whole-table downloads in PX format and a small reader for PX files.

Not a source itself (no Source subclass), so the registry ignores it.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from ..core import fetch

_WHOLE_TABLE_PX = json.dumps({"query": [], "response": {"format": "px"}}).encode()


def table_url(api_base: str, table_path: str) -> str:
    return api_base.rstrip("/") + "/" + "/".join(urllib.parse.quote(p) for p in table_path.split("/"))


def download_table(source, api_base: str, table_path: str, rel_path: str, *, force: bool = False) -> Path:
    """POST an empty PxWeb query (= every value of every variable; PxWeb serves data only to POST) and cache the
    answer as a PX file."""
    url = table_url(api_base, table_path)
    path = source.download(url, rel_path, force=force, headers={"Content-Type": "application/json"}, data=_WHOLE_TABLE_PX)
    if not path.read_bytes()[:16].lstrip(b"\xef\xbb\xbf").startswith(b"CHARSET="):
        source.discard(rel_path)
        raise fetch.UnexpectedContentError(f"{url}: not a PX file")
    return path


_KEY = re.compile(r'([A-Z0-9-]+)(?:\[([a-z]{2})\])?(?:\("((?:[^"]|"\s*,\s*")*)"\))?=')
_TOKEN = re.compile(r'"([^"]*)"|([^\s",;]+)|(,)')


def _strings(raw: str) -> list[str]:
    """Value list of a PX keyword. Quoted pieces without a comma between them are one string."""
    out: list[str] = []
    glue = False
    for quoted, bare, comma in _TOKEN.findall(raw):
        if comma:
            glue = False
            continue
        piece = quoted if quoted or not bare else bare
        if glue and out:
            out[-1] += piece
        else:
            out.append(piece)
        glue = bool(quoted)
    return out


class PxTable:
    """A PX file: keywords per language, the variables (stub then heading) and the data cube."""

    def __init__(self, path: Path):
        head, _, data = self._decode(path.read_bytes()).partition("\nDATA=")
        self.kw: dict[tuple[str, str, str], list[str]] = {}
        pos = 0
        while m := _KEY.search(head, pos):
            end = pos = self._value_end(head, m.end())
            self.kw[(m.group(1), m.group(2) or "", m.group(3) or "")] = _strings(head[m.end():end])
            pos = end + 1
        self.variables = self.get("STUB") + self.get("HEADING")
        self.values = {v: self.get("VALUES", v) for v in self.variables}
        self.data = [self._number(tok) for tok in _TOKEN.findall(data.rstrip().rstrip(";"))]
        self.data = [d for d in self.data if d is not _SKIP]
        expected = 1
        for v in self.variables:
            expected *= len(self.values[v])
        if len(self.data) != expected:
            raise ValueError(f"{path.name}: {len(self.data)} data cells, expected {expected}")

    @staticmethod
    def _decode(raw: bytes) -> str:
        """PxWeb re-encodes most tables to UTF-8, but old ones come back in their CODEPAGE (iso-8859-2)."""
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            m = re.search(rb'CODEPAGE="([^"]+)"', raw[:4000])
            codepage = m.group(1).decode("ascii") if m else "windows-1252"
            return raw.decode("windows-1252" if codepage.lower().replace("-", "") == "utf8" else codepage)

    @staticmethod
    def _value_end(head: str, i: int) -> int:
        quoted = False
        for j in range(i, len(head)):
            c = head[j]
            if c == '"':
                quoted = not quoted
            elif c == ";" and not quoted:
                return j
        return len(head)

    @staticmethod
    def _number(tok):
        quoted, bare, comma = tok
        if comma:
            return _SKIP
        s = quoted if quoted else bare
        if s == "-":
            return 0  # PX's DATASYMBOLNIL: a published nil, not a gap
        try:
            n = float(s)
        except ValueError:
            return None  # "..", ":" and the other PX data symbols mark figures that are not available
        return int(n) if n.is_integer() else n

    def get(self, key: str, sub: str = "", lang: str = "") -> list[str]:
        return self.kw.get((key, lang, sub), [])

    def text(self, key: str, lang: str = "en") -> str:
        """A text keyword in `lang` (falling back to the default language); '#' is PX's line break."""
        val = self.kw.get((key, lang, "")) or self.kw.get((key, "", ""), [])
        return " ".join(val).replace("#", "\n").strip()

    def labels(self, var: str, lang: str = "en") -> list[str]:
        """Value labels of `var` (named in the default language) in `lang`."""
        i = self.variables.index(var)
        names = self.get("STUB", lang=lang) + self.get("HEADING", lang=lang)
        return self.get("VALUES", names[i], lang) if names else self.values[var]


_SKIP = object()
