import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Inject DESIGN as a global so viz_layout.js can read it
const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;

const { NODE_W, NODE_W_FOCUS, NODE_H, NODE_H_FOCUS, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;
// Focus-to-sibling gap: accounts for focus node being wider than NODE_W.
const FOCUS_TO_SIB = NODE_W_FOCUS / 2 + H_GAP + NODE_W / 2;

const {
  computeLayout,
  _sortByBirthYear,
  _packRow,
  _rightContour,
  _leftContour,
  _requiredSeparation,
} = require('../../js/viz_layout.js');
const SLOT = NODE_W + H_GAP;

// ── helpers ────────────────────────────────────────────────────────────────

function resetGlobals({ people = {}, parents = {}, children = {}, relatives = {} } = {}) {
  global.PEOPLE    = people;
  global.PARENTS   = parents;
  global.CHILDREN  = children;
  global.RELATIVES = relatives;
}

// ── _sortByBirthYear ───────────────────────────────────────────────────────

describe('_sortByBirthYear', () => {
  it('sorts by birth_year ascending', () => {
    global.PEOPLE = {
      '@I1@': { birth_year: 1900 },
      '@I2@': { birth_year: 1880 },
      '@I3@': { birth_year: 1920 },
    };
    expect(_sortByBirthYear(['@I1@', '@I2@', '@I3@'])).toEqual(['@I2@', '@I1@', '@I3@']);
  });

  it('treats missing birth_year as 9999 (sorts last)', () => {
    global.PEOPLE = {
      '@I1@': { birth_year: 1900 },
      '@I2@': {},
    };
    expect(_sortByBirthYear(['@I1@', '@I2@'])).toEqual(['@I1@', '@I2@']);
  });
});

// ── _packRow ───────────────────────────────────────────────────────────────

describe('_packRow', () => {
  it('packs single item at x=0 with generation and role', () => {
    const items = [{ xref: '@I1@' }];
    const nodes = _packRow(items, 0, 0, 'focus');
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({ xref: '@I1@', x: 0, y: 0, generation: 0, role: 'focus' });
  });

  it('packs two items with NODE_W + H_GAP spacing', () => {
    const items = [{ xref: '@I1@' }, { xref: '@I2@' }];
    const nodes = _packRow(items, 0, 0, 'sibling');
    expect(nodes[0].x).toBe(0);
    expect(nodes[1].x).toBe(NODE_W + H_GAP);
  });
});

// ── computeLayout — shape ──────────────────────────────────────────────────

describe('computeLayout — return shape', () => {
  it('returns { nodes, edges }', () => {
    resetGlobals({ people: { '@I1@': { birth_year: 1900 } } });
    const result = computeLayout('@I1@', new Set(), new Set());
    expect(result).toHaveProperty('nodes');
    expect(result).toHaveProperty('edges');
    expect(Array.isArray(result.nodes)).toBe(true);
    expect(Array.isArray(result.edges)).toBe(true);
  });
});

// ── Test 1: Focus-only tree ────────────────────────────────────────────────

describe('computeLayout — focus-only tree', () => {
  beforeEach(() => {
    resetGlobals({ people: { '@I1@': { birth_year: 1900 } } });
  });

  it('has exactly one node', () => {
    const { nodes } = computeLayout('@I1@', new Set(), new Set());
    expect(nodes).toHaveLength(1);
  });

  it('focus node is at x=0, y=0, generation=0, role=focus', () => {
    const { nodes } = computeLayout('@I1@', new Set(), new Set());
    const focus = nodes.find(n => n.xref === '@I1@');
    expect(focus).toBeDefined();
    expect(focus.x).toBe(0);
    expect(focus.y).toBe(0);
    expect(focus.generation).toBe(0);
    expect(focus.role).toBe('focus');
  });
});

// ── Test 2: Focus with siblings (birth order) ─────────────────────────────

describe('computeLayout — focus with siblings', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@OLDER@':  { birth_year: 1870 },
        '@FOCUS@':  { birth_year: 1873 },
        '@YOUNGER@': { birth_year: 1876 },
      },
      relatives: {
        '@FOCUS@': { siblings: ['@OLDER@', '@YOUNGER@'], spouses: [] },
      },
    });
  });

  it('focus is at x=0', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const focus = nodes.find(n => n.xref === '@FOCUS@');
    expect(focus.x).toBe(0);
  });

  it('older sibling is at x = -FOCUS_TO_SIB (accounts for wider focus node)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const older = nodes.find(n => n.xref === '@OLDER@');
    expect(older).toBeDefined();
    expect(older.x).toBe(-FOCUS_TO_SIB);
  });

  it('younger sibling is at x = +FOCUS_TO_SIB (accounts for wider focus node)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const younger = nodes.find(n => n.xref === '@YOUNGER@');
    expect(younger).toBeDefined();
    expect(younger.x).toBe(FOCUS_TO_SIB);
  });

  it('all generation-0 nodes are at y=0', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    nodes.filter(n => n.generation === 0).forEach(n => {
      expect(n.y).toBe(0);
    });
  });
});

// ── Test 3: Focus with parents ─────────────────────────────────────────────

describe('computeLayout — focus with parents', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
        '@MOTHER@': { birth_year: 1872 },
      },
      parents: {
        '@FOCUS@': ['@FATHER@', '@MOTHER@'],
      },
    });
  });

  it('father is at x < 0, y = -ROW_HEIGHT', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const father = nodes.find(n => n.xref === '@FATHER@');
    expect(father).toBeDefined();
    expect(father.x).toBeLessThan(0);
    expect(father.y).toBe(-ROW_HEIGHT);
  });

  it('mother is at x > 0, y = -ROW_HEIGHT', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    expect(mother).toBeDefined();
    expect(mother.x).toBeGreaterThan(0);
    expect(mother.y).toBe(-ROW_HEIGHT);
  });

  it('parent nodes have generation = -1', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const parents = nodes.filter(n => n.generation === -1);
    expect(parents).toHaveLength(2);
  });

  it('edges include an ancestor edge for each parent', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const ancestorEdges = edges.filter(e => e.type === 'ancestor');
    expect(ancestorEdges.length).toBeGreaterThanOrEqual(2);
  });
});

// ── Test 4: Focus with children ────────────────────────────────────────────

describe('computeLayout — focus with children', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@': { birth_year: 1900 },
        '@C1@':    { birth_year: 1925 },
        '@C2@':    { birth_year: 1927 },
        '@C3@':    { birth_year: 1929 },
      },
      children: {
        '@FOCUS@': ['@C1@', '@C2@', '@C3@'],
      },
    });
  });

  it('children are at y = +ROW_HEIGHT', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    ['@C1@', '@C2@', '@C3@'].forEach(xref => {
      const child = nodes.find(n => n.xref === xref);
      expect(child).toBeDefined();
      expect(child.y).toBe(ROW_HEIGHT);
    });
  });

  it('children have generation = +1', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const children = nodes.filter(n => n.generation === 1);
    expect(children).toHaveLength(3);
  });

  it('children are centered under the focus node center', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const focus = nodes.find(n => n.xref === '@FOCUS@');
    // Focus uses NODE_W_FOCUS; its true visual center is focus.x + NODE_W_FOCUS/2.
    const focusCenterX = focus.x + NODE_W_FOCUS / 2;
    const childXs = ['@C1@', '@C2@', '@C3@'].map(xref => {
      const n = nodes.find(c => c.xref === xref);
      return n.x + NODE_W / 2;
    });
    const centerX = (Math.min(...childXs) + Math.max(...childXs)) / 2;
    expect(centerX).toBeCloseTo(focusCenterX);
  });

  it('children are evenly spaced', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const childXs = ['@C1@', '@C2@', '@C3@']
      .map(xref => nodes.find(n => n.xref === xref).x)
      .sort((a, b) => a - b);
    const gap1 = childXs[1] - childXs[0];
    const gap2 = childXs[2] - childXs[1];
    expect(gap1).toBeCloseTo(gap2);
    expect(gap1).toBeCloseTo(NODE_W + H_GAP);
  });
});

// ── Test 5: Focus with spouse ──────────────────────────────────────────────

describe('computeLayout — focus with spouse', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@': { birth_year: 1900 },
        '@SPOUSE@': { birth_year: 1902 },
      },
      relatives: {
        '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] },
      },
    });
  });

  it('spouse is to the right of focus (no siblings)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const focus  = nodes.find(n => n.xref === '@FOCUS@');
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    expect(spouse).toBeDefined();
    expect(spouse.x).toBeGreaterThan(focus.x);
  });

  it('spouse is at x = NODE_W_FOCUS/2 + MARRIAGE_GAP + NODE_W/2 (no siblings)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    // Focus at x=0 has width NODE_W_FOCUS; right edge = NODE_W_FOCUS/2.
    // Spouse center = right edge + MARRIAGE_GAP + NODE_W/2.
    expect(spouse.x).toBe(NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2);
  });

  it('spouse has role "spouse"', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    expect(spouse.role).toBe('spouse');
  });

  it('edges include a marriage edge', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const marriageEdges = edges.filter(e => e.type === 'marriage');
    expect(marriageEdges.length).toBeGreaterThanOrEqual(1);
  });

  it('marriage edge x1 is the right edge of the focus node (no siblings)', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const me = edges.find(e => e.type === 'marriage');
    // Focus at x=0 has width NODE_W_FOCUS; right edge center = NODE_W_FOCUS/2.
    expect(me.x1).toBe(NODE_W_FOCUS / 2);
  });
});

// ── Test 5c: Multi-spouse marriage edges ───────────────────────────────────

describe('computeLayout — multi-spouse marriage edges', () => {
  it('second spouse marriage edge starts at right edge of first spouse', () => {
    resetGlobals({
      people: {
        '@FOCUS@':   { birth_year: 1900 },
        '@SPOUSE1@': { birth_year: 1901 },
        '@SPOUSE2@': { birth_year: 1920 },
      },
      relatives: {
        '@FOCUS@': { siblings: [], spouses: ['@SPOUSE1@', '@SPOUSE2@'] },
      },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const sp1 = nodes.find(n => n.xref === '@SPOUSE1@');
    const sp2 = nodes.find(n => n.xref === '@SPOUSE2@');
    const marriageEdges = edges.filter(e => e.type === 'marriage');
    expect(marriageEdges).toHaveLength(2);
    // First edge: focus right edge (NODE_W_FOCUS/2) → spouse1 center
    expect(marriageEdges[0].x1).toBe(NODE_W_FOCUS / 2);
    expect(marriageEdges[0].x2).toBe(sp1.x);
    // Second edge: spouse1 right edge center (sp1.x + NODE_W/2) → spouse2 center
    expect(marriageEdges[1].x1).toBe(sp1.x + NODE_W / 2);
    expect(marriageEdges[1].x2).toBe(sp2.x);
  });
});

// ── Test 5b: Spouse siblings expanded ─────────────────────────────────────

describe('computeLayout — spouse siblings expanded', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@SPOUSE@': { birth_year: 1902 },
        '@SS1@':    { birth_year: 1895 },
        '@SS2@':    { birth_year: 1898 },
      },
      relatives: {
        '@FOCUS@':  { siblings: [], spouses: ['@SPOUSE@'] },
        '@SPOUSE@': { siblings: ['@SS1@', '@SS2@'], spouses: [] },
      },
    });
  });

  it('spouse siblings appear to the right of the spouse', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    const ss1    = nodes.find(n => n.xref === '@SS1@');
    const ss2    = nodes.find(n => n.xref === '@SS2@');
    expect(ss1).toBeDefined();
    expect(ss2).toBeDefined();
    expect(ss1.x).toBeGreaterThan(spouse.x);
    expect(ss2.x).toBeGreaterThan(spouse.x);
  });

  it('first spouse sibling is exactly one SLOT to the right of the spouse', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    // spouse siblings sorted by birth_year; @SS1@ (1895) comes first
    const ss1 = nodes.find(n => n.xref === '@SS1@');
    expect(ss1.x).toBe(spouse.x + NODE_W + H_GAP);
  });

  it('spouse siblings have role "spouse_sibling"', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
    const spouseSibs = nodes.filter(n => n.role === 'spouse_sibling');
    expect(spouseSibs).toHaveLength(2);
  });

  it('spouse siblings do NOT appear when spouseSiblingsExpanded is false', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const spouseSibs = nodes.filter(n => n.role === 'spouse_sibling');
    expect(spouseSibs).toHaveLength(0);
  });
});

// ── A1 regression: sibling_bracket edges must never be emitted ────────────

describe('computeLayout — no sibling_bracket edges', () => {
  it('emits zero sibling_bracket edges when focus has siblings', () => {
    resetGlobals({
      people: {
        '@OLDER@':   { birth_year: 1870 },
        '@FOCUS@':   { birth_year: 1873 },
        '@YOUNGER@': { birth_year: 1876 },
      },
      relatives: {
        '@FOCUS@': { siblings: ['@OLDER@', '@YOUNGER@'], spouses: [] },
      },
    });
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
    expect(edges.filter(e => e.type === 'sibling_bracket').length).toBe(0);
  });
});

// ── A2: Spouse placed immediately after focus, before younger siblings ─────

describe('computeLayout — spouse before younger siblings', () => {
  it('spouse x is NODE_W_FOCUS/2 + MARRIAGE_GAP + NODE_W/2 even when focus has younger sibling', () => {
    resetGlobals({
      people: {
        '@FOCUS@':   { birth_year: 1900 },
        '@YOUNGER@': { birth_year: 1905 },
        '@SPOUSE@':  { birth_year: 1902 },
      },
      relatives: {
        '@FOCUS@': { siblings: ['@YOUNGER@'], spouses: ['@SPOUSE@'] },
      },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    expect(spouse.x).toBe(NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2);
  });

  it('younger sibling x is greater than spouse x', () => {
    resetGlobals({
      people: {
        '@FOCUS@':   { birth_year: 1900 },
        '@YOUNGER@': { birth_year: 1905 },
        '@SPOUSE@':  { birth_year: 1902 },
      },
      relatives: {
        '@FOCUS@': { siblings: ['@YOUNGER@'], spouses: ['@SPOUSE@'] },
      },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const spouse  = nodes.find(n => n.xref === '@SPOUSE@');
    const younger = nodes.find(n => n.xref === '@YOUNGER@');
    expect(younger.x).toBeGreaterThan(spouse.x);
  });

  it('second spouse marriage edge x1 is firstSpouseX + NODE_W/2', () => {
    resetGlobals({
      people: {
        '@FOCUS@':   { birth_year: 1900 },
        '@SPOUSE1@': { birth_year: 1901 },
        '@SPOUSE2@': { birth_year: 1920 },
      },
      relatives: {
        '@FOCUS@': { siblings: [], spouses: ['@SPOUSE1@', '@SPOUSE2@'] },
      },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const firstSpouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
    const marriageEdges = edges.filter(e => e.type === 'marriage');
    expect(marriageEdges[1].x1).toBe(firstSpouseX + NODE_W / 2);
  });
});

// ── Test 6: No overlap (6 siblings + spouse with 4 siblings expanded) ──────

describe('computeLayout — no overlap', () => {
  it('all nodes in generation 0 have distinct x values', () => {
    const sibs = ['@S1@', '@S2@', '@S3@', '@S4@', '@S5@', '@S6@'];
    const spouseSibs = ['@SS1@', '@SS2@', '@SS3@', '@SS4@'];
    const people = {
      '@FOCUS@':  { birth_year: 1900 },
      '@SPOUSE@': { birth_year: 1901 },
      '@S1@': { birth_year: 1880 },
      '@S2@': { birth_year: 1882 },
      '@S3@': { birth_year: 1884 },
      '@S4@': { birth_year: 1903 },
      '@S5@': { birth_year: 1905 },
      '@S6@': { birth_year: 1907 },
      '@SS1@': { birth_year: 1890 },
      '@SS2@': { birth_year: 1892 },
      '@SS3@': { birth_year: 1894 },
      '@SS4@': { birth_year: 1910 },
    };
    const relatives = {
      '@FOCUS@':  { siblings: sibs,       spouses: ['@SPOUSE@'] },
      '@SPOUSE@': { siblings: spouseSibs, spouses: [] },
    };
    resetGlobals({ people, relatives });

    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@SPOUSE@']));
    const gen0 = nodes.filter(n => n.generation === 0);
    const xs = gen0.map(n => n.x);
    const uniqueXs = new Set(xs);
    expect(uniqueXs.size).toBe(xs.length);
  });
});

// ── Test 7: Grandparent expansion ─────────────────────────────────────────

describe('computeLayout — grandparent expansion', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
        '@MOTHER@': { birth_year: 1872 },
        '@GFF@':    { birth_year: 1840 },
        '@GFM@':    { birth_year: 1842 },
      },
      parents: {
        '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
        '@FATHER@': ['@GFF@', '@GFM@'],
      },
    });
  });

  it('grandparents appear at y = -2 * ROW_HEIGHT when father is in expandedAncestors', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@']), new Set());
    const gff = nodes.find(n => n.xref === '@GFF@');
    const gfm = nodes.find(n => n.xref === '@GFM@');
    expect(gff).toBeDefined();
    expect(gfm).toBeDefined();
    expect(gff.y).toBe(-2 * ROW_HEIGHT);
    expect(gfm.y).toBe(-2 * ROW_HEIGHT);
  });

  it('grandparents do NOT appear when father is NOT in expandedAncestors', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const gff = nodes.find(n => n.xref === '@GFF@');
    expect(gff).toBeUndefined();
  });

  it('grandparent nodes have generation = -2', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@']), new Set());
    const grandparents = nodes.filter(n => n.generation === -2);
    expect(grandparents).toHaveLength(2);
  });
});

// ── Test 8: Only one parent ────────────────────────────────────────────────

describe('computeLayout — single parent', () => {
  // Parent center aligns with focus visual center (NODE_W_FOCUS/2 = 80);
  // so parent.x = 80 - NODE_W/2 = 10.
  const SINGLE_PARENT_X = NODE_W_FOCUS / 2 - NODE_W / 2;

  it('single mother is centered above focus (center at focus center)', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@MOTHER@': { birth_year: 1870 },
      },
      parents: { '@FOCUS@': [null, '@MOTHER@'] },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    expect(mother).toBeDefined();
    expect(mother.x).toBe(SINGLE_PARENT_X);
    expect(mother.y).toBe(-ROW_HEIGHT);
  });

  it('single father is centered above focus (center at focus center)', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
      },
      parents: { '@FOCUS@': ['@FATHER@', null] },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const father = nodes.find(n => n.xref === '@FATHER@');
    expect(father).toBeDefined();
    expect(father.x).toBe(SINGLE_PARENT_X);
    expect(father.y).toBe(-ROW_HEIGHT);
  });
});

// ── Test 9: Width-aware ancestor placement (no overlap when both parents expanded) ─

describe('computeLayout — width-aware ancestor placement', () => {
  const SLOT = NODE_W + H_GAP;

  // Tree mirrors the screenshot scenario:
  //   @FOCUS@ → [@FATHER@(unexpanded), @MOTHER@(expanded)]
  //   @MOTHER@ → [@MGF@(expanded), @MGM@(expanded)]
  //   @MGF@  → [@MGGF@, @MGGM@]   (leaf grandparents)
  //   @MGM@  → [@MMGF@, @MMGM@]   (leaf grandparents)
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@': { birth_year: 1995 },
        '@FATHER@': { birth_year: 1963 },
        '@MOTHER@': { birth_year: 1963 },
        '@MGF@':   { birth_year: 1926 },
        '@MGM@':   { birth_year: 1941 },
        '@MGGF@':  { birth_year: 1882 },
        '@MGGM@':  { birth_year: 1895 },
        '@MMGF@':  { birth_year: 1901 },
        '@MMGM@':  { birth_year: 1909 },
      },
      parents: {
        '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
        '@MOTHER@': ['@MGF@', '@MGM@'],
        '@MGF@':    ['@MGGF@', '@MGGM@'],
        '@MGM@':    ['@MMGF@', '@MMGM@'],
      },
    });
  });

  it('no two ancestor nodes at the same generation overlap', () => {
    const expanded = new Set(['@MOTHER@', '@MGF@', '@MGM@']);
    const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
    const ancestorsByGen = {};
    for (const node of nodes) {
      if (node.role !== 'ancestor') continue;
      if (!ancestorsByGen[node.generation]) ancestorsByGen[node.generation] = [];
      ancestorsByGen[node.generation].push(node);
    }
    for (const genNodes of Object.values(ancestorsByGen)) {
      const sorted = genNodes.slice().sort((a, b) => a.x - b.x);
      for (let i = 1; i < sorted.length; i++) {
        const gap = sorted[i].x - sorted[i - 1].x;
        expect(gap).toBeGreaterThanOrEqual(SLOT);
      }
    }
  });

  it('parent pair midpoint aligns with child center when both parents expanded', () => {
    const expanded = new Set(['@MOTHER@', '@MGF@', '@MGM@']);
    const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
    const nodeMap = new Map(nodes.map(n => [n.xref, n]));
    const mgf = nodeMap.get('@MGF@');
    const mgm = nodeMap.get('@MGM@');
    const mother = nodeMap.get('@MOTHER@');
    // Midpoint of MGF and MGM centers should equal MOTHER's center
    const midpoint = (mgf.x + NODE_W / 2 + mgm.x + NODE_W / 2) / 2;
    expect(midpoint).toBeCloseTo(mother.x + NODE_W / 2, 1);
  });

  it('gen-3 nodes are exactly SLOT apart (4 leaf grandparents, all non-overlapping)', () => {
    const expanded = new Set(['@MOTHER@', '@MGF@', '@MGM@']);
    const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
    const gen3 = nodes.filter(n => n.generation === -3).sort((a, b) => a.x - b.x);
    expect(gen3).toHaveLength(4);
    for (let i = 1; i < gen3.length; i++) {
      expect(gen3[i].x - gen3[i - 1].x).toBeCloseTo(SLOT, 1);
    }
  });

  it('unexpanded ancestor keeps symmetric ±SLOT/2 placement (backward compat)', () => {
    // Only @MOTHER@ expanded (neither of her parents is expanded)
    const expanded = new Set(['@MOTHER@']);
    const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
    const mgf = nodes.find(n => n.xref === '@MGF@');
    const mgm = nodes.find(n => n.xref === '@MGM@');
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    expect(mgf.x).toBeCloseTo(mother.x - SLOT / 2, 1);
    expect(mgm.x).toBeCloseTo(mother.x + SLOT / 2, 1);
  });
});

// ── Test 10: Descendant umbrella layout ────────────────────────────────────

describe('computeLayout — descendant umbrella', () => {
  const UMBRELLA_Y = NODE_H + (ROW_HEIGHT - NODE_H) / 2;

  it('single child, no spouse, focus has spouse: anchor is focus↔spouse midpoint', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@SPOUSE@': { birth_year: 1902 },
        '@C1@':     { birth_year: 1925 },
      },
      children:  { '@FOCUS@': ['@C1@'] },
      relatives: { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] } },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

    const focusCenter  = NODE_W_FOCUS / 2;                       // 80
    const spouseX      = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2; // 210 (left edge)
    const spouseCenter = spouseX + NODE_W / 2;                   // 280
    const anchorX      = (focusCenter + spouseCenter) / 2;       // 180

    const c1 = nodes.find(n => n.xref === '@C1@');
    expect(c1).toBeDefined();
    expect(c1.x + NODE_W / 2).toBeCloseTo(anchorX, 1);

    const descEdges = edges.filter(e => e.type === 'descendant');
    // Anchor drop: starts on the focus↔spouse marriage line (y = NODE_H/2)
    // so it meets the marriage line perpendicularly with no gap.
    const anchorDrop = descEdges.find(e =>
      e.x1 === anchorX && e.y1 === NODE_H / 2 && e.x2 === anchorX && e.y2 === UMBRELLA_Y
    );
    expect(anchorDrop).toBeDefined();
    // Per-child drop: (anchorX, umbrellaY) → (anchorX, ROW_HEIGHT)
    const childDrop = descEdges.find(e =>
      e.x1 === anchorX && e.y1 === UMBRELLA_Y && e.x2 === anchorX && e.y2 === ROW_HEIGHT
    );
    expect(childDrop).toBeDefined();
    // No crossbar at umbrellaY with distinct x1/x2
    const crossbar = descEdges.find(e =>
      e.y1 === UMBRELLA_Y && e.y2 === UMBRELLA_Y && e.x1 !== e.x2
    );
    expect(crossbar).toBeUndefined();
  });

  it('multiple children, none with spouses: umbrella spans leftmost→rightmost child centers', () => {
    resetGlobals({
      people: {
        '@FOCUS@': { birth_year: 1900 },
        '@C1@':    { birth_year: 1925 },
        '@C2@':    { birth_year: 1927 },
        '@C3@':    { birth_year: 1929 },
      },
      children: { '@FOCUS@': ['@C1@', '@C2@', '@C3@'] },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const anchorX = NODE_W_FOCUS / 2; // no focus-spouse → focus center

    const centers = ['@C1@', '@C2@', '@C3@']
      .map(x => nodes.find(n => n.xref === x).x + NODE_W / 2)
      .sort((a, b) => a - b);
    const leftmost  = centers[0];
    const rightmost = centers[centers.length - 1];

    const descEdges = edges.filter(e => e.type === 'descendant');

    const crossbar = descEdges.find(e =>
      e.y1 === UMBRELLA_Y && e.y2 === UMBRELLA_Y &&
      Math.min(e.x1, e.x2) === leftmost && Math.max(e.x1, e.x2) === rightmost
    );
    expect(crossbar).toBeDefined();

    // No focus-spouse → drop starts at the bottom of the focus (NODE_H_FOCUS = 42),
    // not at NODE_H (= 38) which would be 4px inside the focus node.
    const anchorDrop = descEdges.find(e =>
      e.x1 === anchorX && e.y1 === NODE_H_FOCUS && e.x2 === anchorX && e.y2 === UMBRELLA_Y
    );
    expect(anchorDrop).toBeDefined();

    centers.forEach(cx => {
      const drop = descEdges.find(e =>
        e.x1 === cx && e.y1 === UMBRELLA_Y && e.x2 === cx && e.y2 === ROW_HEIGHT
      );
      expect(drop).toBeDefined();
    });
  });

  it('child with spouse: spouse node has role descendant_spouse; marriage edge between them', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@C1@':     { birth_year: 1925 },
        '@C1SP@':   { birth_year: 1927 },
      },
      children:  { '@FOCUS@': ['@C1@'] },
      relatives: { '@C1@': { siblings: [], spouses: ['@C1SP@'] } },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const sp = nodes.find(n => n.xref === '@C1SP@');
    expect(sp).toBeDefined();
    expect(sp.role).toBe('descendant_spouse');
    expect(sp.y).toBe(ROW_HEIGHT);

    const c1 = nodes.find(n => n.xref === '@C1@');
    // Descendant-row spouses use a short gap (H_GAP) — MARRIAGE_GAP is reserved
    // for the focus couple (where children hang below the marriage midpoint).
    expect(sp.x).toBeCloseTo(c1.x + NODE_W + H_GAP, 1);

    const marriageAtChildRow = edges.find(e =>
      e.type === 'marriage' && e.y1 === ROW_HEIGHT + NODE_H / 2 && e.y2 === ROW_HEIGHT + NODE_H / 2
    );
    expect(marriageAtChildRow).toBeDefined();
    expect(marriageAtChildRow.x1).toBeCloseTo(c1.x + NODE_W, 1); // child right edge
    expect(marriageAtChildRow.x2).toBeCloseTo(sp.x, 1);          // spouse left edge
  });

  it('focus with no spouse: anchor originates at focus center (NODE_W_FOCUS/2)', () => {
    resetGlobals({
      people: {
        '@FOCUS@': { birth_year: 1900 },
        '@C1@':    { birth_year: 1925 },
      },
      children: { '@FOCUS@': ['@C1@'] },
    });
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const anchorX = NODE_W_FOCUS / 2;
    // No spouse → drop starts at NODE_H_FOCUS (the bottom of the focus node).
    const anchorDrop = edges.find(e =>
      e.type === 'descendant' &&
      e.x1 === anchorX && e.y1 === NODE_H_FOCUS && e.x2 === anchorX && e.y2 === (NODE_H + (ROW_HEIGHT - NODE_H) / 2)
    );
    expect(anchorDrop).toBeDefined();
  });

  it('two children both with spouses: crossbar x-span covers only child centers', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@C1@':     { birth_year: 1925 },
        '@C1SP@':   { birth_year: 1926 },
        '@C2@':     { birth_year: 1928 },
        '@C2SP@':   { birth_year: 1930 },
      },
      children:  { '@FOCUS@': ['@C1@', '@C2@'] },
      relatives: {
        '@C1@': { siblings: [], spouses: ['@C1SP@'] },
        '@C2@': { siblings: [], spouses: ['@C2SP@'] },
      },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const c1 = nodes.find(n => n.xref === '@C1@');
    const c2 = nodes.find(n => n.xref === '@C2@');
    const sp1 = nodes.find(n => n.xref === '@C1SP@');
    const sp2 = nodes.find(n => n.xref === '@C2SP@');

    const c1Center = c1.x + NODE_W / 2;
    const c2Center = c2.x + NODE_W / 2;
    const sp2Center = sp2.x + NODE_W / 2;

    const crossbar = edges.find(e =>
      e.type === 'descendant' && e.y1 === e.y2 &&
      e.y1 === NODE_H + (ROW_HEIGHT - NODE_H) / 2 && e.x1 !== e.x2
    );
    expect(crossbar).toBeDefined();
    const leftmost  = Math.min(crossbar.x1, crossbar.x2);
    const rightmost = Math.max(crossbar.x1, crossbar.x2);
    expect(leftmost).toBeCloseTo(c1Center, 1);
    expect(rightmost).toBeCloseTo(c2Center, 1);
    // Crossbar must NOT extend as far as the second spouse
    expect(rightmost).toBeLessThan(sp2Center);

    // Group ordering: c1, sp1, c2, sp2 packed left→right
    expect(c1.x).toBeLessThan(sp1.x);
    expect(sp1.x).toBeLessThan(c2.x);
    expect(c2.x).toBeLessThan(sp2.x);
    // Child-spouse marriage edges (two, one per group)
    const marriageEdges = edges.filter(e =>
      e.type === 'marriage' && e.y1 === ROW_HEIGHT + NODE_H / 2
    );
    expect(marriageEdges).toHaveLength(2);
  });

  it('child-centers midpoint equals anchorX when focus has one spouse and two unmarried children', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@SPOUSE@': { birth_year: 1902 },
        '@C1@':     { birth_year: 1925 },
        '@C2@':     { birth_year: 1928 },
      },
      children:  { '@FOCUS@': ['@C1@', '@C2@'] },
      relatives: { '@FOCUS@': { siblings: [], spouses: ['@SPOUSE@'] } },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    const c1Center = nodes.find(n => n.xref === '@C1@').x + NODE_W / 2;
    const c2Center = nodes.find(n => n.xref === '@C2@').x + NODE_W / 2;
    const mid = (c1Center + c2Center) / 2;

    const focusCenter = NODE_W_FOCUS / 2;
    const spouseX = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2;
    const spouseCenter = spouseX + NODE_W / 2;
    const anchorX = (focusCenter + spouseCenter) / 2;

    expect(mid).toBeCloseTo(anchorX, 1);
  });

  it('does not emit the old per-child slanted edge from (NODE_W/2, NODE_H) to a child top', () => {
    resetGlobals({
      people: {
        '@FOCUS@': { birth_year: 1900 },
        '@C1@':    { birth_year: 1925 },
        '@C2@':    { birth_year: 1927 },
      },
      children: { '@FOCUS@': ['@C1@', '@C2@'] },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const childCenters = ['@C1@', '@C2@']
      .map(x => nodes.find(n => n.xref === x).x + NODE_W / 2);
    childCenters.forEach(cx => {
      const slant = edges.find(e =>
        e.type === 'descendant' &&
        e.x1 === NODE_W / 2 && e.y1 === NODE_H &&
        e.x2 === cx && e.y2 === ROW_HEIGHT
      );
      expect(slant).toBeUndefined();
    });
  });
});

// ── Test 11: Ancestor umbrella layout ─────────────────────────────────────

describe('computeLayout — ancestor umbrella', () => {
  const ANC_UMBRELLA_Y = -(ROW_HEIGHT - NODE_H) / 2;   // -26
  const PARENT_BOTTOM  = -ROW_HEIGHT + NODE_H;         // -52
  const PARENT_MID_Y   = -ROW_HEIGHT + NODE_H / 2;     // -71

  it('two parents, no siblings: marriage edge between parents + anchor drop + single drop to focus', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
        '@MOTHER@': { birth_year: 1872 },
      },
      parents: { '@FOCUS@': ['@FATHER@', '@MOTHER@'] },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

    const father = nodes.find(n => n.xref === '@FATHER@');
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    expect(father).toBeDefined();
    expect(mother).toBeDefined();

    // Parents are centered on the focus visual center (NODE_W_FOCUS/2 = 80).
    const focusCenterX = NODE_W_FOCUS / 2;
    const fatherCenter = father.x + NODE_W / 2;
    const motherCenter = mother.x + NODE_W / 2;
    expect((fatherCenter + motherCenter) / 2).toBeCloseTo(focusCenterX, 1);

    // Marriage edge: father right edge → mother left edge at parent row middle y.
    const marriageEdge = edges.find(e =>
      e.type === 'marriage' && e.y1 === PARENT_MID_Y && e.y2 === PARENT_MID_Y
    );
    expect(marriageEdge).toBeDefined();
    expect(marriageEdge.x1).toBeCloseTo(father.x + NODE_W, 1);
    expect(marriageEdge.x2).toBeCloseTo(mother.x, 1);

    // Anchor drop: from the marriage line y down to umbrella y, at focus center x.
    // Starting at the marriage line (not parent bottom) so it meets perpendicularly with no gap.
    const ancEdges = edges.filter(e => e.type === 'ancestor');
    const anchorDrop = ancEdges.find(e =>
      e.x1 === focusCenterX && e.y1 === PARENT_MID_Y &&
      e.x2 === focusCenterX && e.y2 === ANC_UMBRELLA_Y
    );
    expect(anchorDrop).toBeDefined();

    // No crossbar (only one child of parents).
    const crossbar = ancEdges.find(e =>
      e.y1 === ANC_UMBRELLA_Y && e.y2 === ANC_UMBRELLA_Y && e.x1 !== e.x2
    );
    expect(crossbar).toBeUndefined();

    // Single drop from umbrella to focus top.
    const focusDrop = ancEdges.find(e =>
      e.x1 === focusCenterX && e.y1 === ANC_UMBRELLA_Y &&
      e.x2 === focusCenterX && e.y2 === 0
    );
    expect(focusDrop).toBeDefined();
  });

  it('two parents with siblings: crossbar spans leftmost→rightmost child center + per-child drops', () => {
    resetGlobals({
      people: {
        '@OLDER@':   { birth_year: 1895 },
        '@FOCUS@':   { birth_year: 1900 },
        '@YOUNGER@': { birth_year: 1905 },
        '@FATHER@':  { birth_year: 1870 },
        '@MOTHER@':  { birth_year: 1872 },
      },
      parents:   { '@FOCUS@': ['@FATHER@', '@MOTHER@'] },
      relatives: { '@FOCUS@': { siblings: ['@OLDER@', '@YOUNGER@'], spouses: [] } },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

    const focus   = nodes.find(n => n.xref === '@FOCUS@');
    const older   = nodes.find(n => n.xref === '@OLDER@');
    const younger = nodes.find(n => n.xref === '@YOUNGER@');

    const focusCenterX   = focus.x + NODE_W_FOCUS / 2;
    const olderCenterX   = older.x + NODE_W / 2;
    const youngerCenterX = younger.x + NODE_W / 2;

    const centers = [olderCenterX, focusCenterX, youngerCenterX];
    const leftmost  = Math.min(...centers);
    const rightmost = Math.max(...centers);

    const ancEdges = edges.filter(e => e.type === 'ancestor');

    // Crossbar spanning leftmost child center to rightmost child center.
    const crossbar = ancEdges.find(e =>
      e.y1 === ANC_UMBRELLA_Y && e.y2 === ANC_UMBRELLA_Y &&
      Math.min(e.x1, e.x2) === leftmost && Math.max(e.x1, e.x2) === rightmost
    );
    expect(crossbar).toBeDefined();

    // Anchor drop at focus center x — starts at marriage line y (both parents present).
    const anchorDrop = ancEdges.find(e =>
      e.x1 === focusCenterX && e.y1 === PARENT_MID_Y &&
      e.x2 === focusCenterX && e.y2 === ANC_UMBRELLA_Y
    );
    expect(anchorDrop).toBeDefined();

    // Per-child drops — one per gen-0 child of the parents (focus + siblings).
    centers.forEach(cx => {
      const drop = ancEdges.find(e =>
        e.x1 === cx && e.y1 === ANC_UMBRELLA_Y &&
        e.x2 === cx && e.y2 === 0
      );
      expect(drop).toBeDefined();
    });
  });

  it('single parent with siblings: no marriage edge; parent centered on focus center', () => {
    resetGlobals({
      people: {
        '@OLDER@':   { birth_year: 1895 },
        '@FOCUS@':   { birth_year: 1900 },
        '@MOTHER@':  { birth_year: 1872 },
      },
      parents:   { '@FOCUS@': [null, '@MOTHER@'] },
      relatives: { '@FOCUS@': { siblings: ['@OLDER@'], spouses: [] } },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set());

    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const focusCenterX = NODE_W_FOCUS / 2;
    // Mother's center is the focus center.
    expect(mother.x + NODE_W / 2).toBeCloseTo(focusCenterX, 1);

    // No marriage edge at the parent row (single parent).
    const parentMarriage = edges.find(e =>
      e.type === 'marriage' && e.y1 === PARENT_MID_Y
    );
    expect(parentMarriage).toBeUndefined();

    const older = nodes.find(n => n.xref === '@OLDER@');
    const olderCenterX = older.x + NODE_W / 2;

    const ancEdges = edges.filter(e => e.type === 'ancestor');

    // Anchor drop from (focusCenterX, PARENT_BOTTOM) to (focusCenterX, umbrellaY).
    const anchorDrop = ancEdges.find(e =>
      e.x1 === focusCenterX && e.y1 === PARENT_BOTTOM &&
      e.x2 === focusCenterX && e.y2 === ANC_UMBRELLA_Y
    );
    expect(anchorDrop).toBeDefined();

    // Crossbar spans the two gen-0 children.
    const crossbar = ancEdges.find(e =>
      e.y1 === ANC_UMBRELLA_Y && e.y2 === ANC_UMBRELLA_Y && e.x1 !== e.x2
    );
    expect(crossbar).toBeDefined();
    expect(Math.min(crossbar.x1, crossbar.x2)).toBeCloseTo(Math.min(focusCenterX, olderCenterX), 1);
    expect(Math.max(crossbar.x1, crossbar.x2)).toBeCloseTo(Math.max(focusCenterX, olderCenterX), 1);

    // Per-child drops.
    [focusCenterX, olderCenterX].forEach(cx => {
      const drop = ancEdges.find(e =>
        e.x1 === cx && e.y1 === ANC_UMBRELLA_Y &&
        e.x2 === cx && e.y2 === 0
      );
      expect(drop).toBeDefined();
    });
  });

  it('does not emit the old H-connector crossbar at y = -ROW_HEIGHT/2', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
        '@MOTHER@': { birth_year: 1872 },
      },
      parents: { '@FOCUS@': ['@FATHER@', '@MOTHER@'] },
    });
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set());
    const oldCrossbar = edges.find(e =>
      e.type === 'ancestor' &&
      e.y1 === -ROW_HEIGHT / 2 && e.y2 === -ROW_HEIGHT / 2 && e.x1 !== e.x2
    );
    expect(oldCrossbar).toBeUndefined();
  });
});

// ── Test 12: Recursive ancestor umbrella (grandparents and deeper) ────────

describe('computeLayout — recursive ancestor umbrella', () => {
  it('two grandparents: marriage edge + single drop to intermediate parent', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
        '@MOTHER@': { birth_year: 1872 },
        '@MGF@':    { birth_year: 1840 },
        '@MGM@':    { birth_year: 1842 },
      },
      parents: {
        '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
        '@MOTHER@': ['@MGF@', '@MGM@'],
      },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(['@MOTHER@']), new Set());

    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const mgf    = nodes.find(n => n.xref === '@MGF@');
    const mgm    = nodes.find(n => n.xref === '@MGM@');
    expect(mgf).toBeDefined();
    expect(mgm).toBeDefined();

    const gpMidY = -2 * ROW_HEIGHT + NODE_H / 2;

    // Marriage edge between MGF and MGM at the grandparent row center y.
    const marriageEdge = edges.find(e =>
      e.type === 'marriage' && e.y1 === gpMidY && e.y2 === gpMidY
    );
    expect(marriageEdge).toBeDefined();
    expect(marriageEdge.x1).toBeCloseTo(mgf.x + NODE_W, 1);
    expect(marriageEdge.x2).toBeCloseTo(mgm.x, 1);

    // Single vertical drop from the grandparents' marriage line midpoint (= mother's center)
    // down to the mother node's top. Type 'ancestor'.
    const motherCenterX = mother.x + NODE_W / 2;
    const drop = edges.find(e =>
      e.type === 'ancestor' &&
      e.x1 === motherCenterX && e.y1 === gpMidY &&
      e.x2 === motherCenterX && e.y2 === -ROW_HEIGHT
    );
    expect(drop).toBeDefined();

    // No old H-connector crossbar at y = -2*ROW_HEIGHT + ROW_HEIGHT/2.
    const oldCrossbarY = -2 * ROW_HEIGHT + ROW_HEIGHT / 2;
    const oldCrossbar = edges.find(e =>
      e.type === 'ancestor' &&
      e.y1 === oldCrossbarY && e.y2 === oldCrossbarY && e.x1 !== e.x2
    );
    expect(oldCrossbar).toBeUndefined();
  });

  it('single grandparent: one vertical drop, no marriage edge at grandparent row', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@MOTHER@': { birth_year: 1872 },
        '@MGM@':    { birth_year: 1842 },
      },
      parents: {
        '@FOCUS@':  [null, '@MOTHER@'],
        '@MOTHER@': [null, '@MGM@'],
      },
    });
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(['@MOTHER@']), new Set());

    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const motherCenterX = mother.x + NODE_W / 2;
    const gpBottomY = -2 * ROW_HEIGHT + NODE_H;

    // Single vertical from grandparent bottom to mother top.
    const drop = edges.find(e =>
      e.type === 'ancestor' &&
      e.x1 === motherCenterX && e.y1 === gpBottomY &&
      e.x2 === motherCenterX && e.y2 === -ROW_HEIGHT
    );
    expect(drop).toBeDefined();

    // No marriage edge at the grandparent row center y.
    const gpMidY = -2 * ROW_HEIGHT + NODE_H / 2;
    const marriageAtGpRow = edges.find(e =>
      e.type === 'marriage' && e.y1 === gpMidY
    );
    expect(marriageAtGpRow).toBeUndefined();
  });

  it('three generations expanded: umbrella pattern recurses to great-grandparents', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1995 },
        '@MOTHER@': { birth_year: 1965 },
        '@MGF@':    { birth_year: 1935 },
        '@MGM@':    { birth_year: 1937 },
        '@MGGF@':   { birth_year: 1905 },
        '@MGGM@':   { birth_year: 1907 },
      },
      parents: {
        '@FOCUS@':  [null, '@MOTHER@'],
        '@MOTHER@': ['@MGF@', '@MGM@'],
        '@MGF@':    ['@MGGF@', '@MGGM@'],
      },
    });
    const expanded = new Set(['@MOTHER@', '@MGF@']);
    const { nodes, edges } = computeLayout('@FOCUS@', expanded, new Set());

    const mgf   = nodes.find(n => n.xref === '@MGF@');
    const mggf  = nodes.find(n => n.xref === '@MGGF@');
    const mggm  = nodes.find(n => n.xref === '@MGGM@');
    expect(mggf).toBeDefined();
    expect(mggm).toBeDefined();

    const ggpMidY = -3 * ROW_HEIGHT + NODE_H / 2;
    const mgfCenterX = mgf.x + NODE_W / 2;

    // Marriage edge between great-grandparents.
    const marriageEdge = edges.find(e =>
      e.type === 'marriage' && e.y1 === ggpMidY && e.y2 === ggpMidY
    );
    expect(marriageEdge).toBeDefined();
    expect(marriageEdge.x1).toBeCloseTo(mggf.x + NODE_W, 1);
    expect(marriageEdge.x2).toBeCloseTo(mggm.x, 1);

    // Single drop from great-grandparents' marriage line midpoint (= MGF center) to MGF top.
    const drop = edges.find(e =>
      e.type === 'ancestor' &&
      e.x1 === mgfCenterX && e.y1 === ggpMidY &&
      e.x2 === mgfCenterX && e.y2 === -2 * ROW_HEIGHT
    );
    expect(drop).toBeDefined();
  });
});

// ── Test 13: Contour helpers ───────────────────────────────────────────────

describe('_requiredSeparation', () => {
  it('two leaves: sep = SLOT (adjacent at row 0)', () => {
    resetGlobals({
      people: { '@F@': {}, '@M@': {} },
      parents: {},
    });
    expect(_requiredSeparation('@F@', '@M@', new Set())).toBeCloseTo(SLOT, 1);
  });

  it('leaf vs 1-level subtree: still sep = SLOT (no collision on deeper row)', () => {
    resetGlobals({
      people: { '@F@': {}, '@M@': {}, '@MF@': {}, '@MM@': {} },
      parents: { '@M@': ['@MF@', '@MM@'] },
    });
    expect(_requiredSeparation('@F@', '@M@', new Set(['@M@']))).toBeCloseTo(SLOT, 1);
  });

  it('both 1-level subtrees: sep = 2*SLOT (row-1 widths force separation)', () => {
    resetGlobals({
      people: {
        '@F@': {}, '@M@': {},
        '@FF@': {}, '@FM@': {}, '@MF@': {}, '@MM@': {},
      },
      parents: {
        '@F@': ['@FF@', '@FM@'],
        '@M@': ['@MF@', '@MM@'],
      },
    });
    expect(_requiredSeparation('@F@', '@M@', new Set(['@F@', '@M@']))).toBeCloseTo(2 * SLOT, 1);
  });

  it('single-parent subtree: parent sits at root center, depth-1 width = 0', () => {
    // F has only one expanded parent (single-parent recursion places it at root center).
    // Collision constraint on row 1: only F's-lone-parent vs M itself → SLOT.
    resetGlobals({
      people: { '@F@': {}, '@M@': {}, '@FF@': {} },
      parents: { '@F@': ['@FF@', null] },
    });
    expect(_requiredSeparation('@F@', '@M@', new Set(['@F@']))).toBeCloseTo(SLOT, 1);
  });
});

// ── Test 14: Pietro-Elena regression — imbalanced ancestor subtrees ────────

// Regression for the bug where expanding one spouse's subtree caused the other
// (leaf) spouse to jump sideways, leaving the couple's marriage midpoint no
// longer above the child. Mirrors the user scenario:
//   Helena focus → Joseph expanded → Pietro (leaf) + Elena (expanded) → Elena's parents.
describe('computeLayout — imbalanced ancestor subtrees keep midpoint above child', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@HELENA@':  { birth_year: 1995 },
        '@JOSEPH@':  { birth_year: 1965 },
        '@MARIE@':   { birth_year: 1967 },
        '@PIETRO@':  { birth_year: 1935 },
        '@ELENA@':   { birth_year: 1937 },
        '@ELENA_F@': { birth_year: 1905 },
        '@ELENA_M@': { birth_year: 1907 },
        '@PIETRO_F@': { birth_year: 1905 },
        '@PIETRO_M@': { birth_year: 1907 },
      },
      parents: {
        '@HELENA@': ['@JOSEPH@', '@MARIE@'],
        '@JOSEPH@': ['@PIETRO@', '@ELENA@'],
        '@ELENA@':  ['@ELENA_F@', '@ELENA_M@'],
        '@PIETRO@': ['@PIETRO_F@', '@PIETRO_M@'],
      },
    });
  });

  it('Pietro (leaf) stays put when Elena expands her own subtree', () => {
    const { nodes: before } = computeLayout('@HELENA@', new Set(['@JOSEPH@']), new Set());
    const { nodes: after  } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@ELENA@']), new Set());
    const pietroBefore = before.find(n => n.xref === '@PIETRO@');
    const pietroAfter  = after.find(n => n.xref === '@PIETRO@');
    expect(pietroAfter.x).toBe(pietroBefore.x);
  });

  it('symmetric case: Elena (leaf) stays put when Pietro expands', () => {
    const { nodes: before } = computeLayout('@HELENA@', new Set(['@JOSEPH@']), new Set());
    const { nodes: after  } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@PIETRO@']), new Set());
    const elenaBefore = before.find(n => n.xref === '@ELENA@');
    const elenaAfter  = after.find(n => n.xref === '@ELENA@');
    expect(elenaAfter.x).toBe(elenaBefore.x);
  });

  it('couple marriage midpoint = child center when only Elena expands', () => {
    const { nodes } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@ELENA@']), new Set());
    const joseph = nodes.find(n => n.xref === '@JOSEPH@');
    const pietro = nodes.find(n => n.xref === '@PIETRO@');
    const elena  = nodes.find(n => n.xref === '@ELENA@');
    const marriageMidX = ((pietro.x + NODE_W) + elena.x) / 2;
    expect(marriageMidX).toBeCloseTo(joseph.x + NODE_W / 2, 1);
  });

  it('ancestor drop to child starts at child center on the marriage line', () => {
    const { nodes, edges } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@ELENA@']), new Set());
    const joseph = nodes.find(n => n.xref === '@JOSEPH@');
    const jcenter = joseph.x + NODE_W / 2;
    const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;
    const drop = edges.find(e =>
      e.type === 'ancestor' &&
      e.x1 === jcenter && e.x2 === jcenter &&
      e.y1 === parentMidY && e.y2 === -ROW_HEIGHT
    );
    expect(drop).toBeDefined();
  });

  it('balanced case (both expanded): placement unchanged from previous behaviour', () => {
    const { nodes } = computeLayout('@HELENA@', new Set(['@JOSEPH@', '@PIETRO@', '@ELENA@']), new Set());
    const joseph = nodes.find(n => n.xref === '@JOSEPH@');
    const pietro = nodes.find(n => n.xref === '@PIETRO@');
    const elena  = nodes.find(n => n.xref === '@ELENA@');
    // Both sides have 1-level subtrees → sep = 2*SLOT.
    expect(pietro.x).toBeCloseTo(joseph.x + NODE_W / 2 - SLOT - NODE_W / 2, 1);
    expect(elena.x).toBeCloseTo(joseph.x + NODE_W / 2 + SLOT - NODE_W / 2, 1);
  });
});

// ── Ancestor sibling expansion ─────────────────────────────────────────────
//
// Fixture: focus has both parents (FATHER, MOTHER). Each parent has two
// full siblings (same FAMC) and one of those siblings has a spouse.
//
//        gp_father ═══ gp_mother           (not rendered by default)
//        /    |    \
//   F_SIB1  FATHER  F_SIB2══F_SIB2_SP     (father + father's siblings)
//
//                     MOTHER ═══ father    (standard couple)
//                        |
//                      FOCUS

describe('computeLayout — ancestor sibling expansion', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@':       { birth_year: 2000, sex: 'M' },
        '@FATHER@':      { birth_year: 1970, sex: 'M' },
        '@MOTHER@':      { birth_year: 1972, sex: 'F' },
        '@F_SIB1@':      { birth_year: 1965, sex: 'M' },
        '@F_SIB2@':      { birth_year: 1975, sex: 'F' },
        '@F_SIB2_SP@':   { birth_year: 1974, sex: 'M' },
        '@M_SIB1@':      { birth_year: 1968, sex: 'F' },
        '@M_SIB2@':      { birth_year: 1976, sex: 'M' },
      },
      parents: {
        '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
        '@FATHER@': [null, null],
        '@MOTHER@': [null, null],
      },
      relatives: {
        '@FOCUS@':  { siblings: [], spouses: [] },
        '@FATHER@': { siblings: ['@F_SIB1@', '@F_SIB2@'], spouses: [] },
        '@MOTHER@': { siblings: ['@M_SIB1@', '@M_SIB2@'], spouses: [] },
        '@F_SIB1@': { siblings: [], spouses: [] },
        '@F_SIB2@': { siblings: [], spouses: ['@F_SIB2_SP@'] },
        '@M_SIB1@': { siblings: [], spouses: [] },
        '@M_SIB2@': { siblings: [], spouses: [] },
      },
    });
  });

  it('does NOT render ancestor siblings when set is empty', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
    expect(nodes.find(n => n.xref === '@F_SIB1@')).toBeUndefined();
    expect(nodes.find(n => n.xref === '@M_SIB1@')).toBeUndefined();
  });

  it('renders mother\'s siblings to the right of mother when mother is expanded', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const sib1   = nodes.find(n => n.xref === '@M_SIB1@');
    const sib2   = nodes.find(n => n.xref === '@M_SIB2@');
    expect(sib1).toBeDefined();
    expect(sib2).toBeDefined();
    expect(sib1.x).toBeGreaterThan(mother.x);
    expect(sib2.x).toBeGreaterThan(mother.x);
  });

  it('renders father\'s siblings to the left of father when father is expanded', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@']));
    const father = nodes.find(n => n.xref === '@FATHER@');
    const sib1   = nodes.find(n => n.xref === '@F_SIB1@');
    const sib2   = nodes.find(n => n.xref === '@F_SIB2@');
    expect(sib1).toBeDefined();
    expect(sib2).toBeDefined();
    expect(sib1.x).toBeLessThan(father.x);
    expect(sib2.x).toBeLessThan(father.x);
  });

  it('ancestor siblings sit at the same y as their parent-node', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const sib1   = nodes.find(n => n.xref === '@M_SIB1@');
    expect(sib1.y).toBe(mother.y);
  });

  it('ancestor siblings have role "ancestor_sibling"', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const sib = nodes.find(n => n.xref === '@M_SIB1@');
    expect(sib.role).toBe('ancestor_sibling');
  });

  it('ancestor siblings are sorted chronologically within their stack', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const sib1 = nodes.find(n => n.xref === '@M_SIB1@'); // 1968
    const sib2 = nodes.find(n => n.xref === '@M_SIB2@'); // 1976
    // On mother's right (increasing x = younger→further right): older sib closer to mother
    expect(sib1.x).toBeLessThan(sib2.x);
  });

  it('renders a sibling\'s spouse adjacent to the sibling', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    // F_SIB2 has a spouse; but we only expanded MOTHER, not FATHER.
    // Switch to father expansion to exercise the spouse rendering path.
    const { nodes: nodes2 } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@']));
    const sib2 = nodes2.find(n => n.xref === '@F_SIB2@');
    const sp   = nodes2.find(n => n.xref === '@F_SIB2_SP@');
    expect(sib2).toBeDefined();
    expect(sp).toBeDefined();
    expect(sp.role).toBe('ancestor_sibling_spouse');
    expect(sp.y).toBe(sib2.y);
  });

  it('emits a sibling_bracket edge when an ancestor\'s siblings are expanded', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const brackets = edges.filter(e => e.type === 'sibling_bracket');
    expect(brackets.length).toBeGreaterThan(0);
  });

  it('expanding both parents places each side\'s siblings on the correct outward side', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@', '@MOTHER@']));
    const father = nodes.find(n => n.xref === '@FATHER@');
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const fSib1  = nodes.find(n => n.xref === '@F_SIB1@');
    const mSib1  = nodes.find(n => n.xref === '@M_SIB1@');
    expect(fSib1.x).toBeLessThan(father.x);
    expect(mSib1.x).toBeGreaterThan(mother.x);
  });

  it('no overlap between father\'s siblings and any other node on the same row', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@FATHER@', '@MOTHER@']));
    const rowNodes = nodes.filter(n => n.y === -ROW_HEIGHT);
    const sorted = [...rowNodes].sort((a, b) => a.x - b.x);
    for (let i = 1; i < sorted.length; i++) {
      expect(sorted[i].x).toBeGreaterThanOrEqual(sorted[i - 1].x + NODE_W);
    }
  });
});

// ── Sibling umbrella (force-expand parents, umbrella spans ancestor+sibs) ──

describe('computeLayout — sibling expansion umbrella', () => {
  beforeEach(() => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 2000, sex: 'M' },
        '@FATHER@': { birth_year: 1970, sex: 'M' },
        '@MOTHER@': { birth_year: 1972, sex: 'F' },
        '@M_GF@':   { birth_year: 1945, sex: 'M' },  // mother's father
        '@M_GM@':   { birth_year: 1947, sex: 'F' },  // mother's mother
        '@M_SIB1@': { birth_year: 1968, sex: 'F' },
        '@M_SIB2@': { birth_year: 1976, sex: 'M' },
        '@M_SIB2_SP@': { birth_year: 1975, sex: 'F' },
      },
      parents: {
        '@FOCUS@':  ['@FATHER@', '@MOTHER@'],
        '@FATHER@': [null, null],
        '@MOTHER@': ['@M_GF@', '@M_GM@'],
      },
      relatives: {
        '@FOCUS@':  { siblings: [], spouses: [] },
        '@FATHER@': { siblings: [], spouses: [] },
        '@MOTHER@': { siblings: ['@M_SIB1@', '@M_SIB2@'], spouses: [] },
        '@M_SIB1@': { siblings: [], spouses: [] },
        '@M_SIB2@': { siblings: [], spouses: ['@M_SIB2_SP@'] },
      },
    });
  });

  it('force-expands the ancestor\'s parents when only siblings are expanded', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    expect(nodes.find(n => n.xref === '@M_GF@')).toBeDefined();
    expect(nodes.find(n => n.xref === '@M_GM@')).toBeDefined();
  });

  it('emits a crossbar at umbrella-y spanning leftmost to rightmost of (ancestor + siblings)', () => {
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const sib1   = nodes.find(n => n.xref === '@M_SIB1@');
    const sib2   = nodes.find(n => n.xref === '@M_SIB2@');
    const bioCenters = [mother, sib1, sib2].map(n => n.x + NODE_W / 2).sort((a, b) => a - b);
    const leftX = bioCenters[0];
    const rightX = bioCenters[bioCenters.length - 1];
    const crossbar = edges.find(e =>
      Math.abs(e.y1 - umbrellaY) < 0.5 && Math.abs(e.y2 - umbrellaY) < 0.5 &&
      Math.abs(e.x1 - leftX) < 0.5 && Math.abs(e.x2 - rightX) < 0.5
    );
    expect(crossbar).toBeDefined();
  });

  it('emits a vertical drop from umbrella to each biological child (ancestor + each sibling)', () => {
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
    const bioXrefs = ['@MOTHER@', '@M_SIB1@', '@M_SIB2@'];
    for (const xref of bioXrefs) {
      const n = nodes.find(nn => nn.xref === xref);
      const cx = n.x + NODE_W / 2;
      const drop = edges.find(e =>
        Math.abs(e.x1 - cx) < 0.5 && Math.abs(e.x2 - cx) < 0.5 &&
        Math.abs(e.y1 - umbrellaY) < 0.5 && Math.abs(e.y2 - n.y) < 0.5
      );
      expect(drop).toBeDefined();
    }
  });

  it('does NOT drop to siblings\' spouses (only biological children)', () => {
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
    const sp = nodes.find(n => n.xref === '@M_SIB2_SP@');
    expect(sp).toBeDefined();
    const cx = sp.x + NODE_W / 2;
    const dropToSpouse = edges.find(e =>
      Math.abs(e.x1 - cx) < 0.5 && Math.abs(e.x2 - cx) < 0.5 &&
      Math.abs(e.y1 - umbrellaY) < 0.5
    );
    expect(dropToSpouse).toBeUndefined();
  });

  it('anchor drop goes from parent marriage midpoint down to umbrella-y', () => {
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const umbrellaY = -ROW_HEIGHT - (ROW_HEIGHT - NODE_H) / 2;
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;
    const anchorCx = mother.x + NODE_W / 2;
    const anchor = edges.find(e =>
      Math.abs(e.x1 - anchorCx) < 0.5 && Math.abs(e.x2 - anchorCx) < 0.5 &&
      Math.abs(e.y1 - parentMidY) < 0.5 && Math.abs(e.y2 - umbrellaY) < 0.5
    );
    expect(anchor).toBeDefined();
  });

  it('does NOT emit the legacy straight drop from parent marriage to child top when siblings are expanded', () => {
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), new Set(['@MOTHER@']));
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    const cx = mother.x + NODE_W / 2;
    const parentMidY = -2 * ROW_HEIGHT + NODE_H / 2;
    // The old behavior was a drop from parentMidY down to y=-ROW_HEIGHT (mother top).
    // With umbrella, that direct drop is replaced by an anchor-to-umbrella drop.
    const legacyDrop = edges.find(e =>
      Math.abs(e.x1 - cx) < 0.5 && Math.abs(e.x2 - cx) < 0.5 &&
      Math.abs(e.y1 - parentMidY) < 0.5 && Math.abs(e.y2 - (-ROW_HEIGHT)) < 0.5
    );
    expect(legacyDrop).toBeUndefined();
  });
});
