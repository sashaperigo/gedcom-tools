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
        // Find a crossbar at the drop's top y that covers the drop's x
        const cb = crossbars.find(e =>
            Math.abs(e.y1 - drop.y1) < 0.5 &&
            Math.min(e.x1, e.x2) - 0.5 <= drop.x1 &&
            drop.x1 <= Math.max(e.x1, e.x2) + 0.5
        );
        // Single-child cluster has no crossbar (just an anchor + drop) — that's fine
        if (!cb && crossbars.some(c => Math.abs(c.y1 - drop.y1) < 0.5)) {
            throw new Error(
                `${child.xref} drop at x=${drop.x1} is outside crossbar range at y=${drop.y1}`
            );
        }
    }
}

module.exports = {
    assertNoNodeOverlap,
    assertExactlyOneFocus,
    assertSiblingOrderMonotonic,
    assertChildrenInParentClusterRange,
};
