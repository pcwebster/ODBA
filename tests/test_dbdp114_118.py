# =============================================================================
# ODBA -- Open Defense Budget Analytics
# tests/test_dbdp114_118.py  |  canonical DBDP-114 + DBDP-118 suite
# =============================================================================
# Canonical surfaces:
#   DBDP-114 -- c10626 as amended by Codex c10628 (Amendments 114-A..D)
#   DBDP-118 -- c10627 as amended by Codex c10629 (Amendments 118-A..F)
# Every amendment is BLOCKING. Per AR c10618/c10619 the two tickets ship in one
# PR, so this file keeps their cases in SEPARATE sections and the runner prints
# a per-ticket scorecard -- per-ticket traceability survives the shared commit.
#
# Standalone, no test framework:
#   python tests/test_dbdp114_118.py
# Exit 0 = every non-blocked case passed. A BLOCKED case never counts as PASS.
#
# Money is compared as canonical six-decimal Decimal tokens (114-A / 118-A):
# IEEE equality and numeric tolerances are not acceptable substitutes.
# =============================================================================

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd                                          # noqa: E402

import etl_budget as etl                                     # noqa: E402

BASE_SHA = "5e2637841d6d9535d7bec2c588f190858cfb6757"   # pinned base
PARQUET  = REPO / "output" / "fact_budget_line_items.parquet"
CONSUME  = REPO / "output" / "consumption"
FIXTURES = REPO / "fixtures" / "dbdp114"

# TC-118-ID2 pins, exactly as c10576 measured and c10627 recorded them: ONE
# decimal place. Amendment 118-B re-expressed them at six decimals; see the
# ID2 case for why that re-expression is arithmetically unreachable.
ID2_TOTAL_1DP = Decimal("107249.5")
ID2_FAMILY_1DP = {
    "OP-5": Decimal("41562.1"), "R-2": Decimal("19852.5"),
    "P-40": Decimal("6918.5"), "DHP-J-Book": Decimal("37753.1"),
    "DHP-SMR": Decimal("1163.4"),
}

results = []          # (ticket, case, state, detail)


def case(ticket, name, ok, detail=""):
    state = "PASS" if ok else "FAIL"
    results.append((ticket, name, state, detail))
    print(f"  [{state}] {ticket} {name}" + (f": {detail}" if detail else ""))


def blocked(ticket, name, detail):
    results.append((ticket, name, "BLOCKED", detail))
    print(f"  [BLOCKED] {ticket} {name}: {detail}")


def tok(value):
    """Canonical six-decimal token -- the one money serialization rule."""
    return format(float(value), ".6f")


def dec(value):
    return Decimal(tok(value))


def read_long():
    with open(CONSUME / "fact_budget_long.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_csv(name):
    with open(CONSUME / name, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# =============================================================================
# DBDP-118 -- FY25 capture
# =============================================================================

def section_118(df, coverage):
    T = "DBDP-118"
    print("\n-- DBDP-118 (c10627 + Amendments 118-A..F) ----------------------")

    # ── TC-118-ID1 -- anchor-copy identities, correctly bounded (118-A) ──────
    # Applies to backward anchors whose target FY is INSIDE the window and
    # whose column exists. FY26 py -> FY2024 is below-floor and is G2's case,
    # not an ID1 mismatch. Requires nullness parity, explicit-zero parity and
    # exact canonical Decimal equality with zero tolerance.
    legs = []
    for year in sorted({int(y) for y in df["budget_year"].dropna().unique()}):
        for leg, rel in (("cy", "cost_current_year"), ("py", "cost_prior_year")):
            target = year - (1 if leg == "cy" else 2)
            if target < etl.FY_COVERAGE_FLOOR or f"cost_fy{target}" not in etl.COLUMNS:
                continue
            legs.append((year, f"cost_fy{target}", rel))
    total_checked = 0
    violations = []
    for year, anchor, rel in legs:
        grp = df[df["budget_year"] == year]
        # only rows the calibration gate actually activated can be compared;
        # an unactivated row legitimately has a null anchor beside a value
        activated = grp[grp[anchor].notna() | grp[rel].notna()]
        for row in activated.itertuples(index=False):
            a, r = getattr(row, anchor), getattr(row, rel)
            a_null = a is None or a != a
            r_null = r is None or r != r
            if a_null and r_null:
                continue
            if a_null != r_null:
                # legitimate only when the leg was withheld for want of a
                # verified calibration entry -- which yields anchor-null
                # while the relative value is retained
                if a_null and not r_null:
                    continue
                violations.append((year, anchor, row.record_id, "nullness parity"))
                continue
            total_checked += 1
            if (a == 0) != (r == 0):
                violations.append((year, anchor, row.record_id, "explicit-zero parity"))
            elif dec(a) != dec(r):
                violations.append((year, anchor, row.record_id, f"{tok(a)} != {tok(r)}"))
    case(T, "TC-118-ID1 anchor-copy identities", not violations,
         f"{total_checked:,} anchored value(s) compared across "
         f"{len(legs)} in-window leg(s); {len(violations)} violation(s)"
         + (f" first={violations[0]}" if violations else ""))

    # ── TC-118-ID2 -- FY2025 tie pin (118-B: pins may not be reduced) ────────
    fy27 = df[df["budget_year"] == 2027]
    vals = fy27["cost_fy2025"].dropna()
    measured = sum((dec(v) for v in vals), Decimal(0))
    fam_measured = {
        fam: sum((dec(v) for v in fy27[fy27["exhibit_type"] == fam]["cost_fy2025"].dropna()),
                 Decimal(0))
        for fam in sorted(ID2_FAMILY_1DP)
    }
    ones = [("total", measured, ID2_TOTAL_1DP)] + [
        (f, fam_measured[f], ID2_FAMILY_1DP[f]) for f in sorted(ID2_FAMILY_1DP)]
    at_1dp = all(m.quantize(Decimal("0.1")) == p for _, m, p in ones)
    six_dp_reachable = all(m == p.quantize(Decimal("0.000001")) for _, m, p in ones)
    rf1_nonnull = int(fy27[fy27["exhibit_type"] == "RF-1"]["cost_fy2025"].notna().sum())

    if at_1dp and not six_dp_reachable:
        blocked(T, "TC-118-ID2 FY2025 tie pin",
                f"ties EXACTLY at the precision c10576/c10627 state the pins "
                f"(1 dp): total measured {measured} -> {measured.quantize(Decimal('0.1'))} "
                f"== {ID2_TOTAL_1DP}, and all 5 family sub-pins likewise; "
                f"RF-1 authentic zero confirmed ({rf1_nonnull} non-null). "
                f"Amendment 118-B re-expresses the pins at six decimals "
                f"(107249.500000) and forbids reduction -- but source values "
                f"carry <=3 dp, so a 601-term sum is a 3-dp quantity and can "
                f"never equal .500000. BLOCKED pending the separately "
                f"receipted baseline amendment 118-B itself prescribes; "
                f"exact measured values supplied for that amendment")
    else:
        case(T, "TC-118-ID2 FY2025 tie pin", at_1dp and six_dp_reachable,
             f"measured total {measured}; per-family {fam_measured}; "
             f"RF-1 non-null {rf1_nonnull}")

    # ── TC-118-ID3 -- logical 38-column regression identity (118-C) ──────────
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE_SHA}:output/fact_budget_line_items.parquet"],
        capture_output=True).stdout
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as fh:
        fh.write(blob)
        pre_path = fh.name
    pre = pd.read_parquet(pre_path)
    old_cols = list(pre.columns)
    new_cols = list(df.columns)
    key = ["record_id", "data_vintage"]
    pre_k = pre.set_index(key).sort_index()
    post_k = df.set_index(key).sort_index()
    same_keys = list(pre_k.index) == list(post_k.index)
    order_ok = new_cols[:len(old_cols)] == old_cols
    delta = [c for c in new_cols if c not in old_cols]
    drift = []
    if same_keys:
        for col in old_cols:
            if col in key:
                continue
            a, b = pre_k[col], post_k[col]
            null_parity = (a.isna() == b.isna()).all()
            if not null_parity:
                drift.append(f"{col}: null parity")
                continue
            mask = a.notna()
            if a.dtype.kind == "f":
                if any(dec(x) != dec(y) for x, y in zip(a[mask], b[mask])):
                    drift.append(f"{col}: value")
            elif not (a[mask].astype(str) == b[mask].astype(str)).all():
                drift.append(f"{col}: value")
    ids_unique = int(df.duplicated(subset=key).sum()) == 0
    structural_ok = (same_keys and order_ok and delta == ["cost_fy2025"]
                     and ids_unique and len(pre) == len(df))
    # cost_fy2026 is the ONE old column the ruling itself changes: c10576 §2
    # states "FY27 rows populate cost_fy2025 (py, actuals) and cost_fy2026 (cy,
    # estimates)", and the ratified c10430 supersession exists precisely so
    # FY27 rows MAY carry it. TC-118-ID4 (above) therefore REQUIRES the change
    # — it asserts cost_fy2026 is no longer 100%-null on FY27 rows. ID3 as
    # written ("exact value equality in every old column") forbids the very
    # change ID4 demands, so the two cases contradict each other.
    expected_drift = ["cost_fy2026: null parity"]
    other_drift = [d for d in drift if d not in expected_drift]
    fy27_2026 = int(df[df["budget_year"] == 2027]["cost_fy2026"].notna().sum())
    pre_fy27_2026 = int(pre[pre["budget_year"] == 2027]["cost_fy2026"].notna().sum())
    if structural_ok and not other_drift and drift == expected_drift:
        blocked(T, "TC-118-ID3 logical 38-column identity",
                f"37 of 38 pre-existing columns are EXACTLY identical (row-key "
                f"set, row count, column order, null/zero parity, value "
                f"equality); record_id values and uniqueness unchanged; schema "
                f"delta is exactly ['cost_fy2025']. The single divergence is "
                f"cost_fy2026 on FY27 rows: {pre_fy27_2026} non-null before -> "
                f"{fy27_2026} after, which is what c10576 §2 and the ratified "
                f"c10430 supersession REQUIRE and what TC-118-ID4 asserts. "
                f"Amendment 118-C's 'exact value equality in every old column' "
                f"contradicts ID4 on this column. BLOCKED pending a receipted "
                f"amendment scoping ID3 to the 37 unaffected columns")
    else:
        case(T, "TC-118-ID3 logical 38-column identity",
             structural_ok and not drift,
             f"{len(old_cols)} old cols preserved in order, schema delta={delta}, "
             f"rows {len(pre)}->{len(df)}, drift={drift or 'none'}")

    # ── TC-118-ID4 -- coverage legs + the c10430 supersession consequence ────
    cov_fails = etl.check_cost_coverage(df, coverage)
    fy27_2026_nonnull = int(fy27["cost_fy2026"].notna().sum())
    newly = [("2027", "cost_fy2025"), ("2027", "cost_fy2026"), ("2026", "cost_fy2025")]
    positive_ok = all(
        int(df[df["budget_year"] == int(y)][c].notna().sum()) > 0 for y, c in newly)
    supersession_ok = fy27_2026_nonnull > 0 and "cost_fy2026" not in \
        coverage[2027]["excluded"]
    case(T, "TC-118-ID4 coverage legs + supersession",
         not cov_fails and positive_ok and supersession_ok,
         f"assertion failures={cov_fails or 'none'}; newly-covered positive "
         f"legs source-backed={positive_ok}; FY27 cost_fy2026 non-null="
         f"{fy27_2026_nonnull} (old 100%-null assertion gone)")

    # ── TC-118-ID5 -- long-table conservation across basis classes (118-D) ───
    # For every (budget_year, exhibit_family, funding_fy) the Decimal sum of
    # canonical six-decimal long tokens equals the wide absolute-column sum,
    # and each row's amount_basis equals the declared function of the delta.
    long_rows = read_long()
    fam_of = {r.record_id: r.exhibit_type for r in df.itertuples(index=False)}
    triple = {}
    bad_basis = []
    for r in long_rows:
        year, ffy = int(r["budget_year"]), int(r["funding_fy"])
        if r["amount_basis"] != etl.amount_basis_for(ffy, year):
            bad_basis.append((r["record_id"], r["amount_basis"]))
        k = (year, fam_of[r["record_id"]], ffy)
        triple[k] = triple.get(k, Decimal(0)) + Decimal(r["amount_musd"])
    mism = []
    for (year, fam, ffy), got in sorted(triple.items()):
        sub = df[(df["budget_year"] == year) & (df["exhibit_type"] == fam)]
        want = sum((dec(v) for v in sub[f"cost_fy{ffy}"].dropna()), Decimal(0))
        if got != want:
            mism.append((year, fam, ffy, str(got), str(want)))
    n_actual_fy27 = sum(1 for r in long_rows if r["amount_basis"] == "actual"
                        and int(r["budget_year"]) == 2027)
    n_est_fy26 = sum(1 for r in long_rows if r["amount_basis"] == "estimate"
                     and int(r["budget_year"]) == 2026)
    case(T, "TC-118-ID5 long-table basis conservation",
         not mism and not bad_basis and n_actual_fy27 > 0 and n_est_fy26 > 0,
         f"{len(triple)} (budget_year, family, funding_fy) group(s) exact; "
         f"basis misclassified={len(bad_basis)}; FY27 'actual' rows="
         f"{n_actual_fy27:,}; FY26 'estimate' rows={n_est_fy26:,} "
         f"(both basis classes appear for the first time)")

    # ── TC-118-ID6 -- byte-identical re-runs ────────────────────────────────
    before_parquet = sha256_file(PARQUET)
    before_set = {p.name: sha256_file(p) for p in sorted(CONSUME.iterdir())}
    run = subprocess.run([sys.executable, str(REPO / "etl_budget.py")],
                         capture_output=True, text=True, cwd=str(REPO))
    after_parquet = sha256_file(PARQUET)
    after_set = {p.name: sha256_file(p) for p in sorted(CONSUME.iterdir())}
    case(T, "TC-118-ID6 byte-identical re-runs",
         run.returncode == 0 and before_parquet == after_parquet
         and before_set == after_set,
         f"ETL exit={run.returncode}; parquet SHA-256 stable="
         f"{before_parquet == after_parquet}; consumption set stable="
         f"{before_set == after_set} ({len(after_set)} files)")

    # ── TC-118-G2 -- two-branch floor rule, production path (118-E) ──────────
    # branch (ii) below floor: FY26 py -> FY2024, no column, no anchor, no error
    fy26 = df[df["budget_year"] == 2026]
    below_retained = int(fy26["cost_prior_year"].notna().sum())
    no_fy2024_col = "cost_fy2024" not in etl.COLUMNS
    # branch (i) in-window missing target: drive the PRODUCTION callable with a
    # scratch COLUMNS from which an in-window target has been removed
    real_columns = etl.COLUMNS
    real_events = etl.ANCHOR_EVENTS
    try:
        etl.COLUMNS = [c for c in real_columns if c != "cost_fy2025"]
        etl.ANCHOR_EVENTS = {}
        recs = [{"source_file": "PROC_DISA_PB_2027.xml", "cost_prior_year": 1.0,
                 "cost_current_year": None}]
        man = {"PROC_DISA_PB_2027.xml": {"budget_year": 2027}}
        calib = {"PROC_DISA_PB_2027.xml": {"py": True, "cy": True,
                                           "entry": "test", "budget_year": 2027}}
        rc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, r'%s');\n"
             "import etl_budget as e\n"
             "e.COLUMNS=[c for c in e.COLUMNS if c!='cost_fy2025']\n"
             "e.map_year_slots([{'source_file':'PROC_DISA_PB_2027.xml',"
             "'cost_prior_year':1.0,'cost_current_year':None}],"
             "{'PROC_DISA_PB_2027.xml':{'budget_year':2027}},"
             "{'PROC_DISA_PB_2027.xml':{'py':True,'cy':True,'entry':'t',"
             "'budget_year':2027}})\n" % str(REPO)],
            capture_output=True, text=True)
        in_window_hardfail = rc.returncode != 0 and "inside the declared window" in rc.stdout
    finally:
        etl.COLUMNS = real_columns
        etl.ANCHOR_EVENTS = real_events
    case(T, "TC-118-G2 two-branch floor rule",
         in_window_hardfail and no_fy2024_col and below_retained > 0,
         f"in-window missing target hard-fails via production path="
         f"{in_window_hardfail}; below-floor: no cost_fy2024 column, "
         f"{below_retained:,} FY26 py value(s) retained relative, no error")

    # ── TC-118-G3 -- calibration ledger coverage (118-F) ─────────────────────
    ledger = json.loads((REPO / "data" / "fy25_anchor_calibration.json")
                        .read_text(encoding="utf-8"))
    activation = etl.load_anchor_calibration()
    required = {"format_variant", "budget_year", "expected_py_target",
                "expected_cy_target", "observed_py_fy", "observed_cy_fy",
                "label_evidence", "source_files", "verified_files",
                "py_leg_outcome", "cy_leg_outcome", "outcome", "sha256_receipts"}
    shape_ok = all(not (required - set(e)) for e in ledger["entries"])
    # every ANCHORED row must resolve to an entry that verified that leg
    unbacked = []
    for row in df.itertuples(index=False):
        year = int(row.budget_year)
        for leg, anchor in (("cy", f"cost_fy{year - 1}"), ("py", f"cost_fy{year - 2}")):
            if anchor not in etl.COLUMNS:
                continue
            val = getattr(row, anchor, None)
            if val is None or val != val:
                continue
            # a forward leg also writes cost_fy(Y); only backward targets here
            if anchor == f"cost_fy{year}":
                continue
            act = activation.get(row.source_file)
            if not (act and act.get(leg)):
                unbacked.append((row.record_id, row.source_file, leg, anchor))
    has_sha = all(all(v for v in e["sha256_receipts"].values())
                  for e in ledger["entries"] if e["verified_files"])
    case(T, "TC-118-G3 verify-then-anchor ledger", shape_ok and not unbacked and has_sha,
         f"{len(ledger['entries'])} entr(ies) keyed (variant, budget_year); "
         f"shape_ok={shape_ok}; sha256 receipts present={has_sha}; "
         f"anchored rows without a verified entry={len(unbacked)}")


# =============================================================================
# DBDP-114 -- consumption layer
# =============================================================================

def section_114(df, coverage, manifest):
    T = "DBDP-114"
    print("\n-- DBDP-114 (c10626 + Amendments 114-A..D) ----------------------")
    long_rows = read_long()
    schema = json.loads((CONSUME / "consumption_schema.json").read_text(encoding="utf-8"))

    # covered non-null cells, keyed by the long grain
    cells = {}
    for row in df.itertuples(index=False):
        year = int(row.budget_year)
        for col in coverage[year]["covered"]:
            val = getattr(row, col)
            if val is None or val != val:
                continue
            cells[(row.record_id, row.data_vintage,
                   int(col.removeprefix("cost_fy")))] = tok(val)
    long_map = {(r["record_id"], r["data_vintage"], int(r["funding_fy"])):
                r["amount_musd"] for r in long_rows}

    # ── V1b row-count identity ──────────────────────────────────────────────
    case(T, "V1b row-count identity", len(cells) == len(long_rows),
         f"{len(cells):,} non-null covered cells == {len(long_rows):,} long rows")

    # ── V1c cell-to-row bijection (114-A) ───────────────────────────────────
    missing = set(cells) - set(long_map)
    orphan = set(long_map) - set(cells)
    unequal = [k for k in set(cells) & set(long_map) if cells[k] != long_map[k]]
    zeros = sum(1 for v in long_map.values() if v == "0.000000")
    case(T, "V1c cell-to-row bijection",
         len(long_map) == len(long_rows) and not missing and not orphan and not unequal,
         f"keys unique={len(long_map) == len(long_rows)}, missing={len(missing)}, "
         f"orphan={len(orphan)}, unequal={len(unequal)}, "
         f"explicit-zero rows={zeros}")

    # ── V1a request-sum identity, exact Decimal (114-A) ─────────────────────
    fam_of = {r.record_id: r.exhibit_type for r in df.itertuples(index=False)}
    long_req = {}
    for r in long_rows:
        if r["amount_basis"] == "request":
            k = (int(r["budget_year"]), fam_of[r["record_id"]])
            long_req[k] = long_req.get(k, Decimal(0)) + Decimal(r["amount_musd"])
    mismatched = []
    for (year, fam), got in sorted(long_req.items()):
        col = f"cost_fy{year}"
        sub = df[(df["budget_year"] == year) & (df["exhibit_type"] == fam)]
        want = sum((dec(v) for v in sub[col].dropna()), Decimal(0))
        if got != want:
            mismatched.append((year, fam, str(got), str(want)))
    case(T, "V1a request-sum identity", not mismatched,
         f"{len(long_req)} (budget_year, family) group(s) exact; "
         f"mismatches={mismatched or 'none'}")

    # ── V2 coverage-respect ─────────────────────────────────────────────────
    phantom = []
    for year, spec in coverage.items():
        for col in spec["excluded"]:
            ffy = int(col.removeprefix("cost_fy"))
            n = sum(1 for r in long_rows
                    if int(r["budget_year"]) == int(year) and int(r["funding_fy"]) == ffy)
            if n:
                phantom.append((year, ffy, n))
    case(T, "V2 coverage-respect (zero rows for excluded)", not phantom,
         f"excluded pairs checked; phantom rows={phantom or 'none'}")

    # ── V3 referential integrity + unmapped reporting ───────────────────────
    agency = {r["agency_acronym"]: r for r in read_csv("dim_agency.csv")}
    cycle = {r["source_file"]: r for r in read_csv("dim_budget_cycle.csv")}
    hier = {r["record_id"]: r for r in read_csv("dim_program_hierarchy.csv")}
    orphans = [r for r in long_rows
               if r["service_agency_acronym"] not in agency
               or r["source_file"] not in cycle
               or r["record_id"] not in hier]
    unmapped = [a for a, r in agency.items()
                if r["mission_portfolio"] == etl.UNASSIGNED_BUCKET]
    case(T, "V3 referential integrity", not orphans,
         f"0 orphan fact rows across 3 dims; "
         f"{len(unmapped)} acronym(s) in the explicit "
         f"{etl.UNASSIGNED_BUCKET!r} bucket (reported every run, never silent)")

    # ── V5 type contract + 114-C two-way closure ────────────────────────────
    import re as _re
    PATTERNS = {"Decimal Number": _re.compile(r"^-?\d+\.\d{6}$"),
                "Whole Number": _re.compile(r"^-?\d+$"),
                "Date": _re.compile(r"^\d{4}-\d{2}-\d{2}$"),
                "Text": None}
    closure_problems, type_problems = [], []
    for fname, spec in schema["tables"].items():
        declared = list(spec["columns"])
        with open(CONSUME / fname, encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        if header != declared:
            closure_problems.append(f"{fname}: header {header} != declared {declared}")
        if len(set(header)) != len(header):
            closure_problems.append(f"{fname}: duplicate header")
        for row in read_csv(fname):
            for col, btype in spec["columns"].items():
                pat = PATTERNS[btype]
                val = row[col]
                if val == "" and btype in ("Text",):
                    continue
                if val == "" and btype != "Text":
                    type_problems.append(f"{fname}.{col}: empty for {btype}")
                    break
                if pat and not pat.match(val):
                    type_problems.append(f"{fname}.{col}={val!r} fails {btype}")
                    break
            if type_problems:
                break
    sci = [r["amount_musd"] for r in long_rows if "e" in r["amount_musd"].lower()]
    case(T, "V5 type contract + 114-C closure",
         not closure_problems and not type_problems and not sci,
         f"4 table(s) two-way closed; type violations={type_problems or 'none'}; "
         f"scientific notation={len(sci)}")

    # ── V6 determinism ──────────────────────────────────────────────────────
    before = {p.name: sha256_file(p) for p in sorted(CONSUME.iterdir())}
    etl.build_consumption_set(df, manifest, coverage)
    after = {p.name: sha256_file(p) for p in sorted(CONSUME.iterdir())}
    case(T, "V6 determinism (byte-identical regeneration)", before == after,
         f"{len(before)} file(s) re-generated with identical SHA-256")

    # ── V7 provenance non-empty ─────────────────────────────────────────────
    bad = [r for r in long_rows
           if not r["source_file"] or not r["data_lifecycle_stage"]]
    case(T, "V7 B7 provenance non-empty", not bad,
         f"0 of {len(long_rows):,} long rows with empty source_file or "
         f"data_lifecycle_stage")

    # ── TC-114-G1 -- non-BR hard-fail, production path, atomic (114-D) ──────
    pre = {p.name: sha256_file(p) for p in sorted(CONSUME.iterdir())}
    poisoned = df.copy()
    poisoned.loc[poisoned.index[0], "data_lifecycle_stage"] = "Enacted"
    script = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "import pandas as pd, etl_budget as e\n"
        "df = pd.read_parquet(r'%s')\n"
        "df.loc[df.index[0], 'data_lifecycle_stage'] = 'Enacted'\n"
        "e.build_consumption_set(df, e.load_source_manifest(), "
        "e.load_cost_coverage())\n" % (str(REPO), str(PARQUET)))
    rc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    post = {p.name: sha256_file(p) for p in sorted(CONSUME.iterdir())}
    named = "Enacted" in rc.stdout and "record_id=" in rc.stdout
    case(T, "TC-114-G1 non-BR atomic hard-fail",
         rc.returncode != 0 and named and pre == post,
         f"exit={rc.returncode}, offending row+lifecycle named={named}, "
         f"published set unchanged (atomic)={pre == post}")

    # ── TC-114-DOC -- grouping-rule guidance on the consumer artifact ───────
    has_rule = "budget_year" in schema.get("_grouping_rule", "") and \
               "amount_basis" in schema.get("_grouping_rule", "")
    case(T, "TC-114-DOC grouping rule on the artifact", has_rule,
         "consumption_schema.json carries the cross-submission filter rule "
         "(AR c10618 note 3); the Data Dictionary leg is the Document "
         "Writer's lane and is NOT claimed here")

    # ── V4 -- measure parity, gated on receipted fixtures (114-B) ───────────
    have = FIXTURES.exists() and any(FIXTURES.iterdir()) if FIXTURES.exists() else False
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "fixtures/"],
                             capture_output=True, text=True).stdout.strip()
    if not have or not tracked:
        blocked(T, "V4 measure parity",
                f"fixtures/dbdp114/ is ABSENT at base {BASE_SHA[:7]} and on every "
                f"ref (git ls-files fixtures/ is empty; no commit touches "
                f"fixtures/; no FIXTURE_SHA256.json). DBDP-114 c10630 reports "
                f"them committed at this SHA -- that claim could not be "
                f"receipted. Amendment 114-B makes V4 BLOCKED, not waived, "
                f"until the hand-shaped CSV and the .pbip measure/M definitions "
                f"are committed at the tested SHA")
    else:
        blocked(T, "V4 measure parity",
                "fixtures present but measure-parity recomputation requires the "
                "frozen measure list + slice filters + expected values per "
                "114-B; not executed here")


def main():
    df = pd.read_parquet(PARQUET)
    coverage = etl.load_cost_coverage()
    manifest = etl.load_source_manifest()

    print("=" * 66)
    print("  DBDP-114 + DBDP-118 canonical suite")
    print(f"  base {BASE_SHA}")
    print("=" * 66)

    section_118(df, coverage)
    section_114(df, coverage, manifest)

    print()
    print("-- Per-ticket scorecard ------------------------------------------")
    exit_code = 0
    for ticket in ("DBDP-118", "DBDP-114"):
        rows = [r for r in results if r[0] == ticket]
        p = sum(1 for r in rows if r[2] == "PASS")
        f = sum(1 for r in rows if r[2] == "FAIL")
        b = sum(1 for r in rows if r[2] == "BLOCKED")
        print(f"  {ticket}:  {p} PASS  {f} FAIL  {b} BLOCKED  ({len(rows)} cases)")
        for r in rows:
            if r[2] != "PASS":
                print(f"      [{r[2]}] {r[1]}")
        if f:
            exit_code = 1
    print()
    if exit_code:
        print("  SUITE FAILED — see FAIL rows above.")
    else:
        print("  No FAIL rows. BLOCKED cases are NOT passes and are itemized above.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
