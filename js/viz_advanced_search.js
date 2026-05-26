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
        const pane    = document.getElementById('adv-search-pane');
        const toggle  = document.getElementById('advanced-search-toggle');
        const closeBt = document.getElementById('adv-pane-close');
        const evtPills   = document.getElementById('adv-event-pills');
        const evtSects   = document.getElementById('adv-event-sections');
        const famPills   = document.getElementById('adv-family-pills');
        const famSects   = document.getElementById('adv-family-sections');
        const searchBtn  = document.getElementById('adv-search-btn');
        const clearBtn   = document.getElementById('adv-clear-btn');
        const resultsEl  = document.getElementById('adv-results');
        const firstName  = document.getElementById('adv-first-name');
        const lastName   = document.getElementById('adv-last-name');
        const sexM       = document.getElementById('adv-sex-m');
        const sexF       = document.getElementById('adv-sex-f');

        // Build the relationship index once.
        const relIndex = buildRelIndex(FAMILIES, PARENTS);
        const ctx = { PARENTS, PEOPLE_BY_ID: PEOPLE, relIndex };

        const eventSections = [];
        const familySections = [];

        toggle.addEventListener('click', () => { pane.hidden = false; });
        closeBt.addEventListener('click', () => { pane.hidden = true; });

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
                sex,
                events,
                family,
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
                if (isQueryEmpty(q)) {
                    searchBtn.textContent = 'Search';
                    return;
                }
                const count = runAdvancedSearch(q, ALL_PEOPLE, ctx).length;
                searchBtn.textContent = `Search · ${count} match${count === 1 ? '' : 'es'}`;
            }, 150);
        }

        [firstName, lastName].forEach(el => el.addEventListener('input', updateCount));
        [sexM, sexF].forEach(el => el.addEventListener('change', updateCount));

        function runAndRender() {
            const q = readQuery();
            if (isQueryEmpty(q)) { resultsEl.innerHTML = ''; return; }
            const hits = runAdvancedSearch(q, ALL_PEOPLE, ctx);
            renderResults(hits, q);
        }
        searchBtn.addEventListener('click', runAndRender);

        pane.addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
                e.preventDefault();
                runAndRender();
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
            resultsEl.innerHTML = '';
            updateCount();
        });

        function renderResults(hits, q) {
            resultsEl.innerHTML = '';
            if (hits.length === 0) {
                resultsEl.innerHTML = '<div class="adv-hint" style="padding:10px">No matches.</div>';
                return;
            }
            for (const p of hits) {
                const full = PEOPLE[p.id] || p;
                const div = document.createElement('div');
                div.className = 'adv-result';
                div.dataset.id = p.id;
                const spouseXref = (relIndex.spousesOf[p.id] || [])[0];
                const spouseName = spouseXref ? (PEOPLE[spouseXref] && PEOPLE[spouseXref].name) : null;
                const birth = (full.events || []).find(e => e.tag === 'BIRT');
                const death = (full.events || []).find(e => e.tag === 'DEAT');
                const lines = [];
                if (birth) lines.push(['BORN', formatFact(birth)]);
                if (death) lines.push(['DIED', formatFact(death)]);
                if (spouseName) lines.push(['SPOUSE', spouseName]);
                div.innerHTML =
                    `<div class="adv-name">${escapeHtml(full.name || '?')}</div>` +
                    lines.map(([k,v]) => `<div class="adv-fact"><span class="adv-fact-label">${k}</span><span>${escapeHtml(v)}</span></div>`).join('');
                div.addEventListener('click', () => {
                    setState({ focusXref: p.id, panelOpen: true, panelXref: p.id });
                });
                resultsEl.appendChild(div);
            }
        }

        function formatFact(evt) {
            const y = extractYear(evt.date);
            const place = evt.place || '';
            if (y && place) return `${y} · ${place}`;
            if (y) return String(y);
            return place;
        }

        function escapeHtml(s) {
            return String(s == null ? '' : s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
    })();
}

if (typeof module !== 'undefined') {
    module.exports = { extractYear, buildRelIndex, eventSectionMatches, familySectionMatches, personMatchesAdvanced, runAdvancedSearch };
}
