#!/usr/bin/env python3
"""
Dev server: watches viz_ancestors.py for changes, regenerates the HTML,
and serves it on http://localhost:8080/viz.html
"""
import http.server
import os
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


def regenerate(person=None):
    if person is None:
        person = sys.argv[1] if len(sys.argv) > 1 else "@I380071267816@"
    result = subprocess.run(
        ["python3", str(VIZ), str(GED), "--person", person, "-o", str(OUT)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"[rebuilt] {OUT} (person={person})")
    else:
        print(f"[error] {result.stderr.strip()}")


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
        self.send_error(404)

    def log_message(self, fmt, *args):
        pass  # suppress access logs


if __name__ == '__main__':
    regenerate()
    threading.Thread(target=watch, daemon=True).start()
    print(f"Serving on http://localhost:{PORT}/viz.html  (watching viz_ancestors.py for changes)")
    with http.server.HTTPServer(('', PORT), Handler) as httpd:
        httpd.serve_forever()
