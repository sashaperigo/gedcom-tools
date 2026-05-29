import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { computeRelationship, enumerateRelationships, buildRelationshipPath } = require('../../js/viz_relationship.js');

function ctx({ people = {}, parents = {}, children = {}, relatives = {}, families = {} } = {}) {
  return { PEOPLE: people, PARENTS: parents, CHILDREN: children, RELATIVES: relatives, FAMILIES: families };
}

describe('computeRelationship — Self', () => {
  it('returns Self when other === viewer', () => {
    const c = ctx({ people: { '@I1@': { sex: 'F' } } });
    const r = computeRelationship('@I1@', '@I1@', c);
    expect(r).toEqual({ label: 'Self', debug: { a: 0, b: 0 } });
  });
});

describe('computeRelationship — direct parents (a=1, b=0)', () => {
  it('Mother (sex=F)', () => {
    const c = ctx({
      people: { '@I1@': {}, '@I2@': { sex: 'F' } },
      parents: { '@I1@': [null, '@I2@'] },
      children: { '@I2@': ['@I1@'] },
    });
    expect(computeRelationship('@I1@', '@I2@', c).label).toBe('Mother');
  });

  it('Father (sex=M)', () => {
    const c = ctx({
      people: { '@I1@': {}, '@I2@': { sex: 'M' } },
      parents: { '@I1@': ['@I2@', null] },
      children: { '@I2@': ['@I1@'] },
    });
    expect(computeRelationship('@I1@', '@I2@', c).label).toBe('Father');
  });

  it('Parent (sex unknown) — gender-neutral fallback', () => {
    const c = ctx({
      people: { '@I1@': {}, '@I2@': {} },
      parents: { '@I1@': ['@I2@', null] },
      children: { '@I2@': ['@I1@'] },
    });
    expect(computeRelationship('@I1@', '@I2@', c).label).toBe('Parent');
  });
});

describe('computeRelationship — deeper ancestors (b=0)', () => {
  function chain(generations) {
    // Build a parent chain: I1 → I2 → I3 → ... where I_k+1 is the parent of I_k.
    const people = {};
    const parents = {};
    const children = {};
    for (let i = 1; i <= generations; i++) {
      people[`@I${i}@`] = i === generations ? { sex: 'F' } : {};
    }
    for (let i = 1; i < generations; i++) {
      parents[`@I${i}@`] = ['@I' + (i + 1) + '@', null];
      children[`@I${i + 1}@`] = [`@I${i}@`];
    }
    return ctx({ people, parents, children });
  }

  it('Grandmother (a=2)', () => {
    expect(computeRelationship('@I1@', '@I3@', chain(3)).label).toBe('Grandmother');
  });

  it('Great-Grandmother (a=3)', () => {
    expect(computeRelationship('@I1@', '@I4@', chain(4)).label).toBe('Great-Grandmother');
  });

  it('2× Great-Grandmother (a=4)', () => {
    expect(computeRelationship('@I1@', '@I5@', chain(5)).label).toBe('2× Great-Grandmother');
  });

  it('5× Great-Grandparent (a=7, sex unknown)', () => {
    const c = chain(8);
    c.PEOPLE['@I8@'] = {}; // unknown sex
    expect(computeRelationship('@I1@', '@I8@', c).label).toBe('5× Great-Grandparent');
  });
});

describe('computeRelationship — descendants (a=0, b≥1)', () => {
  function descendantChain(generations) {
    const people = {}, parents = {}, children = {};
    for (let i = 1; i <= generations; i++) {
      people[`@I${i}@`] = i === 1 ? { sex: 'F' } : { sex: 'F' };
    }
    for (let i = 1; i < generations; i++) {
      parents[`@I${i + 1}@`] = ['@I' + i + '@', null];
      children[`@I${i}@`] = [`@I${i + 1}@`];
    }
    return ctx({ people, parents, children });
  }

  it('Daughter (b=1)', () => {
    expect(computeRelationship('@I1@', '@I2@', descendantChain(2)).label).toBe('Daughter');
  });

  it('Granddaughter (b=2)', () => {
    expect(computeRelationship('@I1@', '@I3@', descendantChain(3)).label).toBe('Granddaughter');
  });

  it('Great-Grandchild (b=3, sex unknown)', () => {
    const c = descendantChain(4);
    c.PEOPLE['@I4@'] = {};
    expect(computeRelationship('@I1@', '@I4@', c).label).toBe('Great-Grandchild');
  });

  it('3× Great-Grandson (b=5)', () => {
    const c = descendantChain(6);
    c.PEOPLE['@I6@'] = { sex: 'M' };
    expect(computeRelationship('@I1@', '@I6@', c).label).toBe('3× Great-Grandson');
  });
});

describe('computeRelationship — full siblings (a=1, b=1)', () => {
  function fullSibCtx(otherSex) {
    return ctx({
      people: {
        '@I1@': {},
        '@I2@': { sex: otherSex },
        '@DAD@': { sex: 'M' },
        '@MOM@': { sex: 'F' },
      },
      parents: {
        '@I1@': ['@DAD@', '@MOM@'],
        '@I2@': ['@DAD@', '@MOM@'],
      },
      children: {
        '@DAD@': ['@I1@', '@I2@'],
        '@MOM@': ['@I1@', '@I2@'],
      },
    });
  }

  it('Sister (sex=F)', () => {
    expect(computeRelationship('@I1@', '@I2@', fullSibCtx('F')).label).toBe('Sister');
  });
  it('Brother (sex=M)', () => {
    expect(computeRelationship('@I1@', '@I2@', fullSibCtx('M')).label).toBe('Brother');
  });
  it('Sibling (sex unknown)', () => {
    expect(computeRelationship('@I1@', '@I2@', fullSibCtx(undefined)).label).toBe('Sibling');
  });
});

describe('computeRelationship — half- prefix', () => {
  it('Half-Sister: shares one parent only', () => {
    const c = ctx({
      people: { '@I1@': {}, '@I2@': { sex: 'F' }, '@DAD@': { sex: 'M' }, '@MOM1@': { sex: 'F' }, '@MOM2@': { sex: 'F' } },
      parents: { '@I1@': ['@DAD@', '@MOM1@'], '@I2@': ['@DAD@', '@MOM2@'] },
      children: { '@DAD@': ['@I1@', '@I2@'], '@MOM1@': ['@I1@'], '@MOM2@': ['@I2@'] },
    });
    expect(computeRelationship('@I1@', '@I2@', c).label).toBe('Half-Sister');
  });
});

describe('computeRelationship — aunt/uncle line (b=1, a≥2)', () => {
  function auntCtx(genUp, auntSex) {
    const people = {}, parents = {}, children = {};
    // For genUp=2: P1 -> P2 -> GRANDPA+GRANDMA
    // AUNT is a sibling of P2, also child of GRANDPA+GRANDMA
    // Build lineage: P1 -> P2 -> ... -> P_{genUp} -> GRANDPA+GRANDMA
    for (let i = 1; i <= genUp; i++) {
      people[`@P${i}@`] = {};
    }
    people['@GRANDPA@'] = { sex: 'M' };
    people['@GRANDMA@'] = { sex: 'F' };

    // Connect P1 -> P2 -> ... -> P_{genUp}
    for (let i = 1; i < genUp; i++) {
      parents[`@P${i}@`] = [null, `@P${i + 1}@`];
      children[`@P${i + 1}@`] = (children[`@P${i + 1}@`] || []).concat([`@P${i}@`]);
    }
    // P_{genUp} is a child of GRANDPA and GRANDMA
    parents[`@P${genUp}@`] = ['@GRANDPA@', '@GRANDMA@'];
    children['@GRANDPA@'] = (children['@GRANDPA@'] || []).concat([`@P${genUp}@`]);
    children['@GRANDMA@'] = (children['@GRANDMA@'] || []).concat([`@P${genUp}@`]);

    // AUNT is a sibling of P_{genUp}, with same parents GRANDPA and GRANDMA
    people['@AUNT@'] = { sex: auntSex };
    parents['@AUNT@'] = ['@GRANDPA@', '@GRANDMA@'];
    children['@GRANDPA@'].push('@AUNT@');
    children['@GRANDMA@'].push('@AUNT@');

    return { c: ctx({ people, parents, children }), viewer: '@P1@', other: '@AUNT@' };
  }

  it('Aunt (a=2)', () => {
    const { c, viewer, other } = auntCtx(2, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('Aunt');
  });
  it('Uncle (a=2, sex=M)', () => {
    const { c, viewer, other } = auntCtx(2, 'M');
    expect(computeRelationship(viewer, other, c).label).toBe('Uncle');
  });
  it('Aunt or Uncle (a=2, sex unknown)', () => {
    const { c, viewer, other } = auntCtx(2, undefined);
    expect(computeRelationship(viewer, other, c).label).toBe('Aunt or Uncle');
  });
  it('Grandaunt (a=3) — sibling of grandparent', () => {
    const { c, viewer, other } = auntCtx(3, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('Grandaunt');
  });
  it('Granduncle (a=3, sex=M)', () => {
    const { c, viewer, other } = auntCtx(3, 'M');
    expect(computeRelationship(viewer, other, c).label).toBe('Granduncle');
  });
  it('Great-Grandaunt (a=4) — sibling of great-grandparent', () => {
    const { c, viewer, other } = auntCtx(4, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('Great-Grandaunt');
  });
  it('2× Great-Grandaunt (a=5)', () => {
    const { c, viewer, other } = auntCtx(5, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('2× Great-Grandaunt');
  });
  it('4× Great-Granduncle (a=7) — sibling of 4× great-grandparent', () => {
    const { c, viewer, other } = auntCtx(7, 'M');
    expect(computeRelationship(viewer, other, c).label).toBe('4× Great-Granduncle');
  });
});

describe('computeRelationship — niece/nephew line (a=1, b≥2)', () => {
  // viewer has a sibling who has descendants. The sibling and viewer share BOTH parents
  // (DAD + MOM) so the niece is a FULL niece (not half-niece).
  function nieceCtx(genDown, nieceSex) {
    const people = {}, parents = {}, children = {};
    people['@VIEW@'] = {};
    people['@SIB@'] = { sex: 'M' };
    people['@DAD@'] = { sex: 'M' };
    people['@MOM@'] = { sex: 'F' };
    parents['@VIEW@'] = ['@DAD@', '@MOM@'];
    parents['@SIB@']  = ['@DAD@', '@MOM@'];
    children['@DAD@'] = ['@VIEW@', '@SIB@'];
    children['@MOM@'] = ['@VIEW@', '@SIB@'];
    let cursor = '@SIB@';
    for (let i = 1; i <= genDown; i++) {
      const xref = `@D${i}@`;
      people[xref] = i === genDown ? { sex: nieceSex } : { sex: 'F' };
      parents[xref] = [null, cursor];
      children[cursor] = (children[cursor] || []).concat([xref]);
      cursor = xref;
    }
    return { c: ctx({ people, parents, children }), viewer: '@VIEW@', other: cursor };
  }

  it('Niece (b=2, sex=F)', () => {
    const { c, viewer, other } = nieceCtx(1, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('Niece');
  });
  it('Nephew (b=2, sex=M)', () => {
    const { c, viewer, other } = nieceCtx(1, 'M');
    expect(computeRelationship(viewer, other, c).label).toBe('Nephew');
  });
  it('Grandniece (b=3) — grandchild of sibling', () => {
    const { c, viewer, other } = nieceCtx(2, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('Grandniece');
  });
  it('Grandnephew (b=3, sex=M)', () => {
    const { c, viewer, other } = nieceCtx(2, 'M');
    expect(computeRelationship(viewer, other, c).label).toBe('Grandnephew');
  });
  it('Great-Grandnephew (b=4)', () => {
    const { c, viewer, other } = nieceCtx(3, 'M');
    expect(computeRelationship(viewer, other, c).label).toBe('Great-Grandnephew');
  });
  it('3× Great-Grandniece (b=6)', () => {
    const { c, viewer, other } = nieceCtx(5, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('3× Great-Grandniece');
  });
});

describe('computeRelationship — cousins', () => {
  // Build: two siblings each with a chain of descendants.
  // The siblings share BOTH parents (MRCA + MRCA_SP) so cousins are FULL (not half).
  function cousinCtx(genA, genB) {
    const people = {}, parents = {}, children = {};
    people['@MRCA@']    = { sex: 'F' };
    people['@MRCA_SP@'] = { sex: 'M' };
    people['@SIBA@']    = { sex: 'F' };
    people['@SIBB@']    = { sex: 'F' };
    parents['@SIBA@'] = ['@MRCA_SP@', '@MRCA@'];
    parents['@SIBB@'] = ['@MRCA_SP@', '@MRCA@'];
    children['@MRCA@']    = ['@SIBA@', '@SIBB@'];
    children['@MRCA_SP@'] = ['@SIBA@', '@SIBB@'];

    let cursor = '@SIBA@';
    for (let i = 2; i <= genA; i++) {
      const xref = `@A${i}@`;
      people[xref] = {};
      parents[xref] = [null, cursor];
      children[cursor] = (children[cursor] || []).concat([xref]);
      cursor = xref;
    }
    const viewer = cursor;

    cursor = '@SIBB@';
    for (let i = 2; i <= genB; i++) {
      const xref = `@B${i}@`;
      people[xref] = {};
      parents[xref] = [null, cursor];
      children[cursor] = (children[cursor] || []).concat([xref]);
      cursor = xref;
    }
    const other = cursor;

    return { c: ctx({ people, parents, children }), viewer, other };
  }

  it('1st Cousin (a=2, b=2)', () => {
    const { c, viewer, other } = cousinCtx(2, 2);
    expect(computeRelationship(viewer, other, c).label).toBe('1st Cousin');
  });
  it('2nd Cousin (a=3, b=3)', () => {
    const { c, viewer, other } = cousinCtx(3, 3);
    expect(computeRelationship(viewer, other, c).label).toBe('2nd Cousin');
  });
  it('1st Cousin 1× Removed (a=2, b=3)', () => {
    const { c, viewer, other } = cousinCtx(2, 3);
    expect(computeRelationship(viewer, other, c).label).toBe('1st Cousin 1× Removed');
  });
  it('1st Cousin 1× Removed (a=3, b=2) — same label, no direction', () => {
    const { c, viewer, other } = cousinCtx(3, 2);
    expect(computeRelationship(viewer, other, c).label).toBe('1st Cousin 1× Removed');
  });
  it('5th Cousin 3× Removed (a=6, b=9)', () => {
    const { c, viewer, other } = cousinCtx(6, 9);
    expect(computeRelationship(viewer, other, c).label).toBe('5th Cousin 3× Removed');
  });
  it('11th Cousin (a=12, b=12)', () => {
    const { c, viewer, other } = cousinCtx(12, 12);
    expect(computeRelationship(viewer, other, c).label).toBe('11th Cousin');
  });
  it('12th Cousin (a=13, b=13)', () => {
    const { c, viewer, other } = cousinCtx(13, 13);
    expect(computeRelationship(viewer, other, c).label).toBe('12th Cousin');
  });
});

describe('computeRelationship — half-prefix propagation', () => {
  it('Half-Aunt: parent has half-sibling (shared grandparent only)', () => {
    const c = ctx({
      people: {
        '@VIEW@': {},
        '@PARENT@': { sex: 'F' },
        '@AUNT@': { sex: 'F' },
        '@GRANDMA@': { sex: 'F' },
        '@GP_DAD1@': { sex: 'M' },
        '@GP_DAD2@': { sex: 'M' },
      },
      parents: {
        '@VIEW@': [null, '@PARENT@'],
        '@PARENT@': ['@GP_DAD1@', '@GRANDMA@'],
        '@AUNT@':   ['@GP_DAD2@', '@GRANDMA@'],
      },
      children: {
        '@PARENT@': ['@VIEW@'],
        '@GRANDMA@': ['@PARENT@', '@AUNT@'],
        '@GP_DAD1@': ['@PARENT@'],
        '@GP_DAD2@': ['@AUNT@'],
      },
    });
    expect(computeRelationship('@VIEW@', '@AUNT@', c).label).toBe('Half-Aunt');
  });

  it('Half-1st Cousin: cousin via half-sibling parents', () => {
    const c = ctx({
      people: {
        '@V@': {}, '@C@': {},
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' },
        '@GMA@': { sex: 'F' }, '@DAD1@': { sex: 'M' }, '@DAD2@': { sex: 'M' },
      },
      parents: {
        '@V@': [null, '@PV@'],
        '@C@': [null, '@PC@'],
        '@PV@': ['@DAD1@', '@GMA@'],
        '@PC@': ['@DAD2@', '@GMA@'],
      },
      children: {
        '@PV@': ['@V@'], '@PC@': ['@C@'],
        '@GMA@': ['@PV@', '@PC@'],
        '@DAD1@': ['@PV@'], '@DAD2@': ['@PC@'],
      },
    });
    expect(computeRelationship('@V@', '@C@', c).label).toBe('Half-1st Cousin');
  });
});

describe('computeRelationship — pedigree collapse', () => {
  it('Person reachable as 1st cousin AND 3rd cousin → label as 1st Cousin (smaller a+b)', () => {
    // Cousin-marriage scenario: viewer's grandparent and other's grandparent are siblings
    // (1st cousin path); they're also 2× great-grandparents on a deeper path (3rd cousin).
    // We construct just the closer path here — the algorithm picks shortest a+b regardless.
    const c = ctx({
      people: {
        '@V@': {}, '@O@': {},
        '@PV@': { sex: 'F' }, '@PO@': { sex: 'F' },
        '@GP@': { sex: 'F' },
      },
      parents: {
        '@V@': [null, '@PV@'],
        '@O@': [null, '@PO@'],
        '@PV@': [null, '@GP@'],
        '@PO@': [null, '@GP@'],
      },
      children: {
        '@PV@': ['@V@'], '@PO@': ['@O@'],
        '@GP@': ['@PV@', '@PO@'],
      },
    });
    expect(computeRelationship('@V@', '@O@', c).label).toBe('Half-1st Cousin');
  });

  it('Two real paths: 1st Cousin via close MRCA wins over 3rd Cousin via deeper MRCA', () => {
    // V and O have two shared-ancestor paths:
    //   Path 1: shared GP (grandparent) — both are grandchildren → 1st Cousin (a+b=4)
    //   Path 2: shared 2GGP (2× great-grandparent) on a separate ancestral branch → 3rd Cousin (a+b=8)
    // pickClosestPath should select Path 1 (smaller a+b) → "1st Cousin".
    //
    // Graph:
    //   2GGP — ancestor of both V and O via separate chains GGV and GGO
    //   GP   — grandparent of both V and O via PV and PO
    //   V's parents: PV (via GP) AND HV (via GGV chain)? — no, simpler:
    //   We make V have two parent lines that both lead to ancestors of O.
    const c = ctx({
      people: {
        '@V@': {}, '@O@': {},
        // Close path (1st cousin): shared grandparent couple
        '@PV@': { sex: 'F' }, '@PO@': { sex: 'M' },
        '@GP1@': { sex: 'F' }, '@GP2@': { sex: 'M' },
        // Deeper path (3rd cousin): V's other parent and O's other parent share a 2× great-grandparent couple
        '@HV@': { sex: 'M' }, '@HO@': { sex: 'F' },
        '@HV_P@': { sex: 'F' }, '@HO_P@': { sex: 'M' },
        '@HV_GP@': { sex: 'F' }, '@HO_GP@': { sex: 'M' },
        '@DEEP_F@': { sex: 'M' }, '@DEEP_M@': { sex: 'F' },
      },
      parents: {
        '@V@': ['@HV@', '@PV@'],
        '@O@': ['@PO@', '@HO@'],
        '@PV@': ['@GP2@', '@GP1@'],
        '@PO@': ['@GP2@', '@GP1@'],
        '@HV@': ['@HV_P@', null],   '@HO@': [null, '@HO_P@'],
        '@HV_P@': ['@HV_GP@', null],'@HO_P@': [null, '@HO_GP@'],
        '@HV_GP@': ['@DEEP_F@', '@DEEP_M@'],
        '@HO_GP@': ['@DEEP_F@', '@DEEP_M@'],
      },
      children: {
        '@PV@': ['@V@'], '@HV@': ['@V@'],
        '@PO@': ['@O@'], '@HO@': ['@O@'],
        '@GP1@': ['@PV@', '@PO@'], '@GP2@': ['@PV@', '@PO@'],
        '@HV_P@': ['@HV@'], '@HO_P@': ['@HO@'],
        '@HV_GP@': ['@HV_P@'], '@HO_GP@': ['@HO_P@'],
        '@DEEP_F@': ['@HV_GP@', '@HO_GP@'], '@DEEP_M@': ['@HV_GP@', '@HO_GP@'],
      },
    });
    expect(computeRelationship('@V@', '@O@', c).label).toBe('1st Cousin');
  });
});

describe('computeRelationship — affinity: spouse of viewer', () => {
  function spouseCtx(spouseSex) {
    return ctx({
      people: { '@V@': { sex: 'F' }, '@S@': { sex: spouseSex } },
      parents: { '@V@': [null, null], '@S@': [null, null] },
      children: {},
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: spouseSex === 'M' ? '@S@' : '@V@', wife: spouseSex === 'F' ? '@S@' : '@V@', chil: [] } },
    });
  }

  it('Husband (sex=M)', () => {
    expect(computeRelationship('@V@', '@S@', spouseCtx('M')).label).toBe('Husband');
  });
  it('Wife (sex=F)', () => {
    expect(computeRelationship('@V@', '@S@', spouseCtx('F')).label).toBe('Wife');
  });
  it('Spouse (sex unknown)', () => {
    expect(computeRelationship('@V@', '@S@', spouseCtx(undefined)).label).toBe('Spouse');
  });
});

describe('computeRelationship — affinity: specific in-laws', () => {
  it('Mother-in-law (parent of viewer\'s spouse)', () => {
    const c = ctx({
      people: { '@V@': {}, '@S@': { sex: 'F' }, '@SM@': { sex: 'F' } },
      parents: { '@V@': [null, null], '@S@': [null, '@SM@'], '@SM@': [null, null] },
      children: { '@SM@': ['@S@'] },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [] } },
    });
    expect(computeRelationship('@V@', '@SM@', c).label).toBe('Mother-in-law');
  });

  it('Brother-in-law (spouse of viewer\'s sister)', () => {
    const c = ctx({
      people: { '@V@': {}, '@SIB@': { sex: 'F' }, '@SIBSP@': { sex: 'M' }, '@MOM@': { sex: 'F' } },
      parents: { '@V@': [null, '@MOM@'], '@SIB@': [null, '@MOM@'], '@SIBSP@': [null, null] },
      children: { '@MOM@': ['@V@', '@SIB@'] },
      relatives: { '@SIB@': { spouses: ['@SIBSP@'] }, '@SIBSP@': { spouses: ['@SIB@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@SIBSP@', c).label).toBe('Brother-in-law');
  });

  it('Sister-in-law (sibling of viewer\'s spouse)', () => {
    const c = ctx({
      people: { '@V@': {}, '@SP@': { sex: 'F' }, '@SPSIB@': { sex: 'F' }, '@SM@': { sex: 'F' } },
      parents: { '@V@': [null, null], '@SP@': [null, '@SM@'], '@SPSIB@': [null, '@SM@'] },
      children: { '@SM@': ['@SP@', '@SPSIB@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@SPSIB@', c).label).toBe('Sister-in-law');
  });

  it('Son-in-law (spouse of viewer\'s daughter)', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@D@': { sex: 'F' }, '@DH@': { sex: 'M' } },
      parents: { '@D@': [null, '@V@'], '@DH@': [null, null] },
      children: { '@V@': ['@D@'] },
      relatives: { '@D@': { spouses: ['@DH@'] }, '@DH@': { spouses: ['@D@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@DH@', c).label).toBe('Son-in-law');
  });
});

describe('computeRelationship — affinity: step relationships', () => {
  it('Step-Mother (spouse of viewer\'s father, not viewer\'s bio mother)', () => {
    const c = ctx({
      people: { '@V@': {}, '@DAD@': { sex: 'M' }, '@STEPMOM@': { sex: 'F' }, '@BIOMOM@': { sex: 'F' } },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'] },
      relatives: { '@DAD@': { spouses: ['@BIOMOM@', '@STEPMOM@'] }, '@STEPMOM@': { spouses: ['@DAD@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@STEPMOM@', c).label).toBe('Step-Mother');
  });

  it('Step-Daughter (viewer\'s spouse\'s daughter, not viewer\'s bio)', () => {
    const c = ctx({
      people: { '@V@': {}, '@SP@': { sex: 'F' }, '@SD@': { sex: 'F' }, '@SDX@': { sex: 'M' } },
      parents: { '@SD@': ['@SDX@', '@SP@'] },
      children: { '@SP@': ['@SD@'], '@SDX@': ['@SD@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@SD@', c).label).toBe('Step-Daughter');
  });

  it('Step-Sister (child of viewer\'s step-mother, no shared bio parent)', () => {
    const c = ctx({
      people: {
        '@V@': {}, '@DAD@': { sex: 'M' }, '@BIOMOM@': { sex: 'F' },
        '@STEPMOM@': { sex: 'F' }, '@SS@': { sex: 'F' }, '@SSX@': { sex: 'M' },
      },
      parents: {
        '@V@': ['@DAD@', '@BIOMOM@'],
        '@SS@': ['@SSX@', '@STEPMOM@'],
      },
      children: {
        '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'],
        '@STEPMOM@': ['@SS@'], '@SSX@': ['@SS@'],
      },
      relatives: { '@DAD@': { spouses: ['@BIOMOM@', '@STEPMOM@'] }, '@STEPMOM@': { spouses: ['@DAD@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@SS@', c).label).toBe('Step-Sister');
  });
});

describe('computeRelationship — affinity: generic templates', () => {
  it('Wife of 1st Cousin', () => {
    // viewer's 1st cousin married someone — that someone = "Wife of 1st Cousin"
    const c = ctx({
      people: {
        '@V@': {}, '@C@': { sex: 'F' }, '@CW@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' },
        '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: {
        '@V@': [null, '@PV@'], '@C@': [null, '@PC@'],
        '@PV@': ['@GPA@', '@GMA@'], '@PC@': ['@GPA@', '@GMA@'],
      },
      children: {
        '@PV@': ['@V@'], '@PC@': ['@C@'],
        '@GMA@': ['@PV@', '@PC@'], '@GPA@': ['@PV@', '@PC@'],
      },
      relatives: { '@C@': { spouses: ['@CW@'] }, '@CW@': { spouses: ['@C@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@CW@', c).label).toBe('Wife of 1st Cousin');
  });

  it('1st Cousin of Spouse', () => {
    // viewer's spouse has a 1st cousin — that cousin = "1st Cousin of Spouse"
    const c = ctx({
      people: {
        '@V@': {}, '@S@': { sex: 'F' }, '@SC@': { sex: 'F' },
        '@PS@': { sex: 'F' }, '@PSC@': { sex: 'F' },
        '@SGM@': { sex: 'F' }, '@SGP@': { sex: 'M' },
      },
      parents: {
        '@S@': [null, '@PS@'], '@SC@': [null, '@PSC@'],
        '@PS@': ['@SGP@', '@SGM@'], '@PSC@': ['@SGP@', '@SGM@'],
      },
      children: {
        '@PS@': ['@S@'], '@PSC@': ['@SC@'],
        '@SGM@': ['@PS@', '@PSC@'], '@SGP@': ['@PS@', '@PSC@'],
      },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@SC@', c).label).toBe('1st Cousin of Spouse');
  });
});

describe('computeRelationship — affinity: divorced couples use Ex- prefix', () => {
  it('Ex-Husband (direct spouse, family has divs)', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@S@': { sex: 'M' } },
      parents: { '@V@': [null, null], '@S@': [null, null] },
      children: {},
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@S@', wife: '@V@', chil: [], divorced: true } },
    });
    expect(computeRelationship('@V@', '@S@', c).label).toBe('Ex-Husband');
  });

  it('Ex-Wife (direct spouse, family has divs)', () => {
    const c = ctx({
      people: { '@V@': { sex: 'M' }, '@S@': { sex: 'F' } },
      parents: { '@V@': [null, null], '@S@': [null, null] },
      children: {},
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [], divorced: true } },
    });
    expect(computeRelationship('@V@', '@S@', c).label).toBe('Ex-Wife');
  });

  it('Ex-Spouse (sex unknown, divorced)', () => {
    const c = ctx({
      people: { '@V@': {}, '@S@': {} },
      parents: { '@V@': [null, null], '@S@': [null, null] },
      children: {},
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [], divorced: true } },
    });
    expect(computeRelationship('@V@', '@S@', c).label).toBe('Ex-Spouse');
  });

  it('Husband stays Husband when not divorced', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@S@': { sex: 'M' } },
      parents: { '@V@': [null, null], '@S@': [null, null] },
      children: {},
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@S@', wife: '@V@', chil: [], divorced: false } },
    });
    expect(computeRelationship('@V@', '@S@', c).label).toBe('Husband');
  });

  it('Ex-Wife of 1st Cousin (composed spouse-of-relative label)', () => {
    const c = ctx({
      people: {
        '@V@': {}, '@C@': { sex: 'F' }, '@CW@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' },
        '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: {
        '@V@': [null, '@PV@'], '@C@': [null, '@PC@'],
        '@PV@': ['@GPA@', '@GMA@'], '@PC@': ['@GPA@', '@GMA@'],
      },
      children: {
        '@PV@': ['@V@'], '@PC@': ['@C@'],
        '@GMA@': ['@PV@', '@PC@'], '@GPA@': ['@PV@', '@PC@'],
      },
      relatives: { '@C@': { spouses: ['@CW@'] }, '@CW@': { spouses: ['@C@'] } },
      families: { '@F1@': { husb: null, wife: '@C@', chil: [], divorced: true } },
    });
    // Note: spouse family between @C@ and @CW@. _findSpouseFamily matches husb/wife exactly,
    // so we encode the spouse-pair correctly:
    c.FAMILIES['@F1@'] = { husb: '@CW@', wife: '@C@', chil: [], divorced: true };
    expect(computeRelationship('@V@', '@CW@', c).label).toBe('Ex-Wife of 1st Cousin');
  });
});

describe('computeRelationship — affinity: deep chains', () => {
  // Build a graph where viewer V has a 1st cousin C; C is married to H; H has parents OFIL/OMIL
  // and a sister OSIS. Used to test "<atomic-in-law> of <blood-relative>" composition.
  function cousinInLawCtx() {
    return ctx({
      people: {
        '@V@':    { sex: 'M' },
        '@PV@':   { sex: 'F' },
        '@PC@':   { sex: 'F' },
        '@GMA@':  { sex: 'F' },
        '@GPA@':  { sex: 'M' },
        '@C@':    { sex: 'F' },
        '@H@':    { sex: 'M' },
        '@OFIL@': { sex: 'M' }, // H's father — V's cousin's father-in-law
        '@OMIL@': { sex: 'F' }, // H's mother — V's cousin's mother-in-law
        '@OSIS@': { sex: 'F' }, // H's sister — V's cousin's sister-in-law
      },
      parents: {
        '@V@':    [null, '@PV@'],
        '@C@':    [null, '@PC@'],
        '@PV@':   ['@GPA@', '@GMA@'],
        '@PC@':   ['@GPA@', '@GMA@'],
        '@H@':    ['@OFIL@', '@OMIL@'],
        '@OSIS@': ['@OFIL@', '@OMIL@'],
      },
      children: {
        '@PV@':   ['@V@'],
        '@PC@':   ['@C@'],
        '@GMA@':  ['@PV@', '@PC@'],
        '@GPA@':  ['@PV@', '@PC@'],
        '@OFIL@': ['@H@', '@OSIS@'],
        '@OMIL@': ['@H@', '@OSIS@'],
      },
      relatives: { '@C@': { spouses: ['@H@'] }, '@H@': { spouses: ['@C@'] } },
      families: {},
    });
  }

  it('Father-in-law of 1st Cousin (parent of cousin\'s husband)', () => {
    expect(computeRelationship('@V@', '@OFIL@', cousinInLawCtx()).label).toBe('Father-in-law of 1st Cousin');
  });

  it('Mother-in-law of 1st Cousin', () => {
    expect(computeRelationship('@V@', '@OMIL@', cousinInLawCtx()).label).toBe('Mother-in-law of 1st Cousin');
  });

  it('Sister-in-law of 1st Cousin (sister of cousin\'s husband)', () => {
    expect(computeRelationship('@V@', '@OSIS@', cousinInLawCtx()).label).toBe('Sister-in-law of 1st Cousin');
  });

  it('Husband of 1st Cousin still works (regression of existing Tier 4a)', () => {
    expect(computeRelationship('@V@', '@H@', cousinInLawCtx()).label).toBe('Husband of 1st Cousin');
  });

  it('Daughter-in-law of Sister (spouse of sister\'s son)', () => {
    const c = ctx({
      people: {
        '@V@': {}, '@SIB@': { sex: 'F' },
        '@N@': { sex: 'M' }, '@NW@': { sex: 'F' },
        '@MOM@': { sex: 'F' }, '@DAD@': { sex: 'M' },
      },
      parents: { '@V@': ['@DAD@', '@MOM@'], '@SIB@': ['@DAD@', '@MOM@'], '@N@': [null, '@SIB@'] },
      children: { '@MOM@': ['@V@', '@SIB@'], '@DAD@': ['@V@', '@SIB@'], '@SIB@': ['@N@'] },
      relatives: { '@N@': { spouses: ['@NW@'] }, '@NW@': { spouses: ['@N@'] } },
      families: {},
    });
    // V's sister's son's wife. SIB→son N (nephew)→wife. atomic from SIB = "Daughter-in-law" cost 2.
    // Composed: "Daughter-in-law of Sister", edges 2+2=4, ofs 1.
    // Alt: Z=N (nephew), edges 2, atomic "Wife" cost 1 → "Wife of Nephew" edges 3, ofs 1. Fewer edges → wins.
    expect(computeRelationship('@V@', '@NW@', c).label).toBe('Wife of Nephew');
  });

  it('Atomic Brother-in-law beats composed "Husband of Sister" (no regression)', () => {
    const c = ctx({
      people: { '@V@': {}, '@SIB@': { sex: 'F' }, '@SIBSP@': { sex: 'M' }, '@MOM@': { sex: 'F' } },
      parents: { '@V@': [null, '@MOM@'], '@SIB@': [null, '@MOM@'], '@SIBSP@': [null, null] },
      children: { '@MOM@': ['@V@', '@SIB@'] },
      relatives: { '@SIB@': { spouses: ['@SIBSP@'] }, '@SIBSP@': { spouses: ['@SIB@'] } },
      families: {},
    });
    expect(computeRelationship('@V@', '@SIBSP@', c).label).toBe('Brother-in-law');
  });
});

describe('computeRelationship — godparent', () => {
  function evt(tag, assoXref, rela) {
    return { tag, asso: [{ xref: assoXref, rela }] };
  }

  it('Godmother (direct, female godparent on viewer\'s BAPM)', () => {
    const c = ctx({
      people: {
        '@V@':  { sex: 'M', events: [evt('BAPM', '@GM@', 'Godparent')] },
        '@GM@': { sex: 'F', events: [] },
      },
    });
    expect(computeRelationship('@V@', '@GM@', c).label).toBe('Godmother');
  });

  it('Godfather (rela="Godfather" overrides missing sex)', () => {
    const c = ctx({
      people: {
        '@V@':  { events: [evt('BAPM', '@GF@', 'Godfather')] },
        '@GF@': { events: [] }, // no sex; rela disambiguates
      },
    });
    expect(computeRelationship('@V@', '@GF@', c).label).toBe('Godfather');
  });

  it('Godparent (gender-neutral when sex unknown)', () => {
    const c = ctx({
      people: {
        '@V@':  { events: [evt('BAPM', '@GP@', 'Godparent')] },
        '@GP@': { events: [] },
      },
    });
    expect(computeRelationship('@V@', '@GP@', c).label).toBe('Godparent');
  });

  it('Goddaughter (reverse: other is viewer\'s godchild)', () => {
    const c = ctx({
      people: {
        '@V@':  { sex: 'F', events: [] },
        '@GD@': { sex: 'F', events: [evt('BAPM', '@V@', 'Godmother')] },
      },
    });
    expect(computeRelationship('@V@', '@GD@', c).label).toBe('Goddaughter');
  });

  it('Godson (reverse, male)', () => {
    const c = ctx({
      people: {
        '@V@':  { sex: 'M', events: [] },
        '@GS@': { sex: 'M', events: [evt('BAPM', '@V@', 'Godparent')] },
      },
    });
    expect(computeRelationship('@V@', '@GS@', c).label).toBe('Godson');
  });

  it('CHR event also produces godparent label', () => {
    const c = ctx({
      people: {
        '@V@':  { events: [evt('CHR', '@GM@', 'Godparent')] },
        '@GM@': { sex: 'F', events: [] },
      },
    });
    expect(computeRelationship('@V@', '@GM@', c).label).toBe('Godmother');
  });

  it('Godmother of 1st Cousin (composed)', () => {
    const c = ctx({
      people: {
        '@V@':  {},
        '@C@':  { sex: 'F', events: [evt('BAPM', '@GM@', 'Godmother')] },
        '@GM@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' },
        '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: {
        '@V@': [null, '@PV@'], '@C@': [null, '@PC@'],
        '@PV@': ['@GPA@', '@GMA@'], '@PC@': ['@GPA@', '@GMA@'],
      },
      children: {
        '@PV@': ['@V@'], '@PC@': ['@C@'],
        '@GMA@': ['@PV@', '@PC@'], '@GPA@': ['@PV@', '@PC@'],
      },
    });
    expect(computeRelationship('@V@', '@GM@', c).label).toBe('Godmother of 1st Cousin');
  });

  it('Goddaughter of Sister (composed reverse)', () => {
    // V's sister has a goddaughter GD.
    const c = ctx({
      people: {
        '@V@': {},
        '@SIS@': { sex: 'F' },
        '@GD@':  { sex: 'F', events: [evt('BAPM', '@SIS@', 'Godmother')] },
        '@MOM@': { sex: 'F' }, '@DAD@': { sex: 'M' },
      },
      parents: { '@V@': ['@DAD@', '@MOM@'], '@SIS@': ['@DAD@', '@MOM@'] },
      children: { '@MOM@': ['@V@', '@SIS@'], '@DAD@': ['@V@', '@SIS@'] },
    });
    expect(computeRelationship('@V@', '@GD@', c).label).toBe('Goddaughter of Sister');
  });

  it('Godfather of Spouse (composed via spouse)', () => {
    const c = ctx({
      people: {
        '@V@':  {},
        '@S@':  { sex: 'F', events: [evt('BAPM', '@GF@', 'Godfather')] },
        '@GF@': { sex: 'M' },
      },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
    });
    expect(computeRelationship('@V@', '@GF@', c).label).toBe('Godfather of Spouse');
  });

  it('Uncle and Godfather (atomic blood + direct godparent)', () => {
    const c = ctx({
      people: {
        '@V@': { events: [evt('BAPM', '@U@', 'Godfather')] },
        '@U@': { sex: 'M' },
        '@PV@': { sex: 'F' }, '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: { '@V@': [null, '@PV@'], '@PV@': ['@GPA@', '@GMA@'], '@U@': ['@GPA@', '@GMA@'] },
      children: { '@PV@': ['@V@'], '@GMA@': ['@PV@', '@U@'], '@GPA@': ['@PV@', '@U@'] },
    });
    expect(computeRelationship('@V@', '@U@', c).label).toBe('Uncle and Godfather');
  });

  it('1st Cousin and Godmother (atomic blood + direct godparent)', () => {
    const c = ctx({
      people: {
        '@V@': { events: [evt('BAPM', '@C@', 'Godmother')] },
        '@C@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' },
        '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: {
        '@V@': [null, '@PV@'], '@C@': [null, '@PC@'],
        '@PV@': ['@GPA@', '@GMA@'], '@PC@': ['@GPA@', '@GMA@'],
      },
      children: {
        '@PV@': ['@V@'], '@PC@': ['@C@'],
        '@GMA@': ['@PV@', '@PC@'], '@GPA@': ['@PV@', '@PC@'],
      },
    });
    expect(computeRelationship('@V@', '@C@', c).label).toBe('1st Cousin and Godmother');
  });

  it('Sister-in-law and Godmother (atomic affinity + direct godparent)', () => {
    const c = ctx({
      people: {
        '@V@':   { events: [evt('BAPM', '@SIS@', 'Godmother')] },
        '@SP@':  { sex: 'F' },
        '@SIS@': { sex: 'F' },
        '@SM@':  { sex: 'F' },
      },
      parents: { '@SP@': [null, '@SM@'], '@SIS@': [null, '@SM@'] },
      children: { '@SM@': ['@SP@', '@SIS@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
    });
    expect(computeRelationship('@V@', '@SIS@', c).label).toBe('Sister-in-law and Godmother');
  });

  it('Composed (distant) kin + direct godparent → godparent only', () => {
    // O is V's cousin's wife (composed kin "Wife of 1st Cousin") AND V's godmother.
    // Rule: composed kin + atomic godparent → just "Godmother".
    const c = ctx({
      people: {
        '@V@': { events: [evt('BAPM', '@O@', 'Godmother')] },
        '@C@': { sex: 'F' },
        '@O@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' },
        '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: {
        '@V@': [null, '@PV@'], '@C@': [null, '@PC@'],
        '@PV@': ['@GPA@', '@GMA@'], '@PC@': ['@GPA@', '@GMA@'],
      },
      children: {
        '@PV@': ['@V@'], '@PC@': ['@C@'],
        '@GMA@': ['@PV@', '@PC@'], '@GPA@': ['@PV@', '@PC@'],
      },
      relatives: { '@C@': { spouses: ['@O@'] }, '@O@': { spouses: ['@C@'] } },
    });
    expect(computeRelationship('@V@', '@O@', c).label).toBe('Godmother');
  });

  it('No godparent: plain Uncle (regression)', () => {
    const c = ctx({
      people: {
        '@V@': {},
        '@U@': { sex: 'M' },
        '@PV@': { sex: 'F' }, '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: { '@V@': [null, '@PV@'], '@PV@': ['@GPA@', '@GMA@'], '@U@': ['@GPA@', '@GMA@'] },
      children: { '@PV@': ['@V@'], '@GMA@': ['@PV@', '@U@'], '@GPA@': ['@PV@', '@U@'] },
    });
    expect(computeRelationship('@V@', '@U@', c).label).toBe('Uncle');
  });
});

describe('enumerateRelationships', () => {
  it('returns blood + godparent for an uncle who is also godfather', () => {
    const c = ctx({
      people: {
        '@V@': { events: [{ tag: 'BAPM', asso: [{ xref: '@U@', rela: 'Godfather' }] }] },
        '@U@': { sex: 'M' },
        '@PV@': { sex: 'F' }, '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: { '@V@': [null, '@PV@'], '@PV@': ['@GPA@', '@GMA@'], '@U@': ['@GPA@', '@GMA@'] },
      children: { '@PV@': ['@V@'], '@GMA@': ['@PV@', '@U@'], '@GPA@': ['@PV@', '@U@'] },
    });
    const rels = enumerateRelationships('@V@', '@U@', c);
    const kinds = rels.map(r => r.kind).sort();
    expect(kinds).toEqual(['blood', 'godparent']);
    expect(rels.find(r => r.kind === 'blood').label).toBe('Uncle');
    expect(rels.find(r => r.kind === 'godparent').label).toBe('Godfather');
  });

  it('returns only godparent when no kin relationship', () => {
    const c = ctx({
      people: {
        '@V@':  { events: [{ tag: 'BAPM', asso: [{ xref: '@GM@', rela: 'Godmother' }] }] },
        '@GM@': { sex: 'F' },
      },
    });
    const rels = enumerateRelationships('@V@', '@GM@', c);
    expect(rels.map(r => r.kind)).toEqual(['godparent']);
    expect(rels[0].label).toBe('Godmother');
  });

  it('returns empty array for unrelated people', () => {
    const c = ctx({ people: { '@V@': {}, '@X@': {} } });
    expect(enumerateRelationships('@V@', '@X@', c)).toEqual([]);
  });
});

describe('computeRelationship — unrelated', () => {
  it('returns null for person with no graph path', () => {
    const c = ctx({
      people: { '@V@': {}, '@X@': { sex: 'M' } },
      parents: { '@V@': [null, null], '@X@': [null, null] },
      children: {},
      relatives: {},
      families: {},
    });
    expect(computeRelationship('@V@', '@X@', c)).toBeNull();
  });
});

describe('computeRelationship — affinity: date-aware step relabeling', () => {
  it('Wife of Father when father remarried after prior wife (marriage-ordering signal)', () => {
    // DAD married S1 in F1 (1900). DAD later married BIOMOM in F2 (1910). V is child of F2.
    // S1 is "Wife of Father", not "Step-Mother".
    const c = ctx({
      people: {
        '@V@': {}, '@DAD@': { sex: 'M' },
        '@BIOMOM@': { sex: 'F' }, '@S1@': { sex: 'F' },
      },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'] },
      relatives: { '@DAD@': { spouses: ['@S1@', '@BIOMOM@'] }, '@S1@': { spouses: ['@DAD@'] } },
      families: {
        '@F1@': { husb: '@DAD@', wife: '@S1@',    chil: [],     marr_year: 1900 },
        '@F2@': { husb: '@DAD@', wife: '@BIOMOM@', chil: ['@V@'], marr_year: 1910 },
      },
    });
    expect(computeRelationship('@V@', '@S1@', c).label).toBe('Wife of Father');
  });

  it('Husband of Mother when mother\'s prior husband died before viewer was born', () => {
    // MOM married S1; S1 died 1890. MOM then had V in 1900 with DAD.
    const c = ctx({
      people: {
        '@V@':   { birth_year: 1900 },
        '@MOM@': { sex: 'F' },
        '@DAD@': { sex: 'M' },
        '@S1@':  { sex: 'M', death_year: 1890 },
      },
      parents: { '@V@': ['@DAD@', '@MOM@'] },
      children: { '@MOM@': ['@V@'], '@DAD@': ['@V@'] },
      relatives: { '@MOM@': { spouses: ['@S1@', '@DAD@'] }, '@S1@': { spouses: ['@MOM@'] } },
      families: {
        '@F1@': { husb: '@S1@',  wife: '@MOM@', chil: [],     marr_year: null },
        '@F2@': { husb: '@DAD@', wife: '@MOM@', chil: ['@V@'], marr_year: null },
      },
    });
    expect(computeRelationship('@V@', '@S1@', c).label).toBe('Husband of Mother');
  });

  it('keeps Step-Mother when no date evidence is available', () => {
    const c = ctx({
      people: { '@V@': {}, '@DAD@': { sex: 'M' }, '@BIOMOM@': { sex: 'F' }, '@S1@': { sex: 'F' } },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'] },
      relatives: { '@DAD@': { spouses: ['@S1@', '@BIOMOM@'] }, '@S1@': { spouses: ['@DAD@'] } },
      families: {
        '@F1@': { husb: '@DAD@', wife: '@S1@',    chil: [] },
        '@F2@': { husb: '@DAD@', wife: '@BIOMOM@', chil: ['@V@'] },
      },
    });
    expect(computeRelationship('@V@', '@S1@', c).label).toBe('Step-Mother');
  });

  it('Daughter of Wife when viewer\'s prior wife had a daughter with a later spouse', () => {
    // V married W1 in F1 (1900). W1 later married SX in F2 (1910), and D is their child.
    // From V's perspective, D should be "Daughter of Wife", not "Step-Daughter".
    const c = ctx({
      people: {
        '@V@':  { sex: 'M' },
        '@W1@': { sex: 'F' },
        '@SX@': { sex: 'M' },
        '@D@':  { sex: 'F' },
      },
      parents: { '@D@': ['@SX@', '@W1@'] },
      children: { '@W1@': ['@D@'], '@SX@': ['@D@'] },
      relatives: { '@V@': { spouses: ['@W1@'] }, '@W1@': { spouses: ['@V@', '@SX@'] } },
      families: {
        '@F1@': { husb: '@V@',  wife: '@W1@', chil: [],    marr_year: 1900 },
        '@F2@': { husb: '@SX@', wife: '@W1@', chil: ['@D@'], marr_year: 1910 },
      },
    });
    expect(computeRelationship('@V@', '@D@', c).label).toBe('Daughter of Wife');
  });

  it('Son of Husband when viewer died before husband had a later child', () => {
    // V married H1; V died 1890. H1 later had S2 (born 1900) with PX.
    // From V's perspective, S2 should be "Son of Husband".
    const c = ctx({
      people: {
        '@V@':  { sex: 'F', death_year: 1890 },
        '@H1@': { sex: 'M' },
        '@PX@': { sex: 'F' },
        '@S2@': { sex: 'M', birth_year: 1900 },
      },
      parents: { '@S2@': ['@H1@', '@PX@'] },
      children: { '@H1@': ['@S2@'], '@PX@': ['@S2@'] },
      relatives: { '@V@': { spouses: ['@H1@'] }, '@H1@': { spouses: ['@V@', '@PX@'] } },
      families: {
        '@F1@': { husb: '@H1@', wife: '@V@',  chil: [] },
        '@F2@': { husb: '@H1@', wife: '@PX@', chil: ['@S2@'] },
      },
    });
    expect(computeRelationship('@V@', '@S2@', c).label).toBe('Son of Husband');
  });

  it('keeps Step-Daughter when no date evidence is available', () => {
    const c = ctx({
      people: { '@V@': { sex: 'M' }, '@SP@': { sex: 'F' }, '@SD@': { sex: 'F' }, '@SDX@': { sex: 'M' } },
      parents: { '@SD@': ['@SDX@', '@SP@'] },
      children: { '@SP@': ['@SD@'], '@SDX@': ['@SD@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@', '@SDX@'] } },
      families: {
        '@F1@': { husb: '@V@',   wife: '@SP@', chil: [] },
        '@F2@': { husb: '@SDX@', wife: '@SP@', chil: ['@SD@'] },
      },
    });
    expect(computeRelationship('@V@', '@SD@', c).label).toBe('Step-Daughter');
  });
});

describe('buildRelationshipPath — structure', () => {
  // Helper: assert ordering + flags shared by every blood case.
  function expectEnds(path, otherXref, viewerXref) {
    expect(path[0].xref).toBe(otherXref);
    expect(path[0].isOther).toBe(true);
    expect(path[path.length - 1].xref).toBe(viewerXref);
    expect(path[path.length - 1].isViewer).toBe(true);
    expect(path[path.length - 1].relToNext).toBe(null);
    expect(path.filter(n => n.isMrca).length).toBe(1);
  }

  it('Self → single-element path (other === viewer)', () => {
    const c = ctx({ people: { '@I1@': { sex: 'F' } } });
    const path = buildRelationshipPath('@I1@', '@I1@', c);
    expect(path).toHaveLength(1);
    expect(path[0]).toMatchObject({ xref: '@I1@', isMrca: true, isViewer: true, isOther: true, relToNext: null });
  });

  it('Sibling (a=1,b=1): other → parent(MRCA) → you, with flipped step terms', () => {
    // @I1@ viewer (M), @I2@ sibling (F), shared parent @P@ (M)
    const c = ctx({
      people: { '@I1@': { sex: 'M' }, '@I2@': { sex: 'F' }, '@P@': { sex: 'M' } },
      parents: { '@I1@': ['@P@', null], '@I2@': ['@P@', null] },
      children: { '@P@': ['@I1@', '@I2@'] },
    });
    const path = buildRelationshipPath('@I1@', '@I2@', c);
    expect(path.map(n => n.xref)).toEqual(['@I2@', '@P@', '@I1@']);
    expectEnds(path, '@I2@', '@I1@');
    expect(path[1].isMrca).toBe(true);
    expect(path[0].relToNext).toBe('daughter of'); // other is child of MRCA (above)
    expect(path[1].relToNext).toBe('father of');   // MRCA is parent of viewer (below)
  });

  it('Direct ancestor (b=0): MRCA is the other person', () => {
    // @I3@ grandmother (F) → @I2@ parent (M) → @I1@ viewer
    const c = ctx({
      people: { '@I1@': { sex: 'M' }, '@I2@': { sex: 'M' }, '@I3@': { sex: 'F' } },
      parents: { '@I1@': ['@I2@', null], '@I2@': ['@I3@', null] },
      children: { '@I2@': ['@I1@'], '@I3@': ['@I2@'] },
    });
    const path = buildRelationshipPath('@I1@', '@I3@', c);
    expect(path.map(n => n.xref)).toEqual(['@I3@', '@I2@', '@I1@']);
    expect(path[0].isMrca).toBe(true);              // ancestor is the MRCA
    expect(path[0].relToNext).toBe('mother of');    // below-MRCA: parent term
    expect(path[1].relToNext).toBe('father of');
  });

  it('Direct descendant (a=0): MRCA is the viewer', () => {
    // viewer @I1@ → child @I2@ → grandchild @I3@ (other)
    const c = ctx({
      people: { '@I1@': { sex: 'F' }, '@I2@': { sex: 'M' }, '@I3@': { sex: 'F' } },
      parents: { '@I2@': ['@I1@', null], '@I3@': ['@I2@', null] },
      children: { '@I1@': ['@I2@'], '@I2@': ['@I3@'] },
    });
    const path = buildRelationshipPath('@I1@', '@I3@', c);
    expect(path.map(n => n.xref)).toEqual(['@I3@', '@I2@', '@I1@']);
    expect(path[2].isMrca).toBe(true);              // viewer is the MRCA
    expect(path[0].relToNext).toBe('daughter of');  // above-MRCA: child term
    expect(path[1].relToNext).toBe('son of');
  });

  it('First cousins (a=2,b=2): full chain other→…→MRCA→…→you', () => {
    // GP @GP@ (M) has children @PA@ (viewer-side, F) and @PB@ (other-side, M).
    // viewer @V@ child of @PA@; other @O@ child of @PB@.
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@O@': { sex: 'F' },
        '@PA@': { sex: 'F' }, '@PB@': { sex: 'M' }, '@GP@': { sex: 'M' },
      },
      parents: { '@V@': ['@PA@', null], '@O@': ['@PB@', null], '@PA@': ['@GP@', null], '@PB@': ['@GP@', null] },
      children: { '@PA@': ['@V@'], '@PB@': ['@O@'], '@GP@': ['@PA@', '@PB@'] },
    });
    const path = buildRelationshipPath('@V@', '@O@', c);
    expect(path.map(n => n.xref)).toEqual(['@O@', '@PB@', '@GP@', '@PA@', '@V@']);
    expect(path[2].isMrca).toBe(true);
    expect(path[0].relToNext).toBe('daughter of'); // @O@ (F) child of @PB@
    expect(path[1].relToNext).toBe('son of');      // @PB@ (M) child of @GP@
    expect(path[2].relToNext).toBe('father of');   // @GP@ (M) parent of @PA@
    expect(path[3].relToNext).toBe('mother of');   // @PA@ (F) parent of @V@
    expect(path[4].relToNext).toBe(null);
  });

  it('Aunt (a=2,b=1): unequal legs', () => {
    // @GP@ (M) → children @P@ (viewer parent, M) and @A@ (aunt, F).
    // viewer @V@ child of @P@. Other @A@ is sibling of @P@.
    const c = ctx({
      people: { '@V@': { sex: 'M' }, '@A@': { sex: 'F' }, '@P@': { sex: 'M' }, '@GP@': { sex: 'M' } },
      parents: { '@V@': ['@P@', null], '@P@': ['@GP@', null], '@A@': ['@GP@', null] },
      children: { '@P@': ['@V@'], '@GP@': ['@P@', '@A@'] },
    });
    const path = buildRelationshipPath('@V@', '@A@', c);
    expect(path.map(n => n.xref)).toEqual(['@A@', '@GP@', '@P@', '@V@']);
    expect(path[1].isMrca).toBe(true);             // @GP@ is MRCA (b=1 → mrcaIndex 1)
    expect(path[0].relToNext).toBe('daughter of'); // @A@ (F) child of @GP@
    expect(path[1].relToNext).toBe('father of');   // @GP@ (M) parent of @P@
    expect(path[2].relToNext).toBe('father of');   // @P@ (M) parent of @V@
  });

  it('precomputedPath mode produces the same chain as self-contained mode', () => {
    const c = ctx({
      people: { '@I1@': { sex: 'M' }, '@I2@': { sex: 'F' }, '@P@': { sex: 'M' } },
      parents: { '@I1@': ['@P@', null], '@I2@': ['@P@', null] },
      children: { '@P@': ['@I1@', '@I2@'] },
    });
    const selfContained = buildRelationshipPath('@I1@', '@I2@', c);
    const precomputed = buildRelationshipPath('@I1@', '@I2@', c, { a: 1, b: 1, mrca: '@P@' });
    expect(precomputed).toEqual(selfContained);
  });

  it('returns null when there is no blood path', () => {
    const c = ctx({
      people: { '@I1@': { sex: 'M' }, '@I2@': { sex: 'F' } },
      parents: {}, children: {},
    });
    expect(buildRelationshipPath('@I1@', '@I2@', c)).toBe(null);
  });

  it('returns null when precomputedPath references an unreachable MRCA', () => {
    // @I1@ and @I2@ are unrelated; precomputedPath claims a bogus common ancestor.
    const c = ctx({
      people: { '@I1@': { sex: 'M' }, '@I2@': { sex: 'F' }, '@X@': { sex: 'M' } },
      parents: {}, children: {},
    });
    expect(buildRelationshipPath('@I1@', '@I2@', c, { a: 2, b: 2, mrca: '@X@' })).toBe(null);
  });

  it('blood chain carries edgeKind per node (descent-down before MRCA, descent-up after)', () => {
    // First cousins: @O@ → @PB@ → @GP@(MRCA) → @PA@ → @V@
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@O@': { sex: 'F' },
        '@PA@': { sex: 'F' }, '@PB@': { sex: 'M' }, '@GP@': { sex: 'M' },
      },
      parents: { '@V@': ['@PA@', null], '@O@': ['@PB@', null], '@PA@': ['@GP@', null], '@PB@': ['@GP@', null] },
      children: { '@PA@': ['@V@'], '@PB@': ['@O@'], '@GP@': ['@PA@', '@PB@'] },
    });
    const path = buildRelationshipPath('@V@', '@O@', c);
    expect(path.map(n => n.edgeKind)).toEqual(['descent-down', 'descent-down', 'descent-up', 'descent-up', null]);
  });
});

describe('enumerateRelationships — affinity paths', () => {
  // Pull the entry of a given kind and return its rendered path array.
  function pathOf(rels, kind) {
    const e = rels.find(r => r.kind === kind);
    return e ? e.path : null;
  }

  it('spouse: other → you, single spouse edge', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@S@': { sex: 'M' } },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@S@', wife: '@V@', chil: [] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@S@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@S@', '@V@']);
    expect(p[0]).toMatchObject({ isOther: true, edgeKind: 'spouse', relToNext: 'husband of', isMrca: false });
    expect(p[1]).toMatchObject({ isViewer: true, relToNext: null });
  });

  it('mother-in-law: parent of viewer spouse (descent-up then spouse)', () => {
    const c = ctx({
      people: { '@V@': {}, '@S@': { sex: 'F' }, '@SM@': { sex: 'F' } },
      parents: { '@S@': [null, '@SM@'] },
      children: { '@SM@': ['@S@'] },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SM@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SM@', '@S@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-up', 'spouse', null]);
    expect(p[0].relToNext).toBe('mother of');
    expect(p[1].relToNext).toBe('wife of');
    expect(p.some(n => n.isMrca)).toBe(false);
  });

  it('step-mother: spouse of bio father (spouse then descent-up)', () => {
    const c = ctx({
      people: { '@V@': {}, '@DAD@': { sex: 'M' }, '@STEPMOM@': { sex: 'F' }, '@BIOMOM@': { sex: 'F' } },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'] },
      relatives: { '@DAD@': { spouses: ['@BIOMOM@', '@STEPMOM@'] }, '@STEPMOM@': { spouses: ['@DAD@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@STEPMOM@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@STEPMOM@', '@DAD@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['spouse', 'descent-up', null]);
    expect(p[0].relToNext).toBe('wife of');   // step-mom (F) spouse of dad
    expect(p[1].relToNext).toBe('father of');  // dad (M) parent of you
  });

  it('godparent: single godparent edge', () => {
    const c = ctx({
      people: {
        '@V@': { events: [{ tag: 'BAPM', asso: [{ xref: '@GM@', rela: 'Godmother' }] }] },
        '@GM@': { sex: 'F' },
      },
    });
    const p = pathOf(enumerateRelationships('@V@', '@GM@', c), 'godparent');
    expect(p.map(n => n.xref)).toEqual(['@GM@', '@V@']);
    expect(p[0]).toMatchObject({ edgeKind: 'godparent', relToNext: 'godmother of' });
  });

  it('ex-spouse: edgeKind ex-spouse with ex- term', () => {
    const c = ctx({
      people: { '@V@': { sex: 'M' }, '@S@': { sex: 'F' } },
      relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      families: { '@F1@': { husb: '@V@', wife: '@S@', chil: [], divorced: true } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@S@', c), 'affinity');
    expect(p[0]).toMatchObject({ edgeKind: 'ex-spouse', relToNext: 'ex-wife of' });
  });

  it('step-child: descent-down then spouse', () => {
    const c = ctx({
      people: { '@V@': {}, '@SP@': { sex: 'F' }, '@SD@': { sex: 'F' }, '@SDX@': { sex: 'M' } },
      parents: { '@SD@': ['@SDX@', '@SP@'] },
      children: { '@SP@': ['@SD@'], '@SDX@': ['@SD@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SD@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SD@', '@SP@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-down', 'spouse', null]);
    expect(p[0].relToNext).toBe('daughter of'); // SD (F) child of SP
  });

  it('step-sibling: descent-down, spouse, descent-up', () => {
    const c = ctx({
      people: {
        '@V@': {}, '@DAD@': { sex: 'M' }, '@BIOMOM@': { sex: 'F' },
        '@STEPMOM@': { sex: 'F' }, '@SS@': { sex: 'F' }, '@SSX@': { sex: 'M' },
      },
      parents: { '@V@': ['@DAD@', '@BIOMOM@'], '@SS@': ['@SSX@', '@STEPMOM@'] },
      children: { '@DAD@': ['@V@'], '@BIOMOM@': ['@V@'], '@STEPMOM@': ['@SS@'], '@SSX@': ['@SS@'] },
      relatives: { '@DAD@': { spouses: ['@BIOMOM@', '@STEPMOM@'] }, '@STEPMOM@': { spouses: ['@DAD@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SS@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SS@', '@STEPMOM@', '@DAD@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-down', 'spouse', 'descent-up', null]);
  });

  it('sibling-in-law via spouse sibling (3b): descent-down, descent-up, spouse', () => {
    const c = ctx({
      people: { '@V@': {}, '@SP@': { sex: 'F' }, '@SPSIB@': { sex: 'F' }, '@SM@': { sex: 'F' } },
      parents: { '@SP@': [null, '@SM@'], '@SPSIB@': [null, '@SM@'] },
      children: { '@SM@': ['@SP@', '@SPSIB@'] },
      relatives: { '@V@': { spouses: ['@SP@'] }, '@SP@': { spouses: ['@V@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SPSIB@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SPSIB@', '@SM@', '@SP@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['descent-down', 'descent-up', 'spouse', null]);
  });

  it('sibling-in-law via sibling spouse (3c): spouse, descent-down, descent-up', () => {
    const c = ctx({
      people: { '@V@': {}, '@SIB@': { sex: 'F' }, '@SIBSP@': { sex: 'M' }, '@MOM@': { sex: 'F' } },
      parents: { '@V@': [null, '@MOM@'], '@SIB@': [null, '@MOM@'] },
      children: { '@MOM@': ['@V@', '@SIB@'] },
      relatives: { '@SIB@': { spouses: ['@SIBSP@'] }, '@SIBSP@': { spouses: ['@SIB@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@SIBSP@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@SIBSP@', '@SIB@', '@MOM@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['spouse', 'descent-down', 'descent-up', null]);
  });

  it('child-in-law (3d): spouse then descent-down', () => {
    const c = ctx({
      people: { '@V@': { sex: 'F' }, '@D@': { sex: 'F' }, '@DH@': { sex: 'M' } },
      parents: { '@D@': [null, '@V@'] },
      children: { '@V@': ['@D@'] },
      relatives: { '@D@': { spouses: ['@DH@'] }, '@DH@': { spouses: ['@D@'] } },
    });
    const p = pathOf(enumerateRelationships('@V@', '@DH@', c), 'affinity');
    expect(p.map(n => n.xref)).toEqual(['@DH@', '@D@', '@V@']);
    expect(p.map(n => n.edgeKind)).toEqual(['spouse', 'descent-down', null]);
    expect(p[1].relToNext).toBe('daughter of'); // D (F) child of V
  });

  it('godchild: edgeKind godchild', () => {
    const c = ctx({
      people: {
        '@V@': { sex: 'M' },
        '@GC@': { sex: 'M', events: [{ tag: 'BAPM', asso: [{ xref: '@V@', rela: 'Godfather' }] }] },
      },
    });
    const p = pathOf(enumerateRelationships('@V@', '@GC@', c), 'godparent');
    expect(p.map(n => n.xref)).toEqual(['@GC@', '@V@']);
    expect(p[0]).toMatchObject({ edgeKind: 'godchild', relToNext: 'godson of' });
  });

  it('multi-relationship (uncle who is also godfather): both entries carry a path, blood first', () => {
    const c = ctx({
      people: {
        '@V@': { events: [{ tag: 'BAPM', asso: [{ xref: '@U@', rela: 'Godfather' }] }] },
        '@U@': { sex: 'M' },
        '@PV@': { sex: 'F' }, '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: { '@V@': [null, '@PV@'], '@PV@': ['@GPA@', '@GMA@'], '@U@': ['@GPA@', '@GMA@'] },
      children: { '@PV@': ['@V@'], '@GMA@': ['@PV@', '@U@'], '@GPA@': ['@PV@', '@U@'] },
    });
    const rels = enumerateRelationships('@V@', '@U@', c);
    expect(rels.map(r => r.kind)).toEqual(['blood', 'godparent']); // blood first (primary)
    for (const r of rels) {
      expect(r.path, `${r.kind} should have a path`).toBeTruthy();
      expect(r.path[0].xref).toBe('@U@');
      expect(r.path[r.path.length - 1].xref).toBe('@V@');
    }
    expect(pathOf(rels, 'godparent').map(n => n.edgeKind)).toEqual(['godparent', null]);
  });

  it('Wife of 1st Cousin: spouse edge then blood leg with tagged MRCA', () => {
    // @V@'s 1st cousin @C@; @C@'s wife @CW@ is the "other".
    // Cousin tree: @GMA@(MRCA) → @PV@ → @V@  and  @GMA@ → @PC@ → @C@.
    // @GPA@ is the shared second parent of @PV@ and @PC@ so they are full cousins.
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@C@': { sex: 'F' }, '@CW@': { sex: 'F' },
        '@PV@': { sex: 'F' }, '@PC@': { sex: 'F' }, '@GMA@': { sex: 'F' }, '@GPA@': { sex: 'M' },
      },
      parents: { '@V@': [null, '@PV@'], '@C@': [null, '@PC@'], '@PV@': ['@GMA@', '@GPA@'], '@PC@': ['@GMA@', '@GPA@'] },
      children: { '@PV@': ['@V@'], '@PC@': ['@C@'], '@GMA@': ['@PV@', '@PC@'], '@GPA@': ['@PV@', '@PC@'] },
      relatives: { '@C@': { spouses: ['@CW@'] }, '@CW@': { spouses: ['@C@'] } },
    });
    const rels = enumerateRelationships('@V@', '@CW@', c);
    const aff = rels.find(r => r.kind === 'affinity');
    expect(aff.label).toBe('Wife of 1st Cousin');
    expect(aff.path.map(n => n.xref)).toEqual(['@CW@', '@C@', '@PC@', '@GMA@', '@PV@', '@V@']);
    expect(aff.path.map(n => n.edgeKind)).toEqual(['spouse', 'descent-down', 'descent-down', 'descent-up', 'descent-up', null]);
    expect(aff.path.findIndex(n => n.isMrca)).toBe(3); // @GMA@
    expect(aff.path[0].relToNext).toBe('wife of');
  });

  it('Niece of Spouse: spouse split appends spouse hop, keeps sub-path order', () => {
    // viewer @V@ married @W@; @W@'s niece @N@ (W's sibling @SIB@'s daughter).
    // NOTE: the spouse split uses the generic word "Spouse" in the LABEL, while
    // the chain TERM stays gendered ("wife of"). This is the live _bestRel
    // behavior — there is no gendered-spouse composition in the engine.
    const c = ctx({
      people: {
        '@V@': { sex: 'M' }, '@W@': { sex: 'F' }, '@SIB@': { sex: 'F' },
        '@N@': { sex: 'F' }, '@WP@': { sex: 'F' }, '@WF@': { sex: 'M' },
      },
      parents: { '@W@': ['@WP@', '@WF@'], '@SIB@': ['@WP@', '@WF@'], '@N@': [null, '@SIB@'] },
      children: { '@WP@': ['@W@', '@SIB@'], '@WF@': ['@W@', '@SIB@'], '@SIB@': ['@N@'] },
      relatives: { '@V@': { spouses: ['@W@'] }, '@W@': { spouses: ['@V@'] } },
    });
    const rels = enumerateRelationships('@V@', '@N@', c);
    const aff = rels.find(r => r.kind === 'affinity');
    expect(aff.label).toBe('Niece of Spouse');
    // other → … → spouse → you ; the spouse hop W→V is the last edge.
    expect(aff.path[aff.path.length - 1].xref).toBe('@V@');
    expect(aff.path[aff.path.length - 2].xref).toBe('@W@');
    expect(aff.path[aff.path.length - 2].edgeKind).toBe('spouse');
    expect(aff.path[aff.path.length - 2].relToNext).toBe('wife of');
  });

  it('label-parity: each entry path is non-null and consistent with its label for representative fixtures', () => {
    const fixtures = [
      ['spouse', {
        people: { '@V@': { sex: 'F' }, '@S@': { sex: 'M' } },
        relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      }, '@V@', '@S@'],
      ['mother-in-law', {
        people: { '@V@': {}, '@S@': { sex: 'F' }, '@SM@': { sex: 'F' } },
        parents: { '@S@': [null, '@SM@'] }, children: { '@SM@': ['@S@'] },
        relatives: { '@V@': { spouses: ['@S@'] }, '@S@': { spouses: ['@V@'] } },
      }, '@V@', '@SM@'],
    ];
    for (const [, args, v, o] of fixtures) {
      const c = ctx(args);
      const rels = enumerateRelationships(v, o, c);
      for (const r of rels) {
        expect(r.path, `${r.kind} entry should have a path`).toBeTruthy();
        expect(r.path[0].isOther).toBe(true);
        expect(r.path[r.path.length - 1].isViewer).toBe(true);
        expect(r.path[r.path.length - 1].xref).toBe(v);
        expect(r.path[0].xref).toBe(o);
      }
    }
  });
});
