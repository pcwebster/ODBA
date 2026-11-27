# fixtures/dbdp114: V4 measure-parity fixtures

These fixtures make DBDP-114 V4 (measure parity, c10626) machine-recomputable, as amendment 114-B (DBDP-114 c10628) requires. V4 recomputes the core measures of Peter's PB27 Defense-Wide O&M Executive Dashboard twice: once from the hand-shaped CSV below and once from the consumption layer (`output/consumption/fact_budget_long.csv` and its dimensions). Then it compares the two.

Everything in this README is frozen before the Tester runs V4. Under 114-B, a delta that wasn't declared here in advance is a FAIL. It can't be explained away after the run.

## Files

| File | What it is | Source |
| --- | --- | --- |
| `Defense_Wide_OM_PB27.csv` | The hand-shaped CSV the dashboard imports: 750 rows, 28 agencies, all `exhibit_type = OP-5`, FY2025 to FY2027. UTF-8 with BOM, CRLF line endings, kept byte-exact. | The model's only import table, `OP5`. Copied from the dashboard project's local data folder, file dated 2026-08-23, 155,221 bytes. |
| `core_measures.dax` | The four core measures, copied from `OP5.tmdl` | `PB27_Defense_Wide_OM_Executive_Dashboard.SemanticModel/definition/tables/OP5.tmdl` |
| `op5_partition.m` | The `OP5` import query (Power Query M). One deliberate change from the model's copy: the hard-coded local file path is replaced by a `FixtureRoot` parameter (the file's header says how to set it). The query steps are unchanged. | Same `OP5.tmdl`, partition section |
| `relationships.tmdl` | The model's one relationship, `OP5.service_agency_acronym` to `Agency.service_agency_acronym` | Same SemanticModel folder |
| `FIXTURE_SHA256.json` | SHA-256 digest of every file above and of this README | Generated at commit |

Not included: `Agency.tmdl` (the Mission Portfolio SWITCH map) and `Bridge.tmdl`. Neither feeds the four core measures. The SWITCH map belongs to DBDP-121.

The M query renames `Attribute` to `FY` and `Sum of Value` to `Amount`, types `FY` as whole number and `Amount` as decimal, and fills a blank `budget_activity_title` with "Core Operations". Only `FY` and `Amount` matter to the core measures.

## Core measures under test

| Measure | Hand-model definition | Consumption-layer equivalent |
| --- | --- | --- |
| `FY25 $` | `CALCULATE(SUM(OP5[Amount]), OP5[FY] = 2025)` | `SUM(amount_musd)` where `funding_fy = 2025` |
| `FY26 $` | `CALCULATE(SUM(OP5[Amount]), OP5[FY] = 2026)` | `SUM(amount_musd)` where `funding_fy = 2026` |
| `FY27 $` | `CALCULATE(SUM(OP5[Amount]), OP5[FY] = 2027)` | `SUM(amount_musd)` where `funding_fy = 2027` |
| `Total Amount` | `SUM(OP5[Amount])` | `SUM(amount_musd)` over FY2025 to FY2027 |

No other measures are under test.

## Slice

Both sides are computed on the same slice: FY2027 President's Budget, Defense-Wide O&M (OP-5).

- **Hand-model side:** the whole CSV. It already holds only this slice.
- **Consumption-layer side:** `budget_year = 2027` and `exhibit_type = 'OP-5'`, taken through `dim_program_hierarchy` on `record_id`.

The `budget_year = 2027` filter is required. `fact_budget_long` holds both the FY2026 and FY2027 submissions, so an unfiltered `FY26 $` would add the two submissions' views of FY2026 together.

At main 619337e this slice returns the same 28 `service_agency_acronym` values as the CSV.

## Expected values

Units $M, at the dashboard's display format `#,##0.0` (one decimal), which is the `formatString` on all four measures.

| Measure | Expected value ($M) | Exact sum from the CSV |
| --- | --- | --- |
| `FY25 $` | 41,562.1 | 41562.080 |
| `FY26 $` | 33,223.6 | 33223.593 |
| `FY27 $` | 37,995.0 | 37995.003 |
| `Total Amount` | 112,780.7 | 112780.676 |

PENDING PETER'S CHECK: these values were computed on 2026-11-27 from the CSV with the DAX above, not read off the dashboard. Before merge, Peter confirms the dashboard's four cards show the same numbers (or replaces them here).

## Comparison rule

- Each measure is computed on both sides and rounded to one decimal. The two must be exactly equal at that precision.
- No tolerance applies unless one is declared here, per measure, with a reason. Declared tolerances: none.
- Units: the CSV's `Sum of Value` (`Amount`) is in millions (`cost_units = Millions`). `amount_musd` is in $M.

## Known differences declared before the run

- None that change a value.
- Label-only: the hand model calls FY2026 "enacted", while the consumption layer labels FY2026 on FY2027-submission rows `amount_basis = estimate`.

## Independence of the fixture

The CSV is a pivot export (`Attribute`, `Sum of Value`, `source_file` such as `DAWDA_OP-5.json`) and was most likely shaped from ODBA's own earlier output (`output/fact_budget_line_items.parquet`), not built from the PDFs by hand. Its totals already equal the consumption layer's at main 619337e. So V4 here proves the consumption layer still reproduces the dashboard Peter briefs from. It does not independently check ODBA against the source exhibits.

## Receipt

After merge, post on DBDP-114: the merge SHA, these paths, and the digests from `FIXTURE_SHA256.json`.
