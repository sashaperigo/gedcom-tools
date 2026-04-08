# gedcom-tools

A collection of Python scripts for cleaning, normalizing, validating, and visualizing GEDCOM 5.5.1 genealogy files — with a focus on Ancestry.com exports.

## Installation

```bash
pip install -e .           # linter CLI only
pip install -e ".[test]"   # include pytest dependencies
```

All scripts can also be run directly without installing:

```bash
python gedcom_linter.py yourfile.ged
```

---

## Scripts

### `normalize_ancestry.py` — Full normalization pipeline

Runs all cleaning steps in sequence on an Ancestry.com GEDCOM export and writes a clean output file.

```bash
python normalize_ancestry.py yourfile.ged                  # → yourfile_normalized.ged
python normalize_ancestry.py yourfile.ged --output clean.ged
python normalize_ancestry.py yourfile.ged --in-place
python normalize_ancestry.py yourfile.ged --dry-run
```

**Pipeline steps (in order):**

1. `strip_ancestry_artifacts` — Remove proprietary tags (`_APID`, `_OID`, `_CREA`, etc.)
2. `convert_physical_attrs` — Convert `_HEIG`/`_WEIG` to standard `DSCR`
3. `add_unaccented_names` — Add AKA entries with accents stripped (ö→oe, etc.)
4. `convert_nonstandard_events` — Convert `_MILT`, `_SEPR`, `_DCAUSE` to standard GEDCOM
5. `convert_wlnk` — Convert `_WLNK` web links to `ASSO`/`NOTE` records
6. `clean_notexml` — Strip `<notexml>` wrappers from NOTE fields
7. `extract_occupations` — Pull "Occupation: X" from notes into `OCCU` events
8. `purge_broken_obje` — Remove `OBJE` references with missing files
9. `purge_duplicate_events` — Merge duplicate `BIRT`/`DEAT` blocks
10. `linter` — Fix dates, whitespace, PLAC spacing, names, long lines, duplicate sources

---

### `gedcom_linter.py` — Linter and fixer

Detect and optionally fix common GEDCOM issues. All fixes can be previewed with `--dry-run`.

```bash
gedcom-lint yourfile.ged                    # check only
gedcom-lint --fix-dates yourfile.ged        # normalize DATE values (about→ABT, January→JAN, etc.)
gedcom-lint --fix-whitespace yourfile.ged   # strip trailing spaces/tabs
gedcom-lint --fix-places yourfile.ged       # normalize PLAC comma spacing
gedcom-lint --fix-names yourfile.ged        # collapse double spaces in NAME values
gedcom-lint --fix-long-lines yourfile.ged   # wrap >255-char lines with CONC
gedcom-lint --fix-duplicate-sources yourfile.ged  # remove exact-duplicate SOUR blocks
gedcom-lint --fix-all yourfile.ged          # run all fixes
gedcom-lint --fix-all --dry-run yourfile.ged
```

**What the linter detects (beyond the fixable items above):**

- Level jumps (e.g. jumping from level 1 to level 3)
- Unbalanced NAME slashes
- Invalid SEX values
- Ancestry proprietary tags still present
- Broken `OBJE` file references
- Structural issues (missing HEAD/TRLR, malformed lines)

---

### `export_minimal.py` — Compact export

Strips citations and optional fields to produce a clean, minimal GEDCOM suitable for sharing or importing into other tools.

```bash
python export_minimal.py yourfile.ged                  # → yourfile_minimal.txt
python export_minimal.py yourfile.ged --output out.txt
python export_minimal.py yourfile.ged --keep-fact-sources   # preserve fact-level SOUR
python export_minimal.py yourfile.ged --strip-sour-bodies   # reduce SOUR records to header+TITL
python export_minimal.py yourfile.ged --dry-run
```

Runs the full normalization pipeline first (minus AKA name expansion), then:
- Removes AKA NAME blocks
- Strips person-level and optionally fact-level source citations
- Drops empty event blocks

---

### `viz_ancestors.py` — Interactive ancestor pedigree chart

Generates a self-contained HTML file with an interactive Ahnentafel pedigree tree. The starting person appears at the bottom; ancestors expand upward by generation with a click.

```bash
python viz_ancestors.py yourfile.ged --person "John Smith"
python viz_ancestors.py yourfile.ged --person "@I123@" --output chart.html
```

Use `serve_viz.py` during development — it watches `viz_ancestors.py` for changes, regenerates the chart, and serves it at `http://localhost:8080/viz.html`.

---

### Individual cleaning scripts

Each of these is also usable standalone:

| Script | What it does |
|--------|-------------|
| `strip_ancestry_artifacts.py` | Remove Ancestry proprietary tags (`_APID`, `_OID`, `_CREA`, `_PRIM`, `_CROP`, etc.) |
| `convert_wlnk.py` | Convert `_WLNK` web link blocks to standard `ASSO`/`NOTE` records |
| `convert_nonstandard_events.py` | Convert `_MILT`, `_SEPR`, `_DCAUSE` to standard GEDCOM event tags |
| `convert_physical_attrs.py` | Convert `_HEIG`/`_WEIG` to standard `DSCR` |
| `clean_notexml.py` | Strip Geneanet `<notexml>` wrappers from NOTE fields |
| `extract_occupations.py` | Parse "Occupation: X" from NOTE fields and create `OCCU` events |
| `add_unaccented_names.py` | Insert AKA NAME entries with accent characters transliterated (ö→oe, etc.) |
| `purge_broken_obje.py` | Remove `OBJE` records whose `FILE` path does not exist on disk |
| `purge_duplicate_events.py` | Remove duplicate `BIRT`/`DEAT` blocks from the same individual |
| `count_trees.py` | Count and report distinct connected family trees in the file |

---

## Test Suite

The test suite validates a GEDCOM file for structural integrity, cross-reference consistency, data quality, and demographic plausibility.

```bash
pytest --gedfile yourfile.ged
GED_FILE=yourfile.ged pytest

pytest --gedfile yourfile.ged tests/test_dates.py  # run a single file
pytest --gedfile yourfile.ged -v
```

| Test file | Checks |
|-----------|--------|
| `test_structure.py` | HEAD/TRLR bookends, line grammar, no level jumps |
| `test_xrefs.py` | No duplicate xrefs, all pointers resolve, FAMC/FAMS→FAM, HUSB/WIFE/CHIL→INDI |
| `test_whitespace.py` | No trailing whitespace |
| `test_names.py` | No double spaces in names, no lines >255 chars |
| `test_plac.py` | PLAC comma spacing |
| `test_dates.py` | All DATE values contain a year; level-2 dates conform to GEDCOM 5.5.1 |
| `test_demographics.py` | No death before birth, plausible parent ages, no ancestor cycles |
| `test_data_quality.py` | Balanced NAME slashes, valid SEX values, no self-referential FAMs, no blank PLAC, marriage date sanity |
| `test_relationships.py` | No future dates, no posthumous births, HUSB/WIFE sex consistency, no orphaned SOURs, no empty FAMs |
| `test_completeness.py` | No duplicate SOURs, every INDI has NAME, bidirectional FAMS/FAMC links |
| `test_ancestry_tags.py` | No Ancestry proprietary tags remain (regression guard for Ancestry exports) |

---

## Notes on Ancestry exports

Ancestry.com GEDCOM exports have several known quirks:

- **Blank `OBJE` file paths** — photo references are stripped on export; `purge_broken_obje.py` cleans these up
- **Proprietary tags** — `_APID`, `_CREA`, `_PRIM`, `_CROP`, `_WLNK`, etc. have no meaning in standard GEDCOM; `strip_ancestry_artifacts.py` removes them
- **Missing `REPO` records** — repository records are omitted; you may need stub records to satisfy xref checks
- **Embedded metadata in notes** — occupation data, web links, and XML wrappers are embedded in NOTE fields rather than proper GEDCOM tags

`normalize_ancestry.py` handles all of the above in one pass.
