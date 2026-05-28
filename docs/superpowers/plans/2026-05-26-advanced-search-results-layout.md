# Advanced Search Results-Pane Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After the user clicks Search in the advanced-search side pane, collapse the form into a one-line filter-chip summary and show a paginated, sortable, scrollable results list that fills the rest of the pane.

**Architecture:** Two-mode pane (`form` ↔ `results`) driven by a `data-mode` attribute. The form DOM is unchanged; a sibling `.adv-results-mode` container holds the new filter-chip bar, count/sort bar, scrollable list, and pager. Rendering of the results mode is split into a pure-string template module (easily unit-testable) plus a thin controller that wires events.

**Tech Stack:** Vanilla JS (ES module style + global IIFE registration), Vitest with manual `global.document` stubs, plain CSS.

**Reference spec:** `docs/superpowers/specs/2026-05-26-advanced-search-results-layout-design.md`

---

## File Structure

**New files:**
- `js/viz_advanced_results.js` — Pure render-to-HTML helpers for results mode: `buildFilterChipsHTML(criteria)`, `buildCountBarHTML(total, sort)`, `buildResultRowsHTML(rows, ctx)`, `buildPagerHTML(page, total, perPage)`. No DOM mutation, no event listeners — emits strings only. Also exports `paginate(arr, page, perPage)` and `sortResults(rows, sortKey)`.
- `tests/js/viz_advanced_results.test.js` — Vitest specs for the above pure functions.

**Modified files:**
- `viz_ancestors.html` — Wrap the existing form sections in `<div class="adv-form">…</div>` and add a sibling `<div class="adv-results-mode">…</div>` with empty containers for filter-bar, count-bar, list, pager. Add `data-mode="form"` on `.adv-pane-body`.
- `viz_ancestors.css` — Add styles for `.adv-form`/`.adv-results-mode` mode-switch, `.adv-filterbar`, `.adv-countbar`, `.adv-resultlist`, `.adv-pager`, `.adv-row`. Adjust `#adv-search-pane` to enable the new layout (already `display:flex; flex-direction:column`). Remove `#adv-results` rules that no longer apply.
- `js/viz_advanced_search.js` — Add the pane mode machine (`currentMode`, `currentCriteria`, `currentResults`, `currentPage`, `currentSort`). On Search: serialize form → criteria, run search, switch to results mode, render via `viz_advanced_results.js`. Wire pager + sort dropdown + filter-bar-click-to-edit. Remove the old `renderResults` and `#adv-results` references.
- `tests/js/viz_advanced_search.test.js` — Existing pure-function tests stay. No new tests here (mode controller is exercised manually like the rest of the IIFE).

---

## Task 1: Pure render helpers — filter chips

**Files:**
- Create: `js/viz_advanced_results.js`
- Create: `tests/js/viz_advanced_results.test.js`

- [ ] **Step 1: Write the failing test**

```js
// tests/js/viz_advanced_results.test.js
import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { buildFilterChipsHTML } = require('../../js/viz_advanced_results.js');

describe('buildFilterChipsHTML', () => {
    it('emits chips for name + sex + event + family criteria', () => {
        const html = buildFilterChipsHTML({
            firstName: 'Maria',
            lastName: 'Aliotti',
            sex: new Set(['F']),
            events: [{ kind: 'birth', place: 'Smyrna', yearFrom: 1850, yearTo: 1920 }],
            family: [{ kind: 'spouse', name: 'Domenico' }],
        });
        expect(html).toContain('First: Maria');
        expect(html).toContain('Last: Aliotti');
        expect(html).toContain('Female');
        expect(html).toContain('Born in Smyrna 1850–1920');
        expect(html).toContain('Spouse: Domenico');
        expect(html).toContain('class="adv-chip"');
    });

    it('skips empty event/family sections', () => {
        const html = buildFilterChipsHTML({
            firstName: 'X', lastName: '', sex: new Set(),
            events: [{ kind: 'birth', place: '', yearFrom: null, yearTo: null }],
            family: [{ kind: 'spouse', name: '' }],
        });
        expect(html).toContain('First: X');
        expect(html).not.toContain('Born');
        expect(html).not.toContain('Spouse');
    });

    it('formats year ranges: from-only, to-only, exact, range', () => {
        const mk = (yf, yt) => buildFilterChipsHTML({
            firstName: '', lastName: '', sex: new Set(),
            events: [{ kind: 'death', place: 'Izmir', yearFrom: yf, yearTo: yt }],
            family: [],
        });
        expect(mk(1900, 1920)).toContain('Died in Izmir 1900–1920');
        expect(mk(1900, null)).toContain('Died in Izmir 1900–');
        expect(mk(null, 1920)).toContain('Died in Izmir –1920');
        expect(mk(1900, 1900)).toContain('Died in Izmir 1900');
    });

    it('escapes HTML in user-entered text', () => {
        const html = buildFilterChipsHTML({
            firstName: '<script>', lastName: '', sex: new Set(),
            events: [], family: [],
        });
        expect(html).not.toContain('<script>');
        expect(html).toContain('&lt;script&gt;');
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/js/viz_advanced_results.test.js`
Expected: FAIL with "Cannot find module '../../js/viz_advanced_results.js'".

- [ ] **Step 3: Write minimal implementation**

```js
// js/viz_advanced_results.js
// Pure render-to-HTML helpers for the advanced-search results mode.

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

const _EVENT_VERB = { birth: 'Born', death: 'Died', marriage: 'Married', residence: 'Lived', any: 'Event' };
const _FAMILY_LABEL = { spouse: 'Spouse', father: 'Father', mother: 'Mother', other: 'Person' };

function _yearRange(yf, yt) {
    if (yf != null && yt != null) return yf === yt ? String(yf) : `${yf}–${yt}`;
    if (yf != null) return `${yf}–`;
    if (yt != null) return `–${yt}`;
    return '';
}

function _eventChipText(evt) {
    const verb = _EVENT_VERB[evt.kind] || 'Event';
    const place = evt.place ? ` in ${evt.place}` : '';
    const yr = _yearRange(evt.yearFrom, evt.yearTo);
    return `${verb}${place}${yr ? ' ' + yr : ''}`;
}

function buildFilterChipsHTML(criteria) {
    const chips = [];
    if (criteria.firstName) chips.push(`First: ${escapeHtml(criteria.firstName)}`);
    if (criteria.lastName)  chips.push(`Last: ${escapeHtml(criteria.lastName)}`);
    if (criteria.sex && criteria.sex.has('M')) chips.push('Male');
    if (criteria.sex && criteria.sex.has('F')) chips.push('Female');
    for (const e of (criteria.events || [])) {
        if (!e.place && e.yearFrom == null && e.yearTo == null) continue;
        chips.push(escapeHtml(_eventChipText(e)));
    }
    for (const f of (criteria.family || [])) {
        if (!f.name) continue;
        chips.push(`${_FAMILY_LABEL[f.kind] || 'Person'}: ${escapeHtml(f.name)}`);
    }
    return chips.map(c => `<span class="adv-chip">${c}</span>`).join('');
}

if (typeof module !== 'undefined') {
    module.exports = { buildFilterChipsHTML, escapeHtml };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/js/viz_advanced_results.test.js`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add js/viz_advanced_results.js tests/js/viz_advanced_results.test.js
git commit -m "feat(adv-search): buildFilterChipsHTML for results-mode chip bar"
```

---

## Task 2: Pure render helpers — count bar + sort

**Files:**
- Modify: `js/viz_advanced_results.js`
- Modify: `tests/js/viz_advanced_results.test.js`

- [ ] **Step 1: Append failing test**

```js
// Append at end of tests/js/viz_advanced_results.test.js
const { buildCountBarHTML } = require('../../js/viz_advanced_results.js');

describe('buildCountBarHTML', () => {
    it('shows count with correct pluralization and selected sort', () => {
        const h0 = buildCountBarHTML(0, 'name');
        expect(h0).toContain('0 matches');
        const h1 = buildCountBarHTML(1, 'name');
        expect(h1).toContain('1 match');
        expect(h1).not.toContain('1 matches');
        const h2 = buildCountBarHTML(156, 'birth');
        expect(h2).toContain('156 matches');
    });

    it('marks the selected sort option', () => {
        const html = buildCountBarHTML(10, 'birth');
        // The <option value="birth"> should be the selected one.
        expect(html).toMatch(/<option[^>]*value="birth"[^>]*selected/);
        expect(html).not.toMatch(/<option[^>]*value="name"[^>]*selected/);
    });

    it('includes both sort options', () => {
        const html = buildCountBarHTML(10, 'name');
        expect(html).toContain('value="name"');
        expect(html).toContain('value="birth"');
        expect(html).toContain('Name');
        expect(html).toContain('Birth year');
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/js/viz_advanced_results.test.js`
Expected: FAIL with "buildCountBarHTML is not a function".

- [ ] **Step 3: Add implementation to `js/viz_advanced_results.js`**

Insert before the `if (typeof module !== 'undefined')` line:

```js
function buildCountBarHTML(total, sortKey) {
    const word = total === 1 ? 'match' : 'matches';
    const opts = [
        { v: 'name',  label: 'Name' },
        { v: 'birth', label: 'Birth year' },
    ];
    const optHTML = opts.map(o =>
        `<option value="${o.v}"${o.v === sortKey ? ' selected' : ''}>${o.label}</option>`
    ).join('');
    return `<span class="adv-count"><b>${total}</b> ${word}</span>` +
        `<span class="adv-sort">Sort: <select class="adv-sort-select">${optHTML}</select></span>`;
}
```

Update the `module.exports` to include `buildCountBarHTML`:

```js
module.exports = { buildFilterChipsHTML, buildCountBarHTML, escapeHtml };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/js/viz_advanced_results.test.js`
Expected: PASS, 7 tests total.

- [ ] **Step 5: Commit**

```bash
git add js/viz_advanced_results.js tests/js/viz_advanced_results.test.js
git commit -m "feat(adv-search): buildCountBarHTML with sort dropdown"
```

---

## Task 3: Pure render helpers — result rows + sort + pagination

**Files:**
- Modify: `js/viz_advanced_results.js`
- Modify: `tests/js/viz_advanced_results.test.js`

- [ ] **Step 1: Append failing tests**

```js
const { buildResultRowsHTML, paginate, sortResults } = require('../../js/viz_advanced_results.js');

describe('paginate', () => {
    it('returns the requested page slice', () => {
        const arr = Array.from({ length: 60 }, (_, i) => i);
        expect(paginate(arr, 1, 25)).toEqual(arr.slice(0, 25));
        expect(paginate(arr, 2, 25)).toEqual(arr.slice(25, 50));
        expect(paginate(arr, 3, 25)).toEqual(arr.slice(50, 60));
    });
    it('returns [] for out-of-range pages', () => {
        expect(paginate([1, 2, 3], 5, 25)).toEqual([]);
    });
});

describe('sortResults', () => {
    const rows = [
        { id: 'a', name: 'Zara', birth_year: 1900 },
        { id: 'b', name: 'Anna', birth_year: 1850 },
        { id: 'c', name: 'Mia',  birth_year: null },
    ];
    it('sorts by name alphabetically', () => {
        const out = sortResults(rows, 'name');
        expect(out.map(r => r.id)).toEqual(['b', 'c', 'a']);
    });
    it('sorts by birth year ascending, undated last', () => {
        const out = sortResults(rows, 'birth');
        expect(out.map(r => r.id)).toEqual(['b', 'a', 'c']);
    });
    it('does not mutate the input array', () => {
        const original = rows.map(r => r.id);
        sortResults(rows, 'name');
        expect(rows.map(r => r.id)).toEqual(original);
    });
});

describe('buildResultRowsHTML', () => {
    const peopleById = {
        I1: { name: 'Anna Aliotti', events: [
            { tag: 'BIRT', date: '1850', place: 'Smyrna, Izmir, Turkey' },
            { tag: 'DEAT', date: '1920', place: 'Smyrna' },
        ]},
        I2: { name: 'Bob Smith', events: [
            { tag: 'BIRT', date: '1900', place: '' },
        ]},
        I3: { name: 'No Dates', events: [] },
    };
    const spousesOf = { I1: ['I2'] };

    it('renders one row per person with name + meta line', () => {
        const html = buildResultRowsHTML(
            [{ id: 'I1' }, { id: 'I2' }],
            { peopleById, spousesOf }
        );
        expect(html).toContain('Anna Aliotti');
        expect(html).toContain('Bob Smith');
        // Two rows.
        expect(html.match(/class="adv-row"/g).length).toBe(2);
    });

    it('formats years as b–d, b–, b only', () => {
        const h1 = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(h1).toMatch(/1850–1920/);
        const h2 = buildResultRowsHTML([{ id: 'I2' }], { peopleById, spousesOf });
        expect(h2).toMatch(/b\.\s*1900/);
        const h3 = buildResultRowsHTML([{ id: 'I3' }], { peopleById, spousesOf });
        // No years means meta line skips the year segment.
        expect(h3).not.toMatch(/\d{4}/);
    });

    it('shows spouse name when available', () => {
        const html = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(html).toContain('spouse Bob Smith');
    });

    it('truncates long place names to the last two segments', () => {
        const html = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        // "Smyrna, Izmir, Turkey" → "Izmir, Turkey"
        expect(html).toContain('Izmir, Turkey');
        expect(html).not.toContain('Smyrna, Izmir, Turkey');
    });

    it('embeds the person xref as data-id', () => {
        const html = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(html).toContain('data-id="I1"');
    });
});

describe('buildPagerHTML', () => {
    const { buildPagerHTML } = require('../../js/viz_advanced_results.js');

    it('renders "X–Y of N" range', () => {
        expect(buildPagerHTML(1, 156, 25)).toContain('1–25 of 156');
        expect(buildPagerHTML(2, 156, 25)).toContain('26–50 of 156');
        expect(buildPagerHTML(7, 156, 25)).toContain('151–156 of 156');
    });

    it('disables prev on page 1 and next on last page', () => {
        const h1 = buildPagerHTML(1, 60, 25);
        expect(h1).toMatch(/data-page="prev"[^>]*disabled/);
        expect(h1).not.toMatch(/data-page="next"[^>]*disabled/);
        const hLast = buildPagerHTML(3, 60, 25);
        expect(hLast).toMatch(/data-page="next"[^>]*disabled/);
    });

    it('marks the current page button as active', () => {
        const html = buildPagerHTML(2, 100, 25);
        expect(html).toMatch(/data-page="2"[^>]*class="[^"]*active/);
    });

    it('renders nothing when total fits in one page', () => {
        expect(buildPagerHTML(1, 10, 25)).toBe('');
    });

    it('windows page buttons around the current page for many pages', () => {
        // 50 pages, currently on page 25 — should show 1 … 24 [25] 26 … 50.
        const html = buildPagerHTML(25, 25 * 50, 25);
        expect(html).toMatch(/data-page="1"/);
        expect(html).toMatch(/data-page="24"/);
        expect(html).toMatch(/data-page="25"[^>]*active/);
        expect(html).toMatch(/data-page="26"/);
        expect(html).toMatch(/data-page="50"/);
        expect(html).toContain('…');
        expect(html).not.toMatch(/data-page="10"/);
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/js/viz_advanced_results.test.js`
Expected: FAIL — multiple "is not a function" errors.

- [ ] **Step 3: Add implementations to `js/viz_advanced_results.js`**

Insert before the `if (typeof module !== 'undefined')` line:

```js
function paginate(arr, page, perPage) {
    const start = (page - 1) * perPage;
    return arr.slice(start, start + perPage);
}

function sortResults(rows, sortKey) {
    const copy = rows.slice();
    if (sortKey === 'birth') {
        copy.sort((a, b) => {
            const ya = a.birth_year, yb = b.birth_year;
            if (ya == null && yb == null) return 0;
            if (ya == null) return 1;   // undated last
            if (yb == null) return -1;
            return ya - yb;
        });
    } else {
        // 'name' — case-insensitive alphabetical on full name
        copy.sort((a, b) => {
            const na = (a.name || '').toLowerCase();
            const nb = (b.name || '').toLowerCase();
            return na < nb ? -1 : na > nb ? 1 : 0;
        });
    }
    return copy;
}

function _extractYear(dateStr) {
    if (!dateStr) return null;
    const m = String(dateStr).match(/\b(\d{4})\b/);
    return m ? parseInt(m[1], 10) : null;
}

function _truncatePlace(place) {
    if (!place) return '';
    const parts = place.split(',').map(s => s.trim()).filter(Boolean);
    if (parts.length <= 2) return parts.join(', ');
    return parts.slice(-2).join(', ');
}

function _formatRowMeta(person, spouseName) {
    const birth = (person.events || []).find(e => e.tag === 'BIRT');
    const death = (person.events || []).find(e => e.tag === 'DEAT');
    const by = birth ? _extractYear(birth.date) : null;
    const dy = death ? _extractYear(death.date) : null;
    const segments = [];
    if (by != null && dy != null) segments.push(`${by}–${dy}`);
    else if (by != null)          segments.push(`b. ${by}`);
    else if (dy != null)          segments.push(`d. ${dy}`);
    const place = _truncatePlace((birth && birth.place) || (death && death.place) || '');
    if (place) segments.push(place);
    if (spouseName) segments.push(`spouse ${spouseName}`);
    return segments.join(' · ');
}

function buildResultRowsHTML(rows, ctx) {
    const { peopleById, spousesOf } = ctx;
    const out = [];
    for (const r of rows) {
        const full = peopleById[r.id] || r;
        const spouseXref = (spousesOf && spousesOf[r.id]) ? spousesOf[r.id][0] : null;
        const spouseName = spouseXref && peopleById[spouseXref] ? peopleById[spouseXref].name : null;
        const meta = _formatRowMeta(full, spouseName);
        out.push(
            `<div class="adv-row" data-id="${escapeHtml(r.id)}">` +
                `<div class="adv-row-name">${escapeHtml(full.name || '?')}</div>` +
                (meta ? `<div class="adv-row-meta">${escapeHtml(meta)}</div>` : '') +
            `</div>`
        );
    }
    return out.join('');
}

function buildPagerHTML(page, total, perPage) {
    const pageCount = Math.ceil(total / perPage);
    if (pageCount <= 1) return '';
    const start = (page - 1) * perPage + 1;
    const end = Math.min(page * perPage, total);

    // Windowing: always show 1, last, current ± 1, with … for gaps.
    const nums = new Set([1, pageCount, page - 1, page, page + 1]);
    const visible = [...nums].filter(n => n >= 1 && n <= pageCount).sort((a, b) => a - b);
    const btns = [];
    let prev = 0;
    for (const n of visible) {
        if (n - prev > 1) btns.push('<span class="adv-pager-gap">…</span>');
        btns.push(
            `<button type="button" class="adv-pager-num${n === page ? ' active' : ''}" ` +
                `data-page="${n}">${n}</button>`
        );
        prev = n;
    }
    const prevDis = page === 1 ? ' disabled' : '';
    const nextDis = page === pageCount ? ' disabled' : '';
    return (
        `<span class="adv-pager-range">${start}–${end} of ${total}</span>` +
        `<span class="adv-pager-btns">` +
            `<button type="button" data-page="prev"${prevDis}>‹</button>` +
            btns.join('') +
            `<button type="button" data-page="next"${nextDis}>›</button>` +
        `</span>`
    );
}
```

Update the export:

```js
module.exports = {
    buildFilterChipsHTML, buildCountBarHTML, buildResultRowsHTML,
    buildPagerHTML, paginate, sortResults, escapeHtml,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/js/viz_advanced_results.test.js`
Expected: PASS, all tests across the file (about 18 total).

- [ ] **Step 5: Commit**

```bash
git add js/viz_advanced_results.js tests/js/viz_advanced_results.test.js
git commit -m "feat(adv-search): result-row, pagination, and sort helpers"
```

---

## Task 4: HTML scaffold for two-mode pane

**Files:**
- Modify: `viz_ancestors.html:27-70`

- [ ] **Step 1: Update the pane markup**

Replace the existing `<aside id="adv-search-pane" hidden>…</aside>` block (lines 27-70) with:

```html
<aside id="adv-search-pane" hidden>
    <div class="adv-pane-head">
        <h2 id="adv-pane-title">Advanced search</h2>
        <button id="adv-pane-close" type="button" title="Close">×</button>
    </div>
    <div class="adv-pane-body" data-mode="form">
        <div class="adv-form">
            <section class="adv-grp">
                <h3>Name</h3>
                <input id="adv-first-name" type="text" placeholder="First name" autocomplete="off">
                <input id="adv-last-name" type="text" placeholder="Last name" autocomplete="off">
            </section>
            <section class="adv-grp">
                <h3>Sex</h3>
                <label class="adv-cb"><input type="checkbox" id="adv-sex-m"> Male</label>
                <label class="adv-cb"><input type="checkbox" id="adv-sex-f"> Female</label>
            </section>
            <section class="adv-grp">
                <h3>Add life event</h3>
                <div class="adv-pillrow" id="adv-event-pills">
                    <span class="adv-pill" data-kind="birth">Birth</span>
                    <span class="adv-pill" data-kind="marriage">Marriage</span>
                    <span class="adv-pill" data-kind="residence">Residence</span>
                    <span class="adv-pill" data-kind="death">Death</span>
                    <span class="adv-pill" data-kind="any">Any event</span>
                </div>
                <div id="adv-event-sections"></div>
            </section>
            <section class="adv-grp">
                <h3>Add family member</h3>
                <div class="adv-pillrow" id="adv-family-pills">
                    <span class="adv-pill" data-kind="spouse">Spouse</span>
                    <span class="adv-pill" data-kind="father">Father</span>
                    <span class="adv-pill" data-kind="mother">Mother</span>
                    <span class="adv-pill" data-kind="other">Other person</span>
                </div>
                <div id="adv-family-sections"></div>
            </section>
            <div class="adv-actions">
                <button id="adv-search-btn" type="button">Search</button>
                <button id="adv-clear-btn" type="button">Clear</button>
            </div>
        </div>
        <div class="adv-results-mode">
            <div class="adv-filterbar" id="adv-filterbar" title="Click to edit filters">
                <div class="adv-chips" id="adv-chips"></div>
                <span class="adv-edit-link">Edit</span>
            </div>
            <div class="adv-countbar" id="adv-countbar"></div>
            <div class="adv-resultlist" id="adv-resultlist"></div>
            <div class="adv-pager" id="adv-pager"></div>
        </div>
    </div>
</aside>
```

- [ ] **Step 2: Verify markup is syntactically valid**

Run: `python -c "import html.parser, pathlib; p=html.parser.HTMLParser(); p.feed(pathlib.Path('viz_ancestors.html').read_text()); print('ok')"`
Expected: `ok` (no exception).

- [ ] **Step 3: Commit**

```bash
git add viz_ancestors.html
git commit -m "feat(adv-search): HTML scaffold for two-mode pane (form/results)"
```

---

## Task 5: CSS for results mode

**Files:**
- Modify: `viz_ancestors.css` (around line 2826)

- [ ] **Step 1: Replace the `#adv-results*` rules and add new results-mode rules**

Find the existing block starting at `#adv-search-pane {` (line ~2826) through the last `.adv-result` rule. Keep everything from `#adv-search-pane` through `.adv-actions button { … }` unchanged (the form styling). Then **delete** the four rules from `#adv-results { margin-top: 12px; }` through `.adv-result .adv-fact-label { … }` (the old result-row styles). In their place, append:

```css
/* Two-mode pane body: form vs results. */
.adv-pane-body { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.adv-pane-body[data-mode="form"]    .adv-results-mode { display: none; }
.adv-pane-body[data-mode="results"] .adv-form         { display: none; }
.adv-form { flex: 1; overflow-y: auto; padding: 12px 14px; }
.adv-results-mode { flex: 1; display: flex; flex-direction: column; min-height: 0; }

/* Filter-summary bar (results mode). */
.adv-filterbar {
    padding: 10px 14px; background: #eaf2fb; border-bottom: 1px solid #d8e3f0;
    display: flex; align-items: center; gap: 8px; cursor: pointer;
}
.adv-filterbar:hover { background: #dbe9f7; }
.adv-chips { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; min-width: 0; }
.adv-chip {
    font-size: 11px; background: #fff; border: 1px solid #c8d8ea; color: #2a4d7a;
    padding: 2px 7px; border-radius: 10px; white-space: nowrap;
}
.adv-edit-link {
    font-size: 11px; color: #2a6fa8; font-weight: 600;
    text-decoration: underline; white-space: nowrap;
}

/* Count + sort bar. */
.adv-countbar {
    padding: 7px 14px; font-size: 11px; color: #666; background: #fafcfe;
    border-bottom: 1px solid #eef2f7; display: flex;
    align-items: center; justify-content: space-between;
}
.adv-sort-select { font-size: 11px; border: 1px solid #d0d0d0; border-radius: 3px; padding: 1px 4px; }

/* Scrollable list of result rows. */
.adv-resultlist { flex: 1; overflow-y: auto; }
.adv-row { padding: 8px 14px; border-bottom: 1px solid #eef2f7; cursor: pointer; }
.adv-row:hover, .adv-row.active { background: #eaf2fb; }
.adv-row-name { font-weight: 600; font-size: 13px; color: #222; }
.adv-row-meta { font-size: 11px; color: #666; margin-top: 2px; }

/* Pager pinned to the bottom of the pane. */
.adv-pager {
    padding: 8px 14px; border-top: 1px solid #d8e3f0; background: #f5f8fb;
    display: flex; align-items: center; justify-content: space-between;
    font-size: 11px; color: #666;
}
.adv-pager:empty { display: none; }
.adv-pager-btns { display: flex; gap: 4px; }
.adv-pager button {
    background: #fff; border: 1px solid #c8d8ea; border-radius: 3px;
    padding: 2px 8px; font-size: 11px; cursor: pointer; color: #2a4d7a;
}
.adv-pager button.active { background: #2a4d7a; color: #fff; border-color: #2a4d7a; }
.adv-pager button:disabled { color: #bbb; cursor: default; }
.adv-pager-gap { color: #999; padding: 0 2px; }
```

- [ ] **Step 2: Commit**

```bash
git add viz_ancestors.css
git commit -m "feat(adv-search): CSS for two-mode pane + chip/list/pager"
```

---

## Task 6: Controller mode machine + rendering wire-up

**Files:**
- Modify: `js/viz_advanced_search.js:179-402` (the DOM IIFE)
- Modify: `viz_ancestors.py` (to ensure the new JS module is loaded — check first)

- [ ] **Step 1: Check whether viz_ancestors.py needs to register the new JS file**

Run: `grep -n "viz_advanced_search\|viz_advanced_results" viz_ancestors.py`
If `viz_advanced_search.js` appears in a list of script files, you'll need to add `viz_advanced_results.js` alongside it. If it doesn't appear (e.g., scripts are bundled by glob), no change needed.

If a change is needed, add `viz_advanced_results.js` to the same list, immediately before `viz_advanced_search.js`, so its functions are defined when the controller runs.

- [ ] **Step 2: Replace the IIFE in `js/viz_advanced_search.js`**

In `js/viz_advanced_search.js`, replace everything from line 179 (`if (typeof document !== 'undefined' && document.getElementById('adv-search-pane')) {`) through line 402 (the closing `}` of the IIFE — i.e., the line right before `if (typeof module !== 'undefined')`) with:

```js
if (typeof document !== 'undefined' && document.getElementById('adv-search-pane')) {
    (function () {
        const PER_PAGE = 25;

        // Elements
        const pane    = document.getElementById('adv-search-pane');
        const body    = pane.querySelector('.adv-pane-body');
        const toggle  = document.getElementById('advanced-search-toggle');
        const closeBt = document.getElementById('adv-pane-close');
        const evtPills   = document.getElementById('adv-event-pills');
        const evtSects   = document.getElementById('adv-event-sections');
        const famPills   = document.getElementById('adv-family-pills');
        const famSects   = document.getElementById('adv-family-sections');
        const searchBtn  = document.getElementById('adv-search-btn');
        const clearBtn   = document.getElementById('adv-clear-btn');
        const firstName  = document.getElementById('adv-first-name');
        const lastName   = document.getElementById('adv-last-name');
        const sexM       = document.getElementById('adv-sex-m');
        const sexF       = document.getElementById('adv-sex-f');
        const filterbar  = document.getElementById('adv-filterbar');
        const chipsEl    = document.getElementById('adv-chips');
        const countbarEl = document.getElementById('adv-countbar');
        const listEl     = document.getElementById('adv-resultlist');
        const pagerEl    = document.getElementById('adv-pager');

        const relIndex = buildRelIndex(FAMILIES, PARENTS);
        const ctx = { PARENTS, PEOPLE_BY_ID: PEOPLE, relIndex };

        const eventSections = [];
        const familySections = [];

        // Results-mode state
        let currentCriteria = null;
        let currentResults  = [];
        let currentPage     = 1;
        let currentSort     = 'name';

        // ── Mode switching ─────────────────────────────────────────────
        function setMode(mode) { body.setAttribute('data-mode', mode); }

        toggle.addEventListener('click', () => { pane.hidden = false; });
        closeBt.addEventListener('click', () => { pane.hidden = true; });

        filterbar.addEventListener('click', () => { setMode('form'); });

        // ── Form section pills (unchanged from prior implementation) ─
        evtPills.addEventListener('click', e => {
            const pill = e.target.closest('.adv-pill');
            if (!pill || pill.classList.contains('disabled')) return;
            addEventSection(pill.dataset.kind);
        });
        famPills.addEventListener('click', e => {
            const pill = e.target.closest('.adv-pill');
            if (!pill || pill.classList.contains('disabled')) return;
            addFamilySection(pill.dataset.kind);
        });

        function setPillDisabled(row, kind, disabled) {
            const pill = row.querySelector(`.adv-pill[data-kind="${kind}"]`);
            if (pill) pill.classList.toggle('disabled', disabled);
        }

        function addEventSection(kind) {
            if (kind !== 'any') setPillDisabled(evtPills, kind, true);
            const labels = { birth: 'Birth', marriage: 'Marriage', residence: 'Residence', death: 'Death', any: 'Any event' };
            const wrap = document.createElement('div');
            wrap.className = 'adv-section';
            wrap.innerHTML = `
                <button class="adv-x" type="button" title="Remove">×</button>
                <h4>${labels[kind]}</h4>
                <label>Place</label>
                <input type="text" class="adv-place" placeholder="City, region, country">
                <label>Year</label>
                <div class="adv-yearrow">
                    <input type="text" class="adv-from" placeholder="From" inputmode="numeric">
                    <span class="adv-sep">–</span>
                    <input type="text" class="adv-to" placeholder="To" inputmode="numeric">
                </div>
                <div class="adv-hint">Leave From blank for "To or earlier." Same year in both = exact match.</div>
            `;
            const entry = { kind, node: wrap };
            wrap.querySelector('.adv-x').addEventListener('click', () => {
                wrap.remove();
                const i = eventSections.indexOf(entry);
                if (i >= 0) eventSections.splice(i, 1);
                if (kind !== 'any') setPillDisabled(evtPills, kind, false);
                updateCount();
            });
            wrap.addEventListener('input', updateCount);
            evtSects.appendChild(wrap);
            eventSections.push(entry);
            updateCount();
        }

        function addFamilySection(kind) {
            if (kind !== 'other') setPillDisabled(famPills, kind, true);
            const labels = { spouse: 'Spouse', father: 'Father', mother: 'Mother', other: 'Other person' };
            const wrap = document.createElement('div');
            wrap.className = 'adv-section';
            wrap.innerHTML = `
                <button class="adv-x" type="button" title="Remove">×</button>
                <h4>${labels[kind]}</h4>
                <input type="text" class="adv-relname" placeholder="Name">
            `;
            const entry = { kind, node: wrap };
            wrap.querySelector('.adv-x').addEventListener('click', () => {
                wrap.remove();
                const i = familySections.indexOf(entry);
                if (i >= 0) familySections.splice(i, 1);
                if (kind !== 'other') setPillDisabled(famPills, kind, false);
                updateCount();
            });
            wrap.addEventListener('input', updateCount);
            famSects.appendChild(wrap);
            familySections.push(entry);
            updateCount();
        }

        function parseIntOrNull(s) {
            const n = parseInt(s, 10);
            return Number.isFinite(n) ? n : null;
        }

        function readQuery() {
            const sex = new Set();
            if (sexM.checked) sex.add('M');
            if (sexF.checked) sex.add('F');
            const events = eventSections.map(s => ({
                kind: s.kind,
                place: s.node.querySelector('.adv-place').value.trim(),
                yearFrom: parseIntOrNull(s.node.querySelector('.adv-from').value),
                yearTo:   parseIntOrNull(s.node.querySelector('.adv-to').value),
            }));
            const family = familySections.map(s => ({
                kind: s.kind,
                name: s.node.querySelector('.adv-relname').value.trim(),
            }));
            return {
                firstName: firstName.value.trim(),
                lastName:  lastName.value.trim(),
                sex, events, family,
            };
        }

        function isQueryEmpty(q) {
            if (q.firstName || q.lastName) return false;
            if (q.sex.size > 0) return false;
            if (q.events.some(s => s.place || s.yearFrom != null || s.yearTo != null)) return false;
            if (q.family.some(s => s.name)) return false;
            return true;
        }

        let countTimer = null;
        function updateCount() {
            clearTimeout(countTimer);
            countTimer = setTimeout(() => {
                const q = readQuery();
                if (isQueryEmpty(q)) { searchBtn.textContent = 'Search'; return; }
                const count = runAdvancedSearch(q, ALL_PEOPLE, ctx).length;
                searchBtn.textContent = `Search · ${count} match${count === 1 ? '' : 'es'}`;
            }, 150);
        }
        [firstName, lastName].forEach(el => el.addEventListener('input', updateCount));
        [sexM, sexF].forEach(el => el.addEventListener('change', updateCount));

        // ── Run search and switch to results mode ──────────────────────
        function runAndShow() {
            const q = readQuery();
            if (isQueryEmpty(q)) return;
            currentCriteria = q;
            currentResults  = runAdvancedSearch(q, ALL_PEOPLE, ctx);
            currentPage     = 1;
            currentSort     = 'name';
            renderResultsMode();
            setMode('results');
        }
        searchBtn.addEventListener('click', runAndShow);

        pane.addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.tagName === 'INPUT' && body.getAttribute('data-mode') === 'form') {
                e.preventDefault();
                runAndShow();
            }
        });

        clearBtn.addEventListener('click', () => {
            firstName.value = '';
            lastName.value = '';
            sexM.checked = false;
            sexF.checked = false;
            evtSects.innerHTML = '';
            famSects.innerHTML = '';
            eventSections.length = 0;
            familySections.length = 0;
            evtPills.querySelectorAll('.adv-pill').forEach(p => p.classList.remove('disabled'));
            famPills.querySelectorAll('.adv-pill').forEach(p => p.classList.remove('disabled'));
            updateCount();
        });

        // ── Results-mode rendering ─────────────────────────────────────
        function renderResultsMode() {
            chipsEl.innerHTML    = buildFilterChipsHTML(currentCriteria);
            countbarEl.innerHTML = buildCountBarHTML(currentResults.length, currentSort);
            const sorted = sortResults(currentResults, currentSort);
            const slice  = paginate(sorted, currentPage, PER_PAGE);
            listEl.innerHTML  = buildResultRowsHTML(slice, { peopleById: PEOPLE, spousesOf: relIndex.spousesOf });
            pagerEl.innerHTML = buildPagerHTML(currentPage, currentResults.length, PER_PAGE);
            listEl.scrollTop = 0;
        }

        // Row click: re-root + open person panel.
        listEl.addEventListener('click', e => {
            const row = e.target.closest('.adv-row');
            if (!row) return;
            const xref = row.dataset.id;
            if (!xref) return;
            setState({ focusXref: xref, panelOpen: true, panelXref: xref });
        });

        // Pager click: prev / next / numbered.
        pagerEl.addEventListener('click', e => {
            const btn = e.target.closest('button[data-page]');
            if (!btn || btn.disabled) return;
            const p = btn.dataset.page;
            const pageCount = Math.ceil(currentResults.length / PER_PAGE);
            let next = currentPage;
            if (p === 'prev') next = Math.max(1, currentPage - 1);
            else if (p === 'next') next = Math.min(pageCount, currentPage + 1);
            else next = parseInt(p, 10);
            if (next !== currentPage && Number.isFinite(next)) {
                currentPage = next;
                renderResultsMode();
            }
        });

        // Sort change: re-render from page 1.
        countbarEl.addEventListener('change', e => {
            if (!e.target.classList.contains('adv-sort-select')) return;
            currentSort = e.target.value;
            currentPage = 1;
            renderResultsMode();
        });
    })();
}
```

- [ ] **Step 3: Run all JS tests to confirm no regressions**

Run: `npm test`
Expected: PASS — all viz_advanced_search.test.js and viz_advanced_results.test.js tests green; no new failures elsewhere.

- [ ] **Step 4: Commit**

```bash
git add js/viz_advanced_search.js
git commit -m "feat(adv-search): mode machine + paginated results rendering"
```

---

## Task 7: Manual browser verification

**Files:** None modified.

- [ ] **Step 1: Start the dev server**

```bash
python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```

- [ ] **Step 2: Walk the golden path**

In the browser (typically `http://localhost:8765`):

1. Click **Advanced ▾** in the header — pane opens to the form.
2. Type a last name like `Aliotti`, click **Search** — pane switches to results mode. Form is hidden. Chip bar shows `Last: Aliotti`. Count bar shows total. Result rows visible. Pager visible at bottom (if >25 matches).
3. Scroll the result list — it scrolls independently of the chip bar / count bar / pager.
4. Click a result row — pedigree re-roots on that person and the right-side person panel opens.
5. Click the filter-chip bar — pane switches back to form. Form values are still populated.
6. Change a field, click **Search** — results update, chip bar reflects the new criteria.
7. Change the sort dropdown from Name → Birth year — results re-sort, pager resets to page 1.
8. Click pager **2** (or `›`) — list updates with the next 25 results.
9. Click pager **1** (or `‹`) — list returns to first page.
10. Click **Clear** while in form mode — all fields reset.

- [ ] **Step 3: Try edge cases**

1. Search with a query that returns 0 matches — count bar shows "0 matches", list is empty, no pager.
2. Search with a query that returns 1 match — count bar shows "1 match" (singular).
3. Search with a query that returns ≤25 matches — no pager visible.
4. Search across multiple criteria (sex + event + family) — all chips appear in the filter bar.

- [ ] **Step 4: If any test fails, do NOT mark this task complete**

Diagnose, fix in the relevant earlier task's files, re-run npm test, re-verify manually.

- [ ] **Step 5: Commit any fixes (none if everything works)**

If you made follow-up fixes during verification, commit them with a clear `fix(adv-search):` message.

---

## Done

All seven tasks complete. The advanced-search pane now:

- Collapses the form after Search, freeing the full pane for results.
- Shows criteria as readable chips with one-click Edit.
- Renders denser one-line result rows with name + years + place + spouse/relationship.
- Paginates at 25 per page with prev/next/numbered buttons.
- Offers Name and Birth-year sort.
- Keeps the pedigree visible throughout.
