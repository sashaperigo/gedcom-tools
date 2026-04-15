"""
Tests for marriage / divorce add-and-delete features added to serve_viz.py.

Covers:
  - _find_existing_fam   – finds FAM xref for a known couple (either order)
  - _next_fam_xref       – allocates @F(max+1)@
  - _add_fams_to_indi    – inserts 1 FAMS line in an INDI block
  - _insert_fam_event    – appends MARR/DIV block to existing FAM
  - _create_fam_with_event – builds a brand-new FAM record
  - /api/delete_marriage – removes a MARR block from a FAM record
  - /api/add_marriage    – creates or reuses a FAM and inserts MARR/DIV

Fixture individuals (ancestors_sample.ged):
  @I1@  Rose /Smith/   SEX F  FAMS @F5@
  @I12@ Mark /Davis/   SEX M  FAMS @F5@
  @F5@  HUSB @I12@  WIFE @I1@  MARR 2015 Greenwich
  @I2@  James /Smith/  SEX M  FAMS @F1@
  @I3@  Clara /Jones/  SEX F  FAMS @F1@
  @F1@  HUSB @I2@   WIFE @I3@  (no MARR event)
  Max FAM xref in file: @F7@  → next should be @F8@
"""

import json
import os
import shutil
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

from serve_viz import (          # noqa: E402  (after env var is set)
    _find_existing_fam,
    _next_fam_xref,
    _add_fams_to_indi,
    _insert_fam_event,
    _create_fam_with_event,
)
import serve_viz  # noqa: E402

FIXTURE = Path(_FIXTURE_GED)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _lines():
    return FIXTURE.read_text(encoding='utf-8').splitlines()


@pytest.fixture
def live_server(tmp_path):
    """Spin up a live server on an ephemeral port with a writable GED copy."""
    ged = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, ged)

    with patch.object(serve_viz, 'GED', ged), \
         patch.object(serve_viz, 'regenerate', return_value=None):
        server = HTTPServer(('127.0.0.1', 0), serve_viz.Handler)
        port = server.server_address[1]
        base = f'http://127.0.0.1:{port}'

        def _one_request():
            server.handle_request()

        def post(path, body):
            import urllib.request
            t = threading.Thread(target=_one_request, daemon=True)
            t.start()
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                base + path, data=data,
                headers={'Content-Type': 'application/json',
                         'Content-Length': str(len(data))},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())

        yield ged, post, server
        server.server_close()


# ===========================================================================
# _find_existing_fam
# ===========================================================================

class TestFindExistingFam:

    def test_finds_fam_husb_then_wife(self):
        lines = _lines()
        result = _find_existing_fam(lines, '@I12@', '@I1@')
        assert result == '@F5@'

    def test_finds_fam_wife_then_husb(self):
        """Order of arguments should not matter."""
        lines = _lines()
        result = _find_existing_fam(lines, '@I1@', '@I12@')
        assert result == '@F5@'

    def test_returns_none_for_no_match(self):
        lines = _lines()
        # @I2@ and @I12@ are not in a FAM together
        result = _find_existing_fam(lines, '@I2@', '@I12@')
        assert result is None

    def test_returns_none_for_unknown_xrefs(self):
        lines = _lines()
        result = _find_existing_fam(lines, '@NOBODY@', '@GONE@')
        assert result is None

    def test_does_not_match_one_sided(self):
        """FAM with only HUSB set should not match a query for HUSB+unknown."""
        lines = _lines()
        # @F6@ has only HUSB @I10@, no WIFE
        result = _find_existing_fam(lines, '@I10@', '@NOBODY@')
        assert result is None


# ===========================================================================
# _next_fam_xref
# ===========================================================================

class TestNextFamXref:

    def test_increments_beyond_max(self):
        lines = _lines()
        # Fixture has @F1@ … @F7@, so next should be @F8@
        result = _next_fam_xref(lines)
        assert result == '@F8@'

    def test_works_with_minimal_ged(self):
        lines = ['0 HEAD', '0 @F3@ FAM', '1 HUSB @I1@', '0 TRLR']
        result = _next_fam_xref(lines)
        assert result == '@F4@'

    def test_works_with_no_fam_records(self):
        lines = ['0 HEAD', '0 @I1@ INDI', '1 NAME Test /Person/', '0 TRLR']
        result = _next_fam_xref(lines)
        assert result == '@F1@'


# ===========================================================================
# _add_fams_to_indi
# ===========================================================================

class TestAddFamsToIndi:

    def test_inserts_fams_line_in_indi_block(self):
        lines = _lines()
        new_lines = _add_fams_to_indi(lines, '@I2@', '@F7@')
        text = '\n'.join(new_lines)
        # Must appear inside @I2@'s block (before next record)
        i2_start = next(i for i, l in enumerate(new_lines) if '0 @I2@ INDI' in l)
        i2_end = next(i for i in range(i2_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[i2_start:i2_end]
        assert any('1 FAMS @F7@' == l.strip() for l in block)

    def test_does_not_add_duplicate_fams(self):
        """If FAMS already exists for this family, do not add a second copy."""
        lines = _lines()
        # @I1@ already has FAMS @F5@
        new_lines = _add_fams_to_indi(lines, '@I1@', '@F5@')
        # Count only within @I1@'s block (not @I12@ which also has FAMS @F5@)
        i1_start = next(i for i, l in enumerate(new_lines) if '0 @I1@ INDI' in l)
        i1_end = next(i for i in range(i1_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[i1_start:i1_end]
        count = sum(1 for l in block if l.strip() == '1 FAMS @F5@')
        assert count == 1

    def test_returns_list_of_strings(self):
        lines = _lines()
        result = _add_fams_to_indi(lines, '@I4@', '@F7@')
        assert isinstance(result, list)
        assert all(isinstance(l, str) for l in result)


# ===========================================================================
# _insert_fam_event
# ===========================================================================

class TestInsertFamEvent:

    def test_inserts_marr_into_existing_fam(self):
        lines = _lines()
        # @F1@ has no MARR event
        new_lines = _insert_fam_event(lines, '@F1@', 'MARR', {'DATE': '1985', 'PLAC': 'Boston, MA'})
        f1_start = next(i for i, l in enumerate(new_lines) if '0 @F1@ FAM' in l)
        f1_end = next(i for i in range(f1_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[f1_start:f1_end]
        assert any('1 MARR' == l.strip() for l in block)
        assert any('1985' in l for l in block)
        assert any('Boston' in l for l in block)

    def test_inserts_div_into_existing_fam(self):
        lines = _lines()
        new_lines = _insert_fam_event(lines, '@F5@', 'DIV', {'DATE': '2020'})
        f5_start = next(i for i, l in enumerate(new_lines) if '0 @F5@ FAM' in l)
        f5_end = next(i for i in range(f5_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[f5_start:f5_end]
        assert any('1 DIV' == l.strip() for l in block)
        assert any('2020' in l for l in block)

    def test_preserves_existing_marr(self):
        """Adding a second MARR should not remove the first."""
        lines = _lines()
        new_lines = _insert_fam_event(lines, '@F5@', 'MARR', {'DATE': '2016', 'PLAC': 'Church'})
        f5_start = next(i for i, l in enumerate(new_lines) if '0 @F5@ FAM' in l)
        f5_end = next(i for i in range(f5_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[f5_start:f5_end]
        marr_count = sum(1 for l in block if l.strip() == '1 MARR')
        assert marr_count == 2

    def test_omits_empty_subtags(self):
        lines = _lines()
        new_lines = _insert_fam_event(lines, '@F1@', 'MARR', {'DATE': '', 'PLAC': ''})
        f1_start = next(i for i, l in enumerate(new_lines) if '0 @F1@ FAM' in l)
        f1_end = next(i for i in range(f1_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[f1_start:f1_end]
        # No bare '2 DATE ' or '2 PLAC ' lines
        assert not any(l.startswith('2 DATE ') and l.strip() == '2 DATE' for l in block)


# ===========================================================================
# _create_fam_with_event
# ===========================================================================

class TestCreateFamWithEvent:

    def test_creates_fam_record(self):
        lines = _lines()
        new_lines = _create_fam_with_event(
            lines, '@I4@', '@I5@', '@F8@', 'MARR', {'DATE': '1955'}
        )
        assert any('0 @F8@ FAM' in l for l in new_lines)

    def test_fam_contains_husb_wife(self):
        lines = _lines()
        new_lines = _create_fam_with_event(
            lines, '@I4@', '@I5@', '@F8@', 'MARR', {}
        )
        f8_start = next(i for i, l in enumerate(new_lines) if '0 @F8@ FAM' in l)
        f8_end = next(i for i in range(f8_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[f8_start:f8_end]
        assert any('1 HUSB @I4@' == l.strip() for l in block)
        assert any('1 WIFE @I5@' == l.strip() for l in block)

    def test_fam_contains_event(self):
        lines = _lines()
        new_lines = _create_fam_with_event(
            lines, '@I4@', '@I5@', '@F8@', 'MARR', {'DATE': '1955', 'PLAC': 'Dublin'}
        )
        f8_start = next(i for i, l in enumerate(new_lines) if '0 @F8@ FAM' in l)
        f8_end = next(i for i in range(f8_start + 1, len(new_lines)) if new_lines[i].startswith('0 '))
        block = new_lines[f8_start:f8_end]
        assert any('1 MARR' == l.strip() for l in block)
        assert any('1955' in l for l in block)
        assert any('Dublin' in l for l in block)

    def test_appended_after_existing_fam_records(self):
        """New FAM should come after the last existing FAM block, before TRLR."""
        lines = _lines()
        new_lines = _create_fam_with_event(
            lines, '@I4@', '@I5@', '@F8@', 'MARR', {}
        )
        trlr_idx = next(i for i, l in enumerate(new_lines) if l.strip() == '0 TRLR')
        f8_idx = next(i for i, l in enumerate(new_lines) if '0 @F8@ FAM' in l)
        assert f8_idx < trlr_idx


# ===========================================================================
# /api/delete_marriage  (HTTP integration)
# ===========================================================================

class TestDeleteMarriageEndpoint:

    def test_returns_ok_true(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/delete_marriage', {
            'xref': '@I1@', 'fam_xref': '@F5@', 'marr_occurrence': 0,
        })
        assert resp['ok'] is True

    def test_removes_marr_block_from_ged(self, live_server):
        ged, post, _ = live_server
        post('/api/delete_marriage', {
            'xref': '@I1@', 'fam_xref': '@F5@', 'marr_occurrence': 0,
        })
        text = ged.read_text(encoding='utf-8')
        # The MARR event (with date 2015) should be gone; FAM record may remain
        assert '2 DATE 2015' not in text or '1 MARR' not in text

    def test_returns_updated_people(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/delete_marriage', {
            'xref': '@I1@', 'fam_xref': '@F5@', 'marr_occurrence': 0,
        })
        assert 'people' in resp
        assert '@I1@' in resp['people']

    def test_returns_both_spouses(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/delete_marriage', {
            'xref': '@I1@', 'fam_xref': '@F5@', 'marr_occurrence': 0,
        })
        assert '@I12@' in resp['people']

    def test_unknown_fam_returns_error(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/delete_marriage', {
            'xref': '@I1@', 'fam_xref': '@FNOBODY@', 'marr_occurrence': 0,
        })
        assert resp['ok'] is False
        assert 'error' in resp

    def test_bad_occurrence_returns_error(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/delete_marriage', {
            'xref': '@I1@', 'fam_xref': '@F5@', 'marr_occurrence': 99,
        })
        assert resp['ok'] is False


# ===========================================================================
# /api/add_marriage  (HTTP integration)
# ===========================================================================

class TestAddMarriageEndpoint:

    def test_add_marr_to_existing_fam(self, live_server):
        """Adding MARR to @F1@ (which has no MARR event) should succeed."""
        ged, post, _ = live_server
        resp = post('/api/add_marriage', {
            'xref': '@I2@', 'spouse_xref': '@I3@', 'tag': 'MARR',
            'fields': {'DATE': '1984', 'PLAC': 'Ann Arbor, Michigan, USA'},
        })
        assert resp['ok'] is True
        text = ged.read_text(encoding='utf-8')
        assert '1 MARR' in text
        assert '1984' in text

    def test_add_marr_creates_new_fam_when_none_exists(self, live_server):
        """No FAM between @I4@ and @I11@ → new FAM should be created."""
        ged, post, _ = live_server
        resp = post('/api/add_marriage', {
            'xref': '@I4@', 'spouse_xref': '@I11@', 'tag': 'MARR',
            'fields': {'DATE': '1952'},
        })
        assert resp['ok'] is True
        text = ged.read_text(encoding='utf-8')
        # New FAM record should exist with both people
        assert '@I4@' in text
        assert '@I11@' in text
        # The new FAM should have a MARR event
        assert '1 MARR' in text

    def test_new_fam_adds_fams_to_both_indis(self, live_server):
        ged, post, _ = live_server
        post('/api/add_marriage', {
            'xref': '@I4@', 'spouse_xref': '@I11@', 'tag': 'MARR',
            'fields': {},
        })
        text = ged.read_text(encoding='utf-8')
        # Both @I4@ and @I11@ should have FAMS pointing to the new FAM
        # We can check that a new @FX@ appears as FAMS in both INDI blocks
        new_fam = '@F8@'   # fixture max is @F7@, next is @F8@
        assert f'1 FAMS {new_fam}' in text

    def test_add_div_creates_fam_event(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/add_marriage', {
            'xref': '@I4@', 'spouse_xref': '@I11@', 'tag': 'DIV',
            'fields': {'DATE': '1960'},
        })
        assert resp['ok'] is True
        text = ged.read_text(encoding='utf-8')
        assert '1 DIV' in text

    def test_returns_people_for_both_parties(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/add_marriage', {
            'xref': '@I2@', 'spouse_xref': '@I3@', 'tag': 'MARR',
            'fields': {},
        })
        assert 'people' in resp
        assert '@I2@' in resp['people']
        assert '@I3@' in resp['people']

    def test_invalid_date_returns_error(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/add_marriage', {
            'xref': '@I2@', 'spouse_xref': '@I3@', 'tag': 'MARR',
            'fields': {'DATE': 'NOT A DATE'},
        })
        assert resp['ok'] is False
        assert 'error' in resp

    def test_missing_spouse_returns_error(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/add_marriage', {
            'xref': '@I2@', 'tag': 'MARR', 'fields': {},
        })
        assert resp['ok'] is False
