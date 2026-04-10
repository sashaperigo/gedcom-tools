"""
validator.py — Post-merge referential integrity validation.

Parses the written GEDCOM file back and checks 9 invariants.
Returns a list of error strings (empty = valid).
"""

from __future__ import annotations
import re


_XREF_RE = re.compile(r'@[^@]+@')


def validate(path: str) -> list[str]:
    """
    Parse path and run referential integrity checks.
    Returns list of error strings; empty list means valid.
    """
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = [l.rstrip('\r\n') for l in f]
    except OSError as e:
        return [f'Cannot open output file: {e}']

    errors: list[str] = []

    # --- Check 1: starts with 0 HEAD, ends with 0 TRLR ---
    first_data = next((l for l in lines if l.strip()), '')
    last_data = next((l for l in reversed(lines) if l.strip()), '')
    if not first_data.startswith('0 HEAD'):
        errors.append(f'File does not start with "0 HEAD" (got: {first_data!r})')
    if not last_data.startswith('0 TRLR'):
        errors.append(f'File does not end with "0 TRLR" (got: {last_data!r})')

    # --- Check 2: GEDC version present ---
    gedc_found = any('GEDC' in l for l in lines[:50])
    vers_found = any('5.5' in l for l in lines[:50])
    if not gedc_found:
        errors.append('No GEDC tag found in header')
    if not vers_found:
        errors.append('No GEDC version (5.5.x) found in header')

    # --- Build sets of defined xrefs and all pointer usages ---
    defined_xrefs: set[str] = set()
    duplicate_xrefs: list[str] = []
    xref_tag: dict[str, str] = {}   # xref → record type

    # pointer usages: tag → [(xref_value, context_xref)]
    used_pointers: dict[str, list[tuple[str, str]]] = {
        'FAMC': [], 'FAMS': [], 'HUSB': [], 'WIFE': [], 'CHIL': [],
        'SOUR': [], 'REPO': [], 'OBJE': [], 'ASSO': [],
    }

    current_xref = ''

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split(' ', 3)
        if not parts[0].isdigit():
            continue
        level = int(parts[0])

        if level == 0 and len(parts) >= 3 and parts[1].startswith('@'):
            xref = parts[1]
            tag = parts[2]
            if xref in defined_xrefs:
                duplicate_xrefs.append(xref)
            defined_xrefs.add(xref)
            xref_tag[xref] = tag
            current_xref = xref
        elif level >= 1 and len(parts) >= 3:
            tag = parts[1]
            val = parts[2] if len(parts) > 2 else ''
            if val.startswith('@') and val.endswith('@') and tag in used_pointers:
                used_pointers[tag].append((val, current_xref))

    # --- Check 3: no duplicate xrefs ---
    for xref in set(duplicate_xrefs):
        errors.append(f'Duplicate xref defined: {xref}')

    # --- Check 4: FAMC/FAMS → existing FAM ---
    fam_xrefs = {x for x, t in xref_tag.items() if t == 'FAM'}
    for ptr_val, ctx in used_pointers.get('FAMC', []):
        if ptr_val not in fam_xrefs:
            errors.append(f'INDI {ctx}: FAMC {ptr_val} not defined')
    for ptr_val, ctx in used_pointers.get('FAMS', []):
        if ptr_val not in fam_xrefs:
            errors.append(f'INDI {ctx}: FAMS {ptr_val} not defined')

    # --- Check 5: HUSB/WIFE/CHIL → existing INDI ---
    indi_xrefs = {x for x, t in xref_tag.items() if t == 'INDI'}
    for ptr_val, ctx in used_pointers.get('HUSB', []):
        if ptr_val not in indi_xrefs:
            errors.append(f'FAM {ctx}: HUSB {ptr_val} not defined')
    for ptr_val, ctx in used_pointers.get('WIFE', []):
        if ptr_val not in indi_xrefs:
            errors.append(f'FAM {ctx}: WIFE {ptr_val} not defined')
    for ptr_val, ctx in used_pointers.get('CHIL', []):
        if ptr_val not in indi_xrefs:
            errors.append(f'FAM {ctx}: CHIL {ptr_val} not defined')

    # --- Check 6: SOUR citations → existing SOUR ---
    sour_xrefs = {x for x, t in xref_tag.items() if t == 'SOUR'}
    for ptr_val, ctx in used_pointers.get('SOUR', []):
        if ptr_val not in sour_xrefs:
            errors.append(f'{ctx}: SOUR {ptr_val} not defined')

    # --- Check 7: REPO → existing REPO ---
    repo_xrefs = {x for x, t in xref_tag.items() if t == 'REPO'}
    for ptr_val, ctx in used_pointers.get('REPO', []):
        if ptr_val not in repo_xrefs:
            errors.append(f'{ctx}: REPO {ptr_val} not defined')

    # --- Check 8: OBJE → existing OBJE ---
    obje_xrefs = {x for x, t in xref_tag.items() if t == 'OBJE'}
    for ptr_val, ctx in used_pointers.get('OBJE', []):
        if ptr_val not in obje_xrefs:
            errors.append(f'{ctx}: OBJE {ptr_val} not defined')

    return errors
