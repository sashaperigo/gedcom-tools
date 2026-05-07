// Random GED-shaped input generator for property-based layout tests.
//
// generateLayoutInput(seed, options) → {
//   globals: { PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES },
//   focusXref,
//   expandedAncestors: Set,
//   expandedChildrenPersons: Set,
//   expandedSiblingsXrefs: Set,
// }
//
// Same seed → same output. Output is internally consistent: every parent
// referenced exists, PARENTS/CHILDREN are bidirectional, every FAM's members
// are in PEOPLE, RELATIVES.siblings reflects shared parents, RELATIVES.spouses
// reflects FAM membership.

function mulberry32(seed) {
    let s = seed >>> 0;
    return function () {
        s = (s + 0x6D2B79F5) >>> 0;
        let t = s;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

const DEFAULT_OPTIONS = {
    maxAncestorGenerations: 2,    // up from focus
    maxDescendantGenerations: 2,  // down from focus
    maxSiblingsPerCouple: 3,
    maxChildrenPerCouple: 3,
    pSecondMarriage: 0.2,
    pOnRowSpouse: 0.6,
    pSiblingHasOwnKids: 0.4,
    pExpandAncestor: 0.5,
    pExpandChild: 0.5,
    pExpandSibling: 0.5,
    maxTotalPersons: 30,
};

function generateLayoutInput(seed, opts = {}) {
    const o = { ...DEFAULT_OPTIONS, ...opts };
    const rand = mulberry32(seed);
    const randInt = (lo, hi) => lo + Math.floor(rand() * (hi - lo + 1));
    const randChance = (p) => rand() < p;

    const PEOPLE = {};
    const PARENTS = {};
    const CHILDREN = {};
    const FAMILIES = {};
    const RELATIVES = {};

    let nextPersonId = 1;
    let nextFamId = 1;

    function newPerson(birthYear) {
        if (Object.keys(PEOPLE).length >= o.maxTotalPersons) return null;
        const xref = `@I${nextPersonId++}@`;
        PEOPLE[xref] = { birth_year: birthYear };
        RELATIVES[xref] = { siblings: [], spouses: [] };
        return xref;
    }

    function newFamily({ husb, wife, chil = [] }) {
        const xref = `@F${nextFamId++}@`;
        FAMILIES[xref] = { husb, wife, chil: [...chil] };
        // Wire RELATIVES.spouses
        if (husb && wife) {
            if (!RELATIVES[husb].spouses.includes(wife)) RELATIVES[husb].spouses.push(wife);
            if (!RELATIVES[wife].spouses.includes(husb)) RELATIVES[wife].spouses.push(husb);
        }
        // Wire PARENTS / CHILDREN for each child
        for (const c of chil) {
            for (const parent of [husb, wife].filter(Boolean)) {
                PARENTS[c] = PARENTS[c] || [];
                if (!PARENTS[c].includes(parent)) PARENTS[c].push(parent);
                CHILDREN[parent] = CHILDREN[parent] || [];
                if (!CHILDREN[parent].includes(c)) CHILDREN[parent].push(c);
            }
        }
        // Wire RELATIVES.siblings (everyone in chil shares parents → siblings of each other)
        for (const a of chil) {
            for (const b of chil) {
                if (a === b) continue;
                if (!RELATIVES[a].siblings.includes(b)) RELATIVES[a].siblings.push(b);
            }
        }
        return xref;
    }

    function jitter(year) {
        return year + randInt(-3, 3);
    }

    // Build descendant subtree rooted at `personXref`. Returns nothing; mutates globals.
    function buildDescendants(personXref, generation, baseBirthYear) {
        if (generation > o.maxDescendantGenerations) return;
        if (Object.keys(PEOPLE).length >= o.maxTotalPersons) return;
        // Maybe a spouse
        let spouseXref = null;
        if (randChance(o.pOnRowSpouse)) {
            spouseXref = newPerson(jitter(baseBirthYear));
            if (!spouseXref) return;
        }
        // Number of children in this primary FAM
        const nChildren = randInt(0, o.maxChildrenPerCouple);
        if (nChildren === 0 && !spouseXref) return;
        const childXrefs = [];
        const childBaseYear = baseBirthYear + 30;
        for (let i = 0; i < nChildren; i++) {
            const c = newPerson(jitter(childBaseYear));
            if (!c) break;
            childXrefs.push(c);
        }
        if (childXrefs.length > 0 || spouseXref) {
            // Husb/wife placement is arbitrary — just be consistent
            newFamily({ husb: personXref, wife: spouseXref, chil: childXrefs });
        }
        // Maybe a second marriage (different spouse, more children)
        if (randChance(o.pSecondMarriage)) {
            const spouse2 = newPerson(jitter(baseBirthYear));
            if (spouse2) {
                const nChil2 = randInt(1, o.maxChildrenPerCouple);
                const chil2 = [];
                for (let i = 0; i < nChil2; i++) {
                    const c = newPerson(jitter(childBaseYear));
                    if (!c) break;
                    chil2.push(c);
                }
                if (chil2.length > 0) newFamily({ husb: personXref, wife: spouse2, chil: chil2 });
            }
        }
        // Recurse into grandchildren
        for (const c of childXrefs) {
            buildDescendants(c, generation + 1, PEOPLE[c].birth_year);
        }
    }

    // Build ancestor subtree above `personXref`. Returns nothing; mutates globals.
    function buildAncestors(personXref, generation, baseBirthYear) {
        if (generation > o.maxAncestorGenerations) return;
        if (Object.keys(PEOPLE).length >= o.maxTotalPersons) return;
        const father = newPerson(baseBirthYear - 30 + randInt(-5, 5));
        const mother = newPerson(baseBirthYear - 30 + randInt(-5, 5));
        if (!father || !mother) return;
        // Couple has personXref as one of their children, plus 0-2 of personXref's siblings
        const siblings = [];
        const nSibs = randInt(0, o.maxSiblingsPerCouple);
        for (let i = 0; i < nSibs; i++) {
            const sib = newPerson(jitter(baseBirthYear));
            if (!sib) break;
            siblings.push(sib);
        }
        // Family with father/mother and [personXref + siblings]
        newFamily({ husb: father, wife: mother, chil: [personXref, ...siblings] });
        // Each sibling may have their own kids — triggers focus-row-sibling-with-kids bug class
        for (const sib of siblings) {
            if (randChance(o.pSiblingHasOwnKids)) {
                buildDescendants(sib, 1, PEOPLE[sib].birth_year);
            }
        }
        // Recurse upward on father and mother (their parents = grandparents)
        buildAncestors(father, generation + 1, PEOPLE[father].birth_year);
        buildAncestors(mother, generation + 1, PEOPLE[mother].birth_year);
    }

    // Generate focus + tree.
    const focusXref = newPerson(1900);
    buildAncestors(focusXref, 1, 1900);
    buildDescendants(focusXref, 1, 1900);

    // Pick expansion sets.
    const expandedAncestors = new Set();
    const expandedChildrenPersons = new Set();
    const expandedSiblingsXrefs = new Set();

    // Eligible-to-expand:
    //  - ancestors (anyone whose descendant chain leads to focus)
    //  - any person with children (could be expanded for child-display)
    //  - siblings (focus's own siblings, sib's spouses' siblings, ancestor siblings)
    const focusParentXrefs = PARENTS[focusXref] || [];
    const ancestorXrefs = collectAncestors(focusXref, PARENTS);
    const peopleWithChildren = Object.keys(PEOPLE).filter(x => (CHILDREN[x] || []).length > 0);
    const focusSiblings = RELATIVES[focusXref]?.siblings || [];

    for (const a of ancestorXrefs) {
        if (randChance(o.pExpandAncestor)) expandedAncestors.add(a);
    }
    for (const p of peopleWithChildren) {
        // Always-eligible: anyone except focus (focus's children show by default).
        if (p === focusXref) continue;
        if (randChance(o.pExpandChild)) expandedChildrenPersons.add(p);
    }
    // Sibling-expand only on ancestors (force-expand semantics) — focus's siblings show by default.
    for (const a of ancestorXrefs) {
        if (randChance(o.pExpandSibling)) expandedSiblingsXrefs.add(a);
    }
    // Focus's parents are always implicitly visible if any ancestor is in expandedAncestors;
    // tests don't need to explicitly add them.

    return {
        globals: { PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES },
        focusXref,
        expandedAncestors,
        expandedChildrenPersons,
        expandedSiblingsXrefs,
    };
}

function collectAncestors(focusXref, PARENTS) {
    const out = new Set();
    const stack = [focusXref];
    while (stack.length) {
        const cur = stack.pop();
        for (const p of PARENTS[cur] || []) {
            if (!out.has(p)) {
                out.add(p);
                stack.push(p);
            }
        }
    }
    return out;
}

// Internal-consistency validator. Returns null on success, or a string
// describing the first inconsistency found.
function validateInput(input) {
    const { globals: g } = input;
    for (const xref of Object.keys(g.PEOPLE)) {
        if (!g.RELATIVES[xref]) return `${xref} in PEOPLE but not RELATIVES`;
    }
    for (const [child, parents] of Object.entries(g.PARENTS)) {
        if (!g.PEOPLE[child]) return `PARENTS[${child}]: child not in PEOPLE`;
        for (const p of parents) {
            if (!g.PEOPLE[p]) return `PARENTS[${child}] references ${p} not in PEOPLE`;
            if (!(g.CHILDREN[p] || []).includes(child)) {
                return `PARENTS[${child}]→${p} but CHILDREN[${p}] missing ${child}`;
            }
        }
    }
    for (const [parent, children] of Object.entries(g.CHILDREN)) {
        if (!g.PEOPLE[parent]) return `CHILDREN[${parent}]: parent not in PEOPLE`;
        for (const c of children) {
            if (!g.PEOPLE[c]) return `CHILDREN[${parent}] references ${c} not in PEOPLE`;
            if (!(g.PARENTS[c] || []).includes(parent)) {
                return `CHILDREN[${parent}]→${c} but PARENTS[${c}] missing ${parent}`;
            }
        }
    }
    for (const [fxref, fam] of Object.entries(g.FAMILIES)) {
        if (fam.husb && !g.PEOPLE[fam.husb]) return `${fxref}.husb=${fam.husb} not in PEOPLE`;
        if (fam.wife && !g.PEOPLE[fam.wife]) return `${fxref}.wife=${fam.wife} not in PEOPLE`;
        for (const c of fam.chil || []) {
            if (!g.PEOPLE[c]) return `${fxref}.chil includes ${c} not in PEOPLE`;
        }
    }
    return null;
}

module.exports = {
    generateLayoutInput,
    validateInput,
    mulberry32,
    DEFAULT_OPTIONS,
};
