#!/usr/bin/env python3
"""
clean_notexml.py — Strip <notexml> wrappers from GEDCOM NOTE fields.

Geneanet exports notes wrapped in a proprietary <notexml> format:

  Raw XML:
    1 NOTE <notexml><line>text one</line><line>text two</line></notexml>

  HTML-encoded (also common):
    1 NOTE &lt;notexml&gt;<line>https://example.com</line>&lt;/notexml&gt;

Both forms are converted to standard GEDCOM NOTE + CONT lines:

    1 NOTE text one
    2 CONT text two

CONC continuation lines that were part of a notexml block are consumed
during reconstruction and replaced by the clean CONT output.

Usage:
  python clean_notexml.py yourfile.ged
  python clean_notexml.py yourfile.ged --output clean.ged
  python clean_notexml.py yourfile.ged --dry-run
"""

import argparse
import html
import os
import re
import sys

from gedcom_io import write_lines

_NOTEXML_RE = re.compile(r'<notexml>(.*?)</notexml>', re.DOTALL)
_LINE_RE = re.compile(r'<line>(.*?)</line>', re.DOTALL)
_NOTE_RE = re.compile(r'^(\d+) NOTE (.*)$', re.DOTALL)
_CONC_RE = re.compile(r'^(\d+) CONC (.*)$', re.DOTALL)


def _has_notexml(text: str) -> bool:
    return '<notexml>' in text or '&lt;notexml&gt;' in text


def _reconstruct_note(lines: list[str], start: int) -> tuple[int, str, int]:
    """
    Starting at a NOTE line, reconstruct its full text by consuming any
    immediately following CONC continuation lines.

    Returns (note_level, full_text, next_index).
    """
    m = _NOTE_RE.match(lines[start].rstrip('\n'))
    level = int(m.group(1))
    text = m.group(2)
    i = start + 1
    while i < len(lines):
        cm = _CONC_RE.match(lines[i].rstrip('\n'))
        if cm and int(cm.group(1)) == level + 1:
            text += cm.group(2)
            i += 1
        else:
            break
    return level, text, i


def _clean_notexml_text(raw_text: str) -> list[str]:
    """
    Given the full text of a notexml NOTE, return a list of clean text segments.
    The first segment becomes the NOTE value; subsequent ones become CONT lines.
    An empty string in the list represents a blank CONT line.
    """
    # Decode HTML entities (&lt; → <, &amp; → &, etc.)
    text = html.unescape(raw_text)
    # Extract notexml body
    m = _NOTEXML_RE.search(text)
    if not m:
        return [text]
    inner = m.group(1)
    # Extract <line> elements (may be empty for blank lines)
    segments = _LINE_RE.findall(inner)
    if not segments:
        # No <line> elements — use inner text directly
        return [inner.strip()]
    return [s.strip() for s in segments]  # strip whitespace; empty string → blank CONT


def _emit_note_lines(level: int, segments: list[str]) -> list[str]:
    """
    Convert a list of text segments into GEDCOM NOTE + CONT raw lines.
    NOTE is at `level`; CONT lines are at `level + 1` (subordinate).
    Empty segments produce blank CONT lines ('N+1 CONT\n').
    """
    out = []
    cont_level = level + 1
    for i, seg in enumerate(segments):
        if i == 0:
            out.append(f'{level} NOTE {seg}\n' if seg else f'{level} NOTE\n')
        else:
            out.append(f'{cont_level} CONT {seg}\n' if seg else f'{cont_level} CONT\n')
    return out


def clean_notexml(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Remove <notexml> wrappers from NOTE fields in a GEDCOM file.

    Returns dict with keys:
      'lines_read'   : total input lines
      'lines_delta'  : lines added minus lines removed (net change)
      'notes_cleaned': number of NOTE blocks converted
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    lines_out: list[str] = []
    notes_cleaned = 0
    i = 0

    while i < len(lines):
        raw = lines[i]
        m = _NOTE_RE.match(raw.rstrip('\n'))

        if m and _has_notexml(m.group(2)):
            level, full_text, next_i = _reconstruct_note(lines, i)
            segments = _clean_notexml_text(full_text)
            lines_out.extend(_emit_note_lines(level, segments))
            notes_cleaned += 1
            i = next_i
        else:
            lines_out.append(raw)
            i += 1

    lines_delta = len(lines_out) - len(lines)
    result = {
        'lines_read': len(lines),
        'lines_delta': lines_delta,
        'notes_cleaned': notes_cleaned,
    }

    write_lines(lines_out, path_in, path_out, dry_run, changed=lines_delta != 0)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Strip <notexml> wrappers from GEDCOM NOTE fields.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Write output here instead of overwriting input')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without writing')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    result = clean_notexml(args.gedfile, path_out=args.output, dry_run=args.dry_run)

    mode = 'DRY RUN' if args.dry_run else 'CLEAN'
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read   : {result["lines_read"]}')
    print(f'  Lines delta  : {result["lines_delta"]:+d}')
    print(f'  Notes cleaned: {result["notes_cleaned"]}')
    if not args.dry_run and result['lines_delta'] != 0:
        dest = args.output or args.gedfile
        print(f'  Written to   : {dest}')


if __name__ == '__main__':
    main()
