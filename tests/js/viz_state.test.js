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
  vi.stubGlobal('history', { pushState: vi.fn() });

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
