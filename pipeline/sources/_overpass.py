"""Overpass API queries for the OpenStreetMap sources: cached like any download, with mirror fallback.

Not a source itself (no Source subclass), so the registry ignores it.
"""

from __future__ import annotations

import http.client
import json
import urllib.parse
from pathlib import Path
from typing import Callable

ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
MAX_GET_URL = 2000  # longer queries are POSTed; a GET keeps the query in the manifest URL that the Almanac cites


def query(source, ql: str, rel_path: str, problem: Callable[[list[dict]], str | None], *, force: bool = False) -> Path:
    """Cache the answer to `ql` as data/raw/<source id>/<rel_path>, from the first mirror that answers in full.

    Overpass answers overload with 5xx and timeouts with a 200 'remark': such an answer, or one whose elements
    `problem` finds fault with (it returns what is wrong, or None), is discarded and the next mirror is tried.
    """
    last = None
    for endpoint in ENDPOINTS:
        url = f"{endpoint}?data={urllib.parse.quote(ql)}"
        post = len(url) > MAX_GET_URL
        body = urllib.parse.urlencode({"data": ql}).encode() if post else None
        try:
            path = source.download(endpoint if post else url, rel_path, force=force, data=body)
        except (OSError, http.client.HTTPException) as exc:
            last = exc
            print(f"      {endpoint} failed: {exc}")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        remark = doc.get("remark", "")
        wrong = remark if "error" in remark else problem(doc.get("elements", []))
        if not wrong:
            return path
        last = RuntimeError(f"{endpoint}: incomplete answer ({wrong})")
        print(f"      {last}")
        source.discard(rel_path)
        force = True
    raise RuntimeError(f"the Overpass query for {rel_path} failed on every mirror") from last
