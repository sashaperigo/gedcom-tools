# Age on the timeline — design

**Status:** Approved
**Author:** Claude (with sasha)
**Date:** 2026-04-30

## Problem

The detail-panel timeline currently renders the year of each event in a 46 px gutter on the left of every row. The focal person's age at the time of the event is not shown. Ancestry.com displays the age beneath the year and it makes the timeline scannable in a way ours isn't.

## Goal

Show the focal person's age beneath the year for every dated row in the panel timeline. Year stays left-aligned in the gutter (preserving today's two-line wrap behavior for ranges). Age sits below, **centered** within the gutter. Birth row shows a small uppercase "(AGE)" hint instead of the literal `0`.

## Out of scope

- Ages on undated rows (the "Also lived in" / "Other facts" sections at the bottom of the panel — they have no year column and no event year to anchor on).
- Ages on rows where the focal person has no known birth year (no anchor → no age).
- Pre-birth events. Per user, no event prior to the focal person's birth ever renders on the timeline, so the age formula does not need to handle negative ages.

## Affected surfaces

All five kinds of timeline rows in `js/viz_panel.js`:

| Row kind        | DOM container       | Year span class | Year value source                         |
|-----------------|---------------------|-----------------|-------------------------------------------|
| Standard event  | `.evt-entry`        | `.evt-year`     | `evtYear` (int) — single year             |
| Collapsed RESI  | `.evt-entry`        | `.evt-year`     | `evt._yearRange` (string) — `"1942–1944"` |
| Marriage card   | `.marr-card`        | `.marr-year`    | `evtYear` (int)                           |
| Divorce card    | `.div-card`         | `.marr-year`    | `evtYear` (int)                           |
| Relative event  | `.evt-rel-row`      | `.yr`           | `rel.year` (int)                          |

All five render through `viz_panel.js` (lines ~595, ~688, ~720, ~758, ~774, ~789–803). The CSS for the year column lives in `viz_ancestors.css` (`.evt-year-col`, `.marr-card .marr-year`, `.div-card .marr-year`, `.evt-rel-row .yr`).

## Design

### Age computation

Add one helper in `viz_panel.js`:

```js
// Returns null when no age can be derived. Otherwise a display string:
//   single year  → "16"
//   year range   → "16" if start==end, else "16–18"
function _ageAt(yearOrRange, birthYear) {
    if (birthYear == null) return null;
    if (yearOrRange == null || yearOrRange === '') return null;
    const s = String(yearOrRange);
    const m = s.match(/^(\d{3,4})(?:\s*[–\-]\s*(\d{3,4}))?$/);
    if (!m) return null;
    const lo = parseInt(m[1], 10) - birthYear;
    const hi = m[2] ? (parseInt(m[2], 10) - birthYear) : lo;
    return lo === hi ? String(lo) : `${lo}–${hi}`;
}
```

`birthYear` comes from `data.birth_year` (already parsed into `by` near line 464 in `populateDetail`). Pass `by` into the per-row branches that build year HTML.

### HTML changes

For each year span, render an age sibling immediately after.

- **Birth row** (`evt.tag === 'BIRT'`): render `<span class="evt-age-hint">(age)</span>` regardless of the computed age. The literal text `(age)` is rendered by CSS as uppercase "(AGE)".
- **Every other row** with a known birth year and a parseable year: render `<span class="evt-age">${ageStr}</span>`.
- **No birth year, no parseable year, or no year on the row:** no age node.

The same `.evt-age` / `.evt-age-hint` classes are reused inside `.marr-card`, `.div-card`, and the standard `.evt-entry` since they all already share `.evt-year-col`. The relative-event row (`.evt-rel-row`) needs a small wrapper because today its year is a peer element, not in a column — see CSS section below.

### CSS changes (`viz_ancestors.css`)

1. Convert `.evt-year-col` from a fixed-width plain block into a left-aligned flex column. Width stays **46 px** so all rows align on the same gutter edge; the year continues to wrap naturally after the en-dash (Unicode UAX 14 BA) for ranges, producing `1942–` / `1944` on two lines, like today.

   ```css
   .evt-year-col {
       width: 46px;
       flex-shrink: 0;
       border-right: 1px solid var(--border);
       padding-right: 10px;
       display: flex;
       flex-direction: column;
       align-items: flex-start;
       justify-content: center;
       text-align: left;
   }
   ```

2. New rule for the age beneath the year, centered within the gutter (the year stays left-aligned but the age centers under it):

   ```css
   .evt-age {
       font-size: 11px;
       color: var(--text-muted);
       margin-top: 4px;
       line-height: 1.2;
       font-variant-numeric: tabular-nums;
       align-self: center;
   }
   ```

3. New rule for the birth-row hint:

   ```css
   .evt-age-hint {
       font-size: 9px;
       color: var(--text-disabled);
       margin-top: 4px;
       line-height: 1.2;
       letter-spacing: 0.5px;
       text-transform: uppercase;
       font-family: 'IBM Plex Mono', ui-monospace, monospace;
       align-self: center;
   }
   ```

4. Marriage and divorce cards inherit `.evt-year-col` so no per-card CSS changes are required beyond making sure they use the same class.

5. Relative-event row keeps a single-line layout. Wrap the year + age in a small flex column so they stack:

   ```css
   .evt-rel-row .yr-stack {
       display: inline-flex;
       flex-direction: column;
       align-items: flex-start;
       width: 36px;       /* current .yr width */
       flex-shrink: 0;
   }
   .evt-rel-row .yr  { font-weight: 600; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
   .evt-rel-row .age { font-size: 10px; color: var(--text-muted); margin-top: 1px; font-variant-numeric: tabular-nums; align-self: center; }
   ```

   `_renderRelEventRow` wraps the year and (optional) age in a `<span class="yr-stack">`. The relative-event row uses `.age` (a class scoped under `.evt-rel-row`), not `.evt-age`, since its size and margin differ.

### What the user sees

| Year cell             | Age cell        |
|-----------------------|-----------------|
| `1926` (BIRT)         | `(AGE)` hint    |
| `1941`                | `14`            |
| `1942`                | `16`            |
| `1942–` / `1944`      | `16–18`         |
| `1947`                | `21`            |
| (no year)             | (no age)        |
| (year, no birth_year) | (no age)        |

The wrapped year stays left-aligned (so `1942–` and `1944` line up on the left edge of the gutter), and the age beneath sits centered under whichever year line is widest.

## Testing

Unit tests in a new `tests/js/age_at.test.js`:

- single year + birth year → numeric string
- birth year of focal person + same year → `"0"` (helper still returns `0`; the BIRT row uses the hint instead at render time)
- range `"1942–1944"` (em-dash) + birth year → range string `"16–18"`
- range with hyphen `"1942-1944"` → same result
- range with same start/end → single value
- null/missing birth year → `null`
- malformed year input → `null`
- non-numeric range → `null`

DOM tests using the existing panel test harness (`tests/js/viz_panel.*`):

- standard event: `.evt-year-col` contains both `.evt-year` and `.evt-age`, age text equals computed age
- RESI range: `.evt-age` text matches `^\d+–\d+$`
- BIRT row: `.evt-age-hint` exists with text `(age)`, no `.evt-age` sibling
- MARR card: age renders inside the year column
- relative-event row: age renders inside `.yr-stack` next to the year
- focal person with no `birth_year`: no `.evt-age` or `.evt-age-hint` nodes in the timeline

## Risks / non-issues

- **No-year rows.** `.evt-entry.no-year` already hides `.evt-year-col`; any age node inside it hides with it.
- **Year wrap behavior.** Default UAX 14 line breaking already breaks after the en-dash, producing two lines for ranges in the existing 46 px column. We add nothing — explicitly *not* setting `overflow-wrap: anywhere`, which would over-break.
- **Age wrap behavior.** Age values are at most ~5 characters (`16–18`, `92–105`). They fit in the 46 px gutter without wrapping.
- **Performance.** `_ageAt` runs once per row; trivial.

## Plan-level scope

This spec produces:

1. `_ageAt` helper in `js/viz_panel.js`
2. Per-row HTML changes (5 row kinds) in `js/viz_panel.js` and `js/viz_relative_events.js` rendering helper
3. CSS updates in `viz_ancestors.css`
4. JS unit tests for `_ageAt`
5. JS DOM tests for each row kind
