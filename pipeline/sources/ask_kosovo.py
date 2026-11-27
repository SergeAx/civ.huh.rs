"""Kosovo and Metohija by municipality, from the Kosovo Agency of Statistics (ASK) PxWeb database.

The Statistical Office of the Republic of Serbia has published nothing on Kosovo and Metohija since
1999, so this source takes ASK's figures for its 38 municipalities and files each under the Serbian
name and okrug it has in the Serbian administrative division (okruzi 25-29).

Each table is downloaded whole, as a PX file, so ASK's own notes travel with the numbers.
"""

from __future__ import annotations

import itertools
import re
import time
import unicodedata

from ..core.source import Source, SourceInfo
from ._pxweb import PxTable, download_table, table_url

API = "https://askdata.rks-gov.net/api/v1/en/ASKdata"
_CENSUS = "Census population"
_HOUSING = f"{_CENSUS}/5_Ndërtesat, banesat dhe ekonomitë familjare"
_ACCOUNTS = "National and government accounts/National accounts/Annual national accounts"

# path in data/raw/ask_kosovo/ -> table path in the ASK database
TABLES = {
    "census/census2024_00.px": f"{_CENSUS}/1_Demographic_Characteristics/census2024_00.px",
    "census/tab04census.px": f"{_CENSUS}/1_Demographic_Characteristics/tab04census.px",
    "census/census2024_63.px": f"{_CENSUS}/1_Demographic_Characteristics/census2024_63.px",
    "census/census2024_10.px": f"{_CENSUS}/1_Demographic_Characteristics/census2024_10.px",
    "census/tabcensusedu3.px": f"{_CENSUS}/2_Education/tabcensusedu3.px",
    "census/lc02ensus.px": f"{_CENSUS}/4_Labour market/lc02ensus.px",
    "census/lc03ensus.px": f"{_CENSUS}/4_Labour market/lc03ensus.px",
    "census/lc13ensus.px": f"{_CENSUS}/4_Labour market/lc13ensus.px",
    "census/tab_5.11.px": f"{_CENSUS}/4_Labour market/tab_5.11.px",
    "census/census2024_51.px": f"{_HOUSING}/census2024_51.px",
    "census/census2024_52.px": f"{_HOUSING}/census2024_52.px",
    "census/tab02ncensus.px": f"{_HOUSING}/tab02ncensus.px",
    "estimates/tab001.px": "Population/Estimate, projection and structure of population/Population estimate/tab001.px",
    "business_register/enterprises03.px": "Statistical business register/Quarterly indicators/enterprises03.px",
    "national_accounts/gdp09.px": f"{_ACCOUNTS}/gdp09.px",
    "national_accounts/gdp13.px": f"{_ACCOUNTS}/gdp13.px",
    "wages/tab01.px": "Labour market/Niveli i Pagave/tab01.px",
    "wages/tab03.px": "Labour market/Niveli i Pagave/tab03.px",
}

OKRUZI = {
    "25": ("Косовски", "Kosovski"),
    "26": ("Пећки", "Pećki"),
    "27": ("Призренски", "Prizrenski"),
    "28": ("Косовскомитровачки", "Kosovskomitrovački"),
    "29": ("Косовскопоморавски", "Kosovskopomoravski"),
}

# ASK's municipality number (the row order of every ASK table; its settlement tables are filed
# under "1 …" to "38 …"), the Serbian name, the okrug, and the spellings ASK tables use (folded).
MUNICIPALITIES = [
    (1, "Дечани", "Dečani", "26", ["decan"]),
    (2, "Ђаковица", "Đakovica", "26", ["gjakove"]),
    (3, "Глоговац", "Glogovac", "25", ["gllogovc", "gllogoc"]),
    (4, "Гњилане", "Gnjilane", "29", ["gjilan"]),
    (5, "Драгаш", "Dragaš", "27", ["dragash"]),
    (6, "Исток", "Istok", "26", ["istog"]),
    (7, "Качаник", "Kačanik", "25", ["kacanik"]),
    (8, "Клина", "Klina", "26", ["kline", "klin"]),
    (9, "Косово Поље", "Kosovo Polje", "25", ["fushekosove", "fushekosovo", "fkosove"]),
    (10, "Косовска Каменица", "Kosovska Kamenica", "29", ["kamenice"]),
    (11, "Косовска Митровица", "Kosovska Mitrovica", "28", ["mitrovice"]),
    (12, "Лепосавић", "Leposavić", "28", ["leposaviq"]),
    (13, "Липљан", "Lipljan", "25", ["lipjan"]),
    (14, "Ново Брдо", "Novo Brdo", "29", ["novoberde"]),
    (15, "Обилић", "Obilić", "25", ["obiliq"]),
    (16, "Ораховац", "Orahovac", "27", ["rahovec"]),
    (17, "Пећ", "Peć", "26", ["peje"]),
    (18, "Подујево", "Podujevo", "25", ["podujeve"]),
    (19, "Приштина", "Priština", "25", ["prishtine", "pristina"]),
    (20, "Призрен", "Prizren", "27", ["prizren"]),
    (21, "Србица", "Srbica", "28", ["skenderaj", "sknderaj"]),
    (22, "Штимље", "Štimlje", "25", ["shtime"]),
    (23, "Штрпце", "Štrpce", "25", ["shterpce"]),
    (24, "Сува Река", "Suva Reka", "27", ["suhareke"]),
    (25, "Урошевац", "Uroševac", "25", ["ferizaj"]),
    (26, "Витина", "Vitina", "29", ["viti"]),
    (27, "Вучитрн", "Vučitrn", "28", ["vushtrri"]),
    (28, "Зубин Поток", "Zubin Potok", "28", ["zubinpotok"]),
    (29, "Звечан", "Zvečan", "28", ["zveqan", "zvecan"]),
    (30, "Малишево", "Mališevo", "27", ["malisheve"]),
    (31, "Јуник", "Junik", "26", ["junik", "juniku"]),
    (32, "Мамуша", "Mamuša", "27", ["mamushe"]),
    (33, "Елез Хан", "Elez Han", "25", ["haniielezit"]),
    (34, "Грачаница", "Gračanica", "25", ["gracanice", "gracanica"]),
    (35, "Ранилуг", "Ranilug", "29", ["ranillug", "ranilug"]),
    (36, "Партеш", "Parteš", "29", ["partesh"]),
    (37, "Клокот", "Klokot", "29", ["kllokot"]),
    (38, "Северна Косовска Митровица", "Severna Kosovska Mitrovica", "28",
     ["mitrovicaveriore", "mitroviceeveriut", "mitrovicaeveriut", "mitrveriore", "mitrovicaev"]),
]
CODES = [m[0] for m in MUNICIPALITIES]
NORTH = {12, 28, 29, 38}
KIM = "KIM"


def fold(label: str) -> str:
    plain = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.lower())


AREA = {alias: m[0] for m in MUNICIPALITIES for alias in m[4]} | dict.fromkeys(
    ("kosova", "kosove", "total", "gjithsej"), KIM
)


def area_key(code: int) -> str:
    return f"KM{code:02d}"


AGE_GROUPS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49",
              "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84", "85+"]
SEXES = {"Total": "", "Male": "_male", "Female": "_female"}
ETHNICITY = {
    "Total": "total", "Albanian": "albanian", "Serb": "serb", "Bosniak": "bosniak", "Turk": "turk",
    "Romani": "roma", "Ashkali": "ashkali", "Egyptian": "egyptian", "Gorani": "gorani", "Others": "other",
    "Prefers not to answer": "not_declared",
}
RELIGION = {
    "Total": "total", "Islam": "islam", "Orthodox": "orthodox", "Catholic": "catholic", "Others": "other",
    "No religious affiliation": "none", "Prefers not to answer": "not_declared",
}
EDUCATION = {
    "Total": "total", "No completed level": "none", "Elementary school": "primary",
    "Lower secondary school": "lower_secondary", "Upper secondary school": "upper_secondary",
    "Higher school": "higher_school", "College, Bachelor's degree": "bachelor",
    "Postgraduate degree": "postgraduate", "Doctorate degree": "doctorate", "Unknown": "unknown",
}
LABOUR_FORCE = {"Total": "pop_15_64", "Economically active": "active", "(Labor Force)Inactive": "inactive"}
EMPLOYMENT = {"Economically active (Labor Force)": "active_lc03", "Employed": "employed", "Unemployed": "unemployed"}
OCCUPATION_2011 = {  # ASK's labels are the ISCO-88 sub-major groups, plus a residual "9_nec"
    "Total": "total", "Legislators": "11", "Corporate managers": "12", "Small organisation managers": "13",
    "Physical, mathematical and engineering science professionals": "21",
    "Life science and health professionals": "22", "Teaching professionals": "23", "Other professionals": "24",
    "Technical associate professionals": "31", "Life science and health associate professionals": "32",
    "Teaching associate professionals": "33",
    "Public administration and commercial work associate professionals": "34", "Office clerks": "41",
    "Customer services clerks": "42", "Personal and protective services workers": "51",
    "Models, salespersons and demonstrators": "52", "Skilled agricultural and fishery workers": "61",
    "Miners and building trades workers": "71", "Metal, machinery and related trade workers": "72",
    "Precision, handicraft, printing and related trade workers": "73",
    "Other craft and related trades workers": "74", "Stationary-plant and related operators": "81",
    "Products machine operators and assemblers": "82", "Drivers and mobile-plant operators": "83",
    "Sales and services elementary occupations": "91", "Agricultural, fishery and related labourers": "92",
    "Elementary occupations in mining, construction, manufacturing and transport": "93",
    "Elementary occupations not elsewhere classified": "9_nec",
}
DWELLINGS = {
    "uilding with at least one habitable conventional dwelling": "buildings",  # sic
    "Number of conventional dwellings": "conventional",
    "Number of vacant dwellings": "vacant",
}
HOUSEHOLDS = {"Housing": "dwellings_occupied", "Households": "households", "Persons": "persons"}
HOUSEHOLD_SIZES = {"Total": "total"} | {s: s for s in [*map(str, range(1, 10)), "10+"]}
GDP_TOTALS = {"GVA at basic prices": "gva_basic_keur", "Taxes on product": "taxes_on_products_keur",
              "Subsidies": "subsidies_keur", "Gross Domestic Product": "gdp_keur"}
WAGE_SECTORS = {"Average salary": "all", "Public sector": "public", "Publicly Owned Enterprises": "public_enterprises",
                "Private Sector": "private"}

_SECTION = re.compile(r"([A-U])(?:\s|-)")


def section(label: str) -> str:
    """NACE Rev.2 section letter of an ASK activity label ("C - Manufacturing", "C Production")."""
    if label == "Unknown":
        return "unknown"
    if label == "Total":
        return "total"
    if m := _SECTION.match(label):
        return m.group(1)
    raise ValueError(f"not a NACE section: {label!r}")


def _clean(label: str) -> str:
    return " ".join(label.replace("​", "").split())


class Table:
    """A PX table addressed by English variable names and labels."""

    def __init__(self, raw_dir, rel: str):
        self.rel = rel
        self.px = PxTable(raw_dir / rel)
        names = self.px.get("STUB", lang="en") + self.px.get("HEADING", lang="en")
        self.names = [_clean(n) for n in names or self.px.variables]
        self.labels = [[_clean(x) for x in self.px.labels(v, "en")] for v in self.px.variables]

    def grid(self, area_var: str | None, cat_var: str | None, mapping=None, *, where: dict, strict: bool = True):
        """{area code | KIM: {category: value}} ({area: value} without `cat_var`) over the cells matching
        `where` {variable: label}. `mapping` turns labels into category keys: a dict (with `strict`, every
        label must be in it; either way every key must be found) or a function."""
        idx = {n: i for i, n in enumerate(self.names)}
        if loose := set(self.names) - {area_var, cat_var} - set(where):
            raise ValueError(f"{self.rel}: variables {loose} neither selected nor kept")
        out: dict = {}
        for cell, value in zip(itertools.product(*self.labels), self.px.data):
            if any(cell[idx[k]] != v for k, v in where.items()):
                continue
            area = self._area(cell[idx[area_var]]) if area_var else KIM
            if cat_var is None:
                out[area] = value
                continue
            label = cell[idx[cat_var]]
            if mapping is None:
                cat = label
            elif callable(mapping):
                cat = mapping(label)
            elif label in mapping:
                cat = mapping[label]
            elif strict:
                raise ValueError(f"{self.rel}: unexpected {cat_var} {label!r}")
            else:
                continue
            out.setdefault(area, {})[cat] = value
        if not out:
            raise ValueError(f"{self.rel}: no cells match {where}")
        if isinstance(mapping, dict):
            for area, cats in out.items():
                if lost := set(mapping.values()) - set(cats):
                    raise ValueError(f"{self.rel}: {area} lacks {lost}; did ASK rename a label?")
        return out

    def _area(self, label: str):
        try:
            return AREA[fold(label)]
        except KeyError:
            raise ValueError(f"{self.rel}: unknown municipality {label!r}") from None

    def latest(self, var: str) -> str:
        """The newest label of a year variable that has any figure."""
        i = self.names.index(var)
        filled = {cell[i] for cell, v in zip(itertools.product(*self.labels), self.px.data) if v is not None}
        return max(filled)

    def spellings(self) -> dict[int, str]:
        """{municipality number: the name exactly as this table spells it}."""
        for i, name in enumerate(self.names):
            if name.lower() == "municipality":
                labels = self.px.labels(self.px.variables[i], "")
                return {AREA[fold(x)]: x for x in labels if isinstance(AREA.get(fold(x)), int)}
        return {}

    def describe(self) -> dict:
        return {
            "raw": self.rel,
            "title": self.px.text("TITLE"),
            "url": table_url(API, TABLES[self.rel]),
            "updated": self.px.text("LAST-UPDATED"),
            "ask_notes": [s for s in (self.px.text("NOTE"), self.px.text("NOTEX")) if len(s) > 40],
        }


def median_age(by_age: dict) -> float | None:
    """Median of single-year ages (open group 85+), interpolated within the median year of age."""
    counts = [by_age.get(str(a)) for a in range(85)] + [by_age.get("85+")]
    if any(n is None for n in counts):
        return None
    half, below = sum(counts) / 2, 0
    for age, n in enumerate(counts):
        if n and below + n >= half:
            return round(age + (half - below) / n, 1)
        below += n
    return None


def _add(values):
    """Sum, skipping nulls (the north in 2011); null when everything is null."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _total(values: list):
    if isinstance(values[0], dict):
        return {k: _add(v.get(k) for v in values) for k in values[0]}
    return _add(values)


def _differs(a, b) -> bool:
    if isinstance(a, dict):
        return any(_differs(v, b.get(k)) for k, v in a.items())
    return (a is None) != (b is None) or (a is not None and abs(a - b) > 2)  # ASK rounds fractional estimates


def _invert(mapping: dict) -> dict:
    return {v: k for k, v in mapping.items()}


class AskKosovo(Source):
    info = SourceInfo(
        id="ask_kosovo",
        title="Kosovo and Metohija by municipality (ASK census 2024 and other tables)",
        publisher="Kosovo Agency of Statistics (ASK), Priština",
        homepage="https://askdata.rks-gov.net/",
        license="Free to reuse with ASK credited as the source (the PX files are marked COPYRIGHT=YES)",
        description="The 38 municipalities of Kosovo and Metohija, which the Serbian statistics office has not "
        "covered since 1999: the April 2024 census (population by sex and 5-year age group, ethnicity, "
        "religion, education, economic activity, employment by NACE section, households and dwellings), the "
        "2011 census population and occupations, ASK's population estimates 2012-2025, newly registered "
        "enterprises, and Kosovo-wide GDP by activity and average wages. In the four northern municipalities "
        "(Leposavić, Zubin Potok, Zvečan, Severna Kosovska Mitrovica) most Serbs boycotted the 2024 census: "
        "ASK estimated their population, sex, age and ethnicity; every other 2024 characteristic there "
        "covers only the 15-34% who were enumerated. The north was not enumerated in 2011.",
        used_for=["Kosovo and Metohija municipalities and okruzi 25-29"],
    )

    def fetch(self, force=False):
        for rel, table in TABLES.items():
            cached = (self.raw_dir / rel).exists() and not force
            download_table(self, API, table, rel, force=force)
            if not cached:
                time.sleep(0.5)  # PxWeb's API refuses bursts (it allows a few dozen calls per 10 s)

    def process(self):
        t = {rel.rsplit("/", 1)[1].removesuffix(".px"): Table(self.raw_dir, rel) for rel in TABLES}
        areas: dict = {code: {} for code in CODES} | {KIM: {}}
        topics: dict = {}
        checks: list[str] = []

        def put(field: str, grid: dict, tables: str, basis: str):
            if missing := [c for c in CODES if c not in grid]:
                if basis != "north_not_enumerated" or set(missing) - NORTH:
                    raise ValueError(f"{tables}: no {field} for {[area_key(c) for c in missing]}")
                sample = next(iter(grid.values()))  # 2011: Mitrovica North did not exist yet
                blank = dict.fromkeys(sample) if isinstance(sample, dict) else None
                grid = {**grid, **{c: blank for c in missing}}
            summed = _total([grid[c] for c in CODES if grid[c] is not None])
            if field.startswith("median_age"):
                pass
            elif KIM not in grid:
                grid = {**grid, KIM: summed}
            elif _differs(grid[KIM], summed):
                checks.append(f"{field}: ASK's Kosovo row {grid[KIM]} != sum of municipalities {summed}; kim has the sum")
                grid = {**grid, KIM: summed}
            for area, value in grid.items():
                areas[area][field] = value
            topics[field] = {"basis": basis, "tables": tables.split("+")}

        single = t["census2024_00"]
        for year, basis in (("2024", "north_estimated"), ("2011", "north_not_enumerated")):
            by_sex = single.grid("Municipality", "Sex", SEXES, where={"Year": year, "Age": "Total"})
            for suffix in SEXES.values():
                put(f"pop_{year}{suffix}", {a: v[suffix] for a, v in by_sex.items()}, "census2024_00", basis)
            by_age = single.grid("Municipality", "Age", where={"Year": year, "Sex": "Total"})
            put(f"median_age_{year}", {a: median_age(v) for a, v in by_age.items()}, "census2024_00", "derived")

        groups = {"Total": "total"} | {g: g for g in AGE_GROUPS}
        for sex, suffix in SEXES.items():
            put(f"age_2024{suffix}", t["tab04census"].grid("Municipality", "Age group", groups, where={"Sex": sex}),
                "tab04census", "north_estimated")

        households = t["tab02ncensus"].grid("Municipality", "Categories", HOUSEHOLDS,
                                            where={"Type of residence": "Total"})
        for cat, field in (("persons", "pop_2024_enumerated"), ("households", "households_2024"),
                           ("dwellings_occupied", "dwellings_occupied_2024")):
            put(field, {a: v[cat] for a, v in households.items()}, "tab02ncensus", "enumerated")
        put("household_size_2024", t["census2024_52"].grid("Municipality", "Number of household members",
                                                           HOUSEHOLD_SIZES, where={"Year": "2024"}),
            "census2024_52", "enumerated")
        for year, basis in (("2024", "enumerated"), ("2011", "north_not_enumerated")):
            put(f"dwellings_{year}", t["census2024_51"].grid("Municipality", "Select the variable", DWELLINGS,
                                                             where={"Year": year}, strict=False),
                "census2024_51", basis)

        for year in ("2024", "2011"):
            put(f"ethnicity_{year}", t["census2024_63"].grid("Municipality", "Ethnic affiliation", ETHNICITY,
                                                             where={"Sex": "Total", "Year": year}),
                "census2024_63", "north_estimated" if year == "2024" else "north_not_enumerated")
            put(f"religion_{year}", t["census2024_10"].grid("Municipality", "Religion", RELIGION,
                                                            where={"Sex": "Total", "Year": year}),
                "census2024_10", "enumerated" if year == "2024" else "north_not_enumerated")

        put("education_2024", t["tabcensusedu3"].grid("Municipality", "Highest level of education completed",
                                                      EDUCATION, where={"Sex": "Total", "Ethnicity": "Total"}),
            "tabcensusedu3", "enumerated")

        everyone = {"Type of residence": "Total", "Sex": "Total"}
        force = t["lc02ensus"].grid("Municipality", "Category", LABOUR_FORCE, where=everyone)
        jobs = t["lc03ensus"].grid("Municipality", "Category", EMPLOYMENT, where=everyone)
        activity = {}
        for a in force:
            if force[a]["active"] != jobs[a]["active_lc03"]:
                checks.append(f"activity_2024 {a}: lc02 active {force[a]['active']} != lc03 {jobs[a]['active_lc03']}")
            activity[a] = force[a] | {k: v for k, v in jobs[a].items() if k != "active_lc03"}
        put("activity_2024", activity, "lc02ensus+lc03ensus", "enumerated")
        put("employed_by_section_2024",
            t["lc13ensus"].grid("Municipality", "Economic activities - NACE Rev.2", section,
                                where={"Employment status": "Total", "Sex": "Total"}),
            "lc13ensus", "enumerated")
        put("occupation_2011", t["tab_5.11"].grid("Municipality", "Main occupation", OCCUPATION_2011,
                                                  where={"Sex": "Total"}),
            "tab_5.11", "north_not_enumerated")

        estimates = t["tab001"].grid("Municipality", "Year", where={})
        put("pop_estimate", estimates, "tab001", "estimate")
        for a in areas.values():
            a["pop_estimate"] = {y: None if v is None else round(v) for y, v in sorted(a["pop_estimate"].items())}

        sbr = t["enterprises03"]
        years = sorted(set(sbr.labels[sbr.names.index("year")]))
        new = {}
        for y in years:
            quarters = [sbr.grid("municipality", "Code/Sector of economic activity", section,
                                 where={"year": y, "period": q}) for q in ("Q1", "Q2", "Q3", "Q4")]
            new[y] = {a: _total([q[a] for q in quarters]) for a in CODES}
        put("new_enterprises", {a: {y: new[y][a]["total"] for y in years} for a in CODES}, "enterprises03",
            "register")
        put(f"new_enterprises_{years[-1]}_by_section", new[years[-1]], "enterprises03", "register")

        for a in areas.values():
            pop, counted = a["pop_2024"], a["pop_2024_enumerated"]
            a["enumerated_share_2024"] = round(counted / pop, 4) if pop else None

        names = t["census2024_00"].spellings()
        variants: dict[int, list[str]] = {code: [] for code in CODES}
        for tab in t.values():
            for code, name in tab.spellings().items():
                if name != names[code] and name not in variants[code]:
                    variants[code].append(name)

        municipalities = {
            area_key(code): {
                "ask_code": code,
                "name_sq": names[code],
                "name_sq_variants": variants[code],
                "name_sr_cyr": cyr,
                "name_sr_lat": lat,
                "okrug_code": okrug,
                "okrug_name_cyr": OKRUZI[okrug][0],
                "okrug_name_lat": OKRUZI[okrug][1],
                "north": code in NORTH,
                **areas[code],
            }
            for code, cyr, lat, okrug, _ in MUNICIPALITIES
        }
        kim = {"name_sr_cyr": "Косово и Метохија", "name_sr_lat": "Kosovo i Metohija", **areas[KIM],
               "economy": self._economy(t)}

        return {
            "vintage": f"ASK census 2024, population estimates {max(estimates[KIM])}, "
                       f"new enterprises {years[-1]}, GDP {kim['economy']['gdp']['year']}",
            "census_reference_date": "2024-04-05",
            "okruzi": {
                code: {"name_cyr": cyr, "name_lat": lat,
                       "municipalities": [area_key(m[0]) for m in MUNICIPALITIES if m[3] == code]}
                for code, (cyr, lat) in OKRUZI.items()
            },
            "municipalities": municipalities,
            "kim": kim,
            "meta": {
                "key": "\"KM\" + ASK's municipality number (1-38, ASK's row order), zero-padded to two digits",
                "basis": {
                    "north_estimated": "2024 census; for Leposavić, Zubin Potok, Zvečan and Severna Kosovska "
                    "Mitrovica, ASK's estimate of the whole population (most Serbs boycotted the census)",
                    "enumerated": "2024 census, persons actually enumerated only; in the north a minority of "
                    "the population (see enumerated_share_2024), mostly non-Serbs",
                    "north_not_enumerated": "2011 census, which did not cover the north (null there)",
                    "derived": "computed here from ASK's single-year ages",
                    "estimate": "ASK population estimate, rounded to whole persons",
                    "register": "Statistical Business Register: enterprises newly registered in the year",
                },
                "units": {
                    "default": "persons; dwellings, buildings, households and enterprises are counts",
                    "median_age_*": "years",
                    "enumerated_share_2024": "pop_2024_enumerated / pop_2024",
                    "kim.economy.gdp": "*_keur: thousand EUR at current prices; gdp_per_capita_eur: EUR",
                    "kim.economy.wages": "average monthly wage, EUR",
                },
                "categories": {
                    "age_2024": AGE_GROUPS,
                    "ethnicity": _invert(ETHNICITY),
                    "religion": _invert(RELIGION),
                    "education_2024": {"_universe": "population aged 15+"} | _invert(EDUCATION),
                    "activity_2024": {"_universe": "population aged 15-64"} | _invert(LABOUR_FORCE)
                    | {k: v for k, v in _invert(EMPLOYMENT).items() if k != "active_lc03"},
                    "employed_by_section_2024": {"_universe": "employed aged 15-64", "keys": "NACE Rev.2 "
                                                 "sections A-U, unknown"},
                    "occupation_2011": {"_universe": "employed, ISCO-88 sub-major groups"} | _invert(OCCUPATION_2011),
                    "dwellings": _invert(DWELLINGS),
                    "household_size_2024": "household members: 1-9, 10+",
                    "new_enterprises_by_section": "NACE Rev.2 sections A-U",
                },
                "topics": topics,
                "tables": {name: tab.describe() for name, tab in t.items()},
                "checks": checks,
            },
            "_files": list(TABLES),
        }

    @staticmethod
    def _economy(t: dict) -> dict:
        gdp09, gdp13, wages, wages_by = t["gdp09"], t["gdp13"], t["tab01"], t["tab03"]
        year = gdp09.latest("Year")
        gva = gdp09.grid(None, "NACE Rev2-Economic activities", lambda s: GDP_TOTALS.get(s) or section(s),
                         where={"Gross Value Added (GVA)": "Gross Value Added (GVA)", "Year": year})[KIM]
        per_head = gdp13.grid(None, "Variables", {"GDP per capita (Euro)": "eur"}, where={"Year": year},
                              strict=False)[KIM]["eur"]
        wage_year, by_year = wages.latest("Year"), wages_by.latest("viti")

        def wage(table, var, mapping, where):
            return table.grid(None, var, mapping, where=where)[KIM]

        return {
            "gdp": {
                "year": int(year),
                **{k: gva.pop(k) for k in GDP_TOTALS.values()},
                "gdp_per_capita_eur": per_head,
                "gva_by_section_keur": gva,
                "tables": ["gdp09", "gdp13"],
            },
            "wages": {
                "year": int(wage_year),
                "gross_eur": wage(wages, "Variabla", WAGE_SECTORS, {"Year": wage_year, "Gross/net": "Gross"}),
                "net_eur": wage(wages, "Variabla", WAGE_SECTORS, {"Year": wage_year, "Gross/net": "Net"}),
                "by_section_year": int(by_year),
                "by_section_gross_eur": wage(wages_by, "economic activity", section,
                                             {"viti": by_year, "average salary": "gross"}),
                "by_section_net_eur": wage(wages_by, "economic activity", section,
                                           {"viti": by_year, "average salary": "net"}),
                "tables": ["tab01", "tab03"],
            },
        }

