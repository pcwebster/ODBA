# PB27 consolidated R-1 (standalone)

Source: the Comptroller's [Exhibit R-1, April 2026](https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_r1.pdf),
SHA-256 `1aa8846edb69d4c3a54e03b383b0cabb77f93433162b8139ab8cbb55bcc7882a`.
The official copy Peter provided matched the previously audited mirror byte for byte
([intake receipt](https://fmtransformation.atlassian.net/browse/DBDP-90?focusedCommentId=10678)).
The source PDF is not committed. The acquisition date, publication cadence, native funding
lanes and derived artifact hashes are in [provenance.json](provenance.json).
This is the approved R-1-only slice of [DBDP-90](https://fmtransformation.atlassian.net/browse/DBDP-90?focusedCommentId=10694),
not an import into the ODBA fact model.

| File | Grain and coverage |
| --- | --- |
| `detail_in_title.csv` | 1,148 unique detail rows inside the published RDT&E title. |
| `detail_outside_title.csv` | 15 unique detail rows outside the title. Some accounts (including 0107D and 0130D) overlap the O-1 sidecar; do not sum them with O-1. |
| `source_occurrences.csv` | 1,452 physical appearances of the detail rows, including 289 Defense-Wide repeats. Non-additive; join back only for citations. Contains the printed and physical PDF pages, printed row identity, title and security-code label as published, and presentation type. The label does not change the public source's status. |
| `published_controls.csv` | Ten appropriation controls and two separate scope totals from printed p. 1 / physical p. 6. Non-additive; do not sum these records with detail or with their descendant controls. |

Read appropriation, budget activity, printed line and program element as **text**.
The unique key is `(submission_edition, appropriation, budget_activity,
printed_line, program_element)`; a repeated appearance must agree across all
seven funding lanes, including blankness. Page position and title are evidence,
not identity. Reused program elements, including the printed classified placeholder,
are not global program identities.

The funding columns are signed integer USD thousands of **TOA as printed**. Empty
cells are unreported; literal zero is not empty. Keep the PB submission edition
separate from the funding fiscal year using the lane catalog in the provenance.
FY25 Actuals is historical TOA as reported, **not obligations or outlays**.
FY26 PL 119-21 Spend Plan is separate from FY26 Discretionary Enacted; FY27
Discretionary Request is separate from Mandatory Request. FY26 and FY27 published
totals are source lanes, not additional dollars to add to their components.
There is no default combined total across sources, vintages, bases or scopes.

## Rebuild and verify

Requires Python 3.10+ and Poppler's `pdftotext`. Supply the exact registered PDF:

```sh
python tools/build_r1_pb2027.py /path/to/FY2027_r1.pdf /tmp/pb27-r1
ODBA_PB27_R1_PDF=/path/to/FY2027_r1.pdf python -m unittest discover -s tests -p 'test_r1_pb2027.py'
```

The builder verifies SHA-256 before extraction, compares every detail appearance
and all 10,164 nullable amount positions against a separate coordinate extraction
of the same PDF, and reconciles the 70 appropriation positions and 14 scope-total
positions exactly (including blanks). Two independent extraction paths are used,
not two engines: both use Poppler. A hash, identity, coverage, repeat amount, or
control mismatch fails before writing the output. The source-supplied test
requires byte-identical regeneration. P-1, historical editions, the canonical ETL,
existing outputs, and the Explorer are out of scope.
