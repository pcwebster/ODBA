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
        self.assertEqual(len(rows), 760)
        self.assertEqual({r["source_year_status"] for r in rows}, {"Historical"})
        self.assertEqual({r["reconciliation_status"] for r in rows},
                         {"Within rounding tolerance"})
        self.assertEqual({int(r["funding_fy"]) for r in rows}, set(range(1948, 2024)))
        for year in ("2003", "2011"):
            with self.subTest(restored_nominal_year=year):
                self.assertEqual(len([r for r in rows if r["funding_fy"] == year
                                      and r["dollar_basis"] == "Current"]), 5)

    def test_all_totals_reconcile(self):
        rows = self.read("reconciliation.csv")
        self.assertEqual(len(rows), 164)
        deltas = {(int(r["funding_fy"]), r["dollar_basis"]):
                  int(r["difference_usd_m"]) for r in rows}
        self.assertEqual(set(deltas), {(year, basis) for year in range(1948, 2030)
                                     for basis in ("Current", "Constant FY2025")})
        for row in rows:
            with self.subTest(year=row["funding_fy"], basis=row["dollar_basis"]):
                delta = int(row["component_sum_usd_m"]) - int(row["published_total_usd_m"])
                self.assertEqual(int(row["difference_usd_m"]), delta)
                self.assertLessEqual(abs(delta), 2)
                self.assertEqual(row["reconciliation_status"], "Within rounding tolerance")
        self.assertEqual({year: deltas[year, "Current"] for year in (2003, 2011, 2029)},
                         {2003: 0, 2011: -1, 2029: 1})

    def test_corrected_nominal_values(self):
        values = {(int(r["funding_fy"]), r["military_department"], r["dollar_basis"]):
                  int(r["budget_authority"]) for r in self.read("budget_authority.csv")}
        expected = {(2003, "DoD total", "Current"): 437801,
                    (2011, "Defense-Wide", "Current"): 110407,
                    (2029, "Navy", "Current"): 282471}
        for key, amount in expected.items():
            with self.subTest(key=key):
                self.assertEqual(values[key], amount)

    def test_transcription_regressions_fail(self):
        source = SOURCE / "table_6_10_indexed.json"
        for year, label, amount in ((2003, "Total Current Dollars", "437,301"),
                                    (2011, "Defense-Wide", "115,407"),
                                    (2029, "Navy", "282,474")):
            payload = json.loads(source.read_text(encoding="utf-8"))
            for page in payload["pages"]:
                headers = page["header"].split("|")
                if f"FY {year}" not in [h.strip() for h in headers[1:]]:
                    continue
                col = [h.strip() for h in headers].index(f"FY {year}")
                for i, row in enumerate(page["rows"][:5]):
                    fields = row.split("|")
                    if fields[0].strip() == label:
                        fields[col] = f" {amount} "
                        page["rows"][i] = "|".join(fields)
                        break
                break
            with self.subTest(year=year), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "fixture.json"
                p.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Unexpected reconciliation exceptions"):
                    MODULE.build(p)

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
