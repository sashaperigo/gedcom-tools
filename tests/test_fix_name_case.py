"""
Tests for fix_name_case and _name_to_title_case in gedcom_linter.py.

Covers:
  - _name_to_title_case: unit tests for casing logic
  - fix_name_case: integration tests (file read/write, dry-run, return count)
"""
import textwrap
from pathlib import Path


from gedcom_linter import _name_to_title_case, fix_name_case


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_ged(tmp_path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# _name_to_title_case — unit tests
# ---------------------------------------------------------------------------

class TestNameToTitleCase:

    # ── Basic conversion ─────────────────────────────────────────────────────

    def test_simple_given_and_surname(self):
        assert _name_to_title_case('JOHN /SMITH/') == 'John /Smith/'

    def test_given_only(self):
        assert _name_to_title_case('JOHN') == 'John'

    def test_surname_only_in_slashes(self):
        assert _name_to_title_case('/SMITH/') == '/Smith/'

    def test_multiple_given_names(self):
        assert _name_to_title_case('JOHN WILLIAM /SMITH/') == 'John William /Smith/'

    # ── Particles outside slashes (stay lowercase) ───────────────────────────

    def test_de_before_surname(self):
        assert _name_to_title_case('JOHN DE /TORRE/') == 'John de /Torre/'

    def test_de_la_before_surname(self):
        assert _name_to_title_case('JOHN DE LA /TORRE/') == 'John de la /Torre/'

    def test_van_before_surname(self):
        assert _name_to_title_case('PIETER /VAN DEN BERG/') == 'Pieter /van den Berg/'

    def test_von_before_surname(self):
        assert _name_to_title_case('HANS /VON TRAPP/') == 'Hans /von Trapp/'

    def test_di_particle(self):
        assert _name_to_title_case('MARIO DI /STEFANO/') == 'Mario di /Stefano/'

    def test_del_particle(self):
        assert _name_to_title_case('LUIGI DEL /BOSCO/') == 'Luigi del /Bosco/'

    # ── Particles inside slashes (first word of surname → capitalized) ───────

    def test_de_inside_slashes_lowercase(self):
        # "de Torre" — particle stays lowercase even at the start of a surname block
        assert _name_to_title_case('JOHN /DE TORRE/') == 'John /de Torre/'

    def test_van_inside_slashes_lowercase(self):
        assert _name_to_title_case('PIETER /VAN BERG/') == 'Pieter /van Berg/'

    # ── Special punctuation ───────────────────────────────────────────────────

    def test_hyphenated_surname(self):
        assert _name_to_title_case('MARY /SMITH-JONES/') == 'Mary /Smith-Jones/'

    def test_apostrophe_in_surname(self):
        assert _name_to_title_case("SEAN /O'BRIEN/") == "Sean /O'Brien/"

    # ── No change when already mixed case ────────────────────────────────────
    # (This is handled by fix_name_case; _name_to_title_case is called only
    #  when the caller has already confirmed the value is all-caps.)


# ---------------------------------------------------------------------------
# fix_name_case — integration tests
# ---------------------------------------------------------------------------

class TestFixNameCase:

    def test_all_caps_name_converted(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME JOHN /SMITH/
            0 TRLR
        """)
        fix_name_case(str(p))
        assert '1 NAME John /Smith/' in p.read_text(encoding='utf-8')

    def test_mixed_case_name_untouched(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_name_case(str(p))
        assert p.read_text(encoding='utf-8') == original

    def test_partial_caps_name_untouched(self, tmp_path):
        """A name with any lowercase letter is left alone."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME JOHN /Smith/
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_name_case(str(p))
        assert p.read_text(encoding='utf-8') == original

    def test_particle_de_stays_lowercase(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME JOHN DE LA /TORRE/
            0 TRLR
        """)
        fix_name_case(str(p))
        assert '1 NAME John de la /Torre/' in p.read_text(encoding='utf-8')

    def test_non_name_tag_untouched(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME JOHN /SMITH/
            2 NOTE BORN IN LONDON
            0 TRLR
        """)
        fix_name_case(str(p))
        c = p.read_text(encoding='utf-8')
        assert 'BORN IN LONDON' in c

    def test_returns_count_of_changed_lines(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME ALICE /JONES/
            0 @I2@ INDI
            1 NAME BOB /JONES/
            0 @I3@ INDI
            1 NAME Carol /Jones/
            0 TRLR
        """)
        count = fix_name_case(str(p))
        assert count == 2

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME JOHN /SMITH/
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_name_case(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_dry_run_returns_correct_count(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME ALICE /JONES/
            0 @I2@ INDI
            1 NAME BOB /JONES/
            0 TRLR
        """)
        count = fix_name_case(str(p), dry_run=True)
        assert count == 2

    def test_no_changes_returns_zero(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            0 TRLR
        """)
        count = fix_name_case(str(p))
        assert count == 0
