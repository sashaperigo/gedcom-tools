import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

function loadModule({ allPeople = [], parents = {}, children = {}, families = {} } = {}) {
    vi.resetModules();
    const modPath = require.resolve('../../js/viz_relative_events.js');
    delete require.cache[modPath];
    global.ALL_PEOPLE = allPeople;
    global.ALL_PEOPLE_BY_ID = Object.fromEntries(allPeople.map(p => [p.id, p]));
    global.PARENTS = parents;
    global.CHILDREN = children;
    global.FAMILIES = families;
    return require('../../js/viz_relative_events.js');
}

beforeEach(() => {
    delete global.ALL_PEOPLE;
    delete global.ALL_PEOPLE_BY_ID;
    delete global.PARENTS;
    delete global.CHILDREN;
    delete global.FAMILIES;
});

describe('_role — child', () => {
    it('returns "son" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'child')).toBe('son');
    });
    it('returns "daughter" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'child')).toBe('daughter');
    });
    it('returns "child" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'child')).toBe('child');
    });
});

describe('_role — spouse', () => {
    it('returns "husband" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'spouse')).toBe('husband');
    });
    it('returns "wife" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'spouse')).toBe('wife');
    });
    it('returns "spouse" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'spouse')).toBe('spouse');
    });
});

describe('_role — parent', () => {
    it('returns "father" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'parent')).toBe('father');
    });
    it('returns "mother" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'parent')).toBe('mother');
    });
    it('returns "parent" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'parent')).toBe('parent');
    });
});

describe('_lifetimeBounds', () => {
    it('returns null when birth_year is missing', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '', death_year: '', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toBe(null);
    });
    it('returns {lo: birth, hi: death} when both known', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1880, death_year: 1945, sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1945, deathYear: 1945 });
    });
    it('caps at birth_year+100 when death year is missing', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1880, death_year: '', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1980, deathYear: null });
    });
    it('handles string years from JSON payload', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '1880', death_year: '1945', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1945, deathYear: 1945 });
    });
    it('returns null when xref not found in ALL_PEOPLE_BY_ID', () => {
        const mod = loadModule();
        expect(mod._lifetimeBounds('@IX@')).toBe(null);
    });
});

// Helper to build a fixture: focus = @I1@ (b.1880, d.1945)
// Children: @I2@ (b.1904, F), @I3@ (b.1907, M, d.1928)
// Spouse: @I4@ (M, d.1934) — connected via FAM
// Parents: @I5@ (M, d.1895) father, @I6@ (F, d.1920) mother
function focusedFixture() {
    const allPeople = [
        { id: '@I1@', name: 'Maria',    birth_year: 1880, death_year: 1945, sex: 'F' },
        { id: '@I2@', name: 'Eleni',    birth_year: 1904, death_year: '',   sex: 'F' },
        { id: '@I3@', name: 'Georgios', birth_year: 1907, death_year: 1928, sex: 'M' },
        { id: '@I4@', name: 'Stavros',  birth_year: 1878, death_year: 1934, sex: 'M' },
        { id: '@I5@', name: 'Dimitrios',birth_year: 1850, death_year: 1895, sex: 'M' },
        { id: '@I6@', name: 'Sofia',    birth_year: 1855, death_year: 1920, sex: 'F' },
    ];
    return {
        allPeople,
        parents:  { '@I1@': ['@I5@', '@I6@'], '@I2@': ['@I4@', '@I1@'], '@I3@': ['@I4@', '@I1@'] },
        children: { '@I1@': ['@I2@', '@I3@'], '@I4@': ['@I2@', '@I3@'], '@I5@': ['@I1@'], '@I6@': ['@I1@'] },
        families: { '@F1@': { husb: '@I4@', wife: '@I1@', chil: ['@I2@', '@I3@'], marr_year: 1902 } },
    };
}

describe('buildRelativeEvents — basic', () => {
    it('returns [] when focused person has no birth year', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '', death_year: '', sex: '' }],
        });
        expect(mod.buildRelativeEvents('@I1@')).toEqual([]);
    });

    it('returns [] when focused person has no relatives', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1900, death_year: 1980, sex: 'M' }],
        });
        expect(mod.buildRelativeEvents('@I1@')).toEqual([]);
    });

    it('includes child birth, child death, spouse death, and parent deaths within lifetime', () => {
        const mod = loadModule(focusedFixture());
        const events = mod.buildRelativeEvents('@I1@');
        const summary = events.map(e => `${e.year} ${e.kind} ${e.role} ${e.name}`);
        expect(summary).toEqual([
            '1895 death father Dimitrios',
            '1904 birth daughter Eleni',
            '1907 birth son Georgios',
            '1920 death mother Sofia',
            '1928 death son Georgios',
            '1934 death husband Stavros',
        ]);
    });
});

describe('buildRelativeEvents — filtering', () => {
    it('excludes child birth when child has no birth year', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I2@' ? { ...p, birth_year: '' } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1904);
    });

    it("excludes child birth when child is born after focused person's death", () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I2@' ? { ...p, birth_year: 1950 } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1950);
    });

    it("excludes parent death that occurred before focused person's birth", () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I5@' ? { ...p, death_year: 1860 } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1860);
    });

    it("excludes spouse death after focused person's death", () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I4@' ? { ...p, death_year: 1960 } : p);
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1960);
    });

    it('uses birth_year+100 cap when focused person has no death year', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I1@' ? { ...p, death_year: '' } : p);
        fx.allPeople.push({ id: '@I7@', name: 'Late', birth_year: 1985, death_year: '', sex: 'F' });
        fx.children['@I1@'].push('@I7@');
        const mod = loadModule(fx);
        const years = mod.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years).not.toContain(1985);
        fx.allPeople.push({ id: '@I8@', name: 'EarlyEnough', birth_year: 1970, death_year: '', sex: 'M' });
        fx.children['@I1@'].push('@I8@');
        const mod2 = loadModule(fx);
        const years2 = mod2.buildRelativeEvents('@I1@').map(e => e.year);
        expect(years2).toContain(1970);
    });
});

describe('buildRelativeEvents — section + sort', () => {
    it('assigns Early Life when year <= birth_year + 18, else Life', () => {
        const fx = focusedFixture();
        const mod = loadModule(fx);
        const events = mod.buildRelativeEvents('@I1@');
        const father = events.find(e => e.year === 1895);
        const mother = events.find(e => e.year === 1920);
        expect(father.section).toBe('Early Life');
        expect(mother.section).toBe('Life');
    });

    it('intra-year sort: parent-death < child-birth < child-death < spouse-death', () => {
        const fx = {
            allPeople: [
                { id: '@F@', name: 'F',  birth_year: 1900, death_year: 1980, sex: 'F' },
                { id: '@P@', name: 'Pa', birth_year: 1870, death_year: 1950, sex: 'M' },
                { id: '@C1@', name: 'C1', birth_year: 1950, death_year: '',   sex: 'F' },
                { id: '@C2@', name: 'C2', birth_year: 1925, death_year: 1950, sex: 'M' },
                { id: '@S@', name: 'S',  birth_year: 1898, death_year: 1950, sex: 'M' },
            ],
            parents: { '@F@': ['@P@', null] },
            children: { '@F@': ['@C1@', '@C2@'] },
            families: { '@F1@': { husb: '@S@', wife: '@F@', chil: [], marr_year: 1922 } },
        };
        const mod = loadModule(fx);
        const events = mod.buildRelativeEvents('@F@');
        const yr1950 = events.filter(e => e.year === 1950);
        expect(yr1950.map(e => `${e.kind}-${e.role}`)).toEqual([
            'death-father',
            'birth-daughter',
            'death-son',
            'death-husband',
        ]);
    });
});

describe('buildRelativeEvents — Later Life', () => {
    it('assigns Later Life when relative death is at the focused person\'s death year', () => {
        const fx = {
            allPeople: [
                { id: '@F@', name: 'F',  birth_year: 1900, death_year: 1980, sex: 'F' },
                { id: '@S@', name: 'S',  birth_year: 1898, death_year: 1980, sex: 'M' },
            ],
            parents: {},
            children: {},
            families: { '@F1@': { husb: '@S@', wife: '@F@', chil: [], marr_year: 1922 } },
        };
        const mod = loadModule(fx);
        const events = mod.buildRelativeEvents('@F@');
        const spouseDeath = events.find(e => e.role === 'husband');
        expect(spouseDeath.section).toBe('Later Life');
    });

    it('assigns Life (not Later Life) when focus has no death year and event is past birth+18', () => {
        const fx = {
            allPeople: [
                { id: '@F@', name: 'F',  birth_year: 1900, death_year: '', sex: 'F' },
                { id: '@C@', name: 'C',  birth_year: 1950, death_year: 1990, sex: 'M' },
            ],
            parents: {},
            children: { '@F@': ['@C@'] },
            families: {},
        };
        const mod = loadModule(fx);
        const events = mod.buildRelativeEvents('@F@');
        const childDeath = events.find(e => e.kind === 'death' && e.role === 'son');
        // Focus has no death year → bounds.deathYear is null → no Later Life assignment.
        expect(childDeath.section).toBe('Life');
    });
});

describe('buildRelativeEvents — name fallback', () => {
    it('emits empty name string when relative has no name', () => {
        const fx = focusedFixture();
        fx.allPeople = fx.allPeople.map(p =>
            p.id === '@I2@' ? { ...p, name: '' } : p);
        const mod = loadModule(fx);
        const evt = mod.buildRelativeEvents('@I1@').find(e => e.year === 1904);
        expect(evt.name).toBe('');
        expect(evt.role).toBe('daughter');
    });
});
