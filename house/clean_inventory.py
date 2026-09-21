"""Clean the SF Rent Board Housing Inventory CSV into a typed parquet file.

The raw export stores every quantity as a banded string ("$2251-$2500",
"501-750 Sq.Ft") and lets filers type free text into what should be
categorical columns, so nothing in it can be aggregated as-is. This script
normalizes those columns, keeps every raw value alongside its parsed form, and
prints a reconciliation table so parse failures are visible rather than silent.

Usage:
    .venv/bin/python house/clean_inventory.py
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE / "Rent_Board_Housing_Inventory_20260913.csv"
DST = HERE / "inventory_clean.parquet"

# The date the file was pulled; occupancy dates after this are data entry errors.
DATA_PULL_DATE = "2026/09/13"

# Columns with exactly one distinct value across all 550k rows: no information.
DROP_COLS = ["case_type_name", "data_as_of", "data_loaded_at"]

# Bedroom/bathroom are free-text contaminated (45 and 31 distinct values for
# what should be ~7). Match on a normalized form rather than enumerating every
# typo, and let anything that doesn't match fall through to null.
_BED_WORDS = {
    "studio": 0, "zero": 0, "0": 0,
    "one": 1, "1": 1,
    "two": 2, "2": 2,
    "three": 3, "3": 3,
    "four": 4, "4": 4,
    "five": 5, "5": 5,
    "six": 6, "6": 6,
}


def norm_bedrooms(raw):
    """Bedroom count as an int, or None if the value is unusable."""
    if not raw:
        return None
    s = raw.strip().lower()
    if "studio" in s:
        return 0
    if s in ("5+", "five-bedroom"):
        return 5
    # Leading token carries the count: "One-Bedroom", "2br", "3 bedroom", "1U".
    m = re.match(r"^([a-z]+|\d+)", s)
    if not m:
        return None
    n = _BED_WORDS.get(m.group(1))
    if n is None:
        return None
    # Guard against values that parse numerically but mean something else:
    # "Garage", "Vacant", and stray unit labels like "2AH" carry no bedroom count
    # unless the rest of the string looks like a bedroom word or is empty.
    rest = s[m.end():].strip(" -_.")
    if rest and not re.match(r"^(bed|br|bd|\+|\(sm\)|$)", rest):
        return None
    return n


def norm_bathrooms(raw):
    """Bathroom count as a float (half-baths preserved), or None.

    Returns (count, is_shared) since "Shared bathroom facilities with other
    units" is a meaningful category, not a missing value: it flags SRO stock.
    """
    if not raw:
        return None, False
    s = raw.strip().lower()
    if "shared" in s:
        return None, True
    if s == "none":
        return 0.0, False
    # A handful of rows have bedroom text in the bathroom column; not a bath count.
    if "bedroom" in s or "bedrom" in s:
        return None, False
    if "half" in s:
        base = 1.0 if "one" in s else 2.0 if "two" in s else 3.0 if "three" in s else None
        return (base + 0.5) if base is not None else None, False
    if "three" in s or "3" in s:
        return 3.0, False
    if "two" in s or s.startswith("2"):
        return 2.5 if "2.5" in s else 2.0, False
    if "one" in s or s.startswith("1"):
        return 1.0, False
    if s.startswith("0"):
        return 0.0, False
    return None, False


# Rent and square footage arrive as bands. Midpoints make them arithmetic-safe,
# but the open-ended top bands have no midpoint in the data - the values below
# are assumptions and are flagged so downstream work can exclude them.
OPEN_RENT_MID = 7500.0
OPEN_SQFT_MID = 4400.0

_NUM = re.compile(r"\d+")


def parse_rent(raw):
    """-> (low, high, mid, is_open_band, status).

    status distinguishes three cases the raw column conflates:
      'reported'  - a real band
      'no_rent'   - "$0 (no rent paid by the occupant)", NOT a rent of zero
      'missing'   - blank
    """
    if not raw:
        return None, None, None, False, "missing"
    s = raw.strip()
    # "$0 (no rent paid by the occupant)" and the 6 bare "0" rows are not $0 rent.
    if s.startswith("$0") or s == "0":
        return None, None, None, False, "no_rent"
    if "+" in s:
        lo = int(_NUM.search(s).group())
        return float(lo), None, OPEN_RENT_MID, True, "reported"
    nums = _NUM.findall(s.replace(",", ""))
    if len(nums) != 2:
        return None, None, None, False, "missing"
    lo, hi = int(nums[0]), int(nums[1])
    return float(lo), float(hi), (lo + hi) / 2, False, "reported"


def parse_sqft(raw):
    """-> (low, high, mid, is_open_band). 'Unknown' and blanks yield nulls."""
    if not raw or raw.strip().lower() == "unknown":
        return None, None, None, False
    s = raw.strip()
    if "+" in s:
        lo = int(_NUM.search(s).group())
        return float(lo), None, OPEN_SQFT_MID, True
    nums = _NUM.findall(s)
    if len(nums) != 2:
        return None, None, None, False
    lo, hi = int(nums[0]), int(nums[1])
    return float(lo), float(hi), (lo + hi) / 2, False


def parse_point(raw):
    """WKT POINT -> (lon, lat). Coordinates are building-level and reliable."""
    if not raw:
        return None, None
    m = re.match(r"POINT \((-?[\d.]+) (-?[\d.]+)\)", raw)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def to_num(raw):
    """unit_count is written both as '4' and '4.0'; normalize to float."""
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def to_date(raw):
    """'YYYY/MM/DD' or 'YYYY/MM/DD HH:MM:SS AM' -> 'YYYY-MM-DD', else None."""
    if not raw or len(raw) < 10:
        return None
    d = raw[:10].replace("/", "-")
    return d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else None


def main():
    if not SRC.exists():
        sys.exit(f"missing source file: {SRC}")

    csv.field_size_limit(10 ** 9)
    stats = Counter()
    bad_bed, bad_bath = Counter(), Counter()
    records = []

    with SRC.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            stats["rows_in"] += 1

            raw_bed = row["bedroom_count"]
            raw_bath = row["bathroom_count"]
            bedrooms = norm_bedrooms(raw_bed)
            bathrooms, shared_bath = norm_bathrooms(raw_bath)
            if bedrooms is None and raw_bed:
                stats["bedroom_unparsed"] += 1
                bad_bed[raw_bed] += 1
            if bathrooms is None and raw_bath and not shared_bath:
                stats["bathroom_unparsed"] += 1
                bad_bath[raw_bath] += 1

            r_lo, r_hi, r_mid, r_open, r_status = parse_rent(row["monthly_rent"])
            s_lo, s_hi, s_mid, s_open = parse_sqft(row["square_footage"])
            lon, lat = parse_point(row["point"])
            stats[f"rent_{r_status}"] += 1

            occ_date = to_date(row["occupancy_or_vacancy_date"])
            sig_date = to_date(row["signature_date"])
            vac_date = to_date(row["vacancy_date"])

            # Two distinct integrity problems, flagged rather than dropped.
            date_flag = None
            if occ_date and occ_date > DATA_PULL_DATE.replace("/", "-"):
                date_flag = "occupancy_in_future"
                stats["date_flag_future"] += 1
            elif occ_date and sig_date and occ_date > sig_date:
                date_flag = "occupancy_after_signature"
                stats["date_flag_after_signature"] += 1

            occ_type = row["occupancy_type"]
            # Contradictions worth surfacing: a vacant unit reporting a rent, or
            # a tenant-occupied unit reporting none.
            if occ_type == "Vacant" and r_status == "reported":
                stats["vacant_with_rent"] += 1
            if occ_type == "Occupied by non-owner" and r_status == "missing":
                stats["tenant_without_rent"] += 1

            sub_year = int(row["submission_year"]) if row["submission_year"] else None
            occ_year = row["occupancy_or_vacancy_date_year"]
            occ_year = int(occ_year) if occ_year and occ_year.isdigit() else None
            # Years since move-in at the time of filing: the key derived variable.
            tenure = None
            if sub_year and occ_year and 1900 <= occ_year <= sub_year:
                tenure = sub_year - occ_year

            year_built = to_num(row["year_property_built"])

            records.append({
                "unique_id": row["unique_id"],
                "block_num": row["block_num"],
                "block_address": row["block_address"] or None,
                "unit_count": to_num(row["unit_count"]),
                "submission_year": sub_year,
                "occupancy_type": occ_type,
                "occupancy_or_vacancy_date": occ_date,
                "move_in_year": occ_year,
                "tenure_years": tenure,
                "vacancy_date": vac_date,
                "signature_date": sig_date,
                "date_flag": date_flag,
                "bedrooms_n": bedrooms,
                "bedroom_count_raw": raw_bed or None,
                "bathrooms_n": bathrooms,
                "shared_bathroom": shared_bath,
                "bathroom_count_raw": raw_bath or None,
                "sqft_low": s_lo, "sqft_high": s_hi, "sqft_mid": s_mid,
                "sqft_is_open_band": s_open,
                "square_footage_raw": row["square_footage"] or None,
                "rent_low": r_lo, "rent_high": r_hi, "rent_mid": r_mid,
                "rent_is_open_band": r_open,
                "rent_status": r_status,
                "monthly_rent_raw": row["monthly_rent"] or None,
                "incl_water_sewer": row["base_rent_includes_water_sewer"] == "Y",
                "incl_natural_gas": row["base_rent_includes_natural_gas"] == "Y",
                "incl_electricity": row["base_rent_includes_electricity"] == "Y",
                "incl_refuse_recycling": row["base_rent_includes_refuse_recycling"] == "Y",
                "incl_other_utilities": row["base_rent_includes_other_utilities"] or None,
                "past_occupancy": row["past_occupancy"] or None,
                "occupancy_history_json": row["occupancy_or_vacancy_date_history"] or None,
                "year_property_built": year_built,
                "longitude": lon, "latitude": lat,
                "analysis_neighborhood": row["analysis_neighborhood"] or None,
                "supervisor_district": row["supervisor_district"] or None,
            })

    df = pd.DataFrame.from_records(records)
    for col in ("occupancy_or_vacancy_date", "vacancy_date", "signature_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ("occupancy_type", "rent_status", "analysis_neighborhood",
                "supervisor_district", "date_flag"):
        df[col] = df[col].astype("category")

    df.to_parquet(DST, index=False, compression="zstd")

    print(f"wrote {DST}  ({DST.stat().st_size / 1e6:.1f} MB)")
    print(f"\nrows in : {stats['rows_in']:,}")
    print(f"rows out: {len(df):,}")
    print(f"distinct unique_id: {df['unique_id'].nunique():,}")
    print(f"dropped columns: {', '.join(DROP_COLS)}")

    print("\nparse reconciliation")
    n = stats["rows_in"]
    for key in ("bedroom_unparsed", "bathroom_unparsed", "rent_reported",
                "rent_no_rent", "rent_missing", "date_flag_future",
                "date_flag_after_signature", "vacant_with_rent",
                "tenant_without_rent"):
        print(f"  {key:<28} {stats[key]:>8,}  ({100 * stats[key] / n:5.2f}%)")

    print("\nnull rate of derived columns")
    for col in ("bedrooms_n", "bathrooms_n", "rent_mid", "sqft_mid",
                "tenure_years", "year_property_built", "latitude"):
        print(f"  {col:<28} {100 * df[col].isna().mean():5.2f}%")

    if bad_bed:
        print("\nunparseable bedroom_count values (dropped to null)")
        for val, cnt in bad_bed.most_common(15):
            print(f"  {cnt:>5,}  {val!r}")
    if bad_bath:
        print("\nunparseable bathroom_count values (dropped to null)")
        for val, cnt in bad_bath.most_common(15):
            print(f"  {cnt:>5,}  {val!r}")


if __name__ == "__main__":
    main()
