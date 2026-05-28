import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { escapeHtml } = require('../../js/viz_html_utils.js');

describe('escapeHtml', () => {
    it('escapes double quotes to &quot;', () => {
        expect(escapeHtml('"hello"')).toBe('&quot;hello&quot;');
    });

    it('escapes &, <, >', () => {
        expect(escapeHtml('a & b < c > d')).toBe('a &amp; b &lt; c &gt; d');
    });

    it('handles null/undefined by returning empty string', () => {
        expect(escapeHtml(null)).toBe('');
        expect(escapeHtml(undefined)).toBe('');
    });
});
