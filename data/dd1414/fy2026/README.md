# FY2026 DD 1414 enacted base (DBDP-134)

Built by `tools/build_dd1414_fy2026.py` from the pinned FY 2026 DD 1414 Base for
Reprogramming Actions PDF (SHA-256 `4cef3b41d68da3812828993bbb4b110d1aca5d5b0a67b1cb9eee8961324a96a3`). The PDF is not committed, and the
build stops on any other file.

## Files

| File | Grain | Additive |
| --- | --- | --- |
| `baseline_lines.csv` | one row per `line` or `parent` (heading, no amounts) | only rows with `is_additive = true` |
| `adjustments.csv` | one row per congressional adjustment or general provision, with its parent line | lane g sums to its line's lane g |
| `published_controls.csv` | printed subtotals, grand totals and Financing rows, with the line sums beside them | no, tie-out only |
| `source_cells.csv` | one row per text token on a data page: both readers, font, size, colour, strike, edit disposition | no |
| `provenance.json` | source pin, readers, lane catalog, counts, colour and edit census, diagnostics, file hashes | |
| `edit_exceptions.json` | reviewed dispositions for edit tokens (committed input) | |
| `published_differences.json` | the 12 printed controls that miss their line sum by rounding (committed input) | |

## Lanes

Lane columns keep the form's letters. c is the request presented to Congress. e and g are
changes, not stages. i is the base after congressional and presidential action (enacted).
b, d, f and h are the matching quantities. No lane is relabeled or combined. Blank stays
blank and a printed zero stays zero.

## Keys

`record_id` is a hash of content fields only: form, fiscal year program, account code and
availability as printed, organization, budget activity, row kind, printed line (this edition
prints none), line identifier and normalized title. An adjustment adds its row kind, footnote
codes and text to its parent's key. A repeated key stops the build, with one reviewed
exception: on N-29, "CVN Refueling Overhauls" (1611N 2026/2030, BA 02) prints a second time
blank in every lane with no adjustments. That repeat stays in `source_cells.csv` as printed
and is left out of `baseline_lines.csv` (Peter, DBDP-134 c10840). If it ever shows a value,
the build stops.

## What not to sum

Sum only `baseline_lines.csv` rows with `is_additive = true`, or `adjustments.csv` lane g.
Never add `published_controls.csv` rows to anything. Appropriated-base rows repeat their line
and appear in `source_cells.csv` only.

## Edits and strikes in this edition

In this edition only: Acrobat text edits appear on A-58 (red Arial runs replacing struck values, and one black amount in its own font subset) and on AF-43 (one black footnote code in its own font subset). Red here marks a published correction. It is not a rule for other forms or editions and not a funding-type classification; B4 does not classify (c10824 section D).

Struck values never own an amount. A row whose title is struck is superseded and appears only in
`source_cells.csv`. `provenance.json` lists each edit token with its owner, the first-printed
values of edited lines, and each reviewed exception with its approval comment.

Twelve printed controls in RDT&E Navy and RDT&E Defense-Wide miss the sum of their lines by 1 or 2
(rounding as published). They are published as printed and flagged in `published_rounding`
(Peter, DBDP-134 c10838). Any other difference stops the build.

## Rebuild

```
python3 tools/build_dd1414_fy2026.py --pdf <path to the pinned PDF>
python3 tools/build_dd1414_fy2026.py --pdf <path to the pinned PDF> --check
```

Needs Poppler 24.02.0 and pdfminer.six 20260107 (requirements.txt). `--check` rebuilds in
memory and stops unless every file is byte-identical to the committed one.
