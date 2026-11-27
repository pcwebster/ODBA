"""DBDP-132: MHS account 0146D, Private Sector Care Program (PB27).

Implements design c10751 as revised by c10763 (OpenAI APPROVE c10771;
Peter's decision c10774: store the J-Book line 020 as printed and crosswalk
it to the consolidated O-1 line 010).

The fixture is a small hand-built SpreadsheetML file with the same shape as
MHS_PB27_J-Book-Vol1-COMP_PSCP.xml: the 0130D O-1 rows, the 0130 Part C
transfer text, the merged O-1 text cell that holds the 0146D line, and the
PSCP OP-5 Parts A and B. It is not the source file; the exact-bytes check
stays with the DBDP-73 integrity gate and the full-ETL replay.

The line-code crosswalk and the amount reconciliation are separate tests
(c10763 finding 3).
"""
import csv
import importlib.util
import io
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "output" / "fact_budget_line_items.parquet"
HEALTH = ROOT / "data" / "o1" / "pb2027_health"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import etl_budget as etl  # noqa: E402

NBSP = "\xa0"
SOURCE = etl.MHS_PSCP_SOURCE
PINNED = {SOURCE: {"sha256": etl.MHS_PSCP_SHA256, "budget_year": 2027}}

# Values as printed in the PB27 Vol 1 J-Book ($K).
COMP_ROWS = [  # line, title, FY25 actuals, FY26 enacted, FY27 request
    ("010", "In-House Care", "10,294,476", "10,735,135", "10,863,317"),
    ("020", "Private Sector Care", "20,201,022", "20,773,888", "-"),
]
O1_LINE = ("0146D     020     PRIVATE SECTOR CARE PROGRAM"
           "                -        -        -        -     22,175,472"
           "        -     22,175,472")
TOTAL_LINE = ("TOTAL, BA 01:  OPERATION & MAINTENANCE"
              "        -        -        -        -     22,175,472"
              "        -     22,175,472")
PART_A = [
    ("1. Pharmaceuticals Purchased Health Care", "1950895"),
    ("2. National Retail Pharmacy", "1994922"),
    ("3. Managed Care Support Contracts", "8818935"),
    ("4, MTF Enrollee Purchased Care", "3174102"),   # printed with a comma
    ("5. Dental Purchased Care", "297714"),
    ("6. Uniformed Services Family Health Prog", "691627"),
    ("7. Supplemental Care - Health Care", "2271162"),
    ("8. Supplemental Care - Dental", "130795"),
    ("9. Continuing Health Education/Capitaliz", "390487"),
    ("10. Overseas Purchased Health Care", "586792"),
    ("11. Miscellaneous Purchased Health Care", "1752266"),
    ("12. Miscellaneous Support Activities", "115775"),
]
PART_A_TOTAL = "22175472"
PART_B = [("BASELINE FUNDING", "0"), ("Price Changes", "0"),
          ("Functional Transfers", "21581449"), ("Program Changes", "594,023"),
          ("CURRENT ESTIMATE", "22175472")]
PART_C = ("a) Increases $0 b) Decreases $0 Revised FY 2026 Estimate $20,773,888 "
          "FY 2026 Normalized Current Estimate $20,773,888 6. Price Change "
          "$807,561 7. Functional Transfers ($21,581,449) a) Transfers In $0 "
          "b) Transfers Out ($21,581,449) 1) Establishment of PSCP "
          "Appropriation ($21,581,449) The FY 2027 President's Budget "
          "establishes the PSCP appropriation.")

FY27_K = 22175472
RECORD_ID = "c0bd6256fca229039395"   # make_id(SOURCE, "0146D", "020")


def _cell(index, text, merge=None):
    attrs = f' ss:Index="{index}"'
    if merge:
        attrs += f' ss:MergeAcross="{merge}"'
    return (f"<Cell{attrs}><Data ss:Type=\"String\">{escape(text)}</Data>"
            f"</Cell>")


def _row(*cells):
    return "<Row>" + "".join(cells) + "</Row>"


def build_fixture(path, *, o1_lines=None, extra_o1_cell=False, part_a=None,
                  part_a_total=PART_A_TOTAL, part_b=None, part_c=PART_C,
                  comp_rows=None):
    """Write a Vol 1-shaped SpreadsheetML file; keyword args break one fact."""
    if o1_lines is None:
        o1_lines = [O1_LINE, TOTAL_LINE]
    o1_text = "\n".join(
        [f"BUDGET{NBSP}ACTIVITY{NBSP}01:{NBSP}{NBSP}OPERATION{NBSP}&{NBSP}"
         f"MAINTENANCE"] + o1_lines + ["Note:", "1. Private Sector Care moved "
                                       "from account 0130 to account 0146."])
    rows = [_row(_cell(1, "0130D"), _cell(4, line), _cell(7, title),
                 _cell(26, fy25), _cell(32, fy26), _cell(59, fy27))
            for line, title, fy25, fy26, fy27 in (comp_rows or COMP_ROWS)]
    rows.append(_row(_cell(1, part_c, merge=85)))
    rows.append(_row(_cell(1, o1_text, merge=85)))
    if extra_o1_cell:
        rows.append(_row(_cell(1, o1_text, merge=85)))
    rows.append(_row(_cell(1, "A. BA Subactivities"), _cell(23, "FY 2025 Actuals"),
                     _cell(76, "FY 2027 Request")))
    for label, value in (part_a or PART_A):
        rows.append(_row(_cell(1, label), _cell(23, "0"), _cell(76, value)))
    rows.append(_row(_cell(1, "Total"), _cell(23, "0"), _cell(76, part_a_total)))
    rows.append(_row(_cell(1, "Note: 1. FY27 Request excludes other funding.")))
    rows.append(_row(_cell(1, "B. Reconciliation Summary"),
                     _cell(41, "Change FY 2026/FY 2026"),
                     _cell(56, "Change FY 2026/FY 2027")))
    for label, value in (part_b or PART_B):
        rows.append(_row(_cell(1, label), _cell(56, value)))
    xml = ('<?xml version="1.0"?>\n'
           '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
           'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
           '<Worksheet ss:Name="O-1"><Table>' + "".join(rows) +
           "</Table></Worksheet></Workbook>")
    Path(path).write_text(xml, encoding="utf-8")
    return Path(path)


class _FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        etl.MHS_PSCP_CONTROLS.clear()
        self.addCleanup(etl.MHS_PSCP_CONTROLS.clear)

    def fixture(self, name=SOURCE, **broken):
        return build_fixture(Path(self.tmp.name) / name, **broken)

    def parse(self, path, manifest=PINNED):
        out = io.StringIO()
        with redirect_stdout(out):
            records = etl.parse_mhs_xml(str(path), manifest)
        return records, out.getvalue()

    def extract(self, path):
        """The extractor alone, with the 0130D records parsed from the file."""
        rows = etl._mhs_get_rows(str(path))
        comp, _ = self.parse(path, manifest=None)
        return etl._extract_mhs_pscp_0146d(rows, path.name, comp)


class ExtractTests(_FixtureCase):

    def test_one_0146d_record_as_printed(self):
        records, _ = self.parse(self.fixture())
        pscp = [r for r in records if r["appropriation_code"] == "0146D"]
        self.assertEqual(len(pscp), 1)
        r = pscp[0]
        self.assertEqual(r["budget_sub_activity_number"], "020")
        self.assertEqual(r["budget_sub_activity_title"], "PRIVATE SECTOR CARE PROGRAM")
        self.assertEqual(r["appropriation_name"], "Private Sector Care Program")
        self.assertEqual((r["appropriation_type"], r["exhibit_type"]),
                         ("DHP", "DHP-J-Book"))
        self.assertEqual(r["budget_activity_number"], "01")
        self.assertEqual(r["_by_slots"], [22175.472, None, None, None, None])
        self.assertEqual(r["source_file"], SOURCE)

    def test_dashes_stay_blank_not_zero(self):
        records, _ = self.parse(self.fixture())
        [r] = [r for r in records if r["appropriation_code"] == "0146D"]
        self.assertIsNone(r["cost_prior_year"])
        self.assertIsNone(r["cost_current_year"])
        etl.map_year_slots([r], PINNED)
        self.assertEqual(r["cost_fy2027"], 22175.472)
        for col in ("cost_fy2025", "cost_fy2026"):
            self.assertIsNone(r.get(col), col)

    def test_0130d_rows_unchanged(self):
        records, _ = self.parse(self.fixture())
        comp = [r for r in records if r["appropriation_code"] == "0130D"]
        self.assertEqual([r["budget_sub_activity_number"] for r in comp],
                         ["010", "020"])
        psc = comp[1]
        self.assertIsNone(psc["_by_slots"][0])   # 0130D 020 FY2027 stays blank
        self.assertEqual(psc["cost_current_year"], 20773.888)

    def test_record_id_is_content_only_and_stable(self):
        first, _ = self.parse(self.fixture())
        second, _ = self.parse(self.fixture())
        self.assertEqual(first, second)
        [r] = [r for r in first if r["appropriation_code"] == "0146D"]
        self.assertEqual(r["record_id"], etl.make_id(SOURCE, "0146D", "020"))
        self.assertEqual(r["record_id"], RECORD_ID)
        ids = [r["record_id"] for r in first]
        self.assertEqual(len(ids), len(set(ids)))


class CrosswalkTests(unittest.TestCase):
    """Line codes only (c10763 finding 3): J-Book 0146D/020 = O-1 0146D/010."""

    def test_crosswalk_maps_jbook_020_to_o1_010(self):
        self.assertEqual(etl.MHS_PSCP_LINE_CROSSWALK,
                         {("0146D", "020"): ("0146D", "010")})

    def test_crosswalk_matches_committed_bridge_target(self):
        with (HEALTH / "private_sector_care_bridge.csv").open(newline="") as f:
            [bridge] = list(csv.DictReader(f))
        target = (bridge["to_account"], bridge["to_o1_line"])
        self.assertEqual(etl.MHS_PSCP_LINE_CROSSWALK[("0146D", "020")], target)

    def test_line_number_alone_is_ambiguous(self):
        # 0130D also has a line 020 (its historical Private Sector Care line),
        # so the crosswalk is keyed by account AND line, and 0130D is absent.
        self.assertNotIn(("0130D", "020"), etl.MHS_PSCP_LINE_CROSSWALK)
        self.assertTrue(all(len(k) == 2 and k[0] == "0146D"
                            for k in etl.MHS_PSCP_LINE_CROSSWALK))


class ReconciliationTests(_FixtureCase):
    """Amounts only (c10763 finding 3)."""

    def test_controls_tie_to_the_request(self):
        _, controls = self.extract(self.fixture())
        self.assertEqual(controls["o1_amounts_k"]["FY 2027 Request"], FY27_K)
        self.assertTrue(controls["total_ba01_matches"])
        self.assertEqual(controls["op5_subactivities"], 12)
        self.assertEqual(controls["op5_sum_k"], FY27_K)
        self.assertEqual(controls["op5_total_k"], FY27_K)
        b = controls["part_b_k"]
        self.assertEqual(b["baseline"] + b["price"] + b["transfers"] + b["program"],
                         b["current"])
        self.assertEqual(b["current"], FY27_K)
        c = controls["part_c_k"]
        self.assertEqual(c["normalized_estimate"] + c["price"], c["transfer_out"])
        self.assertEqual(c["transfer_out"], b["transfers"])
        self.assertEqual(c["normalized_estimate"], 20773888)  # 0130D 020 FY2026

    def test_matches_committed_consolidated_o1(self):
        _, controls = self.extract(self.fixture())
        with (HEALTH / "observations.csv").open(newline="") as f:
            obs = [r for r in csv.DictReader(f)
                   if (r["appropriation_account"], r["o1_line_code"],
                       r["row_grain"], r["funding_fy"]) == ("0146D", "010",
                                                            "detail", "2027")]
        request = {r["source_column_key"]: r["amount"] for r in obs}
        self.assertEqual(int(request["discretionary_requested"]),
                         controls["o1_amounts_k"]["FY 2027 Request"])
        self.assertEqual(request["mandatory_requested"], "")
        self.assertIsNone(controls["o1_amounts_k"]["FY 2027 Mandatory Request"])


class HardStopTests(_FixtureCase):
    """Each broken fact stops the pinned source (c10763 finding 1)."""

    BROKEN = {
        "no 0146D line": dict(o1_lines=[TOTAL_LINE]),
        "two 0146D lines": dict(extra_o1_cell=True),
        "six amount tokens": dict(o1_lines=[O1_LINE.replace("        -", "", 1),
                                            TOTAL_LINE]),
        "eight amount tokens": dict(o1_lines=[O1_LINE + "        -", TOTAL_LINE]),
        "TOTAL BA 01 differs": dict(o1_lines=[O1_LINE, TOTAL_LINE.replace(
            "22,175,472", "22,175,473", 1)]),
        "no TOTAL BA 01": dict(o1_lines=[O1_LINE]),
        "OP-5 row changed": dict(part_a=PART_A[:-1] + [(PART_A[-1][0], "115776")]),
        "OP-5 total changed": dict(part_a_total="22175473"),
        "Part B current changed": dict(part_b=PART_B[:-1] + [("CURRENT ESTIMATE",
                                                              "22175473")]),
        "Part B row missing": dict(part_b=PART_B[1:]),
        "Part C price changed": dict(part_c=PART_C.replace("$807,561", "$807,562")),
        "Part C missing": dict(part_c="No transfer text here."),
        "0130D 020 FY2026 changed": dict(comp_rows=[
            COMP_ROWS[0], ("020", "Private Sector Care", "20,201,022",
                           "20,773,889", "-")]),
    }

    def test_extractor_raises(self):
        for name, broken in self.BROKEN.items():
            with self.subTest(name):
                with self.assertRaises(etl.PscpControlError):
                    self.extract(self.fixture(**broken))

    def test_parse_exits_on_pinned_source(self):
        for name, broken in self.BROKEN.items():
            with self.subTest(name):
                with self.assertRaises(SystemExit) as cm:
                    self.parse(self.fixture(**broken))
                self.assertEqual(cm.exception.code, 1)


class ScopeTests(_FixtureCase):
    """The 0146D step runs only for the pinned name AND manifest sha256."""

    def assert_no_0146d(self, records):
        self.assertEqual([r for r in records if r["appropriation_code"] == "0146D"],
                         [])
        self.assertEqual(etl.MHS_PSCP_CONTROLS, {})

    def test_other_vintage_is_parsed_as_before(self):
        name = "MHS_PB26_J-Book-Vol1-COMP_PSCP.xml"
        path = self.fixture(name, o1_lines=[TOTAL_LINE])   # broken, yet no stop
        records, out = self.parse(path, manifest={name: PINNED[SOURCE]})
        self.assert_no_0146d(records)
        self.assertEqual(len(records), 2)
        self.assertNotIn("DBDP-132", out)

    def test_pinned_name_other_sha_skips_with_warning(self):
        path = self.fixture(o1_lines=[TOTAL_LINE])        # broken, yet no stop
        manifest = {SOURCE: {"sha256": "0" * 64, "budget_year": 2027}}
        records, out = self.parse(path, manifest=manifest)
        self.assert_no_0146d(records)
        self.assertIn("[WARN] DBDP-132", out)

    def test_no_manifest_skips(self):
        records, _ = self.parse(self.fixture(), manifest=None)
        self.assert_no_0146d(records)

    def test_controls_reset_per_pinned_parse(self):
        self.parse(self.fixture())
        self.assertEqual(etl.MHS_PSCP_CONTROLS["source_file"], SOURCE)
        self.parse(self.fixture("MHS_PB26_J-Book-Vol1-COMP_PSCP.xml"),
                   manifest={"MHS_PB26_J-Book-Vol1-COMP_PSCP.xml": PINNED[SOURCE]})
        self.assertEqual(etl.MHS_PSCP_CONTROLS["source_file"], SOURCE)


def _have_parquet():
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return PARQUET.exists()


@unittest.skipUnless(_have_parquet(),
                     "needs pyarrow and output/fact_budget_line_items.parquet")
class PostRunCheckTests(_FixtureCase):
    """check_mhs_pscp: the post-run assertion main() runs, on the committed
    parquet plus the fixture's record (one executable path)."""

    def frame(self, with_record=True, **override):
        import pandas as pd
        base = pd.read_parquet(PARQUET)
        base = base[base["appropriation_code"] != "0146D"]
        records, _ = self.parse(self.fixture())
        [r] = [r for r in records if r["appropriation_code"] == "0146D"]
        etl.map_year_slots([r], PINNED)
        r.update(override)
        if not with_record:
            return base
        with warnings.catch_warnings():   # all-NA columns in the one new row
            warnings.simplefilter("ignore", FutureWarning)
            return pd.concat([base, pd.DataFrame([r])[list(base.columns)]],
                             ignore_index=True)

    def test_passes_with_the_record(self):
        df = self.frame()
        self.assertEqual(etl.check_mhs_pscp(df, etl.MHS_PSCP_CONTROLS), [])

    def test_fails_without_the_record(self):
        df = self.frame(with_record=False)
        fails = etl.check_mhs_pscp(df, etl.MHS_PSCP_CONTROLS)
        self.assertIn("expected 1 0146D record, found 0", fails)

    def test_fails_when_a_dash_becomes_zero(self):
        df = self.frame(cost_current_year=0.0)
        fails = etl.check_mhs_pscp(df, etl.MHS_PSCP_CONTROLS)
        self.assertTrue(any("cost_current_year" in f for f in fails), fails)

    def test_replay_helper_accepts_one_added_row_only(self):
        import shutil
        spec = importlib.util.spec_from_file_location(
            "dbdp132_replay_check", ROOT / "tools" / "dbdp132_replay_check.py")
        replay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(replay)
        dirs = {k: Path(self.tmp.name) / k for k in ("base", "branch", "rerun", "bad")}
        for d in dirs.values():
            d.mkdir()
        self.frame(with_record=False).to_parquet(dirs["base"] / PARQUET.name)
        self.frame().to_parquet(dirs["branch"] / PARQUET.name)
        shutil.copy(dirs["branch"] / PARQUET.name, dirs["rerun"] / PARQUET.name)
        self.assertEqual(replay.check(dirs["base"], dirs["branch"], dirs["rerun"]), [])
        bad = self.frame()
        bad.loc[0, "line_item_title"] = "changed"
        bad.to_parquet(dirs["bad"] / PARQUET.name)
        fails = replay.check(dirs["base"], dirs["bad"], dirs["rerun"])
        self.assertTrue(any("existing rows changed" in f for f in fails), fails)
        self.assertTrue(any("not byte-identical" in f for f in fails), fails)

    def test_fails_without_controls(self):
        df = self.frame()
        self.assertEqual(etl.check_mhs_pscp(df, {}),
                         ["pinned source parsed but the 0146D controls did not run"])


if __name__ == "__main__":
    unittest.main()
