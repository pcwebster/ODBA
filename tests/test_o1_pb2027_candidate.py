from copy import deepcopy
import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SIDE=ROOT/"data/o1/pb2027_candidate"
PILOT=ROOT/"data/o1/pb2027_health"
SPEC=importlib.util.spec_from_file_location("candidate",ROOT/"tools/build_o1_pb2027_candidate.py")
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def read(p):
    with p.open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))


class TestO1Candidate(unittest.TestCase):
    def setUp(self):
        self.rows=read(SIDE/"detail_candidate.csv")

    def test_scope_and_source(self):
        rows=self.rows
        self.assertEqual(len(rows),397)
        self.assertEqual(len({r["account_raw"] for r in rows}),31)
        self.assertEqual(sum(r["scope"]=="om_title" for r in rows),390)
        self.assertEqual(sum(r["scope"]=="indefinite_accounts" for r in rows),7)
        wk=[r for r in rows if r["source_kind"]=="workbook_mirror"]
        self.assertEqual(len(wk),395)
        self.assertEqual(sum(not r["organization_raw"] for r in wk),7)
        self.assertEqual(len({(r["account_raw"],r["activity_raw"],r["line_raw"]) for r in wk}),395)
        dup=[r for r in wk if r["account_raw"]=="3400F" and r["line_raw"]=="999"]
        self.assertEqual(len({r["activity_raw"] for r in dup}),2)

    def test_sign_blanks_and_official_additions(self):
        def only(a,l):
            [r]=[r for r in self.rows if r["account_raw"]==a and r["line_raw"]==l]
            return r
        self.assertEqual(only("5188D","140")["fy25_printed_actuals_lane"],"-24")
        self.assertEqual(only("5188D","140")["fy27_published_total"],"")
        for a,l,v in (("0833D","110","9"),("5286A","120","12")):
            r=only(a,l)
            self.assertEqual(r["fy25_printed_actuals_lane"],v)
            self.assertEqual(r["fy25_workbook_total"],"")
            self.assertEqual(r["classification_raw"],"U")
            self.assertEqual(r["fy26_published_total"],"")
        self.assertIsNone(M.int_cell(""))
        self.assertEqual(M.int_cell(0),0)

    def test_official_headlines(self):
        rows=read(SIDE/"headline_controls.csv")
        self.assertEqual(len(rows),42)
        self.assertEqual(sum(r["status"]=="blank_both" for r in rows),2)
        source=json.loads((SIDE/"provenance.json").read_text(encoding="utf-8"))
        columns=source["official_control_columns"]
        groups={scope: [r for r in self.rows if scope=="om_title_plus_indefinite"
                       or r["scope"]==scope] for scope in source["official_controls"]}
        controls=dict(source["official_controls"])
        for scope, control in source["military_department_controls"].items():
            groups[scope]=[r for r in self.rows if r["scope"]=="om_title"
                           and r["account_raw"] in control["accounts"]]
            controls[scope]=control["amounts"]
        audit={(r["scope"],r["source_column_key"]):r for r in rows}
        self.assertEqual(set(audit), {(scope, column) for scope in controls
                                     for column in columns})
        for scope, amounts in controls.items():
            for column, expected in zip(columns, amounts, strict=True):
                with self.subTest(scope=scope, column=column):
                    values=[int(r[column]) for r in groups[scope] if r[column]!=""]
                    observed=sum(values) if values else None
                    self.assertEqual(observed, expected)
                    row=audit[scope,column]
                    expected_text="" if expected is None else str(expected)
                    self.assertEqual(row["candidate_sum_usd_thousands"],
                                     "" if observed is None else str(observed))
                    self.assertEqual(row["official_amount_usd_thousands"],expected_text)
                    self.assertEqual(row["difference_usd_thousands"],
                                     "" if expected is None else "0")
                    self.assertEqual(row["status"],
                                     "blank_both" if expected is None else "matched_amount")
        key={(r["scope"],r["source_column_key"]):r["official_amount_usd_thousands"] for r in rows}
        self.assertEqual(key["om_title_plus_indefinite","fy27_published_total"],"430776786")
        self.assertEqual(key["om_title","fy26_pl11921_spend_plan"],"19991335")
        self.assertEqual(key["army_accounts","fy27_published_total"],"88581961")

    def test_all_printed_pdf_details_match(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        source=json.loads((SIDE/"provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(reference["columns"],source["official_control_columns"])
        self.assertEqual(len(reference["columns"]),7)
        self.assertEqual(len(reference["rows"]),397)
        self.assertEqual(sum(len(r["amounts"]) for r in reference["rows"]),397*7)
        self.assertEqual(reference["reported_amount_count"],1866)
        self.assertEqual(reference["blank_cell_count"],913)
        self.assertIsNone(M.verify_pdf_details(self.rows, reference))

    def test_pdf_identity_changes_rejected(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        af999=[i for i,r in enumerate(self.rows)
               if r["account_raw"]=="3400F" and r["line_raw"]=="999"]
        self.assertEqual(len(af999),2)
        self.assertNotEqual(self.rows[af999[0]]["activity_raw"],
                            self.rows[af999[1]]["activity_raw"])
        omitted=deepcopy(self.rows)
        omitted.pop(af999[0])
        extra=deepcopy(self.rows)
        unexpected=dict(extra[0],line_raw="998")
        extra.append(unexpected)
        replaced=deepcopy(self.rows)
        replaced[0]=unexpected
        repeated=deepcopy(self.rows)
        repeated[af999[0]]=dict(repeated[af999[1]])
        for name, rows in (("omitted_999_activity",omitted),("extra_detail",extra),
                           ("same_count_missing_and_extra",replaced),
                           ("repeated_999_activity",repeated)):
            with self.subTest(change=name), self.assertRaises(ValueError):
                M.verify_pdf_details(rows,reference)

    def test_pdf_sign_blank_and_lane_changes_rejected(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        negative=next(i for i,r in enumerate(self.rows)
                      if r["account_raw"]=="5188D" and r["line_raw"]=="140")
        sign=deepcopy(self.rows)
        sign[negative]["fy25_printed_actuals_lane"]="24"
        blank=deepcopy(self.rows)
        self.assertEqual(blank[negative]["fy27_published_total"],"")
        blank[negative]["fy27_published_total"]="0"
        swapped=deepcopy(self.rows)
        columns=("fy26_discretionary_enacted","fy26_pl11921_spend_plan")
        row=next(r for r in swapped if all(r[c]!="" for c in columns)
                 and r[columns[0]]!=r[columns[1]])
        row[columns[0]],row[columns[1]]=row[columns[1]],row[columns[0]]
        for name, rows in (("sign_lost",sign),("blank_changed_to_zero",blank),
                           ("fy26_lanes_swapped",swapped)):
            with self.subTest(change=name), self.assertRaises(ValueError):
                M.verify_pdf_details(rows,reference)

    def test_reported_zero_is_distinct_from_blank(self):
        reference=deepcopy(M.load_pdf_reference(SIDE/"provenance.json"))
        printed=next(r for r in reference["rows"] if r["activity"] is not None
                     and None in r["amounts"])
        index=printed["amounts"].index(None)
        rows=deepcopy(self.rows)
        [detail]=[r for r in rows if (r["account_raw"],r["activity_raw"],r["line_raw"])
                  ==(printed["account"],printed["activity"],printed["line"])]
        column=reference["columns"][index]
        self.assertEqual(detail[column],"")
        printed["amounts"][index]=0
        reference["reported_amount_count"]+=1
        reference["blank_cell_count"]-=1
        detail[column]="0"
        self.assertIsNone(M.verify_pdf_details(rows,reference))
        with self.assertRaises(ValueError):
            M.verify_pdf_details(self.rows,reference)

    def test_workbook_only_lanes_remain_separate(self):
        source=json.loads((SIDE/"provenance.json").read_text(encoding="utf-8"))
        native=("fy25_workbook_actuals","fy25_workbook_reconciliation","fy25_workbook_total")
        self.assertTrue(set(native).isdisjoint(source["official_control_columns"]))
        [row]=[r for r in self.rows if (r["account_raw"],r["activity_raw"],r["line_raw"])
               ==("2020A","01","210")]
        self.assertEqual(tuple(row[c] for c in native),("589505","7700","597205"))
        self.assertEqual(row["fy25_printed_actuals_lane"],"597205")
        pdf_only=[r for r in self.rows if r["source_kind"]=="official_pdf_indexed"]
        self.assertEqual(len(pdf_only),2)
        for row in pdf_only:
            with self.subTest(account=row["account_raw"]):
                self.assertTrue(all(row[c]=="" for c in native))

    def test_official_health_pilot_not_duplicated(self):
        pairs=zip(
            [("2025","actuals_as_reported"),("2026","discretionary_enacted"),
             ("2026","pl_119_21_spend_plan"),("2026","published_total"),
             ("2027","discretionary_requested"),("2027","mandatory_requested"),
             ("2027","published_total")],
            ["fy25_printed_actuals_lane","fy26_discretionary_enacted",
             "fy26_pl11921_spend_plan","fy26_published_total",
             "fy27_discretionary_request","fy27_mandatory_request","fy27_published_total"])
        keys=dict(pairs)
        health=read(PILOT/"observations.csv")
        self.assertEqual(len(health),182)
        for v in health:
            candidates=[r for r in self.rows if r["account_raw"]==v["appropriation_account"]
                        and (v["row_grain"]=="account_total" or r["activity_raw"]==v["budget_activity"])
                        and (v["row_grain"]!="detail" or r["line_raw"]==v["o1_line_code"])]
            if v["row_grain"]=="detail":
                self.assertEqual(len(candidates),1)
            k=keys[v["funding_fy"],v["source_column_key"]]
            a=M.sum_cell([int(r[k]) if r[k]!="" else None for r in candidates])
            self.assertEqual("" if a is None else str(a), v["amount"])

    def test_unpinned_workbook_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"wrong.xlsx"
            p.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                M.build(p,SIDE/"provenance.json")

    @unittest.skipUnless(os.environ.get("ODBA_PB27_O1_WORKBOOK"),"exact workbook not supplied")
    def test_regenerates(self):
        results=M.build(Path(os.environ["ODBA_PB27_O1_WORKBOOK"]),SIDE/"provenance.json")
        for f, value in results.items():
            self.assertEqual(value,(SIDE/f).read_bytes())


if __name__=="__main__":
    unittest.main()
