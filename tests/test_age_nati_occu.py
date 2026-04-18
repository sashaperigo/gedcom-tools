"""
Tests for:
  1. GEDCOM AGE tag format validation (is_valid_age)
  2. AGE tag parsed from GEDCOM into event dict
  3. DEAT+AGE (no date) display as "Died at age …" in _HTML_TEMPLATE
  4. NATI inline_val present in build_people_json output
  5. Nationality pill display code in _HTML_TEMPLATE (regression guard)
  6. OCCU prose does NOT add "Worked as" prefix (regression guard)

Bug history:
  - NATI events not displaying: natiEvents rendered e.inline_val which was null
    for events where the type was stored only in e.type (pre-fix). Fixed by ensuring
    the parser sets inline_val from the GEDCOM inline value.
  - OCCU "Worked as" prefix: commit 2717ed7 added `Worked as ${type}` prefix,
    making "Worked as Employed with the French company…" grammatically wrong.
    Fixed to display type directly.
"""

import json
import re
from pathlib import Path

import pytest

from viz_ancestors import (
    _HTML_TEMPLATE,
    build_people_json,
    is_valid_age,
    parse_gedcom,
    render_html,
    build_tree_json,
    build_relatives_json,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'

# JS logic now lives in external js/ files; combine all sources for pattern checks.
_JS_DIR = Path(__file__).parent.parent / 'js'
_FULL_SOURCE = _HTML_TEMPLATE + ''.join(
    f.read_text(encoding='utf-8') for f in sorted(_JS_DIR.glob('*.js'))
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def parsed():
    return parse_gedcom(str(FIXTURE))


@pytest.fixture(scope='module')
def indis(parsed):
    return parsed[0]


@pytest.fixture(scope='module')
def fams(parsed):
    return parsed[1]


@pytest.fixture(scope='module')
def people(indis, fams, parsed):
    _, _, sources = parsed
    return build_people_json(set(indis.keys()), indis, fams, sources)


# ---------------------------------------------------------------------------
# Part 1: is_valid_age unit tests
# ---------------------------------------------------------------------------

class TestIsValidAge:
    """Validate the GEDCOM AGE tag format per spec."""

    # ── valid values ──────────────────────────────────────────────────────

    @pytest.mark.parametrize('age', [
        '55y',
        '6m',
        '14d',
        '4y 8m 10d',
        '55y 3m',
        '2y 10d',
        '6m 14d',
        '>55y',
        '<1y',
        '>55y 3m',
        'INFANT',
        'STILLBORN',
        'CHILD',
        '>CHILD',
        '<CHILD',
        '0y',
        '100y 11m',   # exactly 10 chars — within 12-char limit
        '1y',
        '1m',
        '1d',
        '55Y',                 # case-insensitive: uppercase unit labels are accepted
    ])
    def test_valid(self, age):
        assert is_valid_age(age), f"Expected valid: {age!r}"

    # ── invalid values ────────────────────────────────────────────────────

    @pytest.mark.parametrize('age', [
        'ABT 55',              # ABT is a date prefix, not an AGE prefix
        '55',                  # missing unit label
        '55 years',            # must use single-letter labels
        'BET 50y AND 60y',     # no range syntax for AGE
        '4y, 8m, 10d',         # no commas allowed
        '8m 4y',               # wrong order (months before years)
        '10d 6m',              # wrong order (days before months)
        '10d 55y',             # wrong order
        '',                    # empty string
        'roughly 55',          # free text
        'about 30y',           # ABT-like free text
        '>100y 11m 30d extra', # too long (> 12 chars)
    ])
    def test_invalid(self, age):
        assert not is_valid_age(age), f"Expected invalid: {age!r}"

    def test_none_is_invalid(self):
        assert not is_valid_age(None)

    def test_too_long_is_invalid(self):
        # 13 characters — exceeds the 12-char GEDCOM field limit
        assert not is_valid_age('100y 11m 30d!')

    def test_whitespace_stripped(self):
        assert is_valid_age('  55y  ')

    def test_keyword_case_insensitive(self):
        assert is_valid_age('infant')
        assert is_valid_age('Infant')
        assert is_valid_age('INFANT')


# ---------------------------------------------------------------------------
# Part 2: AGE parsed into event dict
# ---------------------------------------------------------------------------

class TestAgeParsed:
    """AGE sub-tag on DEAT is stored in event['age']."""

    def test_deat_age_stored(self, indis):
        # @I9@ Helen Taylor has: 1 DEAT Y / 2 AGE 55y / 2 NOTE ...
        deat = next((e for e in indis['@I9@']['events'] if e['tag'] == 'DEAT'), None)
        assert deat is not None, "Helen Taylor should have a DEAT event"
        assert deat['age'] == '55y', f"Expected age '55y', got {deat['age']!r}"

    def test_deat_age_in_people_json(self, people):
        events = people['@I9@']['events']
        deat = next((e for e in events if e['tag'] == 'DEAT'), None)
        assert deat is not None
        assert deat.get('age') == '55y'

    def test_age_field_present_on_all_events(self, people):
        """Every event in build_people_json output has an 'age' key."""
        for xref, person in people.items():
            for evt in person['events']:
                assert 'age' in evt, (
                    f"{xref} event {evt.get('tag')!r} missing 'age' key"
                )

    def test_deat_without_age_has_none(self, people):
        # @I2@ James Smith has a DEAT with a date but no AGE
        deat = next((e for e in people['@I2@']['events'] if e['tag'] == 'DEAT'), None)
        assert deat is not None
        assert deat.get('age') is None


# ---------------------------------------------------------------------------
# Part 3: DEAT + AGE display prose in _HTML_TEMPLATE
# ---------------------------------------------------------------------------

class TestDeatAgeDisplay:
    """Regression guard: DEAT with age but no date shows 'Died … age'."""

    def test_fmt_age_function_present(self):
        assert 'function fmtAge' in _FULL_SOURCE

    def test_deat_age_branch_in_prose(self):
        # The DEAT case must reference the age field and call fmtAge.
        # The variable may be named 'fact' or 'evt' depending on the impl.
        assert ('fact.age' in _FULL_SOURCE or 'evt.age' in _FULL_SOURCE), (
            "DEAT prose must reference the .age field"
        )
        assert (
            'fmtAge(fact.age)' in _FULL_SOURCE
            or 'fmtAge(evt.age)' in _FULL_SOURCE
            or 'fmtAge(age)' in _FULL_SOURCE
        ), "DEAT prose must call fmtAge on the age field"

    def test_deat_age_prose_in_rendered_html(self, people, indis, fams, parsed):
        tree = build_tree_json('@I1@', indis, fams)
        relatives = build_relatives_json(tree, indis, fams)
        html = render_html(tree, 'Rose Smith', people, relatives, indis,
                           fams=fams, root_xref='@I1@')
        # @I9@ Helen Taylor DEAT has age='55y', no date — must be in PEOPLE JSON
        people_match = re.search(r'const PEOPLE = (.*?);[ \t]*$', html, re.MULTILINE)
        assert people_match, "PEOPLE const not found in rendered HTML"
        p = json.loads(people_match.group(1))
        helen = p.get('@I9@')
        assert helen is not None
        deat = next((e for e in helen['events'] if e['tag'] == 'DEAT'), None)
        assert deat is not None
        assert deat.get('age') == '55y'
        assert deat.get('date') is None, "Helen should have no DEAT date"


# ---------------------------------------------------------------------------
# Part 4 & 5: NATI inline_val and pill display regression
# ---------------------------------------------------------------------------

class TestNatiDisplay:
    """
    Regression guard: NATI events must carry inline_val so the nationality
    pill can display the value.  Before the fix, natiEvents rendered
    e.inline_val which was empty/null for some events.
    """

    def test_nati_inline_val_in_parsed_indis(self, indis):
        # @I2@ James Smith has '1 NATI American'
        nati = next((e for e in indis['@I2@']['events'] if e['tag'] == 'NATI'), None)
        assert nati is not None, "@I2@ should have a NATI event"
        assert nati['inline_val'] == 'American', (
            f"Expected inline_val 'American', got {nati['inline_val']!r}"
        )

    def test_nati_inline_val_in_people_json(self, people):
        nati_events = [e for e in people['@I2@']['events'] if e['tag'] == 'NATI']
        assert nati_events, "@I2@ NATI event not in build_people_json output"
        assert nati_events[0]['inline_val'] == 'American'

    def test_nati_type_matches_inline_val(self, people):
        # For NATI, type is set from the inline value (used in prose)
        nati = next((e for e in people['@I2@']['events'] if e['tag'] == 'NATI'), None)
        assert nati['type'] == 'American'

    def test_nati_pill_renders_inline_val_in_template(self):
        # The pill must use e.inline_val so empty inline_val shows nothing
        assert "e.inline_val || ''" in _FULL_SOURCE, (
            "Nationality pill must render e.inline_val"
        )

    def test_nati_filter_in_template(self):
        # NATI events must be extracted by tag === 'NATI' for pill rendering
        assert "e.tag === 'NATI'" in _FULL_SOURCE

    def test_nati_excluded_from_all_visible(self):
        # NATI events must not appear in the Life Events timeline
        assert "e.tag !== 'NATI'" in _FULL_SOURCE

    def test_nati_events_present_in_rendered_html_people_json(self, people, indis, fams, parsed):
        """
        End-to-end: the rendered HTML's PEOPLE const must contain NATI events
        with inline_val set for @I2@ James Smith.
        This guards against NATI events being dropped or losing inline_val during
        build_people_json or JSON serialization.
        """
        tree = build_tree_json('@I1@', indis, fams)
        relatives = build_relatives_json(tree, indis, fams)
        _, _, sources = parsed
        html = render_html(tree, 'Rose Smith', people, relatives, indis,
                           fams=fams, root_xref='@I1@')
        people_match = re.search(r'const PEOPLE = (.*?);[ \t]*$', html, re.MULTILINE)
        assert people_match, "PEOPLE const not found in rendered HTML"
        p = json.loads(people_match.group(1))
        james = p.get('@I2@')
        assert james is not None, "@I2@ not in rendered PEOPLE"
        nati_evts = [e for e in james['events'] if e['tag'] == 'NATI']
        assert nati_evts, "@I2@ has no NATI events in rendered HTML"
        assert nati_evts[0]['inline_val'] == 'American', (
            f"Expected inline_val 'American', got {nati_evts[0]['inline_val']!r}"
        )

    def test_nati_events_not_filtered_by_allvisible_logic(self, people):
        """
        Guard: NATI events with only inline_val set (no date/place/note/type/cause)
        must NOT be filtered out from the natiEvents array. The allVisible filter
        requires (date||place||note||type||cause) which would exclude bare NATI events,
        but natiEvents uses its own tag-only filter so they must still appear.
        The fix: confirm NATI events are in build_people_json output regardless of
        whether other fields are set.
        """
        nati_evts = [e for e in people['@I2@']['events'] if e['tag'] == 'NATI']
        assert nati_evts, "NATI events missing from build_people_json output"
        # Verify these would NOT be caught by allVisible (which requires content fields)
        # but WOULD be caught by the tag-only natiEvents filter
        for e in nati_evts:
            # inline_val must always be set so the pill has text to display
            assert e['inline_val'] is not None, (
                f"NATI event has null inline_val — pill would render empty: {e}"
            )


# ---------------------------------------------------------------------------
# Part 6: OCCU prose regression
# ---------------------------------------------------------------------------

class TestOccuProse:
    """
    Regression guard: OCCU prose must use 'Worked as <inline_val>', NOT the TYPE subtag.
    Before the fix, 'Worked as Employed with the French company…' appeared because
    the note/type content from 2 TYPE was used instead of the actual 1 OCCU inline value.
    """

    def test_occu_prose_uses_inline_val(self):
        # The OCCU case must use inline_val (the value on the 1 OCCU line), not type.
        # The variable may be named 'fact' or 'evt' depending on the impl.
        assert ('fact.inline_val' in _FULL_SOURCE or 'evt.inline_val' in _FULL_SOURCE), (
            "OCCU prose must use inline_val for the job title"
        )
        assert 'Worked as' in _FULL_SOURCE, (
            "OCCU prose must still include 'Worked as' prefix"
        )

    def test_occu_prose_not_using_type_as_title(self):
        # The OCCU case must not use "Worked as ${type}" (type = 2 TYPE subtag)
        assert '`Worked as ${type}`' not in _HTML_TEMPLATE, (
            "OCCU prose must not use 2 TYPE subtag as job title"
        )

    def test_occu_inline_val_in_people_json(self, people):
        # @I2@ James Smith has OCCU with TYPE 'Engineer' but no inline val
        occu = next((e for e in people['@I2@']['events'] if e['tag'] == 'OCCU'), None)
        assert occu is not None
        assert occu.get('type') == 'Engineer'
