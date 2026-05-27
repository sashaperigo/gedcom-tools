// Regression test: in the browser, all <script src="/js/..."> tags share a
// single classic-script scope. Two `const`/`let`/`function` declarations of
// the same identifier at top level cause a parse-time SyntaxError that
// vitest's per-module ESM environment never sees.
//
// This test concatenates every viz_*.js file referenced by viz_ancestors.html
// in load order and tries to compile the result as one script. A duplicate
// top-level identifier will throw at `new vm.Script(...)`.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import vm from 'vm';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '../..');

function extractLocalScriptSrcs(html) {
    const srcs = [];
    const re = /<script\s+src="(\/js\/[^"]+)"\s*>\s*<\/script>/g;
    let m;
    while ((m = re.exec(html)) !== null) srcs.push(m[1]);
    return srcs;
}

describe('viz_ancestors.html script bundle', () => {
    it('compiles as a single classic-script scope without duplicate-identifier errors', () => {
        const html = readFileSync(resolve(repoRoot, 'viz_ancestors.html'), 'utf8');
        const srcs = extractLocalScriptSrcs(html);
        expect(srcs.length).toBeGreaterThan(0);

        const parts = srcs.map(src => {
            const abs = resolve(repoRoot, src.replace(/^\//, ''));
            return `// ===== ${src} =====\n` + readFileSync(abs, 'utf8');
        });
        const combined = parts.join('\n');

        expect(() => new vm.Script(combined, { filename: 'viz_ancestors_bundle.js' }))
            .not.toThrow();
    });
});
