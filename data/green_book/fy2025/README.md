ODBA historical baseline: budget authority by military department

Import Historical_QA_Passed.csv first. Use either Current (nominal)
or Constant FY2025 (inflation-adjusted) dollar basis, never both in a sum.
Use row_grain=Component for department comparisons. Use Published total
for the official DoD-wide series; never add it to component rows.

Source: National Defense Budget Estimates for FY2025, Table 6-10, printed
pages 154–161. Extracted from the official PDF's indexed text.
https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/fy25_Green_Book.pdf

Budget_Authority.csv contains all 820 source observations for FY1948–2029.
Reconciliation.csv tests sums against the same table's published total.
161 of 164 pairs reconcile within $2 million. Source values were retained.
Three nominal pairs are excluded from the QA-passed view. FY2003: Table
6-10 indexed total is $437,301M, but the component sum and Tables 6-8/6-9
are $437,801M. FY2011: the $690,781M total agrees with Tables 6-8/6-9,
but Table 6-10's indexed component sum is $695,780M. FY2029: total
$956,115M also appears in other tables; component sum is $956,119M.
These findings are cross-checks, not corrections.

Data dictionary:
source_vintage_fy identifies the President's Budget edition; funding_fy
is the fiscal year of the amount. source_year_status is Historical
(FY1948–23), Continuing resolution (FY2024), President's Budget (FY2025),
or Outyear estimate (FY2026–29) as represented in this edition.
military_department is Army, Navy, Air Force, Defense-Wide, or DoD total.
row_grain distinguishes a component from the published total.
dollar_basis and unit specify the price basis and USD millions.
budget_authority is not obligations or outlays. funding_scope includes
discretionary and mandatory; the source includes war and supplemental
funding. source_table, source_printed_page and source_url identify the
source. reconciliation_status flags the entire year and basis, not an
individual component. Historical_QA_Passed omits flagged basis/year
pairs and all nonhistorical years. It is an aggregate view, not exhibit
or program-level data.

## Repository integration

This is a standalone aggregate sidecar; it is not an input to the existing
exhibit ETL, CSV star export, or dashboard. The checked-in indexed extract
is a provenance snapshot of selected source rows, not the official PDF binary.
Build and validate from the repo root with Python 3:

    python tools/build_green_book_fy2025.py --out-dir data/green_book/fy2025
    python tools/build_green_book_fy2025.py --check data/green_book/fy2025
    python -m unittest discover -s tests -p test_green_book_fy2025.py

Byte-identical regeneration proves the transformation is repeatable; it
does not independently verify the source text against the original PDF.
