# Viz Expand-Layout Bugs

Diagnostic playbook for the class of bug where **expanding a chevron places nodes in the wrong horizontal position** (overlapping, far off, "crossing over" another cluster). Read this before touching `js/viz_layout.js` if any of the trigger phrases below match.

---

## When to read this doc

Trigger on any of these symptoms:

- "Expanded children appear past/over another cluster"
- "Sibling's kids land to the right of focus's kids" (or vice-versa)
- "Cluster lines cross / umbrella crosses another umbrella"
- "Layout is fine until I expand X, then everything shifts"
- "Tests pass but the chart still looks wrong"
- Any change to `_placeChildrenOfPerson`, `_packRowWithDescendants`, `_descendantHalfwidth`, or Phase 1/2/3 code in `computeLayout`

---

## Mental model: how expand-layout actually works

The codebase's *top-level strategy* — incremental, lazy expansion via `expandedChildrenPersons` / `expandedAncestors` / `expandedSiblingsXrefs` — is correct. It's the standard way commercial genealogy tools sidestep the NP-hard global-layout problem. **The bugs are not in lazy expansion; they're in the within-frame placement mechanism.**

Within a single recompute, `computeLayout` runs in three phases. **Each phase can only see what earlier phases emitted** — that's where every bug in this class lives.

| Phase | What it places | Sees from earlier phases |
|-------|---------------|--------------------------|
| **1** | Focus row: focus, spouses, siblings, sibling-spouses; then ancestors | Nothing (first phase) |
| **2** | Focus's children (`y=ROW_HEIGHT`) | Focus + spouses' positions |
| **3** | Children of every other person in `expandedChildrenPersons` | Everything from 1 + 2 |

**The one trick that fixes most bugs in this class:** Phase 1 packs siblings using `_descendantHalfwidth` to reserve room between *adjacent* siblings, but it cannot see focus's children (they don't exist yet). So **any sibling boundary that touches focus must reserve space for both subtrees explicitly** — `_descendantHalfwidth` alone won't do it.

---

## The eight gotchas

### 1. Phase ordering blinds the sibling packer
The packer accounts for adjacent siblings' descendant halfwidths but not for focus's children. A sibling next to focus that has its own expanded children needs room on both sides — bug class: "sibling's child cluster spills past focus's children." Bug only shows when *both* sides have expanded kids; one-sided tests miss it.

**Fix pattern**: pre-adjust `olderSibsAnchor` / `youngerSibStartX` using a Phase-2-preview helper (e.g. `_focusChildrenExtents`). Don't try to fix it in Phase 3.

**Mirror gotcha for focus's own children:** Phase 2's `buildGroup` (focus children) didn't reserve room for *grandchildren* clusters either. When two adjacent gen-1 siblings each have an expanded gen-2 cluster, Phase 3's `_placeChildrenOfPerson` has nowhere natural to place them and pushes via `pickStartInFreeGap`. Fix: thread `_descendantHalfwidth` into Phase 2's per-pair advance so gen-1 siblings are spaced wide enough that gen-2 clusters fit. The required cursor advance is `prev.width/2 + prev.halfRight + next.halfLeft - next.width/2 + INTER_FAM_GAP`; falls back to `prev.width + H_GAP` when neither side has descendants (otherwise the formula widens unrelated rows by ~84px and breaks plain-children tests).

### 2. `pickStartInFreeGap` is a fallback, not a layout strategy
When the ideal position can't fit, `pickStartInFreeGap` picks the nearest valid gap — which can be infinitely far (`-Inf` or `+Inf`) from the ideal. **If you ever see "expanded children landed past another cluster," it's almost always a Phase 1/2 anchoring bug, not a Phase 3 bug.** Don't add cluster-shifting logic to Phase 3 to compensate. Find the upstream phase that should have left enough room.

### 3. Coordinate convention is asymmetric for focus
- `focus.x = 0` means *left edge* at 0; center at `NODE_W_FOCUS / 2 = 58`.
- All other nodes: `node.x = left edge`, width `NODE_W = 100`.
- `FOCUS_TO_SIB = NODE_W_FOCUS/2 + H_GAP + NODE_W/2 = 120`. This is the value passed as `lastLeftEdge` for older sibs — it's the **left edge** of the rightmost older sib relative to focus, not a center distance.

When reasoning about positions, always say which one (left edge / center) and use both `NODE_W_FOCUS` and `NODE_W` correctly.

### 4. Spouse insertion shifts older sibs *after* the packer
`_packRowWithDescendants` outputs sibling positions, then a right-to-left loop inserts each older sib's spouse to its LEFT and shifts already-placed sibs further left by `NODE_W + SIB_MARRIAGE_GAP = 112` per spouse. Younger-sib loop does the mirror (left-to-right, shift right).

So `xs[i+1] - xs[i]` from the packer ≠ final post-render distance between sibs. When debugging, compute: "packer center distance" + "spouse-insertion shift accumulated for the right-of-pair." See lines 173–195 / 322–340 of `viz_layout.js`.

### 5. `_descendantHalfwidth` is conservative-symmetric
It adds `(SIB_MARRIAGE_GAP + NODE_W) / 2 ≈ 56px` of spousal offset to **both** sides because it doesn't know which side the on-row spouse is on. For older sibs (spouse always inserted on left) it overcounts the right side; younger sibs vice-versa. Conservative is fine — it just adds whitespace. Don't tighten it unless you're prepared to thread spouse-side through every caller.

### 6. The focus pill is the lower bound on the left/right edge
For computing "where does focus's content end on side X," use `Math.min` with the focus pill edge. If focus has a right spouse, the visible-FAM children are pushed right of focus center, so focus's *leftward* extent is just the pill itself (`NODE_W_FOCUS/2`). Don't assume children always extend the bounds.

### 7. `effectiveExpandedAncestors` is a force-expand, not a generic union
At the top of `computeLayout`, `effectiveExpandedAncestors = expandedAncestors ∪ expandedSiblingsXrefs`. This force-expand exists for one specific reason: **an ancestor-row sibling group needs the parents above it placed so the umbrella can hang from a real anchor.** It is NOT a generic "treat sibling-expand as ancestor-expand everywhere."

Bug pattern: code that gates Phase 1.5 (focus-spouse subtree) on `effectiveExpandedAncestors.has(spouse)` runs even when the user only expanded the spouse's siblings. Spouse-siblings sit at gen 0 and need no umbrella, so this leaks `_placeAncestors`/`_placeAncestorSiblings` calls that emit duplicate nodes (siblings show up as both `spouse_sibling` from Phase 1 and `ancestor_sibling` from Phase 1.5).

**Rule**: gate gen-0 phases (Phase 1.5 focus-spouse loop) on the *original* `expandedAncestors`. Only deeper recursion into ancestor rows should consult the force-expanded set.

### 8.5. `role: 'descendant'` covers both focus-side and ancestor-side
A node with `role: 'descendant'` can sit at `y > 0` (a child/grandchild of focus on the visible-FAM side) **or** at `y < 0` (a child of an expanded ancestor-sibling — visually drawn as "descendant of the aunt/uncle"). Layout code that assumes "descendant means focus-side" will be wrong for the second case.

This bites layout-correctness invariants in particular: an invariant like "child sits within its genealogical parent's pill x-span" holds for focus-side descendants but breaks for ancestor-side ones, because the cluster anchor is determined by packing constraints around the ancestor row, not by the parent's pill position. When writing such an invariant, gate on `n.y > 0` to restrict to focus-side descendants. See `tests/js/_layout_invariants.js` → `assertChildWithinParentSpanRange`.

### 8. Single-child anchor patterns share `umbrellaY` with multi-child crossbars
The multi-FAM design intentionally emits two umbrellas at the same `umbrellaY` — one for the visible-FAM cluster, one for the other-FAM cluster. A single-child cluster emits *no crossbar* (just an anchor drop above and a drop to the child, both at the same x). The `assertChildrenInParentClusterRange` invariant must therefore exempt drops based on a colinear vertical anchor edge above them, **not** on "no crossbars exist at this y." With multi-FAM, other unrelated umbrellas can sit at the same y; the single-child drop is still valid.

**Rule** (assertion-side): a drop is valid if (a) it falls within some crossbar at its top y, OR (b) there's a colinear vertical edge above it (signature of single-child anchor). Don't gate on "no crossbars exist at this y."

---

## Diagnosis playbook

When you hit a "wrong position after expand" bug:

1. **Reproduce with a failing test that dumps positions.** Add a `console.log` for every relevant node's `x` and `y` in a copy of the existing test. Run with `npx vitest run tests/js/viz_layout.test.js -t "your test"` and read the actual numbers. **Don't reason about positions abstractly first** — read them off the layout, then explain.

2. **Identify which phase placed each misplaced node.**
   - `y === 0` → Phase 1
   - `y === ROW_HEIGHT` and node's parent is focus → Phase 2
   - Otherwise → Phase 3 (`_placeChildrenOfPerson`)

3. **For Phase-3-placed nodes that landed wrong:** look at the obstacles already at `childY` when Phase 3 ran. Compute the gap widths between them. Compare to the cluster's required width. **If the cluster doesn't fit in the natural gap, the bug is upstream** — Phase 1 or Phase 2 didn't leave enough room. Don't fix in Phase 3.

4. **For obstacle-too-close bugs:** trace which phase placed the obstacle, then check whether that phase had enough information to know about the cluster that needed the gap. If not, that's where to add a preview/lookahead helper.

5. **Verify with a regression test that uses cluster widths *exceeding* the natural gap.** A test where the cluster *just barely* fits passes by accident — it catches the bug class but not the size threshold. Use enough children to make `cluster_width > min_natural_gap` so the test would fail without the fix.

---

## When NOT to fix it upstream: structurally impossible configurations

Not every "ugly layout after expand" report has a clean fix. Some genealogical configurations **cannot be drawn without line crossings, no matter how nodes are arranged.** Crossing-minimization for layered multitree graphs is NP-hard in general, and specific instances are provably unsatisfiable — e.g., three children who each marry someone whose parents you also want to display.

If you've checked all of:
- The natural gap is wide enough for the cluster
- All upstream phases have correct extent information
- No phase ordering / cascading-expansion issue applies

…and the layout still has crossings or awkward placement, **the configuration may simply not be drawable cleanly in node-link form**. Don't keep tweak-fixing.

Acceptable answers in this case:
- **Accept the crossings.** Per the genealogy-layout literature, every commercial tool eventually does. Minimize, don't eliminate.
- **Collapse the offending branch by default.** Hide the in-laws' parents until the user opts in.
- **Show that subgraph differently** — a callout, a list, or a separate matrix view (à la GeneaQuilts) for dense subgraphs.

**Trigger words in a bug report that suggest this case**: "crossings appear when I expand X *and* Y *and* Z" (combinatorial), "this only happens with cousin marriages / intermarriage" (cycle), "the in-laws of multiple children" (constraint conflict). When you see these, consult `genealogy-tree-layout` skill before chasing a layout fix.

---

## Where to add the fix

| Symptom | Likely fix location |
|---------|--------------------|
| Sibling's kids land past focus's kids | Phase 1 anchor (`olderSibsAnchor` / `youngerSibStartX`) |
| Focus child's grandchildren land past sibling | Phase 3 sort by parent x (already done) |
| Two adjacent siblings' kids overlap | `_descendantHalfwidth` underestimating; check if it's missing child-spouse widths |
| Cluster ends up at `+Inf` / `-Inf` of chart | `pickStartInFreeGap` couldn't fit it. Find the upstream phase that didn't leave a gap. |
| Children appear under wrong parent | Sort-by-parent-x in Phase 3 (already done) |
| Click-order changes the layout | Phase 3 iteration order (already sorted by parent x; verify regression hasn't sneaked in) |
| Two umbrellas merge into one visual line | Both anchored at same `umbrellaY` and overlapping anchor X — fix by placing clusters on **opposite sides** of personCenter |
| Multi-FAM other-cluster has gappy spacing inside | Other-FAMs cluster should be flat-by-birth-year with H_GAP, not segmented by FAM (`famXref: null` normalization) |
| Expanding person X renders nothing when X was placed by another expanded ancestor | Phase 3 must iterate to a fixed point — single linear pass misses cascading dependencies |

---

## Reusable patterns (proven solutions in this codebase)

### Preview-Phase-2 to constrain Phase 1
When Phase 1 packs siblings whose subtrees might collide with Phase 2's focus children, run a Phase-2 placement *preview* (no node emission) to get focus's child cluster extents, then constrain the sibling anchor accordingly. Example: `_focusChildrenExtents`. **Don't** reorder Phase 1/2 outright — Phase 1 also emits ancestors that depend on sibling positions.

### Pre-nudge before `pickStartInFreeGap`
When an ideal cluster start would land too close to a known obstacle on side X, *shift the ideal* on side X before calling `pickStartInFreeGap` to open the gap to exactly `nextClusterWidth + 2*CHEVRON_CLEARANCE`. Then call pickStartInFreeGap once. This is cheaper and clearer than two-pass placement-then-shift, and used in `_placeChildrenOfPerson` for the "obstacle past visible cluster" case (`2026-04-23-pre-nudge-visible-cluster-for-gap.md`).

### Opposite-side rule for two umbrellas at the same Y
Two umbrellas anchored at the same Y *cannot* be visually separated by widening their gap — they merge into one continuous line at `umbrellaY`. The only fix is to put them on opposite sides of the shared anchor X (e.g., visible-FAM cluster on marriage-midpoint side, other-FAMs on opposite-side-of-personCenter). See `_placeChildrenOfPerson` and `2026-04-21-fix-multi-fam-children-umbrella.md`. **The invariant is: two umbrellas' horizontal X-ranges at umbrellaY must be disjoint.**

### Phase 3 fixed-point iteration
Phase 3 cannot use a single linear pass over `expandedChildrenPersons` — a person may not exist in `nodes[]` until *another* expanded person's pass places them (e.g., grandma → her son → her son's kids). Iterate until no progress; re-sort by x each pass. Don't bound iterations by a fixed N (depth is unbounded). See `2026-04-28-phase3-fixed-point-iteration.md`.

### Phase 3 sort by parent x (not Set order)
`expandedChildrenPersons` is a Set whose iteration order = click order. Sort by `nodes.find(n => n.xref === x).x` (left→right) before placing. Otherwise a right-side parent expanded first occupies the interior gap and pushes left-side parents' kids past it. Already implemented; see `2026-04-25-phase3-sort-by-x.md`.

### Guard by `actual` placement, not `ideal`
After `pickStartInFreeGap` may have moved a cluster, any subsequent gap-enforcement push (e.g., INTER_FAM_GAP) must check the *actual* landed position, not the original ideal. If the cluster was pushed to the wrong side of `personCenter` by obstacles, skip the gap-enforcement entirely and let CHEVRON_CLEARANCE handle node-level collisions. See `2026-04-23-inter-cluster-gap-guard.md`.

---

## Anti-patterns (don't do these)

- **Tweak-fixing the same bug across multiple commits.** Three commits each making the symptom "less bad" is a signal the design is wrong. Stop, identify the *invariant being violated*, and fix at the level that enforces it (`2026-04-21-fix-multi-fam-children-umbrella.md` records 3 prior failed attempts before the disjoint-X-ranges fix).
- **Fixing layout bugs inside `pickStartInFreeGap`.** It only knows about node-level (NODE_W) obstacles, not cluster boundaries. Adjust `idealStart` *before* the call instead of teaching pickStartInFreeGap about clusters.
- **Asserting on edge objects / FAM groupings.** Tests can pass while the visual is broken. Assert geometric properties: disjoint cluster X-ranges, no horizontal at Y crosses anchor X, child x is between left-cluster-right and right-cluster-left.
- **Tightening conservative width estimates without threading spouse-side context.** `_descendantHalfwidth` is intentionally symmetric-conservative; making it asymmetric requires plumbing through *which side* the on-row spouse will be on, which the packer doesn't know at planning time. Accept the small extra whitespace.

---

## Related completion docs (consult for prior context on a similar bug)

| Doc | Bug class |
|-----|-----------|
| `2026-04-21-fix-multi-fam-children-umbrella.md` | Multi-FAM children umbrella merges into one crossbar |
| `2026-04-23-inter-cluster-gap-half-siblings.md` | Two clusters appear to "touch" — INTER_FAM_GAP enforcement |
| `2026-04-23-inter-cluster-gap-guard.md` | INTER_FAM_GAP push amplifies wrong-side placement |
| `2026-04-23-pre-nudge-visible-cluster-for-gap.md` | Other-cluster lands past obstacle instead of in the gap |
| `2026-04-24-middle-sibling-child-expand-bug.md` | `_descendantHalfwidth` underestimating cluster width |
| `2026-04-24-fix-parent-in-expandedChildrenPersons-duplicates-siblings.md` | Stale state duplicates focus-row nodes after navigation |
| `2026-04-25-merge-non-visible-fam-children-cluster.md` | Other-FAMs internal spacing should be H_GAP (flat) not INTER_FAM_GAP (segmented) |
| `2026-04-25-phase3-sort-by-x.md` | Click order changes layout — Phase 3 must sort by parent x |
| `2026-04-28-phase3-fixed-point-iteration.md` | Cascading expansions silently skipped — Phase 3 needs fixed-point loop |
| `2026-05-06-sibling-children-anchor.md` | Focus-sibling's kids overflow past focus's kids — Phase 1 anchor preview |

---

## The structural fix (if bugs keep recurring)

The skill `genealogy-tree-layout` covers the field's standard algorithms. The relevant insight: **lazy expansion is correct (keep it); within-frame placement is the buggy part.** The principled within-frame algorithm is **Reingold-Tilford** (1981, with Buchheim 2002's linear-time improvement) — every commercial genealogy tool uses some adaptation.

The shape of the fix:

1. **Bottom-up measure pass.** Walk every currently-expanded node. Each node computes its subtree's left/right contour (extent envelope on each side). Store on the node.
2. **Top-down place pass.** Walk again. Place each node, then place its children inside the parent's region. When packing two siblings, pack their *contours* together — not just node widths.

This eliminates the entire bug class: no phase ever has to predict downstream needs because every extent is precomputed. `_descendantHalfwidth` and `_focusChildrenExtents` are spot-fixes for *two* specific predictions — there are infinite more such predictions waiting in the multi-pass design.

**Tier-2 incremental version** (smaller change, ~80% of payoff): keep the existing phases, but generalize `_descendantHalfwidth` + `_focusChildrenExtents` into one universal extent pre-pass that annotates every node with `{leftExtent, rightExtent}` *before* any phase places anything. Phases stay; they just stop being blind.

**Tier-3 full version**: replace Phase 1/2/3 with a measure pass + place pass. Use the dual-tree model (McGuffin & Balakrishnan 2005) for ancestor + descendant from a focal person — run Reingold-Tilford twice (up, down) and align on the focus.

Genealogy-specific extensions Reingold-Tilford alone doesn't cover, but which all extend cleanly:
- On-row spouses → bundle person + spouse as one composite node before measuring
- Multi-FAM children clusters → one subtree with the opposite-side-of-anchor invariant in measure
- Expanded-on-demand → measure only what's currently expanded; recompute on state change (still O(n))

When to reach for tier 3: if the same bug class keeps recurring, or if scope grows (dual-tree views, pedigree collapse, thousands of nodes). Until then, tier 2 contains the damage at a fraction of the effort.

**Property-based testing is worth doing regardless of architecture.** Random GED-shaped inputs + assertions ("no two clusters' x-ranges overlap at any Y," "every umbrella's horizontal range is disjoint from any other's at the same Y," "every child x is between its parent and on-row-spouse midpoint ± half-cluster-width") would have caught most of the bugs in the completion docs at PR time.

**Implemented**: `tests/js/viz_layout_property.test.js` — 200 seeds per `npm test` run, ~1.2s. Generator at `tests/js/_layout_generator.js`, shrinker at `tests/js/_layout_shrink.js`, invariants at `tests/js/_layout_invariants.js` (now wired through `computeLayoutChecked`). Failures reduce to a paste-able minimal input. `KNOWN_FAILURES` in the runner tracks open layout bugs without blocking CI.

---

## Related

- `docs/learnings/common-pitfalls.md` → "SVG edge geometry", "Phase 2 emitGroup vs sibling-row"
- `docs/learnings/viz-patterns.md` for the broader viz architecture
- Skill: `genealogy-tree-layout` — Reingold-Tilford, dual-tree model, GeneaQuilts, structural-impossibility theory. **Consult before any architectural change to the layout engine.**
