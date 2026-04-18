"""
Trailing-whitespace test for a GEDCOM file.

Every line must end with the newline character only — no spaces or tabs
before it. Trailing whitespace is invisible in most editors and viewers
but can cause issues with GEDCOM parsers and diffs.

Run `gedcom-lint --fix-whitespace yourfile.ged` to auto-fix.
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

_CONC_RE = re.compile(r"^\d+ CONC")


def collect_trailing_whitespace(path: str):
    violations = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    for i, raw in enumerate(lines):
        stripped = raw.rstrip("\n")
        if stripped != stripped.rstrip():
            # Trailing space before a CONC continuation is semantically valid
            # in GEDCOM 5.5.1/5.5.5 (the space is the inter-word separator).
            next_raw = lines[i + 1] if i + 1 < len(lines) else ""
            if not _CONC_RE.match(next_raw.strip()):
                violations.append((i + 1, stripped))
    return violations


@pytest.fixture(scope="module")
def trailing_ws_violations():
    return collect_trailing_whitespace(GED_PATH)


def test_no_trailing_whitespace(trailing_ws_violations):
    bad = trailing_ws_violations
    assert bad == [], (
        f"{len(bad)} line(s) have trailing whitespace:\n"
        + "\n".join(f"  line {ln}: {v!r}" for ln, v in bad[:20])
        + ("\n  ..." if len(bad) > 20 else "")
    )
