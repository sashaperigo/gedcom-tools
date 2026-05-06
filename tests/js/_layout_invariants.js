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

module.exports = {
    assertNoNodeOverlap,
};
