"""
Tests for PLAC address-part detection and fixing.

Covers:
  - classify_plac_part: unit tests for all classification branches
  - scan_plac_address_parts: integration tests using inline GED content
  - fix_plac_address_parts: fix tests including merge, dry-run, and edge cases
"""
import textwrap
from pathlib import Path

import pytest

from gedcom_linter import classify_plac_part, scan_plac_address_parts, fix_plac_address_parts

FIXTURE = Path(__file__).parent / 'fixtures' / 'plac_address_parts.ged'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_ged(tmp_path, content: str) -> Path:
    """Write a GED string (de-indented) to a temp file and return the path."""
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# classify_plac_part — unit tests
# ---------------------------------------------------------------------------

class TestClassifyPlacPart:

    # ── Street-address cases (→ 'addr') ─────────────────────────────────────

    def test_number_and_street_suffix(self):
        assert classify_plac_part('51 Forest Ave') == 'addr'

    def test_number_and_full_suffix(self):
        assert classify_plac_part('123 Main Street') == 'addr'

    def test_suffix_without_number(self):
        """Street suffix alone (no leading digit) still → addr."""
        assert classify_plac_part('Forest Avenue') == 'addr'

    def test_old_post_road(self):
        assert classify_plac_part('Old Post Road') == 'addr'

    def test_route_keyword(self):
        assert classify_plac_part('Route 66') == 'addr'

    def test_highway_keyword(self):
        assert classify_plac_part('Highway 101') == 'addr'

    def test_parkway(self):
        assert classify_plac_part('Riverside Parkway') == 'addr'

    def test_leading_digit_no_suffix(self):
        """Any leading digit → addr, even without a recognisable suffix."""
        assert classify_plac_part('4 High Street') == 'addr'

    def test_bare_number(self):
        """A bare number (e.g. house number) → addr."""
        assert classify_plac_part('42') == 'addr'

    def test_zip_code(self):
        """ZIP codes embedded as first part → addr (starts with digit)."""
        assert classify_plac_part('02134') == 'addr'

    def test_1st_avenue(self):
        """Ordinal street name starts with digit → addr."""
        assert classify_plac_part('1st Avenue') == 'addr'

    def test_number_wins_over_place_keyword(self):
        """Leading digit takes priority, even if a place keyword appears later."""
        assert classify_plac_part('100 Acres Plantation') == 'addr'

    def test_street_suffix_wins_over_place_keyword(self):
        """Street suffix wins over place keyword (e.g. 'New Cemetery Lane')."""
        assert classify_plac_part('New Cemetery Lane') == 'addr'

    def test_alley(self):
        assert classify_plac_part('Tin Pan Alley') == 'addr'

    def test_court(self):
        assert classify_plac_part('Madison Court') == 'addr'

    def test_suffix_case_insensitive(self):
        assert classify_plac_part('Oak BOULEVARD') == 'addr'

    # ── Named-place descriptor cases (→ 'note') ──────────────────────────────

    def test_cemetery(self):
        assert classify_plac_part('Putnam Cemetery') == 'note'

    def test_common_misspelling_cemetary(self):
        assert classify_plac_part('Green Lawn Cemetary') == 'note'

    def test_church(self):
        assert classify_plac_part("St. Mary's Church") == 'note'

    def test_hospital(self):
        assert classify_plac_part("St. Mary's Hospital") == 'note'

    def test_university(self):
        assert classify_plac_part('University of Oxford') == 'note'

    def test_college(self):
        assert classify_plac_part('King College') == 'note'

    def test_fort(self):
        assert classify_plac_part('Fort Hamilton') == 'note'

    def test_camp(self):
        assert classify_plac_part('Camp David') == 'note'

    def test_chapel(self):
        assert classify_plac_part('Royal Chapel') == 'note'

    def test_synagogue(self):
        assert classify_plac_part('Beth Shalom Synagogue') == 'note'

    def test_mosque(self):
        assert classify_plac_part('Al-Noor Mosque') == 'note'

    def test_asylum(self):
        assert classify_plac_part('Broadmoor Asylum') == 'note'

    def test_graveyard(self):
        assert classify_plac_part('Old Parish Graveyard') == 'note'

    def test_plantation(self):
        assert classify_plac_part('Magnolia Plantation') == 'note'

    def test_keyword_case_insensitive(self):
        assert classify_plac_part('MOUNT AUBURN CEMETERY') == 'note'

    def test_funeral_home(self):
        assert classify_plac_part('Jones Funeral Home') == 'note'

    def test_barracks(self):
        assert classify_plac_part('Wellington Barracks') == 'note'

    def test_crematorium(self):
        assert classify_plac_part('West London Crematorium') == 'note'

    def test_infirmary(self):
        assert classify_plac_part('Royal Infirmary') == 'note'

    # ── Ambiguous cases ──────────────────────────────────────────────────────

    def test_apartment_number(self):
        assert classify_plac_part('Apt 4B') == 'ambiguous'

    def test_po_box(self):
        assert classify_plac_part('P.O. Box 123') == 'ambiguous'

    def test_plain_building_name(self):
        assert classify_plac_part('The Elms') == 'ambiguous'

    def test_neighbourhood(self):
        assert classify_plac_part('Notting Hill') == 'ambiguous'

    # ── None cases ───────────────────────────────────────────────────────────

    def test_empty_string(self):
        assert classify_plac_part('') is None

    def test_whitespace_only(self):
        assert classify_plac_part('   ') is None


# ---------------------------------------------------------------------------
# scan_plac_address_parts — integration tests
# ---------------------------------------------------------------------------

class TestScanPlacAddressParts:

    def test_street_address_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 1
        ln, val, first, cat = results[0]
        assert first == '51 Forest Ave'
        assert cat == 'addr'

    def test_cemetery_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BURT
            2 PLAC Putnam Cemetery, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 1
        assert results[0][3] == 'note'
        assert results[0][2] == 'Putnam Cemetery'

    def test_clean_plac_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        assert scan_plac_address_parts(str(p)) == []

    def test_single_component_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC England
            0 TRLR
        """)
        assert scan_plac_address_parts(str(p)) == []

    def test_ambiguous_not_in_scan_results(self, tmp_path):
        """Ambiguous first parts (e.g. 'Apt 4B') are not returned by scan —
        they are indistinguishable from valid city names and would be too noisy."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESI
            2 PLAC Apt 4B, New York, New York, USA
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert results == []

    def test_multiple_violations(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            1 BURI
            2 PLAC Putnam Cemetery, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 2
        cats = {r[3] for r in results}
        assert cats == {'addr', 'note'}

    def test_level1_plac_detected(self, tmp_path):
        """PLAC at level 1 (unusual but valid) should still be detected."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 PLAC 51 Main Street, London, England
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 1
        assert results[0][3] == 'addr'

    def test_level3_plac_detected(self, tmp_path):
        """PLAC at level 3 with a named-place keyword should still be detected."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PLAC Putnam Cemetery, London, England
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 1
        assert results[0][3] == 'note'

    def test_zip_code_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESI
            2 PLAC 02134, Boston, Suffolk, Massachusetts, USA
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 1
        assert results[0][3] == 'addr'

    def test_university_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 EDUC
            2 PLAC University of Oxford, Oxford, Oxfordshire, England
            0 TRLR
        """)
        results = scan_plac_address_parts(str(p))
        assert len(results) == 1
        assert results[0][3] == 'note'

    def test_fixture_file(self):
        """The bundled fixture has exactly the expected violations."""
        results = scan_plac_address_parts(str(FIXTURE))
        cats = [r[3] for r in results]
        # 51 Forest Ave → addr
        # Putnam Cemetery → note
        # St. Mary's Church → note  (St. prefix stripped before suffix check)
        # Apt 4B → ambiguous → NOT returned (excluded from scan)
        # 100 Old Post Road → addr
        assert cats.count('addr') == 2
        assert cats.count('note') == 2
        assert 'ambiguous' not in cats


# ---------------------------------------------------------------------------
# fix_plac_address_parts — fix tests
# ---------------------------------------------------------------------------

class TestFixPlacAddressParts:

    def test_street_address_moved_to_addr(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 1
        lines = p.read_text(encoding='utf-8').splitlines()
        assert any('PLAC Greenwich, Fairfield, Connecticut, USA' in l for l in lines)
        assert any('3 ADDR 51 Forest Ave' in l for l in lines)

    def test_cemetery_moved_to_note(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BURI
            2 PLAC Putnam Cemetery, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 1
        lines = p.read_text(encoding='utf-8').splitlines()
        assert any('PLAC Greenwich, Fairfield, Connecticut, USA' in l for l in lines)
        assert any('3 NOTE Putnam Cemetery' in l for l in lines)

    def test_existing_addr_prepended(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESI
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            3 ADDR Apt 4B
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 1
        text = p.read_text(encoding='utf-8')
        assert '3 ADDR 51 Forest Ave; Apt 4B' in text
        assert 'PLAC Greenwich, Fairfield, Connecticut, USA' in text

    def test_existing_note_prepended(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BURI
            2 PLAC Putnam Cemetery, Greenwich, Fairfield, Connecticut, USA
            3 NOTE Old section
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 1
        text = p.read_text(encoding='utf-8')
        assert '3 NOTE Putnam Cemetery; Old section' in text

    def test_different_child_tag_not_merged(self, tmp_path):
        """Next line is 3 DATE, not 3 ADDR — new ADDR inserted, DATE untouched."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            3 DATE 1900
            0 TRLR
        """)
        fix_plac_address_parts(str(p))
        lines = p.read_text(encoding='utf-8').splitlines()
        assert any('3 ADDR 51 Forest Ave' in l for l in lines)
        assert any('3 DATE 1900' in l for l in lines)

    def test_dry_run_does_not_modify_file(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        changed = fix_plac_address_parts(str(p), dry_run=True)
        assert changed == 1
        assert p.read_text(encoding='utf-8') == original

    def test_multiple_violations_all_fixed(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            1 BURI
            2 PLAC Putnam Cemetery, Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 2
        text = p.read_text(encoding='utf-8')
        assert '3 ADDR 51 Forest Ave' in text
        assert '3 NOTE Putnam Cemetery' in text

    def test_ambiguous_not_fixed(self, tmp_path):
        """Ambiguous first parts are never auto-fixed."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESI
            2 PLAC Apt 4B, New York, New York, USA
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        changed = fix_plac_address_parts(str(p))
        assert changed == 0
        assert p.read_text(encoding='utf-8') == original

    def test_title_prefix_church_not_addr(self, tmp_path):
        """'St. Mary's Church' must not be misclassified as an address."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BURI
            2 PLAC St. Mary's Church, London, England
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 1
        text = p.read_text(encoding='utf-8')
        assert '3 NOTE' in text
        assert '3 ADDR' not in text

    def test_clean_plac_no_change(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC Greenwich, Fairfield, Connecticut, USA
            0 TRLR
        """)
        changed = fix_plac_address_parts(str(p))
        assert changed == 0

    def test_level1_plac_gets_level2_child(self, tmp_path):
        """Level-1 PLAC → child tag at level 2."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 PLAC 51 Main Street, London, England
            0 TRLR
        """)
        fix_plac_address_parts(str(p))
        text = p.read_text(encoding='utf-8')
        assert '2 ADDR 51 Main Street' in text
        assert '1 PLAC London, England' in text

    def test_level2_plac_gets_level3_child(self, tmp_path):
        """Standard level-2 PLAC → child at level 3."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC 100 Oak Road, Bristol, Somerset, England
            0 TRLR
        """)
        fix_plac_address_parts(str(p))
        text = p.read_text(encoding='utf-8')
        assert '3 ADDR 100 Oak Road' in text

    def test_addr_inserted_immediately_after_plac(self, tmp_path):
        """The ADDR tag must appear on the line directly after PLAC."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 1900
            2 PLAC 51 Forest Ave, Greenwich, Fairfield, Connecticut, USA
            2 SOUR @S1@
            0 TRLR
        """)
        fix_plac_address_parts(str(p))
        lines = [l.rstrip() for l in p.read_text(encoding='utf-8').splitlines()]
        plac_idx = next(i for i, l in enumerate(lines) if 'PLAC Greenwich' in l)
        assert '3 ADDR 51 Forest Ave' in lines[plac_idx + 1]
