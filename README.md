# ODBA — Open Defense Budget Analytics

A local-first PPBE-native analytics platform for the DoD FY2027 President's Budget submission. Parses official DoD Comptroller budget exhibits into a unified dataset for cross-appropriation analysis.

## What It Does

- Ingests **O-1 (O&M)**, **P-1 (Procurement)**, **R-1 (RDT&E)**, **RF-1 (DWCF)**, and **DHP** budget exhibits from the DoD Comptroller
- Parses both XML (DTIC schema) and JSON (OP-5 exhibit format) source files
- Includes a custom SpreadsheetML parser for Military Health System (MHS) J-Book files
- Outputs a unified **Parquet** dataset via DuckDB for SQL-compatible querying
- Generates a multi-tab **Excel report** with cross-appropriation summaries

## Data Sources

All source data is the FY2027 President's Budget (PB27), published by the [DoD Comptroller](https://comptroller.defense.gov/Budget-Materials/). Source files are not included in this repo — use the download scripts to fetch them.

| Folder | Exhibit | Format |
|---|---|---|
| `01_Operation_and_Maintenance/` | O-1 / OP-5 | JSON |
| `02_Procurement/` | P-1 | XML |
| `03_RDT_and_E/` | R-1 / R-2 | XML |
| `06_Defense_Working_Capital_Fund/` | RF-1 | JSON |
| `09_Defense_Health_Program/` | DHP J-Book | JSON |
| `09_Military_Health_System/` | MHS J-Book | XML (SpreadsheetML) |

## Project Structure

```
ODBA/
├── etl_budget.py          # ETL: parses all source files → Parquet
├── query_budget.py        # Report generator: Parquet → Excel
├── Download-FY2027-JSON.ps1  # Downloads O&M, DWCF, DHP JSON files
├── Download-XML.ps1          # Downloads P-1 and R-1 XML files
├── Download-Missing.ps1      # Fills gaps in partial downloads
├── Run-ETL.ps1               # Launcher for etl_budget.py
├── Run-Query.ps1             # Launcher for query_budget.py
├── output/                # Generated (gitignored): .parquet, .xlsx
└── README.md
```

## Setup

**Requirements:** Python 3.10+, PowerShell 5+

```bash
pip install pandas pyarrow duckdb openpyxl
```

## Usage

```powershell
# 1. Download source data (first time only)
.\Download-FY2027-JSON.ps1
.\Download-XML.ps1

# 2. Run ETL to build the Parquet dataset
.\Run-ETL.ps1

# 3. Generate the Excel report
.\Run-Query.ps1
```

Output: `output/fact_budget_line_items.parquet` and `output/ODBA_FY2027_Budget_Report.xlsx`

## Dataset (FY2027 PB)

| Exhibit | Records | FY2027 Total |
|---|---|---|
| O-1 (O&M) | 270 | $38.0B |
| R-1 (RDT&E) | 255 | $34.9B |
| P-1 (Procurement) | 62 | $7.2B |
| DHP | 45 | $2.1B |
| RF-1 (DWCF) | 3 | — |
| **Total** | **635** | |

All figures are Defense-Wide agencies only (SOCOM, DISA, OSW, CYBERCOM, DARPA, etc.) — does not include Army, Navy, or Air Force appropriations.

## License

MIT
