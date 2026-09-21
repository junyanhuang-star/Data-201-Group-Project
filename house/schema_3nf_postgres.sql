-- ============================================================================
-- SF Rent Board Housing Inventory -- 3NF schema (PostgreSQL 14+)
--
-- Source : Rent_Board_Housing_Inventory_20260913.csv
--          550,201 rows / 28 columns; one row per rental unit per filing year.
--          `unique_id` is unique across all 550,201 rows.
--
-- Run    : psql -d rentboard -f schema_3nf_postgres.sql
--
-- Every decomposition is justified by a functional dependency measured on the
-- raw file. Violation rates are quoted in the comments; see README.md.
--
-- MySQL equivalent: schema_3nf.sql
-- ============================================================================

BEGIN;

DROP SCHEMA IF EXISTS rentboard CASCADE;
CREATE SCHEMA rentboard;
SET search_path TO rentboard, public;


-- ---------------------------------------------------------------------------
-- 1. Extract metadata
--    data_as_of and data_loaded_at hold exactly ONE distinct value across all
--    550,201 rows -- they describe the extract, not the unit.
-- ---------------------------------------------------------------------------
CREATE TABLE extract_batch (
    batch_id        smallint PRIMARY KEY,
    data_as_of      timestamp NOT NULL,   -- 2026-09-03 01:32:48
    data_loaded_at  timestamp NOT NULL,   -- 2026-09-10 06:11:33
    source_filename text    NOT NULL
);

COMMENT ON TABLE extract_batch IS
    'One row per CSV extract. Replaces two constant columns on 550k fact rows.';


-- ---------------------------------------------------------------------------
-- 2. Filing cycle
--    submission_year <-> case_type_name is a verified 1:1 bijection
--    (5 groups, 0 violations). Transitive dependency
--    unique_id -> submission_year -> case_type_name  =>  3NF violation.
-- ---------------------------------------------------------------------------
CREATE TABLE filing_cycle (
    submission_year smallint PRIMARY KEY
        CHECK (submission_year BETWEEN 2022 AND 2026),
    case_type_name  text NOT NULL UNIQUE
);


-- ---------------------------------------------------------------------------
-- 3. Geography
--    point -> analysis_neighborhood : 13,430 groups, 0 violations  (exact FD)
--    point -> supervisor_district   : 13,431 groups, 0 violations  (exact FD)
--
--    analysis_neighborhood -> supervisor_district DOES NOT hold: 25 of the 41
--    neighborhoods span 2-4 districts. So both hang off the point directly
--    rather than chaining neighborhood -> district.
--
--    CAUTION: `point` is a privacy-jittered coordinate, not a real address.
--    13,435 distinct points over 4,287 assessor blocks, and the same block
--    reports a different point on different filings. See section 4.
-- ---------------------------------------------------------------------------
CREATE TABLE neighborhood (
    neighborhood_id smallint PRIMARY KEY,
    name            text NOT NULL UNIQUE   -- 41 distinct values
);

CREATE TABLE supervisor_district (
    district_id smallint PRIMARY KEY CHECK (district_id BETWEEN 1 AND 11)
);

CREATE TABLE location_point (
    point_id        integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    longitude       numeric(12, 9) NOT NULL CHECK (longitude BETWEEN -123 AND -122),
    latitude        numeric(12, 9) NOT NULL CHECK (latitude  BETWEEN   37 AND   38),
    neighborhood_id smallint REFERENCES neighborhood(neighborhood_id),
    district_id     smallint REFERENCES supervisor_district(district_id),
    UNIQUE (longitude, latitude)
);

COMMENT ON COLUMN location_point.longitude IS
    'Parsed from the WKT "POINT (lon lat)" string. Jittered for privacy: '
    'does not identify a building.';

-- With PostGIS available, add:
--   ALTER TABLE location_point ADD COLUMN geom geography(Point, 4326)
--       GENERATED ALWAYS AS (ST_MakePoint(longitude, latitude)::geography) STORED;
--   CREATE INDEX ix_location_point_geom ON location_point USING GIST (geom);


-- ---------------------------------------------------------------------------
-- 4. Address labels
--    These are value lookups that de-duplicate repeated strings -- NOT property
--    entities. There is deliberately no `property` table, because the
--    anonymized data cannot support one:
--
--        block_num -> block_address                       83.7% of blocks violate
--        block_num -> year_property_built                 84.7% violate
--        block_num -> unit_count                          79.5% violate
--        block_num -> point                               84.6% violate
--        block_num + block_address -> year_property_built 56.4% violate
--
--    A block holds many buildings and the geometry is re-randomized per filing,
--    so nothing below the filing row can be keyed to a building.
-- ---------------------------------------------------------------------------
CREATE TABLE assessor_block (
    block_num varchar(5) PRIMARY KEY   -- 4,287 distinct; zero-padded, 4 and 5 chars
);

CREATE TABLE street_block (
    street_block_id smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    raw_label       text NOT NULL UNIQUE,  -- '400 Block of STOCKTON ST'
    block_range     smallint,              -- 400
    street_name     text                   -- 'STOCKTON ST'
);


-- ---------------------------------------------------------------------------
-- 5. Categorical lookups
--    Each raw label determines its own parsed bounds / canonical form, so the
--    bounds belong beside the label, not repeated on 550k fact rows.
--
--    bedroom_count (45 distinct) and bathroom_count (31 distinct) are free
--    text for what should be ~7 categories: 'One-Bedroom', '1br', '2 bedriin',
--    'Garage', '$D$61'. The raw string is kept so the cleaning is auditable and
--    reversible; the canonical value sits next to it.
-- ---------------------------------------------------------------------------
CREATE TABLE occupancy_type (
    occupancy_type_id smallint PRIMARY KEY,
    name              text NOT NULL UNIQUE   -- 4 values
);

CREATE TABLE bedroom_type (
    bedroom_type_id smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    raw_label       text NOT NULL UNIQUE,
    bedrooms        smallint CHECK (bedrooms BETWEEN 0 AND 10),  -- Studio -> 0, '5+' -> 5
    is_unparseable  boolean NOT NULL DEFAULT false,
    CHECK (is_unparseable = (bedrooms IS NULL))
);

CREATE TABLE bathroom_type (
    bathroom_type_id smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    raw_label        text NOT NULL UNIQUE,
    bathrooms        numeric(3, 1) CHECK (bathrooms BETWEEN 0 AND 10), -- 'One and a half' -> 1.5
    is_shared        boolean NOT NULL DEFAULT false,  -- 'Shared bathroom facilities
                                                      -- with other units' = SRO stock,
                                                      -- a category, not a missing value
    is_unparseable   boolean NOT NULL DEFAULT false
);

CREATE TABLE sqft_band (
    sqft_band_id smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    raw_label    text NOT NULL UNIQUE,   -- '501-750 Sq.Ft'
    sqft_min     integer,
    sqft_max     integer,                -- NULL for '4000+ Sq.Ft'
    is_unknown   boolean NOT NULL DEFAULT false,   -- 'Unknown' (38,392 rows)
    CHECK (sqft_max IS NULL OR sqft_min IS NULL OR sqft_max >= sqft_min)
);

CREATE TABLE rent_band (
    rent_band_id    smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    raw_label       text NOT NULL UNIQUE,   -- '$2251-$2500'
    rent_min        numeric(8, 2),
    rent_max        numeric(8, 2),          -- NULL for '$7000+'
    is_no_rent_paid boolean NOT NULL DEFAULT false,  -- '$0 (no rent paid by the
                                                     -- occupant)' is NOT a $0 rent
    CHECK (rent_max IS NULL OR rent_min IS NULL OR rent_max >= rent_min)
);

-- The 5 'Year Unknown (...)' phrases filers may pick instead of a date
-- (9,560 rows).
CREATE TABLE date_unknown_reason (
    reason_id      smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    label          text NOT NULL UNIQUE,
    approx_min_yrs smallint,   -- 'within past 5-10 years' -> 5
    approx_max_yrs smallint    -- 'within past 5-10 years' -> 10
);

CREATE TABLE date_range_type (
    date_range_type_id smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name               text NOT NULL UNIQUE  -- 'Occupied', 'Vacant',
                                             -- 'Occupied - Non Owner'
);


-- ---------------------------------------------------------------------------
-- 6. Fact table: one row per unit per filing year
--
--    Because the primary key is a single column, 2NF holds automatically --
--    every non-trivial FD from a proper subset of the key is impossible. All
--    the decomposition above was removing 3NF transitive dependencies.
--
--    building_unit_count and year_property_built stay HERE rather than on a
--    block table, for the reason in section 4: they are what this filer
--    reported this year, and the same block reports different values on
--    different filings.
--
--    Date/year handling. Measured: 33,402 rows carry a year with no date, and
--    0 rows carry a date with no year. So the year is NOT derivable from the
--    date in general, but where the date exists the year would be a derived,
--    transitively dependent copy. Rule enforced below: at most one of
--    (date, year, unknown-reason) is populated.
--      occupancy_or_vacancy_year -- a plausible parsed year
--      date_unknown_reason_id    -- one of the 5 'Year Unknown' phrases
--      occupancy_year_raw        -- the 25 junk strings ('20204', '2008.',
--                                   '21'); numeric values in the raw column
--                                   range from 3 to 5020
-- ---------------------------------------------------------------------------
CREATE TABLE unit_record (
    unique_id                 bigint PRIMARY KEY,
    batch_id                  smallint NOT NULL REFERENCES extract_batch(batch_id),
    submission_year           smallint NOT NULL REFERENCES filing_cycle(submission_year),
    signature_date            date,      -- 134 rows arrive dated year 0001; max 2026-12-02

    -- location (nullable: 3-80 rows are missing each)
    block_num                 varchar(5) REFERENCES assessor_block(block_num),
    street_block_id           smallint   REFERENCES street_block(street_block_id),
    point_id                  integer    REFERENCES location_point(point_id),

    -- building attributes AS REPORTED ON THIS FILING
    building_unit_count       numeric(6, 1) CHECK (building_unit_count >= 0),
                                          -- raw file mixes '70' and '72.0'; max 720
    year_property_built       smallint CHECK (year_property_built BETWEEN 1800 AND 2030),

    -- unit attributes
    occupancy_type_id         smallint NOT NULL REFERENCES occupancy_type(occupancy_type_id),
    bedroom_type_id           smallint REFERENCES bedroom_type(bedroom_type_id),
    bathroom_type_id          smallint REFERENCES bathroom_type(bathroom_type_id),
    sqft_band_id              smallint REFERENCES sqft_band(sqft_band_id),
    rent_band_id              smallint REFERENCES rent_band(rent_band_id),

    -- occupancy / vacancy timing
    occupancy_or_vacancy_date date,
    occupancy_or_vacancy_year smallint CHECK (occupancy_or_vacancy_year
                                               BETWEEN 1900 AND 2026),
    date_unknown_reason_id    smallint REFERENCES date_unknown_reason(reason_id),
    occupancy_year_raw        text,
    vacancy_date              date,      -- 21,184 rows (3.9%); populated for 56% of
                                         -- 'Vacant' units and <0.2% of every other type
    past_occupancy            boolean,   -- Yes/No, 27.7% NULL

    other_utilities_raw       text,      -- free text kept for audit; parsed into
                                         -- record_utility_included below

    -- At most one representation of the move-in/vacancy timing is stored.
    CONSTRAINT ck_one_occ_date_form CHECK (
        (occupancy_or_vacancy_date IS NOT NULL)::int
      + (occupancy_or_vacancy_year IS NOT NULL)::int
      + (date_unknown_reason_id    IS NOT NULL)::int
      + (occupancy_year_raw        IS NOT NULL)::int <= 1
    )
);

CREATE INDEX ix_unit_record_year  ON unit_record (submission_year);
CREATE INDEX ix_unit_record_point ON unit_record (point_id);
CREATE INDEX ix_unit_record_rent  ON unit_record (rent_band_id, submission_year);
CREATE INDEX ix_unit_record_block ON unit_record (block_num, submission_year);
CREATE INDEX ix_unit_record_occ   ON unit_record (occupancy_type_id, submission_year);

COMMENT ON TABLE unit_record IS
    'Grain: one rental unit as reported in one annual filing. There is no '
    'identifier linking the same physical unit across years -- the source does '
    'not provide one.';


-- ---------------------------------------------------------------------------
-- 7. Included utilities -- resolves a 1NF violation
--    The raw file has four Y/N columns PLUS base_rent_includes_other_utilities,
--    a free-text field with 94 distinct values that is genuinely multi-valued:
--    'parking & heat', 'cable and internet', 'pest control/valet trash'.
--    A repeating group across five columns, with a comma-bag in the fifth, is
--    not atomic. Both collapse into one junction table.
-- ---------------------------------------------------------------------------
CREATE TABLE utility (
    utility_id  smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name        text NOT NULL UNIQUE,   -- water_sewer, natural_gas, electricity,
                                        -- refuse_recycling, heat, internet, parking, ...
    is_standard boolean NOT NULL DEFAULT false  -- true for the 4 checkbox utilities
);

CREATE TABLE record_utility_included (
    unique_id  bigint   NOT NULL REFERENCES unit_record(unique_id) ON DELETE CASCADE,
    utility_id smallint NOT NULL REFERENCES utility(utility_id),
    PRIMARY KEY (unique_id, utility_id)
);

CREATE INDEX ix_record_utility_utility ON record_utility_included (utility_id);


-- ---------------------------------------------------------------------------
-- 8. Occupancy history -- resolves the other 1NF violation
--    occupancy_or_vacancy_date_history is a JSON array of
--    {date_range_type, start_date, end_date} objects, non-null on 81,004 rows.
--    Every array currently holds exactly 1 element, but the array shape means
--    the source may emit more -- so it is modeled 1:N, not flattened to columns.
-- ---------------------------------------------------------------------------
CREATE TABLE occupancy_history (
    history_id         bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    unique_id          bigint   NOT NULL REFERENCES unit_record(unique_id) ON DELETE CASCADE,
    seq_no             smallint NOT NULL,  -- position in the source JSON array
    date_range_type_id smallint REFERENCES date_range_type(date_range_type_id),
                                           -- some entries have a null type
    start_date         date,
    end_date           date,
    UNIQUE (unique_id, seq_no),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE INDEX ix_occupancy_history_unit ON occupancy_history (unique_id);


-- ---------------------------------------------------------------------------
-- 9. Seed data for the small fixed lookups
-- ---------------------------------------------------------------------------
INSERT INTO filing_cycle (submission_year, case_type_name) VALUES
    (2022, 'Housing Inventory - Unit information (2022)'),
    (2023, 'Housing Inventory - Unit information (2023)'),
    (2024, 'Housing Inventory - Unit information (2024)'),
    (2025, 'Housing Inventory - Unit information (2025)'),
    (2026, 'Housing Inventory - Unit information (2026)');

INSERT INTO supervisor_district (district_id)
SELECT generate_series(1, 11);

INSERT INTO occupancy_type (occupancy_type_id, name) VALUES
    (1, 'Occupied by non-owner'),   -- 483,575 rows
    (2, 'Vacant'),                  --  36,079
    (3, 'Occupied by owner'),       --  27,921
    (4, 'Non-Residential');         --   2,626

INSERT INTO date_range_type (name) VALUES
    ('Occupied'), ('Vacant'), ('Occupied - Non Owner');

INSERT INTO date_unknown_reason (label, approx_min_yrs, approx_max_yrs) VALUES
    ('Year Unknown (within past five years)',   0,    5),
    ('Year Unknown (within past 5-10 years)',   5,   10),
    ('Year Unknown (within past 10-20 years)', 10,   20),
    ('Year Unknown (more than 20 years)',      20, NULL),
    ('Year unknown (no information available)', NULL, NULL);

INSERT INTO utility (name, is_standard) VALUES
    ('water_sewer',      true),
    ('natural_gas',      true),
    ('electricity',      true),
    ('refuse_recycling', true),
    ('heat',             false),
    ('internet',         false),
    ('cable',            false),
    ('parking',          false),
    ('pest_control',     false),
    ('hot_water',        false),
    ('other',            false);

INSERT INTO sqft_band (raw_label, sqft_min, sqft_max, is_unknown) VALUES
    ('0-250 Sq.Ft',       0,  250, false),
    ('251-500 Sq.Ft',   251,  500, false),
    ('501-750 Sq.Ft',   501,  750, false),
    ('751-1000 Sq.Ft',  751, 1000, false),
    ('1001-1250 Sq.Ft',1001, 1250, false),
    ('1251-1500 Sq.Ft',1251, 1500, false),
    ('1501-1750 Sq.Ft',1501, 1750, false),
    ('1751-2000 Sq.Ft',1751, 2000, false),
    ('2001-2250 Sq.Ft',2001, 2250, false),
    ('2251-2500 Sq.Ft',2251, 2500, false),
    ('2501-2750 Sq.Ft',2501, 2750, false),
    ('2751-3000 Sq.Ft',2751, 3000, false),
    ('3001-3250 Sq.Ft',3001, 3250, false),
    ('3251-3500 Sq.Ft',3251, 3500, false),
    ('3501-3750 Sq.Ft',3501, 3750, false),
    ('3751-4000 Sq.Ft',3751, 4000, false),
    ('4000+ Sq.Ft',    4000, NULL, false),
    ('Unknown',        NULL, NULL, true),
    ('0-250 Sq.ft',       0,  250, false);   -- 1 row, case typo

COMMIT;

-- ============================================================================
-- Lossless-decomposition check: reconstructs the original 28-column flat file.
-- Should return exactly 550,201 rows.
-- ============================================================================
-- SELECT r.unique_id,
--        r.block_num,
--        r.building_unit_count                          AS unit_count,
--        f.case_type_name,
--        r.submission_year,
--        sb.raw_label                                   AS block_address,
--        ot.name                                        AS occupancy_type,
--        r.occupancy_or_vacancy_date,
--        COALESCE(EXTRACT(YEAR FROM r.occupancy_or_vacancy_date)::text,
--                 r.occupancy_or_vacancy_year::text,
--                 dur.label,
--                 r.occupancy_year_raw)                 AS occupancy_or_vacancy_date_year,
--        bd.raw_label                                   AS bedroom_count,
--        ba.raw_label                                   AS bathroom_count,
--        sf.raw_label                                   AS square_footage,
--        rb.raw_label                                   AS monthly_rent,
--        bool_or(u.name = 'water_sewer')                AS incl_water_sewer,
--        bool_or(u.name = 'natural_gas')                AS incl_natural_gas,
--        bool_or(u.name = 'electricity')                AS incl_electricity,
--        bool_or(u.name = 'refuse_recycling')           AS incl_refuse_recycling,
--        r.other_utilities_raw,
--        r.past_occupancy,
--        r.vacancy_date,
--        r.signature_date,
--        r.year_property_built,
--        format('POINT (%s %s)', lp.longitude, lp.latitude) AS point,
--        n.name                                         AS analysis_neighborhood,
--        lp.district_id                                 AS supervisor_district,
--        eb.data_as_of, eb.data_loaded_at
--   FROM unit_record r
--   JOIN filing_cycle    f  USING (submission_year)
--   JOIN extract_batch   eb USING (batch_id)
--   JOIN occupancy_type  ot USING (occupancy_type_id)
--   LEFT JOIN street_block        sb  USING (street_block_id)
--   LEFT JOIN bedroom_type        bd  USING (bedroom_type_id)
--   LEFT JOIN bathroom_type       ba  USING (bathroom_type_id)
--   LEFT JOIN sqft_band           sf  USING (sqft_band_id)
--   LEFT JOIN rent_band           rb  USING (rent_band_id)
--   LEFT JOIN location_point      lp  USING (point_id)
--   LEFT JOIN neighborhood        n   USING (neighborhood_id)
--   LEFT JOIN date_unknown_reason dur ON dur.reason_id = r.date_unknown_reason_id
--   LEFT JOIN record_utility_included ru ON ru.unique_id = r.unique_id
--   LEFT JOIN utility             u   ON u.utility_id = ru.utility_id
--  GROUP BY r.unique_id, f.case_type_name, sb.raw_label, ot.name, bd.raw_label,
--           ba.raw_label, sf.raw_label, rb.raw_label, lp.longitude, lp.latitude,
--           n.name, lp.district_id, dur.label, eb.data_as_of, eb.data_loaded_at;