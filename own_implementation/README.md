# SF Rent Board Housing Inventory: MySQL pipeline

Loads the Rent Board Housing Inventory CSV into a 3NF MySQL database,
`sf_rent_board` (16 tables).

## Files

| File | Role |
|---|---|
| `schema.sql` | Creates the `sf_rent_board` database: tables, keys, constraints, seed rows |
| `clean_inventory.py` | Parsing rules (bedrooms, bathrooms, rent/sqft bands, dates, utilities) |
| `load_3nf.py` | Reads the CSV and writes the load files (uses `clean_inventory.py`) |
| `analysis_queries.sql` | Example queries used in the presentation |
| `sf_rent_board_ERDiagram.png` | ER diagram of the schema |

## Requirements

- Python 3 (standard library only)
- MySQL 8 with `LOCAL INFILE` allowed on the server **and** the client
- The CSV: `Rent_Board_Housing_Inventory_20261001.csv` (2026-10-01 extract,
  551,551 rows). It is too large for GitHub, so it is shared outside the repo.

## Run it

**1. Generate the load files** (from the repository root):

```bash
python3 own_implementation/load_3nf.py \
  --source /path/to/Rent_Board_Housing_Inventory_20261001.csv \
  --output-dir own_implementation/generated/load
```

This writes to the output directory:
- `staging/*.tsv`: one file per table
- `load_3nf.sql`: the load script. It contains absolute paths, so generate
  your own copy rather than using someone else's.
- `quality_issues.csv`: every data problem found (unique_id, column, issue
  code, raw value, description)

**2. Create the database:** run `own_implementation/schema.sql`. It drops
and recreates `sf_rent_board`.

**3. Allow local file loading:**

```sql
SET GLOBAL local_infile = 1;
```

In Workbench, also add `OPT_LOCAL_INFILE=1` to the connection's Advanced
settings, then reconnect. In IntelliJ/DataGrip, set the driver property
`allowLoadLocalInfile = true`.

**4. Load the data:** run `own_implementation/generated/load/load_3nf.sql`.
It ends with two result grids. Every `verdict` must be `ok` and every
`orphans` count must be 0.

If the load fails, rerun `schema.sql` (step 2), then step 4.

## Expected result (2026-10-01 extract)

| Table | Rows |
|---|---|
| UnitReport | 551,551 |
| ReportUtility | 701,950 |
| OccupancyHistory | 81,085 |
| LocationPoint | 13,448 |
| BlockAddress | 7,677 |
| AssessorBlock | 4,288 |

`quality_issues.csv` has 9,981 rows. Every source row is loaded. A value
that cannot be stored (for example a date in year 0001) is set to NULL, and
its original text is kept in the CSV.
