import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { computeRelationship } = require('../../js/viz_relationship.js');

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
  it('Great-Aunt (a=3)', () => {
    const { c, viewer, other } = auntCtx(3, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('Great-Aunt');
  });
  it('3× Great-Aunt (a=5)', () => {
    const { c, viewer, other } = auntCtx(5, 'F');
    expect(computeRelationship(viewer, other, c).label).toBe('3× Great-Aunt');
  });
});
