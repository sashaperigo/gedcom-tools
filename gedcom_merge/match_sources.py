"""
match_sources.py — Match source records between two GEDCOM files.

Uses Jaccard similarity on title token sets, with fuzzy string matching as a
tiebreaker. Brute-force all-pairs is fine since source counts are small (< 500).
"""

from __future__ import annotations

from gedcom_merge.model import (
    GedcomFile, Source, SourceMatch, SourceMatchResult,
)
from gedcom_merge.normalize import jaccard

try:
    from rapidfuzz import fuzz as _fuzz
    def _levenshtein_similarity(a: str, b: str) -> float:
        return _fuzz.ratio(a, b) / 100.0
except ImportError:
    def _levenshtein_similarity(a: str, b: str) -> float:  # type: ignore[misc]
        """Pure-Python fallback (slow, but correct)."""
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        # Simple SequenceMatcher approach
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_string(a: str | None, b: str | None) -> float:
    """Fuzzy score for optional string fields. 1.0 if both empty."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return _levenshtein_similarity(a, b)


def _extract_location_prefix(title: str | None) -> str | None:
    """
    For Ancestry-style titles ("Location, Database Name, Dates"), return the
    normalized location prefix (everything before the first comma).

    Returns None if the title has no commas or is empty.
    """
    if not title or ',' not in title:
        return None
    prefix = title.split(',', 1)[0].strip().lower()
    return prefix if prefix else None


def _score_title(src_a: Source, src_b: Source) -> float:
    """
    Primary: Jaccard on token sets.
    Secondary tiebreaker: normalized Levenshtein if Jaccard is 0.5–0.85.

    Hard veto: for Ancestry-style "Location, Database, Dates" titles, if both
    sources have a location prefix and they differ, return 0.0 — different
    locations mean different databases regardless of how similar the rest is.
    """
    loc_a = _extract_location_prefix(src_a.title)
    loc_b = _extract_location_prefix(src_b.title)

    # Hard veto: both have location prefixes and they don't match
    if loc_a and loc_b and loc_a != loc_b:
        return 0.0

    ta, tb = src_a.title_tokens, src_b.title_tokens
    # Subset bonus: if all tokens of one title appear in the other (e.g. Ancestry
    # databases where one tree records "..., 1800's-current" and the other drops
    # the date range suffix), treat it as a near-certain match.
    if ta and tb and (ta <= tb or tb <= ta):
        return 0.97

    j = jaccard(ta, tb)
    if 0.50 < j < 0.85:
        # Also compute Levenshtein on full titles as tiebreaker
        lev = _levenshtein_similarity(src_a.title, src_b.title)
        return (j + lev) / 2.0
    return j


def _score_pair(src_a: Source, src_b: Source) -> float:
    """
    Weighted score for a source pair.

    title_similarity    * 0.60
    author_similarity   * 0.15
    publisher_similarity * 0.10
    date_range_overlap  * 0.10   (approximated via title token year overlap)
    repo_similarity     * 0.05
    """
    title_score = _score_title(src_a, src_b)

    # Author / publisher fuzzy match
    author_score = _score_string(src_a.author, src_b.author)
    publisher_score = _score_string(src_a.publisher, src_b.publisher)

    # Date range overlap: check if year tokens in titles overlap
    year_tokens_a = {t for t in src_a.title_tokens if t.isdigit() and len(t) == 4}
    year_tokens_b = {t for t in src_b.title_tokens if t.isdigit() and len(t) == 4}
    if year_tokens_a or year_tokens_b:
        date_score = jaccard(year_tokens_a, year_tokens_b)
    else:
        date_score = 1.0  # neither has years → neutral

    # Repository name similarity
    if src_a.repository_xref and src_b.repository_xref:
        # We don't have repo names here — just check both have one
        repo_score = 0.8
    elif not src_a.repository_xref and not src_b.repository_xref:
        repo_score = 1.0
    else:
        repo_score = 0.0

    score = (
        title_score      * 0.60 +
        author_score     * 0.15 +
        publisher_score  * 0.10 +
        date_score       * 0.10 +
        repo_score       * 0.05
    )
    return round(score, 4)


# ---------------------------------------------------------------------------
# Main matching function
# ---------------------------------------------------------------------------

def match_sources(
    file_a: GedcomFile,
    file_b: GedcomFile,
    auto_threshold: float = 0.90,
    review_threshold: float = 0.65,
) -> SourceMatchResult:
    """
    Brute-force all-pairs source matching.

    Returns a SourceMatchResult with:
      - auto_matches:  score ≥ auto_threshold (one-to-one, highest score wins)
      - candidates:    review_threshold ≤ score < auto_threshold
      - unmatched_b:   File B sources with no match above review_threshold
    """
    sources_a = list(file_a.sources.values())
    sources_b = list(file_b.sources.values())

    # Score all pairs
    scored: list[tuple[float, str, str]] = []  # (score, xref_b, xref_a)
    for src_b in sources_b:
        for src_a in sources_a:
            score = _score_pair(src_a, src_b)
            if score >= review_threshold:
                scored.append((score, src_b.xref, src_a.xref))

    # Sort by score descending, then greedily assign best matches (one-to-one)
    scored.sort(key=lambda x: -x[0])
    used_a: set[str] = set()
    used_b: set[str] = set()
    auto_matches: list[SourceMatch] = []
    candidates: list[SourceMatch] = []

    for score, xref_b, xref_a in scored:
        if xref_b in used_b or xref_a in used_a:
            continue
        match = SourceMatch(xref_a=xref_a, xref_b=xref_b, score=score)
        if score >= auto_threshold:
            auto_matches.append(match)
            used_a.add(xref_a)
            used_b.add(xref_b)
        else:
            candidates.append(match)
            used_a.add(xref_a)
            used_b.add(xref_b)

    # Anything in B not matched above review_threshold
    matched_b = used_b
    unmatched_b = [src.xref for src in sources_b if src.xref not in matched_b]

    return SourceMatchResult(
        auto_matches=auto_matches,
        candidates=candidates,
        unmatched_b=unmatched_b,
    )
