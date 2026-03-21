"""
PLAC (place) value tests for a GEDCOM file.

Checks:
  1. No PLAC value has leading/trailing whitespace or commas.
  2. All commas in PLAC values are followed by exactly one space and not
     preceded by a space (standard "City, County, State, Country" format).

Run `gedcom-lint --fix-plac yourfile.ged` to auto-fix.
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

PLAC_RE = re.compile(r"^\d+ PLAC (.+)$")


def normalize_plac(val: str) -> str:
    v = val.strip().strip(",").strip()
    v = re.sub(r"\s*,\s*", ", ", v)
    v = re.sub(r"\s{2,}", " ", v)
    return v


def collect_plac_violations(path: str):
    violations = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = PLAC_RE.match(line.rstrip("\n"))
            if not m:
                continue
            val = m.group(1)
            fixed = normalize_plac(val)
            if fixed != val:
                violations.append((lineno, val, fixed))
    return violations


@pytest.fixture(scope="module")
def plac_violations():
    return collect_plac_violations(GED_PATH)


def test_plac_comma_spacing(plac_violations):
    bad = plac_violations
    assert bad == [], (
        f"{len(bad)} PLAC value(s) have spacing or comma issues:\n"
        + "\n".join(f"  line {ln}: {v!r}  →  {f!r}" for ln, v, f in bad)
    )
