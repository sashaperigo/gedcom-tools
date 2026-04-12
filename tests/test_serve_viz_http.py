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
        import tempfile, pathlib
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
            'updates': {'DATE': '1900-01-05'},
        })
        assert resp['ok'] is False
        assert 'error' in resp
        assert _ged_text(ged) == original  # file must be unchanged


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
            'fields': {'DATE': '1985-06-15'},
        })
        assert resp['ok'] is False
        assert _ged_text(ged) == original

    def test_unknown_xref_returns_error(self, live_server):
        ged, post, _, _ = live_server
        resp = post('/api/add_event', {
            'xref': '@NOBODY@', 'tag': 'RESI', 'fields': {},
        })
        assert resp['ok'] is False


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
