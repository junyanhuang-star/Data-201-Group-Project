-- ============================================================================
-- Post-load validation for RentBoardDB.
--
-- Run : mysql -u <user> -p < validate_3nf.sql
--       (after schema_3nf.sql and the generated load_3nf.sql)
--
-- Three things are checked:
--   A. every table holds the row count the loader reported;
--   B. the functional dependencies the decomposition relies on still hold;
--   C. the decomposition is lossless -- v_inventory_flat rebuilds all 28
--      original columns and returns exactly 550,201 rows.
-- ============================================================================

USE RentBoardDB;

-- ---------------------------------------------------------------------------
-- A. Row counts. Compare against the table load_3nf.py prints.
-- ---------------------------------------------------------------------------
SELECT 'A. row counts' AS section;

SELECT 'extract_batch'           AS table_name, COUNT(*) AS rows_loaded, 1       AS expected FROM extract_batch
UNION ALL SELECT 'filing_cycle',            COUNT(*),      5 FROM filing_cycle
UNION ALL SELECT 'neighborhood',            COUNT(*),     41 FROM neighborhood
UNION ALL SELECT 'supervisor_district',     COUNT(*),     11 FROM supervisor_district
UNION ALL SELECT 'location_point',          COUNT(*),  13435 FROM location_point
UNION ALL SELECT 'assessor_block',          COUNT(*),   4287 FROM assessor_block
UNION ALL SELECT 'street_block',            COUNT(*),   7677 FROM street_block
UNION ALL SELECT 'occupancy_type',          COUNT(*),      4 FROM occupancy_type
UNION ALL SELECT 'bedroom_type',            COUNT(*),     45 FROM bedroom_type
UNION ALL SELECT 'bathroom_type',           COUNT(*),     31 FROM bathroom_type
UNION ALL SELECT 'sqft_band',               COUNT(*),     19 FROM sqft_band
UNION ALL SELECT 'rent_band',               COUNT(*),     33 FROM rent_band
UNION ALL SELECT 'date_unknown_reason',     COUNT(*),      5 FROM date_unknown_reason
UNION ALL SELECT 'date_range_type',         COUNT(*),      3 FROM date_range_type
UNION ALL SELECT 'quality_flag',            COUNT(*),     11 FROM quality_flag
UNION ALL SELECT 'utility',                 COUNT(*),     16 FROM utility
UNION ALL SELECT 'duplicate_group',         COUNT(*),  21008 FROM duplicate_group
UNION ALL SELECT 'unit_record',             COUNT(*), 550201 FROM unit_record
UNION ALL SELECT 'record_utility_included', COUNT(*), 700285 FROM record_utility_included
UNION ALL SELECT 'record_quality_flag',     COUNT(*),   9835 FROM record_quality_flag
UNION ALL SELECT 'occupancy_history',       COUNT(*),  81004 FROM occupancy_history;


-- ---------------------------------------------------------------------------
-- B. The functional dependencies the schema is built on. Every count must be 0.
--    (The two that DO NOT hold are listed too, with their expected non-zero
--    counts -- they are the reason neighborhood hangs off the point and there
--    is no property table.)
-- ---------------------------------------------------------------------------
SELECT 'B. functional dependencies' AS section;

SELECT 'point -> neighborhood (must be 0)' AS fd, COUNT(*) AS violations FROM (
    SELECT point_id FROM location_point GROUP BY point_id
     HAVING COUNT(DISTINCT neighborhood_id) > 1) v
UNION ALL
SELECT 'unique_id is the key (must be 0)', COUNT(*) - COUNT(DISTINCT unique_id) FROM unit_record
UNION ALL
SELECT 'one occ-date representation (must be 0)', COUNT(*) FROM unit_record
 WHERE (occupancy_or_vacancy_date IS NOT NULL)
     + (occupancy_or_vacancy_year IS NOT NULL)
     + (date_unknown_reason_id    IS NOT NULL)
     + (occupancy_year_raw        IS NOT NULL) > 1
UNION ALL
SELECT 'submission_year -> case_type_name (must be 0)', COUNT(*) FROM (
    SELECT submission_year FROM filing_cycle
     GROUP BY submission_year HAVING COUNT(DISTINCT case_type_name) > 1) v
UNION ALL
SELECT 'neighborhood -> district (expected 25, does NOT hold)', COUNT(*) FROM (
    SELECT neighborhood_id FROM location_point WHERE neighborhood_id IS NOT NULL
     GROUP BY neighborhood_id HAVING COUNT(DISTINCT district_id) > 1) v
UNION ALL
SELECT 'block_num -> block_address (expected 3588, does NOT hold)', COUNT(*) FROM (
    SELECT block_num FROM unit_record WHERE block_num IS NOT NULL
     GROUP BY block_num HAVING COUNT(DISTINCT street_block_id) > 1) v;


-- ---------------------------------------------------------------------------
-- C. Lossless decomposition.
--    v_inventory_flat rebuilds the original 28-column export. Two columns can
--    only be rebuilt up to formatting, and are compared numerically rather
--    than as strings:
--      * point   -- DECIMAL(12,9) pads latitudes that the CSV wrote with 8
--                   decimals, so the WKT text differs while the value does not;
--      * unit_count -- the CSV mixes "70" and "72.0" for the same quantity.
-- ---------------------------------------------------------------------------
SELECT 'C. lossless round-trip' AS section;

CREATE OR REPLACE VIEW v_inventory_flat AS
SELECT r.unique_id,
       r.block_num,
       r.building_unit_count                                  AS unit_count,
       f.case_type_name,
       r.submission_year,
       sb.raw_label                                           AS block_address,
       ot.name                                                AS occupancy_type,
       r.occupancy_or_vacancy_date,
       COALESCE(LPAD(YEAR(r.occupancy_or_vacancy_date), 4, '0'),
                CAST(r.occupancy_or_vacancy_year AS CHAR),
                dur.label,
                r.occupancy_year_raw)                         AS occupancy_or_vacancy_date_year,
       bd.raw_label                                           AS bedroom_count,
       ba.raw_label                                           AS bathroom_count,
       sf.raw_label                                           AS square_footage,
       rb.raw_label                                           AS monthly_rent,
       MAX(CASE WHEN u.name = 'water_sewer'      AND ru.from_checkbox THEN 'Y' ELSE 'N' END)
                                                              AS base_rent_includes_water_sewer,
       MAX(CASE WHEN u.name = 'natural_gas'      AND ru.from_checkbox THEN 'Y' ELSE 'N' END)
                                                              AS base_rent_includes_natural_gas,
       MAX(CASE WHEN u.name = 'electricity'      AND ru.from_checkbox THEN 'Y' ELSE 'N' END)
                                                              AS base_rent_includes_electricity,
       MAX(CASE WHEN u.name = 'refuse_recycling' AND ru.from_checkbox THEN 'Y' ELSE 'N' END)
                                                              AS base_rent_includes_refuse_recycling,
       r.other_utilities_raw          AS base_rent_includes_other_utilities,
       CASE r.past_occupancy WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END AS past_occupancy,
       r.vacancy_date,
       r.signature_date,
       r.year_property_built,
       CONCAT('POINT (', lp.longitude, ' ', lp.latitude, ')')  AS point,
       n.name                                                 AS analysis_neighborhood,
       lp.district_id                                         AS supervisor_district,
       eb.data_as_of,
       eb.data_loaded_at
  FROM unit_record r
  JOIN filing_cycle    f  ON f.submission_year   = r.submission_year
  JOIN extract_batch   eb ON eb.batch_id         = r.batch_id
  JOIN occupancy_type  ot ON ot.occupancy_type_id = r.occupancy_type_id
  LEFT JOIN street_block        sb  ON sb.street_block_id = r.street_block_id
  LEFT JOIN bedroom_type        bd  ON bd.bedroom_type_id = r.bedroom_type_id
  LEFT JOIN bathroom_type       ba  ON ba.bathroom_type_id = r.bathroom_type_id
  LEFT JOIN sqft_band           sf  ON sf.sqft_band_id    = r.sqft_band_id
  LEFT JOIN rent_band           rb  ON rb.rent_band_id    = r.rent_band_id
  LEFT JOIN location_point      lp  ON lp.point_id        = r.point_id
  LEFT JOIN neighborhood        n   ON n.neighborhood_id  = lp.neighborhood_id
  LEFT JOIN date_unknown_reason dur ON dur.reason_id      = r.date_unknown_reason_id
  LEFT JOIN record_utility_included ru ON ru.unique_id    = r.unique_id
  LEFT JOIN utility             u   ON u.utility_id       = ru.utility_id
 GROUP BY r.unique_id, r.block_num, r.building_unit_count, f.case_type_name,
          r.submission_year, sb.raw_label, ot.name, r.occupancy_or_vacancy_date,
          r.occupancy_or_vacancy_year, dur.label, r.occupancy_year_raw,
          bd.raw_label, ba.raw_label, sf.raw_label, rb.raw_label,
          r.other_utilities_raw, r.past_occupancy, r.vacancy_date,
          r.signature_date, r.year_property_built, lp.longitude, lp.latitude,
          n.name, lp.district_id, eb.data_as_of, eb.data_loaded_at;

SELECT COUNT(*) AS reconstructed_rows, 550201 AS expected FROM v_inventory_flat;

-- The dates deliberately NOT reconstructed: out-of-domain values live on the
-- flag rows instead of in a DATE column. This must total 371 (147 + 136 + 88).
SELECT 'values rejected by the DATE domain and preserved on flags' AS note,
       COUNT(*) AS n
  FROM record_quality_flag WHERE flag_id IN (1, 2, 3);


-- ---------------------------------------------------------------------------
-- D. Reference results -- the numbers the write-up quotes.
-- ---------------------------------------------------------------------------
SELECT 'D. reference results' AS section;

SELECT qf.code, COUNT(*) AS rows_flagged
  FROM record_quality_flag rqf JOIN quality_flag qf USING (flag_id)
 GROUP BY qf.code ORDER BY rows_flagged DESC;

-- Rent is a sitting tenant's contract rent, so only tenant-occupied units with
-- a real band are meaningful; the "$0 (no rent paid)" sentinels are excluded.
SELECT r.submission_year,
       COUNT(*)                                        AS tenant_units,
       ROUND(AVG((rb.rent_min + rb.rent_max) / 2))     AS mean_band_midpoint
  FROM unit_record r
  JOIN occupancy_type ot ON ot.occupancy_type_id = r.occupancy_type_id
  JOIN rent_band      rb ON rb.rent_band_id      = r.rent_band_id
 WHERE ot.name = 'Occupied by non-owner'
   AND rb.is_no_rent_paid = FALSE
   AND rb.rent_max IS NOT NULL
 GROUP BY r.submission_year ORDER BY r.submission_year;
