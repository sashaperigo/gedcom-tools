"""
Data quality tests for a GEDCOM file.

Covers:
  1. Every NAME value has balanced surname slashes (e.g. /Smith/).
  2. Every SEX value is one of M, F, or U.
  3. No FAM record lists the same individual as both HUSB and WIFE.
  4. No PLAC value is blank.
  5. No marriage date precedes either spouse's birth date.
  6. No marriage date follows either spouse's death date.
"""
import os
import re
import pytest
from collections import defaultdict

GED_PATH = os.environ.get("GED_FILE", "")

DEFN_RE  = re.compile(r"^0 (@[^@]+@) (INDI|FAM)$")
L0_RE    = re.compile(r"^0 ")
L1_RE    = re.compile(r"^1 ([A-Z]+)(?: (.+))?$")
L2_DATE  = re.compile(r"^2 DATE (.+)$")
L1_PTR   = re.compile(r"^1 (HUSB|WIFE) (@[^@]+@)$")
YEAR_RE  = re.compile(r"\b(\d{3,4})\b")
NAME_RE  = re.compile(r"^1 NAME (.*)$")
SEX_RE   = re.compile(r"^1 SEX (.+)$")
PLAC_RE  = re.compile(r"^\d+ PLAC (.*)$")

VALID_SEX = {"M", "F", "U"}


def first_year(s: str) -> int | None:
    m = YEAR_RE.search(s)
    return int(m.group(1)) if m else None


def parse_ged(path: str) -> dict:
    records = {}
    current = None
    current_event = None
    name_issues = []
    sex_issues = []
    blank_plac = []

    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")

            if L0_RE.match(line):
                current = None
                current_event = None

            m = DEFN_RE.match(line)
            if m:
                current = m.group(1)
                records[current] = {
                    "type": m.group(2), "name": "?",
                    "birt": None, "deat": None, "marr": None,
                    "husb": None, "wife": None,
                }
                continue

            if current is None:
                continue

            mn = NAME_RE.match(line)
            if mn:
                val = mn.group(1)
                records[current]["name"] = val
                slash_count = val.count("/")
                if slash_count % 2 != 0:
                    name_issues.append((lineno, current, val))
                continue

            ms = SEX_RE.match(line)
            if ms:
                sex = ms.group(1).strip()
                if sex not in VALID_SEX:
                    sex_issues.append((lineno, current, sex))
                continue

            mp = PLAC_RE.match(line)
            if mp and mp.group(1).strip() == "":
                blank_plac.append((lineno, current))
                continue

            ml = L1_PTR.match(line)
            if ml:
                tag, xref = ml.group(1), ml.group(2)
                if tag == "HUSB": records[current]["husb"] = xref
                elif tag == "WIFE": records[current]["wife"] = xref
                current_event = None
                continue

            ml1 = L1_RE.match(line)
            if ml1:
                current_event = ml1.group(1)
                continue

            md = L2_DATE.match(line)
            if md and current_event in ("BIRT", "DEAT", "MARR"):
                yr = first_year(md.group(1))
                if yr:
                    field = {"BIRT": "birt", "DEAT": "deat", "MARR": "marr"}[current_event]
                    if records[current][field] is None:
                        records[current][field] = yr

    return {
        "records": records,
        "name_issues": name_issues,
        "sex_issues": sex_issues,
        "blank_plac": blank_plac,
    }


@pytest.fixture(scope="module")
def ged():
    return parse_ged(GED_PATH)


def test_name_slash_balance(ged):
    bad = ged["name_issues"]
    assert bad == [], (
        f"{len(bad)} NAME value(s) have unbalanced slashes:\n"
        + "\n".join(f"  line {ln} {x}: {v!r}" for ln, x, v in bad)
    )


def test_sex_values_valid(ged):
    bad = ged["sex_issues"]
    assert bad == [], (
        f"{len(bad)} SEX value(s) not in {{M, F, U}}:\n"
        + "\n".join(f"  line {ln} {x}: {v!r}" for ln, x, v in bad)
    )


def test_no_self_referential_fam(ged):
    records = ged["records"]
    bad = [
        xref for xref, r in records.items()
        if r["type"] == "FAM" and r["husb"] and r["husb"] == r["wife"]
    ]
    assert bad == [], f"FAM records with same HUSB and WIFE: {bad}"


def test_no_blank_plac(ged):
    bad = ged["blank_plac"]
    assert bad == [], (
        f"{len(bad)} blank PLAC value(s):\n"
        + "\n".join(f"  line {ln} in {x}" for ln, x in bad[:20])
    )


def test_marriage_not_before_spouse_birth(ged):
    records = ged["records"]
    bad = []
    for xref, rec in records.items():
        if rec["type"] != "FAM" or not rec["marr"]:
            continue
        for pk in ("husb", "wife"):
            p = rec[pk]
            if not p or p not in records:
                continue
            pr = records[p]
            if pr["birt"] and rec["marr"] < pr["birt"]:
                bad.append((xref, records[p]["name"], rec["marr"], pr["birt"]))
    assert bad == [], (
        f"{len(bad)} marriage(s) before a spouse's birth:\n"
        + "\n".join(
            f"  FAM {f}: {n!r} born {b}, married {m}" for f, n, m, b in bad
        )
    )


def test_marriage_not_after_spouse_death(ged):
    records = ged["records"]
    bad = []
    for xref, rec in records.items():
        if rec["type"] != "FAM" or not rec["marr"]:
            continue
        for pk in ("husb", "wife"):
            p = rec[pk]
            if not p or p not in records:
                continue
            pr = records[p]
            if pr["deat"] and rec["marr"] > pr["deat"]:
                bad.append((xref, records[p]["name"], rec["marr"], pr["deat"]))
    assert bad == [], (
        f"{len(bad)} marriage(s) after a spouse's death:\n"
        + "\n".join(
            f"  FAM {f}: {n!r} died {d}, married {m}" for f, n, m, d in bad
        )
    )
