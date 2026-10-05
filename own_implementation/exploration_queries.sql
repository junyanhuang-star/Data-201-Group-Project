-- Q1.) How are unit reports distributed across the valid canonical bedroom
-- and bathroom counts?
-- A correct answer would output the frequency of UnitReport rows in each
-- bedroom-and-bathroom combination.
-- A JOIN is used to join UnitReport to BedroomLabel and BathroomLabel.
-- COUNT(*) is used to count the UnitReport rows in each combination.
-- GROUP BY is used on both canonical bedroom and bathroom values. This groups
-- by the combination of the two attributes rather than creating a separate
-- secondary GROUP BY.
-- Rows with unparseable bedroom or bathroom labels should be excluded if the
-- question is intended to compare only valid canonical values.
-- ORDER BY should use DESC if the most frequent combinations should appear
-- first. ASC can be used when viewing the values from least to most frequent.

-- The BedroomLabel and BathroomLabel tables are joined so that the actual names of
-- the bedroom/bathroom labels can be returned. The UnitReport only contains the ID
-- of the labels as a foreign key. The Bedroom/BathroomLabel tables act like a lookup table 
SELECT bed.canonical_bedrooms, bath.canonical_bathrooms, COUNT(*) AS report_count
FROM UnitReport AS ur
JOIN BedroomLabel AS bed ON ur.bedroom_label_id = bed.bedroom_label_id
JOIN BathroomLabel AS bath ON ur.bathroom_label_id = bath.bathroom_label_id
-- The lookup tables have a boolean 'is_unparseable' which means that original raw labels
-- could not be mapped to a numerical value, so it is excluded from the list.
-- If the row entry did not have an original raw label, they would be excluded entirely as well
WHERE bed.is_unparseable = FALSE
    AND bath.is_unparseable = FALSE
    AND bed.canonical_bedrooms IS NOT NULL
    AND bath.canonical_bathrooms IS NOT NULL
-- Groups the rows first by bedrooms, then further subgroup based on bathroom count
GROUP BY bed.canonical_bedrooms, bath.canonical_bathrooms
-- Rows will be ordered with highest count to lowest
ORDER BY report_count DESC, bed.canonical_bedrooms, bath.canonical_bathrooms;

-- Q2.) How are square-footage bands distributed across rent bands?
-- A correct answer would output the frequency of each square-footage band
-- within each rent-band group.
-- A JOIN is used to join UnitReport to RentBand and SquareFootageBand.
-- COUNT(*) is used to count the UnitReport rows in each combination.
-- GROUP BY is used on the rent band and square-footage band.
-- ORDER BY, rather than SORT BY, is used to sort the results. A numeric rent
-- attribute such as min_rent should be used when sorting rent bands instead of
-- the raw text label.

-- The UnitReport table is joined with the RentBand and SquareFootageBand tables so that
-- the actual original ranges can be referenced. UnitReport only has the foreign keys and
-- the RentBand and SquareFootageBand act like lookup tables
SELECT rb.raw_label AS rent_band, sb.raw_label AS sqft_band, COUNT(*) AS report_count
FROM UnitReport AS ur
JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
JOIN SquareFootageBand AS sb ON ur.sqft_band_id = sb.sqft_band_id
-- The lookup table for SquareFootageBand has a boolean 'is_unknown' which is flagged for rows
-- that could not be mapped to a valid range.
WHERE sb.is_unknown = FALSE
-- The tables are grouped by the rent range and square footage ranges combinations
GROUP BY rb.raw_label, sb.raw_label
-- Rows will be ordered with highest count to lowest
ORDER BY report_count DESC, rb.min_rent, sb.min_sqft;


-- Q3.) Which bedroom-bathroom combination is most frequently reported within
-- each rent band, and what is its frequency?
-- A correct answer would output the bedroom-bathroom frequencies within each
-- rent band and identify the highest-count combination for each rent band.
-- This gives an indication of what kinds of rooms are commonly available to
-- users who want to spend within a particular rent range.
-- A JOIN is used to join UnitReport to RentBand, BedroomLabel, and BathroomLabel.
-- COUNT(*) is used to count the UnitReport rows in each combination.
-- Reports whose bedroom or bathroom lookup row has is_unparseable = TRUE
-- should be filtered out when comparing valid canonical values.
-- GROUP BY is used on the rent band, canonical bedroom count, and canonical
-- bathroom count.
-- A subquery is used to find the highest grouped count within each rent band.
-- If multiple combinations tie for the highest count, the query should retain
-- all tied combinations unless the project defines a different rule.

-- The UnitReport table is joined with the lookup tables for Rent, Bedroom, and Bathroom labels
SELECT rb.raw_label AS rent_band, bed.canonical_bedrooms, bath.canonical_bathrooms, COUNT(*) AS report_count
FROM UnitReport AS ur
JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
JOIN BedroomLabel AS bed ON ur.bedroom_label_id = bed.bedroom_label_id
JOIN BathroomLabel  AS bath ON ur.bathroom_label_id = bath.bathroom_label_id
-- The rows with values that cannot be looked up and converted to normalized values are excluded entirely
WHERE bed.is_unparseable = FALSE
    AND bath.is_unparseable = FALSE
    AND bed.canonical_bedrooms IS NOT NULL
    AND bath.canonical_bathrooms IS NOT NULL
    AND rb.is_no_rent_paid = FALSE
-- Create groups based on the combination of rent ranges, bedroom ranges, bathroom ranges
GROUP BY rb.raw_label, bed.canonical_bedrooms, bath.canonical_bathrooms
-- Without the subquery, the report_count of all combinations will be returned.
-- With the subquery, only the highest bedroom/bathroom range combination of each rent range will be outputted
HAVING COUNT(*) >= ALL (
    -- This subquery counts bedroom/bathroom combinations within the correlated rent band
    SELECT COUNT(*)
    FROM UnitReport AS ur2
    JOIN RentBand AS rb2 ON ur2.rent_band_id = rb2.rent_band_id
    JOIN BedroomLabel AS bed2 ON ur2.bedroom_label_id = bed2.bedroom_label_id
    JOIN BathroomLabel  AS bath2 ON ur2.bathroom_label_id = bath2.bathroom_label_id
    WHERE ur2.rent_band_id = rb.rent_band_id
        AND bed2.is_unparseable = FALSE
        AND bath2.is_unparseable = FALSE
        AND bed2.canonical_bedrooms IS NOT NULL
        AND bath2.canonical_bathrooms IS NOT NULL
        AND rb2.is_no_rent_paid = FALSE
    GROUP BY bed2.canonical_bedrooms, bath2.canonical_bathrooms
)
-- Rows will be ordered with highest count to lowest
-- Rent bands will be displayed together, but ordered by report count
ORDER BY rb.min_rent, report_count DESC, bed.canonical_bedrooms, bath.canonical_bathrooms;


-- Q4.) Which combination of bedroom count, bathroom count, square-footage band,
-- and rent band occurs more frequently than the average combination?
-- A correct answer would output the grouped profiles whose UnitReport count is
-- higher than the average count across all grouped profiles.
-- Here, "average combination" means the average UnitReport count calculated
-- across the grouped bedroom/bathroom/square-footage/rent profiles.
-- A JOIN is used to join UnitReport to RentBand, BedroomLabel, BathroomLabel,
-- and SquareFootageBand.
-- COUNT(*) is used to count the UnitReport rows in each four-attribute group.
-- GROUP BY is used on the rent band, canonical bedroom count, canonical
-- bathroom count, and square-footage band.
-- A subquery is used to calculate the average grouped count and filter out
-- profiles whose counts are not above that average.
-- The query should document whether it excludes unparseable labels, missing
-- bands, or rent bands marked as no rent paid.

-- The UnitReport is joined with all of the lookup tables and 
-- the same joins and data filters are applied as in the other queries.
SELECT rb.raw_label AS rent_band, bed.canonical_bedrooms, bath.canonical_bathrooms, sb.raw_label AS sqft_band, COUNT(*) AS report_count
FROM UnitReport AS ur
JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
JOIN BedroomLabel AS bed ON ur.bedroom_label_id = bed.bedroom_label_id
JOIN BathroomLabel  AS bath ON ur.bathroom_label_id = bath.bathroom_label_id
JOIN SquareFootageBand AS sb ON ur.sqft_band_id = sb.sqft_band_id
WHERE bed.is_unparseable = FALSE
    AND bath.is_unparseable = FALSE
    AND bed.canonical_bedrooms IS NOT NULL
    AND bath.canonical_bathrooms IS NOT NULL
    AND rb.is_no_rent_paid = FALSE
    AND sb.is_unknown = FALSE
GROUP BY rb.raw_label, bed.canonical_bedrooms, bath.canonical_bathrooms, sb.raw_label
-- Only the rows that have a higher count than the average count among the combinations
-- The subquery used is almost identical to the outer query, the difference is that the average is
-- taken among the count in each group and is used to filter out the profiles. Only profiles with
-- report counts higher than the calculated average are returned.
HAVING COUNT(*) > (
    SELECT AVG(profile.report_count)
    FROM (
        SELECT COUNT(*) AS report_count
        FROM UnitReport AS ur2
        JOIN RentBand AS rb2 ON ur2.rent_band_id = rb2.rent_band_id
        JOIN BedroomLabel AS bed2 ON ur2.bedroom_label_id = bed2.bedroom_label_id
        JOIN BathroomLabel AS bath2 ON ur2.bathroom_label_id = bath2.bathroom_label_id
        JOIN SquareFootageBand AS sb2 ON ur2.sqft_band_id = sb2.sqft_band_id
        WHERE bed2.is_unparseable = FALSE
            AND bath2.is_unparseable = FALSE
            AND bed2.canonical_bedrooms IS NOT NULL
            AND bath2.canonical_bathrooms IS NOT NULL
            AND rb2.is_no_rent_paid = FALSE
            AND sb2.is_unknown = FALSE
        GROUP BY rb2.raw_label, bed2.canonical_bedrooms, bath2.canonical_bathrooms, sb2.raw_label
    ) AS profile
)
-- Rows will be ordered with highest count to lowest
ORDER BY report_count DESC, rb.min_rent;