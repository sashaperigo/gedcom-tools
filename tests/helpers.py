"""Shared test builder helpers for gedcom_merge tests.

Import these directly in test files:
    from tests.helpers import make_indi, make_family, make_file, make_source, make_citation, _node
"""
from gedcom_merge.model import (
    GedcomFile, Individual, Family, Source, GedcomNode,
    NameRecord, EventRecord, CitationRecord, ParsedDate,
)
from gedcom_merge.normalize import tokenize_title


def _node(tag: str = 'INDI', xref: str | None = None) -> GedcomNode:
    return GedcomNode(0, tag, '', xref, [])


def make_indi(
    xref: str,
    given: str = 'John',
    surname: str = 'Smith',
    sex: str = 'M',
    birth_year: int | None = None,
    death_year: int | None = None,
    birth_place: str | None = None,
    death_place: str | None = None,
    fams: list[str] | None = None,
    famc: list[str] | None = None,
    citations: list[CitationRecord] | None = None,
) -> Individual:
    names = [NameRecord(
        full=f'{given} /{surname}/',
        given=given.lower(),
        surname=surname.lower(),
        name_type=None,
    )]
    events = []
    if birth_year:
        events.append(EventRecord(
            tag='BIRT', event_type=None,
            date=ParsedDate(None, birth_year),
            place=birth_place,
            citations=[], raw=_node('BIRT'),
        ))
    if death_year:
        events.append(EventRecord(
            tag='DEAT', event_type=None,
            date=ParsedDate(None, death_year),
            place=death_place,
            citations=[], raw=_node('DEAT'),
        ))
    return Individual(
        xref=xref,
        names=names,
        sex=sex,
        events=events,
        family_child=famc or [],
        family_spouse=fams or [],
        citations=citations or [],
        media=[],
        raw=_node(xref=xref),
        normalized_surnames={surname.lower()},
        normalized_givens={g.lower() for g in given.split()},
        birth_date=ParsedDate(None, birth_year) if birth_year else None,
        death_date=ParsedDate(None, death_year) if death_year else None,
    )


def make_family(
    xref: str,
    husb: str | None = None,
    wife: str | None = None,
    children: list[str] | None = None,
) -> Family:
    return Family(
        xref=xref,
        husband_xref=husb,
        wife_xref=wife,
        child_xrefs=children or [],
        events=[],
        citations=[],
        raw=_node('FAM', xref),
    )


def make_file(
    indis: dict | None = None,
    fams: dict | None = None,
    sources: dict | None = None,
) -> GedcomFile:
    return GedcomFile(
        individuals=indis or {},
        families=fams or {},
        sources=sources or {},
        repositories={},
        media={},
        notes={},
        submitter=None,
        header_raw=None,
    )


def make_source(
    xref: str,
    title: str = 'Test Source',
    author: str | None = None,
) -> Source:
    return Source(
        xref=xref,
        title=title,
        author=author,
        publisher=None,
        repository_xref=None,
        notes=[],
        refn=None,
        raw=_node('SOUR', xref),
        title_tokens=tokenize_title(title),
    )


def make_citation(
    source_xref: str,
    page: str | None = None,
) -> CitationRecord:
    return CitationRecord(
        source_xref=source_xref,
        page=page,
        data=None,
        raw=_node('SOUR'),
    )
