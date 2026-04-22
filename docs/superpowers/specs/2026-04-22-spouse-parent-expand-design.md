# Spouse Parent-Expand Chevron — Design

**Date:** 2026-04-22
**Status:** Approved for implementation

## Summary

Extend the existing parent-expand chevron (today shown only above focus-side ancestor pills) to also appear above the focus person's spouse when that spouse has parents. Clicking the chevron expands/contracts the spouse's parents using the same machinery that powers focus-side ancestor expansion, giving parity with how any other ancestor pill behaves.

## Motivation

Today, when Maria Borg is the focus and her spouse Emanuele Bonnici has parents in the GEDCOM, there is no way to bring them onto the canvas. Users expect the spouse side of the tree to be just as explorable as the focus side.

## Scope

**In scope**

- The focus person's currently-displayed primary spouse only — nodes with `role === 'spouse'` at `generation === 0`.
- Recursive behavior: once the spouse's parents render (as role `'ancestor'`), they automatically get their own parent-expand and sibling-expand chevrons via the existing render path.

**Out of scope**

- `role: 'spouse_sibling'` and `role: 'ancestor_sibling_spouse'` — no chevron on those.
- Layout collision handling between the focus-parents subtree and the spouse-parents subtree when both are expanded. Ship simple; iterate only if real GEDCOM data exposes overlap.
- Pedigree-collapse edge cases (spouse is also an ancestor of focus).
- Primary-spouse switching logic (`viz_primary_spouse.js`) is untouched.

## Design

### 1. Chevron rendering — `js/viz_render.js`

The current parent-expand block (at `viz_render.js:301`) is gated on `isAncestor`:

```js
if (isAncestor) { /* draw chevron if PARENTS[node.xref] non-empty */ }
```

Extend the gate to include the focus spouse:

```js
const canShowParentChevron = isAncestor || (node.role === 'spouse' && node.generation === 0);
if (canShowParentChevron) { /* same body as today */ }
```

Same SVG (r=8 circle + up/down chevron), same classes (`expand-btn btn-expand` / `btn-collapse`), same `onExpandClick(node.xref)` handler. No CSS changes.

### 2. State

Reuse the existing `expandedNodes` state set (referred to internally as `expandedAncestors`). Clicking the spouse's chevron toggles the spouse's xref in that set. No new state key, no schema change, no URL-state change beyond what `expandedNodes` already round-trips.

### 3. Layout — `js/viz_layout.js`

In `computeLayout`, after the focus spouse node is pushed (current code around lines 203 / 266 — the two code paths that place a spouse at generation 0), add:

```js
_placeAncestorSiblings(spouseXref, spouseX, 0, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
_placeAncestors(spouseXref, spouseX, 0, 0, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
```

Rationale:

- `_placeAncestors` already short-circuits when `!expandedAncestors.has(xref)`, so it is a no-op when the spouse chevron hasn't been clicked.
- It recursively handles grandparents, great-grandparents, sibling-expand, and emits `type: 'ancestor'` edges — so once the spouse's parents are on screen as role `'ancestor'`, all further expansion works for free.
- `_placeAncestorSiblings` is called for parity: a chevron-expanded spouse behaves like any other ancestor anchor, including (in the future) being able to show its own siblings via the sibling chevron on the spouse. If this causes visual noise in practice, it can be dropped without affecting the parent-expand feature.

### 4. Collision handling

Deferred. When the user first exercises this feature on real data, if the spouse's parents visually overlap the focus's right parent, we revisit with a shift-the-focus-parents-subtree-left adjustment. No collision code ships in this change.

### 5. Tests — `tests/test_viz_ancestors_rendering.py`

- **Chevron presence:** focus spouse has parents → layout/render surface reports a parent-expand affordance on the spouse node; focus spouse has no parents → no affordance.
- **Expansion places nodes:** with spouse xref in `expandedNodes`, layout produces nodes for each of the spouse's parents at `y === -ROW_HEIGHT` with `role === 'ancestor'`.
- **Recursive expansion:** with both spouse and spouse's father in `expandedNodes`, the spouse's grandparents appear at `y === -2 * ROW_HEIGHT`.
- **No regression:** existing focus-side ancestor expansion tests continue to pass unchanged.

Tests follow existing patterns in `test_viz_ancestors_rendering.py`; no new fixtures required beyond small inline GEDCOM snippets.

## Files touched

- `js/viz_render.js` — extend parent-expand chevron gate.
- `js/viz_layout.js` — two new calls in `computeLayout` after spouse placement.
- `tests/test_viz_ancestors_rendering.py` — new test cases.

## Risks

- **Layout overlap** between focus-parents and spouse-parents subtrees when both expanded. Accepted risk; revisit after first real-data sighting.
- **Sibling chevron on spouse** (from step 3's `_placeAncestorSiblings` call) may surface a chevron that looks odd on a spouse pill if the spouse has many full siblings. Easy to drop if it does.
