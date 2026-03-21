"""
NAME value tests for a GEDCOM file.

Checks:
  1. No NAME value contains consecutive spaces (double spaces are data-entry
     artifacts and should be collapsed to a single space).
  2. No GEDCOM line exceeds 255 characters (the GEDCOM 5.5.1 spec limit).
     Long values must be broken with CONC continuation lines.

Run `gedcom-lint --fix-names yourfile.ged` to fix double spaces.
Run `gedcom-lint --fix-long-lines yourfile.ged` to wrap long lines.
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

NAME_LINE_RE = re.compile(r"^\d+ NAME (.+)$")
GEDCOM_MAX_LINE = 255


def collect_name_double_spaces(path: str):
    violations = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = NAME_LINE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            val = m.group(1)
            fixed = re.sub(r"  +", " ", val).strip()
            if fixed != val:
                violations.append((lineno, val, fixed))
    return violations


def collect_long_lines(path: str, max_len: int = GEDCOM_MAX_LINE):
    violations = []
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if len(line) > max_len:
                violations.append((lineno, len(line)))
    return violations


@pytest.fixture(scope="module")
def name_double_space_violations():
    return collect_name_double_spaces(GED_PATH)


@pytest.fixture(scope="module")
def long_line_violations():
    return collect_long_lines(GED_PATH)


def test_no_double_spaces_in_names(name_double_space_violations):
    bad = name_double_space_violations
    assert bad == [], (
        f"{len(bad)} NAME value(s) contain double spaces:\n"
        + "\n".join(f"  line {ln}: {v!r}  →  {f!r}" for ln, v, f in bad)
    )


def test_no_lines_exceed_255_chars(long_line_violations):
    bad = long_line_violations
    assert bad == [], (
        f"{len(bad)} line(s) exceed {GEDCOM_MAX_LINE} characters "
        f"(GEDCOM 5.5.1 spec limit):\n"
        + "\n".join(f"  line {ln}: {length} chars" for ln, length in bad)
    )
