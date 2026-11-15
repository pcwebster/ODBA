"""Build PB25 O-1 details from a pinned workbook and original-PDF reference."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path

DEFAULT=Path(__file__).resolve().parents[1]/"data/o1/pb2025_candidate"
COLUMNS=("fy23_actuals_as_reported","fy24_pb_request_cr_adjusted","fy25_request")
IDENTITY=("account_raw","account_title_workbook","organization_raw","activity_raw",
          "activity_title_workbook","activity_group_raw","activity_group_title_workbook",
          "line_raw","subactivity_raw","line_title_workbook","include_in_toa_workbook_raw")
HEAD=("Account","Account Title","Organization","Budget Activity","Budget Activity Title",
      "AG/BSA","AG/Budget SubActivity (BSA) Title","Line Number","SAG/BLI",
      "SAG/Budget Line Item (BLI) Title","Include In TOA","FY 2023 Actuals",
      "FY 2024 PB Request with CR Adjustments*","FY 2025 Request","Classification")


def require(ok,msg):
    if not ok:
        raise ValueError(msg)


def int_cell(v):
    if v in (None,""):
        return None
    require(type(v) is int,f"unexpected amount: {v!r}")
    return v


def sum_cell(values):
    vals=[v for v in values if v is not None]
    return sum(vals) if vals else None


def load_pdf_reference(source):
    src = json.loads(source.read_text(encoding="utf-8"))
    name = src["pdf_reference_file"]
    require(Path(name).name == name, "invalid PDF reference filename")
    raw = (source.parent / name).read_bytes()
    require(sha256(raw).hexdigest() == src["pdf_reference_sha256"], "PDF reference hash mismatch")
    reference = json.loads(raw)
    require(reference["source_pdf_sha256"] == src["pdf_sha256"], "wrong PDF binary reference")
    require(reference["columns"] == list(COLUMNS), "wrong PB25 PDF columns")
    require(reference["printed_pages_scanned"] == list(range(1, 68))
            and reference["physical_pdf_pages_scanned"] == list(range(5, 72)),
            "incomplete PDF page scope")
    require(reference["row_count"] == len(reference["rows"]) == 434, "incomplete PDF reference")
    return reference


def _match_pdf_details(rows, reference):
    printed = reference["rows"]
    require(len(rows) == len(printed) == reference["row_count"],
            "PDF detail coverage: missing or extra rows")
    # Bind by account and printed activity/line; shared BLI values are not identities.
    keys = [(r["account_raw"], r["activity_raw"] or "", r["line_raw"] or "") for r in rows]
    require(len(set(keys)) == len(rows), "duplicate candidate detail identity")
    pdf_keys = [(r["account"], r["activity"], r["line"]) for r in printed]
    require(len(set(pdf_keys)) == len(printed), "duplicate PDF detail identity")
    matched = []
    used = set()
    for detail in printed:
        key = (detail["account"], detail["activity"], detail["line"])
        matches = [(i, r) for i, r in enumerate(rows)
                   if r["account_raw"] == detail["account"]
                   and (r["line_raw"] or "") == (detail["line"] or "")
                   and (detail["activity"] is None or r["activity_raw"] == detail["activity"])]
        require(len(matches) == 1, f"PDF detail coverage: missing or ambiguous {key}")
        index, row = matches[0]
        require(index not in used, f"PDF detail coverage: repeated {key}")
        used.add(index)
        matched.append((row, detail))
    require(len(used) == len(rows), "PDF detail coverage: extra candidate rows")
    return matched


def verify_pdf_details(rows, reference):
    """Check printed identities, separate labels and every signed/nullable cell."""
    require(reference["columns"] == list(COLUMNS), "wrong PB25 PDF columns")
    reported = blanks = 0
    for row, detail in _match_pdf_details(rows, reference):
        key = (detail["account"], detail["activity"], detail["line"])
        require(row["line_title_printed"] == detail["line_title"], f"PDF title mismatch: {key}")
        require(row["classification_raw"] == detail["classification"],
                f"PDF classification mismatch: {key}")
        if detail["subactivity"] is not None:
            require(row["subactivity_raw"] == detail["subactivity"],
                    f"PDF subactivity mismatch: {key}")
        require(4 <= detail["printed_page"] <= 67
                and detail["pdf_page"] == detail["printed_page"] + 4,
                f"invalid PDF page locator: {key}")
        require(int(row["pdf_printed_page"]) == detail["printed_page"],
                f"PDF page mismatch: {key}")
        if row["official_indexed_line_title"]:
            # Keep the initial indexed label separately: its comma spacing may
            # differ from the exact PDF spelling in line_title_printed.
            require(int(row["official_indexed_check_page"]) == detail["printed_page"],
                    f"indexed/printed page mismatch: {key}")
        require(len(detail["amounts"]) == 3, f"incomplete PDF cells: {key}")
        for column, expected in zip(COLUMNS, detail["amounts"], strict=True):
            require(expected is None or type(expected) is int, f"invalid PDF amount: {key}")
            value = row[column]
            if value is None or value == "":
                observed = None
            elif type(value) is int:
                observed = value
            else:
                require(isinstance(value, str) and value.lstrip("-").isdigit(),
                        f"invalid detail amount: {key} {column}")
                observed = int(value)
            require(observed == expected,
                    f"PDF amount/blank mismatch: {key} {column}: {observed} != {expected}")
            reported += expected is not None
            blanks += expected is None
    require((reported, blanks) == (reference["reported_amount_count"], reference["blank_cell_count"]),
            "PDF monetary coverage counts differ")


def read_workbook(workbook,src):
    raw=workbook.read_bytes()
    require(sha256(raw).hexdigest()==src["workbook_sha256"],"mirror workbook hash mismatch")
    from openpyxl import load_workbook
    book=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    try:
        rows=list(book[src["worksheet"]].values)
    finally:
        book.close()
    require(len(rows)==440 and rows[1]==HEAD and rows[0][8]=="Total of Displayed Rows",
            "unexpected worksheet layout")
    require(not any(rows[436]),"unexpected sheet separator")
    require([r[0] for r in rows[437:]]==src["workbook_cr_footnote_rows_438_to_440"]
            and not any(x for r in rows[437:] for x in r[1:]),"CR footnote changed")
    result=[]
    for i,row in enumerate(rows[2:436],start=3):
        ids=tuple(row[:11])
        require(all(x is None or isinstance(x,str) for x in (*ids,row[-1])),"bad detail metadata")
        require(row[0] and row[3] and row[7] and row[10] in {"Y","N"},"missing detail or scope")
        vals=tuple(map(int_cell,row[11:14]))
        require(any(v is not None for v in vals),"empty detail row")
        result.append((i,ids,row[-1],vals))
    require(len(result)==434 and len({r[1][0] for r in result})==31,"wrong coverage")
    require(len({(r[1][0],r[1][3],r[1][7]) for r in result})==434,"duplicate within-edition key")
    require(Counter(r[1][10] for r in result)=={"Y":427,"N":7},"wrong scopes")
    require(len({r[1][3] for r in result if r[1][0]=="3400F" and r[1][7]=="999"})==2,
            "missing activity-qualified 3400F adjustment rows")
    require(sum(not r[1][2] for r in result)==8,"wrong organization blanks")
    vals=[v for r in result for v in r[3]]
    require((len(vals),sum(v is None for v in vals),sum(v is not None and v<0 for v in vals))
            ==(1302,200,15),"unexpected monetary positions")
    require(tuple(sum_cell(r[3][j] for r in result) for j in range(3))==rows[0][11:14],
            "cached workbook totals mismatch")
    return result


def csv_bytes(cols,rows):
    f=io.StringIO(newline="")
    w=csv.writer(f,lineterminator="\n")
    w.writerow(cols)
    w.writerows(rows)
    return f.getvalue().encode("utf-8")


def build(workbook,source):
    src=json.loads(source.read_text(encoding="utf-8"))
    require((src["submission_fy"],src["exhibit"],src["unit"],src["last_o1_printed_page"])
            ==(2025,"O-1","USD thousands",67),"wrong vintage or boundary")
    d=read_workbook(workbook,src)
    details=[]
    audit=[]
    observed_specific=set()
    specific={(x["account"],x["activity"],x["line"],x["bli"]):x for x in src["official_detail_checks"]}
    require(len(specific)==3,"wrong detail cross-checks")
    for i,m,cls,v in d:
        k=(m[0],m[3],m[7],m[8])
        page=None
        title=""
        if k in specific:
            item=specific[k]
            require(list(v)==item["amounts"],f"detail verification failure {k}")
            page=item["printed_page"]
            title=item.get("printed_line_title","")
            observed_specific.add(k)
        scope="om_title" if m[10]=="Y" else "indefinite_accounts"
        details.append((2025,*m,cls,scope,"detail",src["measure"],src["unit"],
            "workbook_mirror",f'{src["worksheet"]}!{i}',src["workbook_url"],page,
            src["pdf_url"] if page else "",title,*v))
    require(observed_specific==set(specific),"missing official edge-case row")
    blis={(r[1][0],r[1][7]) for r in d if r[1][8]=="1PL3"}
    require({("5751D","010"),("0134D","010")}<=blis,"shared BLI lost")
    def check(scope,subset,expected,page):
        for j,(key,value) in enumerate(zip(COLUMNS,expected,strict=True)):
            got=sum_cell(r[3][j] for r in subset)
            require(got==value,f"published control failed: {scope}/{key}: {got} != {value}")
            audit.append((scope,key,got,value,0 if value is not None else None,
                          "blank_both" if value is None else "matched_amount",page,src["pdf_url"]))
    for scope,a in src["official_controls"].items():
        group=[r for r in d if scope=="om_title_plus_indefinite"
               or r[1][10]=={"om_title":"Y","indefinite_accounts":"N"}[scope]]
        require(len(group)=={"om_title":427,"indefinite_accounts":7,"om_title_plus_indefinite":434}[scope],
                "wrong control scope")
        check(scope,group,a,3)
    for page,key in ((1,"military_department_controls"),(3,"other_controls")):
        for scope,g in src[key].items():
            accounts=set(g["accounts"])
            group=[r for r in d if r[1][0] in accounts and r[1][10]=="Y"]
            require({r[1][0] for r in group}==accounts,"missing a control account")
            check(scope,group,g["amounts"],g.get("page",page))
    require(len(audit)==27,"missing official controls")
    cols=("submission_fy",*IDENTITY,"classification_raw","scope","row_grain","measure","unit",
          "source_kind","source_locator","source_url","official_indexed_check_page",
          "official_indexed_check_url","official_indexed_line_title",*COLUMNS)
    reference = load_pdf_reference(source)
    records = [dict(zip(cols, row, strict=True)) for row in details]
    for record, printed in _match_pdf_details(records, reference):
        record["line_title_printed"] = printed["line_title"]
        record["pdf_printed_page"] = printed["printed_page"]
    verify_pdf_details(records, reference)
    output_columns = cols[:-3] + ("line_title_printed", "pdf_printed_page") + COLUMNS
    return {"detail_candidate.csv":csv_bytes(output_columns,
                ([record[key] for key in output_columns] for record in records)),
            "headline_controls.csv":csv_bytes(("scope","source_column_key","computed",
            "official_reported","difference_usd_thousands","status","printed_page","source_url"),audit)}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workbook",type=Path,required=True)
    p.add_argument("--source",type=Path,default=DEFAULT/"provenance.json")
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out-dir",type=Path)
    mode.add_argument("--check",type=Path)
    a=p.parse_args()
    for name,content in build(a.workbook,a.source).items():
        if a.check:
            if (a.check/name).read_bytes()!=content:
                raise SystemExit(f"Output mismatch: {name}")
        else:
            a.out_dir.mkdir(exist_ok=True,parents=True)
            (a.out_dir/name).write_bytes(content)
