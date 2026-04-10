"""
match_individuals.py — Match individual records between two GEDCOM files.

Algorithm:
1. Build a surname blocking index for File A.
2. For each File B individual, find candidates via surname blocking.
3. Score each candidate pair with a weighted function.
4. Auto-match above threshold; propagate family context; repeat until stable.
5. Return auto_matches, candidates (for review), and unmatched_b.
"""

from __future__ import annotations
from collections import defaultdict

from gedcom_merge.model import (
    GedcomFile, Individual,
    IndividualMatch, IndividualMatchResult,
)
from gedcom_merge.normalize import (
    normalize_surname, date_overlap_score, place_similarity,
)

try:
    from rapidfuzz import fuzz as _fuzz
    from rapidfuzz.distance import Levenshtein as _Lev

    def _name_similarity(a: str, b: str) -> float:
        return _fuzz.ratio(a, b) / 100.0

    def _levenshtein_distance(a: str, b: str) -> int:
        return _Lev.distance(a, b)

except ImportError:
    from difflib import SequenceMatcher

    def _name_similarity(a: str, b: str) -> float:  # type: ignore[misc]
        return SequenceMatcher(None, a, b).ratio()

    def _levenshtein_distance(a: str, b: str) -> int:  # type: ignore[misc]
        # Simple O(nm) DP
        la, lb = len(a), len(b)
        dp = list(range(lb + 1))
        for i in range(1, la + 1):
            ndp = [i] + [0] * lb
            for j in range(1, lb + 1):
                if a[i - 1] == b[j - 1]:
                    ndp[j] = dp[j - 1]
                else:
                    ndp[j] = 1 + min(dp[j], ndp[j - 1], dp[j - 1])
            dp = ndp
        return dp[lb]


# ---------------------------------------------------------------------------
# Name alias table (Greek/Turkish/Western equivalents)
# ---------------------------------------------------------------------------

def _build_alias_groups() -> dict[str, set[str]]:
    groups = [                                                                                             
      # ── Male ──────────────────────────────────────────────────                                       
      {'george', 'georgios', 'giorgios', 'kevork', 'georgio', 'giorgio'},                                
      {'francis', 'francesco', 'francois', 'français'},                                                  
      {'john', 'ioannis', 'yiannis', 'yannis', 'giannis', 'jean', 'juan', 'giovanni', 'johannes',        
       'yanni'},                                                                                         
      {'constantine', 'konstantinos', 'kostas', 'costas', 'constantino'},                                
      {'stephen', 'esteban', 'stefan', 'stefano', 'steve', 'steven', 'stephano', 'stephane'},            
      {'nicholas', 'nikolaos', 'nikos', 'nikolas', 'nicolas', 'nikola', 'nicolao', 'nicola', 'nico',     
       'nicolo', 'nicolò', 'niccolo', 'niccolò', 'nicolaas', 'nicorosi'},                                
      {'peter', 'petros', 'pierre', 'pietro', 'piero', 'petar', 'porto'},                                
      {'michael', 'michail', 'michalis', 'mikael', 'miguel', 'mihail', 'michel', 'michele'},             
      {'theodore', 'theodoros', 'theo'},                                                                 
      {'dimitri', 'dimitrios', 'demetrios', 'demetrius', 'demetri'},                                     
      {'thomas', 'tomas', 'tommaso', 'tomaso'},                                                          
      {'alexander', 'alexandros', 'alexios', 'alex', 'alekos', 'aleksander', 'alexandre'},               
      {'evangelos', 'vangelis'},                                                                         
      {'panagiotis', 'panos', 'panayiotis', 'takis'},                                                    
      {'christos', 'christodoulos', 'christoforos', 'christopher', 'chris', 'christo',                   
       'cristoforo', 'christoforo'},                                                                     
      {'spyros', 'spyridon', 'spiro', 'spiridon', 'spiridione'},                                         
      {'vasilis', 'vassilis', 'vasileios', 'basilios', 'vaselios', 'vasilios'},                          
      {'antonis', 'antonios', 'antonio', 'anthony', 'tony', 'antoine'},                                  
      {'emilio', 'emil', 'emile', 'emin'},                                                               
      {'jacobo', 'giacomo', 'jacques', 'jacob', 'zaccaria'},                                             
      {'paul', 'paolo', 'paulo', 'pablo', 'pauli', 'polycarpe', 'policarpo'},                            
      {'philip', 'filippo', 'philippe', 'philippo'},                                                     
      {'andrew', 'andre', 'andrei'},                                                                     
      {'dominic', 'dominique', 'domenico'},                                                              
      {'gregory', 'gregoire', 'gregorio', 'kirkor'},                                                     
      {'jerome', 'jérôme', 'gerolamo', 'geronimo', 'hyeronimo'},                                         
      {'louis', 'luigi'},                                                                                
      {'giuseppe', 'joseph', 'josef'},                                              
      {'pantaleone', 'pandeli', 'leon'},                                                                 
                                                                                                         
      # ── Female ────────────────────────────────────────────────                                       
      {'helen', 'eleni', 'elena', 'helene', 'helena', 'hélène', 'ellen'},                                
      {'giuseppa', 'giuseppina', 'josephine', 'joséphine', 'josephina', 'josefina', 'josepha'},
      {'mary', 'maria', 'marie', 'maruca', 'marigho'},                                                   
      {'sophia', 'sofia', 'sophie'},                                                
      {'katerina', 'katherine', 'catherine', 'katarina', 'caterina', 'katrina', 'kate',                  
       'catarina', 'catharina', 'kathleen', 'chatrine', 'catu', 'catù'},                                 
      {'anna', 'anne', 'ann', 'ana'},                                                                    
      {'evangeline', 'vangelio'},                                                                        
      {'fotini', 'photini'},                                                                             
      {'angela', 'angele', 'angelina', 'angelica', 'angelique', 'angélique', 'angeru', 'angerù'},        
      {'teresa', 'therese', 'thérèse', 'theresa'},                                                       
      {'madeleine', 'magdalena', 'maddalena', 'madalena'},                                               
      {'brigida', 'brigidina', 'birgitta', 'bergula'},                                                   
      {'apollonia', 'appollonia', 'plumu', 'plumù'},                                                     
      {'despina', 'despinu', 'despinù'},                                                                 
      {'battistina', 'battina', 'bettina', 'battistine', 'batestu', 'batestù', 'battu'},                 
      {'julia', 'giulia', 'giuliana'},                                                                   
      {'joanna', 'giovanna', 'jeanne'},                                                                  
      {'rose', 'rosa', 'rosine', 'rosina', 'rosalie'},                                                   
      {'louise', 'luigia'},                                                                              
      {'epiphanie', 'fanny'},                                                                            
      {'lucia', 'lula'},                                                                                 
      {'sofronia', 'subru', 'subrù'},                                                                    
    ]                                       
    result: dict[str, set[str]] = {}
    for group in groups:
        for name in group:
            result[name] = group
    return result


_NAME_ALIASES: dict[str, set[str]] = _build_alias_groups()

# Tokens that mean "unknown" — treat as blank for both blocking and scoring.
_UNKNOWN_TOKENS: frozenset[str] = frozenset({
    'unknown', 'unkn', 'unk', 'unnamed', 'name unknown', '?', 'nn', 'n.n.',
})


def _is_unknown(name: str) -> bool:
    """Return True if name is a placeholder meaning the name is not known."""
    return name.strip().lower() in _UNKNOWN_TOKENS


# ---------------------------------------------------------------------------
# Surname blocking
# ---------------------------------------------------------------------------

def _get_husband_surnames(ind: Individual, file: GedcomFile) -> list[str]:
    """
    Return normalized surnames of the husband(s) of a married woman with unknown surname.
    Used to augment blocking for women whose surname wasn't recorded.
    """
    if ind.sex == 'M':
        return []
    surnames: list[str] = []
    for fams in ind.family_spouse[:2]:
        fam = file.families.get(fams)
        if not fam:
            continue
        husb = file.individuals.get(fam.husband_xref or '')
        if husb:
            for s in husb.normalized_surnames:
                if not _is_unknown(s) and s not in surnames:
                    surnames.append(s)
    return surnames


def _build_surname_index(file: GedcomFile) -> dict[str, list[str]]:
    """
    Build normalized_surname → [xref, ...] index for fast blocking.

    For women with unknown surnames who are married, also indexes them under
    their husband's surname so they can be found when the other file records
    that woman under the married name.
    """
    index: dict[str, list[str]] = defaultdict(list)
    for xref, ind in file.individuals.items():
        meaningful_surnames = [s for s in ind.normalized_surnames if not _is_unknown(s)]
        for sname in meaningful_surnames:
            index[sname].append(xref)
            # For compound double-surnames (e.g. "sarachaga mendoza"), also index
            # under each component so a single-surname record can find them.
            parts = sname.split()
            if len(parts) > 1:
                for part in parts:
                    if part not in meaningful_surnames:
                        index[part].append(xref)
        if not meaningful_surnames:
            # For married women with unknown surnames, index by husband's surname
            husb_surnames = _get_husband_surnames(ind, file)
            for sname in husb_surnames:
                index[sname].append(xref)
            if not husb_surnames:
                # Fall back: index by first given-name token (skip unknown givens too)
                for g in list(ind.normalized_givens)[:2]:
                    if not _is_unknown(g):
                        index['_given_' + g].append(xref)
                        break
    return dict(index)


def _get_candidates_for(
    ind_b: Individual,
    index_a: dict[str, list[str]],
    all_xrefs_a: list[str],
    file_b: GedcomFile | None = None,
) -> set[str]:
    """
    Return the set of File A xrefs that are candidates for matching ind_b.

    Uses exact + fuzzy (Levenshtein ≤ 2) surname matching.
    For women with unknown surnames, also searches by husband's surname.
    Falls back to given-name index if no surname match found.
    """
    candidates: set[str] = set()

    meaningful_surnames_b = [s for s in ind_b.normalized_surnames if not _is_unknown(s)]
    for sname in meaningful_surnames_b:
        # Exact lookup
        for xref in index_a.get(sname, []):
            candidates.add(xref)
        # Fuzzy expansion for longer surnames
        if len(sname) >= 5:
            for indexed_sname, xrefs in index_a.items():
                if indexed_sname.startswith('_given_'):
                    continue
                if _levenshtein_distance(sname, indexed_sname) <= 2:
                    candidates.update(xrefs)

    if not candidates and not meaningful_surnames_b and file_b:
        # No meaningful surname: for married women, try husband's surname
        for sname in _get_husband_surnames(ind_b, file_b):
            for xref in index_a.get(sname, []):
                candidates.add(xref)
            if len(sname) >= 5:
                for indexed_sname, xrefs in index_a.items():
                    if indexed_sname.startswith('_given_'):
                        continue
                    if _levenshtein_distance(sname, indexed_sname) <= 2:
                        candidates.update(xrefs)

    if not candidates:
        # No surname → try given-name index (skip unknown givens)
        for g in list(ind_b.normalized_givens)[:2]:
            if not _is_unknown(g):
                for xref in index_a.get('_given_' + g, []):
                    candidates.add(xref)

    return candidates


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_names(ind_a: Individual, ind_b: Individual) -> tuple[float, float]:
    """
    Return (surname_score, given_score).

    Compares all name variants from both sides, taking the best-matching pair.
    """
    # Filter out "unknown" placeholders — treat as blank (absence of data)
    surnames_a = {s for s in ind_a.normalized_surnames if not _is_unknown(s)} or {''}
    surnames_b = {s for s in ind_b.normalized_surnames if not _is_unknown(s)} or {''}
    givens_a = {g for g in ind_a.normalized_givens if not _is_unknown(g)} or {''}
    givens_b = {g for g in ind_b.normalized_givens if not _is_unknown(g)} or {''}

    best_surname = 0.0
    for sa in surnames_a:
        for sb in surnames_b:
            if not sa or not sb:
                continue
            s = _name_similarity(sa, sb)
            # Compound-surname bonus: if one surname is a full word component
            # of the other (e.g. "sarachaga" vs "sarachaga mendoza"), treat as
            # a strong match — one file just records the double surname.
            parts_a = sa.split()
            parts_b = sb.split()
            if sa in parts_b or sb in parts_a:
                s = max(s, 0.92)
            if s > best_surname:
                best_surname = s

    best_given = 0.0
    for ga in givens_a:
        for gb in givens_b:
            if not ga or not gb:
                continue
            s = _name_similarity(ga, gb)
            # Bonus: substring match (e.g., "Michael" vs "Michael James")
            if ga in gb or gb in ga:
                s = max(s, 0.95)
            # Alias boost: known equivalent name forms (Greek/Turkish/Western)
            alias_group = _NAME_ALIASES.get(ga)
            if alias_group and gb in alias_group:
                s = max(s, 0.92)
            if s > best_given:
                best_given = s

    return best_surname, best_given


def _score_sex(ind_a: Individual, ind_b: Individual) -> float:
    if not ind_a.sex or not ind_b.sex:
        return 0.5   # unknown → neutral
    return 1.0 if ind_a.sex == ind_b.sex else 0.0


def _estimate_birth_year(ind: Individual, file: GedcomFile) -> int | None:
    """
    Estimate a birth year for an individual with no recorded birth date.

    Strategy 1: spouse's birth year (assume roughly same generation).
    Strategy 2: parent's birth year + 27.
    Strategy 3: child's birth year - 27 (average of first child's year - 27).
    Strategy 4: if both parent estimate and child estimate are available, average them.

    Returns None if no estimate is possible.
    """
    # Strategy 1: spouse's birth year
    spouse_est: int | None = None
    for fams in ind.family_spouse[:2]:
        fam = file.families.get(fams)
        if not fam:
            continue
        for sx in [fam.husband_xref, fam.wife_xref]:
            if not sx or sx == ind.xref:
                continue
            spouse = file.individuals.get(sx)
            if not spouse:
                continue
            birth_ev = next((e for e in spouse.events if e.tag == 'BIRT'), None)
            if birth_ev and birth_ev.date and birth_ev.date.year:
                spouse_est = birth_ev.date.year
                break
        if spouse_est:
            break

    if spouse_est:
        return spouse_est

    # Strategy 2: parent's birth year + 27
    parent_est: int | None = None
    for famc in ind.family_child[:1]:
        fam = file.families.get(famc)
        if not fam:
            continue
        for px in [fam.husband_xref, fam.wife_xref]:
            if not px:
                continue
            parent = file.individuals.get(px)
            if not parent:
                continue
            birth_ev = next((e for e in parent.events if e.tag == 'BIRT'), None)
            if birth_ev and birth_ev.date and birth_ev.date.year:
                parent_est = birth_ev.date.year + 27
                break
        if parent_est:
            break

    # Strategy 3: child's birth year - 27 (use earliest-born child)
    child_est: int | None = None
    for fams in ind.family_spouse[:2]:
        fam = file.families.get(fams)
        if not fam:
            continue
        earliest_child_year: int | None = None
        for chil_xref in fam.child_xrefs:
            child = file.individuals.get(chil_xref)
            if not child:
                continue
            birth_ev = next((e for e in child.events if e.tag == 'BIRT'), None)
            if birth_ev and birth_ev.date and birth_ev.date.year:
                yr = birth_ev.date.year
                if earliest_child_year is None or yr < earliest_child_year:
                    earliest_child_year = yr
        if earliest_child_year:
            child_est = earliest_child_year - 27
            break

    # Strategy 4: if both parent and child estimates exist, average them
    if parent_est and child_est:
        return round((parent_est + child_est) / 2)
    if parent_est:
        return parent_est
    if child_est:
        return child_est

    return None


def _score_event(ind_a: Individual, ind_b: Individual, tag: str) -> float:
    """Score birth or death match (date + place)."""
    ev_a = next((e for e in ind_a.events if e.tag == tag), None)
    ev_b = next((e for e in ind_b.events if e.tag == tag), None)

    if ev_a is None and ev_b is None:
        return 0.5   # both missing → fully neutral
    if ev_a is None or ev_b is None:
        return 0.5   # one missing → neutral (absence of data shouldn't penalize)

    date_score = date_overlap_score(ev_a.date, ev_b.date)

    # Place: neutral (0.5) if one or both sides are missing — absence of data
    # shouldn't penalize; place_similarity returns 0.0 for one-side missing.
    if ev_a.place and ev_b.place:
        place_score = place_similarity(ev_a.place, ev_b.place)
    else:
        place_score = 0.5   # neutral — don't penalize for missing place

    # Weighted: date is more reliable than place
    return date_score * 0.70 + place_score * 0.30


def _has_parent_contradiction(
    ind_b: Individual,
    ind_a: Individual,
    matched_b_to_a: dict[str, str],
    file_a: GedcomFile,
    file_b: GedcomFile,
) -> bool:
    """
    Return True if ind_b and ind_a have confirmed-different parents.

    A contradiction is: a parent of ind_b has already been matched to someone
    in File A, but that someone is *not* the corresponding parent of ind_a.
    This is a very strong signal that the two individuals are different people.
    """
    for famc_b in ind_b.family_child:
        fam_b = file_b.families.get(famc_b)
        if not fam_b:
            continue
        for famc_a in ind_a.family_child:
            fam_a = file_a.families.get(famc_a)
            if not fam_a:
                continue
            for pb, pa in [
                (fam_b.husband_xref, fam_a.husband_xref),
                (fam_b.wife_xref,    fam_a.wife_xref),
            ]:
                if pb and pa and pb in matched_b_to_a:
                    if matched_b_to_a[pb] != pa:
                        return True
    return False


def _score_family_context(
    ind_b: Individual,
    ind_a: Individual,
    matched_b_to_a: dict[str, str],   # xref_b → xref_a confirmed so far
    file_a: GedcomFile,
    file_b: GedcomFile,
) -> float:
    """
    Score based on how many relatives have already been matched.

    Tiers (highest to lowest):
      0.97  parents AND spouse both match
      0.90  at least one parent matches
      0.85  spouse matches (no parent data to compare)
      0.78  ≥ 2 children match
      0.68  1 child matches
      0.05  parent contradiction (a confirmed-matched parent doesn't agree)
      0.50  neutral (no relatives to check, or none matched yet)
    """
    if not matched_b_to_a:
        return 0.5   # neutral on first pass

    # --- Parents ---
    parent_matches = 0
    parent_contradictions = 0

    for famc_b in ind_b.family_child:
        fam_b = file_b.families.get(famc_b)
        if not fam_b:
            continue
        for famc_a in ind_a.family_child:
            fam_a = file_a.families.get(famc_a)
            if not fam_a:
                continue
            for pb, pa in [
                (fam_b.husband_xref, fam_a.husband_xref),
                (fam_b.wife_xref,    fam_a.wife_xref),
            ]:
                if pb and pa:
                    if matched_b_to_a.get(pb) == pa:
                        parent_matches += 1
                    elif pb in matched_b_to_a:
                        parent_contradictions += 1

    if parent_contradictions > 0:
        return 0.05   # almost certainly different people

    # --- Spouses ---
    spouse_matches = 0
    for fams_b in ind_b.family_spouse:
        fam_b = file_b.families.get(fams_b)
        if not fam_b:
            continue
        spouse_b = fam_b.wife_xref if ind_b.sex == 'M' else fam_b.husband_xref
        for fams_a in ind_a.family_spouse:
            fam_a = file_a.families.get(fams_a)
            if not fam_a:
                continue
            spouse_a = fam_a.wife_xref if ind_a.sex == 'M' else fam_a.husband_xref
            if spouse_b and spouse_a and matched_b_to_a.get(spouse_b) == spouse_a:
                spouse_matches += 1

    # --- Children ---
    child_matches = 0
    for fams_b in ind_b.family_spouse:
        fam_b = file_b.families.get(fams_b)
        if not fam_b:
            continue
        for fams_a in ind_a.family_spouse:
            fam_a = file_a.families.get(fams_a)
            if not fam_a:
                continue
            for chil_b in fam_b.child_xrefs:
                for chil_a in fam_a.child_xrefs:
                    if chil_b and chil_a and matched_b_to_a.get(chil_b) == chil_a:
                        child_matches += 1

    # Scored tiers: parents + spouse is the strongest signal
    if parent_matches > 0 and spouse_matches > 0:
        return 0.97
    if parent_matches > 0:
        return 0.90
    if spouse_matches > 0:
        return 0.85
    if child_matches >= 2:
        return 0.78
    if child_matches == 1:
        return 0.68

    return 0.5   # no relatives to check → neutral


def _plausible_lifespan(ind: Individual, file: GedcomFile) -> tuple[int | None, int | None]:
    """
    Return (earliest_birth, latest_death) as plausible bounds for when this
    individual could have been alive.

    Rules (per domain conventions for genealogical records):
    - Born in X (any qualifier): latest_death = X + 100
    - Died BEF Y: death in [Y-40, Y], so earliest_birth = Y - 140 (death_min - 100 yrs)
    - Died exact/ABT/BET Y: latest_death = Y + 5 (small slack for qualifiers)
    - Died AFT Y: latest_death = Y + 100 (open-ended)
    - No birth or death: fall back to estimated birth year ± slack
    """
    birth_ev = next((e for e in ind.events if e.tag == 'BIRT'), None)
    death_ev = next((e for e in ind.events if e.tag == 'DEAT'), None)

    # ── earliest plausible birth ──────────────────────────────────────────────
    earliest_birth: int | None = None
    if birth_ev and birth_ev.date and birth_ev.date.year:
        d = birth_ev.date
        if d.qualifier == 'BEF':
            earliest_birth = None          # unbounded: could be any time before Y
        elif d.qualifier == 'AFT':
            earliest_birth = d.year
        else:                              # exact, ABT, BET — use year with slack
            earliest_birth = d.year - 10
    elif death_ev and death_ev.date and death_ev.date.year:
        d = death_ev.date
        if d.qualifier == 'BEF':
            # Death in [Y-40, Y]; born at most 100 years before death_min
            earliest_birth = d.year - 40 - 100
        else:
            # Died around Y; born at most 100 years before
            earliest_birth = d.year - 100
    else:
        est = _estimate_birth_year(ind, file)
        if est:
            earliest_birth = est - 15

    # ── latest plausible death ────────────────────────────────────────────────
    latest_death: int | None = None
    if death_ev and death_ev.date and death_ev.date.year:
        d = death_ev.date
        if d.qualifier == 'BEF':
            latest_death = d.year
        elif d.qualifier == 'AFT':
            latest_death = d.year + 100
        else:                              # exact, ABT, BET
            year2 = getattr(d, 'year2', None)
            latest_death = (year2 or d.year) + 5
    elif birth_ev and birth_ev.date and birth_ev.date.year:
        d = birth_ev.date
        # Born around/before/after Y — assume they could live at most 100 years
        year = d.year if d.qualifier != 'BEF' else d.year
        latest_death = year + 100
    else:
        est = _estimate_birth_year(ind, file)
        if est:
            latest_death = est + 115

    return earliest_birth, latest_death


def _score_pair(
    ind_a: Individual,
    ind_b: Individual,
    matched_b_to_a: dict[str, str],
    file_a: GedcomFile,
    file_b: GedcomFile,
) -> tuple[float, dict]:
    """
    Compute the weighted matching score for a pair of individuals.

    Returns (score, component_dict).
    """
    surname_score, given_score = _score_names(ind_a, ind_b)
    birth_score = _score_event(ind_a, ind_b, 'BIRT')
    death_score = _score_event(ind_a, ind_b, 'DEAT')
    sex_score = _score_sex(ind_a, ind_b)
    family_score = _score_family_context(ind_b, ind_a, matched_b_to_a, file_a, file_b)

    # Hard veto: if sex is known and contradicts, score is essentially 0.
    # Exception: bypass when name + birth + death are all near-perfect (≥ 3.6/4.0
    # combined), which strongly implies a data-entry error in the SEX field rather
    # than a genuine distinction between two different people.
    if ind_a.sex and ind_b.sex and ind_a.sex != ind_b.sex:
        primary_signal_sum = surname_score + given_score + birth_score + death_score
        if primary_signal_sum < 3.4:
            return 0.0, {}

    # Hard veto: both sides have known surnames that are clearly different.
    # fuzz.ratio on short strings can produce misleadingly high scores from
    # accidental shared characters (e.g. "hancy" vs "banca" → 60%).
    # If the best surname pair scores below 0.65, these are different families.
    known_surnames_a = {s for s in ind_a.normalized_surnames if not _is_unknown(s)}
    known_surnames_b = {s for s in ind_b.normalized_surnames if not _is_unknown(s)}
    if known_surnames_a and known_surnames_b and surname_score < 0.55:
        return 0.0, {}

    def _get_birth_ev(ind: Individual):
        return next((e for e in ind.events if e.tag == 'BIRT'), None)

    def _get_death_ev(ind: Individual):
        return next((e for e in ind.events if e.tag == 'DEAT'), None)

    birt_a = _get_birth_ev(ind_a)
    birt_b = _get_birth_ev(ind_b)
    deat_a = _get_death_ev(ind_a)
    deat_b = _get_death_ev(ind_b)

    actual_birth_a = birt_a.date.year if (birt_a and birt_a.date and birt_a.date.year) else None
    actual_birth_b = birt_b.date.year if (birt_b and birt_b.date and birt_b.date.year) else None
    actual_death_a = deat_a.date.year if (deat_a and deat_a.date and deat_a.date.year) else None
    actual_death_b = deat_b.date.year if (deat_b and deat_b.date and deat_b.date.year) else None

    # Hard veto: birth years > 50 apart (use actual birth year or estimate)
    est_birth_a = actual_birth_a or _estimate_birth_year(ind_a, file_a)
    est_birth_b = actual_birth_b or _estimate_birth_year(ind_b, file_b)
    if est_birth_a and est_birth_b and abs(est_birth_a - est_birth_b) > 50:
        return 0.0, {}

    # Hard veto: both have specific birth dates (month+year minimum, no qualifier) and
    # they differ by > 5 years. A bare year ("1892") or approximate date ("ABT 1890")
    # does NOT count as specific — only month+year or day+month+year without a qualifier.
    def _specific_birth_year(ev) -> int | None:
        if not ev or not ev.date:
            return None
        d = ev.date
        if d.qualifier is not None:  # ABT, BEF, AFT, BET → not specific
            return None
        if d.month is None:          # year-only → not specific
            return None
        return d.year

    specific_birth_a = _specific_birth_year(birt_a)
    specific_birth_b = _specific_birth_year(birt_b)
    if specific_birth_a and specific_birth_b and abs(specific_birth_a - specific_birth_b) > 5:
        return 0.0, {}

    # Hard veto: death years both present and differ by > 25 years
    if actual_death_a and actual_death_b and abs(actual_death_a - actual_death_b) > 25:
        return 0.0, {}

    # Hard veto: one person died before the other was born — impossible match.
    # Use actual birth/death years only (not estimates — too imprecise for this check).
    if actual_death_a and actual_birth_b and actual_death_a < actual_birth_b:
        return 0.0, {}
    if actual_death_b and actual_birth_a and actual_death_b < actual_birth_a:
        return 0.0, {}

    # Hard veto: plausible lifespans cannot overlap.
    # Catches cross-date cases like "born ABT 1150" vs "died BEF 1512" where
    # no single-field check fires (different field types on each side).
    #   - Born X → latest possible death = X + 100
    #   - Died BEF Y → death in [Y-40, Y], earliest possible birth = Y - 140
    eb_a, ld_a = _plausible_lifespan(ind_a, file_a)
    eb_b, ld_b = _plausible_lifespan(ind_b, file_b)
    if ld_a is not None and eb_b is not None and ld_a < eb_b:
        return 0.0, {}
    if ld_b is not None and eb_a is not None and ld_b < eb_a:
        return 0.0, {}

    score = (
        surname_score * 0.20 +
        given_score   * 0.20 +
        birth_score   * 0.20 +
        death_score   * 0.10 +
        sex_score     * 0.05 +
        family_score  * 0.25
    )

    # Soft cap for parent contradiction: can still appear as a candidate
    # (adoption/step-parent edge case) but never auto-matches.
    if family_score <= 0.05 and _has_parent_contradiction(ind_b, ind_a, matched_b_to_a, file_a, file_b):
        score = min(score, 0.60)

    # Corroboration requirement: name-only matches are too ambiguous.
    # If neither individual has any birth/death year AND no relatives are matched,
    # cap the score below the review threshold so it doesn't surface for review.
    def _has_dated_event(ind: Individual, tag: str) -> bool:
        return any(e.tag == tag and e.date and e.date.year for e in ind.events)

    has_any_date = (
        _has_dated_event(ind_a, 'BIRT') or _has_dated_event(ind_b, 'BIRT') or
        _has_dated_event(ind_a, 'DEAT') or _has_dated_event(ind_b, 'DEAT')
    )
    if not has_any_date and family_score <= 0.50:
        score = min(score, 0.62)

    components = {
        'surname': round(surname_score, 3),
        'given': round(given_score, 3),
        'birth': round(birth_score, 3),
        'death': round(death_score, 3),
        'sex': round(sex_score, 3),
        'family': round(family_score, 3),
    }
    return round(score, 4), components


# ---------------------------------------------------------------------------
# Iterative propagation
# ---------------------------------------------------------------------------

def _relatives_of_b(ind_b: Individual, file_b: GedcomFile) -> list[str]:
    """Return xrefs of all close relatives of ind_b in file_b."""
    relatives: list[str] = []
    for famc in ind_b.family_child:
        fam = file_b.families.get(famc)
        if fam:
            if fam.husband_xref:
                relatives.append(fam.husband_xref)
            if fam.wife_xref:
                relatives.append(fam.wife_xref)
            relatives.extend(fam.child_xrefs)
    for fams in ind_b.family_spouse:
        fam = file_b.families.get(fams)
        if fam:
            if fam.husband_xref:
                relatives.append(fam.husband_xref)
            if fam.wife_xref:
                relatives.append(fam.wife_xref)
            relatives.extend(fam.child_xrefs)
    return relatives


def match_individuals(
    file_a: GedcomFile,
    file_b: GedcomFile,
    source_map: dict[str, str] | None = None,
    auto_threshold: float = 0.75,
    review_threshold: float = 0.65,
) -> IndividualMatchResult:
    """
    Match individuals from file_b to file_a using surname blocking and
    iterative family-context propagation.

    Returns IndividualMatchResult with auto_matches, candidates, and unmatched_b.
    """
    index_a = _build_surname_index(file_a)
    all_xrefs_a = list(file_a.individuals.keys())

    matched_b_to_a: dict[str, str] = {}   # confirmed xref_b → xref_a
    matched_a: set[str] = set()            # xrefs in A that are taken

    auto_matches: list[IndividualMatch] = []
    # dirty_b: set of B xrefs whose family context changed (re-score these)
    dirty_b: set[str] = set(file_b.individuals.keys())

    # Candidate pool: xref_b → list[(score, xref_a, components)]
    candidate_pool: dict[str, list[tuple[float, str, dict]]] = {}

    # Initial scoring pass for all B individuals
    for xref_b, ind_b in file_b.individuals.items():
        candidates_a = _get_candidates_for(ind_b, index_a, all_xrefs_a, file_b)
        best_per_b: list[tuple[float, str, dict]] = []
        for xref_a in candidates_a:
            if xref_a in matched_a:
                continue
            ind_a = file_a.individuals[xref_a]
            score, comps = _score_pair(ind_a, ind_b, matched_b_to_a, file_a, file_b)
            if score >= review_threshold:
                best_per_b.append((score, xref_a, comps))
        best_per_b.sort(key=lambda x: -x[0])
        candidate_pool[xref_b] = best_per_b

    # Iterative auto-matching with propagation
    changed = True
    while changed:
        changed = False

        # Sort B individuals by their best candidate score, highest first
        order = sorted(
            dirty_b,
            key=lambda xb: -(candidate_pool[xb][0][0] if candidate_pool.get(xb) else 0.0)
        )

        newly_matched: list[str] = []

        for xref_b in order:
            if xref_b in matched_b_to_a:
                continue
            pool = candidate_pool.get(xref_b, [])
            # Re-score with updated family context
            ind_b = file_b.individuals[xref_b]
            rescored: list[tuple[float, str, dict]] = []
            for _, xref_a, _ in pool:
                if xref_a in matched_a:
                    continue
                ind_a = file_a.individuals[xref_a]
                score, comps = _score_pair(ind_a, ind_b, matched_b_to_a, file_a, file_b)
                if score >= review_threshold:
                    rescored.append((score, xref_a, comps))
            rescored.sort(key=lambda x: -x[0])
            candidate_pool[xref_b] = rescored

            if rescored:
                best_score, best_xref_a, best_comps = rescored[0]
                family_score = best_comps.get('family', 0.5)
                effective_threshold = 0.60 if family_score >= 0.90 else auto_threshold
                if best_score >= effective_threshold:
                    # Confirm match
                    matched_b_to_a[xref_b] = best_xref_a
                    matched_a.add(best_xref_a)
                    auto_matches.append(IndividualMatch(
                        xref_a=best_xref_a,
                        xref_b=xref_b,
                        score=best_score,
                        score_components=best_comps,
                    ))
                    newly_matched.append(xref_b)
                    changed = True

        # Mark relatives of newly matched B individuals as dirty
        dirty_b = set()
        for xref_b in newly_matched:
            ind_b = file_b.individuals[xref_b]
            for rel_xref in _relatives_of_b(ind_b, file_b):
                if rel_xref not in matched_b_to_a:
                    dirty_b.add(rel_xref)

    # Final re-score pass: family context is now fully populated.
    # Many individuals were scored early when matched_b_to_a was sparse;
    # re-scoring now may reveal additional auto-matches.
    for xref_b in sorted(candidate_pool.keys()):
        if xref_b in matched_b_to_a:
            continue
        pool = candidate_pool.get(xref_b, [])
        ind_b = file_b.individuals[xref_b]
        rescored = []
        for _, xref_a, _ in pool:
            if xref_a in matched_a:
                continue
            ind_a = file_a.individuals[xref_a]
            score, comps = _score_pair(ind_a, ind_b, matched_b_to_a, file_a, file_b)
            if score >= review_threshold:
                rescored.append((score, xref_a, comps))
        rescored.sort(key=lambda x: -x[0])
        candidate_pool[xref_b] = rescored
        if rescored:
            best_score, best_xref_a, best_comps = rescored[0]
            family_score = best_comps.get('family', 0.5)
            effective_threshold = 0.60 if family_score >= 0.90 else auto_threshold
            if best_score >= effective_threshold and best_xref_a not in matched_a:
                matched_b_to_a[xref_b] = best_xref_a
                matched_a.add(best_xref_a)
                auto_matches.append(IndividualMatch(
                    xref_a=best_xref_a,
                    xref_b=xref_b,
                    score=best_score,
                    score_components=best_comps,
                ))

    # Sibling rivalry filter: if ind_b has a sibling in File B who scores
    # substantially better (>= 0.10) against the same File A person, this
    # candidate is almost certainly a false positive — the sibling is the real match.
    xa_to_cands: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for xref_b, pool in candidate_pool.items():
        if xref_b not in matched_b_to_a and pool:
            xa_to_cands[pool[0][1]].append((pool[0][0], xref_b))

    sibling_filtered: set[str] = set()
    for xref_b, pool in candidate_pool.items():
        if xref_b in matched_b_to_a or xref_b in sibling_filtered or not pool:
            continue
        best_score, best_xa, _ = pool[0]
        ind_b = file_b.individuals[xref_b]
        siblings_b: set[str] = set()
        for famc in ind_b.family_child[:1]:
            fam = file_b.families.get(famc)
            if fam:
                siblings_b.update(c for c in fam.child_xrefs if c != xref_b)
        for sib_score, sib_xref in xa_to_cands.get(best_xa, []):
            if sib_xref in siblings_b and sib_score >= best_score + 0.10:
                sibling_filtered.add(xref_b)
                break

    for xref_b in sibling_filtered:
        candidate_pool[xref_b] = []

    # Build candidates list from remaining unmatched B with pool scores
    candidates: list[IndividualMatch] = []
    for xref_b, pool in candidate_pool.items():
        if xref_b in matched_b_to_a:
            continue
        if pool:
            best_score, best_xref_a, best_comps = pool[0]
            if review_threshold <= best_score < auto_threshold:
                candidates.append(IndividualMatch(
                    xref_a=best_xref_a,
                    xref_b=xref_b,
                    score=best_score,
                    score_components=best_comps,
                ))

    # Unmatched: B individuals with no match at all
    unmatched_b = [
        xref_b for xref_b in file_b.individuals
        if xref_b not in matched_b_to_a
        and not any(m.xref_b == xref_b for m in candidates)
    ]

    # Sort for determinism
    auto_matches.sort(key=lambda m: -m.score)
    candidates.sort(key=lambda m: -m.score)

    return IndividualMatchResult(
        auto_matches=auto_matches,
        candidates=candidates,
        unmatched_b=unmatched_b,
    )
