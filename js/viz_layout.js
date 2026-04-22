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

/**
 * Sort an array of xrefs by birth_year ascending.
 * Unknown birth_year (missing or undefined) sorts last (treated as 9999).
 */
/**
 * Filter a person's spouse list down to those the user wants visible.
 * If any of the person's FAMs are in visibleSpouseFams, return spouses from
 * exactly those FAMs (deduplicated, in defaultSpouses order where possible).
 * Otherwise return a single-element list: the other parent of primaryFamFor.
 * People with 0 or 1 FAM get defaultSpouses unchanged.
 *
 * @param {string} personXref
 * @param {string[]} defaultSpouses — RELATIVES[personXref].spouses
 * @param {Set<string>} visibleSpouseFams
 * @param {string} focusXref
 * @returns {string[]}
 */
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
    const olderSibsAnchor = leftmostSpouseAreaX !== null ?
        leftmostSpouseAreaX - NODE_W / 2 - H_GAP - NODE_W / 2 :
        -FOCUS_TO_SIB;
    if (olderSibs.length > 0) {
        const olderSibNodes = _packRowWithDescendants(
            olderSibs.map(xref => ({ xref })),
            0,
            'sibling',
            expandedChildrenPersons,
            { type: 'lastLeftEdge', value: olderSibsAnchor },
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
    });

    if (leftSpouseXref) {
        nodes.push({
            xref: leftSpouseXref,
            x: leftSpouseX,
            y: 0,
            generation: 0,
            role: 'spouse',
        });
        edges.push({
            x1: leftSpouseX + NODE_W,
            y1: NODE_H / 2,
            x2: NODE_W_FOCUS / 2,
            y2: NODE_H / 2,
            type: 'marriage',
        });
    }

    // Younger siblings: packed after the rightmost spouse/spouse-sibling (or at FOCUS_TO_SIB if no spouses).
    const youngerSibStartX = rightmostSpouseAreaX !== null ?
        rightmostSpouseAreaX + NODE_W / 2 + H_GAP + NODE_W / 2 :
        FOCUS_TO_SIB;
    if (youngerSibs.length > 0) {
        const youngerSibNodes = _packRowWithDescendants(
            youngerSibs.map(xref => ({ xref })),
            0,
            'sibling',
            expandedChildrenPersons,
            { type: 'firstLeftEdge', value: youngerSibStartX },
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

    const focusParents = PARENTS[focusXref] ?? [];
    const fatherXref = focusParents[0] ?? null;
    const motherXref = focusParents[1] ?? null;

    if (fatherXref || motherXref) {
        const focusCenterX = NODE_W_FOCUS / 2;
        const ancUmbrellaY = -(ROW_HEIGHT - NODE_H) / 2; // halfway between parent row bottom and focus row top
        const parentBottomY = -ROW_HEIGHT + NODE_H;
        const parentMidY = -ROW_HEIGHT + NODE_H / 2;

        // Anchor drop and per-child drops span the focus and all gen-0 siblings:
        // they're the biological children of the parents sitting at y=0.
        // Focus uses NODE_W_FOCUS; siblings use NODE_W.
        const childCenters = [focusCenterX];
        nodes.forEach(n => {
            if (n.generation === 0 && n.role === 'sibling') {
                childCenters.push(n.x + NODE_W / 2);
            }
        });
        childCenters.sort((a, b) => a - b);

        // Parent couple re-centers over the sibling group (focus + siblings),
        // not over the focus alone. This keeps the drop from the marriage line
        // to the umbrella crossbar perfectly vertical — no L-shape.
        const focusGroupCenterX = (childCenters[0] + childCenters[childCenters.length - 1]) / 2;

        if (fatherXref && motherXref) {
            // Both parents: symmetric around groupCenter. Father left, mother right.
            // Separation is driven by each parent's subtree contour so that deep
            // ancestors on either side don't collide while keeping the marriage-line
            // midpoint above the sibling group.
            const sep = _requiredSeparation(fatherXref, motherXref, effectiveExpandedAncestors, expandedSiblingsXrefs);
            const fatherX = focusGroupCenterX - sep / 2 - NODE_W / 2;
            const motherX = focusGroupCenterX + sep / 2 - NODE_W / 2;

            nodes.push({ xref: fatherXref, x: fatherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
            nodes.push({ xref: motherXref, x: motherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });

            // Marriage edge between parents (father right edge → mother left edge).
            edges.push({
                x1: fatherX + NODE_W,
                y1: parentMidY,
                x2: motherX,
                y2: parentMidY,
                type: 'marriage',
            });

            // Place siblings BEFORE parents so _placeAncestors can emit an umbrella
            // spanning each ancestor + its siblings.
            _placeAncestorSiblings(fatherXref, fatherX, -ROW_HEIGHT, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
            _placeAncestorSiblings(motherXref, motherX, -ROW_HEIGHT, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);

            _placeAncestors(fatherXref, fatherX, -ROW_HEIGHT, -1, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
            _placeAncestors(motherXref, motherX, -ROW_HEIGHT, -1, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        } else {
            // Single parent: centered on the sibling group.
            const singleParent = fatherXref || motherXref;
            const singleParentX = focusGroupCenterX - NODE_W / 2;
            nodes.push({ xref: singleParent, x: singleParentX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
            _placeAncestorSiblings(singleParent, singleParentX, -ROW_HEIGHT, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
            _placeAncestors(singleParent, singleParentX, -ROW_HEIGHT, -1, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        }

        // Umbrella anchor drop (mirrors the descendant umbrella).
        // Since the parent couple sits directly above the sibling group center,
        // the anchor drop is a single straight vertical segment at groupCenterX.
        const anchorTopY = (fatherXref && motherXref) ? parentMidY : parentBottomY;
        edges.push({
            x1: focusGroupCenterX,
            y1: anchorTopY,
            x2: focusGroupCenterX,
            y2: ancUmbrellaY,
            type: 'ancestor',
        });

        // Crossbar spans leftmost→rightmost child center (only if >1 child of parents).
        if (childCenters.length > 1) {
            edges.push({
                x1: childCenters[0],
                y1: ancUmbrellaY,
                x2: childCenters[childCenters.length - 1],
                y2: ancUmbrellaY,
                type: 'ancestor',
            });
        }

        // Per-child drop from umbrella down to each child's top.
        childCenters.forEach(cx => {
            edges.push({
                x1: cx,
                y1: ancUmbrellaY,
                x2: cx,
                y2: 0,
                type: 'ancestor',
            });
        });
    }

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
        const buildGroup = (childXref) => {
            const childSpouses = _visibleSpousesFor(childXref, RELATIVES[childXref]?.spouses ?? [], visibleSpouseFams, focusXref);
            const width = NODE_W + childSpouses.length * (CHILD_MARRIAGE_GAP + NODE_W);
            return { childXref, childSpouses, width };
        };
        const visibleGroups = visibleKids.map(buildGroup);
        const otherGroups = otherKids.map(buildGroup);

        const sumWidth = (groups) => groups.reduce((w, g, i) => w + g.width + (i > 0 ? H_GAP : 0), 0);
        const visibleWidth = sumWidth(visibleGroups);
        const otherWidth = sumWidth(otherGroups);

        const marriageMidpointX = visibleOtherNode ?
            (focusCenterX + visibleOtherNode.x + NODE_W / 2) / 2 :
            focusCenterX;

        let visibleStart = marriageMidpointX - visibleWidth / 2;
        let otherStart = focusCenterX - otherWidth / 2;
        const INTER_GROUP_GAP = H_GAP * 4;
        if (otherGroups.length > 0 && visibleGroups.length > 0) {
            const otherEnd = otherStart + otherWidth;
            if (otherEnd + INTER_GROUP_GAP > visibleStart) {
                otherStart = visibleStart - INTER_GROUP_GAP - otherWidth;
            }
        }

        const umbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;

        const emitGroup = (groups, startX) => {
            const centers = [];
            let cursor = startX;
            groups.forEach((g, i) => {
                if (i > 0) cursor += H_GAP;
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

        const emitUmbrella = (centers, famAnchorX, anchorTopY) => {
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
            emitUmbrella(visibleCenters, marriageMidpointX, anchorTopY);
        }
        if (otherCenters.length > 0) {
            emitUmbrella(otherCenters, focusCenterX, NODE_H_FOCUS);
        }
    }

    // ── Phase 3: Expanded children of non-focus persons ─────────────────────
    // Skip focusXref — Phase 2 already placed the focus person's children.
    expandedChildrenPersons.forEach(personXref => {
        if (personXref === focusXref) return;
        _placeChildrenOfPerson(personXref, visibleSpouseFams, focusXref, nodes, edges);
    });

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
//
// Within the other-FAMs cluster, kids stay grouped by FAM (INTER_FAM_GAP
// between different FAMs, H_GAP within) so multi-marriage fatherhood is
// still visually distinguishable.

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
    const umbrellaY = personY + NODE_H + (ROW_HEIGHT - NODE_H) / 2;

    // Visible FAM = first childful FAM whose other-parent is on-row.
    let visibleFamXref = null;
    let visibleSpouseNode = null;
    for (const f of personFams) {
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
        const kidsSorted = fam.chil.slice().sort((a, b) => {
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
    const otherFamsSorted = personFams
        .filter(f => f !== visibleFamXref)
        .sort((a, b) => famEarliestBirth(a) - famEarliestBirth(b));
    const otherGroups = otherFamsSorted.flatMap(buildGroupsForFam);

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
    const visibleIdealStart = marriageMidpointX !== null
        ? marriageMidpointX - visibleWidth / 2
        : null;
    let otherIdealStart;
    if (visibleSpouseNode) {
        const spouseRight = visibleSpouseNode.x > personNode.x;
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

    const emitUmbrella = (anchorX, anchorTopY, centers) => {
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

    if (visibleGroups.length > 0) {
        const startX = pickStartInFreeGap(visibleIdealStart, visibleWidth);
        const centers = emitClusterNodes(visibleGroups, startX);
        emitUmbrella(marriageMidpointX, personY + NODE_H / 2, centers);
    }
    if (otherGroups.length > 0) {
        const startX = pickStartInFreeGap(otherIdealStart, otherWidth);
        const centers = emitClusterNodes(otherGroups, startX);
        emitUmbrella(personCenter, personY + NODE_H, centers);
    }
}

// ---------------------------------------------------------------------------
// Recursive ancestor placement
// ---------------------------------------------------------------------------

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
    const extraRight = (sx) => Math.max(0, _descendantHalfwidth(sx, 'right', expandedChildrenPersons) - NODE_W / 2);
    const extraLeft = (sx) => Math.max(0, _descendantHalfwidth(sx, 'left', expandedChildrenPersons) - NODE_W / 2);

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
                const halfLeft = _descendantHalfwidth(sibXref, 'left', expandedChildrenPersons);
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
            cursor = Math.max(cursor, sibX + NODE_W / 2 + _descendantHalfwidth(sibXref, 'right', expandedChildrenPersons));
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
                const halfRight = _descendantHalfwidth(sibXref, 'right', expandedChildrenPersons);
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
            rightEdge = Math.min(cursorLeft, sibX + NODE_W / 2 - _descendantHalfwidth(sibXref, 'left', expandedChildrenPersons));
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
function _descendantHalfwidth(xref, side, expandedChildrenPersons, visited) {
    const { NODE_W, H_GAP } = DESIGN;
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
        const totalWidth = sorted.length * NODE_W + (sorted.length - 1) * H_GAP;
        const groupStart = -totalWidth / 2; // relative to xref center
        sorted.forEach((cx, i) => {
            const childCenterOffset = groupStart + i * (NODE_W + H_GAP) + NODE_W / 2;
            const childHalf = _descendantHalfwidth(cx, side, expandedChildrenPersons, visited);
            const reach = side === 'right' ?
                childCenterOffset + childHalf :
                -childCenterOffset + childHalf;
            if (reach > extent) extent = reach;
        });
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
function _packRowWithDescendants(items, y, role, expandedChildrenPersons, anchor) {
    const { NODE_W, H_GAP, ROW_HEIGHT } = DESIGN;
    const xs = [];
    items.forEach((it, i) => {
        if (i === 0) {
            xs.push(0);
        } else {
            const prevRight = _descendantHalfwidth(items[i - 1].xref, 'right', expandedChildrenPersons);
            const currLeft = _descendantHalfwidth(it.xref, 'left', expandedChildrenPersons);
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

if (typeof module !== 'undefined') {
    module.exports = {
        computeLayout,
        _sortByBirthYear,
        _packRow,
        _rightContour,
        _leftContour,
        _requiredSeparation,
        _placeChildrenOfPerson,
    };
}