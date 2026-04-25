# Link Existing Person — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When clicking "+ Parent", "+ Sibling", "+ Spouse", or "+ Child" in the info panel, let the user choose between creating a new person or linking to an existing person already in the tree.

**Architecture:** The existing `#add-person-modal` gains three panels (search, preview, create) driven by a `_addPersonMode` state variable in `viz_modals.js`. Selecting an existing person POSTs to a new `/api/link_person` endpoint; the "Add new" path continues to use the existing `/api/add_person` endpoint unchanged.

**Tech Stack:** Python 3 (serve_viz.py), JavaScript ES modules (viz_modals.js), Vitest (JS tests), pytest (Python tests)

**Spec:** `docs/superpowers/specs/2026-04-24-link-existing-person-design.md`

---

## File Map

| File | Change |
|------|--------|
| `tests/test_link_person.py` | **Create** — Python integration tests for `/api/link_person` |
| `serve_viz.py` | **Modify** — add `elif parsed.path == '/api/link_person':` handler after the `/api/add_person` block (~line 1950) |
| `tests/js/viz_modals.test.js` | **Modify** — add JS unit tests for `_filterAddPersonResults` |
| `viz_ancestors.html` | **Modify** — replace the flat field list inside `#add-person-modal` with three panels |
| `js/viz_modals.js` | **Modify** — add state vars, new functions, update click/input listeners, update exports |

---

## Task 1: Python tests for `/api/link_person`

**Files:**
- Create: `tests/test_link_person.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Integration tests for /api/link_person endpoint."""
import json
import os
import re
import shutil
import threading
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
import urllib.request
import urllib.error

import pytest

_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

import serve_viz  # noqa: E402

FIXTURE = Path(_FIXTURE_GED)


@pytest.fixture
def live_server(tmp_path):
    ged = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, ged)

    with patch.object(serve_viz, 'GED', ged), \
         patch.object(serve_viz, 'regenerate', return_value=None):
        server = HTTPServer(('127.0.0.1', 0), serve_viz.Handler)
        port = server.server_address[1]
        base = f'http://127.0.0.1:{port}'

        def _one_request():
            server.handle_request()

        def post(path, body):
            t = threading.Thread(target=_one_request, daemon=True)
            t.start()
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                base + path, data=data,
                headers={'Content-Type': 'application/json',
                         'Content-Length': str(len(data))},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())

        yield ged, post, server
        server.server_close()


def _ged_text(ged_path):
    return ged_path.read_text(encoding='utf-8')


def _fam_block(text, fam_xref):
    """Return the FAM block text for the given xref, or ''."""
    pattern = re.compile(
        r'(0 ' + re.escape(fam_xref) + r' FAM.*?)(?=\n0 )', re.DOTALL
    )
    m = pattern.search(text)
    return m.group(1) if m else ''


class TestLinkPersonEndpoint:

    def test_spouse_of_creates_new_fam_record(self, live_server):
        # @I2@ James Smith (M), @I14@ George Cooper (M) — unrelated
        ged, post, _ = live_server
        resp = post('/api/link_person', {
            'rel_xref': '@I2@',
            'link_xref': '@I14@',
            'rel_type': 'spouse_of',
        })
        assert resp['ok'] is True
        assert resp['xref'] == '@I14@'
        text = _ged_text(ged)
        # There must be a FAM containing both xrefs
        fam_blocks = re.findall(r'0 @F\w+@ FAM.*?(?=\n0 )', text, re.DOTALL)
        assert any('@I2@' in b and '@I14@' in b for b in fam_blocks)

    def test_spouse_of_does_not_create_new_indi(self, live_server):
        ged, post, _ = live_server
        before = _ged_text(ged).count('0 @I')
        post('/api/link_person', {
            'rel_xref': '@I2@',
            'link_xref': '@I14@',
            'rel_type': 'spouse_of',
        })
        after = _ged_text(ged).count('0 @I')
        assert before == after

    def test_parent_of_adds_wife_to_existing_famc(self, live_server):
        # @I6@ John Jones (M) has FAMC @F6@; @F6@ has HUSB @I10@ but no WIFE.
        # Link @I7@ Jane Brown (F) as parent_of @I6@ → adds WIFE @I7@ to @F6@.
        ged, post, _ = live_server
        resp = post('/api/link_person', {
            'rel_xref': '@I6@',
            'link_xref': '@I7@',
            'rel_type': 'parent_of',
        })
        assert resp['ok'] is True
        text = _ged_text(ged)
        f6 = _fam_block(text, '@F6@')
        assert '1 WIFE @I7@' in f6

    def test_parent_of_does_not_create_new_indi(self, live_server):
        ged, post, _ = live_server
        before = _ged_text(ged).count('0 @I')
        post('/api/link_person', {
            'rel_xref': '@I6@',
            'link_xref': '@I7@',
            'rel_type': 'parent_of',
        })
        assert _ged_text(ged).count('0 @I') == before

    def test_child_of_adds_link_xref_as_chil(self, live_server):
        # @I2@ James Smith has FAMS @F1@.
        # Link @I14@ George Cooper as child_of @I2@ with new family.
        ged, post, _ = live_server
        resp = post('/api/link_person', {
            'rel_xref': '@I2@',
            'link_xref': '@I14@',
            'rel_type': 'child_of',
            'other_parent_xref': '',
        })
        assert resp['ok'] is True
        text = _ged_text(ged)
        # A FAM containing @I2@ must now have CHIL @I14@
        fam_blocks = re.findall(r'0 @F\w+@ FAM.*?(?=\n0 )', text, re.DOTALL)
        assert any('@I2@' in b and '1 CHIL @I14@' in b for b in fam_blocks)
        # @I14@'s INDI block must have a FAMC tag
        i14_block = re.search(r'0 @I14@ INDI.*?(?=\n0 )', text, re.DOTALL)
        assert i14_block and '1 FAMC' in i14_block.group(0)

    def test_child_of_does_not_create_new_indi(self, live_server):
        ged, post, _ = live_server
        before = _ged_text(ged).count('0 @I')
        post('/api/link_person', {
            'rel_xref': '@I2@',
            'link_xref': '@I14@',
            'rel_type': 'child_of',
            'other_parent_xref': '',
        })
        assert _ged_text(ged).count('0 @I') == before

    def test_sibling_of_adds_link_xref_to_same_famc_family(self, live_server):
        # @I1@ Rose has FAMC @F1@.
        # Link @I14@ George Cooper as sibling_of @I1@ → adds @I14@ as CHIL to @F1@.
        ged, post, _ = live_server
        resp = post('/api/link_person', {
            'rel_xref': '@I1@',
            'link_xref': '@I14@',
            'rel_type': 'sibling_of',
        })
        assert resp['ok'] is True
        text = _ged_text(ged)
        f1 = _fam_block(text, '@F1@')
        assert '1 CHIL @I14@' in f1

    def test_sibling_of_does_not_create_new_indi(self, live_server):
        ged, post, _ = live_server
        before = _ged_text(ged).count('0 @I')
        post('/api/link_person', {
            'rel_xref': '@I1@',
            'link_xref': '@I14@',
            'rel_type': 'sibling_of',
        })
        assert _ged_text(ged).count('0 @I') == before

    def test_returns_updated_people_json(self, live_server):
        ged, post, _ = live_server
        resp = post('/api/link_person', {
            'rel_xref': '@I2@',
            'link_xref': '@I14@',
            'rel_type': 'spouse_of',
        })
        assert 'people' in resp
        assert '@I2@' in resp['people']
        assert '@I14@' in resp['people']
        assert 'family_maps' in resp

    def test_missing_link_xref_returns_400(self, live_server):
        ged, post, _ = live_server
        try:
            post('/api/link_person', {'rel_xref': '@I1@', 'rel_type': 'spouse_of'})
            pytest.fail('Expected HTTP 400')
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_missing_rel_xref_returns_400(self, live_server):
        ged, post, _ = live_server
        try:
            post('/api/link_person', {'link_xref': '@I1@', 'rel_type': 'spouse_of'})
            pytest.fail('Expected HTTP 400')
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_invalid_rel_type_returns_400(self, live_server):
        ged, post, _ = live_server
        try:
            post('/api/link_person', {
                'rel_xref': '@I1@', 'link_xref': '@I14@', 'rel_type': 'invalid'
            })
            pytest.fail('Expected HTTP 400')
        except urllib.error.HTTPError as e:
            assert e.code == 400
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_link_person.py -v
```

Expected: `FAILED` — `urllib.error.HTTPError: HTTP Error 404: Not Found` (endpoint doesn't exist yet)

---

## Task 2: Implement `/api/link_person` in serve_viz.py

**Files:**
- Modify: `serve_viz.py` (after the `/api/add_person` block, ~line 1950)

- [ ] **Step 1: Insert the new endpoint handler**

Find this comment in `serve_viz.py` (around line 1951):
```python
        # ------------------------------------------------------------------ #
        # Change / delete one of a child's parents                            #
        # ------------------------------------------------------------------ #

        elif parsed.path == '/api/change_parent':
```

Insert the following block **before** that comment:

```python
        # ------------------------------------------------------------------ #
        # Link an existing person into a relationship                         #
        # ------------------------------------------------------------------ #

        elif parsed.path == '/api/link_person':
            link_xref = (body.get('link_xref') or '').strip()
            rel_xref  = (body.get('rel_xref')  or '').strip()
            rel_type  = (body.get('rel_type')   or '').strip()

            if not link_xref:
                self.send_error(400, 'link_xref is required')
                return
            if not rel_xref:
                self.send_error(400, 'rel_xref is required')
                return
            if rel_type not in ('child_of', 'parent_of', 'spouse_of', 'sibling_of'):
                self.send_error(400, 'rel_type must be one of child_of, parent_of, spouse_of, sibling_of')
                return

            lines = GED.read_text(encoding='utf-8').splitlines()

            if rel_type == 'child_of':
                other_parent_xref = body.get('other_parent_xref')

                def _mk_bare_fam_with_lp(a_xref, b_xref):
                    fam_xref_local = _next_fam_xref(lines)
                    a_sex = _get_sex(lines, a_xref) if a_xref else None
                    b_sex = _get_sex(lines, b_xref) if b_xref else None
                    if a_sex == 'F' and b_sex != 'F':
                        husb, wife = b_xref, a_xref
                    elif b_sex == 'F' and a_sex != 'F':
                        husb, wife = a_xref, b_xref
                    else:
                        husb, wife = a_xref, b_xref
                    return fam_xref_local, husb, wife

                if other_parent_xref is None:
                    existing_fams = _get_fams_for_indi(lines, rel_xref)
                    if existing_fams:
                        fam_xref = existing_fams[0]
                    else:
                        fam_xref, husb, wife = _mk_bare_fam_with_lp(rel_xref, None)
                        lines = _create_bare_fam(lines, fam_xref, husb, wife)
                        lines = _add_fams_to_indi(lines, rel_xref, fam_xref)
                elif other_parent_xref == '':
                    fam_xref, husb, wife = _mk_bare_fam_with_lp(rel_xref, None)
                    lines = _create_bare_fam(lines, fam_xref, husb, wife)
                    lines = _add_fams_to_indi(lines, rel_xref, fam_xref)
                else:
                    other_parent_fams = set(_get_fams_for_indi(lines, other_parent_xref))
                    shared_fams = [f for f in _get_fams_for_indi(lines, rel_xref) if f in other_parent_fams]
                    if shared_fams:
                        fam_xref = shared_fams[0]
                    else:
                        fam_xref, husb, wife = _mk_bare_fam_with_lp(rel_xref, other_parent_xref)
                        lines = _create_bare_fam(lines, fam_xref, husb, wife)
                        lines = _add_fams_to_indi(lines, rel_xref, fam_xref)
                        lines = _add_fams_to_indi(lines, other_parent_xref, fam_xref)
                lines = _add_chil_to_fam(lines, fam_xref, link_xref)
                lines = _add_famc_to_indi(lines, link_xref, fam_xref)

            elif rel_type == 'parent_of':
                link_sex = _get_sex(lines, link_xref)
                famc_xref = _get_famc_for_indi(lines, rel_xref)
                if famc_xref:
                    fam_xref = famc_xref
                    slot = 'WIFE' if link_sex == 'F' else 'HUSB'
                    fam_start, fam_end, ferr = _find_fam_block(lines, fam_xref)
                    if not ferr:
                        slot_occupied = any(
                            (m := _TAG_RE.match(ln)) and m.group(2) == slot
                            for ln in lines[fam_start:fam_end]
                        )
                        if slot_occupied:
                            self.send_error(400, f'Family {fam_xref} already has a {slot}')
                            return
                        lines = lines[:fam_end] + [f'1 {slot} {link_xref}'] + lines[fam_end:]
                else:
                    fam_xref = _next_fam_xref(lines)
                    if link_sex == 'F':
                        lines = _create_bare_fam(lines, fam_xref, None, link_xref)
                    else:
                        lines = _create_bare_fam(lines, fam_xref, link_xref, None)
                    lines = _add_chil_to_fam(lines, fam_xref, rel_xref)
                    lines = _add_famc_to_indi(lines, rel_xref, fam_xref)
                lines = _add_fams_to_indi(lines, link_xref, fam_xref)

            elif rel_type == 'spouse_of':
                rel_sex  = _get_sex(lines, rel_xref)
                link_sex = _get_sex(lines, link_xref)
                fam_xref = _next_fam_xref(lines)
                if link_sex == 'F' and rel_sex != 'F':
                    husb_xref, wife_xref = rel_xref, link_xref
                elif rel_sex == 'F' and link_sex != 'F':
                    husb_xref, wife_xref = link_xref, rel_xref
                else:
                    husb_xref, wife_xref = link_xref, rel_xref
                lines = _create_bare_fam(lines, fam_xref, husb_xref, wife_xref)
                lines = _add_fams_to_indi(lines, link_xref, fam_xref)
                lines = _add_fams_to_indi(lines, rel_xref, fam_xref)

            elif rel_type == 'sibling_of':
                famc_xref = _get_famc_for_indi(lines, rel_xref)
                if famc_xref:
                    fam_xref = famc_xref
                else:
                    fam_xref = _next_fam_xref(lines)
                    lines = _create_bare_fam(lines, fam_xref, None, None)
                    lines = _add_chil_to_fam(lines, fam_xref, rel_xref)
                    lines = _add_famc_to_indi(lines, rel_xref, fam_xref)
                lines = _add_chil_to_fam(lines, fam_xref, link_xref)
                lines = _add_famc_to_indi(lines, link_xref, fam_xref)

            _write_gedcom_atomic(lines)
            print(f"[person-link] {link_xref} → {rel_type} {rel_xref}")
            regenerate(body.get('current_person'))
            viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
            indis, fams, sources = parse_gedcom(str(GED))
            updated = build_people_json({rel_xref, link_xref}, indis, fams=fams, sources=sources)
            family_maps = viz.build_family_maps(indis, fams)
            resp = json.dumps({'ok': True, 'xref': link_xref, 'people': updated,
                               'family_maps': family_maps}).encode()

```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_link_person.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
pytest tests/ -x -q
```

Expected: no failures (other than any pre-existing skips).

- [ ] **Step 4: Commit**

```bash
git add serve_viz.py tests/test_link_person.py
git commit -m "feat(api): add /api/link_person endpoint to link existing people

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: JS unit tests for `_filterAddPersonResults`

**Files:**
- Modify: `tests/js/viz_modals.test.js`

- [ ] **Step 1: Add the failing tests**

In `tests/js/viz_modals.test.js`, add to the imports at line 18 (the destructured require):

```javascript
const {
    _filterSpouseResults,
    _filterAddPersonResults,   // ← add this
    _isFamEventTag,
    // ... rest of existing imports unchanged
```

Then append a new describe block at the end of the file:

```javascript
// ── _filterAddPersonResults ───────────────────────────────────────────────

const ADD_SEARCH_PEOPLE = [
    { id: '@I1@', name: 'Rose Smith', birth_year: '1990', death_year: '' },
    { id: '@I2@', name: 'James Smith', birth_year: '1960', death_year: '' },
    { id: '@I3@', name: 'Clara Jones', birth_year: '1963', death_year: '' },
    { id: '@I4@', name: 'Patrick Smith', birth_year: '1930', death_year: '2005' },
    { id: '@I5@', name: 'Mary O\'Brien', birth_year: '1932', death_year: '' },
    { id: '@I6@', name: 'John Jones', birth_year: '1935', death_year: '' },
    { id: '@I7@', name: 'Jane Brown', birth_year: '1938', death_year: '' },
    { id: '@I8@', name: 'William Brown', birth_year: '1908', death_year: '' },
    { id: '@I9@', name: 'Helen Taylor', birth_year: '1910', death_year: '' },
    { id: '@I10@', name: 'Thomas Jones', birth_year: '1905', death_year: '' },
    { id: '@I11@', name: 'Alice Smith', birth_year: '1992', death_year: '' },
    { id: '@I12@', name: 'Mark Davis', birth_year: '1988', death_year: '' },
];

describe('_filterAddPersonResults', () => {
    it('returns empty array for empty query', () => {
        expect(_filterAddPersonResults('', ADD_SEARCH_PEOPLE)).toEqual([]);
    });

    it('returns empty array for whitespace-only query', () => {
        expect(_filterAddPersonResults('  ', ADD_SEARCH_PEOPLE)).toEqual([]);
    });

    it('returns people whose names include the query (case-insensitive)', () => {
        const results = _filterAddPersonResults('smith', ADD_SEARCH_PEOPLE);
        expect(results.map(p => p.id)).toEqual(
            expect.arrayContaining(['@I1@', '@I2@', '@I4@', '@I11@'])
        );
        expect(results.every(p => p.name.toLowerCase().includes('smith'))).toBe(true);
    });

    it('is case-insensitive', () => {
        const lower = _filterAddPersonResults('jones', ADD_SEARCH_PEOPLE);
        const upper = _filterAddPersonResults('JONES', ADD_SEARCH_PEOPLE);
        expect(lower.map(p => p.id)).toEqual(upper.map(p => p.id));
    });

    it('returns at most 10 results', () => {
        const many = Array.from({ length: 15 }, (_, i) => ({
            id: `@I${i + 100}@`, name: `John Smith ${i}`, birth_year: '1900', death_year: ''
        }));
        const results = _filterAddPersonResults('smith', many);
        expect(results.length).toBe(10);
    });

    it('returns empty array when no people match', () => {
        expect(_filterAddPersonResults('zzznothere', ADD_SEARCH_PEOPLE)).toEqual([]);
    });

    it('returns empty array when people list is empty', () => {
        expect(_filterAddPersonResults('smith', [])).toEqual([]);
    });
});
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
npm test -- --reporter=verbose 2>&1 | grep -A3 '_filterAddPersonResults'
```

Expected: `_filterAddPersonResults is not a function` (not yet exported)

---

## Task 4: HTML restructure + JS panel implementation

**Files:**
- Modify: `viz_ancestors.html` (lines 213–245)
- Modify: `js/viz_modals.js`

- [ ] **Step 1: Replace the add-person modal HTML**

In `viz_ancestors.html`, replace the entire block from line 213 through line 245:

```html
    <div id="add-person-modal-overlay" onclick="closeIfFarFromPanel(event,'add-person-modal',closeAddPersonModal)">
        <div id="add-person-modal" onkeydown="if(event.key==='Escape')closeAddPersonModal()">
            <h3 id="add-person-modal-title">Add Person</h3>
            <div class="event-modal-field">
                <label for="add-person-modal-given">Given name</label>
                <input type="text" id="add-person-modal-given" autocomplete="off">
            </div>
            <div class="event-modal-field">
                <label for="add-person-modal-surname">Surname</label>
                <input type="text" id="add-person-modal-surname" autocomplete="off">
            </div>
            <div class="event-modal-field">
                <label for="add-person-modal-sex">Sex</label>
                <select id="add-person-modal-sex">
                    <option value="U">Unknown</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                </select>
            </div>
            <div class="event-modal-field">
                <label for="add-person-modal-birth-year">Birth year</label>
                <input type="text" id="add-person-modal-birth-year" inputmode="numeric" autocomplete="off">
            </div>
            <div class="event-modal-field" id="add-person-modal-other-parent-row" style="display:none">
                <label for="add-person-modal-other-parent">Other parent</label>
                <select id="add-person-modal-other-parent"></select>
            </div>
            <div class="event-modal-actions">
                <button class="event-modal-cancel" onclick="closeAddPersonModal()">Cancel</button>
                <button class="event-modal-save" onclick="submitAddPersonModal()">Add</button>
            </div>
        </div>
    </div>
```

With this three-panel structure:

```html
    <div id="add-person-modal-overlay" onclick="closeIfFarFromPanel(event,'add-person-modal',closeAddPersonModal)">
        <div id="add-person-modal" onkeydown="if(event.key==='Escape')closeAddPersonModal()">
            <h3 id="add-person-modal-title">Add Person</h3>

            <!-- Panel: search (shown on open) -->
            <div id="add-person-panel-search">
                <div class="event-modal-field">
                    <input type="text" id="add-person-search-input" placeholder="Type a name…" autocomplete="off">
                    <div id="add-person-search-results"></div>
                </div>
                <div class="event-modal-actions">
                    <button class="event-modal-cancel" onclick="closeAddPersonModal()">Cancel</button>
                </div>
            </div>

            <!-- Panel: preview (hidden until existing person selected) -->
            <div id="add-person-panel-preview" style="display:none">
                <div class="add-person-preview-card">
                    <div id="add-person-preview-name" class="add-person-preview-name"></div>
                    <div id="add-person-preview-lifespan" class="add-person-preview-detail"></div>
                    <div id="add-person-preview-spouse" class="add-person-preview-detail"></div>
                </div>
                <div class="event-modal-field" id="add-person-preview-other-parent-row" style="display:none">
                    <label for="add-person-preview-other-parent">Other parent</label>
                    <select id="add-person-preview-other-parent"></select>
                </div>
                <div class="event-modal-actions">
                    <button class="event-modal-cancel" onclick="_showAddPersonPanel('search')">← Back</button>
                    <button class="event-modal-save" onclick="submitAddPersonModal()">Confirm link</button>
                </div>
            </div>

            <!-- Panel: create (hidden until "Add new" selected) -->
            <div id="add-person-panel-create" style="display:none">
                <div class="event-modal-field">
                    <label for="add-person-modal-given">Given name</label>
                    <input type="text" id="add-person-modal-given" autocomplete="off">
                </div>
                <div class="event-modal-field">
                    <label for="add-person-modal-surname">Surname</label>
                    <input type="text" id="add-person-modal-surname" autocomplete="off">
                </div>
                <div class="event-modal-field">
                    <label for="add-person-modal-sex">Sex</label>
                    <select id="add-person-modal-sex">
                        <option value="U">Unknown</option>
                        <option value="M">Male</option>
                        <option value="F">Female</option>
                    </select>
                </div>
                <div class="event-modal-field">
                    <label for="add-person-modal-birth-year">Birth year</label>
                    <input type="text" id="add-person-modal-birth-year" inputmode="numeric" autocomplete="off">
                </div>
                <div class="event-modal-field" id="add-person-modal-other-parent-row" style="display:none">
                    <label for="add-person-modal-other-parent">Other parent</label>
                    <select id="add-person-modal-other-parent"></select>
                </div>
                <div class="event-modal-actions">
                    <button class="event-modal-cancel" onclick="_showAddPersonPanel('search')">← Back</button>
                    <button class="event-modal-save" onclick="submitAddPersonModal()">Add person</button>
                </div>
            </div>

        </div>
    </div>
```

- [ ] **Step 2: Add state variables and new functions to viz_modals.js**

Find this block in `viz_modals.js` (~line 1696):
```javascript
let _addPersonRelXref = null,
    _addPersonRelType = null;
```

Replace it with:
```javascript
let _addPersonRelXref  = null,
    _addPersonRelType  = null,
    _addPersonMode     = 'search',   // 'search' | 'preview' | 'create'
    _addPersonLinkXref = null;
```

- [ ] **Step 3: Add `_filterAddPersonResults` and `_showAddPersonPanel` after the state vars**

Insert the following two functions after the `_ADD_PERSON_REL_LABELS` const (~line 1703), before `function openAddPersonModal`:

```javascript
function _filterAddPersonResults(query, people) {
    const q = (query || '').trim().toLowerCase();
    if (!q) return [];
    return (people || []).filter(p => p.name && p.name.toLowerCase().includes(q)).slice(0, 10);
}

function _showAddPersonPanel(mode) {
    _addPersonMode = mode;
    ['search', 'preview', 'create'].forEach(p => {
        const el = document.getElementById('add-person-panel-' + p);
        if (el) el.style.display = p === mode ? '' : 'none';
    });
    if (mode === 'search') {
        const inp = document.getElementById('add-person-search-input');
        if (inp) setTimeout(() => inp.focus && inp.focus(), 50);
    } else if (mode === 'create') {
        const inp = document.getElementById('add-person-modal-given');
        if (inp) setTimeout(() => inp.focus && inp.focus(), 50);
    }
}

function _renderAddPersonSearch(query) {
    const container = document.getElementById('add-person-search-results');
    if (!container) return;
    const hits = _filterAddPersonResults(query, typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : []);
    const q = (query || '').trim();
    container.innerHTML = hits.map(p =>
        `<div class="add-person-result-item" data-xref="${escHtml(p.id)}" data-name="${escHtml(p.name)}">${escHtml(p.name)}${p.birth_year ? ' (b. ' + escHtml(p.birth_year) + ')' : ''}</div>`
    ).join('') + (q ? `<div class="add-person-result-new" data-query="${escHtml(q)}">+ Add "${escHtml(q)}" as new person</div>` : '');
}

function _selectAddPersonExisting(xref) {
    _addPersonLinkXref = xref;
    const person = (typeof PEOPLE !== 'undefined' && PEOPLE[xref]) || {};

    const nameEl     = document.getElementById('add-person-preview-name');
    const lifespanEl = document.getElementById('add-person-preview-lifespan');
    const spouseEl   = document.getElementById('add-person-preview-spouse');
    const otherRow   = document.getElementById('add-person-preview-other-parent-row');
    const otherSel   = document.getElementById('add-person-preview-other-parent');

    if (nameEl) nameEl.textContent = person.name || xref;

    if (lifespanEl) {
        const parts = [];
        if (person.birth_year) parts.push('b. ' + person.birth_year);
        if (person.death_year) parts.push('d. ' + person.death_year);
        lifespanEl.textContent = parts.join(' · ');
    }

    if (spouseEl) {
        const marr = (person.events || []).find(e => e.tag === 'MARR');
        if (marr && marr.spouse) {
            const yr = marr.date ? (' m. ' + (marr.date.match(/\d{4}/) || [])[0]) : '';
            spouseEl.textContent = 'Spouse: ' + marr.spouse + yr;
            spouseEl.style.display = '';
        } else {
            spouseEl.textContent = '';
            spouseEl.style.display = 'none';
        }
    }

    // Mirror the other-parent dropdown into the preview panel for child_of
    if (otherRow && otherSel && _addPersonRelType === 'child_of') {
        const src = document.getElementById('add-person-modal-other-parent');
        if (src) otherSel.innerHTML = src.innerHTML;
        otherRow.style.display = '';
    } else if (otherRow) {
        otherRow.style.display = 'none';
    }

    _showAddPersonPanel('preview');
}

function _selectAddPersonNew(query) {
    _addPersonLinkXref = null;
    const givenEl = document.getElementById('add-person-modal-given');
    if (givenEl) givenEl.value = query || '';
    _showAddPersonPanel('create');
}
```

- [ ] **Step 4: Replace `openAddPersonModal` to start in search mode**

Replace the existing `openAddPersonModal` function (lines 1705–1746) with:

```javascript
function openAddPersonModal(xref, relType) {
    _addPersonRelXref  = xref;
    _addPersonRelType  = relType;
    _addPersonLinkXref = null;

    const overlayEl = document.getElementById('add-person-modal-overlay');
    const titleEl   = document.getElementById('add-person-modal-title');

    const label = _ADD_PERSON_REL_LABELS[relType] || 'Person';
    if (titleEl) titleEl.textContent = 'Add ' + label;

    // Reset search panel
    const searchEl  = document.getElementById('add-person-search-input');
    const resultsEl = document.getElementById('add-person-search-results');
    if (searchEl)  searchEl.value = '';
    if (resultsEl) resultsEl.innerHTML = '';

    // Prepare other-parent dropdown (used by both create and preview panels)
    const otherRowEl = document.getElementById('add-person-modal-other-parent-row');
    const otherSelEl = document.getElementById('add-person-modal-other-parent');
    if (relType === 'child_of' && otherSelEl && otherRowEl) {
        const person = PEOPLE[xref] || {};
        const seen = new Set();
        const spouses = [];
        for (const e of (person.events || [])) {
            if (e.tag === 'MARR' && e.spouse_xref && !seen.has(e.spouse_xref)) {
                seen.add(e.spouse_xref);
                spouses.push({ xref: e.spouse_xref, name: e.spouse || (PEOPLE[e.spouse_xref] && PEOPLE[e.spouse_xref].name) || e.spouse_xref });
            }
        }
        const opts = spouses.map(s => `<option value="${escHtml(s.xref)}">${escHtml(s.name)}</option>`).join('') +
            '<option value="__none__">No other parent (new family)</option>';
        otherSelEl.innerHTML = opts;
        otherSelEl.value = spouses.length ? spouses[0].xref : '__none__';
        otherRowEl.style.display = '';
    } else if (otherRowEl) {
        otherRowEl.style.display = 'none';
    }

    // Reset create form fields
    const givenEl = document.getElementById('add-person-modal-given');
    const surnEl  = document.getElementById('add-person-modal-surname');
    const sexEl   = document.getElementById('add-person-modal-sex');
    const byEl    = document.getElementById('add-person-modal-birth-year');
    if (givenEl) givenEl.value = '';
    if (surnEl)  surnEl.value  = '';
    if (sexEl)   sexEl.value   = 'U';
    if (byEl)    byEl.value    = '';

    _showAddPersonPanel('search');
    if (overlayEl) overlayEl.classList.add('open');
}
```

- [ ] **Step 5: Update `closeAddPersonModal` to reset mode**

Replace the existing `closeAddPersonModal` (lines 1748–1752):

```javascript
function closeAddPersonModal() {
    const overlayEl = document.getElementById('add-person-modal-overlay');
    if (overlayEl) overlayEl.classList.remove('open');
    _addPersonRelXref = _addPersonRelType = _addPersonLinkXref = null;
    _addPersonMode = 'search';
}
```

- [ ] **Step 6: Update `submitAddPersonModal` to route on mode**

Replace the existing `submitAddPersonModal` (lines 1867–1913) with:

```javascript
async function submitAddPersonModal() {
    if (_addPersonMode === 'preview') {
        // Link an existing person
        const linkXref = _addPersonLinkXref;
        const relXref  = _addPersonRelXref;
        const relType  = _addPersonRelType;
        if (!linkXref || !relXref || !relType) { alert('Missing relationship context.'); return; }

        const body = {
            link_xref: linkXref,
            rel_xref:  relXref,
            rel_type:  relType,
            current_person: window._currentPerson || null,
        };
        if (relType === 'child_of') {
            const otherSelEl = document.getElementById('add-person-preview-other-parent');
            const v = otherSelEl ? otherSelEl.value : '';
            body.other_parent_xref = (v === '__none__') ? '' : v;
        }

        try {
            const resp = await fetch('/api/link_person', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json();
            if (data.ok) {
                if (data.people)
                    for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
                if (typeof _applyFamilyMaps === 'function') _applyFamilyMaps(data.family_maps);
                closeAddPersonModal();
                window._openDetailKey = null;
                setState({ panelXref: relXref, panelOpen: true });
            } else {
                alert('Save failed: ' + (data.error || 'unknown error'));
            }
        } catch (e) {
            alert('Request failed: ' + e);
        }
        return;
    }

    // Create a new person (original flow)
    const given    = (document.getElementById('add-person-modal-given').value || '').trim();
    const surn     = (document.getElementById('add-person-modal-surname').value || '').trim();
    const sex      = document.getElementById('add-person-modal-sex').value || 'U';
    const birthYear = (document.getElementById('add-person-modal-birth-year').value || '').trim();
    const relXref  = _addPersonRelXref;
    const relType  = _addPersonRelType;

    if (!given) { alert('Given name is required.'); return; }
    if (!relXref || !relType) { alert('Missing relationship context.'); return; }

    const body = {
        given,
        surn,
        sex,
        birth_year: birthYear,
        rel_type: relType,
        rel_xref: relXref,
        current_person: window._currentPerson || null,
    };
    if (relType === 'child_of') {
        const otherSelEl = document.getElementById('add-person-modal-other-parent');
        const v = otherSelEl ? otherSelEl.value : '';
        body.other_parent_xref = (v === '__none__') ? '' : v;
    }

    try {
        const resp = await fetch('/api/add_person', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
            if (data.people)
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
            if (typeof _applyFamilyMaps === 'function') _applyFamilyMaps(data.family_maps);
            closeAddPersonModal();
            window._openDetailKey = null;
            setState({ panelXref: relXref, panelOpen: true });
        } else {
            alert('Save failed: ' + (data.error || 'unknown error'));
        }
    } catch (e) {
        alert('Request failed: ' + e);
    }
}
```

- [ ] **Step 7: Update the click and input event listeners**

Find the existing click listener (~line 1805):
```javascript
document.addEventListener('click', e => {
    const item = e.target.closest('.change-parent-result-item');
    if (item) _selectChangeParent(item.dataset.xref, item.dataset.name);
});
```

Replace it with:
```javascript
document.addEventListener('click', e => {
    const cpItem = e.target.closest('.change-parent-result-item');
    if (cpItem) { _selectChangeParent(cpItem.dataset.xref, cpItem.dataset.name); return; }

    const apItem = e.target.closest('.add-person-result-item');
    if (apItem) { _selectAddPersonExisting(apItem.dataset.xref); return; }

    const apNew = e.target.closest('.add-person-result-new');
    if (apNew) { _selectAddPersonNew(apNew.dataset.query); return; }
});
```

Find the existing input listener (~line 1810):
```javascript
document.addEventListener('input', e => {
    if (e.target.id === 'change-parent-modal-search') {
        _changeParentNewXref = null;
        _renderChangeParentResults(e.target.value);
    }
});
```

Replace it with:
```javascript
document.addEventListener('input', e => {
    if (e.target.id === 'change-parent-modal-search') {
        _changeParentNewXref = null;
        _renderChangeParentResults(e.target.value);
    }
    if (e.target.id === 'add-person-search-input') {
        _renderAddPersonSearch(e.target.value);
    }
});
```

- [ ] **Step 8: Add new functions to the module.exports block**

Find the `module.exports` block (~line 2097) and add to it:

```javascript
        _filterAddPersonResults,
        _showAddPersonPanel,
        _renderAddPersonSearch,
        _selectAddPersonExisting,
        _selectAddPersonNew,
        openAddPersonModal,
        closeAddPersonModal,
        submitAddPersonModal,
```

Add these lines after `_filterSpouseResults,` in the existing exports list.

- [ ] **Step 9: Run JS tests**

```bash
npm test -- --reporter=verbose 2>&1 | grep -A5 '_filterAddPersonResults'
```

Expected: all `_filterAddPersonResults` tests pass.

- [ ] **Step 10: Run full JS test suite**

```bash
npm test
```

Expected: no failures.

- [ ] **Step 11: Commit**

```bash
git add viz_ancestors.html js/viz_modals.js tests/js/viz_modals.test.js
git commit -m "feat(ui): add search-first panel flow to add-person modal

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: End-to-end browser verification

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server**

```bash
python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```

Open http://localhost:8000 in a browser.

- [ ] **Step 2: Test "+ Spouse" → select existing person → preview → confirm**

1. Click on any person in the tree to open their info panel
2. Scroll to the family section, click "+ Spouse"
3. Verify: modal opens showing a search input, no form fields visible
4. Type part of a name that exists in the tree
5. Verify: matching results appear with birth years; "Add '[name]' as new person" row at the bottom
6. Click an existing result
7. Verify: preview panel shows name, lifespan (b./d. years), spouse if any; "Confirm link" and "← Back" buttons visible
8. Click "← Back"
9. Verify: returns to search panel with previous query cleared
10. Select the result again, click "Confirm link"
11. Verify: modal closes, the family section now shows the linked person as a spouse

- [ ] **Step 3: Test "+ Child" → "Add new" → create panel with pre-filled name**

1. Click "+ Child" on a person
2. Type "Testname" in the search box
3. Click the "Add 'Testname' as new person" row
4. Verify: create form appears with "Testname" pre-filled in Given name; "← Back" button present
5. Click "← Back"
6. Verify: returns to search panel
7. Fill out the create form and click "Add person"
8. Verify: new person appears as a child in the family section

- [ ] **Step 4: Test "+ Child" → preview panel shows "Other parent" dropdown**

1. Click "+ Child" on a person who has a spouse
2. Select an existing person from search results
3. Verify: preview panel shows the "Other parent" dropdown with the spouse's name

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest tests/ -x -q && npm test
```

Expected: all tests pass.

- [ ] **Step 6: Final commit if any fixes needed**

```bash
git add -p
git commit -m "fix: address browser verification findings

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
