"""Integrity and optional exact-source regeneration of the PB27 R-1 sidecar."""
from collections import Counter
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import build_r1_pb2027 as r1


SOURCE = os.environ.get("ODBA_PB27_R1_PDF")


def csv_rows(filename):
    with (r1.DEFAULT / filename).open(encoding="utf-8", newline="") as data:
        return list(csv.DictReader(data))


def identity(record):
    return tuple(record[field] for field in r1.DETAIL_KEY)


def amounts(record):
    return tuple(int(record[field]) if record[field] != "" else None for field in r1.LANES)


def nullable_sum(values):
    numbers = [number for number in values if number is not None]
    return sum(numbers) if numbers else None


class PB27R1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inside = csv_rows(r1.NAMES[0])
        cls.outside = csv_rows(r1.NAMES[1])
        cls.occurrences = csv_rows(r1.NAMES[2])
        cls.controls = csv_rows(r1.NAMES[3])
        cls.rows = cls.inside + cls.outside
        cls.by_id = {identity(row): row for row in cls.rows}
        cls.provenance = json.loads((r1.DEFAULT / r1.NAMES[4]).read_text(encoding="utf-8"))

    def test_source_pin_and_artifact_integrity(self):
        p = self.provenance
        self.assertEqual(p["source_role"], "publisher_pdf")
        self.assertEqual(p["sha256"], r1.EXPECTED_HASH)
        self.assertEqual(p["source_url"], r1.OFFICIAL)
        self.assertEqual((p["submission_edition"], p["submission_fy"]), ("PB27", 2027))
        self.assertEqual(tuple(p["identity"]), r1.DETAIL_KEY)
        for name in r1.NAMES[:4]:
            self.assertEqual(sha256((r1.DEFAULT / name).read_bytes()).hexdigest(),
                             p["sidecar_artifact_sha256"][name], name)

    def test_distinct_as_printed_funding_bases(self):
        lanes = self.provenance["funding_lanes"]
        self.assertEqual([item["field"] for item in lanes], list(r1.LANES))
        self.assertEqual([item["funding_fy"] for item in lanes], [2025, 2026, 2026, 2026, 2027, 2027, 2027])
        self.assertEqual([item["basis"] for item in lanes], [
            "historical_toa_as_reported", "discretionary_enacted", "pl11921_spend_plan",
            "published_total", "discretionary_request", "mandatory_request", "published_total",
        ])
        self.assertEqual([item["funding_fy"] for item in lanes if item["is_published_total"]], [2026, 2027])
        self.assertEqual(sum(v is None for row in self.rows for v in amounts(row)), 3060)
        self.assertEqual(r1.numeric_columns("   0             -2", 0, (4, 12, 19)), (0, None, -2))

    def test_scope_and_occurrence_coverage(self):
        self.assertEqual((len(self.inside), len(self.outside), len(self.by_id)), (1148, 15, 1163))
        self.assertEqual({x["scope"] for x in self.inside}, {"rdte_title"})
        self.assertEqual({x["scope"] for x in self.outside}, {"outside_rdte_title"})
        self.assertEqual({x["appropriation"] for x in self.outside}, {"0107D", "0130D", "0390D"})
        counts = Counter(identity(row) for row in self.occurrences)
        self.assertEqual(set(counts), set(self.by_id))
        self.assertEqual((len(self.occurrences), sum(n-1 for n in counts.values())), (1452, 289))
        self.assertEqual({key[1] for key, n in counts.items() if n > 1}, {"0400D"})
        self.assertEqual({x["role"] for x in self.occurrences}, {"non_additive_source_occurrence"})
        self.assertEqual(len({(identity(o), o["physical_pdf_page"]) for o in self.occurrences}), 1452)
        for o in self.occurrences:
            self.assertEqual(int(o["printed_page"]) + 5, int(o["physical_pdf_page"]))
            self.assertEqual(o["scope"], self.by_id[identity(o)]["scope"])
        self.assertEqual(len(self.occurrences) * len(r1.LANES),
                         self.provenance["coverage"]["verified_nullable_occurrence_positions"])

    def test_repeat_pe_reuse_and_literal_ids(self):
        key = ("PB27", "0400D", "07", "309", "1160483BB")
        self.assertEqual(amounts(self.by_id[key]), (194828, 126047, 180813, 306860, 351721, None, 351721))
        repeat = [x for x in self.occurrences if identity(x) == key]
        self.assertEqual([x["printed_page"] for x in repeat], ["77", "113"])
        self.assertEqual([x["physical_pdf_page"] for x in repeat], ["82", "118"])
        distinct = [self.by_id["PB27", "3007D", activity, line, "1204159D8Z"]
                    for activity, line in (("03", "16"), ("07", "19"))]
        self.assertEqual([amounts(x)[2] for x in distinct], [10623800, 132000])
        placeholders = [x for x in self.inside if x["appropriation"] == "0400D" and x["printed_line"] == "999"]
        self.assertGreater(len(placeholders), 1)
        self.assertEqual(len(placeholders), len({x["budget_activity"] for x in placeholders}))
        self.assertEqual(
            [x["printed_page"] for x in self.occurrences if x["program_element"] == "0901517X"], ["116"])
        self.assertNotIn("0901517x", {x["program_element"] for x in self.rows})

    def test_control_total_and_nullability_reconciliation(self):
        self.assertEqual(Counter(c["control_grain"] for c in self.controls),
                         {"appropriation": 10, "scope_total": 2})
        self.assertEqual({c["role"] for c in self.controls}, {"non_additive_published_control"})
        for control in self.controls:
            self.assertEqual((control["printed_page"], control["physical_pdf_page"]), ("1", "6"))
            candidates = [r for r in self.rows if r["scope"] == control["scope"] and
                          (control["control_grain"] == "scope_total" or
                           r["appropriation"] == control["control_code"])]
            actual = tuple(nullable_sum(lane) for lane in zip(*(amounts(r) for r in candidates)))
            self.assertEqual(actual, amounts(control), control["control_code"])
        by_code = {c["control_code"]: c for c in self.controls}
        self.assertEqual(amounts(by_code["rdte_title_total"]),
                         (143345996, 144922309, 65462721, 210385030, 218791608, 124897313, 343688921))
        self.assertEqual(amounts(by_code["outside_title_total"]),
                         (2452098, 2687376, None, 2687376, 1076840, None, 1076840))

    def test_digest_mismatch_fails_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "wrong.pdf"
            src.write_bytes(b"wrong bytes")
            dest = Path(td) / "not-created"
            with self.assertRaisesRegex(ValueError, "Unexpected PB27 publisher PDF fingerprint"):
                r1.build(src, dest)
            self.assertFalse(dest.exists())

    @unittest.skipUnless(SOURCE, "ODBA_PB27_R1_PDF not supplied")
    def test_exact_source_regeneration(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            built = r1.build(Path(SOURCE), dest)
            self.assertEqual(built, self.provenance)
            for name in r1.NAMES:
                self.assertEqual((dest / name).read_bytes(), (r1.DEFAULT / name).read_bytes(), name)


    @unittest.skipUnless(SOURCE, "ODBA_PB27_R1_PDF not supplied")
    def test_geometry_check_rejects_an_altered_cell(self):
        payload = r1.read(Path(SOURCE))
        first = payload["detail"][0]
        first["amount_k"] = (first["amount_k"][0] + 1, *first["amount_k"][1:])
        with self.assertRaisesRegex(ValueError, "Unexpected occurrence or amount mismatch"):
            r1.check_coordinates(Path(SOURCE), payload)
