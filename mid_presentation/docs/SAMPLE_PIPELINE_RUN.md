# Reproducible Rent Board Pipeline

This document explains how to run the preprocessing and loading workflow with
the CSV version selected by the team. The commands use variables so that a
teammate can change the source filename without rewriting every command.

The generated files are local outputs. They do not need to be committed to the
repository because the Python scripts recreate them.

## 1. Set the source CSV and output folders

Run these commands from the repository root. Replace only `CSV_PATH` with the
absolute path to the exact CSV snapshot agreed on by the team. All teammates
should use the same CSV file version for comparable results.

```bash
# CHANGE THIS: replace the path with your own local project-directory path.
cd "/absolute/path/to/Data-201-Group-Project"

# CHANGE THIS: replace with the path to the exact team CSV on your computer.
CSV_PATH="/absolute/path/to/Rent_Board_Housing_Inventory.csv"

# KEEP THESE PATHS AS WRITTEN. SAMPLE_CSV is created by the next step.
SAMPLE_CSV="own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv"
SAMPLE_CLEANED_DIR="own_implementation/generated/sample_cleaned"
SAMPLE_LOAD_DIR="own_implementation/generated/sample_load"
FULL_CLEANED_DIR="own_implementation/generated/cleaned"
FULL_LOAD_DIR="own_implementation/generated/load"
```

The repository path above is only an example. If the repository is located
elsewhere, change the `cd` path. The `CSV_PATH` value must point to the local
copy of the team CSV; it is not a URL. `SAMPLE_CSV` is not an input file that
the team needs to download: the sample-extraction step creates it from
`CSV_PATH`.

## 2. Optional: create a 100-row discussion sample

This copies the header and first 100 data rows while preserving quoted fields
and embedded commas. It does not modify the original CSV.

```bash
mkdir -p "$(dirname "$SAMPLE_CSV")"

python3 - "$CSV_PATH" "$SAMPLE_CSV" <<'PY'
import csv
import sys

source_path, sample_path = sys.argv[1:]
csv.field_size_limit(10**9)

with open(source_path, encoding="utf-8-sig", newline="") as source, \
     open(sample_path, "w", encoding="utf-8", newline="") as output:
    reader = csv.reader(source)
    writer = csv.writer(output)
    writer.writerow(next(reader))
    for number, row in zip(range(100), reader):
        writer.writerow(row)
PY
```

Check the sample size:

```bash
python3 - "$SAMPLE_CSV" <<'PY'
import csv
import sys

with open(sys.argv[1], encoding="utf-8-sig", newline="") as source:
    print(sum(1 for _ in csv.DictReader(source)))
PY
```

Expected output:

```text
100
```

The sample is for discussion and debugging only. Its counts and values may
differ from a later team CSV snapshot.

## 3. Run Python preprocessing

To inspect cleaned outputs for the 100-row sample:

```bash
python3 own_implementation/clean_inventory.py \
  --source "$SAMPLE_CSV" \
  --output-dir "$SAMPLE_CLEANED_DIR"
```

To preprocess the complete team CSV:

```bash
python3 own_implementation/clean_inventory.py \
  --source "$CSV_PATH" \
  --output-dir "$FULL_CLEANED_DIR"
```

The script creates the selected output directory if it does not exist. It
writes table-shaped cleaned files, including labels, utility rows, occupancy
history, and quality issues. This step is independent from the loader; the
loader parses the source CSV itself.

## 4. Generate the MySQL loader files

For the 100-row sample:

```bash
python3 own_implementation/load_3nf.py \
  --source "$SAMPLE_CSV" \
  --output-dir "$SAMPLE_LOAD_DIR"
```

For the complete team CSV:

```bash
python3 own_implementation/load_3nf.py \
  --source "$CSV_PATH" \
  --output-dir "$FULL_LOAD_DIR"
```

Each run creates:

```text
<output directory>/load_3nf.sql
<output directory>/staging/*.tsv
```

The generated SQL contains absolute paths to the staging files on the
computer that generated it. Therefore, each teammate should generate their
own loader SQL locally rather than sharing a generated SQL file from another
computer.

## 5. Load the tables in MySQL Workbench

1. Open and run `own_implementation/schema.sql`. This creates the
   `sf_rent_board` database, tables, constraints, and seeded lookup rows.
2. Enable `LOCAL INFILE` for both the MySQL server and the Workbench client if
   it is disabled by following the setup instructions below. Do this before
   opening or executing the generated loader. The earlier run produced error
   3948 until both sides were configured.

### Enabling `LOCAL INFILE`

Run this in a MySQL Workbench query tab using an account with permission to
change global server variables:

```sql
SHOW GLOBAL VARIABLES LIKE 'local_infile';
SET GLOBAL local_infile = 1;
SHOW GLOBAL VARIABLES LIKE 'local_infile';
```

The final query should show `ON`. Then configure the Workbench client for the
same connection:

1. Close the SQL editor or disconnect from the connection.
2. Open **Database > Manage Connections**.
3. Select the connection and open its **Advanced** settings.
4. Add `OPT_LOCAL_INFILE=1` to the connection's driver/other parameters,
   following the format already used by that Workbench version.
5. Save the connection and reconnect.

If `SET GLOBAL local_infile = 1` fails, the MySQL account does not have the
required server privilege. A database administrator must enable it, or the
team must use an approved alternative loading method.

3. Open the generated loader file. For the sample, this is:

   ```text
   own_implementation/generated/sample_load/load_3nf.sql
   ```

   For a full run, use:

   ```text
   own_implementation/generated/load/load_3nf.sql
   ```

4. Run the complete generated SQL file in Workbench.
5. Use the team's validation queries, if needed, to check row counts and
   foreign-key integrity. Validation documentation remains on the working
   branch unless the team decides otherwise.

If a load fails partway through, rerun `schema.sql` before retrying. The schema
script recreates the database so that the next load starts from an empty,
consistent state.

## 6. View sample table contents

After a successful sample load, these queries can be run in Workbench:

```sql
USE sf_rent_board;

SELECT * FROM ExtractBatch LIMIT 100;
SELECT * FROM FilingCycle LIMIT 100;
SELECT * FROM Neighborhood LIMIT 100;
SELECT * FROM SupervisorDistrict LIMIT 100;
SELECT * FROM LocationPoint LIMIT 100;
SELECT * FROM AssessorBlock LIMIT 100;
SELECT * FROM BlockAddress LIMIT 100;
SELECT * FROM OccupancyType LIMIT 100;
SELECT * FROM BedroomLabel LIMIT 100;
SELECT * FROM BathroomLabel LIMIT 100;
SELECT * FROM SquareFootageBand LIMIT 100;
SELECT * FROM RentBand LIMIT 100;
SELECT * FROM UnitReport LIMIT 100;
SELECT * FROM Utility LIMIT 100;
SELECT * FROM ReportUtility LIMIT 100;
SELECT * FROM OccupancyHistory LIMIT 100;
SELECT * FROM QualityIssue LIMIT 100;
```

The exact row counts depend on the CSV snapshot. For the previously tested
100-row snapshot, the loader reported 100 reports, 13 occupancy-history rows,
118 utility rows, and zero quality issues. Those are historical example
outputs, not guaranteed results for the team's final CSV.

Missing dates should be stored as SQL `NULL`, not `0000-00-00`. A quick check
is:

```sql
SELECT COUNT(*) AS total_reports FROM UnitReport;

SELECT COUNT(*) AS nonnull_vacancy_dates
FROM UnitReport
WHERE vacancy_date IS NOT NULL;

SELECT COUNT(*) AS null_vacancy_dates
FROM UnitReport
WHERE vacancy_date IS NULL;
```
