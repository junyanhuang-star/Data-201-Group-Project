"""Two-pass CSV-to-3NF staging loader.

Usage:
    python3 load_3nf.py --csv Rent_Board_Housing_Inventory_flat_final.csv

The script writes gitignored TSV staging files and a generated load_3nf.sql.
It does not connect to MySQL; this keeps transformation and database loading
separate and makes the staged row counts auditable before loading.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from clean_inventory import (
    DATE_RANGE_TYPES, DATE_UNKNOWN_REASONS, OCCUPANCY_TYPES, RENT_IDS,
    SQFT_IDS, clean, parse_bathroom, parse_block_label, parse_date,
    parse_decimal, parse_history_date, parse_int, parse_point, parse_bedroom,
    utility_matches,
)


ROOT = Path(__file__).resolve().parent
STANDARD_UTILITY_COLUMNS = {
    "base_rent_includes_water_sewer": "water_sewer",
    "base_rent_includes_natural_gas": "natural_gas",
    "base_rent_includes_electricity": "electricity",
    "base_rent_includes_refuse_recycling": "refuse_recycling",
}
UTILITY_IDS = {
    "water_sewer": 1, "natural_gas": 2, "electricity": 3, "refuse_recycling": 4,
    "heat": 5, "hot_water": 6, "internet": 7, "cable": 8, "parking": 9,
    "storage": 10, "pest_control": 11, "laundry": 12, "janitorial": 13,
    "solar": 14, "all_utilities": 15, "other": 16,
}
FLAG_IDS = {
    "occupancy_date_out_of_range": 1, "signature_date_out_of_range": 2,
    "vacancy_date_out_of_range": 3, "year_disagrees_with_date": 4,
    "occupancy_after_signature": 5, "occupancy_in_future": 6,
    "vacant_with_rent": 7, "tenant_without_rent": 8,
    "bathroom_holds_bedroom_text": 9, "zero_unit_count": 10,
    "occupancy_year_unparseable": 11,
}


def tsv_value(value) -> str:
    if value is None or value == "":
        return r"\N"
    return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def write_tsv(path: Path, columns: list[str], rows) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="") as out:
        for row in rows:
            out.write("\t".join(tsv_value(row.get(c)) for c in columns) + "\n")
            count += 1
    return count


def source_rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def duplicate_hash(row: dict[str, str], fields: list[str]) -> str:
    content = "\x1f".join(clean(row.get(field)) for field in fields[1:])
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def make_load_statement(table: str, columns: list[str], path: Path) -> str:
    try:
        infile = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        infile = str(path.resolve()).replace("\\", "\\\\")
    infile = infile.replace("'", "\\'")
    return (
        f"LOAD DATA LOCAL INFILE '{infile}' INTO TABLE `{table}`\n"
        "FIELDS TERMINATED BY '\\t' ESCAPED BY '\\\\'\n"
        "LINES TERMINATED BY '\\n'\n"
        f"(`{columns[0]}`" + "".join(f", `{c}`" for c in columns[1:]) + ");\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=ROOT / "Rent_Board_Housing_Inventory_flat_final.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "load")
    args = parser.parse_args()
    csv_path = args.csv.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    opener = gzip.open if csv_path.suffix == ".gz" else open
    with opener(csv_path, "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
    if len(fields) != 28 or "unique_id" not in fields:
        raise SystemExit(f"Expected the 28-column inventory CSV; found {len(fields)} columns")

    neighborhoods, points, blocks, streets, bedrooms, bathrooms = set(), set(), set(), set(), set(), set()
    point_metadata = {}
    hashes = Counter()
    for row in source_rows(csv_path):
        neighborhood = clean(row["analysis_neighborhood"])
        point = parse_point(row["point"])
        block = clean(row["block_num"])
        street = clean(row["block_address"])
        if neighborhood: neighborhoods.add(neighborhood)
        if point:
            points.add(point)
            metadata = (neighborhood or None, parse_int(row["supervisor_district"], 1, 11))
            previous = point_metadata.setdefault(point, metadata)
            if previous != metadata:
                raise SystemExit(f"Point functional dependency failed for {point}: {previous} vs {metadata}")
        if block: blocks.add(block)
        if street: streets.add(street)
        if clean(row["bedroom_count"]): bedrooms.add(clean(row["bedroom_count"]))
        if clean(row["bathroom_count"]): bathrooms.add(clean(row["bathroom_count"]))
        hashes[duplicate_hash(row, fields)] += 1

    neighborhood_id = {v: i for i, v in enumerate(sorted(neighborhoods), 1)}
    point_id = {v: i for i, v in enumerate(sorted(points), 1)}
    block_id = {v: i for i, v in enumerate(sorted(streets), 1)}
    bedroom_id = {v: i for i, v in enumerate(sorted(bedrooms), 1)}
    bathroom_id = {v: i for i, v in enumerate(sorted(bathrooms), 1)}
    duplicate_id = {h: i for i, h in enumerate(sorted(h for h, n in hashes.items() if n > 1), 1)}

    dimensions = {
        "neighborhood": ({"neighborhood_id": i, "name": v} for v, i in neighborhood_id.items()),
        "supervisor_district": ({"district_id": i} for i in range(1, 12)),
        "location_point": (
            {"point_id": i, "longitude": v[0], "latitude": v[1],
             "neighborhood_id": neighborhood_id.get(point_metadata[v][0]),
             "district_id": point_metadata[v][1]}
            for v, i in point_id.items()
        ),
        "assessor_block": ({"block_num": v} for v in sorted(blocks)),
        "street_block": (
            {"street_block_id": i, "raw_label": v, "block_range": parse_block_label(v)[0], "street_name": parse_block_label(v)[1]}
            for v, i in block_id.items()
        ),
        "bedroom_type": (
            {"bedroom_type_id": i, "raw_label": v, "bedrooms": parse_bedroom(v), "is_unparseable": parse_bedroom(v) is None}
            for v, i in bedroom_id.items()
        ),
        "bathroom_type": (
            {"bathroom_type_id": i, "raw_label": v, "bathrooms": parse_bathroom(v)[0], "is_shared": parse_bathroom(v)[1], "is_unparseable": parse_bathroom(v)[2]}
            for v, i in bathroom_id.items()
        ),
        "duplicate_group": ({"dup_group_id": i, "content_hash": h, "member_count": hashes[h]} for h, i in duplicate_id.items()),
    }
    dimension_columns = {
        "neighborhood": ["neighborhood_id", "name"],
        "supervisor_district": ["district_id"],
        "location_point": ["point_id", "longitude", "latitude", "neighborhood_id", "district_id"],
        "assessor_block": ["block_num"],
        "street_block": ["street_block_id", "raw_label", "block_range", "street_name"],
        "bedroom_type": ["bedroom_type_id", "raw_label", "bedrooms", "is_unparseable"],
        "bathroom_type": ["bathroom_type_id", "raw_label", "bathrooms", "is_shared", "is_unparseable"],
        "duplicate_group": ["dup_group_id", "content_hash", "member_count"],
    }
    staged = []
    for table, rows in dimensions.items():
        path = out / f"{table}.tsv"
        write_tsv(path, dimension_columns[table], rows)
        staged.append((table, dimension_columns[table], path))

    unit_columns = [
        "unique_id", "batch_id", "submission_year", "signature_date", "block_num", "street_block_id", "point_id",
        "building_unit_count", "year_property_built", "occupancy_type_id", "bedroom_type_id", "bathroom_type_id",
        "sqft_band_id", "rent_band_id", "occupancy_or_vacancy_date", "occupancy_or_vacancy_year",
        "date_unknown_reason_id", "occupancy_year_raw", "vacancy_date", "past_occupancy", "other_utilities_raw", "dup_group_id",
    ]
    history_columns = ["unique_id", "seq_no", "date_range_type_id", "start_date", "end_date"]
    utility_columns = ["unique_id", "utility_id", "from_checkbox", "from_other_text"]
    quality_columns = ["unique_id", "flag_id", "rejected_value"]
    unit_out, history_out, utility_out, quality_out = [], [], [], []
    extract_date = date(2026, 9, 3)
    for row in source_rows(csv_path):
        uid = int(row["unique_id"])
        occupancy_raw = clean(row["occupancy_or_vacancy_date"])
        year_raw = clean(row["occupancy_or_vacancy_date_year"])
        occ_date, occ_bad = parse_date(occupancy_raw, date(1900, 1, 1), date(2026, 12, 31))
        sig_date, sig_bad = parse_date(row["signature_date"], date(2022, 1, 1), date(2026, 12, 31))
        vac_date, vac_bad = parse_date(row["vacancy_date"], date(1900, 1, 1), date(2026, 12, 31))
        parsed_year = parse_int(year_raw, 1900, 2026)
        reason_id = DATE_UNKNOWN_REASONS.get(year_raw)
        year_value = parsed_year if not occ_date and not reason_id else None
        year_unparseable = bool(year_raw and not parsed_year and not reason_id)
        if year_unparseable:
            year_value, year_raw_kept = None, year_raw
        else:
            year_raw_kept = None
        bedroom = clean(row["bedroom_count"])
        bathroom = clean(row["bathroom_count"])
        bath_value, is_shared, bath_unparseable = parse_bathroom(bathroom)
        flags = []
        if occ_bad: flags.append(("occupancy_date_out_of_range", occupancy_raw))
        if sig_bad: flags.append(("signature_date_out_of_range", clean(row["signature_date"])))
        if vac_bad: flags.append(("vacancy_date_out_of_range", clean(row["vacancy_date"])))
        if occ_date and parsed_year and int(occ_date[:4]) != parsed_year: flags.append(("year_disagrees_with_date", year_raw))
        if occ_date and sig_date and occ_date > sig_date: flags.append(("occupancy_after_signature", None))
        if occ_date and date.fromisoformat(occ_date) > extract_date: flags.append(("occupancy_in_future", None))
        if row["occupancy_type"] == "Vacant" and clean(row["monthly_rent"]): flags.append(("vacant_with_rent", None))
        if row["occupancy_type"] == "Occupied by non-owner" and not clean(row["monthly_rent"]): flags.append(("tenant_without_rent", None))
        if "bedroom" in bathroom.lower(): flags.append(("bathroom_holds_bedroom_text", bathroom))
        if parse_decimal(row["unit_count"]) == "0": flags.append(("zero_unit_count", None))
        if year_unparseable: flags.append(("occupancy_year_unparseable", year_raw))
        point = parse_point(row["point"])
        block_label = clean(row["block_address"])
        unit_out.append({
            "unique_id": uid, "batch_id": 1, "submission_year": int(row["submission_year"]), "signature_date": sig_date,
            "block_num": clean(row["block_num"]) or None, "street_block_id": block_id.get(block_label), "point_id": point_id.get(point),
            "building_unit_count": parse_decimal(row["unit_count"]), "year_property_built": parse_int(row["year_property_built"], 1800, 2030),
            "occupancy_type_id": OCCUPANCY_TYPES[row["occupancy_type"]], "bedroom_type_id": bedroom_id.get(bedroom), "bathroom_type_id": bathroom_id.get(bathroom),
            "sqft_band_id": SQFT_IDS.get(clean(row["square_footage"])), "rent_band_id": RENT_IDS.get(clean(row["monthly_rent"])),
            "occupancy_or_vacancy_date": occ_date, "occupancy_or_vacancy_year": year_value, "date_unknown_reason_id": reason_id,
            "occupancy_year_raw": year_raw_kept, "vacancy_date": vac_date, "past_occupancy": {"Yes": 1, "No": 0}.get(clean(row["past_occupancy"])),
            "other_utilities_raw": clean(row["base_rent_includes_other_utilities"]) or None,
            "dup_group_id": duplicate_id.get(duplicate_hash(row, fields)),
        })
        if any(clean(row[c]) for c in ("occ_history_type", "occ_history_start", "occ_history_end")):
            history_out.append({"unique_id": uid, "seq_no": 1, "date_range_type_id": DATE_RANGE_TYPES.get(clean(row["occ_history_type"]).lower()), "start_date": parse_history_date(row["occ_history_start"]), "end_date": parse_history_date(row["occ_history_end"])})
        utility_sources = defaultdict(lambda: [0, 0])
        for column, name in STANDARD_UTILITY_COLUMNS.items():
            if clean(row[column]).upper() == "Y": utility_sources[name][0] = 1
        for name in utility_matches(row["base_rent_includes_other_utilities"]): utility_sources[name][1] = 1
        for name, (checkbox, text) in sorted(utility_sources.items()):
            utility_out.append({"unique_id": uid, "utility_id": UTILITY_IDS[name], "from_checkbox": checkbox, "from_other_text": text})
        for code, rejected in flags: quality_out.append({"unique_id": uid, "flag_id": FLAG_IDS[code], "rejected_value": rejected})

    for table, columns, rows in [
        ("unit_record", unit_columns, unit_out), ("occupancy_history", history_columns, history_out),
        ("record_utility_included", utility_columns, utility_out), ("record_quality_flag", quality_columns, quality_out),
    ]:
        path = out / f"{table}.tsv"
        write_tsv(path, columns, rows)
        staged.append((table, columns, path))

    sql_path = ROOT / "load_3nf.sql"
    with sql_path.open("w", encoding="utf-8") as sql:
        sql.write("USE RentBoardDB;\nSET FOREIGN_KEY_CHECKS = 0;\n")
        for table, columns, path in staged:
            sql.write(make_load_statement(table, columns, path))
        sql.write("SET FOREIGN_KEY_CHECKS = 1;\n")
        sql.write("SELECT 'staging complete' AS status, COUNT(*) AS unit_records FROM unit_record;\n")
    print(f"staged {len(unit_out):,} unit records")
    print(f"staged {len(history_out):,} history records")
    print(f"staged {len(utility_out):,} utility links")
    print(f"staged {len(quality_out):,} quality flags")
    print(f"wrote {sql_path}")


if __name__ == "__main__":
    main()
