"""
Tests for purge_duplicate_events.py

Uses tests/fixtures/duplicate_events.ged — a synthetic GEDCOM covering:

  @I1@  Same date+place, different sources (S1, S2)    → merge; both sources kept
  @I2@  Different dates, same place                    → not a dup; both kept
  @I3@  Same date, first has place, second doesn't     → not a dup; both kept
  @I4@  Two bare BIRT blocks (no date, no place)       → merge; one removed
  @I5@  Same date+place on BIRT and DEAT               → not a dup (diff types)
  @I6@  Three BIRTs: pair match + one differs          → merge pair; unique kept
  @I7@  Same date+place, same source in both           → merge; source not duplicated
  @I8@  Same date+place; keeper has source, dup doesn't → merge; source preserved
  @I9@  Same date+place; keeper bare, dup has source   → merge; source migrated
  @I10@ Same date+place on DEAT, different sources     → merge; both DEAT sources kept
  @I11@ Single BIRT, no duplicates                     → unchanged
"""

import re
import shutil
from pathlib import Path

import pytest

from purge_duplicate_events import purge_duplicate_events

FIXTURE = Path(__file__).parent / 'fixtures' / 'duplicate_events.ged'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_ged(path) -> str:
    return Path(path).read_text(encoding='utf-8')


def event_blocks_for(content: str, xref: str, tag: str) -> list[list[str]]:
    """
    Return the list of event blocks of type `tag` (e.g. 'BIRT') for individual `xref`.
    Each block is a list of lines starting with '1 TAG' through its last sub-line.
    """
    lines = content.splitlines()
    in_rec = False
    blocks: list[list[str]] = []
    current_block: list[str] | None = None

    for line in lines:
        if re.match(r'^0 ', line):
            if current_block is not None:
                blocks.append(current_block)
                current_block = None
            in_rec = line.startswith(f'0 {xref} INDI')
            continue

        if not in_rec:
            continue

        if re.match(rf'^1 {re.escape(tag)}\b', line):
            if current_block is not None:
                blocks.append(current_block)
            current_block = [line]
        elif current_block is not None and re.match(r'^[2-9] ', line):
            current_block.append(line)
        else:
            if current_block is not None:
                blocks.append(current_block)
                current_block = None

    if current_block is not None:
        blocks.append(current_block)

    return blocks


def source_refs_in_block(block: list[str]) -> list[str]:
    """Return the list of SOUR xrefs cited within an event block."""
    return [
        re.match(r'^2 SOUR (@[^@]+@)', l).group(1)
        for l in block
        if re.match(r'^2 SOUR (@[^@]+@)', l)
    ]


@pytest.fixture()
def merged(tmp_path) -> tuple[str, dict]:
    """Run purge_duplicate_events on the fixture and return (output_content, result)."""
    dest = tmp_path / 'out.ged'
    result = purge_duplicate_events(str(FIXTURE), path_out=str(dest))
    return read_ged(dest), result


# ---------------------------------------------------------------------------
# Fixture sanity checks
# ---------------------------------------------------------------------------

class TestFixture:
    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_i1_has_two_birt_blocks(self):
        content = read_ged(FIXTURE)
        assert len(event_blocks_for(content, '@I1@', 'BIRT')) == 2

    def test_i2_has_two_birt_blocks(self):
        content = read_ged(FIXTURE)
        assert len(event_blocks_for(content, '@I2@', 'BIRT')) == 2

    def test_i3_has_two_birt_blocks(self):
        content = read_ged(FIXTURE)
        assert len(event_blocks_for(content, '@I3@', 'BIRT')) == 2

    def test_i4_has_two_bare_birt_blocks(self):
        content = read_ged(FIXTURE)
        blocks = event_blocks_for(content, '@I4@', 'BIRT')
        assert len(blocks) == 2
        assert all(len(b) == 1 for b in blocks)  # just the header line

    def test_i5_has_matching_birt_and_deat(self):
        content = read_ged(FIXTURE)
        birt = event_blocks_for(content, '@I5@', 'BIRT')
        deat = event_blocks_for(content, '@I5@', 'DEAT')
        assert len(birt) == 1 and len(deat) == 1

    def test_i6_has_three_birt_blocks(self):
        content = read_ged(FIXTURE)
        assert len(event_blocks_for(content, '@I6@', 'BIRT')) == 3

    def test_i11_has_one_birt_block(self):
        content = read_ged(FIXTURE)
        assert len(event_blocks_for(content, '@I11@', 'BIRT')) == 1


# ---------------------------------------------------------------------------
# @I1@ — same date+place, different sources → merge; both sources kept
# ---------------------------------------------------------------------------

class TestI1SameDatePlaceDifferentSources:
    def test_one_birt_block_remains(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I1@', 'BIRT')) == 1

    def test_both_sources_present(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I1@', 'BIRT')[0]
        refs = source_refs_in_block(block)
        assert '@S1@' in refs
        assert '@S2@' in refs

    def test_source_page_lines_preserved(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I1@', 'BIRT')[0]
        block_text = '\n'.join(block)
        assert 'Census entry' in block_text
        assert 'Birth certificate' in block_text


# ---------------------------------------------------------------------------
# @I2@ — different dates, same place → not a duplicate; both kept
# ---------------------------------------------------------------------------

class TestI2DifferentDates:
    def test_both_birt_blocks_kept(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I2@', 'BIRT')) == 2

    def test_both_dates_present(self, merged):
        content, _ = merged
        blocks = event_blocks_for(content, '@I2@', 'BIRT')
        all_lines = [l for b in blocks for l in b]
        dates = [re.match(r'^2 DATE (.+)', l).group(1) for l in all_lines if re.match(r'^2 DATE ', l)]
        assert '15 MAR 1850' in dates
        assert '20 APR 1850' in dates


# ---------------------------------------------------------------------------
# @I3@ — same date, one has place and one doesn't → not a duplicate; both kept
# ---------------------------------------------------------------------------

class TestI3SameDateMissingPlace:
    def test_both_birt_blocks_kept(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I3@', 'BIRT')) == 2

    def test_both_blocks_have_their_date(self, merged):
        content, _ = merged
        blocks = event_blocks_for(content, '@I3@', 'BIRT')
        assert all(
            any(re.match(r'^2 DATE 5 JUN 1920', l) for l in b)
            for b in blocks
        )


# ---------------------------------------------------------------------------
# @I4@ — two bare BIRT blocks (no date, no place) → merge; one removed
# ---------------------------------------------------------------------------

class TestI4TwoBareBlocks:
    def test_one_birt_block_remains(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I4@', 'BIRT')) == 1


# ---------------------------------------------------------------------------
# @I5@ — same date+place on BIRT and DEAT → not a duplicate across types
# ---------------------------------------------------------------------------

class TestI5DifferentEventTypes:
    def test_birt_kept(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I5@', 'BIRT')) == 1

    def test_deat_kept(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I5@', 'DEAT')) == 1

    def test_birt_and_deat_have_correct_dates(self, merged):
        content, _ = merged
        birt = event_blocks_for(content, '@I5@', 'BIRT')[0]
        deat = event_blocks_for(content, '@I5@', 'DEAT')[0]
        assert any('10 OCT 1880' in l for l in birt)
        assert any('10 OCT 1880' in l for l in deat)


# ---------------------------------------------------------------------------
# @I6@ — three BIRTs: pair share date+place; one differs → merge pair, keep unique
# ---------------------------------------------------------------------------

class TestI6ThreeBlocksMergeTwo:
    def test_two_birt_blocks_remain(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I6@', 'BIRT')) == 2

    def test_unique_date_kept(self, merged):
        content, _ = merged
        blocks = event_blocks_for(content, '@I6@', 'BIRT')
        all_dates = [
            re.match(r'^2 DATE (.+)', l).group(1)
            for b in blocks for l in b
            if re.match(r'^2 DATE ', l)
        ]
        assert '15 SEP 1900' in all_dates

    def test_merged_block_has_both_sources(self, merged):
        content, _ = merged
        blocks = event_blocks_for(content, '@I6@', 'BIRT')
        # The merged block (1 APR 1900) should carry both S3 and S4
        merged_block = next(
            b for b in blocks
            if any('1 APR 1900' in l for l in b)
        )
        refs = source_refs_in_block(merged_block)
        assert '@S3@' in refs
        assert '@S4@' in refs


# ---------------------------------------------------------------------------
# @I7@ — same date+place, same source in both → merge; source not duplicated
# ---------------------------------------------------------------------------

class TestI7SameSourceNotDuplicated:
    def test_one_birt_block_remains(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I7@', 'BIRT')) == 1

    def test_source_appears_exactly_once(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I7@', 'BIRT')[0]
        refs = source_refs_in_block(block)
        assert refs.count('@S1@') == 1


# ---------------------------------------------------------------------------
# @I8@ — same date+place; keeper has source, duplicate doesn't → source preserved
# ---------------------------------------------------------------------------

class TestI8KeeperHasSourceDupDoesnt:
    def test_one_birt_block_remains(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I8@', 'BIRT')) == 1

    def test_source_preserved(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I8@', 'BIRT')[0]
        assert '@S2@' in source_refs_in_block(block)

    def test_source_page_preserved(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I8@', 'BIRT')[0]
        assert any('Birth record' in l for l in block)


# ---------------------------------------------------------------------------
# @I9@ — same date+place; keeper bare, duplicate has source → source migrated
# ---------------------------------------------------------------------------

class TestI9KeeperBareDupHasSource:
    def test_one_birt_block_remains(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I9@', 'BIRT')) == 1

    def test_source_migrated_to_keeper(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I9@', 'BIRT')[0]
        assert '@S3@' in source_refs_in_block(block)

    def test_source_page_migrated(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I9@', 'BIRT')[0]
        assert any('Parish record' in l for l in block)


# ---------------------------------------------------------------------------
# @I10@ — same date+place on DEAT, two different sources → merge; both kept
# ---------------------------------------------------------------------------

class TestI10DeathDuplicateDifferentSources:
    def test_one_deat_block_remains(self, merged):
        content, _ = merged
        assert len(event_blocks_for(content, '@I10@', 'DEAT')) == 1

    def test_both_sources_present(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I10@', 'DEAT')[0]
        refs = source_refs_in_block(block)
        assert '@S4@' in refs
        assert '@S1@' in refs

    def test_both_page_lines_present(self, merged):
        content, _ = merged
        block = event_blocks_for(content, '@I10@', 'DEAT')[0]
        block_text = '\n'.join(block)
        assert 'Military record' in block_text
        assert 'Casualty list' in block_text


# ---------------------------------------------------------------------------
# @I11@ — single BIRT, no duplicates → unchanged
# ---------------------------------------------------------------------------

class TestI11NoDuplicates:
    def test_birt_block_unchanged(self, merged):
        content, _ = merged
        blocks = event_blocks_for(content, '@I11@', 'BIRT')
        assert len(blocks) == 1
        assert any('20 FEB 1930' in l for l in blocks[0])
        assert any('Sydney, Australia' in l for l in blocks[0])


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestReturnValues:
    def test_events_merged_positive(self, merged):
        _, result = merged
        # I1, I4, I6(pair), I7, I8, I9, I10 → 7 merges
        assert result['events_merged'] == 7

    def test_sources_added_correct(self, merged):
        _, result = merged
        # I1: +1 (S2 migrated), I9: +1 (S3 migrated), I6: +1 (S4 migrated),
        # I10: +1 (S1 migrated); others add 0
        assert result['sources_added'] == 4

    def test_lines_removed_positive(self, merged):
        _, result = merged
        assert result['lines_removed'] > 0

    def test_lines_read_matches_fixture(self, merged):
        content, result = merged
        with open(FIXTURE, encoding='utf-8') as f:
            fixture_lines = sum(1 for _ in f)
        assert result['lines_read'] == fixture_lines


# ---------------------------------------------------------------------------
# Structural integrity of output
# ---------------------------------------------------------------------------

class TestOutputIntegrity:
    def test_head_present(self, merged):
        content, _ = merged
        assert content.startswith('0 HEAD')

    def test_trlr_is_last_record(self, merged):
        content, _ = merged
        lines = [l for l in content.splitlines() if l.strip()]
        assert lines[-1] == '0 TRLR'

    def test_no_orphaned_level2_lines(self, merged):
        """No level-2+ line should appear without a preceding level-1 line in its block."""
        content, _ = merged
        prev_level = None
        for line in content.splitlines():
            m = re.match(r'^(\d+) ', line)
            if not m:
                continue
            level = int(m.group(1))
            if level > 1 and prev_level is not None:
                assert level <= prev_level + 1, (
                    f'Level skips from {prev_level} to {level}: {line!r}'
                )
            prev_level = level

    def test_all_indi_records_present(self, merged):
        content, _ = merged
        for i in range(1, 12):
            assert f'@I{i}@' in content


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_does_not_write(self, tmp_path):
        out = tmp_path / 'out.ged'
        purge_duplicate_events(str(FIXTURE), path_out=str(out), dry_run=True)
        assert not out.exists()

    def test_dry_run_returns_same_stats(self, tmp_path):
        out = tmp_path / 'out.ged'
        dry = purge_duplicate_events(str(FIXTURE), path_out=str(out), dry_run=True)
        real = purge_duplicate_events(str(FIXTURE), path_out=str(out))
        assert dry['events_merged'] == real['events_merged']
        assert dry['sources_added'] == real['sources_added']
        assert dry['lines_removed'] == real['lines_removed']


# ---------------------------------------------------------------------------
# Output-file option
# ---------------------------------------------------------------------------

class TestOutputFile:
    def test_output_to_separate_file(self, tmp_path):
        out = tmp_path / 'clean.ged'
        purge_duplicate_events(str(FIXTURE), path_out=str(out))
        assert out.exists()

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = tmp_path / 'clean.ged'
        original = FIXTURE.read_text(encoding='utf-8')
        purge_duplicate_events(str(FIXTURE), path_out=str(out))
        assert FIXTURE.read_text(encoding='utf-8') == original

    def test_in_place_modifies_file(self, tmp_path):
        copy = tmp_path / 'copy.ged'
        shutil.copy(FIXTURE, copy)
        original_lines = sum(1 for _ in copy.open(encoding='utf-8'))
        purge_duplicate_events(str(copy))
        new_lines = sum(1 for _ in copy.open(encoding='utf-8'))
        assert new_lines < original_lines


# ---------------------------------------------------------------------------
# Clean-file passthrough
# ---------------------------------------------------------------------------

class TestCleanFile:
    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Wonder/\n'
            '1 BIRT\n'
            '2 DATE 1 APR 1900\n'
            '2 PLAC London, England\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = purge_duplicate_events(str(clean))
        assert result['events_merged'] == 0
        assert result['sources_added'] == 0
        assert result['lines_removed'] == 0
        assert clean.read_text(encoding='utf-8') == original
