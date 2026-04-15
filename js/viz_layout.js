// Layout engine for the ancestor tree SVG visualiser.
//
// Reads the following module-level globals (set by the HTML template before
// this file loads, or injected via global.* in tests):
//
//   NODE_W, NODE_H, H_GAP, V_GAP, BTN_PAD, MARGIN_X, MARGIN_TOP, BTN_ZONE
//   visibleKeys        — Set of Ahnentafel integer keys currently shown
//   currentTree        — Map of key → xref  (Ahnentafel tree)
//   expandedRelatives  — Set of keys whose relatives panel is open
//   expandedChildrenOf — Set of xrefs whose children are shown
//   PEOPLE             — Map of xref → {sex, birth_year, …}
//   RELATIVES          — Map of xref → {siblings, spouses, sib_spouses, …}
//   CHILDREN           — Map of xref → [child xref, …]
//
// Writes to:
//   _posCache          — Map of key → {x, y}  (ancestor positions)
//   _relPosCache       — Map of key-string → {x, y, xref, …}  (relative positions)
//   _sibSlots          — Map (internal, cleared on each computePositions call)
//   _sibSpouseIdx      — Map of "${anchorKey}:${sibIdx}" → current spouse index

// ---------------------------------------------------------------------------
// Ahnentafel helpers
// ---------------------------------------------------------------------------

function genOf(k) { return Math.floor(Math.log2(k)); }
function slotOf(k) { return k - Math.pow(2, genOf(k)); }

function maxVisibleGen() {
  let mx = 0;
  for (const k of visibleKeys) mx = Math.max(mx, genOf(k));
  return mx;
}

// True if key k represents a male: even keys (fathers) are male; key 1 uses GEDCOM sex field.
function isMaleKey(k) {
  if (k === 1) return PEOPLE[currentTree[1]]?.sex === 'M';
  return k % 2 === 0;
}

// ---------------------------------------------------------------------------
// Subtree width
// ---------------------------------------------------------------------------

// Pre-computed new sibling slot counts per key (excludes already-visible ancestors).
// Built before layout so _subtreeWidth can use it.
const _sibSlots = new Map();
function _buildSibSlots() {
  _sibSlots.clear();
  const visXrefs = new Set([...visibleKeys].map(k => currentTree[k]).filter(Boolean));
  for (const k of expandedRelatives) {
    if (k === 1) continue;  // root handled separately; no layout slot needed
    const rels = RELATIVES[currentTree[k]];
    if (!rels) continue;
    const n = rels.siblings.filter(xref => !visXrefs.has(xref)).length;
    if (n > 0) _sibSlots.set(k, n);
  }
}

function _subtreeWidth(k, cache) {
  if (cache.has(k)) return cache.get(k);
  const fk = 2*k, mk = 2*k+1;
  const hasFather = visibleKeys.has(fk);
  const hasMother = visibleKeys.has(mk);
  let w;
  if (!hasFather && !hasMother) {
    w = 1;
  } else {
    const fw = hasFather ? _subtreeWidth(fk, cache) : 0;
    const mw = hasMother ? _subtreeWidth(mk, cache) : 0;
    // Add 1 gap slot when both sides have visible ancestors so the two parent
    // groups don't run into each other.
    const fHasAnc = hasFather && (visibleKeys.has(2*fk) || visibleKeys.has(2*fk+1));
    const mHasAnc = hasMother && (visibleKeys.has(2*mk) || visibleKeys.has(2*mk+1));
    // QUICK FIX: inject a fixed 1-slot gap when both sides have ancestors.
    // This prevents the two parent groups from touching but is too blunt —
    // it applies the same gap at every level regardless of actual subtree density,
    // and doesn't handle asymmetric cases (e.g. one side much wider than the other).
    // A proper fix would use a Reingold-Tilford-style contour algorithm to compute
    // the minimal separation that avoids overlap at each level.
    // See: https://github.com/sashaperigo/gedcom-tools/issues/5
    w = Math.max(1, fw + mw + (fHasAnc && mHasAnc ? 1 : 0));
  }
  // Reserve sibling slots (non-root only; root siblings are placed outside layout bounds)
  w += _sibSlots.get(k) || 0;
  cache.set(k, w);
  return w;
}

// ---------------------------------------------------------------------------
// Ancestor position layout
// ---------------------------------------------------------------------------

function computePositions() {
  _posCache = new Map();
  _buildSibSlots();
  const maxGen = maxVisibleGen();
  const slotW  = NODE_W + H_GAP;
  const wCache = new Map();
  _subtreeWidth(1, wCache);

  function layout(k, xStart) {
    const w      = wCache.get(k) || 1;
    const sibN   = _sibSlots.get(k) || 0;
    const male   = isMaleKey(k);
    // Male non-root with siblings: shift node right so siblings fit to its left.
    // Female non-root: siblings extend right; node stays at natural left edge of its ancestor slots.
    const leftShift  = (male && k !== 1) ? sibN : 0;
    const ancestorW  = w - sibN;          // slots used by actual ancestor subtree

    const fk = 2*k, mk = 2*k+1;
    const hasFather = visibleKeys.has(fk);
    const hasMother = visibleKeys.has(mk);
    const g  = genOf(k);
    const x  = xStart + leftShift * slotW + (ancestorW * slotW - NODE_W) / 2;
    const y  = MARGIN_TOP + BTN_ZONE + (maxGen - g) * (NODE_H + V_GAP);
    _posCache.set(k, {x, y});

    // Lay out children so parents center above the full sibling group (not just the ancestor subtree).
    // Shifting by sibN/2 slots places parents above the midpoint of the combined anchor+sibling row.
    const fHasAnc = hasFather && (visibleKeys.has(2*fk) || visibleKeys.has(2*fk+1));
    const mHasAnc = hasMother && (visibleKeys.has(2*mk) || visibleKeys.has(2*mk+1));
    const familyGap = (fHasAnc && mHasAnc) ? slotW : 0;
    let offset = xStart + (sibN / 2) * slotW;
    if (hasFather) { const fw = wCache.get(fk) || 1; layout(fk, offset); offset += fw * slotW; }
    offset += familyGap;
    if (hasMother) { layout(mk, offset); }
  }
  layout(1, MARGIN_X);

  // Couple compaction: move an isolated parent (no visible ancestors, no expanded siblings)
  // adjacent to their partner when the gap between them exceeds one slot.
  // This prevents e.g. a father with no ancestors from being placed far left of a mother
  // whose large subtree pushed her far right.
  for (const k of visibleKeys) {
    const fk = 2*k, mk = 2*k+1;
    if (!visibleKeys.has(fk) || !visibleKeys.has(mk)) continue;
    const fp = _posCache.get(fk), mp = _posCache.get(mk);
    if (!fp || !mp) continue;
    const fHasAncestors = visibleKeys.has(2*fk) || visibleKeys.has(2*fk+1);
    const mHasAncestors = visibleKeys.has(2*mk) || visibleKeys.has(2*mk+1);
    const fHasSiblings  = (_sibSlots.get(fk) || 0) > 0;
    const mHasSiblings  = (_sibSlots.get(mk) || 0) > 0;
    const gap = mp.x - (fp.x + NODE_W + H_GAP);
    if (!fHasAncestors && !fHasSiblings && gap > slotW) {
      _posCache.set(fk, {x: mp.x - NODE_W - H_GAP, y: fp.y});
    } else if (!mHasAncestors && !mHasSiblings && gap > slotW) {
      _posCache.set(mk, {x: fp.x + NODE_W + H_GAP, y: mp.y});
    }
  }
}

function nodePos(k) {
  return _posCache.get(k) || {x: 0, y: 0};
}

// ---------------------------------------------------------------------------
// Relative (sibling / spouse / child) position layout
// ---------------------------------------------------------------------------

function computeRelativePositions() {
  _relPosCache.clear();
  const slotW = NODE_W + H_GAP;
  // Build xref → Ahnentafel key map for all visible ancestors
  const xrefToKey = new Map();
  for (const k of visibleKeys) {
    const xref = currentTree[k];
    if (xref) xrefToKey.set(xref, k);
  }

  for (const k of expandedRelatives) {
    if (!_posCache.has(k)) continue;
    const {x, y} = _posCache.get(k);
    const rels = RELATIVES[currentTree[k]];
    if (!rels) continue;
    const male = isMaleKey(k);

    // Spouses always go to the RIGHT of the anchor
    let newSpIdx = 0;
    rels.spouses.forEach((xref, j) => {
      const existingKey = xrefToKey.get(xref);
      if (existingKey !== undefined) {
        const pos = _posCache.get(existingKey);
        if (pos) _relPosCache.set(`sp:${k}:${j}`, {x: pos.x, y: pos.y, xref, existing: true});
      } else {
        _relPosCache.set(`sp:${k}:${j}`, {x: x + NODE_W + H_GAP + newSpIdx * slotW, y, xref, existing: false});
        newSpIdx++;
      }
    });

    // Siblings: males go LEFT, females go RIGHT (after any new spouses).
    // Each sibling group occupies 1 + (number of sibling's spouses) slots.
    // Sort chronologically so the leftmost sibling is always the earliest born.
    // For male anchors (siblings left), first-iterated lands nearest the anchor
    // (rightmost among siblings), so we reverse the sorted order.
    // We preserve the original array index as the cache key so _sibSpouseIdx
    // (spouse cycle state) remains stable across re-renders.
    const _sibsSorted = rels.siblings
      .map((xref, origIdx) => ({xref, origIdx, by: (PEOPLE[xref] || {}).birth_year || 9999}))
      .sort((a, b) => a.by - b.by);
    if (male) _sibsSorted.reverse();

    let newSibOffset = 0;
    _sibsSorted.forEach(({xref, origIdx: i}) => {
      const sibSpouses = (rels.sib_spouses || {})[xref] || [];
      const existingKey = xrefToKey.get(xref);
      if (existingKey !== undefined) {
        const pos = _posCache.get(existingKey);
        if (pos) _relPosCache.set(`sib:${k}:${i}`, {x: pos.x, y: pos.y, xref, existing: true});
        // Sibling already in tree — no new slot consumed, skip its spouses here
      } else {
        const sibX = male
          ? x - (newSibOffset + 1) * slotW - BTN_PAD                          // left of anchor, with button clearance
          : x + NODE_W + H_GAP + BTN_PAD + (newSpIdx + newSibOffset) * slotW; // right, after spouses, with button clearance
        _relPosCache.set(`sib:${k}:${i}`, {x: sibX, y, xref, existing: false});

        // Show only the currently-selected spouse (one slot reserved if any spouses exist)
        if (sibSpouses.length > 0) {
          const spIdx = _sibSpouseIdx.get(`${k}:${i}`) || 0;
          const spXref = sibSpouses[spIdx];
          const existingSpKey = xrefToKey.get(spXref);
          if (existingSpKey !== undefined) {
            const pos = _posCache.get(existingSpKey);
            if (pos) _relPosCache.set(`sibsp:${k}:${i}`, {x: pos.x, y: pos.y, xref: spXref, existing: true, total: sibSpouses.length, spIdx});
          } else {
            const spX = male
              ? x - (newSibOffset + 2) * slotW - BTN_PAD
              : x + NODE_W + H_GAP + BTN_PAD + (newSpIdx + newSibOffset + 1) * slotW;
            _relPosCache.set(`sibsp:${k}:${i}`, {x: spX, y, xref: spXref, existing: false, total: sibSpouses.length, spIdx});
          }
        }

        newSibOffset += 1 + (sibSpouses.length > 0 ? 1 : 0);
      }
    });
  }

  // Helper: compute spouse-line midpoint for a node, or fall back to node bottom-center
  function _spouseMidX(nx, ny, spouseEntry) {
    if (spouseEntry && !spouseEntry.existing) {
      const [lx, rx2] = spouseEntry.x < nx ? [spouseEntry.x + NODE_W, nx] : [nx + NODE_W, spouseEntry.x];
      return {stemX: (lx + rx2) / 2, stemY: ny + NODE_H / 2};
    }
    return {stemX: nx + NODE_W / 2, stemY: ny + NODE_H};
  }

  // Children below any expanded node (root or siblings)
  // Pass 1: root children
  const rootXref = currentTree[1];
  if (expandedChildrenOf.has(rootXref) && _posCache.has(1)) {
    const {x: rx, y: ry} = _posCache.get(1);
    const children = CHILDREN[rootXref] || [];
    if (children.length > 0) {
      const {stemX, stemY} = _spouseMidX(rx, ry, _relPosCache.get('sp:1:0'));
      const totalW = children.length * slotW - H_GAP;
      const startX = stemX - totalW / 2;
      children.forEach((cx, i) => {
        _relPosCache.set(`ch:${i}`, {x: startX + i * slotW, y: ry + NODE_H + V_GAP, xref: cx, stemX, stemY});
      });
    }
  }
  // Pass 2: sibling children — iterate over already-placed sibling entries
  for (const [key, entry] of [..._relPosCache.entries()]) {
    if (!key.startsWith('sib:') || key.startsWith('sibsp:') || entry.existing) continue;
    const {x: sibX, y: sibY, xref: sibXref} = entry;
    if (!expandedChildrenOf.has(sibXref)) continue;
    const sibChildren = CHILDREN[sibXref] || [];
    if (!sibChildren.length) continue;
    const [, k, i] = key.split(':');
    const {stemX, stemY} = _spouseMidX(sibX, sibY, _relPosCache.get(`sibsp:${k}:${i}`));
    const totalW = sibChildren.length * slotW - H_GAP;
    const startX = stemX - totalW / 2;
    sibChildren.forEach((cx, j) => {
      _relPosCache.set(`sibch:${k}:${i}:${j}`, {x: startX + j * slotW, y: sibY + NODE_H + V_GAP, xref: cx, stemX, stemY});
    });
  }

  // Pass 3: resolve collisions — push sibling groups outward if their children
  // overlap ANY fixed node (ancestor or root-children) at the same Y level.
  // Math: a sibling of a generation-G ancestor has children at y(G-1), which is
  // the exact same Y as generation-(G-1) ancestor nodes.  Pass 3 must check
  // _posCache (ancestors) not just ch: (root's own children).
  {
    // Build Y → {minX, maxX} for all fixed nodes.
    // Pad ancestor nodes by BTN_PAD on both sides to account for the expand/
    // relatives-toggle buttons that sit just outside the node box.
    const occupiedByY = new Map();
    const _mergeOcc = (y, xMin, xMax) => {
      if (!occupiedByY.has(y)) { occupiedByY.set(y, {minX: xMin, maxX: xMax}); return; }
      const b = occupiedByY.get(y);
      b.minX = Math.min(b.minX, xMin);
      b.maxX = Math.max(b.maxX, xMax);
    };
    for (const [, pos] of _posCache.entries())
      _mergeOcc(pos.y, pos.x - BTN_PAD, pos.x + NODE_W + BTN_PAD);
    for (const [k, e] of _relPosCache.entries()) {
      if (k.startsWith('ch:')) _mergeOcc(e.y, e.x, e.x + NODE_W);
    }

    // Group sibling-child entries by their parent sibling key
    const sibChGroups = new Map();
    for (const [k, e] of _relPosCache.entries()) {
      if (!k.startsWith('sibch:')) continue;
      const parts = k.split(':');
      const parentKey = `sib:${parts[1]}:${parts[2]}`;
      if (!sibChGroups.has(parentKey)) sibChGroups.set(parentKey, []);
      sibChGroups.get(parentKey).push([k, e]);
    }

    // Track anchors already processed so a second sibling group for the same
    // anchor doesn't double-shift the whole row.
    const processedAnchors = new Set();

    for (const [parentKey, chEntries] of sibChGroups.entries()) {
      const sibEntry = _relPosCache.get(parentKey);
      if (!sibEntry || sibEntry.existing) continue;

      const sibChY = chEntries[0][1].y;
      const occupied = occupiedByY.get(sibChY);
      if (!occupied) continue;

      const sibChMinX = Math.min(...chEntries.map(([, e]) => e.x));
      const sibChMaxX = Math.max(...chEntries.map(([, e]) => e.x)) + NODE_W;

      // No overlap — nothing to fix
      if (sibChMaxX <= occupied.minX || sibChMinX >= occupied.maxX) continue;

      const [, anchorK] = parentKey.split(':');
      if (processedAnchors.has(anchorK)) continue;
      processedAnchors.add(anchorK);

      // Compare the sibling's center to the occupied zone's center to determine
      // which way to push.  Using rootNodeX was wrong: it's at the bottom-center
      // of the tree and has no relationship to where the collision is happening.
      const occupiedCenter = (occupied.minX + occupied.maxX) / 2;
      const isLeft = (sibEntry.x + NODE_W / 2) < occupiedCenter;
      const shift = isLeft
        ? occupied.minX - H_GAP - sibChMaxX   // negative → push left
        : occupied.maxX + H_GAP - sibChMinX;  // positive → push right

      // Shift the ENTIRE sibling row for this anchor so all siblings (and their
      // spouses / children) move together and don't collide with each other.
      for (const [cacheKey, cacheEntry] of _relPosCache.entries()) {
        if (cacheEntry.existing) continue;
        if (!cacheKey.startsWith('sib')) continue;   // sib:, sibsp:, sibch:
        if (cacheKey.split(':')[1] !== anchorK) continue;
        cacheEntry.x += shift;
        if (cacheEntry.stemX !== undefined) cacheEntry.stemX += shift;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Visibility helpers
// ---------------------------------------------------------------------------

function hasHiddenParents(k) {
  return ((2 * k) in currentTree || (2 * k + 1) in currentTree) &&
         !visibleKeys.has(2 * k) && !visibleKeys.has(2 * k + 1);
}

function hasVisibleParents(k) {
  return visibleKeys.has(2 * k) || visibleKeys.has(2 * k + 1);
}

// ---------------------------------------------------------------------------
// Node export (for tests)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
  module.exports = {
    genOf, slotOf, isMaleKey, maxVisibleGen,
    _buildSibSlots, _subtreeWidth,
    computePositions, computeRelativePositions, nodePos,
    hasHiddenParents, hasVisibleParents,
  };
}
