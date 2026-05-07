// Greedy single-pass shrinker for failing layout inputs.
//
// shrink(input, fails) tries removing one thing at a time and keeps the
// removal if `fails(reduced)` still returns true. Iterates until a full pass
// finds no further removable element.
//
// Removable: any non-focus person, any expansion-set entry, any spouse link.
//
// Returns the minimal still-failing input.

function deepCopyInput(input) {
    return {
        globals: {
            PEOPLE: { ...input.globals.PEOPLE },
            PARENTS: Object.fromEntries(
                Object.entries(input.globals.PARENTS).map(([k, v]) => [k, [...v]])
            ),
            CHILDREN: Object.fromEntries(
                Object.entries(input.globals.CHILDREN).map(([k, v]) => [k, [...v]])
            ),
            RELATIVES: Object.fromEntries(
                Object.entries(input.globals.RELATIVES).map(([k, v]) => [k, {
                    siblings: [...v.siblings],
                    spouses: [...v.spouses],
                }])
            ),
            FAMILIES: Object.fromEntries(
                Object.entries(input.globals.FAMILIES).map(([k, v]) => [k, {
                    husb: v.husb,
                    wife: v.wife,
                    chil: [...(v.chil || [])],
                }])
            ),
        },
        focusXref: input.focusXref,
        expandedAncestors: new Set(input.expandedAncestors),
        expandedChildrenPersons: new Set(input.expandedChildrenPersons),
        expandedSiblingsXrefs: new Set(input.expandedSiblingsXrefs),
    };
}

// Remove a person (and all references) from `input`. Returns a new input.
function withPersonRemoved(input, xref) {
    const out = deepCopyInput(input);
    delete out.globals.PEOPLE[xref];
    delete out.globals.PARENTS[xref];
    delete out.globals.CHILDREN[xref];
    delete out.globals.RELATIVES[xref];
    out.expandedAncestors.delete(xref);
    out.expandedChildrenPersons.delete(xref);
    out.expandedSiblingsXrefs.delete(xref);
    // Strip references in remaining people
    for (const [k, parents] of Object.entries(out.globals.PARENTS)) {
        out.globals.PARENTS[k] = parents.filter(p => p !== xref);
    }
    for (const [k, children] of Object.entries(out.globals.CHILDREN)) {
        out.globals.CHILDREN[k] = children.filter(c => c !== xref);
    }
    for (const rel of Object.values(out.globals.RELATIVES)) {
        rel.siblings = rel.siblings.filter(s => s !== xref);
        rel.spouses = rel.spouses.filter(s => s !== xref);
    }
    // Strip from FAMILIES
    for (const [fkey, fam] of Object.entries(out.globals.FAMILIES)) {
        if (fam.husb === xref) fam.husb = null;
        if (fam.wife === xref) fam.wife = null;
        fam.chil = (fam.chil || []).filter(c => c !== xref);
        // Drop empty family
        if (!fam.husb && !fam.wife && fam.chil.length === 0) {
            delete out.globals.FAMILIES[fkey];
        }
    }
    return out;
}

function withExpansionRemoved(input, setName, xref) {
    const out = deepCopyInput(input);
    out[setName].delete(xref);
    return out;
}

// Greedy shrink. fails(input) → boolean. Returns minimal still-failing input.
function shrink(input, fails, opts = {}) {
    const maxPasses = opts.maxPasses ?? 5;
    let current = input;
    for (let pass = 0; pass < maxPasses; pass++) {
        let progressed = false;

        // Try removing each non-focus person
        for (const xref of Object.keys(current.globals.PEOPLE)) {
            if (xref === current.focusXref) continue;
            const reduced = withPersonRemoved(current, xref);
            if (fails(reduced)) {
                current = reduced;
                progressed = true;
            }
        }

        // Try removing entries from each expansion set
        for (const setName of ['expandedAncestors', 'expandedChildrenPersons', 'expandedSiblingsXrefs']) {
            for (const xref of [...current[setName]]) {
                const reduced = withExpansionRemoved(current, setName, xref);
                if (fails(reduced)) {
                    current = reduced;
                    progressed = true;
                }
            }
        }

        if (!progressed) break;
    }
    return current;
}

// Pretty-print a (minimal) input for paste-into-regression-test use.
function formatInput(input) {
    const g = input.globals;
    const lines = [];
    lines.push('  PEOPLE:');
    for (const [x, p] of Object.entries(g.PEOPLE)) {
        lines.push(`    ${x}: { birth_year: ${p.birth_year} }`);
    }
    lines.push('  FAMILIES:');
    for (const [f, fam] of Object.entries(g.FAMILIES)) {
        lines.push(`    ${f}: husb=${fam.husb} wife=${fam.wife} chil=[${(fam.chil || []).join(',')}]`);
    }
    lines.push('  PARENTS:');
    for (const [c, ps] of Object.entries(g.PARENTS)) {
        if (ps.length) lines.push(`    ${c}: [${ps.join(',')}]`);
    }
    lines.push(`  focus=${input.focusXref}`);
    lines.push(`  expandedAncestors={${[...input.expandedAncestors].join(',')}}`);
    lines.push(`  expandedChildrenPersons={${[...input.expandedChildrenPersons].join(',')}}`);
    lines.push(`  expandedSiblingsXrefs={${[...input.expandedSiblingsXrefs].join(',')}}`);
    return lines.join('\n');
}

module.exports = {
    shrink,
    formatInput,
    withPersonRemoved,
    withExpansionRemoved,
    deepCopyInput,
};
