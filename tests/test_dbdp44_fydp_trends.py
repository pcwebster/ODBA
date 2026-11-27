"""DBDP-44: FYDP Trends sheet in the Excel report.

Builds the workbook from the committed parquet into a temp dir (never
output/) and checks the sheet against the records, the Summary sheet and
the committed consumption-layer long fact. Skips only when the report
dependencies or the committed parquet are missing.
"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "output" / "fact_budget_line_items.parquet"
LONG_FACT = ROOT / "output" / "consumption" / "fact_budget_long.csv"
HAVE_DEPS = all(importlib.util.find_spec(m) for m in ("duckdb", "openpyxl", "pandas"))
SKIP_REASON = ("needs duckdb, openpyxl and pandas (pip install -r requirements.txt) "
               "and output/fact_budget_line_items.parquet")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["OPENPYXL_LXML"] = "False"   # same pin as query_budget (DBDP-43)


@unittest.skipUnless(HAVE_DEPS and PARQUET.exists(), SKIP_REASON)
class FydpTrendsSheetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import query_budget as qb
        from openpyxl import load_workbook
        cls.qb = qb
        cls.sheets, cls.extra = qb.run_queries(qb.PARQUET_FILE)
        cls.fydp = cls.extra["fydp_trends"]
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "report.xlsx"
        qb.save_workbook_deterministic(qb.build_workbook(cls.sheets, cls.extra),
                                       cls.path, cls.extra["vintage"])
        cls.wb = load_workbook(cls.path)
        cls.ws = cls.wb[qb.FYDP_SHEET]
        cls.records = cls.sheets["All Records"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self):
        return list(self.ws.iter_rows(values_only=True))

    def text(self):
        return " ".join(v for r in self.rows() for v in r if isinstance(v, str))

    def test_is_ninth_sheet(self):
        self.assertEqual(len(self.wb.sheetnames), 9)
        self.assertEqual(self.wb.sheetnames[-1], "FYDP Trends")

    def section_rows(self, title):
        """Rows of the table under a section title, header first."""
        rows = self.rows()
        i = next(n for n, r in enumerate(rows) if r[0] == title) + 1
        out = []
        while i < len(rows) and rows[i][0] is not None:
            out.append(rows[i])
            i += 1
        return out

    def test_budget_request_label_on_sheet(self):
        """AR c10045: the sheet must say the figures are Budget Request data."""
        t = self.text()
        self.assertIn("Lifecycle Stage: Budget Request", t)
        self.assertIn("FY2027 President's Budget Request submission", t)

    def test_provenance_kept_apart_from_basis_model(self):
        """Review @ efceec0 finding 1: no blanket claim about what the amounts
        are; year roles are labelled as ODBA's model, not as source headings."""
        t = self.text()
        self.assertNotIn("None of it is enacted", t)
        self.assertNotIn("as printed in the request exhibits", t)
        self.assertIn("ODBA's amount-basis model", t)
        self.assertIn("not from the headings printed in each exhibit", t)
        self.assertIn("discretionary enacted", t)
        # year headers carry no basis word
        for fy, label in self.fydp["years"]:
            self.assertEqual(label, f"FY{fy} ($M)")
        # the x axis says the prior/current-year lanes are request columns
        with zipfile.ZipFile(self.path) as z:
            xml = z.read("xl/charts/chart1.xml").decode("utf-8")
        self.assertIn("prior- and current-year columns of the request", xml)

    def test_years_and_basis_labels_follow_consumption_rule(self):
        from etl_budget import amount_basis_for
        years = [fy for fy, _ in self.fydp["years"]]
        self.assertEqual(years, list(range(2025, 2032)))
        names = {"actual": "Actual", "estimate": "Estimate", "request": "Request",
                 "fydp_projection": "FYDP projection"}
        roles = dict(self.fydp["roles"].itertuples(index=False))
        for fy, _ in self.fydp["years"]:
            self.assertEqual(roles[f"FY{fy}"], names[amount_basis_for(fy, 2027)])
        self.assertEqual(self.section_rows("Year roles")[1:],
                         [(k, v) + (None,) * 7 for k, v in roles.items()])
        self.assertEqual(list(self.fydp["amounts"].columns),
                         ["Appropriation Type"] + [l for _, l in self.fydp["years"]])

    def test_appropriation_order(self):
        self.assertEqual(list(self.fydp["amounts"]["Appropriation Type"]),
                         ["O&M", "Procurement", "RDT&E", "DWCF", "DHP"])
        self.assertEqual(set(self.fydp["amounts"]["Appropriation Type"]),
                         set(self.records["appropriation_type"]))

    def test_amounts_and_counts_tie_to_records(self):
        df = self.records
        for (_, a), (_, c) in zip(self.fydp["amounts"].iterrows(),
                                  self.fydp["records"].iterrows()):
            sub = df[df["appropriation_type"] == a["Appropriation Type"]]
            self.assertEqual(c["Records"], len(sub))
            for fy, label in self.fydp["years"]:
                col = sub[f"cost_fy{fy}"].dropna().astype(float)
                self.assertEqual(c[f"FY{fy}"], len(col))
                if len(col) == 0:
                    self.assertIsNone(a[label], (a["Appropriation Type"], fy))
                else:
                    self.assertAlmostEqual(a[label], round(col.sum(), 1), places=6)

    def test_fy2027_ties_to_summary_sheet(self):
        summ = self.sheets["Summary"]
        for _, a in self.fydp["amounts"].iterrows():
            s = summ[summ["Appropriation Type"] == a["Appropriation Type"]]
            expect = float(s["FY2027 Request ($M)"].sum())
            got = a["FY2027 ($M)"]
            if got is None:
                self.assertEqual(expect, 0)        # Summary COALESCEs to 0
            else:
                self.assertLessEqual(abs(got - expect), 0.05 * len(s) + 0.05)

    @unittest.skipUnless(LONG_FACT.exists(), "consumption long fact not committed")
    def test_ties_to_consumption_long_fact(self):
        """Same totals and same basis as the canonical long fact (c10575)."""
        import pandas as pd
        long = pd.read_csv(LONG_FACT)
        long = long[(long["budget_year"] == 2027)
                    & (long["data_vintage"] == self.extra["vintage"])]
        m = long.merge(self.records[["record_id", "appropriation_type"]],
                       on="record_id", how="inner")
        self.assertEqual(len(m), len(long), "every FY2027 long row is in the slice")
        names = {"actual": "Actual", "estimate": "Estimate", "request": "Request",
                 "fydp_projection": "FYDP projection"}
        roles = dict(self.fydp["roles"].itertuples(index=False))
        for fy, _ in self.fydp["years"]:
            bases = set(m[m["funding_fy"] == fy]["amount_basis"])
            self.assertEqual({names[b] for b in bases}, {roles[f"FY{fy}"]})
        for _, a in self.fydp["amounts"].iterrows():
            for fy, label in self.fydp["years"]:
                sub = m[(m["appropriation_type"] == a["Appropriation Type"])
                        & (m["funding_fy"] == fy)]
                if a[label] is None:
                    self.assertEqual(len(sub), 0)
                else:
                    self.assertAlmostEqual(a[label], round(sub["amount_musd"].sum(), 1),
                                           places=6)

    def test_blank_is_not_zero(self):
        rows = {r[0]: r for r in self.section_rows("Funding by appropriation type")}
        dwcf = rows["DWCF"]
        self.assertTrue(all(v is None for v in dwcf[1:8]), dwcf)
        om = rows["O&M"]
        self.assertIsNotNone(om[3])          # FY2027 request present
        self.assertTrue(all(v is None for v in om[4:8]), om)   # no FY2028+ in OP-5

    def test_dhp_fy2027_coverage_break_flagged(self):
        """Review @ efceec0 finding 2: the DHP record that drops out in FY2027
        held about half of DHP's FY2026 total, so FY2027 is flagged."""
        b = self.fydp["breaks"]
        self.assertNotIn("Comparable with prior year", b.columns)
        self.assertEqual(set(b["Threshold status"]), {"Flagged", "Below threshold"})
        flagged = b[b["Threshold status"] == "Flagged"]
        self.assertEqual([tuple(r) for r in flagged[["Appropriation Type", "Year"]]
                          .itertuples(index=False)], [("DHP", "FY2027")])
        dhp = flagged.iloc[0]
        self.assertEqual(dhp["Records dropped (prior-year amount, none this year)"], 1)
        self.assertAlmostEqual(dhp["Share of type's prior-year total"], 0.5065, places=3)
        self.assertEqual(self.fydp["flagged"], [("DHP", "FY2027")])
        # every row's share agrees with the threshold
        for _, r in b.iterrows():
            self.assertEqual(r["Threshold status"] == "Flagged",
                             r["Share of type's prior-year total"] >= self.qb.FYDP_BREAK_SHARE)
        # and the table is on the sheet
        sheet = self.section_rows("Coverage breaks between years")
        self.assertIn(("DHP", "FY2027", 1), [r[:3] for r in sheet])

    def test_below_threshold_is_not_called_comparable(self):
        """Review @ 488c7cc: below threshold must not read as comparable."""
        b = self.fydp["breaks"].set_index(["Appropriation Type", "Year"])
        proc = b.loc[("Procurement", "FY2027")]
        self.assertEqual(proc["Threshold status"], "Below threshold")
        self.assertAlmostEqual(proc["Share of type's prior-year total"], 0.2243, places=3)
        sheet = self.section_rows("Coverage breaks between years")
        self.assertEqual(sheet[0][5], "Threshold status")
        self.assertNotIn("Yes", [r[5] for r in sheet[1:]])
        t = self.text()
        self.assertIn("Below threshold does not mean the years are comparable", t)
        self.assertNotIn("Comparable with prior year", t)
        self.assertNotIn("non-comparable", t)

    def test_dhp_break_recomputed_from_records(self):
        """The break comes from the data, not a hard-coded type."""
        df = self.records[self.records["appropriation_type"] == "DHP"]
        drop = df[df["cost_fy2026"].notna() & df["cost_fy2027"].isna()]
        share = drop["cost_fy2026"].sum() / df["cost_fy2026"].sum()
        self.assertEqual(len(drop), 1)
        self.assertGreaterEqual(share, self.qb.FYDP_BREAK_SHARE)
        # DBDP-132: the 0146D record is new in FY2027, so it is not a drop
        pscp = df[df["appropriation_code"] == "0146D"]
        self.assertEqual(len(pscp), 1)
        self.assertTrue(pscp["cost_fy2026"].isna().all())

    def test_table_keeps_summed_figure_and_chart_data_blanks_break(self):
        amounts = self.fydp["amounts"].set_index("Appropriation Type")
        chart = self.fydp["chart"].set_index("Appropriation Type")
        flagged = set(self.fydp["flagged"])
        # table unchanged: DHP FY2027 is still the summed figure, not zero/blank
        dhp27 = self.records[self.records["appropriation_type"] == "DHP"]["cost_fy2027"]
        self.assertAlmostEqual(amounts.at["DHP", "FY2027 ($M)"],
                               round(dhp27.dropna().sum(), 1), places=6)
        for typ in amounts.index:
            for fy, label in self.fydp["years"]:
                if (typ, f"FY{fy}") in flagged:
                    self.assertIsNone(chart.at[typ, label])
                else:
                    self.assertEqual(chart.at[typ, label], amounts.at[typ, label])
        sheet = {r[0]: r for r in self.section_rows(
            "Chart data (flagged points left blank)")}
        self.assertEqual(sheet["DHP"][1:4], (38916.5, 41011.9, None))
        main = {r[0]: r for r in self.section_rows("Funding by appropriation type")}
        self.assertEqual(main["DHP"][3], amounts.at["DHP", "FY2027 ($M)"])

    def test_chart_reads_chart_data_block(self):
        """Series point at the chart-data rows, so the DHP line stops at FY2026."""
        rows = self.rows()
        start = next(n for n, r in enumerate(rows)
                     if r[0] == "Chart data (flagged points left blank)") + 2
        with zipfile.ZipFile(self.path) as z:
            xml = z.read("xl/charts/chart1.xml").decode("utf-8")
        refs = re.findall(r"<(?:c:)?val><(?:c:)?numRef><(?:c:)?f>([^<]+)<", xml)
        self.assertEqual(len(refs), 4)
        for ref in refs:
            row = int(re.search(r"\$(\d+)$", ref).group(1))
            self.assertGreater(row, start)

    def test_chart_one_line_per_type_with_data_and_gaps(self):
        with zipfile.ZipFile(self.path) as z:
            charts = [n for n in z.namelist() if re.fullmatch(r"xl/charts/chart\d+\.xml", n)]
            self.assertEqual(len(charts), 1)
            xml = z.read(charts[0]).decode("utf-8")
        with_data = sum(1 for _, a in self.fydp["amounts"].iterrows()
                        if any(a[l] is not None for _, l in self.fydp["years"]))
        self.assertEqual(len(re.findall(r"<(?:c:)?ser>", xml)), with_data)
        self.assertEqual(with_data, 4)       # DWCF has no amounts
        self.assertRegex(xml, r'<(?:c:)?dispBlanksAs val="gap"')
        self.assertIn("President's Budget Request", xml)
        # categories are the year headers, read as text
        self.assertEqual(len(re.findall(r"<(?:c:)?cat><(?:c:)?strRef>", xml)), with_data)
        self.assertNotRegex(xml, r"<(?:c:)?cat><(?:c:)?numRef>")

    def test_dhp_transfer_note_visible_without_moving_chart_data(self):
        # DBDP-132 (c10763): account 0146 is now loaded, so the note says the
        # table includes it; the FY2027 DHP point stays off the chart because
        # the 0130 record still counts as a coverage break.
        expected = ("FY2027 DHP is left off the chart because, in the FY2027 "
                    "President's Budget request, Private Sector Care moved from "
                    "account 0130 to account 0146. The 0130 record carries FY2026 "
                    "but no FY2027 amount, which counts as a coverage break above. "
                    "The table's FY2027 DHP figure includes account 0146.")
        self.assertEqual(self.ws["A56"].value, expected)
        self.assertIn("A56:H56", {str(r) for r in self.ws.merged_cells.ranges})
        self.assertTrue(self.ws["A56"].alignment.wrap_text)
        self.assertGreaterEqual(self.ws.row_dimensions[56].height, 45)
        # 21,012.3 (0130D + SMR) + 22,175.5 (0146D) = 43,187.8 $M
        self.assertEqual(self.ws["D12"].value, 43187.8)
        self.assertIsNone(self.ws["D55"].value)
        self.assertEqual(self.ws._charts[0].series[-1].val.numRef.f,
                         "'FYDP Trends'!$B$55:$H$55")

    def test_no_wall_clock_values(self):
        import datetime as dt
        ts = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
        for row in self.rows():
            for v in row:
                self.assertNotIsInstance(v, (dt.datetime, dt.time))
                if isinstance(v, str):
                    self.assertIsNone(ts.search(v), v)


if __name__ == "__main__":
    unittest.main()
