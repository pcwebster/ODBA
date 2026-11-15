# PB25 consolidated O-1 detail import

This isolated sidecar imports all 434 printed PB25 O-1 detail rows: 427
O&M-title and seven indefinite rows across 31 raw accounts. All 1,302
monetary positions have been independently checked against the original
PDF in both directions. The historical pb2025_candidate path is retained.
Existing PB26/PB27 ingestion, the health pilot, ETL, dashboard and Green
Book are unchanged. All amounts are TOA in USD thousands from this one
PB25 submission, not independently measured obligations or outlays.

## Sources and independent original-PDF check

The initial candidate was extracted from the pinned third-party mirror
workbook listed in provenance.json, with selected indexed official controls.
The combined OM Title plus Indefinite sheet supplies 434 physical detail
rows; other worksheets repeat or subset those observations. The workbook
bytes are hash-pinned; publisher-workbook byte equivalence is not claimed.
The later independent original-PDF comparison is separate from that initial
mirror/indexed extraction.

- Official source: <https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2025/FY2025_o1.pdf>
- Verified binary: FY2025_o1.pdf, uploaded by the user. The binary is not
  committed and no independent download is claimed.
- PDF SHA-256: `f4934028d923998791f672ee9f11e2094a3537ba89e406f9c42a324e2cf12111`
- Scope: printed O-1 **pp. 1–67**, physical PDF **pages 5–71**, one-based.
  This offset differs from PB26/PB27. Physical page 72 is the RF-1 table
  of contents; physical page 73 starts RF-1. Neither enters this import.

The independent extraction used PDF word coordinates, all three printed
monetary headings, account/line identities, printed activity/subactivity
scopes, classifications and geometric multiline titles. A separate plain-
text detail inventory checked coverage, and rendered pages verified signs,
CR adjustments, both Air Force line 999 records, shared BLI identities and
ambiguous labels. Every PDF detail must match exactly one candidate detail,
and every candidate detail must match a PDF detail; headline totals alone
are not the coverage test.

**Result: all 434 rows / 31 accounts match, with no omissions or extras.
All 1,302 cells match: 1,102 reported amounts and 200 blanks, including
15 signed negative amounts.** No literal numeric zero is printed; synthetic
regressions separately preserve zero versus blank. Printed activity,
subactivity and classification agree wherever present. There are no
unresolved printed identity or monetary mismatches.

`pdf_detail_reference.json` preserves the independently extracted printed
rows, PDF hash, page scope, identities, exact titles and three nullable
signed values. Its own SHA-256 is pinned in provenance.json. Every build
and the default tests enforce exact coverage and values against this stored
reference; they do not claim to download or re-extract a missing PDF.

## Three reporting lanes and identities

Keep these native lanes separate:

1. FY2023 actuals as reported in the PB25 submission.
2. FY2024 President's Budget request with continuing-resolution adjustments.
3. FY2025 request.

The source header and footnote identify the FY24 basis. Where footnoted,
a full-year appropriation had not been enacted when prepared, and amounts
reflect annualized levels under P.L. 118-35. Do not relabel this lane as
FY24 enacted or actual, or combine it with PB26's reported FY24 actuals.
The three trailing workbook cells containing the CR footnote are recorded
verbatim in provenance.json and checked on intake; they are not detail facts.

The stable within-edition grain is account + activity + line, not a BLI or
physical workbook row. Preserve both 3400F line 999 details under BA01 and
BA04 (printed pp. 39 and 43). Preserve 5751D/010 and 0134D/010 as separate
accounts even though both use BLI 1PL3: 5751D has FY23 3,731 thousand on
p. 63, while 0134D is independently printed on p. 62. The negative FY24
0100D/BA20/490/CR24 adjustment on p. 56 remains **-1,288,238** thousand.
All other negative signs and all blanks remain unchanged.

Eight workbook organization fields remain blank. On printed pp. 65–66,
28 rows do not print activity/subactivity codes. Those reference fields
remain null; their unique account/line pairs provide matching without
claiming the workbook's unprinted metadata was verified by the PDF. PB25's
5286A detail does print line **210** on p. 66; it is not replaced by the
blank line ID printed in the separate PB26 edition.

## Separate printed, workbook and indexed labels

All line_title_workbook values remain unchanged. The regenerated output
adds line_title_printed and pdf_printed_page from the verified PDF for every
row. There are **18 printed-title/workbook-label differences**, listed in
provenance.json; each source's wording remains in its own field.

For 0838D/170, the workbook label is **Adj to Match Continuing Resolution**.
The exact PDF title is **Support for International Sporting Competitions , Defense**,
including the space before the comma. The initial indexed label in
official_indexed_line_title omits that space; it is retained separately
as an indexed extraction rather than silently substituted for the PDF.
provenance.json records this additional indexed/printed spacing variant.
The printed-title field is checked exactly against the PDF reference,
including a regression rejecting either workbook or normalized indexed
wording in that field.

No monetary values, blanks, signs, row identities or workbook labels needed
correction. The import adds exact printed-label/page fields and persistent
PDF evidence. Initial indexed control/edge URLs were corrected from an
unverified RF-1/combined URL to the actual checked O-1 source URL. Initial
indexed labels retain their own provenance and are not asserted to be
verbatim PDF typography.

## Non-additive summaries and excluded subsets

headline_controls.csv retains 27 selected non-additive control cells,
independently matched to the original PDF: 26 reported amounts and one
blank. Tests also recompute each control directly from the detail facts.

| Retained controls | Printed page | Cells |
| --- | --- | ---: |
| Army, Navy and Air Force department account groups | 1 | 9 |
| Transfer and Defense-Wide groups | 2 | 6 |
| O&M title, indefinite, combined and miscellaneous | 3 | 12 |

Individual appropriation/account summaries, 63 distinct account/activity
subtotal scopes appearing 105 times, and lower activity-group subtotals
are outside this control file. Repeated summary appearances and combined/
component controls are duplicate or overlapping evidence, not extra facts.
No summary is appended to additive detail totals.

Only the combined worksheet's detail rows are ingested. Overseas operations
cost (OOC) subset presentations and other repeating tabs are not unioned
with these rows. There is no separate OOC section within the verified
printed O-1 boundary; RF-1 and later material are excluded. Verification
is limited to this PB25 edition and its cited pages. Unprinted workbook
metadata retains its stated limitation; other vintages and execution
sources are not being verified here.

## Exact regeneration and tests

Obtain the exact mirror workbook from provenance.json. Its SHA-256 is
verified before parsing. Python 3.10+ and openpyxl (tested 3.1.5) are needed
for workbook regeneration; no dependency declaration is changed. Run from
the repository root:

```bash
python tools/build_o1_pb2025_candidate.py --workbook PATH/peer-pb25.xlsx --out-dir data/o1/pb2025_candidate
python tools/build_o1_pb2025_candidate.py --workbook PATH/peer-pb25.xlsx --check data/o1/pb2025_candidate
ODBA_PB25_O1_WORKBOOK=PATH/peer-pb25.xlsx python -m unittest discover -s tests -p test_o1_pb2025_candidate.py -v
ODBA_PB26_O1_WORKBOOK=PATH/peer-pb26.xlsx python -m unittest discover -s tests -p test_o1_pb2026_candidate.py -v
ODBA_PB27_O1_WORKBOOK=PATH/peer-pb27.xlsx python -m unittest discover -s tests -p test_o1_pb2027_candidate.py -v
python -m unittest discover -s tests -p test_o1_pb2027_health.py -v
python -m unittest discover -s tests -p test_green_book_fy2025.py -v
```

Supply all pinned workbook paths to run the real-file regeneration tests;
skips do not establish exact regeneration. Default PB25 tests still enforce
the complete PDF reference, all three reporting lanes, separate accounts
sharing BLIs, activity-qualified line 999 identities, all 15 signs, nullable
cells, exact printed labels and independent sums for the 27 controls.
