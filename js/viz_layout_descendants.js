// viz_layout subroutines: descendant (children) placement,
// descendant-aware sibling packing, and focus-children extent preview.
// Used by computeLayout in viz_layout.js.


function _placeChildrenOfPerson(personXref, visibleSpouseFams, focusXref, nodes, edges) {
    const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP } = DESIGN;
    const CHILD_MARRIAGE_GAP = H_GAP;
    const INTER_FAM_GAP = H_GAP * 8;

    if (typeof FAMILIES === 'undefined' || !FAMILIES) return;
    const personNode = nodes.find(n => n.xref === personXref);
    if (!personNode) return;

    const personFams = Object.keys(FAMILIES)
        .filter(f => {
            const fam = FAMILIES[f];
            return fam && (fam.husb === personXref || fam.wife === personXref) && (fam.chil || []).length > 0;
        });
    if (personFams.length === 0) return;

    const personY = personNode.y;
    const childY = personY + ROW_HEIGHT;
    const personCenter = personNode.x + NODE_W / 2;
    const visibleUmbrellaY = personY + NODE_H + (ROW_HEIGHT - NODE_H) / 2;

    // Skip FAMs whose children are all already placed at childY. This prevents
    // Phase 3 from re-rendering the focus row's siblings when a parent of the
    // focus person is in expandedChildrenPersons (stale state from a prior focus).
    const alreadyAtChildY = new Set(nodes.filter(n => n.y === childY).map(n => n.xref));
    const activeFams = personFams.filter(f =>
        (FAMILIES[f].chil || []).some(c => !alreadyAtChildY.has(c))
    );
    if (activeFams.length === 0) return;

    // Visible FAM = first childful FAM whose other-parent is on-row.
    let visibleFamXref = null;
    let visibleSpouseNode = null;
    for (const f of activeFams) {
        const fam = FAMILIES[f];
        const other = fam.husb === personXref ? fam.wife : fam.husb;
        if (!other) continue;
        const otherNode = nodes.find(n => n.xref === other && n.y === personY);
        if (otherNode) { visibleFamXref = f; visibleSpouseNode = otherNode; break; }
    }
    // If no childful FAM has a visible spouse, look across all FAMs for any
    // on-row spouse — their x tells us which side to place the other cluster.
    if (!visibleSpouseNode) {
        for (const f of Object.keys(FAMILIES)) {
            const fam = FAMILIES[f];
            if (!fam || (fam.husb !== personXref && fam.wife !== personXref)) continue;
            const other = fam.husb === personXref ? fam.wife : fam.husb;
            if (!other) continue;
            const otherNode = nodes.find(n => n.xref === other && n.y === personY);
            if (otherNode) { visibleSpouseNode = otherNode; break; }
        }
    }

    const famEarliestBirth = (f) =>
        Math.min(...FAMILIES[f].chil.map(c =>
            (typeof PEOPLE !== 'undefined' && PEOPLE[c]?.birth_year) || 9999
        ));

    const buildGroupsForFam = (famXref) => {
        const fam = FAMILIES[famXref];
        const kidsSorted = fam.chil
            .filter(c => !alreadyAtChildY.has(c))
            .slice().sort((a, b) => {
                const ya = (typeof PEOPLE !== 'undefined' && PEOPLE[a]?.birth_year) || 9999;
                const yb = (typeof PEOPLE !== 'undefined' && PEOPLE[b]?.birth_year) || 9999;
                return ya - yb;
            });
        return kidsSorted.map(childXref => {
            const childSpouses = _visibleSpousesFor(
                childXref,
                (typeof RELATIVES !== 'undefined' && RELATIVES[childXref]?.spouses) || [],
                visibleSpouseFams,
                focusXref,
            );
            const width = NODE_W + childSpouses.length * (CHILD_MARRIAGE_GAP + NODE_W);
            return { famXref, childXref, childSpouses, width };
        });
    };

    const visibleGroups = visibleFamXref ? buildGroupsForFam(visibleFamXref) : [];
    const otherFamsSorted = activeFams
        .filter(f => f !== visibleFamXref)
        .sort((a, b) => famEarliestBirth(a) - famEarliestBirth(b));
    // Merge all non-visible-FAM children into one flat cluster sorted by birth
    // year with uniform H_GAP between them (no FAM-boundary gaps within the
    // other cluster).
    const otherGroups = otherFamsSorted.flatMap(buildGroupsForFam)
        .sort((a, b) => {
            const ya = (typeof PEOPLE !== 'undefined' && PEOPLE[a.childXref]?.birth_year) || 9999;
            const yb = (typeof PEOPLE !== 'undefined' && PEOPLE[b.childXref]?.birth_year) || 9999;
            return ya - yb;
        })
        .map(g => ({ ...g, famXref: null }));

    const groupsWidth = (groups) => groups.reduce((w, g, i) => {
        if (i === 0) return g.width;
        const gap = groups[i - 1].famXref === g.famXref ? H_GAP : INTER_FAM_GAP;
        return w + gap + g.width;
    }, 0);

    const visibleWidth = groupsWidth(visibleGroups);
    const otherWidth = groupsWidth(otherGroups);

    const marriageMidpointX = visibleFamXref && visibleSpouseNode
        ? (personCenter + visibleSpouseNode.x + NODE_W / 2) / 2
        : null;

    // Ideal start positions. Other cluster goes on the opposite side of
    // personCenter from the visible spouse so its umbrella horizontal can
    // never extend past personCenter into the visible-FAM drop's territory.
    let visibleIdealStart = marriageMidpointX !== null
        ? marriageMidpointX - visibleWidth / 2
        : null;
    const spouseRight = !!(visibleSpouseNode && visibleSpouseNode.x > personNode.x);
    let otherIdealStart;
    if (visibleSpouseNode) {
        otherIdealStart = spouseRight
            ? personCenter - otherWidth  // right edge at personCenter
            : personCenter;              // left edge at personCenter
    } else {
        otherIdealStart = personCenter - otherWidth / 2;
    }

    // Free-gap collision avoidance: clamp a cluster's start into the nearest
    // gap at childY big enough to hold it. Re-called per cluster so the
    // second cluster sees the first cluster's pills as obstacles.
    const pickStartInFreeGap = (idealStart, clusterWidth) => {
        const occupied = nodes.filter(n => n.y === childY);
        if (occupied.length === 0) return idealStart;
        const sortedOccupied = occupied
            .map(n => [n.x, n.x + NODE_W])
            .sort((a, b) => a[0] - b[0]);
        const merged = [];
        for (const [l, r] of sortedOccupied) {
            if (merged.length && l <= merged[merged.length - 1][1]) {
                merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], r);
            } else {
                merged.push([l, r]);
            }
        }
        const gaps = [];
        let prevRight = -Infinity;
        for (const [l, r] of merged) {
            const gapL = prevRight === -Infinity ? -Infinity : prevRight + CHEVRON_CLEARANCE;
            const gapR = l - CHEVRON_CLEARANCE;
            if (gapR - gapL >= clusterWidth) gaps.push([gapL, gapR]);
            prevRight = r;
        }
        gaps.push([prevRight === -Infinity ? -Infinity : prevRight + CHEVRON_CLEARANCE, Infinity]);

        let best = null, bestDist = Infinity;
        for (const [gL, gR] of gaps) {
            if (gR - gL < clusterWidth) continue;
            const minStart = gL;
            const maxStart = gR - clusterWidth;
            const clamped = Math.max(minStart, Math.min(maxStart, idealStart));
            const dist = Math.abs(clamped - idealStart);
            if (dist < bestDist) { bestDist = dist; best = clamped; }
        }
        return best !== null ? best : idealStart;
    };

    // Emit child + spouse pills and inter-spouse marriage edges for one
    // cluster; return the ordered list of child center x-coordinates.
    const emitClusterNodes = (groups, startX) => {
        const generation = Math.round(childY / ROW_HEIGHT);
        const centers = [];
        let cursor = startX;
        for (let i = 0; i < groups.length; i++) {
            const g = groups[i];
            if (i > 0) {
                const gap = groups[i - 1].famXref === g.famXref ? H_GAP : INTER_FAM_GAP;
                cursor += gap;
            }
            const childX = cursor;
            nodes.push({ xref: g.childXref, x: childX, y: childY, generation, role: 'descendant' });
            centers.push(childX + NODE_W / 2);
            g.childSpouses.forEach((sxref, si) => {
                const spouseX = childX + (si + 1) * (NODE_W + CHILD_MARRIAGE_GAP);
                nodes.push({ xref: sxref, x: spouseX, y: childY, generation, role: 'descendant_spouse' });
                const prevX = si === 0 ? childX : childX + si * (NODE_W + CHILD_MARRIAGE_GAP);
                edges.push({
                    x1: prevX + NODE_W,
                    y1: childY + NODE_H / 2,
                    x2: spouseX,
                    y2: childY + NODE_H / 2,
                    type: 'marriage',
                });
            });
            cursor += g.width;
        }
        return centers;
    };

    // When the person owns BOTH cluster types, the other-FAM umbrella shifts
    // DOWN by H_GAP so its horizontal connector cannot share a y-line with
    // the visible-FAM crossbar. See docs/learnings/umbrella-connector-overlap.md.
    const otherUmbrellaY = (visibleGroups.length > 0 && otherGroups.length > 0)
        ? visibleUmbrellaY + H_GAP
        : visibleUmbrellaY;

    const emitUmbrella = (anchorX, anchorTopY, centers, umbrellaY) => {
        if (centers.length === 0) return;
        const leftCenter = Math.min(...centers);
        const rightCenter = Math.max(...centers);
        const umbrellaAnchorX = Math.min(Math.max(anchorX, leftCenter), rightCenter);
        edges.push({ x1: anchorX, y1: anchorTopY, x2: anchorX, y2: umbrellaY, type: 'descendant' });
        if (umbrellaAnchorX !== anchorX) {
            edges.push({ x1: anchorX, y1: umbrellaY, x2: umbrellaAnchorX, y2: umbrellaY, type: 'descendant' });
        }
        if (centers.length > 1) {
            edges.push({ x1: leftCenter, y1: umbrellaY, x2: rightCenter, y2: umbrellaY, type: 'descendant' });
        }
        centers.forEach(cx => {
            edges.push({ x1: cx, y1: umbrellaY, x2: cx, y2: childY, type: 'descendant' });
        });
    };

    // Pre-nudge: when the gap between the visible cluster's ideal right edge and
    // the nearest obstacle on the other side is too narrow for the other cluster,
    // shift visibleIdealStart toward the obstacle to open the gap. This lets the
    // other cluster land between the two families instead of being pushed past
    // the obstacle entirely.
    let shiftedForGap = false;
    if (visibleGroups.length > 0 && otherGroups.length > 0 && visibleIdealStart !== null) {
        if (!spouseRight) {
            // Visible goes LEFT → other fills gap to the RIGHT. Find nearest right obstacle.
            const visibleRightEdge = visibleIdealStart + visibleWidth;
            const rightObstacle = nodes
                .filter(n => n.y === childY && n.x > visibleRightEdge - CHEVRON_CLEARANCE)
                .reduce((best, n) => (!best || n.x < best.x) ? n : best, null);
            if (rightObstacle) {
                const maxStart = rightObstacle.x - 2 * CHEVRON_CLEARANCE - otherWidth - visibleWidth;
                if (visibleIdealStart > maxStart) {
                    visibleIdealStart = maxStart;
                    shiftedForGap = true;
                }
            }
        } else {
            // Visible goes RIGHT → other fills gap to the LEFT. Find nearest left obstacle.
            const leftObstacle = nodes
                .filter(n => n.y === childY && n.x + NODE_W < visibleIdealStart + CHEVRON_CLEARANCE)
                .reduce((best, n) => (!best || n.x + NODE_W > best.x + NODE_W) ? n : best, null);
            if (leftObstacle) {
                const minStart = leftObstacle.x + NODE_W + 2 * CHEVRON_CLEARANCE + otherWidth;
                if (visibleIdealStart < minStart) {
                    visibleIdealStart = minStart;
                    shiftedForGap = true;
                }
            }
        }
    }

    let actualVisibleStart = visibleIdealStart;
    if (visibleGroups.length > 0) {
        actualVisibleStart = pickStartInFreeGap(visibleIdealStart, visibleWidth);
        const centers = emitClusterNodes(visibleGroups, actualVisibleStart);
        emitUmbrella(marriageMidpointX, personY + NODE_H / 2, centers, visibleUmbrellaY);
    }
    if (otherGroups.length > 0) {
        // When we pre-shifted the visible cluster to make room, the other cluster
        // finds the natural gap via pickStartInFreeGap — no additional push needed.
        // Only enforce INTER_FAM_GAP when no shift occurred (open space, no obstacle).
        if (visibleGroups.length > 0 && !shiftedForGap) {
            if (spouseRight && actualVisibleStart + visibleWidth > personCenter) {
                otherIdealStart = Math.min(otherIdealStart, actualVisibleStart - INTER_FAM_GAP - otherWidth);
            } else if (!spouseRight && actualVisibleStart < personCenter) {
                otherIdealStart = Math.max(otherIdealStart, actualVisibleStart + visibleWidth + INTER_FAM_GAP);
            }
        }
        const startX = pickStartInFreeGap(otherIdealStart, otherWidth);
        const centers = emitClusterNodes(otherGroups, startX);
        emitUmbrella(personCenter, personY + NODE_H, centers, otherUmbrellaY);
    }
}

// ---------------------------------------------------------------------------
// Recursive ancestor placement
// ---------------------------------------------------------------------------

function _focusChildrenExtents(focusXref, rightSpouseXrefs, leftSpouseXref, leftSpouseX, firstSpouseX, SLOT, visibleSpouseFams) {
    const { NODE_W, NODE_W_FOCUS, H_GAP } = DESIGN;
    const focusCenterX = NODE_W_FOCUS / 2;
    if (typeof CHILDREN === 'undefined' || !CHILDREN) return null;
    const childXrefs = CHILDREN[focusXref] || [];
    if (childXrefs.length === 0) return null;

    let visibleFamXref = null;
    let visibleOtherX = null;
    if (typeof FAMILIES !== 'undefined' && FAMILIES) {
        for (const f of Object.keys(FAMILIES)) {
            const fam = FAMILIES[f];
            if (!fam) continue;
            if (fam.husb !== focusXref && fam.wife !== focusXref) continue;
            if (!(fam.chil || []).length) continue;
            const other = fam.husb === focusXref ? fam.wife : fam.husb;
            if (!other) continue;
            const idx = rightSpouseXrefs.indexOf(other);
            if (idx >= 0) {
                visibleFamXref = f;
                visibleOtherX = firstSpouseX + idx * SLOT;
                break;
            }
            if (other === leftSpouseXref) {
                visibleFamXref = f;
                visibleOtherX = leftSpouseX;
                break;
            }
        }
    }

    const sumWidth = (kids) => kids.reduce((w, cx, i) => {
        const sp = (typeof RELATIVES !== 'undefined' && RELATIVES[cx])
            ? _visibleSpousesFor(cx, RELATIVES[cx]?.spouses ?? [], visibleSpouseFams, focusXref)
            : [];
        const slotW = NODE_W + sp.length * (H_GAP + NODE_W);
        return w + slotW + (i > 0 ? H_GAP : 0);
    }, 0);

    let visibleKids = [], otherKids = [];
    if (visibleFamXref) {
        const visibleSet = new Set(FAMILIES[visibleFamXref].chil || []);
        for (const c of childXrefs) {
            (visibleSet.has(c) ? visibleKids : otherKids).push(c);
        }
    } else {
        otherKids = childXrefs.slice();
    }

    let leftEdge = null, rightEdge = null;
    if (visibleKids.length > 0 && visibleOtherX !== null) {
        const w = sumWidth(visibleKids);
        const midpoint = (focusCenterX + visibleOtherX + NODE_W / 2) / 2;
        const start = midpoint - w / 2;
        leftEdge = start;
        rightEdge = start + w;
    }
    if (otherKids.length > 0) {
        const w = sumWidth(otherKids);
        const start = focusCenterX - w / 2;
        const end = start + w;
        leftEdge = leftEdge === null ? start : Math.min(leftEdge, start);
        rightEdge = rightEdge === null ? end : Math.max(rightEdge, end);
    }
    if (leftEdge === null) return null;
    return { leftEdge, rightEdge };
}

// ---------------------------------------------------------------------------
// Descendant-aware sibling packing
// ---------------------------------------------------------------------------

// How far the xref's own subtree (the pill itself plus expanded children,
// grandchildren, etc.) extends horizontally from xref's CENTER on `side`
// ('left' | 'right'). Descendant placement mirrors _placeChildrenOfFam:
// children are centered under the xref at (NODE_W + H_GAP) slots, and each
// child can itself have an expanded FAM.
//
// Used by sibling-row packing so that two adjacent siblings who both expand
// their kids leave enough horizontal room for their cousin subtrees.

function _descendantHalfwidth(xref, side, expandedChildrenPersons, visited, visibleSpouseFams, focusXref) {
    const { NODE_W, H_GAP } = DESIGN;
    const CHILD_MARRIAGE_GAP = H_GAP;
    if (!expandedChildrenPersons || expandedChildrenPersons.size === 0) return NODE_W / 2;
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return NODE_W / 2;
    if (!expandedChildrenPersons.has(xref)) return NODE_W / 2;
    if (!visited) visited = new Set();
    if (visited.has(xref)) return NODE_W / 2;
    visited.add(xref);

    // Walk all of this person's FAMs with children.
    const allChil = [];
    for (const famXref of Object.keys(FAMILIES)) {
        const fam = FAMILIES[famXref];
        if (!fam) continue;
        if (fam.husb !== xref && fam.wife !== xref) continue;
        for (const c of (fam.chil || [])) allChil.push(c);
    }

    let extent = NODE_W / 2;
    if (allChil.length > 0) {
        const sorted = _sortByBirthYear(allChil);

        // Compute per-child slot widths (pill + visible spouses).
        // This matches _placeChildrenOfPerson's buildGroupsForFam width formula
        // so the parent-row spacing reflects the actual child cluster width.
        const childWidths = sorted.map(cx => {
            const spouses = (visibleSpouseFams !== undefined && focusXref !== undefined &&
                            typeof RELATIVES !== 'undefined' && RELATIVES[cx])
                ? _visibleSpousesFor(cx, RELATIVES[cx]?.spouses ?? [], visibleSpouseFams, focusXref)
                : [];
            return NODE_W + spouses.length * (CHILD_MARRIAGE_GAP + NODE_W);
        });

        const totalWidth = childWidths.reduce((sum, cw, i) => sum + cw + (i > 0 ? H_GAP : 0), 0);
        const groupStart = -totalWidth / 2; // relative to xref center

        // Per-child reach, accounting for variable slot widths and recursive grandchildren.
        let cursor = 0;
        sorted.forEach((cx, i) => {
            if (i > 0) cursor += H_GAP;
            const childPillCenter = groupStart + cursor + NODE_W / 2;
            const childHalf = _descendantHalfwidth(cx, side, expandedChildrenPersons, visited, visibleSpouseFams, focusXref);
            const reach = side === 'right' ? childPillCenter + childHalf : -childPillCenter + childHalf;
            if (reach > extent) extent = reach;
            // The full slot (including spouse pills) also contributes to extent.
            const slotExtent = side === 'right'
                ? groupStart + cursor + childWidths[i]
                : -(groupStart + cursor);
            if (slotExtent > extent) extent = slotExtent;
            cursor += childWidths[i];
        });

        // Centering correction: _placeChildrenOfPerson centers the cluster under the
        // marriage midpoint (between xref and their on-row spouse), not under xref itself.
        // When a spouse exists, this shifts the cluster left or right by roughly
        // (SIB_MARRIAGE_GAP + NODE_W) / 2. To guarantee enough room on both sides
        // regardless of which direction the spouse lies, conservatively add this offset
        // to the extent in both directions.
        const personSpouses = (visibleSpouseFams !== undefined && focusXref !== undefined &&
                              typeof RELATIVES !== 'undefined' && RELATIVES[xref])
            ? _visibleSpousesFor(xref, RELATIVES[xref]?.spouses ?? [], visibleSpouseFams, focusXref)
            : [];
        if (personSpouses.length > 0) {
            const spousalOffset = (SIB_MARRIAGE_GAP + NODE_W) / 2;
            if (totalWidth / 2 + spousalOffset > extent) extent = totalWidth / 2 + spousalOffset;
        }
    }
    visited.delete(xref);
    return extent;
}

// Pack `items` left-to-right on row `y`, computing inter-pair gaps from each
// neighbor's descendant subtree halfwidth so that cousin rows don't collide.
// The gap between two sibling centers is:
//   leftSib.rightHalf + rightSib.leftHalf + H_GAP
// where *Half is max(NODE_W/2, descendant-subtree extent on that side).
//
// `anchor` describes how to position the final row:
//   { type: 'leftEdgeCenter', value: cx }  — first node's CENTER at cx
//   { type: 'rightEdgeCenter', value: cx } — last node's CENTER at cx
//   { type: 'leftEdgeX', value: x }        — first node's LEFT EDGE at x

function _packRowWithDescendants(items, y, role, expandedChildrenPersons, anchor, visibleSpouseFams, focusXref) {
    const { NODE_W, H_GAP, ROW_HEIGHT } = DESIGN;
    const xs = [];
    items.forEach((it, i) => {
        if (i === 0) {
            xs.push(0);
        } else {
            const prevRight = _descendantHalfwidth(items[i - 1].xref, 'right', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref);
            const currLeft = _descendantHalfwidth(it.xref, 'left', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref);
            const prevCenter = xs[i - 1] + NODE_W / 2;
            const currCenter = prevCenter + prevRight + currLeft + H_GAP;
            xs.push(currCenter - NODE_W / 2);
        }
    });
    let shift = 0;
    if (anchor.type === 'firstLeftEdge') shift = anchor.value - xs[0];
    else if (anchor.type === 'lastLeftEdge') shift = anchor.value - xs[xs.length - 1];
    return items.map((it, i) => ({
        xref: it.xref,
        x: xs[i] + shift,
        y,
        generation: Math.round(y / ROW_HEIGHT),
        role,
    }));
}

// ---------------------------------------------------------------------------
// Exports (for tests and other modules)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Exports (node only)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
    module.exports = {
        _placeChildrenOfPerson,
        _focusChildrenExtents,
        _descendantHalfwidth,
        _packRowWithDescendants,
    };
    if (typeof global !== 'undefined') Object.assign(global, module.exports);
}
