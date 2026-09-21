# SF Rent Board Housing Inventory — cleaning assessment and 3NF model

Source file: `Rent_Board_Housing_Inventory_20260913.csv` (207 MB, **550,201 rows ×
28 columns**), the San Francisco Rent Board's annual Housing Inventory export,
downloaded 2026-09-13.

**Grain: one rental unit as reported in one annual filing.** `unique_id` is unique
across all 550,201 rows (0 duplicates), and there is no identifier that links the
same physical unit across filing years — the source does not provide one.

| File | What it is |
|---|---|
| `DATA_DICTIONARY.md` | Reference for the **source CSV**: provenance, grain, all 28 columns, value domains, interpretation caveats. |
| `schema_3nf.sql` | The DDL. MySQL 8.0.16+, 21 tables, with the fixed vocabularies seeded. |
| `load_3nf.py` | Two-pass loader: raw CSV → one TSV per table + a generated `load_3nf.sql`. |
| `load_3nf.sql` | Generated. `LOAD DATA LOCAL INFILE` in foreign-key order. |
| `validate_3nf.sql` | Row counts, FD re-checks, and the lossless round-trip view. |
| `schema_3nf_postgres.sql` | PostgreSQL mirror of an earlier revision. It predates findings 1–7 below. |
| `clean_inventory.py` / `analysis.py` | The existing flat-file (parquet) pipeline. `load_3nf.py` imports its parsers rather than restating them. |

Run order:

```sh
mysql -u <user> -p                   < schema_3nf.sql
.venv/bin/python house/load_3nf.py            # writes house/load/*.tsv (gitignored)
mysql -u <user> -p --local-infile=1  < load_3nf.sql
mysql -u <user> -p                   < validate_3nf.sql
```

`LOAD DATA LOCAL INFILE` needs the *server* side of `local_infile` on as well as the
client flag. This server ships with it off, so the load step needs
`SET GLOBAL local_infile = 1;` first (the account has `SYSTEM_VARIABLES_ADMIN`) and it
is worth setting back to 0 afterwards.

---

## 1. What cleaning the file needs

Every count below was measured on the raw CSV, not estimated.

### 1.1 First-normal-form violations — non-atomic values

| Column | Problem | Size |
|---|---|---|
| `base_rent_includes_water_sewer` … `_refuse_recycling` | A repeating group: four columns that are one attribute (*which utilities are included*) spread across the schema | 4 columns × 550,201 rows |
| `base_rent_includes_other_utilities` | Free-text bag, genuinely multi-valued: `parking & heat`, `cable and internet`, `pest control/valet trash`, `parking, storage & heat` | 94 distinct values, 38,809 non-null rows |
| `occupancy_or_vacancy_date_history` | A JSON array of `{date_range_type, start_date, end_date}` objects embedded in a text column | 81,004 non-null rows |

**Fix.** The five utility columns collapse into `record_utility_included`, a junction
against a 16-row `utility` table, with the free text mapped by substring
(`heat`/`steam`/`boiler`/`hydronic` → `heat`, `wifi`/`wi-fi` → `internet`, and so
on). 448 rows assert the same utility twice — once by checkbox, once in the free
text — so the junction carries `from_checkbox` and `from_other_text` provenance
flags; without them the four Y/N columns would not be reconstructible. Unrecognised
non-empty text maps to `other` and the verbatim string stays on the fact row.
The JSON array flattens into `occupancy_history`, modeled 1:N (every array holds
exactly one element today, but the array shape says the source may emit more).

### 1.2 Free-text contamination of what should be closed vocabularies

| Column | Distinct values | Should be | Examples of the damage |
|---|---|---|---|
| `bedroom_count` | **45** | ~7 | `One-Bedroom`, `One Bedroom`, `1`, `1br`, `1 bed`, `1bedroom`, `studio`, `Zero-(Studio)`, `2 bedriin`, `2 bedroomq`, `Garage`, `Vacant`, `$D$61`, `2AH` |
| `bathroom_count` | **31** | ~6 | `One bathroom`, `One-Bathroom`, `1`, `1.00`, `1bathroom`, `2 batroom`, `One and a half bathdrooms`, `E3` |

**Fix.** Normalise on a canonical form rather than enumerating typos, and keep the
raw label. `bedroom_type` and `bathroom_type` store `raw_label` (unique) beside the
parsed `bedrooms` / `bathrooms`, so the cleaning is auditable and reversible.
14 of the 45 bedroom labels and 3 of the 31 bathroom labels cannot be parsed and
carry `is_unparseable = TRUE` with a NULL canonical value.

Two of those are not noise and must not be nulled:

* `Shared bathroom facilities with other units` (21,032 rows) is a **category**, not
  a missing value — it flags SRO stock. It gets `is_shared = TRUE`.
* `Unknown` in `square_footage` (38,392 rows) is a **stated non-answer**, different
  from the 505 blank rows. It gets `is_unknown = TRUE`.

### 1.3 Quantities stored as banded strings

`monthly_rent` (`$2251-$2500`) and `square_footage` (`501-750 Sq.Ft`) cannot be
averaged, compared or summed as they stand.

**Fix.** `rent_band` and `sqft_band` hold the label once with parsed `min`/`max`
bounds. Three defects in the bands themselves:

* **Overlapping bands.** `$1750-$2000` (5 rows) overlaps `$1751-$2000`, and
  `$250-$500` (1 row) overlaps `$251-$500`. The set of bands is therefore *not a
  partition*, and a band→midpoint join is not safe without saying so. Both are kept
  with `overlaps_other = TRUE` rather than silently merged into their neighbour.
* **`$0 (no rent paid by the occupant)`** (3,585 rows) and the bare `0` (6 rows) are
  not a rent of zero. They get `is_no_rent_paid = TRUE` and NULL bounds, so they
  drop out of averages instead of dragging them down.
* **Casing typo.** `0-250 Sq.ft` (1 row) vs `0-250 Sq.Ft`. Kept as a separate label
  with identical bounds.

### 1.4 Range and domain violations

| Column | Bad values | Detail |
|---|---|---|
| `occupancy_or_vacancy_date` | **147** | years `0002`, `0003`, `0285`, `0987`, `1012`, … and `3022`, `5020` |
| `signature_date` | **136** | 134 rows dated year `0001`, plus one 1974 and one 1977, against a 2022–2026 filing window |
| `vacancy_date` | **88** | years `0022`–`0025`, `3024` |
| `occupancy_or_vacancy_date_year` | **57** | `20204`, `202023`, `12023`, `2008.`, `1985.`, `21`, `06`, `84` |

**Fix.** MySQL's `DATE` domain starts at `1000-01-01`, so these cannot simply be
stored. Each is set to NULL, the column carries a `CHECK` enforcing its window, and
the discarded text is preserved on a `record_quality_flag` row
(`rejected_value`) — **flagged, never dropped**. Unparseable years land in
`occupancy_year_raw`.

### 1.5 Internal contradictions

| Contradiction | Rows | Treatment |
|---|---|---|
| Unit reported occupied *after* the filing was signed | 2,203 | flag `occupancy_after_signature` |
| Occupancy date later than the extract date (2026-09-03) | 9 | flag `occupancy_in_future` |
| `occupancy_type = Vacant` yet a rent band was reported | 1,594 | flag `vacant_with_rent` |
| `occupancy_type = Occupied by non-owner` yet no rent band | 1,895 | flag `tenant_without_rent` |
| `bathroom_count` holds bedroom text (`One-Bedroom`, `2 bedroom`) | 18 | flag `bathroom_holds_bedroom_text` |
| `unit_count = 0` on a building that is filing on a unit | 3,560 | flag `zero_unit_count` |
| A history range that ends before it starts | 418 | `occupancy_history.is_reversed`; both dates are kept as filed |
| `..._date_year` contradicts the year of `..._date` | 19 | all 19 sit on rows whose date is *also* out of range, so the year survives in `occupancy_year_raw`; the `year_disagrees_with_date` flag fires 0 times on this extract and guards future ones |

Not a contradiction, and deliberately not flagged: **missing rent is structural for
three of the four occupancy types.** 100% of `Occupied by owner` (27,921) and
`Non-Residential` (2,626) rows report no rent, as do 33,947 of 36,079 `Vacant` rows.
Only 1,895 of 483,575 tenant-occupied rows are genuinely missing one. Treating the
66,389 blank rents as a 12% missingness problem would be a misreading.

### 1.6 Format inconsistency

* `unit_count` is written both `70` and `72.0` for the same quantity (115 of the 301
  distinct values carry a `.0`, covering 55,014 rows). Stored as `DECIMAL(6,1)`.
* `block_num` is zero-padded to 4 characters on 532,161 rows and 5 on 18,034.
  Preserved as `VARCHAR(5)` — it is an identifier, not a number.
* `date_range_type` inside the history JSON: `Occupied` 35,859 / `Vacant` 36,598 /
  **null 8,535** / `Occupied - Non Owner` 9 / `occupied` 2 / `vacant` 1. Only the
  three canonical spellings are stored; the stray lower-case pair is case-folded and
  typeless entries stay NULL.
* `block_address` parses cleanly: 7,676 of 7,677 distinct labels match
  `^(\d+) Block of (.+)$`. The one exception is the truncated `0 Block of`.
* **Case-only duplicates force a case-sensitive database.** `Studio`/`studio`,
  `Two-Bedroom`/`Two-bedroom`, `One-bedroom`/`One-Bedroom`, `0-250 Sq.Ft`/`0-250 Sq.ft`
  and the lower-cased copy of the shared-bathroom phrase are distinct raw labels that
  collide under MySQL's default `utf8mb4_0900_ai_ci`. `RentBoardDB` is therefore
  created `COLLATE utf8mb4_0900_as_cs`; with the default collation the `UNIQUE
  raw_label` keys fail to load.

### 1.7 Redundancy

| Column | Why it is redundant |
|---|---|
| `data_as_of`, `data_loaded_at` | **One distinct value each** across all 550,201 rows. They describe the extract. |
| `case_type_name` | 1:1 with `submission_year` (5 groups, 0 violations). `Housing Inventory - Unit information (2024)` says nothing the year does not. |
| `occupancy_or_vacancy_date_year` | Derivable from `occupancy_or_vacancy_date` on the 447,141 rows that have both. |
| `analysis_neighborhood`, `supervisor_district` | Determined by `point`; 550,201 repetitions of 13,435 facts. |

### 1.8 Duplicate filings — recorded, not resolved

**40,797 rows are byte-identical to another row on all 27 non-key columns**, spread
over 21,008 groups covering 61,805 rows.

They are *not* deleted. At this grain two identical studios in the same building, in
the same filing year, with a banded rent and a privacy-jittered coordinate are
genuinely indistinguishable from one form submitted twice — the data cannot tell
which. Every row loads, and `unit_record.dup_group_id` points at a `duplicate_group`
row carrying the content hash and member count, so an analysis can collapse them
deliberately (`WHERE dup_group_id IS NULL OR <pick one per group>`) and say that it did.

### 1.9 Missingness worth knowing about

| Column | Null rate | |
|---|---|---|
| `base_rent_includes_other_utilities` | 92.95% | expected — it is the "anything else?" box |
| `occupancy_or_vacancy_date_history` | 85.28% | only filings that reported a prior range |
| `vacancy_date` | 96.15% | 56% populated for `Vacant`, <0.2% for every other type |
| `past_occupancy` | 27.74% | |
| `occupancy_or_vacancy_date` | 18.73% | 9,560 of these chose a "Year Unknown" phrase instead |
| `monthly_rent` | 12.07% | mostly structural — see §1.5 |
| `bedroom_count` / `bathroom_count` | 5.54% / 5.51% | |
| `year_property_built` | 2.95% | |
| `block_num` 6 · `analysis_neighborhood` 19 · `supervisor_district` 16 · `point` 3 · `block_address` 80 · `unit_count` 2 · `square_footage` 505 | <0.1% | |

---

## 2. Functional dependencies

Every decomposition in the DDL rests on one of these, measured on the raw file.

### Dependencies that hold exactly

| FD | Groups | Violations | Used for |
|---|---|---|---|
| `unique_id` → everything | 550,201 | 0 | `unit_record` primary key |
| `submission_year` → `case_type_name` (and back: a bijection) | 5 | 0 | `filing_cycle` |
| `point` → `analysis_neighborhood` | 13,430 | 0 | `location_point.neighborhood_id` |
| `point` → `supervisor_district` | 13,431 | 0 | `location_point.district_id` |
| `monthly_rent` → bounds, `square_footage` → bounds | 33 / 19 | 0 | `rent_band`, `sqft_band` |
| `bedroom_count` → canonical bedrooms | 45 | 0 | `bedroom_type` |
| ∅ → `data_as_of`, `data_loaded_at` (constants) | 1 | 0 | `extract_batch` |

Because the fact table's key is the single column `unique_id`, **2NF is automatic** —
a non-trivial dependency on a proper subset of the key is impossible. All the
decomposition work was removing 3NF *transitive* dependencies:
`unique_id → submission_year → case_type_name`,
`unique_id → point → analysis_neighborhood`,
`unique_id → monthly_rent → rent bounds`.

### Dependencies that fail — and what they rule out

| Candidate FD | Violation rate | Consequence |
|---|---|---|
| `analysis_neighborhood` → `supervisor_district` | 25 of 41 neighborhoods span 2–4 districts | Neighborhood and district hang off the point **independently**; no `neighborhood → district` chain |
| `block_num` → `block_address` | 3,588 of 4,287 (83.7%) | |
| `block_num` → `year_property_built` | 84.7% | |
| `block_num` → `unit_count` | 79.5% | |
| `block_num` → `point` | 84.6% | |
| `block_num` + `block_address` → `year_property_built` | 56.4% | |

**There is deliberately no `property` or `building` table.** An assessor block holds
many buildings, and `point` is a privacy-jittered coordinate that is *re-randomized
per filing* — 13,435 distinct points over 4,287 blocks, with the same block reporting
a different point in different years. Nothing below the filing row can be keyed to a
building. Consequently `unit_count` and `year_property_built` stay on the fact table
as *what this filer reported this year*, not as building attributes.

---

## 3. The 3NF model

21 tables. Fact table `unit_record` (550,201 rows) plus:

**Extract / cycle** — `extract_batch`, `filing_cycle`
**Geography** — `neighborhood`, `supervisor_district`, `location_point`
**Address labels** — `assessor_block`, `street_block`
**Categorical lookups** — `occupancy_type`, `bedroom_type`, `bathroom_type`,
`sqft_band`, `rent_band`, `date_unknown_reason`, `date_range_type`
**Quality** — `quality_flag`, `record_quality_flag`, `duplicate_group`
**Multi-valued children** — `utility`, `record_utility_included`, `occupancy_history`

Two details worth calling out:

**Move-in timing is stored exactly one way.** 447,141 rows carry both a date and a
year, 33,402 carry a year with no date, 0 carry a date with no year. Where the date
exists the year is a derived copy, so it is not stored. `unit_record` enforces with a
`CHECK` that at most one of `occupancy_or_vacancy_date`, `occupancy_or_vacancy_year`,
`date_unknown_reason_id`, `occupancy_year_raw` is populated. The 9,560 rows that
chose a "Year Unknown (…)" phrase get a `date_unknown_reason_id` with the phrase's
`approx_min_yrs`/`approx_max_yrs` parsed out, so they remain usable.

**Nothing is discarded silently.** Anything that cannot satisfy a column's domain
leaves a `record_quality_flag` row carrying the original text (9,835 flag rows over
11 flag types). `validate_3nf.sql` prints the full tally.

---

## 4. Verification — measured, not asserted

The schema and loader were run end to end against the project's MySQL 8.0.32 at
`127.0.0.1:3306` (`ONLY_FULL_GROUP_BY`, `STRICT_TRANS_TABLES`, `NO_ZERO_DATE`), and
again against a throwaway MySQL 9.4 instance. Identical results on both.

| Check | Result |
|---|---|
| `schema_3nf.sql` executes | clean, 21 tables, no warnings, collation `utf8mb4_0900_as_cs` |
| Every staged row reaches its table | 11 of 11 tables `ok` (see below) |
| Foreign-key integrity after the bulk load | 0 orphans on all 4 reference checks |
| `point → neighborhood`, `unique_id` uniqueness, one-date-representation, `submission_year → case_type_name` | 0 violations each |
| `neighborhood → district`, `block_num → block_address` | 25 and 3,588 violations — the expected failures that justify the model |
| **Round-trip row count** | `v_inventory_flat` returns exactly **550,201** |
| **Round-trip content** | all 550,201 rows compared against the CSV across all 27 non-key columns: **exact match on 24**; `unit_count` and `point` match numerically (formatting only); the 371 out-of-domain dates are NULL by design |
| Whole pipeline wall time | ~2 min to stage, 21 s to load, 18 s to validate |
| The 371 rejected dates | recovered **verbatim** from `record_quality_flag.rejected_value`, 0 mismatches |

Loaded row counts:

| Table | Rows | | Table | Rows |
|---|---:|---|---|---:|
| `unit_record` | 550,201 | | `location_point` | 13,435 |
| `record_utility_included` | 700,285 | | `street_block` | 7,677 |
| `occupancy_history` | 81,004 | | `assessor_block` | 4,287 |
| `duplicate_group` | 21,008 | | `bedroom_type` / `bathroom_type` | 45 / 31 |
| `record_quality_flag` | 9,835 | | `neighborhood` | 41 |

Two traps worth recording, both found by running it rather than reading it:

1. **`LOAD DATA` downgrades a CHECK-constraint failure to a warning and discards the
   row.** A `CHECK (end_date >= start_date)` on `occupancy_history` silently dropped
   418 of 81,004 rows. The constraint is gone, replaced by a generated `is_reversed`
   column, and `load_3nf.sql` now asserts every table's loaded count against what was
   staged so a silent drop cannot recur.
2. **The default collation is case-insensitive**, which makes the `UNIQUE raw_label`
   keys reject labels that differ only in case — the very values the model exists to
   preserve. See §1.6.

## 5. Limitations of the source data

These are properties of the export, not of the model, and they bound what any
analysis can claim:

1. **Rent is a sitting tenant's contract rent under rent control, not an asking
   rent.** The sample is dominated by long tenancies. Year-over-year movement in
   these figures mostly reflects tenant turnover, not price changes.
2. **No unit identity across years.** The same physical unit cannot be followed
   between filings, so nothing here supports a true panel.
3. **Coordinates are jittered and re-randomized per filing.** They locate a
   neighborhood, not a building.
4. **Rents and areas are bands, not values.** Any midpoint is an assumption, and the
   open-ended top bands (`$7000+`, `4000+ Sq.Ft`) have no midpoint in the data at all
   — hence the NULL upper bounds rather than a fabricated ceiling.
5. **21,008 duplicate groups are unresolvable** at this grain (§1.8).
