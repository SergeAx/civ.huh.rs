"""citizens.json: per city, the citizen mix for the City View's person icons, from the censuses (units.py).

Rows: workforce (employed by occupation), age, faith, education (15+) and people (national community). Category
keys of the workforce row reuse the figure art's occupations; ISCO major groups map onto them as in GROUPS.
Figures use largest-remainder rounding, so each row's icons sum exactly to its count.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .lenses import FAITHS, PEOPLES
from .units import ETHNICITY, RELIGION, load_units

REQUIRES = ["rzs_census", "rzs_economy", "ask_kosovo", "cities.json"]
PRODUCES = ["citizens.json"]

FIGURES = {"workforce": 20, "age": 10, "faith": 10, "people": 10}
SPECIALIST_HIGH, SPECIALIST_LOW, MIN_SHARE, MAX_HIGH, MAX_LOW = 1.5, 0.67, 0.01, 4, 2

AGE = {"child": ["0-4", "5-9", "10-14"], "young": ["15-19", "20-24", "25-29"],
       "midlife": ["30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64"],
       "elder": ["65-69", "70-74", "75-79", "80-84", "85+"]}
WORK = {
    "executive": ("Managers", ["managers"]), "scholar": ("Professionals", ["professionals"]),
    "engineer": ("Technicians", ["technicians"]), "clerk": ("Clerks", ["clerks"]),
    "service": ("Service & sales", ["service_sales", "armed_forces"]), "farmer": ("Farmers", ["agriculture"]),
    "builder": ("Craft & trades", ["craft"]), "maker": ("Operators & labourers", ["operators", "elementary"]),
}
EDU = {"none": "No primary school", "primary": "Primary school", "secondary": "Secondary school", "tertiary": "College or university"}
GROUPS = {
    "workforce": [{"key": k, "label": lab, "icon": f"c-{k}", "lines": "ISCO-08 major groups " + ", ".join(src)} for k, (lab, src) in WORK.items()],
    "age": [{"key": k, "label": lab, "icon": f"c-{k}", "lines": ", ".join(AGE[k])} for k, lab in
            (("child", "Children (under 15)"), ("young", "Young (15–29)"), ("midlife", "Working age (30–64)"), ("elder", "Elders (65+)"))],
    "faith": [{"key": k, "label": RELIGION[k][0], "icon": f"c-{k}", "lines": k} for k in FAITHS + ["other", "none"]],
    "education": [{"key": k, "label": lab, "icon": f"c-{k}", "lines": k} for k, lab in EDU.items()],
    "people": [{"key": k, "label": ETHNICITY[k][0], "icon": f"c-{k}", "lines": k} for k in PEOPLES[:6] + ["other"]],
}
ROW_LABELS = {
    "workforce": "Employed residents by occupation (census; KiM: 2011 census)",
    "age": "Residents by age",
    "faith": "Residents by declared religion (undeclared left out)",
    "education": "Residents 15+ by highest finished school (unknown left out)",
    "people": "Residents by declared national community (undeclared left out)",
}


def largest_remainder(values: dict[str, float], n: int) -> dict[str, int]:
    """Integer counts summing exactly to n, proportional to `values` (Hamilton's method). Ties in the remainders go
    to the larger value, then to the earlier key. All-zero input → all zeros."""
    keys = list(values)
    vals = [max(0.0, float(values[k] or 0)) for k in keys]
    total = sum(vals)
    if total <= 0 or n <= 0:
        return {k: 0 for k in keys}
    quotas = [v * n / total for v in vals]
    base = [math.floor(q) for q in quotas]
    order = sorted(range(len(keys)), key=lambda i: (-(quotas[i] - base[i]), -vals[i], i))
    for i in order[: n - sum(base)]:
        base[i] += 1
    return dict(zip(keys, base))


def counts_of(name: str, members: list[dict]) -> dict[str, int] | None:
    out: dict[str, int] = {}
    for g in GROUPS[name]:
        k = g["key"]
        total = 0
        for m in members:
            if name == "workforce":
                src = m["occupation"]
                v = None if src is None else sum(src.get(s) or 0 for s in WORK[k][1])
            elif name == "age":
                v = None if m["age"] is None else sum(m["age"][a] for a in AGE[k])
            else:
                src = {"faith": m["religion"], "education": m["education"], "people": m["ethnicity"]}[name]
                if src is None:
                    v = None
                elif k == "other" and name == "faith":
                    v = src.get("other") or 0
                elif k == "other":
                    v = sum(n or 0 for key, n in src.items() if key not in PEOPLES[:6] and key != "undeclared")
                else:
                    v = src.get(k)
            if v is None:
                return None
            total += v
        out[k] = total
    return out


def row(name: str, members: list[dict]) -> dict | None:
    counts = counts_of(name, members)
    if counts is None or not sum(counts.values()):
        return None
    total = sum(counts.values())
    out = {"total": total, "counts": counts, "shares": {k: round(v / total, 3) for k, v in counts.items()}}
    if name in FIGURES:
        out["figures"] = largest_remainder(counts, FIGURES[name])
    if name == "education":
        out["bachelors_plus"] = out["shares"]["tertiary"]
    return out


def specialists(r: dict, nat: dict) -> list[dict]:
    hi, lo = [], []
    for name in GROUPS:
        a, b = r.get(name), nat.get(name)
        if not a or not b:
            continue
        for k, n in a["counts"].items():
            s, ns = n / a["total"], b["counts"][k] / b["total"]
            if not ns or (s < MIN_SHARE and ns < MIN_SHARE):
                continue
            item = {"row": name, "key": k, "share": round(s, 3), "national": round(ns, 3), "ratio": round(s / ns, 2)}
            if s / ns >= SPECIALIST_HIGH:
                hi.append(item)
            elif s / ns <= SPECIALIST_LOW:
                lo.append(item)
    hi.sort(key=lambda x: -x["ratio"])
    lo.sort(key=lambda x: x["ratio"])
    return hi[:MAX_HIGH] + lo[:MAX_LOW]


def build() -> None:
    units, _ = load_units(load_interim("rzs_census"), load_interim("rzs_economy"), load_interim("ask_kosovo"))
    cities = json.loads((WEB_DATA / "cities.json").read_text(encoding="utf-8"))
    everyone = list(units.values())
    national = {name: row(name, [u for u in everyone if counts_of(name, [u]) is not None]) for name in GROUPS}
    national["specialists"] = []
    out = {}
    for c in cities:
        members = [units[code] for code in c["counties"]]
        r = {name: row(name, members) for name in GROUPS}
        if all(v is None for v in r.values()):
            out[c["id"]] = None
            continue
        r["specialists"] = specialists(r, national)
        r["reliable"] = all(m["reliable"] for m in members)
        out[c["id"]] = r
    write_web("citizens.json", {
        "version": 1, "vintage": "Census 2022 · KiM: Census 2024 (occupations 2011)", "year": 2022,
        "sources": ["rzs_census", "ask_kosovo"], "figures": dict(FIGURES), "rows": ROW_LABELS, "groups": GROUPS,
        "rule": {"specialist_high": SPECIALIST_HIGH, "specialist_low": SPECIALIST_LOW, "min_share": MIN_SHARE,
                 "max_high": MAX_HIGH, "max_low": MAX_LOW,
                 "text": "A category is a specialty when its share is at least 1.5× (or at most 0.67×) the national "
                 "share; categories under 1% both here and nationally are skipped."},
        "national": national, "cities": out,
    })
    print(f"    {sum(v is not None for v in out.values())} of {len(cities)} cities with citizens")


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = web_dir / "citizens.json"
    if not path.exists():
        return [("NOTE", "citizens.json not built")]
    doc = json.loads(path.read_text(encoding="utf-8"))
    bad = []
    for cid, r in doc["cities"].items():
        for name, n in doc["figures"].items():
            rr = r and r.get(name)
            if rr and sum(rr["figures"].values()) != n:
                bad.append(f"{cid}: {name} figures sum to {sum(rr['figures'].values())}, not {n}")
    return [("FAIL", b) for b in bad[:5]] or [("PASS", f"citizens.json: {len(doc['cities'])} cities, figures sum right")]
