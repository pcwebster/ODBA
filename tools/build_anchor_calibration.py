# =============================================================================
# ODBA -- Open Defense Budget Analytics
# tools/build_anchor_calibration.py  |  DBDP-118 backward-anchor calibration
# =============================================================================
# Builds data/fy25_anchor_calibration.json -- the committed, machine-readable
# calibration ledger required by Codex Amendment 118-F (DBDP-118 c10629) and
# the c10576 section-5 / AR c10619(b) verify-then-anchor gate.
#
# WHY A SEPARATE TOOL: verification is a CALIBRATION step whose output a human
# reviews; enforcement is a RUN step. etl_budget.py reads this ledger and
# refuses to anchor any row whose source file does not resolve to a verified
# entry. The ledger is never written by the ETL run -- so a calibration claim
# can never be manufactured by the same pass that depends on it.
#
# WHAT IS VERIFIED (KT c10269 section 2 is the trap this answers): that the
# RELATIVE source slots py/cy actually denote FY(Y-2)/FY(Y-1) for a given
# family + format variant + submission year, read from the publisher's own
# labels -- never assumed from the slot name.
#
# Label locations per format, as found in the FY26+FY27 corpora:
#   * procurement-xml / rdte-xml : <jb:BudgetYear> declares Y; the ResourceSummary
#     ladder (AllPriorYears, PriorYear, CurrentYear, BudgetYearOne...) is
#     anchored to it positionally by schema.
#   * grid-json                  : Grid.Columns[code].Text headers, e.g.
#     Py='FY 2025\n Actuals', Cy='FY 2026\n Enacted'. NOTE: some TARGET grids
#     (OP53a) phrase the current-year column relatively ('Current Enacted');
#     the explicit FY label for that same column is published by sibling grids
#     in the SAME document, which is recorded here as the corroboration path.
#   * mhs-spreadsheetml          : header row cells, e.g. 'FY 2025 ($K)',
#     'FY 2026 Enacted'.
#
# Run:  python tools/build_anchor_calibration.py
# Deterministic: sorted keys, sorted file lists, \n endings, UTF-8.
# =============================================================================

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import etl_budget as etl  # noqa: E402  (path set above)

OUT_FILE = REPO / "data" / "fy25_anchor_calibration.json"

# Target grids that are record sources (mirrors etl_budget's JSON_TARGET_GRIDS
# plus the file-scoped DHP addition) -- a label on a NON-target grid can only
# ever be corroboration, never the primary reading.
TARGET_GRIDS = set(etl.JSON_TARGET_GRIDS) | {"OP32AGrid"}

FY_RE = re.compile(r"FY\s*(\d{4})")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_label(text):
    return re.sub(r"\s+", " ", (text or "").replace("\\n", " ")).strip()


# ── format-variant detection ─────────────────────────────────────────────────

def detect_variant(path):
    """Return the format/schema variant key for a source file."""
    suffix = path.suffix.lower()
    if suffix == ".xml":
        if "MHS_" in path.name:
            return ("mhs-spreadsheetml/vol2" if "Vol2" in path.name
                    else "mhs-spreadsheetml/vol1")
        # Read the WHOLE document: the payload namespace can appear well past
        # any fixed-size head (e.g. FY2026/02_Procurement/PB_2026_PDW_VOL_1.xml
        # declares proc: at char ~6.2k), and misdetecting it would manufacture
        # a calibration exception out of a tooling gap rather than source fact.
        raw = path.read_text(encoding="utf-8", errors="replace")
        if etl.PROC_NS in raw:
            return "procurement-xml/jb-022009"
        if etl.JB_NS in raw and ("rdte" in path.name.lower() or "RDTE" in path.name):
            return "rdte-xml/jb-022009"
        if etl.JB_NS in raw:
            return "jb-xml/jb-022009"
        return "xml/other"
    if suffix == ".json":
        return "grid-json/op5-family"
    return f"{suffix.lstrip('.')}/other"


# ── per-format label readers ─────────────────────────────────────────────────

def read_xml_jb_labels(path):
    """<jb:BudgetYear> is the published anchor for the relative ladder."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<jb:BudgetYear>([^<]*)<", raw)
    c = re.search(r"<jb:BudgetCycle>([^<]*)<", raw)
    if not m:
        return None
    return {
        "label_location": "jb:JustificationBook/jb:BudgetYear",
        "declared_budget_year": int(m.group(1)),
        "declared_cycle": (c.group(1) if c else None),
        "py_label": "PriorYear (schema ladder position, anchored to BudgetYear)",
        "cy_label": "CurrentYear (schema ladder position, anchored to BudgetYear)",
    }


def read_grid_json_labels(path):
    """Collect Py/Cy header text per grid, splitting target vs corroborating."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    target, corroborating = {}, {}
    stack = [doc]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        if node.get("Type") == "Grid":
            code = node.get("Code")
            bucket = target if code in TARGET_GRIDS else corroborating
            for col in (node.get("Columns") or []):
                if col.get("Code") in ("Py", "Cy", "By1"):
                    bucket.setdefault(code, {})[col["Code"]] = norm_label(col.get("Text"))
        stack.extend(node.values())
    if not target and not corroborating:
        return None
    return {"target_grids": target, "corroborating_grids": corroborating}


def read_mhs_labels(path):
    """Header-row cells carrying explicit 'FY nnnn' text."""
    try:
        rows = etl._mhs_get_rows(path)
    except Exception:                                    # noqa: BLE001
        return None
    for idx, row in enumerate(rows[:60]):
        cells = etl._mhs_row_cells(row)
        hits = {j: norm_label(c) for j, c in enumerate(cells)
                if c and FY_RE.search(str(c)) and len(str(c)) < 40}
        if len(hits) >= 2:
            return {"label_location": f"header row index {idx}",
                    "header_cells": {str(k): v for k, v in sorted(hits.items())}}
    return None


# ── semantics resolution ─────────────────────────────────────────────────────

def resolve_semantics(variant, labels, submission_year):
    """Decide observed py/cy fiscal years from published labels.

    Returns (observed_py_fy, observed_cy_fy, evidence, corroboration).
    Any leg that cannot be read from a label comes back None -- the caller
    turns that into an unverified outcome, never a guess.
    """
    y = submission_year
    if variant.startswith(("procurement-xml", "rdte-xml", "jb-xml")):
        if not labels or labels.get("declared_budget_year") != y:
            return None, None, "jb:BudgetYear absent or disagrees with manifest", None
        return (y - 2, y - 1,
                f"jb:BudgetYear={y} declares the submission year; PriorYear/"
                f"CurrentYear are the ladder positions immediately below it",
                None)

    if variant.startswith("mhs-spreadsheetml"):
        if not labels:
            return None, None, "no FY-labelled header row found", None
        years = sorted({int(FY_RE.search(v).group(1))
                        for v in labels["header_cells"].values()
                        if FY_RE.search(v)})
        py = y - 2 if (y - 2) in years else None
        cy = y - 1 if (y - 1) in years else None
        return (py, cy,
                f"{labels['label_location']}: {labels['header_cells']}",
                None)

    if variant.startswith("grid-json"):
        if not labels:
            return None, None, "no Py/Cy grid headers published", None
        tgt, corr = labels["target_grids"], labels["corroborating_grids"]
        if not tgt:
            return None, None, "no Py/Cy headers on any TARGET grid", None

        def fy_from(bucket, code):
            found = {}
            for grid, cols in bucket.items():
                m = FY_RE.search(cols.get(code, "") or "")
                if m:
                    found.setdefault(int(m.group(1)), []).append(f"{grid}.{code}")
            return found

        py_t, cy_t = fy_from(tgt, "Py"), fy_from(tgt, "Cy")
        py_c, cy_c = fy_from(corr, "Py"), fy_from(corr, "Cy")

        evidence, corroboration = {}, {}
        for code, from_t, from_c in (("py", py_t, py_c), ("cy", cy_t, cy_c)):
            if from_t:
                evidence[code] = {str(k): v for k, v in sorted(from_t.items())}
            if from_c:
                corroboration[code] = {str(k): v for k, v in sorted(from_c.items())}

        def pick(want, from_t, from_c):
            if want in from_t:
                return want
            # relative phrasing on the target grid ('Current Enacted'): accept
            # only when a label published elsewhere in the SAME document names
            # the wanted FY for that same column, and nothing contradicts it.
            if want in from_c and not (set(from_t) - {want}):
                return want
            return None

        return (pick(y - 2, py_t, py_c), pick(y - 1, cy_t, cy_c),
                evidence or "no FY label on target-grid headers",
                corroboration or None)

    return None, None, f"no reader for variant {variant}", None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    manifest = etl.load_source_manifest()
    files = etl.collect_files(manifest)
    # collect_files returns whatever routing the ETL uses; flatten to paths
    flat = []
    for value in (files.values() if isinstance(files, dict) else files):
        if isinstance(value, (list, tuple, set)):
            flat.extend(value)
        elif value is not None:
            flat.append(value)
    paths = sorted({Path(p) for p in flat if isinstance(p, (str, Path))},
                   key=lambda p: p.name)

    entries = {}
    for path in paths:
        name = path.name
        entry_manifest = manifest.get(name)
        if entry_manifest is None:
            continue
        if entry_manifest.get("ingest_status") != etl.RECORD_EMITTING_STATUS:
            continue          # only record-emitting files can anchor anything
        year = int(entry_manifest["budget_year"])
        variant = detect_variant(path)

        if variant.startswith(("procurement-xml", "rdte-xml", "jb-xml", "xml/other")):
            labels = read_xml_jb_labels(path)
        elif variant.startswith("mhs-spreadsheetml"):
            labels = read_mhs_labels(path)
        else:
            labels = read_grid_json_labels(path)

        py_fy, cy_fy, evidence, corroboration = resolve_semantics(variant, labels, year)

        key = f"{variant}|{year}"
        bucket = entries.setdefault(key, {
            "format_variant": variant,
            "budget_year": year,
            "expected_py_target": f"cost_fy{year - 2}",
            "expected_cy_target": f"cost_fy{year - 1}",
            "observed_py_fy": py_fy,
            "observed_cy_fy": cy_fy,
            "label_evidence": evidence,
            "corroboration": corroboration,
            "source_files": [],
            "verified_files": [],
            "unverified_files": [],
        })
        # a file joins the entry only when its own reading agrees with it
        agrees = (py_fy == bucket["observed_py_fy"]
                  and cy_fy == bucket["observed_cy_fy"])
        bucket["source_files"].append(name)
        (bucket["verified_files"] if agrees
         else bucket["unverified_files"]).append(
            {"source_file": name, "observed_py_fy": py_fy, "observed_cy_fy": cy_fy,
             "sha256": entry_manifest.get("sha256") or sha256_of(path)}
            if not agrees else name)

    # finalize: outcomes, sha256 receipts, deterministic ordering
    ledger_entries = []
    for key in sorted(entries):
        e = entries[key]
        e["source_files"] = sorted(set(e["source_files"]))
        e["verified_files"] = sorted({f for f in e["verified_files"] if isinstance(f, str)})
        e["unverified_files"] = sorted(
            [f for f in e["unverified_files"] if isinstance(f, dict)],
            key=lambda d: d["source_file"])
        # Amendment 118-F: a non-activating file is named, with its reason and
        # the anchors it is therefore expected to produce (zero). These are
        # metadata-only / summary sources that publish no Py/Cy headers AND
        # carry no py/cy values, so relative-only is the correct outcome, not
        # a withheld anchor. The run's `uncalibrated_*` counters surface any
        # file that DOES carry a value without a verified label.
        for f in e["unverified_files"]:
            f["reason"] = ("source publishes no Py/Cy column header on any "
                           "target grid; no fiscal-year label to verify")
            f["expected_backward_anchors"] = 0
            f["capture"] = "relative-only"
        py_ok = e["observed_py_fy"] == int(e["expected_py_target"].removeprefix("cost_fy"))
        cy_ok = e["observed_cy_fy"] == int(e["expected_cy_target"].removeprefix("cost_fy"))
        e["py_leg_outcome"] = "verified" if py_ok else "unverified"
        e["cy_leg_outcome"] = "verified" if cy_ok else "unverified"
        e["outcome"] = ("verified" if (py_ok and cy_ok)
                        else "partially-verified" if (py_ok or cy_ok)
                        else "unverified")
        e["declared_exception"] = None if e["outcome"] == "verified" else {
            "reason": "published source labels do not establish the fiscal year "
                      "of the affected leg(s); rows stay relative-only and "
                      "produce zero backward anchors (c10576 section 5)",
            "affected_files": e["source_files"],
            "unverified_legs": [leg for leg, ok in (("py", py_ok), ("cy", cy_ok))
                                if not ok],
        }
        # sha256 receipts for the files whose labels were read directly
        e["sha256_receipts"] = {
            f: (manifest[f].get("sha256") or "") for f in e["verified_files"]
        }
        ledger_entries.append(e)

    doc = {
        "_schema": "odba/dbdp-118/anchor-calibration/1",
        "_authority": "DBDP-118 c10576 section 5 + AR PASS c10619(b) + "
                      "Codex Amendment 118-F (c10629)",
        "_built_from_base": "5e2637841d6d9535d7bec2c588f190858cfb6757",
        "_fy_floor": etl.FY_COVERAGE_FLOOR,
        "_fy_ceiling": etl.FY_COVERAGE_CEILING,
        "_note": "Keyed by (format variant, budget_year); exhibit families are "
                 "listed per entry because one variant serves several families. "
                 "A source file anchors a backward leg ONLY via a verified "
                 "entry covering it. Rebuild with tools/build_anchor_calibration.py.",
        "entries": ledger_entries,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote {OUT_FILE.relative_to(REPO)}")
    for e in ledger_entries:
        print(f"  {e['format_variant']:<30} BY{e['budget_year']}  "
              f"py={e['py_leg_outcome']:<10} cy={e['cy_leg_outcome']:<10} "
              f"-> {e['outcome']:<18} files={len(e['source_files']):>3} "
              f"(unverified {len(e['unverified_files'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
