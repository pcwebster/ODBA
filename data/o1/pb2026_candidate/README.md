# PB26 consolidated O-1 detail import

This isolated sidecar contains all 407 consolidated PB26 O-1 detail rows:
400 O&M-title and seven indefinite-account rows across 30 raw accounts.
The original PDF has now been independently checked in both directions;
the historical pb2026_candidate path is retained. No existing PB27,
health-pilot, dashboard or ETL ingestion is changed. All seven columns
are TOA in USD thousands from this single PB26 submission, not independently
measured obligations or outlays.

## Source and independent original-PDF verification

The initial candidate was extracted from one pinned third-party mirror
workbook and selected indexed official controls. The exact workbook URL,
SHA-256 and combined sheet are in provenance.json; overlapping tabs are
not imported again. Publisher-workbook byte equivalence remains unverified.
The later independent PDF check described here is separate from that initial
mirror/indexed extraction.

- Official source: <https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2026/FY2026_o1.pdf>
- Verified binary: FY2026_o1.pdf, uploaded by the user after direct official
  downloads returned HTTP 403. The original binary is not committed and no
  independent download is claimed.
- PDF SHA-256: `41c4970437c11fefc325bb1fa9d4ab5799ccecf14b78d3a00794bcf1d9a53b65`
- Scope: printed O-1 **pp. 1–55**, physical PDF **pages 6–60**, one-based.
  The supplied binary also contains later material; reimbursements and RF-1
  pages are outside the scanned/imported scope.

The PDF was independently extracted by word coordinates, using all seven
published column headings. Each account/line, printed activity/subactivity,
classification, wrapped title and signed/nullable cell was identified from
the PDF rather than filled from workbook values. A separate plain-text
inventory checked detail occurrences; rendered pages confirmed the blank
5286A line ID, all negative signs, and the six repeated FY25 triplets.
Every PDF detail must match exactly one candidate detail, and every candidate
detail must match one PDF detail: totals alone are not the coverage test.

**Result: all 407 rows / 30 accounts match, with no omitted or extra rows.
All 2,849 monetary cells match: 1,856 reported amounts and 993 blanks,
including five negative amounts.** No literal numeric zero is printed;
a synthetic regression separately protects the distinction between zero
and blank. Printed classification/activity/subactivity match wherever those
fields are actually printed. There are no unresolved identity or monetary
mismatches.

`pdf_detail_reference.json` stores the independent extraction, PDF hash,
page scope, printed identities, exact titles and seven nullable values.
Its own SHA-256 is pinned in provenance.json. The builder and default tests
enforce both-direction identity and cell equality against this stored
reference. They do not claim to download or re-extract a missing binary.

## Printed identities and separate labels

The 5286A detail on printed p. 55 has a genuinely blank printed line ID,
FY24 actuals 24 thousand, and title **National Science Center, Army**.
line_raw stays blank; no synthetic line ID is invented. The pinned workbook
locator OM Title plus Indefinite!108 supplies source location separately
from the blank identity. Eight blank workbook organization fields also
remain blank. Both activity-specific 3400F line 999 details remain distinct.

On printed pp. 54–55, 25 rows do not print activity/subactivity codes.
Those reference fields remain null; matching uses each unique account/line
pair, including the empty 5286A line. Workbook raw codes remain available
without claiming the PDF independently verifies unprinted metadata.

There are **19 printed-title/workbook-label differences**. Original
line_title_workbook values are retained unchanged. The builder adds
line_title_printed and pdf_printed_page from the verified PDF reference
for every row. The initial limited official_indexed_line_title and
its page field are also preserved separately and checked where populated.
For example, the seven 0833D program labels remain in workbook fields,
while the printed title is **Emergency Response Fund, Defense**. The five
0105D rows similarly retain their individual workbook labels and the PDF's
common account-level title. The full list of pairs is in provenance.json.
These are explicitly represented source variants, not unresolved label
conflicts or silent replacements.

## Seven monetary lanes and six exact FY25 exceptions

The columns remain separate:

1. FY24 reported actuals.
2. FY25 enacted.
3. FY25 supplemental.
4. FY25 published total.
5. FY26 discretionary request.
6. FY26 reconciliation request.
7. FY26 published total.

The PB26 FY26 reconciliation **request** is not the PB27 FY26 PL 119-21
**spend plan** or budget execution. Do not merge editions or combine these
reporting bases. Blanks stay unreported; they are never converted to zero.

Rendered original PDF p. 55 confirms the six exact indefinite-account
triplets below. Each figure is physically printed in **all three FY25
columns: enacted, supplemental and published total**, in USD thousands:

| Account | Printed line | Enacted = supplemental = published total |
| --- | --- | ---: |
| 5188D | 190 | 3,262 |
| 5188D | 210 | 540 |
| 5188D | 230 | 3,318 |
| 5189D | 260 | 16,434 |
| 5189D | 280 | 7,539 |
| 5189D | 300 | 10,207 |

This is a confirmed published-source arithmetic exception, not a duplicated
indexed column. Preserve each **printed total** rather than summing its
enacted and supplemental entries. Their component-sum excess is 41,300
thousand in indefinite and combined scopes; the title-only scope ties
additively. The builder permits only these six exact account/line/amount
triplets, requires all six once, and rejects any new or altered exception.
Every other FY25 detail and every FY26 request detail still must tie.
fy25_nonadditive_triplets.csv records the exceptions as audit rows, not
additional facts.

## Non-additive controls and remaining limits

headline_controls.csv retains 56 selected printed control cells, all
independently matched to the PDF: 47 reported amounts and nine blanks.
These are not extra detail facts or additive datasets:

| Retained controls | Printed page | Cells |
| --- | --- | ---: |
| Army, Navy, Air Force account rollups | 1 | 21 |
| O&M title, indefinite and combined totals | 3 | 21 |
| Transfer Accounts total | 54 | 7 |
| Miscellaneous Accounts total | 55 | 7 |

Other summaries are outside this control file: Defense-Wide p. 2;
individual appropriation/account summaries; 43 distinct account/activity
subtotal scopes appearing 73 times; and lower activity-group subtotals.
Repeated summary appearances are duplicate evidence, not additional
amounts. No subtotal or rollup is appended to additive detail facts.

No candidate amounts, signs, blanks, identifiers or original workbook
labels required correction. The import adds persistent PDF evidence and
complete printed-title/page columns, replacing stale unverified-PDF claims.
Workbook metadata absent from the PDF retains its stated source limitation.
PB25, other source editions, RF-1, WCF and execution datasets remain outside
this sidecar.

## Exact regeneration and tests

Obtain the exact mirror workbook from provenance.json; the builder verifies
its SHA-256 before reading it. Python 3.10+ and openpyxl (tested 3.1.5)
are needed for workbook regeneration; no dependency declaration is changed.
Run from the repository root:

```bash
python tools/build_o1_pb2026_candidate.py --workbook PATH/peer-pb26.xlsx --out-dir data/o1/pb2026_candidate
python tools/build_o1_pb2026_candidate.py --workbook PATH/peer-pb26.xlsx --check data/o1/pb2026_candidate
ODBA_PB26_O1_WORKBOOK=PATH/peer-pb26.xlsx python -m unittest discover -s tests -p test_o1_pb2026_candidate.py -v
ODBA_PB27_O1_WORKBOOK=PATH/peer-pb27.xlsx python -m unittest discover -s tests -p test_o1_pb2027_candidate.py -v
python -m unittest discover -s tests -p test_o1_pb2027_health.py -v
python -m unittest discover -s tests -p test_green_book_fy2025.py -v
```

Supply the pinned workbooks to execute the real-file regeneration tests;
skipped regeneration is not evidence of byte-identical outputs. Default
PB26 tests still check every PDF-reference row/cell, recompute all 56
controls from facts, and reject missing/extra rows, invented blank line IDs,
lost negative signs, blank-to-zero changes, swapped FY26 lanes, altered
published totals, and modified reference bytes.
