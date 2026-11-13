-- JUN

USE sf_rent_board;

-- Q5 (TREND): avg rent per submission year

SELECT r.submission_year,
       COUNT((rb.min_rent + rb.max_rent) / 2)      AS reports_averaged,
       ROUND(AVG((rb.min_rent + rb.max_rent) / 2)) AS avg_rent
  FROM UnitReport r
  JOIN RentBand rb ON rb.rent_band_id = r.rent_band_id
 GROUP BY r.submission_year
 ORDER BY r.submission_year;


-- Q6 (AGGREGATION): vacancy rate per supervisor district

SELECT lp.district_id                                  AS supervisor_district,
       COUNT(*)                                        AS reports,
       SUM(ot.name = 'Vacant')                         AS vacant_reports,
       ROUND(100 * SUM(ot.name = 'Vacant') / COUNT(*), 2) AS pct_vacant
  FROM UnitReport r
  JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
  JOIN LocationPoint lp ON lp.point_id          = r.point_id
 WHERE lp.district_id IS NOT NULL
 GROUP BY lp.district_id
 ORDER BY pct_vacant DESC;


-- Q7 (JOIN): utilities most often included in base rent

SELECT u.name     AS utility,
       COUNT(*)   AS reports_including
  FROM ReportUtility ru
  JOIN Utility u ON u.utility_id = ru.utility_id
 GROUP BY u.name
 ORDER BY reports_including DESC;


-- Q8 (JOIN): avg rent by number of bedrooms

SELECT bl.canonical_bedrooms                         AS bedrooms,
       COUNT((rb.min_rent + rb.max_rent) / 2)        AS reports_averaged,
       ROUND(AVG((rb.min_rent + rb.max_rent) / 2))   AS avg_rent
  FROM UnitReport r
  JOIN BedroomLabel bl ON bl.bedroom_label_id = r.bedroom_label_id
  JOIN RentBand rb     ON rb.rent_band_id     = r.rent_band_id
 WHERE bl.canonical_bedrooms IS NOT NULL
 GROUP BY bl.canonical_bedrooms
 ORDER BY bl.canonical_bedrooms;
