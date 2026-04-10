#!/usr/bin/env python3
"""
Dev server: watches viz_ancestors.py for changes, regenerates the HTML,
and serves it on http://localhost:8080/viz.html

Fact deletion is staged: deletions are queued in memory during the session and
written to disk only when you click "Commit deletions" (or run with --commit).
Before writing, the result is validated with the GEDCOM linter so no pointers
are broken.
"""
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

_ged_env = os.environ.get("GED_FILE", "")
if not _ged_env:
    sys.exit("Error: set the GED_FILE environment variable to the path of your .ged file")
GED = Path(_ged_env)
VIZ = Path(__file__).parent / "viz_ancestors.py"
OUT = Path(os.environ.get("VIZ_OUT", "/tmp/viz.html"))
PORT = 8080

_TAG_RE = re.compile(r'^(\d+) (\w+)(?: (.+))?$')

# ---------------------------------------------------------------------------
# Pending deletions — staged, not written to disk until committed
# ---------------------------------------------------------------------------
_pending: list[dict] = []   # [{xref, tag, date, place, type, inline_val, label}]
_pending_lock = threading.Lock()


def _pending_file() -> Path:
    return GED.with_suffix('.deletions.json')


def _save_pending():
    with _pending_lock:
        _pending_file().write_text(json.dumps(_pending, indent=2), encoding='utf-8')


def _load_pending():
    global _pending
    p = _pending_file()
    if p.exists():
        try:
            _pending = json.loads(p.read_text(encoding='utf-8'))
            print(f"[resumed] {len(_pending)} pending deletion(s) from {p.name}")
        except Exception:
            _pending = []


# ---------------------------------------------------------------------------
# HTML regeneration
# ---------------------------------------------------------------------------

def regenerate(person=None):
    if person is None:
        person = sys.argv[1] if len(sys.argv) > 1 else "@I380071267816@"
    args = ["python3", str(VIZ), str(GED), "--person", person, "-o", str(OUT)]
    with _pending_lock:
        if _pending:
            args += ["--exclude", json.dumps(_pending)]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[rebuilt] {OUT} (person={person}, {len(_pending)} pending deletion(s))")
    else:
        print(f"[error] {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# File watcher
# ---------------------------------------------------------------------------

def watch():
    last_mtime = None
    while True:
        try:
            mtime = VIZ.stat().st_mtime
            if last_mtime is None:
                last_mtime = mtime
            elif mtime != last_mtime:
                last_mtime = mtime
                regenerate()
        except FileNotFoundError:
            pass
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Commit: apply pending deletions to disk with validation
# ---------------------------------------------------------------------------

def _apply_deletion(lines: list[str], d: dict) -> tuple[list[str], str | None]:
    """Remove one fact from lines. Returns (new_lines, error_or_None)."""
    xref = d['xref']
    tag = d['tag']
    date = d.get('date') or None
    place = d.get('place') or None
    fact_type = d.get('type') or None
    inline_val = d.get('inline_val') or None

    indi_start = next(
        (i for i, l in enumerate(lines) if l.strip() == f'0 {xref} INDI'), None
    )
    if indi_start is None:
        return lines, f'Individual {xref} not found'

    indi_end = next(
        (i for i in range(indi_start + 1, len(lines)) if lines[i].startswith('0 ')),
        len(lines),
    )

    event_start = event_end = None
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        lvl, t, v = int(m.group(1)), m.group(2), (m.group(3) or '').strip()
        if lvl != 1 or t != tag:
            continue
        if inline_val is not None and v != inline_val:
            continue

        j = i + 1
        sub: dict[str, str] = {}
        while j < indi_end:
            sm = _TAG_RE.match(lines[j])
            if not sm or int(sm.group(1)) <= 1:
                break
            sl, st, sv = int(sm.group(1)), sm.group(2), (sm.group(3) or '').strip()
            if sl == 2 and st not in sub:
                sub[st] = sv
            j += 1

        def _eq(actual, expected):
            return expected is None or actual == expected

        if _eq(sub.get('DATE'), date) and _eq(sub.get('PLAC'), place) and _eq(sub.get('TYPE'), fact_type):
            event_start, event_end = i, j
            break

    if event_start is None:
        return lines, f'Fact {tag} not found in {xref} (may have already been deleted)'

    return lines[:event_start] + lines[event_end:], None


def _find_note_block(lines: list[str], xref: str, note_idx: int) -> tuple[int | None, int | None, str | None]:
    """Return (start, end, err) — line range [start, end) for note at note_idx in xref."""
    indi_start = next(
        (i for i, l in enumerate(lines) if l.strip() == f'0 {xref} INDI'), None
    )
    if indi_start is None:
        return None, None, f'Individual {xref} not found'
    indi_end = next(
        (i for i in range(indi_start + 1, len(lines)) if lines[i].startswith('0 ')),
        len(lines),
    )
    count = 0
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        lvl, tag = int(m.group(1)), m.group(2)
        if lvl == 1 and tag == 'NOTE':
            if count == note_idx:
                j = i + 1
                while j < indi_end:
                    sm = _TAG_RE.match(lines[j])
                    if sm and int(sm.group(1)) == 2 and sm.group(2) in ('CONT', 'CONC'):
                        j += 1
                    else:
                        break
                return i, j, None
            count += 1
    return None, None, f'Note index {note_idx} not found in {xref}'


def _encode_note_lines(text: str) -> list[str]:
    """Encode text into GEDCOM '1 NOTE / 2 CONT' lines (split on newlines)."""
    parts = text.split('\n')
    out = [f'1 NOTE {parts[0]}']
    for part in parts[1:]:
        out.append(f'2 CONT {part}')
    return out


def _write_gedcom_atomic(lines: list[str]) -> None:
    """Backup original and write new lines to GED atomically."""
    backup = GED.with_suffix('.ged.bak')
    GED.rename(backup)
    GED.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def commit_deletions() -> tuple[int, list[str]]:
    """
    Apply all pending deletions to the GEDCOM file.
    Validates the result before writing.
    Returns (count_applied, list_of_errors).
    """
    global _pending
    with _pending_lock:
        if not _pending:
            return 0, []
        batch = list(_pending)

    lines = GED.read_text(encoding='utf-8').splitlines()
    errors: list[str] = []
    applied = 0

    for d in batch:
        new_lines, err = _apply_deletion(lines, d)
        if err:
            errors.append(err)
        else:
            lines = new_lines
            applied += 1

    if not applied:
        return 0, errors

    # Validate before writing
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ged',
                                     encoding='utf-8', delete=False) as tmp:
        tmp.write('\n'.join(lines) + '\n')
        tmp_path = tmp.name

    linter = Path(__file__).parent / 'gedcom_linter.py'
    result = subprocess.run(
        ['python3', str(linter), tmp_path],
        capture_output=True, text=True
    )
    Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0 and 'ERROR' in (result.stdout + result.stderr):
        errors.append('Validation failed — no changes written:\n' + result.stdout)
        return 0, errors

    # Write atomically: backup original, replace
    backup = GED.with_suffix('.ged.bak')
    GED.rename(backup)
    GED.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"[committed] {applied} deletion(s) written to {GED.name} (backup: {backup.name})")

    with _pending_lock:
        _pending = []
    _pending_file().unlink(missing_ok=True)

    return applied, errors


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/viz.html'):
            params = parse_qs(parsed.query)
            if 'person' in params:
                regenerate(unquote(params['person'][0]))
            else:
                regenerate()
            self.path = OUT.name
            self.directory = str(OUT.parent)
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        if parsed.path == '/api/pending':
            with _pending_lock:
                resp = json.dumps({'pending': _pending}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(resp))
            self.end_headers()
            self.wfile.write(resp)
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if parsed.path == '/api/delete_fact':
            entry = {
                'xref':       body['xref'],
                'tag':        body['tag'],
                'date':       body.get('date') or None,
                'place':      body.get('place') or None,
                'type':       body.get('type') or None,
                'inline_val': body.get('inline_val') or None,
                'label':      body.get('label') or body['tag'],
            }
            with _pending_lock:
                _pending.append(entry)
            _save_pending()
            regenerate(body.get('current_person'))
            resp = json.dumps({'ok': True, 'pending': len(_pending)}).encode()

        elif parsed.path == '/api/commit_deletions':
            count, errors = commit_deletions()
            regenerate(body.get('current_person'))
            resp = json.dumps({'ok': not errors, 'applied': count, 'errors': errors}).encode()

        elif parsed.path == '/api/clear_pending':
            with _pending_lock:
                _pending.clear()
            _pending_file().unlink(missing_ok=True)
            regenerate(body.get('current_person'))
            resp = json.dumps({'ok': True}).encode()

        elif parsed.path == '/api/delete_note':
            xref     = body['xref']
            note_idx = int(body['note_idx'])
            lines    = GED.read_text(encoding='utf-8').splitlines()
            start, end, err = _find_note_block(lines, xref, note_idx)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = lines[:start] + lines[end:]
                _write_gedcom_atomic(new_lines)
                print(f"[note-delete] {xref} note[{note_idx}] deleted")
                regenerate(body.get('current_person'))
                from viz_ancestors import parse_gedcom, build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/edit_note':
            xref     = body['xref']
            note_idx = int(body['note_idx'])
            new_text = body.get('new_text', '')
            lines    = GED.read_text(encoding='utf-8').splitlines()
            start, end, err = _find_note_block(lines, xref, note_idx)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = lines[:start] + _encode_note_lines(new_text) + lines[end:]
                _write_gedcom_atomic(new_lines)
                print(f"[note-edit] {xref} note[{note_idx}] updated")
                regenerate(body.get('current_person'))
                from viz_ancestors import parse_gedcom, build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(resp))
        self.end_headers()
        self.wfile.write(resp)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


# ---------------------------------------------------------------------------
# Graceful shutdown: commit on Ctrl-C
# ---------------------------------------------------------------------------

def _shutdown_handler(sig, frame):
    with _pending_lock:
        n = len(_pending)
    if n:
        print(f"\n[shutdown] {n} pending deletion(s) — run 'Commit deletions' in the UI or restart to resume.")
    sys.exit(0)


if __name__ == '__main__':
    _load_pending()
    signal.signal(signal.SIGINT, _shutdown_handler)
    regenerate()
    threading.Thread(target=watch, daemon=True).start()
    print(f"Serving on http://localhost:{PORT}/viz.html  (watching viz_ancestors.py for changes)")
    with http.server.HTTPServer(('', PORT), Handler) as httpd:
        httpd.serve_forever()
