"""
Tests for extract_occupations.py

Covers:
  extract_occupation_from_note() — parses "Occupation: X" from a semicolon-separated note string
  extract_occupations()          — adds 1 OCCU events after events whose notes contain occupations
"""

import shutil
from pathlib import Path

import pytest

from extract_occupations import (
    IGNORED_OCCUPATIONS,
    extract_occupation_from_note,
    extract_occupations,
    purge_blocked_occupations,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'occupation_notes.ged'


@pytest.fixture()
def tmp_copy(tmp_path):
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


def content_of(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def lines_of(path: str) -> list[str]:
    with open(path, encoding='utf-8') as f:
        return [line.rstrip('\n') for line in f]


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

class TestExtractOccupationFromNote:

    def test_simple(self):
        assert extract_occupation_from_note('Occupation: Tailor') == 'Tailor'

    def test_trailing_field(self):
        assert extract_occupation_from_note(
            'Occupation: Police Constable; Marital Status: Married'
        ) == 'Police Constable'

    def test_leading_field(self):
        assert extract_occupation_from_note(
            'Marital Status: Married; Occupation: Mohair Merchant'
        ) == 'Mohair Merchant'

    def test_middle_field(self):
        assert extract_occupation_from_note(
            'A: X; Occupation: Grocer; B: Y'
        ) == 'Grocer'

    def test_strip_whitespace(self):
        assert extract_occupation_from_note('Occupation:  Tailor ') == 'Tailor'

    def test_no_occupation_returns_none(self):
        assert extract_occupation_from_note('Marital Status: Married') is None

    def test_empty_string_returns_none(self):
        assert extract_occupation_from_note('') is None

    def test_student_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Student') is None

    def test_scholar_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Scholar') is None

    def test_school_is_ignored(self):
        assert extract_occupation_from_note('Occupation: School') is None

    def test_home_duties_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Home Duties') is None

    def test_unpaid_domestic_duties_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Unpaid Domestic Duties') is None

    def test_private_means_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Private Means') is None

    def test_ignored_occupation_case_insensitive(self):
        assert extract_occupation_from_note('Occupation: STUDENT') is None
        assert extract_occupation_from_note('Occupation: home duties') is None

    def test_ignored_occupation_in_compound_note(self):
        assert extract_occupation_from_note(
            'Occupation: Student; Marital Status: Single'
        ) is None

    def test_none_is_ignored(self):
        assert extract_occupation_from_note('Occupation: None') is None

    def test_no_occupation_label_is_ignored(self):
        assert extract_occupation_from_note('Occupation: (No Occupation)') is None

    def test_keeping_house_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Keeping House') is None

    def test_house_wife_is_ignored(self):
        assert extract_occupation_from_note('Occupation: House Wife') is None

    def test_unpaid_domestic_duties_variant_is_ignored(self):
        assert extract_occupation_from_note('Occupation: Unpaid Domestic Duties (Retired)') is None

    def test_unpaid_domestic_duties_prefix_case_insensitive(self):
        assert extract_occupation_from_note('Occupation: unpaid domestic duties - other') is None

    def test_ignored_occupations_set_contains_expected_values(self):
        for val in ('student', 'scholar', 'school', 'home duties',
                    'unpaid domestic duties', 'private means', 'none',
                    '(no occupation)', 'keeping house', 'house wife'):
            assert val in IGNORED_OCCUPATIONS

    def test_french_student_ignored(self):
        # étudiante / étudiant — French for student
        assert extract_occupation_from_note('Occupation: étudiante') is None
        assert extract_occupation_from_note('Occupation: étudiant') is None

    def test_french_child_ignored(self):
        # enfant — French for child, not a meaningful occupation
        assert extract_occupation_from_note('Occupation: Enfant') is None
        assert extract_occupation_from_note('Occupation: enfant') is None


# ---------------------------------------------------------------------------
# Fixture sanity checks
# ---------------------------------------------------------------------------

class TestFixtureContents:

    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_fixture_has_occupation_note(self):
        assert 'Occupation:' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_simple_occupation(self):
        assert 'Occupation: Tailor' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_occupation_with_trailing_field(self):
        assert 'Occupation: Police Constable; Marital Status' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_occupation_after_leading_field(self):
        assert 'Marital Status: Married; Occupation: Mohair Merchant' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_event_without_occupation(self):
        """@I4@ has a NOTE with no occupation."""
        assert '@I4@ INDI' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_even_with_occupation(self):
        """@I5@ has an EVEN block with occupation note."""
        assert '@I5@ INDI' in FIXTURE.read_text(encoding='utf-8')
        assert 'Occupation: Director' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_existing_occu(self):
        """@I6@ already has a proper OCCU tag."""
        assert '1 OCCU Engineer' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_blocked_occupation(self):
        """@I7@ and @I8@ have notes with blocked occupations."""
        content = FIXTURE.read_text(encoding='utf-8')
        assert 'Occupation: Student' in content
        assert 'Occupation: Scholar' in content


# ---------------------------------------------------------------------------
# Extraction integration tests
# ---------------------------------------------------------------------------

class TestExtraction:

    def test_occu_added_for_simple_occupation(self, tmp_copy):
        extract_occupations(tmp_copy)
        assert '1 OCCU Tailor' in content_of(tmp_copy)

    def test_occu_added_for_leading_field(self, tmp_copy):
        extract_occupations(tmp_copy)
        assert '1 OCCU Mohair Merchant' in content_of(tmp_copy)

    def test_occu_added_for_trailing_field(self, tmp_copy):
        extract_occupations(tmp_copy)
        assert '1 OCCU Police Constable' in content_of(tmp_copy)

    def test_occu_added_for_even_event(self, tmp_copy):
        extract_occupations(tmp_copy)
        assert '1 OCCU Director' in content_of(tmp_copy)

    def test_occu_gets_date_from_parent_event(self, tmp_copy):
        extract_occupations(tmp_copy)
        lines = lines_of(tmp_copy)
        # @I2@ RESI has DATE 1921; the new OCCU Police Constable should have 2 DATE 1921
        for i, line in enumerate(lines):
            if line == '1 OCCU Police Constable':
                assert i + 1 < len(lines), 'No line after OCCU'
                assert lines[i + 1] == '2 DATE 1921'
                return
        pytest.fail('1 OCCU Police Constable not found')

    def test_occu_gets_date_from_even_event(self, tmp_copy):
        extract_occupations(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 OCCU Director':
                assert i + 1 < len(lines)
                assert lines[i + 1] == '2 DATE 15 Nov 1955'
                return
        pytest.fail('1 OCCU Director not found')

    def test_occu_without_date_when_event_has_no_date(self, tmp_copy):
        """@I1@ RESI has no DATE child; OCCU Tailor should appear with no DATE."""
        extract_occupations(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 OCCU Tailor':
                if i + 1 < len(lines):
                    assert not lines[i + 1].startswith('2 DATE')
                return
        pytest.fail('1 OCCU Tailor not found')

    def test_no_occu_when_no_occupation_in_note(self, tmp_copy):
        """@I4@ note has no occupation — no new OCCU should be added for that person."""
        extract_occupations(tmp_copy)
        lines = lines_of(tmp_copy)
        # Locate @I4@ record and check no OCCU between it and the next level-0
        in_i4 = False
        for line in lines:
            if line == '0 @I4@ INDI':
                in_i4 = True
            elif in_i4 and line.startswith('0 '):
                break
            elif in_i4 and line.startswith('1 OCCU'):
                pytest.fail('@I4@ should not have an OCCU event')

    def test_original_note_unchanged(self, tmp_copy):
        extract_occupations(tmp_copy)
        c = content_of(tmp_copy)
        assert '2 NOTE Occupation: Tailor' in c
        assert '2 NOTE Occupation: Police Constable; Marital Status: Married; Relation to Head of House: Head' in c
        assert '2 NOTE Marital Status: Married; Occupation: Mohair Merchant' in c

    def test_existing_occu_not_duplicated(self, tmp_copy):
        """@I6@ already has 1 OCCU Engineer; it should not be added again."""
        extract_occupations(tmp_copy)
        lines = lines_of(tmp_copy)
        count = sum(1 for l in lines if l == '1 OCCU Engineer')
        assert count == 1

    def test_blocked_occupation_not_added(self, tmp_copy):
        """@I7@ has Occupation: Student and @I8@ has Occupation: Scholar — both blocked."""
        extract_occupations(tmp_copy)
        c = content_of(tmp_copy)
        assert '1 OCCU Student' not in c
        assert '1 OCCU Scholar' not in c

    def test_occu_inserted_after_event_block_not_at_end(self, tmp_copy):
        """OCCU should appear right after the parent event, before the next level-1 sibling."""
        extract_occupations(tmp_copy)
        lines = lines_of(tmp_copy)
        # For @I2@: RESI block → 2 NOTE → then 1 OCCU → then 1 BIRT
        note_idx = next(
            i for i, l in enumerate(lines)
            if l == '2 NOTE Occupation: Police Constable; Marital Status: Married; Relation to Head of House: Head'
        )
        # The line after the note (and any other level-2+ children) should be the new OCCU
        assert lines[note_idx + 1] == '1 OCCU Police Constable'


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_stats_keys_present(self, tmp_copy):
        result = extract_occupations(tmp_copy)
        for key in ('lines_read', 'lines_delta', 'occu_added'):
            assert key in result, f'Missing key {key!r}'

    def test_occu_added_count(self, tmp_copy):
        result = extract_occupations(tmp_copy)
        # @I1@: Tailor, @I2@: Police Constable, @I3@: Mohair Merchant, @I5@: Director = 4
        assert result['occu_added'] == 4

    def test_lines_delta_positive(self, tmp_copy):
        result = extract_occupations(tmp_copy)
        assert result['lines_delta'] > 0

    def test_lines_delta_matches_actual_diff(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = extract_occupations(tmp_copy)
        with open(tmp_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_delta'] == after - before

    def test_lines_read_matches_file(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            file_len = sum(1 for _ in f)
        result = extract_occupations(tmp_copy)
        assert result['lines_read'] == file_len


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /Wonder/\n1 BIRT\n2 DATE 1 APR 1900\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = extract_occupations(str(clean))
        assert result['occu_added'] == 0
        assert clean.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        extract_occupations(tmp_copy, dry_run=True)
        assert Path(tmp_copy).read_text(encoding='utf-8') == original

    def test_dry_run_stats_match_real(self, tmp_copy):
        dry = extract_occupations(tmp_copy, dry_run=True)
        # tmp_copy is now modified by real run in a different tmp_path, so copy again
        import shutil, tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.ged', delete=False) as t:
            real_copy = t.name
        try:
            shutil.copy(tmp_copy, real_copy)
            real = extract_occupations(real_copy)
        finally:
            os.unlink(real_copy)
        assert dry['occu_added'] == real['occu_added']
        assert dry['lines_delta'] == real['lines_delta']

    def test_output_file_option(self, tmp_path):
        out = str(tmp_path / 'out.ged')
        extract_occupations(str(FIXTURE), path_out=out)
        c = Path(out).read_text(encoding='utf-8')
        assert '1 OCCU Tailor' in c
        assert '1 OCCU Police Constable' in c

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'out.ged')
        original = FIXTURE.read_text(encoding='utf-8')
        extract_occupations(str(FIXTURE), path_out=out)
        assert FIXTURE.read_text(encoding='utf-8') == original

    def test_trlr_preserved(self, tmp_copy):
        extract_occupations(tmp_copy)
        assert lines_of(tmp_copy)[-1] == '0 TRLR'


# ---------------------------------------------------------------------------
# Purge blocked occupations
# ---------------------------------------------------------------------------

_PURGE_GED = (
    '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
    '0 @I1@ INDI\n'
    '1 NAME Alice /Smith/\n'
    '1 RESI\n2 DATE 1921\n2 NOTE Occupation: Scholar\n'
    '1 OCCU Scholar\n2 DATE 1921\n'       # should be removed
    '1 RESI\n2 DATE 1939\n2 NOTE Occupation: Clerk\n'
    '1 OCCU Clerk\n2 DATE 1939\n'         # should be kept
    '0 @I2@ INDI\n'
    '1 NAME Bob /Jones/\n'
    '1 OCCU Home Duties\n2 DATE 1911\n'   # should be removed
    '1 OCCU Student\n'                    # should be removed (no DATE child)
    '1 OCCU Engineer\n'                   # should be kept
    '0 TRLR\n'
)


@pytest.fixture()
def purge_copy(tmp_path):
    dest = tmp_path / 'purge.ged'
    dest.write_text(_PURGE_GED, encoding='utf-8')
    return str(dest)


class TestPurge:

    def test_blocked_occu_removed(self, purge_copy):
        purge_blocked_occupations(purge_copy)
        c = content_of(purge_copy)
        assert '1 OCCU Scholar' not in c
        assert '1 OCCU Home Duties' not in c
        assert '1 OCCU Student' not in c

    def test_allowed_occu_preserved(self, purge_copy):
        purge_blocked_occupations(purge_copy)
        c = content_of(purge_copy)
        assert '1 OCCU Clerk' in c
        assert '1 OCCU Engineer' in c

    def test_date_child_of_blocked_occu_removed(self, purge_copy):
        purge_blocked_occupations(purge_copy)
        lines = lines_of(purge_copy)
        # The '2 DATE 1921' that belonged to OCCU Scholar should be gone;
        # the '2 DATE 1939' belonging to OCCU Clerk should remain.
        occu_clerk_idx = next(i for i, l in enumerate(lines) if l == '1 OCCU Clerk')
        assert lines[occu_clerk_idx + 1] == '2 DATE 1939'
        # Only one '2 DATE 1921' should exist (inside the RESI block, not the removed OCCU)
        date_1921_lines = [l for l in lines if l == '2 DATE 1921']
        assert len(date_1921_lines) == 1

    def test_note_lines_unchanged(self, purge_copy):
        purge_blocked_occupations(purge_copy)
        c = content_of(purge_copy)
        assert '2 NOTE Occupation: Scholar' in c
        assert '2 NOTE Occupation: Clerk' in c

    def test_stats_keys_present(self, purge_copy):
        result = purge_blocked_occupations(purge_copy)
        for key in ('lines_read', 'lines_delta', 'occu_removed'):
            assert key in result

    def test_occu_removed_count(self, purge_copy):
        result = purge_blocked_occupations(purge_copy)
        # Scholar, Home Duties, Student = 3
        assert result['occu_removed'] == 3

    def test_lines_delta_negative(self, purge_copy):
        result = purge_blocked_occupations(purge_copy)
        assert result['lines_delta'] < 0

    def test_lines_delta_matches_actual_diff(self, purge_copy):
        with open(purge_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = purge_blocked_occupations(purge_copy)
        with open(purge_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_delta'] == after - before

    def test_dry_run_no_write(self, purge_copy):
        original = Path(purge_copy).read_text(encoding='utf-8')
        purge_blocked_occupations(purge_copy, dry_run=True)
        assert Path(purge_copy).read_text(encoding='utf-8') == original

    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /Smith/\n1 OCCU Engineer\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = purge_blocked_occupations(str(clean))
        assert result['occu_removed'] == 0
        assert clean.read_text(encoding='utf-8') == original

    def test_trlr_preserved(self, purge_copy):
        purge_blocked_occupations(purge_copy)
        assert lines_of(purge_copy)[-1] == '0 TRLR'


# ---------------------------------------------------------------------------
# Idempotency: re-running must not create duplicate OCCU events
# ---------------------------------------------------------------------------

_IDEMPOTENT_GED = (
    '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
    '0 @I1@ INDI\n'
    '1 NAME John /Smith/\n'
    '1 CENS\n2 DATE 1911\n2 NOTE Occupation: Brass Polisher; Marital Status: Married\n'
    '1 CENS\n2 DATE 1921\n2 NOTE Occupation: Police Constable; Marital Status: Married\n'
    '0 TRLR\n'
)


@pytest.fixture()
def idempotent_copy(tmp_path):
    dest = tmp_path / 'idempotent.ged'
    dest.write_text(_IDEMPOTENT_GED, encoding='utf-8')
    return str(dest)


class TestIdempotency:

    def test_first_run_adds_occu(self, idempotent_copy):
        result = extract_occupations(idempotent_copy)
        assert result['occu_added'] == 2

    def test_second_run_adds_nothing(self, idempotent_copy):
        extract_occupations(idempotent_copy)
        result = extract_occupations(idempotent_copy)
        assert result['occu_added'] == 0

    def test_no_duplicate_occu_after_two_runs(self, idempotent_copy):
        extract_occupations(idempotent_copy)
        extract_occupations(idempotent_copy)
        lines = lines_of(idempotent_copy)
        brass_count = sum(1 for l in lines if l == '1 OCCU Brass Polisher')
        constable_count = sum(1 for l in lines if l == '1 OCCU Police Constable')
        assert brass_count == 1
        assert constable_count == 1

    def test_file_unchanged_on_second_run(self, idempotent_copy):
        extract_occupations(idempotent_copy)
        after_first = Path(idempotent_copy).read_text(encoding='utf-8')
        extract_occupations(idempotent_copy)
        after_second = Path(idempotent_copy).read_text(encoding='utf-8')
        assert after_first == after_second


# ---------------------------------------------------------------------------
# Citation copying: SOUR from parent event copied onto new OCCU
# ---------------------------------------------------------------------------

_CITATION_GED = (
    '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
    '0 @I1@ INDI\n'
    '1 NAME Alice /Brown/\n'
    '1 CENS\n'
    '2 DATE 1911\n'
    '2 PLAC London, England\n'
    '2 NOTE Occupation: Nurse; Marital Status: Single\n'
    '2 SOUR @S1@\n'
    '3 PAGE Census roll 42\n'
    '0 @S1@ SOUR\n'
    '1 TITL 1911 Census\n'
    '0 TRLR\n'
)

_NO_CITATION_GED = (
    '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
    '0 @I1@ INDI\n'
    '1 NAME Alice /Brown/\n'
    '1 CENS\n'
    '2 DATE 1911\n'
    '2 NOTE Occupation: Nurse; Marital Status: Single\n'
    '0 TRLR\n'
)


@pytest.fixture()
def citation_copy(tmp_path):
    dest = tmp_path / 'citation.ged'
    dest.write_text(_CITATION_GED, encoding='utf-8')
    return str(dest)


@pytest.fixture()
def no_citation_copy(tmp_path):
    dest = tmp_path / 'no_citation.ged'
    dest.write_text(_NO_CITATION_GED, encoding='utf-8')
    return str(dest)


class TestCitationCopying:

    def test_sour_copied_onto_occu(self, citation_copy):
        extract_occupations(citation_copy)
        lines = lines_of(citation_copy)
        occu_idx = next(i for i, l in enumerate(lines) if l == '1 OCCU Nurse')
        # DATE then SOUR should follow
        assert lines[occu_idx + 1] == '2 DATE 1911'
        assert lines[occu_idx + 2] == '2 SOUR @S1@'

    def test_sour_page_child_copied(self, citation_copy):
        extract_occupations(citation_copy)
        lines = lines_of(citation_copy)
        occu_idx = next(i for i, l in enumerate(lines) if l == '1 OCCU Nurse')
        assert lines[occu_idx + 3] == '3 PAGE Census roll 42'

    def test_no_sour_on_occu_when_event_has_none(self, no_citation_copy):
        extract_occupations(no_citation_copy)
        lines = lines_of(no_citation_copy)
        occu_idx = next(i for i, l in enumerate(lines) if l == '1 OCCU Nurse')
        # Only DATE should follow, no SOUR
        assert lines[occu_idx + 1] == '2 DATE 1911'
        assert not any(l.startswith('2 SOUR') for l in lines[occu_idx:occu_idx + 3])

    def test_original_event_sour_still_present(self, citation_copy):
        extract_occupations(citation_copy)
        lines = lines_of(citation_copy)
        cens_idx = next(i for i, l in enumerate(lines) if l == '1 CENS')
        # The original SOUR must still be inside the CENS block
        assert any(l == '2 SOUR @S1@' for l in lines[cens_idx:cens_idx + 6])
