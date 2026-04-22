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

function _renderEdge(edge) {
    return _svgEl('line', {
        x1: edge.x1,
        y1: edge.y1,
        x2: edge.x2,
        y2: edge.y2,
        class: `edge-${edge.type}`,
    });
}

// ---------------------------------------------------------------------------
// Node rendering
// ---------------------------------------------------------------------------

// Append a small amber badge to a node <g> when the person died as a child,
// infant, or stillborn.  Placed in the top-right corner of the node box.
function _drawDiedYoungBadge(g, w, ageAtDeath) {
    if (!ageAtDeath) return;
    const cx = w - 11,
        cy = 11;
    const titleText = ageAtDeath === 'STILLBORN' ? 'Stillborn' :
        ageAtDeath === 'INFANT' ? 'Died in infancy' :
        'Died in childhood';
    const circle = _svgEl('circle', { cx, cy, r: 8, class: 'badge-died-young', 'pointer-events': 'all' });
    const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    titleEl.textContent = titleText;
    circle.appendChild(titleEl);
    g.appendChild(circle);
    const sym = _svgEl('text', {
        x: cx,
        y: cy + 3,
        'text-anchor': 'middle',
        class: 'badge-died-young-text',
        'font-size': 9,
        'font-weight': 700,
        'font-family': 'system-ui, sans-serif',
        'pointer-events': 'none',
    });
    sym.textContent = '\u2726'; // ✦ BLACK FOUR POINTED STAR
    g.appendChild(sym);
}

// Append a small hamburger badge to a node <g> whose person participates in
// two or more FAMs. Placed in the top-left corner. Clicking opens the
// spouse-menu modal via openSpouseMenuModal(xref).
function _personFamCount(xref) {
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return 0;
    let n = 0;
    for (const f in FAMILIES) {
        const fam = FAMILIES[f];
        if (fam && (fam.husb === xref || fam.wife === xref)) n++;
    }
    return n;
}

function _drawSpouseMenuBadge(g, xref) {
    const cx = 11, cy = 11;
    const circle = _svgEl('circle', {
        cx, cy, r: 8,
        class: 'spouse-menu-btn',
        'data-xref': xref,
        cursor: 'pointer',
    });
    const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    titleEl.textContent = 'Spouses';
    circle.appendChild(titleEl);
    g.appendChild(circle);
    // Three short horizontal lines (hamburger icon)
    for (let i = -1; i <= 1; i++) {
        const line = _svgEl('line', {
            x1: cx - 3, y1: cy + i * 2.5,
            x2: cx + 3, y2: cy + i * 2.5,
            class: 'badge-spouse-menu-icon',
            'stroke-width': 1.2,
            'stroke-linecap': 'round',
            'pointer-events': 'none',
        });
        g.appendChild(line);
    }
    circle.addEventListener('click', (e) => {
        e.stopPropagation();
        if (typeof openSpouseMenuModal === 'function') openSpouseMenuModal(xref);
    });
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

function _renderNode(node, onNodeClick, onExpandClick, expandedNodes = new Set(), onSiblingExpandClick = () => {}, expandedSiblingsXrefs = new Set(), expandedChildrenPersons = new Set(), onChildrenExpandClick = () => {}) {
    const {
        BG_NODE,
        BG_NODE_FOCUS,
        BORDER,
        BORDER_FOCUS,
        ACCENT_SPOUSE,
        TEXT_PRIMARY,
        TEXT_SECONDARY,
        TEXT_MUTED,
        TEXT_DIM,
        NODE_W,
        NODE_W_FOCUS,
        NODE_H,
        NODE_H_FOCUS,
        NODE_RADIUS,
    } = DESIGN;

    const isFocus = node.role === 'focus';
    const isSpouse = node.role === 'spouse';
    const isSpouseSib = node.role === 'spouse_sibling';
    const isAncestor = node.role === 'ancestor';

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
        strokeWidth = 1; // fill/stroke handled by CSS .node-spouse-sib
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

    // Background rect — spouse-sib colors come from CSS; all others use DESIGN attrs
    const rectAttrs = { x: 0, y: 0, width: w, height: h, rx: NODE_RADIUS, 'stroke-width': strokeWidth };
    if (isSpouseSib) {
        rectAttrs.class = 'node-spouse-sib';
    } else {
        rectAttrs.fill = fill;
        rectAttrs.stroke = stroke;
    }
    const rect = _svgEl('rect', rectAttrs);
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

    // Spouse-menu hamburger badge (top-left) when person has ≥2 FAMs.
    if (_personFamCount(node.xref) >= 2) {
        _drawSpouseMenuBadge(g, node.xref);
    }

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

            const chevronUp = `M ${btnCx - 3.5} ${btnCy + 1.5} L ${btnCx} ${btnCy - 2} L ${btnCx + 3.5} ${btnCy + 1.5}`;
            const chevronDown = `M ${btnCx - 3.5} ${btnCy - 1.5} L ${btnCx} ${btnCy + 2} L ${btnCx + 3.5} ${btnCy - 1.5}`;
            const chevronD = canCollapse ? chevronDown : chevronUp;

            const btn = _svgEl('circle', {
                cx: btnCx,
                cy: btnCy,
                r: 8,
                class: `expand-btn ${canCollapse ? 'btn-collapse' : 'btn-expand'}`,
                cursor: 'pointer',
            });
            const chevron = _svgEl('path', {
                d: chevronD,
                class: 'btn-chevron',
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

            // Outward when can-expand; inward when expanded (collapse indicator).
            const pointRight = side === 'right' ? !sibCanCollapse : sibCanCollapse;
            const chevronOut = pointRight ?
                `M ${sibCx - 1.5} ${sibCy - 3.5} L ${sibCx + 2} ${sibCy} L ${sibCx - 1.5} ${sibCy + 3.5}` :
                `M ${sibCx + 1.5} ${sibCy - 3.5} L ${sibCx - 2} ${sibCy} L ${sibCx + 1.5} ${sibCy + 3.5}`;

            const sibBtn = _svgEl('circle', {
                cx: sibCx,
                cy: sibCy,
                r: R,
                class: `sibling-expand-btn ${sibCanCollapse ? 'btn-collapse' : 'btn-expand'}`,
                cursor: 'pointer',
            });
            const sibChevron = _svgEl('path', {
                d: chevronOut,
                class: 'btn-chevron',
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

    // Children-expand chevron — under the pill's bottom-center. Only drawn
    // for eligible roles (person, not spouse) AND when the person has at
    // least one FAM with children.
    if (CHILDREN_EXPAND_ROLES.has(node.role) && _personHasKids(node.xref)) {
        _drawChildrenExpandBadge(g, node, expandedChildrenPersons.has(node.xref), onChildrenExpandClick);
    }

    return g;
}

// Roles eligible for a children-expand chevron. A chevron is anchored on the
// *person* (not the couple): clicking reveals children from all of that
// person's FAMs at once. Excluded roles either already expose their children
// elsewhere (focus, ancestor) or represent a spouse rather than a lineage
// person (spouse, descendant_spouse, ancestor_sibling_spouse, spouse_sibling).
const CHILDREN_EXPAND_ROLES = new Set(['sibling', 'descendant', 'ancestor_sibling']);

function _personHasKids(xref) {
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return false;
    for (const famXref in FAMILIES) {
        const fam = FAMILIES[famXref];
        if (!fam) continue;
        if ((fam.husb === xref || fam.wife === xref) && fam.chil && fam.chil.length > 0) {
            return true;
        }
    }
    return false;
}

function _drawChildrenExpandBadge(g, node, isExpanded, onChildrenExpandClick) {
    const { NODE_W, NODE_H } = DESIGN;
    const R = 8;
    const GAP = 6;
    const cx = NODE_W / 2;
    const cy = NODE_H + GAP + R;

    const chevronDown = `M ${cx - 3.5} ${cy - 1.5} L ${cx} ${cy + 2} L ${cx + 3.5} ${cy - 1.5}`;
    const chevronUp = `M ${cx - 3.5} ${cy + 1.5} L ${cx} ${cy - 2} L ${cx + 3.5} ${cy + 1.5}`;
    const d = isExpanded ? chevronUp : chevronDown;

    const btn = _svgEl('circle', {
        cx,
        cy,
        r: R,
        class: `children-expand-btn ${isExpanded ? 'btn-collapse' : 'btn-expand'}`,
        cursor: 'pointer',
        'data-xref': node.xref,
    });
    const chev = _svgEl('path', {
        d,
        class: 'btn-chevron',
        'stroke-width': 1.5,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        fill: 'none',
        'pointer-events': 'none',
    });
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        onChildrenExpandClick(node.xref);
    });
    g.appendChild(btn);
    g.appendChild(chev);
}

// ---------------------------------------------------------------------------
// Pan / zoom state
// ---------------------------------------------------------------------------

let _treeRoot = null; // the <g id="tree-root"> wrapper
let _svgElRef = null; // the owning <svg>, cached for resetView
let _tx = 0,
    _ty = 0; // current translation
let _scale = 1; // current zoom scale
let _dragging = false;
let _dragStartX = 0,
    _dragStartY = 0;
let _txAtDragStart = 0,
    _tyAtDragStart = 0;

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
    const expandedChildrenPersons = state.expandedChildrenPersons || new Set();
    const visibleSpouseFams = state.visibleSpouseFams || new Set();

    const { nodes, edges } = computeLayout(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenPersons, visibleSpouseFams);

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
            const siblingXrefs = (RELATIVES[xref] && RELATIVES[xref].siblings) || [];
            const childrenPersons = new Set(current.expandedChildrenPersons || new Set());
            for (const s of siblingXrefs) childrenPersons.delete(s);
            setState({ expandedSiblingsXrefs: sibs, expandedChildrenPersons: childrenPersons });
        } else {
            sibs.add(xref);
            const parents = new Set(current.expandedNodes || new Set());
            parents.add(xref);
            setState({ expandedSiblingsXrefs: sibs, expandedNodes: parents });
        }
    }

    // ── Children-expand click handler ────────────────────────────────────────
    // Toggles a person xref in expandedChildrenPersons.
    function onChildrenExpandClick(personXref) {
        const current = getState().expandedChildrenPersons || new Set();
        const next = new Set(current);
        if (next.has(personXref)) next.delete(personXref);
        else next.add(personXref);
        setState({ expandedChildrenPersons: next });
    }

    // ── Render edges (below nodes) ───────────────────────────────────────────
    for (const edge of edges) {
        _treeRoot.appendChild(_renderEdge(edge));
    }

    // ── Render nodes ─────────────────────────────────────────────────────────
    for (const node of nodes) {
        const g = _renderNode(
            node,
            onNodeClick,
            onExpandClick,
            expandedNodes,
            onSiblingExpandClick,
            expandedSiblingsXrefs,
            expandedChildrenPersons,
            onChildrenExpandClick,
        );
        _treeRoot.appendChild(g);
    }
}

// ---------------------------------------------------------------------------
// initRenderer
// ---------------------------------------------------------------------------

function resetView() {
    if (!_svgElRef || !_treeRoot) return;
    const w = parseFloat(_svgElRef.getAttribute('width') || 800);
    const h = parseFloat(_svgElRef.getAttribute('height') || 600);
    _tx = w / 2;
    _ty = h / 2;
    _scale = 1;
    _applyTransform();
}

function initRenderer(svgEl) {
    _svgElRef = svgEl;

    // Create the tree-root group
    _treeRoot = _svgEl('g', { id: 'tree-root' });

    // Initial transform: center the canvas on (svgWidth/2, svgHeight/2)
    // so the focus node at layout origin (0,0) appears centered.
    resetView();

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

if (typeof module !== 'undefined') module.exports = { initRenderer, render, resetView };