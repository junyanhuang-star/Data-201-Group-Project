# Relational schema and 3NF rationale

## Fact grain

`UnitReport` is one row per `unique_id`, meaning one unit report in one filing cycle. It is not a physical-unit table. The name avoids an unsupported claim about longitudinal unit identity.

## Relations

```text
ExtractBatch(batch_id PK, data_as_of, data_loaded_at, source_filename)
FilingCycle(submission_year PK, case_type_name UNIQUE)

Neighborhood(neighborhood_id PK, name UNIQUE)
SupervisorDistrict(district_id PK)
LocationPoint(point_id PK, longitude, latitude,
              neighborhood_id FK, district_id FK)
AssessorBlock(block_num PK)
BlockAddress(block_address_id PK, raw_label UNIQUE, block_range, street_name)

OccupancyType(occupancy_type_id PK, name UNIQUE)
BedroomLabel(bedroom_label_id PK, raw_label UNIQUE, canonical_bedrooms, is_unparseable)
BathroomLabel(bathroom_label_id PK, raw_label UNIQUE, canonical_bathrooms,
              is_shared, is_unparseable)
SquareFootageBand(sqft_band_id PK, raw_label UNIQUE, min_sqft, max_sqft,
                  is_unknown)
RentBand(rent_band_id PK, raw_label UNIQUE, min_rent, max_rent,
         is_no_rent_paid, overlaps_other)

UnitReport(unique_id PK, source_location_id, batch_id FK, submission_year FK,
           block_num FK, block_address_id FK, point_id FK,
           reported_unit_count, year_property_built,
           occupancy_type_id FK, bedroom_label_id FK, bathroom_label_id FK,
           sqft_band_id FK, rent_band_id FK,
           occupancy_or_vacancy_date, occupancy_year,
           date_unknown_text, vacancy_date, past_occupancy,
           other_utilities_raw, signature_date)

Utility(utility_id PK, name UNIQUE)
ReportUtility(unique_id PK/FK, utility_id PK/FK, source_checkbox, source_text)
OccupancyHistory(history_id PK, unique_id FK, range_type, start_date, end_date,
                 is_reversed)
QualityIssue(issue_id PK, unique_id FK, column_name, issue_code,
             raw_value, issue_detail)
```

## Table visuals with representative values

The IDs below are illustrative lookup IDs. A real loader may assign different
auto-increment values. The examples show how raw values, cleaned values, and
foreign keys work together.

```text
ExtractBatch
batch_id | data_as_of                | data_loaded_at             | source_filename
1        | 2026-09-27 01:31:09       | 2026-09-27 06:15:32        | Rent_Board_Housing_Inventory_20260927.csv

FilingCycle
submission_year | case_type_name
2026            | Housing Inventory - Unit information (2026)

Neighborhood
neighborhood_id | name
1              | Chinatown
2              | Oceanview/Merced/Ingleside

SupervisorDistrict
district_id
3
11

LocationPoint
point_id | longitude        | latitude       | neighborhood_id | district_id
1        | -122.408410392  | 37.796255117   | 1               | 3

AssessorBlock
block_num
0285
3180

BlockAddress
block_address_id | raw_label                 | block_range | street_name
1                | 400 Block of STOCKTON ST  | 400         | STOCKTON ST

OccupancyType
occupancy_type_id | name
1                 | Occupied by non-owner
2                 | Vacant
```

```text
BedroomLabel
bedroom_label_id | raw_label   | canonical_bedrooms | is_unparseable
1                | One-Bedroom | 1                  | false
2                | 1br         | 1                  | false
3                | Studio      | 0                  | false
4                | 2AH         | NULL               | true

BathroomLabel
bathroom_label_id | raw_label                                  | canonical_bathrooms | is_shared | is_unparseable
1                 | One bathroom                              | 1.0                 | false     | false
2                 | 2.5                                        | 2.5                 | false     | false
3                 | Shared bathroom facilities with other units | NULL                | true      | false

SquareFootageBand
sqft_band_id | raw_label       | min_sqft | max_sqft | is_unknown
1            | 751-1000 Sq.Ft  | 751      | 1000     | false
2            | 4000+ Sq.Ft     | 4000     | NULL     | false
3            | Unknown         | NULL     | NULL     | true

RentBand
rent_band_id | raw_label                            | min_rent | max_rent | is_no_rent_paid | overlaps_other
1            | $3501-$3750                         | 3501     | 3750     | false           | false
2            | $0 (no rent paid by the occupant)   | NULL     | NULL     | true            | false
3            | $7000+                              | 7000     | NULL     | false           | false
```

```text
UnitReport
unique_id             | batch_id | submission_year | block_num | point_id | occupancy_type_id | bedroom_label_id | bathroom_label_id | rent_band_id
-4703731682178636368  | 1        | 2026            | 3180      | 1        | 1                 | 1                | 1                 | 1

Utility
utility_id | name
1          | water_sewer
2          | natural_gas
3          | electricity
4          | refuse_recycling
5          | heat

ReportUtility
unique_id             | utility_id | source_checkbox | source_text
-4703731682178636368  | 5          | false           | true
-4703731682178636368  | 1          | true            | false
-4703731682178636368  | 4          | true            | false
-4647246791381119432  | 1          | true            | true
-4647246791381119432  | 5          | false           | true
-4647246791381119432  | 7          | false           | true
-4555555555555555555  | 2          | true            | false
-4555555555555555555  | 3          | true            | false
-4555555555555555555  | 6          | false           | true

OccupancyHistory
history_id | unique_id             | seq_no | range_type | start_date | end_date   | is_reversed
1          | -4703731682178636368  | 1      | Occupied   | 2021-06-01 | 2022-06-30 | false

QualityIssue
issue_id | unique_id             | column_name        | issue_code           | raw_value
1        | -4703731682178636368  | past_occupancy     | unexpected_boolean  | utility text
```

The key pattern is that `UnitReport` stores foreign-key IDs, while the lookup
tables explain what those IDs mean. The raw labels remain available in the
lookup tables, and the child/junction tables represent one-to-many or
many-to-many values without repeating columns in `UnitReport`.

For `ReportUtility`, each row means “this report includes this utility.” The
same report can therefore appear several times. For example, the first report
has water/sewer and refuse/recycling from checkboxes, plus heat from free text.
The second report has water/sewer asserted by both sources, plus heat and
parking detected in the free-text field. The third report has natural gas and
electricity from checkboxes, plus internet from free text.

## Why this is in 3NF

1. `unique_id` is a single-column key, so there are no partial dependencies in `UnitReport`.
2. Repeating utilities and occupancy-history events are moved to child/junction tables, so each stored value is atomic.
3. `submission_year -> case_type_name` is stored in `FilingCycle`, rather than repeating the case label on every report.
4. `point -> neighborhood, district` is stored in `LocationPoint`, rather than repeating both labels on every report.
5. Raw category labels and their parsed values are stored once in lookup relations. This keeps typos auditable while letting queries use canonical values.
6. `block_num` is not used to determine `block_address`, `year_property_built`, `unit_count`, or `point`. The source does not establish those dependencies.

## Relationship cardinalities

- `ExtractBatch 1:M UnitReport`
- `FilingCycle 1:M UnitReport`
- `LocationPoint 1:M UnitReport`
- `OccupancyType 1:M UnitReport`
- Each category lookup row can be referenced by many reports.
- `UnitReport 1:M OccupancyHistory`
- `UnitReport M:N Utility` through `ReportUtility`
- `UnitReport 1:M QualityIssue`

In MySQL Workbench, reverse-engineer `sf_rent_board` after loading `schema.sql`; this produces the ER diagram from the actual PK/FK constraints.

The full source-column accounting and the normalization decision record are in [`COLUMN_DECISIONS.md`](COLUMN_DECISIONS.md). That document should be used to explain the transformation from the original 28-column relation to this schema during the presentation.

## Important interpretation limits

- A rent band is not a rent amount. Do not calculate a midpoint unless the analysis explicitly labels it as an assumption.
- `point` can support neighborhood-scale mapping, not exact building addresses.
- Missing rent is often structurally correct for owner-occupied, vacant, or non-residential reports.
- `unique_id` is not stable across future extracts, so it is an extract-row key, not a business identity.
