-- ============================================================================
-- DATA 201 Final Project - SQL Analysis
-- Member: Shraddha Patel
-- Database: sf_rent_board (final/database/schema.sql, loaded with load_3nf.py)
--
-- Domain question:
--   Where in San Francisco are rental units vacant or occupied, how has that
--   changed across filing years, and how does rent differ by area?
--
-- Tables used: UnitReport, OccupancyType, OccupancyHistory, FilingCycle,
--              LocationPoint, Neighborhood, RentBand
--
-- Queries: 2 basic + 5 advanced
--   Q1 Basic       filings per year
--   Q2 Basic       occupancy type share
--   Q3 CTE         neighborhood rent vs. citywide average (4-table join)
--   Q4 Subquery    repeat vacancies per neighborhood (EXISTS)
--   Q5 Window      vacancy rank inside each district + year-over-year change
--   Q6 View        v_shraddha_occupancy for the Tableau dashboard
--   Q7 Index       EXPLAIN ANALYZE before/after an index
--
-- Notes that apply to every rent query:
--   * monthly_rent is reported in $250 bands, so "rent" here is the band
--     midpoint (min_rent + max_rent) / 2. It is an estimate, not exact rent.
--   * "$0 / no rent paid" bands have NULL bounds and the open-ended "$7000+"
--     band has no max_rent, so AVG() skips them automatically.
--   * Vacancy rate = share of residential filings (Non-Residential excluded)
--     whose occupancy type is 'Vacant'.
-- ============================================================================

USE sf_rent_board;


-- ----------------------------------------------------------------------------
-- Q1 (BASIC): How many unit filings were submitted in each filing year?
-- Concepts: JOIN, GROUP BY, COUNT
-- ----------------------------------------------------------------------------
SELECT fc.submission_year,
       fc.case_type_name,
       COUNT(r.unique_id) AS unit_filings
  FROM FilingCycle fc
  LEFT JOIN UnitReport r ON r.submission_year = fc.submission_year
 GROUP BY fc.submission_year, fc.case_type_name
 ORDER BY fc.submission_year;
-- Result (2026-10-01 extract):
--   2022  66,744 | 2023 107,886 | 2024 111,513 | 2025 132,088 | 2026 133,320
-- Key finding: filings doubled from 2022 to 2026 (66,744 -> 133,320).
-- Insight: The inventory is still being adopted, so the number of filings
--   reflects landlord compliance as much as the housing stock. Any trend over
--   years should use rates (percent vacant), not raw counts, or the growth in
--   filings will look like growth in housing.


-- ----------------------------------------------------------------------------
-- Q2 (BASIC): What share of all filings does each occupancy type make up?
-- Concepts: JOIN, GROUP BY, COUNT, percentage
-- ----------------------------------------------------------------------------
SELECT ot.name                                            AS occupancy_type,
       COUNT(*)                                           AS filings,
       ROUND(100 * COUNT(*) / (SELECT COUNT(*) FROM UnitReport), 2) AS pct_of_all
  FROM UnitReport r
  JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
 GROUP BY ot.name
 ORDER BY filings DESC;
-- Result:
--   Occupied by non-owner 484,803 (87.90%) | Vacant 36,110 (6.55%)
--   Occupied by owner      28,006 (5.08%)  | Non-Residential 2,632 (0.48%)
-- Key finding: almost 9 in 10 filings are tenant-occupied; about 1 in 15
--              is vacant.
-- Insight: Rental housing dominates the inventory, so the data mostly
--   describes tenant-occupied units. A 6.55% vacancy share means roughly
--   36,000 filed units were empty, a meaningful pool of potential housing in a
--   city with a housing shortage.


-- ----------------------------------------------------------------------------
-- Q3 (ADVANCED - CTE, 4-table join): Which neighborhoods have the highest
-- estimated rent, and how far is each above or below the citywide average?
-- Concepts: two CTEs, multi-table JOIN, HAVING, CROSS JOIN to a 1-row CTE
-- ----------------------------------------------------------------------------
WITH neighborhood_rent AS (
    SELECT n.name                                AS neighborhood,
           COUNT((rb.min_rent + rb.max_rent) / 2) AS rent_reports,
           AVG((rb.min_rent + rb.max_rent) / 2)   AS avg_rent
      FROM UnitReport r
      JOIN RentBand rb      ON rb.rent_band_id   = r.rent_band_id
      JOIN LocationPoint lp ON lp.point_id       = r.point_id
      JOIN Neighborhood n   ON n.neighborhood_id = lp.neighborhood_id
     GROUP BY n.name
    HAVING COUNT((rb.min_rent + rb.max_rent) / 2) >= 100   -- skip tiny groups
),
city AS (
    SELECT AVG((rb.min_rent + rb.max_rent) / 2) AS city_avg_rent
      FROM UnitReport r
      JOIN RentBand rb ON rb.rent_band_id = r.rent_band_id
)
SELECT nr.neighborhood,
       nr.rent_reports,
       ROUND(nr.avg_rent)                                          AS avg_rent,
       ROUND(c.city_avg_rent)                                      AS city_avg_rent,
       ROUND(nr.avg_rent - c.city_avg_rent)                        AS diff_from_city,
       ROUND(100 * (nr.avg_rent - c.city_avg_rent) / c.city_avg_rent, 1) AS pct_diff
  FROM neighborhood_rent nr
 CROSS JOIN city c
 ORDER BY nr.avg_rent DESC;
-- Result (37 neighborhoods, citywide average estimated rent = $2,502):
--   Highest: Mission Bay $3,618 (+44.6%), Potrero Hill $3,314 (+32.4%),
--            Glen Park $3,216 (+28.5%), Financial District/South Beach $3,174
--   Lowest:  Chinatown $1,156 (-53.8%), Tenderloin $1,639 (-34.5%),
--            Nob Hill $2,016 (-19.4%)
-- Key finding: estimated rent in Mission Bay is about 3x Chinatown's.
-- Insight: Location drives rent strongly. Newer, high-rise areas (Mission Bay,
--   Financial District/South Beach) sit far above the city average, while
--   older, rent-controlled areas (Chinatown, Tenderloin, Nob Hill) sit far
--   below it. Renters and policy makers should compare rent by neighborhood,
--   not by one citywide average.


-- ----------------------------------------------------------------------------
-- Q4 (ADVANCED - SUBQUERY): Among units reported vacant, which neighborhoods
-- have the most "repeat" vacancies, i.e. the unit's history already shows an
-- earlier vacant period that ended before the current vacancy date?
-- Concepts: correlated EXISTS subquery, conditional SUM, JOIN, HAVING
-- ----------------------------------------------------------------------------
SELECT n.name                                     AS neighborhood,
       COUNT(*)                                   AS vacant_filings,
       SUM(EXISTS (SELECT 1
                     FROM OccupancyHistory h
                    WHERE h.unique_id = r.unique_id
                      AND LOWER(h.range_type) = 'vacant'
                      AND h.end_date < r.vacancy_date))  AS repeat_vacancies,
       ROUND(100 * SUM(EXISTS (SELECT 1
                     FROM OccupancyHistory h
                    WHERE h.unique_id = r.unique_id
                      AND LOWER(h.range_type) = 'vacant'
                      AND h.end_date < r.vacancy_date)) / COUNT(*), 1) AS pct_repeat
  FROM UnitReport r
  JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
  JOIN LocationPoint lp ON lp.point_id          = r.point_id
  JOIN Neighborhood n   ON n.neighborhood_id    = lp.neighborhood_id
 WHERE ot.name = 'Vacant'
   AND r.vacancy_date IS NOT NULL
 GROUP BY n.name
HAVING COUNT(*) >= 50
 ORDER BY repeat_vacancies DESC
 LIMIT 15;
-- Result (top rows):
--   Tenderloin 62 of 2,221 vacant filings (2.8%) | Nob Hill 47 of 2,044 (2.3%)
--   Western Addition 30 of 575 (5.2%, highest share) | Mission 18 of 1,461
-- Key finding: repeat vacancies are rare overall (a few percent of vacant
--              filings) and are concentrated in the Tenderloin and Nob Hill.
-- Limitation: only about 81k filings include an occupancy history, so this
--             undercounts repeat vacancies.
-- Insight: Most vacant units are not chronically empty; repeat vacancy is the
--   exception. Western Addition has the highest share (5.2%), so outreach on
--   long-term or repeated vacancies could start there and in the Tenderloin,
--   which has the most repeat cases.


-- ----------------------------------------------------------------------------
-- Q5 (ADVANCED - WINDOW FUNCTIONS)
-- Q5a: Inside each supervisor district, which neighborhood has the highest
--      vacancy rate?  RANK() OVER (PARTITION BY district)
-- ----------------------------------------------------------------------------
WITH nbhd_vacancy AS (
    SELECT lp.district_id                                   AS district,
           n.name                                           AS neighborhood,
           COUNT(*)                                         AS residential_filings,
           ROUND(100 * SUM(ot.name = 'Vacant') / COUNT(*), 2) AS vacancy_rate
      FROM UnitReport r
      JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
      JOIN LocationPoint lp ON lp.point_id          = r.point_id
      JOIN Neighborhood n   ON n.neighborhood_id    = lp.neighborhood_id
     WHERE ot.name <> 'Non-Residential'
       AND lp.district_id IS NOT NULL
     GROUP BY lp.district_id, n.name
    HAVING COUNT(*) >= 500
)
SELECT district,
       neighborhood,
       residential_filings,
       vacancy_rate,
       RANK() OVER (PARTITION BY district ORDER BY vacancy_rate DESC) AS rank_in_district
  FROM nbhd_vacancy
 ORDER BY district, rank_in_district;
-- Result (rank 1 in each district):
--   D1 Seacliff 4.16% | D2 Japantown 16.60% | D3 Tenderloin 18.64%
--   D4 Sunset/Parkside 3.11% | D5 Tenderloin 10.71% | D6 Mission 12.07%
--   D7 Lakeshore 16.06% | D8 Hayes Valley 7.50% | D9 Mission 5.69%
--   D10 Bayview Hunters Point 4.04% | D11 Outer Mission 5.53%
-- Key finding: the highest vacancy pockets are the Tenderloin (D3), Japantown
--   (D2) and Lakeshore (D7). A neighborhood can appear in more than one
--   district because district lines cut across neighborhoods.
-- Insight: Vacancy is concentrated in a few pockets rather than spread evenly.
--   Ranking within each district shows each supervisor which neighborhood in
--   their own district needs attention first (for example the Tenderloin in
--   D3, Lakeshore in D7, Japantown in D2).

-- Q5b: How did each district's vacancy rate change from one filing year to
--      the next?  LAG() OVER (PARTITION BY district ORDER BY year)
WITH district_year AS (
    SELECT lp.district_id                                   AS district,
           r.submission_year,
           ROUND(100 * SUM(ot.name = 'Vacant') / COUNT(*), 2) AS vacancy_rate
      FROM UnitReport r
      JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
      JOIN LocationPoint lp ON lp.point_id          = r.point_id
     WHERE ot.name <> 'Non-Residential'
       AND lp.district_id IS NOT NULL
     GROUP BY lp.district_id, r.submission_year
)
SELECT district,
       submission_year,
       vacancy_rate,
       LAG(vacancy_rate) OVER w                  AS prev_year_rate,
       ROUND(vacancy_rate - LAG(vacancy_rate) OVER w, 2) AS change_pts
  FROM district_year
WINDOW w AS (PARTITION BY district ORDER BY submission_year)
 ORDER BY district, submission_year;
-- Result (2022 -> 2026 vacancy rate):
--   D3 13.01% -> 6.41% | D7 10.96% -> 5.99% (12.46% in 2025, then -6.47 pts)
--   D5  9.01% -> 5.51% | D2  7.19% -> 2.91% | D1 5.49% -> 2.53%
-- Key finding: vacancy fell in every district from 2022 to 2026. D3 was
--   highest every year; D7's 2025 spike is the biggest one-year jump.
-- Insight: Vacancy has been falling citywide since 2022, which suggests the
--   rental market is tightening. D7's one-year spike and drop is worth a
--   closer look (it may be one large building, such as student housing near
--   Lakeshore, rather than a district-wide change).


-- ----------------------------------------------------------------------------
-- Q6 (ADVANCED - VIEW): one row per filing with location, year, occupancy and
-- estimated rent. Tableau connects to this view for my two visualizations:
--   (1) vacancy rate by neighborhood (map/bar), filter: filing year
--   (2) vacancy rate over time by district (line), filter: district
-- Concepts: CREATE VIEW, LEFT JOIN (keep filings with no rent band), CASE
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_shraddha_occupancy AS
SELECT r.unique_id,
       r.submission_year,
       lp.district_id                       AS supervisor_district,
       n.name                               AS neighborhood,
       lp.latitude,
       lp.longitude,
       ot.name                              AS occupancy_type,
       CASE WHEN ot.name = 'Vacant' THEN 1 ELSE 0 END AS is_vacant,
       rb.raw_label                         AS rent_band,
       (rb.min_rent + rb.max_rent) / 2      AS est_rent
  FROM UnitReport r
  JOIN OccupancyType ot      ON ot.occupancy_type_id = r.occupancy_type_id
  JOIN LocationPoint lp      ON lp.point_id          = r.point_id
  LEFT JOIN Neighborhood n   ON n.neighborhood_id    = lp.neighborhood_id
  LEFT JOIN RentBand rb      ON rb.rent_band_id      = r.rent_band_id
 WHERE ot.name <> 'Non-Residential';

-- Using the view: top 10 neighborhoods by vacancy rate in the latest year
SELECT neighborhood,
       COUNT(*)                          AS residential_filings,
       ROUND(100 * AVG(is_vacant), 2)    AS vacancy_rate,
       ROUND(AVG(est_rent))              AS avg_est_rent
  FROM v_shraddha_occupancy
 WHERE submission_year = 2026
   AND neighborhood IS NOT NULL
 GROUP BY neighborhood
HAVING COUNT(*) >= 500
 ORDER BY vacancy_rate DESC
 LIMIT 10;
-- Result (2026):
--   Chinatown 13.38% ($1,266) | Lakeshore 10.52% ($2,656) | Tenderloin 9.87% ($1,718)
--   North Beach 6.20% | Financial District/South Beach 6.13% ($3,444) | Mission 4.84%
-- Key finding: in 2026 the highest vacancy is in two of the cheapest
--   neighborhoods (Chinatown, Tenderloin), so low rent does not mean low vacancy.
-- Insight: Cheap units are not automatically filled. High vacancy in low-rent
--   areas may point to older buildings or units in poor condition. The view
--   also gives the Tableau dashboard one clean source to filter by year and
--   district.


-- ----------------------------------------------------------------------------
-- Q7 (ADVANCED - INDEXING / PERFORMANCE): Does an index make the
-- "vacancy rate by district and year" query faster?
-- Run each EXPLAIN ANALYZE and compare the plan and the actual time.
-- ----------------------------------------------------------------------------

-- Step 1: BEFORE (no index on these columns yet)
EXPLAIN ANALYZE
SELECT lp.district_id, r.submission_year, COUNT(*) AS vacant_filings
  FROM UnitReport r
  JOIN LocationPoint lp ON lp.point_id = r.point_id
 WHERE r.occupancy_type_id = 2          -- 2 = 'Vacant' (seeded in schema.sql)
 GROUP BY lp.district_id, r.submission_year;

-- Step 2: add a composite index on the filter column + the join/group columns
CREATE INDEX idx_unitreport_occ_year_point
    ON UnitReport (occupancy_type_id, submission_year, point_id);

-- Step 3: AFTER (same query)
EXPLAIN ANALYZE
SELECT lp.district_id, r.submission_year, COUNT(*) AS vacant_filings
  FROM UnitReport r
  JOIN LocationPoint lp ON lp.point_id = r.point_id
 WHERE r.occupancy_type_id = 2
 GROUP BY lp.district_id, r.submission_year;

-- Result (5 warm runs each, MySQL 8.0):
--   BEFORE: Index lookup on r using occupancy_type_id (the FK index), then
--           reads each row from the table          -> about 88-109 ms
--   AFTER:  Covering index lookup on r using idx_unitreport_occ_year_point
--           (no table reads needed)                -> about 26 ms
-- Key finding: about 3.6x faster. The FK index already finds the vacant rows,
--   but MySQL still has to open every row to get submission_year and
--   point_id. The composite index holds all three columns, so it "covers" the
--   query.
-- Insight: Choosing index columns to match the WHERE, JOIN and GROUP BY of a
--   frequent query lets MySQL answer it from the index alone. This matters
--   for the dashboard, where the same query runs every time a filter changes.

-- To repeat the experiment from scratch, run these two lines first.
-- (Creating the composite index lets MySQL drop the original FK index on
--  occupancy_type_id, so it has to be recreated before the drop works.)
-- CREATE INDEX occupancy_type_id ON UnitReport (occupancy_type_id);
-- DROP INDEX idx_unitreport_occ_year_point ON UnitReport;
