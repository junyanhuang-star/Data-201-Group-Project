"""Parsing and cleaning helpers shared by the 3NF loader.

The functions keep raw labels available while producing the canonical values
needed by the relational schema. They do not write files or connect to MySQL.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10,
}

DATE_UNKNOWN_REASONS = {
    "Year Unknown (within past five years)": 1,
    "Year Unknown (within past 5-10 years)": 2,
    "Year Unknown (within past 10-20 years)": 3,
    "Year Unknown (more than 20 years)": 4,
    "Year unknown (no information available)": 5,
}

OCCUPANCY_TYPES = {
    "Occupied by non-owner": 1,
    "Vacant": 2,
    "Occupied by owner": 3,
    "Non-Residential": 4,
}

DATE_RANGE_TYPES = {"occupied": 1, "vacant": 2, "occupied - non owner": 3}

SQFT_IDS = {
    "0-250 Sq.Ft": 1, "0-250 Sq.ft": 2, "251-500 Sq.Ft": 3,
    "501-750 Sq.Ft": 4, "751-1000 Sq.Ft": 5, "1001-1250 Sq.Ft": 6,
    "1251-1500 Sq.Ft": 7, "1501-1750 Sq.Ft": 8, "1751-2000 Sq.Ft": 9,
    "2001-2250 Sq.Ft": 10, "2251-2500 Sq.Ft": 11, "2501-2750 Sq.Ft": 12,
    "2751-3000 Sq.Ft": 13, "3001-3250 Sq.Ft": 14, "3251-3500 Sq.Ft": 15,
    "3501-3750 Sq.Ft": 16, "3751-4000 Sq.Ft": 17, "4000+ Sq.Ft": 18,
    "Unknown": 19,
}

RENT_IDS = {
    "$0 (no rent paid by the occupant)": 1, "0": 2, "$1-$250": 3,
    "$250-$500": 4, "$251-$500": 5, "$501-$750": 6, "$751-$1000": 7,
    "$1001-$1250": 8, "$1251-$1500": 9, "$1501-$1750": 10,
    "$1750-$2000": 11, "$1751-$2000": 12, "$2001-$2250": 13,
    "$2251-$2500": 14, "$2501-$2750": 15, "$2751-$3000": 16,
    "$3001-$3250": 17, "$3251-$3500": 18, "$3501-$3750": 19,
    "$3751-$4000": 20, "$4001-$4250": 21, "$4251-$4500": 22,
    "$4501-$4750": 23, "$4751-$5000": 24, "$5001-$5250": 25,
    "$5251-$5500": 26, "$5501-$5750": 27, "$5751-$6000": 28,
    "$6001-$6250": 29, "$6251-$6500": 30, "$6501-$6750": 31,
    "$6751-$7000": 32, "$7000+": 33,
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def parse_decimal(value: str | None) -> str | None:
    value = clean(value)
    if not value:
        return None
    try:
        return format(Decimal(value), "f")
    except InvalidOperation:
        return None


def parse_int(value: str | None, minimum: int | None = None, maximum: int | None = None) -> int | None:
    value = clean(value)
    if not value:
        return None
    try:
        number = int(float(value))
    except ValueError:
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def parse_date(value: str | None, minimum: date, maximum: date) -> tuple[str | None, bool]:
    """Return ISO date and whether a nonblank source value was rejected."""
    value = clean(value)
    if not value:
        return None, False
    try:
        year, month, day = (int(part) for part in value.replace("-", "/").split("/"))
        parsed = date(year, month, day)
    except (ValueError, TypeError):
        return None, True
    if not minimum <= parsed <= maximum:
        return None, True
    return parsed.isoformat(), False


def parse_history_date(value: str | None) -> str | None:
    value = clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def parse_bedroom(value: str | None) -> int | None:
    text = clean(value).lower()
    if not text:
        return None
    if "studio" in text or "zero" in text:
        return 0
    if "5+" in text:
        return 5
    for word, number in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return number
    match = re.search(r"(?<!\d)(\d+)(?:\.0)?(?=\s*(?:bed|br|bedroom)?\b)", text)
    if match and ("bed" in text or "br" in text or text.isdigit()):
        return int(match.group(1))
    return None


def parse_bathroom(value: str | None) -> tuple[float | None, bool, bool]:
    text = clean(value).lower()
    if not text:
        return None, False, False
    if "shared bathroom" in text:
        return None, True, False
    if "bedroom" in text or "bed room" in text:
        return None, False, True
    if "three" in text and "more" in text:
        return 3.0, False, False
    if "one and a half" in text:
        return 1.5, False, False
    if "two and a half" in text:
        return 2.5, False, False
    for word, number in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return float(number), False, False
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?=\s*(?:bath|bathroom)?\b)", text)
    if match and ("bath" in text or text.replace(".0", "").isdigit()):
        return float(match.group(1)), False, False
    return None, False, True


def parse_point(value: str | None) -> tuple[str, str] | None:
    match = re.fullmatch(r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)", clean(value))
    return (match.group(1), match.group(2)) if match else None


def parse_block_label(value: str | None) -> tuple[str | None, str | None]:
    value = clean(value)
    match = re.fullmatch(r"(\d+) Block of (.+)", value)
    if not match:
        return ("0", None) if value == "0 Block of" else (None, None)
    return match.group(1), match.group(2)


def utility_matches(value: str | None) -> set[str]:
    text = clean(value).lower()
    if not text:
        return set()
    rules = {
        "heat": ("heat", "steam", "boiler", "hydronic"),
        "hot_water": ("hot water", "hot-water"), "internet": ("internet", "wifi", "wi-fi"),
        "cable": ("cable",), "parking": ("parking",), "storage": ("storage",),
        "pest_control": ("pest",), "laundry": ("laundry",), "janitorial": ("janitorial",),
        "solar": ("solar",), "all_utilities": ("all utilities",),
    }
    found = {name for name, needles in rules.items() if any(n in text for n in needles)}
    return found or {"other"}

