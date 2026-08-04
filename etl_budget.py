# =============================================================================
# ODBA — Open Defense Budget Analytics
# FY2027 Budget ETL Script
# =============================================================================
# Parses DoD Comptroller budget files and outputs a unified Parquet dataset.
#
# Handles:
#   XML — Procurement (P-1)  :  02_Procurement/
#   XML — RDT&E (R-1)        :  03_RDT_and_E/
#   JSON — O&M (O-1)         :  01_Operation_and_Maintenance/
#   JSON — DWCF (RF-1)       :  06_Defense_Working_Capital_Fund/
#   JSON — DHP               :  09_Defense_Health_Program/
#
# JSON parsing:
#   JSON files parsed at line-item level via Grid/Rows structure.
#   Values in source JSON are in thousands; converted to millions here.
#   Aggregate volume files (OM_Volume1_Part1.json etc.) are skipped to
#   avoid double-counting individual agency files.
#
# Output: output/fact_budget_line_items.parquet
# =============================================================================

import os
import re
import sys
import json
import hashlib
import unicodedata
import defusedxml.ElementTree as ET  # DBDP-39: defense-in-depth against XXE/entity-expansion
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent.resolve()
DATA_DIR     = SCRIPT_DIR
OUTPUT_DIR   = SCRIPT_DIR / "output"
OUTPUT_FILE  = OUTPUT_DIR / "fact_budget_line_items.parquet"
MANIFEST_FILE = SCRIPT_DIR / "data" / "source_manifest.json"
COVERAGE_FILE = SCRIPT_DIR / "data" / "cost_coverage.json"

# ── XML Namespaces ────────────────────────────────────────────────────────────
JB_NS   = "http://www.dtic.mil/comptroller/xml/schema/022009/jb"
PROC_NS = "http://www.dtic.mil/comptroller/xml/schema/20100219/procurement"

# ── Column order (matches Project Charter schema) ────────────────────────────
COLUMNS = [
    "record_id",
    "budget_year", "budget_cycle", "submission_date",
    "service_agency_name", "service_agency_acronym",
    "appropriation_code", "appropriation_name", "appropriation_type",
    "exhibit_type",
    "source_file", "file_format",
    "data_lifecycle_stage",
    "line_item_number", "line_item_title",
    "budget_activity_number", "budget_activity_title",
    "budget_sub_activity_number", "budget_sub_activity_title",
    "program_element",
    "cost_all_prior_years", "cost_prior_year", "cost_current_year",
    "cost_fy2027", "cost_fy2028", "cost_fy2029", "cost_fy2030", "cost_fy2031",
    "cost_units",
    "description", "justification",
    "usaspending_federal_account", "program_activity_code", "treasury_account_symbol",
    # DBDP-94 schema-foundation batch (c10315): appended at end, 34 -> 37
    "funding_type", "funding_type_signal", "data_vintage",
    # DBDP-102 B1-1 (c10365 §2, AR c10430): additive FY2026 request-year
    # figure, appended per the c10315 precedent (37 -> 38). NULL until B1-2
    # ingests FY26 rows; forced 100%-null on FY27 rows by the coverage
    # assertion (2027 coverage excludes it — absolute/relative interlock).
    "cost_fy2026",
]

# ── DBDP-102 cost-column coverage (c10365 §2; AR c10430) ─────────────────────
# Absolute (year-named) cost columns governed by data/cost_coverage.json.
# Structural absence is DECLARED there and VERIFIED uniform by the coverage
# assertion — never inferred from nulls. Relative columns (cost_prior_year,
# cost_current_year, …) keep per-submission semantics and are not governed.
ABSOLUTE_COST_COLUMNS = [
    "cost_fy2026", "cost_fy2027", "cost_fy2028",
    "cost_fy2029", "cost_fy2030", "cost_fy2031",
]

# ── DBDP-94 enums / fixed maps (c10315 §1, c10321; DBDP-86 c10274 grammar) ────
# Six-value lifecycle enum (c10321: Apportioned lands ahead of its data).
LIFECYCLE_STAGES = {
    "Budget Request", "Enacted", "Apportioned",
    "Reprogrammed", "Obligated", "Outlayed",
}
# funding_type domain (DBDP-86 c10274 §1) — all rows NULL until the B5
# classifier lands; no default, ever.
FUNDING_TYPES = {"discretionary", "mandatory", "reconciliation"}
# funding_type_signal grammar (c10274 §2) — enforced by the resident
# TC-FT guards; vacuous while all signals are NULL.
SIGNAL_METHODS     = {"red_text", "section_header", "account_marker", "none_found"}
SIGNAL_CONFIDENCES = {"high", "medium", "low"}
# Fixed confidence map (c10274; revisable ONLY via an approved DBDP-86
# AC amendment per DBDP-85 c10299 A3 — never by implementer judgment).
SIGNAL_CONFIDENCE_MAP = {
    "red_text": "high", "section_header": "high",
    "account_marker": "medium", "none_found": "medium",
}
# method -> funding_type (c10274 §3); account_marker resolves per the
# marker table, which must exist + be validated before that method ships.
SIGNAL_METHOD_VALUE_MAP = {
    "red_text": "reconciliation", "section_header": "mandatory",
    "none_found": "discretionary",
}

# ── JSON aggregate files to skip (they duplicate individual agency files) ─────
JSON_AGGREGATE_FILES = {
    "OM_Volume1_Part1.json",
    "OM_Volume1_Part_2.json",
    "Volume_2.json",
    "O-1_Summary.json",
    "Summary_by_Agency.json",
    "Overview_Exhibit.json",
    "OP-32A_Summary.json",
}

# ── Grid codes that contain line-item data in JSON exhibits ───────────────────
JSON_TARGET_GRIDS = {"Op5Part1", "OP53a"}


# =============================================================================
# Shared Helpers
# =============================================================================

def local_name(tag):
    """Strip XML namespace from a tag: '{ns}foo' → 'foo'."""
    return tag.split("}")[1] if "}" in tag else tag


def elem_text(element, tag, ns=None):
    """Return stripped text of a direct child element, or '' if absent."""
    child = element.find(f"{{{ns}}}{tag}") if ns else element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def to_float(val):
    """Parse a string to float; return None on failure."""
    if not val:
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def make_id(*parts):
    """Generate a short stable record ID from key fields.

    DBDP-72 (via DBDP-94 c10315): 20-hex leading truncation (80 bits) of the
    same MD5 over the same inputs as at cc5a594 — so every new ID's first 12
    hex equal the old ID (the SB3 prefix-equality migration property).
    usedforsecurity=False: non-cryptographic use (Bandit B324 / FIPS).
    """
    key = "|".join(str(p) for p in parts)
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:20]


def norm_key(v):
    """Normalize one discriminator component (DBDP-106 c10434 §3).

    None/NaN -> ""; else str -> Unicode NFC -> collapse internal whitespace
    runs to a single space -> strip. NO case folding (case is content).
    """
    if v is None or (isinstance(v, float) and v != v):
        return ""
    s = unicodedata.normalize("NFC", str(v))
    return re.sub(r"\s+", " ", s).strip()


def make_content_id(*parts):
    """Content-derived record ID for the re-keyed families (DBDP-106 c10434).

    Same hash/output contract as make_id (DBDP-72: MD5 usedforsecurity=False,
    20-hex leading truncation, "|" join) over NORMALIZED components with NO
    positional input of any kind. A component containing "|" is ambiguous key
    material -> hard-fail (c10434 §3; none exist at base — future-data guard).
    """
    normed = [norm_key(p) for p in parts]
    for n in normed:
        if "|" in n:
            print(f"  [FATAL] record-id key component contains '|' — ambiguous "
                  f"key material (DBDP-106 c10434 §3): {n!r} in {normed!r}")
            sys.exit(1)
    key = "|".join(normed)
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:20]


def check_discriminator_collisions(all_records):
    """DBDP-106 c10434 §4 collision rule — hard-fail, no silent collapse.

    Groups the three re-keyed families' records by their normalized
    discriminator tuple (stashed at parse time as _disc_key/_disc_family).
    Any group with >1 row is a genuine natural-key duplicate: print the
    family, source_file, full key tuple, and one identifying line per
    colliding row, then abort. NO ordinal or positional tiebreaker exists
    in any form — a future content-identical pair stops the pipeline and
    names itself (the c10431 latent needs-peter trigger; Peter's call,
    never the code's).
    Returns the list of collision messages (empty = pass) so tests can
    exercise the same callable; main() aborts on non-empty.
    """
    groups = {}
    for r in all_records:
        fam = r.get("_disc_family")
        if fam:
            groups.setdefault((fam, r["_disc_key"]), []).append(r)
    msgs = []
    for (fam, key), rows in groups.items():
        if len(rows) > 1:
            lines = "; ".join(
                f"title={r.get('line_item_title')!r} cost_fy2027={r.get('cost_fy2027')!r}"
                for r in rows)
            msgs.append(f"{fam} collision in {rows[0].get('source_file')}: "
                        f"key={key!r} -> {len(rows)} rows [{lines}]")
    return msgs


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_source_manifest():
    """Load the source acquisition manifest (DBDP-87/48 via c10315;
    DBDP-73 c10479/c10487: sha256 is the manifest's fifth file-grain fact).

    The manifest is the ONLY source for data_vintage, data_lifecycle_stage,
    and sha256 — never datetime.now(), never file mtimes. Every entry MUST
    carry a required sha256 (64 lowercase hex); hard-fails on load if any
    entry is missing it or it is malformed (DBDP-73 c10479: "the manifest
    loader hard-fails on a missing or malformed sha256").
    """
    if not MANIFEST_FILE.exists():
        print(f"  [FATAL] source manifest not found: {MANIFEST_FILE}")
        sys.exit(1)
    with open(MANIFEST_FILE, encoding="utf-8") as fh:
        manifest = json.load(fh)
    bad = [f for f, entry in manifest.items()
           if not SHA256_RE.fullmatch(entry.get("sha256", ""))]
    if bad:
        print(f"  [FATAL] {len(bad)} manifest entry(ies) missing or malformed "
              f"'sha256' (required 64 lowercase hex, DBDP-73): {bad[:5]}"
              f"{' ...' if len(bad) > 5 else ''}")
        sys.exit(1)
    return manifest


def sha256_of(filepath):
    """SHA-256 of a file's on-disk bytes, streamed (DBDP-73 c10479)."""
    h = hashlib.sha256()
    with open(filepath, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file_integrity(filepath, manifest):
    """Pre-parse integrity gate (DBDP-73 c10479/c10487).

    Hard-fails naming the file if it has no manifest entry (missing entry)
    or its on-disk bytes don't match the manifest's committed sha256 (hash
    mismatch) — loud stop in both cases, before the file is parsed. This is
    the ETL's only source of protective power for the integrity control;
    a downstream copy of the hash could never catch anything this gate
    didn't (c10479 §2).
    """
    fname = Path(filepath).name
    entry = manifest.get(fname)
    if entry is None:
        print(f"  [FATAL] integrity: {fname} has no source_manifest.json "
              f"entry — cannot verify before parsing (DBDP-73)")
        sys.exit(1)
    actual = sha256_of(filepath)
    expected = entry["sha256"]
    if actual != expected:
        print(f"  [FATAL] integrity: {fname} sha256 mismatch — "
              f"expected {expected}, got {actual} (DBDP-73 tamper/corruption "
              f"gate — the file's on-disk bytes no longer match the "
              f"committed manifest hash)")
        sys.exit(1)


def load_cost_coverage(path=None):
    """Load data/cost_coverage.json (DBDP-102, c10365 §2).

    Year keys are normalized to int (AC-2). Validates structure STRICTLY:
    a year spec carries exactly the keys "covered" and "excluded" — any
    other key (e.g. a resurrected "positive_leg_exceptions") hard-fails,
    per the DBDP-102 delta ruling on Codex c10455 finding 1: the positive
    leg admits no configured exceptions. If a genuine exception case ever
    arises, that is an ETL Designer design item, not a JSON edit.
    Covered lists ⊆ ABSOLUTE_COST_COLUMNS; every excluded column carries a
    reason note. Hard-fails on a missing or malformed file.
    """
    path = Path(path) if path else COVERAGE_FILE
    if not path.exists():
        print(f"  [FATAL] cost coverage file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    coverage = {}
    for year_key, spec in raw.items():
        year = int(year_key)
        unknown = sorted(set(spec) - {"covered", "excluded"})
        if unknown:
            print(f"  [FATAL] cost_coverage[{year}]: unknown key(s) {unknown} — "
                  f"a year spec carries exactly 'covered' and 'excluded'; the "
                  f"positive leg admits no configured exceptions (c10455 f.1)")
            sys.exit(1)
        covered = spec.get("covered", [])
        excluded = spec.get("excluded", {})
        bad = [c for c in covered if c not in ABSOLUTE_COST_COLUMNS]
        if bad:
            print(f"  [FATAL] cost_coverage[{year}]: covered columns not in "
                  f"ABSOLUTE_COST_COLUMNS: {bad}")
            sys.exit(1)
        missing_reason = [c for c in ABSOLUTE_COST_COLUMNS
                          if c not in covered and not excluded.get(c)]
        if missing_reason:
            print(f"  [FATAL] cost_coverage[{year}]: excluded columns without "
                  f"a reason note: {missing_reason}")
            sys.exit(1)
        coverage[year] = {"covered": covered, "excluded": excluded}
    return coverage


def check_cost_coverage(df, coverage):
    """Coverage assertion (DBDP-102; AC-2 as amended c10387; AR c10430).

    This is the SINGLE callable the production run and any test exercise
    against the same in-memory dataframe (Codex c10382 executable-path rule).
    Returns a list of failure strings; empty list = pass.

    Legs:
      validity — budget_year is non-null, numeric, and integral on EVERY
                 row, so every row belongs to exactly one checked group
                 (c10455 finding 2: null/non-integral years must hard-fail,
                 never escape — manifest hard-fail philosophy);
      closure  — every data year has a coverage entry (coverage may carry
                 future years with no rows yet, e.g. 2026 before B1-2);
      negative — a declared-absent column is 100% null within its year group
                 (structural absence is declared + verified, never inferred);
      positive — a declared-covered column has ≥1 non-null value in its
                 year group (c10430 binding note c: required, not optional;
                 NO configured exceptions — c10455 finding 1). The sanctioned
                 handling for legitimate cases like RF-1 is the per-line-null
                 carve-out below, never a column-level exemption.
    Per-line nulls INSIDE coverage are legal gaps (RF-1 case) — untouched.
    """
    failures = []

    # validity leg — runs first; grouping with bad years would be wrong
    by_num = pd.to_numeric(df["budget_year"], errors="coerce")
    null_rows = df.index[df["budget_year"].isna()]
    if len(null_rows) > 0:
        failures.append(
            f"budget_year validity: {len(null_rows):,} row(s) with null "
            f"budget_year (first row index {null_rows[0]}) — every row must "
            f"belong to exactly one coverage group")
    nonnum_rows = df.index[df["budget_year"].notna() & by_num.isna()]
    if len(nonnum_rows) > 0:
        failures.append(
            f"budget_year validity: {len(nonnum_rows):,} non-numeric "
            f"budget_year value(s) (first row index {nonnum_rows[0]})")
    nonint_rows = df.index[by_num.notna() & (by_num % 1 != 0)]
    if len(nonint_rows) > 0:
        failures.append(
            f"budget_year validity: {len(nonint_rows):,} non-integral "
            f"budget_year value(s) (first row index {nonint_rows[0]}, value "
            f"{df['budget_year'][nonint_rows[0]]!r}) — coverage groups are "
            f"integer fiscal years")
    if failures:
        return failures

    # normalize ONCE; from here every row has exactly one integer year
    # (the group-assignment invariant at the end proves it — no assert,
    # which would vanish under python -O; Bandit B101)
    year_of = by_num.astype(int)
    data_years = sorted(year_of.unique())

    for year in data_years:
        if year not in coverage:
            failures.append(f"closure: budget_year {year} has no cost_coverage entry")
    grouped_total = 0
    for year in data_years:
        grp = df[year_of == year]
        grouped_total += len(grp)
        if year not in coverage:
            continue
        spec = coverage[year]
        for col in ABSOLUTE_COST_COLUMNS:
            if col in spec["covered"]:
                if grp[col].notna().sum() == 0:
                    failures.append(
                        f"positive-leg: year {year} column {col} is declared "
                        f"covered but 100% null ({len(grp):,} rows) — silent "
                        f"coverage lie (no exception mechanism exists)")
            else:
                offenders = grp.index[grp[col].notna()]
                if len(offenders) > 0:
                    failures.append(
                        f"declared-absent violation: year {year} column {col} "
                        f"carries {len(offenders):,} non-null value(s) "
                        f"(first row index {offenders[0]}) but is not in "
                        f"{year}'s coverage list")
    # every-row-assigned invariant (c10455 finding 2 closure)
    if grouped_total != len(df):
        failures.append(
            f"group-assignment invariant: {grouped_total:,} rows grouped of "
            f"{len(df):,} — some rows belong to no checked group")
    return failures


def acronym_from_filename(fname):
    """
    Derive an agency acronym from a budget filename.
    Examples:
      PROC_DISA_PB_2027.xml       → DISA
      RDTE_CYBERCOM_PB_2027.xml   → CYBERCOM
      SOCOM_OP-5.json             → SOCOM
      DISA_Cyber_OP-5.json        → DISA
      CMP_OP-5.json               → CMP
    """
    stem = Path(fname).stem
    parts = stem.split("_")
    skip = {"PROC", "RDTE", "VOL1", "VOL2", "VOL3", "VOL4", "VOL5", "VOL2B",
            "Vol1", "Vol2", "Vol3", "Vol4", "Vol5"}
    for part in parts:
        if part.upper() not in skip:
            return part
    return ""


def blank_record():
    """Return a dict pre-filled with all schema columns set to None/''."""
    return {col: None for col in COLUMNS}


# =============================================================================
# XML Parser — Procurement (P-1)
# =============================================================================

def parse_procurement_xml(filepath):
    records = []
    fname = Path(filepath).name

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"    [WARN] XML parse error: {fname} — {e}")
        return records

    book = {
        "year"        : elem_text(root, "BudgetYear",        JB_NS),
        "cycle"       : elem_text(root, "BudgetCycle",       JB_NS),
        "date"        : elem_text(root, "SubmissionDate",     JB_NS),
        "agency"      : elem_text(root, "ServiceAgencyName",  JB_NS),
        "approp_code" : elem_text(root, "AppropriationCode",  JB_NS),
        "approp_name" : elem_text(root, "AppropriationName",  JB_NS),
    }

    line_item_list = root.find(f"{{{PROC_NS}}}LineItemList")
    if line_item_list is None:
        print(f"    [INFO] No LineItemList in {fname} — skipping (combined volume?)")
        return records

    for idx, li in enumerate(line_item_list.findall(f"{{{PROC_NS}}}LineItem")):
        li_num   = elem_text(li, "LineItemNumber",           PROC_NS)
        li_title = elem_text(li, "LineItemTitle",            PROC_NS)
        ba_num   = elem_text(li, "BudgetActivityNumber",     PROC_NS)
        ba_title = elem_text(li, "BudgetActivityTitle",      PROC_NS)
        bsa_num  = elem_text(li, "BudgetSubActivityNumber",  PROC_NS)
        bsa_ttl  = elem_text(li, "BudgetSubActivityTitle",   PROC_NS)
        agency   = elem_text(li, "ServiceAgencyName",        PROC_NS) or book["agency"]
        app_code = elem_text(li, "AppropriationNumber",      PROC_NS) or book["approp_code"]
        app_name = elem_text(li, "AppropriationTitle",       PROC_NS) or book["approp_name"]
        desc     = elem_text(li, "Description",              PROC_NS)
        just     = elem_text(li, "Justification",            PROC_NS)

        cost = {}
        rs = li.find(f"{{{PROC_NS}}}ResourceSummary")
        if rs is not None:
            tc = rs.find(f"{{{PROC_NS}}}TotalCost")
            if tc is not None:
                for field, tag in [
                    ("all_prior", "AllPriorYears"),
                    ("prior",     "PriorYear"),
                    ("current",   "CurrentYear"),
                    ("fy1base",   "BudgetYearOneBase"),
                    ("fy1",       "BudgetYearOne"),
                    ("fy2",       "BudgetYearTwo"),
                    ("fy3",       "BudgetYearThree"),
                    ("fy4",       "BudgetYearFour"),
                    ("fy5",       "BudgetYearFive"),
                ]:
                    cost[field] = elem_text(tc, tag, PROC_NS)

        r = blank_record()
        r.update({
            # DBDP-106 c10434: content discriminator (source_file,
            # line_item_number) — enumerate index removed
            "record_id"               : make_content_id(fname, li_num),
            "_disc_family"            : "P-40",
            "_disc_key"               : (norm_key(fname), norm_key(li_num)),
            "budget_year"             : to_float(book["year"]),
            "budget_cycle"            : book["cycle"],
            "submission_date"         : book["date"],
            "service_agency_name"     : agency,
            "service_agency_acronym"  : acronym_from_filename(fname),
            "appropriation_code"      : app_code,
            "appropriation_name"      : app_name,
            "appropriation_type"      : "Procurement",
            "exhibit_type"            : "P-40",
            "source_file"             : fname,
            "file_format"             : "XML",
            "line_item_number"        : li_num,
            "line_item_title"         : li_title,
            "budget_activity_number"  : ba_num,
            "budget_activity_title"   : ba_title,
            "budget_sub_activity_number" : bsa_num,
            "budget_sub_activity_title"  : bsa_ttl,
            "program_element"         : "",
            "cost_all_prior_years"    : to_float(cost.get("all_prior")),
            "cost_prior_year"         : to_float(cost.get("prior")),
            "cost_current_year"       : to_float(cost.get("current")),
            "cost_fy2027"             : to_float(cost.get("fy1base") or cost.get("fy1")),
            "cost_fy2028"             : to_float(cost.get("fy2")),
            "cost_fy2029"             : to_float(cost.get("fy3")),
            "cost_fy2030"             : to_float(cost.get("fy4")),
            "cost_fy2031"             : to_float(cost.get("fy5")),
            "cost_units"              : li.get("totalCostUnits", "Millions"),
            "description"             : desc,
            "justification"           : just,
        })
        records.append(r)

    return records


# =============================================================================
# XML Parser — RDT&E (R-1)
# =============================================================================

def parse_rdte_xml(filepath):
    records = []
    fname = Path(filepath).name

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"    [WARN] XML parse error: {fname} — {e}")
        return records

    book = {
        "year"        : elem_text(root, "BudgetYear",        JB_NS),
        "cycle"       : elem_text(root, "BudgetCycle",       JB_NS),
        "date"        : elem_text(root, "SubmissionDate",     JB_NS),
        "agency"      : elem_text(root, "ServiceAgencyName",  JB_NS),
        "approp_code" : elem_text(root, "AppropriationCode",  JB_NS),
        "approp_name" : elem_text(root, "AppropriationName",  JB_NS),
    }

    pe_list = None
    r2_ns   = None
    for child in root:
        if local_name(child.tag) == "ProgramElementList":
            pe_list = child
            r2_ns   = child.tag.split("}")[0].lstrip("{") if "}" in child.tag else ""
            break

    if pe_list is None:
        print(f"    [INFO] No ProgramElementList in {fname} — skipping (combined volume?)")
        return records

    def r2(el, tag):
        return elem_text(el, tag, r2_ns)

    for idx, pe in enumerate(pe_list):
        if local_name(pe.tag) != "ProgramElement":
            continue

        pe_num   = r2(pe, "ProgramElementNumber")
        pe_title = r2(pe, "ProgramElementTitle")
        ba_num   = r2(pe, "BudgetActivityNumber")
        ba_title = r2(pe, "BudgetActivityTitle")
        agency   = r2(pe, "ServiceAgencyName") or book["agency"]
        app_code = r2(pe, "AppropriationCode") or book["approp_code"]
        desc     = r2(pe, "ProjectMissionDescription") or r2(pe, "Description")

        cost = {}
        pef = pe.find(f"{{{r2_ns}}}ProgramElementFunding")
        if pef is not None:
            for field, tag in [
                ("all_prior", "AllPriorYears"),
                ("prior",     "PriorYear"),
                ("current",   "CurrentYear"),
                ("fy1base",   "BudgetYearOneBase"),
                ("fy1",       "BudgetYearOne"),
                ("fy2",       "BudgetYearTwo"),
                ("fy3",       "BudgetYearThree"),
                ("fy4",       "BudgetYearFour"),
                ("fy5",       "BudgetYearFive"),
            ]:
                cost[field] = r2(pef, tag)

        r = blank_record()
        r.update({
            # DBDP-106 c10434: content discriminator (source_file,
            # program_element, budget_activity_number) — PE alone is not
            # unique (3 OSW PE-across-BA pairs); enumerate index removed
            "record_id"               : make_content_id(fname, pe_num, ba_num),
            "_disc_family"            : "R-2",
            "_disc_key"               : (norm_key(fname), norm_key(pe_num), norm_key(ba_num)),
            "budget_year"             : to_float(book["year"]),
            "budget_cycle"            : book["cycle"],
            "submission_date"         : book["date"],
            "service_agency_name"     : agency,
            "service_agency_acronym"  : acronym_from_filename(fname),
            "appropriation_code"      : app_code,
            "appropriation_name"      : book["approp_name"],
            "appropriation_type"      : "RDT&E",
            "exhibit_type"            : "R-2",
            "source_file"             : fname,
            "file_format"             : "XML",
            "line_item_number"        : "",
            "line_item_title"         : pe_title,
            "budget_activity_number"  : ba_num,
            "budget_activity_title"   : ba_title,
            "budget_sub_activity_number" : "",
            "budget_sub_activity_title"  : "",
            "program_element"         : pe_num,
            "cost_all_prior_years"    : to_float(cost.get("all_prior")),
            "cost_prior_year"         : to_float(cost.get("prior")),
            "cost_current_year"       : to_float(cost.get("current")),
            "cost_fy2027"             : to_float(cost.get("fy1base") or cost.get("fy1")),
            "cost_fy2028"             : to_float(cost.get("fy2")),
            "cost_fy2029"             : to_float(cost.get("fy3")),
            "cost_fy2030"             : to_float(cost.get("fy4")),
            "cost_fy2031"             : to_float(cost.get("fy5")),
            "cost_units"              : pe.get("monetaryUnit", "Millions"),
            "description"             : desc,
            "justification"           : "",
        })
        records.append(r)

    return records


# =============================================================================
# JSON Parser — O&M, DWCF, DHP
# Extracts line items from Grid/Rows structure.
# Values in source JSON are in thousands; converted to millions here.
# Falls back to metadata-level record if no Grid data found.
# =============================================================================

def _sag_from_go_name(name):
    """Strip exhibit suffix from GeneratedOutput names.
    'Combat Development Activities OP-5' → 'Combat Development Activities'
    """
    if not name:
        return ""
    return re.sub(r"\s*(OP-5|OP5|J-Book|Exhibit)\s*$", "", name,
                  flags=re.IGNORECASE).strip()


def _json_cell(row, *codes):
    """Extract cell value from a Grid Row by ColumnCode."""
    for code in codes:
        for cell in row.get("Cells", []):
            if cell.get("ColumnCode") == code:
                v = cell.get("Value")
                return str(v).strip() if v is not None else ""
    return ""


def _walk_json_grids(node, ctx, seen_codes, raw_rows, depth=0):
    """
    Recursively walk the JSON exhibit tree.
    Collect data rows from TARGET grid codes into raw_rows.
    ctx carries SAG title inferred from GeneratedOutput names.
    """
    if depth > 25:
        return
    if isinstance(node, list):
        for item in node:
            _walk_json_grids(item, ctx, seen_codes, raw_rows, depth + 1)
        return
    if not isinstance(node, dict):
        return

    new_ctx = dict(ctx)

    # GeneratedOutput nodes carry SAG/BA identity in their Name field
    if "GeneratedOutput" in node:
        go = node["GeneratedOutput"]
        go_name = go.get("Name", "") or ""
        sag = _sag_from_go_name(go_name)
        if sag:
            new_ctx["sag_title"] = sag
        _walk_json_grids(go, new_ctx, seen_codes, raw_rows, depth + 1)
        return

    node_type = node.get("Type", "")

    # Process Grid nodes with row data
    if node_type == "Grid" and "Rows" in node:
        grid_code = node.get("Code", "") or ""
        if grid_code in JSON_TARGET_GRIDS:
            for row in node.get("Rows", []):
                if row.get("Type") != "data":
                    continue
                row_code = row.get("Code", "")

                # Deduplicate by row Code across all grids
                if row_code and row_code in seen_codes:
                    continue
                if row_code:
                    seen_codes.add(row_code)

                label = _json_cell(row,
                                   "RowText", "ProgElem", "SubAct",
                                   "BudgActi", "Line")
                py  = to_float(_json_cell(row, "Py"))
                cy  = to_float(_json_cell(row, "Cy"))
                by1 = to_float(_json_cell(row, "By1"))

                # Only keep rows with at least one dollar value
                if py is None and cy is None and by1 is None:
                    continue

                raw_rows.append({
                    "grid_code": grid_code,
                    "row_code":  row_code,
                    "sag_title": new_ctx.get("sag_title", ""),
                    "label":     label,
                    "py":        py,
                    "cy":        cy,
                    "by1":       by1,
                })

    # Recurse — skip blob fields
    for k, v in node.items():
        if k in ("ByteArray", "Uploads"):
            continue
        if isinstance(v, (dict, list)):
            _walk_json_grids(v, new_ctx, seen_codes, raw_rows, depth + 1)


def parse_json_exhibit(filepath):
    """
    Parse an O&M / DWCF / DHP JSON file at the line-item level.

    Extracts program-element rows from Op5Part1 and OP53a Grid nodes.
    Deduplicates: when OP53a rows exist, individual-SAG Op5Part1 rows
    that duplicate the same labels are suppressed (they are the same data
    repeated in a single-SAG view of the combined grid).

    Dollar values in source JSON are in thousands ($K).
    This function divides by 1,000 so cost columns are in millions ($M),
    matching the XML-sourced P-1 / R-1 records.

    Falls back to parse_json_metadata() for files with no Grid data
    (e.g., OP-8 civilian personnel, PB-* exhibits, DWCF J-Books).
    """
    fname = Path(filepath).name
    fpath = str(filepath).replace("\\", "/")

    # Skip aggregate/summary volume files
    if fname in JSON_AGGREGATE_FILES:
        return []

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"    [WARN] JSON parse error: {fname} — {e}")
        return []

    meta = data.get("Metadata", {})
    go   = data.get("GeneratedOutput", {})

    # Determine appropriation type from folder
    if "01_Operation_and_Maintenance" in fpath:
        approp_type  = "O&M"
        exhibit_type = "OP-5"
    elif "06_Defense_Working_Capital_Fund" in fpath:
        approp_type  = "DWCF"
        exhibit_type = "RF-1"
    elif "09_Defense_Health_Program" in fpath:
        approp_type  = "DHP"
        exhibit_type = "DHP"
    else:
        approp_type  = "Unknown"
        exhibit_type = "Unknown"

    agency_name     = meta.get("ServiceAgencyName", "")
    approp_code     = meta.get("AppropriationNumber", "")
    budget_cycle    = meta.get("BudgetCycle", "PB")
    submission_date = meta.get("SubmissionDate", "")
    # Note: BudgetYear in JSON metadata = current year (FY2026).
    # All files are FY2027 PB submissions, so budget_year is 2027.
    budget_year     = 2027.0
    acronym         = acronym_from_filename(fname)

    # Walk tree to collect raw grid rows
    raw_rows   = []
    seen_codes = set()
    _walk_json_grids({"GeneratedOutput": go}, {}, seen_codes, raw_rows)

    # No grid data found — fall back to metadata-level record
    if not raw_rows:
        return parse_json_metadata(filepath)

    # ── Deduplication ─────────────────────────────────────────────────────────
    # Each JSON file may contain two overlapping views of the same SAG data:
    #   Op5Part1 — one row per SAG, plus (in multi-SAG files) an aggregate
    #              totals row whose value equals the sum of all SAG rows.
    #   OP53a    — combined view of all SAGs (RowText cells are always empty).
    #
    # Previous label-matching approach failed because OP53a RowText is empty,
    # so no Op5Part1 rows were ever suppressed — causing 2-3× double-counting.
    # Fix:
    #   1. If OP53a rows exist → use OP53a exclusively; drop all Op5Part1.
    #   2. If only Op5Part1 rows exist → keep them, but remove any row whose
    #      By1 value equals the sum of all other rows (the aggregate totals
    #      row).  2 * row_by1 ≈ total_by1 identifies it reliably.

    has_op53a = any(r["grid_code"] == "OP53a" for r in raw_rows)

    if has_op53a:
        # Two levels of OP53a exist in some files:
        #   - a top-level combined grid (one row per SAG, generic sag_title)
        #   - per-SAG grids (one row each, SAG-specific sag_title -- preferred)
        # Row codes differ between levels, so seen_codes dedup doesn't help.
        # Deduplicate by (py, cy, by1) value tuple; last occurrence wins so
        # per-SAG copies (deeper in the tree, richer context) take priority.
        val_map: dict = {}
        for r in raw_rows:
            if r["grid_code"] != "OP53a":
                continue
            key = (r["py"], r["cy"], r["by1"])
            val_map[key] = r          # last write wins
        filtered = list(val_map.values())
    else:
        op5 = [r for r in raw_rows if r["grid_code"] == "Op5Part1"]
        if len(op5) > 1:
            total_by1 = sum(r["by1"] or 0.0 for r in op5)
            # Aggregate row: its By1 equals the sum of all other rows,
            # i.e. 2 * row_by1 ≈ total_by1.  Tolerance: $1K.
            op5 = [
                r for r in op5
                if abs((r["by1"] or 0.0) * 2 - total_by1) > 1.0
            ]
        filtered = op5

    records = []
    for i, row in enumerate(filtered):

        # Convert from thousands ($K) → millions ($M)
        def k_to_m(v):
            return round(v / 1000.0, 6) if v is not None else None

        r = blank_record()
        r.update({
            # DBDP-106 c10434: content discriminator (source_file, row_code)
            # — the source-carried grid row Code; label fallback and
            # enumerate index removed (row_code present on 100% of filtered
            # rows at base; a future empty row_code duplicates the key and
            # trips the collision hard-fail)
            "record_id"                  : make_content_id(fname, row["row_code"]),
            "_disc_family"               : "OP-5",
            "_disc_key"                  : (norm_key(fname), norm_key(row["row_code"])),
            "budget_year"                : budget_year,
            "budget_cycle"               : budget_cycle,
            "submission_date"            : submission_date,
            "service_agency_name"        : agency_name,
            "service_agency_acronym"     : acronym,
            "appropriation_code"         : approp_code,
            "appropriation_name"         : agency_name,
            "appropriation_type"         : approp_type,
            "exhibit_type"               : exhibit_type,
            "source_file"                : fname,
            "file_format"                : "JSON",
            "line_item_number"           : "",
            "line_item_title"            : row["label"],
            "budget_activity_number"     : "",
            "budget_activity_title"      : row["sag_title"],
            "budget_sub_activity_number" : "",
            "budget_sub_activity_title"  : "",
            "program_element"            : "",
            "cost_all_prior_years"       : None,
            "cost_prior_year"            : k_to_m(row["py"]),
            "cost_current_year"          : k_to_m(row["cy"]),
            "cost_fy2027"                : k_to_m(row["by1"]),
            "cost_fy2028"                : None,
            "cost_fy2029"                : None,
            "cost_fy2030"                : None,
            "cost_fy2031"                : None,
            "cost_units"                 : "Millions",
            "description"                : "",
            "justification"              : "",
        })
        records.append(r)

    return records


def parse_json_metadata(filepath):
    """
    Metadata-level fallback parser for JSON files with no Grid structure
    (OP-8 civilian personnel, PB-* exhibits, DWCF J-Books, etc.).
    Produces one summary record per file.
    """
    records = []
    fname = Path(filepath).name
    fpath = str(filepath).replace("\\", "/")

    if fname in JSON_AGGREGATE_FILES:
        return []

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"    [WARN] JSON parse error: {fname} — {e}")
        return records

    meta   = data.get("Metadata", {})
    output = data.get("GeneratedOutput", {})

    if "01_Operation_and_Maintenance" in fpath:
        approp_type  = "O&M"
        exhibit_type = "OP-5"
    elif "06_Defense_Working_Capital_Fund" in fpath:
        approp_type  = "DWCF"
        exhibit_type = "RF-1"
    elif "09_Defense_Health_Program" in fpath:
        approp_type  = "DHP"
        exhibit_type = "DHP"
    else:
        approp_type  = "Unknown"
        exhibit_type = "Unknown"

    name = output.get("Name", "") or output.get("Description", "")
    desc = output.get("Description", "")

    r = blank_record()
    r.update({
        "record_id"              : make_id(fname, name, 0),
        "budget_year"            : 2027.0,
        "budget_cycle"           : meta.get("BudgetCycle", ""),
        "submission_date"        : meta.get("SubmissionDate", ""),
        "service_agency_name"    : meta.get("ServiceAgencyName", ""),
        "service_agency_acronym" : acronym_from_filename(fname),
        "appropriation_code"     : meta.get("AppropriationNumber", ""),
        "appropriation_name"     : meta.get("ServiceAgencyName", ""),
        "appropriation_type"     : approp_type,
        "exhibit_type"           : exhibit_type,
        "source_file"            : fname,
        "file_format"            : "JSON",
        "line_item_title"        : name,
        "description"            : desc,
        "cost_units"             : "Millions",
    })
    records.append(r)
    return records


# =============================================================================
# XML Parser — MHS J-Book (SpreadsheetML format)
# =============================================================================
#
# The two MHS files use Excel's SpreadsheetML XML format, not the DTIC standard
# XML used by P-1/R-1.  Cells may contain HTML child elements (<Font>) so text
# must be extracted via itertext(), not .text.
#
# Vol 1  (COMP_PSCP)  : BA O&M sub-activity breakdown (7 rows, $K)
#         approp 0130D, sub-acts 010-070, cols 26/32/59
# Vol 2  (SMR)        : Per-service medical readiness detail rows ($K)
#         Army APPN 2020A, Navy 2021A, AF 3400 — SAG + description + FY values
#
# All values are in $K in the source; converted to $M here (/1000).
# =============================================================================

MHS_SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"


def _ss(tag):
    return f"{{{MHS_SS_NS}}}{tag}"


def _mhs_cell_text(cell):
    """Extract text from a SpreadsheetML cell, handling embedded HTML elements."""
    data = cell.find(_ss("Data"))
    if data is None:
        return ""
    text = "".join(data.itertext()).strip()
    return re.sub(r"\s+", " ", text).strip()


def _mhs_row_cells(row):
    """
    Return a 1-indexed list of cell strings for a SpreadsheetML row.
    Respects ss:Index attributes for sparse rows.
    Index 1 → cells[0], Index N → cells[N-1].
    """
    cells = []
    for cell in row.findall(_ss("Cell")):
        idx = cell.get(_ss("Index"))
        text = _mhs_cell_text(cell)
        if idx:
            col = int(idx)          # 1-based
            while len(cells) < col - 1:
                cells.append("")
            cells.append(text)
        else:
            cells.append(text)
    return cells  # cells[0] = column 1


def _mhs_col(cells, col):
    """Return cell value at 1-based column col, or '' if out of range."""
    if col < 1 or col > len(cells):
        return ""
    return cells[col - 1]


def _mhs_float(cells, col):
    """Return float at 1-based column col, or None if blank/non-numeric."""
    val = _mhs_col(cells, col)
    if not val or val in ("-", "–", "—", "$-", "$ -"):
        return None
    val = re.sub(r"[,$]", "", val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _mhs_k_to_m(v):
    """Convert $K to $M."""
    return round(v / 1000.0, 6) if v is not None else None


def _mhs_get_rows(filepath):
    """Parse a SpreadsheetML file and return all Row elements from the first worksheet."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    ws = root.find(".//" + _ss("Worksheet"))
    if ws is None:
        return []
    table = ws.find(_ss("Table"))
    if table is None:
        return []
    return table.findall(_ss("Row"))


def _parse_mhs_vol1(filepath):
    """
    Extract BA O&M sub-activity line items from Vol 1 (COMP_PSCP).

    Target rows (1-indexed) have:
      col 1 = '0130D'   (appropriation code)
      col 4 = sub-activity number, e.g. '010'
      col 7 = sub-activity title, e.g. 'In-House Care'
      col 26 = FY 2025 Actuals  ($K)
      col 32 = FY 2026 Enacted  ($K)
      col 59 = FY 2027 Request  ($K)

    Also captures the TOTAL, BA 01 row for cross-check.
    """
    records = []
    fname = Path(filepath).name
    rows = _mhs_get_rows(filepath)

    for row in rows:
        cells = _mhs_row_cells(row)
        c1 = _mhs_col(cells, 1)

        # Sub-activity detail row
        if c1 == "0130D":
            sub_act_num   = _mhs_col(cells, 4)
            sub_act_title = _mhs_col(cells, 7)
            fy25  = _mhs_float(cells, 26)
            fy26  = _mhs_float(cells, 32)
            fy27  = _mhs_float(cells, 59)

            # Skip rows that lack a valid sub-activity number (e.g. header echoes)
            if not re.match(r"^\d{3}$", sub_act_num):
                continue
            # Skip zero-value rows with no FY2027 request (e.g. Private Sector Care
            # was transferred to PSCP and shows '-' for FY2027)
            if fy27 is None and fy25 is None:
                continue

            r = blank_record()
            r.update({
                "record_id"                    : make_id(fname, "0130D", sub_act_num),
                "budget_year"                  : 2027.0,
                "budget_cycle"                 : "PB",
                "submission_date"              : "2026-04",
                "service_agency_name"          : "Defense Health Agency",
                "service_agency_acronym"       : "DHA",
                "appropriation_code"           : "0130D",
                "appropriation_name"           : "Combat & Operational Medicine Program",
                "appropriation_type"           : "DHP",
                "exhibit_type"                 : "DHP-J-Book",
                "source_file"                  : fname,
                "file_format"                  : "XML",
                "budget_activity_number"       : "01",
                "budget_activity_title"        : "Operation & Maintenance",
                "budget_sub_activity_number"   : sub_act_num,
                "budget_sub_activity_title"    : sub_act_title,
                "cost_prior_year"              : _mhs_k_to_m(fy25),
                "cost_current_year"            : _mhs_k_to_m(fy26),
                "cost_fy2027"                  : _mhs_k_to_m(fy27),
                "cost_units"                   : "Millions",
            })
            records.append(r)

    return records


def _parse_mhs_vol2(filepath):
    """
    Extract per-service medical readiness detail rows from Vol 2 (SMR).

    Each service section has a consistent header row followed by data rows:
      Army (APPN 2020A):  col1=APPN, col5=SAG, col8=desc
                          FY2025 in col 36 (first section) or col 30 (later),
                          FY2026 in col 43, FY2027 in col 48
      Navy (APPN 2021A):  col1=APPN, col5=SAG, col6=desc
                          FY2025 col 30, FY2026 col 36, FY2027 col 43
      AF   (APPN 3400):   col1=APPN, col5=SAG, col8=desc
                          FY2025 col 30, FY2026 col 43, FY2027 col 48

    We detect the active service/column layout from section header rows and
    extract rows that match the APPN pattern for that service.
    """
    records = []
    fname = Path(filepath).name
    rows = _mhs_get_rows(filepath)

    # State tracking
    current_service = None
    current_appn    = None
    fy25_col        = None
    fy26_col        = None
    fy27_col        = None
    section_label   = None   # e.g. "Medical Operations Support"

    # Service detection from APPN codes
    SERVICE_MARKERS = {
        "Army": {
            "appn": "2020A",
            "appn_pat": re.compile(r"^2020A$"),
            "full": "Department of the Army",
            "acronym": "Army",
            "desc_col": 8,
        },
        "Navy": {
            "appn": "2021A",
            "appn_pat": re.compile(r"^2021A$"),
            "full": "Department of the Navy",
            "acronym": "Navy",
            "desc_col": 6,
        },
        "AirForce": {
            "appn": "3400",
            "appn_pat": re.compile(r"^3400$"),
            "full": "Department of the Air Force",
            "acronym": "Air Force",
            "desc_col": 8,
        },
    }

    # Known section labels
    SECTION_LABELS = {
        "Medical Operations Support",
        "Medical Research and Development",
        "Medical Facilities and Installation Support",
        "Medical Acquisition Support",
        "Medical Education and Training",
    }

    # Default (fy25_col, fy26_col, fy27_col) per service
    SERVICE_DEFAULT_COLS = {
        "Army":     (30, 43, 48),
        "Navy":     (30, 36, 43),
        "AirForce": (30, 43, 48),
    }

    def detect_header_cols(cells):
        """Scan a row for FY 202x labels and return (c25, c26, c27) or None."""
        fy_map = {}
        for i, c in enumerate(cells, 1):
            m = re.search(r"FY\s*(202[5-7])", c, re.IGNORECASE)
            if m:
                fy_map[m.group(1)] = i
        if "2025" in fy_map and "2026" in fy_map and "2027" in fy_map:
            return (fy_map["2025"], fy_map["2026"], fy_map["2027"])
        return None

    for row in rows:
        cells = _mhs_row_cells(row)
        if not cells:
            continue
        c1 = _mhs_col(cells, 1)

        # ── Track column layout from header rows ──────────────────────────────
        detected = detect_header_cols(cells)
        if detected and current_service:
            fy25_col, fy26_col, fy27_col = detected

        # ── Track section label ───────────────────────────────────────────────
        if c1.strip() in SECTION_LABELS:
            section_label = c1.strip()

        # ── Detect and extract data rows ──────────────────────────────────────

        # Pattern A: clean split — APPN in col1, SAG in col5, desc in col6/8
        matched = False
        for svc_key, svc in SERVICE_MARKERS.items():
            if not svc["appn_pat"].match(c1):
                continue

            # Switch service context if needed
            if current_service != svc_key:
                current_service = svc_key
                current_appn    = svc["appn"]
                fy25_col, fy26_col, fy27_col = SERVICE_DEFAULT_COLS[svc_key]

            # Extract description (try both common desc columns)
            desc_col = svc["desc_col"]
            desc = _mhs_col(cells, desc_col)
            if not desc:
                alt = 6 if desc_col == 8 else 8
                desc = _mhs_col(cells, alt)
            if not desc:
                break

            # Normalize SAG: "SAG 124" -> "124", "BSIT" -> "BSIT"
            sag_raw = _mhs_col(cells, 5)
            sag = re.sub(r"^SAG\s*", "", sag_raw).strip()

            fy25 = _mhs_float(cells, fy25_col) if fy25_col else None
            fy26 = _mhs_float(cells, fy26_col) if fy26_col else None
            fy27 = _mhs_float(cells, fy27_col) if fy27_col else None

            if fy25 is None and fy26 is None and fy27 is None:
                break

            r = blank_record()
            r.update({
                "record_id"                  : make_id(fname, current_appn, sag, desc, section_label or ""),  # DBDP-62: add budget_sub_activity_title for row-grain uniqueness
                "budget_year"                : 2027.0,
                "budget_cycle"               : "PB",
                "submission_date"            : "2026-04",
                "service_agency_name"        : svc["full"],
                "service_agency_acronym"     : svc["acronym"],
                "appropriation_code"         : current_appn,
                "appropriation_name"         : "Defense Health Program — "
                                               + svc["acronym"] + " Medical Readiness",
                "appropriation_type"         : "DHP",
                "exhibit_type"               : "DHP-SMR",
                "source_file"                : fname,
                "file_format"                : "XML",
                "budget_activity_number"     : sag,
                "budget_sub_activity_title"  : section_label or "",
                "line_item_title"            : desc,
                "cost_prior_year"            : _mhs_k_to_m(fy25),
                "cost_current_year"          : _mhs_k_to_m(fy26),
                "cost_fy2027"                : _mhs_k_to_m(fy27),
                "cost_units"                 : "Millions",
            })
            records.append(r)
            matched = True
            break  # matched — move to next row

        if matched:
            continue

        # Pattern B: merged-cell Navy rows — "2021A SAG description" all in col1
        # e.g. "2021A BSM1 Sustainment, Restoration, and Modernization"
        # Funding columns: col30=FY2025, col36=FY2026, col43=FY2027
        merged = re.match(r"^(2021A)\s+([A-Z0-9]{2,6}[A-Z0-9])\s+(.+)$", c1)
        if merged:
            m_appn = merged.group(1)
            m_sag  = merged.group(2)
            m_desc = merged.group(3).strip()
            # Use Navy column defaults
            fy25 = _mhs_float(cells, 30)
            fy26 = _mhs_float(cells, 36)
            fy27 = _mhs_float(cells, 43)
            if not (fy25 is None and fy26 is None and fy27 is None):
                if current_service != "Navy":
                    current_service = "Navy"
                    current_appn    = "2021A"
                svc_info = SERVICE_MARKERS["Navy"]
                r = blank_record()
                r.update({
                    "record_id"                  : make_id(fname, m_appn, m_sag, m_desc, section_label or ""),  # DBDP-62: add budget_sub_activity_title for row-grain uniqueness
                    "budget_year"                : 2027.0,
                    "budget_cycle"               : "PB",
                    "submission_date"            : "2026-04",
                    "service_agency_name"        : svc_info["full"],
                    "service_agency_acronym"     : svc_info["acronym"],
                    "appropriation_code"         : m_appn,
                    "appropriation_name"         : "Defense Health Program — Navy Medical Readiness",
                    "appropriation_type"         : "DHP",
                    "exhibit_type"               : "DHP-SMR",
                    "source_file"                : fname,
                    "file_format"                : "XML",
                    "budget_activity_number"     : m_sag,
                    "budget_sub_activity_title"  : section_label or "",
                    "line_item_title"            : m_desc,
                    "cost_prior_year"            : _mhs_k_to_m(fy25),
                    "cost_current_year"          : _mhs_k_to_m(fy26),
                    "cost_fy2027"                : _mhs_k_to_m(fy27),
                    "cost_units"                 : "Millions",
                })
                records.append(r)

    return records


def parse_mhs_xml(filepath):
    """
    Dispatch to the correct MHS J-Book parser based on filename.
    Returns a list of budget records.
    """
    fname = Path(filepath).name
    try:
        if "Vol1" in fname or "COMP_PSCP" in fname:
            recs = _parse_mhs_vol1(filepath)
        elif "Vol2" in fname or "SMR" in fname:
            recs = _parse_mhs_vol2(filepath)
        else:
            recs = []
            print(f"    [WARN] Unrecognised MHS file: {fname}")
    except ET.ParseError as e:
        print(f"    [WARN] XML parse error in {fname}: {e}")
        recs = []
    return recs


# =============================================================================
# File walker
# =============================================================================

MHS_FOLDER   = "09_Military_Health_System"
XML_FOLDERS  = ["02_Procurement", "03_RDT_and_E"]
JSON_FOLDERS = [
    "01_Operation_and_Maintenance",
    "06_Defense_Working_Capital_Fund",
    "09_Defense_Health_Program",
]

SKIP_FILES = {
    "PB_2027_PDW_VOL_1.xml",
    "PB_2027_RDTE_VOL_5.xml",
}


def collect_files():
    xml_files  = []
    mhs_files  = []
    json_files = []

    for folder in XML_FOLDERS:
        folder_path = DATA_DIR / folder
        if folder_path.exists():
            for f in sorted(folder_path.rglob("*.xml")):
                if f.name not in SKIP_FILES:
                    xml_files.append(f)

    mhs_path = DATA_DIR / MHS_FOLDER
    if mhs_path.exists():
        for f in sorted(mhs_path.rglob("*.xml")):
            mhs_files.append(f)

    for folder in JSON_FOLDERS:
        folder_path = DATA_DIR / folder
        if folder_path.exists():
            for f in sorted(folder_path.rglob("*.json")):
                json_files.append(f)

    return xml_files, mhs_files, json_files


# =============================================================================
# Main
# =============================================================================

def main():
    print()
    print("=" * 65)
    print("  ODBA — FY2027 Budget ETL  (Defense-Wide Agencies, PB2027)")
    print("=" * 65)
    print(f"  Data directory : {DATA_DIR}")
    print(f"  Output file    : {OUTPUT_FILE}")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)

    xml_files, mhs_files, json_files = collect_files()
    print(f"  Found {len(xml_files)} XML files  |  {len(mhs_files)} MHS files  |  {len(json_files)} JSON files")
    print()

    # Manifest loaded once, up front — reused for the pre-parse integrity
    # gate below and the lifecycle/vintage join later (DBDP-73 c10479).
    manifest = load_source_manifest()

    all_records = []
    errors      = []

    # ── Parse XML files (P-1, R-1) ───────────────────────────────────────────
    print("── Parsing XML files ─────────────────────────────────────────")
    for fp in xml_files:
        parent = fp.parts[len(DATA_DIR.parts)]
        if parent == "02_Procurement":
            parser = parse_procurement_xml
            label  = "P-1 Procurement"
        elif parent == "03_RDT_and_E":
            parser = parse_rdte_xml
            label  = "R-1 RDT&E     "
        else:
            print(f"  [SKIP] Unknown XML folder: {fp.relative_to(DATA_DIR)}")
            continue

        verify_file_integrity(fp, manifest)
        try:
            recs = parser(fp)
            all_records.extend(recs)
            print(f"  [{label}]  {fp.name:<60}  {len(recs):>4} records")
        except Exception as e:
            errors.append((str(fp), str(e)))
            print(f"  [ERROR] {fp.name}: {e}")

    # ── Parse MHS J-Book XML files ────────────────────────────────────────────
    print()
    print("── Parsing MHS J-Book XML files ──────────────────────────────")
    for fp in mhs_files:
        verify_file_integrity(fp, manifest)
        try:
            recs = parse_mhs_xml(fp)
            all_records.extend(recs)
            vol = "Vol1" if "Vol1" in fp.name else "Vol2"
            print(f"  [MHS-{vol}]  {fp.name:<60}  {len(recs):>4} records")
        except Exception as e:
            errors.append((str(fp), str(e)))
            print(f"  [ERROR] {fp.name}: {e}")

    # ── Parse JSON files ──────────────────────────────────────────────────────
    print()
    print("── Parsing JSON files (OP-5 / line-item extraction) ─────────")
    skipped_agg = 0
    for fp in json_files:
        if fp.name in JSON_AGGREGATE_FILES:
            skipped_agg += 1
            continue
        verify_file_integrity(fp, manifest)
        try:
            recs = parse_json_exhibit(fp)
            all_records.extend(recs)
            mode = "grid" if any(
                r.get("line_item_title") and r.get("cost_fy2027") is not None
                for r in recs
            ) else "meta"
            print(f"  [JSON-{mode}]  {fp.name:<58}  {len(recs):>4} record(s)")
        except Exception as e:
            errors.append((str(fp), str(e)))
            print(f"  [ERROR] {fp.name}: {e}")

    if skipped_agg:
        print(f"  [SKIP-AGG]  {skipped_agg} aggregate volume files skipped (avoid double-counting)")

    # ── Build DataFrame ───────────────────────────────────────────────────────
    print()
    print("Building dataset...")

    if not all_records:
        print("  [ERROR] No records parsed.")
        sys.exit(1)

    # ── Discriminator collision hard-fail (DBDP-106 c10434 §4) ────────────────
    collisions = check_discriminator_collisions(all_records)
    if collisions:
        print(f"  [FATAL] {len(collisions)} natural-key collision group(s) — "
              f"no silent collapse, no positional tiebreaker (DBDP-106):")
        for m in collisions:
            print(f"          {m}")
        sys.exit(1)

    df = pd.DataFrame(all_records, columns=COLUMNS)

    float_cols = [
        "budget_year",
        "cost_all_prior_years", "cost_prior_year", "cost_current_year",
        "cost_fy2026",   # DBDP-102: additive; NULL until B1-2 ingests FY26
        "cost_fy2027", "cost_fy2028", "cost_fy2029", "cost_fy2030", "cost_fy2031",
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Manifest join (DBDP-94 c10315: DBDP-87 + DBDP-48 in one join) ─────────
    # data_vintage and data_lifecycle_stage are properties of the SOURCE,
    # recorded in the manifest at registration time. Hard-fail on any parsed
    # file with no manifest entry — a missing entry must be a loud stop, never
    # a silent mislabel. Reuses the manifest loaded at the top of main()
    # (DBDP-73) — one read, one consistent view for the whole run.
    parsed_files = set(df["source_file"].unique())
    missing = sorted(parsed_files - set(manifest))
    if missing:
        print(f"  [FATAL] {len(missing)} parsed source file(s) missing from "
              f"{MANIFEST_FILE.name}: {missing[:5]}{' ...' if len(missing) > 5 else ''}")
        sys.exit(1)
    df["data_vintage"]         = df["source_file"].map(lambda f: manifest[f]["acquisition_date"])
    df["data_lifecycle_stage"] = df["source_file"].map(lambda f: manifest[f]["lifecycle_stage"])

    # funding_type / funding_type_signal stay genuinely NULL until the B5
    # classifier lands (c10315 §1.1–1.2) — excluded from the ""-fill below.
    NULLABLE_UNTIL_CLASSIFIED = {"funding_type", "funding_type_signal"}
    str_cols = [c for c in COLUMNS
                if c not in float_cols and c not in NULLABLE_UNTIL_CLASSIFIED]
    df[str_cols] = df[str_cols].fillna("")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"  Total records  : {len(df):,}")
    print()
    print("  Records by appropriation_type:")
    for approp, count in df["appropriation_type"].value_counts().items():
        print(f"    {approp:<25} {count:>6,}")
    print()
    print("  Records by exhibit_type:")
    for exhibit, count in df["exhibit_type"].value_counts().items():
        print(f"    {exhibit:<25} {count:>6,}")
    print()
    print("  Records by data_lifecycle_stage:")
    for stage, count in df["data_lifecycle_stage"].value_counts().items():
        print(f"    {stage:<25} {count:>6,}")

    # -- Write Parquet --------------------------------------------------------
    print()
    print("Writing Parquet...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_FILE, index=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1_048_576
    print(f"  Saved  ->  {OUTPUT_FILE}")
    print(f"  Size   :  {size_mb:.2f} MB")
    print(f"  Rows   :  {len(df):,}")
    print(f"  Cols   :  {len(df.columns)}")

    # -- Post-run validation --------------------------------------------------
    VALID_EXHIBIT_TYPES = {"P-40", "R-2", "OP-5", "RF-1", "DHP", "DHP-J-Book", "DHP-SMR"}  # DBDP-68
    fails = []

    print()
    print("-- Post-run validation -------------------------------------------")

    # (a0) composite (record_id, data_vintage) uniqueness  # DBDP-94 c10315 §3
    # REPLACES the DBDP-62 standalone record_id assertion (AR c10284 binding
    # note / c10326 note 2): within one vintage the composite is equivalent,
    # and it does not false-fail on a legitimate future restatement.
    n_dupes = df.duplicated(subset=["record_id", "data_vintage"]).sum()
    if n_dupes == 0:
        print(f"  [PASS] (record_id,vintage) : composite unique ({len(df):,} of {len(df):,})")
    else:
        print(f"  [FAIL] (record_id,vintage) : {n_dupes:,} duplicate composite key(s)")
        fails.append("composite_uniqueness")

    # (a1) record_id format: 20-hex (80-bit) per DBDP-72 via c10315 §1.4
    bad_id = (~df["record_id"].str.fullmatch(r"[0-9a-f]{20}")).sum()
    if bad_id == 0:
        print(f"  [PASS] record_id format    : all match ^[0-9a-f]{{20}}$")
    else:
        print(f"  [FAIL] record_id format    : {bad_id:,} record(s) not 20-hex")
        fails.append("record_id_format")

    # (a) exhibit_type: only expected values
    bad_et = set(df["exhibit_type"].unique()) - VALID_EXHIBIT_TYPES
    if not bad_et:
        print(f"  [PASS] exhibit_type        : all values within expected set")
    else:
        print(f"  [FAIL] exhibit_type        : unexpected values: {sorted(bad_et)}")
        fails.append("exhibit_type")

    # (b) data_lifecycle_stage: non-null, in the six-value enum (c10321), and
    #     equal to the manifest-derived value for its source_file (c10315 §5d)
    manifest_chk = load_source_manifest()
    null_ls = (df["data_lifecycle_stage"].isna() | (df["data_lifecycle_stage"] == "")).sum()
    bad_enum = set(df["data_lifecycle_stage"].unique()) - LIFECYCLE_STAGES - {""}
    ls_mismatch = (df["data_lifecycle_stage"]
                   != df["source_file"].map(lambda f: manifest_chk.get(f, {}).get("lifecycle_stage"))).sum()
    if null_ls == 0 and not bad_enum and ls_mismatch == 0:
        print(f"  [PASS] data_lifecycle_stage: 100% populated, in 6-value enum, "
              f"== manifest ({len(df):,} records)")
    else:
        print(f"  [FAIL] data_lifecycle_stage: {null_ls:,} null/empty; "
              f"bad enum values {sorted(bad_enum)}; {ls_mismatch:,} manifest mismatch(es)")
        fails.append("data_lifecycle_stage")

    # (b2) data_vintage: non-null, ISO date, sane range, 1:1 manifest join
    #      (c10315 §5c; DBDP-87 c10275 verification path)
    from datetime import date as _date
    def _valid_vintage(v):
        if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return False
        try:
            d = _date.fromisoformat(v)
        except ValueError:
            return False
        return _date(2025, 1, 1) <= d <= _date.today()
    bad_dv = (~df["data_vintage"].map(_valid_vintage)).sum()
    pair_mismatch = 0
    for sf, dv in df[["source_file", "data_vintage"]].drop_duplicates().itertuples(index=False):
        if manifest_chk.get(sf, {}).get("acquisition_date") != dv:
            pair_mismatch += 1
    if bad_dv == 0 and pair_mismatch == 0:
        print(f"  [PASS] data_vintage        : 100% valid ISO dates in range, "
              f"1:1 manifest join ({df['data_vintage'].nunique()} distinct)")
    else:
        print(f"  [FAIL] data_vintage        : {bad_dv:,} invalid value(s); "
              f"{pair_mismatch:,} (source_file, vintage) pair(s) not in manifest")
        fails.append("data_vintage")

    # (c2) cost-column coverage assertion (DBDP-102; c10365 §2; AR c10430)
    #      — closure + declared-absent 100%-null + covered positive leg,
    #      via the single callable check_cost_coverage() (same dataframe
    #      the tests exercise; Codex c10382 executable-path rule).
    coverage = load_cost_coverage()
    cov_failures = check_cost_coverage(df, coverage)
    if not cov_failures:
        yrs = sorted({int(y) for y in df["budget_year"].dropna().unique()})
        print(f"  [PASS] cost coverage       : closure + absent-null + positive "
              f"leg for year(s) {yrs} (declared in {COVERAGE_FILE.name})")
    else:
        for f_ in cov_failures:
            print(f"  [FAIL] cost coverage       : {f_}")
        fails.append("cost_coverage")

    # (e) TC-FT-01…09 funding_type suite (DBDP-85 c10287 §3, A5 gate-label
    #     matrix c10299). 01/02/03 ACTIVE at landing; 04–09 are RESIDENT
    #     GUARDS — vacuous while every signal is NULL, live the moment the
    #     B5 classifier writes its first non-null value. Their vacuous
    #     success is NOT classifier validation (A5 Tester instruction).
    ft, sig = df["funding_type"], df["funding_type_signal"]

    # TC-FT-01 (ACTIVE): domain
    bad_ft = set(ft.dropna().unique()) - FUNDING_TYPES
    if not bad_ft:
        print(f"  [PASS] TC-FT-01 domain     : non-null funding_type ⊆ {sorted(FUNDING_TYPES)}")
    else:
        print(f"  [FAIL] TC-FT-01 domain     : unexpected values {sorted(bad_ft)}")
        fails.append("TC-FT-01")

    # TC-FT-02 (ACTIVE until B5 lands) — re-bound per DBDP-102 AC-3
    # (c10387): ALL rows unclassified, superseding the c10299 "== 635"
    # literal (row count stops being 635 at B1-2; executable-receipts
    # discipline per TC-ER-06 / DBDP-66 c10327).
    n_null_ft = ft.isna().sum()
    if n_null_ft == len(df):
        print(f"  [PASS] TC-FT-02 all-NULL   : all {len(df):,} rows unclassified "
              f"(re-bound: == len(df), not a literal)")
    else:
        print(f"  [FAIL] TC-FT-02 all-NULL   : {n_null_ft:,} NULL of {len(df):,} rows "
              f"(expected all rows NULL until B5 lands)")
        fails.append("TC-FT-02")

    # TC-FT-03 (ACTIVE): null-pairing invariant
    unpaired = (ft.isna() != sig.isna()).sum()
    if unpaired == 0:
        print(f"  [PASS] TC-FT-03 null-pair  : funding_type NULL ⟺ signal NULL")
    else:
        print(f"  [FAIL] TC-FT-03 null-pair  : {unpaired:,} row(s) with exactly one null")
        fails.append("TC-FT-03")

    # TC-FT-04…09 (RESIDENT GUARDS — vacuous at landing per A5)
    nn = df[sig.notna()]
    ft_guard_fails = []
    for _, row in nn.iterrows():
        raw = row["funding_type_signal"]
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            ft_guard_fails.append("TC-FT-04 (signal not valid JSON)")
            continue
        keys = list(obj.keys())
        if not (obj.get("method") in SIGNAL_METHODS
                and obj.get("confidence") in SIGNAL_CONFIDENCES
                and "evidence" in obj):
            ft_guard_fails.append("TC-FT-04 (method/confidence/evidence)")
        if keys not in (["method", "evidence", "confidence"],
                        ["method", "evidence", "confidence", "corroboration"]) \
           or json.dumps(obj, separators=(",", ":"), ensure_ascii=False) != raw:
            ft_guard_fails.append("TC-FT-05 (key order / compactness)")
        if obj.get("confidence") != SIGNAL_CONFIDENCE_MAP.get(obj.get("method")):
            ft_guard_fails.append("TC-FT-06 (fixed confidence map)")
        method = obj.get("method")
        if method == "account_marker":
            # Gated: no account_marker classification may ship until the
            # marker table exists + is validated (c10287 §2, c10299 A6).
            ft_guard_fails.append("TC-FT-07 (account_marker before marker table)")
        elif SIGNAL_METHOD_VALUE_MAP.get(method) != row["funding_type"]:
            ft_guard_fails.append("TC-FT-07 (method→value)")
        evidence = str(obj.get("evidence", ""))
        if any(stage in evidence for stage in LIFECYCLE_STAGES) \
           or any(c in evidence for c in COLUMNS if c.startswith("cost_")):
            ft_guard_fails.append("TC-FT-08 (evidence references lifecycle/cost)")
        corr = obj.get("corroboration")
        if corr is not None:
            if (not isinstance(corr, list) or corr != sorted(corr)
                    or not set(corr) <= SIGNAL_METHODS or method in corr):
                ft_guard_fails.append("TC-FT-09 (corroboration format)")
    if not ft_guard_fails:
        state = ("vacuous — 0 non-null signals; NOT classifier validation"
                 if nn.empty else f"{len(nn):,} non-null signal(s) checked")
        print(f"  [PASS] TC-FT-04..09 guards : resident ({state})")
    else:
        print(f"  [FAIL] TC-FT-04..09 guards : {len(ft_guard_fails)} violation(s): "
              f"{sorted(set(ft_guard_fails))}")
        fails.append("TC-FT-04..09")

    # (c) source_file: non-null / non-empty on 100% of records
    null_sf = (df["source_file"].isna() | (df["source_file"] == "")).sum()
    if null_sf == 0:
        print(f"  [PASS] source_file         : 100% populated ({len(df):,} records)")
    else:
        print(f"  [FAIL] source_file         : {null_sf:,} null/empty records")
        fails.append("source_file")

    print()
    if fails:
        print(f"  VALIDATION FAILED -- {len(fails)} check(s): {', '.join(fails)}")
        sys.exit(1)   # assertion failure is a hard stop (CLAUDE.md; c10315)
    else:
        print(f"  All validation checks passed.")

    print()
    print("=" * 65)
    print("  ETL complete.")
    print("=" * 65)
    print()


if __name__ == "__main__":
    main()
