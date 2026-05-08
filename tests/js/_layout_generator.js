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
    // Optional scenario template — biases the generator toward a specific
    // genealogical configuration. See SCENARIOS below for the list. When
    // unset (default), random tree generation is used.
    scenario: null,
};

// Each scenario builder is a function (ctx) → void that mutates the shared
// PEOPLE/PARENTS/CHILDREN/FAMILIES/RELATIVES globals via the `ctx` helpers and
// records the focus xref + expansion-set choices on `ctx.out`. Scenarios use
// `ctx.rand` (seeded) for variance in birth years and counts; same seed →
// identical output.
const SCENARIOS = {
    // Focus's aunt/uncle (a sibling of focus's parent) has expanded children.
    // Targets: ancestor-row sibling packing where the sibling has descendants
    // — the case _focusChildrenExtents does NOT cover.
    focus_parent_sibling_with_kids(ctx) {
        const { newPerson, newFamily, jitter, randInt } = ctx;
        const focus = newPerson(1900);
        ctx.out.focusXref = focus;

        const father = newPerson(1870);
        const mother = newPerson(1870);
        // Focus's aunt/uncle (sibling of father)
        const grandfather = newPerson(1840);
        const grandmother = newPerson(1840);
        const uncle = newPerson(jitter(1870));
        newFamily({ husb: grandfather, wife: grandmother, chil: [father, uncle] });
        // Focus's parents' marriage; mother gets her own parents to keep tree
        // shape balanced (optional siblings on father side already present).
        newFamily({ husb: father, wife: mother, chil: [focus] });
        // Uncle's kids
        const nKids = randInt(2, 3);
        const cousins = [];
        for (let i = 0; i < nKids; i++) {
            cousins.push(newPerson(jitter(1900)));
        }
        const uncleSpouse = newPerson(jitter(1870));
        newFamily({ husb: uncle, wife: uncleSpouse, chil: cousins });

        // Expansion: ancestors visible (focus's parents auto-render, but we
        // need father in expandedSiblingsXrefs to surface the uncle, and
        // uncle in expandedChildrenPersons to surface the cousins).
        ctx.out.expandedSiblingsXrefs.add(father);
        ctx.out.expandedChildrenPersons.add(uncle);
    },

    // Focus has a sibling whose own subtree is expanded two generations deep.
    // Targets: Phase 1 ↔ Phase 3 cascade where the sibling's subtree is
    // deeper than focus's.
    focus_sibling_with_grandkids(ctx) {
        const { newPerson, newFamily, jitter, randInt } = ctx;
        const father = newPerson(1870);
        const mother = newPerson(1870);
        const focus = newPerson(1900);
        const sibling = newPerson(jitter(1900));
        ctx.out.focusXref = focus;
        newFamily({ husb: father, wife: mother, chil: [focus, sibling] });

        // Sibling's family
        const sibSpouse = newPerson(jitter(1900));
        const niece = newPerson(jitter(1925));
        // Optional second niece for variance
        const niece2 = randInt(0, 1) ? newPerson(jitter(1925)) : null;
        const sibKids = niece2 ? [niece, niece2] : [niece];
        newFamily({ husb: sibling, wife: sibSpouse, chil: sibKids });

        // Niece's family (focus's expanded grand-niece/nephew)
        const nieceSpouse = newPerson(jitter(1925));
        const grandKids = [];
        for (let i = 0; i < randInt(1, 2); i++) {
            grandKids.push(newPerson(jitter(1950)));
        }
        newFamily({ husb: niece, wife: nieceSpouse, chil: grandKids });

        ctx.out.expandedChildrenPersons.add(sibling);
        ctx.out.expandedChildrenPersons.add(niece);
    },

    // Two adjacent focus-row siblings each have expanded kids.
    // Targets: Phase 1 sibling packing where adjacent sibling clusters must
    // not collide.
    adjacent_siblings_both_expanded(ctx) {
        const { newPerson, newFamily, jitter, randInt } = ctx;
        const father = newPerson(1870);
        const mother = newPerson(1870);
        const sib1 = newPerson(jitter(1898));
        const focus = newPerson(1900);
        const sib2 = newPerson(jitter(1902));
        ctx.out.focusXref = focus;
        newFamily({ husb: father, wife: mother, chil: [sib1, focus, sib2] });

        for (const sib of [sib1, sib2]) {
            const spouse = newPerson(jitter(1900));
            const nKids = randInt(2, 3);
            const kids = [];
            for (let i = 0; i < nKids; i++) {
                kids.push(newPerson(jitter(1925)));
            }
            newFamily({ husb: sib, wife: spouse, chil: kids });
            ctx.out.expandedChildrenPersons.add(sib);
        }
    },

    // Focus has its own expanded children (gen 1), and focus's uncle has
    // expanded children (cousins at gen 0) who themselves have expanded kids
    // (cousins-once-removed at gen 1). Both clusters land at y=ROW_HEIGHT.
    // Targets: row-1 collision between focus's descendant subtree and an
    // ancestor-sibling's descendant subtree — the case where Phase 2's
    // advanceFor fix and _focusChildrenExtents do not jointly cover the
    // ancestor side.
    focus_uncle_grandkids_vs_focus_kids(ctx) {
        const { newPerson, newFamily, jitter, randInt } = ctx;
        const ggFather = newPerson(1840);
        const ggMother = newPerson(1840);
        const grandfather = newPerson(jitter(1870));
        const uncle = newPerson(jitter(1870));
        newFamily({ husb: ggFather, wife: ggMother, chil: [grandfather, uncle] });

        const grandmother = newPerson(jitter(1870));
        const father = newPerson(jitter(1898));
        newFamily({ husb: grandfather, wife: grandmother, chil: [father] });

        const mother = newPerson(jitter(1898));
        const focus = newPerson(1900);
        newFamily({ husb: father, wife: mother, chil: [focus] });
        ctx.out.focusXref = focus;

        // Focus's children
        const focusSpouse = newPerson(jitter(1900));
        const focusKids = [];
        for (let i = 0; i < randInt(2, 3); i++) focusKids.push(newPerson(jitter(1925)));
        newFamily({ husb: focus, wife: focusSpouse, chil: focusKids });

        // Uncle's children (cousins) — same row as focus
        const uncleSpouse = newPerson(jitter(1870));
        const cousins = [];
        for (let i = 0; i < randInt(2, 3); i++) cousins.push(newPerson(jitter(1900)));
        newFamily({ husb: uncle, wife: uncleSpouse, chil: cousins });

        // Each cousin has children (cousins once removed) — same row as focusKids
        for (const cousin of cousins) {
            const cs = newPerson(jitter(1900));
            const cKids = [];
            for (let i = 0; i < randInt(1, 2); i++) cKids.push(newPerson(jitter(1925)));
            newFamily({ husb: cousin, wife: cs, chil: cKids });
            ctx.out.expandedChildrenPersons.add(cousin);
        }

        ctx.out.expandedAncestors.add(father);
        ctx.out.expandedAncestors.add(grandfather);
        ctx.out.expandedSiblingsXrefs.add(grandfather);
        ctx.out.expandedChildrenPersons.add(uncle);
    },

    // Grandparent (gen 2) has expanded siblings, one of whom has expanded
    // children. Targets: ancestor-side descendant clusters in deep rows.
    multi_gen_ancestor_siblings(ctx) {
        const { newPerson, newFamily, jitter, randInt } = ctx;
        const focus = newPerson(1900);
        ctx.out.focusXref = focus;

        const father = newPerson(1870);
        const mother = newPerson(1870);
        newFamily({ husb: father, wife: mother, chil: [focus] });

        // Grandfather + his great-aunt sibling
        const grandfather = newPerson(1840);
        const grandmother = newPerson(1840);
        const greatAunt = newPerson(jitter(1840));
        const ggFather = newPerson(1810);
        const ggMother = newPerson(1810);
        newFamily({ husb: ggFather, wife: ggMother, chil: [grandfather, greatAunt] });
        newFamily({ husb: grandfather, wife: grandmother, chil: [father] });

        // Great-aunt's kids (focus's first cousins once removed)
        const gaSpouse = newPerson(jitter(1840));
        const greatCousins = [];
        for (let i = 0; i < randInt(1, 2); i++) {
            greatCousins.push(newPerson(jitter(1870)));
        }
        newFamily({ husb: gaSpouse, wife: greatAunt, chil: greatCousins });

        ctx.out.expandedAncestors.add(father);
        ctx.out.expandedAncestors.add(grandfather);
        ctx.out.expandedSiblingsXrefs.add(grandfather);
        ctx.out.expandedChildrenPersons.add(greatAunt);
    },
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

    // Scenario branch: build a deterministic configuration biased toward a
    // specific bug class. Bypasses the random tree builder entirely.
    if (o.scenario) {
        const builder = SCENARIOS[o.scenario];
        if (!builder) throw new Error(`Unknown scenario: ${o.scenario}`);
        const out = {
            focusXref: null,
            expandedAncestors: new Set(),
            expandedChildrenPersons: new Set(),
            expandedSiblingsXrefs: new Set(),
        };
        builder({
            rand, randInt, randChance,
            newPerson, newFamily, jitter,
            out,
        });
        if (!out.focusXref) throw new Error(`Scenario ${o.scenario} did not set focusXref`);
        return {
            globals: { PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES },
            focusXref: out.focusXref,
            expandedAncestors: out.expandedAncestors,
            expandedChildrenPersons: out.expandedChildrenPersons,
            expandedSiblingsXrefs: out.expandedSiblingsXrefs,
        };
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
