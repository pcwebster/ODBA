"""Build a standalone PB27 R-1 sidecar from the pinned publisher PDF."""
import argparse
from collections import Counter
import csv
if __package__:
    from .verify_r1_pb2027_coordinates import check as check_coordinates
else:
    from verify_r1_pb2027_coordinates import check as check_coordinates
import hashlib
import json
from pathlib import Path
import re
import subprocess

OFFICIAL = "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_r1.pdf"
DEFAULT = Path(__file__).resolve().parents[1] / "data/r1/pb2027"
SOURCE_FILE = "FY2027_r1.pdf"
EDITION = "PB27"
EXPECTED_HASH = "1aa8846edb69d4c3a54e03b383b0cabb77f93433162b8139ab8cbb55bcc7882a"
LANES = ("fy25_actual_as_reported","fy26_discretionary_enacted","fy26_pl11921_spend_plan",
         "fy26_published_total","fy27_discretionary_request","fy27_mandatory_request","fy27_published_total")
ACCOUNT_LABELS = (
  ("2040A","Research, Development, Test and Evaluation, Army"),
  ("1319N","Research, Development, Test and Evaluation, Navy"),
  ("3600F","Research, Development, Test and Evaluation, Air Force"),
  ("3620F","Research, Development, Test, and Evaluation, Space Force"),
  ("0400D","Research, Development, Test and Evaluation, Defense-Wide"),
  ("3007D","Golden Dome for America Fund"),
  ("0460D","Operational Test and Evaluation, Defense"),
  ("0107D","Office of the Inspector General"),
  ("0130D","Combat and Operational Medicine Program"),
  ("0390D","Chemical Agents and Munitions Destruction, Defense"),
)
EXPECTED_COUNTS = dict(zip((a for a, _ in ACCOUNT_LABELS), (234,254,277,72,289,19,3,1,13,1)))
NON_TITLE = {"0107D","0130D","0390D"}
TITLE_TOTALS = ("Total Research, Development, Test, & Evaluation","Total Not in Research, Development, Test, & Evaluation")
VERIFY_HEADLINES = (
  (143345996,144922309,65462721,210385030,218791608,124897313,343688921),
  (2452098,2687376,None,2687376,1076840,None,1076840),
)
HEADER = re.compile(r"\b(Actuals)\s+(Enacted)\s+(Spend Plan)\s+(Total\*?)\s+(Request)\s+(Request)\s+(Total)")
ACCOUNT = re.compile(r"^\s*Appropriation:\s+([0-9]{4}[A-Z])\b")
DETAIL = re.compile(r"^\s{0,4}(\d{1,3})\s+([0-9A-Za-z]+)\s+(.*?)\s+(\d{2})\s+([A-Z])(?:\s+|$)")
MONEY = re.compile(r"-?\d+(?:,\d{3})*|\(\d+(?:,\d{3})*\)")

def demand(ok, message):
    if not ok:
        raise ValueError(message)

def numeric_columns(line, begin, ends):
    values = [None] * len(ends)
    for token in re.finditer(r"\S+", line[begin:]):
        value = token.group()
        if not MONEY.fullmatch(value):
            raise ValueError(f"Unexpected amount token {value!r}: {line!r}")
        right = begin + token.end()
        column = min(range(len(ends)), key=lambda k: abs(right-ends[k]))
        # Poppler's monospace layout quantization shifts isolated short cells further
        # than longer amounts (45, 63, 24); columns remain separated by at least 10.
        demand(abs(right-ends[column]) <= 6 and values[column] is None,
               f"Ambiguous amount {value!r}: {line!r}")
        values[column] = int(value.replace(",", "").replace("(", "-").replace(")", ""))
    return tuple(values)

def page_ends(text):
    header = next((m for line in text.splitlines() if (m := HEADER.search(line))), None)
    demand(header is not None, "Missing seven-lane page header")
    return tuple(header.end(k) for k in range(1, 8))

def read(pdf):
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    demand(digest == EXPECTED_HASH, f"Unexpected PB27 publisher PDF fingerprint: {digest}")
    dump = subprocess.run(["pdftotext","-layout",str(pdf),"-"], check=True, capture_output=True).stdout
    pages = dump.decode("utf-8").split("\f")
    if pages[-1] == "":
        pages.pop()
    demand(len(pages)==125, f"Expected 125 physical pages, found {len(pages)}")
    facts = {}
    observations = []
    headline = pages[5]
    for i, page in enumerate(pages[5:], 1):
        lines = page.splitlines()
        footer = [re.fullmatch(r"\s*Page\s+(\d+)\s*",line) for line in lines]
        demand(sum(f is not None and int(f[1]) == i for f in footer)==1,f"Unexpected footer on page {i}")
        ends = page_ends(page)
        appropriation = next((m[1] for line in lines if (m := ACCOUNT.match(line))), None)
        if appropriation is None:
            continue
        demand(appropriation in EXPECTED_COUNTS, f"Unknown appropriation {appropriation} on page {i}")
        for idx,line in enumerate(lines):
            m = DETAIL.match(line)
            if not m:
                demand(not re.match(r"^\s{0,2}\d{1,3}\s+[0-9A-Za-z]{7,}",line),
                       f"Unparsed detail candidate on page {i}: {line}")
                continue
            number, pe, printed_title, activity, sec = m.groups()
            values = numeric_columns(line, m.end(5), ends)
            # Blank is distinct from zero. A line lacking lanes is still a printed observation.
            continuations = []
            for line2 in lines[idx+1:]:
                if not line2.strip() or DETAIL.match(line2):
                    break
                if len(line2) > m.start(4) or abs(len(line2)-len(line2.lstrip())-m.start(3)) > 2:
                    break
                continuations.append(line2.strip())
            printed_title = " ".join((printed_title, *continuations))
            key = (appropriation,activity,number,pe)
            occurrence = {
                "printed_page":i, "physical_page":i+5,
                "printed_title":printed_title, "security_code_as_printed":sec,
                "presentation":"defense_agency_repeat" if appropriation=="0400D" and 84<=i<=114 else "appropriation_detail",
            }
            observations.append((key, values, occurrence))
            if key in facts:
                demand(facts[key]["amount_k"]==values, f"Duplicate amount conflict {key}: {i}")
                facts[key]["source_occurrences"].append(occurrence)
            else:
                facts[key] = {"appropriation":appropriation,"activity":activity,"printed_line":number,
                              "program_element":pe,"non_title":appropriation in NON_TITLE,
                              "amount_k":values,"source_occurrences":[occurrence]}
    demand(len(observations)==1452 and len(facts)==1163,"Unexpected identity universe")
    counts = Counter(a for a,*_ in facts)
    demand(counts==EXPECTED_COUNTS, f"Unexpected detail counts: {counts}")
    repeats = [x for x in facts.values() if len(x["source_occurrences"])>1]
    demand(len(repeats)==289 and all(x["appropriation"]=="0400D" and
            [obs["presentation"] for obs in x["source_occurrences"]]==["appropriation_detail","defense_agency_repeat"]
            for x in repeats), "Unexpected repeated detail presentation")
    controls = {}
    ends = page_ends(headline)
    for code,label in (*ACCOUNT_LABELS, *zip(("rdte_title_total","outside_title_total"),TITLE_TOTALS)):
        lines = [line.lstrip() for line in headline.splitlines() if line.lstrip().startswith(label+"  ")]
        demand(len(lines)==1, f"Page 1 control missing or repeated: {label}")
        full_line = next(x for x in headline.splitlines() if x.lstrip()==lines[0])
        controls[code] = numeric_columns(full_line, full_line.index(label)+len(label), ends)
    demand(tuple(controls[k] for k in ("rdte_title_total","outside_title_total"))==VERIFY_HEADLINES,
           "Page 1 headlines do not match independently verified Comptroller values")
    for code,_ in ACCOUNT_LABELS:
        subtotal = sum_lanes([x["amount_k"] for x in facts.values() if x["appropriation"]==code])
        demand(subtotal==controls[code], f"Account control mismatch for {code}: {subtotal}")
    for non_title,total_code in ((False,"rdte_title_total"),(True,"outside_title_total")):
        subtotal = sum_lanes([x["amount_k"] for x in facts.values() if x["non_title"]==non_title])
        demand(subtotal==controls[total_code], f"Topline control mismatch: {total_code}")
    return {"source_sha256":digest, "detail_count":len(facts),
            "occurrence_count":len(observations),"control_printed_page":1,"control_physical_page":6,
            "headline_and_account_controls_k":controls,"detail":list(facts.values())}

def sum_lanes(vectors):
    summed = []
    for lane in zip(*vectors):
        populated = [x for x in lane if x is not None]
        summed.append(sum(populated) if populated else None)
    return tuple(summed)


DETAIL_KEY = ("submission_edition", "appropriation", "budget_activity", "printed_line", "program_element")
DETAIL_FIELDS = (*DETAIL_KEY, "scope", "source_file", *LANES)
OCCURRENCE_FIELDS = (*DETAIL_KEY, "scope", "source_file", "role", "printed_page",
                     "physical_pdf_page", "printed_title", "security_code_as_printed", "presentation")
CONTROL_FIELDS = ("submission_edition", "scope", "source_file", "role", "control_grain",
                  "control_code", "published_label", "printed_page", "physical_pdf_page", *LANES)
LANE_META = (
    (2025, "FY 2025 Actuals", "historical_toa_as_reported", False),
    (2026, "FY 2026 Discretionary Enacted", "discretionary_enacted", False),
    (2026, "FY 2026 PL 119-21 Spend Plan", "pl11921_spend_plan", False),
    (2026, "FY 2026 Total", "published_total", True),
    (2027, "FY 2027 Discretionary Request", "discretionary_request", False),
    (2027, "FY 2027 Mandatory Request", "mandatory_request", False),
    (2027, "FY 2027 Total", "published_total", True),
)
NAMES = ("detail_in_title.csv", "detail_outside_title.csv", "source_occurrences.csv",
         "published_controls.csv", "provenance.json")


def scope(outside):
    return "outside_rdte_title" if outside else "rdte_title"


def csv_out(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as dest:
        writer = csv.writer(dest, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def build(pdf, destination):
    result = read(pdf)
    positions = check_coordinates(pdf, result)
    demand(positions == 10164, f"Unexpected coordinate coverage: {positions}")
    inside, outside, occurrences = [], [], []
    for row in result["detail"]:
        key = (EDITION, row["appropriation"], row["activity"], row["printed_line"],
               row["program_element"], scope(row["non_title"]), SOURCE_FILE)
        (outside if row["non_title"] else inside).append((*key, *row["amount_k"]))
        for o in row["source_occurrences"]:
            occurrences.append((*key, "non_additive_source_occurrence", o["printed_page"],
                                o["physical_page"], o["printed_title"],
                                o["security_code_as_printed"], o["presentation"]))
    demand((len(inside), len(outside), len(occurrences)) == (1148, 15, 1452),
           "Unexpected title/outside-title/occurrence coverage")
    titles = ("rdte_title_total", "outside_title_total")
    labels = dict((*ACCOUNT_LABELS, *zip(titles, TITLE_TOTALS)))
    controls = [
        (EDITION, scope(code in NON_TITLE or code == titles[1]), SOURCE_FILE,
         "non_additive_published_control", "scope_total" if code in titles else "appropriation",
         code, labels[code], result["control_printed_page"], result["control_physical_page"], *amounts)
        for code, amounts in result["headline_and_account_controls_k"].items()
    ]
    demand(len(controls) == 12, "Unexpected control coverage")
    destination.mkdir(parents=True, exist_ok=True)
    csv_out(destination / NAMES[0], DETAIL_FIELDS, inside)
    csv_out(destination / NAMES[1], DETAIL_FIELDS, outside)
    csv_out(destination / NAMES[2], OCCURRENCE_FIELDS, occurrences)
    csv_out(destination / NAMES[3], CONTROL_FIELDS, controls)
    provenance = {
        "source_file": SOURCE_FILE,
        "source_url": OFFICIAL,
        "source_role": "publisher_pdf",
        "sha256": EXPECTED_HASH,
        "exhibit_type": "R-1",
        "exhibit_title": "Exhibit R-1 — Research, Development, Test, & Evaluation Programs",
        "submission_edition": EDITION,
        "submission_fy": 2027,
        "publication_context": "President's Budget; each funding column retains its own basis",
        "publication_month_as_printed": "2026-04",
        "acquisition_date": "2026-11-16",
        "acquisition_evidence": "https://fmtransformation.atlassian.net/browse/DBDP-90?focusedCommentId=10678",
        "publication_cadence": "Annual, President's Budget release",
        "design_receipt": "https://fmtransformation.atlassian.net/browse/DBDP-90?focusedCommentId=10688",
        "approval_receipt": "https://fmtransformation.atlassian.net/browse/DBDP-90?focusedCommentId=10694",
        "unit": "USD thousands, TOA as printed",
        "identity": list(DETAIL_KEY),
        "funding_lanes": [
            {"field": field, "funding_fy": fy, "published_label": label, "basis": basis,
             "is_published_total": total}
            for field, (fy, label, basis, total) in zip(LANES, LANE_META)
        ],
        "coverage": {
            "physical_pdf_pages": 125, "detail_keys_in_title": len(inside),
            "detail_keys_outside_title": len(outside), "source_occurrences": len(occurrences),
            "repeat_occurrences": len(occurrences) - len(inside) - len(outside),
            "verified_nullable_occurrence_positions": positions,
            "appropriation_control_positions": (len(controls) - 2) * len(LANES),
            "scope_total_positions": 2 * len(LANES),
        },
        "sidecar_artifact_sha256": {
            name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in NAMES[:4]
        },
    }
    (destination / NAMES[4]).write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publisher_pdf", type=Path, help="Exact registered Comptroller PDF")
    parser.add_argument("destination", type=Path, nargs="?", default=DEFAULT)
    args = parser.parse_args()
    receipt = build(args.publisher_pdf, args.destination)
    print(json.dumps(receipt["coverage"], sort_keys=True))


if __name__ == "__main__":
    main()
