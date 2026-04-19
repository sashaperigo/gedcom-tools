import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// ── setup ─────────────────────────────────────────────────────────────────

function makeFetchMock(responseData, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(responseData),
  });
}

beforeEach(() => {
  // Reset module between tests to pick up fresh fetch stub
  vi.resetModules();
});

function loadMod(fetchMock) {
  vi.stubGlobal('fetch', fetchMock);
  const req = createRequire(import.meta.url);
  // Bust require cache
  const modPath = require.resolve('../../js/viz_api.js');
  delete require.cache[modPath];
  return req('../../js/viz_api.js');
}

// ── apiDeleteFact ─────────────────────────────────────────────────────────

describe('apiDeleteFact', () => {
  it('calls fetch /api/delete_fact with correct body', async () => {
    const fetchMock = makeFetchMock({ ok: true, xref: '@I1@' });
    const mod = loadMod(fetchMock);

    await mod.apiDeleteFact('@I1@', 'birt_1');

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/delete_fact');
    expect(opts.method).toBe('POST');
    const body = JSON.parse(opts.body);
    expect(body.xref).toBe('@I1@');
    expect(body.fact_key).toBe('birt_1');
  });

  it('returns parsed JSON data on success', async () => {
    const responseData = { xref: '@I1@', name: 'John Smith' };
    const fetchMock = makeFetchMock(responseData);
    const mod = loadMod(fetchMock);

    const result = await mod.apiDeleteFact('@I1@', 'birt_1');
    expect(result).toEqual(responseData);
  });

  it('throws Error with message from response on failure', async () => {
    const fetchMock = makeFetchMock({ error: 'Fact not found' }, false);
    const mod = loadMod(fetchMock);

    await expect(mod.apiDeleteFact('@I1@', 'birt_1')).rejects.toThrow('Fact not found');
  });
});

// ── apiAddSource ──────────────────────────────────────────────────────────

describe('apiAddSource', () => {
  it('calls /api/add_source with correct body', async () => {
    const fetchMock = makeFetchMock({ xref: '@S1@' });
    const mod = loadMod(fetchMock);

    await mod.apiAddSource('My Source', 'Author', '');

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/add_source');
    const body = JSON.parse(opts.body);
    expect(body.titl).toBe('My Source');
    expect(body.auth).toBe('Author');
    expect(body.publ).toBe('');
  });
});

// ── generic _post error handling ──────────────────────────────────────────

describe('_post error handling', () => {
  it('uses fallback message "Request failed" when error field is absent', async () => {
    const fetchMock = makeFetchMock({}, false);
    const mod = loadMod(fetchMock);

    await expect(mod.apiDeleteNote('@I1@', 0)).rejects.toThrow('Request failed');
  });
});

// ── request format ────────────────────────────────────────────────────────

describe('apiAddNote', () => {
  it('sends Content-Type: application/json header', async () => {
    const fetchMock = makeFetchMock({ xref: '@I1@' });
    const mod = loadMod(fetchMock);

    await mod.apiAddNote('@I1@', 'Hello world');

    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.headers['Content-Type']).toBe('application/json');
  });
});

// ── apiConvertEvent ───────────────────────────────────────────────────────

describe('apiConvertEvent', () => {
  it('calls /api/convert_event with correct body', async () => {
    const fetchMock = makeFetchMock({ ok: true, people: {} });
    const mod = loadMod(fetchMock);

    await mod.apiConvertEvent('@I1@', 0, 'BIRT', 'BAPM');

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/convert_event');
    expect(opts.method).toBe('POST');
    const body = JSON.parse(opts.body);
    expect(body.xref).toBe('@I1@');
    expect(body.event_idx).toBe(0);
    expect(body.from_tag).toBe('BIRT');
    expect(body.to_tag).toBe('BAPM');
  });

  it('returns parsed JSON on success', async () => {
    const data = { ok: true, people: { '@I1@': { events: [] } } };
    const fetchMock = makeFetchMock(data);
    const mod = loadMod(fetchMock);

    const result = await mod.apiConvertEvent('@I1@', 0, 'BIRT', 'BAPM');
    expect(result).toEqual(data);
  });

  it('throws on server error', async () => {
    const fetchMock = makeFetchMock({ error: 'Event not found' }, false);
    const mod = loadMod(fetchMock);

    await expect(mod.apiConvertEvent('@I1@', 0, 'BIRT', 'BAPM')).rejects.toThrow('Event not found');
  });
});
