"""
Tests for export_minimal.py

Uses tests/fixtures/minimal_export.ged — a synthetic GEDCOM covering:

  @I1@  Primary NAME with SOUR + AKA NAME; BIRT with fact-SOUR; DEAT clean;
        person-level SOUR → AKA dropped, NAME SOUR stripped (GIVN/SURN kept),
        BIRT SOUR stripped, DEAT unchanged, person SOUR preserved
  @I2@  Primary NAME + AKA NAME; BIRT with DATE + fact-SOUR; person-level SOUR
        → AKA dropped, BIRT SOUR stripped (DATE kept), person SOUR preserved
  @I3@  Primary NAME only; BIRT with ONLY a fact-SOUR; person-level SOUR
        → BIRT block dropped (empty after strip), person SOUR preserved
  @I4@  Primary NAME; SEX with fact-SOUR; BIRT with DATE+PLAC; person-level SOUR
        → SEX preserved (inline value), BIRT unchanged, person SOUR preserved
  @F1@  MARR with DATE+PLAC+fact-SOUR; second MARR with ONLY fact-SOUR
        → first MARR kept (SOUR stripped), second MARR dropped (empty)
  @S1@  SOUR definition record → unchanged
"""

import re
from pathlib import Path

import pytest

from export_minimal import export_minimal

FIXTURE = Path(__file__).parent / 'fixtures' / 'minimal_export.ged'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(tmp_path) -> tuple[str, dict]:
    """Run export_minimal (skip_normalize=True) and return (output_content, stats)."""
    out = tmp_path / 'out.txt'
    result = export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True)
    return out.read_text(encoding='utf-8'), result


def name_blocks_for(content: str, xref: str) -> list[list[str]]:
    """Return all NAME blocks for the given individual xref."""
    lines = content.splitlines()
    in_rec = False
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        if re.match(r'^0 ', line):
            if current is not None:
                blocks.append(current)
                current = None
            in_rec = line.startswith(f'0 {xref} INDI')
            continue
        if not in_rec:
            continue
        if re.match(r'^1 NAME\b', line):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None and re.match(r'^[2-9] ', line):
            current.append(line)
        else:
            if current is not None:
                blocks.append(current)
                current = None

    if current is not None:
        blocks.append(current)
    return blocks


def event_blocks_for(content: str, xref: str, tag: str) -> list[list[str]]:
    """Return all event blocks of type `tag` for the given xref (INDI or FAM)."""
    lines = content.splitlines()
    in_rec = False
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        if re.match(r'^0 ', line):
            if current is not None:
                blocks.append(current)
                current = None
            in_rec = bool(re.match(rf'^0 {re.escape(xref)} (INDI|FAM)\b', line))
            continue
        if not in_rec:
            continue
        if re.match(rf'^1 {re.escape(tag)}\b', line):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None and re.match(r'^[2-9] ', line):
            current.append(line)
        else:
            if current is not None:
                blocks.append(current)
                current = None

    if current is not None:
        blocks.append(current)
    return blocks


def level1_tags_for(content: str, xref: str) -> list[str]:
    """Return the list of level-1 tag names for the given xref."""
    lines = content.splitlines()
    in_rec = False
    tags: list[str] = []

    for line in lines:
        if re.match(r'^0 ', line):
            in_rec = bool(re.match(rf'^0 {re.escape(xref)} ', line))
            continue
        if not in_rec:
            continue
        m = re.match(r'^1 (\w+)', line)
        if m:
            tags.append(m.group(1))
    return tags


@pytest.fixture()
def result(tmp_path):
    return run(tmp_path)


# ---------------------------------------------------------------------------
# AKA removal
# ---------------------------------------------------------------------------

class TestAkaRemoval:

    def test_i1_has_one_name_block(self, result):
        content, _ = result
        assert len(name_blocks_for(content, '@I1@')) == 1

    def test_i1_primary_name_retained(self, result):
        content, _ = result
        blocks = name_blocks_for(content, '@I1@')
        assert any('John /Smith/' in l for l in blocks[0])

    def test_i2_has_one_name_block(self, result):
        content, _ = result
        assert len(name_blocks_for(content, '@I2@')) == 1

    def test_i2_primary_name_retained(self, result):
        content, _ = result
        blocks = name_blocks_for(content, '@I2@')
        assert any('Jane /Doe/' in l for l in blocks[0])

    def test_no_aka_type_lines(self, result):
        content, _ = result
        assert 'TYPE AKA' not in content

    def test_i3_name_unchanged(self, result):
        content, _ = result
        assert len(name_blocks_for(content, '@I3@')) == 1
        assert 'Mary /Jones/' in content


# ---------------------------------------------------------------------------
# Fact-level source stripping
# ---------------------------------------------------------------------------

class TestFactSourceStripping:

    def test_no_level2_sour_in_output(self, result):
        content, _ = result
        assert not re.search(r'^2 SOUR\b', content, re.MULTILINE)

    def test_i1_name_block_has_givn_and_surn(self, result):
        """NAME block SOUR stripped but GIVN/SURN children remain."""
        content, _ = result
        blocks = name_blocks_for(content, '@I1@')
        block_text = '\n'.join(blocks[0])
        assert 'GIVN' in block_text
        assert 'SURN' in block_text

    def test_i1_birt_has_date_and_plac(self, result):
        content, _ = result
        blocks = event_blocks_for(content, '@I1@', 'BIRT')
        assert len(blocks) == 1
        block_text = '\n'.join(blocks[0])
        assert '15 MAR 1850' in block_text
        assert 'London, England' in block_text

    def test_i1_birt_has_no_sour(self, result):
        content, _ = result
        blocks = event_blocks_for(content, '@I1@', 'BIRT')
        assert not any(re.match(r'^2 SOUR\b', l) for l in blocks[0])

    def test_i2_birt_date_kept(self, result):
        content, _ = result
        blocks = event_blocks_for(content, '@I2@', 'BIRT')
        assert len(blocks) == 1
        assert any('3 APR 1855' in l for l in blocks[0])

    def test_i1_deat_unchanged(self, result):
        content, _ = result
        blocks = event_blocks_for(content, '@I1@', 'DEAT')
        assert len(blocks) == 1
        assert any('20 JUN 1920' in l for l in blocks[0])


# ---------------------------------------------------------------------------
# Person-level source preservation
# ---------------------------------------------------------------------------

class TestPersonSourcePreservation:

    def test_i1_has_level1_sour(self, result):
        content, _ = result
        tags = level1_tags_for(content, '@I1@')
        assert 'SOUR' in tags

    def test_i2_has_level1_sour(self, result):
        content, _ = result
        tags = level1_tags_for(content, '@I2@')
        assert 'SOUR' in tags

    def test_i3_has_level1_sour(self, result):
        content, _ = result
        tags = level1_tags_for(content, '@I3@')
        assert 'SOUR' in tags

    def test_i4_has_level1_sour(self, result):
        content, _ = result
        tags = level1_tags_for(content, '@I4@')
        assert 'SOUR' in tags

    def test_i1_person_sour_is_bare_pointer(self, result):
        """Person-level SOUR is always reduced to a bare pointer — no PAGE/DATA children."""
        content, _ = result
        lines = content.splitlines()
        in_i1 = False
        in_sour = False
        for line in lines:
            if re.match(r'^0 ', line):
                in_i1 = line.startswith('0 @I1@ INDI')
                in_sour = False
                continue
            if not in_i1:
                continue
            if re.match(r'^1 SOUR\b', line):
                in_sour = True
            elif in_sour and re.match(r'^1 ', line):
                in_sour = False
            elif in_sour and re.match(r'^2 ', line):
                pytest.fail(f'Person-level SOUR has unexpected child: {line!r}')


# ---------------------------------------------------------------------------
# Empty event dropping
# ---------------------------------------------------------------------------

class TestEmptyEventDropping:

    def test_i3_birt_dropped(self, result):
        """@I3@'s BIRT had only a fact-SOUR; after stripping it should be gone."""
        content, _ = result
        assert len(event_blocks_for(content, '@I3@', 'BIRT')) == 0

    def test_i3_has_no_birt_tag(self, result):
        content, _ = result
        tags = level1_tags_for(content, '@I3@')
        assert 'BIRT' not in tags

    def test_f1_only_one_marr_remains(self, result):
        """@F1@'s second MARR had only a fact-SOUR; it should be dropped."""
        content, _ = result
        assert len(event_blocks_for(content, '@F1@', 'MARR')) == 1

    def test_f1_marr_has_date_and_plac(self, result):
        content, _ = result
        blocks = event_blocks_for(content, '@F1@', 'MARR')
        block_text = '\n'.join(blocks[0])
        assert '5 JUL 1878' in block_text
        assert 'London, England' in block_text


# ---------------------------------------------------------------------------
# Inline-value tags preserved even after SOUR stripping
# ---------------------------------------------------------------------------

class TestInlineValueTagsPreserved:

    def test_i4_sex_present(self, result):
        """SEX M has a SOUR child in the fixture; after stripping, SEX M must remain."""
        content, _ = result
        assert 'SEX M' in content

    def test_i4_sex_has_no_sour(self, result):
        content, _ = result
        lines = content.splitlines()
        in_i4 = False
        for line in lines:
            if re.match(r'^0 ', line):
                in_i4 = line.startswith('0 @I4@ INDI')
                continue
            if not in_i4:
                continue
            if re.match(r'^1 SEX\b', line):
                # next line should NOT be a SOUR
                continue
            if re.match(r'^2 SOUR\b', line):
                pytest.fail(f'Found level-2 SOUR in @I4@ after SEX: {line!r}')


# ---------------------------------------------------------------------------
# FAM record handling
# ---------------------------------------------------------------------------

class TestFamHandling:

    def test_f1_marr_no_sour(self, result):
        content, _ = result
        blocks = event_blocks_for(content, '@F1@', 'MARR')
        assert not any(re.match(r'^2 SOUR\b', l) for l in blocks[0])

    def test_f1_husb_wife_preserved(self, result):
        content, _ = result
        tags = level1_tags_for(content, '@F1@')
        assert 'HUSB' in tags
        assert 'WIFE' in tags


# ---------------------------------------------------------------------------
# SOUR definition record passthrough
# ---------------------------------------------------------------------------

class TestSourceRecordPassthrough:

    def test_sour_record_present(self, result):
        content, _ = result
        assert '0 @S1@ SOUR' in content

    def test_sour_titl_present(self, result):
        content, _ = result
        assert 'Sample Source' in content


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestStats:

    def test_aka_blocks_removed(self, result):
        # @I1@ AKA + @I2@ AKA = 2
        _, stats = result
        assert stats['aka_blocks_removed'] == 2

    def test_fact_sources_removed(self, result):
        # @I1@ NAME, @I1@ BIRT, @I2@ BIRT, @I3@ BIRT, @I4@ SEX, @F1@ MARR1, @F1@ MARR2 = 7
        _, stats = result
        assert stats['fact_sources_removed'] == 7

    def test_empty_events_dropped(self, result):
        # @I3@ BIRT, @F1@ second MARR = 2
        _, stats = result
        assert stats['empty_events_dropped'] == 2

    def test_lines_out_less_than_lines_in(self, result):
        _, stats = result
        assert stats['lines_out'] < stats['lines_in']

    def test_notes_stripped_zero_by_default(self, result):
        _, stats = result
        assert stats['notes_stripped'] == 0


# ---------------------------------------------------------------------------
# Output structural integrity
# ---------------------------------------------------------------------------

class TestOutputIntegrity:

    def test_head_present(self, result):
        content, _ = result
        assert content.startswith('0 HEAD')

    def test_trlr_is_last(self, result):
        content, _ = result
        lines = [l for l in content.splitlines() if l.strip()]
        assert lines[-1] == '0 TRLR'

    def test_all_indi_records_present(self, result):
        content, _ = result
        for xref in ('@I1@', '@I2@', '@I3@', '@I4@'):
            assert xref in content

    def test_fam_record_present(self, result):
        content, _ = result
        assert '@F1@' in content

    def test_no_level_skips(self, result):
        """No line should jump more than one level from its predecessor."""
        content, _ = result
        prev = None
        for line in content.splitlines():
            m = re.match(r'^(\d+) ', line)
            if not m:
                continue
            lv = int(m.group(1))
            if prev is not None and lv > prev + 1:
                pytest.fail(f'Level jump {prev} → {lv}: {line!r}')
            prev = lv


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------

class TestDryRun:

    def test_dry_run_does_not_write(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), dry_run=True, skip_normalize=True)
        assert not out.exists()

    def test_dry_run_returns_same_stats(self, tmp_path):
        out = tmp_path / 'out.txt'
        dry = export_minimal(str(FIXTURE), path_out=str(out), dry_run=True, skip_normalize=True)
        real = export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True)
        assert dry['aka_blocks_removed'] == real['aka_blocks_removed']
        assert dry['fact_sources_removed'] == real['fact_sources_removed']
        assert dry['empty_events_dropped'] == real['empty_events_dropped']
        assert dry['lines_out'] == real['lines_out']


# ---------------------------------------------------------------------------
# Input-file unchanged when --output specified
# ---------------------------------------------------------------------------

class TestKeepFactSources:

    def test_level2_sour_present_when_kept(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       keep_fact_sources=True)
        content = out.read_text(encoding='utf-8')
        assert re.search(r'^2 SOUR\b', content, re.MULTILINE)

    def test_fact_sour_children_stripped_even_when_kept(self, tmp_path):
        """Even when keeping fact-level sources, their PAGE/DATA children are stripped."""
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       keep_fact_sources=True)
        content = out.read_text(encoding='utf-8')
        assert not re.search(r'^3 PAGE\b', content, re.MULTILINE)

    def test_aka_still_removed_when_keeping_sources(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       keep_fact_sources=True)
        content = out.read_text(encoding='utf-8')
        assert 'TYPE AKA' not in content

    def test_fact_sources_removed_stat_is_zero(self, tmp_path):
        out = tmp_path / 'out.txt'
        result = export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                                keep_fact_sources=True)
        assert result['fact_sources_removed'] == 0

    def test_empty_events_not_dropped_when_keeping_sources(self, tmp_path):
        """@I3@'s BIRT and @F1@'s second MARR had only fact-SOURs; with
        keep_fact_sources they have content and should be kept."""
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       keep_fact_sources=True)
        content = out.read_text(encoding='utf-8')
        assert len(event_blocks_for(content, '@I3@', 'BIRT')) == 1
        assert len(event_blocks_for(content, '@F1@', 'MARR')) == 2


class TestStripNotes:

    def test_person_note_removed(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       strip_notes=True)
        content = out.read_text(encoding='utf-8')
        assert 'Peter was a merchant' not in content

    def test_event_note_preserved(self, tmp_path):
        """2 NOTE on a BIRT event must survive even when strip_notes=True."""
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       strip_notes=True)
        content = out.read_text(encoding='utf-8')
        assert 'Born in winter' in content

    def test_note_cont_also_removed(self, tmp_path):
        """The CONT child of a stripped NOTE should not appear."""
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       strip_notes=True)
        content = out.read_text(encoding='utf-8')
        assert 'He married twice' not in content

    def test_notes_stripped_stat(self, tmp_path):
        out = tmp_path / 'out.txt'
        result = export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                                strip_notes=True)
        assert result['notes_stripped'] == 1  # @I4@ has one person-level NOTE


class TestStripSourBodies:

    def test_sour_record_header_present(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       strip_sour_bodies=True)
        content = out.read_text(encoding='utf-8')
        assert '0 @S1@ SOUR' in content

    def test_sour_titl_present(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       strip_sour_bodies=True)
        content = out.read_text(encoding='utf-8')
        assert 'Sample Source' in content

    def test_sour_auth_stripped(self, tmp_path):
        out = tmp_path / 'out.txt'
        export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                       strip_sour_bodies=True)
        content = out.read_text(encoding='utf-8')
        assert 'Test Author' not in content

    def test_sour_records_trimmed_stat(self, tmp_path):
        out = tmp_path / 'out.txt'
        result = export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True,
                                strip_sour_bodies=True)
        assert result['sour_records_trimmed'] == 1  # fixture has one SOUR record

    def test_sour_records_trimmed_zero_when_flag_off(self, result):
        _, stats = result
        assert stats['sour_records_trimmed'] == 0


class TestInputUnchanged:

    def test_fixture_not_modified(self, tmp_path):
        original = FIXTURE.read_text(encoding='utf-8')
        export_minimal(str(FIXTURE), path_out=str(tmp_path / 'out.txt'), skip_normalize=True)
        assert FIXTURE.read_text(encoding='utf-8') == original

    def test_overwrite_input_raises(self, tmp_path):
        copy = tmp_path / 'copy.ged'
        copy.write_text(FIXTURE.read_text(encoding='utf-8'), encoding='utf-8')
        with pytest.raises(ValueError, match='Output path must differ from input'):
            export_minimal(str(copy), path_out=str(copy), skip_normalize=True)


# ---------------------------------------------------------------------------
# Duplicate SOUR deduplication
# ---------------------------------------------------------------------------

class TestDedupSourCitations:
    """Duplicate SOUR citations produced when stripping removes distinguishing detail."""

    # Two person-level SOURs to @S1@ (different PAGE), one BIRT with two
    # fact-level SOURs to @S1@ (different PAGE).
    DUPED_GED = (
        '0 HEAD\n'
        '1 GEDC\n'
        '2 VERS 5.5.1\n'
        '0 @I1@ INDI\n'
        '1 NAME Alice /Test/\n'
        '1 SOUR @S1@\n'
        '2 PAGE First ref\n'
        '1 SOUR @S1@\n'
        '2 PAGE Second ref\n'
        '1 BIRT\n'
        '2 DATE 1 JAN 1900\n'
        '2 SOUR @S1@\n'
        '3 PAGE Page A\n'
        '2 SOUR @S1@\n'
        '3 PAGE Page B\n'
        '0 @S1@ SOUR\n'
        '1 TITL Test Source\n'
        '0 TRLR\n'
    )

    def _run(self, tmp_path, **kwargs):
        src = tmp_path / 'duped.ged'
        src.write_text(self.DUPED_GED, encoding='utf-8')
        out = tmp_path / 'out.txt'
        result = export_minimal(str(src), path_out=str(out), skip_normalize=True, **kwargs)
        return out.read_text(encoding='utf-8'), result

    def test_person_level_sour_deduped(self, tmp_path):
        """Two 1 SOUR @S1@ on the same person collapse to one after PAGE is stripped."""
        content, _ = self._run(tmp_path)
        sour_lines = [l for l in content.splitlines() if re.match(r'^1 SOUR\b', l)]
        assert sour_lines == ['1 SOUR @S1@']

    def test_fact_level_sour_deduped_when_kept(self, tmp_path):
        """Two 2 SOUR @S1@ under the same BIRT collapse to one when keep_fact_sources=True."""
        content, _ = self._run(tmp_path, keep_fact_sources=True)
        birt_blocks = event_blocks_for(content, '@I1@', 'BIRT')
        assert len(birt_blocks) == 1
        sour_lines = [l for l in birt_blocks[0] if re.match(r'^2 SOUR\b', l)]
        assert len(sour_lines) == 1

    def test_stat_default_mode(self, tmp_path):
        """Default mode: 1 person-level dup removed; fact-level SOURs are stripped entirely."""
        _, result = self._run(tmp_path)
        assert result['duplicate_sources_removed'] == 1

    def test_stat_keep_fact_sources(self, tmp_path):
        """keep_fact_sources: 1 person-level dup + 1 fact-level dup = 2 total."""
        _, result = self._run(tmp_path, keep_fact_sources=True)
        assert result['duplicate_sources_removed'] == 2

    def test_stat_zero_on_clean_file(self, tmp_path):
        """No duplicates in the main fixture."""
        out = tmp_path / 'out.txt'
        result = export_minimal(str(FIXTURE), path_out=str(out), skip_normalize=True)
        assert result['duplicate_sources_removed'] == 0


# ---------------------------------------------------------------------------
# Clean passthrough: file with no AKAs and no fact-level SOURs is unchanged
# ---------------------------------------------------------------------------

class TestCleanPassthrough:

    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Wonder/\n'
            '2 GIVN Alice\n'
            '2 SURN Wonder\n'
            '1 BIRT\n'
            '2 DATE 1 APR 1900\n'
            '2 PLAC London, England\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        out = tmp_path / 'out.txt'
        result = export_minimal(str(clean), path_out=str(out), skip_normalize=True)
        assert result['aka_blocks_removed'] == 0
        assert result['fact_sources_removed'] == 0
        assert result['empty_events_dropped'] == 0
        assert out.read_text(encoding='utf-8') == clean.read_text(encoding='utf-8')
