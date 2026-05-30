# ODBA — Open Defense Budget Analytics

A local-first, PPBE-native analytics platform for U.S. Department of Defense budget data. ODBA parses official DoD Comptroller budget justification exhibits into a single, queryable, source-traceable dataset for cross-appropriation analysis.

> **Lifecycle stage — read this first.** All FY2027 data in this repository represents the **President's Budget Request** — the *Budget Request* stage of the PPBE data lifecycle:
>
> **Budget Request → Enacted → Reprogrammed → Obligated → Outlayed**
>
> No enacted appropriations, reprogramming actions, or execution (obligation/outlay) data are included. Every dollar figure produced by ODBA should be read as **Budget Request** stage unless it is explicitly labeled otherwise.

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

- **Python 3.10+**
- **PowerShell 5+** (for the download scripts and launchers)

Install the Python dependencies:

```bash
pip install pandas pyarrow duckdb openpyxl
```

## Data Sources

All source data is the **FY2027 President's Budget (PB27)** submission — **Budget Request** lifecycle stage — published by the DoD Comptroller. The public budget-materials index is at <https://comptroller.defense.gov/Budget-Materials/> (FY2027 Budget Justification); the download scripts fetch the individual files directly from the Comptroller portal via anonymous HTTPS (no account or API key required).

Source files are **not** committed to this repository — run the download scripts to fetch them.

| Folder | Exhibit(s) | Format |
|---|---|---|
| `01_Operation_and_Maintenance/` | O-1 / OP-5 | JSON |
| `02_Procurement/` | P-1 (line item) | XML (DTIC schema) |
| `03_RDT_and_E/` | R-1 / R-2 (program element) | XML (DTIC schema) |
| `06_Defense_Working_Capital_Fund/` | RF-1 | JSON |
| `09_Defense_Health_Program/` | DHP J-Book (O-1, OP-5, P-1, P-40, R-1 sections) | JSON |
| `09_Military_Health_System/` | MHS J-Book (Vol 1 COMP/PSCP, Vol 2 SMR) | XML (SpreadsheetML) |

**Coverage caveat:** the current dataset is **Defense-Wide agencies only** (e.g., SOCOM, DISA, OSW, CYBERCOM, DARPA, MDA). It does **not** include Army, Navy, Air Force, Space Force, or Marine Corps appropriations, and should not be presented as the full FY2027 DoD budget.

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

## Dataset Summary (FY2027 PB — Budget Request stage)

All figures below are **FY2027 President's Budget = Budget Request** stage, Defense-Wide agencies only.

| Exhibit | Records | FY2027 total (Budget Request) |
|---|---|---|
| O-1 (O&M) | 270 | $38.0B |
| R-1 (RDT&E) | 255 | $34.9B |
| P-1 (Procurement) | 62 | $7.2B |
| DHP | 45 | $2.1B |
| RF-1 (DWCF) | 3 | — (totals pending validation) |
| **Total** | **635** | |

## License

MIT

