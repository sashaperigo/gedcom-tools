# gedcom_delete.py
"""Pure line-manipulation helpers for deleting an INDI from GEDCOM lines."""


def _find_record_block(lines, xref, record_tag):
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip() == f'0 {xref} {record_tag}'),
        None,
    )
    if start is None:
        return None, None, f'{record_tag} {xref} not found'
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('0 ')), len(lines))
    return start, end, None


def _find_navigate_to_parent(lines, xref):
    """Return xref of the first parent reachable via FAMC, or None."""
    indi_start, indi_end, err = _find_record_block(lines, xref, 'INDI')
    if err:
        return None
    famc_xref = None
    for line in lines[indi_start:indi_end]:
        parts = line.split()
        if len(parts) == 3 and parts[0] == '1' and parts[1] == 'FAMC':
            famc_xref = parts[2]
            break
    if not famc_xref:
        return None
    fam_start, fam_end, err = _find_record_block(lines, famc_xref, 'FAM')
    if err:
        return None
    for line in lines[fam_start:fam_end]:
        parts = line.split()
        if len(parts) == 3 and parts[0] == '1' and parts[1] in ('HUSB', 'WIFE'):
            return parts[2]
    return None


def delete_person_from_lines(lines: list[str], xref: str) -> tuple[list[str], str | None, str | None]:
    """
    Remove an INDI record and all references to it from GEDCOM lines.

    Returns (new_lines, navigate_to_xref_or_None, error_or_None).

    Family cleanup rules:
    - FAM becomes empty (no HUSB, WIFE, or CHIL) → delete FAM and remove any
      remaining FAMS/FAMC references to it in other INDI records.
    - FAM retains at least one member → keep FAM, only remove person's line.
    - ASSO blocks referencing the deleted xref in other INDI records are removed.
    """
    indi_start, indi_end, err = _find_record_block(lines, xref, 'INDI')
    if err:
        return lines, None, err

    navigate_to = _find_navigate_to_parent(lines, xref)

    remove = set(range(indi_start, indi_end))   # indices of lines to drop
    fams_to_delete: set[str] = set()            # FAM xrefs deleted entirely

    # ── Pass 1: scan all FAM records ─────────────────────────────────────────
    i = 0
    while i < len(lines):
        parts = lines[i].split()
        if (
            len(parts) == 3
            and parts[0] == '0'
            and parts[2] == 'FAM'
            and parts[1].startswith('@')
        ):
            fam_xref = parts[1]
            fam_start = i
            fam_end = next(
                (j for j in range(i + 1, len(lines)) if lines[j].startswith('0 ')),
                len(lines),
            )
            fam_lines = lines[fam_start:fam_end]

            person_line_indices = [
                fam_start + j
                for j, ln in enumerate(fam_lines)
                if ln.split() in [['1', 'HUSB', xref], ['1', 'WIFE', xref], ['1', 'CHIL', xref]]
            ]

            if person_line_indices:
                remaining = [
                    ln for ln in fam_lines
                    if ln.split() not in [['1', 'HUSB', xref], ['1', 'WIFE', xref], ['1', 'CHIL', xref]]
                ]
                # Check what members remain
                has_husb = any(ln.split()[:2] == ['1', 'HUSB'] for ln in remaining)
                has_wife = any(ln.split()[:2] == ['1', 'WIFE'] for ln in remaining)
                has_chil = any(ln.split()[:2] == ['1', 'CHIL'] for ln in remaining)

                # Check what members were originally present
                orig_has_husb = any(ln.split()[:2] == ['1', 'HUSB'] for ln in fam_lines)
                orig_has_wife = any(ln.split()[:2] == ['1', 'WIFE'] for ln in fam_lines)

                # FAM is deleted if:
                # 1. No members remain, OR
                # 2. Originally had both spouses but now has neither both nor any children
                no_members = not (has_husb or has_wife or has_chil)
                was_couple = orig_has_husb and orig_has_wife
                is_now_single_no_child = (has_husb or has_wife) and not (has_husb and has_wife) and not has_chil

                if no_members or (was_couple and is_now_single_no_child):
                    fams_to_delete.add(fam_xref)
                    remove.update(range(fam_start, fam_end))
                else:
                    remove.update(person_line_indices)

            i = fam_end
        else:
            i += 1

    # ── Pass 2: remove dangling FAMS/FAMC refs to deleted FAMs ───────────────
    for j, line in enumerate(lines):
        if j in remove:
            continue
        parts = line.split()
        if (
            len(parts) == 3
            and parts[0] == '1'
            and parts[1] in ('FAMS', 'FAMC')
            and parts[2] in fams_to_delete
        ):
            remove.add(j)

    # ── Pass 3: remove ASSO blocks in other INDIs referencing person ──────────
    i = 0
    while i < len(lines):
        if i in remove:
            i += 1
            continue
        parts = lines[i].split()
        if len(parts) == 3 and parts[0] == '1' and parts[1] == 'ASSO' and parts[2] == xref:
            asso_end = i + 1
            while asso_end < len(lines):
                sub = lines[asso_end].split()
                if not sub or sub[0] in ('0', '1'):
                    break
                asso_end += 1
            remove.update(range(i, asso_end))
            i = asso_end
        else:
            i += 1

    new_lines = [ln for j, ln in enumerate(lines) if j not in remove]
    return new_lines, navigate_to, None
