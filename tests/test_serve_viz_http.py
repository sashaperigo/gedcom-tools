"""
Integration tests for serve_viz.py HTTP API endpoints.

Spins up a real HTTPServer on an ephemeral port with a writable copy of the
fixture GED file.  Each test sends one or more HTTP requests and asserts on:
  - JSON response shape (ok, people keys)
  - GED file content after the mutation
  - .ged.bak file existence / content for write endpoints

Fixture GED at tests/fixtures/ancestors_sample.ged — key individuals:
  @I1@  Rose /Smith/    BIRT 14 MAR 1990,  FAMS @F5@
  @I12@ Mark /Davis/    BIRT 1988,          FAMS @F5@
  @F5@  HUSB @I12@ WIFE @I1@  MARR 2015 Greenwich...
  @I2@  James /Smith/   BIRT 1960           NOTE Rose was an avid gardener.

NOTE: regenerate() is patched to a no-op in all tests; it does a subprocess
call to rebuild the HTML which is unnecessary (and slow) in unit tests.
"""

import json
import os
import shutil
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
import urllib.request
import urllib.error

import pytest

_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

import serve_viz  # noqa: E402

FIXTURE = Path(_FIXTURE_GED)


# ---------------------------------------------------------------------------
# Fixture: live server
# ---------------------------------------------------------------------------

@pytest.fixture
def live_server(tmp_path):
    """
    Spin up a Handler server on an ephemeral port with a writable GED copy.

    Yields (ged_path, post_fn, get_fn, server).

    post_fn(path, body_dict) -> response_dict
    get_fn(path) -> (status, body_bytes)

    regenerate() is patched to a no-op so tests don't invoke subprocesses.
    """
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

        def get(path):
            t = threading.Thread(target=_one_request, daemon=True)
            t.start()
            req = urllib.request.Request(base + path, method='GET')
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as e:
                return e.code, b''

        yield ged, post, get, server
        server.server_close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ged_text(ged_path):
    return ged_path.read_text(encoding='utf-8')


# ===========================================================================
# GET handler
# ===========================================================================

class TestGetHandler:
    def test_root_path_returns_200(self, live_server):
        ged, post, get, server = live_server
        # Patch OUT to a real temp file so SimpleHTTPRequestHandler can serve it
        import tempfile
        import pathlib
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w') as f:
            f.write('<html>test</html>')
            out_path = pathlib.Path(f.name)
        with patch.object(serve_viz, 'OUT', out_path):
            status, _ = get('/')
        out_path.unlink(missing_ok=True)
        assert status == 200

    def test_unknown_path_returns_404(self, live_server):
        ged, post, get, server = live_server
        status, _ = get('/no-such-endpoint')
        assert status == 404


# ===========================================================================
# /api/delete_fact
# ===========================================================================

class TestDeleteFactEndpoint:
    def test_returns_ok_true(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/delete_fact', {
            'xref': '@I1@', 'tag': 'DEAT', 'date': '2080',
        })
        assert resp['ok'] is True

    def test_modifies_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/delete_fact', {'xref': '@I1@', 'tag': 'DEAT', 'date': '2080'})
        text = _ged_text(ged)
        assert '1 DEAT' not in text or '2080' not in text

    def test_returns_updated_people_json(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/delete_fact', {'xref': '@I1@', 'tag': 'DEAT', 'date': '2080'})
        assert 'people' in resp
        assert '@I1@' in resp['people']

    def test_unknown_xref_returns_error(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/delete_fact', {'xref': '@NOBODY@', 'tag': 'BIRT'})
        assert resp['ok'] is False
        assert 'error' in resp

    def test_delete_inline_type_fact_with_type_field(self, live_server):
        # Regression: deleting NATI/OCCU/etc. where type=inline_val was failing because
        # _apply_deletion checked for a 2 TYPE sub-record that doesn't exist for inline tags.
        # @I2@ has "1 NATI American" — type and inline_val both equal "American".
        ged, post, _, _ = live_server
        resp = post('/api/delete_fact', {
            'xref': '@I2@', 'tag': 'NATI',
            'inline_val': 'American', 'type': 'American',
            'date': None, 'place': None,
        })
        assert resp.get('ok') is True, resp.get('error')
        assert '1 NATI American' not in _ged_text(ged)


# ===========================================================================
# /api/delete_note
# ===========================================================================

class TestDeleteNoteEndpoint:
    def test_returns_ok_true(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/delete_note', {'xref': '@I1@', 'note_idx': 0})
        assert resp['ok'] is True

    def test_note_removed_from_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/delete_note', {'xref': '@I1@', 'note_idx': 0})
        text = _ged_text(ged)
        assert 'avid gardener' not in text

    def test_delete_note_bad_idx_returns_error(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/delete_note', {'xref': '@I1@', 'note_idx': 99})
        assert resp['ok'] is False


# ===========================================================================
# /api/edit_note
# ===========================================================================

class TestEditNoteEndpoint:
    def test_returns_ok_true(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_note', {
            'xref': '@I1@', 'note_idx': 0, 'new_text': 'Updated note text',
        })
        assert resp['ok'] is True

    def test_edited_note_text_in_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/edit_note', {'xref': '@I1@', 'note_idx': 0, 'new_text': 'Brand new text'})
        assert 'Brand new text' in _ged_text(ged)

    def test_multiline_note_uses_cont_in_ged(self, live_server):
        ged, post, _, _ = live_server
        post('/api/edit_note', {
            'xref': '@I1@', 'note_idx': 0,
            'new_text': 'Line one\nLine two',
        })
        text = _ged_text(ged)
        assert '2 CONT Line two' in text

    def test_bad_xref_returns_error(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_note', {
            'xref': '@NOBODY@', 'note_idx': 0, 'new_text': 'x',
        })
        assert resp['ok'] is False


# ===========================================================================
# /api/edit_event  — individual event AND family/marriage event
# ===========================================================================

class TestEditEventEndpoint:
    # (1) Individual event: editing BIRT on @I1@
    def test_individual_event_returns_ok(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'BIRT', 'event_idx': 0,
            'updates': {'DATE': '1 JAN 1991'},
        })
        assert resp['ok'] is True

    def test_individual_event_modifies_ged(self, live_server):
        ged, post, _, _ = live_server
        post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'BIRT', 'event_idx': 0,
            'updates': {'DATE': '1 JAN 1991'},
        })
        assert '1 JAN 1991' in _ged_text(ged)

    def test_individual_event_people_json_updated(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'BIRT', 'event_idx': 0,
            'updates': {'PLAC': 'New Haven, Connecticut, USA'},
        })
        assert '@I1@' in resp.get('people', {})

    # (2) Family/marriage event: editing MARR on @F5@ (HUSB=@I12@, WIFE=@I1@)
    def test_family_event_returns_ok(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'MARR', 'fam_xref': '@F5@',
            'updates': {'DATE': '15 JUN 2016'},
        })
        assert resp['ok'] is True

    def test_family_event_modifies_fam_block_in_ged(self, live_server):
        ged, post, _, _ = live_server
        post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'MARR', 'fam_xref': '@F5@',
            'updates': {'DATE': '15 JUN 2016'},
        })
        text = _ged_text(ged)
        assert '15 JUN 2016' in text

    def test_family_event_response_includes_both_spouses(self, live_server):
        """Both @I1@ (wife) and @I12@ (husband) must appear in the people dict."""
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'MARR', 'fam_xref': '@F5@',
            'updates': {'PLAC': 'New York, USA'},
        })
        assert resp['ok'] is True
        people = resp.get('people', {})
        assert '@I1@' in people, 'wife (@I1@) missing from people response'
        assert '@I12@' in people, 'husband (@I12@) missing from people response'

    def test_family_event_addr_written_to_ged(self, live_server):
        """Regression: adding ADDR to a MARR event must write '2 ADDR' into the GED file."""
        ged, post, _, _ = live_server
        post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'MARR', 'fam_xref': '@F5@',
            'updates': {'ADDR': 'St. Paul Cathedral'},
        })
        text = _ged_text(ged)
        assert '2 ADDR St. Paul Cathedral' in text, \
            'ADDR sub-tag must be written under 1 MARR in the FAM block'

    def test_family_event_addr_in_people_json(self, live_server):
        """Regression: after adding ADDR to a MARR event the response people JSON must include it."""
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'MARR', 'fam_xref': '@F5@',
            'updates': {'ADDR': 'St. Paul Cathedral'},
        })
        assert resp['ok'] is True
        marr_evts = [e for e in resp['people']['@I1@']['events'] if e['tag'] == 'MARR']
        assert marr_evts, 'Expected a MARR event in the response'
        assert marr_evts[0].get('addr') == 'St. Paul Cathedral', \
            'addr field must be present and correct in the returned MARR event'

    def test_family_event_edit_returns_both_spouses(self, live_server):
        """
        Regression: editing a marriage event must return updated data for BOTH spouses
        so the caller can refresh the panel for the currently-open person.

        Without this fix: if xref=@I1@ edits @F5@ MARR, the response only contained
        @I1@'s data.  When the JS calls showDetail(@I1@) after updating PEOPLE, Saverio's
        entry (the other spouse) would be stale — so his panel still showed the old MARR
        card without the newly-added ADDR.

        @F5@ has HUSB @I12@ and WIFE @I1@; both must appear in people.
        """
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'MARR', 'fam_xref': '@F5@',
            'updates': {'PLAC': 'New York, NY'},
        })
        assert resp['ok'] is True
        assert '@I1@' in resp['people'], 'Wife xref must be in the response'
        assert '@I12@' in resp['people'], \
            'Husband xref must also be in the response so his panel can be refreshed'

    def test_individual_event_unknown_xref_returns_error(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@NOBODY@', 'tag': 'BIRT', 'event_idx': 0,
            'updates': {'DATE': '1900'},
        })
        assert resp['ok'] is False

    def test_nonstandard_date_normalized_on_edit(self, live_server):
        """Non-standard date input should be silently normalized to GEDCOM format."""
        ged, post, _, _ = live_server
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'BIRT', 'event_idx': 0,
            'updates': {'DATE': 'january 5, 1991'},
        })
        assert resp['ok'] is True
        assert '5 JAN 1991' in _ged_text(ged)
        assert 'january' not in _ged_text(ged)

    def test_invalid_date_rejected_on_edit(self, live_server):
        """Completely invalid date input should return ok: False without writing."""
        ged, post, _, _ = live_server
        original = _ged_text(ged)
        resp = post('/api/edit_event', {
            'xref': '@I1@', 'tag': 'BIRT', 'event_idx': 0,
            'updates': {'DATE': 'not a date at all'},
        })
        assert resp['ok'] is False
        assert 'error' in resp
        assert _ged_text(ged) == original  # file must be unchanged


# ===========================================================================
# /api/convert_event
# ===========================================================================

class TestConvertEventEndpoint:
    def test_converts_birt_tag_to_bapm_in_ged(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        assert resp.get('ok') is True
        lines = _ged_text(ged).splitlines()
        # Extract @I1@'s block and verify the tag was renamed there
        in_i1, i1_lines = False, []
        for ln in lines:
            if ln.startswith('0 @I1@ INDI'):
                in_i1 = True
            elif in_i1 and ln.startswith('0 '):
                break
            if in_i1:
                i1_lines.append(ln)
        assert '1 BAPM' in i1_lines, '1 BAPM not found in @I1@ block'

    def test_preserves_date_and_place_after_conversion(self, live_server):
        ged, post, _, _ = live_server
        post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        text = _ged_text(ged)
        assert '2 DATE 14 MAR 1990' in text
        assert '2 PLAC Greenwich, Connecticut, USA' in text

    def test_returns_people_with_converted_event(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        assert 'people' in resp
        people = resp['people']
        assert '@I1@' in people
        tags = [e['tag'] for e in people['@I1@']['events']]
        assert 'BAPM' in tags
        assert 'BIRT' in tags  # new approximate BIRT is auto-inserted

    def test_unknown_from_tag_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/convert_event', {
                'xref': '@I1@', 'event_idx': 0, 'from_tag': 'XXXX', 'to_tag': 'BAPM',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        bak = ged.with_suffix('.ged.bak')
        bak.unlink(missing_ok=True)
        post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        assert bak.exists()

    def test_birt_to_bapm_inserts_approximate_birt_event(self, live_server):
        ged, post, _, _ = live_server
        post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        text = _ged_text(ged)
        assert '1 BIRT' in text
        assert '2 DATE ABT 1990' in text

    def test_birt_to_bapm_uses_baptism_place_for_new_birth(self, live_server):
        ged, post, _, _ = live_server
        post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        lines = _ged_text(ged).splitlines()
        in_birt, birt_plac = False, None
        for ln in lines:
            if ln == '1 BIRT':
                in_birt = True
            elif in_birt and ln.startswith('2 PLAC '):
                birt_plac = ln[len('2 PLAC '):]
                break
            elif in_birt and ln.startswith('1 '):
                break
        assert birt_plac == 'Greenwich, Connecticut, USA'

    def test_birt_to_bapm_new_birth_inserted_before_bapm(self, live_server):
        ged, post, _, _ = live_server
        post('/api/convert_event', {
            'xref': '@I1@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'BAPM',
        })
        lines = _ged_text(ged).splitlines()
        birt_pos = next((i for i, l in enumerate(lines) if l == '1 BIRT'), None)
        bapm_pos = next((i for i, l in enumerate(lines) if l == '1 BAPM'), None)
        assert birt_pos is not None and bapm_pos is not None
        assert birt_pos < bapm_pos

    def test_birt_to_chr_does_not_insert_extra_birt(self, live_server):
        ged, post, _, _ = live_server
        initial_birt_count = _ged_text(ged).count('1 BIRT')
        post('/api/convert_event', {
            'xref': '@I2@', 'event_idx': 0, 'from_tag': 'BIRT', 'to_tag': 'CHR',
        })
        assert _ged_text(ged).count('1 BIRT') == initial_birt_count - 1


# ===========================================================================
# /api/add_event
# ===========================================================================

class TestAddEventEndpoint:
    def test_returns_ok_true(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'RESI',
            'fields': {'DATE': '1985', 'PLAC': 'Boston, Massachusetts'},
        })
        assert resp['ok'] is True

    def test_added_event_in_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_event', {
            'xref': '@I2@', 'tag': 'RESI',
            'fields': {'DATE': '1985', 'PLAC': 'Boston, Massachusetts'},
        })
        text = _ged_text(ged)
        assert 'Boston, Massachusetts' in text

    def test_nonstandard_date_normalized_on_add(self, live_server):
        """Non-standard date input on add_event should also be normalized."""
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'RESI',
            'fields': {'DATE': 'about 1985', 'PLAC': 'Boston, Massachusetts'},
        })
        assert resp['ok'] is True
        assert 'ABT 1985' in _ged_text(ged)

    def test_invalid_date_rejected_on_add(self, live_server):
        """Invalid date on add_event should return ok: False without writing."""
        ged, post, _, _ = live_server
        original = _ged_text(ged)
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'RESI',
            'fields': {'DATE': 'not a date at all'},
        })
        assert resp['ok'] is False
        assert _ged_text(ged) == original

    def test_unknown_xref_returns_error(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@NOBODY@', 'tag': 'RESI', 'fields': {},
        })
        assert resp['ok'] is False

    def test_empty_tag_rejected(self, live_server):
        """Empty tag must not write orphan '1 ' lines to the GED file.

        Regression: a client bug left the event-type <select> value empty when
        opening the modal with a preset pseudo-tag (e.g. 'FACT:Languages'), so
        the server received tag='' and appended malformed '1 ' lines.
        """
        ged, post, _, _ = live_server
        original = _ged_text(ged)
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': '',
            'fields': {'TYPE': 'Languages', 'NOTE': 'French, Italian'},
        })
        assert resp['ok'] is False
        assert _ged_text(ged) == original

    def test_whitespace_tag_rejected(self, live_server):
        ged, post, _, _ = live_server
        original = _ged_text(ged)
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': '   ',
            'fields': {'TYPE': 'Languages'},
        })
        assert resp['ok'] is False
        assert _ged_text(ged) == original

    def test_malformed_tag_rejected(self, live_server):
        """Tags must match the GEDCOM grammar (uppercase letters/digits/_)."""
        ged, post, _, _ = live_server
        original = _ged_text(ged)
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'FACT:Languages',  # colon is not a valid tag char
            'fields': {},
        })
        assert resp['ok'] is False
        assert _ged_text(ged) == original

    def test_nchi_inline_value_round_trips(self, live_server):
        """Adding NCHI with an inline value must show up in the refreshed
        people payload (the 'Add Fact → Children (count)' flow)."""
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'NCHI',
            'fields': {'inline_val': '5'},
        })
        assert resp['ok'] is True
        assert '1 NCHI 5' in _ged_text(ged)
        events = resp['people']['@I2@']['events']
        nchi = next((e for e in events if e['tag'] == 'NCHI'), None)
        assert nchi is not None, 'NCHI event missing from refreshed panel data'
        assert nchi['inline_val'] == '5'

    def test_dscr_inline_value_round_trips(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'DSCR',
            'fields': {'inline_val': 'Tall with red hair'},
        })
        assert resp['ok'] is True
        events = resp['people']['@I2@']['events']
        dscr = next((e for e in events if e['tag'] == 'DSCR'), None)
        assert dscr is not None, 'DSCR event missing from refreshed panel data'
        assert dscr['inline_val'] == 'Tall with red hair'

    def test_fact_with_type_writes_clean_block(self, live_server):
        """A valid FACT add with TYPE + NOTE produces a well-formed block
        (no orphan '1 ' lines). Models the 'Add Fact: Languages' flow."""
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I2@', 'tag': 'FACT',
            'fields': {'TYPE': 'Languages', 'NOTE': 'French, Italian'},
        })
        assert resp['ok'] is True
        text = _ged_text(ged)
        # The new block must have a tag on every level-1 line — no bare '1 ' lines.
        for line in text.splitlines():
            assert line.rstrip() != '1', f'found orphan level-1 line: {line!r}'
        assert '1 FACT' in text
        assert '2 TYPE Languages' in text
        assert '2 NOTE French, Italian' in text

    def test_deat_y_writes_inline_value_not_subline(self, live_server):
        """DATE='Y' on a DEAT event must write '1 DEAT Y', not '1 DEAT' + '2 DATE Y'."""
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I3@', 'tag': 'DEAT',
            'fields': {'DATE': 'Y'},
        })
        assert resp['ok'] is True
        text = _ged_text(ged)
        assert '1 DEAT Y' in text
        assert '2 DATE Y' not in text

    def test_deat_y_sets_has_death_in_refreshed_people(self, live_server):
        """After adding DEAT Y, the refreshed people payload has has_death=True and death_year=None."""
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I3@', 'tag': 'DEAT',
            'fields': {'DATE': 'Y'},
        })
        assert resp['ok'] is True
        person = resp['people']['@I3@']
        assert person['has_death'] is True
        assert person['death_year'] is None

    def test_deat_y_event_appears_in_refreshed_events(self, live_server):
        """DEAT Y event must appear in the refreshed people event list."""
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@I3@', 'tag': 'DEAT',
            'fields': {'DATE': 'Y'},
        })
        assert resp['ok'] is True
        events = resp['people']['@I3@']['events']
        deat = next((e for e in events if e['tag'] == 'DEAT'), None)
        assert deat is not None, 'DEAT event missing from refreshed panel data'

# ===========================================================================
# /api/edit_name
# ===========================================================================

class TestEditNameEndpoint:
    def test_returns_ok_true(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_name', {
            'xref': '@I2@', 'given_name': 'Jimmy', 'surname': 'Smith',
        })
        assert resp['ok'] is True

    def test_edited_name_in_people_response(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/edit_name', {
            'xref': '@I2@', 'given_name': 'Jimmy', 'surname': 'Smith',
        })
        people = resp.get('people', {})
        assert '@I2@' in people
        assert 'Jimmy' in people['@I2@']['name']

    def test_edited_name_in_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/edit_name', {'xref': '@I2@', 'given_name': 'Jimmy', 'surname': 'Smith'})
        assert 'Jimmy' in _ged_text(ged)


# ===========================================================================
# /api/add_secondary_name  /api/edit_secondary_name  /api/delete_secondary_name
# ===========================================================================

class TestAliasEndpoints:
    def test_add_alias_returns_ok(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_secondary_name', {
            'xref': '@I2@', 'name': 'Jim Smith', 'name_type': 'AKA',
        })
        assert resp['ok'] is True

    def test_added_alias_in_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_secondary_name', {
            'xref': '@I2@', 'name': 'Jim Smith', 'name_type': 'AKA',
        })
        text = _ged_text(ged)
        assert 'Jim /Smith/' in text
        assert '2 TYPE AKA' in text

    def test_edit_alias_returns_ok(self, live_server):
        ged, post, _, _ = live_server
        # First add one so there's something to edit
        post('/api/add_secondary_name', {
            'xref': '@I2@', 'name': 'Jim Smith', 'name_type': 'AKA',
        })
        resp = post('/api/edit_secondary_name', {
            'xref': '@I2@', 'name_occurrence': 0,
            'name': 'James Jr. Smith', 'name_type': 'AKA',
        })
        assert resp['ok'] is True

    def test_edited_alias_in_ged_file(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_secondary_name', {
            'xref': '@I2@', 'name': 'Jim Smith', 'name_type': 'AKA',
        })
        post('/api/edit_secondary_name', {
            'xref': '@I2@', 'name_occurrence': 0,
            'name': 'James Jr. Smith', 'name_type': 'AKA',
        })
        text = _ged_text(ged)
        assert 'James Jr.' in text

    def test_delete_alias_removes_from_ged(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_secondary_name', {
            'xref': '@I2@', 'name': 'Jim Smith', 'name_type': 'AKA',
        })
        resp = post('/api/delete_secondary_name', {
            'xref': '@I2@', 'name_occurrence': 0,
        })
        assert resp['ok'] is True
        # After delete, the alias should be gone
        text = _ged_text(ged)
        assert 'Jim /Smith/' not in text


# ===========================================================================
# Backup created by write endpoints
# ===========================================================================

class TestBackupCreatedByEndpoints:
    def test_delete_fact_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        post('/api/delete_fact', {'xref': '@I1@', 'tag': 'DEAT', 'date': '2080'})
        assert ged.with_suffix('.ged.bak').exists()

    def test_edit_name_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        post('/api/edit_name', {'xref': '@I2@', 'given_name': 'Jimmy', 'surname': 'Smith'})
        assert ged.with_suffix('.ged.bak').exists()

    def test_backup_contains_pre_edit_content(self, live_server):
        ged, post, _, _ = live_server
        original = ged.read_text(encoding='utf-8')
        post('/api/edit_name', {'xref': '@I2@', 'given_name': 'Jimmy', 'surname': 'Smith'})
        backup = ged.with_suffix('.ged.bak').read_text(encoding='utf-8')
        assert backup == original


# ===========================================================================
# /api/add_source
# ===========================================================================

class TestAddSourceEndpoint:
    def test_returns_xref(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_source', {
            'titl': 'Birth Records', 'auth': 'County Office',
            'publ': '', 'repo': '', 'note': '',
        })
        assert 'xref' in resp
        assert resp['xref'].startswith('@S')

    def test_new_sour_record_in_ged(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_source', {
            'titl': 'Birth Records', 'auth': 'County Office',
            'publ': 'City Hall', 'repo': '', 'note': 'Reliable source',
        })
        text = _ged_text(ged)
        xref = resp['xref']
        assert f'0 {xref} SOUR' in text
        assert '1 TITL Birth Records' in text
        assert '1 AUTH County Office' in text
        assert '1 PUBL City Hall' in text
        assert '1 NOTE Reliable source' in text

    def test_empty_optional_fields_not_written(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_source', {
            'titl': 'Simple Source', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })
        text = _ged_text(ged)
        assert '1 AUTH' not in text
        assert '1 PUBL' not in text
        assert '1 REPO' not in text

    def test_xref_increments(self, live_server):
        ged, post, _, _ = live_server
        resp1 = post('/api/add_source', {'titl': 'Source One', 'auth': '', 'publ': '', 'repo': '', 'note': ''})
        resp2 = post('/api/add_source', {'titl': 'Source Two', 'auth': '', 'publ': '', 'repo': '', 'note': ''})
        assert resp1['xref'] != resp2['xref']

    def test_missing_titl_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/add_source', {'auth': 'Someone'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_source', {'titl': 'Source', 'auth': '', 'publ': '', 'repo': '', 'note': ''})
        assert ged.with_suffix('.ged.bak').exists()


# ===========================================================================
# /api/edit_source_record
# ===========================================================================

class TestEditSourceRecordEndpoint:
    def test_updates_titl(self, live_server):
        ged, post, _, _ = live_server
        # First add a source
        resp = post('/api/add_source', {
            'titl': 'Original Title', 'auth': 'Author', 'publ': '', 'repo': '', 'note': '',
        })
        xref = resp['xref']
        resp2 = post('/api/edit_source_record', {
            'xref': xref, 'titl': 'Updated Title', 'auth': 'Author',
            'publ': '', 'repo': '', 'note': '',
        })
        assert resp2.get('ok') is True
        text = _ged_text(ged)
        assert '1 TITL Updated Title' in text
        assert '1 TITL Original Title' not in text

    def test_removes_empty_optional_fields(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_source', {
            'titl': 'Title', 'auth': 'Old Author', 'publ': 'Publisher', 'repo': '', 'note': '',
        })
        xref = resp['xref']
        # Now edit: remove auth and publ by passing empty strings
        post('/api/edit_source_record', {
            'xref': xref, 'titl': 'Title', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })
        text = _ged_text(ged)
        assert '1 AUTH Old Author' not in text
        assert '1 PUBL Publisher' not in text

    def test_unknown_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/edit_source_record', {
                'xref': '@S999@', 'titl': 'X', 'auth': '', 'publ': '', 'repo': '', 'note': '',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_missing_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/edit_source_record', {'titl': 'Title'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_source', {'titl': 'T', 'auth': '', 'publ': '', 'repo': '', 'note': ''})
        # Remove the bak from the add_source call
        bak = ged.with_suffix('.ged.bak')
        bak.unlink(missing_ok=True)
        post('/api/edit_source_record', {
            'xref': resp['xref'], 'titl': 'T2', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })
        assert bak.exists()


# ===========================================================================
# /api/add_citation
# ===========================================================================

class TestAddCitationEndpoint:
    def _add_source(self, post):
        """Helper: add a source, return its xref."""
        return post('/api/add_source', {
            'titl': 'Test Source', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']

    def test_fact_level_citation_written_to_ged(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 42', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert f'2 SOUR {sour_xref}' in text
        assert '3 PAGE p. 42' in text

    def test_fact_citation_with_text(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': '', 'text': 'Entry reads: born 1990', 'note': '',
        })
        text = _ged_text(ged)
        assert '3 DATA' in text
        assert '4 TEXT Entry reads: born 1990' in text

    def test_fact_citation_multiline_text_uses_cont(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': '',
            'text': 'Line one\nLine two\nLine three', 'note': '',
        })
        text = _ged_text(ged)
        assert '4 TEXT Line one' in text
        assert '5 CONT Line two' in text
        assert '5 CONT Line three' in text
        # Must not embed literal newlines in a single line value
        assert '4 TEXT Line one\nLine two' not in text

    def test_person_level_citation(self, live_server):
        """No fact_key → person-level SOUR at level 1."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@I2@', 'sour_xref': sour_xref,
            'fact_key': None, 'page': 'p. 1', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert f'1 SOUR {sour_xref}' in text

    def test_missing_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        sour_xref = self._add_source(post)
        try:
            post('/api/add_citation', {'sour_xref': sour_xref, 'fact_key': 'BIRT:0'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_missing_sour_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/add_citation', {'xref': '@I1@', 'fact_key': 'BIRT:0'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        bak = ged.with_suffix('.ged.bak')
        bak.unlink(missing_ok=True)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 1', 'text': '', 'note': '',
        })
        assert bak.exists()

    def test_returns_people_with_new_citation(self, live_server):
        """Response must include a `people` dict so the client can refresh
        PEOPLE[xref] and re-render the sources modal / panel without reloading."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 42', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        assert 'people' in resp, 'response must include refreshed people payload'
        people = resp['people']
        assert '@I1@' in people, f'refreshed people must include the edited xref; got keys={list(people.keys())}'
        birt_events = [e for e in people['@I1@']['events'] if e['tag'] == 'BIRT']
        assert birt_events, 'refreshed payload must include BIRT'
        assert any(
            (c.get('sourceXref') == sour_xref) or (c.get('sour_xref') == sour_xref)
            for c in birt_events[0].get('citations', [])
        ), 'new citation must appear in refreshed BIRT.citations'

    def test_empty_citation_writes_only_sour_line(self, live_server):
        """Citation with no page/text/note/url must write just a bare SOUR line."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': '', 'text': '', 'note': '', 'url': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert f'2 SOUR {sour_xref}' in text
        # No sub-tags written for empty fields
        lines = text.splitlines()
        sour_idx = next(i for i, l in enumerate(lines) if l.strip() == f'2 SOUR {sour_xref}')
        next_line = lines[sour_idx + 1] if sour_idx + 1 < len(lines) else ''
        assert not next_line.startswith('3 PAGE'), 'no PAGE sub-tag for empty page'
        assert not next_line.startswith('3 DATA'), 'no DATA sub-tag when text and url are empty'

    def test_long_text_is_chunked_into_conc_lines(self, live_server):
        """TEXT fields exceeding 248 chars must be split into CONC continuation lines."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        long_text = 'A' * 200 + ' ' + 'B' * 200  # 401 chars, split at space
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': '', 'text': long_text, 'note': '',
        })
        text = _ged_text(ged)
        assert '4 TEXT ' in text, 'TEXT line must be written'
        assert '5 CONC ' in text, 'long line must produce CONC continuation'
        # No single physical line should exceed 255 chars (level+space+tag+space+value)
        for line in text.splitlines():
            assert len(line) <= 255, f'physical line too long ({len(line)}): {line[:60]}...'

    def test_add_citation_with_url_writes_www_under_data(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': '', 'text': '', 'note': '',
            'url': 'https://example.com/record/42',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        lines = text.splitlines()
        in_i1 = False; in_birt = False; in_data = False; found = False
        for ln in lines:
            if ln.startswith('0 @I1@ INDI'):  in_i1 = True; continue
            if in_i1 and ln.startswith('0 '): break
            if in_i1 and ln == '1 BIRT':      in_birt = True; continue
            if in_birt and ln.startswith('1 '): in_birt = False
            if in_birt and ln.startswith(f'2 SOUR {sour_xref}'): in_data = True; continue
            if in_data and ln == '3 DATA':    continue
            if in_data and ln == '4 WWW https://example.com/record/42': found = True; break
        assert found, f'4 WWW not found under BIRT SOUR block in @I1@\n{text}'

    def test_paste_citation_on_newly_added_event_writes_to_correct_fact(self, live_server):
        """Regression: pasting a citation that already exists on an earlier event
        (e.g. BIRT) onto a newly created event (RESI added via add_event) must
        write the citation under the new event, not silently skip it as a
        false duplicate."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)

        # Step 1: cite BIRT on @I1@ with a specific page.
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 1', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True

        # Step 2: add a new RESI event (simulates "recently created via UI").
        resp = post('/api/add_event', {
            'xref': '@I1@', 'tag': 'RESI',
            'fields': {'DATE': '1 JAN 1950', 'PLAC': 'Boston'},
        })
        assert resp.get('ok') is True

        # Step 3: paste the same source+page onto the new RESI event.
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'RESI:0', 'page': 'p. 1', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True

        # The citation must appear under the RESI block, not just the BIRT block.
        text = _ged_text(ged)
        lines = text.splitlines()
        in_i1 = False; in_resi = False; found = False
        for ln in lines:
            if ln.startswith('0 @I1@ INDI'): in_i1 = True; continue
            if in_i1 and ln.startswith('0 '): break
            if in_i1 and ln == '1 RESI': in_resi = True; continue
            if in_resi and ln.startswith('1 '): in_resi = False
            if in_resi and ln == f'2 SOUR {sour_xref}': found = True; break
        assert found, (
            f'Citation on RESI not found; _citation_already_exists may be '
            f'crossing event block boundaries.\n{text}'
        )


# ===========================================================================
# /api/edit_citation
# ===========================================================================

class TestEditCitationEndpoint:
    def _setup_citation(self, post, xref='@I1@', fact_key='BIRT:0'):
        """Add a source and a citation, return sour_xref."""
        sour_xref = post('/api/add_source', {
            'titl': 'Test Source', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']
        post('/api/add_citation', {
            'xref': xref, 'sour_xref': sour_xref,
            'fact_key': fact_key, 'page': 'p. 1', 'text': '', 'note': '',
        })
        return sour_xref

    def test_updates_page(self, live_server):
        ged, post, _, _ = live_server
        self._setup_citation(post)
        resp = post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 99', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 PAGE p. 99' in text
        assert '3 PAGE p. 1' not in text

    def test_adds_text_field(self, live_server):
        ged, post, _, _ = live_server
        self._setup_citation(post)
        post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 1', 'text': 'New transcription', 'note': '',
        })
        text = _ged_text(ged)
        assert '4 TEXT New transcription' in text

    def test_missing_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/edit_citation', {'citation_key': 'BIRT:0:0', 'page': 'p. 1'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_missing_citation_key_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/edit_citation', {'xref': '@I1@', 'page': 'p. 1'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        self._setup_citation(post)
        bak = ged.with_suffix('.ged.bak')
        bak.unlink(missing_ok=True)
        post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 99', 'text': '', 'note': '',
        })
        assert bak.exists()

    def test_returns_people_with_updated_citation(self, live_server):
        """Response must include a `people` dict so the client can refresh
        PEOPLE[xref] and re-render the panel without reloading."""
        ged, post, _, _ = live_server
        self._setup_citation(post)
        resp = post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 99', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        assert 'people' in resp, 'response must include refreshed people payload'
        people = resp['people']
        assert '@I1@' in people, f'refreshed people must include edited xref; got {list(people.keys())}'
        birt_events = [e for e in people['@I1@']['events'] if e['tag'] == 'BIRT']
        assert birt_events, 'refreshed payload must include BIRT event'
        assert any(c.get('page') == 'p. 99' for c in birt_events[0].get('citations', [])), \
            'updated page must appear in refreshed BIRT.citations'

    def test_edit_second_citation_not_first(self, live_server):
        """Editing citation index 1 must not corrupt citation index 0."""
        ged, post, _, _ = live_server
        sour_xref = self._setup_citation(post)  # adds citation 0 with page 'p. 1'
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 2', 'text': '', 'note': '',
        })
        resp = post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:1',
            'page': 'p. 99', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 PAGE p. 1' in text,  'citation 0 must be untouched'
        assert '3 PAGE p. 99' in text, 'citation 1 must be updated'
        assert '3 PAGE p. 2' not in text

    def test_edit_shrinks_multiline_text(self, live_server):
        """Editing a citation that had multi-line TEXT down to one line must not
        leave orphan CONT lines behind."""
        ged, post, _, _ = live_server
        self._setup_citation(post)
        post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 1', 'text': 'First\nSecond\nThird', 'note': '',
        })
        assert '5 CONT Second' in _ged_text(ged)  # confirm CONT lines were written
        post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 1', 'text': 'Just one line', 'note': '',
        })
        text = _ged_text(ged)
        assert '4 TEXT Just one line' in text
        assert '5 CONT Second' not in text, 'orphan CONT must be removed after edit'
        assert '5 CONT Third' not in text

    def test_out_of_bounds_citation_key_returns_400(self, live_server):
        """Editing a citation index that does not exist must return HTTP 400."""
        import urllib.error
        ged, post, _, _ = live_server
        self._setup_citation(post)  # only BIRT:0:0 exists
        try:
            post('/api/edit_citation', {
                'xref': '@I1@', 'citation_key': 'BIRT:0:5',
                'page': 'p. 99', 'text': '', 'note': '',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_malformed_citation_key_returns_400(self, live_server):
        """A citation_key with the wrong number of parts must return HTTP 400."""
        import urllib.error
        ged, post, _, _ = live_server
        try:
            post('/api/edit_citation', {
                'xref': '@I1@', 'citation_key': 'BIRT:0',  # missing cite_n
                'page': 'p. 1', 'text': '', 'note': '',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400


# ===========================================================================
# QUAY + DATE round-trip on citation builders + add/edit endpoints
# ===========================================================================

class TestCitationQuayAndDate:
    """QUAY (citation quality 0–3) and citation DATE round-trip through
    `_build_citation_lines`, `/api/add_citation`, and `/api/edit_citation`,
    for both INDI events and FAM (MARR/DIV) events."""

    def _add_source(self, post):
        return post('/api/add_source', {
            'titl': 'Quality-and-date Source', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']

    # -------------------------------------------------------------------
    # Pure builder unit tests (`_build_citation_lines`)
    # -------------------------------------------------------------------

    def test_builder_emits_quay_under_sour_at_correct_level(self):
        from serve_viz import _build_citation_lines
        lines = _build_citation_lines('@S1@', 'p. 1', '', '', base_level=2, quay='3')
        assert lines[0] == '2 SOUR @S1@'
        assert '3 QUAY 3' in lines, f'expected `3 QUAY 3` in {lines}'

    def test_builder_emits_date_inside_data_block(self):
        """DATE must be a child of DATA at level b+2, alongside TEXT."""
        from serve_viz import _build_citation_lines
        lines = _build_citation_lines(
            '@S1@', '', 'transcribed text', '', base_level=2, date='21 MAY 1814',
        )
        assert '3 DATA' in lines
        data_i = lines.index('3 DATA')
        assert '4 DATE 21 MAY 1814' in lines, f'expected `4 DATE …` in {lines}'
        date_i = lines.index('4 DATE 21 MAY 1814')
        assert date_i > data_i, 'DATE must appear after DATA'
        # And DATE must precede TEXT per GEDCOM 5.5.1 ordering convention.
        assert date_i < lines.index('4 TEXT transcribed text')

    def test_builder_creates_data_block_when_only_date_set(self):
        """Even without TEXT/URL, setting DATE must wrap it in a DATA block."""
        from serve_viz import _build_citation_lines
        lines = _build_citation_lines('@S1@', '', '', '', base_level=2, date='1900')
        assert '3 DATA' in lines
        assert '4 DATE 1900' in lines

    def test_builder_omits_quay_when_blank(self):
        from serve_viz import _build_citation_lines
        lines = _build_citation_lines('@S1@', 'p. 1', '', '', base_level=2)
        assert not any(ln.startswith('3 QUAY') for ln in lines), f'QUAY must be absent: {lines}'

    def test_builder_omits_date_when_blank(self):
        from serve_viz import _build_citation_lines
        lines = _build_citation_lines('@S1@', 'p. 1', '', '', base_level=2)
        assert not any('DATE' in ln for ln in lines), f'DATE must be absent: {lines}'

    def test_builder_person_level_uses_base_1(self):
        """For person-level citations (base_level=1), QUAY → level 2 and DATE → level 3."""
        from serve_viz import _build_citation_lines
        lines = _build_citation_lines(
            '@S1@', '', '', '', base_level=1, quay='2', date='1900',
        )
        assert '1 SOUR @S1@' == lines[0]
        assert '2 QUAY 2' in lines
        assert '2 DATA' in lines
        assert '3 DATE 1900' in lines

    # -------------------------------------------------------------------
    # /api/add_citation accepts QUAY + DATE on INDI events
    # -------------------------------------------------------------------

    def test_add_citation_writes_quay_and_date_on_indi_event(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0',
            'page': 'p. 1', 'text': '', 'note': '',
            'quay': '3', 'date': '14 MAR 1990',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 QUAY 3' in text
        assert '4 DATE 14 MAR 1990' in text

    def test_add_citation_normalizes_date(self, live_server):
        """`/api/add_citation` runs DATE through the same normalizer used for event dates."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0',
            'page': '', 'text': '', 'note': '',
            'date': '1814-05-21',
        })
        text = _ged_text(ged)
        assert '4 DATE 21 MAY 1814' in text, f'expected normalized date in {text}'

    def test_add_citation_rejects_invalid_quay(self, live_server):
        import urllib.error
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        try:
            post('/api/add_citation', {
                'xref': '@I1@', 'sour_xref': sour_xref,
                'fact_key': 'BIRT:0',
                'page': '', 'text': '', 'note': '',
                'quay': '7',
            })
            assert False, 'Should have raised on QUAY=7'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_add_citation_rejects_invalid_date(self, live_server):
        import urllib.error
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        try:
            post('/api/add_citation', {
                'xref': '@I1@', 'sour_xref': sour_xref,
                'fact_key': 'BIRT:0',
                'page': '', 'text': '', 'note': '',
                'date': 'banana',
            })
            assert False, 'Should have raised on invalid DATE'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    # -------------------------------------------------------------------
    # /api/edit_citation round-trips QUAY + DATE
    # -------------------------------------------------------------------

    def test_edit_citation_adds_quay_and_date(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 1', 'text': '', 'note': '',
        })
        resp = post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 1', 'text': '', 'note': '',
            'quay': '2', 'date': '1990',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 QUAY 2' in text
        assert '4 DATE 1990' in text

    def test_edit_citation_clears_quay_and_date(self, live_server):
        """Setting QUAY/DATE to '' on edit must remove the corresponding lines."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 1', 'text': '', 'note': '',
            'quay': '3', 'date': '1990',
        })
        post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 1', 'text': '', 'note': '',
            'quay': '', 'date': '',
        })
        text = _ged_text(ged)
        assert '3 QUAY' not in text
        assert 'DATE 1990' not in text

    def test_edit_citation_returns_quay_and_date_in_people_payload(self, live_server):
        """Refreshed people payload exposes c.quay and c.date for the client to display."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@I1@', 'sour_xref': sour_xref,
            'fact_key': 'BIRT:0', 'page': 'p. 1', 'text': '', 'note': '',
        })
        resp = post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
            'page': 'p. 1', 'text': '', 'note': '',
            'quay': '3', 'date': '1990',
        })
        birt = next(e for e in resp['people']['@I1@']['events'] if e['tag'] == 'BIRT')
        cite = birt['citations'][0]
        assert cite.get('quay') == '3', f'expected quay=3 in refreshed citation, got {cite}'
        assert cite.get('date') == '1990', f'expected date=1990 in refreshed citation, got {cite}'

    # -------------------------------------------------------------------
    # FAM (MARR/DIV) parity — same flow for FAM events
    # -------------------------------------------------------------------

    def test_add_citation_writes_quay_and_date_on_fam_marr(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0',
            'page': 'p.12', 'text': '', 'note': '',
            'quay': '3', 'date': '21 MAY 1814',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 QUAY 3' in text
        assert '4 DATE 21 MAY 1814' in text

    def test_edit_fam_citation_round_trips_quay_and_date_in_payload(self, live_server):
        """Both spouses' refreshed payloads include the new quay/date on the FAM MARR citation."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.1', 'text': '', 'note': '',
        })
        resp = post('/api/edit_citation', {
            'xref': '@F5@', 'citation_key': 'MARR:0:0',
            'page': 'p.1', 'text': '', 'note': '',
            'quay': '2', 'date': '1814',
        })
        for spouse in ('@I1@', '@I12@'):
            marr = next(e for e in resp['people'][spouse]['events'] if e['tag'] == 'MARR')
            cite = next(c for c in marr['citations'] if c.get('sourceXref') == sour_xref)
            assert cite.get('quay') == '2', f'{spouse} MARR citation missing quay; got {cite}'
            assert cite.get('date') == '1814', f'{spouse} MARR citation missing date; got {cite}'


# ===========================================================================
# /api/delete_citation
# ===========================================================================

class TestDeleteCitationEndpoint:
    def _setup_citation(self, post, xref='@I1@', fact_key='BIRT:0'):
        sour_xref = post('/api/add_source', {
            'titl': 'Test Source', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']
        post('/api/add_citation', {
            'xref': xref, 'sour_xref': sour_xref,
            'fact_key': fact_key, 'page': 'p. 1', 'text': '', 'note': '',
        })
        return sour_xref

    def test_removes_sour_block_from_fact(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._setup_citation(post)
        resp = post('/api/delete_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert f'2 SOUR {sour_xref}' not in text
        assert '3 PAGE p. 1' not in text

    def test_person_level_citation_removed(self, live_server):
        """Deleting a person-level citation (SOUR:0) removes 1 SOUR block."""
        ged, post, _, _ = live_server
        sour_xref = post('/api/add_source', {
            'titl': 'T', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']
        post('/api/add_citation', {
            'xref': '@I2@', 'sour_xref': sour_xref,
            'fact_key': None, 'page': 'p. 1', 'text': '', 'note': '',
        })
        resp = post('/api/delete_citation', {
            'xref': '@I2@', 'citation_key': 'SOUR:0',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert f'1 SOUR {sour_xref}' not in text

    def test_missing_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/delete_citation', {'citation_key': 'BIRT:0:0'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        self._setup_citation(post)
        bak = ged.with_suffix('.ged.bak')
        bak.unlink(missing_ok=True)
        post('/api/delete_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
        })
        assert bak.exists()

    def test_returns_people_without_deleted_citation(self, live_server):
        """Response must include a refreshed `people` dict so the client can
        update PEOPLE[xref] after a citation is deleted."""
        ged, post, _, _ = live_server
        sour_xref = self._setup_citation(post)
        resp = post('/api/delete_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:0',
        })
        assert resp.get('ok') is True
        assert 'people' in resp, 'response must include refreshed people payload'
        people = resp['people']
        assert '@I1@' in people
        birt = next(e for e in people['@I1@']['events'] if e['tag'] == 'BIRT')
        assert not any(
            (c.get('sourceXref') == sour_xref) or (c.get('sour_xref') == sour_xref)
            for c in birt.get('citations', [])
        ), 'deleted citation must not be in refreshed BIRT.citations'

    def test_delete_middle_citation_leaves_others_intact(self, live_server):
        """Delete citation #1 of 3; citations #0 and (former #2, now #1) survive."""
        ged, post, _, _ = live_server
        sour_xref = post('/api/add_source', {
            'titl': 'S', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']
        for page in ('p.A', 'p.B', 'p.C'):
            post('/api/add_citation', {
                'xref': '@I1@', 'sour_xref': sour_xref,
                'fact_key': 'BIRT:0', 'page': page, 'text': '', 'note': '',
            })
        # Delete the middle citation (index 1)
        resp = post('/api/delete_citation', {'xref': '@I1@', 'citation_key': 'BIRT:0:1'})
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 PAGE p.A' in text, 'first citation must survive'
        assert '3 PAGE p.B' not in text, 'deleted citation must be gone'
        assert '3 PAGE p.C' in text, 'third citation must survive'

    def test_delete_middle_then_edit_new_index(self, live_server):
        """After deleting citation #1, the former #2 becomes #1 and is still editable."""
        ged, post, _, _ = live_server
        sour_xref = post('/api/add_source', {
            'titl': 'S', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']
        for page in ('p.A', 'p.B', 'p.C'):
            post('/api/add_citation', {
                'xref': '@I1@', 'sour_xref': sour_xref,
                'fact_key': 'BIRT:0', 'page': page, 'text': '', 'note': '',
            })
        post('/api/delete_citation', {'xref': '@I1@', 'citation_key': 'BIRT:0:1'})
        # Former p.C is now at index 1
        resp = post('/api/edit_citation', {
            'xref': '@I1@', 'citation_key': 'BIRT:0:1',
            'page': 'p.C-edited', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '3 PAGE p.C-edited' in text
        assert '3 PAGE p.C' not in text or 'p.C-edited' in text  # old value gone


# ===========================================================================
# /api/add_citation and /api/delete_citation on FAM records (MARR/DIV)
# ===========================================================================

class TestFamCitationEndpoints:
    """Citation endpoints must accept @F..@ xrefs and operate on MARR/DIV events
    living in FAM blocks, not INDI blocks."""

    def _add_source(self, post):
        return post('/api/add_source', {
            'titl': 'Marriage Register', 'auth': '', 'publ': '', 'repo': '', 'note': '',
        })['xref']

    def test_add_citation_to_fam_marr_writes_sour_under_marr(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.12', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        # The new SOUR line must sit inside @F5@'s MARR block, at level 2.
        lines = text.splitlines()
        in_f5 = False
        in_marr = False
        found = False
        for ln in lines:
            if ln.startswith('0 @F5@ FAM'):
                in_f5 = True; continue
            if in_f5 and ln.startswith('0 '):
                break
            if in_f5 and ln == '1 MARR':
                in_marr = True; continue
            if in_marr and ln.startswith('1 '):
                in_marr = False
            if in_marr and ln == f'2 SOUR {sour_xref}':
                found = True
        assert found, f'2 SOUR {sour_xref} not found inside @F5@\'s MARR block'
        assert '3 PAGE p.12' in text

    def test_add_citation_response_refreshes_both_spouses(self, live_server):
        """Adding a MARR citation on @F5@ must refresh both @I1@ and @I12@ in the
        response so each spouse's panel shows the new citation count."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        resp = post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.12', 'text': '', 'note': '',
        })
        assert 'people' in resp
        assert '@I1@' in resp['people']
        assert '@I12@' in resp['people']
        for spouse in ('@I1@', '@I12@'):
            marr = next(e for e in resp['people'][spouse]['events'] if e['tag'] == 'MARR')
            assert any(c.get('sourceXref') == sour_xref for c in marr.get('citations', [])), \
                f'MARR citation not reflected in refreshed {spouse}.events'

    def test_delete_fam_marr_citation_removes_sour_block(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.12', 'text': '', 'note': '',
        })
        resp = post('/api/delete_citation', {
            'xref': '@F5@', 'citation_key': 'MARR:0:0',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert f'2 SOUR {sour_xref}' not in text
        assert '3 PAGE p.12' not in text

    def test_delete_fam_response_refreshes_both_spouses(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.12', 'text': '', 'note': '',
        })
        resp = post('/api/delete_citation', {
            'xref': '@F5@', 'citation_key': 'MARR:0:0',
        })
        assert '@I1@' in resp.get('people', {})
        assert '@I12@' in resp.get('people', {})
        for spouse in ('@I1@', '@I12@'):
            marr = next(e for e in resp['people'][spouse]['events'] if e['tag'] == 'MARR')
            assert not any(c.get('sourceXref') == sour_xref for c in marr.get('citations', [])), \
                f'deleted citation still appears on {spouse}.MARR'

    def test_invalid_fam_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        sour_xref = self._add_source(post)
        try:
            post('/api/add_citation', {
                'xref': '@F9999@', 'sour_xref': sour_xref,
                'fact_key': 'MARR:0', 'page': '', 'text': '', 'note': '',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_add_citation_to_fam_without_marr_tag_creates_marr_then_writes_sour(self, live_server):
        """Adding a citation to a FAM with no 1 MARR tag (synthetic placeholder) must
        auto-create the bare MARR tag and write the SOUR under it — not return 400."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        # @F1@ has HUSB @I2@ and WIFE @I3@ but no 1 MARR tag in the fixture.
        resp = post('/api/add_citation', {
            'xref': '@F1@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.7', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        lines = text.splitlines()
        in_f1 = False
        in_marr = False
        found_sour = False
        for ln in lines:
            if ln.startswith('0 @F1@ FAM'):
                in_f1 = True; continue
            if in_f1 and ln.startswith('0 '):
                break
            if in_f1 and ln == '1 MARR':
                in_marr = True; continue
            if in_marr and ln.startswith('1 '):
                in_marr = False
            if in_marr and ln == f'2 SOUR {sour_xref}':
                found_sour = True
        assert found_sour, f'2 SOUR {sour_xref} not found inside @F1@\'s MARR block'
        assert '3 PAGE p.7' in text

    def test_edit_citation_updates_url(self, live_server):
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.1', 'text': '', 'note': '',
            'url': 'https://old.example.com',
        })
        resp = post('/api/edit_citation', {
            'xref': '@F5@', 'citation_key': 'MARR:0:0',
            'page': 'p.1', 'text': '', 'note': '',
            'url': 'https://new.example.com',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '4 WWW https://new.example.com' in text
        assert 'https://old.example.com' not in text

    def test_edit_fam_response_refreshes_both_spouses(self, live_server):
        """Editing a MARR citation on @F5@ must refresh both @I1@ and @I12@ in the
        response so each spouse's panel shows the updated citation."""
        ged, post, _, _ = live_server
        sour_xref = self._add_source(post)
        post('/api/add_citation', {
            'xref': '@F5@', 'sour_xref': sour_xref,
            'fact_key': 'MARR:0', 'page': 'p.1', 'text': '', 'note': '',
        })
        resp = post('/api/edit_citation', {
            'xref': '@F5@', 'citation_key': 'MARR:0:0',
            'page': 'p.99', 'text': '', 'note': '',
        })
        assert resp.get('ok') is True
        assert 'people' in resp
        assert '@I1@' in resp['people']
        assert '@I12@' in resp['people']
        for spouse in ('@I1@', '@I12@'):
            marr = next(e for e in resp['people'][spouse]['events'] if e['tag'] == 'MARR')
            assert any(c.get('page') == 'p.99' for c in marr.get('citations', [])), \
                f'updated page not reflected in refreshed {spouse}.MARR.citations'


# ===========================================================================
# /api/add_person
# ===========================================================================

class TestAddPersonEndpoint:
    def test_child_of_creates_new_indi(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Lucy', 'surn': 'Smith', 'sex': 'F',
            'birth_year': '2000',
            'rel_type': 'child_of', 'rel_xref': '@I2@',
        })
        assert 'xref' in resp
        xref = resp['xref']
        text = _ged_text(ged)
        assert f'0 {xref} INDI' in text
        assert '1 NAME Lucy /Smith/' in text

    def test_child_of_adds_famc_link(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Lucy', 'surn': 'Smith', 'sex': 'F',
            'birth_year': '2000',
            'rel_type': 'child_of', 'rel_xref': '@I2@',
        })
        xref = resp['xref']
        text = _ged_text(ged)
        # New INDI should have FAMC link
        assert '1 FAMC' in text
        # The family that @I2@ belongs to should have a CHIL link to the new person
        assert f'1 CHIL {xref}' in text

    def test_birth_year_written(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_person', {
            'given': 'Ted', 'surn': 'Jones', 'sex': 'M',
            'birth_year': '1975',
            'rel_type': 'spouse_of', 'rel_xref': '@I3@',
        })
        text = _ged_text(ged)
        assert '2 DATE 1975' in text

    def test_spouse_of_creates_fam(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Ted', 'surn': 'Jones', 'sex': 'M',
            'birth_year': '',
            'rel_type': 'spouse_of', 'rel_xref': '@I3@',
        })
        xref = resp['xref']
        text = _ged_text(ged)
        # A FAM record should reference both
        assert '@F' in text
        assert f'1 HUSB {xref}' in text or f'1 WIFE {xref}' in text

    def test_sibling_of_adds_to_same_fam(self, live_server):
        """New sibling of @I1@ (FAMC @F1@) should be added as CHIL to @F1@."""
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Tom', 'surn': 'Smith', 'sex': 'M',
            'birth_year': '',
            'rel_type': 'sibling_of', 'rel_xref': '@I1@',
        })
        xref = resp['xref']
        text = _ged_text(ged)
        # @F1@ already has @I1@ as a child — new INDI should also appear as CHIL
        assert f'1 CHIL {xref}' in text

    def test_missing_given_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/add_person', {
                'surn': 'Smith', 'sex': 'M', 'birth_year': '',
                'rel_type': 'child_of', 'rel_xref': '@I2@',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_missing_rel_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/add_person', {
                'given': 'Tom', 'surn': 'Smith', 'sex': 'M',
                'birth_year': '', 'rel_type': 'child_of',
            })
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_person', {
            'given': 'Lucy', 'surn': 'Smith', 'sex': 'F',
            'birth_year': '', 'rel_type': 'child_of', 'rel_xref': '@I2@',
        })
        assert ged.with_suffix('.ged.bak').exists()

    def test_child_of_uses_existing_fam_when_other_parent_matches(self, live_server):
        """Adding a child of @I1@ with other_parent_xref=@I12@ should reuse @F5@
        (the existing FAM with both as parents), not create a new FAM."""
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Kid', 'surn': 'Davis', 'sex': 'M',
            'birth_year': '2018',
            'rel_type': 'child_of', 'rel_xref': '@I1@',
            'other_parent_xref': '@I12@',
        })
        new_xref = resp['xref']
        text = _ged_text(ged)
        # The existing @F5@ should now have the new child
        f5_start = text.index('0 @F5@ FAM')
        f5_end_candidates = [i for i in range(f5_start, len(text)) if text.startswith('\n0 ', i)]
        f5_end = f5_end_candidates[0] if f5_end_candidates else len(text)
        f5_block = text[f5_start:f5_end]
        assert f'1 CHIL {new_xref}' in f5_block
        # No new FAM should have been created for this case
        assert text.count('0 @F') == 7  # F1..F7 only

    def test_child_of_creates_new_fam_when_other_parent_has_no_matching_fam(self, live_server):
        """Adding a child of @I1@ with other_parent_xref=@I2@ (James, who has no
        FAM with Rose) should create a new FAM containing both as parents."""
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Love', 'surn': 'Child', 'sex': 'F',
            'birth_year': '1991',
            'rel_type': 'child_of', 'rel_xref': '@I1@',
            'other_parent_xref': '@I2@',
        })
        new_xref = resp['xref']
        text = _ged_text(ged)
        # A new FAM should exist containing both @I1@ (WIFE) and @I2@ (HUSB)
        # and the new child as CHIL
        assert text.count('0 @F') == 8  # one new FAM
        # Locate the new FAM and confirm both parents + child
        fam_lines = [l for l in text.splitlines() if l.startswith('0 @F')]
        new_fam = fam_lines[-1].split()[1]
        fam_start = text.index(f'0 {new_fam} FAM')
        fam_end_candidates = [i for i in range(fam_start, len(text)) if text.startswith('\n0 ', i)]
        fam_end = fam_end_candidates[0] if fam_end_candidates else len(text)
        fam_block = text[fam_start:fam_end]
        assert '1 HUSB @I2@' in fam_block
        assert '1 WIFE @I1@' in fam_block
        assert f'1 CHIL {new_xref}' in fam_block

    def test_child_of_empty_other_parent_creates_single_parent_fam(self, live_server):
        """Adding a child of @I1@ with other_parent_xref='' should create a new
        FAM with only Rose as parent (not reuse @F5@)."""
        ged, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Solo', 'surn': 'Kid', 'sex': 'M',
            'birth_year': '1995',
            'rel_type': 'child_of', 'rel_xref': '@I1@',
            'other_parent_xref': '',
        })
        new_xref = resp['xref']
        text = _ged_text(ged)
        # A new FAM should exist
        assert text.count('0 @F') == 8
        # The new FAM should contain only @I1@ as parent + new child
        fam_lines = [l for l in text.splitlines() if l.startswith('0 @F')]
        new_fam = fam_lines[-1].split()[1]
        fam_start = text.index(f'0 {new_fam} FAM')
        fam_end_candidates = [i for i in range(fam_start, len(text)) if text.startswith('\n0 ', i)]
        fam_end = fam_end_candidates[0] if fam_end_candidates else len(text)
        fam_block = text[fam_start:fam_end]
        assert '1 WIFE @I1@' in fam_block
        assert '1 HUSB' not in fam_block
        assert f'1 CHIL {new_xref}' in fam_block
        # @F5@ should NOT have the new child
        f5_start = text.index('0 @F5@ FAM')
        f5_end_candidates = [i for i in range(f5_start, len(text)) if text.startswith('\n0 ', i)]
        f5_end = f5_end_candidates[0] if f5_end_candidates else len(text)
        f5_block = text[f5_start:f5_end]
        assert f'1 CHIL {new_xref}' not in f5_block

    def test_response_includes_ok_and_people_dict(self, live_server):
        """Response should include ok=True and a people dict so the UI can refresh
        without a full page reload."""
        _, post, _, _ = live_server
        resp = post('/api/add_person', {
            'given': 'Lucy', 'surn': 'Smith', 'sex': 'F',
            'birth_year': '2000',
            'rel_type': 'child_of', 'rel_xref': '@I2@',
        })
        assert resp.get('ok') is True
        new_xref = resp['xref']
        people = resp.get('people')
        assert isinstance(people, dict)
        assert '@I2@' in people
        assert new_xref in people


# ===========================================================================
# /api/change_parent
# ===========================================================================

class TestChangeParentEndpoint:
    """Change or remove one of a child's parents.

    Fixture: Rose (@I1@) has FAMC @F1@ (HUSB @I2@ James, WIFE @I3@ Clara).
    Alice (@I11@) is also CHIL of @F1@ — must remain after Rose moves.
    """

    def test_replace_father_creates_new_fam_when_no_matching_pair(self, live_server):
        """Change Rose's father from @I2@ to @I4@ Patrick; no FAM pairs Patrick+Clara,
        so a new FAM with @I4@+@I3@ is created and Rose's FAMC updated."""
        ged, post, _, _ = live_server
        resp = post('/api/change_parent', {
            'xref': '@I1@',
            'current_parent_xref': '@I2@',
            'new_parent_xref': '@I4@',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        # A new FAM must exist with Patrick + Clara + Rose
        fam_blocks = _fam_blocks(text)
        new_fam = next((fx for fx, body in fam_blocks.items()
                        if '1 HUSB @I4@' in body and '1 WIFE @I3@' in body
                        and '1 CHIL @I1@' in body), None)
        assert new_fam is not None, 'expected a new FAM with Patrick+Clara+Rose'
        # Rose's FAMC should point to the new FAM, not @F1@
        rose_block = _indi_block(text, '@I1@')
        assert f'1 FAMC {new_fam}' in rose_block
        assert '1 FAMC @F1@' not in rose_block
        # @F1@ still exists, Alice still CHIL, Rose no longer CHIL
        f1_body = fam_blocks['@F1@']
        assert '1 CHIL @I11@' in f1_body
        assert '1 CHIL @I1@' not in f1_body

    def test_delete_father_moves_child_to_single_parent_fam(self, live_server):
        """Delete Rose's father: move Rose to a new FAM with only Clara."""
        ged, post, _, _ = live_server
        resp = post('/api/change_parent', {
            'xref': '@I1@',
            'current_parent_xref': '@I2@',
            'new_parent_xref': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        fam_blocks = _fam_blocks(text)
        new_fam = next((fx for fx, body in fam_blocks.items()
                        if fx != '@F1@' and '1 WIFE @I3@' in body
                        and '1 HUSB' not in body
                        and '1 CHIL @I1@' in body), None)
        assert new_fam is not None, 'expected a new single-parent FAM with Clara'
        rose_block = _indi_block(text, '@I1@')
        assert f'1 FAMC {new_fam}' in rose_block
        # @F1@ still intact with Alice
        assert '1 CHIL @I11@' in fam_blocks['@F1@']

    def test_delete_mother_moves_child_to_single_parent_fam(self, live_server):
        """Delete Rose's mother: move Rose to a new FAM with only James."""
        ged, post, _, _ = live_server
        resp = post('/api/change_parent', {
            'xref': '@I1@',
            'current_parent_xref': '@I3@',
            'new_parent_xref': '',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        fam_blocks = _fam_blocks(text)
        new_fam = next((fx for fx, body in fam_blocks.items()
                        if fx != '@F1@' and '1 HUSB @I2@' in body
                        and '1 WIFE' not in body
                        and '1 CHIL @I1@' in body), None)
        assert new_fam is not None

    def test_missing_xref_returns_400(self, live_server):
        _, post, _, _ = live_server
        try:
            post('/api/change_parent', {
                'current_parent_xref': '@I2@', 'new_parent_xref': '@I4@',
            })
            assert False, 'should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_current_parent_not_in_famc_returns_400(self, live_server):
        _, post, _, _ = live_server
        try:
            post('/api/change_parent', {
                'xref': '@I1@',
                'current_parent_xref': '@I14@',  # George Cooper — not Rose's parent
                'new_parent_xref': '@I4@',
            })
            assert False, 'should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        post('/api/change_parent', {
            'xref': '@I1@',
            'current_parent_xref': '@I2@',
            'new_parent_xref': '@I4@',
        })
        assert ged.with_suffix('.ged.bak').exists()

    def test_response_includes_people_dict(self, live_server):
        _, post, _, _ = live_server
        resp = post('/api/change_parent', {
            'xref': '@I1@',
            'current_parent_xref': '@I2@',
            'new_parent_xref': '@I4@',
        })
        assert isinstance(resp.get('people'), dict)
        assert '@I1@' in resp['people']


def _fam_blocks(text: str) -> dict:
    """Parse GEDCOM text into {fam_xref: body_str} for FAM records."""
    out = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        parts = lines[i].split()
        if len(parts) >= 3 and parts[0] == '0' and parts[2] == 'FAM':
            fx = parts[1]
            j = i + 1
            body = []
            while j < len(lines) and not lines[j].startswith('0 '):
                body.append(lines[j])
                j += 1
            out[fx] = '\n'.join(body)
            i = j
        else:
            i += 1
    return out


def _indi_block(text: str, xref: str) -> str:
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == f'0 {xref} INDI'), None)
    if start is None:
        return ''
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('0 ')), len(lines))
    return '\n'.join(lines[start:end])


# ===========================================================================
# /api/add_godparent
# ===========================================================================

class TestAddGodparentEndpoint:
    def test_asso_rela_written(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '1 ASSO @I4@' in text
        assert '2 RELA Godparent' in text

    def test_asso_within_correct_indi_block(self, live_server):
        """The ASSO must appear before the next level-0 record."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        lines = _ged_text(ged).splitlines()
        indi_start = next(i for i, l in enumerate(lines) if '0 @I1@ INDI' in l)
        indi_end = next(i for i in range(indi_start + 1, len(lines)) if lines[i].startswith('0 '))
        block = '\n'.join(lines[indi_start:indi_end])
        assert '1 ASSO @I4@' in block
        assert '2 RELA Godparent' in block

    def test_missing_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/add_godparent', {'godparent_xref': '@I4@'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_missing_godparent_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/add_godparent', {'xref': '@I1@'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        assert ged.with_suffix('.ged.bak').exists()

    def test_rela_godfather(self, live_server):
        """rela=Godfather should write '2 RELA Godfather'."""
        ged, post, _, _ = live_server
        resp = post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Godfather',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '2 RELA Godfather' in text
        assert '2 RELA Godparent' not in text

    def test_rela_godmother(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Godmother',
        })
        assert resp.get('ok') is True
        assert '2 RELA Godmother' in _ged_text(ged)

    def test_rela_invalid_rejected(self, live_server):
        """Unsupported rela values must be rejected, not silently accepted."""
        ged, post, _, _ = live_server
        original = _ged_text(ged)
        resp = post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Witness',
        })
        assert resp.get('ok') is False
        assert _ged_text(ged) == original

    def test_rela_default_godparent(self, live_server):
        """Omitting rela defaults to Godparent (back-compat)."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        assert '2 RELA Godparent' in _ged_text(ged)

    def test_response_includes_refreshed_people_payload(self, live_server):
        """Client needs fresh PEOPLE data to re-render without a reload."""
        ged, post, _, _ = live_server
        resp = post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Godfather',
        })
        assert resp.get('ok') is True
        people = resp.get('people') or {}
        assert '@I1@' in people, 'subject xref must be present in people payload'
        # At minimum the refreshed payload should carry the basic person fields
        assert 'name' in people['@I1@']
        assert 'events' in people['@I1@']


# ===========================================================================
# /api/delete_godparent
# ===========================================================================

class TestDeleteGodparentEndpoint:
    def _add_godparent(self, post, xref, gp_xref):
        post('/api/add_godparent', {'xref': xref, 'godparent_xref': gp_xref})

    def test_removes_asso_block(self, live_server):
        ged, post, _, _ = live_server
        self._add_godparent(post, '@I1@', '@I4@')
        resp = post('/api/delete_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '1 ASSO @I4@' not in text

    def test_other_asso_records_untouched(self, live_server):
        """Deleting one godparent must not remove other ASSO blocks."""
        ged, post, _, _ = live_server
        self._add_godparent(post, '@I1@', '@I4@')
        self._add_godparent(post, '@I1@', '@I5@')
        post('/api/delete_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        text = _ged_text(ged)
        assert '1 ASSO @I4@' not in text
        assert '1 ASSO @I5@' in text

    def test_missing_xref_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/delete_godparent', {'godparent_xref': '@I4@'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_nonexistent_godparent_returns_400(self, live_server):
        ged, post, _, _ = live_server
        import urllib.error
        try:
            post('/api/delete_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
            assert False, 'Should have raised'
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_creates_backup(self, live_server):
        ged, post, _, _ = live_server
        self._add_godparent(post, '@I1@', '@I4@')
        bak = ged.with_suffix('.ged.bak')
        bak.unlink(missing_ok=True)
        post('/api/delete_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        assert bak.exists()

    def test_removes_godfather_asso(self, live_server):
        """Godfather and Godmother ASSOs must be deletable too, not just Godparent."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Godfather',
        })
        assert '2 RELA Godfather' in _ged_text(ged)
        resp = post('/api/delete_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@',
        })
        assert resp.get('ok') is True
        text = _ged_text(ged)
        assert '1 ASSO @I4@' not in text
        assert '2 RELA Godfather' not in text

    def test_removes_godmother_asso(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I5@', 'rela': 'Godmother',
        })
        resp = post('/api/delete_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I5@',
        })
        assert resp.get('ok') is True
        assert '1 ASSO @I5@' not in _ged_text(ged)

    def test_response_includes_refreshed_people_payload(self, live_server):
        ged, post, _, _ = live_server
        self._add_godparent(post, '@I1@', '@I4@')
        resp = post('/api/delete_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@',
        })
        assert resp.get('ok') is True
        people = resp.get('people') or {}
        assert '@I1@' in people
        assert 'name' in people['@I1@']
        assert 'events' in people['@I1@']

    def test_delete_also_removes_reciprocal_godchild_asso(self, live_server):
        """Deleting a godparent must also remove the reciprocal Godchild ASSO from the godparent's record."""
        ged, post, _, _ = live_server
        self._add_godparent(post, '@I1@', '@I4@')
        post('/api/delete_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        text = _ged_text(ged)
        # Forward ASSO gone
        assert '1 ASSO @I4@' not in text
        # Reciprocal Godchild ASSO gone from @I4@'s block
        lines = text.splitlines()
        i4_start = next(i for i, l in enumerate(lines) if '0 @I4@ INDI' in l)
        i4_end = next(i for i in range(i4_start + 1, len(lines)) if lines[i].startswith('0 '))
        i4_block = '\n'.join(lines[i4_start:i4_end])
        assert 'ASSO @I1@' not in i4_block

    def test_delete_godfather_removes_reciprocal_godchild(self, live_server):
        """Godfather-typed ASSOs also get their reciprocal Godchild removed on delete."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Godfather',
        })
        post('/api/delete_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        lines = _ged_text(ged).splitlines()
        i4_start = next(i for i, l in enumerate(lines) if '0 @I4@ INDI' in l)
        i4_end = next(i for i in range(i4_start + 1, len(lines)) if lines[i].startswith('0 '))
        i4_block = '\n'.join(lines[i4_start:i4_end])
        assert 'ASSO @I1@' not in i4_block


class TestAddGodparentReciprocal:
    """add_godparent must write a reciprocal Godchild ASSO on the godparent's record."""

    def test_reciprocal_godchild_asso_written(self, live_server):
        ged, post, _, _ = live_server
        post('/api/add_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        text = _ged_text(ged)
        assert '1 ASSO @I1@' in text
        assert '2 RELA Godchild' in text

    def test_reciprocal_in_godparent_block(self, live_server):
        """The Godchild ASSO must appear inside @I4@'s INDI block, not @I1@'s."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        lines = _ged_text(ged).splitlines()
        i4_start = next(i for i, l in enumerate(lines) if '0 @I4@ INDI' in l)
        i4_end = next(i for i in range(i4_start + 1, len(lines)) if lines[i].startswith('0 '))
        i4_block = '\n'.join(lines[i4_start:i4_end])
        assert '1 ASSO @I1@' in i4_block
        assert '2 RELA Godchild' in i4_block

    def test_forward_asso_in_child_block(self, live_server):
        """Forward Godparent ASSO must still be in @I1@'s block."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {'xref': '@I1@', 'godparent_xref': '@I4@'})
        lines = _ged_text(ged).splitlines()
        i1_start = next(i for i, l in enumerate(lines) if '0 @I1@ INDI' in l)
        i1_end = next(i for i in range(i1_start + 1, len(lines)) if lines[i].startswith('0 '))
        i1_block = '\n'.join(lines[i1_start:i1_end])
        assert '1 ASSO @I4@' in i1_block
        assert '2 RELA Godparent' in i1_block

    def test_godfather_rela_still_gets_godchild_reciprocal(self, live_server):
        """Godfather-typed ASSO should produce a Godchild reciprocal."""
        ged, post, _, _ = live_server
        post('/api/add_godparent', {
            'xref': '@I1@', 'godparent_xref': '@I4@', 'rela': 'Godfather',
        })
        lines = _ged_text(ged).splitlines()
        i4_start = next(i for i, l in enumerate(lines) if '0 @I4@ INDI' in l)
        i4_end = next(i for i in range(i4_start + 1, len(lines)) if lines[i].startswith('0 '))
        i4_block = '\n'.join(lines[i4_start:i4_end])
        assert '1 ASSO @I1@' in i4_block
        assert '2 RELA Godchild' in i4_block


# ===========================================================================
# Additional regression tests for review-found bugs
# ===========================================================================

class TestEditSourceRecordContinuationLines:
    """edit_source_record must not orphan CONT lines under managed tags."""

    def test_cont_lines_under_note_not_orphaned(self, live_server):
        """A NOTE with a CONT line should be replaced cleanly without leaving
        orphaned CONT lines in the updated block."""
        ged, post, _, _ = live_server
        # Manually insert a SOUR record with a multi-line NOTE
        text = ged.read_text(encoding='utf-8')
        src_block = (
            '0 @S1@ SOUR\n'
            '1 TITL Multi-line Source\n'
            '1 NOTE First line\n'
            '2 CONT Second line\n'
        )
        text = text.replace('0 TRLR', src_block + '0 TRLR')
        ged.write_text(text, encoding='utf-8')

        # Edit the source record — replaces NOTE with new value
        post('/api/edit_source_record', {
            'xref': '@S1@',
            'titl': 'Multi-line Source',
            'auth': '', 'publ': '', 'repo': '',
            'note': 'Replaced note',
        })
        result = _ged_text(ged)
        # Old CONT should be gone
        assert '2 CONT Second line' not in result
        # New NOTE present
        assert '1 NOTE Replaced note' in result
        # No orphaned CONT lines (not preceded by a NOTE/CONC in valid hierarchy)
        lines = result.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith('2 CONT'):
                # The preceding level-1 line should be a text-value tag, not be absent
                prev_l1 = None
                for j in range(i - 1, -1, -1):
                    import re
                    pm = re.match(r'^(\d+)\s', lines[j])
                    if pm:
                        if int(pm.group(1)) < 2:
                            prev_l1 = lines[j]
                            break
                assert prev_l1 is not None, f'Orphaned CONT at line {i}: {ln!r}'


# ===========================================================================
# Change 2a — citation serialisation contract: sourceXref (camelCase)
# ===========================================================================

class TestCitationSerialisationContract:
    """
    Assert that PEOPLE JSON embeds citations with key ``sourceXref`` (camelCase),
    not ``sour_xref`` (snake_case), so the JS panel can resolve source titles.

    Resolution chain:
      SOURCES[PEOPLE[xref].events[0].citations[0].sourceXref].titl  →  non-empty string
    """

    def _setup_ged_with_citation(self, ged_path):
        """
        Inject a SOUR record and a BIRT citation into @I2@'s BIRT event.
        Returns the expected source title.
        """
        text = ged_path.read_text(encoding='utf-8')
        # Add SOUR record before TRLR
        sour_block = (
            '0 @S1@ SOUR\n'
            '1 TITL Civil Registration Birth Record\n'
        )
        # Add citation under @I2@ BIRT
        text = text.replace('1 BIRT\n2 DATE 1960\n', '1 BIRT\n2 DATE 1960\n2 SOUR @S1@\n3 PAGE p. 5\n')
        text = text.replace('0 TRLR', sour_block + '0 TRLR')
        ged_path.write_text(text, encoding='utf-8')
        return 'Civil Registration Birth Record'

    def test_citations_use_sourceXref_key(self, tmp_path):
        """citations[n].sourceXref exists and citations[n].sour_xref does not."""
        import viz_ancestors
        ged = tmp_path / 'contract.ged'
        import shutil
        import pathlib
        shutil.copy(
            str(pathlib.Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'),
            str(ged),
        )
        self._setup_ged_with_citation(ged)
        indis, fams, sources = viz_ancestors.parse_gedcom(str(ged))
        people = viz_ancestors.build_people_json(set(indis.keys()), indis, fams, sources)
        birt_events = [e for e in people['@I2@']['events'] if e['tag'] == 'BIRT']
        assert birt_events, 'Expected a BIRT event for @I2@'
        cites = birt_events[0].get('citations', [])
        assert cites, 'Expected at least one citation on @I2@ BIRT'
        cite = cites[0]
        assert 'sourceXref' in cite, (
            f"Citation must use 'sourceXref' (camelCase); got keys: {list(cite.keys())}"
        )
        assert 'sour_xref' not in cite, (
            "'sour_xref' must not be present in serialised citation"
        )

    def test_source_title_resolves_via_sourceXref(self, tmp_path):
        """SOURCES[citation.sourceXref].titl returns the expected title."""
        import viz_ancestors
        ged = tmp_path / 'contract2.ged'
        import shutil
        import pathlib
        shutil.copy(
            str(pathlib.Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'),
            str(ged),
        )
        expected_title = self._setup_ged_with_citation(ged)
        indis, fams, sources = viz_ancestors.parse_gedcom(str(ged))
        people = viz_ancestors.build_people_json(set(indis.keys()), indis, fams, sources)
        birt_events = [e for e in people['@I2@']['events'] if e['tag'] == 'BIRT']
        cite = birt_events[0]['citations'][0]
        source_xref = cite['sourceXref']
        # Build the SOURCES dict the same way render_html does
        sources_js = {
            xref: {'titl': sour.get('titl') or ''}
            for xref, sour in sources.items()
        }
        resolved_title = sources_js.get(source_xref, {}).get('titl', '')
        assert resolved_title == expected_title, (
            f"Expected title {expected_title!r}, got {resolved_title!r} "
            f"via SOURCES[{source_xref!r}]"
        )

    def test_full_chain_round_trips_through_json(self, tmp_path):
        """
        End-to-end: generate HTML, parse the embedded PEOPLE+SOURCES JSON,
        then verify SOURCES[citation.sourceXref].titl is non-empty.
        """
        import viz_ancestors
        import json as _json
        import re as _re
        ged = tmp_path / 'contract3.ged'
        import shutil
        import pathlib
        shutil.copy(
            str(pathlib.Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'),
            str(ged),
        )
        expected_title = self._setup_ged_with_citation(ged)
        viz_ancestors.viz_ancestors(
            str(ged), '@I2@',
            str(tmp_path / 'out.html'),
        )
        html = (tmp_path / 'out.html').read_text(encoding='utf-8')
        # Extract PEOPLE and SOURCES from the generated JS
        m_people = _re.search(r'const PEOPLE = ({.*?});\n', html, _re.DOTALL)
        m_sources = _re.search(r'const SOURCES = ({.*?});\n', html, _re.DOTALL)
        assert m_people, 'Could not find PEOPLE JSON in generated HTML'
        assert m_sources, 'Could not find SOURCES JSON in generated HTML'
        people = _json.loads(m_people.group(1))
        sources_js = _json.loads(m_sources.group(1))
        birt_events = [e for e in people['@I2@']['events'] if e['tag'] == 'BIRT']
        assert birt_events, 'Expected a BIRT event for @I2@'
        cite = birt_events[0]['citations'][0]
        assert 'sourceXref' in cite, f"Citation key must be 'sourceXref'; got: {list(cite.keys())}"
        resolved_title = sources_js.get(cite['sourceXref'], {}).get('titl', '')
        assert resolved_title == expected_title, (
            f"Full chain failed: expected {expected_title!r}, got {resolved_title!r}"
        )


class TestAddPersonParentOf:
    """add_person with rel_type=parent_of."""

    def test_parent_of_adds_parent_to_existing_family(self, live_server):
        ged, post, _, _ = live_server
        # @I6@ is in @F6@ as a child (FAMC @F6@). @F6@ has only HUSB @I10@ — no WIFE.
        text = _ged_text(ged)
        f6_block = text.split('0 @F6@ FAM')[1].split('\n0 ')[0]
        assert '1 WIFE' not in f6_block  # Confirm no WIFE in @F6@ initially

        # Add a new person as a parent (WIFE) of @I6@
        resp = post('/api/add_person', {
            'given': 'Martha', 'surn': 'Jones', 'sex': 'F',
            'birth_year': '1935',
            'rel_type': 'parent_of', 'rel_xref': '@I6@',
        })
        assert 'xref' in resp
        new_xref = resp['xref']
        result = _ged_text(ged)
        # New INDI created
        assert f'0 {new_xref} INDI' in result
        # WIFE link added to @F6@
        assert f'1 WIFE {new_xref}' in result
        # New INDI has FAMS back-link to @F6@
        assert '1 FAMS @F6@' in result.split(f'0 {new_xref} INDI')[1].split('\n0 ')[0]

    def test_parent_of_returns_400_when_slot_occupied(self, live_server):
        """Adding a second WIFE to a family that already has one should return 400."""
        ged, post, _, _ = live_server
        import urllib.error
        # First add a wife to @F6@ (which starts with only a HUSB)
        post('/api/add_person', {
            'given': 'First', 'surn': 'Wife', 'sex': 'F',
            'birth_year': '', 'rel_type': 'parent_of', 'rel_xref': '@I6@',
        })
        # Now try to add a second wife — should fail with 400
        try:
            post('/api/add_person', {
                'given': 'Second', 'surn': 'Wife', 'sex': 'F',
                'birth_year': '', 'rel_type': 'parent_of', 'rel_xref': '@I6@',
            })
            assert False, 'Expected 400 for duplicate WIFE slot'
        except urllib.error.HTTPError as e:
            assert e.code == 400
