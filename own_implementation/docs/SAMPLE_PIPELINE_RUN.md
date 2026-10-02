# 100-Row Sample Pipeline Run

This document records the commands and results used to create and load the
small discussion sample. It is a reproducible reference for the team, not a
replacement for rerunning the workflow against the full CSV.

## Source and sample size

The source was:

```text
/Users/aduques/Downloads/Rent_Board_Housing_Inventory_20260927.csv
```

From the repository root, the first 100 data rows were copied with Python's
CSV parser so quoted fields and embedded commas remained valid:

```bash
cd "/Users/aduques/DATA 201/Data-201-Group-Project"

python3 -c 'import csv; src="/Users/aduques/Downloads/Rent_Board_Housing_Inventory_20260927.csv"; dst="own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv"; csv.field_size_limit(10**9); f=open(src,encoding="utf-8-sig",newline=""); out=open(dst,"w",encoding="utf-8",newline=""); reader=csv.reader(f); writer=csv.writer(out); writer.writerow(next(reader)); [writer.writerow(row) for _,row in zip(range(100),reader)]; out.close(); f.close()'
```

The sample size was checked with:

```bash
python3 -c 'import csv; p="own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv"; f=open(p,encoding="utf-8-sig",newline=""); print(sum(1 for _ in csv.DictReader(f))); f.close()'
```

Output:

```text
100
```

For this sample specifically, the source contains 99 blank `vacancy_date`
values and 1 populated `vacancy_date` value. Missing dates should appear as
SQL `NULL` in `UnitReport`, not as `0000-00-00`.

## Python preprocessing output

```bash
python3 own_implementation/clean_inventory.py \
  --source own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv \
  --output-dir own_implementation/generated/sample_cleaned
```

Output:

```text
{'rows_in': 100, 'rows_out': 100, 'history_rows': 13, 'utility_rows': 118, 'quality_issues': 0, 'output_dir': 'own_implementation/generated/sample_cleaned'}
```

The cleaned CSV files are in `own_implementation/generated/sample_cleaned/`.

## Loader output

```bash
python3 own_implementation/load_3nf.py \
  --source own_implementation/generated/Rent_Board_Housing_Inventory_sample_100.csv \
  --output-dir own_implementation/generated/sample_load
```

Output:

```text
{
  "source_rows": 100,
  "reports": 100,
  "history_rows": 13,
  "utility_rows": 118,
  "quality_issues": 0,
  "output_dir": "own_implementation/generated/sample_load"
}
```

The generated files are:

```text
own_implementation/generated/sample_load/load_3nf.sql
own_implementation/generated/sample_load/staging/*.tsv
```

The generated SQL begins with `USE sf_rent_board;` and loads the staging files
in foreign-key order. The staging writer represents SQL `NULL` as unquoted
`\N` and quotes non-null values.

## MySQL Workbench steps

1. Run `own_implementation/schema.sql` in Workbench. This creates the database,
   tables, constraints, and seeded lookup rows.
2. Confirm that local loading is enabled on the MySQL server and Workbench
   connection.
3. Open and run the complete generated file:

   ```text
   own_implementation/generated/sample_load/load_3nf.sql
   ```

4. Run `own_implementation/validation.sql`.

The validation run showed successful execution of `USE sf_rent_board`, a
returned row-count result, zero orphan rows for the foreign-key checks, and
zero rows for the filing-cycle and location dependency checks. The final
analysis query returned grouped report counts by submission year and
occupancy type.

## Viewing every populated table

The bottom section of `validation.sql` contains a `SELECT * ... LIMIT 100`
statement for every table:

```sql
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

Workbench displays each query's result as a separate result tab. `QualityIssue`
may return zero rows for this particular 100-row sample; that is a valid result
and does not mean the table was omitted.

## Troubleshooting recorded during the run

- Error 3948 indicated that `LOAD DATA LOCAL INFILE` was disabled. The server
  variable was enabled with `SET GLOBAL local_infile = 1`, and the Workbench
  connection was configured with `OPT_LOCAL_INFILE=1` under its Advanced
  connection settings.
- Error 1046 indicated that no database was selected. The loader generator was
  updated to include `USE sf_rent_board;`.
- The first generated loader produced warnings because the staging `\N` null
  token was escaped incorrectly. The staging writer and generated `LOAD DATA`
  escape configuration were corrected, and the sample loader was regenerated.

After a failed or partially completed load, rerun `schema.sql` before trying
the loader again because `schema.sql` recreates the sample database from an
empty state.

After a successful reload, these checks should show the expected result:

```sql
SELECT COUNT(*) AS total_reports FROM UnitReport;
SELECT COUNT(*) AS nonnull_vacancy_dates
FROM UnitReport
WHERE vacancy_date IS NOT NULL;
SELECT COUNT(*) AS null_vacancy_dates
FROM UnitReport
WHERE vacancy_date IS NULL;
```

For this 100-row sample, the expected values are 100 total reports, 1
non-null vacancy date, and 99 null vacancy dates. If `UnitReport` returns only
85 rows or vacancy dates appear as `0000-00-00`, reset the database with
`schema.sql` and rerun the regenerated loader from the beginning.
