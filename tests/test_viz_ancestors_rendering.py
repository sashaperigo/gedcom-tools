"""
Regression tests for viz_ancestors.py rendering pipeline.

These tests target the class of bugs that are invisible in Python but break
the browser UI — wrong JS variable names, malformed HTML attributes, missing
data fields, and bad JSON structure.  Each test documents the specific bug it
guards against so future readers understand why it exists.

Bug history this file covers:
  B1  TREE vs currentTree — expandNode / hasHiddenParents / relatives-toggle
      all used the static TREE lookup instead of currentTree, causing wrong
      ancestor keys to be added to visibleKeys after changeRoot().
  B2  RELATIVES keyed by ahnentafel int, not xref — after changeRoot() the
      old numeric key pointed to the wrong person's data.
  B3  Missing connector from root to its parents — !expandedRelatives.has(k)
      guard skipped drawing when no siblings were expanded; root is always in
      expandedRelatives so the line was never drawn.
  B4  onclick double-quote injection — JSON.stringify(xref) embeds double
      quotes inside onclick="...", breaking HTML attribute parsing so the
      click handler was silently dropped.

Expansion-button logic (TestExpansionButtonLogic):
  These tests mirror the JS functions hasHiddenParents(), hasVisibleParents(),
  and the relatives-toggle guard in Python so we can exercise every branch
  without a browser.  The mirror functions are defined locally and kept
  intentionally simple — if the JS implementations diverge from them the
  tests will tell us.
  B5  PARENTS/ROOT_XREF missing — changeRoot() and buildAhnentafel() in JS
      need these to rebuild the tree for any root person.
  B6  spouse_xref missing from MARR events — the marriage card click handler
      reads evt.spouse_xref; without it no marriage link was clickable.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from viz_ancestors import (
    _HTML_TEMPLATE,
    build_people_json,
    build_relatives_json,
    build_tree_json,
    parse_gedcom,
    render_html,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'


# ---------------------------------------------------------------------------
# Shared fixture data
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
def tree(indis, fams):
    return build_tree_json('@I1@', indis, fams)


@pytest.fixture(scope='module')
def people(tree, indis, parsed):
    _, fams, sources = parsed
    return build_people_json(set(indis.keys()), indis, fams, sources)


@pytest.fixture(scope='module')
def relatives(tree, indis, fams):
    return build_relatives_json(tree, indis, fams)


@pytest.fixture(scope='module')
def html(tree, people, relatives, indis, fams):
    return render_html(tree, 'Rose Smith', people, relatives, indis,
                       fams=fams, root_xref='@I1@')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_js_const(html_text: str, name: str):
    """Return the parsed JSON value assigned to a JS const in the HTML."""
    pattern = rf'const {re.escape(name)} = (.*?);[ \t]*$'
    m = re.search(pattern, html_text, re.MULTILINE)
    if not m:
        return None
    return json.loads(m.group(1))


class OnclickCollector(HTMLParser):
    """Collect all onclick attribute values from an HTML document."""
    def __init__(self):
        super().__init__()
        self.onclicks: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, val in attrs:
            if name == 'onclick' and val:
                self.onclicks.append(val)


# ---------------------------------------------------------------------------
# B1  Template antipatterns — wrong variable references
# ---------------------------------------------------------------------------

class TestTemplateAntipatterns:
    """
    Validate the raw _HTML_TEMPLATE string for patterns that compile fine in
    Python but produce wrong runtime behaviour in the browser (B1, B2, B3).
    These tests check the *template*, not any generated output, so they catch
    regressions without needing to render a GEDCOM.
    """

    def test_no_in_TREE_for_expand(self):
        """
        B1: (2 * k) in TREE must not appear — expandNode/hasHiddenParents
        must use currentTree so they work after changeRoot().
        """
        assert '2 * k) in TREE' not in _HTML_TEMPLATE, (
            "Found '2 * k) in TREE' — should be 'in currentTree' "
            "(breaks expand button after changeRoot)"
        )

    def test_no_2k1_in_TREE(self):
        """B1: same guard for the mother-side parent key."""
        assert '2 * k + 1) in TREE' not in _HTML_TEMPLATE, (
            "Found '2 * k + 1) in TREE' — should be 'in currentTree'"
        )

    def test_no_relatives_string_k_lookup(self):
        """
        B2: RELATIVES[String(k)] must not appear — after re-keying RELATIVES by
        xref the correct lookup is RELATIVES[currentTree[k]].
        """
        assert 'RELATIVES[String(k)]' not in _HTML_TEMPLATE, (
            "RELATIVES looked up by ahnentafel key string — must use "
            "RELATIVES[currentTree[k]] so it works after changeRoot()"
        )

    def test_expandNode_uses_currentTree(self):
        """B1: expandNode must check currentTree, not the static TREE."""
        assert 'function expandNode' in _HTML_TEMPLATE
        # Find the function body and confirm it references currentTree
        fn_start = _HTML_TEMPLATE.index('function expandNode')
        fn_body = _HTML_TEMPLATE[fn_start:fn_start + 200]
        assert 'currentTree' in fn_body, (
            "expandNode does not reference currentTree — "
            "parent expansion broken after changeRoot()"
        )

    def test_hasHiddenParents_uses_currentTree(self):
        """B1: hasHiddenParents must check currentTree."""
        fn_start = _HTML_TEMPLATE.index('function hasHiddenParents')
        fn_body = _HTML_TEMPLATE[fn_start:fn_start + 200]
        assert 'currentTree' in fn_body, (
            "hasHiddenParents does not reference currentTree — "
            "expand button broken after changeRoot()"
        )

    def test_connector_drawn_unconditionally_for_both_parents(self):
        """
        B3: The connector from a parent pair to the child must be drawn
        regardless of expandedRelatives.  The old guard
        'if (!expandedRelatives.has(k))' blocked drawing for the root node
        (always in expandedRelatives) when it had both parents visible.
        """
        assert 'if (!expandedRelatives.has(k))' not in _HTML_TEMPLATE, (
            "expandedRelatives.has(k) guard still present — connector from "
            "both-parent nodes to child is skipped for the root person"
        )

    def test_currentTree_declared(self):
        """currentTree must be declared as a mutable variable."""
        assert 'let currentTree' in _HTML_TEMPLATE

    def test_parents_json_placeholder_present(self):
        """PARENTS_JSON placeholder must exist so it gets substituted."""
        assert '__PARENTS_JSON__' in _HTML_TEMPLATE

    def test_root_xref_placeholder_present(self):
        """ROOT_XREF_JSON placeholder must exist."""
        assert '__ROOT_XREF_JSON__' in _HTML_TEMPLATE


# ---------------------------------------------------------------------------
# B4  HTML attribute safety — onclick double-quote injection
# ---------------------------------------------------------------------------

class TestHtmlAttributeSafety:
    """
    B4: Dynamically generated onclick attributes must not contain raw double
    quotes.  JSON.stringify(xref) produces "\"@I1@\"" which, when embedded
    directly in onclick="changeRoot(\"@I1@\")", closes the HTML attribute at
    the first inner quote — silently dropping the handler.
    """

    def test_no_raw_double_quotes_in_onclick_attrs(self, html):
        collector = OnclickCollector()
        collector.feed(html)
        for val in collector.onclicks:
            assert '"' not in val, (
                f'Raw double quote in onclick attribute value: {val!r}\n'
                'Use data-* attribute + this.dataset.* to avoid injection.'
            )

    def test_marriage_card_uses_data_attribute(self, html):
        """
        B4 (specific form): marriage cards that call changeRoot must carry the
        xref in a data-* attribute read at runtime, not inline JSON.
        If there is any onclick referencing changeRoot it must not contain a
        raw xref literal in double quotes.
        """
        for m in re.finditer(r'onclick="([^"]*changeRoot[^"]*)"', html):
            assert '"' not in m.group(1), (
                f'Double-quote injection in changeRoot onclick: {m.group(0)!r}'
            )


# ---------------------------------------------------------------------------
# B5  PARENTS and ROOT_XREF present in rendered HTML
# ---------------------------------------------------------------------------

class TestParentsJson:
    """
    B5: The JS changeRoot() / buildAhnentafel() functions need PARENTS and
    ROOT_XREF to rebuild the tree for any starting person.
    """

    def test_parents_const_present(self, html):
        assert 'const PARENTS' in html

    def test_root_xref_const_present(self, html):
        assert 'const ROOT_XREF' in html

    def test_root_xref_value(self, html):
        root_xref = extract_js_const(html, 'ROOT_XREF')
        assert root_xref == '@I1@'

    def test_parents_covers_all_individuals(self, html, indis):
        """Every individual in indis must have an entry in PARENTS."""
        parents = extract_js_const(html, 'PARENTS')
        assert parents is not None, 'PARENTS const not found or not parseable'
        for xref in indis:
            assert xref in parents, f'{xref} missing from PARENTS JSON'

    def test_parents_values_are_two_element_lists(self, html):
        """Each PARENTS entry must be [father_or_null, mother_or_null]."""
        parents = extract_js_const(html, 'PARENTS')
        for xref, pair in parents.items():
            assert isinstance(pair, list), \
                f'PARENTS[{xref!r}] is {type(pair).__name__}, expected list'
            assert len(pair) == 2, \
                f'PARENTS[{xref!r}] has {len(pair)} elements, expected 2'
            father, mother = pair
            assert father is None or isinstance(father, str), \
                f'PARENTS[{xref!r}][0] must be str or null'
            assert mother is None or isinstance(mother, str), \
                f'PARENTS[{xref!r}][1] must be str or null'

    def test_parents_known_family(self, html):
        """Rose (@I1@) has father @I2@ and mother @I3@ per @F1@."""
        parents = extract_js_const(html, 'PARENTS')
        assert parents['@I1@'] == ['@I2@', '@I3@']

    def test_parents_single_parent(self, html):
        """John Jones (@I6@) has only a father (Thomas @I10@), no mother."""
        parents = extract_js_const(html, 'PARENTS')
        father, mother = parents['@I6@']
        assert father == '@I10@'
        assert mother is None

    def test_parents_no_parents(self, html):
        """Patrick Smith (@I4@) has no FAMC → [null, null]."""
        parents = extract_js_const(html, 'PARENTS')
        assert parents['@I4@'] == [None, None]


# ---------------------------------------------------------------------------
# B2  RELATIVES keyed by xref, not ahnentafel int
# ---------------------------------------------------------------------------

class TestRelativesJsonStructure:
    """
    B2: RELATIVES must be keyed by xref strings so that after changeRoot() the
    lookup RELATIVES[currentTree[k]] resolves correctly regardless of which
    person is the root.

    The old bug: RELATIVES was keyed by ahnentafel int (e.g. "1"), so after
    changeRoot() RELATIVES["1"] still pointed to Sasha's siblings, not the new
    root's siblings.
    """

    def test_relatives_const_present(self, html):
        assert 'const RELATIVES' in html

    def test_relatives_keys_are_xref_strings(self, html):
        """All keys in RELATIVES must start with '@' (xref format)."""
        relatives = extract_js_const(html, 'RELATIVES')
        assert relatives is not None, 'RELATIVES const not found or not parseable'
        for key in relatives:
            assert key.startswith('@'), (
                f'RELATIVES key {key!r} is not an xref — '
                'RELATIVES must be keyed by xref so changeRoot() works'
            )

    def test_relatives_keys_are_not_integers(self, html):
        """Keys must not be bare integers (the old ahnentafel format)."""
        relatives = extract_js_const(html, 'RELATIVES')
        for key in relatives:
            assert not key.isdigit(), (
                f'RELATIVES key {key!r} is a plain integer — '
                'this breaks sibling display after changeRoot()'
            )

    def test_relatives_root_has_siblings_and_spouse(self, html):
        """
        Rose (@I1@) has Alice Smith (@I11@) as a sibling and Mark Davis
        (@I12@) as a spouse — both must appear under the xref key '@I1@'.
        """
        relatives = extract_js_const(html, 'RELATIVES')
        assert '@I1@' in relatives, 'Root xref @I1@ missing from RELATIVES'
        assert '@I11@' in relatives['@I1@']['siblings']
        assert '@I12@' in relatives['@I1@']['spouses']


# ---------------------------------------------------------------------------
# B6  MARR events carry spouse_xref
# ---------------------------------------------------------------------------

class TestMarriageEventSpouseXref:
    """
    B6: The marriage card "Married X" link calls changeRoot(this.dataset.spouseXref).
    The dataset attribute is populated from evt.spouse_xref in PEOPLE.
    Without spouse_xref the onclick is not rendered and the link is dead.
    """

    def test_marr_events_have_spouse_xref_field(self, people):
        """
        Every MARR event that has a named spouse must also carry spouse_xref.
        """
        for xref, person in people.items():
            for evt in person.get('events', []):
                if evt.get('tag') == 'MARR' and evt.get('spouse'):
                    assert 'spouse_xref' in evt, (
                        f'MARR event for {xref} names spouse '
                        f'"{evt["spouse"]}" but has no spouse_xref field — '
                        'the marriage link will not be clickable'
                    )

    def test_marr_spouse_xref_is_valid_xref_or_none(self, people, indis):
        """spouse_xref must be either None or a valid individual xref."""
        for xref, person in people.items():
            for evt in person.get('events', []):
                if evt.get('tag') == 'MARR':
                    sp = evt.get('spouse_xref')
                    if sp is not None:
                        assert sp in indis, (
                            f'MARR event for {xref} has spouse_xref={sp!r} '
                            'which is not a known individual'
                        )

    def test_rose_marr_spouse_xref_is_mark(self, people):
        """Rose (@I1@) is married to Mark Davis (@I12@) per @F5@."""
        rose_marr = [e for e in people['@I1@']['events'] if e['tag'] == 'MARR']
        assert rose_marr, '@I1@ has no MARR events despite @F5@'
        assert rose_marr[0]['spouse_xref'] == '@I12@'

    def test_spouse_xref_reciprocal(self, people):
        """
        Mark (@I12@) should also have a MARR event pointing back to Rose.
        """
        mark_marr = [e for e in people.get('@I12@', {}).get('events', [])
                     if e['tag'] == 'MARR']
        if mark_marr:  # Mark is in people (he is, since we include all indis)
            assert mark_marr[0]['spouse_xref'] == '@I1@'


# ---------------------------------------------------------------------------
# Expansion-button logic
# ---------------------------------------------------------------------------
#
# Python mirrors of the three JS predicates that control button visibility.
# Keeping these functions here (rather than importing them from JS) means the
# tests remain runnable without Node.  If the JS implementations change,
# update both the template and these mirrors.
#
#   hasHiddenParents(k)  →  show ▲ expand button
#   hasVisibleParents(k) →  show ▼ collapse button
#   has_relatives_toggle(k, tree, relatives)  →  show ◄/► sibling/spouse button

def _has_hidden_parents(k: int, tree: dict, visible: set) -> bool:
    """Mirror of JS hasHiddenParents(k): ▲ button should appear."""
    fk, mk = 2 * k, 2 * k + 1
    return (fk in tree or mk in tree) and fk not in visible and mk not in visible


def _has_visible_parents(k: int, visible: set) -> bool:
    """Mirror of JS hasVisibleParents(k): ▼ button should appear."""
    return 2 * k in visible or (2 * k + 1) in visible


def _has_relatives_toggle(k: int, tree: dict, relatives: dict) -> bool:
    """
    Mirror of the JS relatives-button guard: k != 1 and the person has an
    entry in RELATIVES (i.e. has siblings or spouses to display).
    `relatives` here is the Python dict from build_relatives_json (xref keys).
    """
    xref = tree.get(k)
    return k != 1 and xref is not None and xref in relatives


class TestExpansionButtonLogic:
    """
    Unit tests for hasHiddenParents / hasVisibleParents / relatives-toggle
    using the fixture tree and relatives data.

    Fixture tree (Rose @I1@ as root):
      key 1  = @I1@  Rose          parents: @I2@(2), @I3@(3)
      key 2  = @I2@  James         parents: @I4@(4), @I5@(5)
      key 3  = @I3@  Clara         parents: @I6@(6), @I7@(7)
      key 4  = @I4@  Patrick       no parents in tree (8,9 absent)
      key 5  = @I5@  Mary          no parents in tree (10,11 absent)
      key 6  = @I6@  John          father: @I10@(12); mother absent (13 absent)
      key 7  = @I7@  Jane          parents: @I8@(14), @I9@(15)
      key 12 = @I10@ Thomas        no parents in tree (24,25 absent)
      key 14 = @I8@  William       no parents in tree (28,29 absent)
      key 15 = @I9@  Helen         no parents in tree (30,31 absent)
    """

    @pytest.fixture(scope='class')
    def _tree(self, indis, fams):
        return build_tree_json('@I1@', indis, fams)

    @pytest.fixture(scope='class')
    def _relatives(self, _tree, indis, fams):
        return build_relatives_json(_tree, indis, fams)

    # ── hasHiddenParents ────────────────────────────────────────────────────

    def test_expand_button_shown_when_parents_in_tree_not_visible(self, _tree):
        """Key 1 (Rose): parents 2 & 3 are in tree but not yet visible → ▲."""
        visible = {1}
        assert _has_hidden_parents(1, _tree, visible)

    def test_expand_button_shown_for_intermediate_node(self, _tree):
        """Key 2 (James): parents 4 & 5 are in tree, not visible → ▲."""
        visible = {1, 2, 3}
        assert _has_hidden_parents(2, _tree, visible)

    def test_expand_button_shown_with_only_one_parent_in_tree(self, _tree):
        """Key 6 (John): only father (12) is in tree; mother (13) absent.
        hasHiddenParents is OR-based, so one parent is enough to show ▲."""
        visible = {1, 2, 3, 6, 7}
        assert _has_hidden_parents(6, _tree, visible)

    def test_expand_button_hidden_when_no_parents_in_tree(self, _tree):
        """Key 4 (Patrick): keys 8 & 9 absent from tree → no ▲."""
        visible = {1, 2, 3, 4, 5}
        assert not _has_hidden_parents(4, _tree, visible)

    def test_expand_button_hidden_when_parents_already_visible(self, _tree):
        """Key 1 (Rose): once parents 2 & 3 are added to visible → no ▲."""
        visible = {1, 2, 3}
        assert not _has_hidden_parents(1, _tree, visible)

    def test_expand_button_hidden_when_one_parent_visible(self, _tree):
        """
        If either parent is already visible, hasHiddenParents returns False
        (the AND condition requires *both* absent).  Prevents duplicate ▲.
        """
        visible = {1, 2, 3, 6, 7, 12}   # key 12 = John's father, now visible
        assert not _has_hidden_parents(6, _tree, visible)

    def test_expand_button_hidden_for_leaf_nodes(self, _tree):
        """Keys 14 & 15 (William, Helen): no parents in tree → no ▲."""
        visible = {1, 2, 3, 6, 7, 14, 15}
        assert not _has_hidden_parents(14, _tree, visible)
        assert not _has_hidden_parents(15, _tree, visible)

    # ── hasVisibleParents ───────────────────────────────────────────────────

    def test_collapse_button_shown_when_father_visible(self, _tree):
        """Key 1 after father (2) expanded → ▼ visible."""
        visible = {1, 2}
        assert _has_visible_parents(1, visible)

    def test_collapse_button_shown_when_mother_visible(self, _tree):
        """Key 1 after only mother (3) visible → ▼ visible."""
        visible = {1, 3}
        assert _has_visible_parents(1, visible)

    def test_collapse_button_shown_when_both_parents_visible(self, _tree):
        visible = {1, 2, 3}
        assert _has_visible_parents(1, visible)

    def test_collapse_button_hidden_when_no_parents_visible(self, _tree):
        visible = {1}
        assert not _has_visible_parents(1, visible)

    def test_exactly_one_button_per_node_with_hidden_parents(self, _tree):
        """
        Invariant: for any node, hasHiddenParents and hasVisibleParents are
        mutually exclusive (never both True at the same time).
        """
        visible = {1, 2, 3, 4, 5}   # gens 0-2 partially expanded
        for k in list(_tree.keys()):
            hidden  = _has_hidden_parents(k, _tree, visible)
            visible_p = _has_visible_parents(k, visible)
            assert not (hidden and visible_p), (
                f'Key {k}: both hasHiddenParents and hasVisibleParents True '
                'simultaneously — two conflicting buttons would appear'
            )

    def test_no_button_for_nodes_with_no_parents_in_tree(self, _tree):
        """Nodes at the top of the known tree show neither ▲ nor ▼."""
        no_parents = [k for k in _tree if 2 * k not in _tree and (2 * k + 1) not in _tree]
        visible = set(_tree.keys())  # everything expanded
        for k in no_parents:
            assert not _has_hidden_parents(k, _tree, visible)
            assert not _has_visible_parents(k, visible)

    # ── Relatives toggle ────────────────────────────────────────────────────

    def test_relatives_toggle_hidden_for_root(self, _tree, _relatives):
        """Key 1 (root) never gets a ◄/► button, even if it has siblings."""
        assert not _has_relatives_toggle(1, _tree, _relatives)

    def test_relatives_toggle_shown_for_ancestor_with_siblings(self, _tree, _relatives):
        """Key 2 (James): has sibling Robert → toggle shown."""
        assert _has_relatives_toggle(2, _tree, _relatives)

    def test_relatives_toggle_hidden_for_ancestor_without_relatives(self, _tree, _relatives):
        """
        Key 12 (Thomas Jones @I10@): no FAMC so no siblings, and @F6@ has no
        WIFE record so no spouse → no entry in relatives dict → no toggle.
        """
        assert not _has_relatives_toggle(12, _tree, _relatives)

    def test_relatives_toggle_only_for_tree_members(self, _tree, _relatives):
        """
        Expansion toggles are only shown for nodes in the current tree.
        Non-tree xrefs in RELATIVES don't produce toggles (JS guard: k != 1 and xref in RELATIVES).
        This test verifies tree members with relatives get a toggle, and non-members don't.
        """
        tree_xrefs = set(_tree.values())
        # Every tree member that has relatives should have a toggle (except root, key 1)
        for k, xref in _tree.items():
            if k == 1:
                continue
            if xref in _relatives:
                assert _has_relatives_toggle(k, _tree, _relatives), (
                    f'Tree key {k} ({xref}) has relatives but no toggle'
                )

    def test_all_relatives_entries_have_required_fields(self, _relatives):
        """Every RELATIVES entry must have siblings and spouses (always present).
        sib_spouses is optional — only included when non-empty."""
        for k, entry in _relatives.items():
            for field in ('siblings', 'spouses'):
                assert field in entry, (
                    f'RELATIVES[{k}] missing field {field!r}'
                )
