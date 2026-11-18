# =============================================================================
# ODBA -- Open Defense Budget Analytics
# query_budget.py  |  FY2027 Budget Report Generator
# =============================================================================
# Reads fact_budget_line_items.parquet and writes a multi-tab Excel workbook:
#   1. Summary          -- total funding by appropriation type
#   2. By Agency        -- FY2027 totals ranked by agency
#   3. Year-over-Year   -- prior year vs FY2027, dollar + % change
#   4. RDT&E by BA      -- R&D budget activity breakdown (BA1-BA8)
#   5. Procurement      -- P-1 line items with full funding profile
#   6. RDT&E            -- R-1 program elements with full funding profile
#   7. All Records      -- complete data dump (all schema columns)
#   8. ETL Run Summary  -- record counts, FY2027 totals, blank-field counts,
#                          lifecycle confirmation and provenance (DBDP-43)
#   9. FYDP Trends      -- FY2025-FY2031 by appropriation type, each year
#                          labelled with its amount basis, plus a chart (DBDP-44)
#
# Output: output/ODBA_FY2027_Budget_Report.xlsx
# =============================================================================

import hashlib
import io
import os
import re
import sys
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

# DBDP-94 c10336 Ruling 1: the schema column list has exactly one home —
# etl_budget.COLUMNS. No second hardcoded enumeration may exist here.
from etl_budget import COLUMNS
# DBDP-44: the year columns and their amount basis have one home too: the
# consumption layer's ABSOLUTE_COST_COLUMNS and amount_basis_for (c10575).
from etl_budget import ABSOLUTE_COST_COLUMNS, amount_basis_for

# DBDP-43 review round 2: openpyxl picks its XML writer when it is first
# imported (lxml when installed, else the standard library), and the two
# write different bytes. Pin the standard-library writer so the workbook
# does not depend on whether lxml happens to be installed. This must run
# before the first openpyxl import in the process; save_workbook_deterministic
# refuses to write if openpyxl was already imported with lxml on.
os.environ["OPENPYXL_LXML"] = "False"

from openpyxl import load_workbook
from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                              numbers)
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.data_source import AxDataSource, StrRef
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent.resolve()
PARQUET_FILE = SCRIPT_DIR / "output" / "fact_budget_line_items.parquet"
OUTPUT_DIR   = SCRIPT_DIR / "output"
OUTPUT_FILE  = OUTPUT_DIR / "ODBA_FY2027_Budget_Report.xlsx"

# ── Colors (DoD blue palette) ─────────────────────────────────────────────────
HEADER_FILL   = PatternFill("solid", fgColor="1F3864")   # dark navy
SUBHEAD_FILL  = PatternFill("solid", fgColor="2E75B6")   # medium blue
ALT_ROW_FILL  = PatternFill("solid", fgColor="DCE6F1")   # light blue
TOTAL_FILL    = PatternFill("solid", fgColor="BDD7EE")   # accent blue
WHITE_FILL    = PatternFill("solid", fgColor="FFFFFF")
NEG_FILL      = PatternFill("solid", fgColor="FCE4D6")   # salmon for decreases

HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
SUBHEAD_FONT  = Font(bold=True, color="FFFFFF", size=10)
TOTAL_FONT    = Font(bold=True, size=10)
BODY_FONT     = Font(size=10)
TITLE_FONT    = Font(bold=True, size=14, color="1F3864")

THIN = Side(style="thin", color="B8CCE4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

NUM_FMT  = '#,##0.0'      # millions with one decimal
COUNT_FMT = '#,##0'

# ── DBDP-43: ETL Run Summary sheet ────────────────────────────────────────────
RUN_SUMMARY_SHEET = "ETL Run Summary"
# Key fields whose blank/null counts are reported per exhibit type.
RUN_SUMMARY_KEY_FIELDS = ("line_item_title", "budget_activity_number",
                          "program_element")
REPORT_STAGE = "Budget Request"
REPORT_BUDGET_YEAR = 2027
FYDP_SHEET = "FYDP Trends"
# Ticket order (DBDP-44); any other appropriation type in the slice follows
# alphabetically so nothing is silently dropped.
FYDP_APPROP_ORDER = ("O&M", "Procurement", "RDT&E", "DWCF", "DHP")
BASIS_LABELS = {"actual": "Actual", "estimate": "Estimate",
                "request": "Request", "fydp_projection": "FYDP projection"}
PCT_FMT  = '+0.0%;-0.0%;0.0%'
DELTA_FMT = '+#,##0.0;-#,##0.0;0.0'


# =============================================================================
# Helpers
# =============================================================================

def autofit(ws, min_width=8, max_width=60):
    """Set column widths based on content."""
    for col_cells in ws.columns:
        length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in col_cells
        )
        col_letter = get_column_letter(col_cells[0].column)
        ws.column_dimensions[col_letter].width = min(max(length + 2, min_width), max_width)


def write_df(ws, df, start_row=1, header_fill=None, alt_rows=True,
             number_cols=None, pct_cols=None, delta_cols=None):
    """
    Write a DataFrame to a worksheet with formatting.
    Returns the row number after the last data row.
    """
    hfill = header_fill or HEADER_FILL
    number_cols = number_cols or []
    pct_cols    = pct_cols    or []
    delta_cols  = delta_cols  or []

    # Header row
    for c_idx, col_name in enumerate(df.columns, 1):
        cell = ws.cell(row=start_row, column=c_idx, value=col_name)
        cell.font   = HEADER_FONT
        cell.fill   = hfill
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Data rows
    for r_idx, row in enumerate(df.itertuples(index=False), 1):
        fill = ALT_ROW_FILL if (alt_rows and r_idx % 2 == 0) else WHITE_FILL
        for c_idx, (col_name, value) in enumerate(zip(df.columns, row), 1):
            cell = ws.cell(row=start_row + r_idx, column=c_idx, value=value)
            cell.font   = BODY_FONT
            cell.fill   = fill
            cell.border = BORDER
            if col_name in number_cols:
                cell.number_format = NUM_FMT
                cell.alignment = Alignment(horizontal="right")
            elif col_name in pct_cols:
                cell.number_format = PCT_FMT
                cell.alignment = Alignment(horizontal="right")
                if isinstance(value, (int, float)) and value < 0:
                    cell.fill = NEG_FILL
            elif col_name in delta_cols:
                cell.number_format = DELTA_FMT
                cell.alignment = Alignment(horizontal="right")
                if isinstance(value, (int, float)) and value < 0:
                    cell.fill = NEG_FILL
            else:
                cell.alignment = Alignment(wrap_text=False)

    return start_row + len(df) + 1


def add_title(ws, title, subtitle=None, row=1):
    """Write a sheet title + optional subtitle."""
    ws.cell(row=row, column=1, value=title).font = TITLE_FONT
    if subtitle:
        ws.cell(row=row + 1, column=1, value=subtitle).font = Font(italic=True, size=10, color="595959")
    return row + (2 if subtitle else 1)   # DBDP-66: header directly under subtitle (row 3) so skiprows=2 works


def freeze_top(ws, data_start_row):
    """Freeze the header row."""
    ws.freeze_panes = ws.cell(row=data_start_row + 1, column=1)


# =============================================================================
# Queries
# =============================================================================

def run_queries(parquet_path):
    con = duckdb.connect()
    p = str(parquet_path).replace("\\", "/")
    # DBDP-50: bind path as parameter instead of f-string interpolation
    # DuckDB supports ? placeholders: con.execute("... read_parquet(?) ...", [p])

    # ── Report guard (DBDP-102 AC-4; AR c10430 binding note a) ────────────────
    # This workbook is a single-year, single-lifecycle, single-vintage report.
    # The three-part pin is FY2027 + 'Budget Request' + one declared vintage;
    # a bare budget_year pin is NOT sufficient once Enacted rows (B1-3) or a
    # restated vintage exist. Hard-fail if more than one lifecycle stage or
    # vintage is eligible for the slice — multi-year/multi-stage reporting is
    # future B7 tier-2 work, a deliberate redesign, never a silent fold-in.
    eligible = con.execute("""
        SELECT DISTINCT data_lifecycle_stage, data_vintage
        FROM read_parquet(?)
        WHERE budget_year = 2027.0 AND data_lifecycle_stage = 'Budget Request'
    """, [p]).fetchall()
    all_pairs = con.execute("""
        SELECT DISTINCT data_lifecycle_stage, data_vintage
        FROM read_parquet(?) WHERE budget_year = 2027.0
    """, [p]).fetchall()
    stages   = sorted({s for s, _ in all_pairs})
    vintages = sorted({v for _, v in eligible})
    if len(stages) > 1 or len(vintages) != 1:
        print("  [FATAL] report guard (DBDP-102 AC-4): the FY2027 report slice "
              "must be exactly one lifecycle stage ('Budget Request') and one "
              "data_vintage.")
        print(f"          eligible stages within budget_year=2027: {stages}")
        print(f"          eligible vintages within FY2027 Budget Request: {vintages}")
        print("          Multi-stage/multi-vintage reporting is a deliberate "
              "B7 tier-2 redesign — refusing to render a mixed workbook.")
        sys.exit(1)
    vintage = vintages[0]
    # Pin all report queries to the validated slice. Literals are inlined
    # only after validation above, escaped, sourced from the parquet itself.
    slice_sql = ("SELECT * FROM read_parquet('{}') WHERE budget_year = 2027.0 "
                 "AND data_lifecycle_stage = 'Budget Request' "
                 "AND data_vintage = '{}'").format(
                     p.replace("'", "''"), vintage.replace("'", "''"))
    con.execute(f"CREATE TEMP VIEW report_slice AS {slice_sql}")
    print(f"  Report slice: budget_year=2027.0 | Budget Request | vintage {vintage}")

    print("  Running queries...")

    # Every ORDER BY below ends in a unique key (group keys, or record_id,
    # which is unique within the single-vintage slice) so tied rows cannot
    # swap places between runs (byte-identical re-runs; DBDP-43 review).

    # 1. Summary by appropriation type
    q_summary = con.execute("""
        SELECT
            appropriation_type                         AS "Appropriation Type",
            exhibit_type                               AS "Exhibit",
            COUNT(*)                                   AS "# Line Items",
            ROUND(COALESCE(SUM(cost_prior_year), 0), 1)       AS "Prior Year ($M)",
            ROUND(COALESCE(SUM(cost_fy2027),     0), 1)       AS "FY2027 Request ($M)",
            ROUND(COALESCE(SUM(cost_fy2027), 0) - COALESCE(SUM(cost_prior_year), 0), 1) AS "Change ($M)",
            CASE WHEN SUM(cost_prior_year) > 0
                 THEN (SUM(cost_fy2027) - SUM(cost_prior_year)) / SUM(cost_prior_year)
                 ELSE NULL END                         AS "Change (%)"
        FROM report_slice
        -- DBDP-66 TC-ER-09R: no dollar filter, so every appropriation_type (incl. DWCF) gets a Summary row
        GROUP BY 1, 2
        ORDER BY "FY2027 Request ($M)" DESC NULLS LAST, 1, 2
    """).df()

    # 2. By agency
    q_agency = con.execute("""
        SELECT
            service_agency_acronym                     AS "Agency",
            service_agency_name                        AS "Agency Name",
            appropriation_type                         AS "Appropriation",
            COUNT(*)                                   AS "# Line Items",
            ROUND(SUM(cost_prior_year), 1)             AS "Prior Year ($M)",
            ROUND(SUM(cost_fy2027),     1)             AS "FY2027 Request ($M)",
            ROUND(SUM(cost_fy2027) - SUM(cost_prior_year), 1) AS "Change ($M)",
            CASE WHEN SUM(cost_prior_year) > 0
                 THEN (SUM(cost_fy2027) - SUM(cost_prior_year)) / SUM(cost_prior_year)
                 ELSE NULL END                         AS "Change (%)"
        FROM report_slice
        GROUP BY 1, 2, 3
        ORDER BY "FY2027 Request ($M)" DESC NULLS LAST, 1, 2, 3
    """).df()

    # 3. Year-over-year by line item (XML records with both years populated)
    q_yoy = con.execute("""
        SELECT
            service_agency_acronym                     AS "Agency",
            appropriation_type                         AS "Type",
            COALESCE(NULLIF(line_item_title,''), line_item_title) AS "Line Item / Program",
            program_element                            AS "PE / Line #",
            budget_activity_number                     AS "BA",
            ROUND(cost_prior_year, 1)                  AS "FY2025 Actuals ($M)",
            ROUND(cost_fy2027,     1)                  AS "FY2027 Request ($M)",
            ROUND(cost_fy2027 - cost_prior_year, 1)    AS "Change ($M)",
            CASE WHEN cost_prior_year > 0
                 THEN (cost_fy2027 - cost_prior_year) / cost_prior_year
                 ELSE NULL END                         AS "Change (%)"
        FROM report_slice
        WHERE file_format = 'XML'
          AND cost_prior_year IS NOT NULL
          AND cost_fy2027     IS NOT NULL
        ORDER BY ABS(cost_fy2027 - cost_prior_year) DESC NULLS LAST, record_id
    """).df()

    # 4. RDT&E by Budget Activity
    q_ba = con.execute("""
        SELECT
            budget_activity_number                     AS "BA",
            budget_activity_title                      AS "Budget Activity Title",
            COUNT(*)                                   AS "# Programs",
            ROUND(SUM(cost_prior_year), 1)             AS "FY2025 Actuals ($M)",
            ROUND(SUM(cost_fy2027),     1)             AS "FY2027 Request ($M)",
            ROUND(SUM(cost_fy2028),     1)             AS "FY2028 FYDP ($M)",
            ROUND(SUM(cost_fy2029),     1)             AS "FY2029 FYDP ($M)",
            ROUND(SUM(cost_fy2030),     1)             AS "FY2030 FYDP ($M)",
            ROUND(SUM(cost_fy2031),     1)             AS "FY2031 FYDP ($M)"
        FROM report_slice
        WHERE appropriation_type = 'RDT&E'
        GROUP BY 1, 2
        ORDER BY CAST(budget_activity_number AS INTEGER) NULLS LAST, 1, 2
    """).df()

    # 5. Procurement detail
    q_proc = con.execute("""
        SELECT
            service_agency_acronym                     AS "Agency",
            line_item_number                           AS "Line #",
            line_item_title                            AS "Line Item Title",
            budget_activity_number                     AS "BA",
            budget_activity_title                      AS "BA Title",
            ROUND(cost_all_prior_years, 1)             AS "All Prior ($M)",
            ROUND(cost_prior_year,  1)                 AS "FY2025 Actuals ($M)",
            ROUND(cost_current_year,1)                 AS "FY2026 Enacted ($M)",
            ROUND(cost_fy2027,      1)                 AS "FY2027 Request ($M)",
            ROUND(cost_fy2028,      1)                 AS "FY2028 ($M)",
            ROUND(cost_fy2029,      1)                 AS "FY2029 ($M)",
            ROUND(cost_fy2030,      1)                 AS "FY2030 ($M)",
            ROUND(cost_fy2031,      1)                 AS "FY2031 ($M)",
            source_file                                AS "Source File"
        FROM report_slice
        WHERE appropriation_type = 'Procurement'
        ORDER BY service_agency_acronym, budget_activity_number, line_item_number,
                 record_id
    """).df()

    # 6. RDT&E detail
    q_rdte = con.execute("""
        SELECT
            service_agency_acronym                     AS "Agency",
            program_element                            AS "PE Number",
            line_item_title                            AS "Program Element Title",
            budget_activity_number                     AS "BA",
            budget_activity_title                      AS "BA Title",
            ROUND(cost_prior_year,  1)                 AS "FY2025 Actuals ($M)",
            ROUND(cost_fy2027,      1)                 AS "FY2027 Request ($M)",
            ROUND(cost_fy2028,      1)                 AS "FY2028 ($M)",
            ROUND(cost_fy2029,      1)                 AS "FY2029 ($M)",
            ROUND(cost_fy2030,      1)                 AS "FY2030 ($M)",
            ROUND(cost_fy2031,      1)                 AS "FY2031 ($M)",
            source_file                                AS "Source File"
        FROM report_slice
        WHERE appropriation_type = 'RDT&E'
        ORDER BY service_agency_acronym, budget_activity_number, program_element,
                 record_id
    """).df()

    # 7. All records — SELECT * so the sheet always carries the full schema
    #    (parquet column order == etl_budget.COLUMNS; DBDP-94 c10336 Ruling 1)
    q_all = con.execute("""
        SELECT *
        FROM report_slice
        ORDER BY appropriation_type, service_agency_acronym, line_item_number,
                 record_id
    """).df()
    # funding_type / funding_type_signal are genuinely NULL until the B5
    # classifier lands; openpyxl cannot write pandas NA — render as empty
    # cells without touching the parquet's NULL state.
    q_all = q_all.astype(object).where(q_all.notna(), None)

    run_summary = run_summary_queries(con, parquet_path, vintage)
    # DBDP-44 rides in the same extras dict so run_queries keeps its shape.
    run_summary["fydp_trends"] = fydp_trend_queries(con)

    return {
        "Summary":        q_summary,
        "By Agency":      q_agency,
        "Year-over-Year": q_yoy,
        "RDT&E by BA":    q_ba,
        "Procurement":    q_proc,
        "RDT&E":          q_rdte,
        "All Records":    q_all,
    }, run_summary


# =============================================================================
# DBDP-43: ETL Run Summary
# =============================================================================
# Everything on this sheet derives from the parquet bytes and the manifest
# values already carried in it (data_vintage, data_lifecycle_stage). Nothing
# derives from the wall clock or file mtimes, so the same parquet always gives
# the same sheet (CLAUDE.md byte-identical rule). That is why the sheet shows
# the data vintage and the parquet SHA-256 instead of an ETL run timestamp.

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _blank(col):
    """SQL predicate: value is NULL or an empty/whitespace-only string."""
    return f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '') IS NULL"


def _check(label, ok_count, total, detail):
    ok_count = int(ok_count or 0)
    total = int(total or 0)
    return {"Check":           label,
            "Result":          "PASS" if total > 0 and ok_count == total else "FAIL",
            "Records Passing": ok_count,
            "Records Checked": total,
            "Detail":          detail}


def run_summary_queries(con, parquet_path, vintage):
    """Build the DBDP-43 sections from the validated report_slice view.

    Returns a dict of DataFrames: provenance, checks, exhibits, missing.
    Row order is fixed by ORDER BY on unique group keys, so it is stable
    across runs.
    """
    p = str(parquet_path).replace("\\", "/")

    n_slice = con.execute("SELECT COUNT(*) FROM report_slice").fetchone()[0]
    n_files = con.execute(
        "SELECT COUNT(DISTINCT source_file) FROM report_slice").fetchone()[0]

    # (1)+(2) records and FY2027 request by exhibit type. SUM over all-NULL
    # stays NULL (blank cell), never 0: blank is not zero. Rounded to $K
    # (3 decimals in $M) only to drop float noise.
    exhibits = con.execute("""
        SELECT
            exhibit_type                         AS "Exhibit Type",
            appropriation_type                   AS "Appropriation Type",
            COUNT(*)                             AS "Records",
            COUNT(cost_fy2027)                   AS "Records with FY2027 Amount",
            ROUND(SUM(cost_fy2027), 3)           AS "FY2027 Request ($M)",
            COUNT(DISTINCT source_file)          AS "Source Files"
        FROM report_slice
        GROUP BY 1, 2
        ORDER BY 2, 1
    """).df()
    total = con.execute("""
        SELECT 'Total', '', COUNT(*), COUNT(cost_fy2027),
               ROUND(SUM(cost_fy2027), 3), COUNT(DISTINCT source_file)
        FROM report_slice
    """).fetchone()
    exhibits = pd.concat(
        [exhibits, pd.DataFrame([list(total)], columns=exhibits.columns)],
        ignore_index=True)
    exhibits = exhibits.astype(object).where(exhibits.notna(), None)

    # (3) blank/null counts in key fields, per exhibit type
    blank_cols = ",\n".join(
        f'            SUM(CASE WHEN {_blank(c)} THEN 1 ELSE 0 END) AS "{c} blank"'
        for c in RUN_SUMMARY_KEY_FIELDS)
    missing = con.execute(f"""
        SELECT
            exhibit_type                         AS "Exhibit Type",
            COUNT(*)                             AS "Records",
{blank_cols}
        FROM report_slice
        GROUP BY 1
        ORDER BY 1
    """).df()
    missing_total = ["Total"] + [int(missing[c].sum()) for c in missing.columns[1:]]
    missing = pd.concat(
        [missing, pd.DataFrame([missing_total], columns=missing.columns)],
        ignore_index=True)
    for c in missing.columns[1:]:
        missing[c] = missing[c].astype(int)

    # (4) lifecycle confirmation over ALL FY2027 rows in the parquet, not
    # just the slice: the slice is filtered on the stage, so counting it
    # there would prove nothing.
    n_fy27, n_fy27_br = con.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN data_lifecycle_stage = ? THEN 1 ELSE 0 END)
        FROM read_parquet(?) WHERE budget_year = 2027.0
    """, [REPORT_STAGE, p]).fetchone()
    n_unique = con.execute("""
        SELECT COUNT(*) FROM (SELECT DISTINCT record_id, data_vintage
                              FROM report_slice)
    """).fetchone()[0]
    n_fmt = con.execute("""
        SELECT COUNT(*) FROM report_slice
        WHERE regexp_full_match(record_id, '[0-9a-f]{20}')
    """).fetchone()[0]
    n_src = con.execute(f"""
        SELECT COUNT(*) FROM report_slice WHERE NOT ({_blank("source_file")})
    """).fetchone()[0]
    n_vint = con.execute(f"""
        SELECT COUNT(*) FROM report_slice WHERE NOT ({_blank("data_vintage")})
    """).fetchone()[0]
    checks = pd.DataFrame([
        _check("data_lifecycle_stage = Budget Request", n_fy27_br, n_fy27,
               "All FY2027 records in the dataset, not only the report slice"),
        _check("(record_id, data_vintage) unique", n_unique, n_slice,
               "Distinct composite keys in the report slice"),
        _check("record_id format", n_fmt, n_slice,
               "20 lowercase hex characters"),
        _check("source_file populated", n_src, n_slice,
               "Every record names the file it was parsed from"),
        _check("data_vintage populated", n_vint, n_slice,
               "Source acquisition date from the download manifest"),
    ])

    years = [int(y) for (y,) in con.execute(
        "SELECT DISTINCT budget_year FROM read_parquet(?) "
        "WHERE budget_year IS NOT NULL ORDER BY 1", [p]).fetchall()]
    # NULL / empty stages outside the slice are shown as labels, never
    # dropped or allowed to break the join (DBDP-43 review advisory).
    stages = ["(null)" if s is None else (s if s.strip() else "(blank)")
              for (s,) in con.execute(
                  "SELECT DISTINCT data_lifecycle_stage FROM read_parquet(?) "
                  "ORDER BY 1 NULLS LAST", [p]).fetchall()]
    n_all = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [p]).fetchone()[0]

    # (5) provenance. No run timestamp: see the block comment above.
    provenance = pd.DataFrame([
        ("Report slice", f"FY2027 | {REPORT_STAGE} | data_vintage {vintage}"),
        ("Data vintage (source acquisition date, download manifest)", vintage),
        ("Run timestamp", "Not stamped. The data vintage and dataset SHA-256 "
                          "identify the input snapshot. With the pinned "
                          "requirements.txt packages, re-running on the same "
                          "dataset writes a byte-identical workbook."),
        ("Source files contributing records", int(n_files)),
        ("Records in report slice", int(n_slice)),
        ("Dataset file", Path(parquet_path).name),
        ("Dataset SHA-256", sha256_file(parquet_path)),
        ("Records in dataset (all budget years)", int(n_all)),
        ("Budget years in dataset", ", ".join(str(y) for y in years)),
        ("Lifecycle stages in dataset", ", ".join(stages)),
    ], columns=["Item", "Value"])

    return {"provenance": provenance, "checks": checks,
            "exhibits": exhibits, "missing": missing, "vintage": vintage}


def _style_total_row(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = TOTAL_FILL
        cell.font = TOTAL_FONT


def _section(ws, row, text):
    ws.cell(row=row, column=1, value=text).font = Font(bold=True, size=12,
                                                       color="1F3864")
    return row + 1


def _note(ws, row, text):
    ws.cell(row=row, column=1, value=text).font = Font(italic=True, size=9,
                                                       color="595959")
    return row + 1


def write_run_summary(wb, summary):
    """Append the DBDP-43 ETL Run Summary sheet to the workbook."""
    ws = wb.create_sheet(title=RUN_SUMMARY_SHEET)
    row = add_title(
        ws, "ETL Run Summary -- Data Completeness and Provenance",
        "Check these figures before relying on the other sheets  |  "
        "Dollars in Millions  |  Lifecycle Stage: Budget Request")
    count_cols = (["Records", "Records with FY2027 Amount", "Source Files",
                   "Records Passing", "Records Checked"]
                  + [f"{c} blank" for c in RUN_SUMMARY_KEY_FIELDS])

    def table(df, start):
        end = write_df(ws, df, start_row=start,
                       number_cols=["FY2027 Request ($M)"])
        for c_idx, name in enumerate(df.columns, 1):
            if name in count_cols:
                for r in range(start + 1, end):
                    cell = ws.cell(row=r, column=c_idx)
                    cell.number_format = COUNT_FMT
                    cell.alignment = Alignment(horizontal="right")
        return end

    row += 1
    row = _section(ws, row, "Provenance")
    row = table(summary["provenance"], row)
    for r in range(row - len(summary["provenance"]), row):
        v = ws.cell(row=r, column=2)
        if isinstance(v.value, int):
            v.number_format = COUNT_FMT
        v.alignment = Alignment(horizontal="left")

    row += 1
    row = _section(ws, row, "Validation checks")
    row = table(summary["checks"], row)
    for r in range(row - len(summary["checks"]), row):
        res = ws.cell(row=r, column=2)
        res.font = Font(bold=True, size=10,
                        color="375623" if res.value == "PASS" else "C00000")

    row += 1
    row = _section(ws, row, "Records and FY2027 request by exhibit type")
    row = table(summary["exhibits"], row)
    _style_total_row(ws, row - 1, len(summary["exhibits"].columns))
    row = _note(ws, row, "Exhibit types are the source exhibits the records "
                "were parsed from (OP-5 for O&M, P-40 for Procurement, R-2 for "
                "RDT&E, RF-1 for DWCF, DHP-J-Book and DHP-SMR for DHP).")
    row = _note(ws, row, "A blank FY2027 amount means no record in that group "
                "carries an FY2027 value. Blank is not zero.")

    row += 1
    row = _section(ws, row, "Records with blank or null key fields")
    row = table(summary["missing"], row)
    _style_total_row(ws, row - 1, len(summary["missing"].columns))
    _note(ws, row, "Counts of records where the field is null or empty. "
          "Whether a field applies to an exhibit type is not judged here.")

    autofit(ws)
    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 66
    return ws


# =============================================================================
# DBDP-44: FYDP Trends
# =============================================================================
# Sums the absolute year columns (cost_fy2025..cost_fy2031) over the validated
# report_slice by appropriation type. Each year is labelled with the basis the
# consumption layer assigns it for the FY2027 submission (amount_basis_for,
# c10575): FY2025 actual, FY2026 estimate, FY2027 request, FY2028-FY2031 FYDP
# projection. Every figure is from the FY2027 President's Budget Request
# submission (AR c10045); the basis says which column of that submission it
# is. A year with no amounts for a type stays blank, never zero.

def fydp_year_columns():
    """[(column, fiscal_year, header label)] in fiscal-year order."""
    out = []
    for col in ABSOLUTE_COST_COLUMNS:
        fy = int(col.removeprefix("cost_fy"))
        basis = BASIS_LABELS[amount_basis_for(fy, REPORT_BUDGET_YEAR)]
        out.append((col, fy, f"FY{fy} {basis} ($M)"))
    return sorted(out, key=lambda t: t[1])


def fydp_trend_queries(con):
    years = fydp_year_columns()
    sums = ",\n".join(f'ROUND(SUM({c}), 1) AS "{label}"' for c, _, label in years)
    counts = ",\n".join(f'COUNT({c}) AS "FY{fy}"' for c, fy, _ in years)
    amounts = con.execute(f"""
        SELECT appropriation_type AS "Appropriation Type", {sums}
        FROM report_slice GROUP BY 1
    """).df()
    records = con.execute(f"""
        SELECT appropriation_type AS "Appropriation Type",
               COUNT(*) AS "Records", {counts}
        FROM report_slice GROUP BY 1
    """).df()

    def ordered(df):
        types = list(df["Appropriation Type"])
        order = ([t for t in FYDP_APPROP_ORDER if t in types]
                 + sorted(t for t in types if t not in FYDP_APPROP_ORDER))
        df = df.set_index("Appropriation Type").loc[order].reset_index()
        # blank stays blank: pandas NaN -> None so openpyxl writes no value
        return df.astype(object).where(df.notna(), None)

    amounts, records = ordered(amounts), ordered(records)
    for name in records.columns[1:]:
        records[name] = [int(v) for v in records[name]]
    return {"amounts": amounts, "records": records,
            "years": [(fy, label) for _, fy, label in years]}


def write_fydp_trends(wb, fydp, vintage):
    """Append the DBDP-44 FYDP Trends sheet: table, coverage, chart."""
    ws = wb.create_sheet(title=FYDP_SHEET)
    years = fydp["years"]
    first_fy, last_fy = years[0][0], years[-1][0]
    by_basis = {}
    for fy, label in years:
        by_basis.setdefault(label.split(" ", 1)[1].removesuffix(" ($M)"), []).append(fy)

    def span(fys):
        return f"FY{fys[0]}" if len(fys) == 1 else f"FY{fys[0]}-FY{fys[-1]}"

    row = add_title(
        ws, f"FYDP Trends -- FY{first_fy}-FY{last_fy} by Appropriation Type",
        f"Dollars in Millions  |  Lifecycle Stage: {REPORT_STAGE}  |  "
        f"FY{REPORT_BUDGET_YEAR} submission, data vintage {vintage}")
    row = _note(ws, row,
                f"Every figure on this sheet is from the FY{REPORT_BUDGET_YEAR} "
                "President's Budget Request submission. None of it is enacted, "
                "apportioned or execution data recorded by ODBA.")
    basis_text = "; ".join(f"{span(fys)} {b if b.startswith('FYDP') else b.lower()}"
                           for b, fys in by_basis.items())
    row = _note(ws, row,
                "Each year is labelled with its column in that submission: "
                f"{basis_text}. Prior- and current-year columns are as printed "
                "in the request exhibits.")
    row += 1

    row = _section(ws, row, "Funding by appropriation type")
    table_header = row
    money = [label for _, label in years]
    row = write_df(ws, fydp["amounts"], start_row=row, number_cols=money)
    table_end = row - 1
    row = _note(ws, row, "A blank cell means no record of that appropriation "
                "type carries an amount for that year. Blank is not zero.")
    row = _note(ws, row, "Types differ in which years their exhibits publish, so "
                "do not read a drop to blank as a funding cut. A change between "
                "years can also come from records that carry an amount in one "
                "year and not the next; compare the record counts below.")
    row += 1

    row = _section(ws, row, "Records with an amount, by year")
    end = write_df(ws, fydp["records"], start_row=row)
    for r in range(row + 1, end):
        for c in range(2, len(fydp["records"].columns) + 1):
            cell = ws.cell(row=r, column=c)
            cell.number_format = COUNT_FMT
            cell.alignment = Alignment(horizontal="right")
    row = end + 1

    # Chart: one line per appropriation type that has any amount. Blank
    # years show as gaps, not as zero.
    chart = LineChart()
    chart.title = f"FY{REPORT_BUDGET_YEAR} President's Budget Request ($M)"
    chart.y_axis.title = "$M"
    chart.x_axis.title = "Fiscal year (amount basis)"
    chart.display_blanks = "gap"
    chart.x_axis.delete = False          # openpyxl 3.1 hides axes by default
    chart.y_axis.delete = False
    chart.height, chart.width = 9, 22
    ncols = len(fydp["amounts"].columns)
    for i, values in enumerate(fydp["amounts"].itertuples(index=False)):
        if all(v is None for v in values[1:]):
            continue
        r = table_header + 1 + i
        chart.add_data(Reference(ws, min_col=1, max_col=ncols, min_row=r, max_row=r),
                       from_rows=True, titles_from_data=True)
    # Year headers are text, so point the categories at them as strings.
    cats = Reference(ws, min_col=2, max_col=ncols,
                     min_row=table_header, max_row=table_header)
    for series in chart.series:
        series.cat = AxDataSource(strRef=StrRef(f=str(cats)))
        series.smooth = False            # straight segments: no invented curve
    ws.add_chart(chart, f"A{row}")

    autofit(ws)
    ws.column_dimensions["A"].width = 22
    for c in range(2, ncols + 1):
        ws.column_dimensions[get_column_letter(c)].width = 18
    return ws


# =============================================================================
# Deterministic save (DBDP-43 review: byte-identical re-runs)
# =============================================================================
# openpyxl stamps the save time into docProps/core.xml and into every zip
# entry header. Both are replaced here with values derived from the data:
# the core created/modified dates become the data vintage (midnight UTC) and
# every zip entry gets the fixed 1980-01-01 DOS epoch. Entry order, content
# and compression are left exactly as openpyxl wrote them.
#
# Supported stack for byte-identical output: the requirements.txt pins and
# openpyxl's standard-library XML writer (pinned at the top of this file).
# Deflate output also depends on the zlib build Python links against; a
# different zlib (for example zlib-ng) can change the compressed bytes
# without changing any cell, style or package part.

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_CORE_DATE = re.compile(
    r"(<dcterms:(created|modified)\b[^>]*>)[^<]*(</dcterms:\2>)")


def save_workbook_deterministic(wb, path, vintage):
    stamp = f"{vintage}T00:00:00Z"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", stamp):
        raise ValueError(f"data vintage is not an ISO date: {vintage!r}")
    import openpyxl.xml
    if openpyxl.xml.LXML:
        raise RuntimeError(
            "openpyxl was imported with its lxml XML writer before "
            "query_budget pinned the standard-library writer, so the "
            "workbook bytes would not be reproducible. Import query_budget "
            "before openpyxl, or set OPENPYXL_LXML=False.")
    buf = io.BytesIO()
    wb.save(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as src, \
         zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                text, n = _CORE_DATE.subn(
                    lambda m: f"{m.group(1)}{stamp}{m.group(3)}",
                    data.decode("utf-8"))
                if n != 2:
                    raise RuntimeError("core.xml: expected created and "
                                       f"modified dates, found {n}")
                data = text.encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=ZIP_EPOCH)
            zi.compress_type = info.compress_type
            zi.create_system = 0
            zi.external_attr = 0
            dst.writestr(zi, data)
    Path(path).write_bytes(out.getvalue())


# =============================================================================
# Build workbook
# =============================================================================

def build_workbook(sheets, run_summary=None):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    num_money = ["FY2025 Actuals ($M)",   # DBDP-66 TC-ER-07 cost_prior_year (Proc/RDT&E/BA/YoY)
                 "Prior Year ($M)",      # Summary/By Agency (neutral; not in TC-ER-07 scope)
                 "FY2026 Enacted ($M)",  # Procurement current_year; RDT&E by BA prior_year
                 "FY2027 Request ($M)", "Change ($M)",
                 "FY2026 ($M)", "FY2027 ($M)",
                 "FY2028 ($M)", "FY2028 FYDP ($M)",
                 "FY2029 ($M)", "FY2029 FYDP ($M)",
                 "FY2030 ($M)", "FY2030 FYDP ($M)",
                 "FY2031 ($M)", "FY2031 FYDP ($M)",
                 "All Prior ($M)",
                 "cost_prior_year", "cost_fy2027", "cost_fy2028",
                 "cost_fy2029", "cost_fy2030", "cost_fy2031",
                 "# Programs", "# Line Items"]
    pct_money  = ["Change (%)"]
    delta_money = ["Change ($M)"]

    LIFECYCLE = "  |  Lifecycle Stage: Budget Request"   # DBDP-66 TC-ER-10
    sheet_meta = {
        "Summary":        ("FY2027 Defense Budget -- Summary",
                           "Total funding by appropriation type  |  Dollars in Millions" + LIFECYCLE),
        "By Agency":      ("FY2027 Defense Budget -- By Agency",
                           "FY2027 request ranked by agency  |  Dollars in Millions" + LIFECYCLE),
        "Year-over-Year": ("Year-over-Year Change by Line Item",
                           "XML records with FY2025 actuals and FY2027 request  |  Sorted by absolute change" + LIFECYCLE),
        "RDT&E by BA":    ("RDT&E Budget Activity Summary (BA 1-8)",
                           "Includes FYDP profile through FY2031  |  Dollars in Millions" + LIFECYCLE),
        "Procurement":    ("Procurement (P-1) Line Items",
                           "All P-1 procurement line items with FYDP  |  Dollars in Millions" + LIFECYCLE),
        "RDT&E":          ("RDT&E (R-1) Program Elements",
                           "All R-1 program elements with FYDP  |  Dollars in Millions" + LIFECYCLE),
        # All Records: subtitle computed from len(COLUMNS) — never a literal
        # (DBDP-94 c10336 Ruling 1; TC-ER-06 is len(COLUMNS)-relative per
        # DBDP-66 c10327). Lifecycle label (TC-ER-10) carried in the title.
        "All Records":    ("Complete Data -- All Records  |  Lifecycle Stage: Budget Request",
                           f"All {len(COLUMNS)} schema columns"),
    }

    for sheet_name, df in sheets.items():
        ws = wb.create_sheet(title=sheet_name)
        title, subtitle = sheet_meta[sheet_name]
        data_start = add_title(ws, title, subtitle)
        write_df(ws, df, start_row=data_start,
                 number_cols=num_money,
                 pct_cols=pct_money,
                 delta_cols=delta_money)
        freeze_top(ws, data_start)
        autofit(ws)

        # Add auto-filter
        last_col = get_column_letter(len(df.columns))
        ws.auto_filter.ref = f"A{data_start}:{last_col}{data_start}"

    if run_summary is not None:          # DBDP-43: 8th sheet
        write_run_summary(wb, run_summary)
        if "fydp_trends" in run_summary:  # DBDP-44: 9th sheet
            write_fydp_trends(wb, run_summary["fydp_trends"],
                              run_summary["vintage"])

    return wb


# =============================================================================
# Main
# =============================================================================

def main():
    print()
    print("=" * 65)
    print("  ODBA -- FY2027 Budget Report Generator")
    print("=" * 65)
    print()

    if not PARQUET_FILE.exists():
        print(f"  [ERROR] Parquet file not found:")
        print(f"    {PARQUET_FILE}")
        print()
        print("  Run Run-ETL.ps1 first to generate the data file.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"  Source : {PARQUET_FILE.name}")
    print(f"  Output : {OUTPUT_FILE.name}")
    print()

    sheets, run_summary = run_queries(PARQUET_FILE)

    total_rows = sum(len(df) for df in sheets.values())
    n_sheets = len(sheets) + 2           # + DBDP-43 Run Summary, DBDP-44 FYDP
    print(f"  Building Excel workbook ({n_sheets} sheets, {total_rows:,} total rows)...")

    wb = build_workbook(sheets, run_summary)
    save_workbook_deterministic(wb, OUTPUT_FILE, run_summary["vintage"])

    size_kb = round(OUTPUT_FILE.stat().st_size / 1024, 1)
    print()
    print("=" * 65)
    print("  Done!")
    print(f"  Report saved: {OUTPUT_FILE}")
    print(f"  Size: {size_kb} KB  |  Sheets: {n_sheets}")
    print()
    print("  Tabs in the workbook:")
    for name, df in sheets.items():
        print(f"    {name:<23} {len(df):>5} rows")
    print(f"    {RUN_SUMMARY_SHEET:<23}  provenance and completeness checks")
    print(f"    {FYDP_SHEET:<23}  FY2025-FY2031 by appropriation type, chart")
    print("=" * 65)
    print()


if __name__ == "__main__":
    main()
