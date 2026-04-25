# Design: Link Existing Person from Family Buttons

**Date:** 2026-04-24

## Context

The info panel's family section has four buttons — "+ Parent", "+ Sibling", "+ Spouse", "+ Child" — that currently only allow creating a new person. When a person already exists in the tree (e.g. a second marriage partner, a sibling added separately), the user has no way to create the relationship without duplicating the record. This feature adds the ability to select an existing person from these buttons.

## Design

### UX Flow

The modal triggered by all four buttons gains a **unified search-first flow** with three panels inside the existing `#add-person-modal`:

1. **Search panel** (new, shown on open)
   - Single text input: "Type a name..."
   - As user types, renders up to 10 matching `ALL_PEOPLE` results (name + birth year), filtered by substring match using the existing `_renderChangeParentResults` pattern from `viz_modals.js`
   - Always appends a final row: `+ Add "[typed]" as new person` in a distinct color
   - Empty input shows no results
   - Clicking an existing result → stores xref, switches to **Preview panel**
   - Clicking "Add new" row → pre-fills given-name field, switches to **Create panel**

2. **Preview panel** (new, shown after selecting existing person)
   - Shows: full name, birth + death year, spouse name + marriage year (if any)
   - Shows "other parent" dropdown (same as current `child_of` flow) — always shown for `child_of`, hidden for other rel types
   - Back button returns to search panel
   - "Confirm link" button submits to `/api/link_person`

3. **Create panel** (existing form, now accessible via "Add new" row)
   - Given name pre-filled from search input
   - All existing fields: surname, sex, birth year, other parent
   - Back button returns to search panel
   - "Add person" button submits to `/api/add_person` (unchanged)

**State variables** added to `viz_modals.js`:
- `_addPersonMode`: `'search' | 'preview' | 'create'`
- `_addPersonLinkXref`: xref of the selected existing person (set when entering preview)

### New API Endpoint: `POST /api/link_person`

Links two existing people via a family relationship. No new INDI record is created.

**Request payload:**
```json
{
  "rel_xref": "@I123@",
  "link_xref": "@I456@",
  "rel_type": "parent_of",
  "other_parent_xref": "@I789@"
}
```

- `rel_xref`: xref of the person currently being viewed (the anchor)
- `link_xref`: xref of the existing person being linked
- `rel_type`: one of `parent_of | sibling_of | spouse_of | child_of`
- `other_parent_xref`: optional, applies to `child_of` only (same semantics as `/api/add_person`)

**Implementation:** Reuses the FAM-building logic from `/api/add_person` lines 1841–1939 in `serve_viz.py`, but skips the INDI-creation step. Creates or finds the correct FAM record and inserts the appropriate HUSB/WIFE/CHIL tag.

**Response:** Same shape as `/api/add_person`:
```json
{
  "ok": true,
  "xref": "@I456@",
  "people": { ... },
  "family_maps": { ... }
}
```

### Files Modified

| File | Change |
|------|--------|
| `viz_ancestors.html` | Add search panel and preview panel `<div>`s inside `#add-person-modal` |
| `js/viz_modals.js` | Add `_addPersonMode`, `_addPersonLinkXref` state vars; add `_renderAddPersonSearch()`, `_selectAddPersonExisting()`, `_showAddPersonPanel(mode)` functions; modify `openAddPersonModal()` to open in search mode; modify `submitAddPersonModal()` to route to `/api/link_person` when in preview mode, `/api/add_person` when in create mode (unchanged behavior) |
| `serve_viz.py` | Add `/api/link_person` handler that extracts and reuses the FAM-building logic from `/api/add_person` |

### Testing

**JS tests** (`tests/js/viz_modals.test.js`):
- Search panel renders existing matches + "Add new" row
- Clicking existing result populates `_addPersonLinkXref` and switches to preview panel
- Clicking "Add new" pre-fills given name and switches to create panel
- Back button from preview returns to search panel
- Back button from create panel returns to search panel
- Preview shows name, lifespan, spouse
- Other parent row visible only for `child_of` in preview panel

**Python tests** (`tests/test_link_person.py`):
- `/api/link_person` with `parent_of` writes correct HUSB/WIFE FAM tag
- `/api/link_person` with `sibling_of` adds CHIL to existing family
- `/api/link_person` with `spouse_of` creates new FAM record
- `/api/link_person` with `child_of` adds CHIL; respects `other_parent_xref`
- No new INDI record is created in any case
- Returns correct `people` and `family_maps` for affected xrefs

### Verification

1. Start the dev server: `python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged`
2. Open a person with known relatives in the tree
3. Click "+ Spouse" — modal opens in search mode
4. Type part of an existing person's name — results appear with "Add new" at the bottom
5. Select an existing person — preview panel shows name, lifespan, spouse
6. Click "Confirm link" — relationship appears in the family section
7. Click "+ Child" — type a name, select "Add new" — create panel opens with name pre-filled
8. Run JS tests: `npm test`
9. Run Python tests: `GED_FILE=... pytest tests/test_link_person.py`
