"""One record per map municipality, harmonised across the two statistical offices.

Outside Kosovo and Metohija the figures are RZS's (Census 2022, registered employment, wages, oblast GVA); inside
it they are the Kosovo Agency of Statistics' (Census 2024, Kosovo GVA), for its 38 municipalities. Both censuses
are mapped onto one set of categories here, so every builder downstream sees a single schema.
"""

from __future__ import annotations

from .okruzi import KIM_OKRUZI

AGE_GROUPS = [f"{a}-{a + 4}" for a in range(0, 85, 5)] + ["85+"]
UNRELIABLE_BELOW = 0.9  # ASK enumerated share under which its enumerated-only tables don't describe the municipality

EDUCATION = {
    "none": ("No schooling or unfinished primary", ["none", "primary_incomplete"], ["none", "primary"]),
    "primary": ("Primary school", ["primary"], ["lower_secondary"]),
    "secondary": ("Secondary school", ["gymnasium", "vocational_short", "vocational_4y", "specialization"], ["upper_secondary"]),
    "tertiary": ("College or university", ["higher_vocational", "university"], ["higher_school", "bachelor", "postgraduate", "doctorate"]),
    "unknown": ("Unknown", ["unknown"], ["unknown"]),
}
RELIGION = {
    "orthodox": ("Orthodox", ["orthodox"], ["orthodox"]),
    "catholic": ("Catholic", ["catholic"], ["catholic"]),
    "protestant": ("Protestant", ["protestant", "other_christian"], []),
    "islam": ("Islam", ["islam"], ["islam"]),
    "other": ("Other religions", ["judaism", "eastern", "other"], ["other"]),
    "none": ("No religion", ["agnostic", "atheist"], ["none"]),
    "undeclared": ("Undeclared or unknown", ["undeclared", "unknown"], ["not_declared"]),
}
ETHNICITY = {
    "serbs": ("Serbs", ["serbs"], ["serb"]),
    "albanians": ("Albanians", ["albanians"], ["albanian"]),
    "hungarians": ("Hungarians", ["hungarians"], []),
    "bosniaks": ("Bosniaks", ["bosniaks"], ["bosniak"]),
    "roma": ("Roma", ["roma"], ["roma"]),
    "slovaks": ("Slovaks", ["slovaks"], []),
    "croats": ("Croats", ["croats"], []),
    "montenegrins": ("Montenegrins", ["montenegrins"], []),
    "romanians": ("Romanians", ["romanians"], []),
    "vlachs": ("Vlachs", ["vlachs"], []),
    "bulgarians": ("Bulgarians", ["bulgarians"], []),
    "muslims": ("Muslims (ethnic)", ["muslims"], []),
    "gorani": ("Gorani", ["gorani"], ["gorani"]),
    "turks": ("Turks", ["turks"], ["turk"]),
    "ashkali_egyptians": ("Ashkali and Egyptians", [], ["ashkali", "egyptian"]),
    "yugoslavs": ("Yugoslavs", ["yugoslavs"], []),
    "other": ("Other", ["bunjevci", "germans", "macedonians", "russians", "rusyns", "slovenes", "ukrainians", "regional", "other"], ["other"]),
    "undeclared": ("Undeclared or unknown", ["undeclared", "unknown"], ["not_declared"]),
}
# ISCO-08 major groups (RZS 2022); ASK has only 2011, in ISCO-88 sub-major groups, mapped by their first digit.
OCCUPATION = {
    "managers": ("Managers", "1"), "professionals": ("Professionals", "2"), "technicians": ("Technicians", "3"),
    "clerks": ("Clerks", "4"), "service_sales": ("Service & sales workers", "5"), "agriculture": ("Farmers & foresters", "6"),
    "craft": ("Craft & trade workers", "7"), "operators": ("Machine operators", "8"), "elementary": ("Elementary occupations", "9"),
    "armed_forces": ("Armed forces", "0"),
}
SECTIONS = "ABCDEFGHIJKLMNOPQRSTU"
GVA_GROUPS = {"A": "A", "B-E": "BCDE", "F": "F", "G-I": "GHI", "J": "J", "K": "K", "L": "L", "M-N": "MN", "O-Q": "OPQ", "R-U": "RSTU"}


def plain_name(name: str) -> str:
    """RZS names a city with its status ("Град Нови Сад"); the map shows the name alone."""
    for prefix in ("Град ", "Grad "):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _harmonise(raw: dict | None, table: dict, part: int) -> dict | None:
    if not raw:
        return None
    out = {}
    for key, spec in table.items():
        srcs = spec[part]
        vals = [raw.get(s) for s in srcs]
        out[key] = None if srcs and any(v is None for v in vals) else sum(v for v in vals if v is not None)
    return None if all(v is None for v in out.values()) else out


def mean_age(groups: dict | None) -> float | None:
    """Mean age from 5-year groups (midpoints; 85+ counts as 90), the one measure both censuses allow."""
    if not groups or any(groups.get(g) is None for g in AGE_GROUPS):
        return None
    n = sum(groups[g] for g in AGE_GROUPS)
    mids = [a + 2.5 for a in range(0, 85, 5)] + [90.0]
    return round(sum(groups[g] * m for g, m in zip(AGE_GROUPS, mids)) / n, 1) if n else None


def _sections(raw: dict | None) -> dict | None:
    return {s: raw.get(s) for s in SECTIONS} if raw else None


def rsd_per_eur(econ: dict, year: int) -> float:
    acc = econ["nation"]["national_accounts"][str(year)]
    return acc["gdp_mio_rsd"] / acc["gdp_mio_eur"]


def serbia_units(census: dict, econ: dict) -> dict[str, dict]:
    eur_wage = rsd_per_eur(econ, int(econ["years"]["wages"]))
    undercount = set(census.get("caveats", {}).get("pop_2011_undercount", {}).get("units", []))
    out = {}
    for code, c in census["units"].items():
        if c.get("aggregate"):
            continue
        e = econ["units"].get(code, {})
        growth = None
        if c.get("pop_2011") and code not in undercount:
            growth = round(c["population"] / c["pop_2011"] - 1, 4)
        act = c.get("activity_15plus") or {}
        out[code] = {
            "code": code, "name_cyr": plain_name(c["name_cyr"]), "name_lat": plain_name(c["name_lat"]), "okrug_code": c["okrug_code"],
            "kim": False, "level": c["level"], "grad_code": c.get("grad_code"),
            "population": c["population"], "pop_year": 2022, "male": c.get("male"), "female": c.get("female"),
            "age": c.get("age", {}).get("total"), "mean_age": mean_age(c.get("age", {}).get("total")),
            "pop_2011": c.get("pop_2011"), "growth": growth, "growth_years": [2011, 2022],
            "education": _harmonise(c.get("education_15plus"), EDUCATION, 1),
            "religion": _harmonise(c.get("religion"), RELIGION, 1),
            "ethnicity": _harmonise(c.get("ethnicity"), ETHNICITY, 1),
            "occupation": {k: c["employed_by_occupation"].get(k) for k in OCCUPATION} if c.get("employed_by_occupation") else None,
            "occupation_year": 2022,
            "employed": act.get("employed"), "unemployed": act.get("unemployed"), "active": act.get("active"),
            "employed_by_section": _sections(c.get("employed_by_section")),
            "households": c.get("households"),
            "wage_net_eur": round(e["wage_net_rsd"] / eur_wage) if e.get("wage_net_rsd") else None,
            "wage_gross_eur": round(e["wage_gross_rsd"] / eur_wage) if e.get("wage_gross_rsd") else None,
            "jobs_workplace": (e.get("employment") or {}).get("total"),
            "jobs_workplace_by_section": e.get("employment_by_section"),
            "farmers": (e.get("employment") or {}).get("farmers"),
            "reliable": True,
        }
    return out


def _isco88_major(raw: dict | None) -> dict | None:
    if not raw or all(n is None for c, n in raw.items() if c != "total"):
        return None
    out = {k: 0 for k in OCCUPATION}
    digit = {d: k for k, (_, d) in OCCUPATION.items()}
    for code, n in raw.items():
        if code == "total" or n is None:
            continue
        out[digit.get(code[0], "elementary")] += n
    return out


def kim_units(ask: dict) -> dict[str, dict]:
    out = {}
    for code, m in ask["municipalities"].items():
        ok = (m.get("enumerated_share_2024") or 0) >= UNRELIABLE_BELOW
        act = m.get("activity_2024") or {}
        growth = round(m["pop_2024"] / m["pop_2011"] - 1, 4) if m.get("pop_2011") and m.get("pop_2024") else None
        out[code] = {
            "code": code, "name_cyr": m["name_sr_cyr"], "name_lat": m["name_sr_lat"], "name_sq": m["name_sq"],
            "okrug_code": m["okrug_code"], "kim": True, "level": "opstina", "grad_code": None,
            "population": m["pop_2024"], "pop_year": 2024, "male": m.get("pop_2024_male"), "female": m.get("pop_2024_female"),
            "age": m.get("age_2024"), "mean_age": mean_age(m.get("age_2024")),
            "pop_2011": m.get("pop_2011"), "growth": growth, "growth_years": [2011, 2024],
            "education": _harmonise(m.get("education_2024"), EDUCATION, 2) if ok else None,
            "religion": _harmonise(m.get("religion_2024"), RELIGION, 2) if ok else None,
            "ethnicity": _harmonise(m.get("ethnicity_2024"), ETHNICITY, 2),
            "occupation": _isco88_major(m.get("occupation_2011")), "occupation_year": 2011,
            "employed": act.get("employed") if ok else None, "unemployed": act.get("unemployed") if ok else None,
            "active": act.get("active") if ok else None,
            "employed_by_section": _sections(m.get("employed_by_section_2024")) if ok else None,
            "households": m.get("households_2024") if ok else None,
            "wage_net_eur": None, "wage_gross_eur": None, "jobs_workplace": None, "jobs_workplace_by_section": None,
            "farmers": None,
            "reliable": ok,
        }
    return out


def _allocate(total: float, weights: dict[str, float]) -> dict[str, float]:
    tw = sum(weights.values())
    return {k: total * w / tw for k, w in weights.items()} if tw > 0 else {k: 0.0 for k in weights}


def add_gva(units: dict[str, dict], econ: dict, ask: dict) -> dict:
    """GDP (EUR) per municipality, the way statistical offices estimate regional GDP: gross value added, published
    per okrug (RZS) and for KiM as a whole (ASK), scaled by the national ratio of GDP to GVA (taxes less subsidies on
    products). Each area's figure by activity group is shared out by the municipalities' employees in that group:
    registered employment by workplace (plus registered farmers for agriculture) in Serbia, census employed by
    residence in KiM; municipalities without usable employment figures (KiM's north) get the area's employees per
    resident times their population. Returns {"year", "rsd_per_eur", "okruzi": {code: eur}, "kim": eur}."""
    year = int(econ["years"]["gva_oblast"])
    rate = rsd_per_eur(econ, year)
    gdp_rsd = econ["nation"]["national_accounts"][str(year)]["gdp_mio_rsd"]
    rate /= gdp_rsd / sum(o["gva_mio_rsd"] for o in econ["okruzi"].values())
    for u in units.values():
        u["gdp"], u["gdp_by_industry"] = None, None
    by_okrug: dict[str, list[dict]] = {}
    for u in units.values():
        if not u["kim"]:
            by_okrug.setdefault(u["okrug_code"], []).append(u)
    okrug_gva = {}
    for okr, members in by_okrug.items():
        groups = econ["okruzi"][okr].get("gva_by_activity_mio_rsd") or {}
        for g, sections in GVA_GROUPS.items():
            weights = {}
            for u in members:
                by = u.get("jobs_workplace_by_section") or {}
                w = sum(by.get(s) or 0 for s in sections) + ((u.get("farmers") or 0) if g == "A" else 0)
                weights[u["code"]] = w
            for code, v in _allocate((groups.get(g) or 0) * 1e6 / rate, weights).items():
                u = units[code]
                u["gdp_by_industry"] = u["gdp_by_industry"] or {}
                u["gdp_by_industry"][g] = round(v)
        okrug_gva[okr] = round(econ["okruzi"][okr]["gva_mio_rsd"] * 1e6 / rate)

    kim = [u for u in units.values() if u["kim"]]
    kim_gdp = ask["kim"]["economy"]["gdp"]
    to_gdp = kim_gdp["gdp_keur"] / kim_gdp["gva_basic_keur"]
    gva = {s: (v or 0) * to_gdp for s, v in kim_gdp["gva_by_section_keur"].items()}
    reliable = [u for u in kim if u["employed_by_section"]]
    pop_ok = sum(u["population"] for u in reliable)
    for g, sections in GVA_GROUPS.items():
        total = sum((gva.get(s) or 0) for s in sections) * 1e3
        emp_ok = sum(sum(u["employed_by_section"].get(s) or 0 for s in sections) for u in reliable)
        weights = {}
        for u in kim:
            if u["employed_by_section"]:
                weights[u["code"]] = sum(u["employed_by_section"].get(s) or 0 for s in sections)
            else:
                weights[u["code"]] = u["population"] * emp_ok / pop_ok
        for code, v in _allocate(total, weights).items():
            u = units[code]
            u["gdp_by_industry"] = u["gdp_by_industry"] or {}
            u["gdp_by_industry"][g] = round(v)
    for u in units.values():
        if u["gdp_by_industry"]:
            u["gdp"] = sum(u["gdp_by_industry"].values())
    return {
        "year": year, "rsd_per_eur": round(rsd_per_eur(econ, year), 2), "okruzi": okrug_gva,
        "kim": round(kim_gdp["gdp_keur"] * 1e3), "kim_year": kim_gdp["year"],
    }


def _total(vals):
    return None if not vals or any(v is None for v in vals) else sum(vals)


def economy(members: list[dict], partial: bool = False) -> dict:
    """The economic shape of a city, okrug or the nation (docs/DATA_CONTRACTS.md cities.json) from its municipalities.
    Counts are None when any member lacks them, unless `partial`: then they add up the members that have them, and
    `partial` lists the codes left out (KiM's north, for an okrug or the nation). The wage is the employee-weighted
    mean of the members that have one (wages, like the census, are counted where people live)."""
    from .yields import INDUSTRIES, yields_of

    everyone = members
    missing = sorted(m["code"] for m in members if not m["reliable"]) if partial else []
    if missing:
        members = [m for m in members if m["reliable"]]
    sections = [m["employed_by_section"] for m in members]
    jobs = {}
    for key, (secs, _) in INDUSTRIES.items():
        jobs[key] = None if any(s is None for s in sections) else sum(sum(s.get(c) or 0 for c in secs) for s in sections)
    gdp = _total([m["gdp"] for m in everyone])
    by_ind = None
    if gdp is not None:
        by_ind = {g: sum(m["gdp_by_industry"][g] for m in everyone) for g in GVA_GROUPS}
    waged = [(m["wage_net_eur"], m["employed"] or 0) for m in members if m["wage_net_eur"]]
    wage = round(sum(w * n for w, n in waged) / sum(n for _, n in waged)) if waged and sum(n for _, n in waged) else None
    active, unemployed = _total([m["active"] for m in members]), _total([m["unemployed"] for m in members])
    return {
        "partial": missing or None,
        "population": sum(m["population"] for m in members),
        "employed": _total([m["employed"] for m in members]),
        "yields": yields_of(jobs, gdp),
        "jobs": jobs,
        "median_income": wage,
        "median_rent": None,
        "home_value": None,
        "unemployment": round(unemployed / active, 4) if active and unemployed is not None else None,
        "rent_burden": None,
        "gdp": gdp,
        "gdp_by_industry": by_ind,
        "gdp_undisclosed": None,
        "gdp_estimated": sorted(GVA_GROUPS) if gdp is not None else None,
    }


def growth_of(members: list[dict]) -> tuple[float | None, list[int] | None]:
    if any(m["growth"] is None for m in members) or len({tuple(m["growth_years"]) for m in members}) != 1:
        return None, None
    before = sum(m["pop_2011"] for m in members)
    return round(sum(m["population"] for m in members) / before - 1, 4), members[0]["growth_years"]


def stat_codes(census: dict, ask: dict) -> set[str]:
    """Codes of the finest municipalities either office reports (aggregates such as Grad Niš left out)."""
    return {c for c, u in census["units"].items() if not u.get("aggregate")} | set(ask["municipalities"])


def map_units(bounds: dict, stat_codes) -> list[dict]:
    """The boundary units keyed like the statistics, sorted by code. A polygon the statistics don't report on its own
    (Novi Sad's two gradske opštine: RZS publishes only Grad Novi Sad) joins its grad; the grad's seat is the member
    named like it."""
    stat_codes = set(stat_codes)
    grad_name = {g["code"]: g.get("name_lat") for g in bounds.get("gradovi", [])}
    out: dict[str, dict] = {}
    for b in sorted(bounds["units"], key=lambda u: u["code"]):
        code = b["code"] if b["code"] in stat_codes else b.get("grad_code")
        if code not in stat_codes:
            raise KeyError(f"boundary unit {b['code']} ({b['name_lat']}) has no statistics, nor has its grad")
        if code == b["code"]:
            out[code] = b
            continue
        merged = out.setdefault(code, {**b, "code": code, "kind": "grad", "grad_code": None, "rings": [], "area_km2": 0.0})
        merged["rings"] = merged["rings"] + b["rings"]
        merged["area_km2"] += b["area_km2"]
        if b["name_lat"] == grad_name.get(code) or (grad_name.get(code) or "").endswith(b["name_lat"]):
            merged["seat"], merged["name_cyr"], merged["name_lat"] = b["seat"], b["name_cyr"], b["name_lat"]
    return sorted(out.values(), key=lambda u: u["code"])


def load_units(census: dict, econ: dict, ask: dict) -> tuple[dict[str, dict], dict]:
    """All map municipalities by code (RZS codes, then KM01…KM38), and the GVA summary of add_gva()."""
    units = serbia_units(census, econ) | kim_units(ask)
    assert {u["okrug_code"] for u in units.values() if u["kim"]} <= KIM_OKRUZI
    gva = add_gva(units, econ, ask)
    return units, gva
