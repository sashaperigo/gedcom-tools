"""
Tests for strip_ancestry_artifacts.py

Uses tests/fixtures/ancestry_export.ged — a synthetic GEDCOM that mimics a
real Ancestry.com export, including all categories of proprietary tags:
  - Person/record identifiers: _APID, _OID, _TID, _PID, _LKID, _MSER
  - Provenance metadata:       _CREA, _USER, _ORIG, _ENCR, _ATL, _CLON
  - Tree/environment:          _TREE, _ENV
  - Photo metadata:            _PRIM, _CROP, _LEFT, _TOP, _WDTH, _HGHT,
                                _TYPE, _WPID, _HPID
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from strip_ancestry_artifacts import (
    ANCESTRY_TAGS,
    strip_ancestry_artifacts,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestry_export.ged'
_TAG_RE = re.compile(r'^\d+ ([A-Z_][A-Z0-9_]*)( |$)')


def tags_in_file(path: str) -> set[str]:
    """Return the set of all GEDCOM tags present in a file."""
    tags = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = _TAG_RE.match(line)
            if m:
                tags.add(m.group(1))
    return tags


def ancestry_tag_lines(path: str, tag: str) -> list[int]:
    """Return 1-based line numbers where a given tag appears."""
    hits = []
    with open(path, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            m = _TAG_RE.match(line)
            if m and m.group(1) == tag:
                hits.append(lineno)
    return hits


@pytest.fixture()
def tmp_copy(tmp_path):
    """Return a writable copy of the fixture file in a temp directory."""
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


# ---------------------------------------------------------------------------
# Fixture sanity checks — confirm the test file actually contains artifacts
# ---------------------------------------------------------------------------

class TestFixtureContents:
    """Verify the fixture has the tags we intend to strip (otherwise tests are vacuous)."""

    def test_fixture_exists(self):
        assert FIXTURE.exists(), f'Fixture file missing: {FIXTURE}'

    @pytest.mark.parametrize('tag', [
        '_APID', '_OID', '_TID', '_PID', '_LKID', '_MSER',
        '_CREA', '_USER', '_ORIG', '_ENCR', '_ATL', '_CLON',
        '_TREE', '_ENV',
        '_PRIM', '_CROP', '_LEFT', '_TOP', '_WDTH', '_HGHT',
        '_TYPE', '_WPID', '_HPID',
    ])
    def test_fixture_contains_tag(self, tag):
        """Fixture must contain each Ancestry tag so our removal tests are meaningful."""
        assert ancestry_tag_lines(str(FIXTURE), tag), (
            f'Fixture does not contain {tag} — add an example to ancestry_export.ged'
        )

    def test_fixture_has_real_records(self):
        """Fixture must also contain standard GEDCOM records."""
        tags = tags_in_file(str(FIXTURE))
        for expected in ('NAME', 'BIRT', 'DEAT', 'MARR', 'SOUR', 'FAMS'):
            assert expected in tags, f'Fixture missing standard tag {expected}'


# ---------------------------------------------------------------------------
# Core removal behaviour
# ---------------------------------------------------------------------------

class TestStripping:

    def test_all_ancestry_tags_removed(self, tmp_copy):
        strip_ancestry_artifacts(tmp_copy)
        remaining = tags_in_file(tmp_copy) & ANCESTRY_TAGS
        assert remaining == set(), f'Ancestry tags still present: {remaining}'

    def test_standard_tags_preserved(self, tmp_copy):
        strip_ancestry_artifacts(tmp_copy)
        tags = tags_in_file(tmp_copy)
        for tag in ('NAME', 'SEX', 'BIRT', 'DEAT', 'MARR', 'DATE', 'PLAC',
                    'FAMS', 'FAMC', 'HUSB', 'WIFE', 'CHIL', 'SOUR', 'HEAD', 'TRLR'):
            assert tag in tags, f'Standard tag {tag} was incorrectly removed'

    def test_lines_removed_count_is_positive(self, tmp_copy):
        result = strip_ancestry_artifacts(tmp_copy)
        assert result['lines_removed'] > 0

    def test_lines_removed_less_than_lines_read(self, tmp_copy):
        result = strip_ancestry_artifacts(tmp_copy)
        assert result['lines_removed'] < result['lines_read']

    def test_tags_removed_dict_populated(self, tmp_copy):
        result = strip_ancestry_artifacts(tmp_copy)
        assert result['tags_removed'], 'Expected tags_removed to be non-empty'

    def test_tags_removed_keys_are_ancestry_tags(self, tmp_copy):
        result = strip_ancestry_artifacts(tmp_copy)
        unknown = set(result['tags_removed'].keys()) - ANCESTRY_TAGS
        assert unknown == set(), f'Unexpected keys in tags_removed: {unknown}'

    def test_child_lines_of_ancestry_tag_removed(self, tmp_copy):
        """_CREA blocks contain _USER and DATE children — all must be gone."""
        strip_ancestry_artifacts(tmp_copy)
        # _USER is a child of _CREA; after stripping, neither should remain
        assert ancestry_tag_lines(tmp_copy, '_USER') == []
        assert ancestry_tag_lines(tmp_copy, '_CREA') == []

    def test_crop_children_removed(self, tmp_copy):
        """_CROP block contains _LEFT/_TOP/_WDTH/_HGHT children."""
        strip_ancestry_artifacts(tmp_copy)
        for child_tag in ('_LEFT', '_TOP', '_WDTH', '_HGHT'):
            assert ancestry_tag_lines(tmp_copy, child_tag) == [], (
                f'{child_tag} (child of _CROP) was not removed'
            )

    def test_output_is_valid_gedcom_structure(self, tmp_copy):
        """Every remaining line should match the basic GEDCOM level-tag pattern."""
        strip_ancestry_artifacts(tmp_copy)
        bad_lines = []
        valid_re = re.compile(r'^\d+ ')
        with open(tmp_copy, encoding='utf-8') as f:
            for lineno, line in enumerate(f, 1):
                stripped = line.rstrip('\n')
                if stripped and not valid_re.match(stripped):
                    bad_lines.append((lineno, stripped))
        assert bad_lines == [], f'Malformed lines after strip: {bad_lines[:5]}'

    def test_trlr_preserved(self, tmp_copy):
        """TRLR must remain as the final substantive line."""
        strip_ancestry_artifacts(tmp_copy)
        tags = []
        with open(tmp_copy, encoding='utf-8') as f:
            for line in f:
                m = _TAG_RE.match(line)
                if m:
                    tags.append(m.group(1))
        assert tags[-1] == 'TRLR', 'TRLR record was removed or displaced'


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_lines_read_matches_file_length(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            file_len = sum(1 for _ in f)
        result = strip_ancestry_artifacts(tmp_copy)
        assert result['lines_read'] == file_len

    def test_lines_removed_equals_diff(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = strip_ancestry_artifacts(tmp_copy)
        with open(tmp_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_removed'] == before - after

    def test_specific_tag_counts(self, tmp_copy):
        result = strip_ancestry_artifacts(tmp_copy)
        tr = result['tags_removed']
        # The fixture has _APID on @I1@, @I2@, @I3@, @S1@ = 4 occurrences
        assert tr.get('_APID', 0) == 4, (
            f"Expected 4 _APID tags, got {tr.get('_APID', 0)}"
        )
        # _CREA appears on @I1@, @I2@, @I3@ = 3 occurrences
        assert tr.get('_CREA', 0) == 3, (
            f"Expected 3 _CREA tags, got {tr.get('_CREA', 0)}"
        )


# ---------------------------------------------------------------------------
# Output-file option
# ---------------------------------------------------------------------------

class TestOutputFile:

    def test_output_to_separate_file(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        result = strip_ancestry_artifacts(str(FIXTURE), path_out=out)
        assert os.path.exists(out)
        remaining = tags_in_file(out) & ANCESTRY_TAGS
        assert remaining == set()

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        # Read original fixture content before stripping
        original = Path(str(FIXTURE)).read_text(encoding='utf-8')
        strip_ancestry_artifacts(str(FIXTURE), path_out=out)
        after = Path(str(FIXTURE)).read_text(encoding='utf-8')
        assert original == after, 'Input file was modified even though --output was given'

    def test_output_file_has_fewer_lines(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        result = strip_ancestry_artifacts(str(FIXTURE), path_out=out)
        with open(out, encoding='utf-8') as f:
            out_lines = sum(1 for _ in f)
        assert out_lines == result['lines_read'] - result['lines_removed']


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------

class TestDryRun:

    def test_dry_run_does_not_modify_file(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        strip_ancestry_artifacts(tmp_copy, dry_run=True)
        after = Path(tmp_copy).read_text(encoding='utf-8')
        assert original == after, 'dry_run=True must not modify the file'

    def test_dry_run_returns_correct_stats(self, tmp_copy):
        dry = strip_ancestry_artifacts(tmp_copy, dry_run=True)
        real = strip_ancestry_artifacts(tmp_copy)
        assert dry['lines_removed'] == real['lines_removed']
        assert dry['tags_removed'] == real['tags_removed']


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_clean_file_unchanged(self, tmp_path):
        """A file with no Ancestry tags should pass through unmodified."""
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Wonder/\n'
            '1 BIRT\n'
            '2 DATE 1 APR 1900\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = strip_ancestry_artifacts(str(clean))
        assert result['lines_removed'] == 0
        assert result['tags_removed'] == {}
        assert clean.read_text(encoding='utf-8') == original

    def test_deeply_nested_ancestry_block_removed(self, tmp_path):
        """Child lines at any depth beneath an Ancestry tag must all be removed."""
        ged = tmp_path / 'nested.ged'
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Bob /Builder/\n'
            '1 _CROP\n'
            '2 _LEFT 10\n'
            '2 _TOP 20\n'
            '3 NOTE some nested note\n'
            '2 _WDTH 100\n'
            '1 SEX M\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        strip_ancestry_artifacts(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '_CROP' not in content
        assert '_LEFT' not in content
        assert 'some nested note' not in content
        assert 'Bob /Builder/' in content
        assert 'SEX M' in content

    def test_ancestry_tag_at_level_zero_not_removed(self, tmp_path):
        """
        Level-0 records with standard xrefs should never be touched.
        This guards against a hypothetical file where someone used _-prefixed
        record IDs (non-standard but shouldn't be mass-deleted).
        The fixture doesn't have this, but the stripper should only target
        known Ancestry tags, not arbitrary _ xrefs.
        """
        ged = tmp_path / 'level0.ged'
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Carol /Smith/\n'
            '1 _APID 1,60238::999\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        strip_ancestry_artifacts(str(ged))
        content = ged.read_text(encoding='utf-8')
        # _APID (level 1) removed, but INDI record (level 0) must remain
        assert '@I1@ INDI' in content
        assert '_APID' not in content
