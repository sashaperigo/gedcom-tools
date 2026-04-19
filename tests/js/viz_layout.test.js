import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Inject DESIGN as a global so viz_layout.js can read it
const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;

const { NODE_W, NODE_W_FOCUS, NODE_H, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;
// Focus-to-sibling gap: accounts for focus node being wider than NODE_W.
const FOCUS_TO_SIB = NODE_W_FOCUS / 2 + H_GAP + NODE_W / 2;

const { computeLayout, _sortByBirthYear, _packRow } = require('../../js/viz_layout.js');

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
    const result = computeLayout('@I1@', new Set(), false);
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
    const { nodes } = computeLayout('@I1@', new Set(), false);
    expect(nodes).toHaveLength(1);
  });

  it('focus node is at x=0, y=0, generation=0, role=focus', () => {
    const { nodes } = computeLayout('@I1@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const focus = nodes.find(n => n.xref === '@FOCUS@');
    expect(focus.x).toBe(0);
  });

  it('older sibling is at x = -FOCUS_TO_SIB (accounts for wider focus node)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const older = nodes.find(n => n.xref === '@OLDER@');
    expect(older).toBeDefined();
    expect(older.x).toBe(-FOCUS_TO_SIB);
  });

  it('younger sibling is at x = +FOCUS_TO_SIB (accounts for wider focus node)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const younger = nodes.find(n => n.xref === '@YOUNGER@');
    expect(younger).toBeDefined();
    expect(younger.x).toBe(FOCUS_TO_SIB);
  });

  it('all generation-0 nodes are at y=0', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const father = nodes.find(n => n.xref === '@FATHER@');
    expect(father).toBeDefined();
    expect(father.x).toBeLessThan(0);
    expect(father.y).toBe(-ROW_HEIGHT);
  });

  it('mother is at x > 0, y = -ROW_HEIGHT', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    expect(mother).toBeDefined();
    expect(mother.x).toBeGreaterThan(0);
    expect(mother.y).toBe(-ROW_HEIGHT);
  });

  it('parent nodes have generation = -1', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const parents = nodes.filter(n => n.generation === -1);
    expect(parents).toHaveLength(2);
  });

  it('edges include an ancestor edge for each parent', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    ['@C1@', '@C2@', '@C3@'].forEach(xref => {
      const child = nodes.find(n => n.xref === xref);
      expect(child).toBeDefined();
      expect(child.y).toBe(ROW_HEIGHT);
    });
  });

  it('children have generation = +1', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const children = nodes.filter(n => n.generation === 1);
    expect(children).toHaveLength(3);
  });

  it('children are centered under the focus node center', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const focus  = nodes.find(n => n.xref === '@FOCUS@');
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    expect(spouse).toBeDefined();
    expect(spouse.x).toBeGreaterThan(focus.x);
  });

  it('spouse is at x = NODE_W_FOCUS/2 + MARRIAGE_GAP + NODE_W/2 (no siblings)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    // Focus at x=0 has width NODE_W_FOCUS; right edge = NODE_W_FOCUS/2.
    // Spouse center = right edge + MARRIAGE_GAP + NODE_W/2.
    expect(spouse.x).toBe(NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2);
  });

  it('spouse has role "spouse"', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    expect(spouse.role).toBe('spouse');
  });

  it('edges include a marriage edge', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), false);
    const marriageEdges = edges.filter(e => e.type === 'marriage');
    expect(marriageEdges.length).toBeGreaterThanOrEqual(1);
  });

  it('marriage edge x1 is the right edge of the focus node (no siblings)', () => {
    const { edges } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), true);
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    const ss1    = nodes.find(n => n.xref === '@SS1@');
    const ss2    = nodes.find(n => n.xref === '@SS2@');
    expect(ss1).toBeDefined();
    expect(ss2).toBeDefined();
    expect(ss1.x).toBeGreaterThan(spouse.x);
    expect(ss2.x).toBeGreaterThan(spouse.x);
  });

  it('first spouse sibling is exactly one SLOT to the right of the spouse', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), true);
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    // spouse siblings sorted by birth_year; @SS1@ (1895) comes first
    const ss1 = nodes.find(n => n.xref === '@SS1@');
    expect(ss1.x).toBe(spouse.x + NODE_W + H_GAP);
  });

  it('spouse siblings have role "spouse_sibling"', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), true);
    const spouseSibs = nodes.filter(n => n.role === 'spouse_sibling');
    expect(spouseSibs).toHaveLength(2);
  });

  it('spouse siblings do NOT appear when spouseSiblingsExpanded is false', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { edges } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);
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

    const { nodes } = computeLayout('@FOCUS@', new Set(), true);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@']), false);
    const gff = nodes.find(n => n.xref === '@GFF@');
    const gfm = nodes.find(n => n.xref === '@GFM@');
    expect(gff).toBeDefined();
    expect(gfm).toBeDefined();
    expect(gff.y).toBe(-2 * ROW_HEIGHT);
    expect(gfm.y).toBe(-2 * ROW_HEIGHT);
  });

  it('grandparents do NOT appear when father is NOT in expandedAncestors', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const gff = nodes.find(n => n.xref === '@GFF@');
    expect(gff).toBeUndefined();
  });

  it('grandparent nodes have generation = -2', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(['@FATHER@']), false);
    const grandparents = nodes.filter(n => n.generation === -2);
    expect(grandparents).toHaveLength(2);
  });
});

// ── Test 8: Only one parent ────────────────────────────────────────────────

describe('computeLayout — single parent', () => {
  it('single mother is centered above focus at x=0', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@MOTHER@': { birth_year: 1870 },
      },
      parents: { '@FOCUS@': [null, '@MOTHER@'] },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const mother = nodes.find(n => n.xref === '@MOTHER@');
    expect(mother).toBeDefined();
    expect(mother.x).toBe(0);
    expect(mother.y).toBe(-ROW_HEIGHT);
  });

  it('single father is centered above focus at x=0', () => {
    resetGlobals({
      people: {
        '@FOCUS@':  { birth_year: 1900 },
        '@FATHER@': { birth_year: 1870 },
      },
      parents: { '@FOCUS@': ['@FATHER@', null] },
    });
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const father = nodes.find(n => n.xref === '@FATHER@');
    expect(father).toBeDefined();
    expect(father.x).toBe(0);
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
    const { nodes } = computeLayout('@FOCUS@', expanded, false);
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
    const { nodes } = computeLayout('@FOCUS@', expanded, false);
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
    const { nodes } = computeLayout('@FOCUS@', expanded, false);
    const gen3 = nodes.filter(n => n.generation === -3).sort((a, b) => a.x - b.x);
    expect(gen3).toHaveLength(4);
    for (let i = 1; i < gen3.length; i++) {
      expect(gen3[i].x - gen3[i - 1].x).toBeCloseTo(SLOT, 1);
    }
  });

  it('unexpanded ancestor keeps symmetric ±SLOT/2 placement (backward compat)', () => {
    // Only @MOTHER@ expanded (neither of her parents is expanded)
    const expanded = new Set(['@MOTHER@']);
    const { nodes } = computeLayout('@FOCUS@', expanded, false);
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);

    const focusCenter  = NODE_W_FOCUS / 2;                       // 80
    const spouseX      = NODE_W_FOCUS / 2 + MARRIAGE_GAP + NODE_W / 2; // 210 (left edge)
    const spouseCenter = spouseX + NODE_W / 2;                   // 280
    const anchorX      = (focusCenter + spouseCenter) / 2;       // 180

    const c1 = nodes.find(n => n.xref === '@C1@');
    expect(c1).toBeDefined();
    expect(c1.x + NODE_W / 2).toBeCloseTo(anchorX, 1);

    const descEdges = edges.filter(e => e.type === 'descendant');
    // Anchor drop: (anchorX, NODE_H) → (anchorX, umbrellaY)
    const anchorDrop = descEdges.find(e =>
      e.x1 === anchorX && e.y1 === NODE_H && e.x2 === anchorX && e.y2 === UMBRELLA_Y
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);
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

    const anchorDrop = descEdges.find(e =>
      e.x1 === anchorX && e.y1 === NODE_H && e.x2 === anchorX && e.y2 === UMBRELLA_Y
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);
    const sp = nodes.find(n => n.xref === '@C1SP@');
    expect(sp).toBeDefined();
    expect(sp.role).toBe('descendant_spouse');
    expect(sp.y).toBe(ROW_HEIGHT);

    const c1 = nodes.find(n => n.xref === '@C1@');
    // Spouse sits NODE_W + MARRIAGE_GAP to the right of the child (left edges)
    expect(sp.x).toBeCloseTo(c1.x + NODE_W + MARRIAGE_GAP, 1);

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
    const { edges } = computeLayout('@FOCUS@', new Set(), false);
    const anchorX = NODE_W_FOCUS / 2;
    const anchorDrop = edges.find(e =>
      e.type === 'descendant' &&
      e.x1 === anchorX && e.y1 === NODE_H && e.x2 === anchorX && e.y2 === (NODE_H + (ROW_HEIGHT - NODE_H) / 2)
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
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
    const { nodes, edges } = computeLayout('@FOCUS@', new Set(), false);
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
