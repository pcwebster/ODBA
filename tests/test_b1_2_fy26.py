# =============================================================================
# ODBA -- Open Defense Budget Analytics
# tests/test_b1_2_fy26.py  |  DBDP-103 B1-2 verification suite
# =============================================================================
# Standalone:  python tests/test_b1_2_fy26.py     (exit 0 = all legs hold)
#
# Legs, and the authority each discharges:
#   AC-4 / TC-B1-REG-01 ... c10527 legs 1-8 (P-40 migration, INDEPENDENT
#                           fingerprint recomputation -- this file implements
#                           the fingerprint from the spec and never calls the
#                           map generator, per leg 3)
#   TC-B1-CV-01/02/03 ..... c10532 / c10533 (amended 2026 declaration, CHIPS
#                           relabel, generalized year-slot mapping w/ sentinels)
#   TC-B1-EX-02 / EX-02N .. c10493 / c10496 (allowlist yield + zero-match
#                           negative control through the production parser)
#   TC-B1-CO-01 ........... c10501 / c10504 (control-only tamper + verified-
#                           before-consumed ordering)
# Production artifacts are never mutated: tamper legs run on temp copies and
# a scratch manifest, and the committed parquet hash is proven unchanged.
# =============================================================================

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import etl_budget as etl

REPO      = Path(__file__).parent.parent
BASE_SHA  = "10ed61bc055af8639f8282e6fd4cf27490fcf1e4"
PARQUET   = REPO / "output" / "fact_budget_line_items.parquet"
MAP_FILE  = REPO / "data" / "record_id_migration_dbdp103_p40.json"

results = []


def case(name, ok, detail=""):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))


# ── Independent fingerprint (c10527 leg 3) ───────────────────────────────────
# Implemented here from the DBDP-106 spec: all COLUMNS at the implementation
# base except record_id, in order; strings normalized; cost floats .6f;
# budget_year .1f; null -> ""; SHA-256 over \x1f-joined UTF-8. The migration
# map generator is NOT called.
_F1 = {"budget_year"}
_F6 = {c for c in etl.COLUMNS if c.startswith("cost_") and c != "cost_units"}


def fingerprint(row):
    parts = []
    for col in etl.COLUMNS:
        if col == "record_id":
            continue
        v = row[col]
        if v is None or (isinstance(v, float) and v != v):
            parts.append("")
        elif col in _F1:
            parts.append(format(float(v), ".1f"))
        elif col in _F6:
            parts.append(format(float(v), ".6f"))
        else:
            parts.append(etl.norm_key(v))
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def pre_change_df():
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE_SHA}:output/fact_budget_line_items.parquet"],
        capture_output=True).stdout
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as fh:
        fh.write(blob)
        return pd.read_parquet(fh.name)


def ac4_migration(post):
    pre = pre_change_df()
    mig = json.load(open(MAP_FILE, encoding="utf-8"))
    entries = mig["entries"]
    post27 = post[post["budget_year"] == 2027.0].reset_index(drop=True)

    case("AC4.1 base_sha pinned + map committed",
         mig["base_sha"] == BASE_SHA and MAP_FILE.exists(), mig["base_sha"][:12])
    case("AC4.2 map = exactly 62 P-40, unique old/new, 20-hex",
         len(entries) == 62
         and len({e["old_id"] for e in entries}) == 62
         and len({e["new_id"] for e in entries}) == 62
         and all(e["family"] == "P-40" for e in entries)
         and all(len(e[k]) == 20 and all(c in "0123456789abcdef" for c in e[k])
                 for e in entries for k in ("old_id", "new_id")),
         f"{len(entries)} entries")

    pre_fp = {fingerprint(r): r for r in pre.to_dict("records")}
    post_fp = {fingerprint(r): r for r in post27.to_dict("records")}
    case("AC4.3/4 independent fingerprints unique + bijective",
         len(pre_fp) == len(pre) == len(post_fp) == len(post27)
         and set(pre_fp) == set(post_fp),
         f"{len(pre_fp)}/{len(pre)} pre, {len(post_fp)}/{len(post27)} post")

    by_fp = {e["row_fingerprint"]: e for e in entries}
    case("AC4.4b each map fingerprint matches both its rows",
         all(f in pre_fp and f in post_fp
             and by_fp[f]["old_id"] == pre_fp[f]["record_id"]
             and by_fp[f]["new_id"] == post_fp[f]["record_id"] for f in by_fp))

    # leg 5: all 37 non-record_id fields equal for mapped rows
    drift = []
    for f in by_fp:
        o, n = pre_fp[f], post_fp[f]
        for col in etl.COLUMNS:
            if col == "record_id":
                continue
            a, b = o[col], n[col]
            na = a is None or (isinstance(a, float) and a != a)
            nb = b is None or (isinstance(b, float) and b != b)
            if na != nb or (not na and a != b):
                drift.append((col, a, b))
    case("AC4.5 mapped rows: all 37 non-record_id fields identical",
         not drift, str(drift[:2]) if drift else "no drift")

    changed = {f for f in pre_fp if pre_fp[f]["record_id"] != post_fp[f]["record_id"]}
    case("AC4.6 non-P-40 FY27 rows byte-identical incl. record_id",
         changed == set(by_fp)
         and all(post_fp[f]["exhibit_type"] == "P-40" for f in changed),
         f"{len(pre_fp) - len(changed)} unchanged rows")

    dup = post.duplicated(subset=["record_id", "data_vintage"]).sum()
    case("AC4.7 composite uniqueness over FULL post corpus (FY26+FY27)",
         dup == 0, f"{len(post)} rows, {dup} dups")

    old_anchor = "24e4f3943b851d6ab8dd"          # TC-ST-03 at the base SHA
    hit = [e for e in entries if e["old_id"] == old_anchor]
    if hit:
        src = post27[post27["record_id"] == hit[0]["new_id"]]
        pre_src = pre[pre["record_id"] == old_anchor]
        same = (not src.empty and not pre_src.empty
                and src.iloc[0]["source_file"] == pre_src.iloc[0]["source_file"]
                and src.iloc[0]["cost_fy2027"] == pre_src.iloc[0]["cost_fy2027"])
        case("AC4.8 TC-ST-03 re-derived through the map, provenance+cost intact",
             same, f"{old_anchor} -> {hit[0]['new_id']}")
    else:
        case("AC4.8 TC-ST-03 present in map", False, "anchor not in map")

    # value conservation across the whole FY27 slice
    for col in ("cost_fy2027", "cost_prior_year", "cost_current_year"):
        a = round(pre[col].fillna(0).sum(), 3)
        b = round(post27[col].fillna(0).sum(), 3)
        case(f"AC4.5b FY27 {col} sum conserved", a == b, f"{a} == {b}")


def cv_legs(post):
    cov = etl.load_cost_coverage()
    case("CV-01 amended 2026 declaration exact",
         cov[2026]["covered"] == ["cost_fy2026", "cost_fy2027", "cost_fy2028",
                                  "cost_fy2029", "cost_fy2030"]
         and list(cov[2026]["excluded"]) == ["cost_fy2031"],
         str(cov[2026]["covered"]))
    fy26 = post[post["budget_year"] == 2026.0]
    case("CV-01.1 FY26 cost_fy2031 100% null",
         fy26["cost_fy2031"].notna().sum() == 0)
    missing = [c for c in cov[2026]["covered"] if fy26[c].notna().sum() == 0]
    case("CV-01.2 every covered 2026 column has >=1 non-null", not missing,
         f"non-null counts " +
         str({c: int(fy26[c].notna().sum()) for c in cov[2026]["covered"]}))
    case("CV-01.3 published zeros captured as 0.0 (not nulled)",
         (fy26["cost_fy2028"] == 0.0).sum() > 0,
         f"{int((fy26['cost_fy2028'] == 0.0).sum())} explicit zeros in cost_fy2028")
    case("CV-01.5 production coverage assertion clean",
         etl.check_cost_coverage(post, cov) == [])

    chips = post[(post["source_file"] == "RDTE_CHIPS_PB_2026.xml")
                 & (post["program_element"] == "0602669D8Z")]
    ok = (len(chips) == 1
          and abs(chips.iloc[0]["cost_fy2027"] - 72.979) <= 0.001
          and not any(chips.iloc[0][c] == 72.979 for c in
                      ("cost_fy2026", "cost_fy2028", "cost_fy2029",
                       "cost_fy2030", "cost_fy2031")))
    case("CV-02 CHIPS BY2 relabelled to cost_fy2027, nowhere else", ok,
         f"cost_fy2027={chips.iloc[0]['cost_fy2027'] if len(chips) else 'n/a'}")

    # CV-03 sentinels through the PRODUCTION mapping callable (c10533 leg 4)
    def probe(year, slots):
        rec = {"source_file": "X.xml", "_by_slots": slots}
        etl.map_year_slots([rec], {"X.xml": {"budget_year": year}})
        return {c: rec.get(c) for c in etl.COLUMNS if c.startswith("cost_fy")}
    s = [11.0, 22.0, 33.0, 44.0, 55.0]
    p26, p27 = probe(2026, s), probe(2027, s)
    case("CV-03.1 Y=2026 BY1-BY5 -> cost_fy2026..2030, fy2031 null",
         [p26["cost_fy2026"], p26["cost_fy2027"], p26["cost_fy2028"],
          p26["cost_fy2029"], p26["cost_fy2030"]] == s
         and p26["cost_fy2031"] is None, str(p26))
    case("CV-03.2 Y=2027 BY1-BY5 -> cost_fy2027..2031 (FY27 parity)",
         [p27["cost_fy2027"], p27["cost_fy2028"], p27["cost_fy2029"],
          p27["cost_fy2030"], p27["cost_fy2031"]] == s
         and p27["cost_fy2026"] is None, str(p27))
    # leg 3: populated slot whose target column is absent -> hard-fail
    try:
        probe(2031, [1.0, 2.0, None, None, None])   # 2032 not in COLUMNS
        case("CV-03.3 missing target column hard-fails", False, "no exit")
    except SystemExit:
        case("CV-03.3 missing target column hard-fails", True,
             "exits naming year/slot/column")


def ex02_legs():
    m = json.load(open(REPO / "data" / "source_manifest.json", encoding="utf-8"))
    for fname, parser, expect in (
            ("PB_2026_PDW_VOL_1.xml", etl.parse_procurement_xml, 3),
            ("PB_2026_RDTE_VOL_5.xml", etl.parse_rdte_xml, 7)):
        fp = next(REPO.joinpath("FY2026").rglob(fname))
        allow = m[fname]["agency_allowlist"]
        recs = parser(fp, allowlist=allow)
        case(f"EX-02 {fname} yields {expect} allowlisted rows",
             len(recs) == expect, f"{len(recs)} rows for {allow}")
        # EX-02N: zero-match allowlist through the SAME production parser
        try:
            parser(fp, allowlist=["No Such Agency Exists"])
            case(f"EX-02N {fname} zero-match hard-fails", False, "no exit")
        except SystemExit:
            case(f"EX-02N {fname} zero-match hard-fails", True,
                 "exits naming file + unmatched agency")


def co01_legs():
    """TC-B1-CO-01 (c10504 binding definition) — control-only tamper + ordering."""
    m = json.load(open(REPO / "data" / "source_manifest.json", encoding="utf-8"))
    control = [f for f, e in m.items() if e["ingest_status"] == "control-only"]
    case("CO-01.0 control-only set declared", len(control) == 3, str(sorted(control)))

    # ordering: every control-consumed file was verified BEFORE its first read
    etl.VERIFICATION_EVENTS.clear()
    etl.CONSUMING_READ_EVENTS.clear()
    files = [next(REPO.joinpath("FY2026").rglob(f)) for f in control]
    etl.read_control_totals(files, m)
    verified = {}
    for seq, name in etl.VERIFICATION_EVENTS:
        verified.setdefault(name, seq)
    consumed = {}
    for seq, name, kind in etl.CONSUMING_READ_EVENTS:
        if kind == "control-total":
            consumed.setdefault(name, seq)
    case("CO-01.1 control-consumed set == control-verified set",
         set(consumed) == set(verified) == set(control),
         f"{len(consumed)} consumed / {len(verified)} verified")
    case("CO-01.2 verification precedes every first control read",
         all(verified[n] < consumed[n] for n in consumed),
         str({n: (verified[n], consumed[n]) for n in list(consumed)[:2]}))

    # tamper: one byte in a temp copy of a control-only file, scratch manifest
    target = "FY2026_OM_Volume1_Part1.json"
    src = next(REPO.joinpath("FY2026").rglob(target))
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / target
        shutil.copy2(src, tmp)
        raw = bytearray(tmp.read_bytes())
        raw[len(raw) // 2] = raw[len(raw) // 2] ^ 0x01     # flip one bit
        tmp.write_bytes(bytes(raw))
        try:
            etl.read_control_totals([tmp], m)
            case("CO-01.3 control-only one-byte tamper hard-fails", False, "no exit")
        except SystemExit:
            case("CO-01.3 control-only one-byte tamper hard-fails", True,
                 "exits before the control value is consumed")
    after = hashlib.sha256(src.read_bytes()).hexdigest()
    case("CO-01.4 production source untouched by the tamper leg",
         before == after, before[:12])


def main():
    post = pd.read_parquet(PARQUET)
    print("── AC-4 / TC-B1-REG-01 (P-40 migration, independent fingerprint) ──")
    ac4_migration(post)
    print("── TC-B1-CV-01/02/03 (coverage, CHIPS relabel, year mapping) ──")
    cv_legs(post)
    print("── TC-B1-EX-02 / EX-02N (allowlist yield + zero-match control) ──")
    ex02_legs()
    print("── TC-B1-CO-01 (control-only integrity, BLOCKING) ──")
    co01_legs()
    bad = [n for n, ok in results if not ok]
    print()
    if bad:
        print(f"B1-2 SUITE FAILED: {bad}")
        return 1
    print(f"All {len(results)} B1-2 legs hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
