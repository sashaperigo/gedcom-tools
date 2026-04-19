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
 * @param {boolean} spouseSiblingsExpanded - whether to show spouse's sibling row
 * @returns {{ nodes: Node[], edges: Edge[] }}
 *
 * Node: { xref, x, y, generation, role }
 *   role: 'focus' | 'ancestor' | 'descendant' | 'sibling' | 'spouse' | 'spouse_sibling'
 *
 * Edge: { x1, y1, x2, y2, type }
 *   type: 'ancestor' | 'descendant' | 'sibling_bracket' | 'marriage'
 */
function computeLayout(focusXref, expandedAncestors, spouseSiblingsExpanded) {
  const { NODE_W, NODE_W_FOCUS, NODE_H, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;
  const SLOT = NODE_W + H_GAP;
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
    if (spouseSiblingsExpanded && si === 0) {
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
      const fatherX = focusCenterX - SLOT / 2 - NODE_W / 2;
      const motherX = focusCenterX + SLOT / 2 - NODE_W / 2;

      nodes.push({ xref: fatherXref, x: fatherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
      nodes.push({ xref: motherXref, x: motherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });

      // Marriage edge between parents (father right edge → mother left edge).
      edges.push({
        x1: fatherX + NODE_W, y1: parentMidY,
        x2: motherX,           y2: parentMidY,
        type: 'marriage',
      });

      _placeAncestors(fatherXref, fatherX, -ROW_HEIGHT, -1, expandedAncestors, nodes, edges);
      _placeAncestors(motherXref, motherX, -ROW_HEIGHT, -1, expandedAncestors, nodes, edges);
    } else {
      // Single parent: centered on focus center.
      const singleParent = fatherXref || motherXref;
      const singleParentX = focusCenterX - NODE_W / 2;
      nodes.push({ xref: singleParent, x: singleParentX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
      _placeAncestors(singleParent, singleParentX, -ROW_HEIGHT, -1, expandedAncestors, nodes, edges);
    }

    // Umbrella geometry (mirrors the descendant umbrella).
    // Anchor drop: from bottom of parent row down to the umbrella bar, at focus center x.
    edges.push({
      x1: focusCenterX, y1: parentBottomY,
      x2: focusCenterX, y2: ancUmbrellaY,
      type: 'ancestor',
    });

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
    // Each group: child at groupStart, spouses at groupStart + i*(NODE_W + MARRIAGE_GAP).
    // Between groups: H_GAP separation.
    const groups = childXrefs.map(childXref => {
      const childSpouses = RELATIVES[childXref]?.spouses ?? [];
      const width = NODE_W + childSpouses.length * (MARRIAGE_GAP + NODE_W);
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
        const spouseX = childX + (si + 1) * (NODE_W + MARRIAGE_GAP);
        nodes.push({ xref: sxref, x: spouseX, y: ROW_HEIGHT, generation: 1, role: 'descendant_spouse' });

        // Marriage edge between consecutive members of the group (right edge → left edge)
        const prevX = si === 0 ? childX : childX + si * (NODE_W + MARRIAGE_GAP);
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

    // Drop from anchor down to umbrella bar
    edges.push({
      x1:   anchorX,
      y1:   NODE_H,
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

function _placeAncestors(xref, x, y, generation, expandedAncestors, nodes, edges) {
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
    const fw = _subtreeWidth(fatherXref, expandedAncestors);
    const mw = _subtreeWidth(motherXref, expandedAncestors);
    const fatherX = x - mw * SLOT / 2;
    const motherX = x + fw * SLOT / 2;

    nodes.push({ xref: fatherXref, x: fatherX, y: nextY, generation: nextGen, role: 'ancestor' });
    nodes.push({ xref: motherXref, x: motherX, y: nextY, generation: nextGen, role: 'ancestor' });

    const midY = nextY + ROW_HEIGHT / 2;
    edges.push({ x1: fatherX + NODE_W / 2, y1: nextY + NODE_H, x2: fatherX + NODE_W / 2, y2: midY, type: 'ancestor' });
    edges.push({ x1: motherX + NODE_W / 2, y1: nextY + NODE_H, x2: motherX + NODE_W / 2, y2: midY, type: 'ancestor' });
    edges.push({ x1: fatherX + NODE_W / 2, y1: midY, x2: motherX + NODE_W / 2, y2: midY, type: 'ancestor' });
    edges.push({ x1: x + NODE_W / 2, y1: midY, x2: x + NODE_W / 2, y2: y, type: 'ancestor' });

    _placeAncestors(fatherXref, fatherX, nextY, nextGen, expandedAncestors, nodes, edges);
    _placeAncestors(motherXref, motherX, nextY, nextGen, expandedAncestors, nodes, edges);
  } else {
    const singleParent = fatherXref || motherXref;
    nodes.push({ xref: singleParent, x, y: nextY, generation: nextGen, role: 'ancestor' });

    const midY = nextY + ROW_HEIGHT / 2;
    edges.push({ x1: x + NODE_W / 2, y1: nextY + NODE_H, x2: x + NODE_W / 2, y2: midY, type: 'ancestor' });
    edges.push({ x1: x + NODE_W / 2, y1: midY, x2: x + NODE_W / 2, y2: y, type: 'ancestor' });

    _placeAncestors(singleParent, x, nextY, nextGen, expandedAncestors, nodes, edges);
  }
}

// ---------------------------------------------------------------------------
// Subtree width (for overlap-free ancestor placement)
// ---------------------------------------------------------------------------

// Returns the number of leaf slots a person's visible ancestor subtree occupies.
// A node not being expanded counts as 1 slot (just itself).
// A node with both parents counts as the sum of their subtree widths.
function _subtreeWidth(xref, expandedAncestors) {
  if (!expandedAncestors.has(xref)) return 1;
  const parents = PARENTS[xref] ?? [];
  const fw = parents[0] ? _subtreeWidth(parents[0], expandedAncestors) : 0;
  const mw = parents[1] ? _subtreeWidth(parents[1], expandedAncestors) : 0;
  if (fw === 0 && mw === 0) return 1;
  return fw + mw;
}

// ---------------------------------------------------------------------------
// Exports (for tests and other modules)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
  module.exports = { computeLayout, _sortByBirthYear, _packRow, _subtreeWidth };
}
