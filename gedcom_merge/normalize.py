"""
normalize.py — Name, date, and place normalization for GEDCOM merge matching.

All normalization is pre-computed during parsing. The functions here are pure
(no I/O) and covered by unit tests.
"""

from __future__ import annotations
import re
import string
import unicodedata

from gedcom_merge.model import ParsedDate

try:
    from unidecode import unidecode as _unidecode
    def _strip_diacritics(s: str) -> str:
        return _unidecode(s)
except ImportError:
    def _strip_diacritics(s: str) -> str:  # type: ignore[misc]
        """Fallback: NFD + strip combining marks."""
        nfd = unicodedata.normalize('NFD', s)
        return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


# ---------------------------------------------------------------------------
# Month name → number
# ---------------------------------------------------------------------------

_MONTH_ABBR = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_GEDCOM_MONTHS = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_QUALIFIERS = {'ABT', 'ABOUT', 'CAL', 'EST', 'BEF', 'AFT', 'BET', 'FROM', 'TO'}


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def normalize_name_str(full: str) -> tuple[str, str]:
    """
    Parse a GEDCOM NAME value into (given, surname).

    GEDCOM convention: surname is enclosed in /slashes/.
    e.g. "Saverio Salvatore /Bonnici/" → ("saverio salvatore", "bonnici")
    """
    surname_match = re.search(r'/([^/]*)/', full)
    if surname_match:
        surname = surname_match.group(1).strip()
        given = full[:surname_match.start()].strip()
        # Also include text after the closing slash as part of given (rare but valid)
        after = full[surname_match.end():].strip()
        if after:
            given = (given + ' ' + after).strip()
    else:
        # No slashes: treat whole string as given, no surname
        given = full.strip()
        surname = ''

    given = _normalize_str(given)
    surname = _normalize_str(surname)
    return given, surname


def _normalize_str(s: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    s = _strip_diacritics(s).lower()
    s = ' '.join(s.split())
    return s


def normalize_surname(s: str) -> str:
    return _normalize_str(s)


def normalize_given(s: str) -> str:
    return _normalize_str(s)


# ---------------------------------------------------------------------------
# Title tokenization (for source matching)
# ---------------------------------------------------------------------------

def tokenize_title(title: str) -> set[str]:
    """
    Produce a set of lowercase tokens from a source title.
    Strips punctuation, drops very short tokens (≤1 char).
    """
    title = _strip_diacritics(title).lower()
    # Replace punctuation with spaces
    title = title.translate(str.maketrans(string.punctuation, ' ' * len(string.punctuation)))
    tokens = {t for t in title.split() if len(t) > 1}
    return tokens


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r'\b(\d{3,4})\b')
_DAY_MONTH_YEAR_RE = re.compile(
    r'^(\d{1,2})\s+([A-Z]{3})\s+(\d{3,4})$'
)
_MONTH_YEAR_RE = re.compile(r'^([A-Z]{3})\s+(\d{3,4})$')
_YEAR_ONLY_RE = re.compile(r'^(\d{3,4})$')
_BET_AND_RE = re.compile(
    r'^BET\s+(.+?)\s+AND\s+(.+)$', re.IGNORECASE
)


def parse_date(date_str: str | None) -> ParsedDate | None:
    """
    Parse a GEDCOM DATE value into a ParsedDate.

    Handles:
      - Exact: "15 MAR 1892", "MAR 1892", "1892"
      - Approximate: "ABT 1890", "BEF 1900", "AFT 1888", "CAL 1890", "EST 1890"
      - Ranges: "BET 1888 AND 1892", "BET 15 MAR 1888 AND 1892"
      - FROM/TO: treated as BEF/AFT equivalents

    Returns None if unparseable.
    """
    if not date_str:
        return None
    s = date_str.strip().upper()

    # BET ... AND ...
    bet_m = _BET_AND_RE.match(s)
    if bet_m:
        d1 = _parse_simple_date(bet_m.group(1).strip())
        d2 = _parse_simple_date(bet_m.group(2).strip())
        if d1 and d2:
            return ParsedDate('BET', d1.year, d1.month, d1.day, year2=d2.year)
        if d1:
            return ParsedDate('BET', d1.year, d1.month, d1.day)
        return None

    # FROM x TO y → treat as BET
    if s.startswith('FROM '):
        inner = s[5:]
        to_idx = inner.upper().find(' TO ')
        if to_idx != -1:
            d1 = _parse_simple_date(inner[:to_idx].strip())
            d2 = _parse_simple_date(inner[to_idx + 4:].strip())
            if d1 and d2:
                return ParsedDate('BET', d1.year, d1.month, d1.day, year2=d2.year)
        d = _parse_simple_date(inner.strip())
        if d:
            return ParsedDate('AFT', d.year, d.month, d.day)
        return None

    # Qualifier prefix
    qualifier = None
    for q in ('ABT', 'ABOUT', 'CAL', 'EST', 'BEF', 'AFT'):
        if s.startswith(q + ' ') or s == q:
            qualifier = 'ABT' if q in ('ABOUT', 'CAL', 'EST', 'ABT') else q
            s = s[len(q):].strip()
            break

    d = _parse_simple_date(s)
    if d is None:
        return None
    return ParsedDate(qualifier, d.year, d.month, d.day)


def _parse_simple_date(s: str) -> ParsedDate | None:
    """Parse 'DD MMM YYYY', 'MMM YYYY', or 'YYYY' (no qualifier)."""
    m = _DAY_MONTH_YEAR_RE.match(s)
    if m:
        month = _GEDCOM_MONTHS.get(m.group(2))
        return ParsedDate(None, int(m.group(3)), month, int(m.group(1)))

    m = _MONTH_YEAR_RE.match(s)
    if m:
        month = _GEDCOM_MONTHS.get(m.group(1))
        return ParsedDate(None, int(m.group(2)), month)

    m = _YEAR_ONLY_RE.match(s)
    if m:
        return ParsedDate(None, int(m.group(1)))

    return None


# ---------------------------------------------------------------------------
# Date comparison / scoring
# ---------------------------------------------------------------------------

def date_overlap_score(a: ParsedDate | None, b: ParsedDate | None) -> float:
    """
    Return a score 0.0–1.0 representing how closely two dates match.

    Per spec:
      - Exact match → 1.0
      - Same year, different month/day → 0.8
      - Within 2 years → 0.5
      - Approximate overlapping exact → 0.7
      - Both approximate and overlapping → 0.6
      - No overlap → 0.0
      - One or both missing → 0.3 (neutral)
    """
    if a is None or b is None:
        return 0.3

    ya = a.year
    yb = b.year
    if ya is None or yb is None:
        return 0.3

    # Exact qualifier on both
    a_exact = a.qualifier is None
    b_exact = b.qualifier is None

    # Range endpoints
    ya_min, ya_max = _year_range(a)
    yb_min, yb_max = _year_range(b)

    # Within 2 years (check before the strict no-overlap test)
    if a_exact and b_exact and ya is not None and yb is not None:
        if abs(ya - yb) <= 2:
            if ya == yb:
                if a.month == b.month and a.month is not None:
                    if a.day == b.day and a.day is not None:
                        return 1.0   # exact match
                    return 0.9       # same month, different day
                return 0.8           # same year, different month
            return 0.5               # within 2 years

    # No overlap — but if one or both dates are approximate, check for a
    # near-miss (within 5 years of the approximate date's central year).
    # e.g. "ABT 1850" vs exact "1856" should not score 0.0.
    if ya_max < yb_min or yb_max < ya_min:
        if not (a_exact and b_exact):
            gap = max(ya_min, yb_min) - min(ya_max, yb_max)
            if gap <= 5:
                return 0.4   # plausible near-miss with approximate date
        return 0.0

    # Ranges overlap (one or both approximate)
    if a_exact or b_exact:
        return 0.7   # approximate overlapping exact

    return 0.6       # both approximate, overlapping


def _year_range(d: ParsedDate) -> tuple[int, int]:
    """Return (min_year, max_year) covered by a ParsedDate."""
    if d.qualifier == 'BET':
        y2 = d.year2 if d.year2 is not None else d.year
        return d.year, y2
    if d.qualifier == 'BEF':
        return 0, d.year
    if d.qualifier == 'AFT':
        return d.year, 9999
    if d.qualifier == 'ABT':
        return d.year - 2, d.year + 2
    # Exact
    return d.year, d.year


# ---------------------------------------------------------------------------
# Place normalization and similarity
# ---------------------------------------------------------------------------

def normalize_place(place: str | None) -> str:
    """Lowercase, strip diacritics, strip trailing commas/whitespace."""
    if not place:
        return ''
    p = _strip_diacritics(place).lower()
    p = p.strip().rstrip(',').strip()
    return p


def place_similarity(a: str | None, b: str | None) -> float:
    """
    Compare two place strings hierarchically.
    Splits on commas, compares components (city, county, state, country).
    Returns 0.0–1.0.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    pa = normalize_place(a)
    pb = normalize_place(b)

    if pa == pb:
        return 1.0

    # Tokenize by comma
    parts_a = [p.strip() for p in pa.split(',') if p.strip()]
    parts_b = [p.strip() for p in pb.split(',') if p.strip()]

    if not parts_a or not parts_b:
        # Fall back to substring check
        return 0.5 if (pa in pb or pb in pa) else 0.0

    # Count matching components
    set_a = set(parts_a)
    set_b = set(parts_b)
    common = set_a & set_b
    union = set_a | set_b

    if not union:
        return 0.0

    jaccard = len(common) / len(union)

    # Boost if the smallest place (most specific) matches
    if parts_a[0] == parts_b[0]:
        jaccard = min(1.0, jaccard + 0.2)

    return min(1.0, jaccard)


# ---------------------------------------------------------------------------
# Jaccard similarity for sets (used for source title matching)
# ---------------------------------------------------------------------------

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)
