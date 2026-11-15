# Source-column decisions and normalization record

This document accounts for every column in the 28-column source export. The source grain is one reported rental-unit row in one filing. The target fact relation is `UnitReport`, not a persistent physical-unit relation.

| # | Source column | Example source value(s) | Clean value / table representation | Meaning / preprocessing | Target relation |
|---:|---|---|---|---|---|
| 1 | `unique_id` | `-4703731682178636368` | Same signed BIGINT value | Preserve as the source-row primary key; not a cross-year unit ID. | `UnitReport.unique_id` |
| 2 | `block_num` | `0285`, `3180` | Same text, including leading zeroes | Preserve identifier formatting. | `AssessorBlock`, `UnitReport.block_num` |
| 3 | `unit_count` | `70`, `173` | `70.0`, `173.0` | Parse numeric text into `DECIMAL(6,1)`; keep it at report grain. | `UnitReport.reported_unit_count` |
| 4 | `case_type_name` | `Housing Inventory - Unit information (2026)` | Filing-cycle label stored once | Compare with year; avoid repeating a one-to-one label. | `FilingCycle.case_type_name` |
| 5 | `submission_year` | `2022`, `2026` | `SMALLINT`: `2022`, `2026` | Validate observed filing range. | `FilingCycle`, `UnitReport.submission_year` |
| 6 | `block_address` | `400 Block of STOCKTON ST` | `block_range=400`, `street_name=STOCKTON ST` | Preserve raw label; not a unique property address. | `BlockAddress`, `UnitReport.block_address_id` |
| 7 | `occupancy_type` | `Occupied by non-owner`, `Vacant` | Same controlled label | Use a controlled vocabulary. | `OccupancyType`, `UnitReport.occupancy_type_id` |
| 8 | `occupancy_or_vacancy_date` | `2024/03/02` | `2024-03-02` | Invalid values become null plus a quality issue. | `UnitReport.occupancy_or_vacancy_date` |
| 9 | `occupancy_or_vacancy_date_year` | `2024`, `Year Unknown (more than 20 years)` | `occupancy_year=2024` or `date_unknown_text` | Separate year from unknown text. | `UnitReport.occupancy_year`, `UnitReport.date_unknown_text` |
| 10 | `bedroom_count` | `One-Bedroom`, `Studio`, `1br`, `2AH` | `1`, `0`, `1`, or `NULL + is_unparseable=TRUE` | Canonicalize safe variants; retain raw label. | `BedroomLabel`, `UnitReport.bedroom_label_id` |
| 11 | `bathroom_count` | `One bathroom`, `2.5`, shared facilities | `1.0`, `2.5`, or `is_shared=TRUE` | Preserve half baths and shared category. | `BathroomLabel`, `UnitReport.bathroom_label_id` |
| 12 | `square_footage` | `751-1000 Sq.Ft`, `4000+ Sq.Ft`, `Unknown` | `min=751,max=1000`; `min=4000,max=NULL`; `is_unknown=TRUE` | Store bounds, not an invented midpoint. | `SquareFootageBand`, `UnitReport.sqft_band_id` |
| 13 | `monthly_rent` | `$3501-$3750`, `$0 (no rent paid...)`, `$7000+` | `min=3501,max=3750`; `is_no_rent_paid=TRUE`; `min=7000,max=NULL` | Preserve bands and no-rent status. | `RentBand`, `UnitReport.rent_band_id` |
| 14 | `base_rent_includes_water_sewer` | `Y`, `N` | Utility row `water_sewer` when `Y` | Convert included utilities to rows. | `ReportUtility` |
| 15 | `base_rent_includes_natural_gas` | `Y`, `N` | Utility row `natural_gas` when `Y` | Convert included utilities to rows. | `ReportUtility` |
| 16 | `base_rent_includes_electricity` | `Y`, `N` | Utility row `electricity` when `Y` | Convert included utilities to rows. | `ReportUtility` |
| 17 | `base_rent_includes_refuse_recycling` | `Y`, `N` | Utility row `refuse_recycling` when `Y` | Convert included utilities to rows. | `ReportUtility` |
| 18 | `base_rent_includes_other_utilities` | blank, `heat`, `parking & heat`, `wifi`, `n/a` | Raw text retained; known terms become utility rows | Unknown text is not silently discarded. | `UnitReport.other_utilities_raw`, `ReportUtility` |
| 19 | `past_occupancy` | `Yes`, `No`, `but gas for heating water is not.` | `1`, `0`, or `NULL + QualityIssue` | Map valid booleans; flag contamination. | `UnitReport.past_occupancy` |
| 20 | `vacancy_date` | blank, `2024/01/15` | `NULL` or `2024-01-15` | Validate and preserve malformed input through quality records. | `UnitReport.vacancy_date` |
| 21 | `signature_date` | `2026/02/27` | `2026-02-27` | Parse and validate the date. | `UnitReport.signature_date` |
| 22 | `occupancy_or_vacancy_date_history` | JSON array with type/start/end | One `OccupancyHistory` row per array item, with `seq_no` | Flatten JSON into atomic child events. | `OccupancyHistory` |
| 23 | `year_property_built` | `1911`, `2012` | `SMALLINT`: `1911`, `2012` | Parse year; invalid values become null plus a quality issue. | `UnitReport.year_property_built` |
| 24 | `point` | `POINT (-122.408410392 37.796255117)` | `longitude=-122.408410392`, `latitude=37.796255117` | Use for location, not exact building identity. | `LocationPoint`, `UnitReport.point_id` |
| 25 | `analysis_neighborhood` | `Chinatown`, `Oceanview/Merced/Ingleside` | One `Neighborhood` lookup row | Use through `LocationPoint` if the dependency is verified. | `Neighborhood`, `LocationPoint.neighborhood_id` |
| 26 | `supervisor_district` | `3`, `11` | `TINYINT`: `3`, `11` | Validate domain; do not assume neighborhood determines it. | `SupervisorDistrict`, `LocationPoint.district_id` |
| 27 | `data_as_of` | `2026/09/27 01:31:09 AM` | One batch metadata timestamp | Dataset-level provenance, not a report attribute. | `ExtractBatch.data_as_of` |
| 28 | `data_loaded_at` | `2026/09/27 06:15:32 AM` | One batch/load timestamp | Load-event provenance, not a report attribute. | `ExtractBatch.data_loaded_at` |

## 1NF decision

The flat source is not fully 1NF for analysis because utilities are represented as a repeating group of four columns, and the occupancy-history fields represent a related event attached to the report. Python preprocessing creates atomic utility rows in `ReportUtility` and one atomic history row in `OccupancyHistory`. Category fields remain one value per source row, but their raw labels are mapped through lookup relations.

## 2NF decision

The source row key is a single `unique_id`, so there cannot be a partial dependency on part of a composite key. The main 2NF decision is therefore to define the fact grain explicitly before decomposing: attributes such as reported unit count, rent band, dates, and bedroom/bathroom responses describe that one report. A made-up composite key such as `(block_num, submission_year)` would incorrectly imply that a block has only one unit report per year.

## 3NF decision

The decomposition removes dependencies that do not belong directly to the report key:

- `submission_year -> filing-cycle label` moves to `FilingCycle`.
- `point -> longitude, latitude, neighborhood, district` moves to `LocationPoint`, subject to validation of the functional dependency.
- `raw bedroom label -> canonical bedroom count` moves to `BedroomLabel`.
- `raw bathroom label -> canonical bathroom value and shared flag` moves to `BathroomLabel`.
- `raw rent band -> band bounds and status` moves to `RentBand`.
- `raw square-footage band -> band bounds and unknown status` moves to `SquareFootageBand`.
- Utility membership and history events become child relations rather than repeating columns.

The model intentionally does not create a `Property` or `Building` table from `block_num`. The available fields do not establish that `block_num` determines address, point, unit count, or year built. Creating that table would create a false dependency and weaken the normalization argument.

## What is retained versus transformed

The cleaned output retains the raw category labels and raw free-text utility field so the team can audit or revise mappings. Derived fields are additions for analysis, not replacements for the evidence. Quality issues identify values that could not be safely converted.
