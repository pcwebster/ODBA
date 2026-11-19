# ODBA Budget Explorer with consolidated O-1

Open `index.html` in Edge, Chrome, Firefox, or Safari.
No terminal, login, or internet is needed; links to source PDFs require a
connection. The O&M funding tab uses PB25, PB26, and PB27. Select a funding
year and published scope for comparable observations. Each O-1 amount is
labeled with its funding fiscal year, budget edition, published basis, and
TOA measure. Search and expand budget lines within one budget submission. Existing Green Book and sampled program
views remain available, separate from O-1.

The default FY25 comparison shows the $338.098474B PB25 request, $338.459009B
PB26 enacted column, $342.358161B PB26 published total, and $350.101702B PB27
reported actuals for the O&M Title plus Indefinite Accounts. They are
as-published views of TOA, not outlays. The supplemental column is separate
and not safely additive to PB26 enacted; the PB26 FY26 reconciliation request
and PB27 P.L. 119-21 spend plan are separate. No automatic cross-vintage line
matching. A missing control or blank is not zero. No RF-1 or execution feed.

## Rebuild and verify

The source inputs are pinned to `pcwebster/ODBA` commit
`b9ea2eba7c65cb40b4086777a59271bde04af880`. The O-1 Git reader uses those
immutable blobs regardless of the current checkout; the included snapshot
contains the same bytes. Green Book and the tracked program outputs must
also match that input version for an identical full HTML rebuild. Install DuckDB in the Python environment
used for the preview builder. Use Node.js for the offline DOM smoke.
No new dependencies are needed to validate the O-1-only snapshot.

Run from `apps/budget_explorer`:

```sh
python build_preview.py /path/to/ODBA/data/green_book/fy2025/historical_qa_passed.csv /path/to/ODBA index.html
node smoke_preview.cjs index.html
python -m unittest -v test_build_o1_explorer
# Optional full browser QA, with Playwright and Chromium installed:
python browser_smoke.py index.html
# In managed environments that restrict file URLs, load the same HTML directly:
python browser_smoke.py index.html --content
```

See [O1_DATA_README.md](O1_DATA_README.md) for offline O-1 regeneration,
provenance, the data contract, and source limitations.

## Validation and scope

The current O-1 display build is committed as `index.html` with SHA-256
`d22a08af345a8d835dac2a892f4d474fb1cd792260b85b985205f4e292f12611`.
It regenerates byte for byte from the pinned inputs. The O-1 evidence
tests and offline Node DOM smoke pass on this build.

The earlier supplied preview was committed without changes to its HTML.
Its SHA-256 was
`6085d8a4f953e950b8aa7326b162830db6da85269a07948702792390d4c38bd0`.
The incoming source ZIP did not include a checksum manifest; all 13 O-1
input pins were verified against both the bundled snapshot and the Git
blobs at the declared commit. The earlier preview passed the Chromium
desktop and 360px mobile checks with `--content`. Those browser checks
were not rerun successfully on the current build. Direct file-URL
navigation and Windows file opening were not verified for this build.

The mobile browser smoke targets the primary amount list explicitly; an
expanded PB27 line also contains a separate workbook-only list. The Node
FY1948 missing-prior-year assertion is a renderer-only boundary check; the
real variance dropdown starts at FY1949. The browser test checks that
actual option boundary and the selectable negative-baseline case.

The historical chart covers FY1948–2023, while its accompanying numeric
table displays only the latest 12 years. A full-history accessible table
is outside this supplied preview's current UI. No ingestion, source data
or deployment configuration is changed by this app. Opening the offline
file and publishing a hosted site are separate actions; no site is
published by these scripts.
