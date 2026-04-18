# Visualizer Redesign — Design Specification

**Date:** 2026-04-15  
**Branch:** `feature/visualizer-redesign`  
**Status:** Implemented

---

## Overview

Full redesign of the GEDCOM family-tree visualizer, replacing the existing Ahnentafel pedigree chart (`ancestors.html` / `viz_ancestors.py`) with an Obsidian-themed, omnidirectional hourglass layout. The Python backend (`serve_viz.py`) is extended with 8 new API endpoints. Three new GEDCOM linter checks are added.

---

## Aesthetic: Obsidian Theme

Deep near-black background with blue-violet accents. All design tokens live in `js/viz_design.js`:

| Token | Value |
|-------|-------|
| `BG_BASE` | `#07070d` |
| `BG_SURFACE` | `#0a0a18` |
| `BG_NODE` | `#131330` |
| `BG_NODE_FOCUS` | `#1e1e42` |
| `BORDER` | `#343468` |
| `BORDER_FOCUS` | `#7878d4` |
| `TEXT_PRIMARY` | `#e4e4ff` |
| `TEXT_SECONDARY` | `#b8b8e0` |
| `ACCENT` | `#7878d4` |
| `ACCENT_SOURCE` | `#78b878` |

Node size: 160×38px (focus), 140×34px (normal). System-ui font.

---

## Layout: Vertical Hourglass

### Generation rows (Phase 1)
- Focus person = generation 0 (y = 0)
- Parents = −1, grandparents = −2, etc.
- Children = +1, grandchildren = +2, etc.
- `y = generation × ROW_HEIGHT` (ROW_HEIGHT = 90px)

### Horizontal packing (Phase 2)
- **Focus row**: focus person at x=0; older siblings packed left, younger right (birth-order); spouse at `max_sibling_x + MARRIAGE_GAP` (60px)
- **Parent row**: father centered above focus+older-siblings, mother above focus+younger-siblings; connected by horizontal bracket rail at y = −0.5 × ROW_HEIGHT
- **Children row**: distributed evenly below focus+spouse midpoint; same bracket rail downward
- **Spouse sibling expansion**: spouse's siblings packed rightward from spouse on demand

All layout computed by `js/viz_layout.js` (`computeLayout`). Returns `{ nodes: [{xref, x, y, generation, role}], edges: [{x1,y1,x2,y2,type}] }`.

---

## Frontend Architecture

### New module set (replaces old `viz_constants`, `viz_init`, `viz_detail`)

| File | Responsibility |
|------|---------------|
| `js/viz_design.js` | DESIGN token object + `escHtml` utility |
| `js/viz_state.js` | Single state object: `{focusXref, expandedNodes, panelOpen, panelXref}`. All mutations via `setState()`. URL deep-linking via `history.pushState`. |
| `js/viz_api.js` | Thin wrappers around all `POST /api/` calls |
| `js/viz_layout.js` | Two-phase layout engine: `computeLayout(focusXref, expandedNodes, spouseSiblingsExpanded)` |
| `js/viz_render.js` | SVG renderer: `initRenderer(svgEl)`, `render(layout)`. Pan/zoom. Expand `+` buttons on ancestor nodes. |
| `js/viz_panel.js` | Right detail panel. Reads `state.panelXref` from `PEOPLE`/`SOURCES`. |
| `js/viz_modals.js` | Modal dialogs for all edit/add/delete operations |
| `js/viz_search.js` | People search autocomplete; calls `setState({ focusXref })` on selection |

D3 v7 is loaded from CDN before the module scripts.

### URL deep-linking

URL: `http://localhost:8080/?person=I42` (xref with `@` stripped).  
On load, `viz_state.js` reads `?person=` and initializes `focusXref`. Browser back/forward navigate tree history.

---

## New Features

### 1. Omnidirectional expansion
- `+` button on ancestor nodes → `setState({ expandedNodes: new Set([...expandedNodes, xref]) })`
- New nodes fetched from `PARENTS` / `CHILDREN` globals (already embedded in HTML)

### 2. Source & citation management

**GEDCOM model:**
- `0 @S1@ SOUR` — global source record (titl, auth, publ, repo, note)
- `2 SOUR @S1@` on a fact — citation (PAGE, DATA/TEXT, NOTE)

**UI:**
- Citation badge on each fact row → **Citation modal**: edit PAGE, full transcription, citation note; "View Source →" button
- Source modal: edit TITL/AUTH/PUBL/REPO/NOTE; shows "changes affect all citations"
- `+` in Facts section → add citation (with fact selector)

**New API endpoints:** `add_source`, `edit_source_record`, `add_citation`, `edit_citation`, `delete_citation`

**Backend notes:**
- `edit_source_record` tracks `skip_children` to prevent CONT-line orphaning
- `SOURCES` global embedded in HTML: `{ xref: { titl, auth, publ, repo, note, url } }`

### 3. Add new person
- `+ Add Person` → modal with: given name, surname, sex, birth year, relationship type, relationship target
- Relationship types: `child_of`, `parent_of`, `spouse_of`, `sibling_of`
- `parent_of` includes duplicate-slot guard (400 if HUSB/WIFE already occupied)

**New API endpoint:** `add_person`

### 4. Godparents
Stored as `1 ASSO @Ix@ / 2 RELA Godparent` on the INDI record.

**UI:** Godparent pills appear under CHR/BAPM events in the detail panel. `[+ Add Godparent]` affordance always shown for CHR/BAPM events (even before any godparents exist).

**New API endpoints:** `add_godparent`, `delete_godparent`

---

## New GEDCOM Linter Checks

### `scan_godparent_count(path)`
Flags individuals with >2 godparents total, or >1 godparent of the same gender. Severity: WARNING.

### `scan_asso_without_rela(path)`
Flags `1 ASSO` records missing a required `2 RELA` sub-tag. Severity: ERROR.

### `scan_sour_without_titl(path)`
Flags `0 @Sn@ SOUR` records with no `1 TITL` tag. Severity: WARNING.

---

## File Changes

**Modified:**
- `viz_ancestors.py` — new script tags, full SOURCES embedding, enhanced SOUR parsing
- `gedcom_linter.py` — 3 new scan functions + summary rows
- `serve_viz.py` — 8 new `/api/` route handlers

**New:**
- `js/viz_design.js`, `js/viz_state.js`, `js/viz_api.js`
- `js/viz_panel.js` (replaces `viz_detail.js`)
- `js/viz_layout.js`, `js/viz_render.js`, `js/viz_modals.js` (rewrites)

**Deleted:**
- `js/viz_constants.js` → merged into `viz_design.js`
- `js/viz_init.js` → replaced by `viz_state.js`
- `js/viz_detail.js` → replaced by `viz_panel.js`

---

## Testing

- **JS unit tests** (`tests/js/`): Vitest; layout, state, API wrapper, render, panel, modals — 100+ tests
- **Python tests** (`tests/`): pytest; HTTP endpoint tests for all 8 new API routes + regression tests for CONT-line orphaning and duplicate-parent guard
- **Linter tests**: godparent count, ASSO without RELA, SOUR without TITL
