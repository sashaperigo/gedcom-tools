"""
Relationship integrity tests for a GEDCOM file.

Covers:
  1. No individual has a birth or death date in the future.
  2. No child is born more than 2 years after a parent's recorded death.
     (2-year buffer accounts for year-level date precision.)
  3. No individual is listed as HUSB when their SEX is F, or WIFE when SEX is M.
  4. No SOUR record is defined but never cited anywhere in the file.
  5. No FAM record has neither a spouse nor any children.
"""
import os
import re
import datetime
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

DEFN_RE      = re.compile(r"^0 (@[^@]+@) (INDI|FAM)")
L1_RE        = re.compile(r"^1 ([A-Z]+)")
L2_DATE      = re.compile(r"^2 DATE (.+)$")
L1_PTR       = re.compile(r"^1 (HUSB|WIFE|CHIL) (@[^@]+@)$")
SOUR_DEFN_RE = re.compile(r"^0 (@[^@]+@) SOUR")
SOUR_CITE_RE = re.compile(r"^\d+ SOUR (@[^@]+@)")
YEAR_RE      = re.compile(r"\b(\d{3,4})\b")

THIS_YEAR = datetime.date.today().year
POSTHUMOUS_BUFFER_YEARS = 2


def first_year(s: str):
    m = YEAR_RE.search(s)
    return int(m.group(1)) if m else None


def parse_ged(path: str):
    records = {}
    sour_defined = set()
    sour_cited = set()
    current = None
    current_event = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            m = SOUR_DEFN_RE.match(line)
            if m:
                sour_defined.add(m.group(1))

            m2 = SOUR_CITE_RE.match(line)
            if m2:
                sour_cited.add(m2.group(1))

            m = DEFN_RE.match(line)
            if m:
                current = m.group(1)
                current_event = None
                records[current] = {
                    "type": m.group(2), "name": "?", "sex": None,
                    "birt": None, "deat": None,
                    "husb": None, "wife": None, "chil": [],
                }
                continue

            if current is None:
                continue

            if line.startswith("1 NAME "):
                records[current]["name"] = line[7:]
                continue
            if line.startswith("1 SEX "):
                records[current]["sex"] = line[6:].strip()
                continue

            m = L1_PTR.match(line)
            if m:
                tag, xref = m.group(1), m.group(2)
                if tag == "HUSB":   records[current]["husb"] = xref
                elif tag == "WIFE": records[current]["wife"] = xref
                elif tag == "CHIL": records[current]["chil"].append(xref)
                current_event = None
                continue

            m = L1_RE.match(line)
            if m:
                current_event = m.group(1)
                continue

            m = L2_DATE.match(line)
            if m and current_event in ("BIRT", "DEAT"):
                yr = first_year(m.group(1))
                if yr:
                    field = "birt" if current_event == "BIRT" else "deat"
                    if records[current][field] is None:
                        records[current][field] = yr

    return records, sour_defined, sour_cited


@pytest.fixture(scope="module")
def parsed():
    return parse_ged(GED_PATH)

@pytest.fixture(scope="module")
def records(parsed):
    return parsed[0]

@pytest.fixture(scope="module")
def sour_defined(parsed):
    return parsed[1]

@pytest.fixture(scope="module")
def sour_cited(parsed):
    return parsed[2]


def test_no_future_dates(records):
    bad = [
        (xref, r["name"], r["birt"], r["deat"])
        for xref, r in records.items()
        if r["type"] == "INDI"
        and ((r["birt"] and r["birt"] > THIS_YEAR)
             or (r["deat"] and r["deat"] > THIS_YEAR))
    ]
    assert bad == [], (
        f"{len(bad)} individual(s) have birth or death dates in the future:\n"
        + "\n".join(f"  {x} {n!r} born={b} died={d}" for x, n, b, d in bad)
    )


def test_no_posthumous_births(records):
    bad = []
    for xref, rec in records.items():
        if rec["type"] != "FAM":
            continue
        child_years = [
            records[c]["birt"] for c in rec["chil"]
            if c in records and records[c]["birt"] is not None
        ]
        for role in ("husb", "wife"):
            p = rec[role]
            if not p or p not in records:
                continue
            pdeat = records[p]["deat"]
            if pdeat is None:
                continue
            for cy in child_years:
                if cy > pdeat + POSTHUMOUS_BUFFER_YEARS:
                    bad.append((xref, records[p]["name"], role, pdeat, cy))
    assert bad == [], (
        f"{len(bad)} child(ren) born more than {POSTHUMOUS_BUFFER_YEARS} year(s) "
        f"after a parent's death:\n"
        + "\n".join(
            f"  FAM {f}: {n!r} ({role}) died {pd}, child born {cy}"
            for f, n, role, pd, cy in bad
        )
    )


def test_husb_wife_sex_consistency(records):
    bad = []
    for xref, rec in records.items():
        if rec["type"] != "FAM":
            continue
        for role, wrong_sex in [("husb", "F"), ("wife", "M")]:
            p = rec[role]
            if not p or p not in records:
                continue
            if records[p]["sex"] == wrong_sex:
                bad.append((xref, records[p]["name"], role, wrong_sex))
    assert bad == [], (
        f"{len(bad)} FAM record(s) where HUSB/WIFE role contradicts SEX tag:\n"
        + "\n".join(
            f"  FAM {f}: {n!r} is {role} but SEX={s}" for f, n, role, s in bad
        )
    )


def test_no_orphaned_sources(sour_defined, sour_cited):
    orphaned = sorted(sour_defined - sour_cited)
    assert orphaned == [], (
        f"{len(orphaned)} SOUR record(s) defined but never cited:\n"
        + "\n".join(f"  {x}" for x in orphaned)
    )


def test_no_empty_families(records):
    empty = [
        xref for xref, r in records.items()
        if r["type"] == "FAM"
        and r["husb"] is None and r["wife"] is None and len(r["chil"]) == 0
    ]
    assert empty == [], (
        f"{len(empty)} FAM record(s) with no spouses and no children:\n"
        + "\n".join(f"  {x}" for x in empty)
    )
