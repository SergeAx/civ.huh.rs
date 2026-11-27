"""RZS economy statistics: registered employment and wages per municipality, regional GDP and GVA.

All from the Statistical Office of the Republic of Serbia (RZS): its open-data service (see _rzs.py) and,
for gross value added by oblast, the tables of the working document "Регионални бруто домаћи производ –
Региони и области Републике Србије" (published only as PDF). Kosovo and Metohija is not covered.

Interim shape (data/interim/rzs_economy.json, "data"): ``units``, ``okruzi``, ``regions`` and ``nation`` as
in rzs_census (same descriptive unit fields; Grad Novi Sad is one unit, as RZS has published it since 2020),
plus ``years`` (reference year of each group of fields) and ``activities`` (the GVA activity groups).

Per unit, okrug, region and the nation (RSD; counts are ints; null = not published):

* ``employment`` {"total", "legal_entities", "entrepreneurs", "farmers"}: registered employment by
  municipality of work, annual average of the 12 monthly states (Statistika registrovane zaposlenosti, CROSO):
  employees of legal entities, entrepreneurs with their employees and the self-employed, and registered
  individual farmers. ``employment_total_by_year`` {"2015" …}. Jobs are counted where the work is done.
* ``employment_by_section`` {"A" … "S"}: the same by NACE Rev. 2 section, without individual farmers
  (sections T and U are not published). Sections add up to legal_entities + entrepreneurs (± rounding).
* ``employment_by_residence`` {"total", "male", "female"}: registered employment by municipality of
  residence (the Republic's total includes persons with no municipality of residence on record).
* ``wage_net_rsd``, ``wage_gross_rsd``: average monthly net and gross wage over the year, by municipality of
  residence of the employee; ``wage_net_rsd_by_year`` {"2018" …}.

Regions and nation only: ``gdp_mio_rsd`` (regional GDP, current prices), ``gdp_index_prev_year`` (nominal,
previous year = 100), ``gdp_share_pct``, ``gdp_per_capita_ths_rsd``, ``gdp_per_capita_index`` (Republic =
100), ``gdp_preliminary``, ``gdp_mio_rsd_by_year`` {"2000" …}; ``lfs_unemployed_ths`` and
``lfs_unemployment_rate_pct`` (Labour Force Survey, persons 15+; no municipal figure exists: registered
unemployment is published by the National Employment Service, not RZS).

Okruzi, regions and nation (from the PDF): ``gva_mio_rsd`` (gross value added; at oblast level RZS publishes
GVA, not GDP: the difference is net taxes on products), ``gva_by_activity_mio_rsd`` {activity group}. Okruzi
also ``gva_mio_rsd_prev_year``, ``gva_index_prev_year``, ``gva_share_pct``, ``gva_per_capita_ths_rsd`` and
``gva_per_capita_index`` (Republic = 100).

Nation only: ``national_accounts`` {year: {"gdp_mio_rsd", "gdp_mio_eur", "gdp_mio_usd",
"gdp_per_capita_rsd", "gdp_per_capita_eur", "gdp_per_capita_usd"}} for the regional-accounts year and the
latest year (RZS publishes regional figures in RSD only; the national accounts give the EUR equivalent, and
their GDP of the regional year may already be revised); ``gva_extra_regio_mio_rsd`` (embassies abroad).
"""

from __future__ import annotations

import re

from ._rzs import (
    OKRUG, REGIONS, Pdf, RzsSource, as_int, categorize, latest_year, pivot, read_table,
)
from ..core.source import SourceInfo

T_EMPLOYMENT = "240204IND01"
T_SECTION = "240205IND01"
T_RESIDENCE = "24021105IND01"
T_WAGE_NET = "2403040403IND01"
T_WAGE_GROSS = "2403040403IND02"
T_RGDP = {"gdp_mio_rsd": "09020404IND01", "gdp_index_prev_year": "09020404IND02", "gdp_share_pct": "09020404IND03",
          "gdp_per_capita_ths_rsd": "09020404IND04", "gdp_per_capita_index": "09020404IND05"}
T_GDP = "09020101IND10"
T_GDP_PC = "09020101IND20"
T_LFS_UNEMPLOYED = "240003020303IND01"
T_LFS_RATE = "240003020304IND01"

# Working document no. 135 (March 2026), reference year 2024. Newer issues are listed at
# https://www.stat.gov.rs/sr-cyrl/publikacije/?a=09&s=090204 (Радни документ, Регионални бруто домаћи производ).
GVA_PDF = "https://publikacije.stat.gov.rs/G2026/Pdf/G202610135.pdf"
GVA_PDF_YEAR = "2024"
GVA_REL = "G202610135.pdf"

MODALITIES = {"0": "total", "01": "legal_entities", "02": "entrepreneurs", "03": "farmers"}
SECTIONS = {c: c for c in "ABCDEFGHIJKLMNOPQRS"}
SEXES = {"0": "total", "1": "male", "2": "female"}
CURRENCIES = {"1": "rsd", "2": "usd", "3": "eur"}
ACTIVITIES = [  # the groups of the PDF's GVA tables (NACE Rev. 2 A*10), in their row order
    ("A", "Пољопривреда"), ("B-E", "Рударство"), ("F", "Грађевинарство"), ("G-I", "Трговина"),
    ("J", "Информисање"), ("K", "Финансијске"), ("L", "Пословање некретнинама"), ("M-N", "Стручне"),
    ("O-Q", "Државна управа"), ("R-U", "Уметност"),
]
ACTIVITY_REGIONS = {"Региони Републике": "RS", "Војводине": "RS12", "Шумадије": "RS21", "Јужне и Источне": "RS22"}
_NUMBER = re.compile(r"-?\d{1,3}( \d{3})*(,\d+)?")
_HOMOGLYPHS = str.maketrans("aeopcxyABEKMHOPCTX", "аеорсхуАВЕКМНОРСТХ")


def _num(cell: str) -> float | None:
    return float(cell.replace(" ", "").replace(",", ".")) if _NUMBER.fullmatch(cell) else None


def _norm(name: str) -> str:
    return re.sub(r"[^а-яђјљњћџ]", "", name.translate(_HOMOGLYPHS).lower())


def _rows(cells: list[tuple[float, float, str]], top: float, bottom: float) -> list[list[tuple[float, str]]]:
    """Cells between y=`top` and y=`bottom`, grouped into lines (top to bottom), each sorted left to right."""
    lines: list[tuple[float, list]] = []
    for x, y, text in sorted((c for c in cells if bottom < c[1] < top), key=lambda c: -c[1]):
        if lines and abs(lines[-1][0] - y) <= 1.5:
            lines[-1][1].append((x, text))
        else:
            lines.append((y, [(x, text)]))
    return [sorted(line) for _, line in lines]


class RzsEconomy(RzsSource):
    info = SourceInfo(
        id="rzs_economy",
        title="Employment, wages and regional GDP (RZS)",
        publisher="Statistical Office of the Republic of Serbia (RZS)",
        homepage="https://data.stat.gov.rs/?caller=SDDB",
        license="Open data; free reuse with attribution of the source (RZS terms of use)",
        description="Registered employment by municipality of work (total and by industry section) and of "
        "residence, and the average monthly net and gross wage, for every municipality and city outside Kosovo "
        "and Metohija; regional GDP of the four statistical regions; gross value added by oblast (okrug) and "
        "activity from RZS's regional accounts working document; national GDP in RSD and EUR; Labour Force "
        "Survey unemployment by region.",
        used_for=["Municipality jobs and wages", "Okrug and regional economy"],
    )
    tables = {T_EMPLOYMENT: "csv", T_SECTION: "csv", T_RESIDENCE: "csv", T_WAGE_NET: "csv", T_WAGE_GROSS: "csv",
              **{t: "csv" for t in T_RGDP.values()}, T_GDP: "csv", T_GDP_PC: "csv",
              T_LFS_UNEMPLOYED: "csv", T_LFS_RATE: "csv"}

    def fetch(self, force: bool = False) -> None:
        super().fetch(force)
        self.download(GVA_PDF, GVA_REL, force=force, expect_binary=True)

    def process(self) -> dict:
        terr = self.territory()
        codes = terr.codes
        stats: dict[str, dict] = {}

        def put(code: str, **fields) -> None:
            if code in codes:
                stats.setdefault(code, {}).update(fields)

        years = {
            "employment": latest_year(self.path(T_EMPLOYMENT), IDModalitetRegZap="0"),
            "employment_by_residence": latest_year(self.path(T_RESIDENCE), IDPol="0"),
            "wages": latest_year(self.path(T_WAGE_NET)),
            "regional_gdp": latest_year(self.path(T_RGDP["gdp_mio_rsd"])),
            "national_gdp": latest_year(self.path(T_GDP), IDVrPod="1"),
            "lfs": latest_year(self.path(T_LFS_RATE), IDPol="0", IDStarGrupa="15"),
            "gva_oblast": GVA_PDF_YEAR,
        }

        emp, _ = pivot(self.path(T_EMPLOYMENT), codes, ("god", "IDModalitetRegZap"))
        for code, v in emp.items():
            put(code, employment={key: as_int(v.get((years["employment"], m))) for m, key in MODALITIES.items()},
                employment_total_by_year={y: as_int(n) for (y, m), n in sorted(v.items()) if m == "0"})
        sec, _ = pivot(self.path(T_SECTION), codes, "IDKD08", year=years["employment"])
        for code, v in sec.items():
            put(code, employment_by_section=categorize(v, SECTIONS, "0"))
        res, _ = pivot(self.path(T_RESIDENCE), codes, "IDPol", year=years["employment_by_residence"])
        for code, v in res.items():
            put(code, employment_by_residence={key: as_int(v.get(s)) for s, key in SEXES.items()})

        net, _ = pivot(self.path(T_WAGE_NET), codes, "god", m_as_zero=False)
        gross, _ = pivot(self.path(T_WAGE_GROSS), codes, "god", year=years["wages"], m_as_zero=False)
        for code, v in net.items():
            put(code, wage_net_rsd=as_int(v.get(years["wages"])),
                wage_gross_rsd=as_int(gross.get(code, {}).get(years["wages"])),
                wage_net_rsd_by_year={y: as_int(n) for y, n in sorted(v.items())})

        rgdp_codes = {"RS", *REGIONS}
        for field, table in T_RGDP.items():
            vals, _ = pivot(self.path(table), rgdp_codes, "god", m_as_zero=False)
            for code, v in vals.items():
                put(code, **{field: v.get(years["regional_gdp"])})
                if field == "gdp_mio_rsd":
                    put(code, gdp_mio_rsd_by_year={y: as_int(n) for y, n in sorted(v.items()) if n is not None})
        for r in read_table(self.path(T_RGDP["gdp_mio_rsd"])):
            if r["IDTer"] in rgdp_codes and r["god"] == years["regional_gdp"]:
                s = stats[r["IDTer"]]
                put(r["IDTer"], gdp_mio_rsd=as_int(s["gdp_mio_rsd"]), gdp_per_capita_ths_rsd=as_int(
                    s["gdp_per_capita_ths_rsd"]), gdp_preliminary=r["IDStatusPodatka"] == "P")

        lfs_fixed = {"IDPol": "0", "IDStarGrupa": "15"}
        rate, _ = pivot(self.path(T_LFS_RATE), rgdp_codes, "god", lfs_fixed, m_as_zero=False)
        count, _ = pivot(self.path(T_LFS_UNEMPLOYED), rgdp_codes, "god", lfs_fixed, m_as_zero=False)
        for code in rgdp_codes:
            put(code, lfs_unemployment_rate_pct=rate.get(code, {}).get(years["lfs"]),
                lfs_unemployed_ths=count.get(code, {}).get(years["lfs"]))

        nat: dict[str, dict] = {}
        for table, what in ((T_GDP, "gdp_mio"), (T_GDP_PC, "gdp_per_capita")):
            for r in read_table(self.path(table)):
                if r["IDTer"] == "RS" and r["god"] in (years["regional_gdp"], years["national_gdp"]):
                    v = r["vrednost"]
                    nat.setdefault(r["god"], {})[f"{what}_{CURRENCIES[r['IDVrPod']]}"] = float(v) if v else None
        put("RS", national_accounts=nat)

        oblasts, extra = self._gva(terr)
        for code, fields in oblasts.items():
            put(code, **fields)
        put("RS", gva_extra_regio_mio_rsd=extra)
        # Novi Sad's gradske opštine have rows only up to 2019: units are those of the reference year.
        stats = {c: s for c, s in stats.items()
                 if c not in terr.municipalities or (s.get("employment") or {}).get("total") is not None}

        return {
            "vintage": f"RZS registered employment {years['employment']}, wages {years['wages']}, "
            f"regional GDP {years['regional_gdp']}",
            "years": years,
            **terr.assemble(stats),
            "activities": [{"key": k, "name_cyr": n} for k, n in ACTIVITIES],
            "tables": {"employment": T_EMPLOYMENT, "employment_by_section": T_SECTION,
                       "employment_by_residence": T_RESIDENCE, "wage_net_rsd": T_WAGE_NET,
                       "wage_gross_rsd": T_WAGE_GROSS, **T_RGDP, "national_accounts": [T_GDP, T_GDP_PC],
                       "lfs_unemployed_ths": T_LFS_UNEMPLOYED, "lfs_unemployment_rate_pct": T_LFS_RATE,
                       "gva": GVA_PDF},
            "_files": [*self.files(), GVA_REL],
        }

    def _gva(self, terr) -> tuple[dict[str, dict], int | None]:
        """GVA by oblast (Table 3) and by region/oblast and activity (Tables 4-7) of the working document.
        Every number is cross-checked (totals against Table 3, activities against totals): a layout the
        parser misreads raises instead of producing wrong figures."""
        pdf = Pdf(self.raw_dir / GVA_REL)
        captions: dict[int, tuple[int, float, float, str]] = {}
        pages = {}
        for i in range(len(pdf.pages())):
            pages[i] = cells = pdf.cells(i)
            found = [(y, x, int(m.group(1))) for x, y, t in cells if (m := re.match(r"Табела\s*(\d+)\.", t))]
            for y, x, number in found:
                caption = " ".join(t for cy, cx, t in sorted(((-cy, cx, t) for cx, cy, t in cells))
                                   if y - 16 <= -cy <= y + 1.5 and cx >= x)  # captions wrap onto a second line
                bottom = max((other for other, _, _ in found if other < y), default=float("-inf"))
                captions[number] = (i, y, bottom, caption)  # the last match wins: tables follow the contents page

        page, top, bottom, _ = captions[3]
        names = {_norm(terr.areas[c]["name_cyr"]): c for c in OKRUG} | {_norm("Република Србија"): "RS"}
        out: dict[str, dict] = {}
        extra = None
        for line in _rows(pages[page], top, bottom):
            label, values = line[0][1], [_num(t) for _, t in line[1:]]
            if len(values) != 9:
                continue
            if _norm(label).startswith(_norm("Екстра регио")):
                extra = as_int(values[0])
            code = names.get(_norm(label))
            if code:
                gva, prev, index, share, _, per_capita, _, level, _ = values
                out[code] = {"gva_mio_rsd": as_int(gva), "gva_mio_rsd_prev_year": as_int(prev),
                             "gva_index_prev_year": index, "gva_share_pct": share,
                             "gva_per_capita_ths_rsd": as_int(per_capita), "gva_per_capita_index": level}
        if len(out) != len(OKRUG) + 1:
            raise ValueError(f"{GVA_REL} Table 3: found {len(out)} of {len(OKRUG) + 1} rows")

        for page, top, bottom, caption in captions.values():
            if f"по делатностима, {GVA_PDF_YEAR}" not in caption:
                continue
            region = next(code for key, code in ACTIVITY_REGIONS.items() if key in caption)
            cols = list(REGIONS) if region == "RS" else [c for c in sorted(OKRUG) if c.startswith(region)]
            cols = ["RS" if region == "RS" else region, *cols]
            lines = _rows(pages[page], top, bottom)
            rows = [[_num(t) for _, t in line if _num(t) is not None] for line in lines]
            rows = [r[:len(cols)] for r in rows if len(r) >= len(cols)][:1 + len(ACTIVITIES)]
            labels = [t.translate(_HOMOGLYPHS) for line in lines for x, t in line if x < 250]
            order = [k for t in labels for k, prefix in ACTIVITIES if t.startswith(prefix)]
            if order != [k for k, _ in ACTIVITIES] or len(rows) != 1 + len(ACTIVITIES):
                raise ValueError(f"{GVA_REL}: unexpected layout of '{caption}'")
            for j, code in enumerate(cols):
                total, parts = rows[0][j], [r[j] for r in rows[1:]]
                expect = out[code]["gva_mio_rsd"] if code in out else sum(
                    out[o]["gva_mio_rsd"] for o in OKRUG if o.startswith(code))
                if abs(total - expect) > len(OKRUG) or abs(sum(parts) - total) > len(ACTIVITIES):
                    raise ValueError(f"{GVA_REL}: '{caption}' column {j} ({code}) does not add up")
                by_activity = {k: as_int(v) for (k, _), v in zip(ACTIVITIES, parts)}
                out.setdefault(code, {}).update(gva_by_activity_mio_rsd=by_activity)
                if code in REGIONS:
                    out[code]["gva_mio_rsd"] = as_int(total)
                if code == "RS11":
                    out["RS110"]["gva_by_activity_mio_rsd"] = by_activity
        missing = [c for c in (*OKRUG, *REGIONS, "RS") if "gva_by_activity_mio_rsd" not in out.get(c, {})]
        if missing:
            raise ValueError(f"{GVA_REL}: no GVA by activity for {missing}")
        return out, extra
