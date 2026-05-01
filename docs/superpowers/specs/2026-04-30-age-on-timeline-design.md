# Age on the timeline — design

**Status:** Draft, awaiting review
**Author:** Claude (with sasha)
**Date:** 2026-04-30

## Problem

The detail-panel timeline currently renders the year of each event in a 46 px gutter on the left of every row. The focal person's age at the time of the event is not shown. Ancestry.com displays the age stacked under the year and it makes the timeline scannable in a way ours isn't.

## Goal

Show the focal person's age beneath the year for every dated row in the panel timeline, matching variation A from the brainstorming session: year on top, age beneath, both centered within the existing gutter column. Birth row shows `0`. Year ranges produce age ranges.

## Out of scope

- Ages on undated rows (the "Also lived in" / "Other facts" sections at the bottom of the panel — they have no year column and no event year to anchor on).
- Ages on rows where the focal person has no known birth year (no anchor → no age).
- Pre-birth events. Per user, no event prior to the focal person's birth ever renders on the timeline, so the age formula does not need to handle negative ages.

## Affected surfaces

All four kinds of timeline rows in `js/viz_panel.js`:

| Row kind        | DOM container       | Year span class | Year value source                         |
|-----------------|---------------------|-----------------|-------------------------------------------|
| Standard event  | `.evt-entry`        | `.evt-year`     | `evtYear` (int) — single year             |
| Collapsed RESI  | `.evt-entry`        | `.evt-year`     | `evt._yearRange` (string) — `"1942–1944"` |
| Marriage card   | `.marr-card`        | `.marr-year`    | `evtYear` (int)                           |
| Divorce card    | `.div-card`         | `.marr-year`    | `evtYear` (int)                           |
| Relative event  | `.evt-rel-row`      | `.yr`           | `rel.year` (int)                          |

All five render through `viz_panel.js` (lines ~595, ~688, ~720, ~758, ~774, ~789–803). The CSS for the year column is in `viz_ancestors.css` (`.evt-year-col`, `.marr-card .marr-year`, `.div-card .marr-year`, `.evt-rel-row .yr`).

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

Each year span gains a sibling `.evt-age` (or `.marr-age` / `.rel-age` to keep selectors local). The age is rendered only when `_ageAt` returns non-null. Example (standard event):

```js
const yearStr = evtYear ? `<span class="evt-year">${evtYear}</span>` : '';
const ageVal  = _ageAt(evtYear, by);
const ageStr  = ageVal != null ? `<span class="evt-age">${ageVal}</span>` : '';
// year-col content becomes: yearStr + ageStr + tagAbbrev
```

Same shape for the RESI-range case (passing `evt._yearRange` instead of `evtYear`), the MARR/DIV cards (using `.marr-age`), and the relative-event row (using `.rel-age`).

### CSS changes (`viz_ancestors.css`)

1. Convert `.evt-year-col` from a fixed-width column into a centered flex stack so the year and age line up vertically. Switch `width: 46px` to `min-width: 46px` so a range like `1942–1944` can grow the column instead of overflowing the border:

   ```css
   .evt-year-col {
       min-width: 46px;
       flex-shrink: 0;
       border-right: 1px solid var(--border);
       padding-right: 10px;
       display: flex;
       flex-direction: column;
       align-items: center;
       justify-content: center;
       text-align: center;
   }
   ```

2. New rule for the age beneath the year:

   ```css
   .evt-age {
       font-size: 11px;
       color: var(--text-muted);
       margin-top: 2px;
       line-height: 1.2;
       font-variant-numeric: tabular-nums;
       white-space: nowrap;
   }
   ```

3. Mirror the same treatment for the marriage and divorce cards. The existing `.marr-card`/`.div-card` rules use `display: flex; align-items: center;` on the card itself; the `.evt-year-col` inside them already inherits the new flex-stack rule, so no per-card CSS is needed beyond an `.marr-age` rule analogous to `.evt-age`. Reuse `.evt-age` as a single class so we don't duplicate.

4. Relative-event row gets the same age treatment with a different layout shape since the row is a single horizontal line, not a card. Update the rule to stack year + age in a small inline-block:

   ```css
   .evt-rel-row .yr-stack {
       display: inline-flex;
       flex-direction: column;
       align-items: center;
       width: 36px;       /* current .yr width */
       flex-shrink: 0;
   }
   .evt-rel-row .yr   { font-weight: 600; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
   .evt-rel-row .age  { font-size: 10px; color: var(--text-muted); margin-top: 1px; font-variant-numeric: tabular-nums; }
   ```

   And in `_renderRelEventRow`, wrap the year and the new age in a `<span class="yr-stack">`.

### What the user sees

| Year cell                | Age cell |
|--------------------------|----------|
| `1926`                   | `0`      |
| `1941`                   | `14`     |
| `1942`                   | `16`     |
| `1942–1944` (RESI run)   | `16–18`  |
| `1947`                   | `21`     |
| (no year)                | (hidden) |
| (year, no birth_year)    | (hidden) |

## Testing

Unit tests in a new `tests/js/age_at.test.js`:

- single year + birth year → numeric string
- birth year of focal person + same year → `"0"` (birth row case)
- range `"1942–1944"` (em-dash) + birth year → range string `"16–18"`
- range with same start/end → single value
- null/missing birth year → `null`
- malformed year input → `null`
- non-numeric range → `null`

Snapshot/DOM tests in the existing panel test harness (`tests/js/viz_panel.*` if present, otherwise add one) for the rendered timeline:

- standard event: `.evt-year-col` contains both `.evt-year` and `.evt-age`
- RESI range: `.evt-age` text matches `\d+–\d+`
- MARR card: age renders inside the year column
- relative-event row: age renders next to the year inside `.yr-stack`
- focal person with no `birth_year`: no `.evt-age` nodes in the timeline

## Open questions

None remaining; design is locked pending review.

## Risks / non-issues

- **Column width with ranges.** Switching `width` → `min-width` on `.evt-year-col` may cause column widths to vary slightly across rows in a single timeline. Acceptable: ranged residences are rare (one per RESI run) and the visual rhythm degrades gracefully.
- **No-year rows.** `.evt-entry.no-year` already hides the year column; the age column hides with it (same parent), so no extra rule needed.
- **Performance.** `_ageAt` runs once per row; trivial.

## Plan-level scope

This spec produces:

1. `_ageAt` helper + per-row HTML changes in `js/viz_panel.js`
2. Wrapping helper for relative-event rows
3. CSS updates in `viz_ancestors.css`
4. JS tests for `_ageAt` and panel render
