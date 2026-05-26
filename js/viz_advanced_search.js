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

if (typeof module !== 'undefined') {
    module.exports = { extractYear, buildRelIndex, eventSectionMatches, familySectionMatches, personMatchesAdvanced, runAdvancedSearch };
}
