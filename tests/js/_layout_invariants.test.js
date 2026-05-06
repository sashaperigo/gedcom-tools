import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;
const { NODE_W, NODE_W_FOCUS } = DESIGN;

const {
    assertNoNodeOverlap,
} = require('./_layout_invariants.js');

describe('assertNoNodeOverlap', () => {
    it('passes when nodes at same y have non-overlapping x ranges', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            { xref: '@B@', x: NODE_W_FOCUS + 12, y: 0, role: 'spouse' },
            { xref: '@C@', x: 0, y: 148, role: 'descendant' },
        ];
        expect(() => assertNoNodeOverlap(nodes)).not.toThrow();
    });

    it('throws when two nodes at same y overlap', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'sibling' },
            { xref: '@B@', x: NODE_W / 2, y: 0, role: 'sibling' }, // overlaps @A@
        ];
        expect(() => assertNoNodeOverlap(nodes)).toThrow(/overlap/i);
    });

    it('uses NODE_W_FOCUS for focus-role nodes', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            // sibling at NODE_W away — overlaps because focus is wider
            { xref: '@B@', x: NODE_W, y: 0, role: 'sibling' },
        ];
        expect(() => assertNoNodeOverlap(nodes)).toThrow(/overlap/i);
    });

    it('ignores overlap across different y', () => {
        const nodes = [
            { xref: '@A@', x: 0, y: 0, role: 'focus' },
            { xref: '@B@', x: 0, y: 148, role: 'descendant' },
        ];
        expect(() => assertNoNodeOverlap(nodes)).not.toThrow();
    });
});
