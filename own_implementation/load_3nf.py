#!/usr/bin/env python3
"""Stage the verified Rent Board CSV for the current 3NF schema.

The loader deliberately has two passes:

* pass 1 discovers data-derived lookup values and checks file-level metadata;
* pass 2 resolves those values to deterministic IDs and writes one TSV per
  table, plus a MySQL ``LOAD DATA LOCAL INFILE`` script.

This is an import/orchestration aid, not a replacement for ``schema.sql``.
The schema still owns keys, foreign keys, types, and constraints. Python is
used for CSV parsing and normalization because those operations are outside
the main DDL material covered in the course.

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
from collections import defaultdict
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

BATCH_ID = 1
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
}


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


def year_value(raw):
    value, unknown = parse_year(raw)
    return str(value) if value is not None else None, unknown


def address_parts(raw):
    match = re.fullmatch(r"(\d+) Block of\s*(.*)", clean_text(raw) or "")
    if not match:
        return None, None
    return int(match.group(1)), clean_text(match.group(2))


def field(value):
    """Represent SQL NULL as the special LOAD DATA token."""
    return r"\N" if value is None else str(value)


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
        expected = {
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
        }
        actual = set(reader.fieldnames or [])
        missing = sorted(expected - actual)
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


def utility_tokens_for_load(row):
    found = utility_tokens(row)
    other = clean_text(row.get("base_rent_includes_other_utilities"))
    if other and not found:
        found["other"] = {"text"}
    return found


def generate(source, output_dir):
    rows, dims, metadata = load_rows(source)
    ids = build_ids(dims)
    stage = output_dir / "staging"
    stage.mkdir(parents=True, exist_ok=True)

    def rows_for(name, columns, values):
        write_tsv(stage / f"{name}.tsv", columns, values)

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
        canonical, bad = normalize_bedroom(raw)
        bedroom_rows.append({"bedroom_label_id": value, "raw_label": raw,
                             "canonical_bedrooms": canonical, "is_unparseable": int(bad)})
    rows_for("BedroomLabel", ["bedroom_label_id", "raw_label", "canonical_bedrooms", "is_unparseable"], bedroom_rows)

    bathroom_rows = []
    for raw, value in ids["bathroom"].items():
        canonical, shared, bad = normalize_bathroom(raw)
        bathroom_rows.append({"bathroom_label_id": value, "raw_label": raw,
                              "canonical_bathrooms": canonical, "is_shared": int(shared),
                              "is_unparseable": int(bad)})
    rows_for("BathroomLabel", ["bathroom_label_id", "raw_label", "canonical_bathrooms", "is_shared", "is_unparseable"], bathroom_rows)

    sqft_rows, rent_rows = [], []
    for raw, value in ids["sqft"].items():
        lo, hi, opened, status = parse_band(raw, "sqft")
        sqft_rows.append({"sqft_band_id": value, "raw_label": raw, "min_sqft": lo,
                          "max_sqft": hi, "is_unknown": int(status != "reported")})
    for raw, value in ids["rent"].items():
        lo, hi, opened, status = parse_band(raw, "rent")
        rent_rows.append({"rent_band_id": value, "raw_label": raw, "min_rent": lo,
                          "max_rent": hi, "is_no_rent_paid": int(status == "no_rent_paid"),
                          "overlaps_other": int(raw in {"$1750-$2000", "$1751-$2000"})})
    rows_for("SquareFootageBand", ["sqft_band_id", "raw_label", "min_sqft", "max_sqft", "is_unknown"], sqft_rows)
    rows_for("RentBand", ["rent_band_id", "raw_label", "min_rent", "max_rent", "is_no_rent_paid", "overlaps_other"], rent_rows)

    report_rows, utility_rows, history_rows, issue_rows = [], [], [], []
    for row in rows:
        unique_id = clean_text(row.get("unique_id"))
        submission_year = clean_text(row.get("submission_year"))
        occupancy_type = clean_text(row.get("occupancy_type"))
        if submission_year not in dims["filing_cycles"]:
            issue_rows.append({"unique_id": unique_id, "column_name": "submission_year",
                               "issue_code": "unknown_filing_cycle", "raw_value": submission_year,
                               "issue_detail": "not present in the discovered filing-cycle mapping"})
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
            issue_rows.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date",
                               "issue_code": "invalid_date", "raw_value": raw_occ_date,
                               "issue_detail": "could not be converted to a permitted DATE"})
        if raw_sig and not sig_date:
            issue_rows.append({"unique_id": unique_id, "column_name": "signature_date",
                               "issue_code": "invalid_date", "raw_value": raw_sig,
                               "issue_detail": "could not be converted to a permitted DATE"})
        if raw_vac and not vac_date:
            issue_rows.append({"unique_id": unique_id, "column_name": "vacancy_date",
                               "issue_code": "invalid_date", "raw_value": raw_vac,
                               "issue_detail": "could not be converted to a permitted DATE"})
        if point[0] is None and clean_text(row.get("point")):
            issue_rows.append({"unique_id": unique_id, "column_name": "point",
                               "issue_code": "invalid_point", "raw_value": row.get("point"),
                               "issue_detail": "expected WKT POINT (longitude latitude)"})
        occ_year, unknown_text = year_value(row.get("occupancy_or_vacancy_date_year"))
        past = parse_yes_no(row.get("past_occupancy"))
        if clean_text(row.get("past_occupancy")) and past is None:
            issue_rows.append({"unique_id": unique_id, "column_name": "past_occupancy",
                               "issue_code": "unexpected_boolean", "raw_value": row.get("past_occupancy"),
                               "issue_detail": "expected Yes/No or Y/N"})
        raw_bed = clean_text(row.get("bedroom_count"))
        raw_bath = clean_text(row.get("bathroom_count"))
        bedroom_id = ids["bedroom"].get(raw_bed)
        bathroom_id = ids["bathroom"].get(raw_bath)
        sqft_id = ids["sqft"].get(clean_text(row.get("square_footage")))
        rent_id = ids["rent"].get(clean_text(row.get("monthly_rent")))
        if unknown_text:
            issue_rows.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date_year",
                               "issue_code": "unparseable_year", "raw_value": row.get("occupancy_or_vacancy_date_year"),
                               "issue_detail": "retained as date_unknown_text"})

        report_rows.append({
            "unique_id": unique_id, "batch_id": BATCH_ID,
            "submission_year": submission_year or None,
            "block_num": clean_text(row.get("block_num")),
            "block_address_id": ids["address"].get(clean_text(row.get("block_address"))),
            "point_id": ids["point"].get(point),
            "reported_unit_count": decimal_text(row.get("unit_count")),
            "year_property_built": clean_text(row.get("year_property_built")),
            "occupancy_type_id": OCCUPANCY_TYPE_IDS[occupancy_type],
            "bedroom_label_id": bedroom_id, "bathroom_label_id": bathroom_id,
            "sqft_band_id": sqft_id, "rent_band_id": rent_id,
            "occupancy_or_vacancy_date": occ_date, "occupancy_year": occ_year,
            "date_unknown_text": unknown_text, "vacancy_date": vac_date,
            "past_occupancy": past, "other_utilities_raw": clean_text(row.get("base_rent_includes_other_utilities")),
            "signature_date": sig_date,
        })
        for utility, sources in utility_tokens_for_load(row).items():
            utility_id = UTILITY_IDS.get(utility, UTILITY_IDS["other"])
            utility_rows.append({"unique_id": unique_id, "utility_id": utility_id,
                                 "source_checkbox": int("checkbox" in sources),
                                 "source_text": int("text" in sources)})

        raw_history = clean_text(row.get("occupancy_or_vacancy_date_history"))
        if raw_history:
            try:
                events = json.loads(raw_history)
                if not isinstance(events, list):
                    raise ValueError("history is not a JSON array")
            except (json.JSONDecodeError, ValueError) as exc:
                issue_rows.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date_history",
                                   "issue_code": "invalid_history_json", "raw_value": raw_history,
                                   "issue_detail": str(exc)})
                events = []
            for seq_no, event in enumerate(events, start=1):
                if not isinstance(event, dict):
                    issue_rows.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date_history",
                                       "issue_code": "invalid_history_item", "raw_value": str(event),
                                       "issue_detail": "history item is not an object"})
                    continue
                start = parse_date(event.get("start_date"))
                end = parse_date(event.get("end_date"))
                history_rows.append({"unique_id": unique_id, "seq_no": seq_no,
                                     "range_type": clean_text(event.get("date_range_type")),
                                     "start_date": start, "end_date": end,
                                     "is_reversed": int(bool(start and end and end < start))})

    rows_for("UnitReport", ["unique_id", "batch_id", "submission_year", "block_num", "block_address_id", "point_id",
                             "reported_unit_count", "year_property_built", "occupancy_type_id", "bedroom_label_id",
                             "bathroom_label_id", "sqft_band_id", "rent_band_id", "occupancy_or_vacancy_date",
                             "occupancy_year", "date_unknown_text", "vacancy_date", "past_occupancy",
                             "other_utilities_raw", "signature_date"], report_rows)
    rows_for("ReportUtility", ["unique_id", "utility_id", "source_checkbox", "source_text"], utility_rows)
    rows_for("OccupancyHistory", ["unique_id", "seq_no", "range_type", "start_date", "end_date", "is_reversed"], history_rows)
    rows_for("QualityIssue", ["unique_id", "column_name", "issue_code", "raw_value", "issue_detail"], issue_rows)

    tables = [
        ("ExtractBatch", ["batch_id", "data_as_of", "data_loaded_at", "source_filename", "source_row_count"]),
        ("Neighborhood", ["neighborhood_id", "name"]),
        ("LocationPoint", ["point_id", "longitude", "latitude", "neighborhood_id", "district_id"]),
        ("AssessorBlock", ["block_num"]),
        ("BlockAddress", ["block_address_id", "raw_label", "block_range", "street_name"]),
        ("BedroomLabel", ["bedroom_label_id", "raw_label", "canonical_bedrooms", "is_unparseable"]),
        ("BathroomLabel", ["bathroom_label_id", "raw_label", "canonical_bathrooms", "is_shared", "is_unparseable"]),
        ("SquareFootageBand", ["sqft_band_id", "raw_label", "min_sqft", "max_sqft", "is_unknown"]),
        ("RentBand", ["rent_band_id", "raw_label", "min_rent", "max_rent", "is_no_rent_paid", "overlaps_other"]),
        ("UnitReport", ["unique_id", "batch_id", "submission_year", "block_num", "block_address_id", "point_id",
                        "reported_unit_count", "year_property_built", "occupancy_type_id", "bedroom_label_id",
                        "bathroom_label_id", "sqft_band_id", "rent_band_id", "occupancy_or_vacancy_date",
                        "occupancy_year", "date_unknown_text", "vacancy_date", "past_occupancy",
                        "other_utilities_raw", "signature_date"]),
        ("ReportUtility", ["unique_id", "utility_id", "source_checkbox", "source_text"]),
        ("OccupancyHistory", ["unique_id", "seq_no", "range_type", "start_date", "end_date", "is_reversed"]),
        ("QualityIssue", ["unique_id", "column_name", "issue_code", "raw_value", "issue_detail"]),
    ]
    sql_path = output_dir / "load_3nf.sql"
    with sql_path.open("w", encoding="utf-8") as handle:
        handle.write("-- Generated by load_3nf.py after schema.sql has been run.\n")
        handle.write("-- Utility, OccupancyType, FilingCycle, and SupervisorDistrict are seeded by schema.sql.\n")
        handle.write("USE sf_rent_board;\n")
        for table, columns in tables:
            path = (stage / f"{table}.tsv").resolve().as_posix().replace("'", "\\'")
            handle.write("\nLOAD DATA LOCAL INFILE '" + path + "'\n")
            handle.write(f"INTO TABLE {table}\n")
            handle.write("FIELDS TERMINATED BY '\\t' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY '\\\\'\n")
            handle.write("LINES TERMINATED BY '\\n'\n")
            handle.write("IGNORE 1 LINES\n")
            handle.write("(" + ", ".join(columns) + ");\n")

    print(json.dumps({"source_rows": len(rows), "reports": len(report_rows),
                      "history_rows": len(history_rows), "utility_rows": len(utility_rows),
                      "quality_issues": len(issue_rows), "output_dir": str(output_dir)}, indent=2))


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
