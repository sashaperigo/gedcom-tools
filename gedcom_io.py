"""
gedcom_io.py — Shared low-level utilities for GEDCOM file processing.

Provides:
  - level(line)       : extract the numeric level from a GEDCOM line
  - level_tag(line)   : extract (level, tag) from a GEDCOM line
  - write_lines(...)  : atomically write output lines using the standard
                        dry_run / in-place / copy-to-output logic
"""

import os
import re

_LEVEL_RE = re.compile(r'^(\d+)')
_LEVEL_TAG_RE = re.compile(r'^(\d+) ([A-Z_][A-Z0-9_]*)')


def level(line: str) -> int | None:
    """Return the GEDCOM level number from a line, or None if not a valid GEDCOM line."""
    m = _LEVEL_RE.match(line.rstrip('\n'))
    return int(m.group(1)) if m else None


def level_tag(line: str) -> tuple[int, str] | None:
    """Return (level, tag) for a GEDCOM line, or None if it doesn't parse."""
    m = _LEVEL_TAG_RE.match(line.rstrip('\n'))
    return (int(m.group(1)), m.group(2)) if m else None


def write_lines(
    lines_out: list[str],
    path_in: str,
    path_out: str | None,
    dry_run: bool,
    changed: bool,
) -> None:
    """
    Write lines_out to the correct destination using the standard transform logic:

    - dry_run=True  : write nothing.
    - changed=True  : write via .tmp + os.replace for atomicity.
    - changed=False, path_out set and != path_in : write a clean copy.
    """
    if dry_run:
        return
    dest = path_out if path_out else path_in
    if changed:
        tmp = dest + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, dest)
    elif path_out and path_out != path_in:
        with open(path_out, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
