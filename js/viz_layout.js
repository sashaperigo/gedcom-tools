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
    xref:       item.xref,
    x:          startX + i * (NODE_W + H_GAP),
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
function computeLayout(focusXref, expandedAncestors, expandedSiblingsXrefs) {
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
  const allSibs    = RELATIVES[focusXref]?.siblings ?? [];
  const sortedSibs = _sortByBirthYear(allSibs);
  const olderSibs  = sortedSibs.filter(x => (PEOPLE[x]?.birth_year ?? 9999) < focusBY);
  const youngerSibs = sortedSibs.filter(x => (PEOPLE[x]?.birth_year ?? 9999) >= focusBY);

  // Older siblings: packed leftward. Closest older sib center = -(FOCUS_TO_SIB).
  if (olderSibs.length > 0) {
    nodes.push(..._packRow(
      olderSibs.map(xref => ({ xref })),
      -(FOCUS_TO_SIB + (olderSibs.length - 1) * SLOT),
      0,
      'sibling',
    ));
  }

  // Focus node at x=0
  nodes.push({ xref: focusXref, x: 0, y: 0, generation: 0, role: 'focus' });

  // Spouses: placed immediately after focus (before younger siblings).
  // firstSpouseX = NODE_W_FOCUS/2 + MARRIAGE_GAP + NODE_W/2 (= 80 + 60 + 70 = 210)
  const spouseXrefs  = RELATIVES[focusXref]?.spouses ?? [];
  const firstSpouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
  // Track the rightmost center x placed (spouse or spouse sibling) to position younger sibs after.
  let rightmostSpouseAreaX = null;

  spouseXrefs.forEach((spouseXref, si) => {
    const thisSpouseX = firstSpouseX + si * SLOT;
    rightmostSpouseAreaX = thisSpouseX;
    nodes.push({
      xref:       spouseXref,
      x:          thisSpouseX,
      y:          0,
      generation: 0,
      role:       'spouse',
    });

    // Marriage edge: focus right edge → first spouse; prev spouse right → next spouse.
    const edgeX1 = si === 0
      ? NODE_W_FOCUS / 2
      : firstSpouseX + (si - 1) * SLOT + NODE_W / 2;
    edges.push({
      x1:   edgeX1,
      y1:   NODE_H / 2,
      x2:   thisSpouseX,
      y2:   NODE_H / 2,
      type: 'marriage',
    });

    // Spouse's siblings (if expanded and this is the primary spouse)
    if (si === 0 && expandedSiblingsXrefs.has(spouseXref)) {
      const spouseSibs = _sortByBirthYear(RELATIVES[spouseXref]?.siblings ?? []);
      if (spouseSibs.length > 0) {
        const spouseSibNodes = _packRow(
          spouseSibs.map(xref => ({ xref })),
          thisSpouseX + SLOT,
          0,
          'spouse_sibling',
        );
        nodes.push(...spouseSibNodes);
        rightmostSpouseAreaX = spouseSibNodes[spouseSibNodes.length - 1].x;
      }
    }
  });

  // Younger siblings: packed after the rightmost spouse/spouse-sibling (or at FOCUS_TO_SIB if no spouses).
  const youngerSibStartX = rightmostSpouseAreaX !== null
    ? rightmostSpouseAreaX + NODE_W / 2 + H_GAP + NODE_W / 2
    : FOCUS_TO_SIB;
  if (youngerSibs.length > 0) {
    nodes.push(..._packRow(
      youngerSibs.map(xref => ({ xref })),
      youngerSibStartX,
      0,
      'sibling',
    ));
  }

  // ── Phase 2: Generation -1 (parents) with umbrella over focus + siblings ─

  const focusParents = PARENTS[focusXref] ?? [];
  const fatherXref   = focusParents[0] ?? null;
  const motherXref   = focusParents[1] ?? null;

  if (fatherXref || motherXref) {
    const focusCenterX = NODE_W_FOCUS / 2;
    const ancUmbrellaY = -(ROW_HEIGHT - NODE_H) / 2;   // halfway between parent row bottom and focus row top
    const parentBottomY = -ROW_HEIGHT + NODE_H;
    const parentMidY    = -ROW_HEIGHT + NODE_H / 2;

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

    if (fatherXref && motherXref) {
      // Both parents: symmetric around focus center. Father left, mother right.
      // Separation is driven by each parent's subtree contour so that deep
      // ancestors on either side don't collide while keeping the marriage-line
      // midpoint above the child.
      const sep = _requiredSeparation(fatherXref, motherXref, effectiveExpandedAncestors, expandedSiblingsXrefs);
      const fatherX = focusCenterX - sep / 2 - NODE_W / 2;
      const motherX = focusCenterX + sep / 2 - NODE_W / 2;

      nodes.push({ xref: fatherXref, x: fatherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
      nodes.push({ xref: motherXref, x: motherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });

      // Marriage edge between parents (father right edge → mother left edge).
      edges.push({
        x1: fatherX + NODE_W, y1: parentMidY,
        x2: motherX,           y2: parentMidY,
        type: 'marriage',
      });

      // Place siblings BEFORE parents so _placeAncestors can emit an umbrella
      // spanning each ancestor + its siblings.
      _placeAncestorSiblings(fatherXref, fatherX, -ROW_HEIGHT, expandedSiblingsXrefs, effectiveExpandedAncestors, nodes, edges);
      _placeAncestorSiblings(motherXref, motherX, -ROW_HEIGHT, expandedSiblingsXrefs, effectiveExpandedAncestors, nodes, edges);

      _placeAncestors(fatherXref, fatherX, -ROW_HEIGHT, -1, effectiveExpandedAncestors, expandedSiblingsXrefs, nodes, edges);
      _placeAncestors(motherXref, motherX, -ROW_HEIGHT, -1, effectiveExpandedAncestors, expandedSiblingsXrefs, nodes, edges);
    } else {
      // Single parent: centered on focus center.
      const singleParent = fatherXref || motherXref;
      const singleParentX = focusCenterX - NODE_W / 2;
      nodes.push({ xref: singleParent, x: singleParentX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
      _placeAncestorSiblings(singleParent, singleParentX, -ROW_HEIGHT, expandedSiblingsXrefs, effectiveExpandedAncestors, nodes, edges);
      _placeAncestors(singleParent, singleParentX, -ROW_HEIGHT, -1, effectiveExpandedAncestors, expandedSiblingsXrefs, nodes, edges);
    }

    // Umbrella geometry (mirrors the descendant umbrella).
    // Anchor drop: starts at the marriage line (y = parent row center) when both
    // parents are present so it meets the marriage edge perpendicularly with no gap.
    // With a single parent, start at the bottom of the parent node.
    const anchorTopY = (fatherXref && motherXref) ? parentMidY : parentBottomY;
    const focusGroupCenterX = (childCenters[0] + childCenters[childCenters.length - 1]) / 2;
    if (Math.abs(focusGroupCenterX - focusCenterX) < 0.5) {
      edges.push({
        x1: focusCenterX, y1: anchorTopY,
        x2: focusCenterX, y2: ancUmbrellaY,
        type: 'ancestor',
      });
    } else {
      // L-shape: parent marriage midpoint sits above focus, but the umbrella
      // crossbar is centered on the focus-sibling group (asymmetric split).
      const elbowY = (anchorTopY + ancUmbrellaY) / 2;
      edges.push({
        x1: focusCenterX, y1: anchorTopY,
        x2: focusCenterX, y2: elbowY,
        type: 'ancestor',
      });
      edges.push({
        x1: focusCenterX,     y1: elbowY,
        x2: focusGroupCenterX, y2: elbowY,
        type: 'ancestor',
      });
      edges.push({
        x1: focusGroupCenterX, y1: elbowY,
        x2: focusGroupCenterX, y2: ancUmbrellaY,
        type: 'ancestor',
      });
    }

    // Crossbar spans leftmost→rightmost child center (only if >1 child of parents).
    if (childCenters.length > 1) {
      edges.push({
        x1: childCenters[0],                      y1: ancUmbrellaY,
        x2: childCenters[childCenters.length - 1], y2: ancUmbrellaY,
        type: 'ancestor',
      });
    }

    // Per-child drop from umbrella down to each child's top.
    childCenters.forEach(cx => {
      edges.push({
        x1: cx, y1: ancUmbrellaY,
        x2: cx, y2: 0,
        type: 'ancestor',
      });
    });
  }

  // ── Phase 2: Generation +1 (children + umbrella) ─────────────────────────

  const childXrefs = CHILDREN[focusXref] ?? [];
  if (childXrefs.length > 0) {
    // Anchor: midpoint between focus center and first spouse center if present,
    // else focus center. This is where the umbrella hangs from.
    const focusCenterX = NODE_W_FOCUS / 2;
    const anchorX = spouseXrefs.length > 0
      ? (focusCenterX + (firstSpouseX + NODE_W / 2)) / 2
      : focusCenterX;

    // Build child groups [child, ...childSpouses] and pack them left→right.
    // Descendant-row couples use H_GAP between partners — a short marriage line;
    // MARRIAGE_GAP is reserved for the focus couple (where children hang below).
    const CHILD_MARRIAGE_GAP = H_GAP;
    const groups = childXrefs.map(childXref => {
      const childSpouses = RELATIVES[childXref]?.spouses ?? [];
      const width = NODE_W + childSpouses.length * (CHILD_MARRIAGE_GAP + NODE_W);
      return { childXref, childSpouses, width };
    });

    const placements = [];
    let cursor = 0;
    groups.forEach(g => {
      placements.push({ ...g, start: cursor });
      cursor += g.width + H_GAP;
    });

    // Shift so the midpoint of first and last *child* centers aligns with anchorX.
    const firstChildCenter = placements[0].start + NODE_W / 2;
    const lastChildCenter  = placements[placements.length - 1].start + NODE_W / 2;
    const shift = anchorX - (firstChildCenter + lastChildCenter) / 2;

    const childCenters = [];
    placements.forEach(p => {
      const childX = p.start + shift;
      nodes.push({ xref: p.childXref, x: childX, y: ROW_HEIGHT, generation: 1, role: 'descendant' });
      childCenters.push(childX + NODE_W / 2);

      p.childSpouses.forEach((sxref, si) => {
        const spouseX = childX + (si + 1) * (NODE_W + CHILD_MARRIAGE_GAP);
        nodes.push({ xref: sxref, x: spouseX, y: ROW_HEIGHT, generation: 1, role: 'descendant_spouse' });

        // Marriage edge between consecutive members of the group (right edge → left edge)
        const prevX = si === 0 ? childX : childX + si * (NODE_W + CHILD_MARRIAGE_GAP);
        edges.push({
          x1:   prevX + NODE_W,
          y1:   ROW_HEIGHT + NODE_H / 2,
          x2:   spouseX,
          y2:   ROW_HEIGHT + NODE_H / 2,
          type: 'marriage',
        });
      });
    });

    // Umbrella geometry
    const umbrellaY = NODE_H + (ROW_HEIGHT - NODE_H) / 2;

    // Drop from anchor down to umbrella bar. When focus has a spouse, start at the
    // marriage-line center (NODE_H/2) so it meets the marriage edge perpendicularly
    // with no gap. No spouse → start at NODE_H_FOCUS (the bottom of the focus node).
    const anchorTopY = spouseXrefs.length > 0 ? NODE_H / 2 : NODE_H_FOCUS;
    edges.push({
      x1:   anchorX,
      y1:   anchorTopY,
      x2:   anchorX,
      y2:   umbrellaY,
      type: 'descendant',
    });

    // Horizontal crossbar from leftmost to rightmost child center (only if >1 child)
    if (childCenters.length > 1) {
      const leftX  = Math.min(...childCenters);
      const rightX = Math.max(...childCenters);
      edges.push({
        x1:   leftX,
        y1:   umbrellaY,
        x2:   rightX,
        y2:   umbrellaY,
        type: 'descendant',
      });
    }

    // Vertical drop from umbrella to each child
    childCenters.forEach(cx => {
      edges.push({
        x1:   cx,
        y1:   umbrellaY,
        x2:   cx,
        y2:   ROW_HEIGHT,
        type: 'descendant',
      });
    });
  }

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Recursive ancestor placement
// ---------------------------------------------------------------------------

function _placeAncestors(xref, x, y, generation, expandedAncestors, expandedSiblingsXrefs, nodes, edges) {
  const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP } = DESIGN;
  const SLOT = NODE_W + H_GAP;

  if (!expandedAncestors.has(xref)) return;

  const parentPair = PARENTS[xref] ?? [];
  const fatherXref = parentPair[0] ?? null;
  const motherXref = parentPair[1] ?? null;

  if (!fatherXref && !motherXref) return;

  const nextGen = generation - 1;
  const nextY   = nextGen * ROW_HEIGHT;

  if (fatherXref && motherXref) {
    // Contour-based separation keeps the marriage midpoint above the child
    // regardless of which side's subtree extends deeper.
    const childCenter = x + NODE_W / 2;
    const sep = _requiredSeparation(fatherXref, motherXref, expandedAncestors, expandedSiblingsXrefs);
    const fatherX = childCenter - sep / 2 - NODE_W / 2;
    const motherX = childCenter + sep / 2 - NODE_W / 2;

    nodes.push({ xref: fatherXref, x: fatherX, y: nextY, generation: nextGen, role: 'ancestor' });
    nodes.push({ xref: motherXref, x: motherX, y: nextY, generation: nextGen, role: 'ancestor' });

    // Marriage edge between the parents.
    const parentMidY = nextY + NODE_H / 2;
    edges.push({
      x1: fatherX + NODE_W, y1: parentMidY,
      x2: motherX,           y2: parentMidY,
      type: 'marriage',
    });

    // Umbrella down to the child row. If the child (xref) has expanded
    // siblings, the umbrella spans all biological children of this couple;
    // otherwise it's a single vertical drop.
    _emitChildUmbrella(xref, x, y, parentMidY, nodes, edges);

    // Place siblings of f/m BEFORE recursing deeper so their subtree umbrellas
    // can span the right groups.
    _placeAncestorSiblings(fatherXref, fatherX, nextY, expandedSiblingsXrefs, expandedAncestors, nodes, edges);
    _placeAncestorSiblings(motherXref, motherX, nextY, expandedSiblingsXrefs, expandedAncestors, nodes, edges);

    _placeAncestors(fatherXref, fatherX, nextY, nextGen, expandedAncestors, expandedSiblingsXrefs, nodes, edges);
    _placeAncestors(motherXref, motherX, nextY, nextGen, expandedAncestors, expandedSiblingsXrefs, nodes, edges);
  } else {
    const singleParent = fatherXref || motherXref;
    nodes.push({ xref: singleParent, x, y: nextY, generation: nextGen, role: 'ancestor' });

    // Single parent → umbrella / straight drop from parent bottom to child top.
    _emitChildUmbrella(xref, x, y, nextY + NODE_H, nodes, edges);

    _placeAncestorSiblings(singleParent, x, nextY, expandedSiblingsXrefs, expandedAncestors, nodes, edges);
    _placeAncestors(singleParent, x, nextY, nextGen, expandedAncestors, expandedSiblingsXrefs, nodes, edges);
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
      x1: childCx, y1: anchorY,
      x2: childCx, y2: y,
      type: 'ancestor',
    });
    return;
  }

  const umbrellaY = y - (ROW_HEIGHT - NODE_H) / 2;

  // Per-child centers (ancestor + each expanded sibling; NOT spouses).
  const centers = [childCx, ...sibNodes.map(n => n.x + NODE_W / 2)].sort((a, b) => a - b);
  const groupCenterX = (centers[0] + centers[centers.length - 1]) / 2;

  // Anchor drop from parent marriage-midpoint (above the ancestor child, so at
  // childCx) down to the umbrella bar. When the group center sits to one side
  // of childCx (asymmetric sibling split), route an L-shape: vertical halfway,
  // horizontal across, vertical the rest of the way.
  if (Math.abs(groupCenterX - childCx) < 0.5) {
    edges.push({
      x1: childCx, y1: anchorY,
      x2: childCx, y2: umbrellaY,
      type: 'ancestor',
    });
  } else {
    const elbowY = (anchorY + umbrellaY) / 2;
    edges.push({
      x1: childCx, y1: anchorY,
      x2: childCx, y2: elbowY,
      type: 'ancestor',
    });
    edges.push({
      x1: childCx,     y1: elbowY,
      x2: groupCenterX, y2: elbowY,
      type: 'ancestor',
    });
    edges.push({
      x1: groupCenterX, y1: elbowY,
      x2: groupCenterX, y2: umbrellaY,
      type: 'ancestor',
    });
  }

  // Crossbar from leftmost to rightmost child center.
  if (centers.length > 1) {
    edges.push({
      x1: centers[0], y1: umbrellaY,
      x2: centers[centers.length - 1], y2: umbrellaY,
      type: 'ancestor',
    });
  }

  // Vertical drop from umbrella down to each child's top.
  centers.forEach(cx => {
    edges.push({
      x1: cx, y1: umbrellaY,
      x2: cx, y2: y,
      type: 'ancestor',
    });
  });
}

// ---------------------------------------------------------------------------
// Ancestor sibling placement
// ---------------------------------------------------------------------------

// For a single ancestor node at (ancX, ancY), if it's in expandedSiblingsXrefs,
// place its full siblings INLINE at the same y as the ancestor: older siblings
// leftward, younger (tie = younger) rightward, each followed by its spouse(s).
// Grouping is handled by the parent umbrella (_emitChildUmbrella) — no bracket
// edge is emitted from here.
//
// Note: the sibling-expand chevron currently sits 4px off the ancestor pill,
// which will overlap the first inline sibling. Chevron relocation (move to the
// outer edge of the inline group) is tracked as a follow-up polish task.
function _placeAncestorSiblings(ancXref, ancX, ancY, expandedSiblingsXrefs, effectiveExpandedAncestors, nodes, edges) {
  if (!expandedSiblingsXrefs || !expandedSiblingsXrefs.has(ancXref)) return;
  const sibs = RELATIVES[ancXref]?.siblings ?? [];
  if (sibs.length === 0) return;

  const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP } = DESIGN;
  // Sibling↔spouse gap mirrors descendant-row convention (tight, no MARRIAGE_GAP).
  const SIB_MARRIAGE_GAP = H_GAP;

  const sorted = _sortByBirthYear(sibs);
  const ancBY  = PEOPLE[ancXref]?.birth_year ?? 9999;
  const older   = sorted.filter(s => (PEOPLE[s]?.birth_year ?? 9999) <  ancBY);
  const younger = sorted.filter(s => (PEOPLE[s]?.birth_year ?? 9999) >= ancBY);
  const generation = Math.round(ancY / ROW_HEIGHT);
  const midY = ancY + NODE_H / 2;

  // Younger siblings: pack right of ancestor, chronologically asc (closest = oldest-younger).
  let cursor = ancX + NODE_W;
  younger.forEach(sibXref => {
    const sibX = cursor + H_GAP;
    nodes.push({ xref: sibXref, x: sibX, y: ancY, generation, role: 'ancestor_sibling' });
    let cursorRight = sibX + NODE_W;
    const sibSpouses = RELATIVES[sibXref]?.spouses ?? [];
    sibSpouses.forEach(spXref => {
      const spX = cursorRight + SIB_MARRIAGE_GAP;
      nodes.push({ xref: spXref, x: spX, y: ancY, generation, role: 'ancestor_sibling_spouse' });
      edges.push({
        x1: cursorRight, y1: midY,
        x2: spX,          y2: midY,
        type: 'marriage',
      });
      cursorRight = spX + NODE_W;
    });
    cursor = cursorRight;
  });

  // Older siblings: pack left of ancestor. Iterate oldest→newest (sorted asc)
  // so the oldest sibling ends up furthest from the ancestor.
  let leftCursor = ancX;  // leftCursor is the left edge of whatever was most-recently placed
  older.forEach(sibXref => {
    // sibling's spouse(s) sit to the LEFT of the sibling (closer to ancestor)
    // if we imagine the sibling as the "anchor" of its own nuclear family. But
    // for consistency with focus-row packing, put the sibling first and its
    // spouse(s) further LEFT (further from ancestor). That mirrors how older
    // focus-row siblings pack (oldest on the far left).
    const sibSpouses = RELATIVES[sibXref]?.spouses ?? [];
    // Compute the full width of this sibling's group: sib + spouses + gaps.
    let groupW = NODE_W;
    sibSpouses.forEach(() => { groupW += SIB_MARRIAGE_GAP + NODE_W; });
    // Group's right edge sits H_GAP left of leftCursor.
    const groupRight = leftCursor - H_GAP;
    const groupLeft  = groupRight - groupW;
    // Sibling pill goes at groupRight - NODE_W (rightmost slot of the group).
    const sibX = groupRight - NODE_W;
    nodes.push({ xref: sibXref, x: sibX, y: ancY, generation, role: 'ancestor_sibling' });
    // Spouses fan leftward from the sibling.
    let cursorLeft = sibX;
    sibSpouses.forEach(spXref => {
      const spX = cursorLeft - SIB_MARRIAGE_GAP - NODE_W;
      nodes.push({ xref: spXref, x: spX, y: ancY, generation, role: 'ancestor_sibling_spouse' });
      edges.push({
        x1: spX + NODE_W, y1: midY,
        x2: cursorLeft,    y2: midY,
        type: 'marriage',
      });
      cursorLeft = spX;
    });
    leftCursor = groupLeft;
  });
}

// ---------------------------------------------------------------------------
// Contour-based separation (Reingold-Tilford style)
// ---------------------------------------------------------------------------

// Each contour is an array indexed by depth (0 = the root row itself).
// Element d = distance from the subtree-root center to the rightmost
// (_rightContour) or leftmost (_leftContour) point of the subtree at depth d.

// Right extension of xref's own inline sibling-group from xref's right edge.
// Returns 0 when the ancestor is not sibling-expanded or has no younger sibs.
function _inlineSiblingExtentRight(xref, expandedSiblingsXrefs) {
  if (!expandedSiblingsXrefs || !expandedSiblingsXrefs.has(xref)) return 0;
  const { NODE_W, H_GAP } = DESIGN;
  const sibs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
  if (sibs.length === 0) return 0;
  const bY = PEOPLE[xref]?.birth_year ?? 9999;
  const younger = _sortByBirthYear(sibs).filter(s => (PEOPLE[s]?.birth_year ?? 9999) >= bY);
  let extent = 0;
  younger.forEach(s => {
    extent += H_GAP + NODE_W;
    const sp = (RELATIVES[s] && RELATIVES[s].spouses) || [];
    sp.forEach(() => { extent += H_GAP + NODE_W; });
  });
  return extent;
}

// Mirror of the above: left extension from xref's left edge, driven by older sibs.
function _inlineSiblingExtentLeft(xref, expandedSiblingsXrefs) {
  if (!expandedSiblingsXrefs || !expandedSiblingsXrefs.has(xref)) return 0;
  const { NODE_W, H_GAP } = DESIGN;
  const sibs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
  if (sibs.length === 0) return 0;
  const bY = PEOPLE[xref]?.birth_year ?? 9999;
  const older = _sortByBirthYear(sibs).filter(s => (PEOPLE[s]?.birth_year ?? 9999) < bY);
  let extent = 0;
  older.forEach(s => {
    extent += H_GAP + NODE_W;
    const sp = (RELATIVES[s] && RELATIVES[s].spouses) || [];
    sp.forEach(() => { extent += H_GAP + NODE_W; });
  });
  return extent;
}

function _rightContour(xref, expandedAncestors, expandedSiblingsXrefs) {
  const { NODE_W } = DESIGN;
  const contour = [NODE_W / 2 + _inlineSiblingExtentRight(xref, expandedSiblingsXrefs)];
  if (!expandedAncestors.has(xref)) return contour;
  const parents = PARENTS[xref] ?? [];
  const f = parents[0] ?? null;
  const m = parents[1] ?? null;
  if (!f && !m) return contour;
  if (f && m) {
    // Mother is the right-side parent; root-to-mother-center = sep/2.
    const sep = _requiredSeparation(f, m, expandedAncestors, expandedSiblingsXrefs);
    const mc  = _rightContour(m, expandedAncestors, expandedSiblingsXrefs);
    for (let d = 0; d < mc.length; d++) contour[d + 1] = sep / 2 + mc[d];
  } else {
    const only = f || m;
    const oc = _rightContour(only, expandedAncestors, expandedSiblingsXrefs);
    for (let d = 0; d < oc.length; d++) contour[d + 1] = oc[d];
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
  if (f && m) {
    // Father is the left-side parent; root-to-father-center = sep/2.
    const sep = _requiredSeparation(f, m, expandedAncestors, expandedSiblingsXrefs);
    const fc  = _leftContour(f, expandedAncestors, expandedSiblingsXrefs);
    for (let d = 0; d < fc.length; d++) contour[d + 1] = sep / 2 + fc[d];
  } else {
    const only = f || m;
    const oc = _leftContour(only, expandedAncestors, expandedSiblingsXrefs);
    for (let d = 0; d < oc.length; d++) contour[d + 1] = oc[d];
  }
  return contour;
}

// Center-to-center separation required so the two parent subtrees do not
// overlap at any shared depth. Floor = SLOT (parents sit adjacent at row 0).
function _requiredSeparation(fatherXref, motherXref, expandedAncestors, expandedSiblingsXrefs) {
  const { NODE_W, H_GAP } = DESIGN;
  const rf = _rightContour(fatherXref, expandedAncestors, expandedSiblingsXrefs);
  const lm = _leftContour(motherXref, expandedAncestors, expandedSiblingsXrefs);
  const shared = Math.min(rf.length, lm.length);
  let sep = NODE_W + H_GAP;
  for (let d = 0; d < shared; d++) {
    sep = Math.max(sep, rf[d] + lm[d] + H_GAP);
  }
  return sep;
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
  };
}
