#!/usr/bin/env python3
"""
Dev server: watches viz_ancestors.py for changes, regenerates the HTML,
and serves it on http://localhost:8080/viz.html
"""
import http.server
import subprocess
import sys
import threading
import time
from pathlib import Path

GED = Path("/Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged")
VIZ = Path(__file__).parent / "viz_ancestors.py"
OUT = Path("/tmp/viz.html")
PORT = 8080


def regenerate():
    person = sys.argv[1] if len(sys.argv) > 1 else "@I382535447943@"
    result = subprocess.run(
        ["python3", str(VIZ), str(GED), "--person", person, "-o", str(OUT)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"[rebuilt] {OUT}")
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
        if self.path in ('/', '/viz.html'):
            self.path = '/viz.html'
            self.directory = '/tmp'
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
