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
  const req = createRequire(import.meta.url);
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
const require = createRequire(import.meta.url);

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

// ── Test suite ────────────────────────────────────────────────────────────

describe('expanded param serialization', () => {
  it('_expandedToParam returns null for empty Set', () => {
    const mod = loadModule('');
    expect(mod._expandedToParam(new Set())).toBeNull();
  });

  it('_expandedToParam returns sorted comma-joined xrefs without @ signs', () => {
    const mod = loadModule('');
    const result = mod._expandedToParam(new Set(['@I23@', '@I5@', '@I12@']));
    expect(result).toBe('I12,I23,I5');
  });

  it('_expandedToParam returns single xref without @ signs', () => {
    const mod = loadModule('');
    expect(mod._expandedToParam(new Set(['@I42@']))).toBe('I42');
  });

  it('_expandedFromParam returns empty Set when no expanded param', () => {
    const mod = loadModule('');
    expect(mod._expandedFromParam('')).toEqual(new Set());
  });

  it('_expandedFromParam returns empty Set for empty param value', () => {
    const mod = loadModule('');
    expect(mod._expandedFromParam('?expanded=')).toEqual(new Set());
  });

  it('_expandedFromParam parses multiple xrefs with @ wrappers', () => {
    const mod = loadModule('');
    expect(mod._expandedFromParam('?expanded=I5,I12,I23')).toEqual(
      new Set(['@I5@', '@I12@', '@I23@'])
    );
  });

  it('_expandedFromParam parses single xref', () => {
    const mod = loadModule('');
    expect(mod._expandedFromParam('?expanded=I5')).toEqual(new Set(['@I5@']));
  });
});

describe('initState', () => {
  it('uses rootXref when no ?person= param in URL', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    expect(mod.getState().focusXref).toBe('@I1@');
  });

  it('reads ?person=I42 from URL and reconstructs xref @I42@', () => {
    const mod = loadModule('?person=I42');
    mod.initState('@I1@');
    expect(mod.getState().focusXref).toBe('@I42@');
  });

  it('does NOT push to history on initState', () => {
    const mod = loadModule('?person=I42');
    mod.initState('@I1@');
    expect(global.history.pushState).not.toHaveBeenCalled();
  });

  it('reads ?expanded=I5,I12,I23 and reconstructs expandedNodes Set', () => {
    const mod = loadModule('?person=I42&expanded=I5,I12,I23');
    mod.initState('@I1@');
    expect(mod.getState().expandedNodes).toEqual(new Set(['@I5@', '@I12@', '@I23@']));
  });

  it('expandedNodes is empty Set when no ?expanded= param', () => {
    const mod = loadModule('?person=I42');
    mod.initState('@I1@');
    expect(mod.getState().expandedNodes).toEqual(new Set());
  });

  it('reads ?expanded= with empty value as empty Set', () => {
    const mod = loadModule('?person=I42&expanded=');
    mod.initState('@I1@');
    expect(mod.getState().expandedNodes).toEqual(new Set());
  });

  it('restores both focusXref and expandedNodes from URL', () => {
    const mod = loadModule('?person=I42&expanded=I5');
    mod.initState('@I1@');
    expect(mod.getState().focusXref).toBe('@I42@');
    expect(mod.getState().expandedNodes).toEqual(new Set(['@I5@']));
  });
});

describe('setState', () => {
  it('calls history.pushState with ?person=I42 when focusXref changes', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    mod.setState({ focusXref: '@I42@' });
    expect(global.history.pushState).toHaveBeenCalledOnce();
    const [, , url] = global.history.pushState.mock.calls[0];
    expect(url).toContain('?person=I42');
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
    // Clear any calls from initState (there should be none, but be safe)
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

  it('URL from replaceState contains sorted expanded= param', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    mod.setState({ expandedNodes: new Set(['@I23@', '@I5@']) });
    const [, , url] = global.history.replaceState.mock.calls[0];
    expect(url).toContain('?person=I1');
    expect(url).toContain('expanded=I23,I5');
  });

  it('expanded= param is omitted when expandedNodes is empty', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    mod.setState({ expandedNodes: new Set() });
    const [, , url] = global.history.replaceState.mock.calls[0];
    expect(url).not.toContain('expanded');
  });

  it('pushState URL contains both person= and expanded= when focusXref changes', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    mod.setState({ focusXref: '@I42@', expandedNodes: new Set(['@I5@']) });
    const [, , url] = global.history.pushState.mock.calls[0];
    expect(url).toContain('?person=I42');
    expect(url).toContain('expanded=I5');
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

  it('replaceState state object contains expandedXrefs field', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    mod.setState({ expandedNodes: new Set(['@I5@', '@I12@']) });
    const [stateObj] = global.history.replaceState.mock.calls[0];
    expect(stateObj).toHaveProperty('expandedXrefs', 'I12,I5');
  });
});

describe('popstate handler', () => {
  it('updates focusXref from popstate event state without pushing history', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    global.history.pushState.mockClear();

    // Fire the popstate listener
    const listeners = global._popstateListeners;
    expect(listeners.length).toBeGreaterThan(0);
    listeners[0]({ state: { focusXref: '@I5@' } });

    expect(mod.getState().focusXref).toBe('@I5@');
    // popstate should NOT push to history again
    expect(global.history.pushState).not.toHaveBeenCalled();
  });

  it('restores expandedNodes from URL on popstate', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    global.history.pushState.mockClear();

    vi.stubGlobal('location', makeURL('?person=I5&expanded=I12,I23'));
    const listeners = global._popstateListeners;
    listeners[0]({ state: null });

    expect(mod.getState().expandedNodes).toEqual(new Set(['@I12@', '@I23@']));
  });

  it('sets expandedNodes to empty Set on popstate with no expanded param', () => {
    const mod = loadModule('?person=I1&expanded=I5');
    mod.initState('@I1@');
    global.history.pushState.mockClear();

    vi.stubGlobal('location', makeURL('?person=I42'));
    const listeners = global._popstateListeners;
    listeners[0]({ state: null });

    expect(mod.getState().expandedNodes).toEqual(new Set());
  });

  it('restores expandedNodes from event.state.expandedXrefs when present', () => {
    const mod = loadModule('?person=I1&expanded=I99');
    mod.initState('@I1@');
    global.history.pushState.mockClear();

    // location still has I99 — but state has I7,I8
    const listeners = global._popstateListeners;
    listeners[0]({ state: { focusXref: '@I5@', expandedXrefs: 'I7,I8' } });

    expect(mod.getState().expandedNodes).toEqual(new Set(['@I7@', '@I8@']));
  });

  it('popstate does not call pushState or replaceState', () => {
    const mod = loadModule('');
    mod.initState('@I1@');
    global.history.pushState.mockClear();
    global.history.replaceState.mockClear();

    vi.stubGlobal('location', makeURL('?person=I5&expanded=I12'));
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
    expect(s.panelOpen).toBe(false);
    expect(s.panelXref).toBeNull();
  });
});
