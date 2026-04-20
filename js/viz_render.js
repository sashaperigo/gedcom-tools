// SVG renderer for the hourglass family tree visualiser.
//
// Reads the following globals (set by HTML template or tests):
//   DESIGN       — from viz_design.js
//   PEOPLE       — { [xref]: { name, birth_year, death_year, ... } }
//   PARENTS      — { [xref]: [fatherXref|null, motherXref|null] }
//   CHILDREN     — { [xref]: [childXref, ...] }
//   RELATIVES    — { [xref]: { siblings: [...], spouses: [...] } }
//
// Calls globals from viz_state.js:
//   setState(updates)
//   getState()
//   onStateChange(callback)
//
// Calls global from viz_layout.js:
//   computeLayout(focusXref, expandedAncestors, spouseSiblingsExpanded)

// ---------------------------------------------------------------------------
// SVG element helper
// ---------------------------------------------------------------------------

function _svgEl(tag, attrs) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

// ---------------------------------------------------------------------------
// Edge rendering
// ---------------------------------------------------------------------------

const EDGE_STYLES = {
  ancestor:   { stroke: '#44447a', width: 1 },
  descendant: { stroke: '#2c2c54', width: 1 },
  marriage:   { stroke: '#3a6a3a', width: 1.5 },
};

function _renderEdge(edge) {
  const style = EDGE_STYLES[edge.type] || EDGE_STYLES.ancestor;
  return _svgEl('line', {
    x1: edge.x1,
    y1: edge.y1,
    x2: edge.x2,
    y2: edge.y2,
    stroke: style.stroke,
    'stroke-width': style.width,
    fill: 'none',
  });
}

// ---------------------------------------------------------------------------
// Node rendering
// ---------------------------------------------------------------------------

// Append a small amber badge to a node <g> when the person died as a child,
// infant, or stillborn.  Placed in the top-right corner of the node box.
function _drawDiedYoungBadge(g, w, ageAtDeath) {
  if (!ageAtDeath) return;
  const cx = w - 11, cy = 11;
  const titleText = ageAtDeath === 'STILLBORN' ? 'Stillborn'
                  : ageAtDeath === 'INFANT'    ? 'Died in infancy'
                  :                              'Died in childhood';
  const circle = _svgEl('circle', { cx, cy, r: 8, fill: '#fbbf24', 'pointer-events': 'all' });
  const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
  titleEl.textContent = titleText;
  circle.appendChild(titleEl);
  g.appendChild(circle);
  const sym = _svgEl('text', {
    x: cx, y: cy + 3,
    'text-anchor': 'middle', fill: '#1c1917',
    'font-size': 9, 'font-weight': 700,
    'font-family': 'system-ui, sans-serif', 'pointer-events': 'none',
  });
  sym.textContent = '\u2726';  // ✦ BLACK FOUR POINTED STAR
  g.appendChild(sym);
}

function _truncateLine(text, maxLen) {
  if (!text) return '';
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1) + '\u2026';
}

// Split a full name into (line1, line2) for two-line wrapping.
// Strategy: split on the LAST whitespace so "Given middle Surname" becomes
// ["Given middle", "Surname"]. Single-word names render on one line.
function _splitName(name, maxLen) {
  if (!name) return ['?', ''];
  const trimmed = name.trim();
  const idx = trimmed.lastIndexOf(' ');
  if (idx < 0) return [_truncateLine(trimmed, maxLen), ''];
  return [
    _truncateLine(trimmed.slice(0, idx), maxLen),
    _truncateLine(trimmed.slice(idx + 1), maxLen),
  ];
}

function _formatYears(person) {
  const parts = [];
  if (person && person.birth_year) parts.push('b.' + person.birth_year);
  if (person && person.death_year) parts.push('d.' + person.death_year);
  return parts.join('  ');
}

function _renderNode(node, onNodeClick, onExpandClick, expandedNodes = new Set(), onSiblingExpandClick = () => {}, expandedSiblingsXrefs = new Set(), onChildrenExpandClick = () => {}, expandedChildrenFams = new Set()) {
  const {
    BG_NODE, BG_NODE_FOCUS, BORDER, BORDER_FOCUS, ACCENT_SPOUSE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_DIM,
    NODE_W, NODE_W_FOCUS, NODE_H, NODE_H_FOCUS, NODE_RADIUS,
  } = DESIGN;

  const isFocus      = node.role === 'focus';
  const isSpouse     = node.role === 'spouse';
  const isSpouseSib  = node.role === 'spouse_sibling';
  const isAncestor   = node.role === 'ancestor';

  const w = isFocus ? NODE_W_FOCUS : NODE_W;
  const h = isFocus ? NODE_H_FOCUS : NODE_H;

  // Fill and stroke
  let fill, stroke, strokeWidth;
  if (isFocus) {
    fill = BG_NODE_FOCUS;
    stroke = BORDER_FOCUS;
    strokeWidth = 1.5;
  } else if (isSpouse) {
    fill = BG_NODE;
    stroke = ACCENT_SPOUSE;
    strokeWidth = 1;
  } else if (isSpouseSib) {
    fill = '#0e0e22';
    stroke = '#22224a';
    strokeWidth = 1;
  } else {
    // ancestor, sibling, descendant
    fill = BG_NODE;
    stroke = BORDER;
    strokeWidth = 1;
  }

  // Text colors
  let nameFill, nameWeight, nameFontSize, yearFill;
  if (isFocus) {
    nameFill = TEXT_PRIMARY;
    nameWeight = 600;
    nameFontSize = 12;
    yearFill = TEXT_MUTED;
  } else if (isSpouseSib) {
    nameFill = TEXT_DIM;
    nameWeight = 500;
    nameFontSize = 10;
    yearFill = TEXT_MUTED;
  } else {
    nameFill = TEXT_SECONDARY;
    nameWeight = 500;
    nameFontSize = 11;
    yearFill = TEXT_MUTED;
  }

  const person = PEOPLE[node.xref] || {};
  const [nameLine1, nameLine2] = _splitName(person.name, 13);
  const years = _formatYears(person);

  // Group positioned at (node.x, node.y)
  const g = _svgEl('g', {
    transform: `translate(${node.x}, ${node.y})`,
    'data-xref': node.xref,
    cursor: 'pointer',
  });

  // Background rect
  const rect = _svgEl('rect', {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx: NODE_RADIUS,
    fill,
    stroke,
    'stroke-width': strokeWidth,
  });
  g.appendChild(rect);

  // Name text — wraps to two lines when the name has whitespace. Line 1 sits
  // in the upper portion of the pill; line 2 (when present) sits just below.
  const hasTwoLines = nameLine2.length > 0;
  const line1Y = hasTwoLines ? h * 0.28 : h * 0.40;
  const line2Y = h * 0.52;

  const nameEl = _svgEl('text', {
    x: w / 2,
    y: line1Y,
    'text-anchor': 'middle',
    'dominant-baseline': 'middle',
    fill: nameFill,
    'font-size': nameFontSize,
    'font-weight': nameWeight,
    'font-family': 'system-ui, sans-serif',
    'pointer-events': 'none',
  });
  nameEl.textContent = nameLine1;
  g.appendChild(nameEl);

  if (hasTwoLines) {
    const nameEl2 = _svgEl('text', {
      x: w / 2,
      y: line2Y,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      fill: nameFill,
      'font-size': nameFontSize,
      'font-weight': nameWeight,
      'font-family': 'system-ui, sans-serif',
      'pointer-events': 'none',
    });
    nameEl2.textContent = nameLine2;
    g.appendChild(nameEl2);
  }

  // Years text — bottom gutter
  if (years) {
    const yearsEl = _svgEl('text', {
      x: w / 2,
      y: h - 10,
      'text-anchor': 'middle',
      fill: yearFill,
      'font-size': 9,
      'font-family': 'system-ui, sans-serif',
      'pointer-events': 'none',
    });
    yearsEl.textContent = years;
    g.appendChild(yearsEl);
  }

  // Died-young badge (stillborn / infant / child)
  _drawDiedYoungBadge(g, w, person.age_at_death);

  // Click handler
  g.addEventListener('click', (e) => {
    e.stopPropagation();
    onNodeClick(node);
  });

  // Expand button on ancestor nodes — floats above the top edge with a small gap.
  // Only rendered when the ancestor has parents. Two visual states:
  //   can expand   → green up-chevron (click to reveal parents)
  //   can collapse → blue down-chevron (click to hide parents)
  if (isAncestor) {
    const parents = PARENTS[node.xref] || [null, null];
    const hasParents = parents.some(p => p !== null);
    if (hasParents) {
      const btnCx = w / 2;
      const btnCy = -14;
      const isExpanded = expandedNodes.has(node.xref);
      const canCollapse = isExpanded;

      const btnFill = canCollapse ? '#2a5a7a' : '#2a7a4a';

      const chevronUp   = `M ${btnCx - 3.5} ${btnCy + 1.5} L ${btnCx} ${btnCy - 2} L ${btnCx + 3.5} ${btnCy + 1.5}`;
      const chevronDown = `M ${btnCx - 3.5} ${btnCy - 1.5} L ${btnCx} ${btnCy + 2} L ${btnCx + 3.5} ${btnCy - 1.5}`;
      const chevronD    = canCollapse ? chevronDown : chevronUp;

      const btn = _svgEl('circle', {
        cx: btnCx,
        cy: btnCy,
        r: 8,
        fill: btnFill,
        class: 'expand-btn',
        cursor: 'pointer',
      });
      const chevron = _svgEl('path', {
        d: chevronD,
        stroke: '#ffffff',
        'stroke-width': 1.5,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        fill: 'none',
        'pointer-events': 'none',
      });
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        onExpandClick(node.xref);
      });
      g.appendChild(btn);
      g.appendChild(chevron);
    }
  }

  // Sibling expand chevron — outward-facing horizontal chevron on the short
  // edge of ancestor pills. Male → left, female → right. Only rendered when
  // the ancestor has siblings. Two visual states:
  //   can expand   → green, chevron points outward
  //   can collapse → blue,  chevron points inward
  if (isAncestor) {
    const sibs = (RELATIVES[node.xref] && RELATIVES[node.xref].siblings) || [];
    const hasSiblings = sibs.length > 0;
    if (hasSiblings) {
      const person2 = PEOPLE[node.xref] || {};
      const isSibExpanded = expandedSiblingsXrefs.has(node.xref);
      const sibCanCollapse = isSibExpanded;
      const side = person2.sex === 'F' ? 'right' : 'left';
      const R = 8;
      const GAP = 4;
      const sibCx = side === 'right' ? (w + GAP + R) : -(GAP + R);
      const sibCy = h / 2;

      const sibFill = sibCanCollapse ? '#2a5a7a' : '#2a7a4a';

      // Outward when can-expand; inward when expanded (collapse indicator).
      const pointRight = side === 'right' ? !sibCanCollapse : sibCanCollapse;
      const chevronOut = pointRight
        ? `M ${sibCx - 1.5} ${sibCy - 3.5} L ${sibCx + 2} ${sibCy} L ${sibCx - 1.5} ${sibCy + 3.5}`
        : `M ${sibCx + 1.5} ${sibCy - 3.5} L ${sibCx - 2} ${sibCy} L ${sibCx + 1.5} ${sibCy + 3.5}`;

      const sibBtn = _svgEl('circle', {
        cx: sibCx,
        cy: sibCy,
        r: R,
        fill: sibFill,
        class: 'sibling-expand-btn',
        cursor: 'pointer',
      });
      const sibChevron = _svgEl('path', {
        d: chevronOut,
        stroke: '#ffffff',
        'stroke-width': 1.5,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        fill: 'none',
        'pointer-events': 'none',
      });
      sibBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        onSiblingExpandClick(node.xref);
      });
      g.appendChild(sibBtn);
      g.appendChild(sibChevron);
    }
  }

  return g;
}

// Children-expand chevron top-level pass. One chevron per eligible FAM,
// rendered as a direct child of the tree-root group (so a couple-centered
// position between two pills is expressible in the same coordinate space as
// the nodes). A FAM is eligible iff it has children, at least one of its
// parents is visible, and none of its visible parents is the focus or a
// direct ancestor (those already expose their children via the focus-row or
// sibling-expand affordances).
function _renderChildrenExpandPass(nodes, expandedChildrenFams, onChildrenExpandClick) {
  if (typeof FAMILIES === 'undefined' || !FAMILIES) return [];
  const { NODE_W, NODE_H } = DESIGN;
  const nodeByXref = new Map(nodes.map(n => [n.xref, n]));
  const els = [];
  for (const famXref in FAMILIES) {
    const fam = FAMILIES[famXref];
    if (!fam || !fam.chil || fam.chil.length === 0) continue;
    const husbNode = fam.husb ? nodeByXref.get(fam.husb) : null;
    const wifeNode = fam.wife ? nodeByXref.get(fam.wife) : null;
    const parentNodes = [husbNode, wifeNode].filter(Boolean);
    if (parentNodes.length === 0) continue;
    if (parentNodes.some(n => n.role === 'focus' || n.role === 'ancestor')) continue;

    const R = 8;
    const GAP = 6;
    let ccx, ccy;
    if (parentNodes.length === 2) {
      ccx = (parentNodes[0].x + NODE_W + parentNodes[1].x) / 2;
      ccy = Math.max(parentNodes[0].y, parentNodes[1].y) + NODE_H + GAP + R;
    } else {
      ccx = parentNodes[0].x + NODE_W / 2;
      ccy = parentNodes[0].y + NODE_H + GAP + R;
    }

    const isExpanded = expandedChildrenFams.has(famXref);
    const fill = isExpanded ? '#2a5a7a' : '#2a7a4a';
    const chevronDown = `M ${ccx - 3.5} ${ccy - 1.5} L ${ccx} ${ccy + 2} L ${ccx + 3.5} ${ccy - 1.5}`;
    const chevronUp   = `M ${ccx - 3.5} ${ccy + 1.5} L ${ccx} ${ccy - 2} L ${ccx + 3.5} ${ccy + 1.5}`;
    const d = isExpanded ? chevronUp : chevronDown;

    const btn = _svgEl('circle', {
      cx: ccx, cy: ccy, r: R,
      fill,
      class: 'children-expand-btn',
      cursor: 'pointer',
      'data-fam': famXref,
    });
    const chev = _svgEl('path', {
      d, stroke: '#ffffff',
      'stroke-width': 1.5,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      fill: 'none',
      'pointer-events': 'none',
    });
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      onChildrenExpandClick(famXref);
    });
    els.push(btn, chev);
  }
  return els;
}

// ---------------------------------------------------------------------------
// Pan / zoom state
// ---------------------------------------------------------------------------

let _treeRoot  = null;    // the <g id="tree-root"> wrapper
let _tx = 0, _ty = 0;    // current translation
let _scale = 1;           // current zoom scale
let _dragging = false;
let _dragStartX = 0, _dragStartY = 0;
let _txAtDragStart = 0, _tyAtDragStart = 0;

function _applyTransform() {
  _treeRoot.setAttribute('transform', `translate(${_tx}, ${_ty}) scale(${_scale})`);
}

function _attachPanZoom(svgEl) {
  svgEl.addEventListener('mousedown', (e) => {
    // Only pan when clicking background/edges, not a node or expand button.
    // Nodes carry a [data-xref] ancestor; expand buttons sit inside those groups.
    const isNodeTarget = e.target.closest && e.target.closest('[data-xref]');
    if (isNodeTarget) return;
    _dragging = true;
    _dragStartX = e.clientX;
    _dragStartY = e.clientY;
    _txAtDragStart = _tx;
    _tyAtDragStart = _ty;
  });

  svgEl.addEventListener('mousemove', (e) => {
    if (!_dragging) return;
    _tx = _txAtDragStart + (e.clientX - _dragStartX);
    _ty = _tyAtDragStart + (e.clientY - _dragStartY);
    _applyTransform();
  });

  svgEl.addEventListener('mouseup', () => { _dragging = false; });
  svgEl.addEventListener('mouseleave', () => { _dragging = false; });

  svgEl.addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault && e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.min(2.5, Math.max(0.3, _scale * delta));

    // Zoom centered on mouse position
    const rect = svgEl.getBoundingClientRect ? svgEl.getBoundingClientRect() : { left: 0, top: 0 };
    const mouseX = (e.clientX || 0) - rect.left;
    const mouseY = (e.clientY || 0) - rect.top;

    _tx = mouseX - (mouseX - _tx) * (newScale / _scale);
    _ty = mouseY - (mouseY - _ty) * (newScale / _scale);
    _scale = newScale;
    _applyTransform();
  });
}

// ---------------------------------------------------------------------------
// Main render function
// ---------------------------------------------------------------------------

function render() {
  const state = getState();
  const focusXref = state.focusXref;
  const expandedNodes = state.expandedNodes || new Set();
  const expandedSiblingsXrefs = state.expandedSiblingsXrefs || new Set();
  const expandedChildrenFams = state.expandedChildrenFams || new Set();

  const { nodes, edges } = computeLayout(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams);

  // Clear tree-root contents
  _treeRoot.innerHTML = '';

  // ── Node click handler ───────────────────────────────────────────────────
  function onNodeClick(node) {
    setState({ panelOpen: true, panelXref: node.xref });
  }

  // ── Expand button click handler ──────────────────────────────────────────
  // Toggles expansion state: collapses if already expanded, expands otherwise.
  function onExpandClick(xref) {
    const current = getState().expandedNodes || new Set();
    const next = new Set(current);
    if (next.has(xref)) next.delete(xref);
    else next.add(xref);
    setState({ expandedNodes: next });
  }

  // ── Sibling expand click handler ─────────────────────────────────────────
  // Expanding also auto-expands the ancestor's parents so the sibling bracket
  // has an anchor. Collapsing only removes from expandedSiblingsXrefs.
  function onSiblingExpandClick(xref) {
    const current = getState();
    const sibs = new Set(current.expandedSiblingsXrefs || new Set());
    if (sibs.has(xref)) {
      sibs.delete(xref);
      setState({ expandedSiblingsXrefs: sibs });
    } else {
      sibs.add(xref);
      const parents = new Set(current.expandedNodes || new Set());
      parents.add(xref);
      setState({ expandedSiblingsXrefs: sibs, expandedNodes: parents });
    }
  }

  // ── Children-expand click handler ────────────────────────────────────────
  // Toggles a FAM xref in expandedChildrenFams.
  function onChildrenExpandClick(famXref) {
    const current = getState().expandedChildrenFams || new Set();
    const next = new Set(current);
    if (next.has(famXref)) next.delete(famXref);
    else next.add(famXref);
    setState({ expandedChildrenFams: next });
  }

  // ── Render edges (below nodes) ───────────────────────────────────────────
  for (const edge of edges) {
    _treeRoot.appendChild(_renderEdge(edge));
  }

  // ── Render nodes ─────────────────────────────────────────────────────────
  for (const node of nodes) {
    const g = _renderNode(node, onNodeClick, onExpandClick, expandedNodes, onSiblingExpandClick, expandedSiblingsXrefs);
    _treeRoot.appendChild(g);
  }

  // ── Children-expand chevrons (one per eligible FAM, tree-root level) ─────
  for (const el of _renderChildrenExpandPass(nodes, expandedChildrenFams, onChildrenExpandClick)) {
    _treeRoot.appendChild(el);
  }
}

// ---------------------------------------------------------------------------
// initRenderer
// ---------------------------------------------------------------------------

function initRenderer(svgEl) {
  // Create the tree-root group
  _treeRoot = _svgEl('g', { id: 'tree-root' });

  // Initial transform: center the canvas on (svgWidth/2, svgHeight/2)
  // so the focus node at layout origin (0,0) appears centered.
  const w = parseFloat(svgEl.getAttribute('width') || 800);
  const h = parseFloat(svgEl.getAttribute('height') || 600);
  _tx = w / 2;
  _ty = h / 2;
  _scale = 1;

  _treeRoot.setAttribute('transform', `translate(${_tx}, ${_ty}) scale(${_scale})`);
  svgEl.appendChild(_treeRoot);

  // Attach pan/zoom
  _attachPanZoom(svgEl);

  // Register re-render on state changes
  onStateChange(render);

  // Initial render
  render();
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') module.exports = { initRenderer, render };
