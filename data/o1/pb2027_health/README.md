# Consolidated O-1: FY2027 health-account pilot

This is an isolated, additive starter, not department-wide ingestion. Includes
all 26 amount-bearing rows from the **PB27 O-1 indexed** printed pages 49–51:
0130D Combat and Operational Medicine and 0146D Private Sector Care only.
FY25–27 columns are all from that **single submission**, not three different
editions. The initial indexed HTML table extraction, including ambiguous
layout, is preserved in source_cells.json; its acquisition metadata describes
that initial extraction. The later independent PDF check is recorded below.
Sources:

- [Consolidated PB27 Exhibit O-1](https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_o1.pdf), April 2026, pp. 49–51.
- [Official PB27 military health justification](https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/budget_justification/pdfs/09_Military_Health_System/MHS_PB27_J-Book-Vol1-COMP_PSCP.pdf), pp. 151–153, independently identifies the Private Sector Care transfer and corroborates the unreported historical cells and FY27 column placement. Use the O-1's row code, not the separate exhibit's row numbering.

## Independent PDF verification

After the indexed extraction, both original official PDFs were supplied by
the user because direct requests to the official URLs returned HTTP 403.
The uploaded binaries were checked independently; no independent download
is claimed and the binaries are not committed. Physical pages below are
one-based PDF page positions, distinct from the printed page labels.

| PDF | Printed pages | Physical PDF pages |
| --- | --- | --- |
| FY2027_o1.pdf | 49–51 | 54–56 |
| MHS_PB27_J-Book-Vol1-COMP_PSCP.pdf | 151–153 | 157–159 |

SHA-256 of each verified binary:

- FY2027_o1.pdf: `8c209bc2af590e460977649ba4e37645fd2ee8e3c8dbf61c227b7d3a27079c4d`
- MHS_PB27_J-Book-Vol1-COMP_PSCP.pdf: `d3b4dc4d3a5a5283df8e9f99afaa008f1d8789f5e48785a6a96c0e6fbf6a4be7`

The O-1 text was extracted with word coordinates and each amount was
assigned to its column using the seven published column headings. All
26 rows were compared with observations.csv in column order. Rendered
pages were also inspected to confirm the ambiguous 0146D layout and the
0130D Private Sector Care blanks. **All 182 cells matched: 123 reported
amounts and 59 blanks.** Blank cells remain blank with not_reported;
they were not converted to zeros.

The 0146D detail, activity total and account total each have four leading
monetary blanks, FY2027 discretionary request 22,175,472, a blank mandatory
request, and total 22,175,472. The companion's printed p. 153 corroborates
the FY2027 placement but uses dashes in unreported cells and line 020;
the consolidated O-1's blanks and line 010 are retained. Notes on the
companion's printed pp. 151 and 153 explicitly confirm the scoped transfer
of 0130 BAG 2 to 0146 and the enacted-to-request amounts used in the bridge.

Account 0130D line 090's title was visually checked on the O-1's printed
p. 49. The source snapshot and generated source_row_title preserve its
exact printed spelling, **R&D Exploratry Development**.

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
reported nonblank children. These arithmetic checks do not impute source
blanks; the independent PDF validation is recorded above. All 74 applicable
checks tie exactly.

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
and independently measured execution. Independent PDF checks cover only the
cited pilot pages. Before wider ingestion, validate the additional source
pages and build separate adapters for other editions and their changed columns.
