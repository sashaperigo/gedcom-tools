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
  const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;
  const SLOT = NODE_W + H_GAP;

  const nodes = [];
  const edges = [];

  // ── Phase 1 & 2: Generation 0 (focus row) ────────────────────────────────

  const focusBY = PEOPLE[focusXref]?.birth_year ?? 9999;

  // Siblings split around focus
  const allSibs = RELATIVES[focusXref]?.siblings ?? [];
  const sortedSibs = _sortByBirthYear(allSibs);
  const olderSibs  = sortedSibs.filter(x => (PEOPLE[x]?.birth_year ?? 9999) < focusBY);
  const youngerSibs = sortedSibs.filter(x => (PEOPLE[x]?.birth_year ?? 9999) >= focusBY);

  // Older siblings: packed leftward from focus (closest sibling at index 0)
  olderSibs.forEach((xref, i) => {
    nodes.push({
      xref,
      x:          -(i + 1) * SLOT,
      y:          0,
      generation: 0,
      role:       'sibling',
    });
  });

  // Focus node at x=0
  nodes.push({ xref: focusXref, x: 0, y: 0, generation: 0, role: 'focus' });

  // Younger siblings: packed rightward from focus
  youngerSibs.forEach((xref, i) => {
    nodes.push({
      xref,
      x:          (i + 1) * SLOT,
      y:          0,
      generation: 0,
      role:       'sibling',
    });
  });

  // Spouse: placed after the rightmost gen-0 node + MARRIAGE_GAP
  const gen0Nodes = nodes.filter(n => n.generation === 0);
  const maxGen0X  = Math.max(...gen0Nodes.map(n => n.x));
  const spouseXrefs = RELATIVES[focusXref]?.spouses ?? [];
  let spouseX = maxGen0X + NODE_W + MARRIAGE_GAP;

  spouseXrefs.forEach((spouseXref, si) => {
    const thisSpouseX = spouseX + si * SLOT;
    nodes.push({
      xref:       spouseXref,
      x:          thisSpouseX,
      y:          0,
      generation: 0,
      role:       'spouse',
    });

    // Marriage edge: horizontal line between last sibling right edge and spouse
    edges.push({
      x1:   maxGen0X + NODE_W,
      y1:   NODE_H / 2,
      x2:   thisSpouseX,
      y2:   NODE_H / 2,
      type: 'marriage',
    });

    // Spouse's siblings (if expanded and this is the primary spouse)
    if (spouseSiblingsExpanded && si === 0) {
      const spouseSibs = _sortByBirthYear(RELATIVES[spouseXref]?.siblings ?? []);
      let nextX = thisSpouseX + SLOT;
      spouseSibs.forEach(xref => {
        nodes.push({
          xref,
          x:          nextX,
          y:          0,
          generation: 0,
          role:       'spouse_sibling',
        });
        nextX += SLOT;
      });
    }
  });

  // Sibling bracket edge (if there are siblings)
  if (allSibs.length > 0) {
    const gen0WithSibs = nodes.filter(n => n.generation === 0 && (n.role === 'focus' || n.role === 'sibling'));
    const minX = Math.min(...gen0WithSibs.map(n => n.x));
    const maxX = Math.max(...gen0WithSibs.map(n => n.x)) + NODE_W;
    const bracketY = -NODE_H / 2;
    edges.push({ x1: minX, y1: bracketY, x2: maxX, y2: bracketY, type: 'sibling_bracket' });
  }

  // ── Phase 2: Generation -1 (parents) ─────────────────────────────────────

  const focusParents = PARENTS[focusXref] ?? [];
  const fatherXref   = focusParents[0] ?? null;
  const motherXref   = focusParents[1] ?? null;

  if (fatherXref || motherXref) {
    if (fatherXref && motherXref) {
      // Both parents: father left of focus, mother right
      const parentOffset = SLOT / 2;
      const fatherX = 0 - parentOffset;
      const motherX = 0 + parentOffset;

      nodes.push({ xref: fatherXref, x: fatherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
      nodes.push({ xref: motherXref, x: motherX, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });

      // Ancestor edges from parents down to focus
      const midY = -ROW_HEIGHT / 2;
      edges.push({ x1: fatherX + NODE_W / 2, y1: -ROW_HEIGHT + NODE_H, x2: fatherX + NODE_W / 2, y2: midY, type: 'ancestor' });
      edges.push({ x1: motherX + NODE_W / 2, y1: -ROW_HEIGHT + NODE_H, x2: motherX + NODE_W / 2, y2: midY, type: 'ancestor' });
      edges.push({ x1: fatherX + NODE_W / 2, y1: midY, x2: motherX + NODE_W / 2, y2: midY, type: 'ancestor' });
      edges.push({ x1: NODE_W / 2, y1: midY, x2: NODE_W / 2, y2: 0, type: 'ancestor' });

      // Recurse into grandparents for each expanded ancestor
      _placeAncestors(fatherXref, fatherX, -ROW_HEIGHT, -1, expandedAncestors, nodes, edges);
      _placeAncestors(motherXref, motherX, -ROW_HEIGHT, -1, expandedAncestors, nodes, edges);
    } else {
      // Single parent: centered above focus
      const singleParent = fatherXref || motherXref;
      nodes.push({ xref: singleParent, x: 0, y: -ROW_HEIGHT, generation: -1, role: 'ancestor' });
      const midY = -ROW_HEIGHT / 2;
      edges.push({ x1: NODE_W / 2, y1: -ROW_HEIGHT + NODE_H, x2: NODE_W / 2, y2: midY, type: 'ancestor' });
      edges.push({ x1: NODE_W / 2, y1: midY, x2: NODE_W / 2, y2: 0, type: 'ancestor' });

      _placeAncestors(singleParent, 0, -ROW_HEIGHT, -1, expandedAncestors, nodes, edges);
    }
  }

  // ── Phase 2: Generation +1 (children) ────────────────────────────────────

  const childXrefs = CHILDREN[focusXref] ?? [];
  if (childXrefs.length > 0) {
    const n       = childXrefs.length;
    const totalW  = n * NODE_W + (n - 1) * H_GAP;
    const startX  = 0 - totalW / 2 + NODE_W / 2;

    childXrefs.forEach((xref, i) => {
      const cx = startX + i * SLOT;
      nodes.push({ xref, x: cx, y: ROW_HEIGHT, generation: 1, role: 'descendant' });

      // Edge from focus down to child
      edges.push({
        x1:   NODE_W / 2,
        y1:   NODE_H,
        x2:   cx + NODE_W / 2,
        y2:   ROW_HEIGHT,
        type: 'descendant',
      });

      // Recurse into grandchildren for expanded children
    });
  }

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Recursive ancestor placement
// ---------------------------------------------------------------------------

function _placeAncestors(xref, x, y, generation, expandedAncestors, nodes, edges) {
  const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP, DESIGN: _DESIGN } = {
    NODE_W:     DESIGN.NODE_W,
    NODE_H:     DESIGN.NODE_H,
    ROW_HEIGHT: DESIGN.ROW_HEIGHT,
    H_GAP:      DESIGN.H_GAP,
  };
  const SLOT = NODE_W + H_GAP;

  if (!expandedAncestors.has(xref)) return;

  const parentPair = PARENTS[xref] ?? [];
  const fatherXref = parentPair[0] ?? null;
  const motherXref = parentPair[1] ?? null;

  if (!fatherXref && !motherXref) return;

  const nextGen = generation - 1;
  const nextY   = nextGen * ROW_HEIGHT;

  if (fatherXref && motherXref) {
    const parentOffset = SLOT / 2;
    const fatherX = x - parentOffset;
    const motherX = x + parentOffset;

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
// Exports (for tests and other modules)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
  module.exports = { computeLayout, _sortByBirthYear, _packRow };
}
