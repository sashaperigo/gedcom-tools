import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Inject DESIGN as a global so viz_layout.js can read it
const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;

const { NODE_W, NODE_H, ROW_HEIGHT, H_GAP, MARRIAGE_GAP } = DESIGN;

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

  it('older sibling is at x = -(NODE_W + H_GAP)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const older = nodes.find(n => n.xref === '@OLDER@');
    expect(older).toBeDefined();
    expect(older.x).toBe(-(NODE_W + H_GAP));
  });

  it('younger sibling is at x = +(NODE_W + H_GAP)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const younger = nodes.find(n => n.xref === '@YOUNGER@');
    expect(younger).toBeDefined();
    expect(younger.x).toBe(NODE_W + H_GAP);
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
    const focusCenterX = focus.x + NODE_W / 2;
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

  it('spouse is at x = NODE_W + MARRIAGE_GAP (no siblings)', () => {
    const { nodes } = computeLayout('@FOCUS@', new Set(), false);
    const spouse = nodes.find(n => n.xref === '@SPOUSE@');
    // maxSiblingX is focus.x (=0) + NODE_W; then add MARRIAGE_GAP offset from right edge
    // Per spec: spouse x = maxSiblingX + NODE_W + MARRIAGE_GAP — actually
    // maxSiblingX = max x of all nodes placed (focus at 0), so
    // spouse.x = 0 + NODE_W + MARRIAGE_GAP
    expect(spouse.x).toBe(NODE_W + MARRIAGE_GAP);
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
