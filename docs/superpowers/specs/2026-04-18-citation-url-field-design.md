# Citation URL Field Design

## Goal

Add a URL field to the Add Citation and Edit Citation modals. The value is written to `DATA/WWW` in the GEDCOM citation block, making it a sibling of `TEXT` under the `DATA` subrecord.

## GEDCOM Structure

```
2 SOUR @S1@
3 PAGE p.42
3 DATA
4 TEXT verbatim quoted text
4 WWW https://example.com/record
3 NOTE optional note
```

`WWW` lives under `DATA`, alongside `TEXT`. Both are optional.

## Components Changed

### `viz_ancestors.py` — HTML template

- Add `URL (optional)` `<input type="url">` field to the Add Citation modal, between Note and the action buttons.
- Add the Edit Citation modal HTML entirely. The JS (`showEditCitationModal`, `submitEditCitationModal`) already references these DOM IDs but the HTML does not exist:
  - `edit-citation-modal-overlay`
  - `edit-citation-modal-title`
  - `edit-citation-modal-page`
  - `edit-citation-modal-text`
  - `edit-citation-modal-note`
  - `edit-citation-modal-url` ← new
  - `edit-citation-view-source-btn`

### `viz_ancestors.py` — CSS

- Add `#edit-citation-modal-overlay` and `#edit-citation-modal` styles, matching the add-citation modal styles exactly.

### `js/viz_modals.js`

- `showAddCitationModal()`: reference `add-citation-modal-url` element; clear it on open; populate from `cite.url` if pre-filling.
- `submitAddCitationModal()`: read `urlEl.value.trim()`; pass as `url` arg to `apiAddCitation`.
- `showEditCitationModal()`: reference `edit-citation-modal-url`; populate from `cite.url || ''`.
- `submitEditCitationModal()`: read url value; pass as `url` arg to `apiEditCitation`.

### `js/viz_api.js`

- `apiAddCitation(xref, sourXref, factKey, page, text, note, url)` — add `url` to POST body.
- `apiEditCitation(xref, citationKey, page, text, note, url)` — add `url` to POST body.

### `serve_viz.py`

- `/api/add_citation` handler: read `url = (body.get('url') or '').strip()` from body; pass to `_build_citation_lines`.
- `/api/edit_citation` handler: read `url` from body; pass to `_update_citation_block`.
- `_build_citation_lines(sour_xref, page, text, note, base_level, url='')`: when `url` is provided, emit `{b+2} WWW {url}` under the `DATA` block (alongside `TEXT`). If only `url` is provided (no `text`), still emit the `DATA` wrapper.
- `_update_citation_block(..., url='')`: add `url` parameter; pass through to `_build_citation_lines`.

### `viz_ancestors.py` — parsing

No changes needed. `WWW` under fact-level citations is already parsed at lines 183-185 (INDI) and 255-257 (FAM) and stored as `citation['url']`. The normalization in `build_people_json` already spreads all citation fields into the JSON response, so `url` reaches the frontend.

## Data Flow

```
User fills URL field
  → submitAddCitationModal() reads urlEl.value
  → apiAddCitation(..., url) POSTs url to /api/add_citation
  → _build_citation_lines writes "4 WWW https://..."
  → parse_gedcom reads it back as citation['url']
  → build_people_json spreads it as cite.url in JSON
  → showEditCitationModal() populates urlEl.value from cite.url
```

## Testing

- Unit: `_build_citation_lines` with url only, text only, both, neither
- Unit: `_update_citation_block` preserves url round-trip
- HTTP integration: POST to `/api/add_citation` with url; assert `4 WWW` appears in GEDCOM under the correct SOUR block
- HTTP integration: POST to `/api/edit_citation` with updated url; assert GEDCOM updated correctly
- JS unit: `submitAddCitationModal` passes url to apiAddCitation
- JS unit: `showEditCitationModal` populates url field from cite data
- Manual: open Add Citation modal → fill URL → Add → open Edit Citation → URL pre-populated
