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

    it('passes for multi-FAM single-child umbrella sharing y with another umbrella', () => {
        // Two parents have umbrellas at the same y. Visible-FAM has 1 child
        // (no crossbar — anchor + drop colinear). Other-FAM has 3 kids with a
        // crossbar. The single-child drop is outside the multi-child crossbar's
        // x-range, but it's anchored from above (its parent's bottom).
        const nodes = [
            { xref: '@SOLO@', x: 100, y: 148, role: 'descendant' },  // center 150
            { xref: '@A@',    x: 250, y: 148, role: 'descendant' },  // center 300
            { xref: '@B@',    x: 350, y: 148, role: 'descendant' },  // center 400
            { xref: '@C@',    x: 450, y: 148, role: 'descendant' },  // center 500
        ];
        const edges = [
            // Visible-FAM single-child: anchor drop above + drop colinear (both at x=150)
            { x1: 150, y1: 50,  x2: 150, y2: 120, type: 'descendant' }, // anchor above
            { x1: 150, y1: 120, x2: 150, y2: 148, type: 'descendant' }, // drop to SOLO
            // Other-FAM multi-child cluster
            { x1: 300, y1: 120, x2: 500, y2: 120, type: 'descendant' }, // crossbar
            { x1: 300, y1: 120, x2: 300, y2: 148, type: 'descendant' }, // drop to A
            { x1: 400, y1: 120, x2: 400, y2: 148, type: 'descendant' }, // drop to B
            { x1: 500, y1: 120, x2: 500, y2: 148, type: 'descendant' }, // drop to C
        ];
        expect(() => assertChildrenInParentClusterRange(nodes, edges)).not.toThrow();
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

    it('ignores T-junctions where crossbars share an endpoint x-coordinate', () => {
        const edges = [
            { x1: 0,   y1: 100, x2: 100, y2: 100, type: 'descendant' },
            { x1: 100, y1: 100, x2: 200, y2: 100, type: 'descendant' }, // shares endpoint
        ];
        expect(() => assertUmbrellasDisjointAtY(edges))
            .not.toThrow();
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
    assertClusterXRangesDisjoint,
} = require('./_layout_invariants.js');

describe('assertClusterXRangesDisjoint', () => {
    // Helper: build a multi-child cluster (crossbar + drop per child)
    function clusterAt(crossbarL, crossbarR, y, childYs, anchorX = (crossbarL + crossbarR) / 2) {
        const crossbarY = y - 50; // crossbar above children
        const edges = [
            { x1: crossbarL, y1: crossbarY, x2: crossbarR, y2: crossbarY, type: 'descendant' },
        ];
        const nodes = childYs.map((cx, i) => ({
            xref: `@C${i}@`, x: cx, y, role: 'descendant',
        }));
        for (const cx of childYs) {
            edges.push({ x1: cx + NODE_W / 2, y1: crossbarY, x2: cx + NODE_W / 2, y2: y, type: 'descendant' });
        }
        return { nodes, edges };
    }

    it('passes on empty input', () => {
        expect(() => assertClusterXRangesDisjoint([], [])).not.toThrow();
    });

    it('passes for a single cluster', () => {
        const c = clusterAt(50, 250, 148, [50, 200]);
        expect(() => assertClusterXRangesDisjoint(c.nodes, c.edges)).not.toThrow();
    });

    it('passes for two clusters at same y with disjoint x-ranges', () => {
        const a = clusterAt(0, 200, 148, [0, 100]);
        const b = clusterAt(400, 600, 148, [400, 500]);
        const nodes = [...a.nodes, ...b.nodes.map((n, i) => ({ ...n, xref: `@D${i}@` }))];
        const edges = [...a.edges, ...b.edges];
        expect(() => assertClusterXRangesDisjoint(nodes, edges)).not.toThrow();
    });

    it('throws when two clusters at same y have overlapping node x-ranges', () => {
        // Crossbars are disjoint (so umbrella check passes) but the node ranges
        // overlap because nodes have width: A's right node x=200..300 vs B's
        // left node x=280..380. This is the inter-cluster-gap bug class.
        const a = clusterAt(50, 250, 148, [0, 200]);   // crossbar at drops; nodes [0..300]
        const b = clusterAt(330, 530, 148, [280, 480]); // nodes [280..580]
        const nodes = [...a.nodes, ...b.nodes.map((n, i) => ({ ...n, xref: `@D${i}@` }))];
        const edges = [...a.edges, ...b.edges];
        expect(() => assertClusterXRangesDisjoint(nodes, edges)).toThrow(/cluster.*overlap/i);
    });

    it('passes when overlapping clusters are at different y', () => {
        const a = clusterAt(0, 250, 148, [0, 150]);
        const b = clusterAt(0, 250, 296, [0, 150]); // same x, different y
        const nodes = [...a.nodes, ...b.nodes.map((n, i) => ({ ...n, xref: `@D${i}@` }))];
        const edges = [...a.edges, ...b.edges];
        expect(() => assertClusterXRangesDisjoint(nodes, edges)).not.toThrow();
    });

    it('handles single-child clusters (anchor-only, no crossbar)', () => {
        // Two single-child clusters: child A at x=0, child B at x=300, both y=148.
        // Each has an anchor vertical from y=50 down to drop at y=98, then drop to y=148.
        const nodes = [
            { xref: '@A@', x: 0, y: 148, role: 'descendant' },
            { xref: '@B@', x: 300, y: 148, role: 'descendant' },
        ];
        const edges = [
            // anchor vertical above drop A
            { x1: NODE_W / 2, y1: 50, x2: NODE_W / 2, y2: 98, type: 'descendant' },
            // drop A
            { x1: NODE_W / 2, y1: 98, x2: NODE_W / 2, y2: 148, type: 'descendant' },
            // anchor vertical above drop B
            { x1: 300 + NODE_W / 2, y1: 50, x2: 300 + NODE_W / 2, y2: 98, type: 'descendant' },
            // drop B
            { x1: 300 + NODE_W / 2, y1: 98, x2: 300 + NODE_W / 2, y2: 148, type: 'descendant' },
        ];
        expect(() => assertClusterXRangesDisjoint(nodes, edges)).not.toThrow();
    });
});

const {
    assertChildWithinParentSpanRange,
} = require('./_layout_invariants.js');

describe('assertChildWithinParentSpanRange', () => {
    // Minimal layout factory: parent at given x, one child cluster below.
    function focusWithChildren(focusX, childXs, opts = {}) {
        const focusY = 0;
        const childY = 148;
        const crossbarY = 98;
        const focusCenter = focusX + NODE_W_FOCUS / 2;
        const nodes = [
            { xref: '@F@', x: focusX, y: focusY, generation: 0, role: 'focus' },
        ];
        const edges = [];
        global.PARENTS = {};
        for (let i = 0; i < childXs.length; i++) {
            const cx = childXs[i];
            const xref = `@C${i}@`;
            nodes.push({ xref, x: cx, y: childY, generation: -1, role: 'descendant' });
            edges.push({ x1: cx + NODE_W / 2, y1: crossbarY, x2: cx + NODE_W / 2, y2: childY, type: 'descendant' });
            global.PARENTS[xref] = ['@F@'];
        }
        if (childXs.length > 1) {
            // multi-child crossbar
            const xs = childXs.map(x => x + NODE_W / 2);
            edges.push({ x1: Math.min(...xs), y1: crossbarY, x2: Math.max(...xs), y2: crossbarY, type: 'descendant' });
        } else if (childXs.length === 1) {
            // single-child anchor vertical from focus center down to crossbarY
            edges.push({ x1: focusCenter, y1: focusY + 50, x2: focusCenter, y2: crossbarY, type: 'descendant' });
        }
        if (opts.spouse !== undefined) {
            nodes.push({ xref: '@S@', x: opts.spouse, y: focusY, generation: 0, role: 'spouse' });
            // spouse co-parents the same children
            for (let i = 0; i < childXs.length; i++) global.PARENTS[`@C${i}@`].push('@S@');
        }
        return { nodes, edges };
    }

    it('passes when one child sits directly below the parent', () => {
        // Focus at x=0 (center=58), child at x=8 (center=58). Right under parent.
        const { nodes, edges } = focusWithChildren(0, [8]);
        expect(() => assertChildWithinParentSpanRange(nodes, edges)).not.toThrow();
    });

    it('passes when children straddle the parent', () => {
        // Focus at x=0; two children at x=-100 and x=120 — crossbar centered roughly on focus.
        const { nodes, edges } = focusWithChildren(0, [-100, 120]);
        expect(() => assertChildWithinParentSpanRange(nodes, edges)).not.toThrow();
    });

    it('throws when a child sits far past the parent on one side', () => {
        // Focus at x=0 (span [0..116]), one child at x=600 (center=650).
        // halfCluster = 50 (single child). Allowed range [-50..166]. 650 is way outside.
        const { nodes, edges } = focusWithChildren(0, [600]);
        expect(() => assertChildWithinParentSpanRange(nodes, edges)).toThrow(/parent.*span|outside/i);
    });

    it('uses NODE_W_FOCUS for focus-role parent (asymmetry per gotcha #3)', () => {
        // Focus span is [0..116] not [0..100]. A child at x=110 (center=160) is within
        // [0-50, 116+50]=[−50,166]. Just barely fits.
        const { nodes, edges } = focusWithChildren(0, [110]);
        expect(() => assertChildWithinParentSpanRange(nodes, edges)).not.toThrow();
    });

    it('extends span to include on-row spouse', () => {
        // Focus at x=0 (right edge 116), spouse at x=200 (right edge 300). Span [0..300].
        // Child at x=150 (center 200). halfCluster=50. Allowed [0-50..300+50]=[-50..350]. ✓
        const { nodes, edges } = focusWithChildren(0, [150], { spouse: 200 });
        expect(() => assertChildWithinParentSpanRange(nodes, edges)).not.toThrow();
    });

    it('skips silently when PARENTS global is missing', () => {
        delete global.PARENTS;
        const nodes = [
            { xref: '@F@', x: 0, y: 0, role: 'focus' },
            { xref: '@C@', x: 600, y: 148, role: 'descendant' }, // would fail if PARENTS were set
        ];
        const edges = [];
        expect(() => assertChildWithinParentSpanRange(nodes, edges)).not.toThrow();
    });

    it('passes on empty input', () => {
        global.PARENTS = {};
        expect(() => assertChildWithinParentSpanRange([], [])).not.toThrow();
    });
});

const {
    assertGenerationsAligned,
} = require('./_layout_invariants.js');

describe('assertGenerationsAligned', () => {
    it('passes when all nodes at the same generation share a y', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, generation: 0 },
            { xref: '@B@', x: 200, y: 0, generation: 0 },
            { xref: '@C@', x: 0, y: 148, generation: -1 },
            { xref: '@D@', x: 0, y: -148, generation: 1 },
        ];
        expect(() => assertGenerationsAligned(nodes)).not.toThrow();
    });

    it('throws when two nodes at the same generation have different y', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, generation: 0 },
            { xref: '@B@', x: 200, y: 10, generation: 0 }, // off-row
        ];
        expect(() => assertGenerationsAligned(nodes)).toThrow(/generation/i);
    });

    it('ignores nodes without a generation field', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, generation: 0 },
            { xref: '@B@', x: 200, y: 50 }, // no generation
        ];
        expect(() => assertGenerationsAligned(nodes)).not.toThrow();
    });

    it('passes on empty input', () => {
        expect(() => assertGenerationsAligned([])).not.toThrow();
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
