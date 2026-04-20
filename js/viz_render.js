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

function _truncateName(name, maxLen) {
  if (!name) return '?';
  if (name.length <= maxLen) return name;
  return name.slice(0, maxLen - 1) + '\u2026';
}

function _formatYears(person) {
  const parts = [];
  if (person && person.birth_year) parts.push('b.' + person.birth_year);
  if (person && person.death_year) parts.push('d.' + person.death_year);
  return parts.join('  ');
}

function _renderNode(node, onNodeClick, onExpandClick, expandedNodes = new Set(), onSiblingExpandClick = () => {}, expandedSiblingsXrefs = new Set()) {
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
  const displayName = _truncateName(person.name, 20);
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

  // Name text — in upper half of rect, leaving room for years below
  const nameY = isFocus ? h * 0.40 : h * 0.42;
  const nameEl = _svgEl('text', {
    x: w / 2,
    y: nameY,
    'text-anchor': 'middle',
    'dominant-baseline': 'middle',
    fill: nameFill,
    'font-size': nameFontSize,
    'font-weight': nameWeight,
    'font-family': 'system-ui, sans-serif',
    'pointer-events': 'none',
  });
  nameEl.textContent = displayName;
  g.appendChild(nameEl);

  // Years text — below name with comfortable padding
  if (years) {
    const yearsEl = _svgEl('text', {
      x: w / 2,
      y: h - 7,
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
  // Three visual states:
  //   !hasParents  → grey up-chevron, inert (no click listener)
  //   can expand   → green up-chevron (click to reveal parents)
  //   can collapse → blue down-chevron (click to hide parents)
  if (isAncestor) {
    const btnCx = w / 2;
    const btnCy = -20;
    const parents = PARENTS[node.xref] || [null, null];
    const hasParents = parents.some(p => p !== null);
    const isExpanded = expandedNodes.has(node.xref);
    const canExpand   = hasParents && !isExpanded;
    const canCollapse = hasParents &&  isExpanded;

    const btnFill = canCollapse ? '#2a5a7a'
                 : canExpand    ? '#2a7a4a'
                 :                '#4a4a6a';

    const chevronUp   = `M ${btnCx - 3.5} ${btnCy + 1.5} L ${btnCx} ${btnCy - 2} L ${btnCx + 3.5} ${btnCy + 1.5}`;
    const chevronDown = `M ${btnCx - 3.5} ${btnCy - 1.5} L ${btnCx} ${btnCy + 2} L ${btnCx + 3.5} ${btnCy - 1.5}`;
    const chevronD    = canCollapse ? chevronDown : chevronUp;

    const btn = _svgEl('circle', {
      cx: btnCx,
      cy: btnCy,
      r: 8,
      fill: btnFill,
      class: 'expand-btn',
      cursor: hasParents ? 'pointer' : 'default',
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
    if (hasParents) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        onExpandClick(node.xref);
      });
    }
    g.appendChild(btn);
    g.appendChild(chevron);
  }

  // Sibling expand chevron — outward-facing horizontal chevron on the short
  // edge of ancestor pills. Male → left, female → right.
  // Tri-state (mirrors the parent chevron colours):
  //   !hasSiblings → grey,  inert
  //   can expand   → green, chevron points outward
  //   can collapse → blue,  chevron points inward
  if (isAncestor) {
    const person2 = PEOPLE[node.xref] || {};
    const sibs = (RELATIVES[node.xref] && RELATIVES[node.xref].siblings) || [];
    const hasSiblings = sibs.length > 0;
    const isSibExpanded = expandedSiblingsXrefs.has(node.xref);
    const sibCanExpand   = hasSiblings && !isSibExpanded;
    const sibCanCollapse = hasSiblings &&  isSibExpanded;
    const side = person2.sex === 'F' ? 'right' : 'left';
    const R = 8;
    const GAP = 4;
    const sibCx = side === 'right' ? (w + GAP + R) : -(GAP + R);
    const sibCy = h / 2;

    const sibFill = sibCanCollapse ? '#2a5a7a'
                  : sibCanExpand   ? '#2a7a4a'
                  :                  '#4a4a6a';

    // Outward-pointing chevron (left-side: points left, right-side: points right)
    // Inward when expanded (collapse indicator).
    const pointRight = side === 'right' ? sibCanExpand : sibCanCollapse;
    const chevronOut = pointRight
      ? `M ${sibCx - 1.5} ${sibCy - 3.5} L ${sibCx + 2} ${sibCy} L ${sibCx - 1.5} ${sibCy + 3.5}`
      : `M ${sibCx + 1.5} ${sibCy - 3.5} L ${sibCx - 2} ${sibCy} L ${sibCx + 1.5} ${sibCy + 3.5}`;

    const sibBtn = _svgEl('circle', {
      cx: sibCx,
      cy: sibCy,
      r: R,
      fill: sibFill,
      class: 'sibling-expand-btn',
      cursor: hasSiblings ? 'pointer' : 'default',
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
    if (hasSiblings) {
      sibBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        onSiblingExpandClick(node.xref);
      });
    }
    g.appendChild(sibBtn);
    g.appendChild(sibChevron);
  }

  return g;
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

  const { nodes, edges } = computeLayout(focusXref, expandedNodes, expandedSiblingsXrefs);

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

  // ── Render edges (below nodes) ───────────────────────────────────────────
  for (const edge of edges) {
    _treeRoot.appendChild(_renderEdge(edge));
  }

  // ── Render nodes ─────────────────────────────────────────────────────────
  for (const node of nodes) {
    const g = _renderNode(node, onNodeClick, onExpandClick, expandedNodes, onSiblingExpandClick, expandedSiblingsXrefs);
    _treeRoot.appendChild(g);
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
