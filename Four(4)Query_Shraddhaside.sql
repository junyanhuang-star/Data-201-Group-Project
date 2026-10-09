-- Q1 (JOIN): Average rent per neighborhood

SELECT n.name AS neighborhood,
       COUNT((rb.rent_min + rb.rent_max) / 2) AS reports_averaged,
       ROUND(AVG((rb.rent_min + rb.rent_max) / 2), 2) AS avg_rent
FROM unit_record r
JOIN rent_band rb
  ON rb.rent_band_id = r.rent_band_id
JOIN location_point lp
  ON lp.point_id = r.point_id
JOIN neighborhood n
  ON n.neighborhood_id = lp.neighborhood_id
WHERE rb.rent_min IS NOT NULL
  AND rb.rent_max IS NOT NULL
GROUP BY n.name
HAVING COUNT((rb.rent_min + rb.rent_max) / 2) >= 100
ORDER BY avg_rent DESC;

-- Q2 (SUBQUERY): Units vacated more than once

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

-- Q3 (AGGREGATION): Submissions by occupancy type

SELECT ot.name AS occupancy_type,
       COUNT(*) AS submissions,
       ROUND(
           100.0 * COUNT(*) /
           (SELECT COUNT(*) FROM unit_record),
           2
       ) AS pct_of_all
FROM unit_record r
JOIN occupancy_type ot
  ON ot.occupancy_type_id = r.occupancy_type_id
GROUP BY ot.name
ORDER BY submissions DESC;

-- Q4 (UNION): Districts with the highest and lowest rents

SELECT *
FROM (
    SELECT 'highest' AS rank_group,
           lp.district_id AS supervisor_district,
           ROUND(AVG((rb.rent_min + rb.rent_max) / 2), 2) AS avg_rent
    FROM unit_record r
    JOIN rent_band rb
      ON rb.rent_band_id = r.rent_band_id
    JOIN location_point lp
      ON lp.point_id = r.point_id
    WHERE lp.district_id IS NOT NULL
      AND rb.rent_min IS NOT NULL
      AND rb.rent_max IS NOT NULL
    GROUP BY lp.district_id
    ORDER BY avg_rent DESC
    LIMIT 3
) AS top3

UNION ALL

SELECT *
FROM (
    SELECT 'lowest' AS rank_group,
           lp.district_id AS supervisor_district,
           ROUND(AVG((rb.rent_min + rb.rent_max) / 2), 2) AS avg_rent
    FROM unit_record r
    JOIN rent_band rb
      ON rb.rent_band_id = r.rent_band_id
    JOIN location_point lp
      ON lp.point_id = r.point_id
    WHERE lp.district_id IS NOT NULL
      AND rb.rent_min IS NOT NULL
      AND rb.rent_max IS NOT NULL
    GROUP BY lp.district_id
    ORDER BY avg_rent ASC
    LIMIT 3
) AS bottom3;
