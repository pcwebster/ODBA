"""DBDP-132 replay check (design c10751 as revised by c10763, finding 1).

Run where the FY2027_Budget_JSON source files live, from the same input
snapshot, and copy each run's output/ folder aside:

    git checkout main                && python etl_budget.py && python query_budget.py
    cp -r output /tmp/dbdp132_baseline
    git checkout <DBDP-132 branch>   && python etl_budget.py && python query_budget.py
    cp -r output /tmp/dbdp132_branch
    python etl_budget.py && python query_budget.py
    cp -r output /tmp/dbdp132_rerun

    python tools/dbdp132_replay_check.py \
        --baseline /tmp/dbdp132_baseline --branch /tmp/dbdp132_branch \
        --rerun /tmp/dbdp132_rerun

It checks, and exits 1 on any failure:
  1. exactly one record_id added (the 0146D row), none removed, every other
     row identical in every column;
  2. the new row has FY2025 and FY2026 blank and FY2027 22,175.472 $M;
  3. the seven 0130D rows of the pinned Vol 1 source are unchanged, with
     0130D 020 FY2027 blank and the FY2027 sum 18,955.553 $M;
  4. every file of the second branch run is byte-identical to the first.
It does not verify the separate DBDP-118 historical replay.
"""
import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import etl_budget as etl  # noqa: E402

PARQUET = "fact_budget_line_items.parquet"


def _m6(v):
    return None if v is None or pd.isna(v) else format(float(v), ".6f")


def _rows_equal(a, b):
    """Column-by-column equality with blank == blank (never blank == 0)."""
    diffs = []
    for col in a.index:
        x, y = a[col], b[col]
        if pd.isna(x) and pd.isna(y):
            continue
        if pd.isna(x) != pd.isna(y) or x != y:
            diffs.append(col)
    return diffs


def check(baseline_dir, branch_dir, rerun_dir=None):
    fails = []
    base = pd.read_parquet(Path(baseline_dir) / PARQUET)
    branch = pd.read_parquet(Path(branch_dir) / PARQUET)
    if list(base.columns) != list(branch.columns):
        fails.append("column list changed")
        return fails

    b_ids, n_ids = set(base["record_id"]), set(branch["record_id"])
    added, removed = n_ids - b_ids, b_ids - n_ids
    want = etl.make_id(etl.MHS_PSCP_SOURCE, "0146D", "020")
    if added != {want}:
        fails.append(f"added record_ids {sorted(added)}, expected [{want}]")
    if removed:
        fails.append(f"removed record_ids {sorted(removed)[:10]}")

    common = sorted(b_ids & n_ids)
    bi = base.set_index("record_id").loc[common]
    ni = branch.set_index("record_id").loc[common]
    changed = {}
    for rid in common:
        d = _rows_equal(bi.loc[rid], ni.loc[rid])
        if d:
            changed[rid] = d
    if changed:
        sample = list(changed.items())[:5]
        fails.append(f"{len(changed)} existing rows changed, e.g. {sample}")

    new = branch[branch["record_id"] == want]
    if len(new) == 1:
        r = new.iloc[0]
        if _m6(r["cost_fy2027"]) != "22175.472000":
            fails.append(f"0146D cost_fy2027 {_m6(r['cost_fy2027'])}")
        for col in ("cost_prior_year", "cost_current_year",
                    "cost_fy2025", "cost_fy2026"):
            if _m6(r[col]) is not None:
                fails.append(f"0146D {col} is {_m6(r[col])}, expected blank")

    comp = branch[(branch["source_file"] == etl.MHS_PSCP_SOURCE)
                  & (branch["appropriation_code"] == "0130D")]
    pins = etl.MHS_PSCP_PINS
    if (len(comp) != pins["comp_rows"]
            or _m6(comp["cost_fy2027"].sum(min_count=1)) != _m6(pins["comp_fy27_sum_m"])):
        fails.append("0130D rows of the pinned source changed")
    psc = comp[comp["budget_sub_activity_number"] == "020"]
    if len(psc) != 1 or _m6(psc.iloc[0]["cost_fy2027"]) is not None:
        fails.append("0130D 020 FY2027 is not blank")

    if rerun_dir is not None:
        def digests(d):
            d = Path(d)
            return {p.relative_to(d).as_posix():
                    hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(d.rglob("*")) if p.is_file()}
        first, second = digests(branch_dir), digests(rerun_dir)
        if first != second:
            diff = sorted(k for k in set(first) | set(second)
                          if first.get(k) != second.get(k))
            fails.append(f"second branch run not byte-identical: {diff}")
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", required=True, help="output/ copy from main")
    ap.add_argument("--branch", required=True, help="output/ copy from the branch")
    ap.add_argument("--rerun", help="output/ copy from a second branch run")
    args = ap.parse_args(argv)
    fails = check(args.baseline, args.branch, args.rerun)
    for f in fails:
        print(f"[FAIL] {f}")
    if not fails:
        print("[PASS] DBDP-132 replay: +1 record_id (0146D), none removed, "
              "others identical, 0130D unchanged"
              + (", rerun byte-identical" if args.rerun else
                 "; rerun NOT checked (--rerun not given)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
