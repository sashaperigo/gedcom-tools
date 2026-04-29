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

if (typeof module !== 'undefined') module.exports = {
    _role,
    _yearNum,
    _lifetimeBounds,
    buildRelativeEvents,
};
