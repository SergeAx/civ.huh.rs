"""Census of Population, Households and Dwellings 2022 (Popis 2022), RZS open data, per municipality.

Reference moment: 30 September 2022, 24:00. Every table comes from RZS's open-data service (see _rzs.py) at
the finest level RZS publishes: municipalities, cities and the gradske opštine of Beograd, Niš, Požarevac,
Vranje and Užice (Novi Sad's two gradske opštine are only published together, as Grad Novi Sad). Kosovo and
Metohija is not covered: RZS has had no data there since 1999.

Interim shape (data/interim/rzs_census.json, "data"):

* ``units``: {5-digit RZS municipality code: unit}. Descriptive fields: ``name_cyr``/``name_lat`` (RZS
  spelling), ``level`` ("opstina", "grad", "gradska_opstina"), ``grad_code`` (the city of a gradska
  opština, else null), ``aggregate`` (true for Grad Niš, Požarevac, Vranje and Užice, whose gradske opštine
  are units too: sum only non-aggregate units), ``okrug_code`` ("00" Grad Beograd … "24", Uredba o upravnim
  okruzima), ``oblast_code`` (RZS NSTJ code of the same okrug, e.g. "RS211"), ``okrug_name_cyr/lat`` (RZS
  oblast name), ``region_code`` ("RS11", "RS12", "RS21", "RS22") and ``region_name_cyr/lat``. Grad Beograd
  (79014) is not a unit: RZS reports it as Beogradska oblast, okruzi["00"].
* ``okruzi`` {okrug code}, ``regions`` {NSTJ code} and ``nation``: the same statistics as RZS publishes them
  for its oblasti, regions and the Republic (okruzi also carry ``nstj_code`` and region fields).

Statistics (counts are ints, persons unless noted; null = not published):
``population``, ``male``, ``female``, ``pop_18plus``; ``age`` {"total"|"male"|"female": {"0-4" … "85+"}};
``avg_age``, ``avg_age_male``, ``avg_age_female`` (years; RZS publishes no median); ``pop_census``
{"1948" … "2022"} population at each census on today's borders; ``pop_2011`` and
``pop_change_2011_2022_pct``; ``ethnicity``; ``religion``; ``education_15plus`` (highest school completed,
persons 15+); ``activity`` (economic activity, all ages) and ``activity_15plus`` (same minus the under-15
age group); ``employed_by_section`` (employed residents by NACE Rev. 2 section of their job, A–U plus
"unknown"); ``employed_by_occupation`` (ISCO-08 major groups); ``households``, ``households_by_size``
{"1" … "6+"}, ``avg_household_size``; ``dwellings`` (housing units by type). ``categories`` lists every key
of these breakdowns with RZS's code and label (Cyrillic, plus Latin transliteration) in RZS order.

RZS marks an empty cell "-" (status M, "data cannot exist"): it is stored as 0, as is a category with no row
at all; both were checked to make the categories add up to the published totals. Subtotals inside a
breakdown are flagged by a "note" in ``categories``.
"""

from __future__ import annotations

from ._rzs import GRAD_PARTS, OKRUG, RzsSource, as_int, categorize, category_list, pivot
from ..core.source import SourceInfo

T_AGE = "3104020201IND01"
T_AVG_AGE = "3104020202IND01"
T_ETHNICITY = "3104020101IND01"
T_RELIGION = "3104020301IND01"
T_EDUCATION = "3104020401IND01"
T_ACTIVITY = "3104020801IND01"
T_SECTION = "3104020802IND01"
T_OCCUPATION = "3104020803IND01"
T_HOUSEHOLDS = "3104030101IND01"
T_HH_SIZE = "3104030102IND01"
T_DWELLINGS = "3104040101IND01"
T_SERIES = "31010101IND01"

AGE = {c: c.replace("00-4", "0-4").replace("05-9", "5-9") for c in
       ("00-4", "05-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59",
        "60-64", "65-69", "70-74", "75-79", "80-84")} | {"85": "85+"}
ETHNICITY = {
    "1010": "serbs", "1200": "hungarians", "1060": "bosniaks", "1260": "roma", "1020": "albanians",
    "1300": "slovaks", "1360": "croats", "1380": "montenegrins", "1270": "romanians", "1090": "vlachs",
    "1070": "bulgarians", "1180": "yugoslavs", "1290": "rusyns", "1220": "muslims", "1080": "bunjevci",
    "1210": "macedonians", "1100": "gorani", "1230": "germans", "1280": "russians", "1310": "slovenes",
    "1330": "ukrainians", "1900": "other", "3000": "regional", "4000": "undeclared", "8990": "unknown",
}
RELIGION = {
    "02": "christian", "03": "orthodox", "04": "catholic", "05": "protestant", "06": "other_christian",
    "07": "islam", "08": "judaism", "09": "eastern", "10": "other", "11": "agnostic", "12": "atheist",
    "13": "undeclared", "14": "unknown",
}
EDUCATION = {
    "1": "none", "2": "primary_incomplete", "3": "primary", "4": "secondary", "5": "gymnasium",
    "6": "vocational_short", "7": "vocational_4y", "8": "specialization", "9": "higher_vocational",
    "10": "university", "11": "unknown",
}
ACTIVITY = {
    "100": "active", "105": "employed", "110": "unemployed", "115": "inactive", "120": "children_under_15",
    "125": "pupils_students", "130": "pensioners", "135": "property_income", "140": "own_household_production",
    "145": "housework", "150": "other_inactive",
}
SECTIONS = {c: c for c in "ABCDEFGHIJKLMNOPQRSTU"} | {"Y": "unknown"}
OCCUPATION = {
    "1": "managers", "2": "professionals", "3": "technicians", "4": "clerks", "5": "service_sales",
    "6": "agriculture", "7": "craft", "8": "operators", "9": "elementary", "0": "armed_forces", "N": "unknown",
}
HH_SIZE = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6+"}
DWELLINGS = {
    "0": "dwellings", "10": "occupied", "20": "temporarily_vacant", "30": "abandoned", "55": "seasonal",
    "60": "business_only", "70": "occupied_business_premises", "80": "emergency_premises", "90": "collective",
}
NOTES = {
    "ethnicity": {"other": "all other declared ethnicities (detail is published for the Republic only)"},
    "religion": {"christian": "subtotal of orthodox, catholic, protestant and other_christian"},
    "education": {
        "secondary": "subtotal of gymnasium, vocational_short, vocational_4y and specialization",
        "higher_vocational": "više obrazovanje (short-cycle tertiary)",
        "university": "visoko obrazovanje (bachelor and above)",
    },
    "activity": {"active": "subtotal: employed + unemployed",
                 "inactive": "subtotal of the six inactive groups below"},
    "dwellings": {
        "dwellings": "all dwellings (stanovi): sum of occupied … business_only",
        "occupied_business_premises": "housing unit that is not a dwelling: not in the dwellings total",
        "emergency_premises": "housing unit that is not a dwelling: not in the dwellings total",
        "collective": "collective living quarters: not in the dwellings total",
    },
}
ALL_SETTLEMENTS = {"IDTipNaselja": "0"}
BOTH_SEXES = {"IDPol": "0"}
UNDERCOUNT_2011 = ("70351", "70963")  # Bujanovac, Preševo


def _sum_parts(values: dict[str, dict], parts: list[str]) -> dict[str, float | None]:
    """Category-wise sum over `parts` (None where any part lacks the category)."""
    rows = [values[p] for p in parts if p in values]
    keys = set().union(*rows) if rows else set()
    return {k: None if any(r.get(k) is None for r in rows) else sum(r[k] for r in rows) for k in keys}


class RzsCensus(RzsSource):
    info = SourceInfo(
        id="rzs_census",
        title="Census of Population, Households and Dwellings 2022",
        publisher="Statistical Office of the Republic of Serbia (RZS)",
        homepage="https://popis2022.stat.gov.rs/",
        license="Open data; free reuse with attribution of the source (RZS terms of use)",
        description="Census 2022 results for every municipality, city and city municipality outside Kosovo "
        "and Metohija, plus the oblasti (okruzi), regions and the Republic: population by sex and five-year age "
        "group, average age, ethnicity, religion, education, economic activity, employed residents by industry "
        "and occupation, households and dwellings, and population at every census since 1948 on today's "
        "borders. Read from RZS's open-data service.",
        used_for=["Municipality population, people and housing"],
    )
    tables = {T_AGE: "zip", T_AVG_AGE: "csv", T_ETHNICITY: "csv", T_RELIGION: "csv", T_EDUCATION: "csv",
              T_ACTIVITY: "csv", T_SECTION: "csv", T_OCCUPATION: "csv", T_HOUSEHOLDS: "csv", T_HH_SIZE: "csv",
              T_DWELLINGS: "csv", T_SERIES: "csv"}

    def process(self) -> dict:
        terr = self.territory()
        codes = terr.codes
        year = "2022"
        stats: dict[str, dict] = {}
        labels: dict[str, dict] = {}

        def put(code: str, **fields) -> None:
            stats.setdefault(code, {}).update(fields)

        age, _ = pivot(self.path(T_AGE), codes, ("IDPol", "IDStarGrupa"), ALL_SETTLEMENTS, year)
        for code, v in age.items():
            sexes = {s: {key: as_int(v.get((sex, c))) for c, key in AGE.items()}
                     for sex, s in (("0", "total"), ("1", "male"), ("2", "female"))}
            put(code, population=as_int(v.get(("0", "0"))), male=as_int(v.get(("1", "0"))),
                female=as_int(v.get(("2", "0"))), pop_18plus=as_int(v.get(("0", "P18"))), age=sexes)

        avg, _ = pivot(self.path(T_AVG_AGE), codes, "IDPol", year=year, m_as_zero=False)
        for code, v in avg.items():
            put(code, avg_age=v.get("0"), avg_age_male=v.get("1"), avg_age_female=v.get("2"))

        series, _ = pivot(self.path(T_SERIES), codes, "god")
        for oblast in OKRUG:
            if oblast not in series:
                series[oblast] = _sum_parts(series, [c for c, m in terr.municipalities.items()
                                                     if m["oblast"] == oblast and c not in GRAD_PARTS])
        for code, v in series.items():
            hist = {y: as_int(n) for y, n in sorted(v.items())}
            p11, p22 = hist.get("2011"), hist.get("2022")
            change = round((p22 / p11 - 1) * 100, 2) if p11 and p22 is not None else None
            put(code, pop_census=hist, pop_2011=p11,
                pop_change_2011_2022_pct=None if code in UNDERCOUNT_2011 else change)

        def breakdown(field: str, table: str, dim: str, cats: dict, total: str | None, fixed: dict) -> None:
            vals, labels[field] = pivot(self.path(table), codes, dim, fixed, year)
            for code, v in vals.items():
                put(code, **{field: categorize(v, cats, total)})

        breakdown("ethnicity", T_ETHNICITY, "IDNacionalnostPS", ETHNICITY, "0",
                  {"IDTipNaseljaMICS": "0", **BOTH_SEXES})
        breakdown("religion", T_RELIGION, "IDVeroispovest", RELIGION, "01", BOTH_SEXES)
        breakdown("education_15plus", T_EDUCATION, "IDSkSpr", EDUCATION, "0", {**ALL_SETTLEMENTS, **BOTH_SEXES})
        breakdown("activity", T_ACTIVITY, "IDEkonomskaAkt", ACTIVITY, "0", {"IDStarGrupa": "0", **BOTH_SEXES})
        breakdown("employed_by_section", T_SECTION, "IDKD08", SECTIONS, "0", BOTH_SEXES)
        breakdown("employed_by_occupation", T_OCCUPATION, "IDZanimanje", OCCUPATION, "", BOTH_SEXES)
        breakdown("households_by_size", T_HOUSEHOLDS, "IDBrClDom", HH_SIZE, "0", ALL_SETTLEMENTS)
        breakdown("dwellings", T_DWELLINGS, "IDVrstaStambeneJedinice", DWELLINGS, "0", ALL_SETTLEMENTS)

        under15, _ = pivot(self.path(T_ACTIVITY), codes, "IDEkonomskaAkt", {"IDStarGrupa": "0-15", **BOTH_SEXES}, year)
        for code, s in stats.items():
            total, young = s.get("activity"), categorize(under15.get(code), ACTIVITY, "0")
            if total and young:
                s["activity_15plus"] = {k: None if total[k] is None or young[k] is None else total[k] - young[k]
                                        for k in total}

        hh, _ = pivot(self.path(T_HOUSEHOLDS), codes, "IDBrClDom", ALL_SETTLEMENTS, year)
        for code, v in hh.items():
            put(code, households=as_int(v.get("0")))
        size, _ = pivot(self.path(T_HH_SIZE), codes, "IDTipNaselja", year=year, m_as_zero=False)
        for code, v in size.items():
            put(code, avg_household_size=None if v.get("0") is None else round(v["0"], 2))

        out = terr.assemble(stats)
        cats = {
            "age": [{"key": k, "rzs_code": c} for c, k in AGE.items()],
            "ethnicity": category_list(ETHNICITY, labels["ethnicity"], NOTES["ethnicity"]),
            "religion": category_list(RELIGION, labels["religion"], NOTES["religion"]),
            "education_15plus": category_list(EDUCATION, labels["education_15plus"], NOTES["education"]),
            "activity": category_list(ACTIVITY, labels["activity"], NOTES["activity"]),
            "employed_by_section": category_list(SECTIONS, labels["employed_by_section"]),
            "employed_by_occupation": category_list(OCCUPATION, labels["employed_by_occupation"]),
            "households_by_size": category_list(HH_SIZE, labels["households_by_size"]),
            "dwellings": category_list(DWELLINGS, labels["dwellings"], NOTES["dwellings"]),
        }
        return {
            "vintage": "Census 2022",
            "reference_date": "2022-09-30",
            **out,
            "categories": cats,
            "caveats": {
                "pop_2011_undercount": {
                    "units": list(UNDERCOUNT_2011),
                    "note": "Most ethnic Albanians boycotted the 2011 census in Bujanovac and Preševo, so their 2011 "
                    "count (and that of Pčinjska oblast, the region and the Republic) is far too low; "
                    "pop_change_2011_2022_pct is null for these two units.",
                },
                "unknown_characteristics": "The 'unknown' ethnicity and religion counts are large (about 5% of "
                "the population): they include the persons whose census record was taken from administrative "
                "registers, which carry no such data.",
                "beogradska_oblast_series": "RZS's census series has no row for Beogradska oblast: okruzi['00']"
                ".pop_census is the sum of its 17 gradske opštine.",
            },
            "tables": {
                "age": T_AGE, "avg_age": T_AVG_AGE, "pop_census": T_SERIES, "ethnicity": T_ETHNICITY,
                "religion": T_RELIGION, "education_15plus": T_EDUCATION, "activity": T_ACTIVITY,
                "employed_by_section": T_SECTION, "employed_by_occupation": T_OCCUPATION,
                "households": T_HOUSEHOLDS, "avg_household_size": T_HH_SIZE, "dwellings": T_DWELLINGS,
            },
            "_files": self.files(),
        }
