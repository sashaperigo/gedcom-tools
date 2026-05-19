// Layout engine for the hourglass-style family tree visualiser.
//
// Reads the following globals (set by the HTML template or injected in tests):
//   DESIGN     — from viz_design.js: NODE_W, NODE_H, ROW_HEIGHT, H_GAP, MARRIAGE_GAP
//   PEOPLE     — { [xref]: { name, sex, birth_year, death_year, ... } }
//   PARENTS    — { [xref]: [fatherXref|null, motherXref|null] }
//   CHILDREN   — { [xref]: [childXref, ...] }
//   RELATIVES  — { [xref]: { siblings: [...], spouses: [...] } }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------


function _visibleSpousesFor(personXref, defaultSpouses, visibleSpouseFams, focusXref) {
    if (!defaultSpouses || defaultSpouses.length <= 1) return defaultSpouses || [];
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return defaultSpouses;

    const personFams = Object.keys(FAMILIES).filter(f =>
        FAMILIES[f].husb === personXref || FAMILIES[f].wife === personXref
    );
    if (personFams.length <= 1) return defaultSpouses;

    const visibleSet = visibleSpouseFams || new Set();
    const enabled = personFams.filter(f => visibleSet.has(f));

    let chosenFams;
    if (enabled.length > 0) {
        chosenFams = enabled;
    } else if (typeof primaryFamFor === 'function') {
        const prim = primaryFamFor(personXref, focusXref);
        chosenFams = prim ? [prim] : personFams.slice(0, 1);
    } else {
        chosenFams = personFams.slice(0, 1);
    }

    const chosenOthers = new Set();
    for (const f of chosenFams) {
        const fam = FAMILIES[f];
        const other = fam.husb === personXref ? fam.wife : fam.husb;
        if (other) chosenOthers.add(other);
    }
    return defaultSpouses.filter(s => chosenOthers.has(s));
}


function _sortByBirthYear(xrefs) {
    return [...xrefs].sort((a, b) => {
        const ay = PEOPLE[a]?.birth_year ?? 9999;
        const by = PEOPLE[b]?.birth_year ?? 9999;
        return ay - by;
    });
}

/**
 * Pack an array of items into nodes starting at startX, all at the given y.
 * Items are laid out left-to-right with NODE_W + H_GAP spacing.
 * @param {Array<{xref: string}>} items
 * @param {number} startX
 * @param {number} y
 * @param {string} role
 * @returns {Node[]}
 */

function _packRow(items, startX, y, role) {
    const { NODE_W, H_GAP } = DESIGN;
    return items.map((item, i) => ({
        xref: item.xref,
        x: startX + i * (NODE_W + H_GAP),
        y,
        generation: Math.round(y / DESIGN.ROW_HEIGHT),
        role,
    }));
}

// ---------------------------------------------------------------------------
// computeLayout
// ---------------------------------------------------------------------------

/**
 * Compute the full layout for a given focus person.
 *
 * @param {string} focusXref - xref of the person at the center of the tree
 * @param {Set<string>} expandedAncestors - set of xrefs whose parents are shown
 * @param {Set<string>} expandedSiblingsXrefs - set of xrefs whose siblings are shown
 * @returns {{ nodes: Node[], edges: Edge[] }}
 *
 * Node: { xref, x, y, generation, role }
 *   role: 'focus' | 'ancestor' | 'descendant' | 'sibling' | 'spouse' | 'spouse_sibling'
 *       | 'ancestor_sibling' | 'ancestor_sibling_spouse'
 *
 * Edge: { x1, y1, x2, y2, type }
 *   type: 'ancestor' | 'descendant' | 'marriage'
 */

function computeLayout(focusXref, expandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, visibleSpouseFams) {
    expandedChildrenPersons = expandedChildrenPersons || new Set();
    visibleSpouseFams = visibleSpouseFams || new Set();
    const { NODE_W, NODE_W_FOCUS, NODE_H, NODE_H_FOCUS, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;
    const SLOT = NODE_W + H_GAP;

    // Force-expand: any ancestor whose siblings are shown also needs their
    // parents placed, so the sibling group can hang from a proper umbrella.
    const effectiveExpandedAncestors = new Set([
        ...(expandedAncestors || []),
        ...(expandedSiblingsXrefs || []),
    ]);
    // Gap between focus node edge and nearest sibling: account for focus being wider than NODE_W.
    const FOCUS_TO_SIB = NODE_W_FOCUS / 2 + H_GAP + NODE_W / 2;

    const nodes = [];
    const edges = [];

    // Focus-spouses recorded during gen-0 emission; processed in Phase 1.5
    // (after focus-parents) so their ancestor subtrees can be separated from
    // the focus-parents subtree via contour comparison.
    const focusSpouses = [];

    // ── Phase 1 & 2: Generation 0 (focus row) ────────────────────────────────

    const focusBY = PEOPLE[focusXref]?.birth_year ?? 9999;

    // Siblings split around focus by birth year.
    // Tie (same birth year as focus) falls into youngerSibs (placed right).
    const allSibs = RELATIVES[focusXref]?.siblings ?? [];
    const sortedSibs = _sortByBirthYear(allSibs);
    const olderSibs = sortedSibs.filter(x => (PEOPLE[x]?.birth_year ?? 9999) < focusBY);
    const youngerSibs = sortedSibs.filter(x => (PEOPLE[x]?.birth_year ?? 9999) >= focusBY);

    // Determine spouse placement up front so older siblings can be packed past the left spouse.
    const allSpouseXrefs = _visibleSpousesFor(focusXref, RELATIVES[focusXref]?.spouses ?? [], visibleSpouseFams, focusXref);
    const leftSpouseXref = allSpouseXrefs.length >= 2 ? allSpouseXrefs[1] : null;
    const rightSpouseXrefs = leftSpouseXref ?
        [allSpouseXrefs[0], ...allSpouseXrefs.slice(2)] :
        allSpouseXrefs;
    const firstSpouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
    const leftSpouseX = -firstSpouseX;
    let rightmostSpouseAreaX = null;
    const leftmostSpouseAreaX = leftSpouseXref ? leftSpouseX : null;

    // Older siblings: packed leftward. If there's a left spouse, siblings start left of it;
    // otherwise closest older sib center = -(FOCUS_TO_SIB).
    let olderSibsAnchor = leftmostSpouseAreaX !== null ?
        leftmostSpouseAreaX - NODE_W / 2 - H_GAP - NODE_W / 2 :
        -FOCUS_TO_SIB;
    // When the rightmost older sibling has expanded children, ensure its child
    // cluster's right edge clears focus's child cluster's left edge — otherwise
    // Phase 3's pickStartInFreeGap can't fit the cluster in the natural gap and
    // pushes it past focus's children. Mirror logic for younger siblings below.
    const INTER_FAM_GAP_FOR_SIB = H_GAP * 8;
    const focusKidsExtents = _focusChildrenExtents(focusXref, rightSpouseXrefs, leftSpouseXref, leftSpouseX, firstSpouseX, SLOT, visibleSpouseFams);
    if (olderSibs.length > 0) {
        const lastSibXref = olderSibs[olderSibs.length - 1];
        if (expandedChildrenPersons.has(lastSibXref) && focusKidsExtents) {
            const sibRightHalf = _descendantHalfwidth(lastSibXref, 'right', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref);
            // sib_center = anchor + NODE_W/2; conservative right cluster edge = sib_center + sibRightHalf
            // Need: cluster_right + INTER_FAM_GAP ≤ focusKidsExtents.leftEdge
            const maxAnchor = focusKidsExtents.leftEdge - INTER_FAM_GAP_FOR_SIB - sibRightHalf - NODE_W / 2;
            if (olderSibsAnchor > maxAnchor) olderSibsAnchor = maxAnchor;
        }
        const olderSibNodes = _packRowWithDescendants(
            olderSibs.map(xref => ({ xref })),
            0,
            'sibling',
            expandedChildrenPersons,
            { type: 'lastLeftEdge', value: olderSibsAnchor },
            visibleSpouseFams,
            focusXref,
        );
        // Insert spouses of older focus-row siblings. Process right→left so that
        // each sib's spouse goes to its LEFT and more-left sibs are shifted left.
        const olderSibSpouseNodes = [];
        let olderShift = 0;
        for (let i = olderSibNodes.length - 1; i >= 0; i--) {
            const sibNode = olderSibNodes[i];
            sibNode.x -= olderShift;
            const spouses = _visibleSpousesFor(
                sibNode.xref,
                RELATIVES[sibNode.xref]?.spouses ?? [],
                visibleSpouseFams,
                focusXref,
            );
            spouses.forEach((spXref, si) => {
                const refX = si === 0 ? sibNode.x : sibNode.x - si * (NODE_W + SIB_MARRIAGE_GAP);
                const spX = refX - SIB_MARRIAGE_GAP - NODE_W;
                olderSibSpouseNodes.push({ xref: spXref, x: spX, y: 0, generation: 0, role: 'spouse' });
                edges.push({
                    x1: spX + NODE_W,
                    y1: NODE_H / 2,
                    x2: refX,
                    y2: NODE_H / 2,
                    type: 'marriage',
                });
                olderShift += NODE_W + SIB_MARRIAGE_GAP;
            });
        }
        nodes.push(...olderSibNodes, ...olderSibSpouseNodes);
    }

    // Focus node at x=0
    nodes.push({ xref: focusXref, x: 0, y: 0, generation: 0, role: 'focus' });

    rightSpouseXrefs.forEach((spouseXref, si) => {
        const thisSpouseX = firstSpouseX + si * SLOT;
        rightmostSpouseAreaX = thisSpouseX;
        nodes.push({
            xref: spouseXref,
            x: thisSpouseX,
            y: 0,
            generation: 0,
            role: 'spouse',
            isFocusSpouse: true,
        });

        const edgeX1 = si === 0 ?
            NODE_W_FOCUS / 2 :
            firstSpouseX + (si - 1) * SLOT + NODE_W / 2;
        edges.push({
            x1: edgeX1,
            y1: NODE_H / 2,
            x2: thisSpouseX,
            y2: NODE_H / 2,
            type: 'marriage',
        });

        // Co-spouses: the first right spouse may have their own additional marriage
        // partners visible via the multi-spouse toggle (e.g., focus is Josephina,
        // Michele is her spouse, and the user has also selected Maria Elena via
        // Michele's toggle). Place those co-spouses to the right of Michele.
        let coSpouseEndX = thisSpouseX;
        if (si === 0) {
            const coSpouses = _visibleSpousesFor(
                spouseXref,
                RELATIVES[spouseXref]?.spouses ?? [],
                visibleSpouseFams,
                focusXref,
            ).filter(s => s !== focusXref);
            coSpouses.forEach((coXref, ci) => {
                const coX = thisSpouseX + (ci + 1) * SLOT;
                nodes.push({ xref: coXref, x: coX, y: 0, generation: 0, role: 'spouse' });
                edges.push({
                    x1: thisSpouseX + ci * SLOT + NODE_W,
                    y1: NODE_H / 2,
                    x2: coX,
                    y2: NODE_H / 2,
                    type: 'marriage',
                });
                coSpouseEndX = coX;
                rightmostSpouseAreaX = coX;
            });
        }

        // Spouse's siblings (if expanded and this is the first right-side spouse)
        if (si === 0 && expandedSiblingsXrefs.has(spouseXref)) {
            const spouseSibs = _sortByBirthYear(RELATIVES[spouseXref]?.siblings ?? []);
            if (spouseSibs.length > 0) {
                const spouseSibNodes = _packRow(
                    spouseSibs.map(xref => ({ xref })),
                    coSpouseEndX + SLOT,
                    0,
                    'spouse_sibling',
                );
                nodes.push(...spouseSibNodes);
                rightmostSpouseAreaX = spouseSibNodes[spouseSibNodes.length - 1].x;
            }
        }

        // Spouse's ancestors are placed in Phase 1.5 (after focus-parents)
        // so contour-based separation can space them away from the
        // focus-parents subtree.
        focusSpouses.push({ xref: spouseXref, originalX: thisSpouseX, side: 'right' });
    });

    if (leftSpouseXref) {
        nodes.push({
            xref: leftSpouseXref,
            x: leftSpouseX,
            y: 0,
            generation: 0,
            role: 'spouse',
            isFocusSpouse: true,
        });
        edges.push({
            x1: leftSpouseX + NODE_W,
            y1: NODE_H / 2,
            x2: NODE_W_FOCUS / 2,
            y2: NODE_H / 2,
            type: 'marriage',
        });
        focusSpouses.push({ xref: leftSpouseXref, originalX: leftSpouseX, side: 'left' });
    }

    // Younger siblings: packed after the rightmost spouse/spouse-sibling (or at FOCUS_TO_SIB if no spouses).
    let youngerSibStartX = rightmostSpouseAreaX !== null ?
        rightmostSpouseAreaX + NODE_W / 2 + H_GAP + NODE_W / 2 :
        FOCUS_TO_SIB;
    if (youngerSibs.length > 0) {
        const firstYoungSibXref = youngerSibs[0];
        if (expandedChildrenPersons.has(firstYoungSibXref) && focusKidsExtents) {
            const sibLeftHalf = _descendantHalfwidth(firstYoungSibXref, 'left', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref);
            // sib_center = startX + NODE_W/2; conservative left cluster edge = sib_center - sibLeftHalf
            // Need: focusKidsExtents.rightEdge + INTER_FAM_GAP ≤ cluster_left
            const minStartX = focusKidsExtents.rightEdge + INTER_FAM_GAP_FOR_SIB + sibLeftHalf - NODE_W / 2;
            if (youngerSibStartX < minStartX) youngerSibStartX = minStartX;
        }
        const youngerSibNodes = _packRowWithDescendants(
            youngerSibs.map(xref => ({ xref })),
            0,
            'sibling',
            expandedChildrenPersons,
            { type: 'firstLeftEdge', value: youngerSibStartX },
            visibleSpouseFams,
            focusXref,
        );
        // Insert spouses of younger focus-row siblings. Process left→right so that
        // each sib's spouse goes to its RIGHT and more-right sibs are shifted right.
        const youngerSibSpouseNodes = [];
        let youngerShift = 0;
        for (const sibNode of youngerSibNodes) {
            sibNode.x += youngerShift;
            const spouses = _visibleSpousesFor(
                sibNode.xref,
                RELATIVES[sibNode.xref]?.spouses ?? [],
                visibleSpouseFams,
                focusXref,
            );
            spouses.forEach((spXref, si) => {
                const prevX = si === 0 ? sibNode.x : sibNode.x + si * (NODE_W + SIB_MARRIAGE_GAP);
                const spX = prevX + NODE_W + SIB_MARRIAGE_GAP;
                youngerSibSpouseNodes.push({ xref: spXref, x: spX, y: 0, generation: 0, role: 'spouse' });
                edges.push({
                    x1: prevX + NODE_W,
                    y1: NODE_H / 2,
                    x2: spX,
                    y2: NODE_H / 2,
                    type: 'marriage',
                });
                youngerShift += NODE_W + SIB_MARRIAGE_GAP;
            });
        }
        nodes.push(...youngerSibNodes, ...youngerSibSpouseNodes);
    }

    // ── Phase 2: Generation -1 (parents) with umbrella over focus + siblings ─
    const { fatherXref, motherXref, fatherX, motherX } = _placeFocusParents(
        focusXref, effectiveExpandedAncestors, expandedSiblingsXrefs,
        expandedChildrenPersons, nodes, edges, visibleSpouseFams,
    );

    // ── Phase 1.5: focus-spouse ancestors with collision avoidance ──────────
    _placeFocusSpouseAncestors(focusSpouses, fatherXref, motherXref, fatherX, motherX, expandedAncestors, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);

    // ── Phase 2: Generation +1 (children + umbrella) ─────────────────────────
    //
    // Focus children are split by FAM:
    //   (1) "visible-FAM" — children of the first FAM whose co-parent is on
    //       the focus row. Hang from that marriage-line midpoint.
    //   (2) "other" — children from every remaining FAM combined. Hang from
    //       a single umbrella anchored under focus alone.
    // This prevents half-siblings from unrelated marriages from being drawn
    // as a single crossbar group.

    const childXrefs = CHILDREN[focusXref] ?? [];
    if (childXrefs.length > 0) {
        const focusCenterX = NODE_W_FOCUS / 2;

        let visibleFamXref = null;
        let visibleOtherNode = null;
        if (typeof FAMILIES !== 'undefined' && FAMILIES) {
            for (const f of Object.keys(FAMILIES)) {
                const fam = FAMILIES[f];
                if (!fam) continue;
                if (fam.husb !== focusXref && fam.wife !== focusXref) continue;
                if (!(fam.chil || []).length) continue;
                const other = fam.husb === focusXref ? fam.wife : fam.husb;
                if (!other) continue;
                const otherNode = nodes.find(n => n.xref === other && n.y === 0);
                if (otherNode) {
                    visibleFamXref = f;
                    visibleOtherNode = otherNode;
                    break;
                }
            }
        }

        const sortByBirth = (a, b) => {
            const ya = PEOPLE[a]?.birth_year ?? 9999;
            const yb = PEOPLE[b]?.birth_year ?? 9999;
            return ya - yb;
        };

        let visibleKids = [];
        let otherKids = [];
        if (visibleFamXref) {
            const visibleChilSet = new Set(FAMILIES[visibleFamXref].chil || []);
            for (const c of childXrefs) {
                if (visibleChilSet.has(c)) visibleKids.push(c);
                else otherKids.push(c);
            }
            visibleKids.sort(sortByBirth);
            otherKids.sort(sortByBirth);
        } else if (rightSpouseXrefs.length > 0) {
            // FAMILIES global missing/incomplete (e.g. unit tests) but focus has
            // an on-row spouse — preserve legacy single-umbrella behavior under
            // the marriage midpoint.
            visibleKids = childXrefs.slice();
            const firstSpouseXref = rightSpouseXrefs[0];
            visibleOtherNode = nodes.find(n => n.xref === firstSpouseXref && n.y === 0) || null;
        } else {
            // No on-row co-parent: all children hang from focus alone.
            otherKids = childXrefs.slice();
        }

        const CHILD_MARRIAGE_GAP = H_GAP;
        const PHASE2_INTER_FAM_GAP = H_GAP * 8;
        const buildGroup = (childXref) => {
            const childSpouses = _visibleSpousesFor(childXref, RELATIVES[childXref]?.spouses ?? [], visibleSpouseFams, focusXref);
            const width = NODE_W + childSpouses.length * (CHILD_MARRIAGE_GAP + NODE_W);
            // Halfwidths of this gen-1 child's own (Phase-3) descendant cluster,
            // measured from the child's marriage midpoint (= group center).
            // NODE_W/2 when the child has no expanded descendants.
            // Phase 2 emitGroup always places child spouses to the right within
            // the child's group, so the child's visible-FAM cluster (if any)
            // will be centered on a midpoint to the child's right.
            const halfLeft = _descendantHalfwidth(childXref, 'left', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref, 'right');
            const halfRight = _descendantHalfwidth(childXref, 'right', expandedChildrenPersons, undefined, visibleSpouseFams, focusXref, 'right');
            return { childXref, childSpouses, width, halfLeft, halfRight };
        };
        const visibleGroups = visibleKids.map(buildGroup);
        const otherGroups = otherKids.map(buildGroup);

        // Per-pair advance from prev group's cursor to next group's cursor.
        // Baseline is prev.width + H_GAP. When either group has an expanded
        // grandchild cluster, ensure the gen-1 spacing leaves enough room so
        // the gen-2 clusters don't overlap (and Phase 3 doesn't need to push
        // children outside their natural position).
        const advanceFor = (prev, next) => {
            const baseline = prev.width + H_GAP;
            const prevHasDesc = prev.halfRight > NODE_W / 2 + 0.001;
            const nextHasDesc = next.halfLeft > NODE_W / 2 + 0.001;
            // Reservation only matters when BOTH siblings' grandkid clusters
            // could collide at the gen-2 row. If only one side has grandkids,
            // the other side is a bare pill on the gen-1 row — different y from
            // the grandkid cluster, so no extra x-clearance is needed. Without
            // this guard, an over-conservative halfwidth on the descendant side
            // pushes a bare-pill sibling hundreds of px away unnecessarily.
            if (!prevHasDesc || !nextHasDesc) return baseline;
            // Marriage midpoint of group sits at cursor + width/2. Cluster
            // reaches right to (mid + halfRight) and next reaches left to
            // (next_mid - halfLeft). Required advance derives from
            //   nextCursor - prevCursor ≥ prev.width/2 + halfRight + halfLeft
            //                              - next.width/2 + INTER_FAM_GAP.
            const required =
                prev.width / 2 + prev.halfRight + next.halfLeft -
                next.width / 2 + PHASE2_INTER_FAM_GAP;
            return Math.max(baseline, required);
        };

        const sumWidth = (groups) => groups.reduce((w, g, i) => {
            if (i === 0) return w + g.width;
            // Match emitGroup's per-pair advance so visibleStart/otherStart
            // center the cluster correctly when grandchildren widen it.
            return w + (advanceFor(groups[i - 1], g) - groups[i - 1].width) + g.width;
        }, 0);
        const visibleWidth = sumWidth(visibleGroups);
        const otherWidth = sumWidth(otherGroups);

        const marriageMidpointX = visibleOtherNode ?
            (focusCenterX + visibleOtherNode.x + NODE_W / 2) / 2 :
            focusCenterX;

        let visibleStart = marriageMidpointX - visibleWidth / 2;
        let otherStart = focusCenterX - otherWidth / 2;
        const INTER_CLUSTER_GAP = H_GAP * 8;
        if (otherGroups.length > 0 && visibleGroups.length > 0) {
            // Push other LEFT if it would encroach on visible
            const otherEnd = otherStart + otherWidth;
            if (otherEnd + INTER_CLUSTER_GAP > visibleStart) {
                otherStart = visibleStart - INTER_CLUSTER_GAP - otherWidth;
            }
            // Push visible RIGHT if other is too close from the left
            const newOtherEnd = otherStart + otherWidth;
            if (visibleStart < newOtherEnd + INTER_CLUSTER_GAP) {
                visibleStart = newOtherEnd + INTER_CLUSTER_GAP;
            }
        }

        const visibleUmbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;
        // When the focus owns BOTH cluster types, the other-FAM umbrella shifts
        // DOWN by H_GAP so its horizontal connector cannot share a y-line with
        // the visible-FAM crossbar. See docs/learnings/umbrella-connector-overlap.md.
        const otherUmbrellaY = (visibleGroups.length > 0 && otherGroups.length > 0)
            ? visibleUmbrellaY + H_GAP
            : visibleUmbrellaY;

        const emitGroup = (groups, startX) => {
            const centers = [];
            let cursor = startX;
            groups.forEach((g, i) => {
                if (i > 0) {
                    const prev = groups[i - 1];
                    cursor += advanceFor(prev, g) - prev.width;
                }
                const childX = cursor;
                nodes.push({ xref: g.childXref, x: childX, y: ROW_HEIGHT, generation: 1, role: 'descendant' });
                centers.push(childX + NODE_W / 2);

                g.childSpouses.forEach((sxref, si) => {
                    const spouseX = childX + (si + 1) * (NODE_W + CHILD_MARRIAGE_GAP);
                    nodes.push({ xref: sxref, x: spouseX, y: ROW_HEIGHT, generation: 1, role: 'descendant_spouse' });
                    const prevX = si === 0 ? childX : childX + si * (NODE_W + CHILD_MARRIAGE_GAP);
                    edges.push({
                        x1: prevX + NODE_W,
                        y1: ROW_HEIGHT + NODE_H / 2,
                        x2: spouseX,
                        y2: ROW_HEIGHT + NODE_H / 2,
                        type: 'marriage',
                    });
                });
                cursor += g.width;
            });
            return centers;
        };

        const emitUmbrella = (centers, famAnchorX, anchorTopY, umbrellaY) => {
            if (centers.length === 0) return;
            const leftCenter = Math.min(...centers);
            const rightCenter = Math.max(...centers);
            const umbrellaAnchorX = Math.min(Math.max(famAnchorX, leftCenter), rightCenter);

            edges.push({ x1: famAnchorX, y1: anchorTopY, x2: famAnchorX, y2: umbrellaY, type: 'descendant' });
            if (umbrellaAnchorX !== famAnchorX) {
                edges.push({ x1: famAnchorX, y1: umbrellaY, x2: umbrellaAnchorX, y2: umbrellaY, type: 'descendant' });
            }
            if (centers.length > 1) {
                edges.push({ x1: leftCenter, y1: umbrellaY, x2: rightCenter, y2: umbrellaY, type: 'descendant' });
            }
            centers.forEach(cx => {
                edges.push({ x1: cx, y1: umbrellaY, x2: cx, y2: ROW_HEIGHT, type: 'descendant' });
            });
        };

        const visibleCenters = emitGroup(visibleGroups, visibleStart);
        const otherCenters = emitGroup(otherGroups, otherStart);

        if (visibleCenters.length > 0) {
            const anchorTopY = rightSpouseXrefs.length > 0 ? NODE_H / 2 : NODE_H_FOCUS;
            emitUmbrella(visibleCenters, marriageMidpointX, anchorTopY, visibleUmbrellaY);
        }
        if (otherCenters.length > 0) {
            emitUmbrella(otherCenters, focusCenterX, NODE_H_FOCUS, otherUmbrellaY);
        }
    }

    // ── Phase 3: Expanded children of non-focus persons ─────────────────────
    _placeNonFocusExpandedChildren(focusXref, expandedChildrenPersons, visibleSpouseFams, nodes, edges);

    return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Non-focus person children placement
// ---------------------------------------------------------------------------
// Clicking the person's chevron reveals every child across every FAM, split
// into two disjoint clusters so the umbrellas can't share horizontal segments
// at the common umbrellaY:
//
//   (1) Visible-FAM cluster — children of the one FAM whose other-parent is
//       on-row. Centered on the marriage-line midpoint; the umbrella drops
//       from that midpoint.
//   (2) Other-FAMs cluster — every child from every non-visible FAM merged
//       into one cluster under a single umbrella that drops from the
//       person's own pill. Placed on the OPPOSITE side of the person from
//       the visible spouse, keeping its horizontal reach strictly on one
//       side of personCenter and therefore away from the visible-FAM drop.
//       Children within this cluster are sorted by birth year with H_GAP
//       between all of them regardless of which FAM they came from.

// ---------------------------------------------------------------------------
// Exports (node only; browser loads each split file via <script> tag)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
    // Load siblings first so their globals/exports exist before
    // any consumer in this module calls into them.
    const _contour = require('./viz_layout_contour.js');
    const _ancestors = require('./viz_layout_ancestors.js');
    const _descendants = require('./viz_layout_descendants.js');
    const _own = {
        _visibleSpousesFor,
        _sortByBirthYear,
        _packRow,
        computeLayout,
    };
    if (typeof global !== 'undefined') Object.assign(global, _own);
    module.exports = { ..._contour, ..._ancestors, ..._descendants, ..._own };
}
