# Relationship Path Popup — Non-Blood Relations — Design

**Date:** 2026-05-28
**Status:** Designed.
**Builds on:** `docs/superpowers/specs/2026-05-28-relationship-path-popup-design.md`
(v1, blood-only). This is that spec's deferred **"Future work item 1 — Option 2:
full coverage"**.

## Goal

In the detail panel, the relationship label is clickable to open the path modal —
but only for **blood** relationships today. Extend it so **every** relationship the
label engine produces is clickable and renders a full people-chain: spouse, step
(parent/child/sibling), the in-laws, godparent/godchild, and one-level composed
labels ("Wife of 1st Cousin", "Father-in-law of Aunt"). When a person has more than
one relationship to the viewer, the modal shows the primary one with a switcher to
the others.

## Decisions (settled with user)

- **Scope:** all non-blood labels the engine produces, including one-level "X of Y"
  composition. (The engine caps composition at `_MAX_REL_DEPTH = 1`, so every
  producible label has a bounded path: at most a blood leg plus one cross-edge, or
  2–3 atomic hops.)
- **Connectors:** symbol + gendered term. Descent keeps v1's ↑/↓; marriage uses ⚭
  with a gendered term ("wife of"/"husband of"/"spouse of", "ex-…" when divorced);
  godparent uses ✝ ("godmother of"/"godfather of"/"godparent of",
  "goddaughter of"/etc. for the godchild direction). The term is gendered by the
  **upper** node's sex, consistent with v1.
- **Multiple relationships:** modal shows the **primary** (displayed/closest) path
  with a compact tab/segmented switcher to the other relationship kinds; one chain
  visible at a time; default tab = primary.
- **Approach A** (single source of truth): the affinity tiers emit the path as a
  byproduct of the same match that produces the label, so label and path can never
  disagree. (Rejected: B, a parallel re-deriver that duplicates tier logic and risks
  drift — see `COMMON_MISTAKES.md #5`; C, parsing labels back into xrefs — fragile.)

## The core problem

v1's `buildRelationshipPath` reconstructs the blood chain by walking `bfsUp`
back-pointers, so it has the intermediate **xrefs**. The affinity engine
(`findAtomicAffinity`, `_bestRel`, `findGodparentAtomic`, `enumerateRelationships`)
holds those xrefs in local variables (`par`, `sp`, `sib`, `child`, the matched
spouse) but returns only a **label string**. The fix is to collect those xrefs
instead of discarding them.

## Architecture

### 1. Normalized path data model

A path is an ordered array, **other (top) → … → you (bottom)** — v1's shape with two
fields added so the renderer can pick a non-descent glyph:

```js
{
  xref,
  isViewer, isOther,
  isMrca,      // true only on a blood apex; absent in pure-affinity chains
  relToNext,   // gendered lowercase term, e.g. "wife of", "godmother of", "son of"
  edgeKind,    // 'descent-up' | 'descent-down' | 'spouse' | 'ex-spouse' | 'godparent'
}
```

`edgeKind` → glyph in the renderer: `descent-up` ↑, `descent-down` ↓,
`spouse`/`ex-spouse` ⚭, `godparent` ✝. Descent edges keep v1's exact arrow
convention (↓ on the other→apex leg, ↑ on the apex→you leg). `relToNext` is gendered
by the upper node's sex.

### 2. Engine refactor — `js/viz_relationship.js` (Approach A)

One normalized format, two producers:

- **Blood:** factor v1's in-function leg walk into a reusable
  `_bloodSteps(viewer, other, {a,b,mrca}, ctx)` returning the viewer→other step-list.
  `buildRelationshipPath`'s blood branch becomes a thin caller.
- **Affinity:** each tier in `findAtomicAffinity` changes its return from
  `{label, edges}` to `{label, edges, steps}`, where `steps` is the ordered
  `[{xref, edgeKind, sex}]` from viewer→other for that tier. `findGodparentAtomic`
  emits a one-edge godparent step.
- **Composition in `_bestRel`:** the two split points concatenate step-lists —
  blood-relative split = `bloodSteps(V→Z) ++ atomicSteps(Z→other)`; spouse split =
  `[spouse edge] ++ subSteps`. `_bestRel`'s return gains `steps`.
- **`computeRelationship`** records the winning `steps` on its result.
- **Delete dead `findAffinityLabel`** (exported but called nowhere — a stale
  near-duplicate of `findAtomicAffinity`; removing it prevents future drift) and drop
  it from the exports.

A small `_stepsToPath(steps, ctx)` converts a viewer→other step-list into the
normalized **other→you** render array, tagging a blood apex as `isMrca` where one
exists. `buildRelationshipPath` becomes the dispatcher: blood `{a,b,mrca}` →
`_bloodSteps` → `_stepsToPath`; affinity `steps` → `_stepsToPath`.

### 3. Switcher data flow

`enumerateRelationships(viewer, other, ctx)` is extended so each entry carries its
rendered path:

```js
{ kind: 'blood' | 'affinity' | 'godparent', label, path /* normalized array */ }
```

It already computes the blood path and runs `_bestRel` (now returning `steps`) and
`findGodparentAtomic` (now emitting a step), so attaching `path` is just running each
through `_stepsToPath`. The **primary** entry (matching the displayed label) is sorted
first.

### 4. Panel — `js/viz_panel.js`

Delete the blood-only gate and the inline `enumerateRelationships`-`<ul>` expand
(~lines 690–735). Every non-Self label becomes clickable (dotted underline, pointer,
"Click to see how you're related"). The handler builds **one warmed `relCtx`** (so
the viewer's blood BFS, memoized on `ctx._bloodCache`, and `ctx._godparentIndex` are
computed once), calls `enumerateRelationships`, and opens the modal. Self
(`a + b === 0`) stays non-clickable.

### 5. Renderer — `js/viz_modal_relpath.js`

- `_renderRelationshipPath` switches arrow logic from the `reachedMrca` boolean to a
  per-node `edgeKind` → glyph map (↑/↓/⚭/✝); the gendered term still comes from
  `relToNext`. The "common ancestor" tag renders only on a node with `isMrca`.
- `showRelationshipPathModal(entries, primaryIndex)` takes the entry list. One entry →
  no tabs (renders like v1). Multiple → a compact tab/segmented control above the
  chain plus `_selectRelationshipTab(i)` that re-renders the body for that entry;
  default = primary.
- Name-click-to-recenter and Escape / click-outside close are unchanged.

### 6. CSS — `viz_ancestors.css`

Add `.relpath-tabs` / `.relpath-tab` (+ active state); a spouse/godparent edge accent
(`.relpath-edge-spouse` / `-godparent`) if the glyphs need distinct color. Match the
existing modal styling.

## Efficiency

- **Per render / per selection: zero added cost.** `computeRelationship` already runs
  on every person selection to draw the label; emitting `steps` is a free byproduct
  (xrefs already in hand). `_bloodSteps` is the O(a+b) walk v1 already does.
- **On click: one extra relationship search.** The switcher needs the other
  relationships → `enumerateRelationships` (re-runs `findBloodPaths` + `_bestRel`).
  It fires only on click, never per-frame; and because the handler reuses one warmed
  `relCtx`, the viewer's blood BFS (`findAllBloodRelatives`, memoized on
  `_bloodCache`) and the godparent index are computed once and shared. The marginal
  cost is the same order as the label computation that already runs on every
  selection.
- Enumerate is deliberately **not** folded into `computeRelationship` — that would
  move the search onto every selection (strictly worse).

## Testing (TDD — tests before implementation)

**Unit — `tests/js/viz_relationship.test.js` (pure, no DOM):**

- `_bloodSteps` / blood `buildRelationshipPath`: regression on v1 cases — refactor
  preserves output.
- One affinity-path case per tier — assert ordered xrefs, `edgeKind`, gendered
  `relToNext`, and no spurious `isMrca`: spouse, ex-spouse, step-parent/child/sibling,
  parent-/sibling-/child-in-law (both sibling-in-law routes), godparent + godchild.
- Composition: "Wife of 1st Cousin" (spouse split) and a blood-relative split
  ("…-in-law of Aunt") — the concatenated chain has the blood apex tagged `isMrca`
  and the cross edge in the right position.
- `enumerateRelationships`: each entry carries a valid `path`; the
  cousin-who-is-also-godparent fixture yields two entries, primary first.
- **Label-parity guard:** for a sampling of fixtures, the path's derived label equals
  `computeRelationship`'s label (catches step/label drift — the Approach A invariant).

**DOM glue** (`viz_modal_relpath.js` tab switching, `viz_panel.js` wiring):
browser-only by codebase convention; covered by the manual gate, not unit-tested.

**Manual verification gate** (`serve_viz.py` + canonical GED path): spouse / in-law /
step / godparent labels each open a correct chain; a multi-rel person shows tabs that
switch; a composed label renders blood apex + cross edge; name-click recenters;
Escape and click-outside close; Self not clickable.

## Out of scope (still deferred)

- **Multiple *blood* paths** (pedigree collapse / intermarriage): v1 and this work
  show the single closest blood path. The switcher toggles between relationship
  *kinds*, not between alternate paths of the same kind.
- Composition beyond one "of" (`_MAX_REL_DEPTH` stays 1).
