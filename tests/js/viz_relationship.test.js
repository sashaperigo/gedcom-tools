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
