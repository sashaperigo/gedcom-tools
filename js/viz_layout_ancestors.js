// viz_layout subroutines: ancestor placement (recursive),
// child-umbrella edge emission, and ancestor sibling placement.
// Used by computeLayout in viz_layout.js.


function _placeAncestors(xref, x, y, generation, expandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref) {
    visibleSpouseFams = visibleSpouseFams || new Set();
    const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP } = DESIGN;
    const SLOT = NODE_W + H_GAP;

    if (!expandedAncestors.has(xref)) return;

    const parentPair = PARENTS[xref] ?? [];
    const fatherXref = parentPair[0] ?? null;
    const motherXref = parentPair[1] ?? null;

    if (!fatherXref && !motherXref) return;

    const nextGen = generation - 1;
    const nextY = nextGen * ROW_HEIGHT;

    // Group center: parent couple re-centers over the sibling group (xref +
    // already-placed inline siblings) so the drop to the umbrella is straight.
    const childCenter = x + NODE_W / 2;
    const sibXrefs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
    const sibCenters = sibXrefs
        .map(sx => nodes.find(n => n.xref === sx && n.y === y))
        .filter(Boolean)
        .map(n => n.x + NODE_W / 2);
    const groupMin = Math.min(childCenter, ...sibCenters);
    const groupMax = Math.max(childCenter, ...sibCenters);
    const groupCenterX = (groupMin + groupMax) / 2;

    if (fatherXref && motherXref) {
        // Contour-based separation keeps deep ancestors from colliding; couple
        // sits centered over the sibling group.
        const sep = _requiredSeparation(fatherXref, motherXref, expandedAncestors, expandedSiblingsXrefs);
        const fatherX = groupCenterX - sep / 2 - NODE_W / 2;
        const motherX = groupCenterX + sep / 2 - NODE_W / 2;

        nodes.push({ xref: fatherXref, x: fatherX, y: nextY, generation: nextGen, role: 'ancestor' });
        nodes.push({ xref: motherXref, x: motherX, y: nextY, generation: nextGen, role: 'ancestor' });

        // Marriage edge between the parents.
        const parentMidY = nextY + NODE_H / 2;
        edges.push({
            x1: fatherX + NODE_W,
            y1: parentMidY,
            x2: motherX,
            y2: parentMidY,
            type: 'marriage',
        });

        // Umbrella down to the child row. If the child (xref) has expanded
        // siblings, the umbrella spans all biological children of this couple;
        // otherwise it's a single vertical drop.
        _emitChildUmbrella(xref, x, y, parentMidY, nodes, edges);

        // Place siblings of f/m BEFORE recursing deeper so their subtree umbrellas
        // can span the right groups.
        _placeAncestorSiblings(fatherXref, fatherX, nextY, expandedSiblingsXrefs, expandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        _placeAncestorSiblings(motherXref, motherX, nextY, expandedSiblingsXrefs, expandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);

        _placeAncestors(fatherXref, fatherX, nextY, nextGen, expandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        _placeAncestors(motherXref, motherX, nextY, nextGen, expandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
    } else {
        const singleParent = fatherXref || motherXref;
        const singleX = groupCenterX - NODE_W / 2;
        nodes.push({ xref: singleParent, x: singleX, y: nextY, generation: nextGen, role: 'ancestor' });

        // Single parent → umbrella / straight drop from parent bottom to child top.
        _emitChildUmbrella(xref, x, y, nextY + NODE_H, nodes, edges);

        _placeAncestorSiblings(singleParent, singleX, nextY, expandedSiblingsXrefs, expandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        _placeAncestors(singleParent, singleX, nextY, nextGen, expandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
    }
}

// For the given child (xref) at (x, y), emit edges connecting the parent
// layer's anchor (at anchorY) down to this child. If xref has siblings
// already placed in `nodes` at the same row, emit a proper umbrella:
// anchor-drop → horizontal crossbar → per-child drops to each biological
// child (xref + siblings, NOT siblings' spouses).
// Otherwise, emit a single vertical drop from anchorY to the child's top.

function _emitChildUmbrella(xref, x, y, anchorY, nodes, edges) {
    const { NODE_W, NODE_H, ROW_HEIGHT } = DESIGN;

    const sibXrefs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
    const sibNodes = sibXrefs
        .map(sx => nodes.find(n => n.xref === sx && n.y === y))
        .filter(Boolean);

    const childCx = x + NODE_W / 2;

    if (sibNodes.length === 0) {
        // Simple drop, no siblings to group under an umbrella.
        edges.push({
            x1: childCx,
            y1: anchorY,
            x2: childCx,
            y2: y,
            type: 'ancestor',
        });
        return;
    }

    const umbrellaY = y - (ROW_HEIGHT - NODE_H) / 2;

    // Per-child centers (ancestor + each expanded sibling; NOT spouses).
    const centers = [childCx, ...sibNodes.map(n => n.x + NODE_W / 2)].sort((a, b) => a - b);
    const groupCenterX = (centers[0] + centers[centers.length - 1]) / 2;

    // Anchor drop from parent marriage-midpoint down to the umbrella bar.
    // The parent couple is placed centered over groupCenterX, so this is always
    // a single straight vertical segment — no L-shape needed.
    edges.push({
        x1: groupCenterX,
        y1: anchorY,
        x2: groupCenterX,
        y2: umbrellaY,
        type: 'ancestor',
    });

    // Crossbar from leftmost to rightmost child center.
    if (centers.length > 1) {
        edges.push({
            x1: centers[0],
            y1: umbrellaY,
            x2: centers[centers.length - 1],
            y2: umbrellaY,
            type: 'ancestor',
        });
    }

    // Vertical drop from umbrella down to each child's top.
    centers.forEach(cx => {
        edges.push({
            x1: cx,
            y1: umbrellaY,
            x2: cx,
            y2: y,
            type: 'ancestor',
        });
    });
}

// ---------------------------------------------------------------------------
// Ancestor sibling placement
// ---------------------------------------------------------------------------

// For a single ancestor node at (ancX, ancY), if it's in expandedSiblingsXrefs,
// place its full siblings INLINE at the same y as the ancestor, ALL on the
// OUTWARD side of the couple (same side as the sibling-expand chevron):
//   - Female ancestor (right-side of a couple) → siblings stack to her RIGHT
//   - Male ancestor (left-side of a couple)    → siblings stack to his LEFT
// This keeps spouses adjacent (no sibling ever splits the couple) and matches
// the direction the sibling-expand chevron points.
//
// Within the sibling stack, siblings are chronologically ordered left-to-right:
//   - Right stack (female): ancestor → oldest sibling → ... → youngest
//   - Left stack (male):    oldest → ... → youngest → ancestor
// The ancestor is pinned to the innermost edge even if that puts her outside
// strict birth order — spouse-adjacency wins over chronology.
//
// The gap between ancestor and first sibling is CHEVRON_CLEARANCE (not H_GAP)
// so the r=8 sibling-expand chevron fits between them without overlap.
// Grouping is handled by the parent umbrella (_emitChildUmbrella); no bracket
// edge is emitted from here.

function _placeAncestorSiblings(ancXref, ancX, ancY, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref) {
    visibleSpouseFams = visibleSpouseFams || new Set();
    if (!expandedSiblingsXrefs || !expandedSiblingsXrefs.has(ancXref)) return;
    const sibs = RELATIVES[ancXref]?.siblings ?? [];
    if (sibs.length === 0) return;

    const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP } = DESIGN;
    const sorted = _sortByBirthYear(sibs);
    const generation = Math.round(ancY / ROW_HEIGHT);
    const midY = ancY + NODE_H / 2;
    const toRight = _hasRightChevron(ancXref); // female with siblings

    // Extra padding beyond pill edge to reserve space for a sibling's expanded-
    // descendant subtree poking out past the pill. Only a sibling's OWN pill
    // carries this (descendants hang under the sibling, not spouses).
    const extraRight = (sx) => Math.max(0, _descendantHalfwidth(sx, 'right', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref) - NODE_W / 2);
    const extraLeft = (sx) => Math.max(0, _descendantHalfwidth(sx, 'left', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref) - NODE_W / 2);

    // If a sibling has an expanded FAM, its children will be placed on the
    // child row (ancY + ROW_HEIGHT) centered under that sibling. Those
    // children must not collide with nodes already placed on that child row
    // by earlier phases (e.g., the focus parent's own ancestor-siblings at
    // a shallower generation).
    //
    // For the toRight fan: the rightmost-relevant child-row node (left
    // barrier) is the one with the max x+NODE_W; since siblings are placed
    // left-to-right and any same-call previous siblings are to our LEFT,
    // using the max across ALL childY nodes is correct.
    //
    // Mirror reasoning for toLeft fan: the min x (right barrier) across ALL
    // childY nodes.
    const childY = ancY + ROW_HEIGHT;
    let childRowLeftBarrier = -Infinity;
    let childRowRightBarrier = Infinity;
    nodes.forEach(n => {
        if (n.y !== childY) return;
        if (n.x + NODE_W > childRowLeftBarrier) childRowLeftBarrier = n.x + NODE_W;
        if (n.x < childRowRightBarrier) childRowRightBarrier = n.x;
    });

    if (toRight) {
        // Siblings fan right of ancestor, chronological L→R (oldest closest to ancestor).
        let cursor = ancX + NODE_W + CHEVRON_CLEARANCE;
        sorted.forEach((sibXref, i) => {
            if (i > 0) {
                cursor += H_GAP + extraLeft(sibXref);
            } else {
                cursor += extraLeft(sibXref);
            }
            // Cross-row barrier: if this sibling has an expanded FAM with kids
            // that will land on childY, make sure the leftmost kid clears the
            // left barrier from pre-existing child-row nodes.
            if (childRowLeftBarrier > -Infinity) {
                const halfLeft = _descendantHalfwidth(sibXref, 'left', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref);
                if (halfLeft > NODE_W / 2) {
                    const minSibX = childRowLeftBarrier + H_GAP + halfLeft - NODE_W / 2;
                    if (minSibX > cursor) cursor = minSibX;
                }
            }
            const sibX = cursor;
            nodes.push({ xref: sibXref, x: sibX, y: ancY, generation, role: 'ancestor_sibling' });
            cursor = sibX + NODE_W;
            const sibSpouses = _visibleSpousesFor(sibXref, RELATIVES[sibXref]?.spouses ?? [], visibleSpouseFams, focusXref);
            sibSpouses.forEach(spXref => {
                const spX = cursor + SIB_MARRIAGE_GAP;
                nodes.push({ xref: spXref, x: spX, y: ancY, generation, role: 'ancestor_sibling_spouse' });
                edges.push({ x1: cursor, y1: midY, x2: spX, y2: midY, type: 'marriage' });
                cursor = spX + NODE_W;
            });
            cursor = Math.max(cursor, sibX + NODE_W / 2 + _descendantHalfwidth(sibXref, 'right', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref));
        });
    } else {
        // Siblings fan left of ancestor, chronological L→R (youngest closest to ancestor).
        const reversed = [...sorted].reverse();
        let rightEdge = ancX - CHEVRON_CLEARANCE;
        reversed.forEach((sibXref, i) => {
            if (i > 0) {
                rightEdge -= H_GAP + extraRight(sibXref);
            } else {
                rightEdge -= extraRight(sibXref);
            }
            if (childRowRightBarrier < Infinity) {
                const halfRight = _descendantHalfwidth(sibXref, 'right', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref);
                if (halfRight > NODE_W / 2) {
                    const maxSibRight = childRowRightBarrier - H_GAP - halfRight + NODE_W / 2;
                    if (maxSibRight < rightEdge) rightEdge = maxSibRight;
                }
            }
            const sibSpouses = _visibleSpousesFor(sibXref, RELATIVES[sibXref]?.spouses ?? [], visibleSpouseFams, focusXref);
            const sibX = rightEdge - NODE_W;
            nodes.push({ xref: sibXref, x: sibX, y: ancY, generation, role: 'ancestor_sibling' });
            let cursorLeft = sibX;
            sibSpouses.forEach(spXref => {
                const spX = cursorLeft - SIB_MARRIAGE_GAP - NODE_W;
                nodes.push({ xref: spXref, x: spX, y: ancY, generation, role: 'ancestor_sibling_spouse' });
                edges.push({ x1: spX + NODE_W, y1: midY, x2: cursorLeft, y2: midY, type: 'marriage' });
                cursorLeft = spX;
            });
            rightEdge = Math.min(cursorLeft, sibX + NODE_W / 2 - _descendantHalfwidth(sibXref, 'left', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref));
        });
    }
}

// ---------------------------------------------------------------------------
// Contour-based separation (Reingold-Tilford style)
// ---------------------------------------------------------------------------

// Each contour is an array indexed by depth (0 = the root row itself).
// Element d = distance from the subtree-root center to the rightmost
// (_rightContour) or leftmost (_leftContour) point of the subtree at depth d.

// Clearance kept on the chevron side of every ancestor pill that has siblings,
// so the r=8 sibling-expand chevron at 4px offset doesn't collide with a
// neighbor pill or an adjacent couple across the row. 40 = r(8)*2 + gap(4) + buffer(20).

// ---------------------------------------------------------------------------
// Exports (node only)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
    module.exports = {
        _placeAncestors,
        _emitChildUmbrella,
        _placeAncestorSiblings,
    };
    if (typeof global !== 'undefined') Object.assign(global, module.exports);
}
