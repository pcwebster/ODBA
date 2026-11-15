from copy import deepcopy
import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SIDE=ROOT/"data/o1/pb2025_candidate"
SPEC=importlib.util.spec_from_file_location("pb25",ROOT/"tools/build_o1_pb2025_candidate.py")
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def read(name):
    with (SIDE/name).open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))


class TestO1PB25(unittest.TestCase):
    def test_coverage_native_lanes_and_nulls(self):
        r=read("detail_candidate.csv")
        self.assertEqual(len(r),434)
        self.assertEqual(len({x["account_raw"] for x in r}),31)
        self.assertEqual(sum(x["scope"]=="om_title" for x in r),427)
        self.assertEqual(sum(x["scope"]=="indefinite_accounts" for x in r),7)
        self.assertEqual(sum(not x["organization_raw"] for x in r),8)
        self.assertEqual(len({(x["account_raw"],x["activity_raw"],x["line_raw"]) for x in r}),434)
        af=[x for x in r if x["account_raw"]=="3400F" and x["line_raw"]=="999"]
        self.assertEqual(len({x["activity_raw"] for x in af}),2)
        flat=[x[c] for x in r for c in M.COLUMNS]
        self.assertEqual((len(flat),flat.count(""),sum(v!="" and int(v)<0 for v in flat)),(1302,200,15))
        self.assertIsNone(M.int_cell(""))
        self.assertEqual(M.int_cell(0),0)

    def test_published_edge_cases(self):
        r=read("detail_candidate.csv")
        def lookup(a,l):
            [x]=[x for x in r if x["account_raw"]==a and x["line_raw"]==l]
            return x
        adj=lookup("0100D","490")
        self.assertEqual([adj[c] for c in M.COLUMNS],["","-1288238",""])
        self.assertEqual(adj["subactivity_raw"],"CR24")
        contrib=lookup("5751D","010")
        self.assertEqual([contrib[c] for c in M.COLUMNS],["3731","",""])
        self.assertEqual(contrib["subactivity_raw"],lookup("0134D","010")["subactivity_raw"])
        variant=lookup("0838D","170")
        self.assertEqual(variant["line_title_workbook"],"Adj to Match Continuing Resolution")
        self.assertEqual(variant["official_indexed_line_title"],"Support for International Sporting Competitions, Defense")
        self.assertEqual(variant["official_indexed_check_page"],"66")
        self.assertEqual(variant["line_title_printed"],
                         "Support for International Sporting Competitions , Defense")
        self.assertNotEqual(variant["line_title_printed"],variant["official_indexed_line_title"])
        self.assertEqual(variant["pdf_printed_page"],"66")

    def test_headline_controls(self):
        r=read("headline_controls.csv")
        self.assertEqual(len(r),27)
        self.assertEqual(sum(x["status"]=="blank_both" for x in r),1)
        source=json.loads((SIDE/"provenance.json").read_text(encoding="utf-8"))
        details=read("detail_candidate.csv")
        groups={scope:[x for x in details if scope=="om_title_plus_indefinite"
                      or x["scope"]==scope] for scope in source["official_controls"]}
        controls=dict(source["official_controls"])
        for metadata_key in ("military_department_controls","other_controls"):
            for scope,control in source[metadata_key].items():
                groups[scope]=[x for x in details if x["scope"]=="om_title"
                               and x["account_raw"] in control["accounts"]]
                controls[scope]=control["amounts"]
        audit={(x["scope"],x["source_column_key"]):x for x in r}
        self.assertEqual(set(audit),{(scope,column) for scope in controls for column in M.COLUMNS})
        for scope,amounts in controls.items():
            for column,expected in zip(M.COLUMNS,amounts,strict=True):
                with self.subTest(scope=scope,column=column):
                    values=[int(x[column]) for x in groups[scope] if x[column]!=""]
                    observed=sum(values) if values else None
                    self.assertEqual(observed,expected)
                    row=audit[scope,column]
                    self.assertEqual(row["computed"],"" if observed is None else str(observed))
                    self.assertEqual(row["official_reported"],"" if expected is None else str(expected))
                    self.assertEqual(row["difference_usd_thousands"],"" if expected is None else "0")
                    self.assertEqual(row["status"],"blank_both" if expected is None else "matched_amount")
        v={(x["scope"],x["source_column_key"]):x["official_reported"] for x in r}
        self.assertEqual(v["om_title_plus_indefinite","fy25_request"],"338098474")
        self.assertEqual(v["defense_wide_accounts","fy24_pb_request_cr_adjusted"],"91820622")
        self.assertEqual(v["transfer_accounts","fy23_actuals_as_reported"],"170")

    def test_full_printed_pdf_reference(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        self.assertEqual(reference["columns"],list(M.COLUMNS))
        self.assertEqual(reference["printed_pages_scanned"],list(range(1,68)))
        self.assertEqual(reference["physical_pdf_pages_scanned"],list(range(5,72)))
        self.assertEqual(len(reference["rows"]),434)
        self.assertEqual(sum(len(x["amounts"]) for x in reference["rows"]),1302)
        self.assertEqual(reference["reported_amount_count"],1102)
        self.assertEqual(reference["blank_cell_count"],200)
        self.assertIsNone(M.verify_pdf_details(read("detail_candidate.csv"),reference))

    def test_pdf_missing_extra_substituted_and_duplicate_rows_rejected(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        rows=read("detail_candidate.csv")
        missing=deepcopy(rows[:-1])
        unexpected=dict(rows[0],line_raw="998")
        extra=deepcopy(rows)+[unexpected]
        substituted=deepcopy(rows)
        substituted[0]=unexpected
        duplicated=deepcopy(rows)
        duplicated[1]=dict(duplicated[0])
        for name,mutated in (("missing",missing),("extra",extra),
                             ("same_count_substituted",substituted),("duplicate",duplicated)):
            with self.subTest(change=name),self.assertRaises(ValueError):
                M.verify_pdf_details(mutated,reference)

    def test_shared_bli_accounts_and_adjustment_activities_stay_distinct(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        rows=read("detail_candidate.csv")
        i=next(i for i,x in enumerate(rows) if x["account_raw"]=="5751D" and x["line_raw"]=="010")
        j=next(i for i,x in enumerate(rows) if x["account_raw"]=="0134D" and x["line_raw"]=="010")
        self.assertEqual(rows[i]["subactivity_raw"],"1PL3")
        self.assertEqual(rows[j]["subactivity_raw"],"1PL3")
        self.assertEqual(rows[i]["fy23_actuals_as_reported"],"3731")
        self.assertEqual(rows[j]["fy23_actuals_as_reported"],"351598")
        swapped=deepcopy(rows)
        for column in M.COLUMNS:
            swapped[i][column],swapped[j][column]=swapped[j][column],swapped[i][column]
        collapsed=deepcopy(rows)
        collapsed[i]["account_raw"]=collapsed[j]["account_raw"]
        adjustment=deepcopy(rows)
        af=[i for i,x in enumerate(adjustment) if x["account_raw"]=="3400F" and x["line_raw"]=="999"]
        self.assertEqual(len(af),2)
        self.assertEqual({adjustment[i]["activity_raw"] for i in af},{"01","04"})
        adjustment[af[0]]=dict(adjustment[af[1]])
        for name,mutated in (("shared_bli_amounts_swapped",swapped),
                             ("shared_bli_accounts_collapsed",collapsed),
                             ("activity_qualified_999_collapsed",adjustment)):
            with self.subTest(change=name),self.assertRaises(ValueError):
                M.verify_pdf_details(mutated,reference)

    def test_signs_blanks_and_three_fiscal_lanes_are_preserved(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        rows=read("detail_candidate.csv")
        self.assertEqual(M.COLUMNS,("fy23_actuals_as_reported","fy24_pb_request_cr_adjusted","fy25_request"))
        negative={(x["account_raw"],x["activity_raw"],x["line_raw"],column):int(x[column])
                  for x in rows for column in M.COLUMNS if x[column]!="" and int(x[column])<0}
        expected={
            ("2020A","04","560","fy23_actuals_as_reported"):-93827,
            ("2020A","20","600","fy24_pb_request_cr_adjusted"):-739807,
            ("2080A","20","210","fy24_pb_request_cr_adjusted"):-424514,
            ("2065A","20","230","fy24_pb_request_cr_adjusted"):-383917,
            ("1804N","20","820","fy24_pb_request_cr_adjusted"):-4058432,
            ("1106N","20","320","fy24_pb_request_cr_adjusted"):-424994,
            ("1806N","20","180","fy24_pb_request_cr_adjusted"):-102760,
            ("3400F","20","490","fy24_pb_request_cr_adjusted"):-2584108,
            ("3410F","20","140","fy24_pb_request_cr_adjusted"):-939342,
            ("3740F","20","130","fy24_pb_request_cr_adjusted"):-415456,
            ("0100D","20","490","fy24_pb_request_cr_adjusted"):-1288238,
            ("0107D","20","050","fy24_pb_request_cr_adjusted"):-40006,
            ("0104D","20","020","fy24_pb_request_cr_adjusted"):-617,
            ("0833D","04","190","fy23_actuals_as_reported"):-133,
            ("0833D","07","200","fy23_actuals_as_reported"):-12705,
        }
        self.assertEqual(negative,expected)
        for (account,activity,line,column),amount in negative.items():
            changed=deepcopy(rows)
            next(x for x in changed if (x["account_raw"],x["activity_raw"],x["line_raw"])
                 ==(account,activity,line))[column]=str(-amount)
            with self.subTest(sign=(account,activity,line,column)),self.assertRaises(ValueError):
                M.verify_pdf_details(changed,reference)
        blank=deepcopy(rows)
        next(x for x in blank if x["fy25_request"]=="")["fy25_request"]="0"
        with self.subTest(change="blank_to_zero"),self.assertRaises(ValueError):
            M.verify_pdf_details(blank,reference)
        for first,second in ((0,1),(0,2),(1,2)):
            changed=deepcopy(rows)
            a,b=M.COLUMNS[first],M.COLUMNS[second]
            target=next(x for x in changed if x[a]!="" and x[b]!="" and x[a]!=x[b])
            target[a],target[b]=target[b],target[a]
            with self.subTest(swapped_lanes=(a,b)),self.assertRaises(ValueError):
                M.verify_pdf_details(changed,reference)

    def test_reported_zero_distinct_from_blank(self):
        reference=deepcopy(M.load_pdf_reference(SIDE/"provenance.json"))
        printed=next(x for x in reference["rows"] if x["activity"] is not None
                     and x["line"] is not None and None in x["amounts"])
        column_index=printed["amounts"].index(None)
        rows=read("detail_candidate.csv")
        [detail]=[x for x in rows if (x["account_raw"],x["activity_raw"],x["line_raw"])
                  ==(printed["account"],printed["activity"],printed["line"])]
        column=reference["columns"][column_index]
        self.assertEqual(detail[column],"")
        detail[column]="0"
        printed["amounts"][column_index]=0
        reference["reported_amount_count"]+=1
        reference["blank_cell_count"]-=1
        self.assertIsNone(M.verify_pdf_details(rows,reference))
        with self.assertRaises(ValueError):
            M.verify_pdf_details(read("detail_candidate.csv"),reference)

    def test_printed_label_does_not_overwrite_workbook_variant(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        rows=read("detail_candidate.csv")
        target=next(x for x in rows if x["account_raw"]=="0838D" and x["line_raw"]=="170")
        self.assertEqual(target["line_title_workbook"],"Adj to Match Continuing Resolution")
        self.assertEqual(target["line_title_printed"],"Support for International Sporting Competitions , Defense")
        for other_label in (target["line_title_workbook"],target["official_indexed_line_title"]):
            with self.subTest(replaced_printed_label=other_label):
                target["line_title_printed"]=other_label
                with self.assertRaises(ValueError):
                    M.verify_pdf_details(rows,reference)

    def test_pdf_reference_hash_and_binary_binding_fail_closed(self):
        original=json.loads((SIDE/"provenance.json").read_text(encoding="utf-8"))
        name=original["pdf_reference_file"]
        raw=(SIDE/name).read_bytes()
        for change in ("reference_bytes","binary_hash"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                dest=Path(tmp)
                meta=deepcopy(original)
                (dest/name).write_bytes(raw+b" " if change=="reference_bytes" else raw)
                if change=="binary_hash":
                    meta["pdf_sha256"]="0"*64
                source=dest/"provenance.json"
                source.write_text(json.dumps(meta),encoding="utf-8")
                with self.assertRaises(ValueError):
                    M.load_pdf_reference(source)

    def test_wrong_workbook_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"fake.xlsx"
            f.write_bytes(b"fake")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                M.build(f,SIDE/"provenance.json")

    @unittest.skipUnless(os.getenv("ODBA_PB25_O1_WORKBOOK"),"exact workbook not supplied")
    def test_regenerate(self):
        w=Path(os.environ["ODBA_PB25_O1_WORKBOOK"])
        for name,payload in M.build(w,SIDE/"provenance.json").items():
            self.assertEqual(payload,(SIDE/name).read_bytes())

    @unittest.skipUnless(os.getenv("ODBA_PB25_O1_WORKBOOK"),"exact workbook not supplied")
    def test_mutated_footnote_or_control_is_rejected(self):
        w=Path(os.environ["ODBA_PB25_O1_WORKBOOK"])
        for mutation,error in (("note","CR footnote changed"),("control","published control failed")):
            meta=json.loads((SIDE/"provenance.json").read_text())
            if mutation=="note":
                meta["workbook_cr_footnote_rows_438_to_440"][1]="unexpected"
            else:
                meta["official_controls"]["om_title"][2]+=1
            with tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/"mutated.json"
                if "pdf_reference_file" in meta:
                    name=meta["pdf_reference_file"]
                    (Path(tmp)/name).write_bytes((SIDE/name).read_bytes())
                f.write_text(json.dumps(meta))
                with self.assertRaisesRegex(ValueError,error):
                    M.build(w,f)


if __name__=="__main__":
    unittest.main()
