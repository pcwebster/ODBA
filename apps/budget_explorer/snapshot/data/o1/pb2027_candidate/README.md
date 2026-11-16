# PB27 consolidated O-1 detail import

This isolated sidecar covers all 397 printed detail rows for the O&M title
and indefinite accounts in the FY2027 President's Budget consolidated O-1.
All seven printed monetary columns, signed amounts, blanks, printed titles
and printed row identities were independently checked against the original
PDF. Money is Total Obligational Authority in USD thousands. The historical
`pb2027_candidate` path is retained; the verification results below replace
its preliminary candidate status. The existing ETL is unchanged.

This is one PB27 submission, not separate PB25/PB26 editions. It excludes
RF-1, revolving-fund orders/revenue, reimbursements, and independently
measured obligations/outlays. Do not union the earlier health pilot with
these detail facts: its same 20 detail rows are already represented once.
The pilot remains an independent cross-check; its scoped 0130D/0146D
Private Sector Care bridge is not a whole-account merge.

## Sources and independent PDF check

The initial extraction uses the pinned third-party mirror workbook in
provenance.json, specifically its combined sheet's 395 physical detail rows.
Other workbook sheets repeat observations. Publisher-workbook byte equivalence
has not been established, but the mirror bytes are pinned and every printed
monetary value has separately been verified against the original official PDF.

- Official PDF: <https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_o1.pdf>
- Verified binary: FY2027_o1.pdf, supplied by the user after direct official
  downloads returned HTTP 403; the binary is not committed.
- PDF SHA-256: `8c209bc2af590e460977649ba4e37645fd2ee8e3c8dbf61c227b7d3a27079c4d`
- Full comparison scope: printed **pp. 1–56**, physical PDF **pages 6–61**
  (one-based). Pages 1–3 are summaries, not additive detail rows. RF-1 and
  reimbursement pages are outside this scope.

The independent extraction used PDF word coordinates and all seven printed
column headings to assign nullable, signed amount cells. Account, line,
printed activity/subactivity, classification, and wrapped titles were parsed
from the PDF separately from the workbook. A second plain-text inventory
checked all account/line occurrences without filtering by classification.
Both directions were compared: every PDF detail must have one matching
candidate detail, and every candidate detail must have one PDF detail.
Rendered pages confirmed both Air Force line 999 records, the two PDF-only
FY25 rows, the negative amount, and the health-account column alignment.

**Result: 397 rows / 31 accounts, no omitted or extra rows; all 2,779 printed
cells match — 1,866 reported amounts and 913 blanks.** All printed titles,
subactivities and classifications also match. There are no unresolved
printed-detail mismatches. No literal numeric zero occurs in these printed
cells; regressions separately establish that reported zero remains distinct
from blank.

`pdf_detail_reference.json` preserves that independent PDF extraction, its
binary hash, page scope, each detail's printed/physical page, printed
identity, title and seven nullable signed values. Its own SHA-256 is pinned
in provenance.json. Every build and the default tests enforce exact
both-direction coverage and cell equality against this reference, not just
aggregate totals. The raw workbook source sheet/physical row remains in
source_locator, separate from identity.

### Identity and reporting bases

The stable workbook grain includes account, activity and line. Both 3400F
line 999 records are retained: BA 01 on printed p. 33 and BA 04 on p. 36.
Seven workbook organization fields remain blank; 29 raw workbook accounts
are preserved, with two additional PDF-only accounts below.

On printed pp. 55–56, 18 detail rows do not print activity/subactivity
codes. Their PDF reference fields remain null. Unique account/line pairs
bind those rows; workbook raw activity/subactivity metadata is retained
without claiming it was printed or independently verified by the PDF.

Two details missing from the mirror workbook were already supplied in the
candidate from the official PDF, and have now been checked in the binary:

- Printed p. 55: 0833D / 110, Emergency Response Fund, Defense, FY25 actuals
  **9** thousand. The account title is on printed p. 3.
- Printed p. 56: 5286A / 120, National Science Center, Army, FY25 actuals
  **12** thousand. The account title is on printed p. 3.

These populate only the printed FY25 lane; all three native workbook FY25
lanes stay blank. They are direct source rows, not amounts inferred from
residuals. Printed p. 56 also confirms 5188D / 140 at **-24** thousand in
FY25, with its later blank cells preserved.

The three FY25 workbook lanes (Actuals, Reconciliation, Total) remain
separate raw workbook fields. For workbook-sourced rows, the workbook FY25
Total matches the PDF's single printed FY25 Actuals column, now checked at
every line. These are not three additive printed lanes; the PDF does not
independently expose all three native workbook components. Never sum them
with fy25_printed_actuals_lane.

FY2026 PL 119-21 Spend Plan remains separate from discretionary enacted.
It is neither actual obligations nor the earlier PB26 reconciliation
request. FY2027 discretionary and mandatory requests remain distinct.
Published total columns must not be added to their components. Blank
means not reported; numeric zero, when present, means reported zero.

## Non-additive printed summary controls

All imported facts have row_grain=detail. Printed summaries and controls
are never appended as additive detail records. Repeated printed appearances
are duplicate evidence, not additional amounts.

headline_controls.csv retains **42 selected non-additive control cells**:
40 reported amounts and two blank controls. All match the PDF and scoped
sums of detail facts exactly:

| Retained control scope | Printed page | Cells |
| --- | --- | ---: |
| Army, Navy and Air Force department rollups | 1 | 21 |
| O&M title, indefinite accounts, combined title plus indefinite | 3 | 21 |

Control source URLs cite the checked O-1 PDF, not an RF-1 file. Department
rollups use the official account lists in provenance.json, not organization
suffixes. The overlapping title/indefinite/combined control scopes are not
three additive datasets.

Other printed summaries are **outside headline_controls.csv coverage**:
Defense-Wide (p. 2); Transfer Accounts (pp. 2 and 55); Miscellaneous Accounts
(pp. 3 and 55); individual appropriation summaries and account totals;
44 distinct account/activity subtotal scopes, printed 74 times across
pp. 4–54; and lower activity-group subtotals such as Land Forces and Base
Support. The indefinite total on p. 56 repeats p. 3. These omitted controls
are not represented as facts or claimed as individually reconciled here;
full detail-row coverage was verified independently of summary coverage.

## Corrections and remaining source limitations

No candidate printed detail amounts, signs, blanks, identities or titles
needed correction. The preliminary unverified FY25 mapping annotation was
replaced after the full comparison passed. The service headline source URL
was corrected from an unverified combined/RF-1 URL to the actual checked
O-1 PDF. PDF evidence, comparison counts and summary coverage are recorded
in provenance.json and this README so they survive a squash merge.

Unprinted workbook metadata and the native workbook-only FY25 lanes retain
their stated source limitations. Verification covers only this PB27 edition
and the cited PDF pages; it does not claim verification of other source
editions or of execution data.

## Rebuild and verify

Download the exact mirror workbook from the URL in provenance.json. The
builder verifies its SHA-256 before reading it. Python 3.10+ and openpyxl
(tested 3.1.5) are needed for workbook regeneration; no new ODBA dependency
or existing ETL change is introduced.

Run from the repository root, using the pinned workbook path:

```bash
python tools/build_o1_pb2027_candidate.py --workbook PATH/peer-pb27.xlsx --out-dir data/o1/pb2027_candidate
python tools/build_o1_pb2027_candidate.py --workbook PATH/peer-pb27.xlsx --check data/o1/pb2027_candidate
ODBA_PB27_O1_WORKBOOK=PATH/peer-pb27.xlsx python -m unittest discover -s tests -p test_o1_pb2027_candidate.py -v
python -m unittest discover -s tests -p test_o1_pb2027_health.py -v
python -m unittest discover -s tests -p test_green_book_fy2025.py -v
```

The environment variable enables the real-workbook regeneration test; an
unset variable skips that test and is not evidence of exact regeneration.
The default tests still enforce full PDF-reference coverage and recompute
all 42 headline cells directly from the detail facts. Negative controls
reject omitted/extra rows, collapsed line 999 activities, lost signs,
blank-to-zero conversion, and swapped FY26 funding lanes.
