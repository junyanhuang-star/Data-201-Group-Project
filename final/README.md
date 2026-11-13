# DATA 201 Final Project

This directory contains the final database, SQL analysis, interactive dashboard,
technical report, and presentation materials.

## Project structure

- `database/` - final schema and data-loading scripts
- `sql/` - member queries, views, and performance analysis
- `dashboard/` - interactive application/dashboard
- `report/` - report source, figures, screenshots, and acknowledgements
- `presentation/` - final presentation materials
- `docs/` - pipeline instructions, ERD, data dictionary, and AI disclosures

## Run the database pipeline

Follow [`docs/PIPELINE_RUN.md`](docs/PIPELINE_RUN.md). The final database should
be loaded from the complete team CSV, not the optional 100-row sample.

The main setup files are:

```text
final/database/schema.sql
final/database/clean_inventory.py
final/database/load_3nf.py
```

The loader-generated files are local outputs and should be regenerated on each
computer because their SQL contains absolute file paths.

## Run final SQL analysis

After loading the database, run the SQL files in `final/sql/`. Each query should
document its domain question, SQL approach, result, and interpretation.

## Archived work

The earlier implementation and mid-presentation materials are preserved in
`mid_presentation/` at the repository root.
