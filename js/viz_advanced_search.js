// Advanced search — pure filter logic + DOM controller.
// Pure functions exported for tests; DOM IIFE (later tasks) runs only in browsers.

function extractYear(dateStr) {
    if (!dateStr) return null;
    const m = String(dateStr).match(/\b(\d{4})\b/);
    return m ? parseInt(m[1], 10) : null;
}

// Build {spousesOf, childrenOf, siblingsOf} from FAMILIES + PARENTS.
// Siblings share the same FAMC (full siblings only); half-siblings excluded.
function buildRelIndex(FAMILIES, PARENTS) {
    const spousesOf = {};   // person xref -> [spouse xref, ...]
    const childrenOf = {};  // person xref -> [child xref, ...]
    const famcOf = {};      // person xref -> FAMC xref (their family-as-child)

    const add = (map, key, value) => {
        if (!key || !value) return;
        (map[key] = map[key] || []).push(value);
    };

    for (const [famXref, fam] of Object.entries(FAMILIES || {})) {
        const h = fam.husb, w = fam.wife;
        if (h && w) { add(spousesOf, h, w); add(spousesOf, w, h); }
        for (const c of (fam.chil || [])) {
            if (h) add(childrenOf, h, c);
            if (w) add(childrenOf, w, c);
            famcOf[c] = famXref;
        }
    }

    // Siblings: those sharing the same FAMC, minus self.
    const famcMembers = {};  // FAMC xref -> [child xref, ...]
    for (const [child, famXref] of Object.entries(famcOf)) {
        (famcMembers[famXref] = famcMembers[famXref] || []).push(child);
    }
    const siblingsOf = {};
    for (const [famXref, members] of Object.entries(famcMembers)) {
        for (const m of members) {
            siblingsOf[m] = members.filter(x => x !== m);
        }
    }

    return { spousesOf, childrenOf, siblingsOf };
}

const _nm = (typeof require !== 'undefined')
    ? require('./viz_name_match.js')
    : { normSearch };
const _normSearch = _nm.normSearch;

const _hu = (typeof require !== 'undefined')
    ? require('./viz_html_utils.js')
    : { escapeHtml };
const escapeHtml = _hu.escapeHtml;

const _SECTION_TAGS = {
    birth: ['BIRT'],
    death: ['DEAT'],
    marriage: ['MARR'],
    residence: ['RESI'],
    any: null,  // null = any tag
};

function _placeMatches(eventPlace, query) {
    if (!query) return true;
    if (!eventPlace) return false;
    return _normSearch(eventPlace).includes(_normSearch(query));
}

function _yearInRange(eventDate, yearFrom, yearTo) {
    if (yearFrom == null && yearTo == null) return true;
    const y = extractYear(eventDate);
    if (y == null) return false;
    if (yearFrom != null && y < yearFrom) return false;
    if (yearTo != null && y > yearTo) return false;
    return true;
}

function _sectionIsEmpty(section) {
    return !section.place && section.yearFrom == null && section.yearTo == null;
}

function eventSectionMatches(person, section) {
    if (_sectionIsEmpty(section)) return true;
    const tags = _SECTION_TAGS[section.kind];
    const events = (person.events || []).filter(e => tags === null || tags.includes(e.tag));
    if (events.length === 0) return false;
    return events.some(e =>
        _placeMatches(e.place, section.place) && _yearInRange(e.date, section.yearFrom, section.yearTo)
    );
}

const _nm2 = (typeof require !== 'undefined')
    ? require('./viz_name_match.js')
    : { nameMatches };
const _nameMatches = _nm2.nameMatches;

function _lookup(ctx, xref) {
    if (!xref) return null;
    return (ctx.PEOPLE_BY_ID || {})[xref] || null;
}

function familySectionMatches(person, section, ctx) {
    if (!section.name) return true;
    const q = section.name;
    if (section.kind === 'spouse') {
        const spouses = (ctx.relIndex.spousesOf[person.id] || []);
        return spouses.some(x => _nameMatches(_lookup(ctx, x), q));
    }
    if (section.kind === 'father') {
        const f = (ctx.PARENTS[person.id] || {}).father;
        return _nameMatches(_lookup(ctx, f), q);
    }
    if (section.kind === 'mother') {
        const m = (ctx.PARENTS[person.id] || {}).mother;
        return _nameMatches(_lookup(ctx, m), q);
    }
    if (section.kind === 'other') {
        const all = [];
        const parents = ctx.PARENTS[person.id] || {};
        if (parents.father) all.push(parents.father);
        if (parents.mother) all.push(parents.mother);
        all.push(...(ctx.relIndex.spousesOf[person.id] || []));
        all.push(...(ctx.relIndex.childrenOf[person.id] || []));
        all.push(...(ctx.relIndex.siblingsOf[person.id] || []));
        return all.some(x => _nameMatches(_lookup(ctx, x), q));
    }
    return false;
}

const _nm3 = (typeof require !== 'undefined')
    ? require('./viz_name_match.js')
    : { getParsed, normSearch };
const _getParsed = _nm3.getParsed;
const _normSearch3 = _nm3.normSearch;

function personMatchesAdvanced(person, query, ctx) {
    // Name
    const parsed = _getParsed(person);
    if (query.firstName) {
        const q = _normSearch3(query.firstName);
        if (!parsed.normFirst.startsWith(q) &&
            !parsed.normNicks.some(n => n.startsWith(q)) &&
            !parsed.normDisp.includes(q)) return false;
    }
    if (query.lastName) {
        const q = _normSearch3(query.lastName);
        if (!parsed.normLast.includes(q) && !parsed.normDisp.includes(q)) return false;
    }
    // Sex
    if (query.sex && query.sex.size > 0) {
        if (!query.sex.has(person.sex)) return false;
    }
    // Events: full person record from PEOPLE_BY_ID has the events array
    const full = (ctx.PEOPLE_BY_ID && ctx.PEOPLE_BY_ID[person.id]) || person;
    for (const sec of (query.events || [])) {
        if (!eventSectionMatches(full, sec)) return false;
    }
    // Family
    for (const sec of (query.family || [])) {
        if (!familySectionMatches(person, sec, ctx)) return false;
    }
    return true;
}

function runAdvancedSearch(query, allPeople, ctx) {
    const hits = allPeople.filter(p => personMatchesAdvanced(p, query, ctx));
    // Sort: last name, birth year asc, first name.
    return hits.sort((a, b) => {
        const pa = _getParsed(a), pb = _getParsed(b);
        if (pa.normLast !== pb.normLast) return pa.normLast < pb.normLast ? -1 : 1;
        const ya = a.birth_year || Infinity, yb = b.birth_year || Infinity;
        if (ya !== yb) return ya - yb;
        if (pa.normFirst !== pb.normFirst) return pa.normFirst < pb.normFirst ? -1 : 1;
        return 0;
    });
}

// ───────────────────────────────────────────────────────────────────────
// DOM controller (browser only) — exercised manually, not via tests.
// ───────────────────────────────────────────────────────────────────────

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

if (typeof module !== 'undefined') {
    module.exports = { extractYear, buildRelIndex, eventSectionMatches, familySectionMatches, personMatchesAdvanced, runAdvancedSearch };
}
