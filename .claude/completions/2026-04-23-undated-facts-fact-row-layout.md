# Task Completion: undatedRows() → fact-row Layout + dotColor Extended

**Date**: 2026-04-23

---

## What was done

Replaced the `evt-entry` layout for undated facts in `undatedRows()` with a compact `fact-row` layout (dot + label + value). RESI events retain the `evt-entry` layout but gain a `no-year` class. Extended `dotColor()` to cover TITL, DSCR, NCHI, and FACT subtypes (Languages, Literacy, Politics, Medical condition).

## Files changed

- `js/viz_panel.js` — `allVisible` filter extended to include `inline_val`; `dotColor()` extended with new tags/FACT subtypes; `undatedRows()` rewritten with `fact-row`/RESI branch logic and `srcBadgeInline`
- `tests/js/viz_panel.test.js` — 3 new tests in `renderPanel — fact-row layout for undated facts` describe block

## Key decisions

- **`inline_val` added to `allVisible` filter**: OCCU/TITL/DSCR events store their primary value in `inline_val`, not `type`/`place`/`date`. Without this, events like `{ tag: 'OCCU', inline_val: 'Merchant', date: null, place: '' }` were silently dropped before reaching `undatedFactoids`, making tests fail and real data disappear.
- **RESI keeps `evt-entry` layout**: Undated RESI entries are conceptually residence records, not compact facts, so they retain the full `evt-entry` structure. Added `no-year` class instead of the `evt-year-col` div.
- **`srcBadgeInline` vs `srcBadge`**: Non-RESI facts use a lightweight `fact-row-src` span (inline) rather than the full `evt-src-badge` widget, matching the compact fact-row aesthetic. RESI keeps `buildSourceBadgeHtml()` output.
- **NCHI special case**: Children-count facts need label+value on one baseline line, so they get a flex-row variant of `fact-row`.

## Tests added/modified

- `tests/js/viz_panel.test.js` — 3 tests:
  - `OCCU renders as fact-row, not evt-entry`
  - `OCCU dot color is #fbbf24`
  - `undated RESI renders as evt-entry with no-year class`

## Follow-up / known gaps

- Task 10 (Note Badge inside `note-card` + no-year class CSS) is next.
- `fact-row-src` span needs CSS to be styled (covered in Task 6 CSS milestone).
