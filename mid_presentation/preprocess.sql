USE sf_rent_board;

-- Python performs preprocessing. This SQL file only loads the cleaned files
-- produced by clean_inventory.py. It intentionally contains no regex mappings.
--
-- python clean_inventory.py \
--   --source /path/to/Rent_Board_Housing_Inventory.csv.gz \
--   --output-dir /path/to/cleaned

-- Import lookup CSVs first, then UnitReport, then the child/junction files.
-- Keep quality_issue.csv so every discarded or unparseable value remains
-- auditable. The generated lookup IDs must match the foreign keys in the load.

-- Example loading pattern:
-- LOAD DATA LOCAL INFILE '/path/to/cleaned/unit_report_clean.csv'
-- INTO TABLE UnitReport
-- FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
-- LINES TERMINATED BY '\n' IGNORE 1 LINES (...);

-- Do not put category cleanup in this file. That logic belongs in
-- clean_inventory.py, where it can be tested and rerun outside MySQL.
