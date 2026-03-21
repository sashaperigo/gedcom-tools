"""
Ancestry.com proprietary tag tests.

If your GEDCOM was exported from Ancestry.com, these tests verify that
platform-specific tags have been stripped. All of these tags are
Ancestry-internal and have no meaning in the GEDCOM 5.5.1 standard.

Skip this file if your GEDCOM was not exported from Ancestry.
"""
import os
import re
import pytest

GED_PATH = os.environ.get("GED_FILE", "")
LINE_RE = re.compile(r"^(\d+) ([A-Z_][A-Z0-9_]*)( |$)")


def ancestry_tag_lines(tag: str) -> list[int]:
    hits = []
    with open(GED_PATH, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = LINE_RE.match(line)
            if m and m.group(2) == tag:
                hits.append(lineno)
    return hits


@pytest.mark.parametrize("tag", ["_APID"])
def test_no_apid(tag):
    assert ancestry_tag_lines(tag) == [], f"{tag} lines still present"


@pytest.mark.parametrize("tag", [
    "_CREA", "_USER", "_ENCR", "_ATL", "_ORIG",
    "_OID", "_MSER", "_LKID", "_CLON", "_DATE",
    "_TID", "_PID",
])
def test_no_ancestry_internal_tag(tag):
    hits = ancestry_tag_lines(tag)
    assert hits == [], f"{tag} still present at lines: {hits[:10]}"


@pytest.mark.parametrize("tag", [
    "_PRIM", "_CROP", "_LEFT", "_TOP", "_WDTH", "_HGHT", "_TYPE",
    "_WPID", "_HPID", "_TREE", "_ENV",
])
def test_no_ancestry_photo_metadata_tag(tag):
    hits = ancestry_tag_lines(tag)
    assert hits == [], f"{tag} still present at lines: {hits[:10]}"
