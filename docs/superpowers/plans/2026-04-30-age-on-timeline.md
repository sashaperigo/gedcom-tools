# Age on Timeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the focal person's age beneath the year in every dated row of the panel timeline. Year stays left-aligned (so range wraps render `1942–` / `1944` cleanly); age sits centered below. Birth row shows a small uppercase `(AGE)` hint instead of `0`.

**Architecture:** A single pure helper `_ageAt(yearOrRange, birthYear)` produces the display string. Five rendering branches in `js/viz_panel.js` (standard event, collapsed RESI run, marriage card, divorce card, relative-event row) call it and append `<span class="evt-age">…</span>` (or `.evt-age-hint` for BIRT, or a `.yr-stack` wrapper for relative events) inside the existing year column. CSS in `viz_ancestors.css` switches `.evt-year-col` to a left-aligned flex column and centers the age via `align-self`.

**Tech Stack:** JavaScript ES modules (no bundler), Vitest for JS tests, plain CSS (custom properties).

**Spec:** `docs/superpowers/specs/2026-04-30-age-on-timeline-design.md`

---

## File Structure

| File                                  | Change kind | Responsibility                                                                 |
|---------------------------------------|-------------|--------------------------------------------------------------------------------|
| `js/viz_panel.js`                     | Modify      | Add `_ageAt` helper, export it; emit age HTML in the 5 row-rendering branches  |
| `viz_ancestors.css`                   | Modify      | Switch `.evt-year-col` to left-aligned flex column; add `.evt-age` / `.evt-age-hint` / `.evt-rel-row .yr-stack` rules |
| `tests/js/age_at.test.js`             | Create      | Unit tests for `_ageAt` helper                                                 |
| `tests/js/viz_panel.test.js`          | Modify      | Append DOM-render tests for each row kind                                      |

No new modules. The helper lives at top-level scope in `viz_panel.js` (not as a closure) so it can be imported by the test file via the existing `module.exports` block at the bottom of the file.

---

## Task 1: `_ageAt` helper

**Files:**
- Create: `tests/js/age_at.test.js`
- Modify: `js/viz_panel.js` — add helper near top of file (after `fmtAge`, around line 100); add to `module.exports` block (~line 1141)

- [ ] **Step 1.1: Write the failing tests**

Create `tests/js/age_at.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Stub globals viz_panel.js touches at load time
global.document = { getElementById: () => null, addEventListener: () => {} };
global.PEOPLE = {};
global.SOURCES = {};
global.setState = () => {};
global.getState = () => ({});
global.onStateChange = () => {};

const { _ageAt } = require('../../js/viz_panel.js');

describe('_ageAt', () => {
    it('returns age as string for a single year after birth', () => {
        expect(_ageAt(1942, 1926)).toBe('16');
    });

    it('returns "0" when event year equals birth year (birth row)', () => {
        expect(_ageAt(1926, 1926)).toBe('0');
    });

    it('returns range for an en-dash year range', () => {
        expect(_ageAt('1942–1944', 1926)).toBe('16–18');
    });

    it('returns range for a hyphen year range', () => {
        expect(_ageAt('1942-1944', 1926)).toBe('16–18');
    });

    it('collapses range to a single value when start equals end', () => {
        expect(_ageAt('1942–1942', 1926)).toBe('16');
    });

    it('returns null when birth year is null', () => {
        expect(_ageAt(1942, null)).toBe(null);
    });

    it('returns null when birth year is undefined', () => {
        expect(_ageAt(1942, undefined)).toBe(null);
    });

    it('returns null when year is null', () => {
        expect(_ageAt(null, 1926)).toBe(null);
    });

    it('returns null when year is empty string', () => {
        expect(_ageAt('', 1926)).toBe(null);
    });

    it('returns null when year input is unparseable', () => {
        expect(_ageAt('abc', 1926)).toBe(null);
    });

    it('returns null when range has non-numeric end', () => {
        expect(_ageAt('1942–xx', 1926)).toBe(null);
    });

    it('accepts numeric and string years equivalently', () => {
        expect(_ageAt('1942', 1926)).toBe('16');
    });
});
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `npx vitest run tests/js/age_at.test.js`
Expected: FAIL — `_ageAt` is not exported.

- [ ] **Step 1.3: Add the helper to `js/viz_panel.js`**

Insert immediately after the `fmtAge` function (around line 100, before `// ── Event labels and prose`):

```js
// Returns null when no age can be derived. Otherwise a display string:
//   single year  → "16"
//   year range   → "16" if start == end, else "16–18"
function _ageAt(yearOrRange, birthYear) {
    if (birthYear == null) return null;
    if (yearOrRange == null || yearOrRange === '') return null;
    const s = String(yearOrRange);
    const m = s.match(/^(\d{3,4})(?:\s*[–\-]\s*(\d{3,4}))?$/);
    if (!m) return null;
    const lo = parseInt(m[1], 10) - birthYear;
    const hi = m[2] ? (parseInt(m[2], 10) - birthYear) : lo;
    return lo === hi ? String(lo) : `${lo}–${hi}`;
}
```

Then add `_ageAt,` to the `module.exports` block at the bottom of the file (around line 1141), preserving alphabetical-ish ordering near the other underscore-prefixed exports:

```js
if (typeof module !== 'undefined') {
    module.exports = {
        initPanel,
        renderPanel,
        fmtDate,
        fmtPlace,
        fmtAge,
        buildProse,
        dotColor,
        collapseResidences,
        toggleResiExpand,
        buildSourceBadgeHtml,
        buildNoteSourceBadgeHtml,
        _ageAt,
        _handleGodparentClick,
        _buildGodparentPillsHtml,
        convertEventTag,
    };
}
```

- [ ] **Step 1.4: Run the test to verify it passes**

Run: `npx vitest run tests/js/age_at.test.js`
Expected: PASS — all 12 tests green.

- [ ] **Step 1.5: Commit**

```bash
git add tests/js/age_at.test.js js/viz_panel.js
git commit -m "feat(viz): add _ageAt helper for timeline age display

Pure year/range → age string transform. Used by upcoming timeline
row changes to render the focal person's age beneath the year.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Standard event rows — age beneath year, plus BIRT hint

**Files:**
- Modify: `js/viz_panel.js` — the standard event branch starting around line 787 (the `if (evt.tag === 'MARR')` and `if (evt.tag === 'DIV')` blocks come *before* this; the standard branch is the one ending the per-row loop)
- Modify: `tests/js/viz_panel.test.js` — append a new describe block

This task covers two cases together (BIRT and non-BIRT) because they share the same code path; splitting would duplicate the surrounding context.

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/js/viz_panel.test.js`:

```js
describe('renderPanel — age column on standard events', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
        global.PARENTS = {};
        global.FAMILIES = {};
        global.CHILDREN = {};
        global.ALL_PEOPLE_BY_ID = {};
    });

    function setupPanel(personData, xref = '@I1@') {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE[xref] = personData;
        global.ALL_PEOPLE_BY_ID = global.PEOPLE;
        global.getState = () => ({ panelOpen: true, panelXref: xref });
        renderPanel();
        global.getState = () => _state;
        return eventsEl;
    }

    it('renders a single-year age beneath the year on a death-of-mother-style event', () => {
        const html = setupPanel({
            name: 'Test', sex: 'M',
            birth_year: '1926',
            events: [
                { tag: 'DEAT', date: '1 Jan 1941', place: '', _origIdx: 0, event_idx: 0 },
            ],
            notes: [], sources: [],
        }).innerHTML;
        expect(html).toContain('class="evt-age"');
        expect(html).toMatch(/<span class="evt-age">15<\/span>/);
    });

    it('renders "(age)" hint on the BIRT row instead of literal 0', () => {
        const html = setupPanel({
            name: 'Test', sex: 'M',
            birth_year: '1926',
            events: [
                { tag: 'BIRT', date: '16 Jan 1926', place: 'Izmir', _origIdx: 0, event_idx: 0 },
            ],
            notes: [], sources: [],
        }).innerHTML;
        expect(html).toContain('class="evt-age-hint"');
        expect(html).toContain('(age)');
        expect(html).not.toMatch(/<span class="evt-age">0<\/span>/);
    });

    it('renders no age node when focal person has no birth year', () => {
        const html = setupPanel({
            name: 'Test', sex: 'M',
            birth_year: null,
            events: [
                { tag: 'RESI', date: '1947', place: 'England', _origIdx: 0, event_idx: 0 },
            ],
            notes: [], sources: [],
        }).innerHTML;
        expect(html).not.toContain('class="evt-age"');
        expect(html).not.toContain('class="evt-age-hint"');
    });
});
```

Note: the DEAT in the first test is the focal person's own death at age 15 (born 1926, died 1941). This exercises the same standard-event branch as a residence row would.

- [ ] **Step 2.2: Run the tests to verify they fail**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on standard events"`
Expected: FAIL — none of the three assertions match (no age HTML emitted).

- [ ] **Step 2.3: Modify the standard event branch in `js/viz_panel.js`**

Find the standard event block around line 787–812 (the one that starts `const isAnch = evt.tag === 'BIRT' || evt.tag === 'DEAT';`).

Replace lines 787–812 with:

```js
                const isAnch = evt.tag === 'BIRT' || evt.tag === 'DEAT';
                const dotCls = isAnch ? 'evt-dot dot-anchor' : 'evt-dot';
                const yearStr = evtYear ? `<span class="evt-year">${evtYear}</span>` : '';
                const ageStr = _buildAgeHtml(evt, evtYear, by);
                const delBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">✕</button>`;
                const editBtn = evt.event_idx !== null && evt.event_idx !== undefined ?
                    `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">✏</button>` :
                    '';
                const srcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);

                // Godparents (CHR/BAPM)
                const godparentHtml = _buildGodparentPillsHtml(evt, xref, xrefQ);

                const tagAbbr = (evt.tag === 'EVEN' && evt.type) ? evt.type.substring(0, 4) : (evt.tag ? evt.tag.substring(0, 4) : '');
                const noYearClass = evtYear ? '' : ' no-year';
                html +=
                    `<div class="evt-entry${noYearClass}">` +
                    `<div class="evt-year-col">${yearStr}${ageStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                    `<div class="evt-content">` +
                    `<span class="evt-prose-text">${escHtml(prose)}</span>` +
                    (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
                    noteInl +
                    godparentHtml +
                    `<div class="evt-actions">${editBtn}${delBtn}</div>` +
                    `</div>` +
                    srcBadge +
                    `</div>`;
```

Then add the shared `_buildAgeHtml` helper at module scope, immediately after `_ageAt` (in the file, so around line 115):

```js
// Renders the small age sub-element for a timeline row. Returns '' when no
// age should appear. BIRT rows show "(age)" hint regardless of computed age.
function _buildAgeHtml(evt, yearOrRange, birthYear) {
    if (birthYear == null || yearOrRange == null || yearOrRange === '') return '';
    if (evt && evt.tag === 'BIRT') {
        return `<span class="evt-age-hint">(age)</span>`;
    }
    const ageVal = _ageAt(yearOrRange, birthYear);
    return ageVal != null ? `<span class="evt-age">${ageVal}</span>` : '';
}
```

Add `_buildAgeHtml,` to the `module.exports` block (next to `_ageAt`) so future tests can reach it directly if needed.

- [ ] **Step 2.4: Run the tests to verify they pass**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on standard events"`
Expected: PASS — all three.

- [ ] **Step 2.5: Run the full panel test suite to check for regressions**

Run: `npx vitest run tests/js/viz_panel.test.js`
Expected: PASS — including the existing `renderPanel — marriage card uses evt-year-col layout` test (which only checks for the *presence* of `evt-year-col`; we haven't broken it).

- [ ] **Step 2.6: Commit**

```bash
git add js/viz_panel.js tests/js/viz_panel.test.js
git commit -m "feat(viz): show age on standard timeline events

Adds .evt-age beneath the year in standard event rows. BIRT rows
render an "(age)" hint instead of the literal 0. Rows for people
with no birth_year render no age node.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Collapsed RESI runs — age range

**Files:**
- Modify: `js/viz_panel.js` — the collapsed RESI branch (around line 767–783, the `else` branch of `if (isExpanded)` inside the `if (evt._run)` block)
- Modify: `tests/js/viz_panel.test.js` — append a describe block

- [ ] **Step 3.1: Write the failing test**

Append to `tests/js/viz_panel.test.js`:

```js
describe('renderPanel — age column on RESI ranges', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
        global.PARENTS = {};
        global.FAMILIES = {};
        global.CHILDREN = {};
        global.ALL_PEOPLE_BY_ID = {};
    });

    it('renders a year-range and age-range when residence spans multiple years', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE['@I1@'] = {
            name: 'Test', sex: 'M',
            birth_year: '1926',
            events: [
                { tag: 'RESI', date: '1942', place: 'Agra, India', _origIdx: 0, event_idx: 0 },
                { tag: 'RESI', date: '1943', place: 'Agra, India', _origIdx: 1, event_idx: 1 },
                { tag: 'RESI', date: '1944', place: 'Agra, India', _origIdx: 2, event_idx: 2 },
            ],
            notes: [], sources: [],
        };
        global.ALL_PEOPLE_BY_ID = global.PEOPLE;
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        global.getState = () => _state;
        const html = eventsEl.innerHTML;
        // Year range "1942–1944" already present today via collapseResidences
        expect(html).toContain('1942–1944');
        // New: age range "16–18"
        expect(html).toMatch(/<span class="evt-age">16–18<\/span>/);
    });
});
```

- [ ] **Step 3.2: Run to verify failure**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on RESI ranges"`
Expected: FAIL — the year-range assertion passes (existing behavior) but the age-range assertion fails.

- [ ] **Step 3.3: Modify the collapsed RESI branch**

Find lines around 767–783 in `js/viz_panel.js` (the `else` branch following `if (isExpanded)`).

Replace the construction of the collapsed RESI HTML — specifically the assignment to `html +=` and the line above it that builds `yearStr`. The current code is:

```js
                    } else {
                        const yearStr = `<span class="evt-year">${escHtml(evt._yearRange)}</span>`;
                        const expandBtn = `<button class="evt-edit-btn" title="Expand to edit" onclick="toggleResiExpand(${xrefQ},${evt.event_idx})">✏</button>`;
                        const delBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">✕</button>`;
                        const srcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);
                        html +=
                            `<div class="evt-entry">` +
                            `<div class="evt-year-col">${yearStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                            ...
```

Change it to insert `${ageStr}` between `${yearStr}` and `<span class="evt-tag-abbrev">`:

```js
                    } else {
                        const yearStr = `<span class="evt-year">${escHtml(evt._yearRange)}</span>`;
                        const ageStr = _buildAgeHtml(evt, evt._yearRange, by);
                        const expandBtn = `<button class="evt-edit-btn" title="Expand to edit" onclick="toggleResiExpand(${xrefQ},${evt.event_idx})">✏</button>`;
                        const delBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">✕</button>`;
                        const srcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);
                        html +=
                            `<div class="evt-entry">` +
                            `<div class="evt-year-col">${yearStr}${ageStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                            `<div class="evt-content">` +
                            `<span class="evt-prose-text">${escHtml(prose)}</span>` +
                            (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
                            noteInl +
                            `<div class="evt-actions">${expandBtn}${delBtn}</div>` +
                            `</div>` +
                            srcBadge +
                            `</div>`;
                    }
```

Also handle the *expanded* RESI rows (around lines 743–765, inside `if (isExpanded)` for-loop). Add `${ageStr}` there too:

```js
                        for (let ri = 0; ri < evt._run.length; ri++) {
                            const re = evt._run[ri];
                            const reYear = re.date ? ((_YR_RE.exec(re.date) || [, 0])[1] | 0) : null;
                            const reYearStr = reYear ? `<span class="evt-year">${reYear}</span>` : '';
                            const reAgeStr = _buildAgeHtml(re, reYear, by);
                            const { prose: reProse, meta: reMeta } = buildProse(re);
                            // ... rest unchanged ...
                            html +=
                                `<div class="evt-entry evt-entry-expanded">` +
                                `<div class="evt-year-col">${reYearStr}${reAgeStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                                // ... rest unchanged ...
```

- [ ] **Step 3.4: Run to verify pass**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on RESI ranges"`
Expected: PASS.

- [ ] **Step 3.5: Run full panel suite to check for regressions**

Run: `npx vitest run tests/js/viz_panel.test.js`
Expected: PASS.

- [ ] **Step 3.6: Commit**

```bash
git add js/viz_panel.js tests/js/viz_panel.test.js
git commit -m "feat(viz): show age range on collapsed RESI residence rows

A residence spanning 1942–1944 for someone born in 1926 now shows
'16–18' beneath the year range. Expanded RESI rows show single ages.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Marriage card

**Files:**
- Modify: `js/viz_panel.js` — the MARR branch (around line 672–701)
- Modify: `tests/js/viz_panel.test.js` — append a describe block

- [ ] **Step 4.1: Write the failing test**

Append to `tests/js/viz_panel.test.js`:

```js
describe('renderPanel — age column on marriage card', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
        global.PARENTS = {};
        global.FAMILIES = {};
        global.CHILDREN = {};
        global.ALL_PEOPLE_BY_ID = {};
    });

    it('renders age beneath the year in a MARR card', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE['@I1@'] = {
            name: 'Test', sex: 'M',
            birth_year: '1900',
            events: [{ tag: 'MARR', date: '1925', place: '', fam_xref: '@F1@', marr_idx: 0, _origIdx: 0, event_idx: null }],
            notes: [], sources: [],
        };
        global.PARENTS = {};
        global.ALL_PEOPLE_BY_ID = global.PEOPLE;
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        global.getState = () => _state;
        const html = eventsEl.innerHTML;
        expect(html).toContain('marr-card');
        expect(html).toMatch(/<span class="evt-age">25<\/span>/);
    });
});
```

- [ ] **Step 4.2: Run to verify failure**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on marriage card"`
Expected: FAIL — `evt-age` not in marriage card.

- [ ] **Step 4.3: Modify MARR branch**

Find the MARR branch around lines 672–701 in `js/viz_panel.js`. The relevant lines are:

```js
                    const yearLabelSpan = evtYear ? `<span class="marr-year">${evtYear}</span>` : '';
                    html +=
                        `<div class="marr-card"${marrClick}>` +
                        marrEditBtn +
                        marrDelBtn +
                        `<div class="evt-year-col">${yearLabelSpan}<span class="evt-tag-abbrev">MARR</span></div>` +
                        ...
```

Insert an age span between `${yearLabelSpan}` and `<span class="evt-tag-abbrev">`:

```js
                    const yearLabelSpan = evtYear ? `<span class="marr-year">${evtYear}</span>` : '';
                    const ageStr = _buildAgeHtml(evt, evtYear, by);
                    html +=
                        `<div class="marr-card"${marrClick}>` +
                        marrEditBtn +
                        marrDelBtn +
                        `<div class="evt-year-col">${yearLabelSpan}${ageStr}<span class="evt-tag-abbrev">MARR</span></div>` +
                        `<div class="evt-content">` +
                        proseHtml +
                        (meta && meta !== String(evtYear) ? `<div class="marr-meta">${escHtml(meta)}</div>` : '') +
                        noteInl +
                        `</div>` +
                        marrSrcBadge +
                        `</div>`;
```

- [ ] **Step 4.4: Run to verify pass**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on marriage card"`
Expected: PASS.

- [ ] **Step 4.5: Commit**

```bash
git add js/viz_panel.js tests/js/viz_panel.test.js
git commit -m "feat(viz): show age beneath year on marriage cards

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Divorce card

**Files:**
- Modify: `js/viz_panel.js` — the DIV branch (around line 704–733)
- Modify: `tests/js/viz_panel.test.js` — append a describe block

- [ ] **Step 5.1: Write the failing test**

Append to `tests/js/viz_panel.test.js`:

```js
describe('renderPanel — age column on divorce card', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
        global.PARENTS = {};
        global.FAMILIES = {};
        global.CHILDREN = {};
        global.ALL_PEOPLE_BY_ID = {};
    });

    it('renders age beneath the year in a DIV card', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE['@I1@'] = {
            name: 'Test', sex: 'M',
            birth_year: '1900',
            events: [{ tag: 'DIV', date: '1940', place: '', fam_xref: '@F1@', div_idx: 0, _origIdx: 0, event_idx: null }],
            notes: [], sources: [],
        };
        global.PARENTS = {};
        global.ALL_PEOPLE_BY_ID = global.PEOPLE;
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        global.getState = () => _state;
        const html = eventsEl.innerHTML;
        expect(html).toContain('div-card');
        expect(html).toMatch(/<span class="evt-age">40<\/span>/);
    });
});
```

- [ ] **Step 5.2: Run to verify failure**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on divorce card"`
Expected: FAIL.

- [ ] **Step 5.3: Modify DIV branch**

Find the DIV branch around lines 704–733. Modify analogously to MARR:

```js
                    const yearLabelSpan = evtYear ? `<span class="marr-year">${evtYear}</span>` : '';
                    const ageStr = _buildAgeHtml(evt, evtYear, by);
                    html +=
                        `<div class="div-card"${divClick}>` +
                        divEditBtn +
                        divDelBtn +
                        `<div class="evt-year-col">${yearLabelSpan}${ageStr}<span class="evt-tag-abbrev">DIV</span></div>` +
                        `<div class="evt-content">` +
                        proseHtml +
                        (meta && meta !== String(evtYear) ? `<div class="marr-meta">${escHtml(meta)}</div>` : '') +
                        noteInl +
                        `</div>` +
                        divSrcBadge +
                        `</div>`;
```

- [ ] **Step 5.4: Run to verify pass**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on divorce card"`
Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add js/viz_panel.js tests/js/viz_panel.test.js
git commit -m "feat(viz): show age beneath year on divorce cards

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Relative-event row — age in `.yr-stack`

**Files:**
- Modify: `js/viz_panel.js` — `_renderRelEventRow` closure around line 590–596
- Modify: `tests/js/viz_panel.test.js` — append a describe block

- [ ] **Step 6.1: Write the failing test**

Append to `tests/js/viz_panel.test.js`:

```js
describe('renderPanel — age column on relative-event row', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
        global.PARENTS = {};
        global.FAMILIES = {};
        global.CHILDREN = {};
        global.ALL_PEOPLE_BY_ID = {};
    });

    it('wraps year + age in .yr-stack and shows age string', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        // Focal person born 1926, mother dies 1941 (he's 14)
        global.PEOPLE = {
            '@I1@': {
                name: 'Child', sex: 'M', birth_year: '1926', death_year: '2000',
                events: [{ tag: 'BIRT', date: '1926', _origIdx: 0, event_idx: 0 }],
                notes: [], sources: [],
            },
            '@M@': {
                name: 'Mother', sex: 'F', birth_year: '1900', death_year: '1941',
                events: [], notes: [], sources: [],
            },
        };
        global.ALL_PEOPLE_BY_ID = global.PEOPLE;
        global.PARENTS = { '@I1@': ['@F@', '@M@'] };
        global.FAMILIES = {};
        global.CHILDREN = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        global.getState = () => _state;
        const html = eventsEl.innerHTML;
        expect(html).toContain('evt-rel-row');
        expect(html).toContain('yr-stack');
        // Mother died in 1941 → child was 15
        expect(html).toMatch(/<span class="age">15<\/span>/);
    });
});
```

Note: this test depends on `buildRelativeEvents` being globally available since `viz_panel.js` calls it via `typeof buildRelativeEvents === 'function'`. If the test runs without that function in scope, it short-circuits to `[]` and no relative-event row appears. Verify by checking the existing pattern in `tests/js/viz_relative_events.test.js` (which loads the module via `require`).

If the test fails because no relative event renders at all (rather than failing on the age assertion), add a global stub before `renderPanel()`:

```js
const relEventsMod = require('../../js/viz_relative_events.js');
global.buildRelativeEvents = relEventsMod.buildRelativeEvents;
```

- [ ] **Step 6.2: Run to verify failure**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on relative-event row"`
Expected: FAIL — neither `yr-stack` nor `age` text appears.

- [ ] **Step 6.3: Modify `_renderRelEventRow`**

Find the closure around line 590 of `js/viz_panel.js`:

```js
    function _renderRelEventRow(rel) {
        const role = escHtml(rel.role || '');
        const name = rel.name ? ' ' + escHtml(rel.name) : '';
        const verb = rel.kind === 'birth' ? 'Birth' : 'Death';
        const label = `${verb} of ${role}${name}`;
        return `<div class="evt-rel-row"><span class="yr">${rel.year}</span><span class="label">${label}</span></div>`;
    }
```

Replace with:

```js
    function _renderRelEventRow(rel) {
        const role = escHtml(rel.role || '');
        const name = rel.name ? ' ' + escHtml(rel.name) : '';
        const verb = rel.kind === 'birth' ? 'Birth' : 'Death';
        const label = `${verb} of ${role}${name}`;
        const ageVal = _ageAt(rel.year, by);
        const ageHtml = ageVal != null ? `<span class="age">${ageVal}</span>` : '';
        const yrStack = `<span class="yr-stack"><span class="yr">${rel.year}</span>${ageHtml}</span>`;
        return `<div class="evt-rel-row">${yrStack}<span class="label">${label}</span></div>`;
    }
```

This closure already has `by` in scope from the enclosing `renderPanel` function (line 464: `const by = data.birth_year ? parseInt(data.birth_year) : null;`).

- [ ] **Step 6.4: Run to verify pass**

Run: `npx vitest run tests/js/viz_panel.test.js -t "age column on relative-event row"`
Expected: PASS.

- [ ] **Step 6.5: Run all panel + relative-event tests**

Run: `npx vitest run tests/js/viz_panel.test.js tests/js/viz_relative_events.test.js`
Expected: PASS — including the existing relative-events tests (we touched only the renderer, not the data builder).

- [ ] **Step 6.6: Commit**

```bash
git add js/viz_panel.js tests/js/viz_panel.test.js
git commit -m "feat(viz): show focal-person age on relative-event timeline rows

Wraps the year and a new age sub-element in .yr-stack so e.g. the
'Death of mother' row shows the focal person's age (14) beneath the
year (1941).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: CSS — column layout and age styling

**Files:**
- Modify: `viz_ancestors.css` — `.evt-year-col` (around line 1872), add `.evt-age` and `.evt-age-hint`, update `.evt-rel-row` rules (around line 1943)

This task has no failing-test step because pure CSS visual changes don't have meaningful unit tests. We verify by visual inspection in the dev server.

- [ ] **Step 7.1: Replace `.evt-year-col` rule**

In `viz_ancestors.css`, find the rule around line 1872:

```css
.evt-year-col {
    width: 46px;
    flex-shrink: 0;
    border-right: 1px solid var(--border);
    padding-right: 10px;
}
```

Replace with:

```css
.evt-year-col {
    width: 46px;
    flex-shrink: 0;
    border-right: 1px solid var(--border);
    padding-right: 10px;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    text-align: left;
}
```

- [ ] **Step 7.2: Add `.evt-age` and `.evt-age-hint` rules**

Insert immediately after the `.evt-tag-abbrev` rule (around line 1901, before `.fact-del`):

```css
.evt-age {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 4px;
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
    align-self: center;
}

.evt-age-hint {
    font-size: 9px;
    color: var(--text-disabled);
    margin-top: 4px;
    line-height: 1.2;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    align-self: center;
}
```

- [ ] **Step 7.3: Update `.evt-rel-row` to support `.yr-stack`**

In `viz_ancestors.css`, find the existing rules around line 1943:

```css
.evt-rel-row { ... }
.evt-rel-row .yr { ... }
.evt-rel-row .label { ... }
```

Add a new `.yr-stack` rule and adjust `.yr` to remove its `width` (the wrapper now provides it):

```css
.evt-rel-row .yr-stack {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    width: 36px;
    flex-shrink: 0;
}
.evt-rel-row .yr {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: var(--text-secondary);
}
.evt-rel-row .age {
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 1px;
    font-variant-numeric: tabular-nums;
    align-self: center;
}
```

(Replace the existing `.evt-rel-row .yr` block — its `width: 36px; flex-shrink: 0;` lines move to `.yr-stack`. The `.label` rule is unchanged.)

- [ ] **Step 7.4: Visual verification**

Start the dev server with the canonical GED file:

```bash
python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```

Open the browser, click on a person who has a known birth year and a mix of events (e.g., search for "Bonnici" or "Papadopoulos"). Verify:

1. Single-year rows show year (left-aligned) with age centered beneath in muted gray.
2. Birth row shows year and a tiny "(AGE)" hint in monospace beneath.
3. RESI range row (if any) shows wrapped year ("1942–" / "1944") with "16–18" centered beneath.
4. Marriage card and divorce card (if any) show age beneath year.
5. Relative-event rows ("Death of mother", "Birth of son") show age in the gutter.
6. A person with no birth year (rare — search for someone with only a death record) shows no age anywhere.

If anything looks off, fix the CSS and re-load.

- [ ] **Step 7.5: Run the full JS test suite to confirm nothing broke**

Run: `npm test`
Expected: PASS — all existing tests still green; no new failures.

- [ ] **Step 7.6: Commit**

```bash
git add viz_ancestors.css
git commit -m "style(viz): age column styling — left-align year, center age beneath

Switches .evt-year-col to a flex column with year flush-left (so
ranges like 1942–/1944 wrap cleanly) and age centered via
align-self. Adds .evt-age (11px muted), .evt-age-hint (9px mono
uppercase for BIRT row), and a .yr-stack wrapper for the relative-
event row.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Completion doc

**Files:**
- Create: `.claude/completions/2026-04-30-age-on-timeline.md`

- [ ] **Step 8.1: Read the template**

Read `.claude/templates/completion-template.md` to see the expected structure.

- [ ] **Step 8.2: Write the completion doc**

Use the template. Cover:
- Summary of what landed (one-paragraph)
- Files changed: `js/viz_panel.js`, `viz_ancestors.css`, `tests/js/age_at.test.js`, `tests/js/viz_panel.test.js`
- Tests added (count by describe block)
- Visual confirmation in the dev server
- Spec link: `docs/superpowers/specs/2026-04-30-age-on-timeline-design.md`
- Plan link: `docs/superpowers/plans/2026-04-30-age-on-timeline.md`

- [ ] **Step 8.3: Commit**

```bash
git add .claude/completions/2026-04-30-age-on-timeline.md
git commit -m "docs(completion): age on timeline

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review Checklist (run before handoff)

- ✅ Spec coverage: all five row kinds (standard, RESI run, MARR, DIV, rel-event) have tasks. BIRT hint covered in Task 2. No-birth-year fallback covered in Task 2 step 2.1. Year-range case covered in Task 3. CSS in Task 7. Helper unit-tested in Task 1.
- ✅ Each step has runnable commands + expected output, no "TBD".
- ✅ Type/name consistency: `_ageAt` and `_buildAgeHtml` are referenced consistently across tasks; both added to `module.exports` in Task 1 and Task 2.
- ✅ Range-format constants: spec uses U+2013 en-dash `–`; tests and code consistently use `–` escape.
- ✅ Test isolation: every describe block resets `_setState_calls`, `_state`, `PEOPLE`, etc. in `beforeEach`.

---

## Risks / things to watch during implementation

- The standard-event branch in Task 2 uses `evtYear` for `_buildAgeHtml`, but `evtYear` can be `null` for events with no parseable year — `_ageAt` returns `null` in that case, `_buildAgeHtml` returns `''`. Verify the no-year regression test in Task 2 step 2.1.
- Task 6's relative-event renderer relies on `by` being in the enclosing function scope. Confirm `_renderRelEventRow` is defined inside `renderPanel` (it is, line 590) and that `by` is computed before the closure is invoked (it is, line 464).
- Task 3's expanded RESI rows pass `reYear` (an integer) to `_buildAgeHtml`. The collapsed branch passes `evt._yearRange` (a string). Both are valid inputs to `_ageAt`.
