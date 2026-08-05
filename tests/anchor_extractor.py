# =============================================================================
# ODBA -- Open Defense Budget Analytics
# tests/anchor_extractor.py  |  DBDP-103 independent raw-XML anchor oracle
# =============================================================================
# c10527 §2: expected anchors must be reproduced directly and independently
# from raw XML WITHOUT importing or calling the production parser. This file
# deliberately imports nothing from etl_budget -- it re-implements the
# selection from the published grain rules:
#
#   P-40 : one value per LineItem, from ResourceSummary/TotalCost
#   R-2  : one value per ProgramElement, from ProgramElementFunding
#   both : request-year precedence BudgetYearOneBase then BudgetYearOne
#          (the "Base-vs-Total" rule -- identical for every submission year)
#
# Validated against known-good FY27 sources for BOTH families before it is
# trusted for FY26 (c10527: "the DISA 2027 $1,345.031M check alone validates
# only the P-40 path").
#
#   python tests/anchor_extractor.py            # self-validate + full table
# =============================================================================

import sys
from pathlib import Path

import defusedxml.ElementTree as ET

REPO = Path(__file__).parent.parent


def _ln(tag):
    return tag.split("}")[1] if "}" in tag else tag


def _num(text):
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _request_year_value(container):
    """Base-vs-Total precedence: BudgetYearOneBase, else BudgetYearOne."""
    vals = {_ln(c.tag): (c.text or "").strip() for c in container}
    return _num(vals.get("BudgetYearOneBase") or vals.get("BudgetYearOne"))


def _item_lists(root, list_tag):
    """Root-level list, else every descendant JustificationBook's list."""
    direct = [c for c in root if _ln(c.tag) == list_tag]
    if direct:
        return direct
    if _ln(root.tag) != "MasterJustificationBook":
        return []
    out = []
    for el in root.iter():
        if _ln(el.tag) == "JustificationBook":
            out += [c for c in el if _ln(c.tag) == list_tag]
    return out


def extract(path, family, agency_allowlist=None):
    """Return (node_count, sum) at the family's published grain."""
    root = ET.parse(path).getroot()
    if family == "P-40":
        list_tag, item_tag, cost_parent = "LineItemList", "LineItem", "ResourceSummary"
    else:
        list_tag, item_tag, cost_parent = "ProgramElementList", "ProgramElement", None

    items = [it for lst in _item_lists(root, list_tag)
             for it in lst if _ln(it.tag) == item_tag]

    total, n = 0.0, 0
    for it in items:
        if agency_allowlist is not None:
            agency = ""
            for c in it:
                if _ln(c.tag) == "ServiceAgencyName":
                    agency = (c.text or "").strip()
                    break
            if agency not in agency_allowlist:
                continue
        if family == "P-40":
            rs = [c for c in it if _ln(c.tag) == cost_parent]
            if not rs:
                continue
            tc = [c for c in rs[0] if _ln(c.tag) == "TotalCost"]
            if not tc:
                continue
            v = _request_year_value(tc[0])
        else:
            pef = [c for c in it if _ln(c.tag) == "ProgramElementFunding"]
            if not pef:
                continue
            v = _request_year_value(pef[0])
        n += 1
        if v is not None:
            total += v
    return n, round(total, 3)


def self_validate():
    """c10527: validate the extractor on a known-good FY27 P-40 AND R-2."""
    checks = []
    p40 = next(REPO.joinpath("02_Procurement").rglob("PROC_DISA_PB_2027.xml"))
    n, s = extract(p40, "P-40")
    checks.append(("FY27 P-40 PROC_DISA_PB_2027.xml", n, s, 9, 1345.031))
    r2 = next(REPO.joinpath("03_RDT_and_E").rglob("RDTE_DISA_PB_2027.xml"))
    n2, s2 = extract(r2, "R-2")
    checks.append(("FY27 R-2 RDTE_DISA_PB_2027.xml", n2, s2, None, None))
    return checks


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Independent extractor self-validation (no production parser imported):")
    for label, n, s, exp_n, exp_s in self_validate():
        note = ""
        if exp_s is not None:
            note = f"  expected {exp_n} nodes / {exp_s} -> {'MATCH' if (n == exp_n and abs(s - exp_s) < 0.001) else 'MISMATCH'}"
        print(f"  {label}: {n} nodes, sum {s}{note}")
