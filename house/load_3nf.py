"""Load Rent_Board_Housing_Inventory_20260913.csv into the 3NF schema.

Two streaming passes over the raw CSV:
  pass 1  collects the data-derived dimensions (neighborhoods, points, blocks,
          street labels, bedroom/bathroom raw labels) and the content hashes
          that identify duplicate rows, which can only be counted once the
          whole file has been seen;
  pass 2  assigns the surrogate keys and writes one tab-separated file per
          table, plus load_3nf.sql -- a LOAD DATA LOCAL INFILE script in
          foreign-key order.

The parsing rules live in clean_inventory.py and are imported, not restated,
so the parquet pipeline and the database cannot drift apart.

Fixed vocabularies (rent/sqft bands, utilities, flags, occupancy types) are
seeded by schema_3nf.sql; their ids are mirrored below and every label the CSV
produces is checked against them, so a new value in a future extract fails
loudly instead of loading as NULL.

Usage:
    .venv/bin/python house/load_3nf.py [--out DIR]
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from clean_inventory import (norm_bathrooms, norm_bedrooms, parse_point,
                             to_date, to_num)

HERE = Path(__file__).resolve().parent
SRC = HERE / "Rent_Board_Housing_Inventory_20260913.csv"
LOAD_SQL = HERE / "load_3nf.sql"

BATCH_ID = 1
DATA_AS_OF = "2026-09-03"          # extract_batch.data_as_of, for the future-date flag

# Domain windows enforced by the CHECK constraints in schema_3nf.sql. MySQL's
# DATE type starts at 1000-01-01 and the file holds dates below it, so a value
# outside these bounds is stored as NULL and kept verbatim on the flag row.
DATE_MIN, DATE_MAX = "1900-01-01", "2026-12-31"
SIG_MIN, SIG_MAX = "2022-01-01", "2026-12-31"

# --- ids mirrored from schema_3nf.sql section 10 ----------------------------

OCCUPANCY_TYPE_IDS = {
    "Occupied by non-owner": 1,
    "Vacant": 2,
    "Occupied by owner": 3,
    "Non-Residential": 4,
}

DATE_RANGE_TYPE_IDS = {"Occupied": 1, "Vacant": 2, "Occupied - Non Owner": 3}

REASON_IDS = {
    "Year Unknown (within past five years)": 1,
    "Year Unknown (within past 5-10 years)": 2,
    "Year Unknown (within past 10-20 years)": 3,
    "Year Unknown (more than 20 years)": 4,
    "Year unknown (no information available)": 5,
}

FLAG_IDS = {
    "occupancy_date_out_of_range": 1,
    "signature_date_out_of_range": 2,
    "vacancy_date_out_of_range": 3,
    "year_disagrees_with_date": 4,
    "occupancy_after_signature": 5,
    "occupancy_in_future": 6,
    "vacant_with_rent": 7,
    "tenant_without_rent": 8,
    "bathroom_holds_bedroom_text": 9,
    "zero_unit_count": 10,
    "occupancy_year_unparseable": 11,
}

UTILITY_IDS = {
    "water_sewer": 1, "natural_gas": 2, "electricity": 3, "refuse_recycling": 4,
    "heat": 5, "hot_water": 6, "internet": 7, "cable": 8, "parking": 9,
    "storage": 10, "pest_control": 11, "laundry": 12, "janitorial": 13,
    "solar": 14, "all_utilities": 15, "other": 16,
}

SQFT_BAND_IDS = {
    "0-250 Sq.Ft": 1, "0-250 Sq.ft": 2, "251-500 Sq.Ft": 3, "501-750 Sq.Ft": 4,
    "751-1000 Sq.Ft": 5, "1001-1250 Sq.Ft": 6, "1251-1500 Sq.Ft": 7,
    "1501-1750 Sq.Ft": 8, "1751-2000 Sq.Ft": 9, "2001-2250 Sq.Ft": 10,
    "2251-2500 Sq.Ft": 11, "2501-2750 Sq.Ft": 12, "2751-3000 Sq.Ft": 13,
    "3001-3250 Sq.Ft": 14, "3251-3500 Sq.Ft": 15, "3501-3750 Sq.Ft": 16,
    "3751-4000 Sq.Ft": 17, "4000+ Sq.Ft": 18, "Unknown": 19,
}

RENT_BAND_IDS = {
    "$0 (no rent paid by the occupant)": 1, "0": 2, "$1-$250": 3,
    "$250-$500": 4, "$251-$500": 5, "$501-$750": 6, "$751-$1000": 7,
    "$1001-$1250": 8, "$1251-$1500": 9, "$1501-$1750": 10, "$1750-$2000": 11,
    "$1751-$2000": 12, "$2001-$2250": 13, "$2251-$2500": 14, "$2501-$2750": 15,
    "$2751-$3000": 16, "$3001-$3250": 17, "$3251-$3500": 18, "$3501-$3750": 19,
    "$3751-$4000": 20, "$4001-$4250": 21, "$4251-$4500": 22, "$4501-$4750": 23,
    "$4751-$5000": 24, "$5001-$5250": 25, "$5251-$5500": 26, "$5501-$5750": 27,
    "$5751-$6000": 28, "$6001-$6250": 29, "$6251-$6500": 30, "$6501-$6750": 31,
    "$6751-$7000": 32, "$7000+": 33,
}

# The four checkbox columns, in utility order.
CHECKBOX_UTILITIES = [
    ("base_rent_includes_water_sewer", "water_sewer"),
    ("base_rent_includes_natural_gas", "natural_gas"),
    ("base_rent_includes_electricity", "electricity"),
    ("base_rent_includes_refuse_recycling", "refuse_recycling"),
]

# base_rent_includes_other_utilities is free text with 94 distinct values, some
# of them genuinely multi-valued ("parking, storage & heat"). Match on
# substrings rather than enumerating every phrasing; order matters only in that
# "hot water" must be tested before the bare "water".
_OTHER_UTILITY_PATTERNS = [
    ("hot_water", ("hot water",)),
    ("heat", ("heat", "steam", "boiler", "hydronic", "radiator")),
    ("internet", ("internet", "wifi", "wi-fi", "wi fi")),
    ("cable", ("cable",)),
    ("parking", ("parking", "car port", "carport", "garage")),
    ("storage", ("storage",)),
    ("pest_control", ("pest",)),
    ("refuse_recycling", ("trash", "garbage", "rubbish", "refuse", "recycl")),
    ("laundry", ("laundry",)),
    ("janitorial", ("janitorial",)),
    ("solar", ("solar",)),
    ("natural_gas", ("gas", "pg&e")),
    ("water_sewer", ("water", "sewer")),
    ("all_utilities", ("all utilities",)),
]

# Values that mean "nothing extra is included" rather than naming a utility.
_OTHER_UTILITY_NEGATIVES = {"", "n/a", "na", "no", "non", "none", "0", "-", "n\\a"}


def parse_other_utilities(raw):
    """Free-text 'other utilities' -> a set of utility names.

    Unrecognised but non-empty text maps to 'other' so the fact that something
    was included is not lost; the verbatim string stays on unit_record.
    """
    if not raw:
        return set()
    s = raw.strip().lower()
    if s in _OTHER_UTILITY_NEGATIVES:
        return set()
    found = set()
    for name, needles in _OTHER_UTILITY_PATTERNS:
        if any(nd in s for nd in needles):
            found.add(name)
    # "hot water" already claimed the phrase; don't also bill it as water/sewer.
    if "hot_water" in found and "water_sewer" in found and "sewer" not in s:
        found.discard("water_sewer")
    if not found:
        found.add("other")
    return found


_ADDR = re.compile(r"^(\d+) Block of\s*(.*)$")


def parse_street_block(label):
    """'400 Block of STOCKTON ST' -> (400, 'STOCKTON ST').

    7,676 of the 7,677 distinct labels match; the exception is the truncated
    '0 Block of', which yields a range with no street name.
    """
    m = _ADDR.match(label)
    if not m:
        return None, None
    street = m.group(2).strip() or None
    return int(m.group(1)), street


def in_range(d, lo=DATE_MIN, hi=DATE_MAX):
    return d is not None and lo <= d <= hi


def content_hash(row, cols):
    """md5 over every column except unique_id -- identifies duplicate filings."""
    payload = "\x1f".join(row[c] for c in cols)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


# --- TSV output -------------------------------------------------------------

def esc(v):
    """One field for MySQL's default LOAD DATA escaping; None -> \\N."""
    if v is None:
        return "\\N"
    if v is True:
        return "1"
    if v is False:
        return "0"
    s = str(v)
    return (s.replace("\\", "\\\\").replace("\t", "\\t")
             .replace("\n", "\\n").replace("\r", "\\r"))


class Table:
    """A tab-separated staging file for one target table."""

    def __init__(self, out_dir, name, columns):
        self.name = name
        self.columns = columns
        self.path = out_dir / f"{name}.tsv"
        self._fh = self.path.open("w", encoding="utf-8", newline="")
        self.rows = 0

    def write(self, *values):
        self._fh.write("\t".join(esc(v) for v in values) + "\n")
        self.rows += 1

    def close(self):
        self._fh.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "load"),
                    help="directory for the generated .tsv files")
    args = ap.parse_args()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not SRC.exists():
        sys.exit(f"missing source file: {SRC}")
    csv.field_size_limit(10 ** 9)

    # ---------------- pass 1: dimensions and duplicate detection ------------
    hoods, points, blocks, streets, beds, baths = {}, {}, {}, {}, {}, {}
    hashes = Counter()
    unknown = defaultdict(Counter)
    n_in = 0

    with SRC.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames
        hash_cols = [c for c in cols if c != "unique_id"]
        for row in reader:
            n_in += 1
            hashes[content_hash(row, hash_cols)] += 1

            if row["analysis_neighborhood"]:
                hoods.setdefault(row["analysis_neighborhood"], len(hoods) + 1)
            if row["point"]:
                points.setdefault(row["point"], len(points) + 1)
            if row["block_num"]:
                blocks.setdefault(row["block_num"], True)
            if row["block_address"]:
                streets.setdefault(row["block_address"], len(streets) + 1)
            if row["bedroom_count"]:
                beds.setdefault(row["bedroom_count"], len(beds) + 1)
            if row["bathroom_count"]:
                baths.setdefault(row["bathroom_count"], len(baths) + 1)

            for col, seeded in (("square_footage", SQFT_BAND_IDS),
                                ("monthly_rent", RENT_BAND_IDS),
                                ("occupancy_type", OCCUPANCY_TYPE_IDS)):
                v = row[col]
                if v and v not in seeded:
                    unknown[col][v] += 1

    if unknown:
        for col, vals in unknown.items():
            print(f"ERROR: {col} holds {len(vals)} value(s) not seeded in "
                  f"schema_3nf.sql: {list(vals)[:10]}", file=sys.stderr)
        sys.exit("aborting: add the values above to the seed data first")

    dup_groups = {h: (i + 1, n) for i, (h, n) in
                  enumerate((h, n) for h, n in hashes.items() if n > 1)}

    # ---------------- pass 2: emit every table ------------------------------
    t = {}
    t["neighborhood"] = Table(out_dir, "neighborhood", ["neighborhood_id", "name"])
    t["location_point"] = Table(out_dir, "location_point",
                                ["point_id", "longitude", "latitude",
                                 "neighborhood_id", "district_id"])
    t["assessor_block"] = Table(out_dir, "assessor_block", ["block_num"])
    t["street_block"] = Table(out_dir, "street_block",
                              ["street_block_id", "raw_label", "block_range",
                               "street_name"])
    t["bedroom_type"] = Table(out_dir, "bedroom_type",
                              ["bedroom_type_id", "raw_label", "bedrooms",
                               "is_unparseable"])
    t["bathroom_type"] = Table(out_dir, "bathroom_type",
                               ["bathroom_type_id", "raw_label", "bathrooms",
                                "is_shared", "is_unparseable"])
    t["duplicate_group"] = Table(out_dir, "duplicate_group",
                                 ["dup_group_id", "content_hash", "member_count"])
    t["unit_record"] = Table(out_dir, "unit_record", [
        "unique_id", "batch_id", "submission_year", "signature_date",
        "block_num", "street_block_id", "point_id", "building_unit_count",
        "year_property_built", "occupancy_type_id", "bedroom_type_id",
        "bathroom_type_id", "sqft_band_id", "rent_band_id",
        "occupancy_or_vacancy_date", "occupancy_or_vacancy_year",
        "date_unknown_reason_id", "occupancy_year_raw", "vacancy_date",
        "past_occupancy", "other_utilities_raw", "dup_group_id"])
    t["record_utility_included"] = Table(out_dir, "record_utility_included",
                                         ["unique_id", "utility_id",
                                          "from_checkbox", "from_other_text"])
    t["record_quality_flag"] = Table(out_dir, "record_quality_flag",
                                     ["unique_id", "flag_id", "rejected_value"])
    t["occupancy_history"] = Table(out_dir, "occupancy_history",
                                   ["history_id", "unique_id", "seq_no",
                                    "date_range_type_id", "start_date", "end_date"])

    for name, nid in hoods.items():
        t["neighborhood"].write(nid, name)
    for blk in blocks:
        t["assessor_block"].write(blk)
    for label, sid in streets.items():
        rng, street = parse_street_block(label)
        t["street_block"].write(sid, label, rng, street)
    for label, bid in beds.items():
        n = norm_bedrooms(label)
        t["bedroom_type"].write(bid, label, n, n is None)
    for label, bid in baths.items():
        n, shared = norm_bathrooms(label)
        t["bathroom_type"].write(bid, label, n, shared, n is None and not shared)
    for h, (gid, n) in dup_groups.items():
        t["duplicate_group"].write(gid, h, n)

    stats = Counter()
    flag_counts = Counter()
    point_rows = {}          # point_id -> (lon, lat, hood_id, district)
    bad_points = set()       # WKT strings that would not parse
    history_id = 0

    def flag(uid, code, value=None):
        t["record_quality_flag"].write(uid, FLAG_IDS[code], value)
        flag_counts[code] += 1

    with SRC.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            uid = int(row["unique_id"])

            # -- geography ----------------------------------------------------
            point_id = None
            if row["point"] and row["point"] not in bad_points:
                point_id = points[row["point"]]
                if point_id not in point_rows:
                    lon, lat = parse_point(row["point"])
                    if lon is None:
                        # point -> neighborhood/district are exact FDs, so the
                        # attributes are written once, from the first row that
                        # carries the point.
                        bad_points.add(row["point"])
                        stats["point_unparsed"] += 1
                        point_id = None
                    else:
                        point_rows[point_id] = (
                            lon, lat,
                            hoods.get(row["analysis_neighborhood"]),
                            int(row["supervisor_district"]) if row["supervisor_district"] else None,
                        )

            # -- dates --------------------------------------------------------
            raw_occ = row["occupancy_or_vacancy_date"]
            raw_year = row["occupancy_or_vacancy_date_year"]
            occ_date = to_date(raw_occ)
            occ_year = reason_id = year_raw = None
            if in_range(occ_date):
                if raw_year and raw_year != occ_date[:4]:
                    flag(uid, "year_disagrees_with_date", raw_year[:40])
            else:
                if raw_occ:
                    flag(uid, "occupancy_date_out_of_range", raw_occ[:40])
                occ_date = None
                if raw_year in REASON_IDS:
                    reason_id = REASON_IDS[raw_year]
                elif raw_year.isdigit() and 1900 <= int(raw_year) <= 2026:
                    occ_year = int(raw_year)
                elif raw_year:
                    year_raw = raw_year[:20]
                    flag(uid, "occupancy_year_unparseable", raw_year[:40])

            sig_date = to_date(row["signature_date"])
            if not in_range(sig_date, SIG_MIN, SIG_MAX):
                if row["signature_date"]:
                    flag(uid, "signature_date_out_of_range", row["signature_date"][:40])
                sig_date = None

            vac_date = to_date(row["vacancy_date"])
            if not in_range(vac_date):
                if row["vacancy_date"]:
                    flag(uid, "vacancy_date_out_of_range", row["vacancy_date"][:40])
                vac_date = None

            if occ_date and sig_date and occ_date > sig_date:
                flag(uid, "occupancy_after_signature")
            if occ_date and occ_date > DATA_AS_OF:
                flag(uid, "occupancy_in_future")

            # -- unit attributes ----------------------------------------------
            occ_type = row["occupancy_type"]
            rent_id = RENT_BAND_IDS.get(row["monthly_rent"]) if row["monthly_rent"] else None
            sqft_id = SQFT_BAND_IDS.get(row["square_footage"]) if row["square_footage"] else None
            bed_id = beds.get(row["bedroom_count"])
            bath_id = baths.get(row["bathroom_count"])

            # A reported band that is the "no rent paid" sentinel is not a rent.
            has_rent = rent_id is not None and rent_id not in (1, 2)
            if occ_type == "Vacant" and has_rent:
                flag(uid, "vacant_with_rent")
            if occ_type == "Occupied by non-owner" and rent_id is None:
                flag(uid, "tenant_without_rent")
            if row["bathroom_count"] and re.search(r"bed", row["bathroom_count"], re.I):
                flag(uid, "bathroom_holds_bedroom_text", row["bathroom_count"][:40])

            units = to_num(row["unit_count"])
            if units == 0:
                flag(uid, "zero_unit_count")
            built = to_num(row["year_property_built"])
            built = int(built) if built is not None and 1800 <= built <= 2030 else None

            past = {"Yes": 1, "No": 0}.get(row["past_occupancy"])

            t["unit_record"].write(
                uid, BATCH_ID, int(row["submission_year"]), sig_date,
                row["block_num"] or None,
                streets.get(row["block_address"]),
                point_id,
                units, built,
                OCCUPANCY_TYPE_IDS[occ_type], bed_id, bath_id, sqft_id, rent_id,
                occ_date, occ_year, reason_id, year_raw, vac_date, past,
                (row["base_rent_includes_other_utilities"] or None),
                dup_groups.get(content_hash(row, hash_cols), (None,))[0],
            )

            # -- utilities ----------------------------------------------------
            checked = {util for col, util in CHECKBOX_UTILITIES if row[col] == "Y"}
            typed = parse_other_utilities(row["base_rent_includes_other_utilities"])
            for util in sorted(checked | typed):
                t["record_utility_included"].write(
                    uid, UTILITY_IDS[util], util in checked, util in typed)
            stats["utility_links"] += len(checked | typed)
            stats["utility_both_sources"] += len(checked & typed)

            # -- occupancy history --------------------------------------------
            raw_hist = row["occupancy_or_vacancy_date_history"]
            if raw_hist:
                try:
                    entries = json.loads(raw_hist)
                except json.JSONDecodeError:
                    stats["history_parse_error"] += 1
                    entries = []
                for i, e in enumerate(entries, start=1):
                    drt = (e.get("date_range_type") or "").strip()
                    # 3 entries arrive lower-cased; fold them into the canon.
                    drt_id = DATE_RANGE_TYPE_IDS.get(drt) or DATE_RANGE_TYPE_IDS.get(drt.title())
                    if drt and drt_id is None:
                        stats["history_unknown_type"] += 1
                    start = e.get("start_date")
                    end = e.get("end_date")
                    start = start if in_range(start) else None
                    end = end if in_range(end) else None
                    if start and end and end < start:
                        stats["history_range_reversed"] += 1
                    history_id += 1
                    t["occupancy_history"].write(history_id, uid, i, drt_id, start, end)

    for point_id, (lon, lat, hood, dist) in sorted(point_rows.items()):
        t["location_point"].write(point_id, lon, lat, hood, dist)

    for tbl in t.values():
        tbl.close()

    write_load_script(out_dir, t)

    # ---------------- reconciliation ----------------------------------------
    print(f"source rows       : {n_in:,}")
    print(f"unit_record rows  : {t['unit_record'].rows:,}")
    assert t["unit_record"].rows == n_in, "every source row must produce one fact row"
    print(f"staging directory : {out_dir}")
    print(f"load script       : {LOAD_SQL}")

    print("\nrows per table")
    for name in ("neighborhood", "location_point", "assessor_block", "street_block",
                 "bedroom_type", "bathroom_type", "duplicate_group", "unit_record",
                 "record_utility_included", "record_quality_flag", "occupancy_history"):
        print(f"  {name:<26} {t[name].rows:>9,}")

    print("\nquality flags raised")
    for code in FLAG_IDS:
        n = flag_counts[code]
        print(f"  {code:<28} {n:>8,}  ({100 * n / n_in:5.2f}% of rows)")

    print("\nunparseable labels kept with a NULL canonical value")
    print(f"  bedroom_type   {sum(1 for lbl in beds if norm_bedrooms(lbl) is None):>3}"
          f" of {len(beds)} distinct labels")
    print(f"  bathroom_type  {sum(1 for lbl in baths if norm_bathrooms(lbl) == (None, False)):>3}"
          f" of {len(baths)} distinct labels")
    dup_rows = sum(n for _, n in dup_groups.values())
    print(f"\nduplicate filings: {dup_rows:,} rows in {len(dup_groups):,} groups "
          f"({dup_rows - len(dup_groups):,} redundant)")
    for k in ("point_unparsed", "history_parse_error", "history_unknown_type",
              "history_range_reversed", "utility_both_sources"):
        if stats[k]:
            print(f"  {k}: {stats[k]:,}")


LOAD_ORDER = [
    "neighborhood", "location_point", "assessor_block", "street_block",
    "bedroom_type", "bathroom_type", "duplicate_group", "unit_record",
    "record_utility_included", "record_quality_flag", "occupancy_history",
]


def write_load_script(out_dir, tables):
    """Emit load_3nf.sql: LOAD DATA LOCAL INFILE in foreign-key order."""
    lines = [
        "-- Generated by load_3nf.py -- do not edit by hand.",
        "-- Run AFTER schema_3nf.sql:",
        "--   mysql -u <user> -p --local-infile=1 < load_3nf.sql",
        "-- If the server has local_infile OFF, enable it for the session with",
        "--   SET GLOBAL local_infile = 1;   (needs SUPER/SYSTEM_VARIABLES_ADMIN)",
        "",
        "USE RentBoardDB;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "SET UNIQUE_CHECKS = 0;",
        "",
    ]
    for name in LOAD_ORDER:
        tbl = tables[name]
        lines += [
            f"-- {tbl.rows:,} rows",
            f"LOAD DATA LOCAL INFILE '{tbl.path}'",
            f"    INTO TABLE {name}",
            "    FIELDS TERMINATED BY '\\t' ESCAPED BY '\\\\'",
            "    LINES TERMINATED BY '\\n'",
            f"    ({', '.join(tbl.columns)});",
            "",
        ]
    checks = " UNION ALL ".join(
        f"SELECT '{name}' AS table_name, COUNT(*) AS rows_loaded, "
        f"{tables[name].rows} AS rows_staged, "
        f"IF(COUNT(*) = {tables[name].rows}, 'ok', 'ROWS LOST') AS verdict "
        f"FROM {name}" for name in LOAD_ORDER)
    lines += [
        "SET UNIQUE_CHECKS = 1;",
        "SET FOREIGN_KEY_CHECKS = 1;",
        "",
        "-- LOAD DATA downgrades a CHECK-constraint failure to a warning and",
        "-- discards the row, so compare every table against what was staged.",
        "-- Every verdict must read 'ok'.",
        checks + ";",
        "",
        "-- FOREIGN_KEY_CHECKS was off during the bulk load, so prove the",
        "-- references anyway; every row below must be 0.",
        "SELECT 'unit_record -> location_point' AS fk, COUNT(*) AS orphans",
        "  FROM unit_record r LEFT JOIN location_point p USING (point_id)",
        " WHERE r.point_id IS NOT NULL AND p.point_id IS NULL",
        "UNION ALL",
        "SELECT 'unit_record -> street_block', COUNT(*)",
        "  FROM unit_record r LEFT JOIN street_block s USING (street_block_id)",
        " WHERE r.street_block_id IS NOT NULL AND s.street_block_id IS NULL",
        "UNION ALL",
        "SELECT 'unit_record -> assessor_block', COUNT(*)",
        "  FROM unit_record r LEFT JOIN assessor_block b USING (block_num)",
        " WHERE r.block_num IS NOT NULL AND b.block_num IS NULL",
        "UNION ALL",
        "SELECT 'occupancy_history -> unit_record', COUNT(*)",
        "  FROM occupancy_history h LEFT JOIN unit_record r USING (unique_id)",
        " WHERE r.unique_id IS NULL;",
        "",
    ]
    LOAD_SQL.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
