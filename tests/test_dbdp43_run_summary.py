"""DBDP-43: ETL Run Summary sheet in the Excel report.

Runs query_budget.run_queries + build_workbook against the committed
parquet and writes the workbook to a temp dir (never to output/).
Skips only when the report dependencies (duckdb, openpyxl) or the
committed parquet are missing; the skip reason says which.
"""
import importlib.util
import json
import os
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

# query_budget pins openpyxl's standard-library XML writer when it is
# imported. Under `unittest discover` another test may import openpyxl
# first, so pin it here too, before any test runs (DBDP-43 round 2).
os.environ["OPENPYXL_LXML"] = "False"
HAVE_LXML = importlib.util.find_spec("lxml") is not None
COMMITTED_XLSX = ROOT / "output" / "ODBA_FY2027_Budget_Report.xlsx"


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

    def test_saved_package_carries_no_clock_values(self):
        """core.xml dates are the data vintage; zip entries use the 1980 epoch."""
        import zipfile
        out = Path(self.tmp.name) / "det.xlsx"
        self.qb.save_workbook_deterministic(
            self.qb.build_workbook(self.sheets, self.summary), out,
            self.summary["vintage"])
        stamp = f"{self.summary['vintage']}T00:00:00Z"
        with zipfile.ZipFile(out) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual({i.date_time for i in z.infolist()}, {self.qb.ZIP_EPOCH})
            core = z.read("docProps/core.xml").decode("utf-8")
        self.assertEqual(len(re.findall(re.escape(stamp), core)), 2, core)

    def test_null_stage_outside_slice_is_labelled_not_fatal(self):
        """An out-of-slice row with a NULL or empty lifecycle stage must not
        break the sheet; FY2027 slice figures stay unchanged."""
        import pandas as pd
        df = pd.read_parquet(PARQUET)
        extra = df[df["budget_year"] != 2027.0].head(2).copy()
        self.assertEqual(len(extra), 2, "fixture needs two non-FY2027 rows")
        extra["data_lifecycle_stage"] = [None, ""]
        fixture = Path(self.tmp.name) / "null_stage.parquet"
        pd.concat([df, extra], ignore_index=True).to_parquet(fixture, index=False)
        sheets, summary = self.qb.run_queries(fixture)
        prov = dict(summary["provenance"].itertuples(index=False))
        self.assertIn("(null)", prov["Lifecycle stages in dataset"])
        self.assertIn("(blank)", prov["Lifecycle stages in dataset"])
        self.assertEqual(prov["Records in report slice"], len(self.sheets["All Records"]))
        self.assertTrue((summary["checks"]["Result"] == "PASS").all())

    BUILD = ("import sys; sys.path.insert(0, sys.argv[1]); import query_budget as q; "
             "s, r = q.run_queries(q.PARQUET_FILE); "
             "q.save_workbook_deterministic(q.build_workbook(s, r), sys.argv[2], r['vintage'])")

    def _build_in_subprocess(self, name, openpyxl_lxml, prelude=""):
        import hashlib
        import subprocess
        env = dict(os.environ)
        if openpyxl_lxml is None:
            env.pop("OPENPYXL_LXML", None)
        else:
            env["OPENPYXL_LXML"] = openpyxl_lxml
        out = Path(self.tmp.name) / name
        res = subprocess.run([sys.executable, "-c", prelude + self.BUILD, str(ROOT), str(out)],
                             env=env, capture_output=True, text=True)
        digest = hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else None
        return res, digest

    def test_byte_identical_across_processes(self):
        """Separate processes write identical bytes, whatever the caller's
        OPENPYXL_LXML setting: query_budget pins the stdlib XML writer."""
        digests = []
        for i, setting in enumerate((None, None, "True", "False")):
            res, digest = self._build_in_subprocess(f"proc{i}.xlsx", setting)
            self.assertEqual(res.returncode, 0, res.stderr)
            digests.append(digest)
        self.assertEqual(len(set(digests)), 1, digests)

    def test_xml_writer_is_pinned_to_stdlib(self):
        import openpyxl.xml
        self.assertIs(openpyxl.xml.LXML, False)

    @unittest.skipUnless(HAVE_LXML, "lxml is not installed, so openpyxl cannot pick it")
    def test_refuses_to_save_with_lxml_writer(self):
        """If openpyxl was imported with lxml before query_budget, the save
        stops instead of writing different bytes."""
        res, digest = self._build_in_subprocess(
            "lxml.xlsx", "True", prelude="import openpyxl; ")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("OPENPYXL_LXML=False", res.stderr)
        self.assertIsNone(digest)

    def test_committed_workbook_is_current(self):
        """A fresh build matches the committed output workbook byte for byte
        (supported stack: requirements.txt pins and this Python's zlib)."""
        import hashlib
        import zlib
        res, digest = self._build_in_subprocess("fresh.xlsx", None)
        self.assertEqual(res.returncode, 0, res.stderr)
        committed = hashlib.sha256(COMMITTED_XLSX.read_bytes()).hexdigest()
        self.assertEqual(digest, committed,
                         f"fresh build differs from {COMMITTED_XLSX.name}; regenerate it with "
                         f"python3 query_budget.py (zlib {zlib.ZLIB_RUNTIME_VERSION})")


if __name__ == "__main__":
    unittest.main()
