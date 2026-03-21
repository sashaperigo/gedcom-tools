"""
Date value tests for a GEDCOM file.

Covers:
  1. Every DATE line contains an extractable year (3-or-4-digit number).
  2. Every level-2 event DATE value conforms to GEDCOM 5.5.1 date grammar.

Run `gedcom-lint --fix yourfile.ged` to auto-normalize common date formats.
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

DATE_LINE_RE = re.compile(r"^\d+ DATE (.+)$")
YEAR_RE      = re.compile(r"\b\d{3,4}\b")

MONTHS_RE = (
    r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
)
GEDCOM_DATE_RE = re.compile(
    r"^(BET .+ AND .+"
    r"|FROM .+"
    r"|(ABT|CAL|EST|BEF|AFT|INT)? ?\d{0,2} ?" + MONTHS_RE + r" \d{1,4}"
    r"|(ABT|CAL|EST|BEF|AFT|INT)? ?\d{1,4}"
    r")$",
    re.IGNORECASE,
)


def collect_date_violations(path: str):
    no_year = []
    bad_format = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = DATE_LINE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            val = m.group(1).strip()
            if not YEAR_RE.search(val):
                no_year.append((lineno, val))
            elif not GEDCOM_DATE_RE.match(val):
                if line.startswith("2 DATE "):
                    bad_format.append((lineno, val))
    return no_year, bad_format


@pytest.fixture(scope="module")
def date_violations():
    no_year, bad_format = collect_date_violations(GED_PATH)
    return {"no_year": no_year, "bad_format": bad_format}


def test_all_dates_have_extractable_year(date_violations):
    bad = date_violations["no_year"]
    assert bad == [], (
        f"{len(bad)} DATE lines have no extractable year:\n"
        + "\n".join(f"  line {ln}: {v!r}" for ln, v in bad)
    )


def test_all_dates_valid_gedcom_format(date_violations):
    bad = date_violations["bad_format"]
    assert bad == [], (
        f"{len(bad)} DATE values don't conform to GEDCOM 5.5.1 format:\n"
        + "\n".join(f"  line {ln}: {v!r}" for ln, v in bad[:20])
        + ("\n  ..." if len(bad) > 20 else "")
    )
