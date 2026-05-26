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

if (typeof module !== 'undefined') {
    module.exports = { extractYear, buildRelIndex };
}
