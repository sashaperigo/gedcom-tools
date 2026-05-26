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

if (typeof module !== 'undefined') {
    module.exports = { extractYear, buildRelIndex, eventSectionMatches };
}
