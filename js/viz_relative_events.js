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
