# Viz Patterns

Patterns for the interactive ancestor pedigree chart (`viz_ancestors.py` + `js/viz_*.js`).

---

## Architecture overview

`viz_ancestors.py` is a self-contained HTML generator. It:
1. Parses the GEDCOM file (two passes: shared notes first, then individuals/families)
2. Inlines `viz_ancestors.css`, all `js/viz_*.js` modules, and GEDCOM data as JSON globals
3. Outputs a single `.html` file with no external dependencies

`serve_viz.py` is the dev server — it wraps this generator, hot-reloads on file change, and adds HTTP API endpoints for editing facts/notes in the live `.ged` file.

---

## JavaScript module structure

Each `js/viz_*.js` file is a focused module with a single responsibility:

| File | Responsibility |
|------|---------------|
| `viz_state.js` | Single state object + URL sync + re-render callbacks |
| `viz_layout.js` | Computes (x, y) positions for all visible nodes |
| `viz_render.js` | Turns layout output into SVG DOM nodes |
| `viz_design.js` | Layout constants (NODE_W, NODE_H, ROW_HEIGHT, H_GAP, etc.) |
| `viz_panel.js` | Detail sidebar: shows bio, events, notes for selected person |
| `viz_modals.js` | Edit dialogs for facts and notes |
| `viz_api.js` | HTTP calls to `serve_viz.py` API for editing GED data |
| `viz_search.js` | Person search/autocomplete |
| `viz_primary_spouse.js` | Logic for selecting the "primary" spouse for a multi-marriage person |

---

## Global data injection

`viz_ancestors.py` injects data as `<script>` globals:

```js
const PEOPLE   = { '@I1@': { name, sex, birth_year, death_year, nati, ... } };
const PARENTS  = { '@I1@': ['@I2@', '@I3@'] };   // [father, mother] or null
const CHILDREN = { '@I1@': ['@I4@', '@I5@'] };
const FAMILIES = { '@F1@': { husb, wife, children, marr_year, ... } };
const RELATIVES = { '@I1@': { siblings: [...], spouses: [...] } };
```

Layout functions read these as globals. In JS tests, set them on `globalThis` before calling layout functions.

---

## State management

`viz_state.js` holds a single `_state` object. Components subscribe via `onStateChange(callback)`. State mutations always go through `setState(patch)`, which merges the patch, syncs to URL, and fires all callbacks.

URL encoding: numeric xref IDs (e.g. `@I380071267816@`) are base62-encoded for compact URLs. `_xrefToToken` / `_tokenToXref` handle conversion. Never read xrefs from URL params directly.

---

## Adding a new visible data field

1. Extract the field in `viz_ancestors.py` → add it to the `person` dict being built
2. Include it in the `PEOPLE` JSON output block
3. Consume it in `viz_panel.js` (sidebar) or `viz_render.js` (node label)
4. Add a test in `tests/js/viz_panel.test.js` or `tests/test_viz_ancestors_utils.py`

### Inline-value fact fields: `evt.type` is the value, not the label

For inline-value facts (RELI, OCCU, TITL, EDUC, RETI), `evt.type` holds the **user-entered value** (e.g., `"Greek Orthodox"`). The display label comes from `EVENT_LABELS[evt.tag]`. Exception: `FACT` events — `evt.type` IS the label (e.g., `"Languages"`) and the value is a separate field. Mixing these up causes label/value order to invert in rendered rows.

### `has_death` boolean is distinct from `death_year`

The `PEOPLE` JSON must include `has_death: bool` tracking whether ANY DEAT record exists for an individual — even undated ones. Gate the "Living" label in the info panel on `!has_death`, not `!death_year`. Without this, people recorded as `1 DEAT Y` (confirmed deceased, no date known) incorrectly show as "Living".

---

## Editing GED data from the browser

`serve_viz.py` exposes:
- `POST /api/edit-fact` — update a fact value in the live `.ged` file
- `POST /api/delete-fact` — remove a fact block
- `POST /api/edit-note` — update a note
- `POST /api/edit-citation` — update a source citation (page, text, note, url) on a fact or person-level source

These write atomically (backup + `os.replace`). After a successful edit, the browser triggers a full chart regeneration via `GET /viz.html?...`. `viz_modals.js` owns the dialog UI; `viz_api.js` owns the HTTP calls.

### Citation boundary scanning uses `cite_level`, not level 0

When scanning backward through lines to detect if a citation already exists, the boundary condition is `level <= cite_level - 1` — not unconditionally `level == 0`. Person-level citations (cite_level 1) stop at level 0; fact-level citations (cite_level 2) stop at level 1. Using level 0 universally causes false-positive duplicate detection: fact-level citations from earlier events in the same record satisfy the boundary check, making newly pasted citations appear to already exist.

---

## Modal and UI state

### Modal field state must be reset on each open

DOM input state (disabled flags, checked checkboxes, hidden/shown toggles) persists across modal opens — the browser does not reset it. `editEvent()` and any other modal-open function must explicitly reset all relevant field states on entry before populating with new data. Failure mode: editing a DEAT event (which sets a "date unknown" checkbox and disables the date input) then immediately editing a MARR event leaves the date field disabled, with no visible indication why.

## Source badge rendering in the panel

`viz_panel.js` has two rendering paths for source citation badges:

- **Timeline events** (dated, rendered in `detail-facts`): use `buildSourceBadgeHtml(evt.citations, xref, evt._origIdx)` which reads `evt.citations.length` to show the correct count.
- **Undated factoids** (rendered in `detail-also-lived` via `undatedRows`): also compute `srcBadge = buildSourceBadgeHtml(...)` and must use it. Do NOT create a second hardcoded badge string — that was the bug where OCCU/RELI/TITL/FACT always showed `+ src` regardless of citations.

When adding or modifying any event row rendering in either path, always pass `evt.citations` into `buildSourceBadgeHtml` and use the return value. Never construct a badge span inline with hardcoded text.

## Phase 3 child placement has dependency ordering

`computeLayout` Phase 3 walks `expandedChildrenPersons` and calls `_placeChildrenOfPerson` for each. That function early-returns if the person isn't in `nodes` yet — but a person *can* be added to `nodes` by another expanded person's pass (e.g., expanding grandma and her son: grandma's pass places the son, then the son's own pass needs to place his children).

A single linear pass — even one sorted by current x — only handles one level of dependency. For chains of expansions, iterate to a fixed point: each pass picks the subset currently in `nodes`, sorts by x, places them, and removes them from a remaining set; repeat until no progress. Persons that never become reachable (stale URL state) drop out naturally.

---

**Last Updated**: 2026-04-28
