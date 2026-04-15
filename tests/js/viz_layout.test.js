import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// ── Constants ──────────────────────────────────────────────────────────────
const C = require('../../js/viz_constants.js');
const { NODE_W, NODE_H, H_GAP, V_GAP, BTN_PAD, MARGIN_X, MARGIN_TOP, BTN_ZONE } = C;

// Inject constants as globals so viz_layout.js can read them
Object.assign(global, C);

// ── Layout functions ───────────────────────────────────────────────────────
const {
  genOf, slotOf, isMaleKey,
  _buildSibSlots, _subtreeWidth,
  computePositions, computeRelativePositions,
  hasHiddenParents, hasVisibleParents,
  maxVisibleGen, nodePos,
} = require('../../js/viz_layout.js');

// ── Helpers ────────────────────────────────────────────────────────────────

/** Build a minimal tree with root + n ancestor generations fully populated. */
function fullTree(gens) {
  const tree = {};
  for (let g = 0; g <= gens; g++) {
    const start = Math.pow(2, g), end = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) tree[k] = `xref${k}`;
  }
  return tree;
}

function resetGlobals(opts = {}) {
  global.currentTree        = opts.tree        ?? { 1: 'root' };
  global.visibleKeys        = opts.visible      ?? new Set([1]);
  global.expandedRelatives  = opts.expanded     ?? new Set([1]);
  global.expandedChildrenOf = opts.expandedCh   ?? new Set();
  global.PEOPLE             = opts.people       ?? {};
  global.RELATIVES          = opts.relatives    ?? {};
  global.CHILDREN           = opts.children     ?? {};
  global._posCache          = new Map();
  global._relPosCache       = new Map();
  global._sibSlots          = new Map();
  global._sibSpouseIdx      = new Map();
}

const SLOT = NODE_W + H_GAP;

// ── genOf / slotOf ─────────────────────────────────────────────────────────

describe('genOf / slotOf', () => {
  it('root (key=1) is gen 0 slot 0', () => {
    expect(genOf(1)).toBe(0);
    expect(slotOf(1)).toBe(0);
  });
  it('keys 2,3 are gen 1', () => {
    expect(genOf(2)).toBe(1);
    expect(genOf(3)).toBe(1);
  });
  it('slot increases left-to-right within a generation', () => {
    expect(slotOf(4)).toBe(0);
    expect(slotOf(5)).toBe(1);
    expect(slotOf(6)).toBe(2);
    expect(slotOf(7)).toBe(3);
  });
});

// ── isMaleKey ─────────────────────────────────────────────────────────────

describe('isMaleKey', () => {
  it('even keys > 1 are male', () => {
    resetGlobals();
    expect(isMaleKey(2)).toBe(true);
    expect(isMaleKey(4)).toBe(true);
    expect(isMaleKey(6)).toBe(true);
  });
  it('odd keys > 1 are female', () => {
    resetGlobals();
    expect(isMaleKey(3)).toBe(false);
    expect(isMaleKey(5)).toBe(false);
  });
  it('key=1 uses GEDCOM sex field (M)', () => {
    resetGlobals({ tree: { 1: 'root' }, people: { root: { sex: 'M' } } });
    expect(isMaleKey(1)).toBe(true);
  });
  it('key=1 uses GEDCOM sex field (F)', () => {
    resetGlobals({ tree: { 1: 'root' }, people: { root: { sex: 'F' } } });
    expect(isMaleKey(1)).toBe(false);
  });
});

// ── _subtreeWidth ──────────────────────────────────────────────────────────

describe('_subtreeWidth', () => {
  beforeEach(() => resetGlobals());

  it('leaf node (no visible parents) = 1', () => {
    global.visibleKeys = new Set([1]);
    const cache = new Map();
    expect(_subtreeWidth(1, cache)).toBe(1);
  });

  it('root + father only = 1 (father IS the one slot)', () => {
    // Width represents ancestor slots; a single parent with no further ancestors
    // still only takes 1 slot — the root is centered above it.
    global.visibleKeys = new Set([1, 2]);
    const cache = new Map();
    expect(_subtreeWidth(1, cache)).toBe(1);
  });

  it('root + mother only = 1', () => {
    global.visibleKeys = new Set([1, 3]);
    const cache = new Map();
    expect(_subtreeWidth(1, cache)).toBe(1);
  });

  it('root + both parents, no grandparents = 2', () => {
    global.visibleKeys = new Set([1, 2, 3]);
    const cache = new Map();
    // Each parent takes 1 slot, no gap (neither has visible ancestors) → total 2
    expect(_subtreeWidth(1, cache)).toBe(2);
  });

  it('root + both parents + all 4 grandparents gets gap slot', () => {
    global.visibleKeys = new Set([1, 2, 3, 4, 5, 6, 7]);
    global.currentTree = fullTree(2);
    const cache = new Map();
    const w = _subtreeWidth(1, cache);
    // Father subtree: 2 grandparents → width 2
    // Mother subtree: 2 grandparents → width 2
    // Both have ancestors → +1 gap = 5
    expect(w).toBe(5);
  });

  it('asymmetric: father has 2 ancestors, mother has none', () => {
    global.visibleKeys = new Set([1, 2, 3, 4, 5]);
    global.currentTree = { 1:'r', 2:'f', 3:'m', 4:'ff', 5:'fm' };
    const cache = new Map();
    // father subtree width = 2, mother = 1, no gap (mother has no ancestors)
    expect(_subtreeWidth(1, cache)).toBe(3);
  });

  it('caches results (second call returns same value without recursing)', () => {
    global.visibleKeys = new Set([1, 2, 3]);
    const cache = new Map();
    _subtreeWidth(1, cache);
    const cached = cache.get(1);
    _subtreeWidth(1, cache);   // should read from cache
    expect(cache.get(1)).toBe(cached);
  });
});

// ── computePositions ───────────────────────────────────────────────────────

describe('computePositions — single root', () => {
  beforeEach(() => {
    resetGlobals({
      tree: { 1: 'root' },
      visible: new Set([1]),
      people: { root: { sex: 'M' } },
    });
  });

  it('places root near MARGIN_X, MARGIN_TOP + BTN_ZONE', () => {
    // The layout centers the root within its 1-slot width:
    // x = MARGIN_X + (slotW - NODE_W)/2 = MARGIN_X + H_GAP/2
    computePositions();
    const pos = global._posCache.get(1);
    const SLOT = NODE_W + H_GAP;
    expect(pos.x).toBeCloseTo(MARGIN_X + (SLOT - NODE_W) / 2);
    expect(pos.y).toBeCloseTo(MARGIN_TOP + BTN_ZONE);
  });
});

describe('computePositions — generation spacing', () => {
  beforeEach(() => {
    resetGlobals({
      tree: fullTree(2),
      visible: new Set([1, 2, 3]),
      people: { xref1: { sex: 'M' } },
    });
  });

  it('each generation is exactly (NODE_H + V_GAP) above the next', () => {
    computePositions();
    const rootY   = global._posCache.get(1).y;
    const fatherY = global._posCache.get(2).y;
    expect(fatherY).toBeCloseTo(rootY - (NODE_H + V_GAP));
  });

  it('parents are above root (lower y value)', () => {
    computePositions();
    const rootY   = global._posCache.get(1).y;
    const fatherY = global._posCache.get(2).y;
    const motherY = global._posCache.get(3).y;
    expect(fatherY).toBeLessThan(rootY);
    expect(motherY).toBeLessThan(rootY);
  });

  it('father is to the left of mother', () => {
    computePositions();
    const fx = global._posCache.get(2).x;
    const mx = global._posCache.get(3).x;
    expect(fx).toBeLessThan(mx);
  });
});

describe('computePositions — couple compaction', () => {
  it('moves isolated father adjacent to mother when gap > slotW', () => {
    // Build a 4-gen tree where mother has 4 grandparents (pushing her far right)
    // but father has no ancestors at all.  The gap must exceed slotW to trigger.
    // Mother (key 3) → grandparents (6,7) → great-grandparents (12,13,14,15)
    const tree = {
      1:'root', 2:'f', 3:'m',
      6:'mm', 7:'mf',
      12:'mmm', 13:'mmf', 14:'mfm', 15:'mff',
    };
    resetGlobals({
      tree,
      visible: new Set([1, 2, 3, 6, 7, 12, 13, 14, 15]),
      people: { root: { sex: 'M' } },
    });
    computePositions();
    const fp = global._posCache.get(2);
    const mp = global._posCache.get(3);
    // After compaction, father is placed just to the left of mother: gap = H_GAP
    const gap = mp.x - (fp.x + NODE_W);
    expect(gap).toBeCloseTo(H_GAP);
  });
});

// ── computeRelativePositions — Pass 1 (root children) ─────────────────────

describe('computeRelativePositions — Pass 1: root children', () => {
  beforeEach(() => {
    resetGlobals({
      tree: { 1: 'root', 2: 'father', 3: 'mother' },
      visible: new Set([1, 2, 3]),
      people: {
        root:   { sex: 'M' },
        father: {},
        mother: {},
        ch0: {}, ch1: {}, ch2: {},
      },
      relatives: { root: { siblings: [], spouses: [], sib_spouses: {} } },
      children: { root: ['ch0', 'ch1', 'ch2'] },
      expandedCh: new Set(['root']),
    });
    computePositions();
  });

  it('places children below root', () => {
    computeRelativePositions();
    const rootY = global._posCache.get(1).y;
    for (let i = 0; i < 3; i++) {
      const ch = global._relPosCache.get(`ch:${i}`);
      expect(ch).toBeDefined();
      expect(ch.y).toBeGreaterThan(rootY);
    }
  });

  it('children are centered below the root–spouse couple midpoint', () => {
    // No spouse on root; stemX = root center
    computeRelativePositions();
    const rootPos = global._posCache.get(1);
    const stemX = rootPos.x + NODE_W / 2;
    const chXs = [0, 1, 2].map(i => global._relPosCache.get(`ch:${i}`).x + NODE_W / 2);
    const centerX = (Math.min(...chXs) + Math.max(...chXs)) / 2;
    expect(centerX).toBeCloseTo(stemX);
  });
});

// ── computeRelativePositions — Pass 3 (collision resolution) ───────────────

describe('computeRelativePositions — Pass 3: sibling-children vs root-children', () => {
  /**
   * Setup:
   *   root (key 1) — has 1 sibling and 1 child
   *
   * Sibling direction is determined by the ANCHOR's sex (isMaleKey(k) for the
   * ancestor key), NOT the sibling's own sex.
   *   - Male anchor (root sex='M') → all siblings go LEFT
   *   - Female anchor (root sex='F') → all siblings go RIGHT
   *
   * sib's child lands at the same Y as root's child; Pass 3 must push it out.
   */
  function setupSiblingChildCollision(anchorSex) {
    const sibXref = 'sib1';
    resetGlobals({
      tree: { 1: 'root', 2: 'father', 3: 'mother' },
      visible: new Set([1, 2, 3]),
      people: {
        root:    { sex: anchorSex },
        father:  {},
        mother:  {},
        sib1:    {},
        ch0: {}, sibch0: {},
      },
      relatives: {
        root: { siblings: [sibXref], spouses: [], sib_spouses: {} },
      },
      children: {
        root:  ['ch0'],
        sib1:  ['sibch0'],
      },
      expandedCh: new Set(['root', 'sib1']),
    });
    computePositions();
  }

  it('left (male anchor) sibling-children do not overlap root-children after shift', () => {
    setupSiblingChildCollision('M');  // male anchor → siblings go left
    computeRelativePositions();
    const ch0   = global._relPosCache.get('ch:0');
    const sibCh = [...global._relPosCache.entries()]
      .find(([k]) => k.startsWith('sibch:'));
    expect(ch0).toBeDefined();
    expect(sibCh).toBeDefined();
    const [, sibChEntry] = sibCh;
    // Sibling is to the left → its child must be entirely left of root-children
    expect(sibChEntry.x + NODE_W + H_GAP).toBeLessThanOrEqual(ch0.x);
  });

  it('right (female anchor) sibling-children do not overlap root-children after shift', () => {
    setupSiblingChildCollision('F');  // female anchor → siblings go right
    computeRelativePositions();
    const ch0   = global._relPosCache.get('ch:0');
    const sibCh = [...global._relPosCache.entries()]
      .find(([k]) => k.startsWith('sibch:'));
    expect(ch0).toBeDefined();
    expect(sibCh).toBeDefined();
    const [, sibChEntry] = sibCh;
    // Sibling is to the right → its child must be entirely right of root-children
    expect(sibChEntry.x).toBeGreaterThanOrEqual(ch0.x + NODE_W + H_GAP);
  });
});

describe('computeRelativePositions — Pass 3: sibling-children vs ancestor nodes', () => {
  /**
   * Root has a parent (key 2). Parent has a sibling (sib_of_parent) with children.
   * Those children land at y(gen 0) = the same Y as root.
   * Pass 3 must push sib_of_parent's children outward so they don't overlap root.
   */
  it('sibling-children of a parent do not overlap root node X range', () => {
    const tree = { 1: 'root', 2: 'father', 3: 'mother' };
    resetGlobals({
      tree,
      visible: new Set([1, 2, 3]),
      people: {
        root:          { sex: 'M' },
        father:        {},
        mother:        {},
        sib_of_father: { sex: 'M' },
        sibch0: {},
      },
      relatives: {
        father: { siblings: ['sib_of_father'], spouses: [], sib_spouses: {} },
      },
      children: { sib_of_father: ['sibch0'] },
      expandedCh: new Set(['sib_of_father']),
      expanded: new Set([1, 2]),
    });
    computePositions();
    computeRelativePositions();

    const rootPos = global._posCache.get(1);
    const sibCh   = [...global._relPosCache.entries()]
      .find(([k]) => k.startsWith('sibch:'));
    expect(sibCh).toBeDefined();
    const [, sibChEntry] = sibCh;

    // sibch must NOT overlap root node horizontally at the same Y
    const noOverlap =
      sibChEntry.x + NODE_W + H_GAP <= rootPos.x  ||
      sibChEntry.x >= rootPos.x + NODE_W + H_GAP;
    expect(noOverlap).toBe(true);
  });
});

// ── maxVisibleGen ──────────────────────────────────────────────────────────

describe('maxVisibleGen', () => {
  beforeEach(() => resetGlobals({ tree: {}, visible: new Set(), people: {}, relatives: {} }));

  it('returns 0 when only root is visible (key=1, gen=0)', () => {
    global.visibleKeys = new Set([1]);
    expect(maxVisibleGen()).toBe(0);
  });

  it('returns 1 when root + both parents visible (keys 1,2,3)', () => {
    global.visibleKeys = new Set([1, 2, 3]);
    expect(maxVisibleGen()).toBe(1);
  });

  it('returns 2 when a full 3-generation tree is visible (keys 1–7)', () => {
    global.visibleKeys = new Set([1, 2, 3, 4, 5, 6, 7]);
    expect(maxVisibleGen()).toBe(2);
  });

  it('handles an asymmetric tree (only paternal line)', () => {
    // keys 1, 2, 4 → gen 0, 1, 2 → max is 2
    global.visibleKeys = new Set([1, 2, 4]);
    expect(maxVisibleGen()).toBe(2);
  });
});

// ── nodePos ────────────────────────────────────────────────────────────────

describe('nodePos', () => {
  beforeEach(() => resetGlobals({ tree: {}, visible: new Set(), people: {}, relatives: {} }));

  it('returns cached position when key is in _posCache', () => {
    global._posCache = new Map([[1, { x: 100, y: 200 }]]);
    expect(nodePos(1)).toEqual({ x: 100, y: 200 });
  });

  it('returns {x:0, y:0} when key is not in _posCache', () => {
    global._posCache = new Map();
    expect(nodePos(99)).toEqual({ x: 0, y: 0 });
  });
});

// ── hasHiddenParents ───────────────────────────────────────────────────────

describe('hasHiddenParents', () => {
  function setup(treeKeys, visKeys) {
    const tree = {};
    treeKeys.forEach(k => { tree[k] = `xref${k}`; });
    global.currentTree = tree;
    global.visibleKeys = new Set(visKeys);
  }

  it('returns true when both parents are in the tree but neither is visible', () => {
    setup([1, 2, 3], [1]);   // key=1 is root; parents are keys 2,3 (in tree, not visible)
    expect(hasHiddenParents(1)).toBe(true);
  });

  it('returns false when neither parent is in the tree at all', () => {
    setup([1], [1]);          // key=1 has no parents in tree
    expect(hasHiddenParents(1)).toBe(false);
  });

  it('returns false when father is visible', () => {
    setup([1, 2, 3], [1, 2]); // father (key=2) is visible
    expect(hasHiddenParents(1)).toBe(false);
  });

  it('returns false when mother is visible', () => {
    setup([1, 2, 3], [1, 3]); // mother (key=3) is visible
    expect(hasHiddenParents(1)).toBe(false);
  });

  it('returns false when both parents are visible', () => {
    setup([1, 2, 3], [1, 2, 3]);
    expect(hasHiddenParents(1)).toBe(false);
  });

  it('returns true when only one parent is in tree and it is not visible', () => {
    setup([1, 2], [1]);       // only father in tree, not visible
    expect(hasHiddenParents(1)).toBe(true);
  });
});

// ── hasVisibleParents ──────────────────────────────────────────────────────

describe('hasVisibleParents', () => {
  function setup(visKeys) {
    global.visibleKeys = new Set(visKeys);
  }

  it('returns true when father (key*2) is visible', () => {
    setup([1, 2]);
    expect(hasVisibleParents(1)).toBe(true);
  });

  it('returns true when mother (key*2+1) is visible', () => {
    setup([1, 3]);
    expect(hasVisibleParents(1)).toBe(true);
  });

  it('returns false when neither parent is visible', () => {
    setup([1]);
    expect(hasVisibleParents(1)).toBe(false);
  });

  it('returns true when both parents are visible', () => {
    setup([1, 2, 3]);
    expect(hasVisibleParents(1)).toBe(true);
  });
});

describe('computeRelativePositions — Pass 3: direction correctness', () => {
  // Direction is determined by anchor sex (isMaleKey(anchorKey)), not sibling sex.

  it('male anchor → sibling-children pushed left of root', () => {
    resetGlobals({
      tree: { 1: 'root', 2: 'father', 3: 'mother' },
      visible: new Set([1, 2, 3]),
      people: {
        root:   { sex: 'M' },   // male anchor → siblings go left
        father: {},
        mother: {},
        sib1:   {},
        ch0: {}, sibch0: {},
      },
      relatives: { root: { siblings: ['sib1'], spouses: [], sib_spouses: {} } },
      children:  { root: ['ch0'], sib1: ['sibch0'] },
      expandedCh: new Set(['root', 'sib1']),
    });
    computePositions();
    computeRelativePositions();
    const rootPos = global._posCache.get(1);
    const sibCh   = [...global._relPosCache.entries()]
      .find(([k]) => k.startsWith('sibch:'));
    expect(sibCh).toBeDefined();
    expect(sibCh[1].x + NODE_W).toBeLessThanOrEqual(rootPos.x);
  });

  it('female anchor → sibling-children pushed right of root', () => {
    resetGlobals({
      tree: { 1: 'root', 2: 'father', 3: 'mother' },
      visible: new Set([1, 2, 3]),
      people: {
        root:   { sex: 'F' },   // female anchor → siblings go right
        father: {},
        mother: {},
        sib1:   {},
        ch0: {}, sibch0: {},
      },
      relatives: { root: { siblings: ['sib1'], spouses: [], sib_spouses: {} } },
      children:  { root: ['ch0'], sib1: ['sibch0'] },
      expandedCh: new Set(['root', 'sib1']),
    });
    computePositions();
    computeRelativePositions();
    const rootPos = global._posCache.get(1);
    const sibCh   = [...global._relPosCache.entries()]
      .find(([k]) => k.startsWith('sibch:'));
    expect(sibCh).toBeDefined();
    expect(sibCh[1].x).toBeGreaterThanOrEqual(rootPos.x + NODE_W);
  });
});

describe('computeRelativePositions — Pass 3: multiple sibling groups', () => {
  it('two sibling groups with children are both shifted away from root-children', () => {
    // Two anchors: male root (sib goes left) and female parent (sib goes right).
    // We test that two separate sibling groups both resolve their children collisions.
    // Simpler: use root (male) with two siblings; both go left.
    // After Pass 3, all their children must be to the left of root-children.
    resetGlobals({
      tree: { 1: 'root', 2: 'father', 3: 'mother' },
      visible: new Set([1, 2, 3]),
      people: {
        root:   { sex: 'M' },   // male anchor → both siblings go left
        father: {},
        mother: {},
        sib_a:  {},
        sib_b:  {},
        ch0: {}, sibch_a0: {}, sibch_b0: {},
      },
      relatives: {
        root: { siblings: ['sib_a', 'sib_b'], spouses: [], sib_spouses: {} },
      },
      children: {
        root:  ['ch0'],
        sib_a: ['sibch_a0'],
        sib_b: ['sibch_b0'],
      },
      expandedCh: new Set(['root', 'sib_a', 'sib_b']),
    });
    computePositions();
    computeRelativePositions();

    const ch0 = global._relPosCache.get('ch:0');
    const allSibCh = [...global._relPosCache.entries()]
      .filter(([k]) => k.startsWith('sibch:'));

    // All sibling-children must be to the left of root-children
    for (const [, e] of allSibCh) {
      expect(e.x + NODE_W + H_GAP).toBeLessThanOrEqual(ch0.x);
    }
  });
});
