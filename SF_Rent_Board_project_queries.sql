-- SF Rent Board Housing Inventory: project analysis queries
-- Run after schema_3nf.sql + load_3nf.sql.
USE RentBoardDB;

-- Q1. Number of housing-inventory records by filing year.
SELECT submission_year, COUNT(*) AS total_unit_records
FROM unit_record
GROUP BY submission_year
ORDER BY submission_year;

-- Q2. Occupancy status distribution by filing year.
SELECT r.submission_year,
       ot.name AS occupancy_type,
       COUNT(*) AS unit_records
FROM unit_record r
JOIN occupancy_type ot ON ot.occupancy_type_id = r.occupancy_type_id
GROUP BY r.submission_year, ot.name
ORDER BY r.submission_year, unit_records DESC;

-- Q3. Canonical bedroom distribution. Unparseable raw labels are excluded.
SELECT bt.bedrooms,
       COUNT(*) AS unit_records
FROM unit_record r
JOIN bedroom_type bt ON bt.bedroom_type_id = r.bedroom_type_id
WHERE bt.bedrooms IS NOT NULL
GROUP BY bt.bedrooms
ORDER BY bt.bedrooms;

-- Q4. Tenant-occupied units and approximate contract-rent midpoint by year.
-- IMPORTANT: monthly_rent is a band, not an exact rent. This uses each closed
-- band's midpoint and excludes no-rent sentinels and open-ended bands.
SELECT r.submission_year,
       COUNT(*) AS tenant_units_with_closed_rent_band,
       ROUND(AVG((rb.rent_min + rb.rent_max) / 2), 2) AS avg_band_midpoint
FROM unit_record r
JOIN occupancy_type ot ON ot.occupancy_type_id = r.occupancy_type_id
JOIN rent_band rb ON rb.rent_band_id = r.rent_band_id
WHERE ot.name = 'Occupied by non-owner'
  AND rb.is_no_rent_paid = FALSE
  AND rb.rent_min IS NOT NULL
  AND rb.rent_max IS NOT NULL
GROUP BY r.submission_year
ORDER BY r.submission_year;

-- Q5. Neighborhood-level tenant rent summary for closed rent bands.
-- Coordinates are privacy-jittered; neighborhood is suitable for aggregate
-- analysis, but the point should not be interpreted as a building location.
SELECT n.name AS neighborhood,
       COUNT(*) AS tenant_units_with_closed_rent_band,
       ROUND(AVG((rb.rent_min + rb.rent_max) / 2), 2) AS avg_band_midpoint
FROM unit_record r
JOIN occupancy_type ot ON ot.occupancy_type_id = r.occupancy_type_id
JOIN rent_band rb ON rb.rent_band_id = r.rent_band_id
JOIN location_point lp ON lp.point_id = r.point_id
JOIN neighborhood n ON n.neighborhood_id = lp.neighborhood_id
WHERE ot.name = 'Occupied by non-owner'
  AND rb.is_no_rent_paid = FALSE
  AND rb.rent_min IS NOT NULL
  AND rb.rent_max IS NOT NULL
GROUP BY n.neighborhood_id, n.name
HAVING COUNT(*) >= 100
ORDER BY avg_band_midpoint DESC, n.name;

-- Q6. Most commonly included utilities.
SELECT u.name AS utility,
       COUNT(*) AS records_including_utility,
       SUM(rui.from_checkbox = TRUE) AS reported_by_checkbox,
       SUM(rui.from_other_text = TRUE) AS found_in_other_text
FROM record_utility_included rui
JOIN utility u ON u.utility_id = rui.utility_id
GROUP BY u.utility_id, u.name
ORDER BY records_including_utility DESC, u.name;

-- Q7. Data-quality problems recorded by the cleaning pipeline.
SELECT qf.code,
       qf.description,
       COUNT(*) AS affected_records
FROM record_quality_flag rqf
JOIN quality_flag qf ON qf.flag_id = rqf.flag_id
GROUP BY qf.flag_id, qf.code, qf.description
ORDER BY affected_records DESC, qf.code;

-- Q8. Duplicate-group summary. These are tagged, not deleted, because the
-- anonymized source cannot prove whether identical filings are true duplicates.
SELECT COUNT(*) AS duplicate_groups,
       SUM(member_count) AS records_in_duplicate_groups,
       MAX(member_count) AS largest_group
FROM duplicate_group;

-- Q9. Occupancy-history rows whose reported end date precedes start date.
SELECT COUNT(*) AS reversed_history_ranges
FROM occupancy_history
WHERE is_reversed = TRUE;

-- Q10. Supervisor-district record counts by filing year.
SELECT r.submission_year,
       lp.district_id AS supervisor_district,
       COUNT(*) AS unit_records
FROM unit_record r
JOIN location_point lp ON lp.point_id = r.point_id
WHERE lp.district_id IS NOT NULL
GROUP BY r.submission_year, lp.district_id
ORDER BY r.submission_year, lp.district_id;
