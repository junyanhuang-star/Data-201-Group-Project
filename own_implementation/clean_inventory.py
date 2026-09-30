#!/usr/bin/env python3
"""Preprocess the SF Rent Board export before loading it into MySQL.

The script maps spelling variants to canonical values, preserves raw labels,
splits repeating utility and history values, and writes quality issues instead
of silently dropping rows.
"""

import argparse
import csv
import gzip
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

csv.field_size_limit(10**9)

BED_WORDS = {"studio": 0, "zero": 0, "0": 0, "one": 1, "1": 1,
             "two": 2, "2": 2, "three": 3, "3": 3, "four": 4, "4": 4}
UTILITY_WORDS = {
    "water": "water_sewer", "sewer": "water_sewer", "gas": "natural_gas",
    "electric": "electricity", "electricity": "electricity",
    "refuse": "refuse_recycling", "recycling": "refuse_recycling",
    "trash": "refuse_recycling", "heat": "heat", "steam": "heat",
    "boiler": "heat", "internet": "internet", "wifi": "internet",
    "wi-fi": "internet", "parking": "parking", "storage": "storage",
    "pest": "pest_control",
}


def clean_text(value):
    value = (value or "").strip()
    return value or None


def normalize_bedroom(raw):
    raw = clean_text(raw)
    if not raw:
        return None, False
    s = raw.lower().replace("_", " ")
    if "studio" in s or s == "zero-(studio)":
        return 0, False
    if s in {"5+", "five-bedroom"}:
        return 5, False
    match = re.match(r"^(one|two|three|four|five|\d+)", s)
    if not match:
        return None, True
    token = match.group(1)
    number = BED_WORDS.get(token, int(token) if token.isdigit() else None)
    remainder = s[match.end():].strip(" -_.")
    if number is None or (remainder and not re.match(r"^(bed|bedroom|br|bd|\+|\(sm\))", remainder)):
        return None, True
    return min(number, 5), False


def normalize_bathroom(raw):
    raw = clean_text(raw)
    if not raw:
        return None, False, False
    s = raw.lower()
    if "shared bathroom" in s:
        return None, True, False
    if "bedroom" in s or "bedrom" in s or s == "e3":
        return None, False, True
    if s == "none":
        return 0.0, False, False
    if "half" in s:
        base = 1.0 if "one" in s else 2.0 if "two" in s else None
        return (base + 0.5, False, False) if base is not None else (None, False, True)
    if re.match(r"^(one|1)( |-)bath", s):
        return 1.0, False, False
    if re.match(r"^(two|2)( |-)bath", s):
        return 2.0, False, False
    if "three bathrooms" in s:
        return 3.0, False, False
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s), False, False
    return None, False, True


def parse_band(raw, kind):
    raw = clean_text(raw)
    if not raw:
        return None, None, False, "missing"
    if kind == "rent" and (raw == "0" or raw.startswith("$0")):
        return None, None, False, "no_rent_paid"
    numbers = [int(n) for n in re.findall(r"\d+", raw.replace(",", ""))]
    if "+" in raw and numbers:
        return numbers[0], None, True, "reported"
    if len(numbers) == 2:
        return numbers[0], numbers[1], False, "reported"
    return None, None, False, "unparseable"


def parse_date(raw):
    raw = clean_text(raw)
    if not raw:
        return None
    try:
        value = datetime.strptime(raw[:10].replace("/", "-"), "%Y-%m-%d")
    except ValueError:
        return None
    return value.strftime("%Y-%m-%d") if 1900 <= value.year <= 2026 else None


def parse_point(raw):
    match = re.fullmatch(r"POINT \((-?[0-9.]+) (-?[0-9.]+)\)", clean_text(raw) or "")
    return (match.group(1), match.group(2)) if match else (None, None)


def parse_year(raw):
    raw = clean_text(raw)
    if raw and re.fullmatch(r"\d{4}", raw) and 1900 <= int(raw) <= 2026:
        return int(raw), None
    if raw and raw.lower().startswith("year"):
        return None, raw
    return None, raw


def parse_yes_no(raw):
    raw = clean_text(raw)
    if raw is None:
        return None
    if raw.lower() in {"y", "yes", "true"}:
        return "1"
    if raw.lower() in {"n", "no", "false"}:
        return "0"
    return None


def utility_tokens(row):
    # Create a temporary dictionary for utilities found in this one CSV row.
    # The dictionary is not the MySQL Utility lookup table yet. It is an
    # intermediate result that will later become ReportUtility rows.
    found = {}

    # Map each raw checkbox column to the canonical utility name that the
    # normalized database will use. The raw CSV stores these as separate Y/N
    # columns, while the normalized design stores utility membership as rows.
    checkbox_map = {
        "base_rent_includes_water_sewer": "water_sewer",
        "base_rent_includes_natural_gas": "natural_gas",
        "base_rent_includes_electricity": "electricity",
        "base_rent_includes_refuse_recycling": "refuse_recycling",
    }

    # Visit each raw checkbox-to-utility mapping one at a time.
    for column, utility in checkbox_map.items():
        # Get this row's value for the checkbox column. If the column is
        # missing, use an empty string; strip whitespace; and normalize case.
        # Only an explicit Y means that the checkbox asserts inclusion.
        if row.get(column, "").strip().upper() == "Y":
            # Create a set for this utility if it has not appeared yet, then
            # record that the checkbox was one source of the utility claim.
            # setdefault prevents duplicate dictionary-key logic and allows
            # the same utility to be found from both checkbox and free text.
            found.setdefault(utility, set()).add("checkbox")

    # Read the free-text "other utilities" field from the same CSV row. Blank
    # strings become None through clean_text(), which makes them easy to skip.
    other = clean_text(row.get("base_rent_includes_other_utilities"))

    # Search the free-text value for known utility words, such as heat, wifi,
    # parking, or storage. UTILITY_WORDS maps the detected word to a canonical
    # utility name.
    for word, utility in UTILITY_WORDS.items():
        # If the row has free text and the known word occurs in it, record that
        # the utility was asserted by free text. This is substring matching,
        # so the mapping should be reviewed for false matches before submission.
        if other and word in other.lower():
            found.setdefault(utility, set()).add("text")

    # Return the utilities found for this row, including whether each utility
    # came from a checkbox, free text, or both.
    return found


def open_csv(path):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return open(path, "r", encoding="utf-8-sig", newline="")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports, history, utilities, issues = [], [], [], []
    dimensions = {"bedroom": {}, "bathroom": {}, "sqft": {}, "rent": {}}
    stats = Counter()
    extract_metadata = None

    with open_csv(args.source) as source:
        reader = csv.DictReader(source)
        for row in reader:
            unique_id = clean_text(row.get("unique_id"))
            if not unique_id:
                stats["missing_unique_id"] += 1
                continue
            stats["rows_in"] += 1
            row_metadata = (clean_text(row.get("data_as_of")),
                            clean_text(row.get("data_loaded_at")))
            if extract_metadata is None:
                extract_metadata = row_metadata
            elif row_metadata != extract_metadata:
                issues.append({"unique_id": unique_id, "column_name": "data_as_of/data_loaded_at",
                               "issue_code": "inconsistent_extract_metadata",
                               "raw_value": " | ".join(value or "" for value in row_metadata),
                               "issue_detail": "metadata differs from the first accepted row"})
            bed, bed_bad = normalize_bedroom(row.get("bedroom_count"))
            bath, bath_shared, bath_bad = normalize_bathroom(row.get("bathroom_count"))
            sqft_min, sqft_max, sqft_open, sqft_status = parse_band(row.get("square_footage"), "sqft")
            rent_min, rent_max, rent_open, rent_status = parse_band(row.get("monthly_rent"), "rent")
            lon, lat = parse_point(row.get("point"))
            raw_bed, raw_bath = clean_text(row.get("bedroom_count")), clean_text(row.get("bathroom_count"))
            if raw_bed and raw_bed not in dimensions["bedroom"]:
                dimensions["bedroom"][raw_bed] = (bed, bed_bad)
            if raw_bath and raw_bath not in dimensions["bathroom"]:
                dimensions["bathroom"][raw_bath] = (bath, bath_shared, bath_bad)
            for kind, raw, values in (("sqft", row.get("square_footage"), (sqft_min, sqft_max, sqft_open, sqft_status)),
                                       ("rent", row.get("monthly_rent"), (rent_min, rent_max, rent_open, rent_status))):
                raw = clean_text(raw)
                if raw and raw not in dimensions[kind]:
                    dimensions[kind][raw] = values

            occ_date, sig_date, vac_date = (parse_date(row.get(c)) for c in
                                             ("occupancy_or_vacancy_date", "signature_date", "vacancy_date"))
            occupancy_year, date_unknown_text = parse_year(row.get("occupancy_or_vacancy_date_year"))
            for column, raw, parsed in (("occupancy_or_vacancy_date", row.get("occupancy_or_vacancy_date"), occ_date),
                                        ("signature_date", row.get("signature_date"), sig_date),
                                        ("vacancy_date", row.get("vacancy_date"), vac_date)):
                if clean_text(raw) and not parsed:
                    issues.append({"unique_id": unique_id, "column_name": column, "issue_code": "invalid_date",
                                   "raw_value": raw, "issue_detail": "invalid or outside accepted year range"})
            if bed_bad and raw_bed:
                issues.append({"unique_id": unique_id, "column_name": "bedroom_count", "issue_code": "unparseable_category",
                               "raw_value": raw_bed, "issue_detail": "retained as raw label"})
            if bath_bad and raw_bath:
                issues.append({"unique_id": unique_id, "column_name": "bathroom_count", "issue_code": "unparseable_category",
                               "raw_value": raw_bath, "issue_detail": "retained as raw label"})
            if rent_status == "unparseable":
                issues.append({"unique_id": unique_id, "column_name": "monthly_rent", "issue_code": "unparseable_band",
                               "raw_value": row.get("monthly_rent"), "issue_detail": "not converted to a numeric amount"})
            raw_past = clean_text(row.get("past_occupancy"))
            if raw_past and parse_yes_no(raw_past) is None:
                issues.append({"unique_id": unique_id, "column_name": "past_occupancy", "issue_code": "unexpected_boolean",
                               "raw_value": raw_past, "issue_detail": "expected Yes/No or Y/N"})
            if clean_text(row.get("point")) and not (lon and lat):
                issues.append({"unique_id": unique_id, "column_name": "point", "issue_code": "invalid_point",
                               "raw_value": row.get("point"), "issue_detail": "expected WKT POINT (longitude latitude)"})
            if occ_date and sig_date and occ_date > sig_date:
                issues.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date",
                               "issue_code": "occupancy_after_signature", "raw_value": occ_date,
                               "issue_detail": "reported occupancy date follows signature date"})

            reports.append({"unique_id": unique_id, "submission_year": clean_text(row.get("submission_year")),
                "block_num": clean_text(row.get("block_num")), "block_address": clean_text(row.get("block_address")),
                "analysis_neighborhood": clean_text(row.get("analysis_neighborhood")),
                "supervisor_district": clean_text(row.get("supervisor_district")), "point_longitude": lon, "point_latitude": lat,
                "unit_count": clean_text(row.get("unit_count")), "year_property_built": clean_text(row.get("year_property_built")),
                "occupancy_type": clean_text(row.get("occupancy_type")), "bedroom_raw": raw_bed, "bathroom_raw": raw_bath,
                "square_footage_raw": clean_text(row.get("square_footage")), "monthly_rent_raw": clean_text(row.get("monthly_rent")),
                "occupancy_or_vacancy_date": occ_date, "occupancy_year": occupancy_year,
                "date_unknown_text": date_unknown_text, "vacancy_date": vac_date, "signature_date": sig_date,
                "past_occupancy": parse_yes_no(row.get("past_occupancy")),
                "other_utilities_raw": clean_text(row.get("base_rent_includes_other_utilities"))})
            for utility, sources in utility_tokens(row).items():
                utilities.append({"unique_id": unique_id, "utility_name": utility,
                                  "source_checkbox": str("checkbox" in sources), "source_text": str("text" in sources)})
            raw_history = clean_text(row.get("occupancy_or_vacancy_date_history"))
            if raw_history:
                try:
                    history_items = json.loads(raw_history)
                    if not isinstance(history_items, list):
                        raise ValueError("history is not a JSON array")
                except (json.JSONDecodeError, ValueError) as exc:
                    issues.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date_history",
                                   "issue_code": "invalid_history_json", "raw_value": raw_history,
                                   "issue_detail": str(exc)})
                    history_items = []
                for sequence, item in enumerate(history_items, start=1):
                    if not isinstance(item, dict):
                        issues.append({"unique_id": unique_id, "column_name": "occupancy_or_vacancy_date_history",
                                       "issue_code": "invalid_history_item", "raw_value": str(item),
                                       "issue_detail": "history item is not an object"})
                        continue
                    start = parse_date(item.get("start_date"))
                    end = parse_date(item.get("end_date"))
                    history.append({"unique_id": unique_id, "seq_no": sequence,
                                    "range_type": clean_text(item.get("date_range_type")),
                                    "start_date": start, "end_date": end,
                                    "is_reversed": str(bool(start and end and end < start))})

    def write_csv(filename, rows):
        if not rows:
            return
        with (args.output_dir / filename).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv("unit_report_clean.csv", reports)
    write_csv("occupancy_history_clean.csv", history)
    write_csv("report_utility_clean.csv", utilities)
    write_csv("quality_issue.csv", issues)
    metadata = [{"data_as_of": extract_metadata[0] if extract_metadata else None,
                 "data_loaded_at": extract_metadata[1] if extract_metadata else None}]
    write_csv("extract_batch.csv", metadata)
    write_csv("bedroom_labels.csv", [{"raw_label": k, "canonical_bedrooms": v[0], "is_unparseable": v[1]} for k, v in dimensions["bedroom"].items()])
    write_csv("bathroom_labels.csv", [{"raw_label": k, "canonical_bathrooms": v[0], "is_shared": v[1], "is_unparseable": v[2]} for k, v in dimensions["bathroom"].items()])
    write_csv("bands.csv", [{"band_type": t, "raw_label": k, "min_value": v[0], "max_value": v[1], "is_open": v[2], "status": v[3]} for t in ("sqft", "rent") for k, v in dimensions[t].items()])
    print({"rows_in": stats["rows_in"], "rows_out": len(reports), "history_rows": len(history),
           "utility_rows": len(utilities), "quality_issues": len(issues), "output_dir": str(args.output_dir)})


if __name__ == "__main__":
    main()
