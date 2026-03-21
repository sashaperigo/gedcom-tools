"""
Structural integrity tests for a GEDCOM file.

Covers:
  1. File starts with a HEAD record and ends with a TRLR record.
  2. Every line matches the GEDCOM grammar: level [xref] tag [value].
  3. Level numbers never skip (e.g. jumping from level 1 to level 3).
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

LINE_RE = re.compile(r"^\d+ (@[^@]+@ )?[A-Za-z0-9_]{1,31}( .*)?$")


@pytest.fixture(scope="module")
def ged_lines():
    with open(GED_PATH, encoding="utf-8") as f:
        return f.readlines()


def test_starts_with_head(ged_lines):
    first = next(l.rstrip("\n") for l in ged_lines if l.strip())
    assert first == "0 HEAD", f"First record is not HEAD: {first!r}"


def test_ends_with_trlr(ged_lines):
    last = next(l.rstrip("\n") for l in reversed(ged_lines) if l.strip())
    assert last == "0 TRLR", f"Last record is not TRLR: {last!r}"


def test_all_lines_match_grammar(ged_lines):
    bad = [
        (i + 1, line.rstrip("\n"))
        for i, line in enumerate(ged_lines)
        if line.strip() and not LINE_RE.match(line.rstrip("\n"))
    ]
    assert bad == [], (
        f"{len(bad)} line(s) don't match GEDCOM grammar:\n"
        + "\n".join(f"  line {ln}: {l!r}" for ln, l in bad[:20])
    )


def test_no_level_skips(ged_lines):
    bad = []
    prev_level = 0
    for i, line in enumerate(ged_lines, 1):
        m = re.match(r"^(\d+)", line)
        if not m:
            continue
        level = int(m.group(1))
        if level > prev_level + 1:
            bad.append((i, prev_level, level, line.rstrip("\n")))
        prev_level = level
    assert bad == [], (
        f"{len(bad)} level skip(s) found:\n"
        + "\n".join(f"  line {ln}: level {a} → {b}" for ln, a, b, _ in bad[:20])
    )
