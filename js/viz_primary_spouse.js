// Resolves the "primary" FAM to display for a person with multiple marriages.
//
// Tiebreaker order:
//   1. Lineage: if personXref is a direct ancestor of focusXref and exactly
//      one of their FAMs has the lineage child, pick that FAM.
//   2. Earliest marr_year.
//   3. Earliest other-parent birth_year (null → Infinity).
//   4. Numeric FAM-xref order.

function _famsFor(personXref) {
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return [];
    return Object.keys(FAMILIES).filter(f =>
        FAMILIES[f].husb === personXref || FAMILIES[f].wife === personXref
    );
}

function _otherParent(famXref, personXref) {
    const fam = FAMILIES[famXref];
    if (!fam) return null;
    if (fam.husb === personXref) return fam.wife;
    if (fam.wife === personXref) return fam.husb;
    return null;
}

function _famXrefNumeric(famXref) {
    const m = /^@F(\d+)@$/.exec(famXref);
    return m ? Number(m[1]) : Infinity;
}

function _lineageChildInFam(famXref, personXref, focusXref) {
    // Walk PARENTS from focusXref upward. If we hit a child whose parents
    // include personXref AND that child is in FAMILIES[famXref].chil, this FAM
    // is the lineage FAM.
    if (typeof PARENTS === 'undefined' || !PARENTS) return false;
    const fam = FAMILIES[famXref];
    if (!fam) return false;
    const chilSet = new Set(fam.chil || []);
    let cursor = focusXref;
    const visited = new Set();
    while (cursor && !visited.has(cursor)) {
        visited.add(cursor);
        const ps = PARENTS[cursor] || [];
        if (ps.includes(personXref)) {
            if (chilSet.has(cursor)) return true;
        }
        // Walk up via either parent that descends from personXref
        const next = ps.find(p => p && _isAncestorOf(personXref, p));
        cursor = next || null;
    }
    return false;
}

function _isAncestorOf(ancestorXref, descendantXref) {
    if (!ancestorXref || !descendantXref) return false;
    if (ancestorXref === descendantXref) return true;
    if (typeof PARENTS === 'undefined' || !PARENTS) return false;
    const visited = new Set();
    const stack = [descendantXref];
    while (stack.length) {
        const cur = stack.pop();
        if (visited.has(cur)) continue;
        visited.add(cur);
        const ps = PARENTS[cur] || [];
        for (const p of ps) {
            if (!p) continue;
            if (p === ancestorXref) return true;
            stack.push(p);
        }
    }
    return false;
}

function primaryFamFor(personXref, focusXref) {
    const fams = _famsFor(personXref);
    if (fams.length === 0) return null;
    if (fams.length === 1) return fams[0];

    // Rule 1: lineage
    const lineage = fams.filter(f => _lineageChildInFam(f, personXref, focusXref));
    if (lineage.length === 1) return lineage[0];

    // Rules 2–4: sort on composite key
    const scored = fams.map(f => {
        const fam = FAMILIES[f];
        const my = fam.marr_year == null ? Infinity : fam.marr_year;
        const otherXref = _otherParent(f, personXref);
        const oBy = (otherXref && typeof PEOPLE !== 'undefined' && PEOPLE[otherXref] &&
            PEOPLE[otherXref].birth_year != null) ?
            Number(PEOPLE[otherXref].birth_year) :
            Infinity;
        return { f, my, oBy, num: _famXrefNumeric(f) };
    });
    scored.sort((a, b) => a.my - b.my || a.oBy - b.oBy || a.num - b.num);
    return scored[0].f;
}

if (typeof module !== 'undefined') module.exports = {
    primaryFamFor,
    _famsFor,
    _otherParent,
};
