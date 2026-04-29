# Relative Life Events on Timeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render births/deaths of close relatives (parents, spouse(s), children) on the focused person's detail-panel timeline, as muted compact one-liners interleaved chronologically with the person's own events, bounded to the person's lifetime.

**Architecture:** New self-contained JS module `viz_relative_events.js` exposes a single `buildRelativeEvents(xref)` function that queries `ALL_PEOPLE`, `PARENTS`, `CHILDREN`, and `FAMILIES` globals to produce a sorted list of relative-event rows. The render block in `viz_panel.js` merges these rows with the focused person's own timeline events. Display-only — no editing, no sources, no places.

**Tech Stack:** Vanilla ES (no bundler), vitest for JS tests, Python 3 for the data-payload change in `viz_ancestors.py`.

**Spec:** `docs/superpowers/specs/2026-04-28-relative-events-on-timeline-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `viz_ancestors.py` | Modify (`~line 1048`) | Add `sex` field to each entry in the `all_people` payload |
| `js/viz_relative_events.js` | **Create** | Pure data layer: produce sorted, filtered relative-event rows for a focused person |
| `tests/js/viz_relative_events.test.js` | **Create** | Vitest suite covering filtering, role resolution, lifetime bounds, sort order |
| `viz_ancestors.css` | Modify (append) | Add `.evt-rel-row`, `.evt-rel-row .yr`, `.evt-rel-row .label` |
| `js/viz_panel.js` | Modify (`~line 590-781`) | Merge relative events into the timeline render loop |
| `viz_ancestors.html` | Modify (`~line 471`) | Add `<script src="/js/viz_relative_events.js">` |

Module load order matters: `viz_relative_events.js` must load before `viz_panel.js`.

---

## Task 1: Add `sex` to `ALL_PEOPLE` payload

**Files:**
- Modify: `viz_ancestors.py:1048-1054`

- [ ] **Step 1: Edit the all_people list comprehension**

Open `viz_ancestors.py` and change the block at line 1048 from:

```python
all_people = sorted(
    [{"id": xref, "name": info["name"] or "",
      "birth_year": info.get("birth_year") or "",
      "death_year": info.get("death_year") or ""}
     for xref, info in indis.items()],
    key=lambda p: p["name"].lower()
)
```

to:

```python
all_people = sorted(
    [{"id": xref, "name": info["name"] or "",
      "birth_year": info.get("birth_year") or "",
      "death_year": info.get("death_year") or "",
      "sex": info.get("sex") or ""}
     for xref, info in indis.items()],
    key=lambda p: p["name"].lower()
)
```

- [ ] **Step 2: Verify the change end-to-end via dev server**

Run:

```bash
python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```

In the browser DevTools console (with the page loaded):

```js
ALL_PEOPLE.find(p => p.sex === 'M')
ALL_PEOPLE.find(p => p.sex === 'F')
```

Expected: both return a person object that includes `sex: 'M'` (or `'F'`).

Stop the server when verified.

- [ ] **Step 3: Commit**

```bash
git add viz_ancestors.py
git commit -m "feat(viz): include sex field in ALL_PEOPLE payload

Required by upcoming relative-events-on-timeline feature for picking
husband/wife, son/daughter, father/mother phrasing.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Create `viz_relative_events.js` — helpers (TDD)

**Files:**
- Create: `js/viz_relative_events.js`
- Create: `tests/js/viz_relative_events.test.js`

This task builds the small private helpers and the `_role` resolver. The main function `buildRelativeEvents` comes in Task 3.

- [ ] **Step 1: Write failing tests for `_role` and `_lifetimeBounds`**

Create `tests/js/viz_relative_events.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

function loadModule({ allPeople = [], parents = {}, children = {}, families = {} } = {}) {
    vi.resetModules();
    const modPath = require.resolve('../../js/viz_relative_events.js');
    delete require.cache[modPath];
    global.ALL_PEOPLE = allPeople;
    global.ALL_PEOPLE_BY_ID = Object.fromEntries(allPeople.map(p => [p.id, p]));
    global.PARENTS = parents;
    global.CHILDREN = children;
    global.FAMILIES = families;
    return require('../../js/viz_relative_events.js');
}

beforeEach(() => {
    delete global.ALL_PEOPLE;
    delete global.ALL_PEOPLE_BY_ID;
    delete global.PARENTS;
    delete global.CHILDREN;
    delete global.FAMILIES;
});

describe('_role — child', () => {
    it('returns "son" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'child')).toBe('son');
    });
    it('returns "daughter" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'child')).toBe('daughter');
    });
    it('returns "child" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'child')).toBe('child');
    });
});

describe('_role — spouse', () => {
    it('returns "husband" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'spouse')).toBe('husband');
    });
    it('returns "wife" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'spouse')).toBe('wife');
    });
    it('returns "spouse" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'spouse')).toBe('spouse');
    });
});

describe('_role — parent', () => {
    it('returns "father" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'parent')).toBe('father');
    });
    it('returns "mother" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'parent')).toBe('mother');
    });
    it('returns "parent" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'parent')).toBe('parent');
    });
});

describe('_lifetimeBounds', () => {
    it('returns null when birth_year is missing', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '', death_year: '', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toBe(null);
    });
    it('returns {lo: birth, hi: death} when both known', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1880, death_year: 1945, sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1945 });
    });
    it('caps at birth_year+100 when death year is missing', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1880, death_year: '', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1980 });
    });
    it('handles string years from JSON payload', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '1880', death_year: '1945', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1945 });
    });
    it('returns null when xref not found in ALL_PEOPLE_BY_ID', () => {
        const mod = loadModule();
        expect(mod._lifetimeBounds('@IX@')).toBe(null);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
npx vitest run tests/js/viz_relative_events.test.js
```

Expected: all tests FAIL (module not found / functions undefined).

- [ ] **Step 3: Create `viz_relative_events.js` with helpers**

Create `js/viz_relative_events.js`:

```js
// Builds the list of relative life events (births of children, deaths of
// children, parents, and spouse(s)) to display on a focused person's
// timeline. Pure data layer — no DOM, no rendering.

function _role(person, relation) {
    const s = (person && person.sex) || '';
    if (relation === 'child')  return s === 'M' ? 'son'     : s === 'F' ? 'daughter' : 'child';
    if (relation === 'spouse') return s === 'M' ? 'husband' : s === 'F' ? 'wife'     : 'spouse';
    if (relation === 'parent') return s === 'M' ? 'father'  : s === 'F' ? 'mother'   : 'parent';
    return relation;
}

function _yearNum(v) {
    if (v === null || v === undefined || v === '') return null;
    const n = typeof v === 'number' ? v : parseInt(v, 10);
    return Number.isFinite(n) ? n : null;
}

function _lifetimeBounds(xref) {
    if (typeof ALL_PEOPLE_BY_ID === 'undefined' || !ALL_PEOPLE_BY_ID) return null;
    const p = ALL_PEOPLE_BY_ID[xref];
    if (!p) return null;
    const lo = _yearNum(p.birth_year);
    if (lo === null) return null;
    const dy = _yearNum(p.death_year);
    const hi = dy !== null ? dy : lo + 100;
    return { lo, hi };
}

if (typeof module !== 'undefined') module.exports = {
    _role,
    _yearNum,
    _lifetimeBounds,
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
npx vitest run tests/js/viz_relative_events.test.js
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add js/viz_relative_events.js tests/js/viz_relative_events.test.js
git commit -m "feat(viz): add relative-events helpers (role + lifetime bounds)

First slice of viz_relative_events.js. Pure helpers:
- _role: maps sex+relation to display word (son/daughter/child, etc.)
- _lifetimeBounds: returns {lo, hi} from ALL_PEOPLE_BY_ID, capping at
  birth_year+100 when death year is missing.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Implement `buildRelativeEvents` (TDD)

**Files:**
- Modify: `js/viz_relative_events.js`
- Modify: `tests/js/viz_relative_events.test.js`

- [ ] **Step 1: Append failing tests for `buildRelativeEvents`**

Append to `tests/js/viz_relative_events.test.js`:

```js
// Helper to build a fixture: focus = @I1@ (b.1880, d.1945, M)
// Children: @I2@ (b.1904, F), @I3@ (b.1907, M, d.1928)
// Spouse: @I4@ (F, d.1934) — connected via FAM
// Parents: @I5@ (M, d.1895) father, @I6@ (F, d.1920) mother
function focusedFixture() {
    const allPeople = [
        { id: '@I1@', name: 'Maria',    birth_year: 1880, death_year: 1945, sex: 'F' },
        { id: '@I2@', name: 'Eleni',    birth_year: 1904, death_year: '',   sex: 'F' },
        { id: '@I3@', name: 'Georgios', birth_year: 1907, death_year: 1928, sex: 'M' },
        { id: '@I4@', name: 'Stavros',  birth_year: 1878, death_year: 1934, sex: 'M' },
        { id: '@I5@', name: 'Dimitrios',birth_year: 1850, death_year: 1895, sex: 'M' },
        { id: '@I6@', name: 'Sofia',    birth_year: 1855, death_year: 1920, sex: 'F' },
    ];
    return {
        allPeople,
        parents:  { '@I1@': ['@I5@', '@I6@'], '@I2@': ['@I4@', '@I1@'], '@I3@': ['@I4@', '@I1@'] },
        children: { '@I1@': ['@I2@', '@I3@'], '@I4@': ['@I2@', '@I3@'], '@I5@': ['@I1@'], '@I6@': ['@I1@'] },
        families: { '@F1@': { husb: '@I4@', wife: '@I1@', chil: ['@I2@', '@I3@'], marr_year: 1902 } },
    };
}

describe('buildRelativeEvents — basic', () => {
    it('returns [] when focused person has no birth year', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '', death_year: '', sex: '' }],
        });
        expect(mod.buildRelativeEvents('@I1@')).toEqual([]);
    });

    it('returns [] when focused person has no relatives', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1900, death_year: 1980, sex: 'M' }],
        });
        expect(mod.buildRelativeEvents('@I1@')).toEqual([]);
    });

    it('includes child birth, child death, spouse death, and parent deaths within lifetime', () => {
        const mod = loadModule(focusedFixture());
        const events = mod.buildRelativeEvents('@I1@');
        const summary = events.map(e => `${e.year} ${e.kind} ${e.role} ${e.name}`);
        expect(summary).toEqual([
            '1895 death father Dimitrios',
            '1904 birth daughter Eleni',
            '1907 birth son Georgios',
            '1920 death mother Sofia',
            '1928 death son Georgios',
            '1934 death husband Stavros',
        ]);
    });
});

describe('buildRelativeEvents — filtering', () => {
    it('excludes child birth when child has no birth year', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I2@' ? { ...p, birth_year: '' } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1904);
    });

    it('excludes child birth when child is born after focused person\'s death', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I2@' ? { ...p, birth_year: 1950 } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1950);
    });

    it('excludes parent death that occurred before focused person\'s birth', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I5@' ? { ...p, death_year: 1860 } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1860);
    });

    it('excludes spouse death after focused person\'s death', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I4@' ? { ...p, death_year: 1960 } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1960);
    });

    it('uses birth_year+100 cap when focused person has no death year', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I1@' ? { ...p, death_year: '' } : p);
        // Add a child born in 1985 (within 1880+100=1980? no — past cap → excluded)
        fx.allPeople.push({ id: '@I7@', name: 'Late', birth_year: 1985, death_year: '', sex: 'F' });
        fx.children['@I1@'].push('@I7@');
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1985);
        // But a child born in 1970 IS within 1880+100=1980 → included
        fx.allPeople.push({ id: '@I8@', name: 'EarlyEnough', birth_year: 1970, death_year: '', sex: 'M' });
        fx.children['@I1@'].push('@I8@');
        const mod2 = loadModule(fx);
        const years2 = mod2.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years2).toContain(1970);
    });
});

describe('buildRelativeEvents — section + sort', () => {
    it('assigns Early Life when year <= birth_year + 18, else Life', () => {
        const fx = focusedFixture();
        const mod = loadModule(fx);
        const events = mod.buildRelativeEvents('@I1@');
        const father = events.find(e => e.year === 1895); // age 15
        const mother = events.find(e => e.year === 1920); // age 40
        expect(father.section).toBe('Early Life');
        expect(mother.section).toBe('Life');
    });

    it('intra-year sort: parent-death < child-birth < child-death < spouse-death', () => {
        const fx = {
            allPeople: [
                { id: '@F@', name: 'F',  birth_year: 1900, death_year: 1980, sex: 'F' },
                { id: '@P@', name: 'Pa', birth_year: 1870, death_year: 1950, sex: 'M' },
                { id: '@C1@', name: 'C1', birth_year: 1950, death_year: '',   sex: 'F' },
                { id: '@C2@', name: 'C2', birth_year: 1925, death_year: 1950, sex: 'M' },
                { id: '@S@', name: 'S',  birth_year: 1898, death_year: 1950, sex: 'M' },
            ],
            parents: { '@F@': ['@P@', null] },
            children: { '@F@': ['@C1@', '@C2@'] },
            families: { '@F1@': { husb: '@S@', wife: '@F@', chil: [], marr_year: 1922 } },
        };
        const mod = loadModule(fx);
        const events = mod.buildRelativeEvents('@F@');
        const yr1950 = events.filter(e => e.year === 1950);
        expect(yr1950.map(e => `${e.kind}-${e.role}`)).toEqual([
            'death-father',
            'birth-daughter',
            'death-son',
            'death-husband',
        ]);
    });
});

describe('buildRelativeEvents — name fallback', () => {
    it('emits empty name string when relative has no name', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I2@' ? { ...p, name: '' } : p);
        const mod = loadModule(fx);
        const evt = mod.buildRelativeEvents('@I1@').find(e => e.year === 1904);
        expect(evt.name).toBe('');
        expect(evt.role).toBe('daughter');
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
npx vitest run tests/js/viz_relative_events.test.js
```

Expected: the new tests FAIL (`buildRelativeEvents is not a function`). Existing helper tests still PASS.

- [ ] **Step 3: Implement `buildRelativeEvents`**

Append to `js/viz_relative_events.js` (before the `module.exports` block):

```js
// Sort key for intra-year ordering: parent-death=0, child-birth=1, child-death=2, spouse-death=3.
const _SORT_KEY = { 'death-parent': 0, 'birth-child': 1, 'death-child': 2, 'death-spouse': 3 };

function _spousesOf(xref) {
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return [];
    const out = [];
    for (const fam of Object.values(FAMILIES)) {
        if (fam.husb === xref && fam.wife) out.push(fam.wife);
        else if (fam.wife === xref && fam.husb) out.push(fam.husb);
    }
    return out;
}

function _parentsOf(xref) {
    if (typeof PARENTS === 'undefined' || !PARENTS) return [];
    const pair = PARENTS[xref] || [];
    return pair.filter(Boolean);
}

function _childrenOf(xref) {
    if (typeof CHILDREN === 'undefined' || !CHILDREN) return [];
    return CHILDREN[xref] || [];
}

function _lookup(xref) {
    if (typeof ALL_PEOPLE_BY_ID === 'undefined' || !ALL_PEOPLE_BY_ID) return null;
    return ALL_PEOPLE_BY_ID[xref] || null;
}

function _push(out, year, kind, relation, person, bounds, focusBirth) {
    if (year === null) return;
    if (year < bounds.lo || year > bounds.hi) return;
    const role = _role(person, relation);
    const sortKey = _SORT_KEY[`${kind}-${relation}`] ?? 99;
    const section = (year <= focusBirth + 18) ? 'Early Life' : 'Life';
    out.push({
        year,
        section,
        kind,
        role,
        name: person.name || '',
        sortKey,
    });
}

function buildRelativeEvents(xref) {
    const bounds = _lifetimeBounds(xref);
    if (!bounds) return [];
    const focusBirth = bounds.lo;
    const out = [];

    for (const cx of _childrenOf(xref)) {
        const c = _lookup(cx);
        if (!c) continue;
        _push(out, _yearNum(c.birth_year), 'birth', 'child', c, bounds, focusBirth);
        _push(out, _yearNum(c.death_year), 'death', 'child', c, bounds, focusBirth);
    }

    for (const px of _parentsOf(xref)) {
        const p = _lookup(px);
        if (!p) continue;
        _push(out, _yearNum(p.death_year), 'death', 'parent', p, bounds, focusBirth);
    }

    for (const sx of _spousesOf(xref)) {
        const s = _lookup(sx);
        if (!s) continue;
        _push(out, _yearNum(s.death_year), 'death', 'spouse', s, bounds, focusBirth);
    }

    out.sort((a, b) =>
        (a.year - b.year) ||
        (a.sortKey - b.sortKey) ||
        a.name.localeCompare(b.name)
    );
    return out;
}
```

Then update the `module.exports` block at the end:

```js
if (typeof module !== 'undefined') module.exports = {
    _role,
    _yearNum,
    _lifetimeBounds,
    buildRelativeEvents,
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
npx vitest run tests/js/viz_relative_events.test.js
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add js/viz_relative_events.js tests/js/viz_relative_events.test.js
git commit -m "feat(viz): implement buildRelativeEvents

Returns sorted list of relative life events (child births/deaths,
parent deaths, spouse deaths) for a focused person, filtered to events
within their lifetime. Year-then-kind ordering with stable
parent-death < child-birth < child-death < spouse-death tiebreak.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Add CSS for `.evt-rel-row`

**Files:**
- Modify: `viz_ancestors.css` (append at end of \"Event card layout\" section, around line 1939)

- [ ] **Step 1: Append the CSS block**

Open `viz_ancestors.css` and find the block that ends around line 1939 (`.evt-note-inline { ... line-height: 1.5; }` followed by the `/* ── Also lived in ── */` section). Insert this block immediately before the `/* ── Also lived in ── */` comment:

```css
/* Relative life events — births of children, deaths of close relatives.
   Compact one-liner, no card chrome, muted italic. */
.evt-rel-row {
    display: flex;
    gap: 10px;
    align-items: baseline;
    padding: 4px 12px;
    margin: 2px 0;
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
}
.evt-rel-row .yr {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: var(--text-secondary);
    width: 36px;
    flex-shrink: 0;
}
.evt-rel-row .label {
    font-style: italic;
}
```

- [ ] **Step 2: Commit**

```bash
git add viz_ancestors.css
git commit -m "feat(viz): add .evt-rel-row styles for relative-event timeline rows

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Wire relative events into the timeline render block

**Files:**
- Modify: `viz_ancestors.html` (around line 447 — build `ALL_PEOPLE_BY_ID`)
- Modify: `js/viz_panel.js` (timeline block around line 590-781)

- [ ] **Step 1: Build `ALL_PEOPLE_BY_ID` in HTML bootstrap**

Open `viz_ancestors.html` and find the block at line 447-451:

```js
let CHILDREN = {};
for (const [cx, [fa, mo]] of Object.entries(PARENTS)) {
    for (const p of [fa, mo]) { if (p) {
            (CHILDREN[p] = CHILDREN[p] || []).push(cx); } }
}
```

Insert immediately after this block (before `function _applyFamilyMaps`):

```js
const ALL_PEOPLE_BY_ID = Object.fromEntries(ALL_PEOPLE.map(p => [p.id, p]));
```

- [ ] **Step 2: Add helper in `viz_panel.js` to render a relative-event row**

Open `js/viz_panel.js`. Find the timeline block beginning at line 590 (`// ── Timeline events ──`). Just above that block, add a private renderer. Locate a clear insertion point — directly above the `// ── Timeline events ──` comment line. Insert:

```js
function _renderRelEventRow(rel) {
    const role = escHtml(rel.role || '');
    const name = rel.name ? ' ' + escHtml(rel.name) : '';
    const verb = rel.kind === 'birth' ? 'Birth' : 'Death';
    const label = `${verb} of ${role}${name}`;
    return `<div class="evt-rel-row"><span class="yr">${rel.year}</span><span class="label">${label}</span></div>`;
}
```

- [ ] **Step 3: Modify the timeline render loop to interleave relative events**

Still in `viz_panel.js`, in the timeline block (the `if (evtDiv)` branch around line 610):

Replace this section (lines ~610-628):

```js
if (evtDiv) {
    const _addEvtBtn = `<button class="add-event-btn" onclick="addEvent(${xrefQ})">&#43; Add event</button>`;
    if (!sorted.length) { evtDiv.innerHTML = _addEvtBtn; } else {
        let html = '',
            lastSection = '';
        for (const evt of sorted) {
            let section = 'Life';
            const evtYear = evt.date ? ((_YR_RE.exec(evt.date) || [, 0])[1] | 0) : null;
            const _typ = (evt.type || '').toLowerCase();
            const _isDeathRelated = evt.tag === 'DEAT' || evt.tag === 'BURI' || evt.tag === 'PROB' ||
                (evt.tag === 'EVEN' && (_typ.includes('death') || _typ.includes('obituar') || _typ.includes('avis de d') || _typ.includes('probate')));
            if (evt.tag === 'BIRT' || (evtYear && by && evtYear <= by + 18)) section = 'Early Life';
            else if (_isDeathRelated) section = 'Later Life';

            if (section !== lastSection) {
                html += `<span class="timeline-section-label">${escHtml(section).toUpperCase()}</span>`;
                lastSection = section;
            }
```

with:

```js
if (evtDiv) {
    const _addEvtBtn = `<button class="add-event-btn" onclick="addEvent(${xrefQ})">&#43; Add event</button>`;
    const relEvents = (typeof buildRelativeEvents === 'function')
        ? buildRelativeEvents(xref)
        : [];

    // Pre-compute (year, section) for each own event so we can merge with relEvents.
    const ownRows = sorted.map(evt => {
        const evtYear = evt.date ? ((_YR_RE.exec(evt.date) || [, 0])[1] | 0) : null;
        const _typ = (evt.type || '').toLowerCase();
        const _isDeathRelated = evt.tag === 'DEAT' || evt.tag === 'BURI' || evt.tag === 'PROB' ||
            (evt.tag === 'EVEN' && (_typ.includes('death') || _typ.includes('obituar') || _typ.includes('avis de d') || _typ.includes('probate')));
        let section = 'Life';
        if (evt.tag === 'BIRT' || (evtYear && by && evtYear <= by + 18)) section = 'Early Life';
        else if (_isDeathRelated) section = 'Later Life';
        return { kind: 'own', year: evtYear, section, evt };
    });
    const relRows = relEvents.map(r => ({ kind: 'rel', year: r.year, section: r.section, rel: r }));

    // Merge: stable sort by year asc; at equal year, own rows before rel rows.
    // Rows without a year keep their position relative to neighbors via stable indexing.
    const merged = [];
    let oi = 0, ri = 0;
    while (oi < ownRows.length && ri < relRows.length) {
        const o = ownRows[oi], r = relRows[ri];
        const oy = o.year ?? Infinity;
        const ry = r.year;
        if (oy <= ry) { merged.push(o); oi++; }
        else          { merged.push(r); ri++; }
    }
    while (oi < ownRows.length) merged.push(ownRows[oi++]);
    while (ri < relRows.length) merged.push(relRows[ri++]);

    if (!merged.length) { evtDiv.innerHTML = _addEvtBtn; } else {
        let html = '',
            lastSection = '';
        for (const row of merged) {
            const section = row.section;
            if (section !== lastSection) {
                html += `<span class="timeline-section-label">${escHtml(section).toUpperCase()}</span>`;
                lastSection = section;
            }
            if (row.kind === 'rel') {
                html += _renderRelEventRow(row.rel);
                continue;
            }
            const evt = row.evt;
            const evtYear = row.year;
```

The remainder of the for-loop body (handling `MARR`, `DIV`, `RESI _run`, and the default `evt-entry`) stays unchanged — it now uses the `evt` and `evtYear` rebound at the top of each own-row iteration. **Verify after editing**: the closing `}` and `html += _addEvtBtn; evtDiv.innerHTML = html;` lines at the end of the original block still appear and still close the `for` loop and the `else` branch correctly.

- [ ] **Step 4: Add `<script>` tag for the new module in HTML**

Open `viz_ancestors.html`. Find the script tag block near line 471:

```html
<script src="/js/viz_panel.js"></script>
```

Insert a new line **above** it:

```html
<script src="/js/viz_relative_events.js"></script>
```

- [ ] **Step 5: Run JS tests to confirm nothing else broke**

Run:

```bash
npm test
```

Expected: all tests PASS, including the new `viz_relative_events.test.js` suite. If `viz_panel.test.js` fails, inspect — it likely needs `ALL_PEOPLE_BY_ID` injected, or `buildRelativeEvents` to be optional (the `typeof === 'function'` guard handles this).

- [ ] **Step 6: Manual browser verification**

Run:

```bash
python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```

Open the chart in the browser. Click on a person who has:
- multiple children with known birth years
- a deceased spouse
- at least one parent with a known death year
- ideally a child who predeceased them

Verify in the detail panel:
1. Relative-event rows appear interleaved chronologically with the person's own events.
2. They render as muted italic single-line text with a year column at left — no card border, no edit/delete buttons.
3. They use phrasing `Birth of daughter <name>`, `Death of father <name>`, etc.
4. The `Early Life` / `Life` / `Later Life` section bands still appear at the right places, and relative events sit in `Early Life` or `Life` (never `Later Life`).
5. No relative events are dated after the focused person's death year (or after birth_year + 100 if no death year).
6. At equal years, the focused person's own event appears before the relative event.

Stop the server when verified.

- [ ] **Step 7: Commit**

```bash
git add viz_ancestors.html js/viz_panel.js
git commit -m "feat(viz): show relative life events on person timeline

Births of children, deaths of children, parents, and spouse(s) now
appear on the focused person's timeline as muted italic one-liners,
interleaved chronologically with their own events. Bounded to the
person's lifetime (death_year, or birth_year+100 if unknown).

Spec: docs/superpowers/specs/2026-04-28-relative-events-on-timeline-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Sanity-pass and completion doc

- [ ] **Step 1: Run the full JS test suite once more**

```bash
npm test
```

Expected: all PASS.

- [ ] **Step 2: Run Python tests** (no GED required for unit tests)

```bash
pytest tests/
```

Expected: all PASS.

- [ ] **Step 3: Write completion doc**

Create `.claude/completions/2026-04-28-relative-events-on-timeline.md` using `.claude/templates/completion-template.md`. Cover:
- What shipped (relative life events on timeline)
- Files touched
- Spec/plan links
- Anything surprising for future-you (e.g., the `ALL_PEOPLE_BY_ID` global pattern, or the merge-loop refactor in `viz_panel.js`)

- [ ] **Step 4: Final commit**

```bash
git add .claude/completions/2026-04-28-relative-events-on-timeline.md
git commit -m "docs: completion note for relative-events-on-timeline

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
