# Implementation Comparison: Current Approach and `jun`

This comparison is for team review. It compares implementation choices, not
which teammate's work is "right." Both approaches target the same 28-column
Rent Board layout, but the snapshots differ: the attached current export has
551,241 rows, while the teammate's checked-in notes describe an earlier
550,201-row export. Counts must therefore be recomputed from the one file the
team chooses before presenting measured statistics.

## Overall result

The approaches agree on the central dependency decisions:

- `unique_id` identifies one submitted unit report at this dataset grain.
- `case_type_name` belongs with `submission_year` in a filing-cycle lookup.
- `point` should be parsed into longitude and latitude, while neighborhood and
  supervisor district remain geographic lookups.
- `block_num` is not a stable building key, so a property/building table should
  not be invented from it.
- Repeating utilities belong in a `Utility` lookup plus a report-utility
  junction table.
- JSON occupancy history belongs in child rows with a sequence number.
- Raw bedroom, bathroom, square-footage, and rent labels should remain
  available beside normalized values so cleaning is auditable.
- Invalid or ambiguous values should be flagged rather than silently deleted.

The meaningful differences are implementation depth, naming, and how much
quality information is retained—not a disagreement about the main 3NF idea.

## Team discussion summary — exact wording

The following notes record the team's interpretation in its own wording:

- Both implementations generally agree on the finalized 3NF, with differences being slight naming conventions. Lookup tables are used to handle M:N relationships like for the utilities. For bands, the raw labels are maintained, but these values are represented with normalized values.
- Validation has a key difference and should be up for discussion. My implementation strictly checks for existing unique_ids but does not check if non-primary key attributes are duplicated. On the other hand, the implementation in /jun does flag these duplicate non-primary attributes. Both implementations will allow these in, but only the implementation in /jun flags them. It would only matter if we plan to use this flag as a potential query question, but it is definitely much more future-proof compared to my approach. The validation done in /jun better handles future data where more duplicate non-primary rows are added, whereas mine will not flag the differences.
- Unformatted/malformed dates are completely rejected on the /jun implementation, but the approach here tries to format them to a consistent format and try to preserve all rows
- The difference between my implementation and the one in /jun is that instead of excluding malformed values, they are replaced with NULL, and additional tables are created to flag these missing data. The implementation done in /jun follows the 3NF that I have as well with the key difference being that I do not have an extensive design to properly audit invalid and duplicate data that would be used for describing the dataset

### Technical clarification for the date note

The last bullet is useful as a discussion of the perceived difference, but the
team should verify the exact behavior before presenting it. In the checked-in
`/jun` loader, an invalid or out-of-range date is generally converted to
`NULL` and recorded through a quality flag rather than causing the entire source
row to be rejected. The practical difference is therefore that `/jun` applies
stricter typed-date handling and records the loss of the original typed value,
while this branch emphasizes preserving the raw value in `QualityIssue` and
continuing the load. The team should decide which wording matches the final
code they actually adopt.

## File-by-file comparison

| Area | Current branch | `jun` branch | Recommended merge |
|---|---|---|---|
| Preprocessing | `clean_inventory.py` uses the Python standard library, writes ordinary CSV files, and keeps raw labels plus parsed values. | `clean_inventory.py` uses pandas and writes a typed parquet result with reconciliation counters. | Keep the standard-library CSV cleaner for readability and portability; add the teammate's measured quality checks and expanded utility vocabulary. |
| Dimension discovery | Dimensions are discovered while reading rows and stored in Python dictionaries. | The loader performs a first pass, then assigns deterministic IDs before a second pass. | Use the two-pass structure. It prevents foreign keys from depending on arbitrary row order. |
| Schema names | PascalCase names such as `UnitReport`, `BedroomLabel`, and `ReportUtility`. | Snake_case names such as `unit_record`, `bedroom_type`, and `record_utility_included`. | Either naming convention is valid. Keep the current names if the existing ERD and presentation use them; document aliases if the teammate's loader is reused. |
| Utility parsing | Four checkbox columns plus a smaller free-text vocabulary; provenance is represented by `source_checkbox` and `source_text`. | A larger vocabulary, including hot water, cable, laundry, janitorial, solar, and an `other` fallback. | Keep the provenance columns and adopt the expanded vocabulary only after reviewing false-positive substring matches. Always retain the original free text on `UnitReport`. |
| Bedroom/bathroom labels | Raw label and canonical numeric value are stored together; shared and unparseable bathroom values are distinguished. | Same basic design, with measured examples and stricter parser diagnostics. | Merge the parser diagnostics, but do not replace raw labels with canonical values. |
| Bands | `SquareFootageBand` and `RentBand` store bounds and special flags. | Same idea, with fixed IDs and explicit coverage checks for every source label. | Keep raw labels, min/max values, no-rent/unknown flags, and explicit checks that every observed label has a dimension row. |
| Dates/history | Dates are parsed into `UnitReport`; history JSON becomes `OccupancyHistory` rows with `seq_no`. | Same, plus date-range and unknown-reason lookup tables and more contradiction flags. | Keep `seq_no` as a source-array position, not as a parsed source column. Add date-range normalization if the team wants the richer version. |
| Quality data | `QualityIssue` stores row-level issue code, column, raw value, and detail. | `quality_flag` plus a junction table supports reusable issue definitions and many flags per record. | The current `QualityIssue` is easier to explain in this course project. It can be expanded later without changing the core fact tables. |
| Duplicate handling | No duplicate-group table is currently populated. | Computes content hashes and preserves duplicate rows while tagging groups. | Add duplicate analysis before deciding whether a duplicate table is needed. Never delete rows merely because they look identical. |
| Loading | Current `preprocess.sql` is a planning/reference script, not a complete CSV-to-FK loader. | `load_3nf.py` uses two passes and generates TSV files plus `LOAD DATA LOCAL INFILE` SQL. | Add the new `load_3nf.py` on this branch, but keep it separate from the schema and explain that CSV loading is an orchestration step outside the core lecture DDL. |
| Validation | `validation.sql` contains checks for keys, nulls, ranges, and row counts. | `validate_3nf.sql` adds round-trip counts, orphan checks, source-label coverage, and quality summaries. | Combine both sets and run them after loading. Validation should expose failures, not turn them into zeros. |
| Documentation | Current documents emphasize the user's notes, 1NF-to-3NF reasoning, and presentation study guidance. | Teammate documents emphasize measured counts, functional-dependency evidence, and loader instructions. | Keep the notes-based explanations and add measured implementation evidence as a separate comparison/review document. |

## Current-branch gaps found during the comparison

1. The existing cleaner has a leftover check for `occ_history_start` and
   `occ_history_end`, which are not columns in the verified 28-column CSV. The
   JSON history parser is the correct source for those dates; the stale check
   should be removed or rewritten.
2. The cleaner writes raw labels and intermediate IDs are not resolved into
   every foreign key required by `schema.sql`.
3. `case_type_name` is represented by the seeded `FilingCycle` table but is not
   explicitly emitted as a separate cleaned dimension file.
4. Extract metadata is currently taken from the last row after iteration. The
   verified file repeats the same metadata, but the loader should capture the
   first values and reject a file if later rows disagree.
5. The current cleaner keeps all report dictionaries in memory. This is useful
   for learning, but a complete-file loader should stream its second pass to
   staged files.
6. The teammate's richer checks—future dates, vacant-with-rent,
   tenant-without-rent, zero unit counts, and duplicate groups—are not all
   represented in the current implementation.

## Merged implementation recommendation

Use this branch's `schema.sql` and notes-based naming as the presentation
baseline, then use the new two-pass Python loader as the import implementation:

1. Read the CSV once to discover stable dimension values and verify constant
   extract metadata.
2. Assign deterministic IDs for data-derived dimensions.
3. Read the CSV a second time, normalize values using the cleaner functions,
   resolve dimension IDs, and write staged table files.
4. Generate a `LOAD DATA LOCAL INFILE` script in foreign-key order.
5. Run `validation.sql` and the loader's reconciliation summary.

This preserves the course-readable decomposition while borrowing the strongest
implementation idea from `jun`: foreign keys should be resolved deliberately,
not inferred from the order in which rows happened to appear in the CSV.

## What should remain a team decision

- Whether to retain the richer duplicate-group and reusable quality-flag
  tables.
- Whether `case_type_name` is worth keeping when it is functionally determined
  by `submission_year`.
- Whether the loader should be used for the final project or only as a
  reference implementation.
- Whether to keep all utility terms as canonical categories or map unknown
  free-text utilities only to `other`.

These are modeling and scope choices. The loader should not silently decide
them on the team's behalf.
