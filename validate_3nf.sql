USE RentBoardDB;

-- Basic row-count and uniqueness checks.
SELECT 'unit_record' AS check_name, COUNT(*) AS actual_count,
       550201 AS expected_count, COUNT(*) = 550201 AS passed
FROM unit_record;

SELECT 'unique_id_duplicates' AS check_name,
       COUNT(*) - COUNT(DISTINCT unique_id) AS violations,
       COUNT(*) - COUNT(DISTINCT unique_id) = 0 AS passed
FROM unit_record;

SELECT 'orphan_points' AS check_name, COUNT(*) AS violations, COUNT(*) = 0 AS passed
FROM unit_record r LEFT JOIN location_point p ON p.point_id = r.point_id
WHERE r.point_id IS NOT NULL AND p.point_id IS NULL;

SELECT 'orphan_utility_links' AS check_name, COUNT(*) AS violations, COUNT(*) = 0 AS passed
FROM record_utility_included x
LEFT JOIN unit_record r ON r.unique_id = x.unique_id
LEFT JOIN utility u ON u.utility_id = x.utility_id
WHERE r.unique_id IS NULL OR u.utility_id IS NULL;

SELECT 'orphan_history_rows' AS check_name, COUNT(*) AS violations, COUNT(*) = 0 AS passed
FROM occupancy_history h LEFT JOIN unit_record r ON r.unique_id = h.unique_id
WHERE r.unique_id IS NULL;

-- The loader records each move-in representation in exactly one form.
SELECT 'multiple_occupancy_representations' AS check_name, COUNT(*) AS violations,
       COUNT(*) = 0 AS passed
FROM unit_record
WHERE (occupancy_or_vacancy_date IS NOT NULL)
    + (occupancy_or_vacancy_year IS NOT NULL)
    + (date_unknown_reason_id IS NOT NULL)
    + (occupancy_year_raw IS NOT NULL) > 1;

-- Expected quality findings are retained rather than silently deleted.
SELECT q.code, COUNT(r.unique_id) AS affected_records
FROM quality_flag q
LEFT JOIN record_quality_flag r ON r.flag_id = q.flag_id
GROUP BY q.flag_id, q.code
ORDER BY affected_records DESC, q.code;

-- Useful evidence for the presentation.
SELECT submission_year, COUNT(*) AS records
FROM unit_record
GROUP BY submission_year
ORDER BY submission_year;

SELECT COUNT(*) AS duplicate_groups, COALESCE(SUM(member_count), 0) AS records_in_groups
FROM duplicate_group;
