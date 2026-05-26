# Advanced search: results-pane redesign

**Date:** 2026-05-26
**Branch:** feat/advanced-search
**Status:** Design — pending implementation

## Problem

The current advanced-search side pane (340px wide, left of the pedigree) stacks the full form vertically: Name, Sex, life-event sections, family-member sections, Search/Clear buttons, and finally the results list. On a typical laptop screen the form alone fills the viewport, leaving the results area squeezed below the fold with no usable scroll. With ~1200 matches possible against the full GEDCOM, the user can't actually browse what they've searched for.

## Solution: collapse the form after Search

Keep the existing 340px left pane (stay-in-tree experience). After the user clicks Search, the form unmounts and the pane switches into a results mode:

1. **Filter-summary bar** at the top — one row of chips, one per active criterion, with an Edit link.
2. **Count + sort bar** — total matches, sort dropdown.
3. **Scrollable result list** — one row per person, denser than today.
4. **Pager** pinned to the bottom of the pane — 25 per page, numbered.

Clicking the filter bar (or Edit) re-opens the form with the previous values restored; clicking Search again returns to results mode.

## Pane states

The pane is a state machine with two modes:

- `form` — current behavior. Form fields, Search button. No results visible.
- `results` — filter chips, count+sort, paginated list, pager. No form fields visible.

Transitions:

- `form → results` on Search button (or Enter in any form field) when ≥1 criterion is set.
- `results → form` on click of the filter-summary bar or its Edit link.
- Closing the pane (× button) returns it to hidden but preserves last criteria + last result set, so re-opening lands back in whichever mode it was in.

## Filter-summary chips

One chip per active criterion. Chip text is short and human:

- Name: `Last: Aliotti`, `First: Maria`
- Sex: `Male`, `Female`
- Event: `Born in Smyrna`, `Married 1850–1920`, `Died in Izmir 1900–`
- Family: `Spouse: Aliotti`, `Father: Domenico`

Chips are read-only display elements (no individual remove × — to change, the user re-opens the form). The whole bar is clickable as one target.

## Result row

One row per person. Layout:

```
<bold name>
<years> · <primary place> · <relationship-or-spouse>
```

- **Name** — full display name (current `full.name`).
- **Years** — `b·d`, `b–`, `–d`, or `b` only, derived from the first BIRT/DEAT event.
- **Primary place** — birth place if present, else death place, else blank. Drops the leading segments if very long (keep last two comma-separated segments).
- **Relationship-or-spouse** — first non-empty of:
  - Relationship label if computable cheaply (already in `viz_relationship.js`); else
  - `spouse <name>` from `relIndex.spousesOf` (existing logic).

Row click behavior: unchanged from today — `setState({ focusXref, panelOpen: true, panelXref })`.

## Sort

Dropdown in the count bar. Two options for v1:

- **Name** (alphabetical, default) — by current `full.name`.
- **Birth year** (ascending, undated last).

Skip relationship-distance sort in v1 — requires graph traversal per result.

## Pagination

25 results per page. Pager pinned to the bottom of the pane:

```
1–25 of 156    ‹ [1] 2 3 ›
```

- Prev/next buttons disable at boundaries.
- Numbered buttons show current page + neighbors (windowing for large totals: `‹ 1 … 5 [6] 7 … 12 ›`).
- Page size is a constant — not user-configurable in v1.
- Sort or filter change resets to page 1.

## Component boundaries (JS)

Today `js/viz_advanced_search.js` (407 lines) contains: pill toggling, section add/remove, form-to-criteria serialization, `runAndRender`, and result-row rendering. The pane mode machine and pagination push it past the threshold where one file stops being readable. Split into:

- `js/viz_advanced_search.js` — pane controller, mode machine, criteria serialization (`form → criteria object`), Search/Clear button wiring. Owns the state: `currentMode`, `currentCriteria`, `currentResults`, `currentPage`, `currentSort`.
- `js/viz_advanced_results.js` — given `(results, criteria, page, sort)`, renders the entire results-mode DOM (filter bar, count/sort, list, pager). Pure render — emits events for page change, sort change, edit-filters, result-click. No state of its own.
- `js/viz_advanced_search_match.js` — extracted matching helpers (`personMatchesAdvanced`, `eventSectionMatches`, `familySectionMatches`, `extractYear`, `buildRelIndex`). Already pure; lifting them out leaves the controller focused.

The split is justified: results rendering is large and entirely independent from form rendering — the only coupling is the criteria object and the click handler.

## HTML / CSS changes

**HTML** (`viz_ancestors.html`) — replace the single `.adv-pane-body` content with two sibling containers:

```html
<div class="adv-pane-body" data-mode="form">
  <div class="adv-form"> ...existing form sections... </div>
  <div class="adv-results-mode">
    <div class="adv-filterbar" id="adv-filterbar"></div>
    <div class="adv-countbar" id="adv-countbar"></div>
    <div class="adv-resultlist" id="adv-resultlist"></div>
    <div class="adv-pager" id="adv-pager"></div>
  </div>
</div>
```

The `[data-mode="form"|"results"]` attribute drives visibility via CSS (one of the two children is `display:none`).

**CSS** (`viz_ancestors.css` near line 2826) — add the new component styles per the mockup. Keep existing form styles unchanged.

## Tests

JS tests under `tests/js/`:

- `viz_advanced_results.test.js` — render with N results, assert chip text, count text, row count per page, pager state at first/middle/last page, sort dropdown options.
- `viz_advanced_search.test.js` (extend) — mode transitions: form → results on Search, results → form on filter-bar click; criteria preserved across transitions; pager resets to 1 on sort change.

No changes needed to existing matcher tests — they live in the pure module and run as-is.

## Out of scope (v1)

- Per-chip remove (one chip = one criterion deletion).
- Relationship-distance sort.
- Photo thumbnails in result rows.
- Saving searches.
- Keyboard navigation through results.
- Infinite scroll (decided against in favor of explicit pager).
