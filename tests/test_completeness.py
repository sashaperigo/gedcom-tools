"""
Completeness tests for a GEDCOM file.

Covers:
  1. No duplicate SOUR records (same title, author, publisher).
  2. Every INDI record has at least one NAME tag.
  3. Every FAM record has at least one member (HUSB, WIFE, or CHIL).
  4. Every OBJE pointer resolves to a defined OBJE record.
  5. Every FAMS pointer on an INDI has a corresponding HUSB/WIFE in that FAM.
  6. Every FAMC pointer on an INDI has a corresponding CHIL in that FAM.
"""
import os
import re
import pytest
from collections import defaultdict

GED_PATH = os.environ.get("GED_FILE", "")

DEFN_RE  = re.compile(r"^0 (@[^@]+@) ([A-Z]+)")
L1_TAG   = re.compile(r"^1 ([A-Z]+)(?: (.*))?$")
L2_TAG   = re.compile(r"^2 ([A-Z]+)(?: (.*))?$")
OBJE_PTR = re.compile(r"^\d+ OBJE (@[^@]+@)$")


def parse_ged(path: str) -> dict:
    records   = {}
    sour_body = defaultdict(list)
    defined   = {}   # xref -> record type string
    obje_refs = []   # (citing_xref, target_xref) for every OBJE pointer
    current   = None
    cur_type  = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            m = DEFN_RE.match(line)
            if m:
                current, cur_type = m.group(1), m.group(2)
                defined[current] = cur_type
                records[current] = {"type": cur_type, "tags": defaultdict(list), "raw": []}
                continue

            if current is None:
                continue

            records[current]["raw"].append(line)

            m1 = L1_TAG.match(line)
            if m1:
                records[current]["tags"][m1.group(1)].append(m1.group(2) or "")

            if cur_type == "SOUR":
                m2 = L2_TAG.match(line)
                if m2 and m2.group(1) in ("TITL", "AUTH", "PUBL"):
                    sour_body[current].append(line)

            mo = OBJE_PTR.match(line)
            if mo:
                obje_refs.append((current, mo.group(1)))

    return {"records": records, "sour_body": sour_body, "defined": defined, "obje_refs": obje_refs}


@pytest.fixture(scope="module")
def ged():
    return parse_ged(GED_PATH)


def test_no_duplicate_sources(ged):
    sour_body = ged["sour_body"]
    seen: dict[tuple, str] = {}
    dupes = []
    for xref, lines in sour_body.items():
        key = tuple(sorted(lines))
        if key in seen:
            dupes.append((xref, seen[key]))
        else:
            seen[key] = xref
    assert dupes == [], (
        f"{len(dupes)} duplicate SOUR record pair(s):\n"
        + "\n".join(f"  {a} == {b}" for a, b in dupes)
    )


def test_every_indi_has_name(ged):
    records = ged["records"]
    bad = [
        xref for xref, r in records.items()
        if r["type"] == "INDI" and not r["tags"].get("NAME")
    ]
    assert bad == [], (
        f"{len(bad)} INDI record(s) with no NAME tag:\n"
        + "\n".join(f"  {x}" for x in bad)
    )


def test_every_fam_has_member(ged):
    records = ged["records"]
    bad = [
        xref for xref, r in records.items()
        if r["type"] == "FAM"
        and not r["tags"].get("HUSB")
        and not r["tags"].get("WIFE")
        and not r["tags"].get("CHIL")
    ]
    assert bad == [], (
        f"{len(bad)} FAM record(s) with no HUSB, WIFE, or CHIL:\n"
        + "\n".join(f"  {x}" for x in bad)
    )


def test_obje_pointers_resolve(ged):
    defined = ged["defined"]
    bad = [
        (src, xref)
        for src, xref in ged["obje_refs"]
        if defined.get(xref) != "OBJE"
    ]
    assert bad == [], (
        f"{len(bad)} OBJE pointer(s) don't resolve to an OBJE record:\n"
        + "\n".join(f"  {s} → {x}" for s, x in bad[:10])
    )


def test_fams_bidirectional(ged):
    records = ged["records"]
    bad = []
    for xref, r in records.items():
        if r["type"] != "INDI":
            continue
        for fam_xref in r["tags"].get("FAMS", []):
            fam_xref = fam_xref.strip()
            if fam_xref not in records:
                continue
            fam = records[fam_xref]
            husbs = [v.strip() for v in fam["tags"].get("HUSB", [])]
            wives = [v.strip() for v in fam["tags"].get("WIFE", [])]
            if xref not in husbs and xref not in wives:
                bad.append((xref, fam_xref))
    assert bad == [], (
        f"{len(bad)} FAMS pointer(s) with no matching HUSB/WIFE in FAM:\n"
        + "\n".join(f"  {i} → FAM {f}" for i, f in bad[:20])
    )


def test_famc_bidirectional(ged):
    records = ged["records"]
    bad = []
    for xref, r in records.items():
        if r["type"] != "INDI":
            continue
        for fam_xref in r["tags"].get("FAMC", []):
            fam_xref = fam_xref.strip()
            if fam_xref not in records:
                continue
            fam = records[fam_xref]
            chil = [v.strip() for v in fam["tags"].get("CHIL", [])]
            if xref not in chil:
                bad.append((xref, fam_xref))
    assert bad == [], (
        f"{len(bad)} FAMC pointer(s) with no matching CHIL in FAM:\n"
        + "\n".join(f"  {i} → FAM {f}" for i, f in bad[:20])
    )
