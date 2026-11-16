import csv
import io
import unittest
from pathlib import Path

from build_o1_explorer import COMMIT, DEFAULT_SCOPE, build_evidence, money

SNAPSHOT = Path(__file__).parent / "snapshot"


def load(relative):
    return (SNAPSHOT / relative).read_bytes()


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_evidence(load)
        cls.detail = cls.payload["detail"]
        cls.controls = {(r["scope"], r["lane"]): r for r in cls.payload["controls"]}

    def test_certified_scope_and_source_commit(self):
        self.assertEqual(self.payload["repoCommit"], COMMIT)
        self.assertEqual(self.payload["defaultFY"], 2025)
        self.assertEqual(self.payload["defaultScope"], DEFAULT_SCOPE)
        self.assertEqual(len(self.detail), 1238)
        self.assertEqual(len(self.controls), 125)
        self.assertEqual(sum(v["publishedCellCount"] for v in self.payload["provenance"].values()), 6930)
        self.assertEqual(len({row["id"] for row in self.detail}), len(self.detail))

    def test_milestones_and_other_stages_kept_apart(self):
        self.assertEqual(
            [self.controls[DEFAULT_SCOPE, key]["amount"] for key in self.payload["defaultMilestones"]],
            [338_098_474, 342_358_161, 350_101_702],
        )
        self.assertEqual(self.controls[DEFAULT_SCOPE, "pb26.fy25_enacted"]["amount"], 338_459_009)
        self.assertEqual(self.controls[DEFAULT_SCOPE, "pb26.fy25_supplemental"]["amount"], 3_940_452)
        self.assertEqual(self.controls[DEFAULT_SCOPE, "pb26.fy26_reconciliation_request"]["amount"], 22_708_023)
        self.assertEqual(self.controls[DEFAULT_SCOPE, "pb27.fy26_pl11921_spend_plan"]["amount"], 19_991_335)
        self.assertNotIn(("defense_wide_accounts", "pb27.fy25_printed_actuals_lane"), self.controls)

    def test_nonadditive_and_real_zero(self):
        triplets = [r for r in self.detail if "pb26_fy25_nonadditive" in r["qaFlags"]]
        self.assertEqual(len(triplets), 6)
        self.assertEqual(sum(r["amounts"]["pb26.fy25_published_total"] for r in triplets), 41_300)
        for row in triplets:
            self.assertEqual(row["page"], 55)
            self.assertEqual(row["amounts"]["pb26.fy25_enacted"], row["amounts"]["pb26.fy25_supplemental"])
        self.assertEqual(money("0"), 0)
        self.assertIsNone(money(""))
        self.assertTrue(any(-1_288_238 in r["amounts"].values() for r in self.detail))
        self.assertIsNone(self.controls["miscellaneous_accounts", "pb25.fy25_request"]["amount"])

    def test_page_anchors_pdf_only_labels_and_collisions(self):
        for row in self.detail:
            self.assertEqual(row["pdfPage"] - row["page"], 4 if row["vintage"] == "pb25" else 5)
            self.assertTrue(row["url"].endswith("#page=" + str(row["pdfPage"])))
        for control in self.controls.values():
            self.assertTrue(control["url"].endswith("#page=" + str(control["pdfPage"])))
        self.assertEqual(len([r for r in self.detail if r["title"] is None]), 2)
        for vintage in ("pb25", "pb27"):
            colliding = [r for r in self.detail if r["vintage"] == vintage and
                         (r["account"], r["line"]) == ("3400F", "999")]
            self.assertEqual(len(colliding), 2)
            self.assertEqual(len({r["ba"] for r in colliding}), 2)

    def test_rejects_tampered_source_cells_and_scope(self):
        target = "data/o1/pb2025_candidate/detail_candidate.csv"
        for field, altered, error in [
            ("fy25_request", "0", "official monetary cells mismatch"),
            ("scope", "indefinite_accounts", "incomplete grouped account coverage|control mismatch"),
        ]:
            def changed(relative):
                raw = load(relative)
                if relative != target:
                    return raw
                rows = list(csv.DictReader(io.StringIO(raw.decode())))
                rows[0][field] = altered
                out = io.StringIO()
                writer = csv.DictWriter(out, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
                return out.getvalue().encode()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                build_evidence(changed)


if __name__ == "__main__":
    unittest.main()
