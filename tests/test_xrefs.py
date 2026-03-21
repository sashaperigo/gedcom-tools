"""
Cross-reference integrity tests for a GEDCOM file.

Covers:
  1. No xref ID is defined more than once.
  2. Every pointer (@xref@) in the file resolves to a defined record.
  3. FAMC pointers reference FAM records.
  4. FAMS pointers reference FAM records.
  5. HUSB pointers reference INDI records.
  6. WIFE pointers reference INDI records.
  7. CHIL pointers reference INDI records.
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")

DEFN_RE    = re.compile(r"^0 (@[^@]+@) ([A-Z]+)")
POINTER_RE = re.compile(r"^(\d+) ([A-Z]+) (@[^@]+@)$")

# Tags whose pointers we skip in the dangling-reference check
# (e.g. Ancestry _MTTAG references that may not be defined)
SKIP_POINTER_TAGS = {"_MTTAG"}


def parse_ged(path: str) -> dict:
    defined  = {}   # xref -> record type
    pointers = {}   # tag  -> [xrefs]
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = DEFN_RE.match(line)
            if m:
                defined[m.group(1)] = m.group(2)
                continue
            m = POINTER_RE.match(line)
            if m:
                tag, xref = m.group(2), m.group(3)
                pointers.setdefault(tag, []).append(xref)
    return {"defined": defined, "pointers": pointers}


@pytest.fixture(scope="module")
def ged():
    return parse_ged(GED_PATH)


def test_no_duplicate_xrefs(ged):
    # Re-parse counting occurrences
    counts: dict[str, int] = {}
    with open(GED_PATH, encoding="utf-8") as f:
        for line in f:
            m = DEFN_RE.match(line.rstrip("\n"))
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    dupes = {x: c for x, c in counts.items() if c > 1}
    assert dupes == {}, f"Duplicate xref definitions: {dupes}"


def test_all_pointers_resolve(ged):
    defined  = ged["defined"]
    pointers = ged["pointers"]
    dangling = []
    for tag, xrefs in pointers.items():
        if tag in SKIP_POINTER_TAGS:
            continue
        for xref in xrefs:
            if xref not in defined:
                dangling.append((tag, xref))
    assert dangling == [], (
        f"{len(dangling)} dangling pointer(s):\n"
        + "\n".join(f"  {tag} → {x}" for tag, x in dangling[:20])
    )


@pytest.mark.parametrize("tag", ["FAMC", "FAMS"])
def test_family_pointers_reference_fam(ged, tag):
    defined  = ged["defined"]
    pointers = ged["pointers"]
    bad = [x for x in pointers.get(tag, []) if defined.get(x) != "FAM"]
    assert bad == [], f"{tag} pointers not pointing to FAM: {bad[:10]}"


@pytest.mark.parametrize("tag", ["HUSB", "WIFE", "CHIL"])
def test_individual_pointers_reference_indi(ged, tag):
    defined  = ged["defined"]
    pointers = ged["pointers"]
    bad = [x for x in pointers.get(tag, []) if defined.get(x) != "INDI"]
    assert bad == [], f"{tag} pointers not pointing to INDI: {bad[:10]}"
