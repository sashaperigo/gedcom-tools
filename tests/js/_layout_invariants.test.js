import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;
const { NODE_W, NODE_W_FOCUS } = DESIGN;

const {
    assertNoNodeOverlap,
} = require('./_layout_invariants.js');

describe('assertNoNodeOverlap', () => {
    it('passes when nodes at same y have non-overlapping x ranges', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            { xref: '@B@', x: NODE_W_FOCUS + 12, y: 0, role: 'spouse' },
            { xref: '@C@', x: 0, y: 148, role: 'descendant' },
        ];
        expect(() => assertNoNodeOverlap(nodes)).not.toThrow();
    });

    it('throws when two nodes at same y overlap', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'sibling' },
            { xref: '@B@', x: NODE_W / 2, y: 0, role: 'sibling' }, // overlaps @A@
        ];
        expect(() => assertNoNodeOverlap(nodes)).toThrow(/overlap/i);
    });

    it('uses NODE_W_FOCUS for focus-role nodes', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            // sibling at NODE_W away — overlaps because focus is wider
            { xref: '@B@', x: NODE_W, y: 0, role: 'sibling' },
        ];
        expect(() => assertNoNodeOverlap(nodes)).toThrow(/overlap/i);
    });

    it('ignores overlap across different y', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            { xref: '@B@', x: 0, y: 148, role: 'descendant' },
        ];
        expect(() => assertNoNodeOverlap(nodes)).not.toThrow();
    });
});

const {
    assertExactlyOneFocus,
    assertSiblingOrderMonotonic,
} = require('./_layout_invariants.js');

describe('assertExactlyOneFocus', () => {
    it('passes when exactly one node has role=focus', () => {
        const nodes = [
            { xref: '@F@', x: 0, y: 0, role: 'focus' },
            { xref: '@S@', x: 200, y: 0, role: 'spouse' },
        ];
        expect(() => assertExactlyOneFocus(nodes)).not.toThrow();
    });

    it('throws when zero focus nodes', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'sibling' },
        ];
        expect(() => assertExactlyOneFocus(nodes)).toThrow(/exactly one focus/i);
    });

    it('throws when two focus nodes', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            { xref: '@B@', x: 200, y: 0, role: 'focus' },
        ];
        expect(() => assertExactlyOneFocus(nodes)).toThrow(/exactly one focus/i);
    });
});

describe('assertSiblingOrderMonotonic', () => {
    // PEOPLE is read globally for birth_year lookup
    it('passes when siblings on focus row are in birth-year order left-to-right', () => {
        global.PEOPLE = {
            '@A@': { birth_year: 1900 },
            '@F@': { birth_year: 1910 },
            '@B@': { birth_year: 1920 },
        };
        const nodes = [
            { xref: '@A@', x: -200, y: 0, role: 'sibling' },
            { xref: '@F@', x: 0,    y: 0, role: 'focus' },
            { xref: '@B@', x: 200,  y: 0, role: 'sibling' },
        ];
        expect(() => assertSiblingOrderMonotonic(nodes)).not.toThrow();
    });

    it('throws when an older sibling is right of a younger sibling on focus row', () => {
        global.PEOPLE = {
            '@A@': { birth_year: 1920 },  // YOUNGER
            '@B@': { birth_year: 1900 },  // OLDER
        };
        const nodes = [
            { xref: '@A@', x: -200, y: 0, role: 'sibling' }, // younger but left
            { xref: '@B@', x: 200,  y: 0, role: 'sibling' }, // older but right
        ];
        expect(() => assertSiblingOrderMonotonic(nodes)).toThrow(/birth.year/i);
    });

    it('ignores spouse-role nodes (they sit next to their sibling regardless of birth year)', () => {
        global.PEOPLE = {
            '@SIB@':    { birth_year: 1900 },
            '@SPOUSE@': { birth_year: 1950 }, // much younger
            '@F@':      { birth_year: 1910 },
        };
        const nodes = [
            { xref: '@SPOUSE@', x: -300, y: 0, role: 'spouse' },
            { xref: '@SIB@',    x: -200, y: 0, role: 'sibling' },
            { xref: '@F@',      x: 0,    y: 0, role: 'focus' },
        ];
        expect(() => assertSiblingOrderMonotonic(nodes)).not.toThrow();
    });
});

const {
    assertChildrenInParentClusterRange,
} = require('./_layout_invariants.js');

describe('assertChildrenInParentClusterRange', () => {
    it('passes when every descendant node sits under its umbrella crossbar', () => {
        // Umbrella crossbar from x=50 to x=250 at y=120; children at 50, 150, 250
        const nodes = [
            { xref: '@C1@', x: 0,   y: 148, role: 'descendant' }, // center 50
            { xref: '@C2@', x: 100, y: 148, role: 'descendant' }, // center 150
            { xref: '@C3@', x: 200, y: 148, role: 'descendant' }, // center 250
        ];
        const edges = [
            { x1: 50, y1: 120, x2: 250, y2: 120, type: 'descendant' }, // crossbar
            { x1: 50, y1: 120, x2: 50, y2: 148, type: 'descendant' },  // drop to C1
            { x1: 150, y1: 120, x2: 150, y2: 148, type: 'descendant' }, // drop to C2
            { x1: 250, y1: 120, x2: 250, y2: 148, type: 'descendant' }, // drop to C3
        ];
        expect(() => assertChildrenInParentClusterRange(nodes, edges)).not.toThrow();
    });

    it('throws when a descendant node has no drop edge connecting it to a crossbar', () => {
        const nodes = [
            { xref: '@ORPHAN@', x: 1000, y: 148, role: 'descendant' },
        ];
        const edges = [];
        expect(() => assertChildrenInParentClusterRange(nodes, edges))
            .toThrow(/no descendant drop edge/i);
    });

    it('throws when a child center is outside its crossbar range', () => {
        // Crossbar spans x=50..150 but child sits at center 250
        const nodes = [
            { xref: '@OUT@', x: 200, y: 148, role: 'descendant' }, // center 250
        ];
        const edges = [
            { x1: 50, y1: 120, x2: 150, y2: 120, type: 'descendant' },  // crossbar
            { x1: 250, y1: 120, x2: 250, y2: 148, type: 'descendant' }, // drop (claims 250)
        ];
        expect(() => assertChildrenInParentClusterRange(nodes, edges))
            .toThrow(/outside.*crossbar/i);
    });
});

const {
    assertUmbrellasDisjointAtY,
} = require('./_layout_invariants.js');

describe('assertUmbrellasDisjointAtY', () => {
    it('passes when crossbars at same y have disjoint x-ranges', () => {
        const edges = [
            { x1: 0,   y1: 100, x2: 100, y2: 100, type: 'descendant' },
            { x1: 200, y1: 100, x2: 300, y2: 100, type: 'descendant' },
        ];
        expect(() => assertUmbrellasDisjointAtY(edges)).not.toThrow();
    });

    it('passes when crossbars at different y can overlap in x', () => {
        const edges = [
            { x1: 0, y1: 100, x2: 200, y2: 100, type: 'descendant' },
            { x1: 100, y1: 250, x2: 300, y2: 250, type: 'descendant' },
        ];
        expect(() => assertUmbrellasDisjointAtY(edges)).not.toThrow();
    });

    it('throws when two crossbars at same y overlap', () => {
        const edges = [
            { x1: 0,   y1: 100, x2: 200, y2: 100, type: 'descendant' },
            { x1: 100, y1: 100, x2: 300, y2: 100, type: 'descendant' }, // overlaps first
        ];
        expect(() => assertUmbrellasDisjointAtY(edges))
            .toThrow(/crossbar.*overlap/i);
    });

    it('throws when crossbars touch (zero gap)', () => {
        const edges = [
            { x1: 0,   y1: 100, x2: 100, y2: 100, type: 'descendant' },
            { x1: 100, y1: 100, x2: 200, y2: 100, type: 'descendant' }, // shares endpoint
        ];
        expect(() => assertUmbrellasDisjointAtY(edges))
            .toThrow(/crossbar.*overlap/i);
    });

    it('ignores non-descendant edges (e.g. marriage edges at same y)', () => {
        const edges = [
            { x1: 0,   y1: 100, x2: 200, y2: 100, type: 'marriage' },
            { x1: 100, y1: 100, x2: 300, y2: 100, type: 'marriage' },
        ];
        expect(() => assertUmbrellasDisjointAtY(edges)).not.toThrow();
    });
});

const {
    assertNoUmbrellaCrossesPersonCenter,
} = require('./_layout_invariants.js');

describe('assertNoUmbrellaCrossesPersonCenter', () => {
    it('passes when two umbrellas at same y have anchor drops on disjoint sides', () => {
        // Anchor at x=150. Visible cluster crossbar [200, 300]. Other cluster crossbar [0, 100].
        // Anchor verticals: visible drops from anchor (150) DOWN to crossbar at y=100;
        // other drops from anchor (150) DOWN to crossbar at y=100.
        const edges = [
            // Anchor verticals (from above-y down to crossbar y)
            { x1: 150, y1: 50, x2: 150, y2: 100, type: 'descendant' }, // visible anchor drop
            { x1: 150, y1: 50, x2: 150, y2: 100, type: 'descendant' }, // other anchor drop
            // Crossbars
            { x1: 200, y1: 100, x2: 300, y2: 100, type: 'descendant' }, // visible crossbar (right of 150)
            { x1: 0,   y1: 100, x2: 100, y2: 100, type: 'descendant' }, // other crossbar (left of 150)
            // Horizontal connectors anchor → crossbar
            { x1: 150, y1: 100, x2: 200, y2: 100, type: 'descendant' },
            { x1: 100, y1: 100, x2: 150, y2: 100, type: 'descendant' },
        ];
        expect(() => assertNoUmbrellaCrossesPersonCenter(edges)).not.toThrow();
    });

    it('throws when one crossbar straddles the shared anchor x of two umbrellas', () => {
        // Two anchor drops both at x=150. One crossbar from 100..200 straddles 150.
        const edges = [
            { x1: 150, y1: 50, x2: 150, y2: 100, type: 'descendant' },
            { x1: 150, y1: 50, x2: 150, y2: 100, type: 'descendant' },
            { x1: 100, y1: 100, x2: 200, y2: 100, type: 'descendant' }, // straddles 150
            { x1: 250, y1: 100, x2: 350, y2: 100, type: 'descendant' },
        ];
        expect(() => assertNoUmbrellaCrossesPersonCenter(edges))
            .toThrow(/cross.*anchor/i);
    });
});

const {
    assertAllLayoutInvariants,
    computeLayoutChecked,
} = require('./_layout_invariants.js');

describe('assertAllLayoutInvariants', () => {
    it('passes for a valid minimal layout', () => {
        global.PEOPLE = { '@F@': { birth_year: 1900 } };
        const result = {
            nodes: [{ xref: '@F@', x: 0, y: 0, role: 'focus' }],
            edges: [],
        };
        expect(() => assertAllLayoutInvariants(result)).not.toThrow();
    });

    it('throws on the first invariant failure', () => {
        const result = {
            nodes: [
                { xref: '@A@', x: 0, y: 0, role: 'sibling' },
                { xref: '@B@', x: 50, y: 0, role: 'sibling' }, // overlaps
            ],
            edges: [],
        };
        expect(() => assertAllLayoutInvariants(result)).toThrow(/overlap|focus/i);
    });
});

describe('computeLayoutChecked', () => {
    it('returns the same shape as computeLayout when invariants pass', () => {
        global.PEOPLE = { '@F@': { birth_year: 1900 } };
        global.PARENTS = {};
        global.CHILDREN = {};
        global.RELATIVES = { '@F@': { siblings: [], spouses: [] } };
        global.FAMILIES = {};
        const result = computeLayoutChecked('@F@', new Set(), new Set(), new Set());
        expect(result).toHaveProperty('nodes');
        expect(result).toHaveProperty('edges');
        expect(result.nodes.find(n => n.xref === '@F@')).toBeDefined();
    });
});
