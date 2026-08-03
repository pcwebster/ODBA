# =============================================================================
# ODBA -- Open Defense Budget Analytics
# tests/test_coverage_bypass_regressions.py  |  DBDP-102 coverage-guard suite
# =============================================================================
# Permanent regression cases for the DBDP-102 coverage assertion, per the
# S6/S7 discipline (DBDP-95): a reviewer's reproduced attacks become the
# suite. R1/R2 are Codex's two PR #5 bypasses (DBDP-102 c10455); CV-04/05
# are the original AC-2 adversarial legs (c10387).
#
# Standalone -- no test framework required:
#   python tests/test_coverage_bypass_regressions.py
# Exit 0 = all regressions hold; exit 1 = a bypass has been reintroduced.
# Every case exercises the SAME callable the production run uses
# (etl_budget.check_cost_coverage / load_cost_coverage) against the
# committed parquet, per the Codex c10382 executable-path rule.
# =============================================================================

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import etl_budget as etl

PARQUET = Path(__file__).parent.parent / "output" / "fact_budget_line_items.parquet"

results = []


def case(name, ok, detail):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def main():
    df = pd.read_parquet(PARQUET)
    cov = etl.load_cost_coverage()

    # ── R1 (c10455 finding 1) — positive-leg exception bypass stays dead ─────
    # R1a: a coverage file carrying positive_leg_exceptions must be REJECTED
    # at load (the mechanism was removed; no configured exception may exempt
    # a covered column).
    bad_cov = json.loads(json.dumps({
        "2027": {
            "covered": ["cost_fy2027", "cost_fy2028", "cost_fy2029",
                        "cost_fy2030", "cost_fy2031"],
            "excluded": {"cost_fy2026": "x"},
            "positive_leg_exceptions": {"cost_fy2031": ""},
        }
    }))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(bad_cov, fh)
        bad_path = fh.name
    try:
        etl.load_cost_coverage(bad_path)
        case("R1a exception-key rejected at load", False,
             "loader ACCEPTED positive_leg_exceptions — bypass reintroduced")
    except SystemExit:
        case("R1a exception-key rejected at load", True,
             "loader hard-fails on positive_leg_exceptions key")

    # R1b: even a hand-built coverage dict smuggling an exceptions key cannot
    # exempt a covered all-null column from the positive leg (the checker
    # consults no exception structure at all).
    m1 = df.copy()
    m1["cost_fy2031"] = None
    smuggled = {y: dict(spec, positive_leg_exceptions={"cost_fy2031": ""})
                for y, spec in cov.items()}
    fails = etl.check_cost_coverage(m1, smuggled)
    hit = any("positive-leg" in f and "cost_fy2031" in f for f in fails)
    case("R1b smuggled exceptions ignored by checker", hit,
         f"covered all-null column still fails: {fails[:1]}")

    # ── R2 (c10455 finding 2) — budget_year bypasses stay dead ───────────────
    # R2a: null budget_year row carrying a value in a declared-absent column.
    m2 = df.copy()
    i = m2.index[0]
    m2.loc[i, "budget_year"] = None
    m2.loc[i, "cost_fy2026"] = 1.0
    fails = etl.check_cost_coverage(m2, cov)
    hit = any("null budget_year" in f for f in fails)
    case("R2a null budget_year hard-fails", hit, f"{fails[:1]}")

    # R2b: non-integral budget_year (2027.5) row carrying a value in a
    # declared-absent column.
    m3 = df.copy()
    m3.loc[i, "budget_year"] = 2027.5
    m3.loc[i, "cost_fy2026"] = 1.0
    fails = etl.check_cost_coverage(m3, cov)
    hit = any("non-integral" in f for f in fails)
    case("R2b non-integral budget_year hard-fails", hit, f"{fails[:1]}")

    # ── original AC-2 adversarial legs stay live (c10387) ────────────────────
    # TC-CV-04: value injected into a declared-absent column.
    m4 = df.copy()
    m4.loc[m4.index[7], "cost_fy2026"] = 12.3
    fails = etl.check_cost_coverage(m4, cov)
    hit = any("declared-absent violation" in f and "cost_fy2026" in f for f in fails)
    case("TC-CV-04 declared-absent injection fails", hit, f"{fails[:1]}")

    # TC-CV-05: the production dataframe (authentic RF-1 per-line nulls in a
    # covered column) passes clean.
    fails = etl.check_cost_coverage(df, cov)
    case("TC-CV-05 production dataframe clean", fails == [], f"failures={fails}")

    bad = [n for n, ok, _ in results if not ok]
    print()
    if bad:
        print(f"REGRESSION SUITE FAILED: {bad}")
        return 1
    print(f"All {len(results)} coverage-guard regressions hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
