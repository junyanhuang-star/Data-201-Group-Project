# San Francisco Rent Board Housing Inventory

## Project dataset

The project uses `Rent_Board_Housing_Inventory_flat_final.csv`, a San Francisco
Rent Board housing-inventory export with 550,201 records and 28 columns.

The grain is one rental-unit record as reported in one annual filing. The
`unique_id` column identifies each row in this extract. It does not identify the
same physical unit across different years.

## Important difference from the README source description

The local CSV has the expected row count and 28-column shape, but it is not an
exact copy of the fully populated source described in the README. In this file:

- `block_num`, `block_address`, `analysis_neighborhood`, and
  `supervisor_district` are blank for all 550,201 rows.
- `point` is still populated for nearly every row, but a point alone cannot
  recover the missing neighborhood or district labels.
- Occupancy history is already flattened into three columns instead of one JSON
  array column.
- The file is therefore suitable for unit, occupancy, rent-band, utility, and
  date-quality analysis, but not for neighborhood or supervisor-district
  summaries unless the missing geography columns are obtained from the original
  source export.

The project also includes `Rent_Board_Housing_Inventory_flat_final.csv.gz`, a
compressed copy of the real CSV suitable for GitHub. The older file named
`Rent_Board_Housing_Inventory_flat_final_2.csv.gz` is not a gzip CSV in the
current branch; it contains project notes. The loader accepts either the
uncompressed CSV or the new real gzip CSV.

## Columns

| Column | Meaning |
|---|---|
| `unique_id` | Unique row identifier. |
| `location_id` | Source location identifier; retained in the raw file for audit. |
| `submission_year` | Annual filing year. |
| `unit_count` | Number of units reported by the filer; stored as a decimal because the source uses values such as `72.0`. |
| `year_property_built` | Reported construction year. |
| `point` | Privacy-jittered WKT point containing longitude and latitude. |
| `bedroom_count` | Raw bedroom label; normalized into `bedroom_type`. |
| `bathroom_count` | Raw bathroom label; normalized into `bathroom_type`. |
| `square_footage` | Raw square-footage band; normalized into `sqft_band`. |
| `occupancy_type` | Occupancy category. |
| `occupancy_or_vacancy_date` | Move-in or occupancy date, when supplied. |
| `occupancy_or_vacancy_date_year` | Reported year or a “Year Unknown” phrase. |
| `past_occupancy` | Yes/No indicator. |
| `monthly_rent` | Rent band, not an exact rent amount. |
| `signature_date` | Date the filing was signed. |
| `vacancy_date` | Vacancy date, when supplied. |
| `base_rent_includes_water_sewer` | Water/sewer utility checkbox. |
| `base_rent_includes_natural_gas` | Natural-gas utility checkbox. |
| `base_rent_includes_electricity` | Electricity utility checkbox. |
| `base_rent_includes_refuse_recycling` | Refuse/recycling utility checkbox. |
| `base_rent_includes_other_utilities` | Free-text list of additional utilities. |
| `block_num` | Assessor block identifier; treated as text, not a number. |
| `block_address` | Street-block label such as `400 Block of STOCKTON ST`. |
| `analysis_neighborhood` | Neighborhood label. |
| `supervisor_district` | Supervisor district number. |
| `occ_history_type` | Flattened occupancy-history type. |
| `occ_history_start` | Flattened occupancy-history start date. |
| `occ_history_end` | Flattened occupancy-history end date. |

## Main cleaning decisions

- Bedroom and bathroom labels retain their raw text and receive canonical
  numeric values where parsing is possible.
- `Unknown` square footage is kept as a stated unknown, distinct from a blank.
- Rent and square-footage bands retain their labels and receive parsed bounds.
- Invalid dates are stored as NULL in date columns and recorded as quality flags.
- The four utility checkboxes and the free-text utility field are combined in a
  many-to-many utility table with provenance flags.
- Occupancy history is stored as a child table. The current flat file has one
  history row represented by three columns, while the database design supports
  multiple history rows per unit record.
- Duplicate records are tagged by a content hash and are not silently deleted.

## Important limitations

- Rent is a banded contract-rent report, not an asking price or exact numeric rent.
- Coordinates are privacy-jittered and should support neighborhood analysis, not
  building-level identification.
- The source does not provide a stable identifier for following a unit across
  filing years.
