"""
Data quality tests for a GEDCOM file.

Covers:
  1. Every NAME value has balanced surname slashes (e.g. /Smith/).
  2. Every SEX value is one of M, F, or U.
  3. No FAM record lists the same individual as both HUSB and WIFE.
  4. No PLAC value is blank.
  5. No marriage date precedes either spouse's birth date.
  6. No marriage date follows either spouse's death date.
  7. No individual has two BIRT or DEAT events with an identical date and place.
  8. No FACT or EVEN record is completely empty (no inline value, no DATE, no PLAC, no TYPE).
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

_EMPTY_EVT_TAGS = {"FACT", "EVEN"}

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
    empty_events = []
    # Track a pending FACT/EVEN: (lineno, xref, tag) — flushed when we see content or next level-1
    _pending_evt = None   # (lineno, xref, tag) waiting to see if it gets any children

    def _flush_pending(had_content: bool):
        nonlocal _pending_evt
        if _pending_evt and not had_content:
            empty_events.append(_pending_evt)
        _pending_evt = None

    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")

            if L0_RE.match(line):
                _flush_pending(False)
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
                # Flush any pending empty-event check before moving to the next level-1 tag
                _flush_pending(False)
                current_event = ml1.group(1)
                inline_val = (ml1.group(2) or "").strip()
                if current_event in _EMPTY_EVT_TAGS and records[current]["type"] == "INDI":
                    # Register as pending; mark content=True if inline value exists
                    if inline_val:
                        _pending_evt = None  # has inline value → not empty
                    else:
                        _pending_evt = (lineno, current, current_event)
                continue

            md = L2_DATE.match(line)
            if md and current_event in ("BIRT", "DEAT", "MARR"):
                yr = first_year(md.group(1))
                if yr:
                    field = {"BIRT": "birt", "DEAT": "deat", "MARR": "marr"}[current_event]
                    if records[current][field] is None:
                        records[current][field] = yr

            # DATE, PLAC, or NOTE children count as real content (TYPE alone is just a label)
            if line.startswith("2 DATE ") or line.startswith("2 PLAC ") or line.startswith("2 NOTE "):
                _flush_pending(True)

    _flush_pending(False)

    return {
        "records": records,
        "name_issues": name_issues,
        "sex_issues": sex_issues,
        "blank_plac": blank_plac,
        "empty_events": empty_events,
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


# ---------------------------------------------------------------------------
# 7. No duplicate identical BIRT/DEAT events
# ---------------------------------------------------------------------------

def _iter_event_blocks(path: str):
    """
    Yield (xref, tag, date, plac) for every BIRT/DEAT block in every INDI record.
    date and plac are None when absent from the block.
    """
    L2_PLAC = re.compile(r"^2 PLAC (.+)$")
    with open(path, encoding="utf-8") as f:
        all_lines = [l.rstrip("\n") for l in f]

    i = 0
    while i < len(all_lines):
        if not re.match(r"^0 @.*@ INDI\b", all_lines[i]):
            i += 1
            continue
        xref = re.match(r"^0 (@[^@]+@)", all_lines[i]).group(1)
        i += 1
        rec_lines = []
        while i < len(all_lines) and not re.match(r"^0 ", all_lines[i]):
            rec_lines.append(all_lines[i])
            i += 1

        j = 0
        while j < len(rec_lines):
            m = re.match(r"^1 (BIRT|DEAT)\b", rec_lines[j])
            if not m:
                j += 1
                continue
            tag = m.group(1)
            j += 1
            date = plac = None
            while j < len(rec_lines) and re.match(r"^[2-9] ", rec_lines[j]):
                dm = L2_DATE.match(rec_lines[j])
                pm = L2_PLAC.match(rec_lines[j])
                if dm:
                    date = dm.group(1).strip()
                if pm:
                    plac = pm.group(1).strip()
                j += 1
            yield xref, tag, date, plac


@pytest.fixture(scope="module")
def event_blocks():
    return list(_iter_event_blocks(GED_PATH))


def test_no_duplicate_identical_events(event_blocks):
    """No individual should have two BIRT or DEAT blocks with the same date and place."""
    seen = defaultdict(list)
    for xref, tag, date, plac in event_blocks:
        seen[(xref, tag)].append((date, plac))

    bad = []
    for (xref, tag), keys in seen.items():
        counts = {}
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        dups = {k: n for k, n in counts.items() if n > 1}
        if dups:
            bad.append((xref, tag, dups))

    assert bad == [], (
        f"{len(bad)} individual(s) have duplicate BIRT/DEAT events with identical date+place:\n"
        + "\n".join(f"  {x} {t}: {d}" for x, t, d in bad[:10])
    )


def test_no_empty_fact_or_even(ged):
    """Every FACT and EVEN on an INDI must have at least one of: inline value, DATE, PLAC, or TYPE."""
    bad = ged["empty_events"]
    assert bad == [], (
        f"{len(bad)} completely empty FACT/EVEN record(s) found:\n"
        + "\n".join(f"  line {ln} {xref}: 1 {tag}" for ln, xref, tag in bad)
    )
