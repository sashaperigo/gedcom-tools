#!/usr/bin/env python3
"""Fail if ARCHITECTURE_MAP.md's file inventory drifts from the real tree.

ARCHITECTURE_MAP.md is loaded into context at every session start, so a stale
listing is worse than none: it costs tokens AND sends Claude exploring to
reconcile the mismatch. This guards the two sections we keep exhaustive — the
`js/` and `gedcom_merge/` subtrees — against added/removed/renamed files.

The doc is local-only (gitignored); if it's absent this check is a no-op.
Bypass a known-stale state with DOC_DRIFT_SKIP=1 (or `git commit --no-verify`).
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(REPO_ROOT, ".claude", "ARCHITECTURE_MAP.md")

# Sections of the tree we keep exhaustive (no "..." abbreviation), keyed by the
# directory marker in the doc, with the rule for what counts as a real file.
SECTIONS = {
    "js/": {
        "dir": "js",
        "ext": ".js",
        "real": lambda f: f.endswith(".js"),
    },
    "gedcom_merge/": {
        "dir": "gedcom_merge",
        "ext": ".py",
        "real": lambda f: f.endswith(".py") and not f.startswith("__"),
    },
}


def listed_files(doc_lines):
    """Walk the directory-tree code block, collecting filenames per section.

    Top-level entries begin with a tree branch char (├/└) at column 0; nested
    child lines begin with a continuation bar (│). A new top-level entry ends
    the current section.
    """
    listed = {key: set() for key in SECTIONS}
    section = None
    for line in doc_lines:
        if line[:1] in ("├", "└"):
            section = next((k for k in SECTIONS if f"── {k}" in line), None)
            continue
        if section and line[:1] == "│":
            m = re.search(r"([\w.-]+\.(?:js|py))", line)
            if m:
                listed[section].add(m.group(1))
    return listed


def main():
    if os.environ.get("DOC_DRIFT_SKIP"):
        return 0
    if not os.path.exists(DOC):
        return 0  # local-only doc absent — nothing to check

    with open(DOC, encoding="utf-8") as fh:
        listed = listed_files(fh.read().splitlines())

    problems = []
    for key, spec in SECTIONS.items():
        actual = {f for f in os.listdir(os.path.join(REPO_ROOT, spec["dir"])) if spec["real"](f)}
        doc = listed[key]
        missing = sorted(actual - doc)   # in tree, not documented
        extra = sorted(doc - actual)     # documented, no longer in tree
        if missing or extra:
            problems.append((key, missing, extra))

    if not problems:
        return 0

    print("ARCHITECTURE_MAP.md is out of sync with the source tree:", file=sys.stderr)
    for key, missing, extra in problems:
        print(f"\n  {key}", file=sys.stderr)
        for f in missing:
            print(f"    + {f}  (in tree, not in ARCHITECTURE_MAP.md)", file=sys.stderr)
        for f in extra:
            print(f"    - {f}  (in ARCHITECTURE_MAP.md, no longer in tree)", file=sys.stderr)
    print(
        "\nUpdate .claude/ARCHITECTURE_MAP.md and bump its 'Last Updated' date.\n"
        "Bypass with DOC_DRIFT_SKIP=1 or git commit --no-verify.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
