// SVG rendering, pan/zoom transform, and tree visibility helpers.
// All functions here require a live DOM.

// ---------------------------------------------------------------------------
// Transform
// ---------------------------------------------------------------------------

function applyTransform() {
  document.getElementById('canvas').setAttribute(
    'transform', `translate(${tx}, ${ty}) scale(${scale})`
  );
  // Generation labels track only vertical pan — never horizontal.
  for (const lbl of document.getElementById('gen-labels').children) {
    lbl.style.top = (parseFloat(lbl.dataset.canvasY) * scale + ty) + 'px';
  }
}

function fitAndCenter(focusKey) {
  computePositions();
  computeRelativePositions();
  const vp = document.getElementById('viewport');
  let minX = Infinity, maxX = 0, maxY = 0;
  for (const {x, y} of _posCache.values()) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x + NODE_W);
    maxY = Math.max(maxY, y + NODE_H);
  }
  for (const {x, y} of _relPosCache.values()) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x + NODE_W);
    maxY = Math.max(maxY, y + NODE_H);
  }
  if (minX === Infinity) minX = 0;
  const treeW = maxX - minX + 2 * MARGIN_X;
  const treeH = maxY + 20;
  // QUICK FIX: fit to height only, ignoring width. This fills vertical space
  // but can leave wide trees clipped horizontally. A proper solution would
  // fit to height as the primary axis and then pan so the focal node is
  // centered — ensuring it's never out of view even when scaleX < scaleY.
  // See: https://github.com/sashaperigo/gedcom-tools/issues/6
  const scaleY = (vp.clientHeight * 0.92) / treeH;
  scale = Math.min(1, scaleY);

  // Left-align: pin the canvas to a fixed horizontal offset so the tree
  // doesn't shift when the detail panel opens/closes (which changes vp.clientWidth).
  const LEFT_OFFSET = 0;

  if (focusKey) {
    // Keep left alignment; only adjust vertical to place parents at ~30% from top.
    const fPos = _posCache.get(2 * focusKey);
    const mPos = _posCache.get(2 * focusKey + 1);
    const parentY = fPos ? fPos.y : (mPos ? mPos.y : null);
    if (parentY !== null) {
      ty = vp.clientHeight * 0.30 - parentY * scale;
    } else {
      ty = vp.clientHeight * 0.50 - (_posCache.get(focusKey)?.y ?? 0) * scale;
    }
    tx = LEFT_OFFSET;
  } else {
    tx = LEFT_OFFSET;
    ty = 0;
  }
  applyTransform();
}

function _animateFitAndCenter(duration) {
  const start = performance.now();
  function frame(now) {
    fitAndCenter();
    if (now - start < duration) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------------------
// SVG helpers
// ---------------------------------------------------------------------------

function svgEl(tag, attrs) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

// Append a small amber badge to a node <g> when the person died as a child,
// infant, or stillborn.  Placed in the top-right corner of the node box.
function drawDiedYoungBadge(g, nx, ny, ageAtDeath) {
  if (!ageAtDeath) return;
  const cx = nx + NODE_W - 11, cy = ny + 11;
  const titleText = ageAtDeath === 'STILLBORN' ? 'Stillborn'
                  : ageAtDeath === 'INFANT'    ? 'Died in infancy'
                  :                              'Died in childhood';
  const circle = svgEl('circle', { cx, cy, r: 8, fill: '#fbbf24', 'pointer-events': 'all' });
  const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
  titleEl.textContent = titleText;
  circle.appendChild(titleEl);
  g.appendChild(circle);
  const sym = svgEl('text', {
    x: cx, y: cy + 3,
    'text-anchor': 'middle', fill: '#1c1917',
    'font-size': 9, 'font-weight': 700,
    'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
  });
  sym.textContent = '\u2726';  // ✦ BLACK FOUR POINTED STAR
  g.appendChild(sym);
}

const GEN_LABELS = ['You', 'Parents', 'Grandparents', 'Great-grandparents'];
function genLabel(g) {
  if (g < GEN_LABELS.length) return GEN_LABELS[g];
  return (g - 1) + '\u00d7 Great-grandparents';
}

// ---------------------------------------------------------------------------
// Visibility + expand/collapse
// ---------------------------------------------------------------------------

function collapseNode(k) {
  function removeSubtree(n) {
    visibleKeys.delete(n);
    if (visibleKeys.has(2 * n)) removeSubtree(2 * n);
    if (visibleKeys.has(2 * n + 1)) removeSubtree(2 * n + 1);
  }
  if (visibleKeys.has(2 * k))     removeSubtree(2 * k);
  if (visibleKeys.has(2 * k + 1)) removeSubtree(2 * k + 1);
  render();
}

function expandNode(k) {
  if ((2 * k) in currentTree)     visibleKeys.add(2 * k);
  if ((2 * k + 1) in currentTree) visibleKeys.add(2 * k + 1);
  render();
}

// ---------------------------------------------------------------------------
// Main render
// ---------------------------------------------------------------------------

function render() {
  computePositions();
  computeRelativePositions();
  const maxGen = maxVisibleGen();
  const canvas = document.getElementById('canvas');
  canvas.innerHTML = '';

  // Connector lines (drawn below nodes)
  for (const k of visibleKeys) {
    const { x: cx, y: cy } = nodePos(k);
    const fk = 2 * k, mk = 2 * k + 1;
    const hasFather = visibleKeys.has(fk);
    const hasMother = visibleKeys.has(mk);
    if (!hasFather && !hasMother) continue;

    const childCx = cx + NODE_W / 2;

    if (hasFather && hasMother) {
      // Horizontal line between the two parents at mid-node height.
      const { x: fx, y: fy } = nodePos(fk);
      const { x: mx }        = nodePos(mk);
      const coupleY = fy + NODE_H / 2;
      canvas.appendChild(svgEl('line', {
        x1: fx + NODE_W, y1: coupleY, x2: mx, y2: coupleY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
      // Route through midY to avoid diagonal lines.
      // Always draw even when siblings are expanded (sibling connector may overdraw).
      const dropX = (fx + NODE_W + mx) / 2;  // midpoint of couple gap
      const midY  = cy - V_GAP / 2;
      canvas.appendChild(svgEl('line', {x1: dropX,   y1: coupleY, x2: dropX,   y2: midY,  stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: dropX,   y1: midY,   x2: childCx, y2: midY,   stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: childCx, y1: midY,   x2: childCx, y2: cy,     stroke: '#475569', 'stroke-width': 1.5}));
    } else if (hasFather) {
      const { x: fx, y: fy } = nodePos(fk);
      const px   = fx + NODE_W / 2;
      const midY = cy - V_GAP / 2;
      canvas.appendChild(svgEl('line', {x1: px,      y1: fy + NODE_H, x2: px,      y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: px,      y1: midY,        x2: childCx, y2: midY,  stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: childCx, y1: midY,        x2: childCx, y2: cy,    stroke: '#475569', 'stroke-width': 1.5}));
    } else {
      const { x: mx, y: my } = nodePos(mk);
      const px   = mx + NODE_W / 2;
      const midY = cy - V_GAP / 2;
      canvas.appendChild(svgEl('line', {x1: px,      y1: my + NODE_H, x2: px,      y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: px,      y1: midY,        x2: childCx, y2: midY,  stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: childCx, y1: midY,        x2: childCx, y2: cy,    stroke: '#475569', 'stroke-width': 1.5}));
    }
  }

  // Relative connectors (drawn before nodes so buttons render on top)
  for (const k of expandedRelatives) {
    const rels = RELATIVES[currentTree[k]];
    if (!rels) continue;
    const ancEntry = _posCache.get(k);
    if (!ancEntry) continue;
    const {x: ax, y: ay} = ancEntry;
    const hasFather = visibleKeys.has(2*k);
    const hasMother = visibleKeys.has(2*k+1);

    // Sibling connectors — Ancestry-style: one horizontal bar + individual vertical drops
    const newSibs = rels.siblings.map((sib, i) => _relPosCache.get(`sib:${k}:${i}`))
                                  .filter(e => e && !e.existing);
    if (newSibs.length) {
      const ancCx = ax + NODE_W / 2;
      const male = isMaleKey(k);
      const outerCx = male
        ? Math.min(...newSibs.map(e => e.x + NODE_W / 2))
        : Math.max(...newSibs.map(e => e.x + NODE_W / 2));
      const [barX1, barX2] = male ? [outerCx, ancCx] : [ancCx, outerCx];
      if (hasFather || hasMother) {
        const midY = ay - V_GAP / 2;
        let extBarX1 = barX1, extBarX2 = barX2;
        if (hasFather && hasMother) {
          const fp = _posCache.get(2*k), mp = _posCache.get(2*k+1);
          const coupleY = fp.y + NODE_H / 2;
          const dropX   = (fp.x + NODE_W + mp.x) / 2;
          canvas.appendChild(svgEl('line', {x1: dropX, y1: coupleY, x2: dropX, y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
          extBarX1 = Math.min(barX1, dropX);
          extBarX2 = Math.max(barX2, dropX);
        }
        canvas.appendChild(svgEl('line', {x1: extBarX1, y1: midY, x2: extBarX2, y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1: ancCx, y1: midY, x2: ancCx, y2: ay, stroke: '#475569', 'stroke-width': 1.5}));
        newSibs.forEach(({x: sx, y: sy}) => {
          const sibCx = sx + NODE_W / 2;
          canvas.appendChild(svgEl('line', {x1: sibCx, y1: midY, x2: sibCx, y2: sy, stroke: '#475569', 'stroke-width': 1.5}));
        });
      } else {
        const barY = ay - 20;
        canvas.appendChild(svgEl('line', {x1: barX1, y1: barY, x2: barX2, y2: barY, stroke: '#475569', 'stroke-width': 1.5}));
        newSibs.forEach(({x: sx, y: sy}) => {
          const sibCx = sx + NODE_W / 2;
          canvas.appendChild(svgEl('line', {x1: sibCx, y1: barY, x2: sibCx, y2: sy, stroke: '#475569', 'stroke-width': 1.5}));
        });
        canvas.appendChild(svgEl('line', {x1: ancCx, y1: barY, x2: ancCx, y2: ay, stroke: '#475569', 'stroke-width': 1.5}));
      }
    }

    // Anchor spouse marriage connectors
    rels.spouses.forEach((sp, j) => {
      const spEntry = _relPosCache.get(`sp:${k}:${j}`);
      if (!spEntry || spEntry.existing) return;
      const {x: spx} = spEntry;
      const lineY = ay + NODE_H / 2;
      const [x1, x2] = spx < ax ? [spx + NODE_W, ax] : [ax + NODE_W, spx];
      canvas.appendChild(svgEl('line', {x1, y1: lineY, x2, y2: lineY, stroke: '#0f766e', 'stroke-width': 1.5}));
    });

    // Sibling-spouse marriage connectors + cycle toggle button
    rels.siblings.forEach((sibXref, i) => {
      const sibEntry = _relPosCache.get(`sib:${k}:${i}`);
      if (!sibEntry || sibEntry.existing) return;
      const {x: sx, y: sy} = sibEntry;
      const spEntry = _relPosCache.get(`sibsp:${k}:${i}`);
      if (!spEntry || spEntry.existing) return;
      const {x: spx, total, spIdx} = spEntry;
      const lineY = sy + NODE_H / 2;
      const [x1, x2] = spx < sx ? [spx + NODE_W, sx] : [sx + NODE_W, spx];
      const midX = (x1 + x2) / 2;
      if (total > 1) {
        const gap = 12;
        canvas.appendChild(svgEl('line', {x1, y1: lineY, x2: midX - gap, y2: lineY, stroke: '#0f766e', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1: midX + gap, y1: lineY, x2, y2: lineY, stroke: '#0f766e', 'stroke-width': 1.5}));
        const bw = 20, bh = 16;
        const btn = svgEl('rect', {x: midX - bw/2, y: lineY - bh/2, width: bw, height: bh, rx: 4, fill: '#0f766e', cursor: 'pointer'});
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          _sibSpouseIdx.set(`${k}:${i}`, (spIdx + 1) % total);
          render();
        });
        canvas.appendChild(btn);
        canvas.appendChild(svgEl('polygon', {
          points: `${midX-4},${lineY-4} ${midX+5},${lineY} ${midX-4},${lineY+4}`,
          fill: 'white', 'pointer-events': 'none'
        }));
      } else {
        canvas.appendChild(svgEl('line', {x1, y1: lineY, x2, y2: lineY, stroke: '#0f766e', 'stroke-width': 1.5}));
      }
    });
  }

  // Generation labels — rendered in a separate overlay div (left-fixed, y-follows pan).
  // Populated here; positioned in applyTransform() using only ty+scale, never tx.
  const genLabelsEl = document.getElementById('gen-labels');
  genLabelsEl.innerHTML = '';
  const gensSeen = new Set([...visibleKeys].map(genOf));
  for (const g of [...gensSeen].sort((a, b) => a - b)) {
    const firstK = [...visibleKeys].find(k => genOf(k) === g);
    const { y } = nodePos(firstK);
    const lbl = document.createElement('div');
    lbl.className = 'gen-label';
    lbl.textContent = genLabel(g);
    lbl.dataset.canvasY = y + NODE_H / 2;
    genLabelsEl.appendChild(lbl);
  }

  // Person nodes
  for (const k of visibleKeys) {
    const { x, y } = nodePos(k);
    const data   = PEOPLE[currentTree[k]];
    const isRoot = (k === 1);
    const isMale = (k % 2 === 0 && k > 1);
    const fill   = isRoot ? '#2563eb' : (isMale ? '#1e40af' : '#6d28d9');

    const nodeG = svgEl('g', { cursor: 'pointer' });
    nodeG.addEventListener('click', (e) => {
      e.stopPropagation();
      const _xref = currentTree[k];
      console.log('[nodeG click] k=', k, 'xref=', _xref, 'didDrag=', didDrag);
      if (!didDrag) showDetail(_xref);
    });

    const nodeRect = svgEl('rect', {
      x, y, width: NODE_W, height: NODE_H,
      rx: 8, fill, opacity: 0.95
    });
    nodeG.appendChild(nodeRect);

    const displayName = data.name.length > 21
      ? data.name.slice(0, 19) + '\u2026'
      : data.name;
    const nameEl = svgEl('text', {
      x: x + NODE_W / 2, y: y + 22,
      'text-anchor': 'middle', fill: 'white',
      'font-size': 13, 'font-weight': 600,
      'font-family': 'system-ui, sans-serif',
      'pointer-events': 'none'
    });
    nameEl.textContent = displayName;
    nodeG.appendChild(nameEl);

    const years = [
      data.birth_year ? 'b.' + data.birth_year : '',
      data.death_year ? 'd.' + data.death_year : ''
    ].filter(Boolean).join('  ');
    if (years) {
      const yrEl = svgEl('text', {
        x: x + NODE_W / 2, y: y + 42,
        'text-anchor': 'middle', fill: 'rgba(255,255,255,0.65)',
        'font-size': 11,
        'font-family': 'system-ui, sans-serif',
        'pointer-events': 'none'
      });
      yrEl.textContent = years;
      nodeG.appendChild(yrEl);
    }
    drawDiedYoungBadge(nodeG, x, y, data.age_at_death);
    canvas.appendChild(nodeG);

    // Expand / collapse buttons — 16×16 polygon triangles, same size as side arrows
    if (hasHiddenParents(k)) {
      const bx = x + NODE_W / 2 - 8;
      const by = y - BTN_ZONE + 4;
      const btn = svgEl('rect', {x: bx, y: by, width: 16, height: 16, rx: 4, fill: '#059669', cursor: 'pointer'});
      btn.addEventListener('click', (e) => { e.stopPropagation(); console.log('[expandBtn click] k=', k, 'xref=', currentTree[k]); expandNode(k); });
      canvas.appendChild(btn);
      canvas.appendChild(svgEl('polygon', {
        points: `${bx+4},${by+11} ${bx+8},${by+5} ${bx+12},${by+11}`,
        fill: 'white', 'pointer-events': 'none'
      }));
    } else if (hasVisibleParents(k)) {
      const bx = x + NODE_W / 2 - 8;
      const by = y - BTN_ZONE + 4;
      const btn = svgEl('rect', {x: bx, y: by, width: 16, height: 16, rx: 4, fill: '#475569', cursor: 'pointer'});
      btn.addEventListener('click', (e) => { e.stopPropagation(); collapseNode(k); });
      canvas.appendChild(btn);
      canvas.appendChild(svgEl('polygon', {
        points: `${bx+4},${by+5} ${bx+8},${by+11} ${bx+12},${by+5}`,
        fill: 'white', 'pointer-events': 'none'
      }));
    }

    // Children expand/collapse button — only on root node, below it
    if (isRoot) {
      const rootXref_ = currentTree[1];
      if ((CHILDREN[rootXref_] || []).length > 0) {
        _drawChildrenBtn(canvas, x, y, rootXref_);
      }
    }

    // Relatives toggle button for non-root ancestors that have siblings or spouses.
    // Positioned outside the node on the side where siblings expand:
    // males expand left → button on left; females expand right → button on right.
    if (k !== 1 && RELATIVES[currentTree[k]]) {
      const isExpanded = expandedRelatives.has(k);
      const male = isMaleKey(k);
      const rbw = 16, rbh = 16;
      const rbx = male ? x - rbw - 4 : x + NODE_W + 4;
      const rby = y + (NODE_H - rbh) / 2;
      const rbtn = svgEl('rect', {
        x: rbx, y: rby, width: rbw, height: rbh,
        rx: 4, fill: isExpanded ? '#334155' : '#059669', cursor: 'pointer', opacity: 0.9
      });
      rbtn.addEventListener('click', (e) => {
        e.stopPropagation();
        console.log('[relToggle click] k=', k, 'xref=', currentTree[k]);
        if (expandedRelatives.has(k)) {
          expandedRelatives.delete(k);
          render();
        } else {
          expandedRelatives.add(k);
          // Auto-expand parents so siblings have a visible shared ancestor
          if ((2 * k) in currentTree) visibleKeys.add(2 * k);
          if ((2 * k + 1) in currentTree) visibleKeys.add(2 * k + 1);
          render();
        }
      });
      canvas.appendChild(rbtn);
      // Draw triangle as SVG polygon so left and right are perfect mirrors.
      // Collapsed: points toward where siblings will appear. Expanded: flips back.
      const pointLeft = (male !== isExpanded);
      const arrow = svgEl('polygon', {
        points: pointLeft
          ? `${rbx+11},${rby+4} ${rbx+5},${rby+8} ${rbx+11},${rby+12}`
          : `${rbx+5},${rby+4} ${rbx+11},${rby+8} ${rbx+5},${rby+12}`,
        fill: 'white', 'pointer-events': 'none'
      });
      canvas.appendChild(arrow);
    }
  }

  // ── Shared helper: draw expand/collapse children button below a node ─────
  function _drawChildrenBtn(canvas, nx, ny, xref) {
    const isExp = expandedChildrenOf.has(xref);
    const bx = nx + NODE_W / 2 - 8, by = ny + NODE_H + 4;
    const btn = svgEl('rect', {x: bx, y: by, width: 16, height: 16, rx: 4,
      fill: isExp ? '#475569' : '#059669', cursor: 'pointer'});
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (expandedChildrenOf.has(xref)) expandedChildrenOf.delete(xref);
      else expandedChildrenOf.add(xref);
      render();
    });
    canvas.appendChild(btn);
    canvas.appendChild(svgEl('polygon', {
      points: isExp
        ? `${bx+4},${by+11} ${bx+8},${by+5} ${bx+12},${by+11}`
        : `${bx+4},${by+5} ${bx+8},${by+11} ${bx+12},${by+5}`,
      fill: 'white', 'pointer-events': 'none'
    }));
  }

  // ── Relative nodes and connectors ────────────────────────────────────────
  function drawRelNode(rx, ry, xref, fill) {
    const nodeData = PEOPLE[xref] || {};
    const rg = svgEl('g', { cursor: 'pointer' });
    rg.addEventListener('click', (e) => {
      e.stopPropagation();
      console.log('[relNode click] xref=', xref, 'didDrag=', didDrag);
      if (!didDrag) showDetail(xref);
    });
    rg.appendChild(svgEl('rect', { x: rx, y: ry, width: NODE_W, height: NODE_H, rx: 8, fill, opacity: 0.85 }));
    const dname = (nodeData.name || '?');
    const displayName = dname.length > 21 ? dname.slice(0, 19) + '\u2026' : dname;
    const nt = svgEl('text', {
      x: rx + NODE_W / 2, y: ry + 22,
      'text-anchor': 'middle', fill: 'white', 'font-size': 13, 'font-weight': 600,
      'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
    });
    nt.textContent = displayName;
    rg.appendChild(nt);
    const yrs = [
      nodeData.birth_year && 'b.' + nodeData.birth_year,
      nodeData.death_year && 'd.' + nodeData.death_year
    ].filter(Boolean).join('  ');
    if (yrs) {
      const yt = svgEl('text', {
        x: rx + NODE_W / 2, y: ry + 42,
        'text-anchor': 'middle', fill: 'rgba(255,255,255,0.65)', 'font-size': 11,
        'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
      });
      yt.textContent = yrs;
      rg.appendChild(yt);
    }
    drawDiedYoungBadge(rg, rx, ry, nodeData.age_at_death);
    canvas.appendChild(rg);
  }

  for (const [key, entry] of _relPosCache.entries()) {
    if (entry.existing) continue;  // already rendered as an ancestor node
    if (key.startsWith('ch:') || key.startsWith('sibch:')) continue;  // drawn below
    const {x: rx, y: ry, xref} = entry;
    const isSibling = key.startsWith('sib:') && !key.startsWith('sibsp:');
    const fill = isSibling ? '#1e3a5f' : '#065f46';
    drawRelNode(rx, ry, xref, fill);
    // Expand-children button on siblings that have children
    if (isSibling && (CHILDREN[xref] || []).length > 0) {
      _drawChildrenBtn(canvas, rx, ry, xref);
    }
  }

  // ── Child node connectors helper ──────────────────────────────────────────
  // childEntries: [[key, {x, y, xref, stemX, stemY}], ...]
  // stemX/stemY are the start point of the vertical stem (spouse-line midpoint or node bottom-center).
  function _drawChildGroup(childEntries, fill) {
    if (!childEntries.length) return;
    const {stemX, stemY, y: childY} = childEntries[0][1];
    const barY = stemY + (childY - stemY) / 2;
    const childXs = childEntries.map(([, e]) => e.x + NODE_W / 2);
    canvas.insertBefore(svgEl('line', {
      x1: stemX, y1: stemY, x2: stemX, y2: barY,
      stroke: '#475569', 'stroke-width': 1.5
    }), canvas.firstChild);
    canvas.insertBefore(svgEl('line', {
      x1: Math.min(...childXs), y1: barY,
      x2: Math.max(...childXs), y2: barY,
      stroke: '#475569', 'stroke-width': 1.5
    }), canvas.firstChild);
    for (const [, e] of childEntries) {
      canvas.insertBefore(svgEl('line', {
        x1: e.x + NODE_W / 2, y1: barY,
        x2: e.x + NODE_W / 2, y2: e.y,
        stroke: '#475569', 'stroke-width': 1.5
      }), canvas.firstChild);
      drawRelNode(e.x, e.y, e.xref, fill);
    }
  }

  // Root children
  {
    const entries = [..._relPosCache.entries()].filter(([k]) => k.startsWith('ch:'));
    if (entries.length) _drawChildGroup(entries, '#155e75');
  }
  // Sibling children — group by sibling key prefix "sibch:k:i:"
  {
    const sibChEntries = [..._relPosCache.entries()].filter(([k]) => k.startsWith('sibch:'));
    const byParent = new Map();
    for (const [k, e] of sibChEntries) {
      const parentKey = k.split(':').slice(0, 3).join(':').replace('sibch', 'sib');
      if (!byParent.has(parentKey)) byParent.set(parentKey, []);
      byParent.get(parentKey).push([k, e]);
    }
    for (const [parentKey, children] of byParent.entries()) {
      const sibEntry = _relPosCache.get(parentKey);
      if (!sibEntry || sibEntry.existing) continue;
      _drawChildGroup(children, '#155e75');
    }
  }

  applyTransform();
}
