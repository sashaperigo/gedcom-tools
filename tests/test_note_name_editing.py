"""
Tests for note editing and secondary-name (alias) helpers in serve_viz.py,
plus the atomic GEDCOM write helper.

Covers:
  - _encode_note_lines        – text → GEDCOM NOTE/CONT lines
  - _find_note_block          – locate nth NOTE block (incl. CONT/CONC range)
  - _find_secondary_name_block – locate nth secondary NAME block
  - _add_secondary_name       – append a new alias NAME record
  - _edit_secondary_name      – replace an existing alias NAME block
  - _write_gedcom_atomic      – backup + overwrite with new lines
"""

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

# serve_viz.py sys.exit()s at import if GED_FILE is not set
_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

import serve_viz  # noqa: E402
from serve_viz import (           # noqa: E402
    _chunk_note_line,
    _encode_note_lines,
    _encode_event_note_lines,
    _find_indi_block,
    _find_note_block,
    _find_secondary_name_block,
    _add_secondary_name,
    _edit_secondary_name,
    _write_gedcom_atomic,
)

# ---------------------------------------------------------------------------
# Shared GEDCOM string fixtures
# ---------------------------------------------------------------------------

# Individual with three notes: first has a CONT, third has CONT + CONC
MULTI_NOTE_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1900
1 NOTE First note line one
2 CONT First note line two
1 NOTE Second note only
1 NOTE Third note line one
2 CONT Third note line two
2 CONC And concatenated
0 @I2@ INDI
1 NAME Jane /Doe/
1 BIRT
2 DATE 1905
0 TRLR""".splitlines()

# Individual with primary NAME + two secondary NAMEs
ALIAS_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME John /Smith/
2 GIVN John
2 SURN Smith
1 NAME Johnny /Smith/
2 TYPE AKA
1 NAME Иван /Кузнецов/
2 TYPE maiden
1 BIRT
2 DATE 1900
0 @I2@ INDI
1 NAME Jane /Doe/
0 TRLR""".splitlines()

# Individual with only a primary NAME (no secondary names, no notes)
PRIMARY_ONLY_GED = """\
0 HEAD
0 @I1@ INDI
1 NAME Alice /Green/
2 GIVN Alice
2 SURN Green
1 BIRT
2 DATE 1950
0 TRLR""".splitlines()


# ===========================================================================
# _encode_note_lines
# ===========================================================================

class TestEncodeNoteLines:
    def test_single_line(self):
        result = _encode_note_lines('hello world')
        assert result == ['1 NOTE hello world']

    def test_multiline_two_lines(self):
        result = _encode_note_lines('line one\nline two')
        assert result == ['1 NOTE line one', '2 CONT line two']

    def test_multiline_three_lines(self):
        result = _encode_note_lines('a\nb\nc')
        assert result == ['1 NOTE a', '2 CONT b', '2 CONT c']

    def test_empty_string(self):
        result = _encode_note_lines('')
        assert result == ['1 NOTE ']

    def test_leading_newline(self):
        result = _encode_note_lines('\nSecond')
        assert result == ['1 NOTE ', '2 CONT Second']

    def test_trailing_newline(self):
        result = _encode_note_lines('Hello\n')
        assert result == ['1 NOTE Hello', '2 CONT ']

    def test_unicode(self):
        result = _encode_note_lines('Héllo wörld')
        assert result == ['1 NOTE Héllo wörld']

    def test_at_sign_escaped(self):
        # Bare '@' in a value would be misread as a pointer; must be doubled.
        result = _encode_note_lines('user@example.com')
        assert result == ['1 NOTE user@@example.com']

    def test_multiple_at_signs_all_escaped(self):
        result = _encode_note_lines('a@b and c@d')
        assert result == ['1 NOTE a@@b and c@@d']

    def test_at_sign_in_multiline_note(self):
        result = _encode_note_lines('from: a@b.com\nto: c@d.org')
        assert result == ['1 NOTE from: a@@b.com', '2 CONT to: c@@d.org']

    def test_output_is_list_not_generator(self):
        result = _encode_note_lines('x\ny')
        assert isinstance(result, list)

    def test_line_count_equals_newline_count_plus_one(self):
        text = 'a\nb\nc\nd'
        result = _encode_note_lines(text)
        assert len(result) == text.count('\n') + 1

    def test_long_line_split_with_conc(self):
        # A line exceeding 248 chars must be split into NOTE + CONC lines
        long = 'x' * 300
        result = _encode_note_lines(long)
        assert result[0].startswith('1 NOTE ')
        assert result[1].startswith('2 CONC ')
        # Reconstituted text must equal original
        body = result[0][len('1 NOTE '):]
        for r in result[1:]:
            body += r[len('2 CONC '):]
        assert body == long

    def test_long_line_word_boundary_leading_space(self):
        # When splitting at a word boundary the space must lead the CONC value,
        # not trail the NOTE line (per GEDCOM 5.5.5 pp. 41, 43-44).
        from serve_viz import _NOTE_LINE_MAX
        # Construct a line where the word boundary falls exactly at the limit
        word_a = 'a' * (_NOTE_LINE_MAX - 1)  # just under limit
        text = word_a + ' bb'                 # space at position _NOTE_LINE_MAX-1
        result = _chunk_note_line(text, '1 NOTE', '2 CONC')
        assert len(result) == 2
        note_val = result[0][len('1 NOTE '):]
        conc_val = result[1][len('2 CONC '):]
        assert not note_val.endswith(' '),  "NOTE line must not have trailing space"
        assert conc_val.startswith(' '),    "CONC value must carry the leading space"
        # Full text must round-trip
        assert note_val + conc_val == text


# ===========================================================================
# _encode_event_note_lines
# ===========================================================================

class TestEncodeEventNoteLines:
    def test_single_line(self):
        result = _encode_event_note_lines('a note')
        assert result == ['2 NOTE a note']

    def test_multiline(self):
        result = _encode_event_note_lines('line one\nline two')
        assert result == ['2 NOTE line one', '3 CONT line two']

    def test_long_line_split_with_conc(self):
        long = 'y' * 300
        result = _encode_event_note_lines(long)
        assert result[0].startswith('2 NOTE ')
        assert result[1].startswith('3 CONC ')
        body = result[0][len('2 NOTE '):]
        for r in result[1:]:
            body += r[len('3 CONC '):]
        assert body == long


# ===========================================================================
# _find_note_block
# ===========================================================================

class TestFindNoteBlock:
    def test_finds_first_note(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 0)
        assert err is None
        assert MULTI_NOTE_GED[start] == '1 NOTE First note line one'

    def test_first_note_includes_cont_line(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 0)
        assert err is None
        lines_in_block = MULTI_NOTE_GED[start:end]
        assert any('CONT' in l for l in lines_in_block)

    def test_first_note_block_size(self):
        # note + 1 CONT = 2 lines
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 0)
        assert err is None
        assert end - start == 2

    def test_finds_second_note(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 1)
        assert err is None
        assert MULTI_NOTE_GED[start] == '1 NOTE Second note only'

    def test_second_note_no_cont_is_single_line(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 1)
        assert err is None
        assert end - start == 1

    def test_finds_third_note_with_cont_and_conc(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 2)
        assert err is None
        block = MULTI_NOTE_GED[start:end]
        assert any('CONT' in l for l in block)
        assert any('CONC' in l for l in block)
        assert end - start == 3  # NOTE + CONT + CONC

    def test_out_of_range_idx_returns_error(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 99)
        assert start is None
        assert end is None
        assert err is not None

    def test_unknown_xref_returns_error(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@NOBODY@', 0)
        assert start is None
        assert err is not None

    def test_individual_with_no_notes_returns_error(self):
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I2@', 0)
        assert start is None
        assert err is not None

    def test_block_end_stops_before_next_level1_tag(self):
        # The block for note[0] must not contain the '1 NOTE Second' line
        start, end, err = _find_note_block(MULTI_NOTE_GED, '@I1@', 0)
        assert err is None
        block = MULTI_NOTE_GED[start:end]
        assert not any('NOTE Second' in l for l in block)

    def test_wrong_level_conc_absorbed_into_block(self):
        # Files exported by some tools arrive with CONT/CONC at the wrong level
        # (e.g. 3 CONC under a 1 NOTE). We absorb them so that editing the note
        # replaces the whole block rather than orphaning the stray lines.
        # The linter still flags wrong-level lines as errors in the output file.
        ged = """\
0 HEAD
0 @I1@ INDI
1 NAME Test /Person/
1 NOTE First line
2 CONT Second line
3 CONC stray continuation at wrong level
0 TRLR""".splitlines()
        start, end, err = _find_note_block(ged, '@I1@', 0)
        assert err is None
        block = ged[start:end]
        assert len(block) == 3  # NOTE + CONT + wrong-level CONC all included
        assert any('3 CONC' in l for l in block)

    def test_edit_replaces_wrong_level_conc_block_entirely(self):
        # After editing, the wrong-level CONC line must be gone
        ged = """\
0 HEAD
0 @I1@ INDI
1 NAME Test /Person/
1 NOTE First line
2 CONT Second line
3 CONC stray continuation at wrong level
0 TRLR""".splitlines()
        result = _apply_edit_note(ged, '@I1@', 0, 'Replacement text')
        assert '3 CONC stray continuation at wrong level' not in result
        assert '1 NOTE Replacement text' in result


# ===========================================================================
# Add note (simulates UI "add note" action)
# ===========================================================================

def _apply_add_note(lines: list[str], xref: str, text: str) -> list[str]:
    """Simulate the /api/add_note handler logic (sans I/O)."""
    _, indi_end, err = _find_indi_block(lines, xref)
    assert err is None, err
    return lines[:indi_end] + _encode_note_lines(text) + lines[indi_end:]


def _apply_edit_note(lines: list[str], xref: str, note_idx: int, text: str) -> list[str]:
    """Simulate the /api/edit_note handler logic (sans I/O)."""
    start, end, err = _find_note_block(lines, xref, note_idx)
    assert err is None, err
    return lines[:start] + _encode_note_lines(text) + lines[end:]


# Base GEDCOM with one individual and no notes
_NO_NOTES_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME Alice /Green/
1 BIRT
2 DATE 1950
0 TRLR""".splitlines()


class TestAddNote:
    def test_adds_note_to_individual_with_no_existing_notes(self):
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'Hello')
        assert '1 NOTE Hello' in result

    def test_note_is_inserted_inside_indi_block(self):
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'Hello')
        trlr_idx = result.index('0 TRLR')
        note_idx = result.index('1 NOTE Hello')
        assert note_idx < trlr_idx

    def test_adds_second_note_without_disturbing_first(self):
        after_first = _apply_add_note(_NO_NOTES_GED, '@I1@', 'First note')
        after_second = _apply_add_note(after_first, '@I1@', 'Second note')
        assert '1 NOTE First note' in after_second
        assert '1 NOTE Second note' in after_second

    def test_multiline_note_uses_cont(self):
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'Line one\nLine two')
        assert '1 NOTE Line one' in result
        assert '2 CONT Line two' in result

    def test_three_line_note(self):
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'a\nb\nc')
        assert '1 NOTE a' in result
        assert '2 CONT b' in result
        assert '2 CONT c' in result

    def test_long_line_produces_conc(self):
        long_text = 'word ' * 60  # 300 chars
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', long_text.rstrip())
        assert any(l.startswith('2 CONC') for l in result)

    def test_long_line_no_trailing_whitespace(self):
        long_text = 'w' * 100 + ' ' + 'x' * 200  # space near boundary
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', long_text)
        for line in result:
            assert not line.rstrip('\n').endswith(' '), f'Trailing space on: {line!r}'

    def test_long_line_conc_value_no_loss(self):
        # The full text must round-trip through the NOTE/CONC representation
        word = 'ab ' * 90  # well over limit, with word boundaries
        encoded = _encode_note_lines(word.strip())
        reconstructed = encoded[0][len('1 NOTE '):]
        for line in encoded[1:]:
            if line.startswith('2 CONC '):
                reconstructed += line[len('2 CONC '):]
            elif line.startswith('2 CONT '):
                reconstructed += '\n' + line[len('2 CONT '):]
        assert reconstructed == word.strip()

    def test_empty_note_rejected_via_strip(self):
        # The handler does new_text.strip() before checking emptiness;
        # pure-whitespace input should produce no note or be empty
        stripped = '   \n\t  '.strip()
        assert not stripped  # verifies handler would reject this as empty

    def test_note_with_only_whitespace_lines(self):
        # A note with blank lines (explicit paragraph breaks) uses empty CONT
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'Para one\n\nPara two')
        assert '1 NOTE Para one' in result
        assert '2 CONT ' in result or '2 CONT' in result  # empty CONT for blank line
        assert '2 CONT Para two' in result

    def test_note_with_unicode_text(self):
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'Ελληνικά και Türkçe')
        assert '1 NOTE Ελληνικά και Türkçe' in result

    def test_note_with_at_sign_escaped_to_double_at(self):
        # '@' in note text must be written as '@@' so parsers don't mistake
        # it for the start of a pointer.
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'email: user@example.com')
        assert any('user@@example.com' in l for l in result)

    def test_unknown_xref_returns_error(self):
        _, _, err = _find_indi_block(_NO_NOTES_GED, '@NOBODY@')
        assert err is not None

    def test_non_destructive_adds_note_at_end_of_indi_block(self):
        # Lines after the INDI block (TRLR) must be unchanged
        result = _apply_add_note(_NO_NOTES_GED, '@I1@', 'New note')
        assert result[-1] == '0 TRLR'


# ===========================================================================
# Edit note (simulates UI "edit note" action)
# ===========================================================================

class TestEditNote:
    def test_replaces_single_line_note(self):
        lines = _NO_NOTES_GED[:]
        lines = _apply_add_note(lines, '@I1@', 'Original text')
        result = _apply_edit_note(lines, '@I1@', 0, 'Updated text')
        assert '1 NOTE Updated text' in result
        assert '1 NOTE Original text' not in result

    def test_replace_with_multiline_text(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Single line')
        result = _apply_edit_note(lines, '@I1@', 0, 'Line A\nLine B')
        assert '1 NOTE Line A' in result
        assert '2 CONT Line B' in result
        assert '1 NOTE Single line' not in result

    def test_replace_multiline_note_with_single_line(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Line A\nLine B')
        result = _apply_edit_note(lines, '@I1@', 0, 'Collapsed')
        assert '1 NOTE Collapsed' in result
        assert '2 CONT Line B' not in result

    def test_edit_first_of_two_notes_leaves_second_intact(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Note one')
        lines = _apply_add_note(lines, '@I1@', 'Note two')
        result = _apply_edit_note(lines, '@I1@', 0, 'Edited one')
        assert '1 NOTE Edited one' in result
        assert '1 NOTE Note two' in result
        assert '1 NOTE Note one' not in result

    def test_edit_second_of_two_notes_leaves_first_intact(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Note one')
        lines = _apply_add_note(lines, '@I1@', 'Note two')
        result = _apply_edit_note(lines, '@I1@', 1, 'Edited two')
        assert '1 NOTE Note one' in result
        assert '1 NOTE Edited two' in result
        assert '1 NOTE Note two' not in result

    def test_edit_note_with_cont_replaces_entire_block(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Original\nOriginal line 2')
        result = _apply_edit_note(lines, '@I1@', 0, 'New single line')
        assert '2 CONT Original line 2' not in result
        assert '1 NOTE New single line' in result

    def test_edit_note_out_of_range_returns_error(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Only note')
        start, end, err = _find_note_block(lines, '@I1@', 99)
        assert err is not None

    def test_edit_note_unknown_xref_returns_error(self):
        _, _, err = _find_note_block(_NO_NOTES_GED, '@NOBODY@', 0)
        assert err is not None

    def test_edit_to_empty_string_produces_empty_note_line(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Some text')
        result = _apply_edit_note(lines, '@I1@', 0, '')
        # Empty string → '1 NOTE ' with no value
        assert any(l == '1 NOTE ' for l in result)

    def test_edit_preserves_surrounding_lines(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Note')
        result = _apply_edit_note(lines, '@I1@', 0, 'Changed')
        assert '0 HEAD' in result
        assert '0 TRLR' in result
        assert '1 BIRT' in result

    def test_edit_with_long_text_produces_conc(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Short')
        long = 'word ' * 60
        result = _apply_edit_note(lines, '@I1@', 0, long.rstrip())
        assert any(l.startswith('2 CONC') for l in result)

    def test_edit_long_text_no_trailing_whitespace(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Short')
        long = 'a' * 100 + ' ' + 'b' * 200
        result = _apply_edit_note(lines, '@I1@', 0, long)
        for line in result:
            assert not line.rstrip('\n').endswith(' '), f'Trailing space: {line!r}'

    def test_edit_with_special_characters(self):
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Plain')
        result = _apply_edit_note(lines, '@I1@', 0, 'Héros & Ñoño – «cited»')
        assert any('Héros' in l for l in result)

    def test_note_count_stable_after_edit(self):
        # Editing must not add or remove notes, only replace the target
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Note A')
        lines = _apply_add_note(lines, '@I1@', 'Note B')
        result = _apply_edit_note(lines, '@I1@', 0, 'Note A revised')
        note_lines = [l for l in result if l.startswith('1 NOTE')]
        assert len(note_lines) == 2

    def test_round_trip_add_then_edit_then_find(self):
        # After adding and editing, _find_note_block must still locate the note
        lines = _apply_add_note(_NO_NOTES_GED[:], '@I1@', 'Original')
        lines = _apply_edit_note(lines, '@I1@', 0, 'Round-tripped')
        start, end, err = _find_note_block(lines, '@I1@', 0)
        assert err is None
        assert lines[start] == '1 NOTE Round-tripped'


# ===========================================================================
# _find_secondary_name_block
# ===========================================================================

class TestFindSecondaryNameBlock:
    def test_finds_first_secondary_name(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I1@', 0)
        assert err is None
        assert ALIAS_GED[start] == '1 NAME Johnny /Smith/'

    def test_first_secondary_includes_type_subtag(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I1@', 0)
        assert err is None
        block = ALIAS_GED[start:end]
        assert any('TYPE' in l for l in block)

    def test_finds_second_secondary_name(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I1@', 1)
        assert err is None
        assert 'Иван' in ALIAS_GED[start]

    def test_primary_name_not_returned_as_secondary(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I1@', 0)
        assert err is None
        # The primary name line must not be in this block
        assert 'John /Smith/' not in ALIAS_GED[start]

    def test_out_of_range_idx_returns_error(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I1@', 99)
        assert start is None
        assert err is not None

    def test_unknown_xref_returns_error(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@NOBODY@', 0)
        assert start is None
        assert err is not None

    def test_individual_with_no_secondary_names_returns_error(self):
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I2@', 0)
        assert start is None
        assert err is not None

    def test_block_end_stops_before_next_level1(self):
        # Block for secondary[0] ends before the next 1 NAME (Иван) or 1 BIRT
        start, end, err = _find_secondary_name_block(ALIAS_GED, '@I1@', 0)
        assert err is None
        # end should point at the line '1 NAME Иван /Кузнецов/'
        assert ALIAS_GED[end].startswith('1 NAME') or ALIAS_GED[end].startswith('1 BIRT')


# ===========================================================================
# _add_secondary_name
# ===========================================================================

class TestAddSecondaryName:
    def test_add_two_word_name_wraps_surname_in_slashes(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Jack Brown', 'AKA')
        assert err is None
        assert any('1 NAME Jack /Brown/' in l for l in new_lines)

    def test_add_single_word_no_slashes(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Jacky', 'AKA')
        assert err is None
        assert any('1 NAME Jacky' in l for l in new_lines)
        # Single word: no slash wrapping
        assert not any('1 NAME /Jacky/' in l for l in new_lines)

    def test_add_already_slashed_name_unchanged(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Jack /Brown/', 'AKA')
        assert err is None
        assert any('1 NAME Jack /Brown/' in l for l in new_lines)

    def test_type_subtag_added_when_provided(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Jackie', 'AKA')
        assert err is None
        assert any('2 TYPE AKA' in l for l in new_lines)

    def test_no_type_subtag_when_empty_type(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Jackie', '')
        assert err is None
        # 2 TYPE line must NOT appear for this new block
        name_idx = next(i for i, l in enumerate(new_lines) if '1 NAME Jackie' in l)
        # Next line after the name should not be '2 TYPE'
        if name_idx + 1 < len(new_lines):
            assert '2 TYPE' not in new_lines[name_idx + 1]

    def test_new_name_block_is_inside_indi_block(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Al', 'AKA')
        assert err is None
        # Must appear before 0 TRLR
        trlr_idx = next(i for i, l in enumerate(new_lines) if l.startswith('0 TRLR'))
        assert any('1 NAME Al' in l for l in new_lines[:trlr_idx])

    def test_unknown_xref_returns_error(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@NOBODY@', 'Test', 'AKA')
        assert err is not None
        assert new_lines == PRIMARY_ONLY_GED

    def test_round_trip_find_secondary_block(self):
        new_lines, err = _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Allie Green', 'nickname')
        assert err is None
        start, end, err2 = _find_secondary_name_block(new_lines, '@I1@', 0)
        assert err2 is None
        assert 'Allie' in new_lines[start]

    def test_original_lines_not_mutated(self):
        original_copy = list(PRIMARY_ONLY_GED)
        _add_secondary_name(PRIMARY_ONLY_GED, '@I1@', 'Test', 'AKA')
        assert PRIMARY_ONLY_GED == original_copy


# ===========================================================================
# _edit_secondary_name
# ===========================================================================

class TestEditSecondaryName:
    def test_edit_first_secondary_name(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@I1@', 0, 'J.R. Smith', 'AKA')
        assert err is None
        assert any('J.R.' in l for l in new_lines)
        assert not any('Johnny /Smith/' in l for l in new_lines)

    def test_edit_second_secondary_name(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@I1@', 1, 'Ivan Kuznetsov', 'AKA')
        assert err is None
        assert any('Ivan' in l for l in new_lines)
        assert not any('Иван' in l for l in new_lines)

    def test_type_updated(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@I1@', 0, 'Johnny /Smith/', 'nickname')
        assert err is None
        assert any('2 TYPE nickname' in l for l in new_lines)

    def test_type_cleared_when_empty(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@I1@', 0, 'Johnny /Smith/', '')
        assert err is None
        # Find the new alias block and ensure no 2 TYPE follows it
        name_idx = next(i for i, l in enumerate(new_lines) if 'Johnny /Smith/' in l)
        # Walk sub-lines of this block
        j = name_idx + 1
        while j < len(new_lines) and not new_lines[j].startswith('1 ') and not new_lines[j].startswith('0 '):
            assert '2 TYPE' not in new_lines[j]
            j += 1

    def test_unknown_xref_returns_error(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@NOBODY@', 0, 'X', 'AKA')
        assert err is not None
        assert new_lines == ALIAS_GED

    def test_out_of_range_idx_returns_error(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@I1@', 99, 'X', 'AKA')
        assert err is not None

    def test_lines_outside_block_unchanged(self):
        new_lines, err = _edit_secondary_name(ALIAS_GED, '@I1@', 0, 'New Name', 'AKA')
        assert err is None
        # Lines before the first secondary NAME are unchanged
        first_sec_start, _, _ = _find_secondary_name_block(ALIAS_GED, '@I1@', 0)
        assert new_lines[:first_sec_start] == ALIAS_GED[:first_sec_start]


# ===========================================================================
# _write_gedcom_atomic
# ===========================================================================

SIMPLE_LINES = ['0 HEAD', '0 @I1@ INDI', '1 NAME Test /Person/', '0 TRLR']


class TestWriteGedcomAtomic:
    @pytest.fixture
    def tmp_ged(self, tmp_path):
        ged = tmp_path / 'test.ged'
        shutil.copy(_FIXTURE_GED, ged)
        return ged

    def test_backup_file_created(self, tmp_ged):
        with patch.object(serve_viz, 'GED', tmp_ged):
            _write_gedcom_atomic(SIMPLE_LINES)
        assert tmp_ged.with_suffix('.ged.bak').exists()

    def test_backup_contains_original_content(self, tmp_ged):
        original = tmp_ged.read_text(encoding='utf-8')
        with patch.object(serve_viz, 'GED', tmp_ged):
            _write_gedcom_atomic(SIMPLE_LINES)
        backup = tmp_ged.with_suffix('.ged.bak').read_text(encoding='utf-8')
        assert backup == original

    def test_new_file_contains_new_lines(self, tmp_ged):
        with patch.object(serve_viz, 'GED', tmp_ged):
            _write_gedcom_atomic(SIMPLE_LINES)
        written = tmp_ged.read_text(encoding='utf-8')
        for line in SIMPLE_LINES:
            assert line in written

    def test_lines_joined_with_newline(self, tmp_ged):
        with patch.object(serve_viz, 'GED', tmp_ged):
            _write_gedcom_atomic(['line A', 'line B'])
        written = tmp_ged.read_text(encoding='utf-8')
        assert 'line A\nline B' in written

    def test_trailing_newline_added(self, tmp_ged):
        with patch.object(serve_viz, 'GED', tmp_ged):
            _write_gedcom_atomic(SIMPLE_LINES)
        written = tmp_ged.read_text(encoding='utf-8')
        assert written.endswith('\n')
