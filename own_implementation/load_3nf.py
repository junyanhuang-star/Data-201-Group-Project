#!/usr/bin/env python3
"""Stage the verified Rent Board CSV for the current 3NF schema.

The loader deliberately has two passes:

* pass 1 discovers data-derived lookup values and checks file-level metadata;
* pass 2 resolves those values to deterministic IDs and writes one TSV per
  table, plus a MySQL ``LOAD DATA LOCAL INFILE`` script that ends by checking
  every table's loaded row count against what was staged.

Every source row is loaded. Data-quality problems (a date that cannot be
stored, a field that contradicts another) are written to
``quality_issues.csv`` in the output directory instead of the database, so
the relational schema holds only the cleaned data.

This is an import/orchestration aid, not a replacement for ``schema.sql``.
The schema still owns keys, foreign keys, types, and constraints. Python is
used for CSV parsing and normalization because those operations are outside
the main DDL material covered in the course. The parsing rules themselves live
in clean_inventory.py and are imported here rather than restated.

AI-assistance disclosure:

The data preparation stage heavily relied on AI assistance to implement code
that was not explicitly covered in the course. In addition, the loader was
assisted with AI because loading a CSV onto tables in MySQL Workbench was not
specifically covered in the course. This loader was considered a practical,
least-tedious way to clean and load the dataset onto Workbench. The team will
review, understand, verify, and modify this implementation before deciding
whether to use any part of it in the final project, and any adopted assistance
will be properly disclosed.
"""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from clean_inventory import (
    clean_text,
    normalize_bathroom,
    normalize_bedroom,
    open_csv,
    parse_band,
    parse_date,
    parse_point,
    parse_year,
    parse_yes_no,
    utility_tokens,
)

csv.field_size_limit(10**9)

# IDs mirrored from the seed data in schema.sql.
BATCH_ID = 1
# Filing window for signature_date. Dates outside it are kept as filed and
# flagged, since the 1900-2026 DATE window already rejects impossible values.
SIGNATURE_WINDOW = ("2022-01-01", "2026-12-31")
OCCUPANCY_TYPE_IDS = {
    "Occupied by non-owner": 1,
    "Vacant": 2,
    "Occupied by owner": 3,
    "Non-Residential": 4,
}
UTILITY_IDS = {
    "water_sewer": 1,
    "natural_gas": 2,
    "electricity": 3,
    "refuse_recycling": 4,
    "heat": 5,
    "internet": 6,
    "parking": 7,
    "storage": 8,
    "pest_control": 9,
    "other": 10,
    "hot_water": 11,
    "cable": 12,
    "laundry": 13,
    "janitorial": 14,
    "solar": 15,
    "all_utilities": 16,
}
# Every issue code the loader can write to quality_issues.csv, with the one
# description that goes with it. An unknown code is a programming error.
ISSUE_CODES = {
    "invalid_date": "date could not be stored as a DATE in 1900-2026; raw text kept here",
    "invalid_point": "point is not WKT POINT (longitude latitude)",
    "unexpected_boolean": "past_occupancy is not Yes/No or Y/N",
    "invalid_history_json": "occupancy history is not a JSON array",
    "invalid_history_item": "occupancy history item is not an object",
    "unknown_filing_cycle": "submission_year not in the filing-cycle mapping",
    "unparseable_year": "year text that is neither a year nor a 'Year Unknown' answer; kept in date_unknown_text",
    "year_disagrees_with_date": "year column contradicts a valid date; the year is not stored",
    "signature_outside_filing_window": "signature_date valid but outside 2022-2026; kept as filed",
    "occupancy_after_signature": "occupancy date follows the signature date",
    "occupancy_in_future": "occupancy date follows the extract date",
    "vacant_with_rent": "occupancy_type is Vacant yet a paid rent band was reported",
    "tenant_without_rent": "occupancy_type is Occupied by non-owner yet no rent band was reported",
    "bathroom_holds_bedroom_text": "bathroom_count contains a bedroom phrase",
    "zero_unit_count": "unit_count reported as 0 for a building filing on a unit",
    "invalid_year_built": "year_property_built outside 1800-2030 or not a year; stored as NULL",
}
ISSUE_COLUMNS = ["unique_id", "column_name", "issue_code", "raw_value", "description"]

# The two malformed rent bands that overlap their neighbour by one dollar
# ("$250-$500" vs "$251-$500", "$1750-$2000" vs "$1751-$2000"). The normal
# form bands are not flagged.
OVERLAPPING_RENT_BANDS = {"$250-$500", "$1750-$2000"}

# Long raw values (e.g. a whole history JSON) are cut to keep the log readable.
RAW_VALUE_MAX = 255

EXPECTED_COLUMNS = [
    "unique_id", "block_num", "unit_count", "case_type_name",
    "submission_year", "block_address", "occupancy_type",
    "occupancy_or_vacancy_date", "occupancy_or_vacancy_date_year",
    "bedroom_count", "bathroom_count", "square_footage", "monthly_rent",
    "base_rent_includes_water_sewer", "base_rent_includes_natural_gas",
    "base_rent_includes_electricity", "base_rent_includes_refuse_recycling",
    "base_rent_includes_other_utilities", "past_occupancy", "vacancy_date",
    "signature_date", "occupancy_or_vacancy_date_history",
    "year_property_built", "point", "analysis_neighborhood",
    "supervisor_district", "data_as_of", "data_loaded_at",
]


def mysql_datetime(raw):
    """Convert the export timestamp to MySQL's DATETIME spelling."""
    raw = clean_text(raw)
    if not raw:
        return None
    for fmt in ("%Y/%m/%d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


def decimal_text(raw):
    """Keep a numeric source value in a form MySQL can load."""
    raw = clean_text(raw)
    if not raw:
        return None
    try:
        return f"{float(raw):.1f}"
    except ValueError:
        return None


def year_built_value(raw):
    """Return year_property_built if it satisfies the schema CHECK, else None.

    A value outside the CHECK would make LOAD DATA skip the whole row, so it
    is set to NULL here and recorded as a quality issue instead.
    """
    raw = clean_text(raw)
    if raw and raw.isdigit() and 1800 <= int(raw) <= 2030:
        return raw
    return None


def address_parts(raw):
    match = re.fullmatch(r"(\d+) Block of\s*(.*)", clean_text(raw) or "")
    if not match:
        return None, None
    return int(match.group(1)), clean_text(match.group(2))


def write_tsv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        # Use backslash as the LOAD DATA escape character. NULL must remain
        # the special unquoted token \N; using csv.writer directly would
        # escape that backslash and turn it into a literal string.
        handle.write("\t".join(columns) + "\n")

        def encode(value):
            if value is None:
                return r"\N"
            text = str(value)
            text = (text.replace("\\", "\\\\").replace('"', '\\"')
                    .replace("\t", "\\t").replace("\r", "\\r")
                    .replace("\n", "\\n"))
            return f'"{text}"'

        for row in rows:
            handle.write("\t".join(encode(row.get(column)) for column in columns) + "\n")


def load_rows(source):
    """Read the source once and return rows plus discovered dimension values."""
    rows = []
    unique_ids = set()
    dims = {
        "neighborhoods": set(),
        "districts": set(),
        "points": {},
        "blocks": set(),
        "addresses": set(),
        "bedrooms": set(),
        "bathrooms": set(),
        "sqft": set(),
        "rent": set(),
        "filing_cycles": {},
    }
    metadata = None
    conflicts = []

    with open_csv(source) as handle:
        reader = csv.DictReader(handle)
        actual = set(reader.fieldnames or [])
        missing = sorted(set(EXPECTED_COLUMNS) - actual)
        if missing:
            raise ValueError(f"CSV is missing expected columns: {', '.join(missing)}")

        for row_number, row in enumerate(reader, start=2):
            unique_id = clean_text(row.get("unique_id"))
            if not unique_id:
                conflicts.append(f"row {row_number}: missing unique_id")
                continue
            if unique_id in unique_ids:
                conflicts.append(f"row {row_number}: duplicate unique_id {unique_id}")
                continue
            unique_ids.add(unique_id)

            current_metadata = (mysql_datetime(row.get("data_as_of")),
                                mysql_datetime(row.get("data_loaded_at")))
            if metadata is None:
                metadata = current_metadata
            elif current_metadata != metadata:
                conflicts.append(f"row {row_number}: extract metadata differs from first row")

            submission_year = clean_text(row.get("submission_year"))
            case_type = clean_text(row.get("case_type_name"))
            if submission_year and case_type:
                previous = dims["filing_cycles"].setdefault(submission_year, case_type)
                if previous != case_type:
                    conflicts.append(f"row {row_number}: case type differs for year {submission_year}")

            block = clean_text(row.get("block_num"))
            neighborhood = clean_text(row.get("analysis_neighborhood"))
            district = clean_text(row.get("supervisor_district"))
            point = parse_point(row.get("point"))
            if block:
                dims["blocks"].add(block)
            if neighborhood:
                dims["neighborhoods"].add(neighborhood)
            if district and district.isdigit():
                dims["districts"].add(int(district))
            if point[0] is not None:
                key = point
                value = (neighborhood, int(district) if district and district.isdigit() else None)
                if key in dims["points"] and dims["points"][key] != value:
                    conflicts.append(f"row {row_number}: point maps to conflicting geography")
                else:
                    dims["points"][key] = value

            for name, target in (("block_address", "addresses"),
                                 ("bedroom_count", "bedrooms"),
                                 ("bathroom_count", "bathrooms"),
                                 ("square_footage", "sqft"),
                                 ("monthly_rent", "rent")):
                value = clean_text(row.get(name))
                if value:
                    dims[target].add(value)
            rows.append(row)

    if conflicts:
        raise ValueError("\n".join(conflicts[:10]) +
                         ("\nadditional conflicts omitted" if len(conflicts) > 10 else ""))
    if metadata is None:
        raise ValueError("CSV contains no data rows with extract metadata")
    return rows, dims, metadata


def build_ids(dims):
    """Create deterministic IDs for dimensions populated by the CSV."""
    ids = {}
    ids["neighborhood"] = {v: i for i, v in enumerate(sorted(dims["neighborhoods"]), 1)}
    ids["point"] = {v: i for i, v in enumerate(sorted(dims["points"]), 1)}
    ids["block"] = {v: v for v in sorted(dims["blocks"])}
    ids["address"] = {v: i for i, v in enumerate(sorted(dims["addresses"]), 1)}
    ids["bedroom"] = {v: i for i, v in enumerate(sorted(dims["bedrooms"]), 1)}
    ids["bathroom"] = {v: i for i, v in enumerate(sorted(dims["bathrooms"]), 1)}
    ids["sqft"] = {v: i for i, v in enumerate(sorted(dims["sqft"]), 1)}
    ids["rent"] = {v: i for i, v in enumerate(sorted(dims["rent"]), 1)}
    return ids


def generate(source, output_dir):
    rows, dims, metadata = load_rows(source)
    ids = build_ids(dims)
    extract_date = metadata[0][:10] if metadata[0] else None
    stage = output_dir / "staging"
    stage.mkdir(parents=True, exist_ok=True)
    staged_counts = {}

    def rows_for(name, columns, values):
        write_tsv(stage / f"{name}.tsv", columns, values)
        staged_counts[name] = len(values)

    rows_for("ExtractBatch",
             ["batch_id", "data_as_of", "data_loaded_at", "source_filename", "source_row_count"],
             [{"batch_id": BATCH_ID, "data_as_of": metadata[0],
               "data_loaded_at": metadata[1], "source_filename": source.name,
               "source_row_count": len(rows)}])
    rows_for("Neighborhood", ["neighborhood_id", "name"],
             [{"neighborhood_id": i, "name": name}
              for name, i in ids["neighborhood"].items()])
    rows_for("LocationPoint", ["point_id", "longitude", "latitude", "neighborhood_id", "district_id"],
             [{"point_id": i, "longitude": point[0], "latitude": point[1],
               "neighborhood_id": ids["neighborhood"].get(geo[0]), "district_id": geo[1]}
              for point, i in ids["point"].items()
              for geo in [dims["points"][point]]])
    rows_for("AssessorBlock", ["block_num"],
             [{"block_num": value} for value in ids["block"]])
    rows_for("BlockAddress", ["block_address_id", "raw_label", "block_range", "street_name"],
             [{"block_address_id": i, "raw_label": value,
               "block_range": address_parts(value)[0], "street_name": address_parts(value)[1]}
              for value, i in ids["address"].items()])

    bedroom_rows = []
    for raw, value in ids["bedroom"].items():
        canonical, _ = normalize_bedroom(raw)
        bedroom_rows.append({"bedroom_label_id": value, "raw_label": raw,
                             "canonical_bedrooms": canonical})
    rows_for("BedroomLabel", ["bedroom_label_id", "raw_label", "canonical_bedrooms"], bedroom_rows)

    bathroom_rows = []
    for raw, value in ids["bathroom"].items():
        canonical, shared, _ = normalize_bathroom(raw)
        bathroom_rows.append({"bathroom_label_id": value, "raw_label": raw,
                              "canonical_bathrooms": canonical, "is_shared": int(shared)})
    rows_for("BathroomLabel", ["bathroom_label_id", "raw_label", "canonical_bathrooms", "is_shared"], bathroom_rows)

    sqft_rows, rent_rows = [], []
    for raw, value in ids["sqft"].items():
        lo, hi, _, _ = parse_band(raw, "sqft")
        sqft_rows.append({"sqft_band_id": value, "raw_label": raw, "min_sqft": lo,
                          "max_sqft": hi})
    for raw, value in ids["rent"].items():
        lo, hi, _, _ = parse_band(raw, "rent")
        rent_rows.append({"rent_band_id": value, "raw_label": raw, "min_rent": lo,
                          "max_rent": hi, "overlaps_other": int(raw in OVERLAPPING_RENT_BANDS)})
    rows_for("SquareFootageBand", ["sqft_band_id", "raw_label", "min_sqft", "max_sqft"], sqft_rows)
    rows_for("RentBand", ["rent_band_id", "raw_label", "min_rent", "max_rent", "overlaps_other"], rent_rows)

    report_rows, utility_rows, history_rows, issue_rows = [], [], [], []
    for row in rows:
        unique_id = clean_text(row.get("unique_id"))

        # The detail argument documents the rule at the call site; the logged
        # description comes from ISSUE_CODES, one text per code.
        def issue(column, code, raw_value, detail):
            if code not in ISSUE_CODES:
                raise ValueError(f"issue code {code!r} is not listed in ISSUE_CODES")
            raw_value = None if raw_value is None else str(raw_value)[:RAW_VALUE_MAX]
            issue_rows.append({"unique_id": unique_id, "column_name": column,
                               "issue_code": code, "raw_value": raw_value,
                               "description": ISSUE_CODES[code]})

        submission_year = clean_text(row.get("submission_year"))
        occupancy_type = clean_text(row.get("occupancy_type"))
        if submission_year not in dims["filing_cycles"]:
            issue("submission_year", "unknown_filing_cycle", submission_year,
                  "not present in the discovered filing-cycle mapping")
        if occupancy_type not in OCCUPANCY_TYPE_IDS:
            raise ValueError(f"unsupported occupancy_type for {unique_id}: {occupancy_type!r}")

        point = parse_point(row.get("point"))
        raw_occ_date = clean_text(row.get("occupancy_or_vacancy_date"))
        occ_date = parse_date(raw_occ_date)
        raw_sig = clean_text(row.get("signature_date"))
        sig_date = parse_date(raw_sig)
        raw_vac = clean_text(row.get("vacancy_date"))
        vac_date = parse_date(raw_vac)
        if raw_occ_date and not occ_date:
            issue("occupancy_or_vacancy_date", "invalid_date", raw_occ_date,
                  "could not be converted to a permitted DATE")
        if raw_sig and not sig_date:
            issue("signature_date", "invalid_date", raw_sig,
                  "could not be converted to a permitted DATE")
        elif sig_date and not SIGNATURE_WINDOW[0] <= sig_date <= SIGNATURE_WINDOW[1]:
            issue("signature_date", "signature_outside_filing_window", raw_sig,
                  "signed outside the 2022-2026 filing window; date kept as filed")
        if raw_vac and not vac_date:
            issue("vacancy_date", "invalid_date", raw_vac,
                  "could not be converted to a permitted DATE")
        if point[0] is None and clean_text(row.get("point")):
            issue("point", "invalid_point", row.get("point"),
                  "expected WKT POINT (longitude latitude)")

        # Move-in timing is stored in exactly one form (see UnitReport in
        # schema.sql). The CHECK there would make LOAD DATA skip a row that
        # broke this rule, so it is enforced here before staging.
        # The form's "Year Unknown (...)" answers are stored as text without a
        # quality issue; other non-year text is stored and flagged.
        raw_year = clean_text(row.get("occupancy_or_vacancy_date_year"))
        occ_year, unknown_phrase, junk_year = parse_year(raw_year)
        if occ_date:
            if raw_year and raw_year != occ_date[:4]:
                issue("occupancy_or_vacancy_date_year", "year_disagrees_with_date", raw_year,
                      "year column contradicts the stored date; the year is not stored")
            occ_year = unknown_phrase = junk_year = None
        elif junk_year:
            issue("occupancy_or_vacancy_date_year", "unparseable_year", raw_year,
                  "retained as date_unknown_text")
        date_text = unknown_phrase or junk_year

        past = parse_yes_no(row.get("past_occupancy"))
        if clean_text(row.get("past_occupancy")) and past is None:
            issue("past_occupancy", "unexpected_boolean", row.get("past_occupancy"),
                  "expected Yes/No or Y/N")

        raw_built = clean_text(row.get("year_property_built"))
        year_built = year_built_value(raw_built)
        if raw_built and year_built is None:
            issue("year_property_built", "invalid_year_built", raw_built,
                  "outside 1800-2030 or not a year; stored as NULL")

        raw_bed = clean_text(row.get("bedroom_count"))
        raw_bath = clean_text(row.get("bathroom_count"))
        raw_rent = clean_text(row.get("monthly_rent"))
        unit_count = decimal_text(row.get("unit_count"))

        # Contradictions between columns. These rows are loaded as filed and
        # flagged so an analysis can exclude or discuss them.
        if occ_date and sig_date and occ_date > sig_date:
            issue("occupancy_or_vacancy_date", "occupancy_after_signature", occ_date,
                  "reported occupancy date follows signature date")
        if occ_date and extract_date and occ_date > extract_date:
            issue("occupancy_or_vacancy_date", "occupancy_in_future", occ_date,
                  "reported occupancy date follows the extract date")
        # "$0 (no rent paid)" on a vacant unit is consistent, not a contradiction.
        rent_paid = raw_rent and parse_band(raw_rent, "rent")[3] != "no_rent_paid"
        if occupancy_type == "Vacant" and rent_paid:
            issue("monthly_rent", "vacant_with_rent", raw_rent,
                  "occupancy_type is Vacant yet a paid rent band was reported")
        if occupancy_type == "Occupied by non-owner" and not raw_rent:
            issue("monthly_rent", "tenant_without_rent", None,
                  "occupancy_type is Occupied by non-owner yet no rent band was reported")
        if raw_bath and ("bedroom" in raw_bath.lower() or "bedrom" in raw_bath.lower()):
            issue("bathroom_count", "bathroom_holds_bedroom_text", raw_bath,
                  "bathroom_count contains a bedroom phrase")
        if unit_count == "0.0":
            issue("unit_count", "zero_unit_count", row.get("unit_count"),
                  "unit_count reported as 0 for a building filing on a unit")

        report_rows.append({
            "unique_id": unique_id, "batch_id": BATCH_ID,
            "submission_year": submission_year or None,
            "block_num": clean_text(row.get("block_num")),
            "block_address_id": ids["address"].get(clean_text(row.get("block_address"))),
            "point_id": ids["point"].get(point),
            "reported_unit_count": unit_count,
            "year_property_built": year_built,
            "occupancy_type_id": OCCUPANCY_TYPE_IDS[occupancy_type],
            "bedroom_label_id": ids["bedroom"].get(raw_bed),
            "bathroom_label_id": ids["bathroom"].get(raw_bath),
            "sqft_band_id": ids["sqft"].get(clean_text(row.get("square_footage"))),
            "rent_band_id": ids["rent"].get(raw_rent),
            "occupancy_or_vacancy_date": occ_date, "occupancy_year": occ_year,
            "date_unknown_text": date_text,
            "vacancy_date": vac_date, "past_occupancy": past,
            "other_utilities_raw": clean_text(row.get("base_rent_includes_other_utilities")),
            "signature_date": sig_date,
        })
        for utility, sources in utility_tokens(row).items():
            if utility not in UTILITY_IDS:
                raise ValueError(f"utility {utility!r} is not seeded in schema.sql")
            utility_rows.append({"unique_id": unique_id, "utility_id": UTILITY_IDS[utility],
                                 "source_checkbox": int("checkbox" in sources),
                                 "source_text": int("text" in sources)})

        raw_history = clean_text(row.get("occupancy_or_vacancy_date_history"))
        if raw_history:
            try:
                events = json.loads(raw_history)
                if not isinstance(events, list):
                    raise ValueError("history is not a JSON array")
            except (json.JSONDecodeError, ValueError) as exc:
                issue("occupancy_or_vacancy_date_history", "invalid_history_json",
                      raw_history, str(exc))
                events = []
            for seq_no, event in enumerate(events, start=1):
                if not isinstance(event, dict):
                    issue("occupancy_or_vacancy_date_history", "invalid_history_item",
                          event, "history item is not an object")
                    continue
                start = parse_date(event.get("start_date"))
                end = parse_date(event.get("end_date"))
                history_rows.append({"unique_id": unique_id, "seq_no": seq_no,
                                     "range_type": clean_text(event.get("date_range_type")),
                                     "start_date": start, "end_date": end})

    tables = [
        ("ExtractBatch", ["batch_id", "data_as_of", "data_loaded_at", "source_filename", "source_row_count"]),
        ("Neighborhood", ["neighborhood_id", "name"]),
        ("LocationPoint", ["point_id", "longitude", "latitude", "neighborhood_id", "district_id"]),
        ("AssessorBlock", ["block_num"]),
        ("BlockAddress", ["block_address_id", "raw_label", "block_range", "street_name"]),
        ("BedroomLabel", ["bedroom_label_id", "raw_label", "canonical_bedrooms"]),
        ("BathroomLabel", ["bathroom_label_id", "raw_label", "canonical_bathrooms", "is_shared"]),
        ("SquareFootageBand", ["sqft_band_id", "raw_label", "min_sqft", "max_sqft"]),
        ("RentBand", ["rent_band_id", "raw_label", "min_rent", "max_rent", "overlaps_other"]),
        ("UnitReport", ["unique_id", "batch_id", "submission_year", "block_num", "block_address_id", "point_id",
                        "reported_unit_count", "year_property_built", "occupancy_type_id", "bedroom_label_id",
                        "bathroom_label_id", "sqft_band_id", "rent_band_id", "occupancy_or_vacancy_date",
                        "occupancy_year", "date_unknown_text", "vacancy_date",
                        "past_occupancy", "other_utilities_raw", "signature_date"]),
        ("ReportUtility", ["unique_id", "utility_id", "source_checkbox", "source_text"]),
        ("OccupancyHistory", ["unique_id", "seq_no", "range_type", "start_date", "end_date"]),
    ]
    fact_rows = {"UnitReport": report_rows, "ReportUtility": utility_rows,
                 "OccupancyHistory": history_rows}
    columns_by_table = dict(tables)
    for name, values in fact_rows.items():
        rows_for(name, columns_by_table[name], values)

    write_load_script(output_dir / "load_3nf.sql", stage, tables, staged_counts)

    issues_path = output_dir / "quality_issues.csv"
    with issues_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ISSUE_COLUMNS)
        writer.writeheader()
        writer.writerows(issue_rows)

    print(json.dumps({"source_rows": len(rows), "reports": len(report_rows),
                      "history_rows": len(history_rows), "utility_rows": len(utility_rows),
                      "quality_issues": len(issue_rows),
                      "quality_issues_by_code": dict(Counter(r["issue_code"] for r in issue_rows).most_common()),
                      "quality_issues_csv": str(issues_path),
                      "output_dir": str(output_dir)}, indent=2))


def write_load_script(sql_path, stage, tables, staged_counts):
    """Write LOAD DATA statements in foreign-key order, then the checks."""
    with sql_path.open("w", encoding="utf-8") as handle:
        handle.write("-- Generated by load_3nf.py after schema.sql has been run.\n")
        handle.write("-- Utility, OccupancyType, FilingCycle, and SupervisorDistrict are\n")
        handle.write("-- seeded by schema.sql. Data-quality problems are in quality_issues.csv.\n")
        handle.write("USE sf_rent_board;\n")
        for table, columns in tables:
            path = (stage / f"{table}.tsv").resolve().as_posix().replace("'", "\\'")
            handle.write(f"\n-- {staged_counts[table]:,} rows staged\n")
            handle.write("LOAD DATA LOCAL INFILE '" + path + "'\n")
            handle.write(f"INTO TABLE {table}\n")
            handle.write("FIELDS TERMINATED BY '\\t' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY '\\\\'\n")
            handle.write("LINES TERMINATED BY '\\n'\n")
            handle.write("IGNORE 1 LINES\n")
            handle.write("(" + ", ".join(columns) + ");\n")

        # LOAD DATA LOCAL turns a constraint failure into a warning and skips
        # the row, so a successful-looking load can still lose rows.
        handle.write("\n-- Every verdict must read 'ok'. LOAD DATA LOCAL turns CHECK and key\n")
        handle.write("-- failures into warnings and skips the row, so compare each table's\n")
        handle.write("-- loaded row count with the number of rows staged.\n")
        checks = [f"SELECT '{table}' AS table_name, COUNT(*) AS rows_loaded, "
                  f"{staged_counts[table]} AS rows_staged, "
                  f"IF(COUNT(*) = {staged_counts[table]}, 'ok', 'ROWS LOST') AS verdict "
                  f"FROM {table}"
                  for table, _ in tables]
        handle.write("\nUNION ALL ".join(checks) + ";\n")

        handle.write("\n-- Every orphan count must be 0.\n")
        orphan_checks = [
            ("UnitReport -> LocationPoint", "UnitReport r LEFT JOIN LocationPoint p ON p.point_id = r.point_id",
             "r.point_id IS NOT NULL AND p.point_id IS NULL"),
            ("UnitReport -> BlockAddress", "UnitReport r LEFT JOIN BlockAddress b ON b.block_address_id = r.block_address_id",
             "r.block_address_id IS NOT NULL AND b.block_address_id IS NULL"),
            ("UnitReport -> AssessorBlock", "UnitReport r LEFT JOIN AssessorBlock b ON b.block_num = r.block_num",
             "r.block_num IS NOT NULL AND b.block_num IS NULL"),
            ("ReportUtility -> UnitReport", "ReportUtility c LEFT JOIN UnitReport r ON r.unique_id = c.unique_id",
             "r.unique_id IS NULL"),
            ("OccupancyHistory -> UnitReport", "OccupancyHistory c LEFT JOIN UnitReport r ON r.unique_id = c.unique_id",
             "r.unique_id IS NULL"),
        ]
        handle.write("\nUNION ALL\n".join(
            f"SELECT '{label}' AS reference, COUNT(*) AS orphans FROM {source} WHERE {condition}"
            for label, source, condition in orphan_checks) + ";\n")


class ThreeNFLoader:
    """Small orchestration class for the two-pass staging workflow.

    The parsing functions remain module-level so they can be read and tested
    independently. The class gives the team one explicit object representing
    a load request: one source CSV and one output directory.
    """

    def __init__(self, source, output_dir):
        self.source = Path(source)
        self.output_dir = Path(output_dir)

    def run(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        generate(self.source, self.output_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    ThreeNFLoader(args.source, args.output_dir).run()


if __name__ == "__main__":
    main()
