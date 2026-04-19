# Citation URL Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a URL field to the Add Citation and Edit Citation modals that writes `DATA/WWW` to the GEDCOM citation block.

**Architecture:** Thread `url` through six layers: HTML modal template → JS modal functions → JS API wrapper → Python HTTP handler → `_build_citation_lines` writer → round-trips back via the existing parser which already reads `WWW` at fact-level. The edit-citation modal HTML is currently missing entirely and must be created.

**Tech Stack:** Python (serve_viz.py, viz_ancestors.py), vanilla JS (js/viz_modals.js, js/viz_api.js), Jest (JS tests), pytest (Python tests)

---

## File Map

| File | Change |
|------|--------|
| `viz_ancestors.py` | Add URL field to add-citation modal HTML; add edit-citation modal HTML + CSS |
| `js/viz_modals.js` | Thread `url` through all 4 modal functions |
| `js/viz_api.js` | Add `url` param to `apiAddCitation` and `apiEditCitation` |
| `serve_viz.py` | Read `url` in both handlers; add `url`/`WWW` to `_build_citation_lines` and `_update_citation_block` |
| `tests/test_serve_viz_http.py` | HTTP integration tests for url round-trip |
| `tests/js/viz_modals.test.js` | JS unit tests for url field population and submission |

---

### Task 1: Add `url` to `_build_citation_lines` and `_update_citation_block`

**Files:**
- Modify: `serve_viz.py:892-922`
- Test: `tests/test_serve_viz_http.py` (new test class)

- [ ] **Step 1: Write the failing Python unit test**

There is no direct unit test for `_build_citation_lines` — test it via the HTTP endpoint. Add to `tests/test_serve_viz_http.py` at the end of `class TestAddCitationEndpoint`:

```python
def test_add_citation_with_url_writes_www_under_data(self, live_server):
    ged, post, _, _ = live_server
    sour_xref = self._add_source(post)
    resp = post('/api/add_citation', {
        'xref': '@I1@', 'sour_xref': sour_xref,
        'fact_key': 'BIRT:0', 'page': '', 'text': '', 'note': '',
        'url': 'https://example.com/record/42',
    })
    assert resp.get('ok') is True
    text = _ged_text(ged)
    lines = text.splitlines()
    # Find the BIRT block for @I1@, then locate the SOUR citation inside it
    in_i1 = False; in_birt = False; in_data = False; found = False
    for ln in lines:
        if ln.startswith('0 @I1@ INDI'):  in_i1 = True; continue
        if in_i1 and ln.startswith('0 '): break
        if in_i1 and ln == '1 BIRT':      in_birt = True; continue
        if in_birt and ln.startswith('1 '): in_birt = False
        if in_birt and ln.startswith(f'2 SOUR {sour_xref}'): in_data = True; continue
        if in_data and ln == '3 DATA':    continue
        if in_data and ln == '4 WWW https://example.com/record/42': found = True; break
    assert found, f'4 WWW not found under BIRT SOUR block in @I1@\n{text}'
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
python -m pytest tests/test_serve_viz_http.py::TestAddCitationEndpoint::test_add_citation_with_url_writes_www_under_data -v 2>&1 | tail -15
```

Expected: FAIL — `4 WWW not found under BIRT SOUR block`

- [ ] **Step 3: Update `_build_citation_lines` to accept and write `url`**

In `serve_viz.py`, replace lines 892-907:

```python
def _build_citation_lines(sour_xref: str, page: str, text: str, note: str, base_level: int, url: str = '') -> list[str]:
    """
    Build the citation block lines at base_level.
    base_level=1 → person-level (1 SOUR, 2 PAGE, 2 DATA, 3 TEXT/WWW, 2 NOTE)
    base_level=2 → fact-level   (2 SOUR, 3 PAGE, 3 DATA, 4 TEXT/WWW, 3 NOTE)
    """
    b = base_level
    lines_out = [f'{b} SOUR {sour_xref}']
    if page and page.strip():
        lines_out.append(f'{b+1} PAGE {page.strip()}')
    if (text and text.strip()) or (url and url.strip()):
        lines_out.append(f'{b+1} DATA')
        if text and text.strip():
            lines_out.append(f'{b+2} TEXT {text.strip()}')
        if url and url.strip():
            lines_out.append(f'{b+2} WWW {url.strip()}')
    if note and note.strip():
        lines_out.append(f'{b+1} NOTE {note.strip()}')
    return lines_out
```

- [ ] **Step 4: Update `_update_citation_block` to accept and pass `url`**

In `serve_viz.py`, replace lines 910-922:

```python
def _update_citation_block(
    lines: list[str], block_start: int, block_end: int,
    citation_level: int, page: str, text: str, note: str, url: str = ''
) -> list[str]:
    """
    Replace citation block (block_start..block_end) with updated PAGE/TEXT/NOTE/WWW values.
    Preserves the SOUR xref header line.
    """
    header = lines[block_start]  # '2 SOUR @S1@' or '1 SOUR @S1@'
    b = citation_level
    sour_xref_val = (header.split(' ', 2) + [''])[2].strip()
    new_block = _build_citation_lines(sour_xref_val, page, text, note, b, url)
    return lines[:block_start] + new_block + lines[block_end:]
```

- [ ] **Step 5: Run the test to confirm it passes**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
python -m pytest tests/test_serve_viz_http.py::TestAddCitationEndpoint::test_add_citation_with_url_writes_www_under_data -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 6: Run full Python test suite**

```bash
python -m pytest tests/test_serve_viz_http.py -v 2>&1 | tail -15
```

Expected: all passing (no regressions)

- [ ] **Step 7: Commit**

```bash
git add serve_viz.py tests/test_serve_viz_http.py
git commit -m "Add url/WWW support to _build_citation_lines and _update_citation_block"
```

---

### Task 2: Thread `url` through the HTTP handlers

**Files:**
- Modify: `serve_viz.py` — `/api/add_citation` handler (~line 1427) and `/api/edit_citation` handler (~line 1481)
- Test: `tests/test_serve_viz_http.py` — add edit_citation url test

- [ ] **Step 1: Write the failing edit-citation url test**

Add to `tests/test_serve_viz_http.py` inside `class TestFamCitationEndpoints`:

```python
def test_edit_citation_updates_url(self, live_server):
    ged, post, _, _ = live_server
    sour_xref = self._add_source(post)
    # First add a citation with a URL
    post('/api/add_citation', {
        'xref': '@F5@', 'sour_xref': sour_xref,
        'fact_key': 'MARR:0', 'page': 'p.1', 'text': '', 'note': '',
        'url': 'https://old.example.com',
    })
    # Now edit it to change the URL
    resp = post('/api/edit_citation', {
        'xref': '@F5@', 'citation_key': 'MARR:0:0',
        'page': 'p.1', 'text': '', 'note': '',
        'url': 'https://new.example.com',
    })
    assert resp.get('ok') is True
    text = _ged_text(ged)
    assert '4 WWW https://new.example.com' in text
    assert 'https://old.example.com' not in text
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
python -m pytest tests/test_serve_viz_http.py::TestFamCitationEndpoints::test_edit_citation_updates_url -v 2>&1 | tail -15
```

Expected: FAIL — old URL still present / new URL not written

- [ ] **Step 3: Update `/api/add_citation` handler to read `url`**

In `serve_viz.py`, find the `/api/add_citation` handler. After the existing `note = (body.get('note') or '').strip()` line (~line 1430), add:

```python
url  = (body.get('url')  or '').strip()
```

Then update both calls to `_build_citation_lines` in that handler to pass `url`:

The person-level call (~line 1444):
```python
cite_lines = _build_citation_lines(sour_xref, page, text, note, base_level=1, url=url)
```

The fact-level call (~line 1451):
```python
cite_lines = _build_citation_lines(sour_xref, page, text, note, base_level=2, url=url)
```

- [ ] **Step 4: Update `/api/edit_citation` handler to read `url`**

In `serve_viz.py`, find the `/api/edit_citation` handler. After `note = (body.get('note') or '').strip()` (~line 1483), add:

```python
url  = (body.get('url')  or '').strip()
```

Update the `_update_citation_block` call (~line 1489):

```python
new_lines = _update_citation_block(lines, block_start, block_end, cite_level, page, text, note, url)
```

- [ ] **Step 5: Run the failing test to confirm it now passes**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
python -m pytest tests/test_serve_viz_http.py::TestFamCitationEndpoints::test_edit_citation_updates_url -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 6: Run full Python test suite**

```bash
python -m pytest tests/test_serve_viz_http.py -v 2>&1 | tail -15
```

Expected: all passing

- [ ] **Step 7: Commit**

```bash
git add serve_viz.py tests/test_serve_viz_http.py
git commit -m "Read url from add_citation and edit_citation request bodies"
```

---

### Task 3: Add `url` to JS API wrappers

**Files:**
- Modify: `js/viz_api.js:76-82`
- Test: `tests/js/viz_modals.test.js` (verified via modal tests in Task 4)

- [ ] **Step 1: Update `apiAddCitation` and `apiEditCitation`**

In `js/viz_api.js`, replace lines 76-82:

```javascript
async function apiAddCitation(xref, sourXref, factKey, page, text, note, url) {
  return _post('/api/add_citation', { xref, sour_xref: sourXref, fact_key: factKey, page, text, note, url });
}

async function apiEditCitation(xref, citationKey, page, text, note, url) {
  return _post('/api/edit_citation', { xref, citation_key: citationKey, page, text, note, url });
}
```

- [ ] **Step 2: Run existing JS tests to confirm no regressions**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
npx jest tests/js/viz_modals.test.js --no-coverage 2>&1 | tail -15
```

Expected: all passing (url is optional — existing calls without it still work)

- [ ] **Step 3: Commit**

```bash
git add js/viz_api.js
git commit -m "Add url parameter to apiAddCitation and apiEditCitation"
```

---

### Task 4: Thread `url` through JS modal functions

**Files:**
- Modify: `js/viz_modals.js:914-985` (add citation), `js/viz_modals.js:992-1060` (edit citation)
- Test: `tests/js/viz_modals.test.js`

- [ ] **Step 1: Write failing JS tests for add-citation url field**

In `tests/js/viz_modals.test.js`, find the `describe('showAddCitationModal'` block (~line 684). Add a `urlInp` fake element and two new tests:

In `beforeEach`, add after `noteInp`:
```javascript
urlInp = _fakeModalEl('add-citation-modal-url');
```

Add to `getElementById` mock:
```javascript
if (id === 'add-citation-modal-url')    return urlInp;
```

Add these tests after the existing ones in the `showAddCitationModal` describe block:
```javascript
it('clears the url field on open', () => {
  if (!showAddCitationModal) return;
  urlInp.value = 'https://previous.com';
  showAddCitationModal('@I1@', 'BIRT');
  expect(urlInp.value).toBe('');
});
```

Then find the `describe('showEditCitationModal'` block (~line 739). Add `urlInp` to its setup:

After `noteInp = _fakeModalEl('edit-citation-modal-note');` add:
```javascript
urlInp = _fakeModalEl('edit-citation-modal-url');
```

Update `PEOPLE` fixture to include `url` on the citation:
```javascript
citations: [
  { sourceXref: '@S1@', page: 'p. 42', text: 'Full transcript', note: 'Researcher note', url: 'https://example.com/src' },
],
```

Add to `getElementById` mock:
```javascript
if (id === 'edit-citation-modal-url') return urlInp;
```

Add test:
```javascript
it('pre-fills url field from existing citation', () => {
  if (!showEditCitationModal) return;
  showEditCitationModal('@I1@', 'BIRT', 0);
  expect(urlInp.value).toBe('https://example.com/src');
});
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
npx jest tests/js/viz_modals.test.js --no-coverage -t "url" 2>&1 | tail -15
```

Expected: FAIL — `urlInp.value` remains empty / untouched

- [ ] **Step 3: Update `showAddCitationModal` to reference and clear the url field**

In `js/viz_modals.js`, update `showAddCitationModal` to add `urlEl` alongside the existing elements. After `const noteEl = document.getElementById('add-citation-modal-note');` add:

```javascript
const urlEl      = document.getElementById('add-citation-modal-url');
```

After `if (noteEl)    noteEl.value  = '';` add:

```javascript
if (urlEl)     urlEl.value   = '';
```

- [ ] **Step 4: Update `submitAddCitationModal` to read and pass `url`**

In `js/viz_modals.js`, update `submitAddCitationModal`. After `const noteEl = document.getElementById('add-citation-modal-note');` add:

```javascript
const urlEl      = document.getElementById('add-citation-modal-url');
```

After `const note = noteEl ? noteEl.value.trim() : '';` add:

```javascript
const url        = urlEl    ? urlEl.value.trim()    : '';
```

Update the `apiAddCitation` call (~line 973):

```javascript
const resp = await apiAddCitation(xref, sourceXref, factKey, page, text, note, url);
```

- [ ] **Step 5: Update `showEditCitationModal` to reference and populate the url field**

In `js/viz_modals.js`, in `showEditCitationModal` (~line 992), after `const noteEl = document.getElementById('edit-citation-modal-note');` add:

```javascript
const urlEl      = document.getElementById('edit-citation-modal-url');
```

After `if (noteEl)  noteEl.value  = (cite && cite.note)  || '';` add:

```javascript
if (urlEl)   urlEl.value   = (cite && cite.url)   || '';
```

- [ ] **Step 6: Update `submitEditCitationModal` to read and pass `url`**

In `js/viz_modals.js`, in `submitEditCitationModal` (~line 1043), after `const noteEl = document.getElementById('edit-citation-modal-note');` add:

```javascript
const urlEl   = document.getElementById('edit-citation-modal-url');
```

After `const note = noteEl ? noteEl.value.trim() : '';` add:

```javascript
const url     = urlEl    ? urlEl.value.trim()    : '';
```

Update the `apiEditCitation` call (~line 1055):

```javascript
await apiEditCitation(xref, factTag ? `${factTag}:${index}` : `SOUR:${index}`, page, text, note, url);
```

- [ ] **Step 7: Run JS tests to confirm they pass**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
npx jest tests/js/viz_modals.test.js --no-coverage 2>&1 | tail -15
```

Expected: all passing

- [ ] **Step 8: Commit**

```bash
git add js/viz_modals.js tests/js/viz_modals.test.js
git commit -m "Thread url field through add and edit citation modal JS functions"
```

---

### Task 5: Add URL field to Add Citation modal HTML; add Edit Citation modal HTML

**Files:**
- Modify: `viz_ancestors.py:968-978` (CSS), `viz_ancestors.py:1316-1340` (add-citation HTML)

- [ ] **Step 1: Add URL input to the Add Citation modal HTML**

In `viz_ancestors.py`, find the add-citation modal HTML (~line 1331). Add the url field between the Note field and the action buttons div:

```html
    <div class="event-modal-field">
      <label>Note (optional)</label>
      <textarea id="add-citation-modal-note" rows="2"></textarea>
    </div>
    <div class="event-modal-field">
      <label>URL (optional)</label>
      <input type="url" id="add-citation-modal-url" autocomplete="off" placeholder="https://">
    </div>
    <div class="event-modal-actions">
```

- [ ] **Step 2: Add Edit Citation modal CSS**

In `viz_ancestors.py`, find the `#add-citation-modal-overlay` CSS block (~line 972). Add after it:

```css
#edit-citation-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1100; align-items: center; justify-content: center; }
#edit-citation-modal-overlay.open { display: flex; }
#edit-citation-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 420px; max-width: 90vw; }
#edit-citation-modal h3 { margin: 0 0 12px; font-size: 14px; color: #94a3b8; font-weight: 600; }
```

- [ ] **Step 3: Add Edit Citation modal HTML**

In `viz_ancestors.py`, immediately after the closing `</div>` of the add-citation modal (~line 1340, before `<div id="name-modal-overlay">`), insert:

```html
<div id="edit-citation-modal-overlay" onclick="if(event.target===this)closeEditCitationModal()">
  <div id="edit-citation-modal" onkeydown="if(event.key==='Escape')closeEditCitationModal()">
    <h3 id="edit-citation-modal-title">Edit Citation</h3>
    <div class="event-modal-field">
      <label>Page / reference</label>
      <input type="text" id="edit-citation-modal-page" autocomplete="off">
    </div>
    <div class="event-modal-field">
      <label>Quoted text (optional)</label>
      <textarea id="edit-citation-modal-text" rows="3"></textarea>
    </div>
    <div class="event-modal-field">
      <label>Note (optional)</label>
      <textarea id="edit-citation-modal-note" rows="2"></textarea>
    </div>
    <div class="event-modal-field">
      <label>URL (optional)</label>
      <input type="url" id="edit-citation-modal-url" autocomplete="off" placeholder="https://">
    </div>
    <div class="event-modal-actions">
      <button id="edit-citation-view-source-btn" class="event-modal-cancel" style="display:none">View Source</button>
      <button class="event-modal-cancel" onclick="closeEditCitationModal()">Cancel</button>
      <button class="event-modal-save" onclick="submitEditCitationModal()">Save</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Run full test suite to confirm nothing broken**

```bash
cd /Users/sashaperigo/claude-code/gedcom-tools
python -m pytest tests/ -v 2>&1 | tail -20
npx jest --no-coverage 2>&1 | tail -15
```

Expected: all passing (HTML changes don't affect Python/JS unit tests)

- [ ] **Step 5: Commit**

```bash
git add viz_ancestors.py
git commit -m "Add URL field to add-citation modal; add missing edit-citation modal HTML"
```

---

## Verification (Manual)

1. Start the server: `python serve_viz.py /Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged`
2. Open the visualizer, click any person, click `+ src` on an event.
3. Fill in Source, Page, and URL fields → click **Add**. Confirm success (no alert).
4. Re-open the sources modal for the same event → click the pencil (edit) icon on the new citation.
5. Confirm the Edit Citation modal appears with the URL pre-populated.
6. Change the URL → click **Save**. Confirm the GEDCOM file now contains the updated `4 WWW` line under the correct `SOUR` block.
