ODBA historical baseline: budget authority by military department

Import historical_qa_passed.csv first. Use either Current (nominal)
or Constant FY2025 (inflation-adjusted) dollar basis, never both in a sum.
Use row_grain=Component for department comparisons. Use Published total
for the official DoD-wide series; never add it to component rows.

Source: National Defense Budget Estimates for FY2025, Table 6-10, printed
pages 154–161 (PDF pages 161–168). The indexed text snapshot has been
checked against all 820 amounts in the user-provided FY2025 PDF.
https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/fy25_Green_Book.pdf

budget_authority.csv contains all 820 source observations for FY1948–2029.
reconciliation.csv tests sums against the same table's published total.
All 164 year-and-dollar-basis pairs reconcile within $2 million.
historical_qa_passed.csv contains 760 rows: all five rows for each of the
76 historical years (FY1948–2023) in both dollar bases. Component rows
and published totals remain separate; do not add them together.

## Source verification and corrections

The PDF was supplied by the user after a request to the official URL
returned HTTP 403. Its SHA-256 is
`c0796fd7ed2de188b2721ec94b1e349fb1df36848afd32cc32f9aa9f6c809250`.
The binary is not committed. Its filename, hash, page mapping, full
820-value comparison, and correction history are recorded in
table_6_10_indexed.json. This records verification against the uploaded
binary; no independently downloaded PDF is claimed.

Three transcription errors in the original indexed snapshot were
corrected to match the PDF (all Current dollars, USD millions):

| Printed page | Entry | Original indexed value | PDF-verified value |
| --- | --- | ---: | ---: |
| 159 | FY2003 DoD total | 437,301 | 437,801 |
| 159 | FY2011 Defense-Wide | 115,407 | 110,407 |
| 161 | FY2029 Navy | 282,474 | 282,471 |

These were snapshot transcription errors, not published-source anomalies.
The corrected component-minus-total differences are 0, -1, and +1 million,
respectively. No nominal year/basis pairs are excluded; the historical
export now includes FY2003 and FY2011 Current-dollar rows.

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
individual component. historical_qa_passed.csv omits flagged basis/year
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
