"""
Tests for convert_events_to_facts.py

Conversions:
  EVEN TYPE Languages         → FACT TYPE Languages
  EVEN TYPE Literacy          → FACT TYPE Literacy
  EVEN TYPE Politics          → FACT TYPE Politics
  EVEN TYPE Medical condition → FACT TYPE Medical condition
  EVEN TYPE Physical Description → DSCR <note_value>
  EVEN TYPE Children          → NCHI <count>
"""

import textwrap

import pytest

from convert_events_to_facts import convert_lines


def ged(text):
    """Strip leading indent and split into lines with newlines."""
    return [l + '\n' for l in textwrap.dedent(text).strip().splitlines()]


def out(lines):
    return ''.join(lines)


# ---------------------------------------------------------------------------
# FACT swaps
# ---------------------------------------------------------------------------

class TestFactSwaps:
    """EVEN → FACT: tag changes, all sub-tags preserved."""

    @pytest.mark.parametrize('type_val', [
        'Languages', 'Literacy', 'Politics', 'Medical condition',
    ])
    def test_even_swapped_to_fact(self, type_val):
        lines = ged(f"""
            0 @I1@ INDI
            1 EVEN
            2 TYPE {type_val}
            2 NOTE Some value
            0 TRLR
        """)
        result = out(convert_lines(lines))
        assert '1 FACT\n' in result
        assert '1 EVEN\n' not in result

    def test_type_and_note_preserved(self):
        lines = ged("""
            1 EVEN
            2 TYPE Literacy
            2 SOUR @S1@
            3 PAGE p. 5
            2 NOTE Illiterate
        """)
        result = out(convert_lines(lines))
        assert '2 TYPE Literacy\n' in result
        assert '2 NOTE Illiterate\n' in result
        assert '2 SOUR @S1@\n' in result
        assert '3 PAGE p. 5\n' in result

    def test_unrelated_even_untouched(self):
        """EVEN with a different TYPE must not be modified."""
        lines = ged("""
            1 EVEN
            2 TYPE Arrival
            2 DATE 1920
            2 PLAC New York, USA
        """)
        result = out(convert_lines(lines))
        assert '1 EVEN\n' in result
        assert '1 FACT\n' not in result

    def test_surrounding_records_untouched(self):
        lines = ged("""
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 EVEN
            2 TYPE Languages
            2 NOTE English, Greek
            1 DEAT
            2 DATE 2000
            0 TRLR
        """)
        result = out(convert_lines(lines))
        assert '1 BIRT\n' in result
        assert '1 DEAT\n' in result
        assert '1 FACT\n' in result
        assert '1 EVEN\n' not in result


# ---------------------------------------------------------------------------
# Physical Description → DSCR
# ---------------------------------------------------------------------------

class TestPhysicalDescriptionToDscr:

    def test_tag_becomes_dscr(self):
        lines = ged("""
            1 EVEN
            2 TYPE Physical Description
            2 NOTE Height: 5'4"; Eyes: Brown
        """)
        result = out(convert_lines(lines))
        assert "1 DSCR Height: 5'4\"; Eyes: Brown\n" in result
        assert '1 EVEN\n' not in result

    def test_type_line_dropped(self):
        lines = ged("""
            1 EVEN
            2 TYPE Physical Description
            2 NOTE Height: 5'6"
        """)
        result = out(convert_lines(lines))
        assert '2 TYPE Physical Description\n' not in result

    def test_note_line_dropped(self):
        """NOTE value moves to DSCR line; the 2 NOTE line itself is removed."""
        lines = ged("""
            1 EVEN
            2 TYPE Physical Description
            2 NOTE Height: 5'6"
        """)
        result = out(convert_lines(lines))
        assert '2 NOTE' not in result

    def test_sources_preserved(self):
        lines = ged("""
            1 EVEN
            2 TYPE Physical Description
            2 NOTE Height: 5'4"
            2 SOUR @S1@
            3 PAGE p. 10
        """)
        result = out(convert_lines(lines))
        assert '2 SOUR @S1@\n' in result
        assert '3 PAGE p. 10\n' in result

    def test_no_note_produces_bare_dscr(self):
        """If somehow no NOTE exists, DSCR line is bare (edge case)."""
        lines = ged("""
            1 EVEN
            2 TYPE Physical Description
            2 SOUR @S1@
        """)
        result = out(convert_lines(lines))
        assert '1 DSCR\n' in result


# ---------------------------------------------------------------------------
# Children → NCHI
# ---------------------------------------------------------------------------

class TestChildrenToNchi:

    def test_tag_becomes_nchi(self):
        lines = ged("""
            1 EVEN
            2 TYPE Children
            2 NOTE 5 children
        """)
        result = out(convert_lines(lines))
        assert '1 NCHI 5\n' in result
        assert '1 EVEN\n' not in result

    def test_type_line_dropped(self):
        lines = ged("""
            1 EVEN
            2 TYPE Children
            2 NOTE 5 children
        """)
        result = out(convert_lines(lines))
        assert '2 TYPE Children\n' not in result

    def test_plac_preserved(self):
        lines = ged("""
            1 EVEN
            2 TYPE Children
            2 PLAC Bornova, Izmir, Turkey
            2 NOTE 5 children
        """)
        result = out(convert_lines(lines))
        assert '2 PLAC Bornova, Izmir, Turkey\n' in result

    def test_note_preserved(self):
        lines = ged("""
            1 EVEN
            2 TYPE Children
            2 NOTE 5 children
        """)
        result = out(convert_lines(lines))
        assert '2 NOTE 5 children\n' in result

    def test_non_numeric_note_produces_bare_nchi(self):
        lines = ged("""
            1 EVEN
            2 TYPE Children
            2 NOTE Several children
        """)
        result = out(convert_lines(lines))
        assert '1 NCHI\n' in result


# ---------------------------------------------------------------------------
# Change counting
# ---------------------------------------------------------------------------

class TestChangeCounting:

    def test_returns_change_summary(self):
        lines = ged("""
            1 EVEN
            2 TYPE Languages
            2 NOTE English
            1 EVEN
            2 TYPE Literacy
            2 NOTE Literate
        """)
        _, changes = convert_lines(lines, return_changes=True)
        assert len(changes) == 2

    def test_no_changes_when_nothing_matches(self):
        lines = ged("""
            1 EVEN
            2 TYPE Arrival
            2 DATE 1920
        """)
        _, changes = convert_lines(lines, return_changes=True)
        assert changes == []
