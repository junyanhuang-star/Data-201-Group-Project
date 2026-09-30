"""Small CSV profile used before loading the database.

Usage:
    python3 analysis.py --csv Rent_Board_Housing_Inventory_flat_final.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=Path(__file__).with_name("Rent_Board_Housing_Inventory_flat_final.csv"))
    args = parser.parse_args()

    counts = Counter()
    years = Counter()
    occupancy = Counter()
    with args.csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = 0
        unique_ids = set()
        for row in reader:
            rows += 1
            unique_ids.add(row["unique_id"])
            years[row["submission_year"]] += 1
            occupancy[row["occupancy_type"]] += 1
            for column, value in row.items():
                if value == "":
                    counts[column] += 1

    print(f"rows: {rows:,}")
    print(f"columns: {len(columns)}")
    print(f"unique IDs: {len(unique_ids):,}")
    print("\nrecords by submission year:")
    for year, count in sorted(years.items()):
        print(f"  {year}: {count:,}")
    print("\nrecords by occupancy type:")
    for label, count in occupancy.most_common():
        print(f"  {label}: {count:,}")
    print("\nblank values in important columns:")
    for column in ("monthly_rent", "bedroom_count", "bathroom_count", "vacancy_date", "analysis_neighborhood", "supervisor_district"):
        print(f"  {column}: {counts[column]:,}")


if __name__ == "__main__":
    main()
