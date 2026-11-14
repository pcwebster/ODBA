# Consolidated O-1: FY2027 health-account pilot

This is an isolated, additive starter, not department-wide ingestion. Includes
all 26 amount-bearing rows from the **PB27 O-1 indexed** printed pages 49–51:
0130D Combat and Operational Medicine and 0146D Private Sector Care only.
FY25–27 columns are all from that **single submission**, not three different
editions. Original PDF binary/page render is not independently verified.
The indexed table cells, including ambiguous HTML layout, are preserved in
source_cells.json. Sources:

- [Consolidated PB27 Exhibit O-1](https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_o1.pdf), April 2026, pp. 49–51.
- [Official PB27 military health justification](https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/budget_justification/pdfs/09_Military_Health_System/MHS_PB27_J-Book-Vol1-COMP_PSCP.pdf), pp. 151–153, independently identifies the Private Sector Care transfer and confirms its blank historical cells and FY27 column placement. Use the O-1's row code, not the separate exhibit's row numbering.

observations.csv has 182 rows (26 exhibit rows × 7 published columns).
Use submission_fy + funding_fy + source_column_key to preserve each reporting
basis. Measure is TOA in USD thousands, not obligations or outlays. Actuals
are those reported in the exhibit; FY2026 enacted is only the published
discretionary enacted column, and the FY2026 PL 119-21 spend-plan amount is
separate. FY2027 discretionary/mandatory requests are also separate. A
future PB26 ingestion must retain its distinct reconciliation **request**,
never equate it to the PB27 spend plan. Published total columns are not
additive to their underlying funding columns. Never combine detail,
activity_total and account_total records in one sum. Blank amount plus
not_reported is not zero. A source_alignment marker records the companion
justification used to restore the omitted indexed blank cells in 0146D.
reconciliation.csv contains checks comparing reported totals with sums of
reported nonblank children. This does not impute source blanks or guarantee
independent PDF accuracy. All 74 applicable checks tie exactly.

private_sector_care_bridge.csv is deliberately limited to PB27 and one
activity/line per account. The official justification identifies the
transfer of operation and maintenance BAG 2 from 0130 to 0146. Compare
FY2026 discretionary enacted $20,773,888 thousand from 0130D to FY2027
discretionary request $22,175,472 thousand from 0146D: +$1,401,584 thousand
(+6.7% rounded). Label this enacted-to-request, not same-stage YoY, and
do not join or merge the entire accounts. The FY2027 0130D Private Sector
Care blank remains blank.

Regenerate and check from repository root (Python standard library only):
    python tools/build_o1_pb2027_health.py --out-dir data/o1/pb2027_health
    python tools/build_o1_pb2027_health.py --check data/o1/pb2027_health
    python -m unittest discover -s tests -p test_o1_pb2027_health.py -v

This scope excludes other accounts, original PB25 and PB26 submissions,
source PDFs beyond the indexed excerpt, and independently measured execution.
Before wider ingestion, compare this pilot against the original official PDF
layout and build separate adapters for other editions and their changed columns.
