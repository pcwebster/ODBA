# ODBA — Open Defense Budget Analytics

A local-first, PPBE-native analytics platform for U.S. Department of Defense budget data. ODBA parses official DoD Comptroller budget justification exhibits into a single, queryable, source-traceable dataset for cross-appropriation analysis.

> **Lifecycle stage — canonical FY2027 report.** The FY2027 PB27 report slice of the canonical exhibit dataset (`output/fact_budget_line_items.parquet`), shown in its Excel report, represents the **President's Budget Request** — the *Budget Request* stage of the PPBE data lifecycle:
>
> **Budget Request → Enacted → Reprogrammed → Obligated → Outlayed**
>
> This report slice contains no enacted appropriations, reprogramming actions, or execution (obligation/outlay) data. Read its FY2027 dollar figures as **Budget Request** stage unless explicitly labeled otherwise. Other fiscal-year columns and submission vintages in the Parquet retain their own reporting bases.
>
> **Separate consolidated O-1 exhibits:** the PB25–PB27 sidecars and Budget Explorer's O-1 view preserve as-published columns, including requests, enacted amounts, supplemental funding, spend plans, published totals, and actuals as reported. These TOA observations retain their own budget edition, funding fiscal year, and column basis; the canonical dataset's request-only warning does not apply to them.

## What ODBA Is

ODBA converts public DoD budget exhibits — R-forms, P-forms, O&M exhibits, and related justification books — into a structured, unified **Parquet** dataset that can be queried with SQL (via DuckDB) and summarized in a pre-built Excel report. It is **exhibit-level** and **source-grounded**: every record traces back to its source file, exhibit type, fiscal year, and PPBE lifecycle stage.

This repository is the reproducible ingestion-and-reporting pipeline behind ODBA: it downloads the public Comptroller source files, parses them, normalizes them into one analytical table, and generates an analyst-friendly Excel workbook.

For project scope, architecture, and governance, see the **[ODBA Project Charter](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/25264136/Project+Charter)** (Confluence). Related onboarding pages:

- [Scope and MVP Definition](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/25362433/Scope+and+MVP+Definition)
- [Data Sources Inventory](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/26804225/Data+Sources+Inventory)
- [Data Dictionary — `fact_budget_line_items`](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/54886402/Data+Dictionary+fact_budget_line_items)

## What's in This Repository

| File | Purpose |
|---|---|
| `etl_budget.py` | ETL parser — reads all XML/JSON source files and writes the unified Parquet dataset |
| `query_budget.py` | Report generator — reads the Parquet dataset via DuckDB and produces the Excel workbook |
| `Download-FY2027-JSON.ps1` | Downloads the FY2027 JSON source files (O&M, DWCF, DHP) |
| `Download-XML.ps1` | Downloads the FY2027 XML source files (Procurement, RDT&E, MHS) |
| `Download-Missing.ps1` | Re-fetches any source files missing from a partial download |
| `Run-ETL.ps1` | No-code launcher for `etl_budget.py` |
| `Run-Query.ps1` | No-code launcher for `query_budget.py` |
| `output/` | Generated artifacts (gitignored): the Parquet dataset and Excel report |

## Prerequisites

- **64-bit CPython 3.10+** (wheel availability is platform-dependent)
- **PowerShell 5+** (for the download scripts and launchers)

Install the Python dependencies:

```bash
python -m pip install --require-hashes --only-binary=:all: -r requirements.txt
```

## Data Sources

The canonical pipeline's FY2027 sources are the **FY2027 President's Budget (PB27)** submission — **Budget Request** lifecycle stage — published by the DoD Comptroller. The public budget-materials index is at <https://comptroller.defense.gov/Budget-Materials/> (FY2027 Budget Justification); the download scripts fetch the individual files directly from the Comptroller portal via anonymous HTTPS (no account or API key required). The separate O-1 sidecars cover PB25, PB26, and PB27 with the reporting bases described above and in their source READMEs.

Raw XML/JSON source files for the canonical pipeline are **not** committed to this repository — run the download scripts to fetch them.

| Folder | Exhibit(s) | Format |
|---|---|---|
| `01_Operation_and_Maintenance/` | O-1 / OP-5 | JSON |
| `02_Procurement/` | P-1 (line item) | XML (DTIC schema) |
| `03_RDT_and_E/` | R-1 / R-2 (program element) | XML (DTIC schema) |
| `06_Defense_Working_Capital_Fund/` | RF-1 | JSON |
| `09_Defense_Health_Program/` | DHP J-Book (O-1, OP-5, P-1, P-40, R-1 sections) | JSON |
| `09_Military_Health_System/` | MHS J-Book (Vol 1 COMP/PSCP, Vol 2 SMR) | XML (SpreadsheetML) |

**Canonical dataset coverage:** the canonical exhibit dataset is **Defense-Wide agencies only** (e.g., SOCOM, DISA, OSW, CYBERCOM, DARPA, MDA). It does **not** include Army, Navy, Air Force, Space Force, or Marine Corps appropriations, and should not be presented as the full FY2027 DoD budget. This coverage limit describes the canonical dataset, not the separate consolidated O-1 sidecars.

## Directory Structure

```
ODBA/
├── etl_budget.py             # ETL: parses all source files → Parquet
├── query_budget.py           # Report generator: Parquet → Excel
├── Download-FY2027-JSON.ps1  # Downloads O&M, DWCF, DHP JSON files
├── Download-XML.ps1          # Downloads Procurement, RDT&E, MHS XML files
├── Download-Missing.ps1      # Fills gaps in partial downloads
├── Run-ETL.ps1               # Launcher for etl_budget.py
├── Run-Query.ps1             # Launcher for query_budget.py
├── 01_Operation_and_Maintenance/   # JSON source files (created by download script)
├── 02_Procurement/                 # XML source files
├── 03_RDT_and_E/                   # XML source files
├── 06_Defense_Working_Capital_Fund/# JSON source files
├── 09_Defense_Health_Program/      # JSON source files
├── 09_Military_Health_System/      # XML (SpreadsheetML) source files
├── output/                   # Generated (gitignored): .parquet, .xlsx
└── README.md
```

The download scripts create the numbered source folders and place each file in the location the ETL expects. Run the download scripts before the ETL.

## Usage

```powershell
# 1. Download source data (first time only)
.\Download-FY2027-JSON.ps1
.\Download-XML.ps1

# 2. Run the ETL to build the unified Parquet dataset
.\Run-ETL.ps1

# 3. Generate the Excel report
.\Run-Query.ps1
```

## Outputs

Both are written to `output/`:

- **`fact_budget_line_items.parquet`** — the unified, line-item-level budget dataset (the canonical ODBA table). See the [Data Dictionary](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/54886402/Data+Dictionary+fact_budget_line_items) for every field, its type, source exhibit, and population status.
- **`ODBA_FY2027_Budget_Report.xlsx`** — a multi-tab Excel workbook with cross-appropriation analytical views generated from the Parquet dataset.

## Canonical Dataset Summary (FY2027 PB — Budget Request stage)

The figures below describe only the canonical dataset's **FY2027 President's Budget = Budget Request** slice, Defense-Wide agencies only.

| Exhibit | Records | FY2027 total (Budget Request) |
|---|---|---|
| O-1 (O&M) | 270 | $38.0B |
| R-1 (RDT&E) | 255 | $34.9B |
| P-1 (Procurement) | 62 | $7.2B |
| DHP | 45 | $2.1B |
| RF-1 (DWCF) | 3 | — (totals pending validation) |
| **Total** | **635** | |

## Consolidated PB27 O-1 detail sidecar (DBDP-90)

The [O-1 detail sidecar](data/o1/pb2027_candidate/README.md) independently
imports all 397 printed detail rows across the O&M title and indefinite
accounts. The original official PDF was checked across printed pp. 1–56
(physical PDF pages 6–61): no omitted or extra rows, and all 2,779 monetary
cells match (1,866 reported amounts and 913 blanks). PDF SHA-256:
`8c209bc2af590e460977649ba4e37645fd2ee8e3c8dbf61c227b7d3a27079c4d`.

The sidecar retains separate FY26 discretionary enacted and reconciliation
spend-plan columns, signed amounts, both Air Force line 999 records, two
PDF-only FY25 rows, and separate workbook-only FY25 lanes. It includes the
health details once; do not union it with the earlier health pilot. Its
42 selected headline controls are non-additive, and coverage of other
printed summaries and remaining source limitations is documented in its
README. This table is separate from the existing ETL and canonical dataset
summarized above; neither is changed by this import. RF-1 and reimbursements
are excluded from this O-1 sidecar.

## Consolidated PB26 O-1 detail sidecar (DBDP-90)

The [PB26 O-1 detail sidecar](data/o1/pb2026_candidate/README.md) contains
all 407 printed detail rows. Original printed pp. 1–55 (physical PDF pages
6–60) were independently checked in both directions: no omitted or extra
rows, and all 2,849 monetary cells match (1,856 reported amounts and 993
blanks, including five negative amounts). PDF SHA-256:
`41c4970437c11fefc325bb1fa9d4ab5799ccecf14b78d3a00794bcf1d9a53b65`.

The hash-pinned reference preserves the blank 5286A line ID and separate
printed/workbook labels. Six confirmed p. 55 FY25 triplets retain their
published totals instead of adding repeated enacted and supplemental
figures. PB26's FY26 reconciliation request remains distinct from PB27's
FY26 spend plan. The sidecar README records the exact exceptions, selected
non-additive control coverage, and remaining workbook-metadata limitations.
This separate PB26 import does not alter existing ingestion or include
RF-1, reimbursements, or execution data.

## Consolidated PB25 O-1 detail sidecar (DBDP-90)

The [PB25 O-1 detail sidecar](data/o1/pb2025_candidate/README.md) contains
all 434 printed detail rows. Original printed pp. 1–67 (physical PDF pages
5–71) were checked in both directions with no omissions or extras. All
1,302 monetary cells match: 1,102 reported amounts and 200 blanks,
including 15 negatives. PDF SHA-256:
`f4934028d923998791f672ee9f11e2094a3537ba89e406f9c42a324e2cf12111`.

FY23 actuals, FY24 request with continuing-resolution adjustments, and
FY25 request remain separate. Both activity-specific 3400F/999 records
and the distinct 5751D/0134D accounts sharing a BLI are preserved. A
hash-pinned PDF reference and separate printed/workbook labels retain
the original evidence; the sidecar README records title variants,
corrections and source limitations. Overseas-operations-cost subsets,
RF-1 and repeated summaries are not added to detail totals. Existing
ingestion and the canonical dataset remain unchanged.

## Offline Budget Explorer

The [Budget Explorer](apps/budget_explorer/README.md) is a standalone,
offline HTML preview for the consolidated PB25–PB27 O-1 imports, Green
Book department history, and sampled exhibit requests. Download or open
[index.html](apps/budget_explorer/index.html) locally; no login or internet
is required for the interface. Official PDF links require connectivity.

The preview keeps budget editions, fiscal years, stages and funding bases
separate. Its read-only O-1 payload contains 1,238 detail rows and 125
selected controls pinned to commit `b9ea2eb`, with 6,930 published
amount/blank cells checked against the stored PDF references. See the app
README for exact rebuild commands, test results and browser-verification
limits. Existing ingestion and data artifacts are unchanged. This addition
does not publish a hosted site.

## Dependency lock maintenance (DBDP-70/71)

Both launchers require `requirements.txt` and stop before running ETL/reporting
if the file is missing or pip fails. There is no unpinned fallback. Install into
a fresh virtual environment for package-integrity verification; pip does not
re-hash packages already installed in an existing environment.

`requirements.in` holds the five runtime pins and NumPy/python-dateutil compatibility
constraints. NumPy uses separate pins before/after Python 3.14 to retain Python
3.10 support without losing 3.14 wheels. `requirements.txt` locks their complete runtime
dependency closure, with SHA-256 hashes from official PyPI. Windows and Linux
wheels are allowed; source builds are deliberately disabled to avoid fetching
unlocked build dependencies. An unsupported interpreter/platform fails closed.

To refresh the lock in a separate maintainer environment with uv 0.13.9 installed (not a runtime dependency):

```sh
uv pip compile --universal --python-version 3.10 --default-index https://pypi.org/simple --generate-hashes --output-file requirements.txt requirements.in
```

Use universal resolution so inactive Python markers are retained; a native-only
lock can silently lose another interpreter's NumPy pin.

Review every version/hash change, verify a clean hash-checked install and
`python -m pip check`, run `pip-audit -r requirements.txt` and the test suite,
and check Windows/Linux wheel resolution before committing the lock. Do not
regenerate budget artifacts as part of dependency maintenance. Hashes protect
the reviewed distributions against substitution, not vulnerabilities or a
compromise that predates lock generation.

## License

MIT

