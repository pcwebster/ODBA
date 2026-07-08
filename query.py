# =============================================================================
# ODBA -- Open Defense Budget Analytics
# query.py  |  Tier-1 DuckDB query helper (DBDP-95, design c10295 + c10305)
# =============================================================================
# Source-traceable query/lookup over output/fact_budget_line_items.parquet.
#
#   python query.py                     interactive SQL prompt (view: budget)
#   python query.py --list              list canned queries
#   python query.py <canned> [arg]      run a canned query
#   python query.py --sql "SELECT ..."  one-shot SQL
#   ... --csv <path>                    export the (primary) result as CSV
#
# B7 non-negotiable (c10305 unconditional rule): EVERY result rendered or
# exported must carry both source_file and data_lifecycle_stage, regardless
# of result content -- nothing about the data is inspected, so there is no
# stringify/retype/alias disguise that evades it. Enforced in shape_result()
# -- the single render/write path in this file. No override flag exists.
# DESCRIBE/SHOW/EXPLAIN (metadata, not data cells) are exempt. Only these
# plus SELECT/WITH are accepted; the dataset is never written.
# =============================================================================

import argparse
import csv
import sys
from pathlib import Path

import duckdb

if hasattr(sys.stdout, "reconfigure"):   # Windows console: render UTF-8 data
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR   = Path(__file__).parent.resolve()
PARQUET_FILE = SCRIPT_DIR / "output" / "fact_budget_line_items.parquet"

# Dollar-type detection survives only for friendlier refusal MESSAGING
# (c10305 demoted it from gate to hint; the gate itself inspects nothing).
DOLLAR_TYPE_PREFIXES = ("DOUBLE", "DECIMAL")
NON_DOLLAR_FLOATS    = {"budget_year"}   # sole non-dollar float, excepted by name

# Exact-first-token whitelists (c10305): provenance-gated vs metadata-exempt.
GATED_TOKENS  = ("select", "with")
EXEMPT_TOKENS = ("describe", "show", "explain")

REFUSAL = """\
REFUSED: this result is missing {missing}.{dollar_hint}
Every rendered or exported result must carry source_file +
data_lifecycle_stage (B7 rule, unconditional -- c10305).
Rewrite pattern -- line-level: add source_file, data_lifecycle_stage to the
SELECT list. Aggregates: add data_lifecycle_stage to the GROUP BY and select
array_agg(DISTINCT source_file) AS source_file. There is no override flag."""

# name: (description, needs_arg)
CANNED_HELP = {
    "totals-by-exhibit": ("line-item count + FY2027 $ by exhibit_type", False),
    "totals-by-agency":  ("FY2027 $ by service_agency_acronym", False),
    "find":              ("<text> case-insensitive match on line_item_title / "
                          "program_element / line_item_number", True),
    "trace":             ("<record_id> one record, all fields, vertical", True),
    "by-source":         ("<source_file> all lines + FY2027 sum for one source file", True),
}

_AGG_SQL = """
    SELECT {key},
           COUNT(*)                        AS line_items,
           SUM(cost_fy2027)                AS cost_fy2027,
           data_lifecycle_stage,
           array_agg(DISTINCT source_file) AS source_file
    FROM budget
    GROUP BY {key}, data_lifecycle_stage
    ORDER BY cost_fy2027 DESC"""

_FIND_SQL = """
    SELECT record_id, exhibit_type, service_agency_acronym, line_item_number,
           program_element, line_item_title,
           cost_all_prior_years, cost_prior_year, cost_current_year,
           cost_fy2027, cost_fy2028, cost_fy2029, cost_fy2030, cost_fy2031,
           cost_units, source_file, data_lifecycle_stage
    FROM budget
    WHERE line_item_title ILIKE '%' || ? || '%'
       OR program_element ILIKE '%' || ? || '%'
       OR line_item_number ILIKE '%' || ? || '%'
    ORDER BY cost_fy2027 DESC NULLS LAST"""


def canned_plan(name, arg):
    """Return a list of (title, sql, params, vertical) for one canned query."""
    if name == "totals-by-exhibit":
        return [(name, _AGG_SQL.format(key="exhibit_type"), [], False)]
    if name == "totals-by-agency":
        return [(name, _AGG_SQL.format(key="service_agency_acronym"), [], False)]
    if name == "find":
        return [(f"find '{arg}'", _FIND_SQL, [arg, arg, arg], False)]
    if name == "trace":
        return [(f"trace {arg}",
                 "SELECT * FROM budget WHERE record_id = ?", [arg], True)]
    if name == "by-source":
        return [(f"lines from {arg}",
                 "SELECT * FROM budget WHERE source_file = ?", [arg], False),
                (f"sum for {arg}",
                 "SELECT COUNT(*) AS line_items, SUM(cost_fy2027) AS cost_fy2027,"
                 " data_lifecycle_stage, array_agg(DISTINCT source_file) AS source_file"
                 " FROM budget WHERE source_file = ? GROUP BY data_lifecycle_stage",
                 [arg], False)]
    return None


def connect():
    con = duckdb.connect()   # in-memory; read_parquet cannot write back
    path = str(PARQUET_FILE).replace("'", "''")
    con.execute(f"CREATE VIEW budget AS SELECT * FROM read_parquet('{path}')")
    return con


def first_token(sql):
    """Defense-in-depth exact-first-token classification (c10305)."""
    return sql.lstrip().split(None, 1)[0].lower() if sql.strip() else ""


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def shape_result(cols, types, rows, title, vertical=False, csv_path=None,
                 exempt=False):
    """SOLE output path: compliance gate, then render (or CSV-write) a result.

    Gate (c10305, unconditional): unless the statement class is exempt
    (DESCRIBE/SHOW/EXPLAIN -- metadata, not data cells), the result must
    contain both provenance columns. Nothing about the data is inspected.
    Returns True if rendered/written, False if refused."""
    if not exempt:
        missing = [c for c in ("source_file", "data_lifecycle_stage") if c not in cols]
        if missing:
            dollar_cols = [c for c, t in zip(cols, types)
                           if str(t).upper().startswith(DOLLAR_TYPE_PREFIXES)
                           and c not in NON_DOLLAR_FLOATS]
            hint = (f"\n(dollar-derived columns present: {', '.join(dollar_cols)})"
                    if dollar_cols else "")
            print(REFUSAL.format(missing=" + ".join(missing), dollar_hint=hint))
            return False

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([_fmt(v) for v in r])
        print(f"-- {title}: wrote {len(rows)} row(s) to {csv_path}")
        return True

    print(f"-- {title} ({len(rows)} row(s))")
    if vertical:
        width = max((len(c) for c in cols), default=0)
        for r in rows:
            for c, v in zip(cols, r):
                print(f"  {c:<{width}} : {_fmt(v)}")
            print()
        return True
    cells = [[_fmt(v)[:60] for v in r] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) if cells else len(c)
              for i, c in enumerate(cols)]
    print("  " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  " + "-+-".join("-" * w for w in widths))
    for row in cells:
        print("  " + " | ".join(v.ljust(w) for v, w in zip(row, widths)))
    return True


def run_statement(con, sql, params, title, vertical=False, csv_path=None):
    """Execute one statement and hand the result to shape_result().

    Returns an exit code: 0 ok, 2 refused."""
    token = first_token(sql)
    if token not in GATED_TOKENS + EXEMPT_TOKENS:
        print("REFUSED: only SELECT/WITH (and DESCRIBE/SHOW/EXPLAIN) statements "
              "are accepted (read-only helper; the dataset is never written).")
        return 2
    try:
        cur = con.execute(sql, params)
        cols  = [d[0] for d in cur.description]
        types = [d[1] for d in cur.description]
        rows  = cur.fetchall()
    except duckdb.Error as e:
        # Controlled refusal, never a traceback (c10305 / c10303 secondary).
        print(f"REFUSED: statement not executable as a read-only query -- "
              f"{str(e).splitlines()[0]}")
        return 2
    return 0 if shape_result(cols, types, rows, title, vertical, csv_path,
                             exempt=token in EXEMPT_TOKENS) else 2


def repl(con):
    print(f"ODBA tier-1 query helper -- view 'budget' over {PARQUET_FILE.name}")
    cols = [r[0] for r in con.execute("DESCRIBE budget").fetchall()]
    print(f"columns: {', '.join(cols)}")
    print("SELECT/WITH only; every result must carry source_file + "
          "data_lifecycle_stage (DESCRIBE/SHOW/EXPLAIN exempt). 'exit' to quit.")
    while True:
        try:
            line = input("budget> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            return 0
        run_statement(con, line, [], "result")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="ODBA tier-1 DuckDB query helper (DBDP-95). "
                    "Every rendered or exported result carries source_file + "
                    "data_lifecycle_stage (B7, unconditional).",
        epilog="Provenance labels are read from the dataset. Selecting literal "
               "values AS source_file / data_lifecycle_stage fabricates "
               "provenance -- falsification, not omission; outside the tier-1 "
               "honest-operator threat model and accepted as residual (c10305).")
    p.add_argument("command", nargs="*",
                   help="canned query name (+ argument where required); see --list")
    p.add_argument("--list", action="store_true", help="list canned queries")
    p.add_argument("--sql", metavar="SQL", help="one-shot SELECT/WITH statement")
    p.add_argument("--csv", metavar="PATH",
                   help="write the (primary) result to PATH as CSV")
    args = p.parse_args(argv)

    if args.list:
        for name, (desc, _) in CANNED_HELP.items():
            print(f"  {name:<18} {desc}")
        return 0

    if not PARQUET_FILE.exists():
        print(f"error: {PARQUET_FILE} not found -- run etl_budget.py first.")
        return 1
    con = connect()

    if args.sql:
        return run_statement(con, args.sql, [], "sql", csv_path=args.csv)

    if not args.command:
        return repl(con)

    name, rest = args.command[0], args.command[1:]
    if name not in CANNED_HELP:
        print(f"error: unknown query '{name}' -- try --list")
        return 1
    needs_arg = CANNED_HELP[name][1]
    if needs_arg and len(rest) != 1:
        print(f"error: '{name}' takes exactly one argument -- see --list")
        return 1
    if not needs_arg and rest:
        print(f"error: '{name}' takes no argument")
        return 1

    code = 0
    for i, (title, sql, params, vertical) in enumerate(canned_plan(name, rest[0] if rest else None)):
        csv_path = args.csv if i == 0 else None   # --csv exports the primary result
        code = max(code, run_statement(con, sql, params, title, vertical, csv_path))
    return code


if __name__ == "__main__":
    sys.exit(main())
