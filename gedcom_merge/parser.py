"""
parser.py — Single-pass streaming GEDCOM parser.

Reads a GEDCOM file once, building typed dataclasses. CONT/CONC lines are
reassembled. Non-standard tags are preserved in the raw GedcomNode tree so
nothing is silently lost.

Usage:
    from gedcom_merge.parser import parse_gedcom
    ged = parse_gedcom("file.ged")
"""

from __future__ import annotations
import re

from gedcom_merge.model import (
    GedcomFile, GedcomNode,
    Individual, Family, Source, Repository, MediaObject, Note,
    NameRecord, EventRecord, CitationRecord, ParsedDate,
)
from gedcom_merge.normalize import (
    normalize_name_str, normalize_surname, extract_parenthetical_surnames, strip_parentheticals,
    tokenize_title, parse_date,
)

# ---------------------------------------------------------------------------
# Line parsing helpers
# ---------------------------------------------------------------------------

_RECORD_DEF_RE = re.compile(r'^0 (@[^@]+@) ([A-Z_][A-Z0-9_]*)(?:\s+(.*))?$')
_REGULAR_LINE_RE = re.compile(r'^(\d+) ([A-Z_][A-Z0-9_]*)(?:\s+(.*))?$')
_XREF_VALUE_RE = re.compile(r'^@[^@]+@$')


def _detect_encoding(path: str) -> str:
    """
    Detect GEDCOM character encoding from the first ~20 lines.
    Falls back to utf-8 (with replacement) if not found.
    """
    encodings_to_try = [
        ('utf-8-sig', 'utf-8-sig'),   # BOM UTF-8
        ('utf-8', 'utf-8'),
        ('cp1252', 'cp1252'),
        ('latin-1', 'latin-1'),
    ]
    for enc, _ in encodings_to_try:
        try:
            with open(path, encoding=enc, errors='strict') as f:
                lines = [f.readline() for _ in range(30)]
            for line in lines:
                line = line.strip()
                if line == '1 CHAR UTF-8' or line == '1 CHAR UTF8':
                    return 'utf-8'
                if line == '1 CHAR ANSI' or line == '1 CHAR CP1252':
                    return 'cp1252'
                if line == '1 CHAR ANSEL':
                    return 'latin-1'
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return 'utf-8'


def _read_lines(path: str) -> list[str]:
    """Read all lines, detecting encoding, stripping trailing newlines."""
    enc = _detect_encoding(path)
    with open(path, encoding=enc, errors='replace') as f:
        return [line.rstrip('\r\n') for line in f]


# ---------------------------------------------------------------------------
# Node tree builder
# ---------------------------------------------------------------------------

def _build_records(lines: list[str]) -> list[GedcomNode]:
    """
    Convert a flat list of GEDCOM lines into a list of top-level GedcomNode
    trees. CONT and CONC sub-lines are folded into their parent's value.

    Returns one GedcomNode per level-0 record.
    """
    # Stack-based approach: stack holds (node, level) for open ancestors
    roots: list[GedcomNode] = []
    stack: list[GedcomNode] = []  # ancestors from root → current

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Try to parse level and tag
        m_record = _RECORD_DEF_RE.match(line)
        m_regular = _REGULAR_LINE_RE.match(line)

        if m_record:
            lvl = 0
            xref = m_record.group(1)
            tag = m_record.group(2)
            value = (m_record.group(3) or '').strip()
            node = GedcomNode(level=0, tag=tag, value=value, xref=xref)
        elif m_regular:
            lvl = int(m_regular.group(1))
            tag = m_regular.group(2)
            if tag in ('CONT', 'CONC'):
                # Preserve leading spaces: value is everything after "LEVEL TAG "
                # (one mandatory separator space; anything beyond that is part of value)
                parts_raw = line.split(' ', 2)
                value = parts_raw[2] if len(parts_raw) > 2 else ''
            else:
                value = (m_regular.group(3) or '').strip()
            node = GedcomNode(level=lvl, tag=tag, value=value, xref=None)
        else:
            # Level-0 without xref (e.g., "0 HEAD", "0 TRLR")
            parts = line.split(' ', 2)
            if parts[0].isdigit():
                lvl = int(parts[0])
                tag = parts[1] if len(parts) > 1 else ''
                value = parts[2] if len(parts) > 2 else ''
                node = GedcomNode(level=lvl, tag=tag, value=value, xref=None)
            else:
                continue  # Unparseable line; skip

        # Handle CONT / CONC: fold into parent's value
        if tag in ('CONT', 'CONC') and stack:
            parent = stack[-1]
            if tag == 'CONT':
                parent.value = parent.value + '\n' + value
            else:  # CONC
                parent.value = parent.value + value
            continue

        # Pop stack to find the right parent level
        # The parent of a level-N node is the most recent ancestor at level < N
        while stack and stack[-1].level >= lvl:
            stack.pop()

        if lvl == 0:
            roots.append(node)
            stack = [node]
        else:
            if stack:
                stack[-1].children.append(node)
            else:
                # Orphaned non-zero level; attach to last root if any
                if roots:
                    roots[-1].children.append(node)
            stack.append(node)

    return roots


# ---------------------------------------------------------------------------
# Record type parsers
# ---------------------------------------------------------------------------

def _parse_citation(node: GedcomNode) -> CitationRecord:
    """Parse a SOUR citation node (level N)."""
    page = node.child_value('PAGE')
    data_node = next((c for c in node.children if c.tag == 'DATA'), None)
    data = None
    if data_node:
        data = {c.tag: c.value for c in data_node.children}
    return CitationRecord(
        source_xref=node.value,
        page=page,
        data=data,
        raw=node,
    )


def _parse_citations(node: GedcomNode) -> list[CitationRecord]:
    return [_parse_citation(c) for c in node.all_children('SOUR')
            if _XREF_VALUE_RE.match(c.value)]


def _parse_event(node: GedcomNode) -> EventRecord:
    """Parse an event node (BIRT, DEAT, MARR, RESI, EVEN, etc.)."""
    event_type = node.child_value('TYPE')
    date_str = node.child_value('DATE')
    place = node.child_value('PLAC')
    citations = _parse_citations(node)
    return EventRecord(
        tag=node.tag,
        event_type=event_type,
        date=parse_date(date_str),
        place=place,
        citations=citations,
        raw=node,
    )


_EVENT_TAGS = frozenset({
    'BIRT', 'DEAT', 'BURI', 'MARR', 'DIV', 'RESI', 'NATU', 'EMIG', 'IMMI',
    'CENS', 'PROB', 'WILL', 'GRAD', 'RETI', 'BAPM', 'CHR', 'EVEN',
    # Common non-standard event tags (preserved but matched generically)
    '_MILT', '_SEPR', '_DCAUSE',
})


def _collect_text(node: GedcomNode) -> str:
    """Collect a potentially multi-line text value (already CONT-reassembled)."""
    return node.value


def _parse_individual(node: GedcomNode) -> Individual:
    """Build an Individual from a level-0 INDI GedcomNode."""
    names: list[NameRecord] = []
    events: list[EventRecord] = []
    family_child: list[str] = []
    family_spouse: list[str] = []
    citations: list[CitationRecord] = []
    media: list[str] = []
    notes: list[str] = []
    note_xrefs: list[str] = []
    sex: str | None = None

    for child in node.children:
        tag = child.tag
        val = child.value

        if tag == 'NAME':
            given, surname = normalize_name_str(val)
            name_type = child.child_value('TYPE')
            name_citations = _parse_citations(child)
            names.append(NameRecord(
                full=val,
                given=given,
                surname=surname,
                name_type=name_type,
                citations=name_citations,
                raw=child,
            ))
        elif tag == 'SEX':
            sex = val.upper() if val else None
        elif tag in _EVENT_TAGS:
            events.append(_parse_event(child))
        elif tag == 'FAMC':
            if val and _XREF_VALUE_RE.match(val):
                family_child.append(val)
        elif tag == 'FAMS':
            if val and _XREF_VALUE_RE.match(val):
                family_spouse.append(val)
        elif tag == 'SOUR':
            if val and _XREF_VALUE_RE.match(val):
                citations.append(_parse_citation(child))
        elif tag == 'OBJE':
            if val and _XREF_VALUE_RE.match(val):
                media.append(val)
        elif tag == 'NOTE':
            if val and _XREF_VALUE_RE.match(val):
                note_xrefs.append(val)
            else:
                # Inline note — CONT lines already folded into node.value by _build_records
                note_text = _collect_text(child)
                if note_text:
                    notes.append(note_text)

    # Pre-compute normalized fields
    normalized_surnames: set[str] = set()
    normalized_givens: set[str] = set()
    for name in names:
        if name.surname:
            # Add the primary surname with parentheticals stripped
            clean_surname = strip_parentheticals(name.surname)
            if clean_surname:
                normalized_surnames.add(normalize_surname(clean_surname))
        # Extract any parenthetical alternate surnames from the full raw name
        # e.g. "/Bonnici/ (Bonnar)" or "/Bonnici (Bonnar)/"
        for alt in extract_parenthetical_surnames(name.full):
            if alt:
                normalized_surnames.add(alt)
        if name.given:
            # Strip parenthetical alternate-name tokens before tokenizing given names
            clean_given = strip_parentheticals(name.given)
            for part in clean_given.split():
                normalized_givens.add(part)

    birth_date: ParsedDate | None = None
    death_date: ParsedDate | None = None
    for ev in events:
        if ev.tag == 'BIRT' and birth_date is None:
            birth_date = ev.date
        elif ev.tag == 'DEAT' and death_date is None:
            death_date = ev.date

    return Individual(
        xref=node.xref or '',
        names=names,
        sex=sex,
        events=events,
        family_child=family_child,
        family_spouse=family_spouse,
        citations=citations,
        media=media,
        notes=notes,
        note_xrefs=note_xrefs,
        raw=node,
        normalized_surnames=normalized_surnames,
        normalized_givens=normalized_givens,
        birth_date=birth_date,
        death_date=death_date,
    )


def _parse_family(node: GedcomNode) -> Family:
    husband_xref: str | None = None
    wife_xref: str | None = None
    child_xrefs: list[str] = []
    events: list[EventRecord] = []
    citations: list[CitationRecord] = []

    for child in node.children:
        tag = child.tag
        val = child.value
        if tag == 'HUSB' and val and _XREF_VALUE_RE.match(val):
            husband_xref = val
        elif tag == 'WIFE' and val and _XREF_VALUE_RE.match(val):
            wife_xref = val
        elif tag == 'CHIL' and val and _XREF_VALUE_RE.match(val):
            child_xrefs.append(val)
        elif tag in _EVENT_TAGS:
            events.append(_parse_event(child))
        elif tag == 'SOUR' and val and _XREF_VALUE_RE.match(val):
            citations.append(_parse_citation(child))

    return Family(
        xref=node.xref or '',
        husband_xref=husband_xref,
        wife_xref=wife_xref,
        child_xrefs=child_xrefs,
        events=events,
        citations=citations,
        raw=node,
    )


def _parse_source(node: GedcomNode) -> Source:
    title = node.child_value('TITL') or ''
    author = node.child_value('AUTH')
    publisher = node.child_value('PUBL')
    repository_xref = None
    repo_node = next((c for c in node.children if c.tag == 'REPO'), None)
    if repo_node and repo_node.value and _XREF_VALUE_RE.match(repo_node.value):
        repository_xref = repo_node.value
    notes = [_collect_text(c) for c in node.all_children('NOTE')]
    refn = node.child_value('REFN')
    title_tokens = tokenize_title(title)

    return Source(
        xref=node.xref or '',
        title=title,
        author=author,
        publisher=publisher,
        repository_xref=repository_xref,
        notes=notes,
        refn=refn,
        raw=node,
        title_tokens=title_tokens,
    )


def _parse_repository(node: GedcomNode) -> Repository:
    name = node.child_value('NAME')
    return Repository(xref=node.xref or '', name=name, raw=node)


def _parse_media(node: GedcomNode) -> MediaObject:
    file_val = node.child_value('FILE')
    form = node.child_value('FORM')
    title = node.child_value('TITL')
    return MediaObject(xref=node.xref or '', file=file_val, form=form, title=title, raw=node)


def _parse_note(node: GedcomNode) -> Note:
    text = _collect_text(node)
    return Note(xref=node.xref or '', text=text, raw=node)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_gedcom(path: str) -> GedcomFile:
    """
    Parse a GEDCOM 5.5.1 file into a GedcomFile.

    All records are preserved — unknown tags stay in the raw GedcomNode trees.
    """
    lines = _read_lines(path)
    roots = _build_records(lines)

    individuals: dict[str, Individual] = {}
    families: dict[str, Family] = {}
    sources: dict[str, Source] = {}
    repositories: dict[str, Repository] = {}
    media: dict[str, MediaObject] = {}
    notes: dict[str, Note] = {}
    submitter: GedcomNode | None = None
    header_raw: GedcomNode | None = None

    for node in roots:
        tag = node.tag
        xref = node.xref

        if tag == 'HEAD':
            header_raw = node
        elif tag == 'TRLR':
            pass
        elif tag == 'INDI' and xref:
            ind = _parse_individual(node)
            individuals[xref] = ind
        elif tag == 'FAM' and xref:
            fam = _parse_family(node)
            families[xref] = fam
        elif tag == 'SOUR' and xref:
            src = _parse_source(node)
            sources[xref] = src
        elif tag == 'REPO' and xref:
            repo = _parse_repository(node)
            repositories[xref] = repo
        elif tag == 'OBJE' and xref:
            obj = _parse_media(node)
            media[xref] = obj
        elif tag == 'NOTE' and xref:
            note = _parse_note(node)
            notes[xref] = note
        elif tag == 'SUBM':
            submitter = node

    return GedcomFile(
        individuals=individuals,
        families=families,
        sources=sources,
        repositories=repositories,
        media=media,
        notes=notes,
        submitter=submitter,
        header_raw=header_raw,
        path=path,
    )
