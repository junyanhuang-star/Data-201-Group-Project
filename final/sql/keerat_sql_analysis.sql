-- ============================================================================
-- Keerat Khandpur: SQL analysis (final project)
-- Topic: UTILITIES INCLUDED IN BASE RENT  (Utility + ReportUtility)
-- Database: sf_rent_board, built from final/database/schema.sql + load_3nf.py
--           on the team CSV Rent_Board_Housing_Inventory_20261001.csv
--
-- Background: the raw CSV had five base_rent_includes_* columns. In 3NF they
-- became Utility (one row per kind of utility) and ReportUtility, a junction
-- table with one row per (report, included utility): a many-to-many link
-- between UnitReport and Utility. Utilities only matter for rented units, so
-- most queries keep tenant-occupied reports ('Occupied by non-owner').
--
--   #  Type      Category               Question
--   1  Basic     JOIN + GROUP BY        Which utilities are most often included?
--   2  Basic     JOIN + conditional SUM Did each claim come from the checkbox or free text?
--   3  Advanced  CTE + LEFT JOIN        Do more included utilities go with higher rent?
--   4  Advanced  Window function        Which districts include each utility most?
--   5  Advanced  VIEW + CASE            Are utilities included more in older buildings?
--   6  Advanced  Subquery               Which neighborhoods beat the citywide water/sewer rate?
--   7  Advanced  Index + EXPLAIN        Does a composite index speed up tenant/rent lookups?
-- ============================================================================
USE sf_rent_board;

-- ----------------------------------------------------------------------------
-- Q1 (BASIC): Which utilities are most often included in tenants' base rent?
-- Concepts: 4-table JOIN, WHERE, GROUP BY, COUNT
-- ----------------------------------------------------------------------------
SELECT u.name                                   AS utility,
       COUNT(*)                                 AS tenant_reports_including_it,
       ROUND(100 * COUNT(*) /
             (SELECT COUNT(*) FROM UnitReport r2
              JOIN OccupancyType o2 ON o2.occupancy_type_id = r2.occupancy_type_id
              WHERE o2.name = 'Occupied by non-owner'), 1) AS pct_of_tenant_reports
FROM ReportUtility ru
JOIN Utility u        ON u.utility_id = ru.utility_id
JOIN UnitReport r     ON r.unique_id = ru.unique_id
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY u.utility_id, u.name
ORDER BY tenant_reports_including_it DESC;

-- ----------------------------------------------------------------------------
-- Q2 (BASIC): Where did each utility claim come from: the checkbox or the
-- free-text "other utilities" box?
-- Concepts: JOIN, GROUP BY, conditional SUM
-- ----------------------------------------------------------------------------
SELECT u.name                                     AS utility,
       COUNT(*)                                   AS total_rows,
       SUM(ru.source_checkbox)                    AS from_checkbox,
       SUM(ru.source_text)                        AS from_free_text,
       SUM(ru.source_checkbox AND ru.source_text) AS from_both
FROM ReportUtility ru
JOIN Utility u ON u.utility_id = ru.utility_id
GROUP BY u.utility_id, u.name
ORDER BY total_rows DESC;

-- ----------------------------------------------------------------------------
-- Q3 (ADVANCED - CTE): Do tenants whose rent includes more utilities report
-- higher rent?
-- Concepts: CTE, LEFT JOIN (keeps reports with zero utilities), 4-table join
-- Rent is a $250 band, so the band midpoint is an ESTIMATE; "no rent paid"
-- and the open-ended $7000+ band are excluded.
-- ----------------------------------------------------------------------------
WITH tenant_utilities AS (
    SELECT r.unique_id,
           r.rent_band_id,
           COUNT(ru.utility_id) AS n_utilities          -- 0 when no ReportUtility rows
    FROM UnitReport r
    JOIN OccupancyType ot      ON ot.occupancy_type_id = r.occupancy_type_id
    LEFT JOIN ReportUtility ru ON ru.unique_id = r.unique_id
    WHERE ot.name = 'Occupied by non-owner'
    GROUP BY r.unique_id, r.rent_band_id
)
SELECT tu.n_utilities,
       COUNT(*)                                        AS tenant_reports,
       ROUND(AVG((rb.min_rent + rb.max_rent) / 2), 0)  AS avg_rent_midpoint
FROM tenant_utilities tu
JOIN RentBand rb ON rb.rent_band_id = tu.rent_band_id
WHERE rb.min_rent IS NOT NULL      -- NULL for "no rent paid" bands
  AND rb.max_rent IS NOT NULL      -- NULL for the open-ended $7000+ band
GROUP BY tu.n_utilities
ORDER BY tu.n_utilities;

-- ----------------------------------------------------------------------------
-- Q4 (ADVANCED - WINDOW FUNCTION): For each utility, which supervisor
-- districts include it most often in tenants' rent?
-- Concepts: CTEs, RANK() OVER (PARTITION BY ...), join through LocationPoint
-- ----------------------------------------------------------------------------
WITH tenant_reports AS (
    SELECT r.unique_id, lp.district_id
    FROM UnitReport r
    JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
    JOIN LocationPoint lp ON lp.point_id = r.point_id
    WHERE ot.name = 'Occupied by non-owner'
      AND lp.district_id IS NOT NULL
),
district_totals AS (
    SELECT district_id, COUNT(*) AS n_tenant_reports
    FROM tenant_reports
    GROUP BY district_id
),
district_utility AS (
    SELECT u.name AS utility,
           tr.district_id,
           ROUND(100 * COUNT(*) / dt.n_tenant_reports, 1) AS pct_including
    FROM tenant_reports tr
    JOIN ReportUtility ru   ON ru.unique_id = tr.unique_id
    JOIN Utility u          ON u.utility_id = ru.utility_id
    JOIN district_totals dt ON dt.district_id = tr.district_id
    WHERE u.name IN ('water_sewer', 'refuse_recycling', 'natural_gas', 'electricity', 'heat')
    GROUP BY u.name, tr.district_id, dt.n_tenant_reports
)
SELECT utility, district_id, pct_including, district_rank
FROM (
    SELECT du.*,
           RANK() OVER (PARTITION BY utility ORDER BY pct_including DESC) AS district_rank
    FROM district_utility du
) ranked
WHERE district_rank <= 3
ORDER BY utility, district_rank;

-- ----------------------------------------------------------------------------
-- Q5 (ADVANCED - VIEW): Are utilities included more often in older buildings?
-- Concepts: CREATE VIEW, CASE, LEFT JOIN, conditional aggregation
-- The view gives one row per tenant report with yes/no utility flags, so any
-- later query (or the dashboard) can reuse it.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_keerat_tenant_utilities AS
SELECT r.unique_id,
       CASE WHEN r.year_property_built <  1940 THEN '1) before 1940'
            WHEN r.year_property_built <  1980 THEN '2) 1940-1979'
            WHEN r.year_property_built >= 1980 THEN '3) 1980 or later'
            ELSE '4) unknown' END                         AS building_era,
       COALESCE(MAX(u.name = 'water_sewer'), 0)          AS has_water_sewer,
       COALESCE(MAX(u.name = 'refuse_recycling'), 0)     AS has_refuse,
       COALESCE(MAX(u.name = 'natural_gas'), 0)          AS has_gas,
       COALESCE(MAX(u.name = 'electricity'), 0)          AS has_electricity,
       COALESCE(MAX(u.name = 'heat'), 0)                 AS has_heat
FROM UnitReport r
JOIN OccupancyType ot      ON ot.occupancy_type_id = r.occupancy_type_id
LEFT JOIN ReportUtility ru ON ru.unique_id = r.unique_id
LEFT JOIN Utility u        ON u.utility_id = ru.utility_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY r.unique_id, building_era;

SELECT building_era,
       COUNT(*)                              AS tenant_reports,
       ROUND(100 * AVG(has_water_sewer), 1)  AS pct_water_sewer,
       ROUND(100 * AVG(has_refuse), 1)       AS pct_refuse,
       ROUND(100 * AVG(has_gas), 1)          AS pct_gas,
       ROUND(100 * AVG(has_electricity), 1)  AS pct_electricity,
       ROUND(100 * AVG(has_heat), 1)         AS pct_heat
FROM v_keerat_tenant_utilities
GROUP BY building_era
ORDER BY building_era;

-- ----------------------------------------------------------------------------
-- Q6 (ADVANCED - SUBQUERY): Which neighborhoods include water & sewer in
-- tenants' rent MORE often than the citywide rate?
-- Concepts: scalar subqueries (citywide rate, utility id), HAVING compared to
-- a subquery, LEFT JOIN with an extra condition in ON
-- ----------------------------------------------------------------------------
SELECT n.name                                         AS neighborhood,
       COUNT(*)                                       AS tenant_reports,
       ROUND(100 * AVG(ru.unique_id IS NOT NULL), 1)  AS pct_water_sewer
FROM UnitReport r
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
JOIN LocationPoint lp ON lp.point_id = r.point_id
JOIN Neighborhood n   ON n.neighborhood_id = lp.neighborhood_id
LEFT JOIN ReportUtility ru
       ON ru.unique_id = r.unique_id
      AND ru.utility_id = (SELECT utility_id FROM Utility WHERE name = 'water_sewer')
WHERE ot.name = 'Occupied by non-owner'
GROUP BY n.neighborhood_id, n.name
HAVING COUNT(*) >= 1000                                   -- skip tiny neighborhoods
   AND AVG(ru.unique_id IS NOT NULL) >
       ( SELECT COUNT(*)                                  -- citywide: tenant reports with water/sewer
         FROM ReportUtility ru2
         JOIN Utility u2       ON u2.utility_id = ru2.utility_id
         JOIN UnitReport r2    ON r2.unique_id = ru2.unique_id
         JOIN OccupancyType o2 ON o2.occupancy_type_id = r2.occupancy_type_id
         WHERE u2.name = 'water_sewer' AND o2.name = 'Occupied by non-owner' )
       /
       ( SELECT COUNT(*)                                  -- ... divided by all tenant reports
         FROM UnitReport r3
         JOIN OccupancyType o3 ON o3.occupancy_type_id = r3.occupancy_type_id
         WHERE o3.name = 'Occupied by non-owner' )
ORDER BY pct_water_sewer DESC;

-- ----------------------------------------------------------------------------
-- Q7 (ADVANCED - INDEXING / EXPLAIN): Does a composite index speed up
-- "tenant reports per rent band", the lookup behind Q3?
-- Run each EXPLAIN ANALYZE and compare the plan and "actual time".
-- ----------------------------------------------------------------------------
-- BEFORE: MySQL uses the single-column foreign-key index on occupancy_type_id,
-- then must read every matching row from the table to get rent_band_id.
EXPLAIN ANALYZE
SELECT r.rent_band_id, COUNT(*) AS tenant_reports
FROM UnitReport r
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY r.rent_band_id;

-- A composite index on (occupancy_type_id, rent_band_id) holds both columns,
-- so the query can be answered from the index alone (a "covering index"),
-- already sorted by rent_band_id within each occupancy type.
CREATE INDEX idx_keerat_occtype_rentband ON UnitReport (occupancy_type_id, rent_band_id);

-- AFTER
EXPLAIN ANALYZE
SELECT r.rent_band_id, COUNT(*) AS tenant_reports
FROM UnitReport r
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY r.rent_band_id;

-- To undo: DROP INDEX idx_keerat_occtype_rentband ON UnitReport;
-- If that fails with error 1553 ("needed in a foreign key constraint"), MySQL
-- removed its automatic occupancy_type_id index (the new one starts with the
-- same column and now backs the foreign key). Recreate it first:
-- CREATE INDEX occupancy_type_id ON UnitReport (occupancy_type_id);
