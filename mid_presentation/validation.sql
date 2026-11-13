USE sf_rent_board;

-- Row preservation: compare this with the raw CSV row count.
SELECT COUNT(*) AS unit_report_rows FROM UnitReport;

-- FK integrity spot checks. Each query should return zero rows.
SELECT r.unique_id FROM UnitReport r
LEFT JOIN FilingCycle f USING (submission_year)
WHERE f.submission_year IS NULL;

SELECT r.unique_id FROM UnitReport r
LEFT JOIN OccupancyType o USING (occupancy_type_id)
WHERE o.occupancy_type_id IS NULL;

SELECT h.history_id FROM OccupancyHistory h
LEFT JOIN UnitReport r USING (unique_id)
WHERE r.unique_id IS NULL;

-- Main dependency checks used in the 3NF argument.
SELECT submission_year, COUNT(DISTINCT case_type_name) AS labels
FROM FilingCycle GROUP BY submission_year HAVING labels <> 1;

SELECT point_id, COUNT(DISTINCT neighborhood_id) AS neighborhoods,
       COUNT(DISTINCT district_id) AS districts
FROM LocationPoint GROUP BY point_id
HAVING neighborhoods > 1 OR districts > 1;

-- Audit rather than hide cleaning decisions.
SELECT issue_code, column_name, COUNT(*) AS affected_rows
FROM QualityIssue GROUP BY issue_code, column_name
ORDER BY affected_rows DESC;

-- Example analysis-safe rent query. Bands remain bands; no midpoint is invented.
SELECT f.submission_year, o.name AS occupancy_type,
       COUNT(*) AS reports, COUNT(r.rent_band_id) AS reports_with_rent_band
FROM UnitReport r
JOIN FilingCycle f USING (submission_year)
JOIN OccupancyType o USING (occupancy_type_id)
LEFT JOIN RentBand rb USING (rent_band_id)
GROUP BY f.submission_year, o.name
ORDER BY f.submission_year, o.name;

-- ============================================================================
-- Sample inspection queries
--
-- These queries are intended for the committed 100-row discussion sample.
-- SELECT * is useful here because the purpose is to view how each relation is
-- populated. LIMIT 100 keeps the same inspection script practical if it is
-- later run after loading the full CSV.
-- ============================================================================
SELECT * FROM ExtractBatch LIMIT 100;
SELECT * FROM FilingCycle LIMIT 100;
SELECT * FROM Neighborhood LIMIT 100;
SELECT * FROM SupervisorDistrict LIMIT 100;
SELECT * FROM LocationPoint LIMIT 100;
SELECT * FROM AssessorBlock LIMIT 100;
SELECT * FROM BlockAddress LIMIT 100;
SELECT * FROM OccupancyType LIMIT 100;
SELECT * FROM BedroomLabel LIMIT 100;
SELECT * FROM BathroomLabel LIMIT 100;
SELECT * FROM SquareFootageBand LIMIT 100;
SELECT * FROM RentBand LIMIT 100;
SELECT * FROM UnitReport LIMIT 100;
SELECT * FROM Utility LIMIT 100;
SELECT * FROM ReportUtility LIMIT 100;
SELECT * FROM OccupancyHistory LIMIT 100;
SELECT * FROM QualityIssue LIMIT 100;
