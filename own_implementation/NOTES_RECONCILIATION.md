# Reconciliation with the original project notes

The PDF `DATA201 Project Notes.pdf` records the team’s initial investigation. It should be treated as evidence of the exploratory process, while the proposed 3NF model remains open to revision.

## What the notes already established well

- The dataset was divided conceptually into building/property, unit, rental/submission, occupancy-history, utility, and metadata attributes.
- `unique_id` was identified as a likely submission-row key.
- The notes used bash to enumerate distinct values and frequencies for important categorical columns.
- The notes correctly identified inconsistent bedroom and bathroom labels.
- The notes correctly identified rent as a banded value rather than a precise amount.
- The notes correctly identified `base_rent_includes_other_utilities` as difficult free text.
- The notes correctly questioned whether `block_num` can identify a property.
- The notes recognized that `past_occupancy` contains unexpected non-Yes/No values and needs validation.

## Initial hypotheses that should be revisited

| Initial note | Revised interpretation to test |
|---|---|
| `block_num` could be the property key | Test the functional dependency first. If one block has different unit counts, build years, points, or addresses, it cannot identify one property. |
| `unit_count` belongs with both property and unit information | Treat it as one reported attribute at the filing grain unless the source proves a stable building key. Do not duplicate it across relations. |
| `point` may identify a property | Parse longitude and latitude, but verify whether the coordinate is stable. A privacy-jittered point should support geographic analysis, not building identity. |
| `case_type_name` may be useful as a separate attribute | Compare it with `submission_year`. If it is a one-to-one label, keep the relationship in `FilingCycle` rather than repeating it in every fact row. |
| `past_occupancy` is a Yes/No field | The notes show contamination by utility-like text. Map recognized Yes/No values and flag the rest instead of silently converting them. |
| `base_rent_includes_other_utilities` is one Yes/No field | The distinct values show that it is free text and sometimes multi-valued. Preserve the original text and tokenize recognized utilities cautiously. |

## Source-version warning and resolution

The attached `Rent_Board_Housing_Inventory_20260927.csv` confirms that the project notes describe the intended source export: it contains `case_type_name`, `data_as_of`, and `data_loaded_at`, and stores occupancy history in `occupancy_or_vacancy_date_history`.

An earlier repository blob inspected during this work showed a different 28-column header containing `location_id` and separate `occ_history_type`, `occ_history_start`, and `occ_history_end` fields. That earlier blob should not be mixed with the newly attached CSV.

The newly attached CSV is now the source to use for the reference implementation. The 28-column audit and Python cleaner have been aligned to its header. The team should still rerun the unique-value and dependency checks against this file before treating any counts as final.

## Why the proposed model differs from the first relational schema

The initial `Property -> Unit -> SubmissionRecord` structure is understandable as a first conceptual decomposition. The main concern is that the source does not necessarily provide a stable property or unit identifier. The revised model uses `UnitReport` as the fact relation because it makes the actual source grain explicit and avoids inventing a relationship that the data cannot support.

The team can still present the initial model as an early design iteration: it shows the reasoning process, the candidate relationships, and the later evidence that caused the model to change.

## Recommended next check

Run the original bash frequency script against the exact source file selected by the team. Compare its output with the PDF notes. Any difference should be explained by a changed export, a changed filter, or a correction to the original notes before loading data into MySQL.
