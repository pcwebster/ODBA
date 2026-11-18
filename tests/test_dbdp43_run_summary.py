"""DBDP-43: ETL Run Summary sheet in the Excel report.

Runs query_budget.run_queries + build_workbook against the committed
parquet and writes the workbook to a temp dir (never to output/).
Skips only when the report dependencies (duckdb, openpyxl) or the
committed parquet are missing; the skip reason says which.
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "output" / "fact_budget_line_items.parquet"
MANIFEST = ROOT / "data" / "source_manifest.json"
HAVE_DEPS = all(importlib.util.find_spec(m) for m in ("duckdb", "openpyxl", "pandas"))
SKIP_REASON = ("needs duckdb, openpyxl and pandas (pip install -r requirements.txt) "
               "and output/fact_budget_line_items.parquet")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@unittest.skipUnless(HAVE_DEPS and PARQUET.exists(), SKIP_REASON)
class RunSummarySheetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import query_budget as qb
        from openpyxl import load_workbook
        cls.qb = qb
        cls.sheets, cls.summary = qb.run_queries(qb.PARQUET_FILE)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "report.xlsx"
        qb.build_workbook(cls.sheets, cls.summary).save(cls.path)
        cls.wb = load_workbook(cls.path)
        cls.ws = cls.wb[qb.RUN_SUMMARY_SHEET]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self):
        return [r for r in self.ws.iter_rows(values_only=True)]

    def test_is_eighth_sheet_and_existing_sheets_unchanged(self):
        self.assertEqual(self.wb.sheetnames,
                         ["Summary", "By Agency", "Year-over-Year", "RDT&E by BA",
                          "Procurement", "RDT&E", "All Records", "ETL Run Summary"])

    def test_lifecycle_label_on_sheet(self):
        self.assertIn("Lifecycle Stage: Budget Request", self.ws["A2"].value)

    def test_record_counts_tie_to_all_records(self):
        ex = self.summary["exhibits"]
        body, total = ex.iloc[:-1], ex.iloc[-1]
        n_all = len(self.sheets["All Records"])
        self.assertEqual(int(body["Records"].sum()), n_all)
        self.assertEqual(total["Records"], n_all)
        self.assertEqual(total["Exhibit Type"], "Total")
        counts = self.sheets["All Records"]["exhibit_type"].value_counts()
        for _, r in body.iterrows():
            self.assertEqual(r["Records"], counts[r["Exhibit Type"]])

    def test_fy2027_totals_tie_to_summary_sheet(self):
        summ = self.sheets["Summary"]
        ex = self.summary["exhibits"].iloc[:-1]
        for _, r in ex.iterrows():
            s = summ[(summ["Exhibit"] == r["Exhibit Type"])
                     & (summ["Appropriation Type"] == r["Appropriation Type"])]
            self.assertEqual(len(s), 1)
            amt = r["FY2027 Request ($M)"]
            expect = s["FY2027 Request ($M)"].iloc[0]
            if amt is None:
                self.assertEqual(expect, 0)   # Summary sheet COALESCEs to 0
            else:
                self.assertAlmostEqual(round(amt, 1), expect, places=6)
        raw = self.sheets["All Records"]["cost_fy2027"].dropna().astype(float).sum()
        self.assertAlmostEqual(self.summary["exhibits"].iloc[-1]["FY2027 Request ($M)"],
                               round(raw, 3), places=6)

    def test_blank_is_not_zero(self):
        ex = self.summary["exhibits"]
        no_amount = ex[ex["Records with FY2027 Amount"] == 0]
        self.assertTrue(len(no_amount) > 0, "fixture expects RF-1 with no FY2027 amounts")
        for v in no_amount["FY2027 Request ($M)"]:
            self.assertIsNone(v)
        # and it lands as an empty cell, not 0, in the saved workbook
        rf1 = [r for r in self.rows() if r[0] == "RF-1" and r[1] == "DWCF"]
        self.assertEqual(len(rf1), 1)
        self.assertIsNone(rf1[0][4])

    def test_missing_counts_match_records(self):
        df = self.sheets["All Records"]
        miss = self.summary["missing"]
        for field in self.qb.RUN_SUMMARY_KEY_FIELDS:
            blank = df[field].isna() | (df[field].astype(str).str.strip() == "")
            self.assertEqual(int(miss.iloc[-1][f"{field} blank"]), int(blank.sum()))
            for _, r in miss.iloc[:-1].iterrows():
                sub = df["exhibit_type"] == r["Exhibit Type"]
                self.assertEqual(int(r[f"{field} blank"]), int((blank & sub).sum()), field)

    def test_checks_all_pass(self):
        checks = self.summary["checks"]
        self.assertTrue((checks["Result"] == "PASS").all(), checks.to_string())
        life = checks[checks["Check"].str.startswith("data_lifecycle_stage")].iloc[0]
        self.assertEqual(life["Records Checked"], len(self.sheets["All Records"]))

    def test_vintage_and_file_count_come_from_manifest(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        prov = dict(self.summary["provenance"].itertuples(index=False))
        files = set(self.sheets["All Records"]["source_file"])
        self.assertEqual(prov["Source files contributing records"], len(files))
        self.assertEqual({manifest[f]["acquisition_date"] for f in files},
                         {prov["Data vintage (source acquisition date, download manifest)"]})
        self.assertEqual(prov["Dataset SHA-256"], self.qb.sha256_file(PARQUET))

    def test_no_wall_clock_values(self):
        """Nothing on the sheet may be a datetime or an ISO timestamp."""
        import datetime as dt
        ts = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
        for row in self.rows():
            for v in row:
                self.assertNotIsInstance(v, (dt.datetime, dt.time))
                if isinstance(v, str):
                    self.assertIsNone(ts.search(v), v)

    def test_deterministic_rebuild(self):
        """Same parquet -> same sheet, cell for cell, including order."""
        from openpyxl import load_workbook
        sheets2, summary2 = self.qb.run_queries(self.qb.PARQUET_FILE)
        p2 = Path(self.tmp.name) / "report2.xlsx"
        self.qb.build_workbook(sheets2, summary2).save(p2)
        ws2 = load_workbook(p2)[self.qb.RUN_SUMMARY_SHEET]
        self.assertEqual(self.rows(), list(ws2.iter_rows(values_only=True)))


if __name__ == "__main__":
    unittest.main()
