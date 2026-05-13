// viz_layout subroutines: Reingold-Tilford-style left/right contours,
// required-separation calculation, chevron-clearance, sibling-extent,
// and focus-spouse subtree shift helpers.
// Used by computeLayout in viz_layout.js.

const CHEVRON_CLEARANCE = 40;
// Gap between a sibling and their own spouse — smaller than H_GAP so couples
// appear visually attached while sibling-pair groups remain clearly separated.

const SIB_MARRIAGE_GAP = 12;

// Female ancestor with siblings → chevron sits on the right side of the pill.

function _hasRightChevron(xref) {
    return (PEOPLE[xref]?.sex === 'F') &&
        (((RELATIVES[xref] && RELATIVES[xref].siblings) || []).length > 0);
}

// Male (or unknown) ancestor with siblings → chevron sits on the left side.

function _hasLeftChevron(xref) {
    return (PEOPLE[xref]?.sex !== 'F') &&
        (((RELATIVES[xref] && RELATIVES[xref].siblings) || []).length > 0);
}

// Right-side extension from xref's right edge outward. Accounts for both the
// sibling-expand chevron (which sits 4px off a female pill with siblings) and
// the inline sibling group when expanded.
//
// - Female ancestor with siblings, NOT expanded: returns CHEVRON_CLEARANCE (the
//   chevron's outward reach beyond the pill edge).
// - Female ancestor with siblings, EXPANDED: returns the full width of the
//   inline sibling group (CHEVRON_CLEARANCE + NODE_W*n + H_GAP*(n-1) + spouse widths).
// - Male / no-chevron / no-siblings: returns 0.

function _inlineSiblingExtentRight(xref, expandedSiblingsXrefs) {
    if (!_hasRightChevron(xref)) return 0;
    const expanded = expandedSiblingsXrefs && expandedSiblingsXrefs.has(xref);
    if (!expanded) return CHEVRON_CLEARANCE;
    const { NODE_W, H_GAP } = DESIGN;
    const sibs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
    let extent = CHEVRON_CLEARANCE;
    sibs.forEach((s, i) => {
        if (i > 0) extent += H_GAP;
        extent += NODE_W;
        const sp = (RELATIVES[s] && RELATIVES[s].spouses) || [];
        sp.forEach(() => { extent += SIB_MARRIAGE_GAP + NODE_W; });
    });
    return extent;
}

// Mirror of the above for the left-side extension from xref's left edge.

function _inlineSiblingExtentLeft(xref, expandedSiblingsXrefs) {
    if (!_hasLeftChevron(xref)) return 0;
    const expanded = expandedSiblingsXrefs && expandedSiblingsXrefs.has(xref);
    if (!expanded) return CHEVRON_CLEARANCE;
    const { NODE_W, H_GAP } = DESIGN;
    const sibs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
    let extent = CHEVRON_CLEARANCE;
    sibs.forEach((s, i) => {
        if (i > 0) extent += H_GAP;
        extent += NODE_W;
        const sp = (RELATIVES[s] && RELATIVES[s].spouses) || [];
        sp.forEach(() => { extent += SIB_MARRIAGE_GAP + NODE_W; });
    });
    return extent;
}

// Signed horizontal offset from xref's own center to its bio-children
// group center (xref + any inline expanded siblings, NOT spouses).
// Positive if group center is to the right of xref (female with right-expanded
// siblings), negative if to the left (male with left-expanded siblings).
// Returns 0 when siblings aren't expanded for xref.

function _bioGroupOffset(xref, expandedSiblingsXrefs) {
    if (!expandedSiblingsXrefs || !expandedSiblingsXrefs.has(xref)) return 0;
    const { NODE_W, H_GAP } = DESIGN;
    const sibs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
    if (sibs.length === 0) return 0;
    const sorted = _sortByBirthYear(sibs);
    const toRight = _hasRightChevron(xref);
    const sibCenters = [];
    if (toRight) {
        let cursor = NODE_W / 2 + CHEVRON_CLEARANCE; // xref.cx → first sib left edge
        sorted.forEach((sx, i) => {
            if (i > 0) cursor += H_GAP;
            sibCenters.push(cursor + NODE_W / 2);
            cursor += NODE_W;
            const sp = (RELATIVES[sx] && RELATIVES[sx].spouses) || [];
            sp.forEach(() => { cursor += SIB_MARRIAGE_GAP + NODE_W; });
        });
    } else if (_hasLeftChevron(xref)) {
        let cursor = -(NODE_W / 2 + CHEVRON_CLEARANCE); // xref.cx → first sib right edge (leftward)
        [...sorted].reverse().forEach((sx, i) => {
            if (i > 0) cursor -= H_GAP;
            sibCenters.push(cursor - NODE_W / 2);
            cursor -= NODE_W;
            const sp = (RELATIVES[sx] && RELATIVES[sx].spouses) || [];
            sp.forEach(() => { cursor -= SIB_MARRIAGE_GAP + NODE_W; });
        });
    } else {
        return 0;
    }
    if (sibCenters.length === 0) return 0;
    const all = [0, ...sibCenters];
    return (Math.min(...all) + Math.max(...all)) / 2;
}


function _rightContour(xref, expandedAncestors, expandedSiblingsXrefs) {
    const { NODE_W } = DESIGN;
    const contour = [NODE_W / 2 + _inlineSiblingExtentRight(xref, expandedSiblingsXrefs)];
    if (!expandedAncestors.has(xref)) return contour;
    const parents = PARENTS[xref] ?? [];
    const f = parents[0] ?? null;
    const m = parents[1] ?? null;
    if (!f && !m) return contour;
    // Parent couple is re-centered over xref's bio-children group, so everything
    // above xref is shifted by groupOffset relative to xref's own center.
    const groupOffset = _bioGroupOffset(xref, expandedSiblingsXrefs);
    if (f && m) {
        // father.cx = xref.cx + groupOffset - sep/2; mother.cx = xref.cx + groupOffset + sep/2.
        // Either subtree can extend rightward at any depth — the father's own
        // maternal line can reach past the father's center even though the father
        // sits left of xref. Take the max of both contributions at each depth.
        const sep = _requiredSeparation(f, m, expandedAncestors, expandedSiblingsXrefs);
        const fc = _rightContour(f, expandedAncestors, expandedSiblingsXrefs);
        const mc = _rightContour(m, expandedAncestors, expandedSiblingsXrefs);
        const maxD = Math.max(fc.length, mc.length);
        for (let d = 0; d < maxD; d++) {
            let best = -Infinity;
            if (d < fc.length) best = Math.max(best, groupOffset - sep / 2 + fc[d]);
            if (d < mc.length) best = Math.max(best, groupOffset + sep / 2 + mc[d]);
            contour[d + 1] = best;
        }
    } else {
        const only = f || m;
        const oc = _rightContour(only, expandedAncestors, expandedSiblingsXrefs);
        for (let d = 0; d < oc.length; d++) contour[d + 1] = groupOffset + oc[d];
    }
    return contour;
}


function _leftContour(xref, expandedAncestors, expandedSiblingsXrefs) {
    const { NODE_W } = DESIGN;
    const contour = [NODE_W / 2 + _inlineSiblingExtentLeft(xref, expandedSiblingsXrefs)];
    if (!expandedAncestors.has(xref)) return contour;
    const parents = PARENTS[xref] ?? [];
    const f = parents[0] ?? null;
    const m = parents[1] ?? null;
    if (!f && !m) return contour;
    const groupOffset = _bioGroupOffset(xref, expandedSiblingsXrefs);
    if (f && m) {
        // Leftward distance from xref of a node at depth d+1 =
        //   father side: -groupOffset + sep/2 + fc[d]   (father is left of xref)
        //   mother side: -groupOffset - sep/2 + mc[d]   (mother is right of xref;
        //                                                her own left wing can still
        //                                                poke left of xref.cx)
        // Take max (most-leftward) at each depth.
        const sep = _requiredSeparation(f, m, expandedAncestors, expandedSiblingsXrefs);
        const fc = _leftContour(f, expandedAncestors, expandedSiblingsXrefs);
        const mc = _leftContour(m, expandedAncestors, expandedSiblingsXrefs);
        const maxD = Math.max(fc.length, mc.length);
        for (let d = 0; d < maxD; d++) {
            let best = -Infinity;
            if (d < fc.length) best = Math.max(best, -groupOffset + sep / 2 + fc[d]);
            if (d < mc.length) best = Math.max(best, -groupOffset - sep / 2 + mc[d]);
            contour[d + 1] = best;
        }
    } else {
        const only = f || m;
        const oc = _leftContour(only, expandedAncestors, expandedSiblingsXrefs);
        for (let d = 0; d < oc.length; d++) contour[d + 1] = -groupOffset + oc[d];
    }
    return contour;
}

// Center-to-center separation required so the two parent subtrees do not
// overlap at any shared depth. Floor = SLOT (parents sit adjacent at row 0).

function _requiredSeparation(fatherXref, motherXref, expandedAncestors, expandedSiblingsXrefs) {
    const { NODE_W, H_GAP, FAMILY_GAP } = DESIGN;
    const rf = _rightContour(fatherXref, expandedAncestors, expandedSiblingsXrefs);
    const lm = _leftContour(motherXref, expandedAncestors, expandedSiblingsXrefs);
    const shared = Math.min(rf.length, lm.length);
    let sep = NODE_W + H_GAP;
    for (let d = 0; d < shared; d++) {
        const gap = d === 0 ? H_GAP : FAMILY_GAP;
        sep = Math.max(sep, rf[d] + lm[d] + gap);
    }
    return sep;
}

// Required x-shift for a focus-spouse so its parent subtree clears the
// focus-parents subtree at every row. Positive = move rightward
// (right-side spouse); negative = move leftward (left-side spouse).
// Returns 0 when no collision is possible: focus has no inner-facing
// parent, spouse has no parents, or current spacing already satisfies
// _requiredSeparation.

function _computeFocusSpouseShift(entry, focusFatherXref, focusMotherXref, focusFatherX, focusMotherX, expandedAncestors, expandedSibs) {
    const { NODE_W } = DESIGN;
    const spParents = PARENTS[entry.xref] ?? [];
    const spFatherXref = spParents[0] ?? null;
    const spMotherXref = spParents[1] ?? null;
    if (!spFatherXref && !spMotherXref) return 0;

    // Where the spouse's inner-facing parent would land if we placed the
    // spouse subtree at its un-shifted originalX. Mirrors _placeAncestors.
    const spouseCenterX = entry.originalX + NODE_W / 2;
    let spouseInnerParentXref;
    let spouseInnerParentCenter;
    if (spFatherXref && spMotherXref) {
        const spSep = _requiredSeparation(spFatherXref, spMotherXref, expandedAncestors, expandedSibs);
        if (entry.side === 'right') {
            spouseInnerParentXref = spFatherXref;
            spouseInnerParentCenter = spouseCenterX - spSep / 2;
        } else {
            spouseInnerParentXref = spMotherXref;
            spouseInnerParentCenter = spouseCenterX + spSep / 2;
        }
    } else {
        spouseInnerParentXref = spFatherXref || spMotherXref;
        spouseInnerParentCenter = spouseCenterX;
    }

    if (entry.side === 'right') {
        if (!focusMotherXref || focusMotherX === null) return 0;
        const focusInnerCenter = focusMotherX + NODE_W / 2;
        const required = _requiredSeparation(focusMotherXref, spouseInnerParentXref, expandedAncestors, expandedSibs);
        const actual = spouseInnerParentCenter - focusInnerCenter;
        return actual >= required ? 0 : required - actual;
    } else {
        if (!focusFatherXref || focusFatherX === null) return 0;
        const focusInnerCenter = focusFatherX + NODE_W / 2;
        const required = _requiredSeparation(spouseInnerParentXref, focusFatherXref, expandedAncestors, expandedSibs);
        const actual = focusInnerCenter - spouseInnerParentCenter;
        return actual >= required ? 0 : -(required - actual);
    }
}

// Mutate nodes/edges in place: shift every gen-0 node and every edge
// endpoint in the gen-0 zone (y >= ancUmbrellaY) that lies on the
// focus-spouse's "side" of the canvas by dx. Focus-parents subtree
// (y < ancUmbrellaY) is untouched.

function _shiftFocusSpouseSubtree(nodes, edges, entry, dx) {
    const { NODE_W, NODE_H, ROW_HEIGHT } = DESIGN;
    const ancUmbrellaY = -(ROW_HEIGHT - NODE_H) / 2;
    const onSide = entry.side === 'right'
        ? (x) => x >= entry.originalX
        : (x) => x <= entry.originalX + NODE_W;

    for (const n of nodes) {
        if (n.y === 0 && onSide(n.x)) {
            n.x += dx;
        }
    }
    for (const e of edges) {
        if (e.y1 < ancUmbrellaY || e.y2 < ancUmbrellaY) continue;
        if (onSide(e.x1)) e.x1 += dx;
        if (onSide(e.x2)) e.x2 += dx;
    }
}

// ---------------------------------------------------------------------------
// Focus children extents (preview Phase 2 placement before siblings are packed)
// ---------------------------------------------------------------------------

// Returns { leftEdge, rightEdge } in absolute coords for focus's child cluster(s),
// or null if focus has no children. Mirrors Phase 2's placement so that Phase 1
// sibling packing can push expanded-children siblings far enough from focus
// to clear focus's child cluster on the same row.

// ---------------------------------------------------------------------------
// Exports (node only)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
    module.exports = {
        CHEVRON_CLEARANCE,
        SIB_MARRIAGE_GAP,
        _hasRightChevron,
        _hasLeftChevron,
        _inlineSiblingExtentRight,
        _inlineSiblingExtentLeft,
        _bioGroupOffset,
        _rightContour,
        _leftContour,
        _requiredSeparation,
        _computeFocusSpouseShift,
        _shiftFocusSpouseSubtree,
    };
    if (typeof global !== 'undefined') Object.assign(global, module.exports);
}
