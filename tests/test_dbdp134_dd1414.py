"""DBDP-134: FY2026 DD 1414 enacted base (design c10752/c10764/c10775, v5 c10824).

Three layers:
* unit and synthetic-PDF tests, which need only the pinned readers (pdfminer.six and Poppler);
* integrity tests on the committed sidecar under data/dd1414/fy2026/;
* the full-source rebuild, run when ODBA_FY26_DD1414_PDF names the pinned original.
"""
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tests import dd1414_synthetic as P

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "data/dd1414/fy2026"
GOLD = ROOT / "tests/fixtures/dd1414_fy2026_gold.json"
SOURCE = os.environ.get("ODBA_FY26_DD1414_PDF")

try:
    from tools import dd1414_read as R
    from tools import dd1414_grammar as G
    from tools import dd1414_strike as S
    from tools import build_dd1414_fy2026 as B
    READERS = shutil.which("pdftotext") and shutil.which("pdftohtml") and shutil.which("pdftoppm")
    MISSING = "" if READERS else "Poppler is not installed"
except ImportError as error:            # pdfminer.six or numpy missing
    R = G = S = B = None
    MISSING = f"reader dependencies missing: {error}"

RED, BLACK = (1, 0, 0), (0, 0, 0)


def rows(name):
    with (SIDECAR / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@unittest.skipIf(R is None, MISSING)
class UnitTest(unittest.TestCase):
    def test_colour_formulas(self):
        self.assertEqual(R.colour_hex("DeviceRGB", (1, 0, 0)), ("FF0000", True))
        self.assertEqual(R.colour_hex("DeviceGray", (0,)), ("000000", True))
        self.assertEqual(R.colour_hex("DeviceCMYK", (0, 1, 1, 0)), ("FF0000", True))
        self.assertEqual(R.colour_hex("Separation", (0.5,)), ("", False))

    def test_half_even_rounding(self):
        self.assertEqual(R.q2(0.125), 0.12)
        self.assertEqual(R.q2(0.135), 0.14)
        self.assertEqual(R.q2(-11.9906), -11.99)

    def test_record_id_is_content_only(self):
        key = ("DD1414", "2026", "2040A", "2026/2027", "", "05", "line", "", "0605345A", "UAS")
        self.assertEqual(B.record_id(key), B.record_id(tuple(key)))
        self.assertNotEqual(B.record_id(key), B.record_id(key[:-1] + ("UAS ",)))
        self.assertRegex(B.record_id(key), r"^dd1414-fy26-[0-9a-f]{20}$")

    def test_pdftohtml_frame_is_truncated_then_shifted(self):
        run = R.Run("1", 10, 100.0, 20, 108.0, "000000", "Arial", 8)
        page = {"width": 791.0, "height": 611.0, "runs": [run]}
        self.assertEqual(B.html_to_crop(page, 791.9996, 611.9998), "")
        self.assertAlmostEqual(run.y0, 100.9998, places=6)
        self.assertIn("truncated", B.html_to_crop({"width": 792.0, "height": 611.0, "runs": []}, 791.9996, 611.9998))


@unittest.skipIf(MISSING, MISSING or "")
class SyntheticPdfTest(unittest.TestCase):
    """c10824 sections A and C on hand-written PDFs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, pages):
        path = self.tmp / "t.pdf"
        path.write_bytes(P.pdf_bytes(pages))
        return path

    def outcomes(self, content):
        path = self.write([{"content": content}])
        page = R.read_pdfminer(path)[0]
        marks, rules = S.page_marks(page)
        pixels = R.render_page(path, 1, self.tmp)
        return {t.text: S.classify(t, marks, rules, [], pixels, 792)[0] for t in G.tokens_of(page)}

    def test_colour_is_read_by_all_three_readers(self):
        path = self.write([{"content": P.text(100, 700, "184,631", RED) + P.text(200, 700, "172,898", BLACK)}])
        glyphs = R.read_pdfminer(path)[0].glyphs
        self.assertEqual({g.hex for g in glyphs if g.text == "8"}, {"FF0000", "000000"})
        runs = {r.text: r.hex for r in R.read_html_runs(path)[0]["runs"]}
        self.assertEqual(runs, {"184,631": "FF0000", "172,898": "000000"})
        words = R.read_bbox_words(path)[0]["words"]
        self.assertEqual(sorted(w.text for w in words), ["172,898", "184,631"])

    def test_coloured_strike_over_black_text_is_struck(self):
        got = self.outcomes(P.text(100, 700, "3,000") + P.line(98, 140, 703.5, RED)
                            + P.text(200, 700, "4,000") + P.bar(198, 240, 703.5, RED))
        self.assertEqual(got, {"3,000": "struck", "4,000": "struck"})

    def test_strike_in_the_text_colour_is_ambiguous(self):
        got = self.outcomes(P.text(100, 700, "172,898") + P.line(98, 140, 703.5)
                            + P.text(200, 700, "184,631", RED) + P.line(198, 240, 703.5, RED))
        self.assertEqual(got, {"172,898": "ambiguous", "184,631": "ambiguous"})

    def test_partial_strike_is_ambiguous(self):
        self.assertEqual(self.outcomes(P.text(100, 700, "172,898") + P.line(98, 118, 703.5, RED)),
                         {"172,898": "ambiguous"})

    def test_rules_and_underlines_are_not_strikes(self):
        got = self.outcomes(P.text(100, 700, "1,000") + P.line(98, 130, 698.5)          # underline
                            + P.text(200, 700, "2,000") + P.line(40, 560, 710)            # rule above the row
                            + P.text(300, 700, "-444") + P.text(400, 700, "-44"))         # minus and crossbar
        self.assertEqual(set(got.values()), {"not_struck"})

    def test_nonzero_origin_frames_agree(self):
        box = (-11.9906, 11.9622, 780.009, 623.962)      # the data-page boxes of the FY26 edition
        path = self.write([{"content": P.text(200, 400, "184,631", RED), "media": box}])
        page = R.read_pdfminer(path)[0]
        word = R.read_bbox_words(path)[0]
        html = R.read_html_runs(path)[0]
        w, h = box[2] - box[0], box[3] - box[1]
        self.assertAlmostEqual(word["width"], w, places=2)
        self.assertEqual(html["width"], math.floor(w))
        self.assertEqual(B.html_to_crop(html, w, h), "")
        g = min(page.glyphs, key=lambda g: g.x0)
        self.assertAlmostEqual(g.ox, 200 - box[0], places=3)
        for other in (word["words"][0], html["runs"][0]):
            self.assertLessEqual(abs(other.x0 - g.x0), B.READER_TOL)
            self.assertLessEqual(abs(other.y0 - min(x.y0 for x in page.glyphs)), B.READER_TOL)
        self.assertEqual(R.render_page(path, 1, self.tmp).shape[0], round(h * S.DPI / 72))

    def test_data_page_with_cropbox_unlike_mediabox_stops(self):
        content = P.text(50, 600, "Appropriation Account Title:") + P.text(50, 580, "Fiscal Year Program")
        path = self.write([{"content": content, "media": (0, 0, 800, 700), "crop": (20, 30, 700, 650)},
                           {"content": P.text(50, 600, "TABLE OF CONTENTS"), "media": (0, 0, 612, 792),
                            "crop": (10, 10, 600, 780)}])
        stops = B.Stops()
        classes, odd = B.classify_pages(R.read_pdfminer(path), stops)
        self.assertEqual(classes, {1: "data", 2: "contents"})
        self.assertTrue(any("CropBox differs" in s for s in stops.items))
        self.assertIn(2, odd)


class SidecarIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = rows("baseline_lines.csv")
        cls.adjustments = rows("adjustments.csv")
        cls.controls = rows("published_controls.csv")
        cls.provenance = json.loads((SIDECAR / "provenance.json").read_text(encoding="utf-8"))

    def test_output_hashes_match_provenance(self):
        for name, digest in self.provenance["outputs"].items():
            self.assertEqual(hashlib.sha256((SIDECAR / name).read_bytes()).hexdigest(), digest, name)
        for name, digest in self.provenance["inputs"].items():
            self.assertEqual(hashlib.sha256((SIDECAR / name).read_bytes()).hexdigest(), digest, name)

    def test_record_ids_unique_and_parents_exist(self):
        ids = [r["record_id"] for r in self.lines + self.adjustments + self.controls]
        self.assertEqual([k for k, n in Counter(ids).items() if n > 1], [])
        line_ids = {r["record_id"] for r in self.lines}
        additive = {r["record_id"] for r in self.lines if r["is_additive"] == "true"}
        self.assertTrue(all(a["parent_record_id"] in additive for a in self.adjustments))
        self.assertTrue(all(r["parent_record_id"] in line_ids for r in self.lines if r["parent_record_id"]))

    def test_amounts_are_integers_or_blank(self):
        for r in self.lines + self.controls:
            for lane in B.LANE_COLUMNS if B else [k for k in r if k.startswith("lane_")]:
                self.assertRegex(r[lane], r"^(-?[1-9][0-9]*|0|)$")

    def test_every_line_ties(self):
        sums = Counter()
        for a in self.adjustments:
            sums[a["parent_record_id"]] += int(a["amount_lane_g"] or 0)
        for r in self.lines:
            if r["is_additive"] != "true":
                continue
            self.assertEqual(int(r["lane_g"] or 0), sums[r["record_id"]], r["record_id"])

    def test_blank_repeat_is_left_out(self):
        cvn = [r for r in self.lines if r["page_code"] == "N-29" and r["title_norm"] == "CVN Refueling Overhauls"]
        self.assertEqual(len(cvn), 1)
        repeats = self.provenance["repeated_blank_lines"]
        self.assertEqual([(e["id"], e["page_code"]) for e in repeats], [("N29-1", "N-29")])

    def test_gold_sample(self):
        gold = json.loads(GOLD.read_text(encoding="utf-8"))
        files = {"baseline_lines.csv": self.lines, "published_controls.csv": self.controls}
        for g in gold["records"]:
            match = {k: v for k, v in g.items() if k not in ("file", "expect")}
            hit = [r for r in files[g["file"]] if all(r[k] == v for k, v in match.items())]
            self.assertEqual(len(hit), 1, match)
            self.assertEqual({k: hit[0][k] for k in g["expect"]}, g["expect"], match)

    def test_navy_m1_cross_publication(self):
        gold = json.loads(GOLD.read_text(encoding="utf-8"))
        files = {"baseline_lines.csv": self.lines, "published_controls.csv": self.controls}
        entries = gold["cross_publication"]
        self.assertEqual([e["id"] for e in entries], ["M1-N"])
        for e in entries:
            c = e["compare"]
            hit = [r for r in files[c["file"]] if r["page_code"] == c["page_code"] and r["title_norm"] == c["title_norm"]]
            self.assertEqual(len(hit), 1)
            self.assertEqual(int(hit[0][c["lane"]]), e["value"])


@unittest.skipIf(B is None, MISSING)
class InputRegistryTest(unittest.TestCase):
    """OpenAI review of PR #30, item 1: a repeated entry must not shadow another."""

    def setUp(self):
        self.exceptions = json.loads((SIDECAR / B.EDIT_EXCEPTIONS).read_text(encoding="utf-8"))
        self.differences = json.loads((SIDECAR / B.PUBLISHED_DIFFERENCES).read_text(encoding="utf-8"))

    def stops(self):
        stops = B.Stops()
        B.check_inputs(self.exceptions, self.differences, stops)
        return stops.items

    def test_committed_inputs_are_clean(self):
        self.assertEqual(self.stops(), [])
        dw54 = {(d["control_title"], d["lane"]) for d in self.differences["entries"] if d["page_code"] == "DW-54"}
        self.assertEqual(len(dw54), 4)

    def test_wrong_entry_shadowed_by_a_correct_one_stops(self):
        right = self.differences["entries"][0]
        wrong = dict(right, id=right["id"] + "x", printed=right["printed"] + 1)
        self.differences["entries"].insert(0, wrong)
        self.assertTrue(any("appears 2 times" in s for s in self.stops()))

    def test_repeated_id_stops(self):
        self.differences["entries"].append(dict(self.differences["entries"][1], id=self.differences["entries"][0]["id"],
                                                lane="x"))
        self.assertTrue(any("id" in s and "appears 2 times" in s for s in self.stops()))
        self.setUp()
        self.exceptions["diagnostics"].append(dict(self.exceptions["diagnostics"][0], lane="c"))
        self.assertTrue(any("appears 2 times" in s for s in self.stops()))

    def test_repeated_edit_entry_stops(self):
        self.exceptions["entries"].append(dict(self.exceptions["entries"][0], id="A58-1b"))
        self.assertTrue(any("entry" in s and "appears 2 times" in s for s in self.stops()))


@unittest.skipUnless(SOURCE and MISSING == "", "set ODBA_FY26_DD1414_PDF to the pinned original")
class FullSourceTest(unittest.TestCase):
    """Check 8 and the A-58 proofs on the original."""

    @classmethod
    def setUpClass(cls):
        cls.build, cls.files = B.build(SOURCE, SIDECAR)

    def test_no_stops_and_byte_identical(self):
        self.assertEqual(self.build.stops.items, [])
        for name, data in self.files.items():
            self.assertEqual((SIDECAR / name).read_bytes(), data, name)

    def test_only_a58_is_struck_and_false_positives_stay_clear(self):
        strikes = self.build.strike_records
        self.assertEqual({s["page_code"] for s in strikes}, {"A-58"})
        self.assertEqual(len(strikes), 12)
        for number, text in ((203, "-444"), (292, "-44")):
            tokens = [t for t in self.build.tokens[number] if t.text == text]
            self.assertTrue(tokens)
            self.assertEqual({t.strike for t in tokens}, {"not_struck"})

    def test_a58_first_printed(self):
        first = {f["line_identifier"]: f for f in self.build.first_printed if f["page_code"] == "A-58"}
        self.assertEqual(first["0605345A"]["first_printed"]["g"], 357529)
        self.assertEqual(first["0605345A"]["owned"]["i"], 184631)
        self.assertEqual(first["0605346A"]["first_printed"], {"c": None, "e": None, "g": None, "i": None})
        self.assertEqual(first["0605346A"]["owned"]["g"], 172898)


if __name__ == "__main__":
    unittest.main()
