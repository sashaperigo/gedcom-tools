import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(
    import.meta.url);

// Redesign: utility functions moved to viz_design.js.
// escHtml is the shared HTML-escaping utility available to all modules.
const { escHtml } = require('../../js/viz_design.js');

// ── escHtml ────────────────────────────────────────────────────────────────

describe('escHtml', () => {
    it('escapes & < > "', () => {
        expect(escHtml('a & b')).toBe('a &amp; b');
        expect(escHtml('<b>')).toBe('&lt;b&gt;');
        expect(escHtml('"hi"')).toBe('&quot;hi&quot;');
    });
    it('leaves plain text unchanged', () => {
        expect(escHtml('hello world')).toBe('hello world');
    });
    it('handles null/undefined gracefully', () => {
        expect(escHtml(null)).toBe('');
        expect(escHtml(undefined)).toBe('');
    });
    it('escapes > character', () => {
        expect(escHtml('a > b')).toBe('a &gt; b');
    });
});