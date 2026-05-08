import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// ── Fake DOM with controllable offsetTop ─────────────────────────────────

function makeEl(tag = 'span', { className = '', offsetTop = 0 } = {}) {
    const el = {
        tagName: tag.toUpperCase(),
        className,
        textContent: '',
        innerHTML: '',
        offsetTop,
        style: {},
        _children: [],
        _listeners: {},
        appendChild(node) { this._children.push(node); node._parent = this; },
        insertBefore(node, ref) {
            const idx = this._children.indexOf(ref);
            if (idx === -1) this._children.push(node);
            else this._children.splice(idx, 0, node);
            node._parent = this;
        },
        addEventListener(type, fn) {
            (this._listeners[type] ||= []).push(fn);
        },
        click() {
            (this._listeners.click || []).forEach(fn => fn({ target: this }));
        },
        querySelectorAll(selector) {
            return _walkMatches(this, selector);
        },
        querySelector(selector) {
            return _walkMatches(this, selector)[0] || null;
        },
        contains(node) {
            if (node === this) return true;
            return this._children.some(c => c.contains && c.contains(node));
        },
    };
    return el;
}

function _matches(el, selector) {
    if (selector.startsWith('.')) {
        const cls = selector.slice(1);
        return (el.className || '').split(/\s+/).includes(cls);
    }
    return false;
}

function _walkMatches(root, selector) {
    const out = [];
    const stack = [...root._children];
    while (stack.length) {
        const cur = stack.shift();
        if (_matches(cur, selector)) out.push(cur);
        if (cur._children) stack.push(...cur._children);
    }
    return out;
}

// document.createElement stub used by the helper
global.document = {
    createElement: (tag) => makeEl(tag),
};

const { _collapseAkaIfWrapped } = require('../../js/viz_panel.js');

// ── Helpers to build an AKA container ────────────────────────────────────

function buildAkaDiv({ entryTops, addBtnTop }) {
    const div = makeEl('div', { className: 'detail-aka-inner' });
    const entries = entryTops.map((top, i) => {
        const e = makeEl('span', { className: 'aka-entry', offsetTop: top });
        e.textContent = `entry${i}`;
        div.appendChild(e);
        return e;
    });
    const addBtn = makeEl('button', {
        className: 'aka-btn aka-add-btn',
        offsetTop: addBtnTop,
    });
    addBtn.textContent = '+ alias';
    div.appendChild(addBtn);
    return { div, entries, addBtn };
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('_collapseAkaIfWrapped', () => {
    it('does nothing when all entries and the add button fit on one row', () => {
        const { div, entries, addBtn } = buildAkaDiv({
            entryTops: [0, 0, 0],
            addBtnTop: 0,
        });

        _collapseAkaIfWrapped(div);

        entries.forEach(e => expect(e.style.display).toBeUndefined());
        expect(div.querySelector('.aka-more')).toBeNull();
        expect(addBtn.style.display).toBeUndefined();
    });

    it('hides entries on wrapped rows and inserts a +N more button', () => {
        const { div, entries, addBtn } = buildAkaDiv({
            entryTops: [0, 0, 20, 20, 20],
            addBtnTop: 20,
        });

        _collapseAkaIfWrapped(div);

        expect(entries[0].style.display).toBeUndefined();
        expect(entries[1].style.display).toBeUndefined();
        expect(entries[2].style.display).toBe('none');
        expect(entries[3].style.display).toBe('none');
        expect(entries[4].style.display).toBe('none');

        const moreBtn = div.querySelector('.aka-more');
        expect(moreBtn).not.toBeNull();
        expect(moreBtn.textContent).toBe('+3 more');

        // + alias still visible
        expect(addBtn.style.display).toBeUndefined();

        // moreBtn appears immediately before addBtn in child order
        const addIdx = div._children.indexOf(addBtn);
        const moreIdx = div._children.indexOf(moreBtn);
        expect(moreIdx).toBe(addIdx - 1);
    });

    it('keeps all entries when only the add button wraps', () => {
        // A full row of aliases should show even if `+ alias` overflows to
        // a second line — the add button stays visible on its own row.
        const { div, entries, addBtn } = buildAkaDiv({
            entryTops: [0, 0, 0, 0],
            addBtnTop: 20,
        });

        _collapseAkaIfWrapped(div);

        entries.forEach(e => expect(e.style.display).toBeUndefined());
        expect(div.querySelector('.aka-more')).toBeNull();
        expect(addBtn.style.display).toBeUndefined();
    });

    it('clicking +N more reveals hidden entries and changes label to "show less"', () => {
        const { div, entries } = buildAkaDiv({
            entryTops: [0, 20, 20],
            addBtnTop: 20,
        });

        _collapseAkaIfWrapped(div);
        const moreBtn = div.querySelector('.aka-more');
        expect(moreBtn.textContent).toBe('+2 more');

        moreBtn.click();

        expect(entries[1].style.display).toBe('');
        expect(entries[2].style.display).toBe('');
        expect(moreBtn.textContent).toBe('show less');
    });

    it('clicking "show less" re-collapses entries', () => {
        const { div, entries } = buildAkaDiv({
            entryTops: [0, 20, 20],
            addBtnTop: 20,
        });

        _collapseAkaIfWrapped(div);
        const moreBtn = div.querySelector('.aka-more');

        moreBtn.click(); // expand
        moreBtn.click(); // collapse again

        expect(entries[1].style.display).toBe('none');
        expect(entries[2].style.display).toBe('none');
        expect(moreBtn.textContent).toBe('+2 more');
    });

    it('does nothing when there are no aka entries', () => {
        const div = makeEl('div', { className: 'detail-aka-inner' });
        const addBtn = makeEl('button', { className: 'aka-btn aka-add-btn', offsetTop: 0 });
        div.appendChild(addBtn);

        expect(() => _collapseAkaIfWrapped(div)).not.toThrow();
        expect(div.querySelector('.aka-more')).toBeNull();
    });
});
