-- ============================================================================
-- SF Rent Board Housing Inventory -- 3NF schema (MySQL 8.0.16+)
--
-- Source : Rent_Board_Housing_Inventory_20260913.csv
--          550,201 rows / 28 columns; one row per rental unit per filing year.
--          `unique_id` is unique across all 550,201 rows (0 duplicates).
--
-- Run    : mysql -u <user> -p < schema_3nf.sql
--          then  .venv/bin/python house/load_3nf.py
--          then  mysql -u <user> -p --local-infile=1 < load_3nf.sql
--          then  mysql -u <user> -p < validate_3nf.sql
--
-- Every decomposition below is justified by a functional dependency measured on
-- the raw file; violation rates are quoted inline. Full cleaning assessment and
-- FD evidence: README.md. PostgreSQL mirror: schema_3nf_postgres.sql.
--
-- Division of labour between this file and the loader:
--   * This file seeds every FIXED vocabulary (filing cycles, districts,
--     occupancy types, quality flags, utilities, and the rent/sqft bands the
--     form offers). Those ids are the source of truth; load_3nf.py mirrors them
--     in BAND_IDS / UTILITY_IDS / FLAG_IDS and aborts if the CSV produces a
--     label this file does not list.
--   * load_3nf.py populates the DATA-DERIVED dimensions (neighborhood,
--     location_point, assessor_block, street_block, bedroom_type,
--     bathroom_type, duplicate_group) and all fact tables.
-- ============================================================================

DROP DATABASE IF EXISTS RentBoardDB;
-- The raw labels this schema preserves differ from each other by case alone
-- ("Studio"/"studio", "0-250 Sq.Ft"/"0-250 Sq.ft", "Two-Bedroom"/"Two-bedroom",
-- and the lower-cased copy of the shared-bathroom phrase). Under MySQL's
-- default utf8mb4_0900_ai_ci they collide on the UNIQUE raw_label keys, so the
-- whole database is accent- and case-sensitive.
CREATE DATABASE RentBoardDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs;
USE RentBoardDB;


-- ---------------------------------------------------------------------------
-- 1. Extract metadata
--    data_as_of and data_loaded_at hold exactly ONE distinct value across all
--    550,201 rows -- they describe the extract, not the unit. Repeating them on
--    every fact row is pure redundancy.
-- ---------------------------------------------------------------------------
CREATE TABLE extract_batch (
    batch_id        SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    data_as_of      DATETIME     NOT NULL,
    data_loaded_at  DATETIME     NOT NULL,
    source_filename VARCHAR(120) NOT NULL,
    row_count       INT UNSIGNED NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 2. Filing cycle
--    submission_year <-> case_type_name is a verified 1:1 bijection (5 groups,
--    0 violations): "Housing Inventory - Unit information (2024)" carries no
--    information beyond the year. The transitive dependency
--    unique_id -> submission_year -> case_type_name is a 3NF violation.
-- ---------------------------------------------------------------------------
CREATE TABLE filing_cycle (
    submission_year SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    case_type_name  VARCHAR(60) NOT NULL UNIQUE,
    CONSTRAINT ck_filing_year CHECK (submission_year BETWEEN 2022 AND 2026)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 3. Geography
--    point -> analysis_neighborhood : 13,430 groups, 0 violations (exact FD)
--    point -> supervisor_district   : 13,431 groups, 0 violations (exact FD)
--    analysis_neighborhood -> supervisor_district DOES NOT hold: 25 of the 41
--    neighborhoods span 2-4 districts. So both hang off the point directly
--    rather than chaining neighborhood -> district.
--
--    CAUTION: `point` is a privacy-jittered coordinate, not a real address.
--    13,435 distinct points over 4,287 assessor blocks, and the same block
--    reports a different point on different filings. See section 4.
-- ---------------------------------------------------------------------------
CREATE TABLE neighborhood (
    neighborhood_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    name            VARCHAR(60) NOT NULL UNIQUE          -- 41 distinct values
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE supervisor_district (
    district_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    CONSTRAINT ck_district_range CHECK (district_id BETWEEN 1 AND 11)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE location_point (
    point_id        INT UNSIGNED NOT NULL PRIMARY KEY,
    longitude       DECIMAL(12, 9) NOT NULL,   -- parsed from WKT "POINT (lon lat)"
    latitude        DECIMAL(12, 9) NOT NULL,
    neighborhood_id TINYINT UNSIGNED NULL,
    district_id     TINYINT UNSIGNED NULL,
    UNIQUE KEY uq_point (longitude, latitude),
    CONSTRAINT ck_point_lon CHECK (longitude BETWEEN -123 AND -122),
    CONSTRAINT ck_point_lat CHECK (latitude  BETWEEN   37 AND   38),
    CONSTRAINT fk_point_hood     FOREIGN KEY (neighborhood_id) REFERENCES neighborhood(neighborhood_id),
    CONSTRAINT fk_point_district FOREIGN KEY (district_id)     REFERENCES supervisor_district(district_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 4. Address labels
--    These are value lookups that de-duplicate repeated strings -- NOT property
--    entities. There is deliberately no `property` table, because the
--    anonymized data cannot support one:
--
--        block_num -> block_address                       3,588 of 4,287 blocks violate (83.7%)
--        block_num -> year_property_built                 84.7% violate
--        block_num -> unit_count                          79.5% violate
--        block_num -> point                               84.6% violate
--        block_num + block_address -> year_property_built 56.4% violate
--
--    A block holds many buildings and the geometry is re-randomized per filing,
--    so nothing below the filing row can be keyed to a building.
-- ---------------------------------------------------------------------------
CREATE TABLE assessor_block (
    block_num VARCHAR(5) NOT NULL PRIMARY KEY   -- 4,287 distinct; zero-padded,
                                                -- 532,161 rows 4-char, 18,034 5-char
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE street_block (
    street_block_id SMALLINT UNSIGNED NOT NULL PRIMARY KEY,   -- 7,677 distinct
    raw_label       VARCHAR(120) NOT NULL UNIQUE,  -- "400 Block of STOCKTON ST"
    block_range     SMALLINT UNSIGNED NULL,        -- 400
    street_name     VARCHAR(80) NULL               -- "STOCKTON ST"
    -- 7,676 of 7,677 match '^(\d+) Block of (.+)$'; the one exception is the
    -- truncated "0 Block of", which parses to block_range=0, street_name NULL.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 5. Categorical lookups
--    Each raw label determines its own parsed bounds / canonical form, so the
--    bounds belong beside the label, not repeated on 550k fact rows.
--
--    bedroom_count (45 distinct) and bathroom_count (31 distinct) are free text
--    for what should be ~7 categories: "One-Bedroom", "1br", "2 bedriin",
--    "Garage", "$D$61". The raw string is kept so the cleaning is auditable and
--    reversible; the canonical value sits next to it.
-- ---------------------------------------------------------------------------
CREATE TABLE occupancy_type (
    occupancy_type_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    name              VARCHAR(30) NOT NULL UNIQUE          -- 4 values
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE bedroom_type (
    bedroom_type_id SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    raw_label       VARCHAR(40) NOT NULL UNIQUE,
    bedrooms        TINYINT UNSIGNED NULL,          -- "Studio" -> 0, "5+" -> 5
    is_unparseable  BOOLEAN NOT NULL DEFAULT FALSE, -- "Garage", "Vacant", "$D$61"
    CONSTRAINT ck_bedroom_range  CHECK (bedrooms BETWEEN 0 AND 10),
    CONSTRAINT ck_bedroom_parsed CHECK (is_unparseable = (bedrooms IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE bathroom_type (
    bathroom_type_id SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    raw_label        VARCHAR(60) NOT NULL UNIQUE,
    bathrooms        DECIMAL(3, 1) NULL,             -- "One and a half" -> 1.5
    is_shared        BOOLEAN NOT NULL DEFAULT FALSE, -- "Shared bathroom facilities
                                                     -- with other units" = SRO stock:
                                                     -- a category, not a missing value
    is_unparseable   BOOLEAN NOT NULL DEFAULT FALSE, -- incl. the 18 rows holding
                                                     -- bedroom text, and "E3"
    CONSTRAINT ck_bathroom_range CHECK (bathrooms BETWEEN 0 AND 10)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE sqft_band (
    sqft_band_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    raw_label    VARCHAR(30) NOT NULL UNIQUE,        -- "501-750 Sq.Ft"
    sqft_min     SMALLINT UNSIGNED NULL,
    sqft_max     SMALLINT UNSIGNED NULL,             -- NULL for "4000+ Sq.Ft"
    is_unknown   BOOLEAN NOT NULL DEFAULT FALSE,     -- "Unknown" (38,392 rows)
    CONSTRAINT ck_sqft_order CHECK (sqft_max IS NULL OR sqft_min IS NULL OR sqft_max >= sqft_min)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE TABLE rent_band (
    rent_band_id    TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    raw_label       VARCHAR(40) NOT NULL UNIQUE,     -- "$2251-$2500"
    rent_min        DECIMAL(8, 2) NULL,
    rent_max        DECIMAL(8, 2) NULL,              -- NULL for "$7000+"
    is_no_rent_paid BOOLEAN NOT NULL DEFAULT FALSE,  -- "$0 (no rent paid by the
                                                     -- occupant)" is NOT a $0 rent
    overlaps_other  BOOLEAN NOT NULL DEFAULT FALSE,  -- the two malformed bands that
                                                     -- overlap their neighbour
    CONSTRAINT ck_rent_order CHECK (rent_max IS NULL OR rent_min IS NULL OR rent_max >= rent_min)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

-- The 5 "Year Unknown (...)" phrases a filer may pick instead of a date
-- (9,560 rows).
CREATE TABLE date_unknown_reason (
    reason_id      TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    label          VARCHAR(60) NOT NULL UNIQUE,
    approx_min_yrs TINYINT UNSIGNED NULL,   -- "within past 5-10 years" -> 5
    approx_max_yrs TINYINT UNSIGNED NULL    -- "within past 5-10 years" -> 10
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

-- date_range_type as it appears inside the history JSON is not canonical:
-- Occupied 35,859 / Vacant 36,598 / null 8,535 / "Occupied - Non Owner" 9 /
-- "occupied" 2 / "vacant" 1. Only the three canonical spellings are stored;
-- the loader case-folds the strays and leaves typeless entries NULL.
CREATE TABLE date_range_type (
    date_range_type_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    name               VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

-- ---------------------------------------------------------------------------
-- 5b. Data-quality flags
--     Integrity problems are recorded, never silently dropped. A row can carry
--     several flags at once, so this is a junction (section 9), not a column.
--     `rejected_value` preserves whatever had to be discarded to satisfy the
--     column's domain -- an out-of-MySQL-range date, or a year that contradicts
--     its own date.
-- ---------------------------------------------------------------------------
CREATE TABLE quality_flag (
    flag_id     TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    code        VARCHAR(40)  NOT NULL UNIQUE,
    description VARCHAR(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 5c. Duplicate groups
--     40,797 rows are byte-identical to another row on all 27 non-key columns,
--     spread over 21,008 groups. They cannot be resolved: at this grain two
--     identical studios in the same building, same filing year, with banded
--     rent and a jittered coordinate are genuinely indistinguishable from a
--     double submission. They are loaded in full and tagged, so any analysis
--     can choose to collapse them.
-- ---------------------------------------------------------------------------
CREATE TABLE duplicate_group (
    dup_group_id INT UNSIGNED NOT NULL PRIMARY KEY,
    content_hash CHAR(32) NOT NULL UNIQUE,      -- md5 of the 27 non-id columns
    member_count INT UNSIGNED NOT NULL,
    CONSTRAINT ck_dup_members CHECK (member_count > 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 6. Fact table: one row per unit per filing year
--
--    Because the primary key is a single column, 2NF holds automatically --
--    a non-trivial FD from a proper subset of the key is impossible. All the
--    decomposition above was removing 3NF transitive dependencies.
--
--    building_unit_count and year_property_built stay HERE rather than on a
--    block table, for the reason in section 4: they are what this filer
--    reported this year, and the same block reports different values on
--    different filings.
--
--    Date / year handling. Measured: 447,141 rows carry both a date and a year,
--    33,402 carry a year with no date, and 0 carry a date with no year. Where
--    the date exists the year is a derived, transitively dependent copy, so it
--    is not stored. All 19 rows whose year contradicts its own date turn out to
--    be rows whose date is itself out of range, so on this extract the
--    `year_disagrees_with_date` flag fires 0 times and the contradicting year
--    survives in occupancy_year_raw; the flag guards future extracts.
--    Exactly one of these four is populated:
--      occupancy_or_vacancy_date  -- a real date in 1900..2026
--      occupancy_or_vacancy_year  -- a plausible parsed year, no date given
--      date_unknown_reason_id     -- one of the 5 "Year Unknown" phrases
--      occupancy_year_raw         -- the ~50 junk strings ("20204", "2008.", "21")
--
--    MySQL's DATE domain starts at 1000-01-01, and the file contains dates
--    below it (year 0002, 0285, 0987) as well as impossible futures (3022,
--    5020). Those are stored as NULL plus a quality flag carrying the original
--    text; see section 9.
-- ---------------------------------------------------------------------------
CREATE TABLE unit_record (
    unique_id                 BIGINT NOT NULL PRIMARY KEY,
    batch_id                  SMALLINT UNSIGNED NOT NULL,
    submission_year           SMALLINT UNSIGNED NOT NULL,
    signature_date            DATE NULL,   -- 136 rows rejected (134 dated year 0001,
                                           -- plus 1974 and 1977)

    -- location (nullable: 3-80 rows are missing each)
    block_num                 VARCHAR(5) NULL,
    street_block_id           SMALLINT UNSIGNED NULL,
    point_id                  INT UNSIGNED NULL,

    -- building attributes AS REPORTED ON THIS FILING
    building_unit_count       DECIMAL(6, 1) NULL,   -- raw file mixes "70" and "72.0";
                                                    -- max 720; 3,560 rows report 0
    year_property_built       SMALLINT UNSIGNED NULL,

    -- unit attributes
    occupancy_type_id         TINYINT UNSIGNED NOT NULL,
    bedroom_type_id           SMALLINT UNSIGNED NULL,
    bathroom_type_id          SMALLINT UNSIGNED NULL,
    sqft_band_id              TINYINT UNSIGNED NULL,
    rent_band_id              TINYINT UNSIGNED NULL,

    -- occupancy / vacancy timing
    occupancy_or_vacancy_date DATE NULL,
    occupancy_or_vacancy_year SMALLINT UNSIGNED NULL,
    date_unknown_reason_id    TINYINT UNSIGNED NULL,
    occupancy_year_raw        VARCHAR(20) NULL,
    vacancy_date              DATE NULL,   -- 21,184 rows (3.9%); 56% of "Vacant"
                                           -- units and <0.2% of every other type
    past_occupancy            BOOLEAN NULL,-- Yes/No, 27.7% NULL

    other_utilities_raw       VARCHAR(255) NULL,  -- free text kept for audit; parsed
                                                  -- into record_utility_included
    dup_group_id              INT UNSIGNED NULL,  -- non-NULL iff this row has a twin

    CONSTRAINT fk_ur_batch    FOREIGN KEY (batch_id)               REFERENCES extract_batch(batch_id),
    CONSTRAINT fk_ur_cycle    FOREIGN KEY (submission_year)        REFERENCES filing_cycle(submission_year),
    CONSTRAINT fk_ur_block    FOREIGN KEY (block_num)              REFERENCES assessor_block(block_num),
    CONSTRAINT fk_ur_street   FOREIGN KEY (street_block_id)        REFERENCES street_block(street_block_id),
    CONSTRAINT fk_ur_point    FOREIGN KEY (point_id)               REFERENCES location_point(point_id),
    CONSTRAINT fk_ur_occtype  FOREIGN KEY (occupancy_type_id)      REFERENCES occupancy_type(occupancy_type_id),
    CONSTRAINT fk_ur_bed      FOREIGN KEY (bedroom_type_id)        REFERENCES bedroom_type(bedroom_type_id),
    CONSTRAINT fk_ur_bath     FOREIGN KEY (bathroom_type_id)       REFERENCES bathroom_type(bathroom_type_id),
    CONSTRAINT fk_ur_sqft     FOREIGN KEY (sqft_band_id)           REFERENCES sqft_band(sqft_band_id),
    CONSTRAINT fk_ur_rent     FOREIGN KEY (rent_band_id)           REFERENCES rent_band(rent_band_id),
    CONSTRAINT fk_ur_reason   FOREIGN KEY (date_unknown_reason_id) REFERENCES date_unknown_reason(reason_id),
    CONSTRAINT fk_ur_dup      FOREIGN KEY (dup_group_id)           REFERENCES duplicate_group(dup_group_id),

    CONSTRAINT ck_ur_built CHECK (year_property_built BETWEEN 1800 AND 2030),
    CONSTRAINT ck_ur_units CHECK (building_unit_count >= 0),
    CONSTRAINT ck_ur_occ_date CHECK (occupancy_or_vacancy_date BETWEEN '1900-01-01' AND '2026-12-31'),
    CONSTRAINT ck_ur_vac_date CHECK (vacancy_date              BETWEEN '1900-01-01' AND '2026-12-31'),
    CONSTRAINT ck_ur_sig_date CHECK (signature_date            BETWEEN '2022-01-01' AND '2026-12-31'),
    CONSTRAINT ck_ur_occ_year CHECK (occupancy_or_vacancy_year BETWEEN 1900 AND 2026),

    -- At most one representation of the move-in / vacancy timing is stored.
    CONSTRAINT ck_one_occ_date_form CHECK (
        (CASE WHEN occupancy_or_vacancy_date IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN occupancy_or_vacancy_year IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN date_unknown_reason_id    IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN occupancy_year_raw        IS NOT NULL THEN 1 ELSE 0 END) <= 1
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE INDEX ix_unit_record_year  ON unit_record (submission_year);
CREATE INDEX ix_unit_record_point ON unit_record (point_id);
CREATE INDEX ix_unit_record_rent  ON unit_record (rent_band_id, submission_year);
CREATE INDEX ix_unit_record_block ON unit_record (block_num, submission_year);
CREATE INDEX ix_unit_record_occ   ON unit_record (occupancy_type_id, submission_year);
CREATE INDEX ix_unit_record_dup   ON unit_record (dup_group_id);


-- ---------------------------------------------------------------------------
-- 7. Included utilities -- resolves a 1NF violation
--    The raw file has four Y/N columns PLUS base_rent_includes_other_utilities,
--    a free-text field with 94 distinct values that is genuinely multi-valued:
--    "parking & heat", "cable and internet", "pest control/valet trash".
--    A repeating group across five columns, with a comma-bag in the fifth, is
--    not atomic. Both collapse into one junction table.
-- ---------------------------------------------------------------------------
CREATE TABLE utility (
    utility_id  TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    name        VARCHAR(40) NOT NULL UNIQUE,
    is_standard BOOLEAN NOT NULL DEFAULT FALSE   -- TRUE for the 4 checkbox utilities
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

--    The two provenance flags are what makes the merge reversible: the same
--    utility can be asserted by its checkbox and named again in the free-text
--    field ("water and trash" on a row whose water/sewer box is ticked), and
--    without them the four Y/N columns could not be reconstructed.
CREATE TABLE record_utility_included (
    unique_id       BIGINT NOT NULL,
    utility_id      TINYINT UNSIGNED NOT NULL,
    from_checkbox   BOOLEAN NOT NULL DEFAULT FALSE,
    from_other_text BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (unique_id, utility_id),
    CONSTRAINT ck_rui_source  CHECK (from_checkbox OR from_other_text),
    CONSTRAINT fk_rui_record  FOREIGN KEY (unique_id)  REFERENCES unit_record(unique_id) ON DELETE CASCADE,
    CONSTRAINT fk_rui_utility FOREIGN KEY (utility_id) REFERENCES utility(utility_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE INDEX ix_record_utility_utility ON record_utility_included (utility_id);


-- ---------------------------------------------------------------------------
-- 8. Occupancy history -- resolves the other 1NF violation
--    occupancy_or_vacancy_date_history is a JSON array of
--    {date_range_type, start_date, end_date} objects, non-null on 81,004 rows.
--    Every array currently holds exactly 1 element, but the array shape means
--    the source may emit more -- so it is modeled 1:N, not flattened to columns.
-- ---------------------------------------------------------------------------
CREATE TABLE occupancy_history (
    history_id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    unique_id          BIGINT NOT NULL,
    seq_no             TINYINT UNSIGNED NOT NULL,  -- position in the source array
    date_range_type_id TINYINT UNSIGNED NULL,      -- 8,535 entries carry no type
    start_date         DATE NULL,
    end_date           DATE NULL,
    -- 418 entries report a range that ends before it starts. Both dates are
    -- what the filer submitted, so neither is invented away and no CHECK
    -- rejects the row -- it is marked instead. (A CHECK here would be worse
    -- than useless: LOAD DATA downgrades a constraint failure to a warning and
    -- silently discards the row.)
    is_reversed        BOOLEAN GENERATED ALWAYS AS
                           (end_date IS NOT NULL AND start_date IS NOT NULL
                            AND end_date < start_date) STORED,
    UNIQUE KEY uq_history (unique_id, seq_no),
    CONSTRAINT fk_hist_record FOREIGN KEY (unique_id)          REFERENCES unit_record(unique_id) ON DELETE CASCADE,
    CONSTRAINT fk_hist_type   FOREIGN KEY (date_range_type_id) REFERENCES date_range_type(date_range_type_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;


-- ---------------------------------------------------------------------------
-- 9. Quality-flag junction
-- ---------------------------------------------------------------------------
CREATE TABLE record_quality_flag (
    unique_id      BIGINT NOT NULL,
    flag_id        TINYINT UNSIGNED NOT NULL,
    rejected_value VARCHAR(40) NULL,   -- the value that had to be discarded, if any
    PRIMARY KEY (unique_id, flag_id),
    CONSTRAINT fk_rqf_record FOREIGN KEY (unique_id) REFERENCES unit_record(unique_id) ON DELETE CASCADE,
    CONSTRAINT fk_rqf_flag   FOREIGN KEY (flag_id)   REFERENCES quality_flag(flag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs;

CREATE INDEX ix_record_quality_flag ON record_quality_flag (flag_id);


-- ===========================================================================
-- 10. Seed data for the fixed vocabularies
--     load_3nf.py mirrors these ids and aborts if the CSV yields a label that
--     is not listed here.
-- ===========================================================================

INSERT INTO extract_batch (batch_id, data_as_of, data_loaded_at, source_filename, row_count) VALUES
    (1, '2026-09-03 01:32:48', '2026-09-10 06:11:33',
        'Rent_Board_Housing_Inventory_20260913.csv', 550201);

INSERT INTO filing_cycle (submission_year, case_type_name) VALUES
    (2022, 'Housing Inventory - Unit information (2022)'),
    (2023, 'Housing Inventory - Unit information (2023)'),
    (2024, 'Housing Inventory - Unit information (2024)'),
    (2025, 'Housing Inventory - Unit information (2025)'),
    (2026, 'Housing Inventory - Unit information (2026)');

INSERT INTO supervisor_district (district_id) VALUES
    (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11);

INSERT INTO occupancy_type (occupancy_type_id, name) VALUES
    (1, 'Occupied by non-owner'),   -- 483,575 rows
    (2, 'Vacant'),                  --  36,079
    (3, 'Occupied by owner'),       --  27,921
    (4, 'Non-Residential');         --   2,626

INSERT INTO date_range_type (date_range_type_id, name) VALUES
    (1, 'Occupied'),
    (2, 'Vacant'),
    (3, 'Occupied - Non Owner');

INSERT INTO date_unknown_reason (reason_id, label, approx_min_yrs, approx_max_yrs) VALUES
    (1, 'Year Unknown (within past five years)',    0,    5),   -- 1,315 rows
    (2, 'Year Unknown (within past 5-10 years)',    5,   10),   --   966
    (3, 'Year Unknown (within past 10-20 years)',  10,   20),   -- 1,840
    (4, 'Year Unknown (more than 20 years)',       20, NULL),   -- 3,588
    (5, 'Year unknown (no information available)', NULL, NULL); -- 1,851

INSERT INTO quality_flag (flag_id, code, description) VALUES
    (1,  'occupancy_date_out_of_range',  'occupancy_or_vacancy_date fell outside 1900-2026; stored NULL, original text in rejected_value'),
    (2,  'signature_date_out_of_range',  'signature_date fell outside the 2022-2026 filing window; stored NULL'),
    (3,  'vacancy_date_out_of_range',    'vacancy_date fell outside 1900-2026; stored NULL'),
    (4,  'year_disagrees_with_date',     'occupancy_or_vacancy_date_year contradicted the year of occupancy_or_vacancy_date; the year was dropped as derivable'),
    (5,  'occupancy_after_signature',    'the unit was reported occupied after the date the filing was signed'),
    (6,  'occupancy_in_future',          'occupancy_or_vacancy_date is later than the extract date'),
    (7,  'vacant_with_rent',             'occupancy_type is Vacant yet a rent band was reported'),
    (8,  'tenant_without_rent',          'occupancy_type is Occupied by non-owner yet no rent band was reported'),
    (9,  'bathroom_holds_bedroom_text',  'bathroom_count contained a bedroom phrase'),
    (10, 'zero_unit_count',              'unit_count reported as 0 for a building that is filing on a unit'),
    (11, 'occupancy_year_unparseable',   'occupancy_or_vacancy_date_year was neither a plausible year nor a known phrase; kept verbatim in occupancy_year_raw');

INSERT INTO utility (utility_id, name, is_standard) VALUES
    (1,  'water_sewer',      TRUE),
    (2,  'natural_gas',      TRUE),
    (3,  'electricity',      TRUE),
    (4,  'refuse_recycling', TRUE),
    (5,  'heat',             FALSE),
    (6,  'hot_water',        FALSE),
    (7,  'internet',         FALSE),
    (8,  'cable',            FALSE),
    (9,  'parking',          FALSE),
    (10, 'storage',          FALSE),
    (11, 'pest_control',     FALSE),
    (12, 'laundry',          FALSE),
    (13, 'janitorial',       FALSE),
    (14, 'solar',            FALSE),
    (15, 'all_utilities',    FALSE),
    (16, 'other',            FALSE);

-- Square-footage bands exactly as the form emits them. Band 2 is a one-row
-- casing typo of band 1; band 18 is open-ended; band 19 is the explicit
-- "Unknown" choice (38,392 rows), which is a stated non-answer, not a NULL.
INSERT INTO sqft_band (sqft_band_id, raw_label, sqft_min, sqft_max, is_unknown) VALUES
    ( 1, '0-250 Sq.Ft',       0,  250, FALSE),
    ( 2, '0-250 Sq.ft',       0,  250, FALSE),
    ( 3, '251-500 Sq.Ft',   251,  500, FALSE),
    ( 4, '501-750 Sq.Ft',   501,  750, FALSE),
    ( 5, '751-1000 Sq.Ft',  751, 1000, FALSE),
    ( 6, '1001-1250 Sq.Ft',1001, 1250, FALSE),
    ( 7, '1251-1500 Sq.Ft',1251, 1500, FALSE),
    ( 8, '1501-1750 Sq.Ft',1501, 1750, FALSE),
    ( 9, '1751-2000 Sq.Ft',1751, 2000, FALSE),
    (10, '2001-2250 Sq.Ft',2001, 2250, FALSE),
    (11, '2251-2500 Sq.Ft',2251, 2500, FALSE),
    (12, '2501-2750 Sq.Ft',2501, 2750, FALSE),
    (13, '2751-3000 Sq.Ft',2751, 3000, FALSE),
    (14, '3001-3250 Sq.Ft',3001, 3250, FALSE),
    (15, '3251-3500 Sq.Ft',3251, 3500, FALSE),
    (16, '3501-3750 Sq.Ft',3501, 3750, FALSE),
    (17, '3751-4000 Sq.Ft',3751, 4000, FALSE),
    (18, '4000+ Sq.Ft',    4000, NULL, FALSE),
    (19, 'Unknown',        NULL, NULL, TRUE);

-- Rent bands. Two are malformed and overlap their neighbour by one dollar
-- ('$1750-$2000' 5 rows vs '$1751-$2000'; '$250-$500' 1 row vs '$251-$500'),
-- so a naive band -> midpoint join is not a partition. Both are kept with
-- overlaps_other = TRUE rather than silently merged. The bare '0' (6 rows) is
-- the same "no rent paid" answer typed by hand.
INSERT INTO rent_band (rent_band_id, raw_label, rent_min, rent_max, is_no_rent_paid, overlaps_other) VALUES
    ( 1, '$0 (no rent paid by the occupant)', NULL, NULL, TRUE,  FALSE),
    ( 2, '0',                                 NULL, NULL, TRUE,  FALSE),
    ( 3, '$1-$250',                              1,  250, FALSE, FALSE),
    ( 4, '$250-$500',                          250,  500, FALSE, TRUE),
    ( 5, '$251-$500',                          251,  500, FALSE, FALSE),
    ( 6, '$501-$750',                          501,  750, FALSE, FALSE),
    ( 7, '$751-$1000',                         751, 1000, FALSE, FALSE),
    ( 8, '$1001-$1250',                       1001, 1250, FALSE, FALSE),
    ( 9, '$1251-$1500',                       1251, 1500, FALSE, FALSE),
    (10, '$1501-$1750',                       1501, 1750, FALSE, FALSE),
    (11, '$1750-$2000',                       1750, 2000, FALSE, TRUE),
    (12, '$1751-$2000',                       1751, 2000, FALSE, FALSE),
    (13, '$2001-$2250',                       2001, 2250, FALSE, FALSE),
    (14, '$2251-$2500',                       2251, 2500, FALSE, FALSE),
    (15, '$2501-$2750',                       2501, 2750, FALSE, FALSE),
    (16, '$2751-$3000',                       2751, 3000, FALSE, FALSE),
    (17, '$3001-$3250',                       3001, 3250, FALSE, FALSE),
    (18, '$3251-$3500',                       3251, 3500, FALSE, FALSE),
    (19, '$3501-$3750',                       3501, 3750, FALSE, FALSE),
    (20, '$3751-$4000',                       3751, 4000, FALSE, FALSE),
    (21, '$4001-$4250',                       4001, 4250, FALSE, FALSE),
    (22, '$4251-$4500',                       4251, 4500, FALSE, FALSE),
    (23, '$4501-$4750',                       4501, 4750, FALSE, FALSE),
    (24, '$4751-$5000',                       4751, 5000, FALSE, FALSE),
    (25, '$5001-$5250',                       5001, 5250, FALSE, FALSE),
    (26, '$5251-$5500',                       5251, 5500, FALSE, FALSE),
    (27, '$5501-$5750',                       5501, 5750, FALSE, FALSE),
    (28, '$5751-$6000',                       5751, 6000, FALSE, FALSE),
    (29, '$6001-$6250',                       6001, 6250, FALSE, FALSE),
    (30, '$6251-$6500',                       6251, 6500, FALSE, FALSE),
    (31, '$6501-$6750',                       6501, 6750, FALSE, FALSE),
    (32, '$6751-$7000',                       6751, 7000, FALSE, FALSE),
    (33, '$7000+',                            7000, NULL, FALSE, FALSE);

-- ============================================================================
-- Losslessness: validate_3nf.sql reconstructs all 28 original columns from
-- these tables and asserts the result is exactly 550,201 rows.
-- ============================================================================
