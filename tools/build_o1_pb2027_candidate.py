"""Build O-1 details from a pinned workbook, checked against the original PDF."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "data/o1/pb2027_candidate"
HEAD = (
    "Account", "Account Title", "Organization", "Budget Activity", "Budget Activity Title",
    "AG/BSA", "AG/Budget SubActivity (BSA) Title", "Line Number", "SAG/BLI",
    "SAG/Budget Line Item (BLI) Title", "Include In TOA", "FY 2025 Actuals",
    "FY 2025 Reconciliation", "FY 2025 Total", "FY 2026 Discretionary Enacted",
    "FY 2026 PL 119-21 Spend Plan", "FY 2026 Total", "FY 2027 Discretionary Request",
    "FY 2027 Mandatory Request", "FY 2027 Total", "Classification",
)
FY25_NATIVE = ("fy25_workbook_actuals", "fy25_workbook_reconciliation", "fy25_workbook_total")
BASE = ("submission_fy", "account_raw", "account_title", "organization_raw", "activity_raw",
        "activity_title", "activity_group_raw", "activity_group_title", "line_raw",
        "subactivity_raw", "line_title", "include_in_toa_workbook_raw", "classification_raw",
        "scope", "row_grain", "measure", "unit", "source_kind", "source_locator",
        "source_url", "fy25_printed_actuals_basis")


def require(condition, msg):
    if not condition:
        raise ValueError(msg)


def int_cell(v):
    if v in (None, ""):
        return None
    require(type(v) is int, f"unexpected money cell: {v!r}")
    return v


def sum_cell(values):
    entries = [x for x in values if x is not None]
    return sum(entries) if entries else None


def load_pdf_reference(source):
    src = json.loads(source.read_text(encoding="utf-8"))
    name = src["pdf_reference_file"]
    require(Path(name).name == name, "invalid PDF reference filename")
    raw = (source.parent / name).read_bytes()
    require(sha256(raw).hexdigest() == src["pdf_reference_sha256"],
            "PDF reference hash mismatch")
    reference = json.loads(raw)
    require(reference["source_pdf_sha256"] == src["pdf_sha256"], "wrong PDF binary reference")
    require(reference["columns"] == src["official_control_columns"], "wrong PDF column order")
    require(reference["printed_pages_scanned"] == list(range(1, 57))
            and reference["physical_pdf_pages_scanned"] == list(range(6, 62)),
            "incomplete PDF page scope")
    require(reference["row_count"] == len(reference["rows"]) == 397,
            "incomplete PDF detail reference")
    return reference


def verify_pdf_details(rows, reference):
    """Require both-direction printed identity and nullable cell equality.

    Pages 55–56 omit activity/subactivity codes. Match those unique account/line
    pairs without treating unprinted workbook metadata as PDF evidence.
    """
    columns = reference["columns"]
    require(len(columns) == 7, "wrong PDF monetary column count")
    printed = reference["rows"]
    require(len(rows) == len(printed) == reference["row_count"],
            "PDF detail coverage: missing or extra rows")
    identities = [(r["account_raw"], r["activity_raw"], r["line_raw"]) for r in rows]
    require(len(set(identities)) == len(rows), "duplicate candidate detail identity")
    pdf_identities = [(r["account"], r["activity"], r["line"]) for r in printed]
    require(len(set(pdf_identities)) == len(printed), "duplicate PDF detail identity")
    used = set()
    reported = blanks = 0
    for detail in printed:
        key = (detail["account"], detail["activity"], detail["line"])
        matches = [(i, r) for i, r in enumerate(rows)
                   if r["account_raw"] == detail["account"]
                   and r["line_raw"] == detail["line"]
                   and (detail["activity"] is None or r["activity_raw"] == detail["activity"])]
        require(len(matches) == 1, f"PDF detail coverage: missing or ambiguous {key}")
        index, row = matches[0]
        require(index not in used, f"PDF detail coverage: repeated {key}")
        used.add(index)
        require(row["line_title"] == detail["line_title"], f"PDF title mismatch: {key}")
        require(row["classification_raw"] == detail["classification"],
                f"PDF classification mismatch: {key}")
        if detail["subactivity"] is not None:
            require(row["subactivity_raw"] == detail["subactivity"],
                    f"PDF subactivity mismatch: {key}")
        require(4 <= detail["printed_page"] <= 56
                and detail["pdf_page"] == detail["printed_page"] + 5,
                f"invalid PDF page locator: {key}")
        require(len(detail["amounts"]) == 7, f"incomplete PDF cells: {key}")
        for column, expected in zip(columns, detail["amounts"], strict=True):
            require(expected is None or type(expected) is int, f"invalid PDF amount: {key}")
            value = row[column]
            if value is None or value == "":
                observed = None
            elif type(value) is int:
                observed = value
            else:
                require(isinstance(value, str)
                        and value.lstrip("-").isdigit(), f"invalid detail amount: {key} {column}")
                observed = int(value)
            require(observed == expected,
                    f"PDF amount/blank mismatch: {key} {column}: {observed} != {expected}")
            reported += expected is not None
            blanks += expected is None
    require(len(used) == len(rows), "PDF detail coverage: extra candidate rows")
    require((reported, blanks) == (reference["reported_amount_count"], reference["blank_cell_count"]),
            "PDF monetary coverage counts differ")


def read_workbook(path, src):
    # Import only for source intake; tests use the pinned real file.
    from openpyxl import load_workbook

    with path.open("rb") as f:
        workbook_bytes = f.read()
    require(sha256(workbook_bytes).hexdigest() == src["workbook_sha256"], "mirror workbook hash mismatch")
    w = load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
    try:
        ws = w[src["worksheet"]]
        rows = list(ws.values)
    finally:
        w.close()
    require(len(rows) == 398 and rows[1] == HEAD and not any(rows[-1]), "unexpected worksheet layout")
    require(rows[0][8] == "Total of Displayed Rows", "missing cached workbook control")
    native = []
    for i, row in enumerate(rows[2:-1], start=3):
        identity = (*row[:11], row[-1])
        require(all(v is None or isinstance(v, str) for v in identity), "unexpected detail labels")
        amounts = tuple(map(int_cell, row[11:20]))
        require(row[0] and row[3] and row[7] and row[10] in {"Y", "N"}, "missing workbook identity or scope")
        require(any(v is not None for v in amounts), "blank detail")
        for a,b,t in (amounts[:3],amounts[3:6],amounts[6:9]):
            require(sum_cell([a,b]) == t, f"native workbook line {i} does not tie")
        native.append((identity, amounts, i))
    require(len(native) == 395, "unexpected detail row count")
    require(Counter(x[0][10] for x in native) == {"Y":389,"N":6}, "unexpected workbook scopes")
    require(sum(not x[0][2] for x in native)==7, "unexpected blank organization count")
    require(len({(x[0][0],x[0][3],x[0][5],x[0][7],x[0][8]) for x in native})==395, "duplicate workbook key")
    require(sum(x[0][0]=="3400F" and x[0][7]=="999" for x in native)==2, "AF 999 rows not retained")
    require(tuple(sum(v or 0 for _, arr, _ in native for v in [arr[j]]) for j in range(9))
            == rows[0][11:20], "computed workbook does not tie to its cached total")
    return native


def csv_bytes(header, rows):
    s=io.StringIO(newline="")
    w=csv.writer(s,lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return s.getvalue().encode("utf-8")


def build(path, source):
    src=json.loads(source.read_text(encoding="utf-8"))
    require((src["submission_fy"],src["exhibit"],src["unit"])==(2027,"O-1","USD thousands"), "wrong metadata")
    data=[]
    for identity, vals, i in read_workbook(path,src):
        scope="om_title" if identity[10]=="Y" else "indefinite_accounts"
        data.append((2027,*identity,scope,"detail",src["measure"],src["unit"],"workbook_mirror",
            f'{src["worksheet"]}!{i}',src["workbook_url"],
            "mapped_from_workbook_fy25_total_verified_against_original_pdf",
            *vals[:3], vals[2], *vals[3:]))
    for item in src["pdf_only_detail"]:
        identity=(item["account"],item["account_title_on_page_3"],None,None,None,
                  None,None,item["line"],None,item["line_title"],None,item["classification"])
        require(not any(x[1]==item["account"] and x[8]==item["line"] for x in data), "overlapping PDF-only row")
        data.append((2027,*identity,item["scope"],"detail",src["measure"],src["unit"],
                     "official_pdf_indexed",f'printed p. {item["printed_page"]}; title p. 3',
                     src["pdf_url"],"official_pdf_fy25_actuals_direct",
                     None,None,None,item["fy25_printed_actuals"],*([None]*6)))
    require(len(data)==397 and len({x[1] for x in data})==31,"unexpected candidate scope")
    header = BASE + FY25_NATIVE + tuple(src["official_control_columns"])
    verify_pdf_details([dict(zip(header, row, strict=True)) for row in data],
                       load_pdf_reference(source))
    audit=[]
    columns=src["official_control_columns"]
    require(len(columns)==7,"invalid controls")
    for scope,controls in src["official_controls"].items():
        match=[x for x in data if x[13]==scope or scope=="om_title_plus_indefinite"]
        require(len(match)=={"om_title":390,"indefinite_accounts":7,"om_title_plus_indefinite":397}[scope],
                "wrong control scope")
        require(len(controls)==7,"missing control")
        for j, (key,expected) in enumerate(zip(columns,controls)):
            observed=sum_cell([r[-7+j] for r in match])
            require(observed==expected,f"official control {scope} {key}: {observed} != {expected}")
            audit.append((scope, key, observed, expected, 0 if expected is not None else None,
                          "matched_amount" if expected is not None else "blank_both",
                          src["control_printed_page"],src["pdf_url"]))
    require(len(audit)==21,"missing control scopes")
    for scope, control in src["military_department_controls"].items():
        group = set(control["accounts"])
        scoped = [r for r in data if r[1] in group and r[13] == "om_title"]
        require({r[1] for r in scoped} == group, "missing service control accounts")
        for j, (key, expected) in enumerate(zip(columns, control["amounts"], strict=True)):
            observed = sum_cell([r[-7+j] for r in scoped])
            require(observed == expected, f"official department control {scope} {key} failed")
            audit.append((scope, key, observed, expected, 0, "matched_amount", 1,
                          src["pdf_url"]))
    require(len(audit)==42,"missing department scopes")
    return {"detail_candidate.csv":csv_bytes(BASE+FY25_NATIVE+tuple(columns),data),
            "headline_controls.csv":csv_bytes(("scope","source_column_key","candidate_sum_usd_thousands",
              "official_amount_usd_thousands","difference_usd_thousands","status","printed_page","source_url"),audit)}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workbook",type=Path,required=True)
    p.add_argument("--source",type=Path,default=DEFAULT/"provenance.json")
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--out-dir",type=Path)
    modes.add_argument("--check",type=Path)
    a=p.parse_args()
    outputs=build(a.workbook,a.source)
    if a.check:
        for name,value in outputs.items():
            if (a.check/name).read_bytes()!=value:
                raise SystemExit(f"Output mismatch: {name}")
    else:
        a.out_dir.mkdir(exist_ok=True,parents=True)
        for name,value in outputs.items():
            (a.out_dir/name).write_bytes(value)
