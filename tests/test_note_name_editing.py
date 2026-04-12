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
    _encode_note_lines,
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

    def test_output_is_list_not_generator(self):
        result = _encode_note_lines('x\ny')
        assert isinstance(result, list)

    def test_line_count_equals_newline_count_plus_one(self):
        text = 'a\nb\nc\nd'
        result = _encode_note_lines(text)
        assert len(result) == text.count('\n') + 1


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
