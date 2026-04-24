# Task Completion: Fix _citation_already_exists Scanning Past Record Boundaries

**Date**: 2026-04-24

---

## What was done

Fixed a bug in `_citation_already_exists` where the backward scan failed to stop at INDI/FAM/SOUR record headers. The function uses `_TAG_RE` (which requires `\w+` for the tag) to detect level-0 boundary lines, but xref-style records like `0 @I123@ INDI` have `@` in the tag position — not a word character — so the regex returns None and the break never fires. The scan continued backward through the entire file, and if the same source+page appeared in any *earlier* person's record, `_citation_already_exists` falsely returned True. The server then returned `ok: true` with an empty sources list, silently refusing to write the citation.

Fix: add `if not m and raw.startswith('0 '): break` after the regex check to catch xref-style level-0 lines.

## Files changed

- `serve_viz.py` — added explicit `startswith('0 ')` break in `_citation_already_exists`
- `tests/test_serve_viz_http.py` — regression test: add same source+page to two different INDIs; assert the second person's sources are actually updated

## Key decisions

The minimal fix is a two-line addition rather than replacing `_TAG_RE` with a simpler level parser, since `_TAG_RE` is used in many other places and this is the only call site that needs to handle xref-style headers.

## Tests added/modified

- `test_person_level_citation_not_blocked_by_same_source_in_earlier_record` in `TestAddCitationEndpoint` — adds a citation to `@I1@`, then adds the *same* source+page to `@I2@` (which appears later in the file), and asserts `@I2@`'s sources list is non-empty in the response.

## Follow-up / known gaps

The same `_TAG_RE` pattern is used in `_find_fact_for_citation` and other server helpers. Those are not affected because they scan forward (not backward) and stop on level-0 lines using `lines[i].startswith('0 ')` directly — only `_citation_already_exists` was using the regex for the boundary check.
