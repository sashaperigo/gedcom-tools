# Non-Blood Relationship Paths — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every relationship label in the detail panel clickable — not just blood — opening the path modal with a full people-chain for spouse, step, in-law, godparent, and one-level composed ("Wife of 1st Cousin") relationships, with a tab switcher when a person has more than one relationship to the viewer.

**Architecture:** Approach A (single source of truth) from `docs/superpowers/specs/2026-05-28-relationship-path-nonblood-design.md`. Each affinity tier and `findGodparentAtomic` already hold their intermediate xrefs in locals; they now emit a display-order path spec `{ nodes, edges, mrcaIndex }` alongside the label. `_bestRel` concatenates specs across "of" composition. A single `_stepsToPath(nodes, edges, mrcaIndex, ctx)` converts a spec into the render array (other→you). `enumerateRelationships` attaches a rendered `path` to every entry; the panel passes the entry list to the modal, which renders a glyph per `edgeKind` (↑/↓/⚭/✝) and a tab bar when >1 entry.

**Tech Stack:** JavaScript ES modules (no bundler), vitest for unit tests. Pure path logic in `js/viz_relationship.js`; browser-only DOM glue in `js/viz_modal_relpath.js`, `js/viz_panel.js`, `viz_ancestors.css`.

**Conventions:**
- Run JS tests with `npm test` (or `npx vitest run tests/js/viz_relationship.test.js`).
- Commit with `git commit --no-verify` — the repo's pre-commit pytest hook fails on a pre-existing, unrelated GED trailing-whitespace issue (documented in `.claude/completions/2026-05-28-relationship-path-popup.md`). No Python is touched here.
- `docs/` is gitignored but spec/plan files are force-added (`git add -f`).

---

## File Structure

- **`js/viz_relationship.js`** (modify) — the path-spec model lives here: new helpers `_spouseStep`/`_godparentStep`/`_godchildStep`, `_stepTerm`, `_stepsToPath`, `_bloodPathSpec`; `findGodparentAtomic` and each `findAtomicAffinity` tier emit `path`; `_bestRel` composes `path`; `enumerateRelationships` attaches a rendered `path` to each entry; dead `findAffinityLabel` deleted. `buildRelationshipPath` keeps its exact v1 output (now built via the shared helpers).
- **`tests/js/viz_relationship.test.js`** (modify) — new `describe` blocks for blood `edgeKind`, atomic affinity paths, composed paths, multi-relationship entries, and a label-parity guard.
- **`js/viz_modal_relpath.js`** (modify) — `edgeKind`→glyph map; tab bar; `showRelationshipPathModal(entries, title)`.
- **`js/viz_panel.js`** (modify) — remove blood-only gate + inline `<ul>` expand; every non-Self label opens the modal via `enumerateRelationships`.
- **`viz_ancestors.css`** (modify) — `.relpath-tabs` / `.relpath-tab` styles.

---

## Task 1: Blood path refactor to the step-spec model (no behavior change)

Introduce the `{ nodes, edges, mrcaIndex }` spec and `_stepsToPath`, and re-express the existing blood `buildRelationshipPath` on top of them. Output must stay byte-for-byte compatible with v1 except for two **new additive** fields (`edgeKind`) on each node. Existing tests must stay green.

**Files:**
- Modify: `js/viz_relationship.js` (helpers near line 743; `buildRelationshipPath` lines 772–807)
- Test: `tests/js/viz_relationship.test.js` (append to the `buildRelationshipPath — structure` describe block, ~line 1132)

- [ ] **Step 1: Write the failing test** — append inside the `buildRelationshipPath — structure` describe block (after the existing cousins test, ~line 1212):

```javascript
  it('blood chain carries edgeKind per node (descent-down before MRCA, descent-up after)', () => {
    // First cousins: @O@ → @PB@ → @GP@(MRCA) → @PA@ → @V@
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@O@': { sex: 'F' },
        '@PA@': { sex: 'F' }, '@PB@': { sex: 'M' }, '@GP@': { sex: 'M' },
      },
      parents: { '@V@': ['@PA@', null], '@O@': ['@PB@', null], '@PA@': ['@GP@', null], '@PB@': ['@GP@', null] },
      children: { '@PA@': ['@V@'], '@PB@': ['@O@'], '@GP@': ['@PA@', '@PB@'] },
    });
    const path = buildRelationshipPath('@V@', '@O@', c);
    expect(path.map(n => n.edgeKind)).toEqual(['descent-down', 'descent-down', 'descent-up', 'descent-up', null]);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/js/viz_relationship.test.js -t "carries edgeKind"`
Expected: FAIL — `edgeKind` is `undefined` (field doesn't exist yet).

- [ ] **Step 3: Add the helpers and `_stepsToPath`** — in `js/viz_relationship.js`, immediately after the existing `_childStep`/`_parentStep` definitions (~line 744), add:

```javascript
function _spouseStep(sex, ex) { return (ex ? 'ex-' : '') + gendered(sex, 'husband of', 'wife of', 'spouse of'); }
function _godparentStep(sex)  { return gendered(sex, 'godfather of', 'godmother of', 'godparent of'); }
function _godchildStep(sex)   { return gendered(sex, 'godson of', 'goddaughter of', 'godchild of'); }

// Map an edgeKind + the UPPER node's sex to the lowercase chain term.
function _stepTerm(edgeKind, upperSex) {
  switch (edgeKind) {
    case 'descent-down': return _childStep(upperSex);
    case 'descent-up':   return _parentStep(upperSex);
    case 'spouse':       return _spouseStep(upperSex, false);
    case 'ex-spouse':    return _spouseStep(upperSex, true);
    case 'godparent':    return _godparentStep(upperSex);
    case 'godchild':     return _godchildStep(upperSex);
    default:             return null;
  }
}

// Convert a display-order path spec into the render array (other → … → you).
// `nodes` are xrefs top→bottom; `edges[i]` is the edgeKind from nodes[i] (upper)
// to nodes[i+1] (lower); `mrcaIndex` flags a blood apex (or null for none).
function _stepsToPath(nodes, edges, mrcaIndex, ctx) {
  return nodes.map((xref, i) => {
    const sex = (ctx.PEOPLE[xref] || {}).sex || null;
    const edgeKind = i < nodes.length - 1 ? edges[i] : null;
    return {
      xref,
      isOther: i === 0,
      isViewer: i === nodes.length - 1,
      isMrca: i === mrcaIndex,
      relToNext: edgeKind ? _stepTerm(edgeKind, sex) : null,
      edgeKind,
    };
  });
}
```

- [ ] **Step 4: Add `_bloodPathSpec` and re-express `buildRelationshipPath`** — replace the body of `buildRelationshipPath` (lines 772–807) and add `_bloodPathSpec` just above it:

```javascript
// Build a display-order blood spec {nodes, edges, mrcaIndex} for viewer↔other,
// given the closest path's {a, b, mrca}. Returns null on a broken back-pointer leg.
function _bloodPathSpec(viewer, other, pathInfo, ctx) {
  const { a, b, mrca } = pathInfo;
  const viewerChain = _reconstructLeg(viewer, mrca, a, ctx.PARENTS); // [mrca, ..., viewer]
  const otherChain  = _reconstructLeg(other,  mrca, b, ctx.PARENTS); // [mrca, ..., other]
  if (!viewerChain || !otherChain) return null;
  const nodes = otherChain.slice().reverse().concat(viewerChain.slice(1)); // other → … → you
  const mrcaIndex = b;
  const edges = nodes.slice(0, -1).map((_, i) => (i < mrcaIndex ? 'descent-down' : 'descent-up'));
  return { nodes, edges, mrcaIndex };
}

function buildRelationshipPath(viewerXref, otherXref, ctx, precomputedPath) {
  let a, b, mrca;
  if (precomputedPath && precomputedPath.mrca != null
      && precomputedPath.a != null && precomputedPath.b != null) {
    ({ a, b, mrca } = precomputedPath);
  } else {
    const paths = findBloodPaths(viewerXref, otherXref, ctx);
    if (paths.length === 0) return null;
    const p = pickClosestPath(paths);
    a = p.a; b = p.b; mrca = p.mrca;
  }
  const spec = _bloodPathSpec(viewerXref, otherXref, { a, b, mrca }, ctx);
  if (!spec) return null;
  return _stepsToPath(spec.nodes, spec.edges, spec.mrcaIndex, ctx);
}
```

- [ ] **Step 5: Run the full relationship suite to verify no regression**

Run: `npx vitest run tests/js/viz_relationship.test.js`
Expected: PASS — the new `edgeKind` test passes and **all** existing `buildRelationshipPath` / `computeRelationship` tests still pass (the render array is unchanged except for the additive `edgeKind` field, and `precomputed`-vs-`self-contained` still `toEqual`).

- [ ] **Step 6: Commit**

```bash
git add js/viz_relationship.js tests/js/viz_relationship.test.js
git commit --no-verify -m "refactor(viz): blood relationship path via step-spec model

Introduce {nodes, edges, mrcaIndex} spec + _stepsToPath; re-express
buildRelationshipPath on top of them and add per-node edgeKind. No
behavior change to the rendered blood chain.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Atomic affinity + godparent tiers emit paths; `enumerateRelationships` attaches them

Each tier in `findAtomicAffinity` and `findGodparentAtomic` returns a display-order `path` spec. `enumerateRelationships` runs every entry's spec through `_stepsToPath` and exposes `entry.path`. Delete the dead `findAffinityLabel`.

**Files:**
- Modify: `js/viz_relationship.js` (`findGodparentAtomic` 208–225; `findAtomicAffinity` 285–382; `enumerateRelationships` 709–738; delete `findAffinityLabel` 511–656; exports line 810)
- Test: `tests/js/viz_relationship.test.js` (new describe block at end of file)

- [ ] **Step 1: Write the failing tests** — append a new describe block at the end of `tests/js/viz_relationship.test.js`:

```javascript
describe('enumerateRelationships — affinity paths', () => {
  // Pull the entry of a given kind and return its rendered path array.
  function pathOf(rels, kind) {
    const e = rels.find(r => r.kind === kind);
    return e ? e.path : null;
  }

  it('spouse: other → you, single spouse edge', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@S@': { sex: 'M' } },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@S@', wife: '@V@', chil: [] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@S@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@S@', '@V@']);
    expect(p[0]).toMatchObject({ isOther: true, edgeKind: 'spouse', relToNext: 'husband of', isMrca: false });
    expect(p[1]).toMatchObject({ isViewer: true, relToNext: null });
  });

  it('mother-in-law: parent of viewer spouse (descent-up then spouse)', () => {
    const c = ctx({
      people: { '@V@': {}, '@S@': { sex: 'F' }, '@SM@': { sex: 'F' } },
      parents: { '@S@': [null, '@SM@'] },
      children: { '@SM@': ['@S@'] },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SM@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SM@', '@S@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-up', 'spouse', null]);
    expect(p[0].relToNext).toBe('mother of');
    expect(p[1].relToNext).toBe('wife of');
    expect(p.some(n => n.isMrca)).toBe(false);
  });

  it('step-mother: spouse of bio father (spouse then descent-up)', () => {
    const c = ctx({
      people: { '@V@': {}, '@DAD@': { sex: 'M' }, '@STEPMOM@': { sex: 'F' }, '@BIOMOM@': { sex: 'F' } },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'] },
      relatives: { '@DAD@': { spouses: ['@BIOMOM@', '@STEPMOM@'] }, '@STEPMOM@': { spouses: ['@DAD@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@STEPMOM@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@STEPMOM@', '@DAD@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['spouse', 'descent-up', null]);
    expect(p[0].relToNext).toBe('wife of');   // step-mom (F) spouse of dad
    expect(p[1].relToNext).toBe('father of');  // dad (M) parent of you
  });

  it('godparent: single godparent edge', () => {
    const c = ctx({
      people: {
        '@V@': { events: [{ tag: 'BAPM', asso: [{ xref: '@GM@', rela: 'Godmother' }] }] },
        '@GM@': { sex: 'F' },
      },
    });
    const p = pathOf(enumerateRelationships('@V@', '@GM@', c), 'godparent');
    expect(p.map(n => n.xref)).toEqual(['@GM@', '@V@']);
    expect(p[0]).toMatchObject({ edgeKind: 'godparent', relToNext: 'godmother of' });
  });

  it('ex-spouse: edgeKind ex-spouse with ex- term', () => {
    const c = ctx({
      people: { '@V@': { sex: 'M' }, '@S@': { sex: 'F' } },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [], divorced: true } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@S@', c), 'affinity');
    expect(p[0]).toMatchObject({ edgeKind: 'ex-spouse', relToNext: 'ex-wife of' });
  });

  it('step-child: descent-down then spouse', () => {
    const c = ctx({
      people: { '@V@': {}, '@SP@': { sex: 'F' }, '@SD@': { sex: 'F' }, '@SDX@': { sex: 'M' } },
      parents: { '@SD@': ['@SDX@', '@SP@'] },
      children: { '@SP@': ['@SD@'], '@SDX@': ['@SD@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SD@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SD@', '@SP@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-down', 'spouse', null]);
    expect(p[0].relToNext).toBe('daughter of'); // SD (F) child of SP
  });

  it('step-sibling: descent-down, spouse, descent-up', () => {
    const c = ctx({
      people: {
        '@V@': {}, '@DAD@': { sex: 'M' }, '@BIOMOM@': { sex: 'F' },
        '@STEPMOM@': { sex: 'F' }, '@SS@': { sex: 'F' }, '@SSX@': { sex: 'M' },
      },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'], '@SS@': ['@SSX@', '@STEPMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'], '@STEPMOM@': ['@SS@'], '@SSX@': ['@SS@'] },
      relatives: { '@DAD@': { spouses: ['@BIOMOM@', '@STEPMOM@'] }, '@STEPMOM@': { spouses: ['@DAD@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SS@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SS@', '@STEPMOM@', '@DAD@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-down', 'spouse', 'descent-up', null]);
  });

  it('sibling-in-law via spouse sibling (3b): descent-down, descent-up, spouse', () => {
    const c = ctx({
      people: { '@V@': {}, '@SP@': { sex: 'F' }, '@SPSIB@': { sex: 'F' }, '@SM@': { sex: 'F' } },
      parents: { '@SP@': [null, '@SM@'], '@SPSIB@': [null, '@SM@'] },
      children: { '@SM@': ['@SP@', '@SPSIB@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SPSIB@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SPSIB@', '@SM@', '@SP@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-down', 'descent-up', 'spouse', null]);
  });

  it('sibling-in-law via sibling spouse (3c): spouse, descent-down, descent-up', () => {
    const c = ctx({
      people: { '@V@': {}, '@SIB@': { sex: 'F' }, '@SIBSP@': { sex: 'M' }, '@MOM@': { sex: 'F' } },
      parents: { '@V@': [null, '@MOM@'], '@SIB@': [null, '@MOM@'] },
      children: { '@MOM@': ['@V@', '@SIB@'] },
      relatives: { '@SIB@': { spouses: ['@SIBSP@'] }, '@SIBSP@': { spouses: ['@SIB@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SIBSP@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SIBSP@', '@SIB@', '@MOM@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['spouse', 'descent-down', 'descent-up', null]);
  });

  it('child-in-law (3d): spouse then descent-down', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@D@': { sex: 'F' }, '@DH@': { sex: 'M' } },
      parents: { '@D@': [null, '@V@'] },
      children: { '@V@': ['@D@'] },
      relatives: { '@D@': { spouses: ['@DH@'] }, '@DH@': { spouses: ['@D@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@DH@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@DH@', '@D@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['spouse', 'descent-down', null]);
    expect(p[1].relToNext).toBe('daughter of'); // D (F) child of V
  });

  it('godchild: edgeKind godchild', () => {
    const c = ctx({
      people: {
        '@V@': { sex: 'M' },
        '@GC@': { sex: 'M', events: [{ tag: 'BAPM', asso: [{ xref: '@V@', rela: 'Godfather' }] }] },
      },
    });
    const p = pathOf(enumerateRelationships('@V@', '@GC@', c), 'godparent');
    expect(p.map(n => n.xref)).toEqual(['@GC@', '@V@']);
    expect(p[0]).toMatchObject({ edgeKind: 'godchild', relToNext: 'godson of' });
  });

  it('multi-relationship (uncle who is also godfather): both entries carry a path, blood first', () => {
    const c = ctx({
      people: {
        '@V@': { events: [{ tag: 'BAPM', asso: [{ xref: '@U@', rela: 'Godfather' }] }] },
        '@U@': { sex: 'M' },
        '@PV@': { sex: 'F' }, '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: { '@V@': [null, '@PV@'], '@PV@': ['@GPA@', '@GMA@'], '@U@': ['@GPA@', '@GMA@'] },
      children: { '@PV@': ['@V@'], '@GMA@': ['@PV@', '@U@'], '@GPA@': ['@PV@', '@U@'] },
    });
    const rels = enumerateRelationships('@V@', '@U@', c);
    expect(rels.map(r => r.kind)).toEqual(['blood', 'godparent']); // blood first (primary)
    for (const r of rels) {
      expect(r.path, `${r.kind} should have a path`).toBeTruthy();
      expect(r.path[0].xref).toBe('@U@');
      expect(r.path[r.path.length - 1].xref).toBe('@V@');
    }
    expect(pathOf(rels, 'godparent').map(n => n.edgeKind)).toEqual(['godparent', null]);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/js/viz_relationship.test.js -t "affinity paths"`
Expected: FAIL — entries have no `.path` (it's `undefined`).

- [ ] **Step 3: Add `path` to `findGodparentAtomic`** — replace its two `return` statements (lines 215 and 221):

```javascript
  // other is viewer's godparent
  for (const entry of idx.byChild.get(viewer) || []) {
    if (entry.xref === other) {
      return { label: _godparentLabel(entry.rela, otherSex), edges: 1,
               path: { nodes: [other, viewer], edges: ['godparent'], mrcaIndex: null } };
    }
  }
  // viewer is other's godparent → other is viewer's godchild
  for (const entry of idx.byChild.get(other) || []) {
    if (entry.xref === viewer) {
      return { label: _godchildLabel(otherSex), edges: 1,
               path: { nodes: [other, viewer], edges: ['godchild'], mrcaIndex: null } };
    }
  }
```

- [ ] **Step 4: Add `path` to every `findAtomicAffinity` tier** — rewrite the tier bodies (lines 285–382). Each `return` gains a display-order `path` (`nodes` top=other→bottom=viewer):

```javascript
function findAtomicAffinity(viewer, other, ctx) {
  const viewerSpouses = getSpousesOf(viewer, ctx);
  const viewerParents = (ctx.PARENTS[viewer] || [null, null]).filter(Boolean);
  const otherSex = (ctx.PEOPLE[other] || {}).sex || null;

  // Tier 1: spouse of viewer (1 edge)
  if (viewerSpouses.includes(other)) {
    const ex = _isDivorced(viewer, other, ctx);
    return { label: _spouseVerb(otherSex, ex), edges: 1,
             path: { nodes: [other, viewer], edges: [ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null } };
  }

  // Tier 2: step-parent (up + across, 2 edges)
  for (const par of viewerParents) {
    if (getSpousesOf(par, ctx).includes(other) && !viewerParents.includes(other)) {
      const ex = _isDivorced(other, par, ctx);
      const path = { nodes: [other, par, viewer], edges: [ex ? 'ex-spouse' : 'spouse', 'descent-up'], mrcaIndex: null };
      if (_isFormerOrPredeceasedStep(other, par, viewer, ctx)) {
        const parSex     = (ctx.PEOPLE[par]   || {}).sex || null;
        const spouseVerb = _spouseVerb(otherSex, ex);
        const parLabel   = gendered(parSex,   'Father', 'Mother', 'Parent');
        return { label: `${spouseVerb} of ${parLabel}`, edges: 2, path };
      }
      return { label: gendered(otherSex, 'Step-Father', 'Step-Mother', 'Step-Parent'), edges: 2, path };
    }
  }

  // Tier 2: step-child (across + down, 2 edges)
  const viewerChildren = ctx.CHILDREN[viewer] || [];
  for (const sp of viewerSpouses) {
    const spChildren = ctx.CHILDREN[sp] || [];
    if (spChildren.includes(other) && !viewerChildren.includes(other)) {
      const ex = _isDivorced(viewer, sp, ctx);
      const path = { nodes: [other, sp, viewer], edges: ['descent-down', ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null };
      if (_isFormerOrPredeceasedStep(viewer, sp, other, ctx)) {
        const spSex      = (ctx.PEOPLE[sp]    || {}).sex || null;
        const childLabel = gendered(otherSex, 'Son', 'Daughter', 'Child');
        const spouseVerb = _spouseVerb(spSex, ex);
        return { label: `${childLabel} of ${spouseVerb}`, edges: 2, path };
      }
      return { label: gendered(otherSex, 'Step-Son', 'Step-Daughter', 'Step-Child'), edges: 2, path };
    }
  }

  // Tier 2: step-sibling (up + across + down, 3 edges)
  for (const par of viewerParents) {
    for (const stepPar of getSpousesOf(par, ctx)) {
      if (viewerParents.includes(stepPar)) continue;
      const stepParChildren = ctx.CHILDREN[stepPar] || [];
      if (stepParChildren.includes(other)) {
        const otherParents = (ctx.PARENTS[other] || [null, null]).filter(Boolean);
        const sharesBioParent = otherParents.some(p => viewerParents.includes(p));
        if (!sharesBioParent) {
          const ex = _isDivorced(stepPar, par, ctx);
          return { label: gendered(otherSex, 'Step-Brother', 'Step-Sister', 'Step-Sibling'), edges: 3,
                   path: { nodes: [other, stepPar, par, viewer],
                           edges: ['descent-down', ex ? 'ex-spouse' : 'spouse', 'descent-up'], mrcaIndex: null } };
        }
      }
    }
  }

  // Tier 3a: parent-in-law (across + up, 2 edges)
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    if (spParents.includes(other)) {
      const ex = _isDivorced(viewer, sp, ctx);
      return { label: gendered(otherSex, 'Father-in-law', 'Mother-in-law', 'Parent-in-law'), edges: 2,
               path: { nodes: [other, sp, viewer], edges: ['descent-up', ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null } };
    }
  }

  // Tier 3b: sibling-in-law via spouse's sibling (across + up + down, 3 edges)
  for (const sp of viewerSpouses) {
    const spParents = ctx.PARENTS[sp] || [null, null];
    for (const p of spParents) {
      if (!p) continue;
      const siblings = (ctx.CHILDREN[p] || []).filter(c => c !== sp);
      if (siblings.includes(other)) {
        const ex = _isDivorced(viewer, sp, ctx);
        return { label: gendered(otherSex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law'), edges: 3,
                 path: { nodes: [other, p, sp, viewer],
                         edges: ['descent-down', 'descent-up', ex ? 'ex-spouse' : 'spouse'], mrcaIndex: null } };
      }
    }
  }

  // Tier 3c: sibling-in-law via sibling's spouse (up + down + across, 3 edges)
  for (const par of viewerParents) {
    for (const sib of (ctx.CHILDREN[par] || [])) {
      if (sib === viewer) continue;
      if (getSpousesOf(sib, ctx).includes(other)) {
        const ex = _isDivorced(sib, other, ctx);
        return { label: gendered(otherSex, 'Brother-in-law', 'Sister-in-law', 'Sibling-in-law'), edges: 3,
                 path: { nodes: [other, sib, par, viewer],
                         edges: [ex ? 'ex-spouse' : 'spouse', 'descent-down', 'descent-up'], mrcaIndex: null } };
      }
    }
  }

  // Tier 3d: child-in-law (down + across, 2 edges)
  for (const child of viewerChildren) {
    if (getSpousesOf(child, ctx).includes(other)) {
      const ex = _isDivorced(child, other, ctx);
      return { label: gendered(otherSex, 'Son-in-law', 'Daughter-in-law', 'Child-in-law'), edges: 2,
               path: { nodes: [other, child, viewer], edges: [ex ? 'ex-spouse' : 'spouse', 'descent-down'], mrcaIndex: null } };
    }
  }

  // Tier 5: godparent / godchild (already returns {label, edges, path}).
  const gp = findGodparentAtomic(viewer, other, ctx);
  if (gp) return gp;

  return null;
}
```

- [ ] **Step 5: Attach `path` in `enumerateRelationships` and delete `findAffinityLabel`** — replace `enumerateRelationships` (709–738):

```javascript
function enumerateRelationships(viewerXref, otherXref, ctx) {
  if (viewerXref === otherXref) return [{ kind: 'self', label: 'Self' }];
  const out = [];

  const paths = findBloodPaths(viewerXref, otherXref, ctx);
  if (paths.length > 0) {
    const path = pickClosestPath(paths);
    const otherSex = (ctx.PEOPLE[otherXref] || {}).sex || null;
    const isHalf = !isFullRelationship(path, ctx);
    const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
    if (label) {
      const spec = _bloodPathSpec(viewerXref, otherXref, path, ctx);
      out.push({ kind: 'blood', label,
                 path: spec ? _stepsToPath(spec.nodes, spec.edges, spec.mrcaIndex, ctx) : null });
    }
  }

  const noGpCtx = Object.create(ctx);
  noGpCtx._godparentIndex = { byChild: new Map(), byParent: new Map() };
  const aff = _bestRel(viewerXref, otherXref, noGpCtx, new Set(), _MAX_REL_DEPTH);
  if (aff && (!out.length || aff.label !== out[0].label)) {
    out.push({ kind: 'affinity', label: aff.label,
               path: aff.path ? _stepsToPath(aff.path.nodes, aff.path.edges, aff.path.mrcaIndex, ctx) : null });
  }

  const gp = findGodparentAtomic(viewerXref, otherXref, ctx);
  if (gp) out.push({ kind: 'godparent', label: gp.label,
                     path: gp.path ? _stepsToPath(gp.path.nodes, gp.path.edges, gp.path.mrcaIndex, ctx) : null });

  return out;
}
```

Then delete the entire `findAffinityLabel` function (lines 511–656) and remove `findAffinityLabel` from the `module.exports` list (line 810). (It is unused — confirmed by grep — and a stale duplicate of the tier logic; deleting it removes a drift hazard.)

> NOTE: `aff.path` is populated by Task 3 (composition). Until Task 3, composed affinity entries will have `path: null` — the Task-2 tests above all exercise **atomic** tiers, which have `path` now. That's fine.

- [ ] **Step 6: Run to verify pass**

Run: `npx vitest run tests/js/viz_relationship.test.js`
Expected: PASS — the four new affinity-path tests pass; the existing `enumerateRelationships` and `computeRelationship` affinity/godparent label tests still pass (labels unchanged; only an additive `path` field added). The `findAffinityLabel` deletion breaks nothing (no callers).

- [ ] **Step 7: Commit**

```bash
git add js/viz_relationship.js tests/js/viz_relationship.test.js
git commit --no-verify -m "feat(viz): emit path spec from atomic affinity + godparent tiers

Each findAtomicAffinity tier and findGodparentAtomic now return a
display-order path spec; enumerateRelationships renders it onto each
entry. Delete dead findAffinityLabel.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Composed paths in `_bestRel` ("X of Y")

`_bestRel`'s two split points concatenate path specs so composed labels ("Wife of 1st Cousin", "1st Cousin of Wife") carry a full chain with the blood apex tagged.

**Files:**
- Modify: `js/viz_relationship.js` (`_bestRel` 434–504)
- Test: `tests/js/viz_relationship.test.js` (append to the `affinity paths` describe block)

- [ ] **Step 1: Write the failing tests** — append inside the `enumerateRelationships — affinity paths` describe block:

```javascript
  it('Wife of 1st Cousin: spouse edge then blood leg with tagged MRCA', () => {
    // @V@'s 1st cousin @C@; @C@'s wife @CW@ is the "other".
    // Cousin tree: @GMA@(MRCA) → @PV@ → @V@  and  @GMA@ → @PC@ → @C@.
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@C@': { sex: 'F' }, '@CW@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' }, '@GMA@': { sex: 'F' },
      },
      parents: { '@V@': [null, '@PV@'], '@C@': [null, '@PC@'], '@PV@': [null, '@GMA@'], '@PC@': [null, '@GMA@'] },
      children: { '@PV@': ['@V@'], '@PC@': ['@C@'], '@GMA@': ['@PV@', '@PC@'] },
      relatives: { '@C@': { spouses: ['@CW@'] }, '@CW@': { spouses: ['@C@'] } },
    });
    const rels = enumerateRelationships('@V@', '@CW@', c);
    const aff = rels.find(r => r.kind === 'affinity');
    expect(aff.label).toBe('Wife of 1st Cousin');
    expect(aff.path.map(n => n.xref)).toEqual(['@CW@', '@C@', '@PC@', '@GMA@', '@PV@', '@V@']);
    expect(aff.path.map(n => n.edgeKind)).toEqual(['spouse', 'descent-down', 'descent-down', 'descent-up', 'descent-up', null]);
    expect(aff.path.findIndex(n => n.isMrca)).toBe(3); // @GMA@
    expect(aff.path[0].relToNext).toBe('wife of');
  });

  it('Niece of Spouse: spouse split appends spouse hop, keeps sub-path order', () => {
    // viewer @V@ married @W@; @W@'s niece @N@ (W's sibling @SIB@'s daughter).
    // NOTE: the spouse split uses the generic word "Spouse" in the LABEL, while
    // the chain TERM stays gendered ("wife of"). This is the live _bestRel
    // behavior — there is no gendered-spouse composition in the engine.
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@W@': { sex: 'F' }, '@SIB@': { sex: 'F' },
        '@N@': { sex: 'F' }, '@WP@': { sex: 'F' },
      },
      parents: { '@W@': [null, '@WP@'], '@SIB@': [null, '@WP@'], '@N@': [null, '@SIB@'] },
      children: { '@WP@': ['@W@', '@SIB@'], '@SIB@': ['@N@'] },
      relatives: { '@V@': { spouses: ['@W@'] }, '@W@': { spouses: ['@V@'] } },
    });
    const rels = enumerateRelationships('@V@', '@N@', c);
    const aff = rels.find(r => r.kind === 'affinity');
    expect(aff.label).toBe('Niece of Spouse');
    // other → … → spouse → you ; the spouse hop W→V is the last edge.
    expect(aff.path[aff.path.length - 1].xref).toBe('@V@');
    expect(aff.path[aff.path.length - 2].xref).toBe('@W@');
    expect(aff.path[aff.path.length - 2].edgeKind).toBe('spouse');
    expect(aff.path[aff.path.length - 2].relToNext).toBe('wife of');
  });
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run tests/js/viz_relationship.test.js -t "Wife of 1st Cousin"`
Expected: FAIL — `aff.path` is `null` (composition doesn't emit a spec yet).

- [ ] **Step 3: Compose specs in `_bestRel`** — make three edits inside `_bestRel`.

(a) Direct blood candidate (lines ~443–448): attach the blood spec.

```javascript
    if (path) {
      const otherSex = (ctx.PEOPLE[other] || {}).sex || null;
      const isHalf = !isFullRelationship(path, ctx);
      const label = formatBloodLabel(path.a, path.b, otherSex, isHalf);
      const spec = _bloodPathSpec(viewer, other, path, ctx);
      if (label && spec) best = _betterCand(best, { label, edges: path.a + path.b, ofs: 0, path: spec });
    }
```

(b) Atomic affinity candidate (line ~452–453): carry `atomic.path`.

```javascript
  const atomic = findAtomicAffinity(viewer, other, ctx);
  if (atomic) best = _betterCand(best, { label: atomic.label, edges: atomic.edges, ofs: 0, path: atomic.path });
```

(c) Blood-relative split (lines ~467–485): build `leftSpec` and concatenate `subAtomic.path` (other→Z) with the blood leg (Z→viewer).

```javascript
  const bloodRels = findAllBloodRelatives(viewer, ctx);
  for (const [zXref, path] of bloodRels) {
    if (zXref === other || newSeen.has(zXref)) continue;
    const leftEdges = path.a + path.b;
    if (best && leftEdges >= best.edges) continue;
    const subAtomic = findAtomicAffinity(zXref, other, ctx);
    if (!subAtomic) continue;
    const zSex = (ctx.PEOPLE[zXref] || {}).sex || null;
    const zIsHalf = !isFullRelationship(path, ctx);
    const leftLabel = formatBloodLabel(path.a, path.b, zSex, zIsHalf);
    if (!leftLabel) continue;
    const leftSpec = _bloodPathSpec(viewer, zXref, path, ctx); // [Z, …, viewer]
    let composedPath = null;
    if (leftSpec && subAtomic.path) {
      composedPath = {
        nodes: subAtomic.path.nodes.concat(leftSpec.nodes.slice(1)),   // other … Z … viewer (Z shared, dropped once)
        edges: subAtomic.path.edges.concat(leftSpec.edges),
        mrcaIndex: (subAtomic.path.nodes.length - 1) + leftSpec.mrcaIndex,
      };
    }
    const cand = {
      label: `${subAtomic.label} of ${leftLabel}`,
      edges: leftEdges + subAtomic.edges,
      ofs: 1,
      leftEdges,
      path: composedPath,
    };
    best = _betterCand(best, cand);
  }
```

(d) Spouse split (lines ~488–501): prepend nothing, append the spouse hop to viewer.

```javascript
  for (const sp of getSpousesOf(viewer, ctx)) {
    if (sp === other || newSeen.has(sp)) continue;
    if (best && 1 >= best.edges) continue;
    const sub = _bestRel(sp, other, ctx, newSeen, depthLeft - 1);
    if (!sub) continue;
    const ex = _isDivorced(viewer, sp, ctx);
    const spouseWord = ex ? 'Ex-Spouse' : 'Spouse';
    const cand = {
      label: `${sub.label} of ${spouseWord}`,
      edges: 1 + sub.edges,
      ofs: sub.ofs + 1,
      leftEdges: 1,
      path: sub.path ? {
        nodes: sub.path.nodes.concat([viewer]),               // other … sp → you
        edges: sub.path.edges.concat([ex ? 'ex-spouse' : 'spouse']),
        mrcaIndex: sub.path.mrcaIndex,
      } : null,
    };
    best = _betterCand(best, cand);
  }
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run tests/js/viz_relationship.test.js -t "affinity paths"`
Expected: PASS — both composition tests pass; the atomic tests from Task 2 still pass.

- [ ] **Step 5: Add the label-parity guard test** — append inside the `affinity paths` describe block. This locks in the Approach-A invariant that the path and the displayed label come from the same match:

```javascript
  it('label-parity: each entry path is non-null and consistent with its label for representative fixtures', () => {
    const fixtures = [
      // [desc, ctxArgs, viewer, other]
      ['spouse', {
        people: { '@V@': { sex: 'F' }, '@S@': { sex: 'M' } },
        relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      }, '@V@', '@S@'],
      ['mother-in-law', {
        people: { '@V@': {}, '@S@': { sex: 'F' }, '@SM@': { sex: 'F' } },
        parents: { '@S@': [null, '@SM@'] }, children: { '@SM@': ['@S@'] },
        relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      }, '@V@', '@SM@'],
    ];
    for (const [, args, v, o] of fixtures) {
      const c = ctx(args);
      const rels = enumerateRelationships(v, o, c);
      for (const r of rels) {
        expect(r.path, `${r.kind} entry should have a path`).toBeTruthy();
        // The "other" person sits at the top and "you" at the bottom of every chain.
        expect(r.path[0].isOther).toBe(true);
        expect(r.path[r.path.length - 1].isViewer).toBe(true);
        expect(r.path[r.path.length - 1].xref).toBe(v);
        expect(r.path[0].xref).toBe(o);
      }
    }
  });
```

- [ ] **Step 6: Run the full suite**

Run: `npm test`
Expected: PASS — entire JS suite green (no DOM tests touched).

- [ ] **Step 7: Commit**

```bash
git add js/viz_relationship.js tests/js/viz_relationship.test.js
git commit --no-verify -m "feat(viz): compose path specs across 'of' in _bestRel

Blood-relative and spouse splits concatenate path specs so composed
affinity labels carry a full chain with the blood apex tagged isMrca.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Renderer — per-edge glyphs + tab switcher

`js/viz_modal_relpath.js` renders the glyph from `edgeKind` (↑/↓/⚭/✝) and shows a tab bar when an entry list has more than one renderable relationship. Browser-only DOM glue — no unit test (codebase convention); verified at the manual gate.

**Files:**
- Modify: `js/viz_modal_relpath.js`

- [ ] **Step 1: Replace `_renderRelationshipPath`'s arrow logic** — swap the `reachedMrca` boolean for a per-node glyph map. Replace lines 14–75 (the function body) with:

```javascript
const _RELPATH_GLYPH = {
  'descent-up': '↑',   // ↑
  'descent-down': '↓', // ↓
  'spouse': '⚭',       // ⚭
  'ex-spouse': '⚭',    // ⚭
  'godparent': '✝',    // ✝
  'godchild': '✝',     // ✝
};

function _renderRelationshipPath(path) {
    const body = document.getElementById('relpath-modal-body');
    if (!body) return;
    body.innerHTML = '';
    path.forEach((node) => {
        const row = document.createElement('div');
        row.className = 'relpath-row';

        const link = document.createElement('span');
        link.className = node.isMrca ? 'relpath-person relpath-person-mrca' : 'relpath-person';
        link.textContent = (typeof _personName === 'function') ? _personName(node.xref) : node.xref;
        link.addEventListener('click', () => {
            closeRelationshipPathModal();
            if (typeof navigate === 'function') {
                navigate(node.xref);
            } else if (typeof setState === 'function') {
                setState({ focusXref: node.xref, panelOpen: true, panelXref: node.xref });
            }
        });
        row.appendChild(link);

        const years = _relpathLifespan(node.xref);
        if (years) {
            const y = document.createElement('span');
            y.className = 'relpath-years';
            y.textContent = years;
            row.appendChild(y);
        }

        if (node.isViewer) {
            const you = document.createElement('span');
            you.className = 'relpath-you';
            you.textContent = 'You';
            row.appendChild(you);
        }

        if (node.isMrca) {
            const tag = document.createElement('span');
            tag.className = 'relpath-mrca';
            tag.textContent = 'common ancestor';
            row.appendChild(tag);
        }
        body.appendChild(row);

        if (node.relToNext) {
            const step = document.createElement('div');
            step.className = 'relpath-step';
            const arrow = document.createElement('span');
            arrow.className = 'relpath-arrow';
            arrow.textContent = _RELPATH_GLYPH[node.edgeKind] || '↓';
            const rel = document.createElement('span');
            rel.textContent = node.relToNext;
            step.appendChild(arrow);
            step.appendChild(rel);
            body.appendChild(step);
        }
    });
}
```

- [ ] **Step 2: Replace `showRelationshipPathModal` + add tab helpers** — replace `showRelationshipPathModal` (77–84) with the entry-list version and add tab rendering + module-level state:

```javascript
let _relpathEntries = [];

function _renderRelationshipTabs(entries, activeIdx) {
    const existing = document.getElementById('relpath-tabs');
    if (existing) existing.remove();
    if (!entries || entries.length < 2) return;
    const body = document.getElementById('relpath-modal-body');
    if (!body) return;
    const bar = document.createElement('div');
    bar.id = 'relpath-tabs';
    bar.className = 'relpath-tabs';
    entries.forEach((e, i) => {
        const tab = document.createElement('button');
        tab.className = 'relpath-tab' + (i === activeIdx ? ' active' : '');
        tab.textContent = e.label;
        tab.addEventListener('click', () => _selectRelationshipTab(i));
        bar.appendChild(tab);
    });
    body.parentNode.insertBefore(bar, body);
}

function _selectRelationshipTab(i) {
    _renderRelationshipTabs(_relpathEntries, i);
    _renderRelationshipPath(_relpathEntries[i].path);
}

// entries: [{ kind, label, path }]; title: the displayed (possibly combined) label.
function showRelationshipPathModal(entries, title) {
    const renderable = (entries || []).filter(e => e.path && e.path.length);
    if (!renderable.length) return;
    const overlay = document.getElementById('relpath-modal-overlay');
    const titleEl = document.getElementById('relpath-modal-title');
    if (titleEl) titleEl.textContent = title ? `Relationship — ${title}` : 'Relationship';
    _relpathEntries = renderable;
    _renderRelationshipTabs(renderable, 0);
    _renderRelationshipPath(renderable[0].path);
    if (overlay) overlay.classList.add('open');
}
```

- [ ] **Step 3: Clean up the tab bar on close** — replace `closeRelationshipPathModal` (86–89):

```javascript
function closeRelationshipPathModal() {
    const overlay = document.getElementById('relpath-modal-overlay');
    if (overlay) overlay.classList.remove('open');
    const bar = document.getElementById('relpath-tabs');
    if (bar) bar.remove();
}
```

- [ ] **Step 4: Sanity-check the file loads** — confirm no syntax error:

Run: `node --check js/viz_modal_relpath.js`
Expected: no output (exit 0).

- [ ] **Step 5: Commit**

```bash
git add js/viz_modal_relpath.js
git commit --no-verify -m "feat(viz): relpath modal renders per-edge glyph + relationship tabs

edgeKind drives ↑/↓/⚭/✝; >1 relationship shows a tab switcher
(primary default); tab bar cleared on close.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Panel — make every non-Self label clickable

Replace the blood-only gate and the inline `<ul>` expand in `js/viz_panel.js` so any non-Self label opens the modal via `enumerateRelationships`, reusing the warmed `relCtx`. Browser-only — verified at the manual gate.

**Files:**
- Modify: `js/viz_panel.js` (lines 684–737)

- [ ] **Step 1: Replace the relationship-label block** — swap the body of `if (rel) { … }` (lines 685–737, the whole blood/affinity branch) for:

```javascript
        if (rel) {
            const labelSpan = document.createElement('span');
            labelSpan.textContent = rel.label;
            relEl.appendChild(labelSpan);

            const isSelf = rel.debug && rel.debug.a === 0 && rel.debug.b === 0;
            if (!isSelf && typeof enumerateRelationships === 'function'
                && typeof showRelationshipPathModal === 'function') {
                labelSpan.style.cursor = 'pointer';
                labelSpan.style.textDecoration = 'underline dotted';
                labelSpan.title = 'Click to see how you are related';
                labelSpan.addEventListener('click', () => {
                    const entries = enumerateRelationships(VIEWER_XREF, xref, relCtx);
                    showRelationshipPathModal(entries, rel.label);
                });
            }
        }
```

This removes the dependence on `buildRelationshipPath`/`findGodparentAtomic` in the panel and the inline `enumerateRelationships`-`<ul>` expand. `relCtx` is the same object `computeRelationship` ran on at line 683, so its `_godparentIndex`/`_bloodCache` are reused by the click's `enumerateRelationships`.

- [ ] **Step 2: Sanity-check the file loads**

Run: `node --check js/viz_panel.js`
Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add js/viz_panel.js
git commit --no-verify -m "feat(viz): every non-Self relationship label opens the path modal

Replace the blood-only gate and inline godparent expand with a single
clickable handler that opens the modal via enumerateRelationships
(reusing the warmed relCtx).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: CSS — relationship tabs

Style the tab bar to match the existing modal theme.

**Files:**
- Modify: `viz_ancestors.css` (append after the `.relpath-arrow` rule, ~line 3067)

- [ ] **Step 1: Add the tab styles** — append:

```css
.relpath-tabs {
    display: flex;
    gap: 6px;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 14px;
}

.relpath-tab {
    font-family: inherit;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 4px 12px;
    border-radius: 6px;
    cursor: pointer;
    color: var(--text-secondary);
    background: transparent;
    border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.14));
    transition: color 0.12s, border-color 0.12s, background 0.12s;
}

.relpath-tab:hover {
    color: var(--text-primary);
    border-color: var(--text-secondary);
}

.relpath-tab.active {
    color: var(--accent-light);
    border-color: var(--accent-light);
    background: var(--accent-bg);
}
```

> If `--border-subtle` is not defined in `:root`, the `rgba(...)` fallback applies — no change needed. `--text-secondary`, `--text-primary`, `--accent-light`, `--accent-bg` are all already used by existing `.relpath-*` rules.

- [ ] **Step 2: Commit**

```bash
git add viz_ancestors.css
git commit --no-verify -m "style(viz): relationship-path modal tab bar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Manual verification gate + docs

No automated browser tests (codebase convention); a human runs the dev server and walks the checklist, then we write the completion doc.

**Files:**
- Create: `.claude/completions/2026-05-28-relationship-path-nonblood.md` (template: `.claude/templates/completion-template.md`)
- Update: the v1 spec's "Future work" note in `docs/superpowers/specs/2026-05-28-relationship-path-popup-design.md` to mark item 1 done (point to the new spec/plan).

- [ ] **Step 1: Start the dev server (human)**

Run:
```bash
python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```
(Canonical GED path — never `merged.ged` or a Desktop copy. See `COMMON_MISTAKES.md #1`.)

- [ ] **Step 2: Walk the verification checklist (human)** — confirm each:
  - A **spouse** label opens a 2-row chain (other ⚭ → You).
  - A **parent-in-law** / **sibling-in-law** / **child-in-law** label opens a correct chain with ⚭ at the marriage hop and ↑/↓ on descent hops; no "common ancestor" tag.
  - A **step-parent/child/sibling** label opens a correct chain.
  - A **godparent** and a **godchild** label each open a 2-row chain with the ✝ glyph and the right gendered term.
  - A **composed** label ("… of <cousin/aunt>") shows the blood apex tagged "common ancestor" with the cross edge in the right spot.
  - A person with **two relationships** (e.g. a blood relative who is also a godparent) shows **tabs**; clicking a tab swaps the chain; default tab = the primary/closest.
  - Clicking an intermediate **name** re-centers the chart and closes the modal.
  - **Escape** and **click-outside** close the modal; reopening shows no stale tab bar.
  - **Self** (viewing yourself) is **not** clickable.

- [ ] **Step 3: Write the completion doc** — at `.claude/completions/2026-05-28-relationship-path-nonblood.md`, summarizing files changed, the step-spec model, the Approach-A invariant (label-parity test), and any gaps found at the gate.

- [ ] **Step 4: Update the v1 spec's Future-work note** — in `docs/superpowers/specs/2026-05-28-relationship-path-popup-design.md`, mark "Future work item 1 — Option 2: full coverage" as implemented and link the new spec + plan.

- [ ] **Step 5: Commit**

```bash
git add -f .claude/completions/2026-05-28-relationship-path-nonblood.md docs/superpowers/specs/2026-05-28-relationship-path-popup-design.md
git commit --no-verify -m "docs: completion + mark v1 future-work item 1 done (non-blood paths)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes on edge cases & invariants

- **`mrcaIndex` semantics:** set **only** by pure-blood paths and the blood-relative composition (a genuine viewer-side blood apex). Atomic in-law tiers (3b/3c) contain a blood apex *between two non-viewer people* and deliberately leave `mrcaIndex: null` — "common ancestor" should appear only when the viewer's own blood connection is what the chain hinges on.
- **Term gendering** is always by the **upper** node's sex (the node carrying `relToNext`), consistent with v1 and with `_stepsToPath`.
- **Null paths:** a composed candidate whose sub-path is null (broken back-pointer) yields `path: null`; `enumerateRelationships` passes it through and `showRelationshipPathModal` filters such entries out of the tab list. The label still computes — only its chain is unavailable.
- **No new exports required:** tests drive everything through the already-exported `buildRelationshipPath` and `enumerateRelationships`.
