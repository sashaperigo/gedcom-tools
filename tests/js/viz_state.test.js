import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';

// ── helpers ───────────────────────────────────────────────────────────────

// We need to reset module state between tests because viz_state.js holds
// module-level mutable state (the state object and callbacks array).
// We do this by deleting the cached require and re-requiring each time.

function makeURL(search = '') {
    return { search };
}

function loadModule(search = '') {
    // Reset module cache
    vi.resetModules();
    const req = createRequire(
        import.meta.url);
    // Delete from require cache so we get a fresh copy
    const modPath = require.resolve('../../js/viz_state.js');
    delete require.cache[modPath];

    // Stub globals before require
    vi.stubGlobal('location', makeURL(search));
    vi.stubGlobal('history', { pushState: vi.fn(), replaceState: vi.fn() });

    const popstateListeners = [];
    vi.stubGlobal('addEventListener', (event, cb) => {
        if (event === 'popstate') popstateListeners.push(cb);
    });
    global._popstateListeners = popstateListeners;

    const mod = req('../../js/viz_state.js');
    return mod;
}

// Use createRequire at module level for initial load pattern
const require = createRequire(
    import.meta.url);

beforeEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
});

// ── Test suite ────────────────────────────────────────────────────────────

// Token values for test IDs (base62 of numeric suffix):
//   @I1@  → '1'   @I5@  → '5'   @I7@  → '7'   @I8@  → '8'
//   @I12@ → 'c'   @I23@ → 'n'   @I42@ → 'G'   @I99@ → '1B'

describe('base62 encoding', () => {
    it('_toBase62(0) returns "0"', () => {
        const mod = loadModule('');
        expect(mod._toBase62(0)).toBe('0');
    });

    it('_toBase62(42) returns "G"', () => {
        const mod = loadModule('');
        expect(mod._toBase62(42)).toBe('G');
    });

    it('_toBase62(380071267816) returns "6GRCj0Y"', () => {
        const mod = loadModule('');
        expect(mod._toBase62(380071267816)).toBe('6GRCj0Y');
    });

    it('_fromBase62("G") returns 42', () => {
        const mod = loadModule('');
        expect(mod._fromBase62('G')).toBe(42);
    });

    it('_fromBase62("6GRCj0Y") returns 380071267816', () => {
        const mod = loadModule('');
        expect(mod._fromBase62('6GRCj0Y')).toBe(380071267816);
    });

    it('_toBase62 / _fromBase62 roundtrip', () => {
        const mod = loadModule('');
        const n = 380071267816;
        expect(mod._fromBase62(mod._toBase62(n))).toBe(n);
    });

    it('_xrefToToken converts @I42@ to "G"', () => {
        const mod = loadModule('');
        expect(mod._xrefToToken('@I42@')).toBe('G');
    });

    it('_tokenToXref converts "G" to @I42@', () => {
        const mod = loadModule('');
        expect(mod._tokenToXref('G')).toBe('@I42@');
    });

    it('_xrefToToken / _tokenToXref roundtrip', () => {
        const mod = loadModule('');
        const xref = '@I380071267816@';
        expect(mod._tokenToXref(mod._xrefToToken(xref))).toBe(xref);
    });
});

describe('expanded param serialization', () => {
    it('_expandedToParam returns null for empty Set', () => {
        const mod = loadModule('');
        expect(mod._expandedToParam(new Set())).toBeNull();
    });

    it('_expandedToParam returns sorted +-joined tokens', () => {
        const mod = loadModule('');
        const result = mod._expandedToParam(new Set(['@I23@', '@I5@', '@I12@']));
        expect(result).toBe('5+c+n');
    });

    it('_expandedToParam returns single token for single xref', () => {
        const mod = loadModule('');
        expect(mod._expandedToParam(new Set(['@I42@']))).toBe('G');
    });

    it('_expandedFromParam returns empty Set when no e param', () => {
        const mod = loadModule('');
        expect(mod._expandedFromParam('')).toEqual(new Set());
    });

    it('_expandedFromParam returns empty Set for empty compact param value', () => {
        const mod = loadModule('');
        expect(mod._expandedFromParam('?e=')).toEqual(new Set());
    });

    it('_expandedFromParam parses multiple compact xrefs with + separator', () => {
        const mod = loadModule('');
        expect(mod._expandedFromParam('?e=5+c+n')).toEqual(
            new Set(['@I5@', '@I12@', '@I23@'])
        );
    });

    it('_expandedFromParam parses single compact xref', () => {
        const mod = loadModule('');
        expect(mod._expandedFromParam('?e=5')).toEqual(new Set(['@I5@']));
    });
});

describe('initState', () => {
    it('uses rootXref when no ?p= param in URL', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        expect(mod.getState().focusXref).toBe('@I1@');
    });

    it('reads ?p= compact token from URL', () => {
        const mod = loadModule('?p=G');
        mod.initState('@I1@');
        expect(mod.getState().focusXref).toBe('@I42@');
    });

    it('reads legacy ?person=I42 for backward compatibility', () => {
        const mod = loadModule('?person=I42');
        mod.initState('@I1@');
        expect(mod.getState().focusXref).toBe('@I42@');
    });

    it('does NOT push to history on initState', () => {
        const mod = loadModule('?p=G');
        mod.initState('@I1@');
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('reads ?e= compact param and reconstructs expandedNodes Set', () => {
        const mod = loadModule('?p=G&e=5+c+n');
        mod.initState('@I1@');
        expect(mod.getState().expandedNodes).toEqual(new Set(['@I5@', '@I12@', '@I23@']));
    });

    it('reads legacy ?expanded= for backward compatibility', () => {
        const mod = loadModule('?person=I42&expanded=I5,I12,I23');
        mod.initState('@I1@');
        expect(mod.getState().expandedNodes).toEqual(new Set(['@I5@', '@I12@', '@I23@']));
    });

    it('expandedNodes is empty Set when no ?e= param', () => {
        const mod = loadModule('?p=G');
        mod.initState('@I1@');
        expect(mod.getState().expandedNodes).toEqual(new Set());
    });

    it('reads ?e= with empty value as empty Set', () => {
        const mod = loadModule('?p=G&e=');
        mod.initState('@I1@');
        expect(mod.getState().expandedNodes).toEqual(new Set());
    });

    it('restores both focusXref and expandedNodes from compact URL', () => {
        const mod = loadModule('?p=G&e=5');
        mod.initState('@I1@');
        expect(mod.getState().focusXref).toBe('@I42@');
        expect(mod.getState().expandedNodes).toEqual(new Set(['@I5@']));
    });
});

describe('setState', () => {
    it('calls history.pushState with compact ?p= URL when focusXref changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ focusXref: '@I42@' });
        expect(global.history.pushState).toHaveBeenCalledOnce();
        const [, , url] = global.history.pushState.mock.calls[0];
        expect(url).toContain('?p=G');
    });

    it('calls registered onStateChange callbacks', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const cb = vi.fn();
        mod.onStateChange(cb);
        mod.setState({ focusXref: '@I42@' });
        expect(cb).toHaveBeenCalledOnce();
    });

    it('does NOT call history.pushState again when focusXref is unchanged', () => {
        const mod = loadModule('');
        mod.initState('@I42@');
        global.history.pushState.mockClear();
        mod.setState({ focusXref: '@I42@' });
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('does NOT push to history when only panelOpen changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();
        mod.setState({ panelOpen: true });
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('calls history.replaceState when only expandedNodes changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();
        mod.setState({ expandedNodes: new Set(['@I5@']) });
        expect(global.history.replaceState).toHaveBeenCalledOnce();
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('URL from replaceState contains compact sorted e= param with + separator', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedNodes: new Set(['@I23@', '@I5@']) });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).toContain('?p=1');
        expect(url).toContain('e=5+n');
    });

    it('e= param is omitted when expandedNodes is empty', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedNodes: new Set() });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).not.toContain('e=');
    });

    it('pushState URL contains compact p= and e= when focusXref changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ focusXref: '@I42@', expandedNodes: new Set(['@I5@']) });
        const [, , url] = global.history.pushState.mock.calls[0];
        expect(url).toContain('?p=G');
        expect(url).toContain('e=5');
    });

    it('when both focusXref and expandedNodes change, only pushState is called', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ focusXref: '@I42@', expandedNodes: new Set(['@I5@']) });
        expect(global.history.pushState).toHaveBeenCalledOnce();
        expect(global.history.replaceState).not.toHaveBeenCalled();
    });

    it('does NOT call replaceState when only panelOpen changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ panelOpen: true });
        expect(global.history.replaceState).not.toHaveBeenCalled();
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('does NOT call replaceState when expandedNodes reference is unchanged', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const sameSet = new Set(['@I5@']);
        mod.setState({ expandedNodes: sameSet });
        global.history.replaceState.mockClear();
        mod.setState({ expandedNodes: sameSet });
        expect(global.history.replaceState).not.toHaveBeenCalled();
    });

    it('replaceState state object contains expandedXrefs as +-joined tokens', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedNodes: new Set(['@I5@', '@I12@']) });
        const [stateObj] = global.history.replaceState.mock.calls[0];
        expect(stateObj).toHaveProperty('expandedXrefs', '5+c');
    });
});

describe('popstate handler', () => {
    it('updates focusXref from popstate event state without pushing history', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();

        const listeners = global._popstateListeners;
        expect(listeners.length).toBeGreaterThan(0);
        listeners[0]({ state: { focusXref: '@I5@' } });

        expect(mod.getState().focusXref).toBe('@I5@');
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('restores expandedNodes from compact URL on popstate', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();

        vi.stubGlobal('location', makeURL('?p=5&e=c+n'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });

        expect(mod.getState().expandedNodes).toEqual(new Set(['@I12@', '@I23@']));
    });

    it('restores expandedNodes from legacy URL on popstate', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();

        vi.stubGlobal('location', makeURL('?person=I5&expanded=I12,I23'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });

        expect(mod.getState().expandedNodes).toEqual(new Set(['@I12@', '@I23@']));
    });

    it('sets expandedNodes to empty Set on popstate with no e param', () => {
        const mod = loadModule('?p=1&e=5');
        mod.initState('@I1@');
        global.history.pushState.mockClear();

        vi.stubGlobal('location', makeURL('?p=G'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });

        expect(mod.getState().expandedNodes).toEqual(new Set());
    });

    it('restores expandedNodes from event.state.expandedXrefs when present', () => {
        const mod = loadModule('?p=1&e=1B');
        mod.initState('@I1@');
        global.history.pushState.mockClear();

        const listeners = global._popstateListeners;
        listeners[0]({ state: { focusXref: '@I5@', expandedXrefs: '7+8' } });

        expect(mod.getState().expandedNodes).toEqual(new Set(['@I7@', '@I8@']));
    });

    it('popstate does not call pushState or replaceState', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();
        global.history.replaceState.mockClear();

        vi.stubGlobal('location', makeURL('?p=5&e=c'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });

        expect(global.history.pushState).not.toHaveBeenCalled();
        expect(global.history.replaceState).not.toHaveBeenCalled();
    });
});

describe('getState', () => {
    it('returns initial state shape', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const s = mod.getState();
        expect(s).toHaveProperty('focusXref');
        expect(s).toHaveProperty('expandedNodes');
        expect(s).toHaveProperty('panelOpen');
        expect(s).toHaveProperty('panelXref');
        expect(s).toHaveProperty('expandedSiblingsXrefs');
        expect(s.expandedSiblingsXrefs).toEqual(new Set());
        expect(s.panelOpen).toBe(false);
        expect(s.panelXref).toBeNull();
    });
});

// ── Sibling expansion state ─────────────────────────────────────────────────

describe('siblings param serialization', () => {
    it('_siblingsToParam returns null for empty Set', () => {
        const mod = loadModule('');
        expect(mod._siblingsToParam(new Set())).toBeNull();
    });

    it('_siblingsToParam returns sorted +-joined tokens', () => {
        const mod = loadModule('');
        expect(mod._siblingsToParam(new Set(['@I23@', '@I5@', '@I12@']))).toBe('5+c+n');
    });

    it('_siblingsFromParam returns empty Set when no s param', () => {
        const mod = loadModule('');
        expect(mod._siblingsFromParam('')).toEqual(new Set());
    });

    it('_siblingsFromParam parses multiple compact xrefs with + separator', () => {
        const mod = loadModule('');
        expect(mod._siblingsFromParam('?s=5+c')).toEqual(new Set(['@I5@', '@I12@']));
    });

    it('_siblingsFromParam ignores ?e= param', () => {
        const mod = loadModule('');
        expect(mod._siblingsFromParam('?e=5')).toEqual(new Set());
    });
});

describe('initState with siblings', () => {
    it('reads ?s= compact param and reconstructs expandedSiblingsXrefs Set', () => {
        const mod = loadModule('?p=G&s=5+c');
        mod.initState('@I1@');
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set(['@I5@', '@I12@']));
    });

    it('reads legacy ?siblings= for backward compatibility', () => {
        const mod = loadModule('?person=I42&siblings=I5,I12');
        mod.initState('@I1@');
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set(['@I5@', '@I12@']));
    });

    it('expandedSiblingsXrefs is empty Set when no ?s= param', () => {
        const mod = loadModule('?p=G');
        mod.initState('@I1@');
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set());
    });

    it('restores all three: focusXref, expandedNodes, expandedSiblingsXrefs from compact URL', () => {
        const mod = loadModule('?p=G&e=5&s=8');
        mod.initState('@I1@');
        const s = mod.getState();
        expect(s.focusXref).toBe('@I42@');
        expect(s.expandedNodes).toEqual(new Set(['@I5@']));
        expect(s.expandedSiblingsXrefs).toEqual(new Set(['@I8@']));
    });
});

describe('setState with siblings', () => {
    it('calls history.replaceState when only expandedSiblingsXrefs changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();
        mod.setState({ expandedSiblingsXrefs: new Set(['@I5@']) });
        expect(global.history.replaceState).toHaveBeenCalledOnce();
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('URL from replaceState contains compact sorted s= param with + separator', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedSiblingsXrefs: new Set(['@I23@', '@I5@']) });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).toContain('s=5+n');
    });

    it('s= param is omitted when expandedSiblingsXrefs is empty', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedSiblingsXrefs: new Set() });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).not.toContain('s=');
    });

    it('does NOT call replaceState when expandedSiblingsXrefs reference is unchanged', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const sameSet = new Set(['@I5@']);
        mod.setState({ expandedSiblingsXrefs: sameSet });
        global.history.replaceState.mockClear();
        mod.setState({ expandedSiblingsXrefs: sameSet });
        expect(global.history.replaceState).not.toHaveBeenCalled();
    });

    it('pushState URL contains compact p=, e=, and s= when focusXref changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({
            focusXref: '@I42@',
            expandedNodes: new Set(['@I5@']),
            expandedSiblingsXrefs: new Set(['@I8@']),
        });
        const [, , url] = global.history.pushState.mock.calls[0];
        expect(url).toContain('?p=G');
        expect(url).toContain('e=5');
        expect(url).toContain('s=8');
    });

    it('replaceState state object contains siblingsXrefs as +-joined tokens', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedSiblingsXrefs: new Set(['@I5@', '@I12@']) });
        const [stateObj] = global.history.replaceState.mock.calls[0];
        expect(stateObj).toHaveProperty('siblingsXrefs', '5+c');
    });

    it('changing both expanded sets in one call triggers exactly one replaceState', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.replaceState.mockClear();
        mod.setState({
            expandedNodes: new Set(['@I5@']),
            expandedSiblingsXrefs: new Set(['@I8@']),
        });
        expect(global.history.replaceState).toHaveBeenCalledOnce();
        expect(global.history.pushState).not.toHaveBeenCalled();
    });
});

describe('popstate with siblings', () => {
    it('restores expandedSiblingsXrefs from event.state.siblingsXrefs', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const listeners = global._popstateListeners;
        listeners[0]({ state: { focusXref: '@I5@', siblingsXrefs: '7+8' } });
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set(['@I7@', '@I8@']));
    });

    it('restores expandedSiblingsXrefs from compact URL when state is null', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        vi.stubGlobal('location', makeURL('?p=5&s=c+n'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set(['@I12@', '@I23@']));
    });

    it('restores expandedSiblingsXrefs from legacy URL when state is null', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        vi.stubGlobal('location', makeURL('?person=I5&siblings=I12,I23'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set(['@I12@', '@I23@']));
    });

    it('sets expandedSiblingsXrefs to empty Set on popstate with no s param', () => {
        const mod = loadModule('?p=1&s=5');
        mod.initState('@I1@');
        vi.stubGlobal('location', makeURL('?p=G'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });
        expect(mod.getState().expandedSiblingsXrefs).toEqual(new Set());
    });
});

// ── Children expansion state (person xrefs) ─────────────────────────────────
// Uses INDI xrefs like @I42@.
// Token values for test INDI IDs (base62 of numeric suffix):
//   @I5@ → '5'   @I7@ → '7'   @I8@ → '8'
//   @I12@ → 'c'  @I23@ → 'n'  @I42@ → 'G'

describe('children (persons) param serialization', () => {
    it('_childrenPersonsToParam returns null for empty Set', () => {
        const mod = loadModule('');
        expect(mod._childrenPersonsToParam(new Set())).toBeNull();
    });

    it('_childrenPersonsToParam returns sorted +-joined tokens', () => {
        const mod = loadModule('');
        expect(mod._childrenPersonsToParam(new Set(['@I23@', '@I5@', '@I12@']))).toBe('5+c+n');
    });

    it('_childrenPersonsFromParam returns empty Set when no c param', () => {
        const mod = loadModule('');
        expect(mod._childrenPersonsFromParam('')).toEqual(new Set());
    });

    it('_childrenPersonsFromParam parses multiple compact xrefs with + separator', () => {
        const mod = loadModule('');
        expect(mod._childrenPersonsFromParam('?c=5+c')).toEqual(new Set(['@I5@', '@I12@']));
    });

    it('_childrenPersonsFromParam decodes INDI xrefs (not FAM)', () => {
        const mod = loadModule('');
        expect(mod._childrenPersonsFromParam('?c=G')).toEqual(new Set(['@I42@']));
    });

    it('_childrenPersonsFromParam ignores ?e= and ?s= params', () => {
        const mod = loadModule('');
        expect(mod._childrenPersonsFromParam('?e=5&s=c')).toEqual(new Set());
    });
});

describe('initState with childrenPersons', () => {
    it('reads ?c= compact param and reconstructs expandedChildrenPersons Set', () => {
        const mod = loadModule('?p=G&c=5+c');
        mod.initState('@I1@');
        expect(mod.getState().expandedChildrenPersons).toEqual(new Set(['@I5@', '@I12@']));
    });

    it('expandedChildrenPersons is empty Set when no ?c= param', () => {
        const mod = loadModule('?p=G');
        mod.initState('@I1@');
        expect(mod.getState().expandedChildrenPersons).toEqual(new Set());
    });

    it('restores all four: focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenPersons', () => {
        const mod = loadModule('?p=G&e=5&s=8&c=c');
        mod.initState('@I1@');
        const s = mod.getState();
        expect(s.focusXref).toBe('@I42@');
        expect(s.expandedNodes).toEqual(new Set(['@I5@']));
        expect(s.expandedSiblingsXrefs).toEqual(new Set(['@I8@']));
        expect(s.expandedChildrenPersons).toEqual(new Set(['@I12@']));
    });
});

describe('setState with childrenPersons', () => {
    it('calls history.replaceState when only expandedChildrenPersons changes', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        global.history.pushState.mockClear();
        mod.setState({ expandedChildrenPersons: new Set(['@I5@']) });
        expect(global.history.replaceState).toHaveBeenCalledOnce();
        expect(global.history.pushState).not.toHaveBeenCalled();
    });

    it('URL from replaceState contains compact sorted c= param with + separator', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedChildrenPersons: new Set(['@I23@', '@I5@']) });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).toContain('c=5+n');
    });

    it('c= param is omitted when expandedChildrenPersons is empty', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedChildrenPersons: new Set() });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).not.toContain('c=');
    });

    it('does NOT call replaceState when expandedChildrenPersons reference is unchanged', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const sameSet = new Set(['@I5@']);
        mod.setState({ expandedChildrenPersons: sameSet });
        global.history.replaceState.mockClear();
        mod.setState({ expandedChildrenPersons: sameSet });
        expect(global.history.replaceState).not.toHaveBeenCalled();
    });

    it('pushState URL contains p=, e=, s=, and c= when focusXref changes with all sets', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({
            focusXref: '@I42@',
            expandedNodes: new Set(['@I5@']),
            expandedSiblingsXrefs: new Set(['@I8@']),
            expandedChildrenPersons: new Set(['@I12@']),
        });
        const [, , url] = global.history.pushState.mock.calls[0];
        expect(url).toContain('?p=G');
        expect(url).toContain('e=5');
        expect(url).toContain('s=8');
        expect(url).toContain('c=c');
    });

    it('replaceState state object contains childrenPersonsXrefs as +-joined tokens', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ expandedChildrenPersons: new Set(['@I5@', '@I12@']) });
        const [stateObj] = global.history.replaceState.mock.calls[0];
        expect(stateObj).toHaveProperty('childrenPersonsXrefs', '5+c');
    });
});

describe('popstate with childrenPersons', () => {
    it('restores expandedChildrenPersons from event.state.childrenPersonsXrefs', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const listeners = global._popstateListeners;
        listeners[0]({ state: { focusXref: '@I5@', childrenPersonsXrefs: '7+8' } });
        expect(mod.getState().expandedChildrenPersons).toEqual(new Set(['@I7@', '@I8@']));
    });

    it('restores expandedChildrenPersons from compact URL when state is null', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        vi.stubGlobal('location', makeURL('?p=5&c=c+n'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });
        expect(mod.getState().expandedChildrenPersons).toEqual(new Set(['@I12@', '@I23@']));
    });

    it('sets expandedChildrenPersons to empty Set on popstate with no c param', () => {
        const mod = loadModule('?p=1&c=5');
        mod.initState('@I1@');
        vi.stubGlobal('location', makeURL('?p=G'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });
        expect(mod.getState().expandedChildrenPersons).toEqual(new Set());
    });
});

describe('getState includes expandedChildrenPersons', () => {
    it('initial state includes expandedChildrenPersons as empty Set', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const s = mod.getState();
        expect(s).toHaveProperty('expandedChildrenPersons');
        expect(s.expandedChildrenPersons).toEqual(new Set());
    });
});

describe('visibleSpouseFams — serialization and URL round-trip', () => {
    it('initial state has empty visibleSpouseFams', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        expect(mod.getState().visibleSpouseFams).toEqual(new Set());
    });

    it('initState reads m= param and decodes FAM xrefs', () => {
        const mod = loadModule('?p=1&m=5+c');
        mod.initState('@I1@');
        expect(mod.getState().visibleSpouseFams).toEqual(new Set(['@F5@', '@F12@']));
    });

    it('setState with visibleSpouseFams calls replaceState and emits m= param', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ visibleSpouseFams: new Set(['@F5@', '@F23@']) });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).toContain('m=5+n');
    });

    it('m= param omitted when visibleSpouseFams is empty', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ visibleSpouseFams: new Set() });
        const [, , url] = global.history.replaceState.mock.calls[0];
        expect(url).not.toContain('m=');
    });

    it('popstate restores visibleSpouseFams from event.state', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        const listeners = global._popstateListeners;
        listeners[0]({ state: { focusXref: '@I5@', visibleSpouseFamsXrefs: '7+8' } });
        expect(mod.getState().visibleSpouseFams).toEqual(new Set(['@F7@', '@F8@']));
    });

    it('popstate restores visibleSpouseFams from raw URL when state is null', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        vi.stubGlobal('location', makeURL('?p=5&m=c+n'));
        const listeners = global._popstateListeners;
        listeners[0]({ state: null });
        expect(mod.getState().visibleSpouseFams).toEqual(new Set(['@F12@', '@F23@']));
    });

    it('replaceState state object contains visibleSpouseFamsXrefs', () => {
        const mod = loadModule('');
        mod.initState('@I1@');
        mod.setState({ visibleSpouseFams: new Set(['@F5@', '@F12@']) });
        const [stateObj] = global.history.replaceState.mock.calls[0];
        expect(stateObj).toHaveProperty('visibleSpouseFamsXrefs', '5+c');
    });
});

describe('resetToRoot', () => {
    it('clears expandedChildrenPersons from URL (c= param absent after reset)', () => {
        const mod = loadModule('?p=G&c=c+n');
        mod.initState('@I1@');
        mod.resetToRoot('@I1@');
        const [, , url] = global.history.pushState.mock.calls.at(-1);
        expect(url).not.toContain('c=');
    });

    it('clears expandedNodes and expandedSiblingsXrefs from URL', () => {
        const mod = loadModule('?p=G&e=5&s=8&c=c');
        mod.initState('@I1@');
        mod.resetToRoot('@I1@');
        const [, , url] = global.history.pushState.mock.calls.at(-1);
        expect(url).not.toContain('e=');
        expect(url).not.toContain('s=');
        expect(url).not.toContain('c=');
    });

    it('restores focusXref to root', () => {
        const mod = loadModule('?p=G');
        mod.initState('@I1@');
        mod.resetToRoot('@I1@');
        expect(mod.getState().focusXref).toBe('@I1@');
    });

    it('URL is just ?p=<rootToken> after reset', () => {
        const mod = loadModule('?p=G&e=5&s=8&c=c');
        mod.initState('@I1@');
        mod.resetToRoot('@I1@');
        const [, , url] = global.history.pushState.mock.calls.at(-1);
        expect(url).toBe('?p=1');
    });

    it('resets state even when already at root (URL still gets rewritten)', () => {
        const mod = loadModule('?p=1&c=c');
        mod.initState('@I1@');
        global.history.replaceState.mockClear();
        global.history.pushState.mockClear();
        mod.resetToRoot('@I1@');
        const calls = [
            ...global.history.pushState.mock.calls,
            ...global.history.replaceState.mock.calls,
        ];
        expect(calls.length).toBeGreaterThan(0);
        const [, , url] = calls[calls.length - 1];
        expect(url).toBe('?p=1');
    });

    it('getState reflects empty sets after reset', () => {
        const mod = loadModule('?p=G&e=5&s=8&c=c');
        mod.initState('@I1@');
        mod.resetToRoot('@I1@');
        const s = mod.getState();
        expect(s.expandedNodes).toEqual(new Set());
        expect(s.expandedSiblingsXrefs).toEqual(new Set());
        expect(s.expandedChildrenPersons).toEqual(new Set());
    });

    it('clears visibleSpouseFams too', () => {
        const mod = loadModule('?p=G&m=5+c');
        mod.initState('@I1@');
        mod.resetToRoot('@I1@');
        const [, , url] = global.history.pushState.mock.calls.at(-1);
        expect(url).not.toContain('m=');
        expect(mod.getState().visibleSpouseFams).toEqual(new Set());
    });
});