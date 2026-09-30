# DATA 201 project report outline

## Dataset selection and motivation

This project uses San Francisco Rent Board housing-inventory records. The file
is large enough to make manual spreadsheet analysis difficult: it contains
550,201 unit records, repeated categorical values, banded rent and square-foot
measurements, multi-valued utilities, occupancy history, and quality problems.
That complexity makes it a good example for relational design and normalization.

The project can answer questions such as:

- How many records were filed in each year?
- How do occupancy categories change by filing year?
- Which bedroom, bathroom, rent, and square-footage categories are most common?
- Which utilities are included in the reported base rent?
- How many records contain invalid dates or other quality problems?

## Schema design

The central fact table is `unit_record`. Its primary key is `unique_id`, and it
stores one unit record from one filing. Repeated labels and attributes are moved
to lookup tables such as `occupancy_type`, `bedroom_type`, `bathroom_type`,
`rent_band`, and `sqft_band`.

The design uses child and junction tables for data that can have multiple values:

- `record_utility_included` connects a record to many utilities.
- `occupancy_history` stores one or more history ranges per record.
- `record_quality_flag` stores multiple quality findings per record.

## Normalization explanation

### First normal form

The source has multiple utility columns and a free-text list of additional
utilities. These are represented as rows in `record_utility_included` so each
stored utility value is atomic. Occupancy history is also moved from repeated or
flattened fields into `occupancy_history`.

### Second normal form

`unit_record` uses one-column primary key `unique_id`, so a non-key attribute
cannot depend on only part of a composite key. The utility table uses the
composite key `(unique_id, utility_id)` and stores only attributes describing
that relationship, namely the two provenance flags.

### Third normal form

Attributes that describe a lookup value are stored with that lookup value rather
than repeated in every fact row. For example, rent-band bounds belong in
`rent_band`, and the filing description belongs in `filing_cycle`. This removes
transitive dependencies from `unit_record`.

## Limitation of the local CSV

The supplied local CSV has blank block, neighborhood, and supervisor-district
columns. The database keeps those relationships nullable and does not pretend
that a privacy-jittered point can recreate the missing labels. Neighborhood and
district analyses require the fully populated source export described in the
README.

## Evidence to include in the presentation

After loading the database, include screenshots or copied results showing:

1. The list of created tables in MySQL Workbench.
2. The `unit_record` count of 550,201.
3. A query grouped by `submission_year`.
4. A quality-flag count.
5. The ER diagram and the normalization explanation.
