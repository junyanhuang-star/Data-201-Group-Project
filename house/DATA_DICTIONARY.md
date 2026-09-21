# Data dictionary — `Rent_Board_Housing_Inventory_20260913.csv`

Reference description of the **source data as delivered**. It documents what the raw
file contains, not what the cleaned database contains. For the cleaning decisions and
the 3NF model see [README.md](README.md); for the DDL see `schema_3nf.sql`.

## 1. Dataset identity

| | |
|---|---|
| Dataset | San Francisco Rent Board **Housing Inventory — Unit information** |
| Publisher | San Francisco Rent Board, published as an open-data extract (the `data_as_of`, `data_loaded_at`, `analysis_neighborhood` and `supervisor_district` columns are DataSF packaging conventions) |
| File | `Rent_Board_Housing_Inventory_20260913.csv`, 207 MB, UTF-8, RFC-4180 quoted, CRLF-free |
| Rows | **550,201** data rows + 1 header row (997,852 physical lines — the JSON history column contains embedded newlines, so line count ≠ row count) |
| Columns | **28** |
| `data_as_of` | 2026-09-03 01:32:48 — one value on every row |
| `data_loaded_at` | 2026-09-10 06:11:33 — one value on every row |
| Filename date | 2026-09-13, the day the file was downloaded |
| Filing cycles covered | 2022 – 2026 |

The exact source URL and licence terms were **not verified in this session** — they
are not recoverable from the file itself. Confirm both against the DataSF catalogue
before redistributing anything derived from it.

## 2. What reads this file in this repo

| Consumer | Produces |
|---|---|
| `clean_inventory.py` | `inventory_clean.parquet` — a flat, typed table for analysis |
| `analysis.py` | `analysis_data.json` — the summary statistics |
| `load_3nf.py` | `load/*.tsv` + `load_3nf.sql` — the normalized database |

`load_3nf.py` imports its parsers from `clean_inventory.py`, so the flat and
normalized pipelines cannot disagree about how a value is read.

## 3. Grain and keys

**One row = one rental unit as reported in one annual filing.**

* `unique_id` is the only key: 550,201 distinct values, 0 duplicates. It is a signed
  64-bit hash spanning −9,223,314,555,602,954,135 … 9,223,362,993,962,851,579 — it is
  **not** an ordinal, carries no meaning, and is not stable across extracts.
* There is **no unit identifier that persists across filing years**, so the file does
  not support a panel. The same physical unit appearing in 2023 and 2024 cannot be
  linked.
* There is **no building key**. `block_num` is an assessor block holding many
  buildings; see §6.
* 40,797 rows are byte-identical to another row on all 27 non-key columns. They may be
  double submissions or genuinely identical units; the data cannot distinguish them.

## 4. Coverage

Rows per filing cycle:

| 2022 | 2023 | 2024 | 2025 | 2026 |
|---:|---:|---:|---:|---:|
| 66,744 | 107,886 | 111,513 | 132,088 | 131,970 |

The 2022 cycle is roughly half the size of later ones — treat cross-year counts as
reflecting reporting coverage, not housing stock.

By supervisor district (rent-controlled stock is concentrated in the dense northeast):

| District | 3 | 2 | 5 | 6 | 8 | 7 | 1 | 9 | 10 | 4 | 11 | missing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rows | 122,518 | 81,260 | 79,999 | 58,106 | 55,444 | 39,457 | 37,881 | 35,726 | 15,683 | 15,196 | 8,915 | 16 |

41 `analysis_neighborhood` values. Largest: Nob Hill 50,680 · Tenderloin 42,374 ·
Mission 41,078 · Marina 31,790 · Pacific Heights 31,502.

## 5. Column reference

Types are **as delivered** — every field arrives as text. "Null" counts empty strings.
"Target" is where the value lands in the 3NF model.

| # | Column | Delivered as | Null | Distinct | Domain / notes | Target |
|---:|---|---|---:|---:|---|---|
| 1 | `unique_id` | int64 as text | 0 | 550,201 | Signed 64-bit hash. The key. | `unit_record.unique_id` |
| 2 | `block_num` | text | 6 | 4,287 | Assessor block, zero-padded; 4 chars on 532,161 rows, 5 on 18,034. An identifier — never cast to a number. | `assessor_block` |
| 3 | `unit_count` | number as text | 2 | 300 | Units in the building **as reported on this filing**. 0 – 720, median 18. Written both `70` and `72.0`. 3,560 rows report 0. | `unit_record.building_unit_count` |
| 4 | `case_type_name` | text | 0 | 5 | `Housing Inventory - Unit information (YYYY)`. 1:1 with `submission_year` — **carries no extra information**. | `filing_cycle` |
| 5 | `submission_year` | year as text | 0 | 5 | 2022 – 2026. | `unit_record.submission_year` |
| 6 | `block_address` | text | 80 | 7,677 | `400 Block of STOCKTON ST`. Block-level, not a street address. 7,676 match `^(\d+) Block of (.+)$`; the exception is the truncated `0 Block of`. | `street_block` |
| 7 | `occupancy_type` | enum | 0 | 4 | See §6.1. | `occupancy_type` |
| 8 | `occupancy_or_vacancy_date` | `YYYY/MM/DD` | 103,060 | — | Move-in (or vacancy) date. In-range values span 1900-01-01 … 2026-12-01. **147 rows are impossible** (years `0002`, `0285`, `0987`, `3022`, `5020`). | `unit_record.occupancy_or_vacancy_date` |
| 9 | `occupancy_or_vacancy_date_year` | mixed | 69,658 | 150 | **Three things in one column**: a 4-digit year, one of 5 `Year Unknown (…)` phrases (9,560 rows, §6.4), or junk (57 rows: `20204`, `202023`, `2008.`, `21`). Redundant with column 8 on the 447,141 rows that have both. | `..._year` / `date_unknown_reason_id` / `occupancy_year_raw` |
| 10 | `bedroom_count` | free text | 30,454 | **45** | Should be ~7 categories. See §6.2. | `bedroom_type` |
| 11 | `bathroom_count` | free text | 30,324 | **31** | Should be ~6. Includes `Shared bathroom facilities with other units` (21,032 rows), which is an **SRO category, not a missing value**. See §6.3. | `bathroom_type` |
| 12 | `square_footage` | banded text | 505 | 19 | 250-ft bands plus `4000+ Sq.Ft` and an explicit `Unknown` (38,392 rows). See §6.5. | `sqft_band` |
| 13 | `monthly_rent` | banded text | 66,389 | 33 | $250 bands plus `$7000+` and `$0 (no rent paid by the occupant)`. **Two bands overlap.** See §6.6. Missing is largely structural — see §7. | `rent_band` |
| 14 | `base_rent_includes_water_sewer` | `Y`/`N` | 0 | 2 | Checkbox. | `record_utility_included` |
| 15 | `base_rent_includes_natural_gas` | `Y`/`N` | 0 | 2 | Checkbox. | `record_utility_included` |
| 16 | `base_rent_includes_electricity` | `Y`/`N` | 0 | 2 | Checkbox. | `record_utility_included` |
| 17 | `base_rent_includes_refuse_recycling` | `Y`/`N` | 0 | 2 | Checkbox. | `record_utility_included` |
| 18 | `base_rent_includes_other_utilities` | free text | 511,392 | 94 | **Multi-valued**: `parking & heat`, `pest control/valet trash`. Also holds non-answers (`n/a`, `yes`, `non`) and bare numbers (`38`, `41`). | `record_utility_included` + `other_utilities_raw` |
| 19 | `past_occupancy` | `Yes`/`No` | 152,609 | 2 | Whether a prior occupancy was reported. | `unit_record.past_occupancy` |
| 20 | `vacancy_date` | `YYYY/MM/DD` | 529,017 | 2,472 | Populated for 56% of `Vacant` rows and <0.2% of every other type. **88 impossible** (`0022`–`0025`, `3024`). | `unit_record.vacancy_date` |
| 21 | `signature_date` | `YYYY/MM/DD` | 0 | 1,537 | When the filing was signed; expected inside the 2022–2026 window. **136 outliers**: 134 dated `0001-01-01`, one 1974, one 1977. | `unit_record.signature_date` |
| 22 | `occupancy_or_vacancy_date_history` | **JSON array** | 469,197 | — | Array of `{date_range_type, start_date, end_date}`. Every array holds exactly 1 element today. Contains embedded newlines. 8,535 entries have a null type; 3 are lower-cased. 418 ranges end before they start. | `occupancy_history` |
| 23 | `year_property_built` | year as text | 16,234 | 160 | 1808 – 2025, median **1927**. Reported per filing, so the same block disagrees with itself across years. | `unit_record.year_property_built` |
| 24 | `point` | WKT | 3 | 13,435 | `POINT (lon lat)`; lon −122.511078 … −122.365380, lat 37.707884 … 37.819372. **Privacy-jittered and re-randomized per filing** — see §7. | `location_point` |
| 25 | `analysis_neighborhood` | enum | 19 | 41 | Analysis neighborhood. Functionally determined by `point`. | `neighborhood` |
| 26 | `supervisor_district` | int as text | 16 | 11 | 1 – 11. Determined by `point`. **Not** determined by neighborhood — 25 of 41 span 2–4 districts. | `location_point.district_id` |
| 27 | `data_as_of` | timestamp | 0 | **1** | `2026/09/03 01:32:48 AM` on every row. Extract metadata. | `extract_batch` |
| 28 | `data_loaded_at` | timestamp | 0 | **1** | `2026/09/10 06:11:33 AM` on every row. Extract metadata. | `extract_batch` |

## 6. Value domains

### 6.1 `occupancy_type` — closed, clean

| Value | Rows | |
|---|---:|---|
| `Occupied by non-owner` | 483,575 | tenant-occupied; the only rows where rent is meaningful |
| `Vacant` | 36,079 | |
| `Occupied by owner` | 27,921 | never reports a rent |
| `Non-Residential` | 2,626 | never reports a rent |

### 6.2 `bedroom_count` — open, contaminated

Intended: `Studio`, `One-Bedroom` … `Four-Bedroom`, `5+`. **45 values actually occur.**

* Clean labels cover 99.0% of non-null rows: `One-Bedroom` 208,992 · `Studio` 141,359 ·
  `Two-Bedroom` 127,364 · `Three-Bedroom` 30,062 · `Four-Bedroom` 6,226 · `5+` 1,606.
* Bare digits: `1` 1,569 · `2` 999 · `0` 605 · `3` 163.
* Case and spacing variants: `One Bedroom`, `studio`, `1 Bedroom`, `1br`, `One-bedroom`,
  `3bedroom`, `Zero-(Studio)`, `Studio (sm)`.
* Typos: `2brd`, `2 bedriin`, `2 bedroomq`.
* **Not bedroom counts at all**: `Garage` (10), `Vacant` (1), `$D$61` (1), and unit
  labels `2A`, `2S`, `1A`, `2T`, `2U`, `1U`, `0U`, `2AH`, `0AH`, `0A`, `1T`.

14 of the 45 labels cannot be parsed to a count.

### 6.3 `bathroom_count` — open, contaminated

* `One bathroom` 415,062 · `Two bathrooms` 60,341 · `Shared bathroom facilities with
  other units` 21,030 · `One and a half bathrooms` 10,850 · `Three bathrooms or more`
  4,650 · `Two and a half bathrooms` 3,892.
* Bare numbers: `1` 2,617 · `2` 240 · `0` 93 · `1.00` 65 · `2.5` 52 · `2.00` 6 · `3.5` 1.
* `None` 36.
* Typos: `2 batroom`, `One and a half bathdrooms`, `2  bathroom`.
* **Bedroom text in the bathroom column**: `One-Bedroom` 12, `1 bedroom` 4,
  `2 bedroom` 2. Plus `E3` (1).

### 6.4 `Year Unknown` phrases — 9,560 rows

| Phrase | Rows | Implied range |
|---|---:|---|
| `Year Unknown (more than 20 years)` | 3,588 | 20+ yrs |
| `Year unknown (no information available)` | 1,851 | — |
| `Year Unknown (within past 10-20 years)` | 1,840 | 10–20 |
| `Year Unknown (within past five years)` | 1,315 | 0–5 |
| `Year Unknown (within past 5-10 years)` | 966 | 5–10 |

Note the inconsistent capitalisation of "unknown" in the fifth phrase.

### 6.5 `square_footage` — 19 values

250-ft bands from `0-250 Sq.Ft` to `3751-4000 Sq.Ft`, then `4000+ Sq.Ft` (224 rows,
open-ended) and `Unknown` (38,392). Largest: `501-750 Sq.Ft` 166,730 ·
`751-1000 Sq.Ft` 110,998 · `251-500 Sq.Ft` 109,595.
One casing typo: `0-250 Sq.ft` (1 row).

### 6.6 `monthly_rent` — 33 values

$250 bands from `$1-$250` to `$6751-$7000`, then `$7000+` (4,022 rows, open-ended).

Three defects:

* `$0 (no rent paid by the occupant)` (3,585) and bare `0` (6) are **not a rent of
  zero** — they mean no rent is paid.
* `$1750-$2000` (5 rows) overlaps `$1751-$2000`, and `$250-$500` (1 row) overlaps
  `$251-$500`. **The bands are not a partition**, so a band→midpoint mapping is
  ambiguous for those rows.
* Bands are the only rent information — there are no actual dollar amounts anywhere in
  the file. Any point estimate is an assumption, and the open top band has no midpoint.

### 6.7 `date_range_type` (inside the JSON of column 22)

`Vacant` 36,598 · `Occupied` 35,859 · **null 8,535** · `Occupied - Non Owner` 9 ·
`occupied` 2 · `vacant` 1.

## 7. Interpretation caveats

These bound what any analysis of this file can honestly claim.

1. **`monthly_rent` is a sitting tenant's contract rent under rent control, not an
   asking or market rent.** The sample is dominated by long tenancies. Year-over-year
   movement mostly reflects tenant turnover, not price change.
2. **No unit identity across years** (§3) — nothing here supports a panel or a true
   same-unit rent change.
3. **Coordinates are privacy-jittered and re-randomized per filing.** 13,435 distinct
   points over 4,287 blocks, and the same block reports a different point in different
   years. A point locates a neighborhood, not a building. 84.6% of blocks have
   inconsistent points across their rows.
4. **Nothing below the filing row can be keyed to a building.** `block_num` does not
   determine `block_address` (83.7% violate), `year_property_built` (84.7%),
   `unit_count` (79.5%) or `point` (84.6%).
5. **Rents and areas are bands, not measurements** (§6.5, §6.6).
6. **Blank rent is mostly structural, not missing data.** All 27,921 `Occupied by
   owner` rows, all 2,626 `Non-Residential` rows, and 33,947 of 36,079 `Vacant` rows
   report no rent — correctly. Only 1,895 of 483,575 tenant rows are genuinely missing
   one. Reading the 66,389 blanks as 12% missingness is a misreading.
7. **Coverage grows over the period** (§4); 2022 has ~half the rows of 2025.
8. **Self-reported.** Every field is typed by a filer, which is why columns 10, 11 and
   18 are free text and why 9,835 rows carry a quality flag after loading.

## 8. Reproducing these numbers

Every figure above was measured on the raw CSV, not estimated. After loading
(see [README.md](README.md)), the distributions are queryable directly:

```sql
SELECT rb.raw_label, COUNT(*) FROM unit_record r
  JOIN rent_band rb USING (rent_band_id) GROUP BY rb.raw_label ORDER BY 2 DESC;

SELECT qf.code, COUNT(*) FROM record_quality_flag JOIN quality_flag qf USING (flag_id)
 GROUP BY qf.code ORDER BY 2 DESC;
```

`validate_3nf.sql` reprints the row counts, the functional-dependency checks and the
flag tally in one run.
