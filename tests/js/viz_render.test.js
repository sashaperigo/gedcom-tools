import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// ── Minimal SVG DOM mock ───────────────────────────────────────────────────
//
// Vitest runs in 'node' environment (no jsdom). We build just enough DOM
// primitives to exercise viz_render.js without a browser.

class MockElement {
  constructor(ns, tag) {
    this.ns = ns;
    this.tagName = tag;
    this.children = [];
    this._attrs = {};
    this._listeners = {};
    this.style = {};
    this.textContent = '';
  }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return this._attrs[k] ?? null; }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(type, fn) {
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(fn);
  }
  // Fire a synthetic event
  dispatchEvent(type, eventObj = {}) {
    const defaultEvent = { stopPropagation: () => {}, ...eventObj };
    (this._listeners[type] || []).forEach(fn => fn(defaultEvent));
  }
  // Depth-first search for all elements matching a selector.
  // Supports: 'tag', '#id', '.class', 'tag[attr]', 'tag[attr=value]'
  querySelectorAll(selector) {
    const results = [];
    const visit = (el) => {
      if (_matchesSelector(el, selector)) results.push(el);
      el.children.forEach(visit);
    };
    this.children.forEach(visit);
    return results;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
  get innerHTML() { return ''; }
  set innerHTML(v) { if (v === '') this.children = []; }
}

function _matchesSelector(el, selector) {
  // #id
  if (selector.startsWith('#')) return el._attrs['id'] === selector.slice(1);
  // .class
  if (selector.startsWith('.')) return (el._attrs['class'] || '').split(' ').includes(selector.slice(1));
  // tag[attr] or tag[attr=value]
  const attrMatch = selector.match(/^([a-zA-Z]+)\[([a-zA-Z_-]+)(?:=["']?([^"'\]]+)["']?)?\]$/);
  if (attrMatch) {
    const [, tag, attr, val] = attrMatch;
    if (el.tagName !== tag) return false;
    if (val === undefined) return el._attrs[attr] !== undefined;
    return el._attrs[attr] === val;
  }
  // plain tag name
  return el.tagName === selector;
}

// Build a mock <svg> element that also has an SVG-like id attribute
function makeSvgEl() {
  const svg = new MockElement('http://www.w3.org/2000/svg', 'svg');
  svg._attrs['id'] = 'tree-svg';
  svg._attrs['width'] = '800';
  svg._attrs['height'] = '600';
  svg.getBoundingClientRect = () => ({ width: 800, height: 600, left: 0, top: 0 });
  return svg;
}

// ── Global setup ───────────────────────────────────────────────────────────

const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;

const { NODE_W, NODE_W_FOCUS, NODE_H, NODE_H_FOCUS } = DESIGN;

// Set up a minimal document mock so createElementNS works
global.document = {
  createElementNS: (ns, tag) => new MockElement(ns, tag),
  addEventListener: () => {},
};

// Stub globals that viz_state.js needs
global.location = { search: '' };
global.history = { pushState: vi.fn(), replaceState: vi.fn() };
global.addEventListener = () => {};

// Load state module
const stateMod = require('../../js/viz_state.js');
global.setState    = stateMod.setState;
global.getState    = stateMod.getState;
global.onStateChange = stateMod.onStateChange;

// Load layout module
const { computeLayout } = require('../../js/viz_layout.js');
global.computeLayout = computeLayout;

// ── Helpers ────────────────────────────────────────────────────────────────

function makeMinimalPeople() {
  return {
    '@FOCUS@':  { name: 'Focus Person', birth_year: 1900, death_year: 1980 },
    '@FATHER@': { name: 'Father Person', birth_year: 1870, death_year: 1940 },
    '@MOTHER@': { name: 'Mother Person', birth_year: 1872, death_year: 1945 },
    '@CHILD@':  { name: 'Child Person', birth_year: 1925, death_year: null },
    '@SPOUSE@': { name: 'Spouse Person', birth_year: 1902, death_year: 1970 },
    '@SIBLING@':{ name: 'Sibling Person', birth_year: 1897, death_year: 1960 },
  };
}

function resetState() {
  stateMod.initState('@FOCUS@');
}

// Load the render module once — it reads globals at call-time, not module load time
let renderMod;

function loadRenderMod() {
  // Bust module cache so we get fresh state bindings
  const modPath = require.resolve('../../js/viz_render.js');
  delete require.cache[modPath];
  // Also bust layout and state caches so globals are picked up fresh
  const layoutPath = require.resolve('../../js/viz_layout.js');
  delete require.cache[layoutPath];
  renderMod = require('../../js/viz_render.js');
  return renderMod;
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('initRenderer', () => {
  beforeEach(() => {
    global.PEOPLE = makeMinimalPeople();
    global.PARENTS   = { '@FOCUS@': ['@FATHER@', '@MOTHER@'] };
    global.CHILDREN  = { '@FOCUS@': ['@CHILD@'] };
    global.RELATIVES = { '@FOCUS@': { siblings: ['@SIBLING@'], spouses: ['@SPOUSE@'] } };
    resetState();
    loadRenderMod();
  });

  it('creates a <g id="tree-root"> inside the SVG', () => {
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    expect(treeRoot).not.toBeNull();
    expect(treeRoot.tagName).toBe('g');
    expect(treeRoot._attrs['id']).toBe('tree-root');
  });

  it('tree-root has an initial translate transform centering focus at (svgW/2, svgH/2)', () => {
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const transform = treeRoot._attrs['transform'] || '';
    // Should contain translate with roughly half the svg dimensions
    expect(transform).toMatch(/translate\(/);
    // Extract numbers
    const match = transform.match(/translate\(\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*\)/);
    expect(match).not.toBeNull();
    const tx = parseFloat(match[1]);
    const ty = parseFloat(match[2]);
    expect(tx).toBeCloseTo(400, 0); // svgWidth / 2 = 800 / 2
    expect(ty).toBeCloseTo(300, 0); // svgHeight / 2 = 600 / 2
  });
});

describe('render — node presence', () => {
  let svg;

  beforeEach(() => {
    global.PEOPLE = makeMinimalPeople();
    global.PARENTS   = { '@FOCUS@': ['@FATHER@', '@MOTHER@'] };
    global.CHILDREN  = { '@FOCUS@': ['@CHILD@'] };
    global.RELATIVES = { '@FOCUS@': { siblings: ['@SIBLING@'], spouses: ['@SPOUSE@'] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    renderMod.initRenderer(svg);
  });

  it('each node in layout has a corresponding <g> element with data-xref attribute', () => {
    const { computeLayout } = require('../../js/viz_layout.js');
    const state = stateMod.getState();
    const { nodes } = computeLayout(state.focusXref, state.expandedNodes || new Set(), new Set());

    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const renderedXrefs = new Set(nodeGs.map(g => g._attrs['data-xref']));

    for (const node of nodes) {
      expect(renderedXrefs.has(node.xref)).toBe(true);
    }
  });

  it('each node <g> has a translate transform matching layout position', () => {
    const { computeLayout } = require('../../js/viz_layout.js');
    const state = stateMod.getState();
    const { nodes } = computeLayout(state.focusXref, state.expandedNodes || new Set(), new Set());

    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const byXref = new Map(nodeGs.map(g => [g._attrs['data-xref'], g]));

    for (const node of nodes) {
      const g = byXref.get(node.xref);
      expect(g).toBeDefined();
      const transform = g._attrs['transform'] || '';
      expect(transform).toMatch(/translate\(/);
      const match = transform.match(/translate\(\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*\)/);
      expect(match).not.toBeNull();
      expect(parseFloat(match[1])).toBeCloseTo(node.x, 1);
      expect(parseFloat(match[2])).toBeCloseTo(node.y, 1);
    }
  });
});

describe('render — focused node styles', () => {
  let svg;

  beforeEach(() => {
    global.PEOPLE = makeMinimalPeople();
    global.PARENTS   = {};
    global.CHILDREN  = {};
    global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: [] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    renderMod.initRenderer(svg);
  });

  it('focused node rect uses BG_NODE_FOCUS fill', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    expect(focusG).toBeDefined();
    const rect = focusG.children.find(c => c.tagName === 'rect');
    expect(rect._attrs['fill']).toBe(DESIGN.BG_NODE_FOCUS);
  });

  it('focused node rect uses BORDER_FOCUS stroke', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const rect = focusG.children.find(c => c.tagName === 'rect');
    expect(rect._attrs['stroke']).toBe(DESIGN.BORDER_FOCUS);
  });

  it('focused node rect uses NODE_W_FOCUS width', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const rect = focusG.children.find(c => c.tagName === 'rect');
    expect(parseFloat(rect._attrs['width'])).toBe(NODE_W_FOCUS);
  });

  it('focused node rect uses NODE_H_FOCUS height', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const rect = focusG.children.find(c => c.tagName === 'rect');
    expect(parseFloat(rect._attrs['height'])).toBe(NODE_H_FOCUS);
  });
});

describe('render — spouse node styles', () => {
  let svg;

  beforeEach(() => {
    global.PEOPLE = makeMinimalPeople();
    global.PARENTS   = {};
    global.CHILDREN  = {};
    global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    renderMod.initRenderer(svg);
  });

  it('spouse node rect uses ACCENT_SPOUSE stroke', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const spouseG = nodeGs.find(g => g._attrs['data-xref'] === '@SPOUSE@');
    expect(spouseG).toBeDefined();
    const rect = spouseG.children.find(c => c.tagName === 'rect');
    expect(rect._attrs['stroke']).toBe(DESIGN.ACCENT_SPOUSE);
  });

  it('spouse node uses normal width (NODE_W)', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const spouseG = nodeGs.find(g => g._attrs['data-xref'] === '@SPOUSE@');
    const rect = spouseG.children.find(c => c.tagName === 'rect');
    expect(parseFloat(rect._attrs['width'])).toBe(NODE_W);
  });
});

describe('render — node pill text spacing', () => {
  // The years line must sit far enough below the name center that the two
  // elements don't visually overlap.  Minimum clearance: the years text y
  // must be at least (nameY + 8) where nameY is the name's y attribute.
  // This ensures at least 8px of gap (name half-height ≈ 6px + 2px padding).
  let svg;

  beforeEach(() => {
    global.PEOPLE = makeMinimalPeople();
    global.PARENTS   = { '@FOCUS@': ['@FATHER@', '@MOTHER@'] };
    global.CHILDREN  = {};
    global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: [] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    renderMod.initRenderer(svg);
  });

  it('years text y is at least 8px below name text y on a normal ancestor node', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    expect(fatherG).toBeDefined();
    const texts = fatherG.children.filter(c => c.tagName === 'text');
    // First text = name, second text = years
    expect(texts.length).toBeGreaterThanOrEqual(2);
    const nameY  = parseFloat(texts[0]._attrs['y']);
    const yearsY = parseFloat(texts[1]._attrs['y']);
    expect(yearsY).toBeGreaterThanOrEqual(nameY + 8);
  });

  it('years text y is at least 8px below name text y on the focused node', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    expect(focusG).toBeDefined();
    const texts = focusG.children.filter(c => c.tagName === 'text');
    expect(texts.length).toBeGreaterThanOrEqual(2);
    const nameY  = parseFloat(texts[0]._attrs['y']);
    const yearsY = parseFloat(texts[1]._attrs['y']);
    expect(yearsY).toBeGreaterThanOrEqual(nameY + 8);
  });

  it('NODE_H and NODE_H_FOCUS are tall enough to contain name + years without cramping', () => {
    // With font-size 11 for name (≈7px rendered height) and 9 for years,
    // we need at least 28px total node height to avoid cramping.
    expect(NODE_H).toBeGreaterThanOrEqual(38);
    expect(NODE_H_FOCUS).toBeGreaterThanOrEqual(42);
  });
});

describe('render — ancestor expand buttons', () => {
  let svg;

  beforeEach(() => {
    // @FATHER@ needs his own parents so the expand button renders (grey
    // chevrons are hidden for ancestors without parents).
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    global.CHILDREN  = {};
    global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: [] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    renderMod.initRenderer(svg);
  });

  it('ancestor nodes have a <circle> with class expand-btn', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    expect(fatherG).toBeDefined();
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn).toBeDefined();
  });

  it('expand button floats above node top edge with a gap (cy < 0, bottom of circle < 0)', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    // The <g data-xref> is translated to node.x, node.y. The button floats
    // above y=0 (pill top) with a visible gap: center + radius must be < 0.
    const cy = parseFloat(expandBtn._attrs['cy']);
    const r = parseFloat(expandBtn._attrs['r']);
    expect(cy + r).toBeLessThan(0);
  });

  it('focus node does NOT have an expand button', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const expandBtn = focusG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn).toBeUndefined();
  });

  it('sibling node does NOT have an expand button', () => {
    global.RELATIVES = { '@FOCUS@': { siblings: ['@SIBLING@'], spouses: [] } };
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const treeRoot = svg2.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const sibG = nodeGs.find(g => g._attrs['data-xref'] === '@SIBLING@');
    if (!sibG) return; // sibling not present in this layout — pass vacuously
    const expandBtn = sibG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn).toBeUndefined();
  });

  it('expand button uses a <path> chevron, not a <text> "+"', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    const textPlus = fatherG.children.find(
      c => c.tagName === 'text' && c.textContent === '+'
    );
    expect(textPlus).toBeUndefined();
    const chevronPath = fatherG.children.find(c => c.tagName === 'path');
    expect(chevronPath).toBeDefined();
  });

  it('expand button circle is green when ancestor has parents and is not expanded', () => {
    // @FATHER@ needs his own parents so his button shows green
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const treeRoot = svg2.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn._attrs['fill']).toBe('#2a7a4a');
  });

  it('expand button circle is blue when ancestor is already expanded (can collapse)', () => {
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    stateMod.setState({ expandedNodes: new Set(['@FATHER@']) });
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const treeRoot = svg2.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn._attrs['fill']).toBe('#2a5a7a');
  });

  it('expanded ancestor shows a down-chevron path', () => {
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    stateMod.setState({ expandedNodes: new Set(['@FATHER@']) });
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const fatherG = svg2.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const d = fatherG.children.find(c => c.tagName === 'path')._attrs['d'];
    // Down-chevron: middle point has a LARGER y than the two end points
    // (SVG y increases downward, so a down-chevron points down to a larger-y apex).
    const matches = d.match(/M\s+([-\d.]+)\s+([-\d.]+)\s+L\s+([-\d.]+)\s+([-\d.]+)\s+L\s+([-\d.]+)\s+([-\d.]+)/);
    expect(matches).not.toBeNull();
    const y1 = parseFloat(matches[2]);
    const ym = parseFloat(matches[4]);
    const y2 = parseFloat(matches[6]);
    expect(ym).toBeGreaterThan(y1);
    expect(ym).toBeGreaterThan(y2);
  });

  it('unexpanded ancestor with parents shows an up-chevron path', () => {
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const fatherG = svg2.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const d = fatherG.children.find(c => c.tagName === 'path')._attrs['d'];
    const matches = d.match(/M\s+([-\d.]+)\s+([-\d.]+)\s+L\s+([-\d.]+)\s+([-\d.]+)\s+L\s+([-\d.]+)\s+([-\d.]+)/);
    expect(matches).not.toBeNull();
    const y1 = parseFloat(matches[2]);
    const ym = parseFloat(matches[4]);
    const y2 = parseFloat(matches[6]);
    // Up-chevron apex is at a smaller y (higher on screen).
    expect(ym).toBeLessThan(y1);
    expect(ym).toBeLessThan(y2);
  });

  it('expand button is NOT rendered when ancestor has no parents', () => {
    // Override beforeEach: remove @FATHER@'s parents.
    global.PEOPLE  = makeMinimalPeople();
    global.PARENTS = { '@FOCUS@': ['@FATHER@', '@MOTHER@'] };
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const fatherG = svg2.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn).toBeUndefined();
  });

  it('up-chevron path when can expand, down-chevron path when expanded', () => {
    // Set up @FATHER@ with parents so he can expand
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    loadRenderMod();
    const svgUp = makeSvgEl();
    renderMod.initRenderer(svgUp);
    const fatherGUp = svgUp.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const upD = fatherGUp.children.find(c => c.tagName === 'path')._attrs['d'];

    stateMod.setState({ expandedNodes: new Set(['@FATHER@']) });
    loadRenderMod();
    const svgDown = makeSvgEl();
    renderMod.initRenderer(svgDown);
    const fatherGDown = svgDown.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const downD = fatherGDown.children.find(c => c.tagName === 'path')._attrs['d'];

    expect(upD).not.toBe(downD);
  });
});

describe('render — click handlers', () => {
  let svg;
  let setStateSpy;

  beforeEach(() => {
    global.PEOPLE = makeMinimalPeople();
    global.PARENTS   = { '@FOCUS@': ['@FATHER@', '@MOTHER@'] };
    global.CHILDREN  = {};
    global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: [] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    // Spy before initRenderer so the initial render() call goes through the spy
    setStateSpy = vi.fn();
    global.setState = setStateSpy;
    renderMod.initRenderer(svg);
  });

  it('clicking a non-focus node opens panel without changing focusXref', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    expect(fatherG).toBeDefined();

    fatherG.dispatchEvent('click', { stopPropagation: () => {} });

    const calls = setStateSpy.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const lastCall = calls[calls.length - 1][0];
    expect(lastCall.panelOpen).toBe(true);
    expect(lastCall.panelXref).toBe('@FATHER@');
    expect('focusXref' in lastCall).toBe(false);
  });

  it('clicking the focus node calls setState with panelOpen but does NOT change focusXref', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    expect(focusG).toBeDefined();

    focusG.dispatchEvent('click', { stopPropagation: () => {} });

    const calls = setStateSpy.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const lastCall = calls[calls.length - 1][0];
    // Should open panel
    expect(lastCall.panelOpen).toBe(true);
    expect(lastCall.panelXref).toBe('@FOCUS@');
    // Should NOT include focusXref key
    expect('focusXref' in lastCall).toBe(false);
  });
});

describe('render — expand button click handler', () => {
  let svg;
  let setStateSpy;

  beforeEach(() => {
    // @FATHER@ has his own parents so the expand button is active (green).
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    global.CHILDREN  = {};
    global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: [] } };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    // Spy before initRenderer so the initial render() call goes through the spy
    setStateSpy = vi.fn();
    global.setState = setStateSpy;
    renderMod.initRenderer(svg);
  });

  it('no expand button is rendered on an ancestor without parents', () => {
    // Separate render where @FATHER@ has no parents.
    global.PEOPLE  = makeMinimalPeople();
    global.PARENTS = { '@FOCUS@': ['@FATHER@', '@MOTHER@'] };
    loadRenderMod();
    const svg2 = makeSvgEl();
    const spy = vi.fn();
    global.setState = spy;
    renderMod.initRenderer(svg2);

    const fatherG = svg2.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn).toBeUndefined();
  });

  it('clicking an expand button adds the xref to expandedAncestors in state', () => {
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const fatherG = nodeGs.find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expect(expandBtn).toBeDefined();

    expandBtn.dispatchEvent('click', { stopPropagation: () => {} });

    expect(setStateSpy).toHaveBeenCalled();
    const calls = setStateSpy.mock.calls;
    const expandCall = calls.find(([update]) => update.expandedNodes !== undefined);
    expect(expandCall).toBeDefined();
    const newSet = expandCall[0].expandedNodes;
    expect(newSet instanceof Set).toBe(true);
    expect(newSet.has('@FATHER@')).toBe(true);
  });

  it('clicking an already-expanded ancestor removes it from expandedNodes (toggle)', () => {
    // Re-seed with @FATHER@ already expanded so his button is the blue down-chevron.
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@PGF@': { name: 'Pat Grandfather', birth_year: 1840, death_year: 1910 },
      '@PGM@': { name: 'Pat Grandmother', birth_year: 1842, death_year: 1915 },
    };
    global.PARENTS = {
      '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      '@FATHER@': ['@PGF@', '@PGM@'],
    };
    stateMod.setState({ expandedNodes: new Set(['@FATHER@']) });
    loadRenderMod();
    const svg2 = makeSvgEl();
    setStateSpy = vi.fn();
    global.setState = setStateSpy;
    renderMod.initRenderer(svg2);

    const fatherG = svg2.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(g => g._attrs['data-xref'] === '@FATHER@');
    const expandBtn = fatherG.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('expand-btn')
    );
    expandBtn.dispatchEvent('click', { stopPropagation: () => {} });

    const calls = setStateSpy.mock.calls;
    const toggleCall = calls.find(([update]) => update.expandedNodes !== undefined);
    expect(toggleCall).toBeDefined();
    const newSet = toggleCall[0].expandedNodes;
    expect(newSet instanceof Set).toBe(true);
    expect(newSet.has('@FATHER@')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// D2  Died-young badge — stillborn / infant / child styling
// ---------------------------------------------------------------------------
//
// Nodes whose person died young (stillborn, infant within ~1 year, or child
// within ~13 years) must receive an amber badge drawn on the node group.
// The old viz_render.js used data.age_at_death values 'STILLBORN', 'INFANT',
// 'CHILD' supplied by the Python build_people_json.  The new renderer must
// read the same field from PEOPLE[node.xref].age_at_death.

describe('render — died-young badge', () => {
  function makeSetupWithAgeAtDeath(ageAtDeath) {
    return function setup() {
      global.PEOPLE = {
        '@FOCUS@': { name: 'Focus Person', birth_year: 1900, death_year: 1900, age_at_death: ageAtDeath },
      };
      global.PARENTS   = {};
      global.CHILDREN  = {};
      global.RELATIVES = { '@FOCUS@': { siblings: [], spouses: [] } };
      stateMod.initState('@FOCUS@');
      loadRenderMod();
    };
  }

  it('stillborn node (birth_year === death_year, age_at_death = STILLBORN) gets amber badge circle', () => {
    makeSetupWithAgeAtDeath('STILLBORN')();
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    expect(focusG).toBeDefined();
    // Badge is an amber circle appended to the node group
    const badgeCircle = focusG.children.find(c => c.tagName === 'circle' && c._attrs['fill'] === '#fbbf24');
    expect(badgeCircle).toBeDefined();
  });

  it('infant node (age_at_death = INFANT) gets amber badge circle', () => {
    makeSetupWithAgeAtDeath('INFANT')();
    global.PEOPLE['@FOCUS@'].death_year = 1901; // died within ~1 year
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const badgeCircle = focusG.children.find(c => c.tagName === 'circle' && c._attrs['fill'] === '#fbbf24');
    expect(badgeCircle).toBeDefined();
  });

  it('child node (age_at_death = CHILD) gets amber badge circle', () => {
    makeSetupWithAgeAtDeath('CHILD')();
    global.PEOPLE['@FOCUS@'].death_year = 1912;
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const badgeCircle = focusG.children.find(c => c.tagName === 'circle' && c._attrs['fill'] === '#fbbf24');
    expect(badgeCircle).toBeDefined();
  });

  it('adult node (no age_at_death) does NOT get amber badge circle', () => {
    makeSetupWithAgeAtDeath(undefined)();
    global.PEOPLE['@FOCUS@'].birth_year = 1900;
    global.PEOPLE['@FOCUS@'].death_year = 1970;
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const nodeGs = treeRoot.querySelectorAll('g[data-xref]');
    const focusG = nodeGs.find(g => g._attrs['data-xref'] === '@FOCUS@');
    const badgeCircle = focusG.children.find(c => c.tagName === 'circle' && c._attrs['fill'] === '#fbbf24');
    expect(badgeCircle).toBeUndefined();
  });
});

describe('render — descendant umbrella edges', () => {
  beforeEach(() => {
    global.PEOPLE = {
      ...makeMinimalPeople(),
      '@C1@':   { name: 'Child One', birth_year: 1925, death_year: null },
      '@C1SP@': { name: 'Child One Spouse', birth_year: 1927, death_year: null },
    };
    global.PARENTS   = {};
    global.CHILDREN  = { '@FOCUS@': ['@C1@'] };
    global.RELATIVES = {
      '@FOCUS@': { siblings: [], spouses: [] },
      '@C1@':   { siblings: [], spouses: ['@C1SP@'] },
    };
    resetState();
    loadRenderMod();
  });

  it('renders umbrella drop/crossbar/child-drop as <line> elements with descendant stroke', () => {
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const lines = treeRoot.querySelectorAll('line');
    const descLines = lines.filter(l => l._attrs['stroke'] === '#2c2c54');
    // At minimum: anchor drop + per-child drop (single child, no crossbar)
    expect(descLines.length).toBeGreaterThanOrEqual(2);
  });

  it('renders the child-spouse marriage line with the marriage stroke color', () => {
    const svg = makeSvgEl();
    renderMod.initRenderer(svg);
    const treeRoot = svg.querySelector('#tree-root');
    const lines = treeRoot.querySelectorAll('line');
    const marriageLines = lines.filter(l => l._attrs['stroke'] === '#3a6a3a');
    // Expect at least one marriage edge (between @C1@ and @C1SP@) in descendant row
    const expectedY = String(DESIGN.ROW_HEIGHT + DESIGN.NODE_H / 2);
    const childRowMarriage = marriageLines.find(l =>
      l._attrs['y1'] === expectedY && l._attrs['y2'] === expectedY
    );
    expect(childRowMarriage).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Ancestor sibling expand chevron
// ---------------------------------------------------------------------------
//
// Each ancestor pill gets an outward-facing horizontal chevron on its short
// edge (male → left, female → right). Tri-state:
//   hasSiblings && !isExpanded → green, points outward  (click to expand)
//   hasSiblings &&  isExpanded → blue,  points inward   (click to collapse)
//   !hasSiblings              → chevron NOT rendered
// Clicking an expand adds the xref to BOTH expandedSiblingsXrefs AND
// expandedNodes (auto-expand parents).

describe('render — ancestor sibling chevron', () => {
  let svg;

  beforeEach(() => {
    global.PEOPLE = {
      '@FOCUS@':  { name: 'Focus',  birth_year: 2000, sex: 'M' },
      '@FATHER@': { name: 'Father', birth_year: 1970, sex: 'M' },
      '@MOTHER@': { name: 'Mother', birth_year: 1972, sex: 'F' },
      '@F_SIB@':  { name: 'F-Sib',  birth_year: 1968, sex: 'M' },
      '@M_SIB@':  { name: 'M-Sib',  birth_year: 1974, sex: 'F' },
    };
    global.PARENTS = {
      '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
      '@FATHER@': [null, null],
      '@MOTHER@': [null, null],
    };
    global.CHILDREN = {};
    global.RELATIVES = {
      '@FOCUS@':  { siblings: [], spouses: [] },
      '@FATHER@': { siblings: ['@F_SIB@'], spouses: [] },
      '@MOTHER@': { siblings: ['@M_SIB@'], spouses: [] },
    };
    resetState();
    loadRenderMod();
    svg = makeSvgEl();
    renderMod.initRenderer(svg);
  });

  function getSibBtn(xref, svgEl = svg) {
    const g = svgEl.querySelector('#tree-root')
      .querySelectorAll('g[data-xref]')
      .find(gr => gr._attrs['data-xref'] === xref);
    return g && g.children.find(
      c => c.tagName === 'circle' && (c._attrs['class'] || '').includes('sibling-expand-btn')
    );
  }

  it('ancestor with siblings has a <circle class="sibling-expand-btn">', () => {
    const btn = getSibBtn('@MOTHER@');
    expect(btn).toBeDefined();
  });

  it('ancestor with no siblings does NOT render a sibling chevron', () => {
    global.RELATIVES = {
      '@FOCUS@':  { siblings: [], spouses: [] },
      '@FATHER@': { siblings: [], spouses: [] },
      '@MOTHER@': { siblings: [], spouses: [] },
    };
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const btn = getSibBtn('@MOTHER@', svg2);
    expect(btn).toBeUndefined();
  });

  it('ancestor with siblings, not expanded → green fill', () => {
    const btn = getSibBtn('@MOTHER@');
    expect(btn._attrs['fill']).toBe('#2a7a4a');
  });

  it('ancestor with siblings, already expanded → blue fill', () => {
    stateMod.setState({ expandedSiblingsXrefs: new Set(['@MOTHER@']) });
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const btn = getSibBtn('@MOTHER@', svg2);
    expect(btn._attrs['fill']).toBe('#2a5a7a');
  });

  it('female ancestor sibling chevron sits to the right of the pill', () => {
    const btn = getSibBtn('@MOTHER@');
    const cx = parseFloat(btn._attrs['cx']);
    // g is translated to node.x,node.y; the button's cx is relative to that
    // group. Right-side chevron: cx must be > NODE_W.
    expect(cx).toBeGreaterThan(NODE_W);
  });

  it('male ancestor sibling chevron sits to the left of the pill', () => {
    const btn = getSibBtn('@FATHER@');
    const cx = parseFloat(btn._attrs['cx']);
    // Left-side chevron: cx must be < 0.
    expect(cx).toBeLessThan(0);
  });

  it('focus node does NOT get a sibling chevron', () => {
    expect(getSibBtn('@FOCUS@')).toBeUndefined();
  });

  it('clicking a green chevron adds xref to BOTH expandedSiblingsXrefs AND expandedNodes', () => {
    const spy = vi.fn();
    global.setState = spy;
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const btn = getSibBtn('@MOTHER@', svg2);
    spy.mockClear();
    btn.dispatchEvent('click', { stopPropagation: () => {} });

    expect(spy).toHaveBeenCalled();
    const call = spy.mock.calls.find(([u]) => u && u.expandedSiblingsXrefs !== undefined);
    expect(call).toBeDefined();
    const update = call[0];
    expect(update.expandedSiblingsXrefs instanceof Set).toBe(true);
    expect(update.expandedSiblingsXrefs.has('@MOTHER@')).toBe(true);
    expect(update.expandedNodes instanceof Set).toBe(true);
    expect(update.expandedNodes.has('@MOTHER@')).toBe(true);
  });

  it('clicking a blue chevron removes xref from expandedSiblingsXrefs only', () => {
    stateMod.setState({ expandedSiblingsXrefs: new Set(['@MOTHER@']), expandedNodes: new Set(['@MOTHER@']) });
    const spy = vi.fn();
    global.setState = spy;
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    const btn = getSibBtn('@MOTHER@', svg2);
    spy.mockClear();
    btn.dispatchEvent('click', { stopPropagation: () => {} });

    const call = spy.mock.calls.find(([u]) => u && u.expandedSiblingsXrefs !== undefined);
    expect(call).toBeDefined();
    const update = call[0];
    expect(update.expandedSiblingsXrefs.has('@MOTHER@')).toBe(false);
    // expandedNodes should NOT be touched on collapse.
    expect('expandedNodes' in update).toBe(false);
  });

  it('no sibling chevron is rendered when ancestor has zero siblings', () => {
    global.RELATIVES = {
      '@FOCUS@':  { siblings: [], spouses: [] },
      '@FATHER@': { siblings: [], spouses: [] },
      '@MOTHER@': { siblings: [], spouses: [] },
    };
    loadRenderMod();
    const svg2 = makeSvgEl();
    renderMod.initRenderer(svg2);
    expect(getSibBtn('@MOTHER@', svg2)).toBeUndefined();
    expect(getSibBtn('@FATHER@', svg2)).toBeUndefined();
  });
});
