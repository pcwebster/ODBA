import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "green_book", ROOT / "tools/build_green_book_fy2025.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SOURCE = ROOT / "data/green_book/fy2025"


class TestGreenBook(unittest.TestCase):
    def setUp(self):
        self.files = MODULE.build(SOURCE / "table_6_10_indexed.json")

    def read(self, name):
        return list(csv.DictReader(io.StringIO(self.files[name])))

    def test_exact_reproduction(self):
        for name, content in self.files.items():
            self.assertEqual(content.encode(), (SOURCE / name).read_bytes())

    def test_known_values(self):
        rows = self.read("budget_authority.csv")
        values = {(r["funding_fy"], r["military_department"], r["dollar_basis"]):
                  int(r["budget_authority"]) for r in rows}
        self.assertEqual(len(rows), 820)
        self.assertEqual(len(values), 820)
        self.assertEqual(values["1948", "Army", "Current"], 2840)
        self.assertEqual(values["1948", "DoD total", "Constant FY2025"], 247005)
        self.assertEqual(values["1991", "Defense-Wide", "Current"], -10636)
        self.assertEqual(values["2025", "DoD total", "Current"], 872126)

    def test_historical_view(self):
        rows = self.read("historical_qa_passed.csv")
        self.assertEqual(len(rows), 750)
        self.assertEqual({r["source_year_status"] for r in rows}, {"Historical"})
        self.assertEqual({r["reconciliation_status"] for r in rows},
                         {"Within rounding tolerance"})
        self.assertEqual({int(r["funding_fy"]) for r in rows}, set(range(1948, 2024)))

    def test_expected_discrepancies(self):
        rows = self.read("reconciliation.csv")
        self.assertEqual(len(rows), 164)
        exceptions = {(int(r["funding_fy"]), r["dollar_basis"]):
                      int(r["difference_usd_m"]) for r in rows
                      if r["reconciliation_status"] == "Review exception"}
        self.assertEqual(exceptions, {(2003, "Current"): 500,
                                      (2011, "Current"): 4999,
                                      (2029, "Current"): 4})

    def test_missing_page_and_changed_totals_fail(self):
        source = SOURCE / "table_6_10_indexed.json"
        for change in ("page", "amount"):
            payload = json.loads(source.read_text(encoding="utf-8"))
            if change == "page":
                payload["pages"].pop()
            else:
                row = payload["pages"][0]["rows"][0]
                payload["pages"][0]["rows"][0] = row.replace("2,840", "2,850", 1)
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "fixture.json"
                p.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.build(p)


if __name__ == "__main__":
    unittest.main()
