# Study guide: understanding this implementation

This document is for personal and team discussion. It is not a final project solution. The goal is to help explain the reasoning well enough to question, revise, or replace parts of the design.

## Recommended learning order

### 1. Understand the source grain

Start with the sentence:

> One row represents one rental-unit report in one filing.

This determines what the primary key means. `unique_id` identifies a source report, not necessarily a physical unit. The data does not provide a reliable key that links the same unit across multiple years.

Before reading the SQL, answer:

- What does one row represent?
- What does `unique_id` identify?
- Which columns describe the report itself?
- Which columns are repeated or multi-valued?
- Which values are reported measurements, and which are categories or labels?

If the team disagrees about the grain, stop there. Every normalization and relationship decision depends on it.

### 2. Read the original notes and the 28-column audit

Read [`NOTES_RECONCILIATION.md`](NOTES_RECONCILIATION.md) before the column audit. It connects the team’s original hypotheses and bash findings to the revised design. Your notes are especially useful because they show which ideas were exploratory rather than final.

Read [`COLUMN_DECISIONS.md`](COLUMN_DECISIONS.md) from top to bottom. For every source column, ask:

1. Is the value preserved?
2. Is it converted to a typed value?
3. Is it moved to another relation?
4. Is the raw value still available for auditing?
5. Is the proposed interpretation supported by the data or merely assumed?

Pay special attention to `location_id`, `point`, `block_num`, `unit_count`, and `year_property_built`. These fields are easy to turn into an unsupported `Property` table.

### 3. Understand the normalization stages

#### 1NF

1NF asks whether each stored field is atomic and whether repeating groups have been separated. In this design:

- utility checkbox columns are transformed into `ReportUtility` rows;
- occupancy history becomes rows in `OccupancyHistory`;
- free-text category labels are mapped through lookup tables while raw labels remain available.

Discuss whether the original four utility columns truly violate the version of 1NF taught in class, or whether they are simply a repeated attribute group that is easier to query when normalized.

#### 2NF

2NF concerns partial dependencies on part of a composite key. Because `UnitReport` uses the single-column key `unique_id`, partial dependency is not possible there.

The important decision is not to invent a composite key such as `(block_num, submission_year)`. That key would incorrectly imply one report per block per year and would fail when multiple units share a block.

#### 3NF

3NF removes non-key attributes that depend on other non-key attributes. Examples in this design include:

- `submission_year -> case_type_name`, moved to `FilingCycle`;
- `point -> longitude, latitude, neighborhood, district`, moved to `LocationPoint` if verified;
- raw bedroom label -> canonical bedroom count, moved to `BedroomLabel`;
- raw rent label -> rent bounds/status, moved to `RentBand`.

The key question is always:

> Does this non-key attribute depend directly on the fact-row key, or does it depend on another non-key value?

### 4. Read the Python preprocessing

Read [`clean_inventory.py`](clean_inventory.py) in this order:

1. `clean_text`
2. `normalize_bedroom`
3. `normalize_bathroom`
4. `parse_band`
5. `parse_date`
6. `parse_point`
7. `utility_tokens`
8. `main`

For each function, write down:

- input values it expects;
- values it maps successfully;
- values it converts to `None`;
- raw values it preserves;
- quality issues it records.

The most important design principle is that cleaning should not silently erase evidence. A value that cannot be parsed should either remain as raw text or produce a `QualityIssue` record.

### 5. Read the SQL schema

Read [`schema.sql`](schema.sql) in this order:

1. database and collation;
2. lookup tables;
3. `UnitReport`;
4. `ReportUtility`;
5. `OccupancyHistory`;
6. `QualityIssue`;
7. foreign keys and checks.

For each table, identify:

- primary key;
- candidate natural key, if one exists;
- foreign keys;
- one-to-many or many-to-many relationships;
- nullable columns and why they can be null;
- constraints that reflect a data-quality rule.

Then try to redraw the schema without looking at the file. If the diagram cannot be explained in terms of the source grain and functional dependencies, the model needs revision.

### 6. Read validation last

[`validation.sql`](validation.sql) is not just a technical appendix. It shows which assumptions can be checked after loading:

- row preservation;
- foreign-key integrity;
- lookup consistency;
- dependency checks;
- counts of quality issues.

Add validation queries whenever the team makes a new modeling assumption.

## Main weak points to discuss with the team

### The source version needs confirmation

The local repository copy is a text summary with a `.csv.gz` suffix rather than the original dataset. The attached `Rent_Board_Housing_Inventory_20260927.csv` now provides the exact 28-column source matching the project notes. Use that file for any final unique-value counts and parser checks.

An earlier repository blob contained a different export variant with `location_id` and separate occupancy-history columns. Do not combine that older header or its counts with the attached CSV.

### `location_id` is not yet interpreted

It is preserved, which is safer than dropping it, but the team should confirm what it means from the official data dictionary. It might become useful as a key, or it might be metadata with no analytical role.

### Location functional dependencies need measurement

The proposed `point -> neighborhood, district` relationship should be tested on the actual source file. If one point maps to multiple neighborhoods or districts, those attributes cannot be placed in `LocationPoint` without further modeling.

### Lookup tables do not automatically prove 3NF

Creating a table for every repeated value is not enough. The team should be able to state the functional dependency that justifies each table and explain why the dependency holds in the data.

### The parser is a policy decision

Mapping `1br` to 1 is reasonable. Mapping ambiguous values such as `2AH` requires a team decision. The team should document whether an ambiguous value is mapped, retained as unknown, or flagged for exclusion.

### Rent and square footage are intervals

The schema correctly keeps bands instead of inventing exact values. If a visualization needs a midpoint, that midpoint should be created in a query or analysis step and labeled as an assumption.

### Loading is not fully automated yet

The Python output contains raw labels, while the SQL schema uses lookup-table IDs. A final implementation needs a clear lookup-loading and foreign-key assignment step. This is a good area for the team to simplify or redesign according to the course requirements.

## Questions to ask during team review

- Is the fact-table name understandable to everyone?
- Does the class require a conceptual ER diagram before the relational schema?
- Are surrogate keys allowed, and where are they actually needed?
- Should utility checkboxes remain as columns for simplicity, or become a junction table?
- Does the class expect raw data cleaning outside SQL, and how much preprocessing should be shown?
- Which constraints can MySQL enforce, and which must be reported through validation queries?
- Can every relationship in the ER diagram be explained without guessing a physical building identity?
- Which tables are necessary for the mid-presentation, and which are optional refinements?

## Suggested personal exercise

Take one raw row and manually trace it through the design:

1. identify its `unique_id` and filing year;
2. normalize its bedroom, bathroom, rent, and square-footage values;
3. parse its point and dates;
4. create its `UnitReport` values;
5. create its utility rows;
6. create its history row;
7. identify any quality issues;
8. explain every foreign key used by that row.

If you can perform this trace and explain why each destination relation exists, you understand the implementation well enough to suggest changes confidently.
