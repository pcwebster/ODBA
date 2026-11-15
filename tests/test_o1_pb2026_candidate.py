from copy import deepcopy
import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SIDE=ROOT/"data/o1/pb2026_candidate"
SPEC=importlib.util.spec_from_file_location("pb26",ROOT/"tools/build_o1_pb2026_candidate.py")
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def read(name):
    with (SIDE/name).open(encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f))


class TestO1PB26(unittest.TestCase):
    def test_native_lanes_and_coverage(self):
        rows=read("detail_candidate.csv")
        self.assertEqual(len(rows),407)
        self.assertEqual(len({r["account_raw"] for r in rows}),30)
        self.assertEqual(sum(r["scope"]=="om_title" for r in rows),400)
        self.assertEqual(sum(r["scope"]=="indefinite_accounts" for r in rows),7)
        self.assertEqual(sum(not r["organization_raw"] for r in rows),8)
        vals=[r[c] for r in rows for c in M.COLUMNS]
        self.assertEqual((len(vals),vals.count(""),sum(v!="" and int(v)<0 for v in vals)),(2849,993,5))
        self.assertEqual(M.int_cell(0),0)
        self.assertIsNone(M.int_cell(""))

    def test_raw_titles_and_blank_line(self):
        rows=read("detail_candidate.csv")
        [r]=[r for r in rows if not r["line_raw"]]
        self.assertEqual((r["account_raw"],r["fy24_actuals_as_reported"],r["line_title_workbook"],
                          r["official_indexed_line_title"],r["official_title_printed_page"]),
                         ("5286A","24","","National Science Center, Army","55"))
        self.assertEqual((r["line_title_printed"],r["pdf_printed_page"]),
                         ("National Science Center, Army","55"))
        grp=[r for r in rows if r["account_raw"]=="0833D"]
        self.assertEqual(len(grp),7)
        self.assertEqual(sum(int(r["fy24_actuals_as_reported"]) for r in grp),1524)
        self.assertTrue(all(r["official_indexed_line_title"]=="Emergency Response Fund, Defense"
                         and r["line_title_workbook"]!=r["official_indexed_line_title"] for r in grp))
        self.assertTrue(all(r["line_title_printed"]==r["official_indexed_line_title"]
                         and r["pdf_printed_page"]==r["official_title_printed_page"] for r in grp))

    def test_exact_exceptions(self):
        rows=read("fy25_nonadditive_triplets.csv")
        self.assertEqual(len(rows),6)
        self.assertEqual({(r["account_raw"],r["line_raw"],int(r["fy25_published_total"])) for r in rows},
            {("5188D","190",3262),("5188D","210",540),("5188D","230",3318),
             ("5189D","260",16434),("5189D","280",7539),("5189D","300",10207)})
        self.assertTrue(all(r["fy25_enacted"]==r["fy25_supplemental"]==r["fy25_published_total"] for r in rows))
        self.assertEqual(sum(int(r["component_sum_minus_published"]) for r in rows),41300)
        expected={("5188D","190"):3262,("5188D","210"):540,("5188D","230"):3318,
                  ("5189D","260"):16434,("5189D","280"):7539,("5189D","300"):10207}
        detail_exceptions={}
        for detail in read("detail_candidate.csv"):
            a,b,total=[int(detail[c]) if detail[c]!="" else None
                       for c in ("fy25_enacted","fy25_supplemental","fy25_published_total")]
            components=[v for v in (a,b) if v is not None]
            component_sum=sum(components) if components else None
            if component_sum!=total:
                key=detail["account_raw"],detail["line_raw"]
                self.assertNotIn(key,detail_exceptions)
                self.assertEqual(detail["scope"],"indefinite_accounts")
                self.assertEqual(detail["pdf_printed_page"],"55")
                self.assertEqual((a,b,total),(expected[key],)*3)
                detail_exceptions[key]=total
        self.assertEqual(detail_exceptions,expected)
        for row in rows:
            with self.subTest(account=row["account_raw"],line=row["line_raw"]):
                amount=expected[row["account_raw"],row["line_raw"]]
                self.assertEqual(int(row["fy25_published_total"]),amount)
                self.assertEqual(int(row["component_sum"]),2*amount)
                self.assertEqual(int(row["component_sum_minus_published"]),amount)
                self.assertEqual(row["printed_page"],"55")
                self.assertEqual(row["status"],"matched_published_nonadditive_triplet")

    def test_headline_controls_match(self):
        rows=read("headline_controls.csv")
        self.assertEqual(len(rows),56)
        self.assertEqual(sum(r["status"]=="blank_both" for r in rows),9)
        source=json.loads((SIDE/"provenance.json").read_text(encoding="utf-8"))
        details=read("detail_candidate.csv")
        groups={scope:[r for r in details if scope=="om_title_plus_indefinite"
                      or r["scope"]==scope] for scope in source["official_controls"]}
        controls=dict(source["official_controls"])
        for metadata_key in ("military_department_controls","printed_account_group_controls"):
            for scope,control in source[metadata_key].items():
                groups[scope]=[r for r in details if r["scope"]=="om_title"
                               and r["account_raw"] in control["accounts"]]
                controls[scope]=control["amounts"]
        audit={(r["scope"],r["source_column_key"]):r for r in rows}
        self.assertEqual(set(audit),{(scope,column) for scope in controls for column in M.COLUMNS})
        for scope,amounts in controls.items():
            for column,expected in zip(M.COLUMNS,amounts,strict=True):
                with self.subTest(scope=scope,column=column):
                    values=[int(r[column]) for r in groups[scope] if r[column]!=""]
                    observed=sum(values) if values else None
                    self.assertEqual(observed,expected)
                    row=audit[scope,column]
                    self.assertEqual(row["computed"],"" if observed is None else str(observed))
                    self.assertEqual(row["official_reported"],"" if expected is None else str(expected))
                    self.assertEqual(row["difference_usd_thousands"],"" if expected is None else "0")
                    self.assertEqual(row["status"],"blank_both" if expected is None else "matched_amount")
        x={(r["scope"],r["source_column_key"]):r["official_reported"] for r in rows}
        self.assertEqual(x["om_title_plus_indefinite","fy25_published_total"],"342358161")
        self.assertEqual(x["om_title","fy26_reconciliation_request"],"22708023")
        self.assertEqual(x["om_title","fy26_published_total"],"360277259")

    def test_full_printed_pdf_reference(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        self.assertEqual(reference["columns"],list(M.COLUMNS))
        self.assertEqual(len(reference["rows"]),407)
        self.assertEqual(sum(len(r["amounts"]) for r in reference["rows"]),2849)
        self.assertEqual(reference["reported_amount_count"],1856)
        self.assertEqual(reference["blank_cell_count"],993)
        self.assertIsNone(M.verify_pdf_details(read("detail_candidate.csv"),reference))

    def test_pdf_missing_extra_substituted_duplicate_and_invented_line_rejected(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        rows=read("detail_candidate.csv")
        missing=deepcopy(rows[:-1])
        unexpected=dict(rows[0],line_raw="998")
        extra=deepcopy(rows)+[unexpected]
        replaced=deepcopy(rows)
        replaced[0]=unexpected
        duplicate=deepcopy(rows)
        duplicate[1]=dict(duplicate[0])
        invented=deepcopy(rows)
        blank=next(r for r in invented if r["account_raw"]=="5286A")
        self.assertEqual(blank["line_raw"],"")
        blank["line_raw"]="120"
        for name,mutated in (("missing",missing),("extra",extra),("substituted",replaced),
                             ("duplicate",duplicate),("invented_5286A_line",invented)):
            with self.subTest(change=name),self.assertRaises(ValueError):
                M.verify_pdf_details(mutated,reference)

    def test_pdf_signed_blank_and_request_lanes_rejected(self):
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        rows=read("detail_candidate.csv")
        negative={(r["account_raw"],r["line_raw"],column):int(r[column]) for r in rows
                  for column in M.COLUMNS if r[column]!="" and int(r[column])<0}
        self.assertEqual(negative,{("0833D",line,"fy24_actuals_as_reported"):value
                                  for line,value in (("110",-224),("120",-7140),("130",-140),
                                                     ("150",-798),("160",-518))})
        mutations=[]
        for (account,line,column),amount in negative.items():
            mutated=deepcopy(rows)
            next(r for r in mutated if r["account_raw"]==account and r["line_raw"]==line)[column]=str(-amount)
            mutations.append((f"sign_{account}_{line}",mutated))
        blank=deepcopy(rows)
        target=next(r for r in blank if r["fy26_reconciliation_request"]=="")
        target["fy26_reconciliation_request"]="0"
        mutations.append(("blank_to_zero",blank))
        swapped=deepcopy(rows)
        columns=("fy26_discretionary_request","fy26_reconciliation_request")
        target=next(r for r in swapped if all(r[c]!="" for c in columns)
                    and r[columns[0]]!=r[columns[1]])
        target[columns[0]],target[columns[1]]=target[columns[1]],target[columns[0]]
        mutations.append(("FY26_request_lanes_swapped",swapped))
        for name,mutated in mutations:
            with self.subTest(change=name),self.assertRaises(ValueError):
                M.verify_pdf_details(mutated,reference)
        self.assertNotIn("fy26_pl11921_spend_plan",rows[0])
        self.assertEqual(M.COLUMNS[-3:],("fy26_discretionary_request",
                                      "fy26_reconciliation_request","fy26_published_total"))

    def test_reported_zero_distinct_from_unreported_blank(self):
        reference=deepcopy(M.load_pdf_reference(SIDE/"provenance.json"))
        printed=next(r for r in reference["rows"] if r["activity"] is not None
                     and r["line"] is not None and None in r["amounts"])
        index=printed["amounts"].index(None)
        rows=read("detail_candidate.csv")
        [detail]=[r for r in rows if (r["account_raw"],r["activity_raw"],r["line_raw"])
                  ==(printed["account"],printed["activity"],printed["line"])]
        column=reference["columns"][index]
        self.assertEqual(detail[column],"")
        detail[column]="0"
        printed["amounts"][index]=0
        reference["reported_amount_count"]+=1
        reference["blank_cell_count"]-=1
        self.assertIsNone(M.verify_pdf_details(rows,reference))
        with self.assertRaises(ValueError):
            M.verify_pdf_details(read("detail_candidate.csv"),reference)

    def test_printed_labels_do_not_overwrite_workbook_labels(self):
        rows=read("detail_candidate.csv")
        reference=M.load_pdf_reference(SIDE/"provenance.json")
        changed=deepcopy(rows)
        target=next(r for r in changed if r["account_raw"]=="0833D" and r["line_raw"]=="110")
        self.assertEqual(target["line_title_workbook"],"Increase Situational Awareness")
        self.assertEqual(target["line_title_printed"],"Emergency Response Fund, Defense")
        target["line_title_printed"]=target["line_title_workbook"]
        with self.assertRaises(ValueError):
            M.verify_pdf_details(changed,reference)

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

    def test_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"bad.xlsx"
            f.write_bytes(b"not the pinned workbook")
            # The optional dependency is required for actual workbook parsing.
            src=json.loads((SIDE/"provenance.json").read_text())
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                M.read_workbook(f,src)

    @unittest.skipUnless(os.environ.get("ODBA_PB26_O1_WORKBOOK"),"exact workbook not supplied")
    def test_exact_regeneration(self):
        w=Path(os.environ["ODBA_PB26_O1_WORKBOOK"])
        for f,data in M.build(w,SIDE/"provenance.json").items():
            self.assertEqual(data,(SIDE/f).read_bytes())

    @unittest.skipUnless(os.environ.get("ODBA_PB26_O1_WORKBOOK"),"exact workbook not supplied")
    def test_unapproved_exception_fails(self):
        meta=json.loads((SIDE/"provenance.json").read_text())
        w=Path(os.environ["ODBA_PB26_O1_WORKBOOK"])
        meta["fy25_repeated_triplets_usd_thousands"][0][2]+=1
        meta["fy25_repeated_triplets_usd_thousands"][1][2]-=1
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bad.json"
            if "pdf_reference_file" in meta:
                name=meta["pdf_reference_file"]
                (Path(tmp)/name).write_bytes((SIDE/name).read_bytes())
            p.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"new FY25 discrepancy"):
                M.build(w,p)


if __name__=="__main__":
    unittest.main()
