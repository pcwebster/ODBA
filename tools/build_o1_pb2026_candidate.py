"""Build PB26 O-1 details from a pinned workbook and original-PDF reference."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "data/o1/pb2026_candidate"
COLUMNS = ("fy24_actuals_as_reported", "fy25_enacted", "fy25_supplemental",
           "fy25_published_total", "fy26_discretionary_request",
           "fy26_reconciliation_request", "fy26_published_total")
IDENTITY = ("account_raw", "account_title_workbook", "organization_raw",
            "activity_raw", "activity_title_workbook", "activity_group_raw",
            "activity_group_title_workbook", "line_raw", "subactivity_raw",
            "line_title_workbook", "include_in_toa_workbook_raw")
HEAD = ("Account", "Account Title", "Organization", "Budget Activity",
        "Budget Activity Title", "AG/BSA", "AG/Budget SubActivity (BSA) Title",
        "Line Number", "SAG/BLI", "SAG/Budget Line Item (BLI) Title",
        "Include In TOA", "FY 2024 Actuals", "FY 2025 Enacted",
        "FY 2025 Supplemental", "FY 2025 Total", "FY 2026 Disc Request",
        "FY 2026 Reconciliation Request", "FY 2026 Total", "Classification")
CONTROL_HEAD = ("scope", "source_column_key", "computed", "official_reported",
                "difference_usd_thousands", "status", "printed_page", "source_url")
EXCEPTION_HEAD = ("submission_fy","account_raw","activity_raw","line_raw",
                  "workbook_locator","fy25_enacted","fy25_supplemental",
                  "fy25_published_total","component_sum","component_sum_minus_published",
                  "scope","printed_page","source_url","status")


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def int_cell(v):
    if v in (None, ""):
        return None
    require(type(v) is int, f"unexpected amount {v!r}")
    return v


def sum_cell(values):
    vals=[x for x in values if x is not None]
    return sum(vals) if vals else None


def load_pdf_reference(source):
    src = json.loads(source.read_text(encoding="utf-8"))
    name = src["pdf_reference_file"]
    require(Path(name).name == name, "invalid PDF reference filename")
    raw = (source.parent / name).read_bytes()
    require(sha256(raw).hexdigest() == src["pdf_reference_sha256"], "PDF reference hash mismatch")
    reference = json.loads(raw)
    require(reference["source_pdf_sha256"] == src["pdf_sha256"], "wrong PDF binary reference")
    require(reference["columns"] == list(COLUMNS), "wrong PB26 PDF columns")
    require(reference["printed_pages_scanned"] == list(range(1, 56))
            and reference["physical_pdf_pages_scanned"] == list(range(6, 61)),
            "incomplete PDF page scope")
    require(reference["row_count"] == len(reference["rows"]) == 407, "incomplete PDF reference")
    return reference


def _match_pdf_details(rows, reference):
    printed = reference["rows"]
    require(len(rows) == len(printed) == reference["row_count"],
            "PDF detail coverage: missing or extra rows")
    # A missing printed line stays empty, including 5286A. Do not invent an ID.
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
    require(reference["columns"] == list(COLUMNS), "wrong PB26 PDF columns")
    reported = blanks = 0
    for row, detail in _match_pdf_details(rows, reference):
        key = (detail["account"], detail["activity"], detail["line"])
        require(row["line_title_printed"] == detail["line_title"], f"PDF title mismatch: {key}")
        require(row["classification_raw"] == detail["classification"],
                f"PDF classification mismatch: {key}")
        if detail["subactivity"] is not None:
            require(row["subactivity_raw"] == detail["subactivity"],
                    f"PDF subactivity mismatch: {key}")
        require(4 <= detail["printed_page"] <= 55
                and detail["pdf_page"] == detail["printed_page"] + 5,
                f"invalid PDF page locator: {key}")
        require(int(row["pdf_printed_page"]) == detail["printed_page"],
                f"PDF page mismatch: {key}")
        if row["official_indexed_line_title"]:
            require(row["official_indexed_line_title"] == detail["line_title"]
                    and int(row["official_title_printed_page"]) == detail["printed_page"],
                    f"indexed/printed label mismatch: {key}")
        require(len(detail["amounts"]) == 7, f"incomplete PDF cells: {key}")
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


def read_workbook(path, src):
    raw=path.read_bytes()
    require(sha256(raw).hexdigest()==src["workbook_sha256"],"mirror workbook hash mismatch")
    from openpyxl import load_workbook

    w=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    try:
        rows=list(w[src["worksheet"]].values)
    finally:
        w.close()
    require(len(rows)==410 and rows[1]==HEAD and not any(rows[-1]),"unrecognized workbook shape")
    require(rows[0][8]=="Total of Displayed Rows","missing cached workbook control")
    details=[]
    for i,r in enumerate(rows[2:-1],3):
        require(all(x is None or isinstance(x,str) for x in (*r[:11],r[-1])),"unexpected detail labels")
        require(r[0] and r[3] and r[10] in {"Y","N"},"missing identity or scope")
        vals=tuple(map(int_cell,r[11:18]))
        require(any(x is not None for x in vals),"blank detail")
        details.append((i, tuple(r[:11]), r[-1], vals))
    require(len(details)==407 and len({r[1][0] for r in details})==30,"wrong detail coverage")
    require(Counter(r[1][10] for r in details)=={"Y":400,"N":7},"wrong detail scopes")
    require(sum(not r[1][2] for r in details)==8,"unexpected organization blanks")
    require([(r[1][0],r[0],r[3]) for r in details if not r[1][7]]
            == [("5286A",108,(24,None,None,None,None,None,None))],"unexpected line ID blanks")
    require(len({(r[1][0],r[1][3],r[1][5],r[1][7],r[1][8]) for r in details})==407,"duplicate detail key")
    require(tuple(sum_cell(r[3][i] for r in details) for i in range(7))==rows[0][11:18],
            "cached workbook totals mismatch")
    require(sum(v is None for r in details for v in r[3])==993,"unexpected monetary blanks")
    require(sum(v is not None and v<0 for r in details for v in r[3])==5,"unexpected signed amounts")
    return details


def csv_bytes(head, rows):
    buf=io.StringIO(newline="")
    writer=csv.writer(buf,lineterminator="\n")
    writer.writerow(head)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build(workbook, source):
    src=json.loads(source.read_text(encoding="utf-8"))
    require((src["submission_fy"],src["exhibit"],src["unit"],src["last_o1_printed_page"])
            ==(2026,"O-1","USD thousands",55),"wrong source identity")
    details=read_workbook(workbook,src)
    known={(a,l):v for a,l,v in src["fy25_repeated_triplets_usd_thousands"]}
    require(len(known)==6 and sum(known.values())==41300,"wrong exception metadata")
    indexed={(g["account"],l):(g["title"],g["page"]) for g in src["official_indexed_titles"] for l in g["lines"]}
    found=set()
    rows=[]
    exc=[]
    audit=[]
    for n, ident, cls, vals in details:
        account, activity, line, flag=ident[0],ident[3],ident[7] or "",ident[10]
        location=f'{src["worksheet"]}!{n}'
        k=(account,line)
        scope="om_title" if flag=="Y" else "indefinite_accounts"
        label, page=indexed.get(k,("",None))
        a,b,t=vals[1:4]
        c,d,u=vals[4:7]
        require(sum_cell([c,d])==u,f"FY26 discrepancy: {location}")
        state="ties_if_reported"
        if sum_cell([a,b])!=t:
            require(k in known and flag=="N" and (a,b,t)==(known[k],)*3,
                    f"new FY25 discrepancy: {location}")
            require(k not in found,f"duplicate exception: {k}")
            found.add(k)
            state="matched_published_nonadditive_triplet"
            exc.append((2026,account,activity,line,location,a,b,t,a+b,a+b-t,scope,
                        src["fy25_repeated_triplets_printed_page"],src["pdf_url"],state))
        rows.append((2026,*ident,cls,scope,"detail",src["measure"],src["unit"],
                     "workbook_mirror",location,src["workbook_url"],label,page,state,*vals))
    require(found==set(known),"known exceptions changed")
    require(sum(r[9] for r in exc)==41300,"wrong scope exception sum")
    require({(r[1][0],r[1][7] or "") for r in details}.issuperset(indexed),"known title row missing")
    controls=src["official_controls"]
    def check(group, subset, expected, page):
        for j,(key,want) in enumerate(zip(COLUMNS,expected,strict=True)):
            got=sum_cell(r[3][j] for r in subset)
            require(got==want,f"headline discrepancy: {group}/{key}: {got} != {want}")
            audit.append((group,key,got,want,0 if want is not None else None,
                          "blank_both" if want is None else "matched_amount",page,src["pdf_url"]))
    counts={"om_title":400,"indefinite_accounts":7,"om_title_plus_indefinite":407}
    for scope,expected in controls.items():
        subset=[r for r in details if scope=="om_title_plus_indefinite"
                or r[1][10]=={"om_title":"Y","indefinite_accounts":"N"}[scope]]
        require(len(subset)==counts[scope],"wrong scope")
        delta=expected[1]+expected[2]-expected[3]
        require(delta==(0 if scope=="om_title" else 41300), "headline exception changed")
        check(scope,subset,expected,3)
    for scope,group in src["military_department_controls"].items():
        accounts=set(group["accounts"])
        subset=[r for r in details if r[1][0] in accounts and r[1][10]=="Y"]
        require({r[1][0] for r in subset}==accounts,"missing military department account")
        check(scope,subset,group["amounts"],1)
    for scope,group in src["printed_account_group_controls"].items():
        accounts=set(group["accounts"])
        subset=[r for r in details if r[1][0] in accounts and r[1][10]=="Y"]
        require({r[1][0] for r in subset}==accounts,"missing printed group account")
        check(scope,subset,group["amounts"],group["page"])
    require(len(audit)==56,"missing headline checks")
    columns=("submission_fy",*IDENTITY,"classification_raw","scope","row_grain",
             "measure","unit","source_kind","source_locator","source_url",
             "official_indexed_line_title","official_title_printed_page","fy25_arithmetic_status",*COLUMNS)
    reference = load_pdf_reference(source)
    records = [dict(zip(columns, row, strict=True)) for row in rows]
    for record, printed in _match_pdf_details(records, reference):
        record["line_title_printed"] = printed["line_title"]
        record["pdf_printed_page"] = printed["printed_page"]
    verify_pdf_details(records, reference)
    output_columns = columns[:-7] + ("line_title_printed", "pdf_printed_page") + COLUMNS
    return {"detail_candidate.csv":csv_bytes(output_columns,
                ([record[key] for key in output_columns] for record in records)),
            "headline_controls.csv":csv_bytes(CONTROL_HEAD,audit),
            "fy25_nonadditive_triplets.csv":csv_bytes(EXCEPTION_HEAD,exc)}


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
