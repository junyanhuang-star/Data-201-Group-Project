# Merged Relational-Schema Review

This document records the recommended merged baseline after comparing the
current branch with `origin/jun:house`. It is a review aid, not a final project
writeup.

## Grain and key

The fact-table grain is one row per `unique_id`, representing one unit report
as submitted for a filing cycle. `unique_id` is therefore the primary key of
`UnitReport`. The source's repeated metadata is extract-level information and
belongs in `ExtractBatch`.

The single-column primary key means there is no partial dependency inside the
fact table, so 2NF is satisfied at this grain. The 3NF work is mainly removing
transitive dependencies and repeating groups while preserving source facts.

## Recommended tables

| Table | Role | Why it remains in the merged design |
|---|---|---|
| `ExtractBatch` | Dataset-level metadata | Prevents `data_as_of` and `data_loaded_at` from being repeated on every report. |
| `FilingCycle` | Submission-year lookup | Captures the observed relationship between submission year and case type. |
| `Neighborhood` | Geographic label lookup | De-duplicates repeated neighborhood names. |
| `SupervisorDistrict` | District lookup | Stores the district identifier referenced by locations. |
| `LocationPoint` | Parsed point plus geographic FKs | Makes longitude and latitude usable independently for mapping and checks. |
| `AssessorBlock` | Block-number lookup | Preserves block labels without falsely treating a block as a building. |
| `BlockAddress` | Repeated block-address label lookup | Separates address-label repetition from report facts; it is not asserted to be a property entity. |
| `OccupancyType` | Occupancy category lookup | Prevents repeated category strings in the fact table. |
| `BedroomLabel` | Raw bedroom label and canonical count | Supports grouping while retaining unusual values for audit. |
| `BathroomLabel` | Raw bathroom label and canonical count/flags | Represents shared and unparseable values without forcing them to numeric zero. |
| `SquareFootageBand` | Raw band plus numeric bounds | Allows range-aware analysis without pretending the band is an exact measurement. |
| `RentBand` | Raw band plus numeric bounds | Preserves no-rent and overlapping-band semantics. |
| `UnitReport` | Main fact table | Holds facts that belong to the individual submission. |
| `Utility` | Utility vocabulary lookup | Converts five wide utility inputs into a repeatable many-valued structure. |
| `ReportUtility` | Report-to-utility junction | Handles any number of included utilities and records checkbox/text provenance. |
| `OccupancyHistory` | Repeating JSON history child | One history event per row, with `seq_no` preserving source-array order. |
| `QualityIssue` | Row-level issue log | Makes invalid, ambiguous, or contradictory inputs visible without dropping the report. |

The teammate's `date_unknown_reason`, `date_range_type`, `quality_flag`, and
`duplicate_group` tables are valid extensions. They should be added only if the
team wants the extra abstraction and can explain the dependencies in the
presentation. They are not required to establish the core 3NF decomposition.

## Why the merged version is safer

- It keeps raw source labels and cleaned values together, so a mapping can be
  reviewed or revised without re-downloading the source.
- It does not infer a building entity from `block_num`, because the observed
  source can report different addresses, unit counts, years built, and points
  for the same block across filings.
- It treats utility fields as a repeating group rather than five unrelated
  attributes, while still preserving their source form.
- It treats history as a repeating group rather than storing JSON as one opaque
  fact column.
- It stores an invalid value as `NULL` only when the typed column requires it,
  and records the original value in `QualityIssue`.
- It keeps open-ended rent and square-footage bands as ranges. A midpoint would
  be an additional assumption and should not be inserted silently.

## Loader contract

The loader added to this branch does not change the schema design. It performs
the mechanical work of:

1. discovering data-derived dimension rows;
2. assigning IDs consistently;
3. parsing dates, WKT points, labels, bands, utilities, and history;
4. writing table-shaped staging files; and
5. generating MySQL `LOAD DATA LOCAL INFILE` statements in dependency order.

The Python step is intentionally separate from the DDL. The SQL schema defines
keys, foreign keys, types, checks, and tables; Python handles CSV parsing and
normalization because that was not a central lecture topic. The team should
rewrite the explanation in its own words if this reference loader is adopted.

## Review checklist before adoption

- Run the loader against the exact CSV used by the team, not an older export.
- Confirm the header has all 28 expected columns.
- Confirm metadata is constant across rows.
- Compare input report count with staged `UnitReport` count.
- Check that every fact-table foreign key resolves.
- Inspect unparseable bedroom/bathroom labels and unmatched utility text.
- Decide whether duplicate rows represent valid indistinguishable reports or
  should only be excluded in downstream analysis.
- Run the SQL validation queries after loading.
- Have each team member explain one decomposition and one cleaning rule before
  presenting the ER diagram.
