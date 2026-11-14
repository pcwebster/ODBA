import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/o1/pb2027_health"
SPEC = importlib.util.spec_from_file_location("o1", ROOT / "tools/build_o1_pb2027_health.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestO1(unittest.TestCase):
    def setUp(self):
        self.source = BASE / "source_cells.json"
        self.files = MOD.build(self.source)

    def rows(self, name):
        return list(csv.DictReader(io.StringIO(self.files[name].decode())))

    def test_regenerates(self):
        for name, value in self.files.items():
            self.assertEqual(value, (BASE / name).read_bytes())

    def test_coverage_and_grains(self):
        r = self.rows("observations.csv")
        self.assertEqual(len(r), 182)
        self.assertEqual({x["row_grain"] for x in r},
                         {"detail", "activity_total", "account_total"})
        self.assertEqual(len({(x["funding_fy"],x["source_column_key"],x["appropriation_account"],
            x["budget_activity"],x["o1_line_code"],x["row_grain"]) for x in r}),182)

    def test_bridge_and_nulls(self):
        r = self.rows("observations.csv")
        with (BASE/"private_sector_care_bridge.csv").open() as f:
            [bridge] = list(csv.DictReader(f))
        def matching(side):
            return {x["source_column_key"] + x["funding_fy"]: x for x in r
                    if x["appropriation_account"] == bridge[side+"_account"]
                    and x["budget_activity"] == bridge[side+"_activity"]
                    and x["o1_line_code"] == bridge[side+"_o1_line"]
                    and x["detail_code"] == bridge[side+"_detail_code"]}
        src, dst = matching("from"), matching("to")
        self.assertEqual(src["discretionary_enacted2026"]["amount"],"20773888")
        self.assertEqual(dst["discretionary_requested2027"]["amount"],"22175472")
        self.assertEqual(src["published_total2027"]["value_status"],"not_reported")
        self.assertEqual(dst["pl_119_21_spend_plan2026"]["amount"],"")
        self.assertEqual(dst["mandatory_requested2027"]["value_status"],"not_reported")

    def test_all_applicable_totals(self):
        r = self.rows("reconciliation.csv")
        self.assertEqual(len(r),74)
        self.assertEqual({x["difference_usd_thousands"] for x in r},{"0"})
        self.assertIsNone(MOD.amount(""))
        self.assertEqual(MOD.amount("0"),0)

    def test_modified_amount_rejected(self):
        source = json.loads(self.source.read_text(encoding="utf-8"))
        source["pages"][0]["rows"][2][2][2] = "10,294,477"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"mod.json"
            p.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"failed check"):
                MOD.build(p)


if __name__ == "__main__":
    unittest.main()
