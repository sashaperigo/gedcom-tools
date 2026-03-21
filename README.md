# gedcom-tools

A GEDCOM 5.5.1 linter and test suite for genealogy files.

## Contents

- **`gedcom_linter.py`** — CLI tool to detect and auto-fix common GEDCOM issues
- **`tests/`** — pytest test suite that validates structural integrity, data quality, and demographic plausibility

---

## Linter

### Installation

```bash
pip install -e .
```

Or run directly without installing:

```bash
python gedcom_linter.py [options] yourfile.ged
```

### Usage

```bash
# Check only — report all issues, make no changes
gedcom-lint yourfile.ged

# Fix trailing whitespace
gedcom-lint --fix-whitespace yourfile.ged

# Normalize DATE values to GEDCOM 5.5.1 format
# (e.g. "about 1835" → "ABT 1835", "January 5, 1900" → "5 JAN 1900")
gedcom-lint --fix yourfile.ged

# Normalize PLAC comma spacing
gedcom-lint --fix-plac yourfile.ged

# Collapse double spaces in NAME values
gedcom-lint --fix-names yourfile.ged

# Wrap lines longer than 255 characters using CONC continuations
gedcom-lint --fix-long-lines yourfile.ged

# Remove exact-duplicate SOUR citation blocks
gedcom-lint --fix-duplicate-sources yourfile.ged

# Preview any fix without writing
gedcom-lint --fix --dry-run yourfile.ged

# Run all fixes
gedcom-lint --fix-whitespace --fix --fix-plac --fix-names --fix-long-lines --fix-duplicate-sources yourfile.ged
```

### What the linter fixes

| Flag | What it fixes |
|------|--------------|
| `--fix-whitespace` | Trailing spaces/tabs on any line |
| `--fix` | Non-standard DATE formats (about→ABT, before→BEF, full month names→JAN etc.) |
| `--fix-plac` | Comma spacing in PLAC values (e.g. `City,County` → `City, County`) |
| `--fix-names` | Double spaces in NAME values (e.g. `John  /Smith/` → `John /Smith/`) |
| `--fix-long-lines` | Lines >255 chars, wrapped with CONC continuations |
| `--fix-duplicate-sources` | Identical SOUR citation blocks appearing more than once under the same event |

---

## Test Suite

The test suite checks a GEDCOM file for structural integrity, cross-reference consistency, data quality, and demographic plausibility.

### Setup

```bash
pip install -e ".[test]"
```

### Running tests

Specify your GEDCOM file via the `--gedfile` flag or the `GED_FILE` environment variable:

```bash
# Using the CLI flag
pytest --gedfile yourfile.ged

# Using an environment variable
GED_FILE=yourfile.ged pytest

# Run a specific test file
pytest --gedfile yourfile.ged tests/test_dates.py

# Verbose output
pytest --gedfile yourfile.ged -v
```

### What the tests check

| File | Checks |
|------|--------|
| `test_structure.py` | HEAD/TRLR bookends, line grammar, no level skips |
| `test_xrefs.py` | No duplicate xrefs, all pointers resolve, FAMC/FAMS→FAM, HUSB/WIFE/CHIL→INDI |
| `test_whitespace.py` | No trailing whitespace |
| `test_names.py` | No double spaces in names, no lines >255 chars |
| `test_plac.py` | PLAC comma spacing |
| `test_dates.py` | All DATE values contain a year; all level-2 dates conform to GEDCOM 5.5.1 |
| `test_demographics.py` | No death before birth, plausible parent ages, no ancestor cycles |
| `test_data_quality.py` | Balanced NAME slashes, valid SEX values, no self-referential FAMs, no blank PLAC, marriage date sanity |
| `test_relationships.py` | No future dates, no posthumous births, HUSB/WIFE sex consistency, no orphaned SOURs, no empty FAMs |
| `test_completeness.py` | No duplicate SOURs, every INDI has NAME, bidirectional FAMS/FAMC links |
| `test_ancestry_tags.py` | Ancestry.com proprietary tags stripped (for Ancestry exports only) |

---

## Notes on Ancestry exports

If your GEDCOM was exported from Ancestry.com:

- Photo file paths are stripped on export — `OBJE` records will have blank `FILE` tags
- Ancestry adds proprietary tags (`_APID`, `_CREA`, `_PRIM`, `_CROP`, etc.) that have no meaning in standard GEDCOM
- Repository (`REPO`) records are omitted — you may need to add stub records to satisfy xref checks

The linter's check mode will report these issues; `test_ancestry_tags.py` provides regression tests to ensure they stay cleaned up.
