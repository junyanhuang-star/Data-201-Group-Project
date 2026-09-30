# SF Rent Board inventory: independent 3NF implementation

This folder is my implementation of the database portion of the project. It keeps the raw filing row as the fact grain and makes every transformation auditable.

## Source and grain

The source contains 28 delivered columns. One row represents one rental-unit report in one annual filing. `unique_id` is the source row key, but it is a signed hash rather than a persistent unit identifier. The data does not support linking the same physical unit across years.

The source also does not support a trustworthy `Property` or `Building` entity. `block_num` is an assessor block, not a building key, and the `point` coordinate is privacy-jittered. Building-level values such as `unit_count` and `year_property_built` therefore stay on the filing fact row.

## Files

- `RELATIONAL_SCHEMA.md` explains the proposed 3NF relations, functional dependencies, and the ER relationships to reproduce in MySQL Workbench.
- `COLUMN_DECISIONS.md` accounts for all 28 source columns and documents the 1NF, 2NF, and 3NF decisions.
- `NOTES_RECONCILIATION.md` compares the original project notes with the revised design and identifies source-version differences that must be resolved.
- `APPROACH_COMPARISON.md` compares the project-notes-driven reference model with the teammate’s `jun/house` implementation and explains how the music-schema template can guide SQL comments.
- `IMPLEMENTATION_COMPARISON.md` compares the two cleaners, schemas, loaders, and validation strategies at implementation level.
- `MERGED_SCHEMA_REVIEW.md` gives the recommended merged baseline and the review checklist before adoption.
- `SAMPLE_PIPELINE_RUN.md` records the commands, outputs, Workbench steps, and troubleshooting for the committed 100-row sample.
- `AI_USE_LOG.md` records the initial prompt, assistance scope, reference materials, and academic-integrity disclosure.
- [`schema.sql`](../schema.sql) creates the normalized MySQL 8 schema and lookup tables.
- [`clean_inventory.py`](../clean_inventory.py) performs preprocessing in Python: mappings, type parsing, utility/history splitting, and quality flags.
- [`load_3nf.py`](../load_3nf.py) performs a two-pass ID-resolution stage and generates TSV files plus `load_3nf.sql` for MySQL import.
- [`preprocess.sql`](../preprocess.sql) is only a MySQL loading note. It does not contain course-out-of-scope transformation logic.
- [`validation.sql`](../validation.sql) checks row preservation, foreign-key orphans, and the main assumptions behind the decomposition.

## Discussion sample

`../generated/Rent_Board_Housing_Inventory_sample_100.csv` contains the first
100 data rows from the verified export, copied with a CSV-aware parser so
quoted fields remain valid. The corresponding discussion outputs are in
`../generated/sample_cleaned/` and `../generated/sample_load/`. The generated
`sample_load/load_3nf.sql` can be opened in MySQL Workbench after running the
schema. These files are small enough to keep for team discussion; they are not
a substitute for rerunning the workflow against the full CSV before final
analysis.

The current repository copy is still a text summary with a `.csv.gz` suffix, but the attached `/Users/aduques/Downloads/Rent_Board_Housing_Inventory_20260927.csv` is the verified 28-column CSV to use for reference preprocessing and sample generation.

The two-pass loader was tested against that attached export. The run observed
551,241 source rows and staged 551,241 reports, 81,075 history rows, 690,454
utility rows, and 10,260 quality-issue rows. These counts are a verification
of the current file, not assumptions that should be hard-coded for a future
download.

The 28-column audit is explicit: every source column is either retained in `UnitReport`, moved to a lookup/child/junction relation, parsed into a typed value, or retained as raw text alongside a derived value. Metadata is considered for provenance but may be excluded from the final analytical schema.

## Load order

```text
clean_inventory.py -> schema.sql -> load_3nf.py -> load_3nf.sql -> validation.sql
```

Run the cleaner for an auditable preprocessing export if desired. Then run
`schema.sql`, run `load_3nf.py` against the verified CSV, execute its generated
`load_3nf.sql` with MySQL local-infile support enabled, and run `validation.sql`.
The loader is included as a reference and requires team review before use.

For the committed 100-row discussion sample, the commands are:

```bash
python3 own_implementation/clean_inventory.py \
  --source own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv \
  --output-dir own_implementation/generated/sample_cleaned

python3 own_implementation/load_3nf.py \
  --source own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv \
  --output-dir own_implementation/generated/sample_load
```

## Cleaning policy

Cleaning is conservative. Python adds canonical values for analysis, while the raw label is retained in the lookup table or fact row. A malformed date becomes `NULL` plus a quality issue. Rent and square footage remain bands, not invented numeric measurements. Utility checkboxes become rows in a junction table; free-text “other utilities” remains available for audit and is tokenized only when a known utility word is detected.

## AI Use Disclosure

The generated ER diagram, Markdown files, explanations, SQL files, Python files, and any other materials from this prompt session will not be used as-is for submission, because doing so would not be consistent with academic integrity expectations. These materials are being used only as references to help our team understand the problem and finalize our own work.

If our team decides to use parts of the proposed approach, we will disclose that AI was used to help determine bash commands for finding unique values, identify ways to group inconsistent data, and draft preprocessing logic that parses and formats rows.

The preprocessing stage, particularly the non-SQL Python preprocessing that may be outside the scope of the course material, was developed with AI assistance. AI helped refine our ideas about how to organize the data, but the team will review, rewrite, test, and modify the approach as needed.

Any ER diagram, SQL tables, Python code, Markdown explanations, schema decisions, and other materials used in the final project will reflect our team’s own work and understanding. The team will verify, rewrite, and modify any adopted ideas, disclose the relevant AI assistance, and remain responsible for explaining all submitted work.
