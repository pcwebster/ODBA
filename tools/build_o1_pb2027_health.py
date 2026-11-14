"""Build the isolated PB27 O-1 health-account pilot from indexed source cells."""
from collections import Counter
import argparse
import csv
from html import unescape
import io
import json
from pathlib import Path
import re

DEFAULT = Path(__file__).resolve().parents[1] / "data/o1/pb2027_health"
URL = "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_o1.pdf"
FIELDS = (
    (2025, "actuals_as_reported", "FY 2025 Actuals"),
    (2026, "discretionary_enacted", "FY 2026 Discretionary Enacted"),
    (2026, "pl_119_21_spend_plan", "FY 2026 PL 119-21 Spend Plan"),
    (2026, "published_total", "FY 2026 Total"),
    (2027, "discretionary_requested", "FY 2027 Discretionary Request"),
    (2027, "mandatory_requested", "FY 2027 Mandatory Request"),
    (2027, "published_total", "FY 2027 Total"),
)
HEADER = ("submission_fy", "funding_fy", "source_column_key", "source_column",
          "appropriation_account", "budget_activity", "o1_line_code", "detail_code",
          "row_grain", "source_row_title", "classification", "amount",
          "value_status", "unit", "measure", "printed_page", "source_url",
          "source_alignment")


def amount(cell):
    if not cell:
        return None
    if not re.fullmatch(r"-?(?:0|[1-9]\d{0,2})(?:,\d{3})*", cell):
        raise ValueError(f"unexpected formatted amount: {cell!r}")
    return int(cell.replace(",", ""))


def read_rows(path):
    src = json.loads(path.read_text(encoding="utf-8"))
    if src["source_url"] != URL or [p["page"] for p in src["pages"]] != [49, 50, 51]:
        raise ValueError("wrong exhibit or pages")
    rows = []
    activity = None
    for page in src["pages"]:
        p = page["page"]
        account = "0146D" if p == 51 else "0130D"
        table = [[unescape(cell[2]) for cell in r] for r in page["rows"]]
        if table[0][-7:] != [s for _, _, s in FIELDS]:
            raise ValueError("unexpected header or column order")
        if p == 51:
            activity = None
        for cells in table[1:]:
            title = cells[0]
            line = detail = security = ""
            alignment = "indexed_cell_columns"
            if title.startswith("Budget Activity "):
                activity = re.fullmatch(r"Budget Activity (\d{2}):.*", title)[1]
                if any(cells[1:]):
                    raise ValueError("activity label has data")
                continue
            if p == 50 and cells == ["0130D", "Combat and Operational Medicine Program"] + [""] * 8:
                # Account name repeated at top of continuation.
                continue
            if title.startswith("Total"):
                grain = "activity_total" if title.startswith("Total, BA ") else "account_total"
                if p == 51:
                    if cells[1:7] != [""] * 6 or cells[-3:] != ["22,175,472", "", "22,175,472"]:
                        raise ValueError("unexpected 0146D subtotal cells")
                    cells = ["", "", "", ""] + cells[-3:]
                    alignment = "summary_columns_corrob_by_official_justification"
                else:
                    cells = cells[-7:]
            else:
                grain = "detail"
                if p == 49:
                    acct, line, detail, title = title.split(maxsplit=3)
                    security, *cells = cells[1:]
                elif p == 50:
                    acct, line, text, security, *cells = cells
                    detail, title = text.split(maxsplit=1)
                else:
                    acct, line, detail, title, security, *fragment = cells
                    if (line, detail, title, fragment) != ("010", "2", "Private Sector Care",
                           ["", "", "22,175,472", "", "22,175,472"]):
                        raise ValueError("unexpected 0146D detail cells")
                    # The index omits two empty leading monetary cells on this detail row.
                    # The official companion justification independently establishes the
                    # three FY27 column positions and that FY25/FY26 are not reported.
                    cells = ["", "", "", "", *fragment[-3:]]
                    alignment = "omitted_index_blanks_corrob_by_official_justification"
                if acct != account or not re.fullmatch(r"\d{3}", line) or not security:
                    raise ValueError("invalid detail identity")
            if len(cells) != 7:
                raise ValueError("incomplete amount columns")
            if grain == "activity_total" and not title.startswith(f"Total, BA {activity}:"):
                raise ValueError("subtotal labels do not bind to the active activity")
            if grain != "account_total" and activity is None:
                raise ValueError("missing activity scope")
            rows.append((p, account, activity if grain != "account_total" else "",
                         line, detail, grain, title, security, alignment, tuple(map(amount, cells))))
    if Counter(r[5] for r in rows) != {"detail": 20, "activity_total": 4, "account_total": 2}:
        raise ValueError("unexpected slice coverage")
    if len({r[1:6] for r in rows}) != len(rows):
        raise ValueError("duplicate identity")
    return rows


def reconcile(rows):
    audit = []
    def check(p, account, activity, kind, i, result, inputs):
        if result is None or not any(x is not None for x in inputs):
            if result is not None or any(x is not None for x in inputs):
                raise ValueError(f"missing side of check: {kind}, {account}, {activity}, {i}")
            return
        computed = sum(x for x in inputs if x is not None)
        delta = computed - result
        if delta:
            raise ValueError(f"failed check: {kind}, {account}, {activity}, {i}, {delta}")
        fy, key, _ = FIELDS[i]
        audit.append((p, account, activity, kind, fy, key, computed, result, delta))
    for p, a, b, l, d, g, t, s, align, v in rows:
        for total, pair in [(3,(1,2)),(6,(4,5))]:
            check(p,a,b,f"column_total:{g}:{l}",total,v[total],[v[k] for k in pair])
        if g == "detail":
            continue
        child = [r[-1] for r in rows if r[1] == a and (
            (g == "activity_total" and r[2] == b and r[5] == "detail") or
            (g == "account_total" and r[5] == "activity_total"))]
        for i, v_i in enumerate(v):
            check(p, a, b, g, i, v_i, [x[i] for x in child])
    return audit


def encode(fields, rows):
    f = io.StringIO(newline="")
    w = csv.writer(f, lineterminator="\n")
    w.writerow(fields)
    w.writerows(rows)
    return f.getvalue().encode("utf-8")


def build(source):
    rows = read_rows(source)
    audit = reconcile(rows)
    fact = []
    for p, a, b, l, d, g, t, s, align, vals in rows:
        for (fy, key, label), v in zip(FIELDS, vals):
            fact.append((2027, fy, key, label, a, b, l, d, g, t, s, v,
                         "reported" if v is not None else "not_reported", "USD thousands",
                         "Total Obligational Authority", p, URL, align))
    if len(fact) != 182:
        raise ValueError("wrong observation count")
    return {"observations.csv": encode(HEADER, fact),
            "reconciliation.csv": encode(("printed_page", "appropriation_account", "budget_activity",
                "check_kind", "funding_fy", "source_column_key", "calculated_nonblank_sum",
                "published_total", "difference_usd_thousands"), audit)}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=DEFAULT / "source_cells.json")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out-dir",type=Path)
    mode.add_argument("--check",type=Path)
    a = p.parse_args()
    outputs = build(a.source)
    if a.check:
        for name, content in outputs.items():
            if (a.check/name).read_bytes() != content:
                raise SystemExit(f"Output mismatch: {name}")
    else:
        a.out_dir.mkdir(parents=True, exist_ok=True)
        for name, content in outputs.items():
            (a.out_dir/name).write_bytes(content)
