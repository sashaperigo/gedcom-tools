// Pure assertion functions for layout geometric invariants.
// Each helper takes the output of computeLayout (nodes, edges) plus optional
// context (focusXref) and throws Error with a descriptive message on violation.
//
// See docs/learnings/viz-expand-layout-bugs.md for the bug classes each
// invariant catches.

const { DESIGN } = require('../../js/viz_design.js');
const { NODE_W, NODE_W_FOCUS } = DESIGN;

function _nodeWidth(node) {
    return node.role === 'focus' ? NODE_W_FOCUS : NODE_W;
}

// Two nodes at the same y must not have overlapping x-ranges
// [node.x, node.x + width). Catches: any layout that places two pills on top
// of each other.
function assertNoNodeOverlap(nodes) {
    const byY = new Map();
    for (const n of nodes) {
        if (!byY.has(n.y)) byY.set(n.y, []);
        byY.get(n.y).push(n);
    }
    for (const [y, group] of byY) {
        const sorted = group.slice().sort((a, b) => a.x - b.x);
        for (let i = 1; i < sorted.length; i++) {
            const prev = sorted[i - 1];
            const curr = sorted[i];
            const prevRight = prev.x + _nodeWidth(prev);
            if (prevRight > curr.x) {
                throw new Error(
                    `Node overlap at y=${y}: ${prev.xref} (x=${prev.x}, right=${prevRight}) ` +
                    `overlaps ${curr.xref} (x=${curr.x})`
                );
            }
        }
    }
}

// Layout must contain exactly one node with role='focus'. Catches: stale
// expandedChildrenPersons producing duplicate focus-row nodes; missing focus.
function assertExactlyOneFocus(nodes) {
    const focuses = nodes.filter(n => n.role === 'focus');
    if (focuses.length !== 1) {
        throw new Error(
            `Expected exactly one focus node, found ${focuses.length}: ` +
            focuses.map(n => n.xref).join(', ')
        );
    }
}

// On the focus row (y=0), nodes with role='sibling' or 'focus' must be ordered
// left-to-right by birth year. Spouses sit next to their sibling and are
// ignored for this check.
function assertSiblingOrderMonotonic(nodes) {
    const focusRow = nodes
        .filter(n => n.y === 0 && (n.role === 'sibling' || n.role === 'focus'))
        .slice()
        .sort((a, b) => a.x - b.x);
    for (let i = 1; i < focusRow.length; i++) {
        const prev = focusRow[i - 1];
        const curr = focusRow[i];
        const prevBY = (typeof PEOPLE !== 'undefined' && PEOPLE[prev.xref]?.birth_year) ?? 9999;
        const currBY = (typeof PEOPLE !== 'undefined' && PEOPLE[curr.xref]?.birth_year) ?? 9999;
        if (prevBY > currBY) {
            throw new Error(
                `Sibling-row birth-year inversion: ${prev.xref} (b.${prevBY}, x=${prev.x}) ` +
                `is left of ${curr.xref} (b.${currBY}, x=${curr.x})`
            );
        }
    }
}

// Every descendant-role node must hang from a descendant-type drop edge
// connecting it to a crossbar (horizontal descendant edge) whose x-range
// covers the drop's x. Catches: children landing outside their parent's
// umbrella range; orphaned children with no umbrella connection.
function assertChildrenInParentClusterRange(nodes, edges) {
    const descNodes = nodes.filter(n => n.role === 'descendant');
    const descEdges = edges.filter(e => e.type === 'descendant');
    const crossbars = descEdges.filter(e => e.y1 === e.y2);
    const verticals = descEdges.filter(e => e.x1 === e.x2);
    for (const child of descNodes) {
        const childCenter = child.x + NODE_W / 2;
        // Find a drop edge ending at this child's center+top
        const drop = descEdges.find(e =>
            e.x1 === e.x2 && // vertical
            Math.abs(e.x1 - childCenter) < 0.5 &&
            Math.abs(e.y2 - child.y) < 0.5
        );
        if (!drop) {
            throw new Error(
                `No descendant drop edge for ${child.xref} at (${childCenter}, ${child.y})`
            );
        }
        // Crossbar covering this drop's x at the drop's top y is the umbrella
        // this child hangs from.
        const cb = crossbars.find(e =>
            Math.abs(e.y1 - drop.y1) < 0.5 &&
            Math.min(e.x1, e.x2) - 0.5 <= drop.x1 &&
            drop.x1 <= Math.max(e.x1, e.x2) + 0.5
        );
        if (cb) continue;
        // Single-child anchor pattern: a colinear vertical edge above the drop
        // (anchor drop from parent's bottom to umbrellaY at the same x). That's
        // a valid umbrella with no crossbar — exempt independent of whether
        // *other* unrelated umbrellas at this y have crossbars.
        const hasAnchorAbove = verticals.some(e =>
            Math.abs(e.x1 - drop.x1) < 0.5 &&
            Math.abs(e.y2 - drop.y1) < 0.5 &&
            e.y1 < drop.y1 - 0.5
        );
        if (hasAnchorAbove) continue;
        throw new Error(
            `${child.xref} drop at x=${drop.x1} is outside crossbar range at y=${drop.y1}`
        );
    }
}

// Two descendant crossbars (horizontal descendant edges) at the same y must
// not share any horizontal x-range — otherwise they merge into one visual
// line at umbrellaY. Catches: multi-FAM umbrella merging bug class.
function assertUmbrellasDisjointAtY(edges) {
    const crossbars = edges
        .filter(e => e.type === 'descendant' && e.y1 === e.y2)
        .map(e => ({
            y: e.y1,
            l: Math.min(e.x1, e.x2),
            r: Math.max(e.x1, e.x2),
        }));
    const byY = new Map();
    for (const cb of crossbars) {
        if (!byY.has(cb.y)) byY.set(cb.y, []);
        byY.get(cb.y).push(cb);
    }
    for (const [y, group] of byY) {
        const sorted = group.slice().sort((a, b) => a.l - b.l);
        for (let i = 1; i < sorted.length; i++) {
            if (sorted[i].l < sorted[i - 1].r) {
                throw new Error(
                    `Descendant crossbar overlap at y=${y}: ` +
                    `[${sorted[i - 1].l}..${sorted[i - 1].r}] and ` +
                    `[${sorted[i].l}..${sorted[i].r}]`
                );
            }
        }
    }
}

// When two or more umbrella anchor drops share an anchor-x at a given y, no
// crossbar at that y may horizontally cross the shared anchor-x. Catches:
// the opposite-side-rule violation that produces visually-merged umbrellas.
function assertNoUmbrellaCrossesPersonCenter(edges) {
    const crossbars = edges.filter(e => e.type === 'descendant' && e.y1 === e.y2);
    const verticals = edges.filter(e => e.type === 'descendant' && e.x1 === e.x2 && e.y1 !== e.y2);
    // Group anchors by (x, top-y) — multiple verticals from same anchor are siblings of each other
    const anchorsByY = new Map();
    for (const v of verticals) {
        const top = Math.min(v.y1, v.y2);
        const bot = Math.max(v.y1, v.y2);
        const key = bot;
        if (!anchorsByY.has(key)) anchorsByY.set(key, new Map());
        const xMap = anchorsByY.get(key);
        if (!xMap.has(v.x1)) xMap.set(v.x1, 0);
        xMap.set(v.x1, xMap.get(v.x1) + 1);
    }
    for (const [y, xMap] of anchorsByY) {
        for (const [anchorX, count] of xMap) {
            if (count < 2) continue; // only multi-anchor case applies
            const cbsAtY = crossbars.filter(c => Math.abs(c.y1 - y) < 0.5);
            for (const cb of cbsAtY) {
                const l = Math.min(cb.x1, cb.x2);
                const r = Math.max(cb.x1, cb.x2);
                if (l < anchorX && anchorX < r) {
                    throw new Error(
                        `Crossbar [${l}..${r}] at y=${y} crosses shared anchor x=${anchorX}`
                    );
                }
            }
        }
    }
}

// Group descendant nodes by which umbrella they hang from. A "cluster" is a
// crossbar (multi-child) or a colinear anchor-vertical above a drop (single
// child). Returns Map<clusterId, { y, l, r, members: [nodes] }>.
function _clustersByUmbrella(nodes, edges) {
    const descNodes = nodes.filter(n => n.role === 'descendant');
    const descEdges = edges.filter(e => e.type === 'descendant');
    const crossbars = descEdges.filter(e => e.y1 === e.y2);
    const verticals = descEdges.filter(e => e.x1 === e.x2);
    const clusters = new Map();
    let synthCounter = 0;
    for (const child of descNodes) {
        const childCenter = child.x + NODE_W / 2;
        const drop = descEdges.find(e =>
            e.x1 === e.x2 &&
            Math.abs(e.x1 - childCenter) < 0.5 &&
            Math.abs(e.y2 - child.y) < 0.5
        );
        if (!drop) continue; // assertChildrenInParentClusterRange will catch this
        const cb = crossbars.find(e =>
            Math.abs(e.y1 - drop.y1) < 0.5 &&
            Math.min(e.x1, e.x2) - 0.5 <= drop.x1 &&
            drop.x1 <= Math.max(e.x1, e.x2) + 0.5
        );
        let id;
        if (cb) {
            id = `cb:${cb.x1},${cb.x2},${cb.y1}`;
        } else {
            const anchor = verticals.find(e =>
                Math.abs(e.x1 - drop.x1) < 0.5 &&
                Math.abs(e.y2 - drop.y1) < 0.5 &&
                e.y1 < drop.y1 - 0.5
            );
            id = anchor ? `anch:${anchor.x1},${anchor.y1},${anchor.y2}` : `orphan:${synthCounter++}`;
        }
        if (!clusters.has(id)) {
            clusters.set(id, { y: child.y, l: Infinity, r: -Infinity, members: [] });
        }
        const c = clusters.get(id);
        c.members.push(child);
        c.l = Math.min(c.l, child.x);
        c.r = Math.max(c.r, child.x + NODE_W);
    }
    return clusters;
}

// At any y, distinct clusters' x-ranges must not overlap. Catches:
// inter-cluster-gap bug class — one expanded cluster spilling into another.
function assertClusterXRangesDisjoint(nodes, edges) {
    const clusters = _clustersByUmbrella(nodes, edges);
    const byY = new Map();
    for (const [id, c] of clusters) {
        if (!byY.has(c.y)) byY.set(c.y, []);
        byY.get(c.y).push({ id, ...c });
    }
    for (const [y, group] of byY) {
        const sorted = group.slice().sort((a, b) => a.l - b.l);
        for (let i = 1; i < sorted.length; i++) {
            if (sorted[i].l < sorted[i - 1].r) {
                throw new Error(
                    `Cluster x-range overlap at y=${y}: ` +
                    `[${sorted[i - 1].l}..${sorted[i - 1].r}] (${sorted[i - 1].members.map(m => m.xref).join(',')}) ` +
                    `and [${sorted[i].l}..${sorted[i].r}] (${sorted[i].members.map(m => m.xref).join(',')})`
                );
            }
        }
    }
}

// Every node with the same `generation` field must share a single y coordinate.
// Catches: any future bug where a node lands on the wrong row.
function assertGenerationsAligned(nodes) {
    const yByGen = new Map();
    for (const n of nodes) {
        if (n.generation === undefined) continue;
        if (!yByGen.has(n.generation)) {
            yByGen.set(n.generation, { y: n.y, witness: n.xref });
            continue;
        }
        const seen = yByGen.get(n.generation);
        if (seen.y !== n.y) {
            throw new Error(
                `Generation alignment broken at gen=${n.generation}: ` +
                `${seen.witness} at y=${seen.y}, ${n.xref} at y=${n.y}`
            );
        }
    }
}

// Each descendant node must sit within its rendered parent's x-span (extended
// to include an on-row spouse), padded by half the cluster's width.
// Catches: cluster anchored to the right umbrella geometrically but mis-
// positioned relative to the actual parent (the bug `assertChildrenInParentClusterRange`
// can miss because it only checks crossbar containment, not parent identity).
function assertChildWithinParentSpanRange(nodes, edges) {
    if (typeof PARENTS === 'undefined') return;
    const nodeByXref = new Map(nodes.map(n => [n.xref, n]));
    const clusters = _clustersByUmbrella(nodes, edges);
    // Index clusters by member xref for fast lookup
    const clusterByMember = new Map();
    for (const [, c] of clusters) {
        for (const m of c.members) clusterByMember.set(m.xref, c);
    }
    const descNodes = nodes.filter(n => n.role === 'descendant');
    for (const c of descNodes) {
        const parentXrefs = PARENTS[c.xref] || [];
        const renderedParents = parentXrefs
            .map(x => nodeByXref.get(x))
            .filter(p => p && p.y < c.y);
        if (renderedParents.length === 0) continue;
        let spanL = Infinity, spanR = -Infinity;
        for (const p of renderedParents) {
            spanL = Math.min(spanL, p.x);
            spanR = Math.max(spanR, p.x + _nodeWidth(p));
        }
        const cluster = clusterByMember.get(c.xref);
        const halfCluster = cluster ? (cluster.r - cluster.l) / 2 : NODE_W / 2;
        const cCenter = c.x + NODE_W / 2;
        const lo = spanL - halfCluster;
        const hi = spanR + halfCluster;
        if (cCenter < lo - 0.5 || cCenter > hi + 0.5) {
            throw new Error(
                `${c.xref} (center=${cCenter}) outside parent span [${lo}..${hi}] ` +
                `(parents: ${renderedParents.map(p => `${p.xref}@${p.x}`).join(',')})`
            );
        }
    }
}

// Run every invariant. Order = cheapest/most-likely-to-fire first.
function assertAllLayoutInvariants({ nodes, edges }) {
    assertExactlyOneFocus(nodes);
    assertGenerationsAligned(nodes);
    assertNoNodeOverlap(nodes);
    assertSiblingOrderMonotonic(nodes);
    assertUmbrellasDisjointAtY(edges);
    assertNoUmbrellaCrossesPersonCenter(edges);
    assertChildrenInParentClusterRange(nodes, edges);
    assertClusterXRangesDisjoint(nodes, edges);
    assertChildWithinParentSpanRange(nodes, edges);
}

const { computeLayout } = require('../../js/viz_layout.js');

// Drop-in replacement for computeLayout in tests: runs the full invariant
// suite and returns the result unchanged. Tests that intentionally produce
// malformed layouts should call computeLayout directly instead.
function computeLayoutChecked(...args) {
    const result = computeLayout(...args);
    assertAllLayoutInvariants(result);
    return result;
}

module.exports = {
    assertNoNodeOverlap,
    assertExactlyOneFocus,
    assertSiblingOrderMonotonic,
    assertChildrenInParentClusterRange,
    assertUmbrellasDisjointAtY,
    assertNoUmbrellaCrossesPersonCenter,
    assertGenerationsAligned,
    assertClusterXRangesDisjoint,
    assertChildWithinParentSpanRange,
    assertAllLayoutInvariants,
    computeLayoutChecked,
    _clustersByUmbrella,
};
