# Task Completion: Non-Blood Relationship Paths

**Date**: 2026-05-29
**Branch**: feat/relationship-path-nonblood

---

## What was done

Extended the relationship-path modal (previously blood-only) so **every** relationship label in the detail panel is clickable and renders a full people-chain: spouse, step-parent/child/sibling, the in-laws, godparent/godchild, and one-level composed labels ("Wife of 1st Cousin"). When a person has more than one relationship to the viewer, the modal shows a tab switcher (primary path default). Implements the v1 spec's deferred "Future work item 1 — Option 2: full coverage."

Spec: `docs/superpowers/specs/2026-05-28-relationship-path-nonblood-design.md`
Plan: `docs/superpowers/plans/2026-05-28-relationship-path-nonblood.md`

## Files changed

- `js/viz_relationship.js` — the path-spec model. New `{nodes, edges, mrcaIndex}` "path spec" (display order other→you) + helpers `_spouseStep`/`_godparentStep`/`_godchildStep`, `_stepTerm`, `_stepsToPath`, `_bloodPathSpec`. Each `findAtomicAffinity` tier and `findGodparentAtomic` now emit a spec alongside the label; `_bestRel` concatenates specs across "of" composition (blood-relative split + spouse split); `enumerateRelationships` attaches a rendered `path` to every entry. `buildRelationshipPath` re-expressed on the shared helpers (output unchanged). Dead `findAffinityLabel` deleted.
- `js/viz_modal_relpath.js` — `edgeKind`→glyph map (↑/↓/⚭/✝); `showRelationshipPathModal(entries, title)` takes an entry list and renders a tab bar (`_renderRelationshipTabs`/`_selectRelationshipTab`) when >1 renderable entry; tab bar cleared on close.
- `js/viz_panel.js` — removed the blood-only gate and the inline `<ul>` godparent expand; every non-Self label opens the modal via `enumerateRelationships` (reusing the warmed `relCtx`). Self stays non-clickable.
- `viz_ancestors.css` — `.relpath-tabs` / `.relpath-tab` styles.
- `tests/js/viz_relationship.test.js` — new `edgeKind` blood test + `enumerateRelationships — affinity paths` block (atomic per-tier, composition, multi-relationship, label-parity guard).

## Key decisions

- **Approach A (single source of truth):** the path is emitted as a byproduct of the same tier match that produces the label, so label and path can never disagree. A `label-parity` test locks the invariant. (Rejected: a parallel path re-deriver, which would duplicate tier logic and risk drift — `COMMON_MISTAKES.md #5`.)
- **`mrcaIndex` only for genuine viewer-side blood apexes** — pure-blood paths and the blood-relative composition set it; atomic in-law tiers (3b/3c, whose blood apex sits between two non-viewer people) leave it `null`. "Common ancestor" shows only when the viewer's own blood connection is what the chain hinges on.
- **Terms gendered by the upper node; glyphs direction-agnostic within a pair** (spouse/ex-spouse share ⚭, godparent/godchild share ✝) — the adjacent term carries direction/divorce.
- **Switcher tabs are by relationship kind, not alternate blood paths** — multi-path-for-pedigree-collapse stays deferred (see gaps).
- **Efficiency:** path emission is free per render; the switcher's `enumerateRelationships` runs only on click, reusing the warmed `relCtx`'s `_bloodCache`/`_godparentIndex`. Not folded into `computeRelationship` (would move cost onto every selection).

## Tests added/modified

- `tests/js/viz_relationship.test.js` — blood-chain `edgeKind`; one path case per affinity tier (spouse, ex-spouse, step-parent/child/sibling, parent-/sibling(3b,3c)-/child-in-law, godparent, godchild); composition ("Wife of 1st Cousin", "Niece of Spouse"); multi-relationship (uncle+godfather, both entries carry a path, blood first); `label-parity` guard. Full suite green: 1574 tests.
- Browser glue (`viz_modal_relpath.js`, `viz_panel.js`) has no unit tests by convention — covered by the manual gate.

## Follow-up / known gaps

- **Manual verification gate** (plan Task 7) — not yet walked by a human: run `serve_viz.py` with the canonical GED path and confirm spouse/in-law/step/godparent/composed labels each open correct chains, tabs switch, name-click recenters, Escape/click-outside close, Self not clickable.
- **Deferred:** multiple *blood* paths for pedigree collapse/intermarriage (the switcher toggles relationship kinds, not alternate paths of one kind); composition beyond one "of" (`_MAX_REL_DEPTH` stays 1).
- **Minor (from code review, not fixed):** if every entry's path is null (rare broken `_reconstructLeg` leg), the label still looks clickable but the modal no-ops. Gating it would require eager `enumerateRelationships` on every render — rejected for the per-selection cost.

## Related docs

- `.claude/completions/2026-05-29-task3-composed-path-specs.md` — Task 3 detail (composition math).
- `docs/learnings/testing-patterns.md` — MRCA-stability / `isFullRelationship` fixture pitfalls found writing composition tests.
- `.claude/COMMON_MISTAKES.md #6` — `_bestRel` re-wraps atomic results and drops new fields.
