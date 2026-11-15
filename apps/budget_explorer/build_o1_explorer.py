"""Stage-safe O-1 inputs for the offline Budget Explorer; stdlib only."""
import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

COMMIT = "b9ea2eba7c65cb40b4086777a59271bde04af880"
SNAPSHOT_HASHES = {'data/o1/pb2025_candidate/detail_candidate.csv': '59d41011d91834d2a36b85c7569ebfe9e8d0551a0e68e359b304f4d6828ef9b6',
 'data/o1/pb2025_candidate/headline_controls.csv': 'adf0c9f000d4ac76f31286aad13b4d6b5c050462c9521eacd3c8e113b85a12a0',
 'data/o1/pb2025_candidate/pdf_detail_reference.json': '4215b8a9839127f34422bf55a01803beda644184f5e0147abd2bad2223edc6ce',
 'data/o1/pb2025_candidate/provenance.json': '0e0cde20009e1ac5c0d7e0be91487dcedb4d7b156a772f88e9b3e83c0c3fd4b9',
 'data/o1/pb2026_candidate/detail_candidate.csv': '639215a776feb9f259d8a4709b55253400158c508c9cdf1501676a63d000b783',
 'data/o1/pb2026_candidate/fy25_nonadditive_triplets.csv': '041bd58cbd9e0e18baf5180d7991ec038b5c62126a5147081a336c2104348f7a',
 'data/o1/pb2026_candidate/headline_controls.csv': 'b62a7916c914b298b3da880c289d28c4e31ef13d21bf9ef8412d02c243ccb539',
 'data/o1/pb2026_candidate/pdf_detail_reference.json': '3a0ec8ed65f8e09c76ba6ddc175e65026f3d9d4c008df09112a4ad3a657fd25d',
 'data/o1/pb2026_candidate/provenance.json': '0c51bb9feed75202686567d29dbe1151e061a5b4b805ac2af7a1f8bfeb1a04b6',
 'data/o1/pb2027_candidate/detail_candidate.csv': 'd1b128301bd734432019243cd652fe1ec09bd19e28ab90418cb58f38ea668411',
 'data/o1/pb2027_candidate/headline_controls.csv': '2d673a102ed3b725a6642777a7390f075c458de31c474421a6e721832fdd2b9a',
 'data/o1/pb2027_candidate/pdf_detail_reference.json': '6fea2b31c7e99ac65a704e6b5034f37b51ef0f28a440084d425a247b33975bc1',
 'data/o1/pb2027_candidate/provenance.json': '7efeb408b3db35d55ed33c16f0487e76cb1b09c08e1d56a491c7137d47273663'}
UNIT = "USD thousands"
MEASURE = "Total Obligational Authority"
DEFAULT_SCOPE = "om_title_plus_indefinite"
LANES = {
    2025: [
        ("fy23_actuals_as_reported", "Actuals as reported", "actual", True),
        ("fy24_pb_request_cr_adjusted", "CR-adjusted request", "cr_adjusted_request", True),
        ("fy25_request", "President’s Budget request", "request", True),
    ],
    2026: [
        ("fy24_actuals_as_reported", "Actuals as reported", "actual", True),
        ("fy25_enacted", "Enacted", "enacted", True),
        ("fy25_supplemental", "Supplemental", "supplemental", True),
        ("fy25_published_total", "Published total (enacted/supplemental)", "published_total", True),
        ("fy26_discretionary_request", "Discretionary request", "request", True),
        ("fy26_reconciliation_request", "Reconciliation request", "reconciliation_request", True),
        ("fy26_published_total", "Published request total", "published_total", True),
    ],
    2027: [
        ("fy25_printed_actuals_lane", "Actuals as reported (printed lane)", "actual", True),
        ("fy25_workbook_actuals", "Workbook actuals", "workbook_actual", False),
        ("fy25_workbook_reconciliation", "Workbook reconciliation", "workbook_reconciliation", False),
        ("fy25_workbook_total", "Workbook total (overlaps printed actuals)", "workbook_total", False),
        ("fy26_discretionary_enacted", "Discretionary enacted", "enacted", True),
        ("fy26_pl11921_spend_plan", "P.L. 119-21 spend plan", "spend_plan", True),
        ("fy26_published_total", "Published total (enacted/spend plan)", "published_total", True),
        ("fy27_discretionary_request", "Discretionary request", "request", True),
        ("fy27_mandatory_request", "Mandatory request", "mandatory_request", True),
        ("fy27_published_total", "Published request total", "published_total", True),
    ],
}
LABELS = {
    DEFAULT_SCOPE: "O&M Title + Indefinite Accounts",
    "om_title": "O&M Title",
    "indefinite_accounts": "Indefinite Accounts",
    "army_accounts": "Army accounts",
    "navy_accounts": "Navy accounts",
    "air_force_accounts": "Air Force accounts",
    "defense_wide_accounts": "Defense-Wide accounts",
    "transfer_accounts": "Transfer accounts",
    "miscellaneous_accounts": "Miscellaneous accounts",
}
EXPECTED = {2025: (434, 27, 4), 2026: (407, 56, 5), 2027: (397, 42, 5)}
FY25_MILESTONES = [
    "pb25.fy25_request", "pb26.fy25_published_total", "pb27.fy25_printed_actuals_lane"
]


def require(value, label):
    if not value:
        raise ValueError(label)


def money(value):
    if value == "":
        return None
    require(isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value),
            f"Invalid signed USD-thousands cell: {value!r}")
    number = int(value)
    require(abs(number) < 2**53, "Monetary cell exceeds exact JS integer range")
    return number


def anchor(url, source, page, offset):
    u, s = urlsplit(url), urlsplit(source)
    require(u.scheme == "https"
            and u.netloc in {"comptroller.war.gov", "comptroller.defense.gov"}
            and u.path == s.path and not (u.query or u.fragment), f"Invalid official URL {url}")
    return f"{url}#page={page + offset}"


def csv_rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def snapshot_reader(repo):
    def load(path):
        return subprocess.check_output(["git", "-C", str(repo), "show", f"{COMMIT}:{path}"])

    return load


def build_o1(repo: Path):
    """Read the exact Git tree, independent of working-copy modifications."""
    return build_evidence(snapshot_reader(repo))


def build_evidence(load):
    lanes, details, controls = [], [], []
    provenance = {}
    for year, specs in LANES.items():
        v = f"pb{year % 100}"
        prefix = f"data/o1/pb{year}_candidate/"
        evidence_hashes = {}

        def read(name):
            path = prefix + name
            raw = load(path)
            evidence_hashes[path] = hashlib.sha256(raw).hexdigest()
            return raw

        prov = json.loads(read("provenance.json"))
        ref = json.loads(read("pdf_detail_reference.json"))
        require(
            evidence_hashes[prefix + "pdf_detail_reference.json"] == prov["pdf_reference_sha256"]
            and prov["pdf_sha256"] == ref["source_pdf_sha256"]
            and prov["submission_fy"] == ref["submission_fy"] == year,
            f"{v}: invalid merged provenance",
        )
        d_count, c_count, offset = EXPECTED[year]
        primary = [name for name, _, _, pub in specs if pub]
        require(primary == ref["columns"], f"{v}: official column mapping mismatch")
        lane_ids = {name: f"{v}.{name}" for name, *_ in specs}
        for name, label, kind, pub in specs:
            lanes.append(dict(id=lane_ids[name], vintage=v, fy=2000 + int(name[2:4]),
                              label=label, kind=kind, primary=pub))
        groups = {
            **prov["military_department_controls"],
            **prov.get("other_controls", {}),
            **prov.get("printed_account_group_controls", {}),
        }
        rows = csv_rows(read("detail_candidate.csv"))
        pub_controls = csv_rows(read("headline_controls.csv"))
        require(
            len(rows) == len(ref["rows"]) == ref["row_count"] == d_count
            and len(pub_controls) == c_count,
            f"{v}: missing/excess evidence rows",
        )
        exceptions = {}
        if year == 2026:
            for exc in csv_rows(read("fy25_nonadditive_triplets.csv")):
                loc = exc["workbook_locator"]
                require(loc not in exceptions and exc["status"] ==
                        "matched_published_nonadditive_triplet", "Invalid exception locator/status")
                exceptions[loc] = exc
            require(len(exceptions) == 6, "Not all six printed PB26 exceptions")
        pdf_by_account_line = defaultdict(list)
        for row in ref["rows"]:
            pdf_by_account_line[row["account"], row["line"] or ""].append(row)

        seen_ids, seen_pdf, used_exceptions, seen_controls = set(), set(), set(), set()
        nullable, negative, zero = Counter(), Counter(), Counter()
        scoped_amounts = defaultdict(list)
        scoped_accounts = defaultdict(set)
        for row in rows:
            require(row["row_grain"] == "detail" and row["unit"] == UNIT
                    and row["measure"] == MEASURE and row["submission_fy"] == str(year),
                    f"{v}: invalid detail metadata")
            account, ba, line, bli = [row[key] for key in
                                      ("account_raw", "activity_raw", "line_raw", "subactivity_raw")]
            key = (v, account, ba, line)
            row_id = ":".join(key)
            require(row_id not in seen_ids, f"Duplicate detail identity: {row_id}")
            seen_ids.add(row_id)
            candidates = [found for found in pdf_by_account_line[account, line]
                          if found["activity"] is None or ba == found["activity"]]
            require(len(candidates) == 1, f"Ambiguous or absent PDF row: {row_id}")
            pdf = candidates[0]
            pdf_key = (pdf["account"], pdf["activity"], pdf["line"])
            require(pdf_key not in seen_pdf, f"Repeated PDF row: {row_id}")
            seen_pdf.add(pdf_key)
            title = row["line_title_workbook"] if year != 2027 else (
                row["line_title"] if row["source_kind"] == "workbook_mirror" else None)
            published_title = pdf["line_title"]
            require(
                published_title == row.get("line_title_printed", row.get("line_title"))
                and row["classification_raw"] == pdf["classification"]
                and (pdf["subactivity"] is None or pdf["subactivity"] == bli),
                f"{row_id}: official metadata mismatch",
            )
            vals = {name: money(row[name]) for name in lane_ids}
            require([vals[k] for k in primary] == pdf["amounts"],
                    f"{row_id}: official monetary cells mismatch")
            printed, physical = pdf["printed_page"], pdf["pdf_page"]
            require(printed + offset == physical and printed in ref["printed_pages_scanned"],
                    f"{row_id}: invalid detail page")
            qa = []
            if title is not None and published_title != title:
                qa.append("workbook_title_differs")
            if year == 2026:
                loc = row["source_locator"]
                amounts = [vals[k] for k in ("fy25_enacted", "fy25_supplemental", "fy25_published_total")]
                components, published = amounts[:2], amounts[2]
                present = [number for number in components if number is not None]
                differs = (sum(present) if present else None) != published
                require(differs == (loc in exceptions), f"{row_id}: unexpected FY25 non-additivity")
                if differs:
                    exc = exceptions[loc]
                    require(
                        (exc["account_raw"], exc["activity_raw"], exc["line_raw"], int(exc["printed_page"]))
                        == (account, ba, line, printed)
                        and amounts == [money(exc[k]) for k in
                                        ("fy25_enacted", "fy25_supplemental", "fy25_published_total")],
                        f"{row_id}: exception does not match published triplet",
                    )
                    used_exceptions.add(loc)
                    qa.append("pb26_fy25_nonadditive")
            if not line:
                qa.append("blank_line_id")
            for name, number in vals.items():
                if number is None:
                    nullable[name] += 1
                elif number < 0:
                    negative[name] += 1
                elif number == 0:
                    zero[name] += 1
            workbook_suffix = "" if year == 2027 else "_workbook"
            scope = row["scope"]
            require(scope in {"om_title", "indefinite_accounts"}, f"{row_id}: invalid detail scope")
            scopes = [DEFAULT_SCOPE, scope]
            if scope == "om_title":
                scopes.extend(group for group, desc in groups.items() if account in desc["accounts"])
            for group in scopes:
                scoped_accounts[group].add(account)
                for name in primary:
                    value = vals[name]
                    if value is not None:
                        scoped_amounts[group, name].append(value)
            details.append(dict(
                vintage=v, id=row_id, account=account, accountTitle=row["account_title" + workbook_suffix],
                ba=ba, activity=row["activity_title" + workbook_suffix],
                activityGroup=row["activity_group_raw"],
                activityGroupTitle=row["activity_group_title" + workbook_suffix],
                line=line, bli=bli, title=title, publishedTitle=published_title,
                organization=row["organization_raw"], classification=row["classification_raw"],
                scope=scope, scopes=scopes, sourceKind=row["source_kind"],
                sourceRow=row["source_locator"], sourceUrl=row["source_url"],
                amounts={lane_ids[name]: number for name, number in vals.items()},
                page=printed, pdfPage=physical, url=anchor(ref["source_url"], ref["source_url"], printed, offset),
                qaFlags=qa,
            ))
        require(used_exceptions == set(exceptions), "Unmatched PB26 exception")
        require(sum(nullable[k] for k in primary) == ref["blank_cell_count"]
                and d_count * len(primary) - ref["blank_cell_count"] == ref["reported_amount_count"],
                f"{v}: PDF monetary coverage mismatch")

        for group, desc in groups.items():
            require(scoped_accounts[group] == set(desc["accounts"]), f"{v}: incomplete grouped account coverage")
        expectations = {**prov["official_controls"], **{group: desc["amounts"] for group, desc in groups.items()}}
        for ctl in pub_controls:
            scope, name = ctl["scope"], ctl["source_column_key"]
            require(scope in LABELS and name in primary
                    and (scope, name) not in seen_controls, f"{v}: invalid control scope/lane")
            seen_controls.add((scope, name))
            amount = money(ctl["official_amount_usd_thousands"] if year == 2027 else ctl["official_reported"])
            observed = money(ctl["candidate_sum_usd_thousands"] if year == 2027 else ctl["computed"])
            status = "blank_both" if amount is None else "matched_amount"
            summed = scoped_amounts[scope, name]
            require(amount == observed == expectations[scope][primary.index(name)]
                    == (sum(summed) if summed else None) and ctl["status"] == status
                    and money(ctl["difference_usd_thousands"]) == (0 if amount is not None else None),
                    f"{v}: control mismatch: {scope} {name}")
            page = int(ctl["printed_page"])
            require(page in ref["printed_pages_scanned"], f"{v}: invalid control page")
            note = None
            if year == 2026 and name in {"fy25_enacted", "fy25_supplemental", "fy25_published_total"} and scope in {
                "indefinite_accounts", DEFAULT_SCOPE
            }:
                note = "Six official PB26 FY25 Indefinite-account lines have non-additive triplets. Use the published total, not enacted plus supplemental."
            controls.append(dict(scope=scope, lane=lane_ids[name], vintage=v, amount=amount,
                                 status=status, page=page, pdfPage=page + offset,
                                 url=anchor(ctl["source_url"], ref["source_url"], page, offset), note=note))
        require(seen_controls == {(scope, key) for scope in expectations for key in primary},
                f"{v}: incomplete official scope/lane matrix")

        provenance[v] = dict(
            pdfUrl=ref["source_url"], pdfSha256=ref["source_pdf_sha256"], pdfStatus=prov["pdf_status"],
            workbookUrl=prov["workbook_url"], workbookSha256=prov["workbook_sha256"],
            workbookStatus=prov["workbook_status"], detailCount=d_count, controlCount=c_count,
            scannedPrintedPages=ref["printed_pages_scanned"], publishedCellCount=d_count * len(primary),
            publishedBlankCount=ref["blank_cell_count"], verifiedNonAdditiveRowCount=len(used_exceptions),
            detailLaneCounts={lane_ids[k]: dict(rows=d_count, blanks=nullable[k], negative=negative[k],
                                               zero=zero[k]) for k in lane_ids},
            controlCoverage=prov["summary_control_coverage"], inputHashes=evidence_hashes,
        )
    return dict(
        schemaVersion=1, repoCommit=COMMIT, unit=UNIT, measure=MEASURE,
        defaultFY=2025, defaultScope=DEFAULT_SCOPE, defaultMilestones=FY25_MILESTONES,
        lanes=lanes, scopes=[dict(id=k, label=v) for k, v in LABELS.items()],
        controls=controls, detail=details, provenance=provenance,
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path, help="Git checkout or extracted source snapshot")
    cli.add_argument("--snapshot", action="store_true", help="Read the source snapshot files instead of Git blobs")
    cli.add_argument("out", type=Path)
    args = cli.parse_args()
    if args.snapshot:
        def read_snapshot(relative):
            raw = (args.source / relative).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == SNAPSHOT_HASHES[relative],
                    f"Snapshot does not match {COMMIT}: {relative}")
            return raw
        result = build_evidence(read_snapshot)
    else:
        result = build_o1(args.source)
    args.out.write_text(json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Built {len(result['detail'])} detail rows, {len(result['controls'])} published control cells")


if __name__ == "__main__":
    main()
