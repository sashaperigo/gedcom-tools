"""
writer.py — Write a GedcomFile to a valid GEDCOM 5.5.1 file.

Record order: SUBM, INDI (sorted), FAM (sorted), SOUR, REPO, OBJE, NOTE, TRLR.
Long lines are wrapped with CONC at the 255-character limit.
"""

from __future__ import annotations
import datetime

from gedcom_merge.model import (
    GedcomFile, GedcomNode,
    Individual, Family, Source, Repository, MediaObject, Note,
    NameRecord, EventRecord, CitationRecord, ParsedDate,
)

_MAX_LINE_LEN = 255
_GEDCOM_MONTHS = ['', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                  'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------

def _format_date(d: ParsedDate | None) -> str | None:
    if d is None:
        return None
    parts = []
    if d.qualifier:
        if d.qualifier == 'BET' and d.year2 is not None:
            y1 = str(d.year) if d.year else ''
            y2 = str(d.year2)
            m1 = f'{d.day} {_GEDCOM_MONTHS[d.month]} ' if d.month and d.day else \
                 (f'{_GEDCOM_MONTHS[d.month]} ' if d.month else '')
            return f'BET {m1}{y1} AND {y2}'
        parts.append(d.qualifier)

    if d.day:
        parts.append(str(d.day))
    if d.month:
        parts.append(_GEDCOM_MONTHS[d.month])
    if d.year:
        parts.append(str(d.year))

    return ' '.join(parts) if parts else None


# ---------------------------------------------------------------------------
# Line wrapping with CONC
# ---------------------------------------------------------------------------

def _split_value(level: int, tag: str, value: str) -> list[str]:
    """
    Split a potentially long value into GEDCOM lines.
    First line: '{level} {tag} {value}', continuation lines use CONC.
    Handles embedded newlines with CONT.
    """
    lines: list[str] = []
    # Split on newlines first (CONT)
    text_parts = value.split('\n')

    for part_idx, part in enumerate(text_parts):
        tag_to_use = tag if part_idx == 0 else 'CONT'
        lvl_to_use = level if part_idx == 0 else level + 1

        prefix = f'{lvl_to_use} {tag_to_use} '
        remaining = part

        first = True
        while True:
            max_val_len = _MAX_LINE_LEN - len(prefix)
            if len(remaining) <= max_val_len:
                lines.append(prefix + remaining)
                break
            # Split here
            chunk = remaining[:max_val_len]
            lines.append(prefix + chunk)
            remaining = remaining[max_val_len:]
            # Continuation
            prefix = f'{lvl_to_use + (0 if first else 0)} CONC '
            prefix = f'{lvl_to_use + 1} CONC '
            first = False

    return lines


def _line(level: int, tag: str, value: str = '') -> list[str]:
    if not value:
        return [f'{level} {tag}']
    return _split_value(level, tag, value)


def _xref_line(level: int, xref: str, tag: str) -> str:
    return f'{level} {xref} {tag}'


# ---------------------------------------------------------------------------
# Node tree serialization (preserves raw structure for unmodified records)
# ---------------------------------------------------------------------------

def _serialize_node(node: GedcomNode, override_level: int | None = None) -> list[str]:
    """Serialize a GedcomNode tree back to GEDCOM lines."""
    lines: list[str] = []
    level = override_level if override_level is not None else node.level

    if node.xref:
        prefix = f'{level} {node.xref} {node.tag}'
    else:
        prefix = f'{level} {node.tag}'

    # Handle long lines and embedded newlines
    text_parts = node.value.split('\n') if node.value else ['']
    first_part = text_parts[0]
    rest_parts = text_parts[1:]

    first_line = f'{prefix} {first_part}'.rstrip() if first_part else prefix
    if len(first_line) <= _MAX_LINE_LEN:
        lines.append(first_line)
    else:
        # Wrap with CONC
        p = prefix + ' '
        remaining = first_part
        while remaining:
            max_len = _MAX_LINE_LEN - len(p)
            chunk = remaining[:max_len]
            lines.append(p + chunk)
            remaining = remaining[max_len:]
            p = f'{level + 1} CONC '

    # Emit CONT for additional lines
    for part in rest_parts:
        cont_prefix = f'{level + 1} CONT '
        remaining = part
        while True:
            max_len = _MAX_LINE_LEN - len(cont_prefix)
            if len(remaining) <= max_len:
                line_val = cont_prefix + remaining
                lines.append(line_val.rstrip())  # strip trailing whitespace on empty CONT lines
                break
            chunk = remaining[:max_len]
            lines.append(cont_prefix + chunk)
            remaining = remaining[max_len:]
            cont_prefix = f'{level + 2} CONC '

    # Recurse into children
    for child in node.children:
        lines.extend(_serialize_node(child))

    return lines


# ---------------------------------------------------------------------------
# Typed record serializers
# ---------------------------------------------------------------------------

def _serialize_citation(cit: CitationRecord, level: int) -> list[str]:
    lines = [f'{level} SOUR {cit.source_xref}']
    if cit.page:
        lines.extend(_line(level + 1, 'PAGE', cit.page))
    if cit.data:
        lines.append(f'{level + 1} DATA')
        for tag, val in cit.data.items():
            if val:
                lines.extend(_line(level + 2, tag, val))
    return lines


def _serialize_event(ev: EventRecord, level: int) -> list[str]:
    """Serialize an event, using typed fields where we have them (more specific),
    then falling back to the raw node's unknown children."""
    lines: list[str] = []

    # Event header
    if ev.event_type and not ev.raw.value:
        lines.append(f'{level} {ev.tag}')
    elif ev.raw.value:
        lines.extend(_line(level, ev.tag, ev.raw.value))
    else:
        lines.append(f'{level} {ev.tag}')

    # TYPE (emit before DATE/PLAC)
    if ev.event_type:
        lines.extend(_line(level + 1, 'TYPE', ev.event_type))

    # Date (use merged date if available, else raw)
    date_str = _format_date(ev.date)
    if date_str:
        lines.extend(_line(level + 1, 'DATE', date_str))

    # Place
    if ev.place:
        lines.extend(_line(level + 1, 'PLAC', ev.place))

    # Citations
    for cit in ev.citations:
        lines.extend(_serialize_citation(cit, level + 1))

    # Preserve any other raw children (non-DATE/PLAC/SOUR/TYPE)
    handled = {'DATE', 'PLAC', 'SOUR', 'TYPE'}
    for child in ev.raw.children:
        if child.tag not in handled:
            lines.extend(_serialize_node(child))

    return lines


def _serialize_name(name: NameRecord, level: int) -> list[str]:
    lines: list[str] = []
    lines.extend(_line(level, 'NAME', name.full))
    if name.name_type:
        lines.extend(_line(level + 1, 'TYPE', name.name_type))
    # Preserve GIVN, SURN, NICK, NSFX and any other raw sub-tags not handled above.
    _handled_name_tags = {'TYPE', 'SOUR'}
    for child in name.raw.children:
        if child.tag not in _handled_name_tags:
            lines.extend(_serialize_node(child))
    for cit in name.citations:
        lines.extend(_serialize_citation(cit, level + 1))
    return lines


def _serialize_individual(ind: Individual) -> list[str]:
    lines: list[str] = [f'0 {ind.xref} INDI']

    for name in ind.names:
        lines.extend(_serialize_name(name, 1))

    if ind.sex:
        lines.append(f'1 SEX {ind.sex}')

    for ev in ind.events:
        lines.extend(_serialize_event(ev, 1))

    for xref in ind.family_child:
        lines.append(f'1 FAMC {xref}')

    for xref in ind.family_spouse:
        lines.append(f'1 FAMS {xref}')

    for cit in ind.citations:
        lines.extend(_serialize_citation(cit, 1))

    for xref in ind.media:
        lines.append(f'1 OBJE {xref}')

    for note_text in ind.notes:
        lines.extend(_line(1, 'NOTE', note_text))

    for xref in ind.note_xrefs:
        lines.append(f'1 NOTE {xref}')

    # Preserve non-standard tags from raw (NOTE now handled explicitly above)
    handled_tags = {'NAME', 'SEX', 'BIRT', 'DEAT', 'BURI', 'MARR', 'DIV',
                    'RESI', 'NATU', 'EMIG', 'IMMI', 'CENS', 'PROB', 'WILL',
                    'GRAD', 'RETI', 'BAPM', 'CHR', 'EVEN', 'FAMC', 'FAMS',
                    'SOUR', 'OBJE', 'NOTE', '_MILT', '_SEPR', '_DCAUSE'}
    for child in ind.raw.children:
        if child.tag not in handled_tags:
            lines.extend(_serialize_node(child))

    return lines


def _serialize_family(fam: Family) -> list[str]:
    lines: list[str] = [f'0 {fam.xref} FAM']

    if fam.husband_xref:
        lines.append(f'1 HUSB {fam.husband_xref}')
    if fam.wife_xref:
        lines.append(f'1 WIFE {fam.wife_xref}')
    for xref in fam.child_xrefs:
        lines.append(f'1 CHIL {xref}')

    for ev in fam.events:
        lines.extend(_serialize_event(ev, 1))

    for cit in fam.citations:
        lines.extend(_serialize_citation(cit, 1))

    # Preserve non-standard tags from raw
    handled_tags = {'HUSB', 'WIFE', 'CHIL', 'MARR', 'DIV', 'EVEN', 'SOUR',
                    'BIRT', 'DEAT', 'RESI', 'NATU', 'EMIG', 'IMMI', 'CENS'}
    for child in fam.raw.children:
        if child.tag not in handled_tags:
            lines.extend(_serialize_node(child))

    return lines


def _serialize_source(src: Source) -> list[str]:
    lines: list[str] = [f'0 {src.xref} SOUR']

    if src.title:
        lines.extend(_line(1, 'TITL', src.title))
    if src.author:
        lines.extend(_line(1, 'AUTH', src.author))
    if src.publisher:
        lines.extend(_line(1, 'PUBL', src.publisher))
    if src.repository_xref:
        lines.append(f'1 REPO {src.repository_xref}')
    if src.refn:
        lines.extend(_line(1, 'REFN', src.refn))
    for note in src.notes:
        lines.extend(_line(1, 'NOTE', note))

    # Preserve other raw children
    handled_tags = {'TITL', 'AUTH', 'PUBL', 'REPO', 'REFN', 'NOTE'}
    for child in src.raw.children:
        if child.tag not in handled_tags:
            lines.extend(_serialize_node(child))

    return lines


def _serialize_repository(repo: Repository) -> list[str]:
    lines: list[str] = [f'0 {repo.xref} REPO']
    # Use raw node for full content
    for child in repo.raw.children:
        lines.extend(_serialize_node(child))
    return lines


def _serialize_media(obj: MediaObject) -> list[str]:
    lines: list[str] = [f'0 {obj.xref} OBJE']
    for child in obj.raw.children:
        lines.extend(_serialize_node(child))
    return lines


def _serialize_note(note: Note) -> list[str]:
    lines: list[str] = []
    note_lines = _line(0, 'NOTE', note.text)
    # First line needs the xref
    if note_lines:
        first = note_lines[0]
        # Replace "0 NOTE " with "0 {xref} NOTE "
        first = f'0 {note.xref} NOTE' + (first[6:] if first.startswith('0 NOTE') else '')
        lines.append(first)
        lines.extend(note_lines[1:])
    return lines


# ---------------------------------------------------------------------------
# Header generation
# ---------------------------------------------------------------------------

def _make_header(
    file_a_path: str = '',
    file_b_path: str = '',
) -> list[str]:
    today = datetime.date.today()
    date_str = today.strftime('%d %b %Y').upper()
    lines = [
        '0 HEAD',
        '1 SOUR gedcom-merge',
        '2 VERS 1.0',
        '2 NAME gedcom-merge',
        f'1 DATE {date_str}',
        '1 GEDC',
        '2 VERS 5.5.1',
        '2 FORM LINEAGE-LINKED',
        '1 CHAR UTF-8',
        '1 PLAC',
        '2 FORM City, County, State, Country',
    ]
    if file_a_path or file_b_path:
        note = f'Merged from: {file_a_path} and {file_b_path}'
        lines.extend(_line(1, 'NOTE', note))
    return lines


# ---------------------------------------------------------------------------
# Main write function
# ---------------------------------------------------------------------------

def write_gedcom(
    merged: GedcomFile,
    path: str,
    file_a_path: str = '',
    file_b_path: str = '',
) -> None:
    """Write a GedcomFile to a GEDCOM 5.5.1 file at path."""
    lines: list[str] = []

    # Header
    lines.extend(_make_header(file_a_path, file_b_path))

    # SUBM
    if merged.submitter:
        lines.extend(_serialize_node(merged.submitter))

    # INDI (sorted by xref)
    for xref in sorted(merged.individuals):
        lines.extend(_serialize_individual(merged.individuals[xref]))

    # FAM (sorted by xref)
    for xref in sorted(merged.families):
        lines.extend(_serialize_family(merged.families[xref]))

    # SOUR (sorted)
    for xref in sorted(merged.sources):
        lines.extend(_serialize_source(merged.sources[xref]))

    # REPO (sorted)
    for xref in sorted(merged.repositories):
        lines.extend(_serialize_repository(merged.repositories[xref]))

    # OBJE (sorted)
    for xref in sorted(merged.media):
        lines.extend(_serialize_media(merged.media[xref]))

    # NOTE (sorted)
    for xref in sorted(merged.notes):
        lines.extend(_serialize_note(merged.notes[xref]))

    # Trailer
    lines.append('0 TRLR')

    # Write atomically
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        for line in lines:
            f.write(line + '\n')
    import os
    os.replace(tmp, path)
