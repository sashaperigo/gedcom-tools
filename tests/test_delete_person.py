# tests/test_delete_person.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from gedcom_delete import delete_person_from_lines

def _lines(*rows):
    return list(rows)

# ── Test 1: Unknown xref returns error ────────────────────────────────────────
def test_unknown_xref_returns_error():
    lines = _lines('0 HEAD', '0 TRLR')
    new_lines, nav, err = delete_person_from_lines(lines, '@I999@')
    assert err is not None
    assert new_lines == lines  # unchanged

# ── Test 2: Delete sole person (no families) ─────────────────────────────────
def test_delete_sole_person():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Alice /Test/',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert '0 @I1@ INDI' not in new_lines
    assert '1 NAME Alice /Test/' not in new_lines
    assert '0 HEAD' in new_lines
    assert '0 TRLR' in new_lines

# ── Test 3: Delete HUSB from childless FAM → FAM deleted ─────────────────────
def test_delete_husb_childless_fam_deletes_fam():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Alice /Test/',
        '1 FAMS @F1@',
        '0 @I2@ INDI',
        '1 NAME Bob /Test/',
        '1 FAMS @F1@',
        '0 @F1@ FAM',
        '1 HUSB @I1@',
        '1 WIFE @I2@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert '0 @I1@ INDI' not in new_lines
    assert '0 @F1@ FAM' not in new_lines          # FAM deleted (no children)
    assert '1 FAMS @F1@' not in new_lines          # dangling ref on @I2@ removed
    assert '0 @I2@ INDI' in new_lines              # surviving spouse kept

# ── Test 4: Delete HUSB from FAM with children → FAM kept ────────────────────
def test_delete_husb_fam_with_children_keeps_fam():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Alice /Test/',
        '1 FAMS @F1@',
        '0 @I2@ INDI',
        '1 NAME Bob /Test/',
        '1 FAMS @F1@',
        '0 @I3@ INDI',
        '1 NAME Carol /Test/',
        '1 FAMC @F1@',
        '0 @F1@ FAM',
        '1 HUSB @I1@',
        '1 WIFE @I2@',
        '1 CHIL @I3@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert '0 @I1@ INDI' not in new_lines
    assert '0 @F1@ FAM' in new_lines               # FAM kept (has child)
    assert '1 HUSB @I1@' not in new_lines           # HUSB line removed
    assert '1 WIFE @I2@' in new_lines               # WIFE kept
    assert '1 CHIL @I3@' in new_lines               # CHIL kept
    # @I2@ FAMS reference kept (FAM still exists)
    assert any(l == '1 FAMS @F1@' for l in new_lines)

# ── Test 5: Delete CHIL from FAM → FAM kept ──────────────────────────────────
def test_delete_chil_fam_kept():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Parent /Test/',
        '1 FAMS @F1@',
        '0 @I2@ INDI',
        '1 NAME Child /Test/',
        '1 FAMC @F1@',
        '0 @F1@ FAM',
        '1 HUSB @I1@',
        '1 CHIL @I2@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I2@')
    assert err is None
    assert '0 @I2@ INDI' not in new_lines
    assert '0 @F1@ FAM' in new_lines               # FAM kept (HUSB remains)
    assert '1 CHIL @I2@' not in new_lines
    assert '1 HUSB @I1@' in new_lines

# ── Test 6: Delete only CHIL from otherwise-empty FAM → FAM deleted ──────────
def test_delete_only_chil_empty_fam_deletes_fam():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Child /Test/',
        '1 FAMC @F1@',
        '0 @F1@ FAM',
        '1 CHIL @I1@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert '0 @I1@ INDI' not in new_lines
    assert '0 @F1@ FAM' not in new_lines            # FAM deleted (no remaining members)
    assert nav is None                               # FAM had no HUSB/WIFE so no parent to navigate to

# ── Test 7: ASSO cleanup ──────────────────────────────────────────────────────
def test_asso_blocks_in_other_indis_removed():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Alice /Test/',
        '1 ASSO @I2@',
        '2 RELA Godchild',
        '0 @I2@ INDI',
        '1 NAME Bob /Test/',
        '1 ASSO @I1@',
        '2 RELA Godparent',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert '0 @I1@ INDI' not in new_lines
    assert '1 ASSO @I1@' not in new_lines           # Bob's ASSO referencing Alice removed
    assert '2 RELA Godparent' not in new_lines       # sub-tag also removed
    assert '0 @I2@ INDI' in new_lines

# ── Test 8: Navigate to parent via FAMC ──────────────────────────────────────
def test_navigate_to_parent():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Parent /Test/',
        '1 FAMS @F1@',
        '0 @I2@ INDI',
        '1 NAME Child /Test/',
        '1 FAMC @F1@',
        '0 @F1@ FAM',
        '1 HUSB @I1@',
        '1 CHIL @I2@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I2@')
    assert err is None
    assert nav == '@I1@'

# ── Test 9: No parent → navigate_to is None ──────────────────────────────────
def test_no_parent_navigate_to_is_none():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Root /Test/',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert nav is None

# ── Test 10: Person in two families (one childless, one with child) ───────────
def test_person_in_two_families():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Alice /Test/',
        '1 FAMS @F1@',
        '1 FAMS @F2@',
        '0 @I2@ INDI',
        '1 NAME Bob /Test/',
        '1 FAMS @F1@',
        '0 @I3@ INDI',
        '1 NAME Carol /Test/',
        '1 FAMS @F2@',
        '0 @I4@ INDI',
        '1 NAME Dave /Test/',
        '1 FAMC @F2@',
        '0 @F1@ FAM',
        '1 HUSB @I1@',
        '1 WIFE @I2@',
        '0 @F2@ FAM',
        '1 HUSB @I1@',
        '1 WIFE @I3@',
        '1 CHIL @I4@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert '0 @I1@ INDI' not in new_lines
    # @F1@ childless → deleted; @I2@'s FAMS @F1@ removed
    assert '0 @F1@ FAM' not in new_lines
    assert not any(l == '1 FAMS @F1@' for l in new_lines)
    # @F2@ has child → kept; only HUSB line removed
    assert '0 @F2@ FAM' in new_lines
    assert '1 HUSB @I1@' not in new_lines
    assert '1 WIFE @I3@' in new_lines
    assert '1 CHIL @I4@' in new_lines

# ── Navigate-to cascade: spouse ───────────────────────────────────────────────
def test_navigate_to_spouse_when_no_parent():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Alice /Test/',
        '1 FAMS @F1@',
        '0 @I2@ INDI',
        '1 NAME Bob /Test/',
        '1 FAMS @F1@',
        '0 @F1@ FAM',
        '1 HUSB @I2@',
        '1 WIFE @I1@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert nav == '@I2@'

# ── Navigate-to cascade: child when no parent or spouse ───────────────────────
def test_navigate_to_child_when_no_parent_or_spouse():
    lines = _lines(
        '0 HEAD',
        '0 @I1@ INDI',
        '1 NAME Parent /Test/',
        '1 FAMS @F1@',
        '0 @I2@ INDI',
        '1 NAME Child /Test/',
        '1 FAMC @F1@',
        '0 @F1@ FAM',
        '1 WIFE @I1@',
        '1 CHIL @I2@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@I1@')
    assert err is None
    assert nav == '@I2@'

# ── Navigate-to: mother preferred over child when both present ────────────────
def test_navigate_to_mother_over_child():
    lines = _lines(
        '0 HEAD',
        '0 @IDAD@ INDI',
        '1 NAME Father /Test/',
        '1 FAMS @FPAR@',
        '0 @IMOM@ INDI',
        '1 NAME Mother /Test/',
        '1 FAMS @FPAR@',
        '0 @ICHLD@ INDI',
        '1 NAME Child /Test/',
        '1 FAMC @FPAR@',
        '1 FAMS @FMAR@',
        '0 @IGRAND@ INDI',
        '1 NAME Grandchild /Test/',
        '1 FAMC @FMAR@',
        '0 @FPAR@ FAM',
        '1 HUSB @IDAD@',
        '1 WIFE @IMOM@',
        '1 CHIL @ICHLD@',
        '0 @FMAR@ FAM',
        '1 WIFE @ICHLD@',
        '1 CHIL @IGRAND@',
        '0 TRLR',
    )
    new_lines, nav, err = delete_person_from_lines(lines, '@ICHLD@')
    assert err is None
    # ICHLD has both parents (IDAD=father) and a child (IGRAND)
    # Father should win
    assert nav == '@IDAD@'
