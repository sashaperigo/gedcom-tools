import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(
    import.meta.url);

// Inject DESIGN as a global so viz_layout.js can read it
const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;

const { NODE_W, NODE_W_FOCUS, NODE_H, NODE_H_FOCUS, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;
// Focus-to-sibling gap: accounts for focus node being wider than NODE_W.
const FOCUS_TO_SIB = NODE_W_FOCUS / 2 + H_GAP + NODE_W / 2;

const {
    computeLayout,
    _sortByBirthYear,
    _packRow,
    _rightContour,
    _leftContour,
    _requiredSeparation,
    _placeChildrenOfPerson,
} = require('../../js/viz_layout.js');
const SLOT = NODE_W + H_GAP;

// ── helpers ────────────────────────────────────────────────────────────────

function resetGlobals({ people = {}, parents = {}, children = {}, relatives = {}, families = {} } = {}) {
    global.PEOPLE = people;
    global.PARENTS = parents;
    global.CHILDREN = children;
    global.RELATIVES = relatives;
    global.FAMILIES = families;
}

// ── _sortByBirthYear ───────────────────────────────────────────────────────

describe('_sortByBirthYear', () => {
    it('sorts by birth_year ascending', () => {
        global.PEOPLE = {
            '@I1@': { birth_year: 1900 },
            '@I2@': { birth_year: 1880 },
            '@I3@': { birth_year: 1920 },
        };
        expect(_sortByBirthYear(['@I1@', '@I2@', '@I3@'])).toEqual(['@I2@', '@I1@', '@I3@']);
    });

    it('treats missing birth_year as 9999 (sorts last)', () => {
        global.PEOPLE = {
            '@I1@': { birth_year: 1900 },
            '@I2@': {},
        };
        expect(_sortByBirthYear(['@I1@', '@I2@'])).toEqual(['@I1@', '@I2@']);
    });
});

// ── _packRow ───────────────────────────────────────────────────────────────

describe('_packRow', () => {
    it('packs single item at x=0 with generation and role', () => {
        const items = [{ xref: '@I1@' }];
        const nodes = _packRow(items, 0, 0, 'focus');
        expect(nodes).toHaveLength(1);
        expect(nodes[0]).toMatchObject({ xref: '@I1@', x: 0, y: 0, generation: 0, role: 'focus' });
    });

    it('packs two items with NODE_W + H_GAP spacing', () => {
        const items = [{ xref: '@I1@' }, { xref: '@I2@' }];
        const nodes = _packRow(items, 0, 0, 'sibling');
        expect(nodes[0].x).toBe(0);
        expect(nodes[1].x).toBe(NODE_W + H_GAP);
    });
});

// ── computeLayout — shape ──────────────────────────────────────────────────

describe('computeLayout — return shape', () => {
    it('returns { nodes, edges }', () => {
        resetGlobals({ people: { '@I1@': { birth_year: 1900 } } });
        const result = computeLayout('@I1@', new Set(), new Set());
        expect(result).toHaveProperty('nodes');
        expect(result).toHaveProperty('edges');
        expect(Array.isArray(result.nodes)).toBe(true);
        expect(Array.isArray(result.edges)).toBe(true);
    });
});

// ── Test 1: Focus-only tree ────────────────────────────────────────────────

describe('computeLayout — focus-only tree', () => {
    beforeEach(() => {
        resetGlobals({ people: { '@I1@': { birth_year: 1900 } } });
    });

    it('has exactly one node', () => {
        const { nodes } = computeLayout('@I1@', new Set(), new Set());
        expect(nodes).toHaveLength(1);
    });

    it('focus node is at x=0, y=0, generation=0, role=focus', () => {
        const { nodes } = computeLayout('@I1@', new Set(), new Set());
        const focus = nodes.find(n => n.xref === '@I1@');
        expect(focus).toBeDefined();
        expect(focus.x).toBe(0);
        expect(focus.y).toBe(0);
        expect(focus.generation).toBe(0);
        expect(focus.role).toBe('focus');
    });
});

// ── Test 2: Focus with siblings (birth order) ─────────────────────────────

describe('computeLayout — focus with siblings', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@OLDER@': { birth_year: 1870 },
                '@FOCUS@': { birth_year: 1873 },
                '@YOUNGER@': { birth_year: 1876 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@OLDER@', '@YOUNGER@'], spouses: [] },
            },
        });
    });

    it('focus is at x=0', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const focus = nodes.find(n => n.xref === '@FOCUS@');
        expect(focus.x).toBe(0);
    });

    it('older sibling is at x = -FOCUS_TO_SIB (accounts for wider focus node)', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const older = nodes.find(n => n.xref === '@OLDER@');
        expect(older).toBeDefined();
        expect(older.x).toBe(-FOCUS_TO_SIB);
    });

    it('younger sibling is at x = +FOCUS_TO_SIB (accounts for wider focus node)', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const younger = nodes.find(n => n.xref === '@YOUNGER@');
        expect(younger).toBeDefined();
        expect(younger.x).toBe(FOCUS_TO_SIB);
    });

    it('all generation-0 nodes are at y=0', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        nodes.filter(n => n.generation === 0).forEach(n => {
            expect(n.y).toBe(0);
        });
    });
});

// ── Test 3: Focus with parents ─────────────────────────────────────────────

describe('computeLayout — focus with parents', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@FATHER@': { birth_year: 1870 },
                '@MOTHER@': { birth_year: 1872 },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
            },
        });
    });

    it('father is at x < 0, y = -ROW_HEIGHT', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const father = nodes.find(n => n.xref === '@FATHER@');
        expect(father).toBeDefined();
        expect(father.x).toBeLessThan(0);
        expect(father.y).toBe(-ROW_HEIGHT);
    });

    it('mother is at x > 0, y = -ROW_HEIGHT', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        expect(mother).toBeDefined();
        expect(mother.x).toBeGreaterThan(0);
        expect(mother.y).toBe(-ROW_HEIGHT);
    });

    it('parent nodes have generation = -1', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const parents = nodes.filter(n => n.generation === -1);
        expect(parents).toHaveLength(2);
    });

    it('edges include an ancestor edge for each parent', () => {
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const ancestorEdges = edges.filter(e => e.type === 'ancestor');
        expect(ancestorEdges.length).toBeGreaterThanOrEqual(2);
    });
});

// ── Test 4: Focus with children ────────────────────────────────────────────

describe('computeLayout — focus with children', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@C1@': { birth_year: 1925 },
                '@C2@': { birth_year: 1927 },
                '@C3@': { birth_year: 1929 },
            },
            children: {
                '@FOCUS@': ['@C1@', '@C2@', '@C3@'],
            },
        });
    });

    it('children are at y = +ROW_HEIGHT', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        ['@C1@', '@C2@', '@C3@'].forEach(xref => {
            const child = nodes.find(n => n.xref === xref);
            expect(child).toBeDefined();
            expect(child.y).toBe(ROW_HEIGHT);
        });
    });

    it('children have generation = +1', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const children = nodes.filter(n => n.generation === 1);
        expect(children).toHaveLength(3);
    });

    it('children are centered under the focus node center', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const focus = nodes.find(n => n.xref === '@FOCUS@');
        // Focus uses NODE_W_FOCUS; its true visual center is focus.x + NODE_W_FOCUS/2.
        const focusCenterX = focus.x + NODE_W_FOCUS / 2;
        const childXs = ['@C1@', '@C2@', '@C3@'].map(xref => {
            const n = nodes.find(c => c.xref === xref);
            return n.x + NODE_W / 2;
        });
        const centerX = (Math.min(...childXs) + Math.max(...childXs)) / 2;
        expect(centerX).toBeCloseTo(focusCenterX);
    });

    it('children are evenly spaced', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const childXs = ['@C1@', '@C2@', '@C3@']
            .map(xref => nodes.find(n => n.xref === xref).x)
            .sort((a, b) => a - b);
        const gap1 = childXs[1] - childXs[0];
        const gap2 = childXs[2] - childXs[1];
        expect(gap1).toBeCloseTo(gap2);
        expect(gap1).toBeCloseTo(NODE_W + H_GAP);
    });
});

// ── Test 5: Focus with spouse ──────────────────────────────────────────────

describe('computeLayout — focus with spouse', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE@': { birth_year: 1902 },
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] },
            },
        });
    });

    it('spouse is to the right of focus (no siblings)', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const focus = nodes.find(n => n.xref === '@FOCUS@');
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        expect(spouse).toBeDefined();
        expect(spouse.x).toBeGreaterThan(focus.x);
    });

    it('spouse is at x = NODE_W_FOCUS/2 + MARRIAGE_GAP + NODE_W/2 (no siblings)', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        // Focus at x=0 has width NODE_W_FOCUS; right edge = NODE_W_FOCUS/2.
        // Spouse center = right edge + MARRIAGE_GAP + NODE_W/2.
        expect(spouse.x).toBe(NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2);
    });

    it('spouse has role "spouse"', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        expect(spouse.role).toBe('spouse');
    });

    it('edges include a marriage edge', () => {
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const marriageEdges = edges.filter(e => e.type === 'marriage');
        expect(marriageEdges.length).toBeGreaterThanOrEqual(1);
    });

    it('marriage edge x1 is the right edge of the focus node (no siblings)', () => {
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const me = edges.find(e => e.type === 'marriage');
        // Focus at x=0 has width NODE_W_FOCUS; right edge center = NODE_W_FOCUS/2.
        expect(me.x1).toBe(NODE_W_FOCUS / 2);
    });
});

// ── Test 5c: Multi-spouse marriage edges ───────────────────────────────────

// ── Regression: left-spouse marriage edge must reach the focus node ─────────
//
// Bug: x2 was -NODE_W_FOCUS/2 = -58, but the focus node's left edge is at x=0.
// The edge ended 58 px before the focus, creating a tiny 10-px stub.
// Fix: use x2 = NODE_W_FOCUS/2 (mirrors the right-side formula) so the edge
// extends into the focus node and is visually covered by it — same pattern as
// the right-side edge which starts at NODE_W_FOCUS/2 (inside the focus).
describe('computeLayout — left-spouse marriage edge reaches focus node', () => {
    it('left-side marriage edge x2 is NODE_W_FOCUS/2 (not -NODE_W_FOCUS/2)', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SP1@': { birth_year: 1890 },
                '@SP2@': { birth_year: 1920 },
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: ['@SP1@', '@SP2@'] },
            },
            families: {
                '@F1@': { husb: '@FOCUS@', wife: '@SP1@', chil: [], marr_year: 1910 },
                '@F2@': { husb: '@FOCUS@', wife: '@SP2@', chil: [], marr_year: 1920 },
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set(['@F1@', '@F2@']));
        const leftSpouseNode = nodes.find(n => n.role === 'spouse' && n.x < 0);
        expect(leftSpouseNode).toBeDefined();
        const leftEdge = edges.find(e => e.type === 'marriage' && e.x1 === leftSpouseNode.x + NODE_W);
        expect(leftEdge).toBeDefined();
        // x2 must be NODE_W_FOCUS/2, NOT -NODE_W_FOCUS/2
        expect(leftEdge.x2).toBe(NODE_W_FOCUS / 2);
        // The edge must cross x=0 (the focus node's left edge), so it's visually connected
        expect(leftEdge.x2).toBeGreaterThan(0);
    });
});

describe('computeLayout — multi-spouse marriage edges', () => {
    it('with 2 spouses, one marriage edge on each side of focus', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE1@': { birth_year: 1901 },
                '@SPOUSE2@': { birth_year: 1920 },
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: ['@SPOUSE1@', '@SPOUSE2@'] },
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const sp1 = nodes.find(n => n.xref === '@SPOUSE1@');
        const sp2 = nodes.find(n => n.xref === '@SPOUSE2@');
        const marriageEdges = edges.filter(e => e.type === 'marriage');
        expect(marriageEdges).toHaveLength(2);
        // Right-side edge: focus right edge → sp1 (primary spouse stays on right)
        expect(marriageEdges[0].x1).toBe(NODE_W_FOCUS / 2);
        expect(marriageEdges[0].x2).toBe(sp1.x);
        expect(sp1.x).toBeGreaterThan(0);
        // Left-side edge: sp2 right edge → focus center (mirrors right side formula)
        expect(marriageEdges[1].x1).toBe(sp2.x + NODE_W);
        expect(marriageEdges[1].x2).toBe(NODE_W_FOCUS / 2);
        expect(sp2.x).toBeLessThan(0);
    });
});

// ── Test 5b: Spouse siblings expanded ─────────────────────────────────────

describe('computeLayout — spouse siblings expanded', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE@': { birth_year: 1902 },
                '@SS1@': { birth_year: 1895 },
                '@SS2@': { birth_year: 1898 },
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] },
                '@SPOUSE@': { siblings: ['@SS1@', '@SS2@'], spouses: [] },
            },
        });
    });

    it('spouse siblings appear to the right of the spouse', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        const ss1 = nodes.find(n => n.xref === '@SS1@');
        const ss2 = nodes.find(n => n.xref === '@SS2@');
        expect(ss1).toBeDefined();
        expect(ss2).toBeDefined();
        expect(ss1.x).toBeGreaterThan(spouse.x);
        expect(ss2.x).toBeGreaterThan(spouse.x);
    });

    it('first spouse sibling is exactly one SLOT to the right of the spouse', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        // spouse siblings sorted by birth_year; @SS1@ (1895) comes first
        const ss1 = nodes.find(n => n.xref === '@SS1@');
        expect(ss1.x).toBe(spouse.x + NODE_W + H_GAP);
    });

    it('spouse siblings have role "spouse_sibling"', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
        const spouseSibs = nodes.filter(n => n.role === 'spouse_sibling');
        expect(spouseSibs).toHaveLength(2);
    });

    it('spouse siblings do NOT appear when spouseSiblingsExpanded is false', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouseSibs = nodes.filter(n => n.role === 'spouse_sibling');
        expect(spouseSibs).toHaveLength(0);
    });
});

// ── A1 regression: sibling_bracket edges must never be emitted ────────────

describe('computeLayout — no sibling_bracket edges', () => {
    it('emits zero sibling_bracket edges when focus has siblings', () => {
        resetGlobals({
            people: {
                '@OLDER@': { birth_year: 1870 },
                '@FOCUS@': { birth_year: 1873 },
                '@YOUNGER@': { birth_year: 1876 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@OLDER@', '@YOUNGER@'], spouses: [] },
            },
        });
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
        expect(edges.filter(e => e.type === 'sibling_bracket').length).toBe(0);
    });
});

// ── A2: Spouse placed immediately after focus, before younger siblings ─────

describe('computeLayout — spouse before younger siblings', () => {
    it('spouse x is NODE_W_FOCUS/2 + MARRIAGE_GAP + NODE_W/2 even when focus has younger sibling', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@YOUNGER@': { birth_year: 1905 },
                '@SPOUSE@': { birth_year: 1902 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@YOUNGER@'], spouses: ['@SPOUSE@'] },
            },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        expect(spouse.x).toBe(NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2);
    });

    it('younger sibling x is greater than spouse x', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@YOUNGER@': { birth_year: 1905 },
                '@SPOUSE@': { birth_year: 1902 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@YOUNGER@'], spouses: ['@SPOUSE@'] },
            },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        const younger = nodes.find(n => n.xref === '@YOUNGER@');
        expect(younger.x).toBeGreaterThan(spouse.x);
    });

    it('with 2 spouses, second spouse is placed to the left of focus', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE1@': { birth_year: 1901 },
                '@SPOUSE2@': { birth_year: 1920 },
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: ['@SPOUSE1@', '@SPOUSE2@'] },
            },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const sp2 = nodes.find(n => n.xref === '@SPOUSE2@');
        const firstSpouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
        expect(sp2.x).toBe(-firstSpouseX);
    });
});

// ── Test 6: No overlap (6 siblings + spouse with 4 siblings expanded) ──────

describe('computeLayout — no overlap', () => {
    it('all nodes in generation 0 have distinct x values', () => {
        const sibs = ['@S1@', '@S2@', '@S3@', '@S4@', '@S5@', '@S6@'];
        const spouseSibs = ['@SS1@', '@SS2@', '@SS3@', '@SS4@'];
        const people = {
            '@FOCUS@': { birth_year: 1900 },
            '@SPOUSE@': { birth_year: 1901 },
            '@S1@': { birth_year: 1880 },
            '@S2@': { birth_year: 1882 },
            '@S3@': { birth_year: 1884 },
            '@S4@': { birth_year: 1903 },
            '@S5@': { birth_year: 1905 },
            '@S6@': { birth_year: 1907 },
            '@SS1@': { birth_year: 1890 },
            '@SS2@': { birth_year: 1892 },
            '@SS3@': { birth_year: 1894 },
            '@SS4@': { birth_year: 1910 },
        };
        const relatives = {
            '@FOCUS@': { siblings: sibs, spouses: ['@SPOUSE@'] },
            '@SPOUSE@': { siblings: spouseSibs, spouses: [] },
        };
        resetGlobals({ people, relatives });

        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
        const gen0 = nodes.filter(n => n.generation === 0);
        const xs = gen0.map(n => n.x);
        const uniqueXs = new Set(xs);
        expect(uniqueXs.size).toBe(xs.length);
    });
});

// ── Test 7: Grandparent expansion ─────────────────────────────────────────

describe('computeLayout — grandparent expansion', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@FATHER@': { birth_year: 1870 },
                '@MOTHER@': { birth_year: 1872 },
                '@GFF@': { birth_year: 1840 },
                '@GFM@': { birth_year: 1842 },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@FATHER@': ['@GFF@', '@GFM@'],
            },
        });
    });

    it('grandparents appear at y = -2 * ROW_HEIGHT when father is in expandedAncestors', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@']), new Set());
        const gff = nodes.find(n => n.xref === '@GFF@');
        const gfm = nodes.find(n => n.xref === '@GFM@');
        expect(gff).toBeDefined();
        expect(gfm).toBeDefined();
        expect(gff.y).toBe(-2 * ROW_HEIGHT);
        expect(gfm.y).toBe(-2 * ROW_HEIGHT);
    });

    it('grandparents do NOT appear when father is NOT in expandedAncestors', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const gff = nodes.find(n => n.xref === '@GFF@');
        expect(gff).toBeUndefined();
    });

    it('grandparent nodes have generation = -2', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@']), new Set());
        const grandparents = nodes.filter(n => n.generation === -2);
        expect(grandparents).toHaveLength(2);
    });
});

// ── Test 8: Only one parent ────────────────────────────────────────────────

describe('computeLayout — single parent', () => {
    // Parent center aligns with focus visual center (NODE_W_FOCUS/2 = 80);
    // so parent.x = 80 - NODE_W/2 = 10.
    const SINGLE_PARENT_X = NODE_W_FOCUS / 2 - NODE_W / 2;

    it('single mother is centered above focus (center at focus center)', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@MOTHER@': { birth_year: 1870 },
            },
            parents: { '@FOCUS@': [null, '@MOTHER@'] },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        expect(mother).toBeDefined();
        expect(mother.x).toBe(SINGLE_PARENT_X);
        expect(mother.y).toBe(-ROW_HEIGHT);
    });

    it('single father is centered above focus (center at focus center)', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@FATHER@': { birth_year: 1870 },
            },
            parents: { '@FOCUS@': ['@FATHER@', null] },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const father = nodes.find(n => n.xref === '@FATHER@');
        expect(father).toBeDefined();
        expect(father.x).toBe(SINGLE_PARENT_X);
        expect(father.y).toBe(-ROW_HEIGHT);
    });
});

// ── Test 9: Width-aware ancestor placement (no overlap when both parents expanded) ─

describe('computeLayout — width-aware ancestor placement', () => {
    const SLOT = NODE_W + H_GAP;

    // Tree mirrors the screenshot scenario:
    //   @FOCUS@ → [@FATHER@(unexpanded), @MOTHER@(expanded)]
    //   @MOTHER@ → [@MGF@(expanded), @MGM@(expanded)]
    //   @MGF@  → [@MGGF@, @MGGM@]   (leaf grandparents)
    //   @MGM@  → [@MMGF@, @MMGM@]   (leaf grandparents)
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1995 },
                '@FATHER@': { birth_year: 1963 },
                '@MOTHER@': { birth_year: 1963 },
                '@MGF@': { birth_year: 1926 },
                '@MGM@': { birth_year: 1941 },
                '@MGGF@': { birth_year: 1882 },
                '@MGGM@': { birth_year: 1895 },
                '@MMGF@': { birth_year: 1901 },
                '@MMGM@': { birth_year: 1909 },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@MOTHER@': ['@MGF@', '@MGM@'],
                '@MGF@': ['@MGGF@', '@MGGM@'],
                '@MGM@': ['@MMGF@', '@MMGM@'],
            },
        });
    });

    it('no two ancestor nodes at the same generation overlap', () => {
        const expanded = new Set(['@MOTHER@', '@MGF@', '@MGM@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const ancestorsByGen = {};
        for (const node of nodes) {
            if (node.role !== 'ancestor') continue;
            if (!ancestorsByGen[node.generation]) ancestorsByGen[node.generation] = [];
            ancestorsByGen[node.generation].push(node);
        }
        for (const genNodes of Object.values(ancestorsByGen)) {
            const sorted = genNodes.slice().sort((a, b) => a.x - b.x);
            for (let i = 1; i < sorted.length; i++) {
                const gap = sorted[i].x - sorted[i - 1].x;
                expect(gap).toBeGreaterThanOrEqual(SLOT);
            }
        }
    });

    it('parent pair midpoint aligns with child center when both parents expanded', () => {
        const expanded = new Set(['@MOTHER@', '@MGF@', '@MGM@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const nodeMap = new Map(nodes.map(n => [n.xref, n]));
        const mgf = nodeMap.get('@MGF@');
        const mgm = nodeMap.get('@MGM@');
        const mother = nodeMap.get('@MOTHER@');
        // Midpoint of MGF and MGM centers should equal MOTHER's center
        const midpoint = (mgf.x + NODE_W / 2 + mgm.x + NODE_W / 2) / 2;
        expect(midpoint).toBeCloseTo(mother.x + NODE_W / 2, 1);
    });

    it('gen-3 nodes are non-overlapping; within-family pairs use SLOT, between-family uses FAMILY_GAP', () => {
        const { FAMILY_GAP } = DESIGN;
        const expanded = new Set(['@MOTHER@', '@MGF@', '@MGM@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const gen3 = nodes.filter(n => n.generation === -3).sort((a, b) => a.x - b.x);
        expect(gen3).toHaveLength(4);
        // Pairs 0-1 and 2-3 are each a couple → SLOT spacing (NODE_W + H_GAP).
        expect(gen3[1].x - gen3[0].x).toBeCloseTo(SLOT, 1);
        expect(gen3[3].x - gen3[2].x).toBeCloseTo(SLOT, 1);
        // Pair 1-2 bridges two different family subtrees at depth ≥ 1 → NODE_W + FAMILY_GAP.
        expect(gen3[2].x - gen3[1].x).toBeCloseTo(NODE_W + FAMILY_GAP, 1);
    });

    it('unexpanded ancestor keeps symmetric ±SLOT/2 placement (backward compat)', () => {
        // Only @MOTHER@ expanded (neither of her parents is expanded)
        const expanded = new Set(['@MOTHER@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const mgf = nodes.find(n => n.xref === '@MGF@');
        const mgm = nodes.find(n => n.xref === '@MGM@');
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        expect(mgf.x).toBeCloseTo(mother.x - SLOT / 2, 1);
        expect(mgm.x).toBeCloseTo(mother.x + SLOT / 2, 1);
    });
});

// ── Test 10: Descendant umbrella layout ────────────────────────────────────

describe('computeLayout — descendant umbrella', () => {
    const UMBRELLA_Y = NODE_H + (ROW_HEIGHT - NODE_H) / 2;

    it('single child, no spouse, focus has spouse: anchor is focus↔spouse midpoint', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE@': { birth_year: 1902 },
                '@C1@': { birth_year: 1925 },
            },
            children: { '@FOCUS@': ['@C1@'] },
            relatives: { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] } },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

        const focusCenter = NODE_W_FOCUS / 2; // 80
        const spouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2; // 210 (left edge)
        const spouseCenter = spouseX + NODE_W / 2; // 280
        const anchorX = (focusCenter + spouseCenter) / 2; // 180

        const c1 = nodes.find(n => n.xref === '@C1@');
        expect(c1).toBeDefined();
        expect(c1.x + NODE_W / 2).toBeCloseTo(anchorX, 1);

        const descEdges = edges.filter(e => e.type === 'descendant');
        // Anchor drop: starts on the focus↔spouse marriage line (y = NODE_H/2)
        // so it meets the marriage line perpendicularly with no gap.
        const anchorDrop = descEdges.find(e =>
            e.x1 === anchorX && e.y1 === NODE_H / 2 && e.x2 === anchorX && e.y2 === UMBRELLA_Y
        );
        expect(anchorDrop).toBeDefined();
        // Per-child drop: (anchorX, umbrellaY) → (anchorX, ROW_HEIGHT)
        const childDrop = descEdges.find(e =>
            e.x1 === anchorX && e.y1 === UMBRELLA_Y && e.x2 === anchorX && e.y2 === ROW_HEIGHT
        );
        expect(childDrop).toBeDefined();
        // No crossbar at umbrellaY with distinct x1/x2
        const crossbar = descEdges.find(e =>
            e.y1 === UMBRELLA_Y && e.y2 === UMBRELLA_Y && e.x1 !== e.x2
        );
        expect(crossbar).toBeUndefined();
    });

    it('multiple children, none with spouses: umbrella spans leftmost→rightmost child centers', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@C1@': { birth_year: 1925 },
                '@C2@': { birth_year: 1927 },
                '@C3@': { birth_year: 1929 },
            },
            children: { '@FOCUS@': ['@C1@', '@C2@', '@C3@'] },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const anchorX = NODE_W_FOCUS / 2; // no focus-spouse → focus center

        const centers = ['@C1@', '@C2@', '@C3@']
            .map(x => nodes.find(n => n.xref === x).x + NODE_W / 2)
            .sort((a, b) => a - b);
        const leftmost = centers[0];
        const rightmost = centers[centers.length - 1];

        const descEdges = edges.filter(e => e.type === 'descendant');

        const crossbar = descEdges.find(e =>
            e.y1 === UMBRELLA_Y && e.y2 === UMBRELLA_Y &&
            Math.min(e.x1, e.x2) === leftmost && Math.max(e.x1, e.x2) === rightmost
        );
        expect(crossbar).toBeDefined();

        // No focus-spouse → drop starts at the bottom of the focus (NODE_H_FOCUS = 42),
        // not at NODE_H (= 38) which would be 4px inside the focus node.
        const anchorDrop = descEdges.find(e =>
            e.x1 === anchorX && e.y1 === NODE_H_FOCUS && e.x2 === anchorX && e.y2 === UMBRELLA_Y
        );
        expect(anchorDrop).toBeDefined();

        centers.forEach(cx => {
            const drop = descEdges.find(e =>
                e.x1 === cx && e.y1 === UMBRELLA_Y && e.x2 === cx && e.y2 === ROW_HEIGHT
            );
            expect(drop).toBeDefined();
        });
    });

    it('child with spouse: spouse node has role descendant_spouse; marriage edge between them', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@C1@': { birth_year: 1925 },
                '@C1SP@': { birth_year: 1927 },
            },
            children: { '@FOCUS@': ['@C1@'] },
            relatives: { '@C1@': { siblings: [], spouses: ['@C1SP@'] } },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const sp = nodes.find(n => n.xref === '@C1SP@');
        expect(sp).toBeDefined();
        expect(sp.role).toBe('descendant_spouse');
        expect(sp.y).toBe(ROW_HEIGHT);

        const c1 = nodes.find(n => n.xref === '@C1@');
        // Descendant-row spouses use a short gap (H_GAP) — MARRIAGE_GAP is reserved
        // for the focus couple (where children hang below the marriage midpoint).
        expect(sp.x).toBeCloseTo(c1.x + NODE_W + H_GAP, 1);

        const marriageAtChildRow = edges.find(e =>
            e.type === 'marriage' && e.y1 === ROW_HEIGHT + NODE_H / 2 && e.y2 === ROW_HEIGHT + NODE_H / 2
        );
        expect(marriageAtChildRow).toBeDefined();
        expect(marriageAtChildRow.x1).toBeCloseTo(c1.x + NODE_W, 1); // child right edge
        expect(marriageAtChildRow.x2).toBeCloseTo(sp.x, 1); // spouse left edge
    });

    it('focus with no spouse: anchor originates at focus center (NODE_W_FOCUS/2)', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@C1@': { birth_year: 1925 },
            },
            children: { '@FOCUS@': ['@C1@'] },
        });
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const anchorX = NODE_W_FOCUS / 2;
        // No spouse → drop starts at NODE_H_FOCUS (the bottom of the focus node).
        const anchorDrop = edges.find(e =>
            e.type === 'descendant' &&
            e.x1 === anchorX && e.y1 === NODE_H_FOCUS && e.x2 === anchorX && e.y2 === (NODE_H + (ROW_HEIGHT - NODE_H) / 2)
        );
        expect(anchorDrop).toBeDefined();
    });

    it('two children both with spouses: crossbar x-span covers only child centers', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@C1@': { birth_year: 1925 },
                '@C1SP@': { birth_year: 1926 },
                '@C2@': { birth_year: 1928 },
                '@C2SP@': { birth_year: 1930 },
            },
            children: { '@FOCUS@': ['@C1@', '@C2@'] },
            relatives: {
                '@C1@': { siblings: [], spouses: ['@C1SP@'] },
                '@C2@': { siblings: [], spouses: ['@C2SP@'] },
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const c1 = nodes.find(n => n.xref === '@C1@');
        const c2 = nodes.find(n => n.xref === '@C2@');
        const sp1 = nodes.find(n => n.xref === '@C1SP@');
        const sp2 = nodes.find(n => n.xref === '@C2SP@');

        const c1Center = c1.x + NODE_W / 2;
        const c2Center = c2.x + NODE_W / 2;
        const sp2Center = sp2.x + NODE_W / 2;

        const crossbar = edges.find(e =>
            e.type === 'descendant' && e.y1 === e.y2 &&
            e.y1 === NODE_H + (ROW_HEIGHT - NODE_H) / 2 && e.x1 !== e.x2
        );
        expect(crossbar).toBeDefined();
        const leftmost = Math.min(crossbar.x1, crossbar.x2);
        const rightmost = Math.max(crossbar.x1, crossbar.x2);
        expect(leftmost).toBeCloseTo(c1Center, 1);
        expect(rightmost).toBeCloseTo(c2Center, 1);
        // Crossbar must NOT extend as far as the second spouse
        expect(rightmost).toBeLessThan(sp2Center);

        // Group ordering: c1, sp1, c2, sp2 packed left→right
        expect(c1.x).toBeLessThan(sp1.x);
        expect(sp1.x).toBeLessThan(c2.x);
        expect(c2.x).toBeLessThan(sp2.x);
        // Child-spouse marriage edges (two, one per group)
        const marriageEdges = edges.filter(e =>
            e.type === 'marriage' && e.y1 === ROW_HEIGHT + NODE_H / 2
        );
        expect(marriageEdges).toHaveLength(2);
    });

    it('child-centers midpoint equals anchorX when focus has one spouse and two unmarried children', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE@': { birth_year: 1902 },
                '@C1@': { birth_year: 1925 },
                '@C2@': { birth_year: 1928 },
            },
            children: { '@FOCUS@': ['@C1@', '@C2@'] },
            relatives: { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] } },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const c1Center = nodes.find(n => n.xref === '@C1@').x + NODE_W / 2;
        const c2Center = nodes.find(n => n.xref === '@C2@').x + NODE_W / 2;
        const mid = (c1Center + c2Center) / 2;

        const focusCenter = NODE_W_FOCUS / 2;
        const spouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
        const spouseCenter = spouseX + NODE_W / 2;
        const anchorX = (focusCenter + spouseCenter) / 2;

        expect(mid).toBeCloseTo(anchorX, 1);
    });

    it('does not emit the old per-child slanted edge from (NODE_W/2, NODE_H) to a child top', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@C1@': { birth_year: 1925 },
                '@C2@': { birth_year: 1927 },
            },
            children: { '@FOCUS@': ['@C1@', '@C2@'] },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const childCenters = ['@C1@', '@C2@']
            .map(x => nodes.find(n => n.xref === x).x + NODE_W / 2);
        childCenters.forEach(cx => {
            const slant = edges.find(e =>
                e.type === 'descendant' &&
                e.x1 === NODE_W / 2 && e.y1 === NODE_H &&
                e.x2 === cx && e.y2 === ROW_HEIGHT
            );
            expect(slant).toBeUndefined();
        });
    });
});

// ── Test 10b: Multi-FAM children split ────────────────────────────────────

describe('computeLayout — multi-FAM children split', () => {
    const UMBRELLA_Y = NODE_H + (ROW_HEIGHT - NODE_H) / 2;

    it('splits focus children into visible-FAM (marriage line) and other-FAM (under focus) umbrellas', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1955 },
                '@SPOUSE1@': { birth_year: 1958 },
                '@CLAIRE@': { birth_year: 1985 },
                '@ELEANOR@': { birth_year: 1994 },
                '@TENG@': { birth_year: 1976 },
                '@WU@': { birth_year: 1978 },
            },
            children: { '@FOCUS@': ['@TENG@', '@WU@', '@CLAIRE@', '@ELEANOR@'] },
            relatives: { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE1@'] } },
            families: {
                '@F1@': { husb: '@FOCUS@', wife: '@SPOUSE1@', chil: ['@CLAIRE@'] },
                '@F2@': { husb: '@FOCUS@', wife: null, chil: ['@ELEANOR@'] },
                '@F3@': { husb: '@FOCUS@', wife: null, chil: ['@TENG@', '@WU@'] },
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

        const focusCenter = NODE_W_FOCUS / 2;
        const spouseLeft = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
        const spouseCenter = spouseLeft + NODE_W / 2;
        const marriageMid = (focusCenter + spouseCenter) / 2;

        const claire = nodes.find(n => n.xref === '@CLAIRE@');
        expect(claire).toBeDefined();
        expect(claire.x + NODE_W / 2).toBeCloseTo(marriageMid, 1);

        const visibleDrop = edges.find(e =>
            e.type === 'descendant' &&
            e.x1 === marriageMid && e.y1 === NODE_H / 2 &&
            e.x2 === marriageMid && e.y2 === UMBRELLA_Y
        );
        expect(visibleDrop).toBeDefined();

        const otherDrop = edges.find(e =>
            e.type === 'descendant' &&
            e.x1 === focusCenter && e.y1 === NODE_H_FOCUS &&
            e.x2 === focusCenter && e.y2 === UMBRELLA_Y
        );
        expect(otherDrop).toBeDefined();

        const teng = nodes.find(n => n.xref === '@TENG@');
        const wu = nodes.find(n => n.xref === '@WU@');
        const eleanor = nodes.find(n => n.xref === '@ELEANOR@');
        [teng, wu, eleanor].forEach(n => {
            expect(n.x + NODE_W).toBeLessThan(claire.x);
        });

        expect(teng.x).toBeLessThan(wu.x);
        expect(wu.x).toBeLessThan(eleanor.x);
    });

    it('single-FAM focus with on-row spouse behaves like legacy (one umbrella at marriage midpoint)', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SPOUSE@': { birth_year: 1902 },
                '@C1@': { birth_year: 1925 },
            },
            children: { '@FOCUS@': ['@C1@'] },
            relatives: { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] } },
            families: {
                '@F1@': { husb: '@FOCUS@', wife: '@SPOUSE@', chil: ['@C1@'] },
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

        const focusCenter = NODE_W_FOCUS / 2;
        const spouseCenter = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2 + NODE_W / 2;
        const marriageMid = (focusCenter + spouseCenter) / 2;

        const c1 = nodes.find(n => n.xref === '@C1@');
        expect(c1.x + NODE_W / 2).toBeCloseTo(marriageMid, 1);

        const otherDrop = edges.find(e =>
            e.type === 'descendant' &&
            e.x1 === focusCenter && e.y1 === NODE_H_FOCUS &&
            e.x2 === focusCenter && e.y2 === UMBRELLA_Y
        );
        expect(otherDrop).toBeUndefined();
    });
});

// ── Test 11: Ancestor umbrella layout ─────────────────────────────────────

describe('computeLayout — ancestor umbrella', () => {
    const ANC_UMBRELLA_Y = -(ROW_HEIGHT - NODE_H) / 2; // -26
    const PARENT_BOTTOM = -ROW_HEIGHT + NODE_H; // -52
    const PARENT_MID_Y = -ROW_HEIGHT + NODE_H / 2; // -71

    it('two parents, no siblings: marriage edge between parents + anchor drop + single drop to focus', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@FATHER@': { birth_year: 1870 },
                '@MOTHER@': { birth_year: 1872 },
            },
            parents: { '@FOCUS@': ['@FATHER@', '@MOTHER@'] },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

        const father = nodes.find(n => n.xref === '@FATHER@');
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        expect(father).toBeDefined();
        expect(mother).toBeDefined();

        // Parents are centered on the focus visual center (NODE_W_FOCUS/2 = 80).
        const focusCenterX = NODE_W_FOCUS / 2;
        const fatherCenter = father.x + NODE_W / 2;
        const motherCenter = mother.x + NODE_W / 2;
        expect((fatherCenter + motherCenter) / 2).toBeCloseTo(focusCenterX, 1);

        // Marriage edge: father right edge → mother left edge at parent row middle y.
        const marriageEdge = edges.find(e =>
            e.type === 'marriage' && e.y1 === PARENT_MID_Y && e.y2 === PARENT_MID_Y
        );
        expect(marriageEdge).toBeDefined();
        expect(marriageEdge.x1).toBeCloseTo(father.x + NODE_W, 1);
        expect(marriageEdge.x2).toBeCloseTo(mother.x, 1);

        // Anchor drop: from the marriage line y down to umbrella y, at focus center x.
        // Starting at the marriage line (not parent bottom) so it meets perpendicularly with no gap.
        const ancEdges = edges.filter(e => e.type === 'ancestor');
        const anchorDrop = ancEdges.find(e =>
            e.x1 === focusCenterX && e.y1 === PARENT_MID_Y &&
            e.x2 === focusCenterX && e.y2 === ANC_UMBRELLA_Y
        );
        expect(anchorDrop).toBeDefined();

        // No crossbar (only one child of parents).
        const crossbar = ancEdges.find(e =>
            e.y1 === ANC_UMBRELLA_Y && e.y2 === ANC_UMBRELLA_Y && e.x1 !== e.x2
        );
        expect(crossbar).toBeUndefined();

        // Single drop from umbrella to focus top.
        const focusDrop = ancEdges.find(e =>
            e.x1 === focusCenterX && e.y1 === ANC_UMBRELLA_Y &&
            e.x2 === focusCenterX && e.y2 === 0
        );
        expect(focusDrop).toBeDefined();
    });

    it('two parents with siblings: crossbar spans leftmost→rightmost child center + per-child drops', () => {
        resetGlobals({
            people: {
                '@OLDER@': { birth_year: 1895 },
                '@FOCUS@': { birth_year: 1900 },
                '@YOUNGER@': { birth_year: 1905 },
                '@FATHER@': { birth_year: 1870 },
                '@MOTHER@': { birth_year: 1872 },
            },
            parents: { '@FOCUS@': ['@FATHER@', '@MOTHER@'] },
            relatives: { '@FOCUS@': { siblings: ['@OLDER@', '@YOUNGER@'], spouses: [] } },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

        const focus = nodes.find(n => n.xref === '@FOCUS@');
        const older = nodes.find(n => n.xref === '@OLDER@');
        const younger = nodes.find(n => n.xref === '@YOUNGER@');

        const focusCenterX = focus.x + NODE_W_FOCUS / 2;
        const olderCenterX = older.x + NODE_W / 2;
        const youngerCenterX = younger.x + NODE_W / 2;

        const centers = [olderCenterX, focusCenterX, youngerCenterX];
        const leftmost = Math.min(...centers);
        const rightmost = Math.max(...centers);

        const ancEdges = edges.filter(e => e.type === 'ancestor');

        // Crossbar spanning leftmost child center to rightmost child center.
        const crossbar = ancEdges.find(e =>
            e.y1 === ANC_UMBRELLA_Y && e.y2 === ANC_UMBRELLA_Y &&
            Math.min(e.x1, e.x2) === leftmost && Math.max(e.x1, e.x2) === rightmost
        );
        expect(crossbar).toBeDefined();

        // Parent couple re-centers over the sibling group, so the anchor is a
        // single straight vertical segment at groupCenterX from PARENT_MID_Y to
        // ANC_UMBRELLA_Y.
        const groupCenterX = (leftmost + rightmost) / 2;
        const straight = ancEdges.find(e =>
            Math.abs(e.x1 - groupCenterX) < 0.5 && Math.abs(e.x2 - groupCenterX) < 0.5 &&
            Math.abs(e.y1 - PARENT_MID_Y) < 0.5 && Math.abs(e.y2 - ANC_UMBRELLA_Y) < 0.5
        );
        expect(straight).toBeDefined();

        // Per-child drops — one per gen-0 child of the parents (focus + siblings).
        centers.forEach(cx => {
            const drop = ancEdges.find(e =>
                e.x1 === cx && e.y1 === ANC_UMBRELLA_Y &&
                e.x2 === cx && e.y2 === 0
            );
            expect(drop).toBeDefined();
        });
    });

    it('single parent with siblings: no marriage edge; parent centered on sibling group', () => {
        resetGlobals({
            people: {
                '@OLDER@': { birth_year: 1895 },
                '@FOCUS@': { birth_year: 1900 },
                '@MOTHER@': { birth_year: 1872 },
            },
            parents: { '@FOCUS@': [null, '@MOTHER@'] },
            relatives: { '@FOCUS@': { siblings: ['@OLDER@'], spouses: [] } },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const focusCenterX = NODE_W_FOCUS / 2;
        const older = nodes.find(n => n.xref === '@OLDER@');
        const olderCenterX = older.x + NODE_W / 2;
        const groupCenterX = (Math.min(focusCenterX, olderCenterX) + Math.max(focusCenterX, olderCenterX)) / 2;

        // Mother's center aligns with the sibling-group center, not the focus center.
        expect(mother.x + NODE_W / 2).toBeCloseTo(groupCenterX, 1);

        // No marriage edge at the parent row (single parent).
        const parentMarriage = edges.find(e =>
            e.type === 'marriage' && e.y1 === PARENT_MID_Y
        );
        expect(parentMarriage).toBeUndefined();

        const ancEdges = edges.filter(e => e.type === 'ancestor');

        // Straight anchor drop at groupCenterX from parent bottom to umbrella y.
        const straight = ancEdges.find(e =>
            Math.abs(e.x1 - groupCenterX) < 0.5 && Math.abs(e.x2 - groupCenterX) < 0.5 &&
            Math.abs(e.y1 - PARENT_BOTTOM) < 0.5 && Math.abs(e.y2 - ANC_UMBRELLA_Y) < 0.5
        );
        expect(straight).toBeDefined();

        // Crossbar spans the two gen-0 children.
        const crossbar = ancEdges.find(e =>
            e.y1 === ANC_UMBRELLA_Y && e.y2 === ANC_UMBRELLA_Y && e.x1 !== e.x2
        );
        expect(crossbar).toBeDefined();
        expect(Math.min(crossbar.x1, crossbar.x2)).toBeCloseTo(Math.min(focusCenterX, olderCenterX), 1);
        expect(Math.max(crossbar.x1, crossbar.x2)).toBeCloseTo(Math.max(focusCenterX, olderCenterX), 1);

        // Per-child drops.
        [focusCenterX, olderCenterX].forEach(cx => {
            const drop = ancEdges.find(e =>
                e.x1 === cx && e.y1 === ANC_UMBRELLA_Y &&
                e.x2 === cx && e.y2 === 0
            );
            expect(drop).toBeDefined();
        });
    });

    it('does not emit the old H-connector crossbar at y = -ROW_HEIGHT/2', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@FATHER@': { birth_year: 1870 },
                '@MOTHER@': { birth_year: 1872 },
            },
            parents: { '@FOCUS@': ['@FATHER@', '@MOTHER@'] },
        });
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
        const oldCrossbar = edges.find(e =>
            e.type === 'ancestor' &&
            e.y1 === -ROW_HEIGHT / 2 && e.y2 === -ROW_HEIGHT / 2 && e.x1 !== e.x2
        );
        expect(oldCrossbar).toBeUndefined();
    });
});

// ── Test 12: Recursive ancestor umbrella (grandparents and deeper) ────────

describe('computeLayout — recursive ancestor umbrella', () => {
    it('two grandparents: marriage edge + single drop to intermediate parent', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@FATHER@': { birth_year: 1870 },
                '@MOTHER@': { birth_year: 1872 },
                '@MGF@': { birth_year: 1840 },
                '@MGM@': { birth_year: 1842 },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@MOTHER@': ['@MGF@', '@MGM@'],
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(['@MOTHER@']), new Set());

        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const mgf = nodes.find(n => n.xref === '@MGF@');
        const mgm = nodes.find(n => n.xref === '@MGM@');
        expect(mgf).toBeDefined();
        expect(mgm).toBeDefined();

        const gpMidY = -2 * ROW_HEIGHT + NODE_H / 2;

        // Marriage edge between MGF and MGM at the grandparent row center y.
        const marriageEdge = edges.find(e =>
            e.type === 'marriage' && e.y1 === gpMidY && e.y2 === gpMidY
        );
        expect(marriageEdge).toBeDefined();
        expect(marriageEdge.x1).toBeCloseTo(mgf.x + NODE_W, 1);
        expect(marriageEdge.x2).toBeCloseTo(mgm.x, 1);

        // Single vertical drop from the grandparents' marriage line midpoint (= mother's center)
        // down to the mother node's top. Type 'ancestor'.
        const motherCenterX = mother.x + NODE_W / 2;
        const drop = edges.find(e =>
            e.type === 'ancestor' &&
            e.x1 === motherCenterX && e.y1 === gpMidY &&
            e.x2 === motherCenterX && e.y2 === -ROW_HEIGHT
        );
        expect(drop).toBeDefined();

        // No old H-connector crossbar at y = -2*ROW_HEIGHT + ROW_HEIGHT/2.
        const oldCrossbarY = -2 * ROW_HEIGHT + ROW_HEIGHT / 2;
        const oldCrossbar = edges.find(e =>
            e.type === 'ancestor' &&
            e.y1 === oldCrossbarY && e.y2 === oldCrossbarY && e.x1 !== e.x2
        );
        expect(oldCrossbar).toBeUndefined();
    });

    it('single grandparent: one vertical drop, no marriage edge at grandparent row', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@MOTHER@': { birth_year: 1872 },
                '@MGM@': { birth_year: 1842 },
            },
            parents: {
                '@FOCUS@': [null, '@MOTHER@'],
                '@MOTHER@': [null, '@MGM@'],
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(['@MOTHER@']), new Set());

        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const motherCenterX = mother.x + NODE_W / 2;
        const gpBottomY = -2 * ROW_HEIGHT + NODE_H;

        // Single vertical from grandparent bottom to mother top.
        const drop = edges.find(e =>
            e.type === 'ancestor' &&
            e.x1 === motherCenterX && e.y1 === gpBottomY &&
            e.x2 === motherCenterX && e.y2 === -ROW_HEIGHT
        );
        expect(drop).toBeDefined();

        // No marriage edge at the grandparent row center y.
        const gpMidY = -2 * ROW_HEIGHT + NODE_H / 2;
        const marriageAtGpRow = edges.find(e =>
            e.type === 'marriage' && e.y1 === gpMidY
        );
        expect(marriageAtGpRow).toBeUndefined();
    });

    it('three generations expanded: umbrella pattern recurses to great-grandparents', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1995 },
                '@MOTHER@': { birth_year: 1965 },
                '@MGF@': { birth_year: 1935 },
                '@MGM@': { birth_year: 1937 },
                '@MGGF@': { birth_year: 1905 },
                '@MGGM@': { birth_year: 1907 },
            },
            parents: {
                '@FOCUS@': [null, '@MOTHER@'],
                '@MOTHER@': ['@MGF@', '@MGM@'],
                '@MGF@': ['@MGGF@', '@MGGM@'],
            },
        });
        const expanded = new Set(['@MOTHER@', '@MGF@']);
        const { nodes, edges } = computeLayout('@FOCUS@', expanded, new Set());

        const mgf = nodes.find(n => n.xref === '@MGF@');
        const mggf = nodes.find(n => n.xref === '@MGGF@');
        const mggm = nodes.find(n => n.xref === '@MGGM@');
        expect(mggf).toBeDefined();
        expect(mggm).toBeDefined();

        const ggpMidY = -3 * ROW_HEIGHT + NODE_H / 2;
        const mgfCenterX = mgf.x + NODE_W / 2;

        // Marriage edge between great-grandparents.
        const marriageEdge = edges.find(e =>
            e.type === 'marriage' && e.y1 === ggpMidY && e.y2 === ggpMidY
        );
        expect(marriageEdge).toBeDefined();
        expect(marriageEdge.x1).toBeCloseTo(mggf.x + NODE_W, 1);
        expect(marriageEdge.x2).toBeCloseTo(mggm.x, 1);

        // Single drop from great-grandparents' marriage line midpoint (= MGF center) to MGF top.
        const drop = edges.find(e =>
            e.type === 'ancestor' &&
            e.x1 === mgfCenterX && e.y1 === ggpMidY &&
            e.x2 === mgfCenterX && e.y2 === -2 * ROW_HEIGHT
        );
        expect(drop).toBeDefined();
    });
});

// ── Test 13: Contour helpers ───────────────────────────────────────────────

describe('_requiredSeparation', () => {
    it('two leaves: sep = SLOT (adjacent at row 0)', () => {
        resetGlobals({
            people: { '@F@': {}, '@M@': {} },
            parents: {},
        });
        expect(_requiredSeparation('@F@', '@M@', new Set())).toBeCloseTo(SLOT, 1);
    });

    it('leaf vs 1-level subtree: still sep = SLOT (no collision on deeper row)', () => {
        resetGlobals({
            people: { '@F@': {}, '@M@': {}, '@MF@': {}, '@MM@': {} },
            parents: { '@M@': ['@MF@', '@MM@'] },
        });
        expect(_requiredSeparation('@F@', '@M@', new Set(['@M@']))).toBeCloseTo(SLOT, 1);
    });

    it('both 1-level subtrees: sep driven by depth-1 width + FAMILY_GAP', () => {
        const { FAMILY_GAP } = DESIGN;
        resetGlobals({
            people: {
                '@F@': {},
                '@M@': {},
                '@FF@': {},
                '@FM@': {},
                '@MF@': {},
                '@MM@': {},
            },
            parents: {
                '@F@': ['@FF@', '@FM@'],
                '@M@': ['@MF@', '@MM@'],
            },
        });
        // At depth 1: each side's rightmost/leftmost is its outer parent's edge —
        // (NODE_W + H_GAP)/2 + NODE_W/2 = NODE_W + H_GAP/2 away from root center.
        // Separation = 2*(NODE_W + H_GAP/2) + FAMILY_GAP = 2*NODE_W + H_GAP + FAMILY_GAP.
        const expected = 2 * NODE_W + H_GAP + FAMILY_GAP;
        expect(_requiredSeparation('@F@', '@M@', new Set(['@F@', '@M@']))).toBeCloseTo(expected, 1);
    });

    it('single-parent subtree: parent sits at root center, depth-1 width = 0', () => {
        // F has only one expanded parent (single-parent recursion places it at root center).
        // Collision constraint on row 1: only F's-lone-parent vs M itself → SLOT.
        resetGlobals({
            people: { '@F@': {}, '@M@': {}, '@FF@': {} },
            parents: { '@F@': ['@FF@', null] },
        });
        expect(_requiredSeparation('@F@', '@M@', new Set(['@F@']))).toBeCloseTo(SLOT, 1);
    });
});

// ── Test 14: Pietro-Elena regression — imbalanced ancestor subtrees ────────

// Regression for the bug where expanding one spouse's subtree caused the other
// (leaf) spouse to jump sideways, leaving the couple's marriage midpoint no
// longer above the child. Mirrors the user scenario:
//   Helena focus → Joseph expanded → Pietro (leaf) + Elena (expanded) → Elena's parents.
describe('computeLayout — imbalanced ancestor subtrees keep midpoint above child', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@HELENA@': { birth_year: 1995 },
                '@JOSEPH@': { birth_year: 1965 },
                '@MARIE@': { birth_year: 1967 },
                '@PIETRO@': { birth_year: 1935 },
                '@ELENA@': { birth_year: 1937 },
                '@ELENA_F@': { birth_year: 1905 },
                '@ELENA_M@': { birth_year: 1907 },
                '@PIETRO_F@': { birth_year: 1905 },
                '@PIETRO_M@': { birth_year: 1907 },
            },
            parents: {
                '@HELENA@': ['@JOSEPH@', '@MARIE@'],
                '@JOSEPH@': ['@PIETRO@', '@ELENA@'],
                '@ELENA@': ['@ELENA_F@', '@ELENA_M@'],
                '@PIETRO@': ['@PIETRO_F@', '@PIETRO_M@'],
            },
        });
    });

    it('Pietro (leaf) stays put when Elena expands her own subtree', () => {
        const { nodes: before } = computeLayout('@HELENA@', new Set(['@JOSEPH@']), new Set());
        const { nodes: after } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@ELENA@']), new Set());
        const pietroBefore = before.find(n => n.xref === '@PIETRO@');
        const pietroAfter = after.find(n => n.xref === '@PIETRO@');
        expect(pietroAfter.x).toBe(pietroBefore.x);
    });

    it('symmetric case: Elena (leaf) stays put when Pietro expands', () => {
        const { nodes: before } = computeLayout('@HELENA@', new Set(['@JOSEPH@']), new Set());
        const { nodes: after } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@PIETRO@']), new Set());
        const elenaBefore = before.find(n => n.xref === '@ELENA@');
        const elenaAfter = after.find(n => n.xref === '@ELENA@');
        expect(elenaAfter.x).toBe(elenaBefore.x);
    });

    it('couple marriage midpoint = child center when only Elena expands', () => {
        const { nodes } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@ELENA@']), new Set());
        const joseph = nodes.find(n => n.xref === '@JOSEPH@');
        const pietro = nodes.find(n => n.xref === '@PIETRO@');
        const elena = nodes.find(n => n.xref === '@ELENA@');
        const marriageMidX = ((pietro.x + NODE_W) + elena.x) / 2;
        expect(marriageMidX).toBeCloseTo(joseph.x + NODE_W / 2, 1);
    });

    it('ancestor drop to child starts at child center on the marriage line', () => {
        const { nodes, edges } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@ELENA@']), new Set());
        const joseph = nodes.find(n => n.xref === '@JOSEPH@');
        const jcenter = joseph.x + NODE_W / 2;
        const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;
        const drop = edges.find(e =>
            e.type === 'ancestor' &&
            e.x1 === jcenter && e.x2 === jcenter &&
            e.y1 === parentMidY && e.y2 === -ROW_HEIGHT
        );
        expect(drop).toBeDefined();
    });

    it('balanced case (both expanded): pietro/elena straddle joseph symmetrically', () => {
        const { FAMILY_GAP } = DESIGN;
        const { nodes } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@PIETRO@', '@ELENA@']), new Set());
        const joseph = nodes.find(n => n.xref === '@JOSEPH@');
        const pietro = nodes.find(n => n.xref === '@PIETRO@');
        const elena = nodes.find(n => n.xref === '@ELENA@');
        // Both sides have 1-level subtrees → sep driven by depth-1 + FAMILY_GAP.
        const sep = 2 * NODE_W + H_GAP + FAMILY_GAP;
        expect(pietro.x).toBeCloseTo(joseph.x + NODE_W / 2 - sep / 2 - NODE_W / 2, 1);
        expect(elena.x).toBeCloseTo(joseph.x + NODE_W / 2 + sep / 2 - NODE_W / 2, 1);
    });
});

// ── Ancestor sibling expansion ─────────────────────────────────────────────
//
// Fixture: focus has both parents (FATHER, MOTHER). Each parent has two
// full siblings (same FAMC) and one of those siblings has a spouse.
//
//        gp_father ═══ gp_mother           (not rendered by default)
//        /    |    \
//   F_SIB1  FATHER  F_SIB2══F_SIB2_SP     (father + father's siblings)
//
//                     MOTHER ═══ father    (standard couple)
//                        |
//                      FOCUS

describe('computeLayout — ancestor sibling expansion', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000, sex: 'M' },
                '@FATHER@': { birth_year: 1970, sex: 'M' },
                '@MOTHER@': { birth_year: 1972, sex: 'F' },
                '@F_SIB1@': { birth_year: 1965, sex: 'M' },
                '@F_SIB2@': { birth_year: 1975, sex: 'F' },
                '@F_SIB2_SP@': { birth_year: 1974, sex: 'M' },
                '@M_SIB1@': { birth_year: 1968, sex: 'F' },
                '@M_SIB2@': { birth_year: 1976, sex: 'M' },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@FATHER@': [null, null],
                '@MOTHER@': [null, null],
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: [] },
                '@FATHER@': { siblings: ['@F_SIB1@', '@F_SIB2@'], spouses: [] },
                '@MOTHER@': { siblings: ['@M_SIB1@', '@M_SIB2@'], spouses: [] },
                '@F_SIB1@': { siblings: [], spouses: [] },
                '@F_SIB2@': { siblings: [], spouses: ['@F_SIB2_SP@'] },
                '@M_SIB1@': { siblings: [], spouses: [] },
                '@M_SIB2@': { siblings: [], spouses: [] },
            },
        });
    });

    it('does NOT render ancestor siblings when set is empty', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        expect(nodes.find(n => n.xref === '@F_SIB1@')).toBeUndefined();
        expect(nodes.find(n => n.xref === '@M_SIB1@')).toBeUndefined();
    });

    it('places ALL of mother\'s siblings to the RIGHT of mother (outward/chevron side)', () => {
        // Spouses must stay adjacent → siblings extend only to the outward side
        // of the couple, regardless of birth year. Mother is the right-side parent,
        // so her siblings stack right of her.
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@'); // 1968, older than mother
        const sib2 = nodes.find(n => n.xref === '@M_SIB2@'); // 1976, younger
        expect(sib1).toBeDefined();
        expect(sib2).toBeDefined();
        expect(sib1.x).toBeGreaterThan(mother.x);
        expect(sib2.x).toBeGreaterThan(mother.x);
    });

    it('places ALL of father\'s siblings to the LEFT of father (outward/chevron side)', () => {
        // Father is the left-side parent; his siblings stack left of him.
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@']));
        const father = nodes.find(n => n.xref === '@FATHER@');
        const sib1 = nodes.find(n => n.xref === '@F_SIB1@'); // 1965, older
        const sib2 = nodes.find(n => n.xref === '@F_SIB2@'); // 1975, younger
        expect(sib1).toBeDefined();
        expect(sib2).toBeDefined();
        expect(sib1.x).toBeLessThan(father.x);
        expect(sib2.x).toBeLessThan(father.x);
    });

    it('ancestor siblings sit at the same y as their parent-node', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@');
        expect(sib1.y).toBe(mother.y);
    });

    it('ancestor siblings have role "ancestor_sibling"', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const sib = nodes.find(n => n.xref === '@M_SIB1@');
        expect(sib.role).toBe('ancestor_sibling');
    });

    it('mother\'s inline siblings are chronologically ordered left-to-right (oldest closest to mother)', () => {
        // All of mother's siblings sit on her right. Sorted by birth-year asc from
        // mother outward: MOTHER → M_SIB1 (1968) → M_SIB2 (1976).
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@');
        const sib2 = nodes.find(n => n.xref === '@M_SIB2@');
        expect(mother.x).toBeLessThan(sib1.x);
        expect(sib1.x).toBeLessThan(sib2.x);
    });

    it('father\'s inline siblings are chronologically ordered left-to-right (youngest closest to father)', () => {
        // All of father's siblings sit on his left. Sorted by birth-year asc from
        // far-left inward: F_SIB1 (1965) → F_SIB2 (1975) → FATHER.
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@']));
        const father = nodes.find(n => n.xref === '@FATHER@');
        const sib1 = nodes.find(n => n.xref === '@F_SIB1@');
        const sib2 = nodes.find(n => n.xref === '@F_SIB2@');
        expect(sib1.x).toBeLessThan(sib2.x);
        expect(sib2.x).toBeLessThan(father.x);
    });

    it('inline siblings leave chevron clearance on the ancestor side', () => {
        // Chevron (r=8, 4px off pill edge) sits between ancestor and first sibling.
        // First gap ≥ 20px (chevron reach) so the chevron doesn't overlap siblings.
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@'); // closest to mother
        const firstGap = sib1.x - (mother.x + NODE_W);
        expect(firstGap).toBeGreaterThanOrEqual(20);
    });

    it('siblings after the first sit tight with H_GAP between them', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@');
        const sib2 = nodes.find(n => n.xref === '@M_SIB2@');
        expect(sib2.x - (sib1.x + NODE_W)).toBe(H_GAP);
    });

    it('renders a sibling\'s spouse adjacent to the sibling', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        // F_SIB2 has a spouse; but we only expanded MOTHER, not FATHER.
        // Switch to father expansion to exercise the spouse rendering path.
        const { nodes: nodes2 } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@']));
        const sib2 = nodes2.find(n => n.xref === '@F_SIB2@');
        const sp = nodes2.find(n => n.xref === '@F_SIB2_SP@');
        expect(sib2).toBeDefined();
        expect(sp).toBeDefined();
        expect(sp.role).toBe('ancestor_sibling_spouse');
        expect(sp.y).toBe(sib2.y);
    });

    it('never emits a sibling_bracket edge (inline model retires that type)', () => {
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        expect(edges.filter(e => e.type === 'sibling_bracket').length).toBe(0);
    });

    it('expanding both parents groups each side\'s siblings on the outward side, keeping the couple adjacent', () => {
        // FATHER: 1970, siblings F_SIB1 (1965, older), F_SIB2 (1975, younger)
        // MOTHER: 1972, siblings M_SIB1 (1968, older), M_SIB2 (1976, younger)
        // Father's sibs ALL go left of father; mother's sibs ALL go right of mother.
        // Father and mother stay adjacent (marriage gap) — no sibling between them.
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@', '@MOTHER@']));
        const father = nodes.find(n => n.xref === '@FATHER@');
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const fSib1 = nodes.find(n => n.xref === '@F_SIB1@');
        const fSib2 = nodes.find(n => n.xref === '@F_SIB2@');
        const mSib1 = nodes.find(n => n.xref === '@M_SIB1@');
        const mSib2 = nodes.find(n => n.xref === '@M_SIB2@');
        // All of father's siblings sit left of father.
        expect(fSib1.x).toBeLessThan(father.x);
        expect(fSib2.x).toBeLessThan(father.x);
        // All of mother's siblings sit right of mother.
        expect(mSib1.x).toBeGreaterThan(mother.x);
        expect(mSib2.x).toBeGreaterThan(mother.x);
        // Couple stays together: no node between father and mother on this row.
        const between = nodes.filter(n =>
            n.y === father.y &&
            n.x > father.x && n.x < mother.x &&
            n.xref !== '@FATHER@' && n.xref !== '@MOTHER@'
        );
        expect(between).toHaveLength(0);
    });

    it('no overlap between father\'s siblings and any other node on the same row', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@', '@MOTHER@']));
        const rowNodes = nodes.filter(n => n.y === -ROW_HEIGHT);
        const sorted = [...rowNodes].sort((a, b) => a.x - b.x);
        for (let i = 1; i < sorted.length; i++) {
            expect(sorted[i].x).toBeGreaterThanOrEqual(sorted[i - 1].x + NODE_W);
        }
    });
});

// ── Sibling umbrella (force-expand parents, umbrella spans ancestor+sibs) ──

describe('computeLayout — sibling expansion umbrella', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000, sex: 'M' },
                '@FATHER@': { birth_year: 1970, sex: 'M' },
                '@MOTHER@': { birth_year: 1972, sex: 'F' },
                '@M_GF@': { birth_year: 1945, sex: 'M' }, // mother's father
                '@M_GM@': { birth_year: 1947, sex: 'F' }, // mother's mother
                '@M_SIB1@': { birth_year: 1968, sex: 'F' },
                '@M_SIB2@': { birth_year: 1976, sex: 'M' },
                '@M_SIB2_SP@': { birth_year: 1975, sex: 'F' },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@FATHER@': [null, null],
                '@MOTHER@': ['@M_GF@', '@M_GM@'],
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: [] },
                '@FATHER@': { siblings: [], spouses: [] },
                '@MOTHER@': { siblings: ['@M_SIB1@', '@M_SIB2@'], spouses: [] },
                '@M_SIB1@': { siblings: [], spouses: [] },
                '@M_SIB2@': { siblings: [], spouses: ['@M_SIB2_SP@'] },
            },
        });
    });

    it('force-expands the ancestor\'s parents when only siblings are expanded', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        expect(nodes.find(n => n.xref === '@M_GF@')).toBeDefined();
        expect(nodes.find(n => n.xref === '@M_GM@')).toBeDefined();
    });

    it('emits a crossbar at umbrella-y spanning leftmost to rightmost of (ancestor + siblings)', () => {
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@');
        const sib2 = nodes.find(n => n.xref === '@M_SIB2@');
        const bioCenters = [mother, sib1, sib2].map(n => n.x + NODE_W / 2).sort((a, b) => a - b);
        const leftX = bioCenters[0];
        const rightX = bioCenters[bioCenters.length - 1];
        const crossbar = edges.find(e =>
            Math.abs(e.y1 - umbrellaY) < 0.5 && Math.abs(e.y2 - umbrellaY) < 0.5 &&
            Math.abs(e.x1 - leftX) < 0.5 && Math.abs(e.x2 - rightX) < 0.5
        );
        expect(crossbar).toBeDefined();
    });

    it('emits a vertical drop from umbrella to each biological child (ancestor + each sibling)', () => {
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
        const bioXrefs = ['@MOTHER@', '@M_SIB1@', '@M_SIB2@'];
        for (const xref of bioXrefs) {
            const n = nodes.find(nn => nn.xref === xref);
            const cx = n.x + NODE_W / 2;
            const drop = edges.find(e =>
                Math.abs(e.x1 - cx) < 0.5 && Math.abs(e.x2 - cx) < 0.5 &&
                Math.abs(e.y1 - umbrellaY) < 0.5 && Math.abs(e.y2 - n.y) < 0.5
            );
            expect(drop).toBeDefined();
        }
    });

    it('does NOT drop to siblings\' spouses (only biological children)', () => {
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
        const sp = nodes.find(n => n.xref === '@M_SIB2_SP@');
        expect(sp).toBeDefined();
        const cx = sp.x + NODE_W / 2;
        const dropToSpouse = edges.find(e =>
            Math.abs(e.x1 - cx) < 0.5 && Math.abs(e.x2 - cx) < 0.5 &&
            Math.abs(e.y1 - umbrellaY) < 0.5
        );
        expect(dropToSpouse).toBeUndefined();
    });

    it('straight anchor drop at groupCenterX when mother\'s siblings expand (parent couple re-centers, no L-shape)', () => {
        // Override fixture to force asymmetric bio-child distribution around mother.
        // Parent couple (M_GF + M_GM) should re-center over the sibling group so
        // their marriage midpoint sits directly above groupCenterX — the anchor
        // drop collapses to a single straight vertical segment.
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000, sex: 'M' },
                '@FATHER@': { birth_year: 1970, sex: 'M' },
                '@MOTHER@': { birth_year: 1972, sex: 'F' },
                '@M_GF@': { birth_year: 1945, sex: 'M' },
                '@M_GM@': { birth_year: 1947, sex: 'F' },
                '@M_SIB1@': { birth_year: 1974, sex: 'F' },
                '@M_SIB2@': { birth_year: 1978, sex: 'M' },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@FATHER@': [null, null],
                '@MOTHER@': ['@M_GF@', '@M_GM@'],
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: [] },
                '@FATHER@': { siblings: [], spouses: [] },
                '@MOTHER@': { siblings: ['@M_SIB1@', '@M_SIB2@'], spouses: [] },
                '@M_SIB1@': { siblings: [], spouses: [] },
                '@M_SIB2@': { siblings: [], spouses: [] },
            },
        });
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const sib1 = nodes.find(n => n.xref === '@M_SIB1@');
        const sib2 = nodes.find(n => n.xref === '@M_SIB2@');
        const gf = nodes.find(n => n.xref === '@M_GF@');
        const gm = nodes.find(n => n.xref === '@M_GM@');

        const bioCenters = [mother, sib1, sib2].map(n => n.x + NODE_W / 2).sort((a, b) => a - b);
        const groupCenterX = (bioCenters[0] + bioCenters[bioCenters.length - 1]) / 2;
        const parentMidX = ((gf.x + NODE_W) + gm.x) / 2;

        // Parent marriage midpoint aligns with group center.
        expect(Math.abs(parentMidX - groupCenterX)).toBeLessThan(0.5);

        const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
        const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;

        // Single straight anchor drop at groupCenterX from parentMidY down to umbrellaY.
        const straight = edges.find(e =>
            e.type === 'ancestor' &&
            Math.abs(e.x1 - groupCenterX) < 0.5 && Math.abs(e.x2 - groupCenterX) < 0.5 &&
            Math.abs(e.y1 - parentMidY) < 0.5 && Math.abs(e.y2 - umbrellaY) < 0.5
        );
        expect(straight).toBeDefined();

        // No horizontal elbow segment at the midpoint-y between parentMidY and umbrellaY.
        const elbowY = (parentMidY + umbrellaY) / 2;
        const elbow = edges.find(e =>
            e.type === 'ancestor' &&
            Math.abs(e.y1 - elbowY) < 0.5 && Math.abs(e.y2 - elbowY) < 0.5 &&
            Math.abs(e.x1 - e.x2) > 0.5
        );
        expect(elbow).toBeUndefined();
    });

    it('parent couple shifts right to re-center over the sibling group when mother\'s siblings expand', () => {
        // Baseline: no sibling expansion → mother sits at her "natural" x, parent midpoint over mother center.
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000, sex: 'M' },
                '@FATHER@': { birth_year: 1970, sex: 'M' },
                '@MOTHER@': { birth_year: 1972, sex: 'F' },
                '@M_GF@': { birth_year: 1945, sex: 'M' },
                '@M_GM@': { birth_year: 1947, sex: 'F' },
                '@M_SIB1@': { birth_year: 1974, sex: 'F' },
                '@M_SIB2@': { birth_year: 1978, sex: 'M' },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@FATHER@': [null, null],
                '@MOTHER@': ['@M_GF@', '@M_GM@'],
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: [] },
                '@FATHER@': { siblings: [], spouses: [] },
                '@MOTHER@': { siblings: ['@M_SIB1@', '@M_SIB2@'], spouses: [] },
                '@M_SIB1@': { siblings: [], spouses: [] },
                '@M_SIB2@': { siblings: [], spouses: [] },
            },
        });

        const baseline = computeLayout('@FOCUS@', new Set(['@MOTHER@']), new Set());
        const expanded = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));

        const baseGm = baseline.nodes.find(n => n.xref === '@M_GM@');
        const expGm = expanded.nodes.find(n => n.xref === '@M_GM@');
        // Maternal grandmother must shift RIGHT when siblings expand to mother's right.
        expect(expGm.x).toBeGreaterThan(baseGm.x);

        const baseGf = baseline.nodes.find(n => n.xref === '@M_GF@');
        const expGf = expanded.nodes.find(n => n.xref === '@M_GF@');
        // Grandfather shifts right too (whole couple translates together).
        expect(expGf.x).toBeGreaterThan(baseGf.x);
    });

    it('FAMILY_GAP: adjacent family subtrees at depth >= 1 get FAMILY_GAP padding (not just H_GAP)', () => {
        // Two sibling subtrees at the gen-0 row (father's grandparents + mother's grandparents).
        // At depth 0 the couple's own marriage gap stays H_GAP; the padding between
        // father-subtree and mother-subtree at depth 1 widens to FAMILY_GAP.
        const { FAMILY_GAP } = DESIGN;
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000, sex: 'M' },
                '@FATHER@': { birth_year: 1970, sex: 'M' },
                '@MOTHER@': { birth_year: 1972, sex: 'F' },
                '@F_GF@': { birth_year: 1945, sex: 'M' },
                '@F_GM@': { birth_year: 1947, sex: 'F' },
                '@M_GF@': { birth_year: 1945, sex: 'M' },
                '@M_GM@': { birth_year: 1947, sex: 'F' },
            },
            parents: {
                '@FOCUS@': ['@FATHER@', '@MOTHER@'],
                '@FATHER@': ['@F_GF@', '@F_GM@'],
                '@MOTHER@': ['@M_GF@', '@M_GM@'],
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: [] },
                '@FATHER@': { siblings: [], spouses: [] },
                '@MOTHER@': { siblings: [], spouses: [] },
            },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@', '@MOTHER@']), new Set());
        const fGm = nodes.find(n => n.xref === '@F_GM@'); // rightmost of father's subtree at gen-2
        const mGf = nodes.find(n => n.xref === '@M_GF@'); // leftmost of mother's subtree at gen-2
        const gap = mGf.x - (fGm.x + NODE_W);
        expect(gap).toBeGreaterThanOrEqual(FAMILY_GAP);
    });

    it('straight anchor drop (no L-shape) when only ancestors are expanded (no sibling offset)', () => {
        // Siblings not expanded → mother is the sole bio child visible under her parents.
        // The legacy straight-drop from parentMidY to mother-top should render (no umbrella).
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(['@MOTHER@']), new Set());
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const motherCx = mother.x + NODE_W / 2;
        const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;

        const straight = edges.find(e =>
            e.type === 'ancestor' &&
            Math.abs(e.x1 - motherCx) < 0.5 && Math.abs(e.x2 - motherCx) < 0.5 &&
            Math.abs(e.y1 - parentMidY) < 0.5 && Math.abs(e.y2 - (-ROW_HEIGHT)) < 0.5
        );
        expect(straight).toBeDefined();
    });

    it('does NOT emit the legacy straight drop from parent marriage to child top when siblings are expanded', () => {
        const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
        const mother = nodes.find(n => n.xref === '@MOTHER@');
        const cx = mother.x + NODE_W / 2;
        const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;
        // The old behavior was a drop from parentMidY down to y=-ROW_HEIGHT (mother top).
        // With umbrella, that direct drop is replaced by an anchor-to-umbrella drop.
        const legacyDrop = edges.find(e =>
            Math.abs(e.x1 - cx) < 0.5 && Math.abs(e.x2 - cx) < 0.5 &&
            Math.abs(e.y1 - parentMidY) < 0.5 && Math.abs(e.y2 - (-ROW_HEIGHT)) < 0.5
        );
        expect(legacyDrop).toBeUndefined();
    });
});

// ── Regression: deep-ancestor overlap via alternating parent paths ─────────
//
// Reproduces the Vitali/Dellatolla collision in Sasha's tree. Before the fix,
// _rightContour only recursed through the mother (right parent) and
// _leftContour only through the father (left parent). This missed deep
// ancestors reached via alternating paths — e.g. a node's MOTHER's FATHER's
// FATHER can stick out LEFTWARD past the node's own center when the deep
// father-chain is wider than the node's own parent separation.
//
// Layout below:
//
//   gen -5:                          Y_MFF   Y_MFM
//   gen -4:               X_MMF X_MMM  Y_MF  Y_MM
//   gen -3:     X_MF X_MM    X_M         Y_M         Y_F
//   gen -2:          X_F         X            Y
//   gen -1:                   X        Y
//   gen  0:                       F (focus)
//
// Both X's right contour and Y's left contour need to reach depth 3 for
// the pair (X_MMM | Y_MFF) at gen -5 to avoid overlap.
describe('computeLayout — deep-ancestor overlap via alternating parent paths', () => {
    const { FAMILY_GAP } = DESIGN;

    beforeEach(() => {
        resetGlobals({
            people: {
                '@F@': { birth_year: 2000, sex: 'M' },
                '@X@': { birth_year: 1970, sex: 'M' },
                '@Y@': { birth_year: 1972, sex: 'F' },
                '@X_F@': { birth_year: 1940, sex: 'M' },
                '@X_M@': { birth_year: 1942, sex: 'F' },
                '@X_MF@': { birth_year: 1910, sex: 'M' },
                '@X_MM@': { birth_year: 1912, sex: 'F' },
                '@X_MMF@': { birth_year: 1880, sex: 'M' },
                '@X_MMM@': { birth_year: 1882, sex: 'F' },
                '@Y_F@': { birth_year: 1940, sex: 'M' },
                '@Y_M@': { birth_year: 1942, sex: 'F' },
                '@Y_MF@': { birth_year: 1910, sex: 'M' },
                '@Y_MM@': { birth_year: 1912, sex: 'F' },
                '@Y_MFF@': { birth_year: 1880, sex: 'M' },
                '@Y_MFM@': { birth_year: 1882, sex: 'F' },
            },
            parents: {
                '@F@': ['@X@', '@Y@'],
                '@X@': ['@X_F@', '@X_M@'],
                '@X_M@': ['@X_MF@', '@X_MM@'],
                '@X_MM@': ['@X_MMF@', '@X_MMM@'],
                '@Y@': ['@Y_F@', '@Y_M@'],
                '@Y_M@': ['@Y_MF@', '@Y_MM@'],
                '@Y_MF@': ['@Y_MFF@', '@Y_MFM@'],
            },
        });
    });

    const fullyExpanded = new Set([
        '@X@', '@X_M@', '@X_MM@',
        '@Y@', '@Y_M@', '@Y_MF@',
    ]);

    it('_rightContour(X) reaches depth 3 (mother-path wing)', () => {
        const rc = _rightContour('@X@', fullyExpanded, new Set());
        expect(rc.length).toBeGreaterThanOrEqual(4);
    });

    it('_leftContour(Y) reaches depth 3 via mother→father→father (alternating) path', () => {
        // Buggy implementation only traces Y's father path (Y_F, who is a leaf),
        // so leftContour length is only 2. With both-parent recursion the left
        // wing through Y_M → Y_MF → Y_MFF makes it length 4.
        const lc = _leftContour('@Y@', fullyExpanded, new Set());
        expect(lc.length).toBeGreaterThanOrEqual(4);
    });

    it('no two nodes at the same generation overlap horizontally', () => {
        const { nodes } = computeLayout('@F@', fullyExpanded, new Set());
        const byGen = {};
        for (const n of nodes) {
            if (!byGen[n.generation]) byGen[n.generation] = [];
            byGen[n.generation].push(n);
        }
        for (const [gen, ns] of Object.entries(byGen)) {
            const sorted = ns.slice().sort((a, b) => a.x - b.x);
            for (let i = 1; i < sorted.length; i++) {
                const gap = sorted[i].x - (sorted[i - 1].x + NODE_W);
                expect(gap, `gen ${gen}: ${sorted[i - 1].xref} → ${sorted[i].xref}`)
                    .toBeGreaterThanOrEqual(0);
            }
        }
    });

    it('deepest great-great-grandparents on X side do not overlap those on Y side', () => {
        const { nodes } = computeLayout('@F@', fullyExpanded, new Set());
        const x_mmm = nodes.find(n => n.xref === '@X_MMM@'); // rightmost of X's subtree at gen -5
        const y_mff = nodes.find(n => n.xref === '@Y_MFF@'); // leftmost of Y's subtree at gen -5
        expect(x_mmm).toBeDefined();
        expect(y_mff).toBeDefined();
        const gap = y_mff.x - (x_mmm.x + NODE_W);
        expect(gap).toBeGreaterThanOrEqual(FAMILY_GAP);
    });
});

// ── Mirror: deep right wing on father side (symmetric to above) ────────────
//
// Father's MOTHER's MOTHER's MOTHER is reached via L→R→R→R. That wing can
// stick out to the right of the father's own center. _rightContour must
// capture it via the father subtree (not just the mother subtree).
describe('computeLayout — right-wing via father-then-mother path', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@F@': { birth_year: 2000, sex: 'M' },
                '@X@': { birth_year: 1970, sex: 'M' },
                '@Y@': { birth_year: 1972, sex: 'F' },
                '@X_F@': { birth_year: 1940, sex: 'M' },
                '@X_M@': { birth_year: 1942, sex: 'F' },
                '@X_FF@': { birth_year: 1910, sex: 'M' },
                '@X_FM@': { birth_year: 1912, sex: 'F' },
                '@X_FMF@': { birth_year: 1880, sex: 'M' },
                '@X_FMM@': { birth_year: 1882, sex: 'F' },
            },
            parents: {
                '@F@': ['@X@', '@Y@'],
                '@X@': ['@X_F@', '@X_M@'],
                '@X_F@': ['@X_FF@', '@X_FM@'],
                '@X_FM@': ['@X_FMF@', '@X_FMM@'],
            },
        });
    });

    it('_rightContour(X) captures the right-wing reached via father-then-mother-then-mother', () => {
        // X's right wing: X_F (left of X) → X_FM (right of X_F) → X_FMM (right of X_FM).
        // Buggy code only traces mother path (X_M, a leaf) → depth 1. With fix,
        // rightContour extends to depth 3 via the father subtree.
        const rc = _rightContour('@X@', new Set(['@X@', '@X_F@', '@X_FM@']), new Set());
        expect(rc.length).toBeGreaterThanOrEqual(4);
    });
});

// ── Expanded children of non-focus families ────────────────────────────────

describe('computeLayout — expandedChildrenPersons: brother\'s kids', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@BROTHER@': { birth_year: 1897 },
                '@NIECE1@': { birth_year: 1920 },
                '@NIECE2@': { birth_year: 1923 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@BROTHER@'], spouses: [] },
            },
            families: {
                '@BFAM@': { husb: '@BROTHER@', wife: null, chil: ['@NIECE1@', '@NIECE2@'] },
            },
        });
    });

    it('nieces do NOT appear when @BFAM@ is NOT in expandedChildrenPersons', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set());
        expect(nodes.find(n => n.xref === '@NIECE1@')).toBeUndefined();
        expect(nodes.find(n => n.xref === '@NIECE2@')).toBeUndefined();
    });

    it('nieces appear at y = +ROW_HEIGHT when @BFAM@ is in expandedChildrenPersons', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@BROTHER@']));
        const n1 = nodes.find(n => n.xref === '@NIECE1@');
        const n2 = nodes.find(n => n.xref === '@NIECE2@');
        expect(n1).toBeDefined();
        expect(n2).toBeDefined();
        expect(n1.y).toBe(ROW_HEIGHT);
        expect(n2.y).toBe(ROW_HEIGHT);
    });

    it('nieces have role "descendant" and generation +1', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@BROTHER@']));
        const n1 = nodes.find(n => n.xref === '@NIECE1@');
        expect(n1.role).toBe('descendant');
        expect(n1.generation).toBe(1);
    });

    it('nieces are centered under the brother', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@BROTHER@']));
        const brother = nodes.find(n => n.xref === '@BROTHER@');
        const n1 = nodes.find(n => n.xref === '@NIECE1@');
        const n2 = nodes.find(n => n.xref === '@NIECE2@');
        const brotherCenter = brother.x + NODE_W / 2;
        const niecesCenter = ((n1.x + NODE_W / 2) + (n2.x + NODE_W / 2)) / 2;
        expect(niecesCenter).toBeCloseTo(brotherCenter);
    });

    it('nieces sorted by birth year left-to-right', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@BROTHER@']));
        const n1 = nodes.find(n => n.xref === '@NIECE1@');
        const n2 = nodes.find(n => n.xref === '@NIECE2@');
        expect(n1.x).toBeLessThan(n2.x);
    });

    it('emits descendant edges for the children umbrella', () => {
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@BROTHER@']));
        const desc = edges.filter(e => e.type === 'descendant');
        expect(desc.length).toBeGreaterThan(0);
    });
});

// ── Regression: focus person in expandedChildrenPersons must not duplicate children ──
describe('computeLayout — focus person in expandedChildrenPersons does not duplicate children', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1905 },
                '@SPOUSE@': { birth_year: 1910 },
                '@CHILD1@': { birth_year: 1930 },
                '@CHILD2@': { birth_year: 1932 },
            },
            relatives: {
                '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] },
            },
            children: {
                '@FOCUS@': ['@CHILD1@', '@CHILD2@'],
            },
            families: {
                '@FAM@': { husb: '@FOCUS@', wife: '@SPOUSE@', chil: ['@CHILD1@', '@CHILD2@'] },
            },
        });
    });

    it('each child appears exactly once when focusXref is in expandedChildrenPersons', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@FOCUS@']));
        const child1Nodes = nodes.filter(n => n.xref === '@CHILD1@');
        const child2Nodes = nodes.filter(n => n.xref === '@CHILD2@');
        expect(child1Nodes).toHaveLength(1);
        expect(child2Nodes).toHaveLength(1);
    });

    it('children appear at y=+ROW_HEIGHT (not doubled)', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@FOCUS@']));
        const child1 = nodes.find(n => n.xref === '@CHILD1@');
        expect(child1.y).toBe(ROW_HEIGHT);
    });

    it('without focusXref in expandedChildrenPersons children still appear once', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set());
        const child1Nodes = nodes.filter(n => n.xref === '@CHILD1@');
        expect(child1Nodes).toHaveLength(1);
    });
});

describe('computeLayout — expandedChildrenPersons: aunt\'s kids (cousins)', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@MOTHER@': { birth_year: 1875 },
                '@AUNT@': { birth_year: 1870 },
                '@C1@': { birth_year: 1895 },
                '@C2@': { birth_year: 1898 },
            },
            parents: {
                '@FOCUS@': [null, '@MOTHER@'],
            },
            relatives: {
                '@MOTHER@': { siblings: ['@AUNT@'], spouses: [] },
            },
            families: {
                '@AFAM@': { husb: null, wife: '@AUNT@', chil: ['@C1@', '@C2@'] },
            },
        });
    });

    it('cousins appear at y=0 (focus row) when aunt\'s FAM is expanded and mother\'s siblings are expanded', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']), new Set(['@AUNT@']));
        const c1 = nodes.find(n => n.xref === '@C1@');
        expect(c1).toBeDefined();
        expect(c1.y).toBe(0);
        expect(c1.generation).toBe(0);
    });
});

// ── Stage A: cousin spacing via descendant-aware contours ──────────────────

// Regression for cousin-overlap bug: when two siblings on the same row both
// expand their children, the default SLOT-based packing lets the cousins run
// into each other. Packing must reserve enough horizontal space for each
// sibling's descendant subtree.

describe('computeLayout — two focus-siblings with expanded kids: no cousin overlap', () => {
    beforeEach(() => {
        // FOCUS has two older sisters, SIB_A and SIB_B.
        // SIB_A has 3 children (A1..A3), SIB_B has 3 children (B1..B3).
        // Both sibling FAMs are expanded. Cousin rows must not overlap.
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SIB_A@': { birth_year: 1895 },
                '@SIB_B@': { birth_year: 1896 },
                '@A1@': { birth_year: 1920 },
                '@A2@': { birth_year: 1922 },
                '@A3@': { birth_year: 1924 },
                '@B1@': { birth_year: 1921 },
                '@B2@': { birth_year: 1923 },
                '@B3@': { birth_year: 1925 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@SIB_A@', '@SIB_B@'], spouses: [] },
            },
            families: {
                '@FAM_A@': { husb: '@SIB_A@', wife: null, chil: ['@A1@', '@A2@', '@A3@'] },
                '@FAM_B@': { husb: '@SIB_B@', wife: null, chil: ['@B1@', '@B2@', '@B3@'] },
            },
        });
    });

    it('sibling pills themselves do not overlap', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@SIB_A@', '@SIB_B@']));
        const a = nodes.find(n => n.xref === '@SIB_A@');
        const b = nodes.find(n => n.xref === '@SIB_B@');
        expect(a).toBeDefined();
        expect(b).toBeDefined();
        const [left, right] = a.x < b.x ? [a, b] : [b, a];
        expect(right.x - (left.x + NODE_W)).toBeGreaterThanOrEqual(H_GAP);
    });

    it('rightmost child of left sibling does not overlap leftmost child of right sibling', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@SIB_A@', '@SIB_B@']));
        // SIB_A is placed left of SIB_B by birth-year sort (1895 < 1896).
        const a3 = nodes.find(n => n.xref === '@A3@'); // rightmost child of SIB_A
        const b1 = nodes.find(n => n.xref === '@B1@'); // leftmost child of SIB_B
        expect(a3).toBeDefined();
        expect(b1).toBeDefined();
        expect(b1.x - (a3.x + NODE_W)).toBeGreaterThanOrEqual(H_GAP);
    });
});

describe('computeLayout — two ancestor-siblings with expanded kids: no cousin overlap', () => {
    beforeEach(() => {
        // Focus's mother has two sisters (aunts). Each aunt has 3 kids.
        // Mother's siblings are expanded; both aunts' FAMs are expanded.
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@MOTHER@': { birth_year: 1875, sex: 'F' },
                '@AUNT_A@': { birth_year: 1870, sex: 'F' },
                '@AUNT_B@': { birth_year: 1872, sex: 'F' },
                '@CA1@': { birth_year: 1895 },
                '@CA2@': { birth_year: 1897 },
                '@CA3@': { birth_year: 1899 },
                '@CB1@': { birth_year: 1896 },
                '@CB2@': { birth_year: 1898 },
                '@CB3@': { birth_year: 1900 },
            },
            parents: {
                '@FOCUS@': [null, '@MOTHER@'],
            },
            relatives: {
                '@MOTHER@': { siblings: ['@AUNT_A@', '@AUNT_B@'], spouses: [] },
            },
            families: {
                '@FAM_A@': { husb: null, wife: '@AUNT_A@', chil: ['@CA1@', '@CA2@', '@CA3@'] },
                '@FAM_B@': { husb: null, wife: '@AUNT_B@', chil: ['@CB1@', '@CB2@', '@CB3@'] },
            },
        });
    });

    it('aunt pills themselves do not overlap', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']), new Set(['@AUNT_A@', '@AUNT_B@']));
        const a = nodes.find(n => n.xref === '@AUNT_A@');
        const b = nodes.find(n => n.xref === '@AUNT_B@');
        expect(a).toBeDefined();
        expect(b).toBeDefined();
        const [left, right] = a.x < b.x ? [a, b] : [b, a];
        expect(right.x - (left.x + NODE_W)).toBeGreaterThanOrEqual(H_GAP);
    });

    it('no two cousins on focus row overlap', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']), new Set(['@AUNT_A@', '@AUNT_B@']));
        const cousins = nodes.filter(n => /^@C[AB]\d@$/.test(n.xref));
        expect(cousins.length).toBe(6);
        const sorted = cousins.slice().sort((x, y) => x.x - y.x);
        for (let i = 1; i < sorted.length; i++) {
            const gap = sorted[i].x - (sorted[i - 1].x + NODE_W);
            expect(gap, `${sorted[i - 1].xref} → ${sorted[i].xref}`).toBeGreaterThanOrEqual(0);
        }
    });
});

describe('computeLayout — single sibling with many expanded kids: pill itself stays adjacent to focus', () => {
    beforeEach(() => {
        // Regression: when a single sibling has many expanded kids, the sibling pill
        // itself must still sit adjacent to focus (not get pushed away). Only the
        // children get spaced out — the sibling pill is placed at the default slot.
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1900 },
                '@SIB@': { birth_year: 1895 },
                '@K1@': { birth_year: 1920 },
                '@K2@': { birth_year: 1922 },
                '@K3@': { birth_year: 1924 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@SIB@'], spouses: [] },
            },
            families: {
                '@FAM@': { husb: '@SIB@', wife: null, chil: ['@K1@', '@K2@', '@K3@'] },
            },
        });
    });

    it('lone older sibling with 3 expanded kids sits at x = -FOCUS_TO_SIB (not pushed further left)', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(['@SIB@']));
        const sib = nodes.find(n => n.xref === '@SIB@');
        expect(sib.x).toBe(-FOCUS_TO_SIB);
    });
});

// Regression for the Ana-Maria-vs-Andrea collision from user screenshot:
// an ancestor-sibling at gen -2 whose expanded-FAM children land on gen -1
// must not overlap nodes already placed on gen -1 (like the focus parent's
// own ancestor-siblings).
describe('computeLayout — cross-generation: great-aunt\'s kids vs aunt+spouse', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1995, sex: 'M' },
                '@DAD@': { birth_year: 1965, sex: 'M' },
                '@MOM@': { birth_year: 1963, sex: 'F' },
                '@AUNT@': { birth_year: 1966, sex: 'F' },
                '@AUNT_SP@': { birth_year: 1964, sex: 'M' },
                '@GF@': { birth_year: 1926, sex: 'M' },
                '@GM@': { birth_year: 1941, sex: 'F' },
                '@GA@': { birth_year: 1938, sex: 'F' },        // great-aunt
                '@GA_SP@': { birth_year: 1932, sex: 'M' },
                '@CUZ1@': { birth_year: 1958, sex: 'M' },      // great-aunt's kids at gen -1
                '@CUZ2@': { birth_year: 1960, sex: 'M' },
                '@CUZ3@': { birth_year: 1963, sex: 'F' },
            },
            parents: {
                '@FOCUS@': ['@DAD@', '@MOM@'],
                '@MOM@': ['@GF@', '@GM@'],
            },
            relatives: {
                '@MOM@': { siblings: ['@AUNT@'], spouses: ['@DAD@'] },
                '@AUNT@': { siblings: [], spouses: ['@AUNT_SP@'] },
                '@GM@': { siblings: ['@GA@'], spouses: ['@GF@'] },
                '@GA@': { siblings: [], spouses: ['@GA_SP@'] },
            },
            families: {
                '@GA_FAM@': { husb: '@GA_SP@', wife: '@GA@', chil: ['@CUZ1@', '@CUZ2@', '@CUZ3@'] },
            },
        });
    });

    it('no two gen -1 nodes overlap when both @MOM@ siblings and great-aunt FAM are expanded', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(['@MOM@']),
            new Set(['@MOM@', '@GM@']),
            new Set(['@GA@']),
        );
        const gen1 = nodes.filter(n => n.generation === -1).sort((a, b) => a.x - b.x);
        for (let i = 1; i < gen1.length; i++) {
            const gap = gen1[i].x - (gen1[i - 1].x + NODE_W);
            expect(gap, `${gen1[i - 1].xref} (x=${gen1[i - 1].x}) → ${gen1[i].xref} (x=${gen1[i].x})`)
                .toBeGreaterThanOrEqual(0);
        }
    });
});

// Mirror of Ana-Maria case on the father's side: great-uncle (father's
// father's brother) with expanded kids collides with uncle+spouse when both
// are on gen -1.
describe('computeLayout — cross-generation mirror: father-side great-uncle vs uncle+spouse', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1995, sex: 'M' },
                '@DAD@': { birth_year: 1965, sex: 'M' },
                '@MOM@': { birth_year: 1967, sex: 'F' },
                '@UNCLE@': { birth_year: 1963, sex: 'M' },
                '@UNCLE_SP@': { birth_year: 1965, sex: 'F' },
                '@PGF@': { birth_year: 1935, sex: 'M' },
                '@PGM@': { birth_year: 1937, sex: 'F' },
                '@GU@': { birth_year: 1930, sex: 'M' }, // great-uncle (PGF's brother)
                '@GU_SP@': { birth_year: 1932, sex: 'F' },
                '@CUZ1@': { birth_year: 1958, sex: 'M' },
                '@CUZ2@': { birth_year: 1960, sex: 'F' },
                '@CUZ3@': { birth_year: 1962, sex: 'M' },
            },
            parents: {
                '@FOCUS@': ['@DAD@', '@MOM@'],
                '@DAD@': ['@PGF@', '@PGM@'],
            },
            relatives: {
                '@DAD@': { siblings: ['@UNCLE@'], spouses: ['@MOM@'] },
                '@UNCLE@': { siblings: [], spouses: ['@UNCLE_SP@'] },
                '@PGF@': { siblings: ['@GU@'], spouses: ['@PGM@'] },
                '@GU@': { siblings: [], spouses: ['@GU_SP@'] },
            },
            families: {
                '@GU_FAM@': { husb: '@GU@', wife: '@GU_SP@', chil: ['@CUZ1@', '@CUZ2@', '@CUZ3@'] },
            },
        });
    });

    it('no two gen -1 nodes overlap (father-side mirror)', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(['@DAD@']),
            new Set(['@DAD@', '@PGF@']),
            new Set(['@GU@']),
        );
        const gen1 = nodes.filter(n => n.generation === -1).sort((a, b) => a.x - b.x);
        for (let i = 1; i < gen1.length; i++) {
            const gap = gen1[i].x - (gen1[i - 1].x + NODE_W);
            expect(gap, `${gen1[i - 1].xref} (x=${gen1[i - 1].x}) → ${gen1[i].xref} (x=${gen1[i].x})`)
                .toBeGreaterThanOrEqual(0);
        }
    });
});

// Aunt (ancestor-sibling at gen -1) with expanded FAM: her kids land at
// gen 0 — the FOCUS row. They must not collide with focus, focus's siblings,
// focus's spouse, or focus's spouse's siblings.
describe('computeLayout — aunt\'s kids on focus row vs focus+spouse+siblings', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1995, sex: 'F' },
                '@FSIB@': { birth_year: 1997, sex: 'F' }, // focus sibling
                '@SPOUSE@': { birth_year: 1994, sex: 'M' },
                '@MOM@': { birth_year: 1965, sex: 'F' },
                '@AUNT@': { birth_year: 1963, sex: 'F' }, // MOM's sister
                '@AUNT_SP@': { birth_year: 1961, sex: 'M' },
                '@CUZ1@': { birth_year: 1990, sex: 'F' },
                '@CUZ2@': { birth_year: 1992, sex: 'M' },
                '@CUZ3@': { birth_year: 1994, sex: 'F' },
            },
            parents: {
                '@FOCUS@': [null, '@MOM@'],
                '@FSIB@': [null, '@MOM@'],
            },
            relatives: {
                '@FOCUS@': { siblings: ['@FSIB@'], spouses: ['@SPOUSE@'] },
                '@MOM@': { siblings: ['@AUNT@'], spouses: [] },
                '@AUNT@': { siblings: [], spouses: ['@AUNT_SP@'] },
            },
            families: {
                '@AUNT_FAM@': { husb: '@AUNT_SP@', wife: '@AUNT@', chil: ['@CUZ1@', '@CUZ2@', '@CUZ3@'] },
            },
        });
    });

    it('no two gen 0 nodes overlap when aunt\'s FAM is expanded', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(),
            new Set(['@MOM@']),
            new Set(['@AUNT@']),
        );
        const gen0 = nodes.filter(n => n.generation === 0).sort((a, b) => a.x - b.x);
        for (let i = 1; i < gen0.length; i++) {
            const gap = gen0[i].x - (gen0[i - 1].x + NODE_W);
            expect(gap, `${gen0[i - 1].xref} (x=${gen0[i - 1].x}) → ${gen0[i].xref} (x=${gen0[i].x})`)
                .toBeGreaterThanOrEqual(0);
        }
    });
});

// Nested cousin subtrees: sibling A's child has 3 kids, sibling B has 3 kids.
// Grand-cousin row at gen +2 must not overlap between the two sibling
// subtrees, even when the intermediate cousin row at gen +1 already clears.
describe('computeLayout — nested: sibling-A\'s grandkids vs sibling-B\'s kids', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000, sex: 'F' },
                '@SIB_A@': { birth_year: 1990, sex: 'F' },
                '@SIB_B@': { birth_year: 1995, sex: 'F' },
                '@A_KID1@': { birth_year: 2015, sex: 'F' },
                '@A_KID2@': { birth_year: 2017, sex: 'M' },
                '@A_GK1@': { birth_year: 2040, sex: 'F' },
                '@A_GK2@': { birth_year: 2042, sex: 'M' },
                '@A_GK3@': { birth_year: 2044, sex: 'F' },
                '@B_KID1@': { birth_year: 2016, sex: 'M' },
                '@B_KID2@': { birth_year: 2018, sex: 'F' },
                '@B_KID3@': { birth_year: 2020, sex: 'M' },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@SIB_A@', '@SIB_B@'], spouses: [] },
            },
            families: {
                '@FAM_A@': { husb: null, wife: '@SIB_A@', chil: ['@A_KID1@', '@A_KID2@'] },
                '@FAM_A2@': { husb: null, wife: '@A_KID2@', chil: ['@A_GK1@', '@A_GK2@', '@A_GK3@'] },
                '@FAM_B@': { husb: null, wife: '@SIB_B@', chil: ['@B_KID1@', '@B_KID2@', '@B_KID3@'] },
            },
        });
    });

    it('no two nodes overlap at gen +1 or +2 across both sibling subtrees', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(),
            new Set(),
            new Set(['@SIB_A@', '@A_KID2@', '@SIB_B@']),
        );
        for (const gen of [1, 2]) {
            const row = nodes.filter(n => n.generation === gen).sort((a, b) => a.x - b.x);
            for (let i = 1; i < row.length; i++) {
                const gap = row[i].x - (row[i - 1].x + NODE_W);
                expect(gap, `gen ${gen}: ${row[i - 1].xref} (x=${row[i - 1].x}) → ${row[i].xref} (x=${row[i].x})`)
                    .toBeGreaterThanOrEqual(0);
            }
        }
    });
});

// Same-person, two expanded FAMs (will matter for Stage B / multi-spouse).
// Even pre-Stage-B, the layout should not crash or overlap when a person
// is a parent in two FAMs both in expandedChildrenPersons.
describe('computeLayout — one sibling, two expanded FAMs (multi-marriage)', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1995 },
                '@SIB@': { birth_year: 1990, sex: 'M' },
                '@K1@': { birth_year: 2015 },
                '@K2@': { birth_year: 2017 },
                '@K3@': { birth_year: 2019 },
                '@K4@': { birth_year: 2021 },
            },
            relatives: {
                '@FOCUS@': { siblings: ['@SIB@'], spouses: [] },
            },
            families: {
                '@FAM1@': { husb: '@SIB@', wife: null, chil: ['@K1@', '@K3@'] },
                '@FAM2@': { husb: '@SIB@', wife: null, chil: ['@K2@', '@K4@'] },
            },
        });
    });

    it('kids from both FAMs land at gen +1 without overlap', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(), new Set(),
            new Set(['@SIB@']),
        );
        const gen1 = nodes.filter(n => n.generation === 1).sort((a, b) => a.x - b.x);
        for (let i = 1; i < gen1.length; i++) {
            const gap = gen1[i].x - (gen1[i - 1].x + NODE_W);
            expect(gap).toBeGreaterThanOrEqual(0);
        }
    });

    // Regression: with two FAMs under the same person, siblings from each FAM
    // must be visually segregated — no cross-FAM interleaving by birth year.
    // FAM1's kids should be contiguous, FAM2's kids should be contiguous,
    // with a visible gap (larger than normal sibling spacing) between them.
    it('kids stay grouped by FAM (no birth-year interleaving across FAMs)', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(), new Set(),
            new Set(['@SIB@']),
        );
        const gen1 = nodes.filter(n => n.generation === 1).sort((a, b) => a.x - b.x);
        const xrefs = gen1.map(n => n.xref);
        // K1, K2 are one FAM; K3, K4 another. Each FAM's kids must be adjacent
        // in the horizontal ordering. Two valid orderings: [K1,K2,K3,K4] or
        // [K3,K4,K1,K2]. Forbidden: anything like [K1,K3,K2,K4].
        const famA = new Set(['@K1@', '@K3@']);
        const famB = new Set(['@K2@', '@K4@']);
        let transitions = 0;
        for (let i = 1; i < xrefs.length; i++) {
            const prevFam = famA.has(xrefs[i - 1]) ? 'A' : 'B';
            const curFam = famA.has(xrefs[i]) ? 'A' : 'B';
            if (prevFam !== curFam) transitions++;
        }
        expect(transitions).toBe(1);
    });

    it('visible gap between FAM groups is larger than gap within a FAM', () => {
        // Place @SIB@ with a visible spouse via defaultSpouses so one FAM is
        // the "visible" one. Here, SIB has no spouse in RELATIVES but both
        // FAMs have wife: null, so visible FAM is the first by iteration;
        // we only assert the cross-FAM gap is strictly larger than the
        // within-FAM gap.
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(), new Set(),
            new Set(['@SIB@']),
        );
        const gen1 = nodes.filter(n => n.generation === 1).sort((a, b) => a.x - b.x);
        const gaps = [];
        for (let i = 1; i < gen1.length; i++) {
            gaps.push(gen1[i].x - (gen1[i - 1].x + NODE_W));
        }
        // One gap (the cross-FAM one) must be strictly larger than the others.
        const maxGap = Math.max(...gaps);
        const others = gaps.filter(g => g !== maxGap);
        expect(others.every(g => g < maxGap)).toBe(true);
    });
});

// Deep cross-generation: great-great-aunt (gen -3) with expanded FAM
// dropping kids to gen -2 where great-aunt already sits.
describe('computeLayout — deep cross-gen: g-g-aunt FAM vs g-aunt', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 2000 },
                '@MOM@': { birth_year: 1970, sex: 'F' },
                '@GM@': { birth_year: 1945, sex: 'F' },
                '@GA@': { birth_year: 1940, sex: 'F' }, // GM's sister (great-aunt)
                '@GA_SP@': { birth_year: 1938, sex: 'M' },
                '@GGM@': { birth_year: 1920, sex: 'F' }, // GM's mother
                '@GGA@': { birth_year: 1915, sex: 'F' }, // GGM's sister (g-g-aunt)
                '@GGA_SP@': { birth_year: 1913, sex: 'M' },
                '@GA_COUSIN1@': { birth_year: 1935, sex: 'F' }, // GGA's kids at gen -2
                '@GA_COUSIN2@': { birth_year: 1937, sex: 'M' },
                '@GA_COUSIN3@': { birth_year: 1939, sex: 'F' },
            },
            parents: {
                '@FOCUS@': [null, '@MOM@'],
                '@MOM@': [null, '@GM@'],
                '@GM@': [null, '@GGM@'],
            },
            relatives: {
                '@GM@': { siblings: ['@GA@'], spouses: [] },
                '@GA@': { siblings: [], spouses: ['@GA_SP@'] },
                '@GGM@': { siblings: ['@GGA@'], spouses: [] },
                '@GGA@': { siblings: [], spouses: ['@GGA_SP@'] },
            },
            families: {
                '@GGA_FAM@': { husb: '@GGA_SP@', wife: '@GGA@', chil: ['@GA_COUSIN1@', '@GA_COUSIN2@', '@GA_COUSIN3@'] },
            },
        });
    });

    it('gen -2 nodes do not overlap when GGA\'s FAM is expanded and GM\'s siblings are shown', () => {
        const { nodes } = computeLayout(
            '@FOCUS@',
            new Set(['@MOM@', '@GM@']),
            new Set(['@GM@', '@GGM@']),
            new Set(['@GGA@']),
        );
        const gen2 = nodes.filter(n => n.generation === -2).sort((a, b) => a.x - b.x);
        for (let i = 1; i < gen2.length; i++) {
            const gap = gen2[i].x - (gen2[i - 1].x + NODE_W);
            expect(gap, `${gen2[i - 1].xref} (x=${gen2[i - 1].x}) → ${gen2[i].xref} (x=${gen2[i].x})`)
                .toBeGreaterThanOrEqual(0);
        }
    });
});

describe('computeLayout — multi-spouse filtering', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1990 },
                '@SP_A@': { birth_year: 1991 },
                '@SP_B@': { birth_year: 1992 },
            },
            parents: { '@FOCUS@': [null, null] },
            children: {},
            relatives: { '@FOCUS@': { spouses: ['@SP_A@', '@SP_B@'] } },
            families: {
                '@F_A@': { husb: '@FOCUS@', wife: '@SP_A@', chil: [], marr_year: 2010 },
                '@F_B@': { husb: '@FOCUS@', wife: '@SP_B@', chil: [], marr_year: 2020 },
            },
        });
    });

    it('default (empty visibleSpouseFams) shows only the primary spouse', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set());
        const spouseNodes = nodes.filter(n => n.role === 'spouse');
        expect(spouseNodes).toHaveLength(1);
        expect(spouseNodes[0].xref).toBe('@SP_A@');
    });

    it('with both FAMs in visibleSpouseFams, both spouses render', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set(['@F_A@', '@F_B@']));
        const spouseNodes = nodes.filter(n => n.role === 'spouse');
        expect(spouseNodes.map(n => n.xref).sort()).toEqual(['@SP_A@', '@SP_B@']);
    });

    it('with only non-primary FAM in visibleSpouseFams, only that spouse renders', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set(['@F_B@']));
        const spouseNodes = nodes.filter(n => n.role === 'spouse');
        expect(spouseNodes).toHaveLength(1);
        expect(spouseNodes[0].xref).toBe('@SP_B@');
    });

    it('when both spouses visible, one is placed left of focus and one right', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set(['@F_A@', '@F_B@']));
        const spouseNodes = nodes.filter(n => n.role === 'spouse');
        expect(spouseNodes).toHaveLength(2);
        const xs = spouseNodes.map(n => n.x).sort((a, b) => a - b);
        expect(xs[0]).toBeLessThan(0);
        expect(xs[1]).toBeGreaterThan(0);
    });

    it('when both spouses visible, there is a marriage edge on both sides of focus', () => {
        const { edges } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set(['@F_A@', '@F_B@']));
        const marriages = edges.filter(e => e.type === 'marriage');
        // Right edge starts at focus center (NODE_W_FOCUS/2); left edge ends at focus center too.
        const { NODE_W_FOCUS } = DESIGN;
        const leftSideEdge = marriages.find(e => Math.abs(e.x2 - (NODE_W_FOCUS / 2)) < 0.5);
        const rightSideEdge = marriages.find(e => Math.abs(e.x1 - (NODE_W_FOCUS / 2)) < 0.5);
        expect(leftSideEdge).toBeDefined();
        expect(rightSideEdge).toBeDefined();
    });

    it('person with 1 FAM always shows their spouse regardless of set', () => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1990 },
                '@SP_A@': { birth_year: 1991 },
            },
            parents: { '@FOCUS@': [null, null] },
            children: {},
            relatives: { '@FOCUS@': { spouses: ['@SP_A@'] } },
            families: {
                '@F_A@': { husb: '@FOCUS@', wife: '@SP_A@', chil: [], marr_year: 2010 },
            },
        });
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(), new Set(), new Set());
        expect(nodes.filter(n => n.role === 'spouse')).toHaveLength(1);
    });
});

// ── Regression: _placeChildrenOfPerson collision avoidance must iterate past
//    multiple adjacent obstacle pills (the Aime Joseph Bonnici screenshot bug).
//
// The buggy two-step push was: push past initially-overlapped pills; if still
// overlapping, push once more past the second-pass overlapping pills — with
// NO further re-check. When the second push still lands on yet another pill
// (a third obstacle further right), the span is placed on top of that pill.
// The fix replaces this with a gap-finding pass that guarantees clearance.

describe('_placeChildrenOfPerson — iterative collision avoidance', () => {
    it('kids land in a gap that clears ALL existing pills on the child row', () => {
        // Anchor person PARENT at x=0, y=0 so kids target childY = ROW_HEIGHT,
        // centered on PARENT (anchorX=50, totalWidth for 3 kids = 324, so
        // naive startX = 50 - 162 = -112).
        //
        // Existing pills on childY form a chain of H_GAP-adjacent obstacles:
        //   P1 @ x=-100..0     (blocks naive startX)
        //   P2 @ x=12..112     (blocks first right-push to maxRight+H_GAP=112)
        //   P3 @ x=124..224    (blocks second push to 224 — the buggy 2nd push
        //                       lands startX=224, end=548, overlapping P3)
        //   P4 @ x=236..336    (still blocks after P3; requires further iter)
        //
        // The fix picks a gap large enough for the 324-wide span and places it
        // there with no overlap; the buggy code drops kids on top of P3 or P4.
        resetGlobals({
            people: {
                '@PARENT@': { birth_year: 1900 },
                '@K1@': { birth_year: 1930 },
                '@K2@': { birth_year: 1932 },
                '@K3@': { birth_year: 1934 },
            },
            families: {
                '@PFAM@': { husb: '@PARENT@', wife: null, chil: ['@K1@', '@K2@', '@K3@'] },
            },
            relatives: { '@PARENT@': { spouses: [], siblings: [] } },
        });

        // P0 blocks leftward pushes (so the code picks rightward). P1..P4 are
        // adjacent with H_GAP; P5 sits further right in the exact window that
        // the buggy two-pass push lands on after push #2. P5 does NOT overlap
        // the push-#1 startX (so maxRight2 ignores it), but DOES overlap the
        // push-#2 startX — a third push is required.
        const nodes = [
            { xref: '@PARENT@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@P0@', x: -500, y: ROW_HEIGHT, generation: 1, role: 'descendant' },
            { xref: '@P1@', x: -100, y: ROW_HEIGHT, generation: 1, role: 'descendant' },
            { xref: '@P2@', x: -100 + NODE_W + H_GAP, y: ROW_HEIGHT, generation: 1, role: 'descendant' },
            { xref: '@P3@', x: -100 + 2 * (NODE_W + H_GAP), y: ROW_HEIGHT, generation: 1, role: 'descendant' },
            { xref: '@P4@', x: -100 + 3 * (NODE_W + H_GAP), y: ROW_HEIGHT, generation: 1, role: 'descendant' },
            { xref: '@P5@', x: 580, y: ROW_HEIGHT, generation: 1, role: 'descendant' },
        ];
        const edges = [];

        _placeChildrenOfPerson('@PARENT@', new Set(), '@PARENT@', nodes, edges);

        const row = nodes.filter(n => n.y === ROW_HEIGHT);
        for (let i = 0; i < row.length; i++) {
            for (let j = i + 1; j < row.length; j++) {
                const a = row[i];
                const b = row[j];
                const overlap = a.x < b.x + NODE_W && a.x + NODE_W > b.x;
                expect(overlap, `${a.xref}@${a.x} overlaps ${b.xref}@${b.x}`).toBe(false);
            }
        }
    });
});

// ── Regression: co-spouse placement in focus row ───────────────────────────
//
// When the focus is Josephina and Michele is her spouse, and the user enables
// Maria Elena via Michele's multi-spouse toggle, Maria Elena must be placed in
// the focus row to the right of Michele. Before the fix, Maria Elena was never
// placed in the layout.
describe('computeLayout — co-spouse placement in focus row', () => {
    function setupJosephinaScene() {
        resetGlobals({
            people: {
                '@Josephina@': { birth_year: 1900 },
                '@Michele@': { birth_year: 1898 },
                '@MariaElena@': { birth_year: 1895 },
            },
            parents: { '@Josephina@': [null, null], '@Michele@': [null, null], '@MariaElena@': [null, null] },
            children: {},
            relatives: {
                '@Josephina@': { siblings: [], spouses: ['@Michele@'] },
                '@Michele@': { siblings: [], spouses: ['@Josephina@', '@MariaElena@'] },
                '@MariaElena@': { siblings: [], spouses: ['@Michele@'] },
            },
            families: {
                '@F_JM@': { husb: '@Michele@', wife: '@Josephina@', chil: [], marr_year: 1920 },
                '@F_MM@': { husb: '@Michele@', wife: '@MariaElena@', chil: [], marr_year: 1915 },
            },
        });
    }

    it('with no visibleSpouseFams Michele appears but MariaElena does not (Rule 0: Josephina is primary)', () => {
        setupJosephinaScene();
        const { nodes } = computeLayout('@Josephina@', new Set(), new Set(), new Set(), new Set());
        const spouseNodes = nodes.filter(n => n.role === 'spouse');
        expect(spouseNodes.map(n => n.xref)).toContain('@Michele@');
        expect(spouseNodes.map(n => n.xref)).not.toContain('@MariaElena@');
    });

    it('with Michele-MariaElena FAM in visibleSpouseFams, MariaElena is placed to the right of Michele', () => {
        setupJosephinaScene();
        const { nodes } = computeLayout(
            '@Josephina@', new Set(), new Set(), new Set(),
            new Set(['@F_JM@', '@F_MM@']),
        );
        const micheleNode = nodes.find(n => n.xref === '@Michele@');
        const mariaNode = nodes.find(n => n.xref === '@MariaElena@');
        expect(micheleNode).toBeDefined();
        expect(mariaNode).toBeDefined();
        expect(mariaNode.y).toBe(0);
        expect(mariaNode.x).toBeGreaterThan(micheleNode.x);
    });

    it('with Michele-MariaElena FAM selected, a marriage edge connects Michele to MariaElena', () => {
        setupJosephinaScene();
        const { edges } = computeLayout(
            '@Josephina@', new Set(), new Set(), new Set(),
            new Set(['@F_JM@', '@F_MM@']),
        );
        const marriageEdges = edges.filter(e => e.type === 'marriage');
        // There must be an edge that starts at Michele's right edge and ends at MariaElena's left edge.
        const micheleRightX = DESIGN.NODE_W_FOCUS / 2 + DESIGN.MARRIAGE_GAP + DESIGN.NODE_W / 2 + DESIGN.NODE_W;
        const coEdge = marriageEdges.find(e => Math.abs(e.x1 - micheleRightX) < 0.5);
        expect(coEdge).toBeDefined();
    });

    it('with only Michele-MariaElena FAM selected (not Josephina FAM), MariaElena still appears', () => {
        setupJosephinaScene();
        const { nodes } = computeLayout(
            '@Josephina@', new Set(), new Set(), new Set(),
            new Set(['@F_MM@']),
        );
        const mariaNode = nodes.find(n => n.xref === '@MariaElena@');
        expect(mariaNode).toBeDefined();
    });

    it('co-spouse placement does not affect younger-sibling start position (no overlap)', () => {
        resetGlobals({
            people: {
                '@Josephina@': { birth_year: 1900 },
                '@Michele@': { birth_year: 1898 },
                '@MariaElena@': { birth_year: 1895 },
                '@YoungSib@': { birth_year: 1905 },
            },
            parents: {
                '@Josephina@': [null, null],
                '@Michele@': [null, null],
                '@MariaElena@': [null, null],
                '@YoungSib@': [null, null],
            },
            children: {},
            relatives: {
                '@Josephina@': { siblings: ['@YoungSib@'], spouses: ['@Michele@'] },
                '@Michele@': { siblings: [], spouses: ['@Josephina@', '@MariaElena@'] },
                '@MariaElena@': { siblings: [], spouses: ['@Michele@'] },
                '@YoungSib@': { siblings: ['@Josephina@'], spouses: [] },
            },
            families: {
                '@F_JM@': { husb: '@Michele@', wife: '@Josephina@', chil: [], marr_year: 1920 },
                '@F_MM@': { husb: '@Michele@', wife: '@MariaElena@', chil: [], marr_year: 1915 },
            },
        });
        const { nodes } = computeLayout(
            '@Josephina@', new Set(), new Set(), new Set(),
            new Set(['@F_JM@', '@F_MM@']),
        );
        const row0 = nodes.filter(n => n.y === 0);
        for (let i = 0; i < row0.length; i++) {
            for (let j = i + 1; j < row0.length; j++) {
                const a = row0[i];
                const b = row0[j];
                const wa = a.role === 'focus' ? DESIGN.NODE_W_FOCUS : DESIGN.NODE_W;
                const overlap = a.x < b.x + DESIGN.NODE_W && a.x + wa > b.x;
                expect(overlap, `${a.xref}@${a.x} overlaps ${b.xref}@${b.x}`).toBe(false);
            }
        }
    });
});

// ── Regression: focus-row siblings must show their spouses ───────────────────
//
// Bug: _packRowWithDescendants only placed sibling nodes; no spouse nodes were
// added. Giacomo's wife never appeared in the focus row next to him.
// Fix: after packing, post-process each sibling to insert their visible spouse(s)
// and shift subsequent siblings to avoid overlap.
describe('computeLayout — focus-row sibling spouse placement', () => {
    function setupSiblingWithSpouse() {
        // Michele is focus; Giacomo is a younger sibling who has a wife (Rosa).
        resetGlobals({
            people: {
                '@Michele@': { birth_year: 1870 },
                '@Giacomo@': { birth_year: 1876 },
                '@Rosa@': { birth_year: 1880 },
                '@Nicola@': { birth_year: 1878 },
            },
            parents: {
                '@Michele@': [null, null],
                '@Giacomo@': [null, null],
                '@Rosa@': [null, null],
                '@Nicola@': [null, null],
            },
            children: {},
            relatives: {
                '@Michele@': { siblings: ['@Giacomo@', '@Nicola@'], spouses: [] },
                '@Giacomo@': { siblings: ['@Michele@', '@Nicola@'], spouses: ['@Rosa@'] },
                '@Rosa@': { siblings: [], spouses: ['@Giacomo@'] },
                '@Nicola@': { siblings: ['@Michele@', '@Giacomo@'], spouses: [] },
            },
            families: {
                '@F_GR@': { husb: '@Giacomo@', wife: '@Rosa@', chil: [], marr_year: 1900 },
            },
        });
    }

    it('Giacomo\'s wife Rosa appears in the focus row', () => {
        setupSiblingWithSpouse();
        const { nodes } = computeLayout('@Michele@', new Set(), new Set(), new Set(), new Set());
        const rosaNode = nodes.find(n => n.xref === '@Rosa@');
        expect(rosaNode).toBeDefined();
        expect(rosaNode.y).toBe(0);
    });

    it('Rosa is placed to the right of Giacomo', () => {
        setupSiblingWithSpouse();
        const { nodes } = computeLayout('@Michele@', new Set(), new Set(), new Set(), new Set());
        const giacomoNode = nodes.find(n => n.xref === '@Giacomo@');
        const rosaNode = nodes.find(n => n.xref === '@Rosa@');
        expect(rosaNode.x).toBeGreaterThan(giacomoNode.x + NODE_W);
    });

    it('a marriage edge connects Giacomo to Rosa', () => {
        setupSiblingWithSpouse();
        const { nodes, edges } = computeLayout('@Michele@', new Set(), new Set(), new Set(), new Set());
        const giacomoNode = nodes.find(n => n.xref === '@Giacomo@');
        const marriageEdge = edges.find(e =>
            e.type === 'marriage' && Math.abs(e.x1 - (giacomoNode.x + NODE_W)) < 0.5
        );
        expect(marriageEdge).toBeDefined();
    });

    it('Nicola is shifted right of Rosa with no overlap', () => {
        setupSiblingWithSpouse();
        const { nodes } = computeLayout('@Michele@', new Set(), new Set(), new Set(), new Set());
        const rosaNode = nodes.find(n => n.xref === '@Rosa@');
        const nicolaNode = nodes.find(n => n.xref === '@Nicola@');
        expect(nicolaNode.x).toBeGreaterThan(rosaNode.x + NODE_W);
    });

    it('focus row has no overlapping nodes', () => {
        setupSiblingWithSpouse();
        const { nodes } = computeLayout('@Michele@', new Set(), new Set(), new Set(), new Set());
        const row0 = nodes.filter(n => n.y === 0);
        for (let i = 0; i < row0.length; i++) {
            for (let j = i + 1; j < row0.length; j++) {
                const a = row0[i];
                const b = row0[j];
                const wa = a.role === 'focus' ? NODE_W_FOCUS : NODE_W;
                expect(
                    a.x < b.x + NODE_W && a.x + wa > b.x,
                    `${a.xref}@${a.x} overlaps ${b.xref}@${b.x}`,
                ).toBe(false);
            }
        }
    });

    it('sibling with no spouse is not affected', () => {
        setupSiblingWithSpouse();
        const { nodes } = computeLayout('@Michele@', new Set(), new Set(), new Set(), new Set());
        const nicolaNode = nodes.find(n => n.xref === '@Nicola@');
        // Nicola has no spouse — no spouse node should appear for her
        const nicolaSpouseCount = nodes.filter(n =>
            n.y === 0 && n.role === 'spouse' && n.xref !== '@Rosa@'
        ).length;
        expect(nicolaSpouseCount).toBe(0);
        expect(nicolaNode).toBeDefined();
    });
});

// ── Regression: non-focus multi-FAM children separate into two umbrellas ──
//
// Adrian Gill scenario: Adrian has 3 FAMs with children — one with a visible
// spouse (Elaine → Claire) and two with non-visible spouses (Jennifer → Wu;
// no spouse → Teng, Eleanor). Clicking the chevron on Adrian must produce:
//   1. A line from the Adrian–Elaine marriage midpoint down to Claire.
//   2. A single 3-pronged umbrella from Adrian's pill covering Wu, Teng,
//      and Eleanor.
//   3. The 3-pronged umbrella must NOT touch the Claire line.
describe('_placeChildrenOfPerson — multi-FAM with visible spouse splits into two umbrellas', () => {
    function setupAdrianScene() {
        resetGlobals({
            people: {
                '@ADRIAN@': { birth_year: 1955 },
                '@ELAINE@': { birth_year: 1957 },
                '@CLAIRE@': { birth_year: 1982 },
                '@WU@': { birth_year: 1993 },
                '@TENG@': { birth_year: 2000 },
                '@ELEANOR@': { birth_year: 2002 },
            },
            relatives: {
                '@ADRIAN@': { siblings: [], spouses: ['@ELAINE@'] },
            },
            families: {
                '@F_AE@': { husb: '@ADRIAN@', wife: '@ELAINE@', chil: ['@CLAIRE@'] },
                '@F_AJ@': { husb: '@ADRIAN@', wife: '@JENNIFER@', chil: ['@WU@'] },
                '@F_A@': { husb: '@ADRIAN@', wife: null, chil: ['@TENG@', '@ELEANOR@'] },
            },
        });
    }

    it('visible-FAM child (Claire) sits on visible-spouse side; other-FAM kids on opposite side', () => {
        setupAdrianScene();
        const elaineX = NODE_W + MARRIAGE_GAP;
        const nodes = [
            { xref: '@ADRIAN@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@ELAINE@', x: elaineX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@ADRIAN@', new Set(), '@ADRIAN@', nodes, edges);

        const adrianCenter = NODE_W / 2;
        const kids = nodes.filter(n => n.y === ROW_HEIGHT && n.role === 'descendant');
        const byXref = Object.fromEntries(kids.map(k => [k.xref, k]));
        expect(byXref['@CLAIRE@']).toBeDefined();
        expect(byXref['@WU@']).toBeDefined();
        expect(byXref['@TENG@']).toBeDefined();
        expect(byXref['@ELEANOR@']).toBeDefined();

        expect(byXref['@CLAIRE@'].x + NODE_W / 2).toBeGreaterThan(adrianCenter);
        expect(byXref['@WU@'].x + NODE_W / 2).toBeLessThan(adrianCenter);
        expect(byXref['@TENG@'].x + NODE_W / 2).toBeLessThan(adrianCenter);
        expect(byXref['@ELEANOR@'].x + NODE_W / 2).toBeLessThan(adrianCenter);
    });

    it('no horizontal edge at umbrellaY crosses Adrian\'s center (two umbrellas stay disjoint)', () => {
        setupAdrianScene();
        const elaineX = NODE_W + MARRIAGE_GAP;
        const nodes = [
            { xref: '@ADRIAN@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@ELAINE@', x: elaineX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@ADRIAN@', new Set(), '@ADRIAN@', nodes, edges);

        const adrianCenter = NODE_W / 2;
        const umbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;
        const horizontals = edges.filter(e =>
            e.type === 'descendant' && e.y1 === umbrellaY && e.y2 === umbrellaY
        );
        for (const e of horizontals) {
            const lo = Math.min(e.x1, e.x2);
            const hi = Math.max(e.x1, e.x2);
            expect(
                hi <= adrianCenter || lo >= adrianCenter,
                `horizontal at umbrellaY spans ${lo}→${hi} crossing Adrian center ${adrianCenter}`,
            ).toBe(true);
        }
    });

    it('Wu, Teng, Eleanor share ONE crossbar at umbrellaY (single 3-pronged umbrella)', () => {
        setupAdrianScene();
        const elaineX = NODE_W + MARRIAGE_GAP;
        const nodes = [
            { xref: '@ADRIAN@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@ELAINE@', x: elaineX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@ADRIAN@', new Set(), '@ADRIAN@', nodes, edges);

        const umbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;
        const byXref = Object.fromEntries(
            nodes.filter(n => n.y === ROW_HEIGHT).map(k => [k.xref, k])
        );
        const otherCenters = [
            byXref['@WU@'].x + NODE_W / 2,
            byXref['@TENG@'].x + NODE_W / 2,
            byXref['@ELEANOR@'].x + NODE_W / 2,
        ];
        const leftC = Math.min(...otherCenters);
        const rightC = Math.max(...otherCenters);

        const crossbar = edges.find(e =>
            e.type === 'descendant' && e.y1 === umbrellaY && e.y2 === umbrellaY &&
            Math.min(e.x1, e.x2) === leftC && Math.max(e.x1, e.x2) === rightC
        );
        expect(crossbar, 'expected a single crossbar spanning the 3 non-visible children').toBeDefined();
    });

    it('mirror: visible spouse on left puts other-FAM kids on Adrian\'s right', () => {
        setupAdrianScene();
        const elaineX = -(NODE_W + MARRIAGE_GAP);
        const nodes = [
            { xref: '@ADRIAN@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@ELAINE@', x: elaineX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@ADRIAN@', new Set(), '@ADRIAN@', nodes, edges);

        const adrianCenter = NODE_W / 2;
        const byXref = Object.fromEntries(
            nodes.filter(n => n.y === ROW_HEIGHT).map(k => [k.xref, k])
        );
        expect(byXref['@CLAIRE@'].x + NODE_W / 2).toBeLessThan(adrianCenter);
        expect(byXref['@WU@'].x + NODE_W / 2).toBeGreaterThan(adrianCenter);
        expect(byXref['@TENG@'].x + NODE_W / 2).toBeGreaterThan(adrianCenter);
        expect(byXref['@ELEANOR@'].x + NODE_W / 2).toBeGreaterThan(adrianCenter);
    });

    it('no visible spouse: all kids share a single umbrella (one crossbar spanning all)', () => {
        resetGlobals({
            people: {
                '@ADRIAN@': { birth_year: 1955 },
                '@WU@': { birth_year: 1993 },
                '@TENG@': { birth_year: 2000 },
                '@ELEANOR@': { birth_year: 2002 },
            },
            relatives: {
                '@ADRIAN@': { siblings: [], spouses: [] },
            },
            families: {
                '@F_AJ@': { husb: '@ADRIAN@', wife: '@JENNIFER@', chil: ['@WU@'] },
                '@F_A@': { husb: '@ADRIAN@', wife: null, chil: ['@TENG@', '@ELEANOR@'] },
            },
        });
        const nodes = [{ xref: '@ADRIAN@', x: 0, y: 0, generation: 0, role: 'sibling' }];
        const edges = [];
        _placeChildrenOfPerson('@ADRIAN@', new Set(), '@ADRIAN@', nodes, edges);

        const umbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;
        const byXref = Object.fromEntries(
            nodes.filter(n => n.y === ROW_HEIGHT).map(k => [k.xref, k])
        );
        const centers = [
            byXref['@WU@'].x + NODE_W / 2,
            byXref['@TENG@'].x + NODE_W / 2,
            byXref['@ELEANOR@'].x + NODE_W / 2,
        ];
        const leftC = Math.min(...centers);
        const rightC = Math.max(...centers);

        const crossbars = edges.filter(e =>
            e.type === 'descendant' && e.y1 === umbrellaY && e.y2 === umbrellaY &&
            Math.min(e.x1, e.x2) === leftC && Math.max(e.x1, e.x2) === rightC
        );
        expect(crossbars.length).toBe(1);
    });
});

// ── Polycarpe scenario: visible spouse LEFT with a child-spouse that extends ──
// past personCenter — the other-FAMs cluster must be separated by INTER_FAM_GAP
// (H_GAP * 8 = 96px), not just CHEVRON_CLEARANCE (40px).
describe('_placeChildrenOfPerson — visible spouse LEFT enforces INTER_FAM_GAP between clusters', () => {
    const INTER_FAM_GAP = H_GAP * 8;
    const CHILD_MARRIAGE_GAP = H_GAP;

    function setupPolycarpeScene() {
        resetGlobals({
            people: {
                '@POLYCARPE@': { birth_year: 1923 },
                '@MARION@': { birth_year: 1929 },
                '@SANDRA@': { birth_year: 1965 },
                '@JIM@': { birth_year: 1966 },
                '@ADRIAN@': { birth_year: 1955 },
            },
            relatives: {
                '@POLYCARPE@': { siblings: [], spouses: ['@MARION@'] },
                '@SANDRA@': { siblings: [], spouses: ['@JIM@'] },
            },
            families: {
                '@F_PM@': { husb: '@POLYCARPE@', wife: '@MARION@', chil: ['@SANDRA@'] },
                '@F_PX@': { husb: '@POLYCARPE@', wife: null, chil: ['@ADRIAN@'] },
            },
        });
    }

    it('gap between visible-cluster rightmost node and other-cluster leftmost node >= INTER_FAM_GAP', () => {
        setupPolycarpeScene();
        const marionX = -(NODE_W + MARRIAGE_GAP);
        const nodes = [
            { xref: '@POLYCARPE@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@MARION@', x: marionX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@POLYCARPE@', new Set(), '@POLYCARPE@', nodes, edges);

        const childY = ROW_HEIGHT;
        const atChildY = nodes.filter(n => n.y === childY);
        const sandraNode = atChildY.find(n => n.xref === '@SANDRA@');
        const jimNode = atChildY.find(n => n.xref === '@JIM@');
        const adrianNode = atChildY.find(n => n.xref === '@ADRIAN@');

        expect(sandraNode).toBeDefined();
        expect(jimNode).toBeDefined();
        expect(adrianNode).toBeDefined();

        const visibleRightEdge = jimNode.x + NODE_W;
        const otherLeftEdge = adrianNode.x;
        expect(
            otherLeftEdge - visibleRightEdge,
            `expected >= ${INTER_FAM_GAP}px between Jim (ends ${visibleRightEdge}) and Adrian (starts ${otherLeftEdge})`,
        ).toBeGreaterThanOrEqual(INTER_FAM_GAP);
    });

    it('other-FAM cluster starts to the RIGHT of personCenter', () => {
        setupPolycarpeScene();
        const marionX = -(NODE_W + MARRIAGE_GAP);
        const nodes = [
            { xref: '@POLYCARPE@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@MARION@', x: marionX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@POLYCARPE@', new Set(), '@POLYCARPE@', nodes, edges);

        const personCenter = NODE_W / 2;
        const adrianNode = nodes.find(n => n.xref === '@ADRIAN@');
        expect(adrianNode.x + NODE_W / 2).toBeGreaterThan(personCenter);
    });

    it('no horizontal at umbrellaY crosses personCenter', () => {
        setupPolycarpeScene();
        const marionX = -(NODE_W + MARRIAGE_GAP);
        const nodes = [
            { xref: '@POLYCARPE@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@MARION@', x: marionX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@POLYCARPE@', new Set(), '@POLYCARPE@', nodes, edges);

        const personCenter = NODE_W / 2;
        const umbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;
        const horizontals = edges.filter(e =>
            e.type === 'descendant' && e.y1 === umbrellaY && e.y2 === umbrellaY,
        );
        for (const e of horizontals) {
            const lo = Math.min(e.x1, e.x2);
            const hi = Math.max(e.x1, e.x2);
            expect(
                hi <= personCenter || lo >= personCenter,
                `horizontal at umbrellaY spans ${lo}→${hi} crossing personCenter ${personCenter}`,
            ).toBe(true);
        }
    });

    it('mirror: visible spouse RIGHT also enforces INTER_FAM_GAP (other cluster left of visible)', () => {
        setupPolycarpeScene();
        const marionX = NODE_W + MARRIAGE_GAP;
        const nodes = [
            { xref: '@POLYCARPE@', x: 0, y: 0, generation: 0, role: 'sibling' },
            { xref: '@MARION@', x: marionX, y: 0, generation: 0, role: 'spouse' },
        ];
        const edges = [];
        _placeChildrenOfPerson('@POLYCARPE@', new Set(), '@POLYCARPE@', nodes, edges);

        const childY = ROW_HEIGHT;
        const atChildY = nodes.filter(n => n.y === childY);
        const sandraNode = atChildY.find(n => n.xref === '@SANDRA@');
        const jimNode = atChildY.find(n => n.xref === '@JIM@');
        const adrianNode = atChildY.find(n => n.xref === '@ADRIAN@');

        const visibleLeftEdge = sandraNode.x;
        const otherRightEdge = adrianNode.x + NODE_W;
        expect(
            visibleLeftEdge - otherRightEdge,
            `expected >= ${INTER_FAM_GAP}px between Adrian (ends ${otherRightEdge}) and Sandra (starts ${visibleLeftEdge})`,
        ).toBeGreaterThanOrEqual(INTER_FAM_GAP);
    });
});

describe('computeLayout — focus spouse parent expansion', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1765 },
                '@SPOUSE@': { birth_year: 1765 },
                '@SPDAD@':  { birth_year: 1735 },
                '@SPMOM@':  { birth_year: 1740 },
                '@SIB@':    { birth_year: 1770 },
                '@SIBSP@':  { birth_year: 1768 },
            },
            relatives: {
                '@FOCUS@':  { siblings: ['@SIB@'], spouses: ['@SPOUSE@'] },
                '@SPOUSE@': { siblings: [], spouses: ['@FOCUS@'] },
                '@SIB@':    { siblings: ['@FOCUS@'], spouses: ['@SIBSP@'] },
                '@SIBSP@':  { siblings: [], spouses: ['@SIB@'] },
            },
            parents: {
                '@SPOUSE@': ['@SPDAD@', '@SPMOM@'],
            },
        });
    });

    it('marks focus spouse with isFocusSpouse=true', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        expect(spouse).toBeDefined();
        expect(spouse.isFocusSpouse).toBe(true);
    });

    it('does NOT mark a sibling-of-focus spouse as isFocusSpouse', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const sibSpouse = nodes.find(n => n.xref === '@SIBSP@');
        expect(sibSpouse).toBeDefined();
        expect(sibSpouse.isFocusSpouse).toBeFalsy();
    });

    it('places spouse parents at y=-ROW_HEIGHT when spouse xref is in expandedAncestors', () => {
        const expanded = new Set(['@SPOUSE@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const spDad = nodes.find(n => n.xref === '@SPDAD@');
        const spMom = nodes.find(n => n.xref === '@SPMOM@');
        expect(spDad).toBeDefined();
        expect(spMom).toBeDefined();
        expect(spDad.y).toBe(-ROW_HEIGHT);
        expect(spMom.y).toBe(-ROW_HEIGHT);
        expect(spDad.role).toBe('ancestor');
        expect(spMom.role).toBe('ancestor');
    });

    it('does NOT place spouse parents when spouse xref is NOT in expandedAncestors', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        expect(nodes.find(n => n.xref === '@SPDAD@')).toBeUndefined();
        expect(nodes.find(n => n.xref === '@SPMOM@')).toBeUndefined();
    });

    it('recursively places spouse grandparents when spouse father is also expanded', () => {
        global.PEOPLE['@SPGRANDPA@'] = { birth_year: 1705 };
        global.PEOPLE['@SPGRANDMA@'] = { birth_year: 1710 };
        global.PARENTS['@SPDAD@'] = ['@SPGRANDPA@', '@SPGRANDMA@'];

        const expanded = new Set(['@SPOUSE@', '@SPDAD@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());

        const gpa = nodes.find(n => n.xref === '@SPGRANDPA@');
        const gma = nodes.find(n => n.xref === '@SPGRANDMA@');
        expect(gpa).toBeDefined();
        expect(gma).toBeDefined();
        expect(gpa.y).toBe(-2 * ROW_HEIGHT);
        expect(gma.y).toBe(-2 * ROW_HEIGHT);
        expect(gpa.role).toBe('ancestor');
    });
});

describe('computeLayout — focus-parents ↔ spouse-parents collision avoidance', () => {
    // Fixture: focus has both parents; spouse has both parents. With both
    // sides expanded, focus's mother and spouse's father sit at the same row
    // and must not overlap. Minimum center-to-center distance is NODE_W + H_GAP
    // (the SLOT floor returned by _requiredSeparation at depth 0).
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@':   { birth_year: 1920 },
                '@SPOUSE@':  { birth_year: 1920 },
                '@FDAD@':    { birth_year: 1890 },
                '@FMOM@':    { birth_year: 1895 },
                '@SPDAD@':   { birth_year: 1888 },
                '@SPMOM@':   { birth_year: 1892 },
            },
            relatives: {
                '@FOCUS@':  { siblings: [], spouses: ['@SPOUSE@'] },
                '@SPOUSE@': { siblings: [], spouses: ['@FOCUS@'] },
            },
            parents: {
                '@FOCUS@':  ['@FDAD@', '@FMOM@'],
                '@SPOUSE@': ['@SPDAD@', '@SPMOM@'],
            },
        });
    });

    it('leaves enough horizontal gap between focus-mother and spouse-father when both sides expanded', () => {
        const expanded = new Set(['@FOCUS@', '@SPOUSE@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const fMom = nodes.find(n => n.xref === '@FMOM@');
        const spDad = nodes.find(n => n.xref === '@SPDAD@');
        expect(fMom).toBeDefined();
        expect(spDad).toBeDefined();

        const fMomCenter = fMom.x + NODE_W / 2;
        const spDadCenter = spDad.x + NODE_W / 2;
        // At depth 0 the required center-to-center gap is NODE_W + H_GAP.
        expect(spDadCenter - fMomCenter).toBeGreaterThanOrEqual(NODE_W + H_GAP);
    });

    it('does not shift the spouse when focus has no parents in the tree', () => {
        // Remove focus's parents from the fixture — no focus-side subtree
        // exists at the ancestor row, so there's nothing to collide with.
        delete global.PARENTS['@FOCUS@'];
        const expanded = new Set(['@SPOUSE@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        const firstSpouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
        expect(spouse.x).toBe(firstSpouseX);
        // Spouse's parents are still placed.
        expect(nodes.find(n => n.xref === '@SPDAD@')).toBeDefined();
    });

    it('does not place spouse parents when spouse side is collapsed', () => {
        const expanded = new Set(['@FOCUS@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        expect(nodes.find(n => n.xref === '@SPDAD@')).toBeUndefined();
        expect(nodes.find(n => n.xref === '@SPMOM@')).toBeUndefined();
        // And focus-mother is at her un-shifted position.
        const fMom = nodes.find(n => n.xref === '@FMOM@');
        expect(fMom).toBeDefined();
    });

    it('keeps younger focus-sibling to the right of the shifted spouse', () => {
        // Extend fixture with a younger focus-sibling.
        global.PEOPLE['@SIB@'] = { birth_year: 1925 };
        global.RELATIVES['@FOCUS@'] = { siblings: ['@SIB@'], spouses: ['@SPOUSE@'] };
        global.RELATIVES['@SIB@'] = { siblings: ['@FOCUS@'], spouses: [] };
        global.PARENTS['@SIB@'] = ['@FDAD@', '@FMOM@'];

        const expanded = new Set(['@FOCUS@', '@SPOUSE@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());

        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        const sib = nodes.find(n => n.xref === '@SIB@');
        expect(spouse).toBeDefined();
        expect(sib).toBeDefined();
        // The younger sibling is placed to the RIGHT of the spouse with a
        // proper gap. If the sibling didn't get shifted alongside the
        // spouse during collision avoidance, it would overlap the spouse.
        expect(sib.x).toBeGreaterThan(spouse.x + NODE_W);
    });
});