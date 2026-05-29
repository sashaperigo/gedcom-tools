# Relationship Path Popup — Design

**Date:** 2026-05-28
**Status:** Implemented (2026-05-28, branch `feat/relationship-path-popup`). Plan: `docs/superpowers/plans/2026-05-28-relationship-path-popup.md`. Completion: `.claude/completions/2026-05-28-relationship-path-popup.md`.

## Goal

In the detail panel, the relationship label (e.g. "6th Cousin 3× Removed") that
describes how the selected person relates to the viewer is currently static text
(with a narrow godparent-only inline expand). Make the label **clickable** to open
a modal that shows the **full relationship path** — the actual chain of people
connecting the two, with each person's name and birth–death years.

## UX (settled with user)

- **Trigger:** clicking the relationship label in the detail panel
  (`#detail-relationship`, rendered in `js/viz_panel.js`).
- **Surface:** a centered modal overlay, reusing the existing modal pattern
  (`#xxx-modal-overlay > #xxx-modal`, `.open` class toggle, `closeIfFarFromPanel`
  for click-outside, Escape to close).
- **Orientation:** **the other (selected) person at the top, the viewer ("You")
  at the bottom.** The chain reads top→bottom: other → … → common ancestor → … → you.
- **Per person:** name + `(birth–death)` years. Each name is **clickable**: clicking
  navigates/re-centers the chart on that person and closes the modal.
- **Between people:** a kinship step term with an up-arrow, e.g. "↑ daughter of".
- **Common ancestor (MRCA):** flagged with a marker ("common ancestor").

## Scope

**v1 — blood relationships only.** The label is clickable only when the displayed
relationship is a blood path (cousins, removed cousins, aunts/uncles, niblings,
grand-relations, siblings, direct ancestors/descendants, self). This covers the
large majority of "interesting path" cases, including the motivating example.

When the displayed relationship is **affinity** (spouse, in-law, step, "X of Y") or
**godparent**, the label is **not** clickable in v1; the existing godparent-only
inline expand in `viz_panel.js` stays as-is for that case.

## Future work (explicitly deferred)

1. **Option 2 — full coverage:** ✅ **IMPLEMENTED (2026-05-29).** Affinity / in-law /
   step / godparent / composed relationships are now clickable, with chains that
   include marriage and godparent edges and "of"-composition, plus a kind switcher.
   Spec: `docs/superpowers/specs/2026-05-28-relationship-path-nonblood-design.md`;
   plan: `docs/superpowers/plans/2026-05-28-relationship-path-nonblood.md`;
   completion: `.claude/completions/2026-05-29-relationship-path-nonblood.md`.
   (Done via "Approach A" — the affinity tiers now emit the matched xrefs as a path
   spec, rather than re-deriving them.)
2. **Multiple relationship paths:** when more than one path connects the two people
   (pedigree collapse / intermarriage), let the user toggle between paths. v1 shows
   only the single closest path (the one the displayed label is based on).

## Architecture

### 1. Path reconstruction — `js/viz_relationship.js`

New **pure, DOM-free** function:

```
buildRelationshipPath(viewerXref, otherXref, ctx, precomputedPath?) -> Array | null
```

- If `precomputedPath` (the closest `{a, b, mrca, viewerLeg, otherLeg}` already
  computed by the panel) is supplied, use it directly — **no graph traversal**.
  Otherwise fall back to `findBloodPaths` + `pickClosestPath` (self-contained mode,
  used by unit tests).
- Reconstruct the two legs using the back-pointers `bfsUp` already records
  (`viaParentXref` = the node one hop closer to the BFS start). Ascend from
  `viewer` to `mrca` (length `a`) and from `other` to `mrca` (length `b`); the
  reconstruction itself is **O(a + b)**.
- Return an ordered array, **other → MRCA → you**. Each element:
  ```
  { xref, isMrca, isViewer, isOther, relToNext }
  ```
  `relToNext` describes how this person relates to the *next person down the list*
  ("daughter of" / "son of" / "father of" / "mother of" / neutral), derived from
  the lower person's role and the upper person's sex. **Direction flips at the
  MRCA:** above the MRCA each person is the child of the one below (so "… of"
  points at a parent); below the MRCA each person is the parent of the one below.
- Returns `null` when there is no blood path (label not clickable).

Name/year lookups stay OUT of this function — the renderer resolves those via
`PEOPLE` / `_personName`.

### 2. Panel integration — `js/viz_panel.js` (~line 683)

The panel already calls `computeRelationship`, which internally computes the blood
paths and picks the closest. Capture that closest path there. Make the label
clickable whenever `rel.debug` indicates a blood path (`a`/`b` present; not
affinity, not godparent-only). The click handler passes the captured path into
`buildRelationshipPath` (**zero extra traversal**) and opens the modal.

The existing godparent-only inline expand remains for the non-blood case.

### 3. Modal shell + open/close

- **`viz_ancestors.html`:** add static `#relpath-modal-overlay > #relpath-modal`
  with a title, close button, and empty `#relpath-modal-body`, matching the
  note/event modal pattern.
- **`viz_ancestors.css`:** styles consistent with existing modals.
- **New JS** (in an appropriate `viz_modal_*.js`): `showRelationshipPathModal(...)`
  and `closeRelationshipPathModal()`. Click-outside via `closeIfFarFromPanel`;
  Escape closes.

### 4. Rendering the chain (modal JS)

From the ordered array, build DOM rows: each row = name + `(birth–death)`
(resolved via `_personName` / `PEOPLE`), with the `relToNext` term + up-arrow
between rows. MRCA row gets the "common ancestor" marker; viewer row marked "You".
Each name is a clickable link calling the existing person-selection function, then
closing the modal. Rendering is O(a + b) DOM nodes.

## Efficiency

A click costs one on-demand computation, not anything per-frame or per-node:
- With the reuse optimization, the click does **zero** extra graph traversal —
  it reuses the path the panel already computed to draw the label, then does the
  O(a + b) back-pointer walk to assemble the chain.
- The only expensive primitive in this file, `findBloodPaths`'s per-ancestor
  `bfsDown`, already runs on every person selection today; this feature does not
  increase how often it runs.

## Testing

- **Unit tests for `buildRelationshipPath`** (pure, no DOM): cousins, removed
  cousins, aunt/uncle, grandparent, sibling, direct ancestor/descendant, self.
  Assert: ordering (other first, you last), MRCA flagged, correct `relToNext`
  including the direction-flip at the MRCA. (Half-vs-full does not affect path
  structure.) Both self-contained mode and `precomputedPath` mode.
- **Render/DOM test** if the JS harness supports it (it injects globals like
  `PEOPLE`); otherwise assert on the path data structure, per the codebase's
  "test what the user sees / test structure when DOM is impractical" guidance.
- Follow project TDD: write tests before implementation.
