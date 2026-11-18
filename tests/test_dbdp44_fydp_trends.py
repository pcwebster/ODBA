"""DBDP-44: FYDP Trends sheet in the Excel report.

Builds the workbook from the committed parquet into a temp dir (never
output/) and checks the sheet against the records, the Summary sheet and
the committed consumption-layer long fact. Skips only when the report
dependencies or the committed parquet are missing.
"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "output" / "fact_budget_line_items.parquet"
LONG_FACT = ROOT / "output" / "consumption" / "fact_budget_long.csv"
HAVE_DEPS = all(importlib.util.find_spec(m) for m in ("duckdb", "openpyxl", "pandas"))
SKIP_REASON = ("needs duckdb, openpyxl and pandas (pip install -r requirements.txt) "
               "and output/fact_budget_line_items.parquet")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["OPENPYXL_LXML"] = "False"   # same pin as query_budget (DBDP-43)


@unittest.skipUnless(HAVE_DEPS and PARQUET.exists(), SKIP_REASON)
class FydpTrendsSheetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import query_budget as qb
        from openpyxl import load_workbook
        cls.qb = qb
        cls.sheets, cls.extra = qb.run_queries(qb.PARQUET_FILE)
        cls.fydp = cls.extra["fydp_trends"]
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "report.xlsx"
        qb.save_workbook_deterministic(qb.build_workbook(cls.sheets, cls.extra),
                                       cls.path, cls.extra["vintage"])
        cls.wb = load_workbook(cls.path)
        cls.ws = cls.wb[qb.FYDP_SHEET]
        cls.records = cls.sheets["All Records"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self):
        return list(self.ws.iter_rows(values_only=True))

    def text(self):
        return " ".join(v for r in self.rows() for v in r if isinstance(v, str))

    def test_is_ninth_sheet(self):
        self.assertEqual(len(self.wb.sheetnames), 9)
        self.assertEqual(self.wb.sheetnames[-1], "FYDP Trends")

    def test_budget_request_label_on_sheet(self):
        """AR c10045: the sheet must say the figures are Budget Request data."""
        t = self.text()
        self.assertIn("Lifecycle Stage: Budget Request", t)
        self.assertIn("FY2027 President's Budget Request submission", t)
        self.assertIn("None of it is enacted, apportioned or execution data", t)

    def test_years_and_basis_labels_follow_consumption_rule(self):
        from etl_budget import amount_basis_for
        years = [fy for fy, _ in self.fydp["years"]]
        self.assertEqual(years, list(range(2025, 2032)))
        names = {"actual": "Actual", "estimate": "Estimate", "request": "Request",
                 "fydp_projection": "FYDP projection"}
        for fy, label in self.fydp["years"]:
            self.assertEqual(label, f"FY{fy} {names[amount_basis_for(fy, 2027)]} ($M)")
        self.assertEqual(list(self.fydp["amounts"].columns),
                         ["Appropriation Type"] + [l for _, l in self.fydp["years"]])

    def test_appropriation_order(self):
        self.assertEqual(list(self.fydp["amounts"]["Appropriation Type"]),
                         ["O&M", "Procurement", "RDT&E", "DWCF", "DHP"])
        self.assertEqual(set(self.fydp["amounts"]["Appropriation Type"]),
                         set(self.records["appropriation_type"]))

    def test_amounts_and_counts_tie_to_records(self):
        df = self.records
        for (_, a), (_, c) in zip(self.fydp["amounts"].iterrows(),
                                  self.fydp["records"].iterrows()):
            sub = df[df["appropriation_type"] == a["Appropriation Type"]]
            self.assertEqual(c["Records"], len(sub))
            for fy, label in self.fydp["years"]:
                col = sub[f"cost_fy{fy}"].dropna().astype(float)
                self.assertEqual(c[f"FY{fy}"], len(col))
                if len(col) == 0:
                    self.assertIsNone(a[label], (a["Appropriation Type"], fy))
                else:
                    self.assertAlmostEqual(a[label], round(col.sum(), 1), places=6)

    def test_fy2027_ties_to_summary_sheet(self):
        summ = self.sheets["Summary"]
        for _, a in self.fydp["amounts"].iterrows():
            s = summ[summ["Appropriation Type"] == a["Appropriation Type"]]
            expect = float(s["FY2027 Request ($M)"].sum())
            got = a["FY2027 Request ($M)"]
            if got is None:
                self.assertEqual(expect, 0)        # Summary COALESCEs to 0
            else:
                self.assertLessEqual(abs(got - expect), 0.05 * len(s) + 0.05)

    @unittest.skipUnless(LONG_FACT.exists(), "consumption long fact not committed")
    def test_ties_to_consumption_long_fact(self):
        """Same totals and same basis as the canonical long fact (c10575)."""
        import pandas as pd
        long = pd.read_csv(LONG_FACT)
        long = long[(long["budget_year"] == 2027)
                    & (long["data_vintage"] == self.extra["vintage"])]
        m = long.merge(self.records[["record_id", "appropriation_type"]],
                       on="record_id", how="inner")
        self.assertEqual(len(m), len(long), "every FY2027 long row is in the slice")
        names = {"actual": "Actual", "estimate": "Estimate", "request": "Request",
                 "fydp_projection": "FYDP projection"}
        for fy, label in self.fydp["years"]:
            bases = set(m[m["funding_fy"] == fy]["amount_basis"])
            self.assertEqual({f"FY{fy} {names[b]} ($M)" for b in bases}, {label})
        for _, a in self.fydp["amounts"].iterrows():
            for fy, label in self.fydp["years"]:
                sub = m[(m["appropriation_type"] == a["Appropriation Type"])
                        & (m["funding_fy"] == fy)]
                if a[label] is None:
                    self.assertEqual(len(sub), 0)
                else:
                    self.assertAlmostEqual(a[label], round(sub["amount_musd"].sum(), 1),
                                           places=6)

    def test_blank_is_not_zero(self):
        rows = {r[0]: r for r in self.rows()
                if r[0] in ("O&M", "Procurement", "RDT&E", "DWCF", "DHP")
                and r[1] is not None and not isinstance(r[1], int)
                or (r[0] == "DWCF" and r[2] is None)}
        dwcf = rows["DWCF"]
        self.assertTrue(all(v is None for v in dwcf[1:8]), dwcf)
        om = rows["O&M"]
        self.assertIsNotNone(om[3])          # FY2027 request present
        self.assertTrue(all(v is None for v in om[4:8]), om)   # no FY2028+ in OP-5

    def test_chart_one_line_per_type_with_data_and_gaps(self):
        with zipfile.ZipFile(self.path) as z:
            charts = [n for n in z.namelist() if re.fullmatch(r"xl/charts/chart\d+\.xml", n)]
            self.assertEqual(len(charts), 1)
            xml = z.read(charts[0]).decode("utf-8")
        with_data = sum(1 for _, a in self.fydp["amounts"].iterrows()
                        if any(a[l] is not None for _, l in self.fydp["years"]))
        self.assertEqual(len(re.findall(r"<(?:c:)?ser>", xml)), with_data)
        self.assertEqual(with_data, 4)       # DWCF has no amounts
        self.assertRegex(xml, r'<(?:c:)?dispBlanksAs val="gap"')
        self.assertIn("President's Budget Request", xml)
        # categories are the year headers, read as text
        self.assertEqual(len(re.findall(r"<(?:c:)?cat><(?:c:)?strRef>", xml)), with_data)
        self.assertNotRegex(xml, r"<(?:c:)?cat><(?:c:)?numRef>")

    def test_no_wall_clock_values(self):
        import datetime as dt
        ts = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
        for row in self.rows():
            for v in row:
                self.assertNotIsInstance(v, (dt.datetime, dt.time))
                if isinstance(v, str):
                    self.assertIsNone(ts.search(v), v)


if __name__ == "__main__":
    unittest.main()
