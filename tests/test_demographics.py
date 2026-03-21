"""
Demographic sanity tests for a GEDCOM file.

Covers:
  1. No individual dies before they are born.
  2. No parent is implausibly young (<10) or old (>90) at a child's birth.
  3. No individual is their own ancestor (cycle detection).

Date parsing extracts the first 3-or-4-digit year found in any DATE value,
which handles all standard GEDCOM formats. Records with missing dates are
skipped rather than treated as errors.
"""
import os
import re
import pytest
from collections import defaultdict

GED_PATH = os.environ.get("GED_FILE", "")

DEFN_RE = re.compile(r"^0 (@[^@]+@) (INDI|FAM)")
L1_RE   = re.compile(r"^1 ([A-Z]+)(?: (.+))?$")
L2_DATE = re.compile(r"^2 DATE (.+)$")
L1_PTR  = re.compile(r"^1 (HUSB|WIFE|CHIL) (@[^@]+@)$")
YEAR_RE = re.compile(r"\b(\d{3,4})\b")

MIN_PARENT_AGE = 10
MAX_PARENT_AGE = 90


def first_year(date_str: str) -> int | None:
    m = YEAR_RE.search(date_str)
    return int(m.group(1)) if m else None


def parse_ged(path: str) -> dict:
    records = {}
    current = None
    current_event = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            m = DEFN_RE.match(line)
            if m:
                current = m.group(1)
                current_event = None
                records[current] = {
                    "type": m.group(2), "name": "?",
                    "birt": None, "deat": None,
                    "husb": None, "wife": None, "chil": [],
                }
                continue

            if current is None:
                continue

            if line.startswith("1 NAME "):
                records[current]["name"] = line[7:]
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

    return records


@pytest.fixture(scope="module")
def records():
    return parse_ged(GED_PATH)


def test_no_death_before_birth(records):
    bad = [
        (xref, r["name"], r["birt"], r["deat"])
        for xref, r in records.items()
        if r["type"] == "INDI"
        and r["birt"] is not None and r["deat"] is not None
        and r["deat"] < r["birt"]
    ]
    assert bad == [], (
        f"{len(bad)} individuals die before birth:\n"
        + "\n".join(f"  {x} {n!r} born {b} died {d}" for x, n, b, d in bad)
    )


def test_parent_not_too_young_at_child_birth(records):
    bad = []
    for xref, rec in records.items():
        if rec["type"] != "FAM":
            continue
        child_years = [
            records[c]["birt"] for c in rec["chil"]
            if c in records and records[c]["birt"] is not None
        ]
        for parent_key in ("husb", "wife"):
            p = rec[parent_key]
            if not p or p not in records:
                continue
            pbirt = records[p]["birt"]
            if pbirt is None:
                continue
            for cy in child_years:
                age = cy - pbirt
                if age < MIN_PARENT_AGE:
                    bad.append((xref, records[p]["name"], pbirt, cy, age))
    assert bad == [], (
        f"{len(bad)} parent/child pairs where parent age at birth < {MIN_PARENT_AGE}:\n"
        + "\n".join(
            f"  FAM {f}: {n!r} born {pb}, child born {cb} → age {a}"
            for f, n, pb, cb, a in bad
        )
    )


def test_parent_not_too_old_at_child_birth(records):
    bad = []
    for xref, rec in records.items():
        if rec["type"] != "FAM":
            continue
        child_years = [
            records[c]["birt"] for c in rec["chil"]
            if c in records and records[c]["birt"] is not None
        ]
        for parent_key in ("husb", "wife"):
            p = rec[parent_key]
            if not p or p not in records:
                continue
            pbirt = records[p]["birt"]
            if pbirt is None:
                continue
            for cy in child_years:
                age = cy - pbirt
                if age > MAX_PARENT_AGE:
                    bad.append((xref, records[p]["name"], pbirt, cy, age))
    assert bad == [], (
        f"{len(bad)} parent/child pairs where parent age at birth > {MAX_PARENT_AGE}:\n"
        + "\n".join(
            f"  FAM {f}: {n!r} born {pb}, child born {cb} → age {a}"
            for f, n, pb, cb, a in bad
        )
    )


def test_no_ancestor_cycles(records):
    child_to_parents: dict[str, set[str]] = defaultdict(set)
    for rec in records.values():
        if rec["type"] != "FAM":
            continue
        for child in rec["chil"]:
            for pk in ("husb", "wife"):
                p = rec[pk]
                if p:
                    child_to_parents[child].add(p)

    def is_own_ancestor(start: str) -> bool:
        visited = set()
        queue = list(child_to_parents.get(start, []))
        while queue:
            node = queue.pop()
            if node == start:
                return True
            if node in visited:
                continue
            visited.add(node)
            queue.extend(child_to_parents.get(node, []))
        return False

    cycles = [
        xref for xref, r in records.items()
        if r["type"] == "INDI" and is_own_ancestor(xref)
    ]
    assert cycles == [], (
        f"{len(cycles)} individuals are their own ancestor:\n"
        + "\n".join(f"  {x} {records[x]['name']!r}" for x in cycles)
    )
