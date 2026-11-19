"""DBDP-97 / DBDP-110 / DBDP-111: query-layer hardening regression tests.

DBDP-110: query_budget.run_queries() builds report_slice with bound
parameters, so a parquet path or data_vintage holding a single quote is
handled as a value, not SQL text.
DBDP-111: query.connect() hands the parquet path to DuckDB as a value and
'budget' stays a read-only view.
DBDP-97: query.py --csv neutralizes leading formula characters in text
cells only; numbers and the console renderer are unchanged.

Fixtures are written to a temp dir, never to output/.
"""
import contextlib
import csv
import io
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PARQUET = ROOT / "output" / "fact_budget_line_items.parquet"

try:
    import duckdb  # noqa: F401
    HAVE_STACK = PARQUET.exists()
except ImportError:
    HAVE_STACK = False


@unittest.skipUnless(HAVE_STACK, "needs duckdb (requirements.txt) and "
                                 "output/fact_budget_line_items.parquet")
class QueryHardeningTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import query
        cls.q = query

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # A directory name with a single quote: the case manual escaping
        # used to exist for.
        self.quoted_dir = Path(self.tmp.name) / "it's here"
        self.quoted_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _quiet(self, fn, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn(*args, **kwargs)
        return result, buf.getvalue()

    # ── DBDP-111 ──────────────────────────────────────────────────────────
    def test_connect_reads_a_path_with_a_single_quote(self):
        copy = self.quoted_dir / "fact.parquet"
        shutil.copyfile(PARQUET, copy)
        expected = self.q.connect().execute("SELECT COUNT(*) FROM budget").fetchone()[0]
        got = self.q.connect(copy).execute("SELECT COUNT(*) FROM budget").fetchone()[0]
        self.assertGreater(expected, 0)
        self.assertEqual(got, expected)

    def test_budget_stays_a_read_only_view(self):
        con = self.q.connect()
        kind = con.execute("SELECT table_type FROM information_schema.tables "
                           "WHERE table_name = 'budget'").fetchone()[0]
        self.assertEqual(kind, "VIEW")
        before = con.execute("SELECT COUNT(*) FROM budget").fetchone()[0]
        # EXPLAIN is an exempt first token; DML through it must still fail.
        code, out = self._quiet(self.q.run_statement, con,
                                "EXPLAIN ANALYZE DELETE FROM budget", [], "x")
        self.assertEqual(code, 2, out)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM budget").fetchone()[0], before)

    # ── DBDP-110 ──────────────────────────────────────────────────────────
    def test_report_slice_handles_quotes_in_path_and_vintage(self):
        import pandas as pd
        import query_budget as qb
        base_sheets, base_summary = self._quiet(qb.run_queries, PARQUET)[0]

        df = pd.read_parquet(PARQUET)
        vintage = base_summary["vintage"]
        quoted_vintage = vintage + "'x"
        df.loc[df["data_vintage"] == vintage, "data_vintage"] = quoted_vintage
        fixture = self.quoted_dir / "quoted.parquet"
        df.to_parquet(fixture, index=False)

        sheets, summary = self._quiet(qb.run_queries, fixture)[0]
        self.assertEqual(summary["vintage"], quoted_vintage)
        self.assertEqual(len(sheets["All Records"]), len(base_sheets["All Records"]))
        self.assertGreater(len(sheets["All Records"]), 0)

    # ── DBDP-97 ───────────────────────────────────────────────────────────
    COLS = ["line_item_title", "cost_fy2027", "source_file", "data_lifecycle_stage"]
    TYPES = ["VARCHAR", "DOUBLE", "VARCHAR[]", "VARCHAR"]

    def _write_csv(self, rows):
        path = Path(self.tmp.name) / "out.csv"
        ok, _ = self._quiet(self.q.shape_result, self.COLS, self.TYPES, rows,
                            "t", csv_path=str(path))
        self.assertTrue(ok)
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))[1:]

    def test_csv_neutralizes_formula_triggers_in_text(self):
        titles = ["=HYPERLINK(\"http://x\",\"y\")", "+1+1", "-2+3", "@SUM(A1)",
                  "\tTAB", "\rCR"]
        rows = [(t, 1.0, ["a.xml"], "Budget Request") for t in titles]
        out = self._write_csv(rows)
        self.assertEqual([r[0] for r in out], ["'" + t for t in titles])

    def test_csv_leaves_numbers_and_plain_text_alone(self):
        rows = [("Plain title", -12.5, ["a.xml"], "Budget Request"),
                ("Other", -7, ["b.xml"], "Budget Request"),
                ("Third", Decimal("-3.25"), ["c.xml"], "Budget Request"),
                (None, None, [], "Budget Request")]
        out = self._write_csv(rows)
        self.assertEqual([r[1] for r in out], ["-12.5", "-7", "-3.25", ""])
        self.assertEqual([r[0] for r in out], ["Plain title", "Other", "Third", ""])

    def test_csv_neutralizes_list_cells(self):
        out = self._write_csv([("t", 1.0, ["=bad.xml", "ok.xml"], "@stage")])
        self.assertEqual(out[0][2], "'=bad.xml; ok.xml")
        self.assertEqual(out[0][3], "'@stage")

    def test_console_renderer_is_unchanged(self):
        rows = [("=1+1", -5.0, ["a.xml"], "Budget Request")]
        ok, out = self._quiet(self.q.shape_result, self.COLS, self.TYPES, rows, "t")
        self.assertTrue(ok)
        self.assertIn(" =1+1 ", out)
        self.assertNotIn("'=1+1", out)
        self.assertIn("-5", out)

    def test_cli_csv_export_end_to_end(self):
        path = Path(self.tmp.name) / "cli.csv"
        # The dataset has no negative FY2027 lines, so negate a positive one:
        # a numeric cell starting with '-' must stay unprefixed.
        sql = ("SELECT '=1+1' AS line_item_title, -cost_fy2027 AS cost_fy2027, "
               "source_file, data_lifecycle_stage FROM budget "
               "WHERE cost_fy2027 > 0 ORDER BY record_id LIMIT 1")
        code, out = self._quiet(self.q.main, ["--sql", sql, "--csv", str(path)])
        self.assertEqual(code, 0, out)
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], self.COLS)
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual(rows[1][0], "'=1+1")
        self.assertRegex(rows[1][1], r"^-[0-9]", rows[1])


if __name__ == "__main__":
    unittest.main()
