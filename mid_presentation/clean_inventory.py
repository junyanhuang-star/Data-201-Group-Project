#!/usr/bin/env python3
"""Parsing rules for the SF Rent Board export.

This module holds the row-level parsing functions only. It maps spelling
variants to canonical values and splits the free-text utility field, while
load_3nf.py owns the full pipeline (reading the CSV, assigning IDs, recording
quality issues, and writing the staging files). Keeping the rules here and
importing them into the loader means each rule is written exactly once.

An earlier version of this file also had its own main() that wrote a second
set of cleaned CSVs. Those files were never read by the loader and repeated
its history and quality-issue logic, so that main() was removed.

AI-assistance disclosure:

The data preparation stage heavily relied on AI assistance to implement code
that was not explicitly covered in the course. AI was used to help determine
bash commands for finding unique values, identify ways to group inconsistent
data, and draft preprocessing logic that parses and formats rows. The team
will review, understand, verify, and modify this implementation before deciding
whether to use any part of it in the final project.
"""

import csv
import gzip
import re
from datetime import datetime

csv.field_size_limit(10**9)

BED_WORDS = {"studio": 0, "zero": 0, "0": 0, "one": 1, "1": 1,
             "two": 2, "2": 2, "three": 3, "3": 3, "four": 4, "4": 4}

# The four Y/N checkbox columns and the canonical utility each one asserts.
CHECKBOX_UTILITIES = {
    "base_rent_includes_water_sewer": "water_sewer",
    "base_rent_includes_natural_gas": "natural_gas",
    "base_rent_includes_electricity": "electricity",
    "base_rent_includes_refuse_recycling": "refuse_recycling",
}

# Free-text "other utilities" patterns, checked by substring. The list is
# ordered so that "hot water" is claimed before the bare word "water"; see
# parse_other_utilities(). Substring matching is a deliberate simplification
# and can over-match on long sentences, so the raw text is always kept on
# UnitReport.other_utilities_raw for review.
OTHER_UTILITY_PATTERNS = [
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
    ("electricity", ("electric",)),
    ("natural_gas", ("gas", "pg&e")),
    ("water_sewer", ("water", "sewer")),
    ("all_utilities", ("all utilities",)),
]

# Free-text answers that mean "nothing extra is included" rather than naming
# a utility. These produce no ReportUtility row at all.
OTHER_UTILITY_NEGATIVES = {"n/a", "na", "n\\a", "no", "non", "none", "0", "-"}

# Clauses that say a utility is NOT included, e.g. "gas for cooking is
# included, but gas for heating water is not." (83 rows). Without this, the
# substring match would credit heat and water_sewer from the negated clause.
CLAUSE_SPLIT = re.compile(r",|;|\bbut\b")
NEGATED_CLAUSE = re.compile(r"\bis not\b|\bnot included\b|\bexcluded\b|\bnot\s*\.?$")

# The five "Year Unknown (...)" choices the form offers instead of a year.
# They are legitimate answers, stored as text in UnitReport.date_unknown_text,
# not data errors. (A lookup table for them is planned future work.)
DATE_UNKNOWN_PREFIX = "year unknown"


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
    """Return (year, unknown_phrase, junk_text) for occupancy_or_vacancy_date_year.

    Exactly one of the three is non-None for a non-blank value: a plausible
    four-digit year, one of the form's "Year Unknown (...)" phrases, or text
    that is neither (for example "20204" or "2008.").
    """
    raw = clean_text(raw)
    if not raw:
        return None, None, None
    if re.fullmatch(r"\d{4}", raw) and 1900 <= int(raw) <= 2026:
        return int(raw), None, None
    if raw.lower().startswith(DATE_UNKNOWN_PREFIX):
        return None, raw, None
    return None, None, raw


def parse_yes_no(raw):
    raw = clean_text(raw)
    if raw is None:
        return None
    if raw.lower() in {"y", "yes", "true"}:
        return "1"
    if raw.lower() in {"n", "no", "false"}:
        return "0"
    return None



def parse_other_utilities(raw):
    """Map the free-text utility field to a set of canonical utility names.

    Unrecognised but non-empty text maps to "other" so the fact that something
    extra was included is not lost. Negative answers ("none", "n/a") map to
    nothing.
    """
    other = clean_text(raw)
    if not other:
        return set()
    s = other.lower().strip(" .!")
    if s in OTHER_UTILITY_NEGATIVES:
        return set()
    # Match only the clauses that assert inclusion.
    s = ",".join(clause for clause in CLAUSE_SPLIT.split(s)
                 if not NEGATED_CLAUSE.search(clause.strip()))
    found = set()
    for utility, needles in OTHER_UTILITY_PATTERNS:
        if any(needle in s for needle in needles):
            found.add(utility)
    # "hot water" already claimed the phrase; do not also count it as
    # water/sewer unless water or sewer is named again on its own.
    remainder = s.replace("hot water", "")
    if "hot_water" in found and "water" not in remainder and "sewer" not in remainder:
        found.discard("water_sewer")
    return found or {"other"}


def utility_tokens(row):
    """Return {utility_name: {"checkbox", "text"}} for one CSV row.

    The raw CSV stores four utilities as separate Y/N columns plus one
    free-text field. The normalized design stores utility membership as
    ReportUtility rows, and the source set records whether each claim came
    from a checkbox, the free text, or both, so the four Y/N columns can
    still be reconstructed.
    """
    found = {}
    for column, utility in CHECKBOX_UTILITIES.items():
        # Only an explicit Y means that the checkbox asserts inclusion.
        if (row.get(column) or "").strip().upper() == "Y":
            found.setdefault(utility, set()).add("checkbox")
    for utility in parse_other_utilities(row.get("base_rent_includes_other_utilities")):
        found.setdefault(utility, set()).add("text")
    return found


def open_csv(path):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return open(path, "r", encoding="utf-8-sig", newline="")


