import unittest

from pipeline.build import units
from pipeline.build.citizens import largest_remainder


def rs_unit(code, okrug="06", pop=1000, sections=None, farmers=0):
    return {
        "code": code, "kim": False, "okrug_code": okrug, "population": pop, "reliable": True,
        "jobs_workplace_by_section": sections or {}, "farmers": farmers, "employed_by_section": None,
    }


class UnitsTest(unittest.TestCase):
    def test_harmonise_sums_source_categories(self):
        raw = {"none": 5, "primary_incomplete": 10, "primary": 20, "gymnasium": 1, "vocational_short": 2,
               "vocational_4y": 3, "specialization": 4, "higher_vocational": 6, "university": 7, "unknown": 1}
        out = units._harmonise(raw, units.EDUCATION, 1)
        self.assertEqual(out, {"none": 15, "primary": 20, "secondary": 10, "tertiary": 13, "unknown": 1})

    def test_harmonise_missing_source_is_null_not_zero(self):
        out = units._harmonise({"orthodox": 5}, units.RELIGION, 1)
        self.assertEqual(out["orthodox"], 5)
        self.assertIsNone(out["catholic"])

    def test_mean_age_from_groups(self):
        groups = dict.fromkeys(units.AGE_GROUPS, 0) | {"20-24": 1, "85+": 1}
        self.assertEqual(units.mean_age(groups), 56.2)
        self.assertIsNone(units.mean_age({"0-4": 3}))

    def test_plain_name_drops_city_status(self):
        self.assertEqual(units.plain_name("Град Нови Сад"), "Нови Сад")
        self.assertEqual(units.plain_name("Grad Niš"), "Niš")
        self.assertEqual(units.plain_name("Градиште"), "Градиште")

    def test_map_units_joins_parts_the_statistics_report_as_one(self):
        bounds = {
            "gradovi": [{"code": "89010", "name_lat": "Grad Novi Sad"}],
            "units": [
                {"code": "80519", "name_cyr": "Петроварадин", "name_lat": "Petrovaradin", "grad_code": "89010",
                 "rings": [[[1, 1]]], "area_km2": 2.0, "seat": {"lon": 2, "lat": 2}},
                {"code": "80284", "name_cyr": "Нови Сад", "name_lat": "Novi Sad", "grad_code": "89010",
                 "rings": [[[0, 0]]], "area_km2": 3.0, "seat": {"lon": 1, "lat": 1}},
                {"code": "70017", "name_cyr": "А", "name_lat": "A", "grad_code": None, "rings": [], "area_km2": 1.0,
                 "seat": {"lon": 0, "lat": 0}},
            ],
        }
        out = units.map_units(bounds, {"89010", "70017"})
        self.assertEqual([u["code"] for u in out], ["70017", "89010"])
        ns = out[1]
        self.assertEqual(ns["area_km2"], 5.0)
        self.assertEqual(len(ns["rings"]), 2)
        self.assertEqual(ns["seat"], {"lon": 1, "lat": 1})
        self.assertEqual(ns["name_lat"], "Novi Sad")
        with self.assertRaises(KeyError):
            units.map_units(bounds, {"70017"})

    def test_gdp_shares_add_up_to_the_published_totals(self):
        us = {
            "1": rs_unit("1", sections={"C": 30, "J": 10}, farmers=5),
            "2": rs_unit("2", sections={"C": 10, "J": 30}),
            "KM01": {"code": "KM01", "kim": True, "population": 100, "reliable": True,
                     "employed_by_section": {s: 1 for s in units.SECTIONS}},
            "KM02": {"code": "KM02", "kim": True, "population": 100, "reliable": False, "employed_by_section": None},
        }
        groups = dict.fromkeys(units.GVA_GROUPS, 0) | {"A": 10, "B-E": 80, "J": 40}
        econ = {
            "years": {"gva_oblast": "2024"},
            "okruzi": {"06": {"gva_mio_rsd": 130, "gva_by_activity_mio_rsd": groups}},
            "nation": {"national_accounts": {"2024": {"gdp_mio_rsd": 260, "gdp_mio_eur": 2}}},
        }
        ask = {"kim": {"economy": {"gdp": {"year": 2024, "gdp_keur": 2000, "gva_basic_keur": 1000,
                                            "gva_by_section_keur": {s: 50 for s in "ABCDEFGHIJKLMNOPQRST"}}}}}
        summary = units.add_gva(us, econ, ask)
        self.assertEqual(summary["okruzi"]["06"], 2_000_000)  # 130 M RSD of GVA, ×2 to GDP, at 130 RSD/€
        self.assertAlmostEqual(us["1"]["gdp"] + us["2"]["gdp"], 2_000_000, delta=10)
        self.assertEqual(us["1"]["gdp_by_industry"]["A"], round(10e6 * 2 / 130))  # farmers only in "1"
        self.assertAlmostEqual(us["KM01"]["gdp"] + us["KM02"]["gdp"], 2_000_000, delta=10)
        self.assertEqual(round(us["KM01"]["gdp"]), round(us["KM02"]["gdp"]))  # same population and per-head rate

    def test_largest_remainder_sums_exactly(self):
        out = largest_remainder({"a": 1, "b": 1, "c": 1}, 10)
        self.assertEqual(sum(out.values()), 10)
        self.assertEqual(largest_remainder({"a": 0, "b": 0}, 5), {"a": 0, "b": 0})


if __name__ == "__main__":
    unittest.main()
