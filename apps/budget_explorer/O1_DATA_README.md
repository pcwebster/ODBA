# Budget Explorer O-1 inputs

Pinned ODBA source: [`b9ea2eb`](https://github.com/pcwebster/ODBA/tree/b9ea2eba7c65cb40b4086777a59271bde04af880).
The export is read-only. It does not change the canonical ETL, Green Book or
other exhibit tables. No downloads or third-party Python packages are needed
to rebuild from the included source snapshot.

```sh
python build_o1_explorer.py --snapshot snapshot o1_payload.json
python -m unittest -v test_build_o1_explorer
# Or read the identical immutable Git blobs:
python build_o1_explorer.py /path/to/ODBA o1_payload.json
```

PB25/PB26/PB27: 434/407/397 detail rows, 27/56/42 control cells.
The builder matches 6,930 exact amount/blank positions against committed
official PDF extraction manifests and separately reconciles 125 published
control positions against detail and the committed source control values.
The manifests were checked against original PDFs upstream; this builder
does not re-extract the PDF binaries. The only non-official money columns
are the three clearly identified PB27 FY25 workbook columns; they remain
detail-only and are not additional amounts on top of the printed lane.

## How to read the payload

- `lanes`: native column IDs prefixed by edition; `fy` is funding FY,
  `vintage` is the publication edition, `kind` is the source stage,
  and `primary` means the lane appears in the official exhibit PDF.
- `controls`: one official published headline cell per scope and lane.
  `amount` is a signed integer in USD thousands, or `null` for a printed
  blank. A missing control is not available in this snapshot; it is not zero.
  Controls are not additive across scopes or stages, and do not include every
  summary printed in the PDF. Show only same-FY available positions for a
  selected scope. FY25 defaults to the O&M Title + Indefinite Accounts.
- `detail`: one row per vintage/account/BA/line with lane-keyed amounts.
  IDs include the vintage and are not cross-vintage matches. `scope`
  is the native nonoverlapping leaf; `scopes` includes overlapping
  headline groups used for scope-aware filtering. `title` is workbook
  text if present, `publishedTitle` is official PDF text. Identifiers are
  strings (preserve leading zeroes and unprinted blanks). Accounts,
  organization, and line classification are not interchangeable.
- `page` is the printed O-1 page; `pdfPage` is the physical page;
  `url` includes a physical-page anchor. `sourceRow` and `sourceUrl`
  retain native row lineage in addition to the official PDF link.
- `provenance`: PDF and workbook fingerprints, merged input hashes,
  official detail/control coverage, and exact lane blank/negative/zero counts.
- `qaFlags`: `pb26_fy25_nonadditive` marks six official FY25 rows
  where enacted and supplemental repeat the published total. Never add those
  lanes to derive the published total. `workbook_title_differs` preserves a
  title difference without implying an amount mismatch. `blank_line_id` is
  source blank, not an ingestion omission.

The fixed measure is Total Obligational Authority in current USD thousands.
The FY25 request, enacted, supplemental, published total and actuals are
different as-published observations, not a same-stage trend or measured
outlays. A spend plan is neither enacted authority nor actual spending.
Core Green Book values and existing exhibit request detail are separate grains.
