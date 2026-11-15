-- AI-ASSISTANCE DISCLOSURE:
-- Since my team and I have decided to focus our queries on the
-- same tables that we worked with during the mid presentation to avoid
-- overlapping domain questions, I relied on Codex to help brainstorm domain
-- questions involving my assigned tables that I had not covered yet. As we
-- have been practicing throughout homework assignments to write solutions
-- first from a given domain question and compare the approaches with an AI
-- solution, I thought it would be okay to use that same approach for working
-- on SQL queries on the project. My goal is to use the AI solutions as a
-- reference and take note of how it is different compared to the way that
-- was covered in the course, and whether it opts in to use methods that aren't
-- covered. If I decide to keep any part of the AI solutions, then I will
-- specifically disclose where AI has been used. I am making sure that my
-- portion of the submitted SQL queries are queries that I have written myself
-- and can understand what each part of the execution. If there are areas of
-- the queries that I do not understand, I plan to get clarification from AI
-- to understand, and I will disclose the areas that I struggled with. I
-- understand that the use of AI is encouraged throughout this project, but I
-- will be transparent with what help is provided.

-- Q1.) What is the frequency percentage of occupied and vacant residential properties of each rent band?
-- Basic Query: uses CTEs, JOINS, CASE, SUM(), GROUP BY, percentages
WITH occupancy_counts AS (
    SELECT rb.rent_band_id,
        rb.raw_label AS rent_band,
        -- Get the count of all reports in each rent band
        COUNT(*) AS total_reports,
        -- The unique values in OccupancyType are:
        -- 'Occupied by non-owner,' 'Vacant,' 'Occupied by owner,' and 'Non-Residential'
        -- Get the count of occupied reports by using CASE
        -- If the occupancy type is not 'Occupied' then the value is 0
        -- SUM gets the total count of the column values
        SUM(CASE
                WHEN ot.name IN (
                    'Occupied by non-owner',
                    'Occupied by owner'
                ) THEN 1 ELSE 0
            END) AS occupied_reports,
        -- Get the count of vacant reports by using CASE
        -- If the occupancy type is not 'Vacant' then the value is 0
        -- SUM gets the total count of the column values
        SUM(CASE
                WHEN ot.name = 'Vacant'
                THEN 1 ELSE 0
            END) AS vacant_reports
    -- The UnitReport table is joined with the RentBand and OccupancyType tables so that
    -- the actual original ranges can be referenced. UnitReport only has the foreign keys and
    -- the RentBand and OccupancyType act like lookup tables
    -- JOIN is used so only matches are shown
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    JOIN OccupancyType AS ot ON ur.occupancy_type_id = ot.occupancy_type_id
    -- OccupancyType also includes 'Non-Residential' which indicates that the property
    -- is not rented by residential, but could be used for commercial use such as businesses
    WHERE rb.min_rent IS NOT NULL
        AND ot.name NOT IN (
            'Non-Residential'
        )
    -- Group by rent band, to get the counts for each rent band
    GROUP by rb.rent_band_id, rb.raw_label
)

-- display the rent_band
-- the statistics from occupancy_counts are grouped by rent_bands
-- display the total report of each rent_band
-- display the total occupied reports of each rent_band
-- display the total vacant reports of each rent_band
-- display the percentages
SELECT
    oc.rent_band, oc.total_reports, oc.occupied_reports, oc.vacant_reports,
    ROUND((oc.occupied_reports / oc.total_reports) * 100, 2) AS occupied_percent,
    ROUND((oc.vacant_reports / oc.total_reports) * 100, 2) AS vacant_percent
FROM occupancy_counts AS oc
ORDER BY oc.rent_band_id;

-- Insight: The unit reports shows reports of both residential properties and also
-- properties used for commercial use such as for stores. However, for this query, I
-- wanted to focus on finding the percentage of occupied vs vacant residential properties.
-- With the results, we could potentially figure out if there was any potential abnormalities
-- where there were significantly more vacancy compared to occupied in a certain rent band. We
-- can use the computed percentages as another way to look at which rent bands are most frequently reported.

-- Q2.) Which utilities are most commonly included within each rent band?
-- Basic Query: JOINS, CTEs, COUNT(), percentages
-- Create a CTE to compute the rent band counts from UnitReport
WITH rent_band_count AS (
    -- display rent_band_id and raw_label as the results will be grouped by these
    SELECT rb.rent_band_id, rb.raw_label AS rent_band,
        -- get the total report count of each rent band group
        COUNT(ur.unique_id) AS total_reports
    -- The UnitReport table is joined with the RentBand table so that
    -- the actual original ranges can be referenced. UnitReport only has the foreign keys and
    -- the RentBand act like lookup tables
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    -- validate that the rent band is valid if it doesn't have a NULL min_rent
    WHERE rb.min_rent IS NOT NULL
    -- group the counts by rent band
    GROUP BY rb.rent_band_id, rb.raw_label
),
-- Create a CTE that gets the rent band - utility combo count
utility_counts AS (
    -- display rent_band_id and utility name as the results will be grouped by these
    SELECT rb.rent_band_id, u.name AS utility,
        -- get the total report count of each rent band - utility combo
        COUNT(DISTINCT ru.unique_id) AS reports_with_utility_count
    -- The UnitReport table is joined with the RentBand, Utility tables so that
    -- the actual original ranges and Utility names can be referenced. UnitReport only has the foreign keys and
    -- the RentBand and Utility act like lookup tables
    -- ReportUtility handles the M:N relationship between unit reports and utilities as a
    -- report can have many utilities, so the ReportUtility table consists of composite keys
    -- that are made up of foreign keys of the unit report and the utilities.
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    JOIN ReportUtility AS ru ON ur.unique_id = ru.unique_id
    JOIN Utility AS u ON ru.utility_id = u.utility_id
    -- validate that the rent band is valid if it doesn't have a NULL min_rent
    WHERE rb.min_rent IS NOT NULL
    -- group the counts by rent band and utility name
    GROUP BY rb.rent_band_id, u.name
)

-- display the rent band and utility
-- display the counts of each rent band - utility combo
-- display the percentage of the utilities in these combos
SELECT rbc.rent_band, uc.utility, uc.reports_with_utility_count,
    ROUND((uc.reports_with_utility_count / rbc.total_reports) * 100, 2) AS utility_percent
FROM utility_counts AS uc
JOIN rent_band_count AS rbc ON uc.rent_band_id = rbc.rent_band_id
-- order by rent band and display with percentages in descending order
ORDER BY rbc.rent_band_id, utility_percent DESC;

-- Q2.) (UPDATED TO HAVE EXPLAIN ANALYZE) Which utilities are most commonly included within each rent band?
-- Basic Query: JOINS, CTEs, COUNT(), percentages
-- Create a CTE to compute the rent band counts from UnitReport
EXPLAIN ANALYZE
WITH rent_band_count AS (
    -- display rent_band_id and raw_label as the results will be grouped by these
    SELECT rb.rent_band_id, rb.raw_label AS rent_band,
        -- get the total report count of each rent band group
        COUNT(ur.unique_id) AS total_reports
    -- The UnitReport table is joined with the RentBand table so that
    -- the actual original ranges can be referenced. UnitReport only has the foreign keys and
    -- the RentBand act like lookup tables
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    -- validate that the rent band is valid if it doesn't have a NULL min_rent
    WHERE rb.min_rent IS NOT NULL
    -- group the counts by rent band
    GROUP BY rb.rent_band_id, rb.raw_label
),
-- Create a CTE that gets the rent band - utility combo count
utility_counts AS (
    -- display rent_band_id and utility name as the results will be grouped by these
    SELECT rb.rent_band_id, u.name AS utility,
        -- get the total report count of each rent band - utility combo
        COUNT(DISTINCT ru.unique_id) AS reports_with_utility_count
    -- The UnitReport table is joined with the RentBand, Utility tables so that
    -- the actual original ranges and Utility names can be referenced. UnitReport only has the foreign keys and
    -- the RentBand and Utility act like lookup tables
    -- ReportUtility handles the M:N relationship between unit reports and utilities as a
    -- report can have many utilities, so the ReportUtility table consists of composite keys
    -- that are made up of foreign keys of the unit report and the utilities.
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    JOIN ReportUtility AS ru ON ur.unique_id = ru.unique_id
    JOIN Utility AS u ON ru.utility_id = u.utility_id
    -- validate that the rent band is valid if it doesn't have a NULL min_rent
    WHERE rb.min_rent IS NOT NULL
    -- group the counts by rent band and utility name
    GROUP BY rb.rent_band_id, u.name
)

-- display the rent band and utility
-- display the counts of each rent band - utility combo
-- display the percentage of the utilities in these combos
SELECT rbc.rent_band, uc.utility, uc.reports_with_utility_count,
    ROUND((uc.reports_with_utility_count / rbc.total_reports) * 100, 2) AS utility_percent
FROM utility_counts AS uc
JOIN rent_band_count AS rbc ON uc.rent_band_id = rbc.rent_band_id
-- order by rent band and display with percentages in descending order
ORDER BY rbc.rent_band_id, utility_percent DESC;

-- Insight:
-- This query can show the utility percentages in each rent band, and can be used to
-- see which utilities are most frequently covered in a certain rent band and what is
-- rarely accessible at a certain price range. The results of this query can give insight
-- as to what utilities can influence a property to be at a certain rent band.
-- In addition, this result could be represented visually with either a pie chart or a stacked
-- bar chart, so that it can be made clear how much the utilities vary at each rent band.

-- Q3.) Within each rent band, which bedroom/bathroom/square-footage combinations are most frequently reported?
-- Advanced Query: CTEs, multi JOINS, RANK(), window functions
-- Create a CTE that gets the report count of each rent band/bedroom/bathroom/square-footage combo
WITH report_combinations AS (
    -- display the rent band, label, bed count label, bath count label, square footage label
    -- display the report count of each of these combinations
    SELECT rb.rent_band_id, rb.raw_label AS rent_band, bed.canonical_bedrooms, bath.canonical_bathrooms,
        sb.raw_label AS sqft_band, COUNT(ur.unique_id) AS report_combination_count
    FROM UnitReport AS ur
    -- The UnitReport table is joined with the lookup tables for RentBand, Bedroom, Bathroom, and Square Footage
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    JOIN BedroomLabel AS bed ON ur.bedroom_label_id = bed.bedroom_label_id
    JOIN BathroomLabel AS bath ON ur.bathroom_label_id = bath.bathroom_label_id
    JOIN SquareFootageBand AS sb ON ur.sqft_band_id = sb.sqft_band_id
    -- Some of the entries are blank for the values corresponding to the lookup tables,
    -- so filter out invalid rows that have a blank value
    WHERE rb.min_rent IS NOT NULL
        AND bed.canonical_bedrooms IS NOT NULL
        AND bath.canonical_bathrooms IS NOT NULL
        AND sb.min_sqft IS NOT NULL
    -- group by rent band/bedroom/bathroom/square footage
    GROUP BY rb.rent_band_id, rb.raw_label, bed.canonical_bedrooms,
        bath.canonical_bathrooms, sb.raw_label
),
-- Create a CTE that takes report_combinations and ranks the combinations
-- based on counts
ranked_combinations AS (
    SELECT rc.rent_band_id, rc.rent_band, rc.canonical_bedrooms, rc.canonical_bathrooms,
        rc.sqft_band, rc.report_combination_count,
        -- partition by rent band, and rank the combinations within each rent band to determine
        -- what is the most frequent combination in each rent band
        RANK() OVER (
            PARTITION BY rc.rent_band_id ORDER BY rc.report_combination_count DESC
        ) AS combination_rank,
        -- compute the windowed total of reports in each rent band
        -- if ORDER BY was used, then there would be a running total
        -- AI DISCLOSURE: I originally had a ORDER BY, but it was computing a running
        -- total instead of a window total. Therefore, when using this value as the denominator
        -- in the final query, it would mistakenly use the total computed for the rank 1 row.
        -- I used AI to clarify the distinction between using ORDER BY and excluding it to get
        -- the window total that I was expecting to get.
        SUM(rc.report_combination_count) OVER (PARTITION BY rc.rent_band_id) AS rent_band_total
    FROM report_combinations AS rc
)

-- display the combinations
-- compute the percentage to determine how much the combination makes up the entire rent band
-- display only the highest ranking combination of each rent band
SELECT rc.rent_band, rc.canonical_bedrooms, rc.canonical_bathrooms, rc.sqft_band, rc.report_combination_count,
    ROUND((rc.report_combination_count / rc.rent_band_total) * 100, 2) AS combination_percent
FROM ranked_combinations AS rc
WHERE combination_rank = 1
ORDER BY rc.rent_band;

-- Insight: Previously, during the mid presentation, I wanted to find the combination counts of the
-- different combinations of the rent/square footage bands and the bedroom/bathroom counts to see if there
-- was any patterns with what was most frequent. After learning more about CTEs and window functions such as
-- RANK(), I can step up this question and determine the ranks of each combination in each rent band to determine
-- which is most frequently reported and which combination is least frequent. Insight on these rankings can give some information
-- on what types of people are frequently renting in San Francisco (ex. single people or smaller families typically rent
-- out properties in SF based on the high rankings of low count rooms and square footage. It can also show what types of properties
-- are most frequent)

-- Q4.) How has the share of each rent band changed across filing years?
-- Advanced Query: chaining CTEs, aggregation, LAG()
-- Create CTE to get the rent band counts in each year
WITH yearly_counts AS (
    -- display submission year, rent band, and report count in each year-rent band group
    SELECT ur.submission_year, rb.rent_band_id, rb.raw_label AS rent_band,
        COUNT(ur.unique_id) AS report_count
    -- join the rent band lookup table onto UnitReport
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    -- filter out rows with invalid rent bands
    WHERE rb.min_rent IS NOT NULL
    -- group by submission year and rent band
    GROUP BY ur.submission_year, rb.rent_band_id, rb.raw_label
),
-- Create CTE to compute the total reports in each submission year
yearly_totals AS (
    -- take the sum of report counts for each submission year
    -- add up the rent band - year combinations
    SELECT yc.submission_year, SUM(yc.report_count) AS total_reports
    FROM yearly_counts AS yc
    -- group by year
    GROUP BY submission_year
),
-- Create CTE to compute the percentage of what rent band makes up for that year
yearly_shares AS (
    -- display year and rent band
    -- compute the percentage of the rent band - year combo making up that year
    SELECT yc.submission_year, yc.rent_band_id, yc.rent_band,
        ROUND((yc.report_count / yt.total_reports) * 100, 2) AS share_percentage
    FROM yearly_counts AS yc
    -- join yearly_totals because it computes the total of each submission year which
    -- is used as the denominator
    JOIN yearly_totals AS yt ON yc.submission_year = yt.submission_year
)

-- display the submission year, rent band, and percentage that combination makes up that year
SELECT ys.submission_year, ys.rent_band, ys.share_percentage,
-- display the percentage of the previous year
    LAG(ys.share_percentage) OVER (PARTITION BY ys.rent_band_id ORDER BY ys.submission_year
    ) AS previous_year_share_percentage,
-- compute the difference between current and previous year
-- AI Disclosure: I relied on AI to get help on resolving the bug with this line. Through AI,
-- I learned that the alias cannot be immediately used in the same SELECT statement. The proposed
-- solution is to reimplement the LAG() logic for the percentage_point_change.
-- I initially tried to use the alias as I noticed what was needed was essentially identical to what
-- has already been calculated. AI had suggested to make this change as a new CTE to save space
-- in the final query, but I decided just to keep the LAG() logic in this select statement.
    ys.share_percentage - LAG(ys.share_percentage) OVER (PARTITION BY ys.rent_band_id ORDER BY ys.submission_year
    ) AS percentage_point_change
FROM yearly_shares AS ys
ORDER BY ys.rent_band, ys.submission_year;

-- Insight: To continue on analyzing how the rent bands are distributed each year, I wanted to
-- have this query determine the behaviors of these distributions across the years. I wanted to
-- see how these rent band distributions might have changed, if at all, throughout different filing
-- cycles. If there is a noticeable shift in the distributions, which would be indicated by large
-- percentage changes, then it could raise questions as to why there was a shift. Some potential reasoning
-- might be that this filing year had experience a year where property values just increased drastically in SF
-- at this year. On the other hand, low percentage changes across different filing years would indicate that
-- the rent prices in San Francisco were stable and there were likely no economic crisis that affected the rates.


-- Q5.) Within each rent band and bedroom count, which square-footage bands are most common?
-- Advanced Query: chaining CTEs, RANK(), window aggregation
-- Create a CTE to get the count for each rent band/bedroom/square footage combination
WITH size_counts AS (
    -- display the rent band, bedroom count label, sqft band label, 
    -- and count the total reports in each rent band/bedroom/sqft group
    SELECT rb.rent_band_id, rb.raw_label AS rent_band, bed.canonical_bedrooms,
        sb.sqft_band_id, sb.raw_label AS sqft_band, COUNT(ur.unique_id) AS size_count
    -- join the RentBand, BedroomLabel, SquareFootageBand tables onto UnitReport as
    -- it contains the foreign key references for these lookup tables
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    JOIN BedroomLabel AS bed ON ur.bedroom_label_id = bed.bedroom_label_id
    JOIN SquareFootageBand AS sb ON ur.sqft_band_id = sb.sqft_band_id
    -- filter out any invalid rows that don't have a valid value from the lookup tables
    WHERE rb.min_rent IS NOT NULL
        AND bed.canonical_bedrooms IS NOT NULL
        AND sb.min_sqft IS NOT NULL
    -- group by rent band/bedroom count/ sqft band
    GROUP BY rb.rent_band_id, rb.raw_label, bed.canonical_bedrooms,
        sb.sqft_band_id, sb.raw_label
),
-- Create a CTE to rank the combinations
-- for each rent band/bedroom group, rank the square footage bands
ranked_sizes AS (
    -- display the same values as size_counts CTE
    SELECT sc.rent_band_id, sc.rent_band, sc.canonical_bedrooms,
        sc.sqft_band_id, sc.sqft_band, sc.size_count,
    -- rank the square footage bands from each rent band/bedroom group
        RANK() OVER (
            PARTITION BY sc.rent_band_id, sc.canonical_bedrooms
            ORDER BY sc.size_count DESC
        ) AS size_rank,
        -- compute the window total reports in each rent band/bedroom group
        SUM(sc.size_count) OVER (
            PARTITION BY sc.rent_band_id, sc.canonical_bedrooms
        ) AS group_total
    FROM size_counts AS sc
)

-- display the rent band/ bedroom/ sqft groups
-- compute the percentage of how much the sqft band makes up the rent band/bedroom group
SELECT rs.rent_band, rs.canonical_bedrooms, rs.sqft_band, rs.size_count,
    ROUND((rs.size_count / rs.group_total) * 100, 2) AS size_band_percent
FROM ranked_sizes AS rs
-- display rank 1 as we want the largest distribution of each rent band/bedroom group
WHERE rs.size_rank = 1
ORDER BY rs.rent_band, rs.canonical_bedrooms;

-- Insight: This query allows us to analyze the behaviors of the rent bands and bedroom counts
-- with the square footage bands. We want to analyze that whether there is a relationship between
-- higher bedroom counts and higher rent bands with higher square footage bands. We want to see
-- if there are opposing cases with smaller square footage bands being grouped with odd pairings
-- such as lower bedroom counts or rent bands. We are anticipating that the results with this query
-- will vary as we expect that the rent bands could be influenced by location (meaning that this
-- question can be raised again when looking at other tables as well) rather than the rooms
-- and space that is provided. Before running the query, we are hypothesizing that there won't be a
-- direct relationship between the groups and square footage bands, and it could possibly vary.

-- Q6.) Which rent bands have an above-average share of units with shared bathrooms?
-- Advanced Query: CTEs, CASE, aggregation, scalar subquery
-- Create a CTE to compute the number of reports from each rent band that have
-- shared bathrooms; shared bathroom is indicated with 'is_shared'
WITH shared_bathroom_rates AS (
    SELECT rb.rent_band_id, rb.raw_label AS rent_band,
        -- get the count of reports that have a shared bathroom with 'is_shared' using CASE
        SUM(CASE
                WHEN bath.is_shared = TRUE THEN 1 ELSE 0
            END) AS shared_bathroom_count,
        -- get the count of reports in each rent band
        COUNT(ur.unique_id) AS total_reports,
        -- compute the percentage of shared bathrooms in each rent band
        ROUND((SUM(
                CASE
                    WHEN bath.is_shared = TRUE THEN 1 ELSE 0
                END) / COUNT(ur.unique_id)) * 100, 2
        ) AS shared_bathroom_percent
    -- join rent band, bathroom lookup tables onto UnitReport
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    JOIN BathroomLabel AS bath ON ur.bathroom_label_id = bath.bathroom_label_id
    -- filter out invalid rows that don't have valid rent band
    WHERE rb.min_rent IS NOT NULL
    GROUP BY rb.rent_band_id, rb.raw_label
)
-- display the rent band, bathroom counts, and percentages from CTE
SELECT sbr.rent_band, sbr.shared_bathroom_count, sbr.total_reports, sbr.shared_bathroom_percent
FROM shared_bathroom_rates AS sbr
-- compute a scalar subquery to find the average bathroom percents, and filter
-- out to only include rent bands that include shared bathroom averages that are
-- higher than the total average
WHERE sbr.shared_bathroom_percent > (
    SELECT AVG(shared_bathroom_percent)
    FROM shared_bathroom_rates
)
ORDER BY sbr.shared_bathroom_percent DESC;

-- Insight: The shared bathroom attribute was not previously explored in other
-- queries, but it could provide more insight about how much the varying bathroom counts
-- consist of shared bathrooms. If there are noticeable percentages with the shared bathrooms,
-- then further questions can be asked about whether the shared bathrooms have any relationship
-- with the size of the properties or the count of rooms/ types of utilities in a property.
-- By filtering out and only including rent bands with  shared bathroom percentages higher than
-- the average, it can be used to determine which rent bands typically have shared bathrooms.
-- The results could also be used to support arguments that these specific rent bands are the price
-- that they are because of their shared bathroom status.

-- Q7.) Which rent bands have the highest percentage of incomplete bedroom, bathroom, or square-footage information?
-- Advanced Query: LEFT JOIN, CTE, CASE, percentages
-- Create a CTE that computes the count of missing values from each of the lookup tables
-- Look at UnitReport, and check whether bedroom, bathroom, or square footage is missing
WITH data_quality AS (
    -- display rent band as results will be grouped by it
    SELECT rb.rent_band_id, rb.raw_label AS rent_band,
        -- count total reports for each rent band group
        COUNT(ur.unique_id) AS total_reports,
        -- use CASE to count missing bathroom rows
        SUM(
            CASE
                WHEN bath.canonical_bathrooms IS NULL THEN 1 ELSE 0
            END) AS missing_bathrooms,
        -- use CASE to count missing bedroom rows
        SUM(
            CASE
                WHEN bed.canonical_bedrooms IS NULL THEN 1 ELSE 0
            END) AS missing_bedrooms,
        -- use CASE to count missing square footage band rows
        SUM(
            CASE
                WHEN sb.min_sqft IS NULL THEN 1 ELSE 0
            END) AS missing_square_footage,
        -- use CASE to count rows that have any missing values
        SUM(
            CASE
                WHEN bath.canonical_bathrooms IS NULL
                    OR bed.canonical_bedrooms IS NULL
                    OR sb.min_sqft IS NULL
                THEN 1 ELSE 0
            END) AS incomplete_reports
    FROM UnitReport AS ur
    JOIN RentBand AS rb ON ur.rent_band_id = rb.rent_band_id
    -- use left join which keeps reports that have missing lookup values
    LEFT JOIN BedroomLabel AS bed ON ur.bedroom_label_id = bed.bedroom_label_id
    LEFT JOIN BathroomLabel AS bath ON ur.bathroom_label_id = bath.bathroom_label_id
    LEFT JOIN SquareFootageBand AS sb ON ur.sqft_band_id = sb.sqft_band_id
    -- filter out rows with invalid rent band
    WHERE rb.min_rent IS NOT NULL
    -- group by rent band
    GROUP BY rb.rent_band_id, rb.raw_label
)

-- display the values from the CTE
SELECT dq.rent_band, dq.total_reports, dq.missing_bathrooms, dq.missing_bedrooms,
    dq.missing_square_footage, dq.incomplete_reports,
    -- compute the percentage of incomplete reports for each rent band
    ROUND((dq.incomplete_reports / dq.total_reports) * 100, 2) AS incomplete_percent
FROM data_quality AS dq
ORDER BY incomplete_percent DESC;

-- Insight: Most of the queries discard rows that have invalid data, however
-- I never focused a query to compute the statistics of missing values. This query
-- will output the missing data count for each of the lookup tables on each rent band
-- and also computes the percentage of incomplete reports.
-- If the percentage is significant, it can be used to support the idea that the
-- data recorded for this filing cycle might not be as accurate due to the frequent missing
-- data. The missing data could actually be hiding behaviors that drastically influence the results,
-- but there would be no way of knowing.