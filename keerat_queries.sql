-- ============================================================================
-- Keerat Khandpur: Initial SQL exploration
-- Topic: UTILITIES INCLUDED IN BASE RENT (tables Utility + ReportUtility)
-- Schema: main branch, own_implementation/schema.sql (database sf_rent_board)
--
-- Background: the raw CSV had five columns (base_rent_includes_*). In 3NF they
-- became Utility (one row per utility) and ReportUtility (one row per report
-- that includes a utility: a many-to-many junction between UnitReport and Utility).
-- Utilities only matter for rented units, so most queries look at
-- tenant-occupied reports ("Occupied by non-owner").
-- ============================================================================
USE sf_rent_board;

-- ----------------------------------------------------------------------------
-- BASIC 1: Which utilities are most often included in tenants' base rent?
-- Concepts: JOIN, WHERE filter, GROUP BY, aggregation
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
-- BASIC 2: Where did each utility claim come from: the checkbox or the
-- free-text "other utilities" box?
-- Concepts: JOIN, GROUP BY, conditional SUM
-- ----------------------------------------------------------------------------
SELECT u.name                    AS utility,
       COUNT(*)                  AS total_rows,
       SUM(ru.source_checkbox)   AS from_checkbox,
       SUM(ru.source_text)       AS from_free_text,
       SUM(ru.source_checkbox AND ru.source_text) AS from_both
FROM ReportUtility ru
JOIN Utility u ON u.utility_id = ru.utility_id
GROUP BY u.utility_id, u.name
ORDER BY total_rows DESC;

-- ----------------------------------------------------------------------------
-- ADVANCED 1: Do tenants whose rent includes more utilities report higher rent?
-- Concepts: CTE, LEFT JOIN (to keep reports with zero utilities),
--           multi-table join (UnitReport, OccupancyType, ReportUtility, RentBand)
-- Note: rent is a $250 band, so we use the band midpoint as an ESTIMATE and
-- skip "no rent paid" and open-ended ($7000+) bands.
-- ----------------------------------------------------------------------------
WITH tenant_utilities AS (
    SELECT r.unique_id,
           r.rent_band_id,
           COUNT(ru.utility_id) AS n_utilities          -- 0 when no ReportUtility rows
    FROM UnitReport r
    JOIN OccupancyType ot     ON ot.occupancy_type_id = r.occupancy_type_id
    LEFT JOIN ReportUtility ru ON ru.unique_id = r.unique_id
    WHERE ot.name = 'Occupied by non-owner'
    GROUP BY r.unique_id, r.rent_band_id
)
SELECT tu.n_utilities,
       COUNT(*)                                        AS tenant_reports,
       ROUND(AVG((rb.min_rent + rb.max_rent) / 2), 0)  AS avg_rent_midpoint
FROM tenant_utilities tu
JOIN RentBand rb ON rb.rent_band_id = tu.rent_band_id
WHERE rb.is_no_rent_paid = FALSE
  AND rb.min_rent IS NOT NULL
  AND rb.max_rent IS NOT NULL
GROUP BY tu.n_utilities
ORDER BY tu.n_utilities;

-- ----------------------------------------------------------------------------
-- ADVANCED 2: For each utility, which supervisor districts include it most
-- often in tenants' rent?
-- Concepts: CTEs, window function RANK() OVER (PARTITION BY ...),
--           join through LocationPoint to get the district
-- ----------------------------------------------------------------------------
WITH tenant_reports AS (                 -- tenant reports per district
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
district_utility AS (                    -- % of tenant reports including each utility
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
-- EXTRA (for the final; need 5 advanced): Are utilities included more often in
-- older buildings?
-- Concepts: VIEW, CASE expression, conditional aggregation
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW tenant_utility_flags AS
SELECT r.unique_id,
       CASE WHEN r.year_property_built <  1940 THEN '1) before 1940'
            WHEN r.year_property_built <  1980 THEN '2) 1940-1979'
            WHEN r.year_property_built >= 1980 THEN '3) 1980 or later'
            ELSE '4) unknown' END                                    AS building_era,
       MAX(u.name = 'water_sewer')      AS has_water_sewer,
       MAX(u.name = 'refuse_recycling') AS has_refuse,
       MAX(u.name = 'natural_gas')      AS has_gas,
       MAX(u.name = 'electricity')      AS has_electricity,
       MAX(u.name = 'heat')             AS has_heat
FROM UnitReport r
JOIN OccupancyType ot      ON ot.occupancy_type_id = r.occupancy_type_id
LEFT JOIN ReportUtility ru ON ru.unique_id = r.unique_id
LEFT JOIN Utility u        ON u.utility_id = ru.utility_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY r.unique_id, building_era;

SELECT building_era,
       COUNT(*)                                   AS tenant_reports,
       ROUND(100 * AVG(COALESCE(has_water_sewer, 0)), 1) AS pct_water_sewer,
       ROUND(100 * AVG(COALESCE(has_refuse, 0)), 1)      AS pct_refuse,
       ROUND(100 * AVG(COALESCE(has_gas, 0)), 1)         AS pct_gas,
       ROUND(100 * AVG(COALESCE(has_electricity, 0)), 1) AS pct_electricity,
       ROUND(100 * AVG(COALESCE(has_heat, 0)), 1)        AS pct_heat
FROM tenant_utility_flags
GROUP BY building_era
ORDER BY building_era;
