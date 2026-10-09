


### Basic Query 1: Records by filing year


USE RentBoardDB;

SELECT submission_year,
       COUNT(*) AS total_unit_records
FROM unit_record
GROUP BY submission_year
ORDER BY submission_year;


### Basic Query 2: Occupancy type distribution


SELECT ot.name AS occupancy_type,
       COUNT(*) AS unit_records
FROM unit_record r
JOIN occupancy_type ot
  ON ot.occupancy_type_id = r.occupancy_type_id
GROUP BY ot.name
ORDER BY unit_records DESC;


### Advanced Query 1: Average rent by neighborhood


SELECT COALESCE(n.name, 'Unknown neighborhood') AS neighborhood,
       COUNT(*) AS reports_averaged,
       ROUND(AVG((rb.rent_min + rb.rent_max) / 2), 2) AS avg_rent
FROM unit_record r
JOIN rent_band rb
  ON rb.rent_band_id = r.rent_band_id
LEFT JOIN location_point lp
  ON lp.point_id = r.point_id
LEFT JOIN neighborhood n
  ON n.neighborhood_id = lp.neighborhood_id
WHERE rb.rent_min IS NOT NULL
  AND rb.rent_max IS NOT NULL
GROUP BY COALESCE(n.name, 'Unknown neighborhood')
ORDER BY avg_rent DESC;


### Advanced Query 2: Units vacated more than once


SELECT r.unique_id,
       r.submission_year,
       r.vacancy_date
FROM unit_record r
WHERE r.vacancy_date IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM occupancy_history h
      JOIN date_range_type drt
        ON drt.date_range_type_id = h.date_range_type_id
      WHERE h.unique_id = r.unique_id
        AND LOWER(drt.name) = 'vacant'
        AND h.end_date < r.vacancy_date
  )
ORDER BY r.submission_year,
         r.vacancy_date;
