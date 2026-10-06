-- JUN

USE sf_rent_board;

-- Q1 (JOIN): avg rent per location

SELECT n.name                                  AS neighborhood,
       COUNT((rb.min_rent + rb.max_rent) / 2)  AS reports_averaged,  -- rows AVG uses
       ROUND(AVG((rb.min_rent + rb.max_rent) / 2)) AS avg_rent
  FROM UnitReport r
  JOIN RentBand rb      ON rb.rent_band_id   = r.rent_band_id
  JOIN LocationPoint lp ON lp.point_id       = r.point_id
  JOIN Neighborhood n   ON n.neighborhood_id = lp.neighborhood_id
 GROUP BY n.name
HAVING COUNT((rb.min_rent + rb.max_rent) / 2) >= 100   -- hide tiny groups
 ORDER BY avg_rent DESC;

-- Q2 (SUBQUERY): units vacated more than once

SELECT r.unique_id,
       r.submission_year,
       r.vacancy_date
  FROM UnitReport r
 WHERE r.vacancy_date IS NOT NULL
   AND r.unique_id IN (SELECT h.unique_id
                         FROM OccupancyHistory h
                        WHERE LOWER(h.range_type) = 'vacant'
                          AND h.end_date < r.vacancy_date)
 ORDER BY r.submission_year, r.vacancy_date;


-- Q3 (AGGREGATION): submissions by occupancy type
SELECT ot.name                                    AS occupancy_type,
       COUNT(*)                                   AS submissions,
       ROUND(100 * COUNT(*) / (SELECT COUNT(*) FROM UnitReport), 2)
                                                  AS pct_of_all
  FROM UnitReport r
  JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
 GROUP BY ot.name
 ORDER BY submissions DESC;


-- Q4 (UNION): districts with the highest and lowest rents
SELECT * FROM (
    SELECT 'highest'                                   AS rank_group,
           lp.district_id                              AS supervisor_district,
           ROUND(AVG((rb.min_rent + rb.max_rent) / 2)) AS avg_rent
      FROM UnitReport r
      JOIN RentBand rb      ON rb.rent_band_id = r.rent_band_id
      JOIN LocationPoint lp ON lp.point_id     = r.point_id
     WHERE lp.district_id IS NOT NULL
     GROUP BY lp.district_id
     ORDER BY avg_rent DESC
     LIMIT 3) AS top3
UNION ALL
SELECT * FROM (
    SELECT 'lowest',
           lp.district_id,
           ROUND(AVG((rb.min_rent + rb.max_rent) / 2)) AS avg_rent
      FROM UnitReport r
      JOIN RentBand rb      ON rb.rent_band_id = r.rent_band_id
      JOIN LocationPoint lp ON lp.point_id     = r.point_id
     WHERE lp.district_id IS NOT NULL
     GROUP BY lp.district_id
     ORDER BY avg_rent ASC
     LIMIT 3) AS bottom3;
