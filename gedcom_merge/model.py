"""
model.py — Typed dataclasses for the GEDCOM merge tool.

All records from both files are parsed into these structures before matching.
The `raw` field on each record preserves the full original GedcomNode tree so
no data is ever silently discarded.
"""

from __future__ import annotations
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Low-level tree node
# ---------------------------------------------------------------------------

@dataclass
class GedcomNode:
    """One logical GEDCOM record line (CONT/CONC already reassembled)."""
    level: int
    tag: str
    value: str                  # may be empty string
    xref: str | None            # @ID@ if this is a top-level record definition
    children: list[GedcomNode] = field(default_factory=list)

    def child_value(self, tag: str) -> str | None:
        """Return the first child value for the given tag, or None."""
        for c in self.children:
            if c.tag == tag:
                return c.value or None
        return None

    def all_children(self, tag: str) -> list[GedcomNode]:
        """Return all direct children with the given tag."""
        return [c for c in self.children if c.tag == tag]


# ---------------------------------------------------------------------------
# Date representation
# ---------------------------------------------------------------------------

@dataclass
class ParsedDate:
    """
    Structured GEDCOM date.

    qualifier: None | 'ABT' | 'BEF' | 'AFT' | 'BET'
    year, year2: 4-digit int or None  (year2 used for BET...AND ranges)
    month: 1-12 or None
    day: 1-31 or None
    """
    qualifier: str | None       # None = exact, 'ABT', 'BEF', 'AFT', 'BET'
    year: int | None
    month: int | None = None
    day: int | None = None
    year2: int | None = None    # end of BET...AND range

    def specificity(self) -> int:
        """Higher = more specific. Used when choosing between two dates."""
        score = 0
        if self.qualifier is None:
            score += 8          # exact qualifier
        elif self.qualifier == 'ABT':
            score += 2
        elif self.qualifier in ('BEF', 'AFT'):
            score += 1
        # BET has score 0 as it's a range
        if self.year is not None:
            score += 1
        if self.month is not None:
            score += 2
        if self.day is not None:
            score += 4
        return score


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------

@dataclass
class CitationRecord:
    source_xref: str            # @S...@
    page: str | None            # PAGE value
    data: dict | None           # DATA sub-records as {tag: value}
    raw: GedcomNode


# ---------------------------------------------------------------------------
# Name
# ---------------------------------------------------------------------------

@dataclass
class NameRecord:
    full: str                   # e.g. "Saverio Salvatore /Bonnici/"
    given: str                  # e.g. "Saverio Salvatore"
    surname: str                # e.g. "Bonnici"
    name_type: str | None       # "AKA", "married", etc.
    citations: list[CitationRecord] = field(default_factory=list)
    raw: 'GedcomNode' = field(default_factory=lambda: GedcomNode(1, '', 'NAME', None))


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass
class EventRecord:
    tag: str                    # BIRT, DEAT, BURI, MARR, RESI, EVEN, etc.
    event_type: str | None      # value of TYPE sub-tag
    date: ParsedDate | None
    place: str | None
    citations: list[CitationRecord] = field(default_factory=list)
    raw: GedcomNode = field(default_factory=lambda: GedcomNode(1, '', '', None))


# ---------------------------------------------------------------------------
# Top-level record types
# ---------------------------------------------------------------------------

@dataclass
class Individual:
    xref: str
    names: list[NameRecord]
    sex: str | None
    events: list[EventRecord]
    family_child: list[str]     # FAMC xrefs
    family_spouse: list[str]    # FAMS xrefs
    citations: list[CitationRecord]
    media: list[str]            # OBJE xrefs
    raw: GedcomNode
    notes: list[str] = field(default_factory=list)       # inline NOTE text
    note_xrefs: list[str] = field(default_factory=list)  # linked NOTE xrefs (@N1@)

    # Pre-computed for matching (populated by parser via normalize.py)
    normalized_surnames: set[str] = field(default_factory=set)
    normalized_givens: set[str] = field(default_factory=set)
    birth_date: ParsedDate | None = None
    death_date: ParsedDate | None = None

    @property
    def display_name(self) -> str:
        if self.names:
            n = self.names[0]
            parts = []
            if n.given:
                parts.append(n.given)
            if n.surname:
                parts.append(n.surname)
            return ' '.join(parts) if parts else n.full
        return '(unknown)'

    @property
    def birth_year(self) -> int | None:
        return self.birth_date.year if self.birth_date else None

    @property
    def death_year(self) -> int | None:
        return self.death_date.year if self.death_date else None


@dataclass
class Family:
    xref: str
    husband_xref: str | None
    wife_xref: str | None
    child_xrefs: list[str]
    events: list[EventRecord]
    citations: list[CitationRecord]
    raw: GedcomNode


@dataclass
class Source:
    xref: str
    title: str
    author: str | None
    publisher: str | None
    repository_xref: str | None
    notes: list[str]
    refn: str | None
    raw: GedcomNode

    # Pre-computed for matching
    title_tokens: set[str] = field(default_factory=set)


@dataclass
class Repository:
    xref: str
    name: str | None
    raw: GedcomNode


@dataclass
class MediaObject:
    xref: str
    file: str | None
    form: str | None
    title: str | None
    raw: GedcomNode


@dataclass
class Note:
    xref: str
    text: str
    raw: GedcomNode


# ---------------------------------------------------------------------------
# Container for a whole parsed file
# ---------------------------------------------------------------------------

@dataclass
class GedcomFile:
    individuals: dict[str, Individual]   # xref → Individual
    families: dict[str, Family]          # xref → Family
    sources: dict[str, Source]           # xref → Source
    repositories: dict[str, Repository] # xref → Repository
    media: dict[str, MediaObject]        # xref → MediaObject
    notes: dict[str, Note]              # xref → Note
    submitter: GedcomNode | None
    header_raw: GedcomNode | None
    path: str = ''

    @property
    def indi_count(self) -> int:
        return len(self.individuals)

    @property
    def fam_count(self) -> int:
        return len(self.families)

    @property
    def source_count(self) -> int:
        return len(self.sources)


# ---------------------------------------------------------------------------
# Match result types
# ---------------------------------------------------------------------------

@dataclass
class SourceMatch:
    xref_a: str
    xref_b: str
    score: float


@dataclass
class SourceMatchResult:
    auto_matches: list[SourceMatch]             # score ≥ auto_threshold
    candidates: list[SourceMatch]               # review_threshold ≤ score < auto_threshold
    unmatched_b: list[str]                      # xrefs from B with no match


@dataclass
class IndividualMatch:
    xref_a: str
    xref_b: str
    score: float
    score_components: dict = field(default_factory=dict)


@dataclass
class IndividualMatchResult:
    auto_matches: list[IndividualMatch]
    candidates: list[IndividualMatch]
    unmatched_b: list[str]


@dataclass
class FamilyMatch:
    xref_a: str
    xref_b: str


@dataclass
class FamilyMatchResult:
    matches: list[FamilyMatch]
    unmatched_b: list[str]


# ---------------------------------------------------------------------------
# Merge decision types (populated by review.py)
# ---------------------------------------------------------------------------

@dataclass
class FieldChoice:
    """User's choice for a conflicting field: 'A', 'B', or 'both'."""
    field: str
    choice: str         # 'A' | 'B' | 'both'


@dataclass
class MergeDecisions:
    """All decisions made during interactive review."""
    # xref_b → xref_a (confirmed matches)
    source_map: dict[str, str] = field(default_factory=dict)
    indi_map: dict[str, str] = field(default_factory=dict)
    family_map: dict[str, str] = field(default_factory=dict)

    # xref_b → 'add' | 'skip'  (unmatched records)
    source_disposition: dict[str, str] = field(default_factory=dict)
    indi_disposition: dict[str, str] = field(default_factory=dict)
    family_disposition: dict[str, str] = field(default_factory=dict)

    # Per-individual field choices: xref_b → list[FieldChoice]
    field_choices: dict[str, list[FieldChoice]] = field(default_factory=dict)
