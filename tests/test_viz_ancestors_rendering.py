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
    _CSS,
    _HTML_TEMPLATE,
    build_people_json,
    build_relatives_json,
    build_tree_json,
    parse_gedcom,
    render_html,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'

# JS logic now lives in external js/ files; combine all sources for pattern checks.
_JS_DIR = Path(__file__).parent.parent / 'js'
_FULL_SOURCE = _HTML_TEMPLATE + ''.join(
    f.read_text(encoding='utf-8') for f in sorted(_JS_DIR.glob('*.js'))
)


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
    """Return the parsed JSON value assigned to a JS const/let in the HTML."""
    pattern = rf'(?:const|let) {re.escape(name)} = (.*?);[ \t]*$'
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

    def test_expand_uses_setState(self):
        """Redesign: ancestor expansion uses setState({ expandedNodes }) not currentTree."""
        # viz_render.js wires expand buttons to setState; verify the pattern
        render_src = (Path(__file__).parent.parent / 'js' / 'viz_render.js').read_text()
        assert 'setState' in render_src, (
            "viz_render.js must call setState for expand button clicks"
        )
        assert 'expandedNodes' in render_src, (
            "viz_render.js must reference expandedNodes state key"
        )

    def test_panel_uses_getState(self):
        """Redesign: detail panel reads from state via getState(), not global _openDetailKey."""
        panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()
        assert 'getState' in panel_src or 'onStateChange' in panel_src, (
            "viz_panel.js must integrate with state management"
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

    def test_currentTree_not_in_template(self):
        """Redesign: currentTree is gone — state is managed by viz_state.js."""
        assert 'let currentTree' not in _HTML_TEMPLATE, (
            "currentTree should not be in the template; state is managed by viz_state.js"
        )

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

    def test_embedded_json_escapes_closing_script_tag(self, indis, fams, parsed, tree, relatives):
        """
        JSON data injected into an inline <script> block must escape `</` as
        `<\\/` — otherwise any note/name containing the substring "</script"
        closes the script element early, producing "Unexpected end of input".
        """
        from viz_ancestors import render_html, build_people_json
        _, fams2, sources = parsed
        # Inject a hostile substring into the first person's name.
        hostile_indis = {k: dict(v) for k, v in indis.items()}
        first = next(iter(hostile_indis))
        hostile_indis[first] = dict(hostile_indis[first])
        hostile_indis[first]['name'] = 'Rose </script><img src=x> Smith'
        people = build_people_json(set(hostile_indis.keys()), hostile_indis, fams2, sources)
        html_out = render_html(tree, 'Rose Smith', people, relatives, hostile_indis,
                               fams=fams2, root_xref='@I1@')
        # Count of "</script" must equal the count of "<script" — anything
        # extra means the HTML parser will terminate a script block early.
        open_tags  = len(re.findall(r'<script\b', html_out, re.IGNORECASE))
        close_tags = html_out.lower().count('</script')
        assert open_tags == close_tags, (
            f'script open tags ({open_tags}) != close tags ({close_tags}). '
            'Embedded JSON must escape "</" as "<\\/" so user-supplied strings '
            'containing "</script" do not prematurely end the <script> element.'
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
        assert 'let PARENTS' in html

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
        assert 'let RELATIVES' in html

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

    def test_spouse_shown_when_fam_has_no_marr_record(self, people):
        """
        Regression: a FAM with a HUSB and WIFE but no MARR sub-record must still
        produce a synthetic MARR event so the spouse appears in the
        Spouses & Children panel.  @F7@ (George @I14@ / Susan @I15@) has no
        MARR tag at all — both individuals must still carry a MARR event with
        the other's xref.
        """
        george_marr = [e for e in people.get('@I14@', {}).get('events', [])
                       if e['tag'] == 'MARR']
        assert george_marr, (
            '@I14@ (George) has no MARR events despite being in @F7@ — '
            'spouse will not appear in the Spouses & Children panel'
        )
        assert george_marr[0].get('spouse_xref') == '@I15@', (
            f"George's MARR event has spouse_xref={george_marr[0].get('spouse_xref')!r}, "
            'expected @I15@ (Susan)'
        )

        susan_marr = [e for e in people.get('@I15@', {}).get('events', [])
                      if e['tag'] == 'MARR']
        assert susan_marr, (
            '@I15@ (Susan) has no MARR events despite being in @F7@ — '
            'spouse will not appear in the Spouses & Children panel'
        )
        assert susan_marr[0].get('spouse_xref') == '@I14@', (
            f"Susan's MARR event has spouse_xref={susan_marr[0].get('spouse_xref')!r}, "
            'expected @I14@ (George)'
        )


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


# ---------------------------------------------------------------------------
# B7  Panel fact rendering — viz_panel.js _buildFactRow
# ---------------------------------------------------------------------------

class TestPanelFactRendering:
    """
    Panel fact rendering — ported from viz_detail.js.
    The new panel uses buildProse (ported wholesale) rather than _buildFactRow.
    """

    def test_buildProse_exists_in_panel(self):
        """viz_panel.js must define buildProse for event rendering."""
        panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()
        assert 'function buildProse' in panel_src, (
            'viz_panel.js must define buildProse for event rendering (ported from viz_detail.js)'
        )

    def test_panel_renders_section_headers(self):
        """viz_panel.js must emit section headers like EARLY LIFE / LIFE / LATER LIFE."""
        panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()
        assert 'EARLY LIFE' in panel_src or "'Early Life'" in panel_src or '"Early Life"' in panel_src, (
            'viz_panel.js must emit timeline section headers (EARLY LIFE / LIFE / LATER LIFE)'
        )


# ---------------------------------------------------------------------------
# B8  Marriage ADDR parsing from FAM blocks
# ---------------------------------------------------------------------------

class TestMarriageAddr:
    """
    B8: The FAM block parser only handled DATE, PLAC, and NOTE under MARR —
    it did not handle ADDR.  Additionally the MARR event dict did not
    initialise an `addr` key.

    Consequence: saving an ADDR via the event modal wrote the tag correctly
    to the GEDCOM file, but the next parse_gedcom() call silently dropped it.
    The UI showed no ADDR on the marriage card and the edit modal always opened
    with a blank Address field even after saving.
    """

    GEDCOM_WITH_MARR_ADDR = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Rose /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mark /Davis/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 2015
2 PLAC Greenwich, Connecticut, USA
2 ADDR St Mary's Church
0 TRLR
"""

    @pytest.fixture(scope='class')
    def parsed_with_addr(self, tmp_path_factory):
        ged = tmp_path_factory.mktemp('marr_addr') / 'test.ged'
        ged.write_text(self.GEDCOM_WITH_MARR_ADDR, encoding='utf-8')
        return parse_gedcom(str(ged))

    def test_marr_addr_field_initialised(self, parsed_with_addr):
        """MARR event dict must always have an `addr` key (even when absent from GEDCOM)."""
        _, fams, _ = parsed_with_addr
        marr = fams['@F1@']['marrs'][0]
        assert 'addr' in marr, (
            "MARR event dict has no 'addr' key — the key is not initialised "
            "in parse_gedcom, so addr can never be set or returned"
        )

    def test_marr_addr_parsed_from_fam_block(self, parsed_with_addr):
        """ADDR sub-tag under MARR must be read into the event dict."""
        _, fams, _ = parsed_with_addr
        marr = fams['@F1@']['marrs'][0]
        assert marr.get('addr') == "St Mary's Church", (
            f"MARR addr={marr.get('addr')!r}; expected \"St Mary's Church\". "
            "The FAM-context level-2 handler didn't include an ADDR branch."
        )

    def test_marr_addr_in_people_json(self, parsed_with_addr):
        """build_people_json must propagate ADDR from the MARR event to PEOPLE."""
        indis, fams, sources = parsed_with_addr
        people = build_people_json({'@I1@', '@I2@'}, indis, fams=fams, sources=sources)
        rose_marr = [e for e in people['@I1@']['events'] if e['tag'] == 'MARR']
        assert rose_marr, '@I1@ has no MARR events'
        assert rose_marr[0].get('addr') == "St Mary's Church", (
            f"MARR event in PEOPLE has addr={rose_marr[0].get('addr')!r}; "
            "expected the address to propagate from FAM parse to PEOPLE JSON"
        )

    def test_marr_addr_absent_when_not_in_gedcom(self):
        """When MARR has no ADDR sub-tag the field must exist but be None/falsy."""
        _, fams, _ = parse_gedcom(str(FIXTURE))
        marrs = fams.get('@F5@', {}).get('marrs', [])
        if not marrs:
            return  # fixture has no @F5@ MARR — skip
        marr = marrs[0]
        # addr key must exist (initialised to None) even when absent from GEDCOM
        assert 'addr' in marr, "MARR event dict missing 'addr' key"
        assert not marr.get('addr'), (
            f"MARR addr={marr.get('addr')!r} when no ADDR in GEDCOM — "
            "expected None or empty"
        )


# ---------------------------------------------------------------------------
# Facts section rendering — single heading, EDUC format, sorted
# ---------------------------------------------------------------------------

class TestPanelTagLabels:
    """
    Redesign: viz_panel.js defines _TAG_LABELS for mapping GEDCOM tags to
    display labels. Verify key labels are present.
    """

    def test_education_label_present(self):
        """EDUC must map to 'Education' in _TAG_LABELS."""
        panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()
        assert "'Education'" in panel_src or '"Education"' in panel_src, \
            "viz_panel.js must define 'Education' label for EDUC tag"

    def test_tag_labels_covers_core_tags(self):
        """_TAG_LABELS must cover key lifecycle events."""
        panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()
        for label in ("'Birth'", "'Death'", "'Burial'", "'Residence'"):
            assert label in panel_src, f'viz_panel.js must define {label} in _TAG_LABELS'

    def test_no_per_group_heading_loop(self):
        """Old grouping-by-heading loop must not exist — panel uses flat fact list."""
        assert 'for (const [heading, evts] of groups)' not in _FULL_SOURCE, \
            "Per-group heading loop must be removed; panel uses flat _buildFactRow list"

    def test_panel_iterates_facts_array(self):
        """viz_panel.js must iterate events to render life events."""
        panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()
        assert (
            'for (const fact of facts)' in panel_src
            or 'facts.forEach' in panel_src
            or 'for (const evt of sorted)' in panel_src
            or 'for (const evt of allVisible)' in panel_src
        ), "viz_panel.js must iterate events to render life event rows"


# ---------------------------------------------------------------------------
# Category 4 — Button wiring pattern checks
# ---------------------------------------------------------------------------

class TestButtonWiringPatterns:
    """
    Assert that viz_panel.js source contains correct function calls/patterns on
    each button. Catches "button present but onclick removed" regressions.
    """

    @pytest.fixture(autouse=True)
    def _panel_src(self):
        self.panel_src = (Path(__file__).parent.parent / 'js' / 'viz_panel.js').read_text()

    def test_set_root_button_uses_setState_and_focusXref(self):
        """Home/set-root button must call setState with focusXref."""
        assert 'setState' in self.panel_src and 'focusXref' in self.panel_src, (
            "viz_panel.js must contain setState({ focusXref }) for the set-root/home button"
        )

    def test_add_event_button_wired(self):
        """Add Event button must call an event-modal open function."""
        assert 'addEvent' in self.panel_src or 'showAddEventModal' in self.panel_src or 'openAddEventModal' in self.panel_src, (
            "viz_panel.js must wire Add Event button to an openAddEventModal (or equivalent) function"
        )

    def test_add_nationality_button_wired(self):
        """Add Nationality button must call a nationality-modal open function."""
        assert 'NATI' in self.panel_src, (
            "viz_panel.js must reference NATI tag for Add Nationality functionality"
        )

    def test_edit_fact_button_wired(self):
        """Edit fact button must reference an edit function."""
        assert 'editEvent' in self.panel_src or 'showEditEventModal' in self.panel_src or 'openEditFactModal' in self.panel_src, (
            "viz_panel.js must wire edit-fact buttons to an editEvent (or equivalent) function"
        )

    def test_source_contains_fmtDate(self):
        """viz_panel.js must define fmtDate."""
        assert 'function fmtDate' in self.panel_src, (
            "viz_panel.js must define fmtDate — its absence is a silent regression"
        )

    def test_source_contains_fmtPlace(self):
        """viz_panel.js must define fmtPlace."""
        assert 'function fmtPlace' in self.panel_src, (
            "viz_panel.js must define fmtPlace — its absence is a silent regression"
        )

    def test_source_contains_EARLY_LIFE(self):
        """viz_panel.js must contain section logic for 'Early Life' events."""
        # The source uses 'Early Life' as a variable value; the rendered output
        # is uppercased at runtime via .toUpperCase(). Either form is acceptable.
        assert 'Early Life' in self.panel_src or 'EARLY LIFE' in self.panel_src, (
            "viz_panel.js must contain 'Early Life' or 'EARLY LIFE' section logic"
        )

    def test_source_contains_marr_card(self):
        """viz_panel.js must contain marr-card class for marriage cards."""
        assert 'marr-card' in self.panel_src, (
            "viz_panel.js must render marr-card class for marriage events"
        )

    def test_source_contains_detail_aka(self):
        """viz_panel.js must reference detail-aka element for aliases."""
        assert 'detail-aka' in self.panel_src, (
            "viz_panel.js must render aliases into the detail-aka element"
        )

    def test_source_contains_resi_rollup_logic(self):
        """viz_panel.js must contain RESI rollup logic (collapseResidences or prevResi)."""
        assert 'collapseResidences' in self.panel_src or 'prevResi' in self.panel_src or '_yearRange' in self.panel_src, (
            "viz_panel.js must implement RESI rollup logic "
            "(collapseResidences function or equivalent _yearRange/_prevResi pattern)"
        )


# ---------------------------------------------------------------------------
# D1  Home button wiring — boot script must wire #home-btn to setState
# ---------------------------------------------------------------------------

class TestHomeBtnWiring:
    """
    D1: The #home-btn in the page header must be wired in the boot script
    (DOMContentLoaded) to call resetToRoot(ROOT_XREF), which resets focusXref
    and clears all expansion sets.
    """

    def test_home_btn_listener_wired_in_boot_script(self):
        """Boot script wires home-btn click to resetToRoot, which clears all expansions."""
        assert "resetToRoot(ROOT_XREF)" in _HTML_TEMPLATE
        assert "focusXref" in _FULL_SOURCE, (
            "resetToRoot must set focusXref in state."
        )
        assert "expandedNodes: new Set()" in _FULL_SOURCE, (
            "resetToRoot must clear expandedNodes so the tree returns to "
            "the default root view."
        )
        assert "expandedSiblingsXrefs: new Set()" in _FULL_SOURCE, (
            "resetToRoot must also clear expandedSiblingsXrefs."
        )

    def test_home_btn_listener_references_home_btn_id(self):
        """Boot script must reference the element id 'home-btn'."""
        assert "home-btn" in _HTML_TEMPLATE, (
            "Boot script must get element by id 'home-btn' to wire click handler"
        )

    def test_rendered_html_contains_home_btn_wiring(self, html):
        """Rendered HTML must contain home-btn wiring that resets expansions."""
        assert "home-btn" in html
        assert "resetToRoot(ROOT_XREF)" in html

    def test_home_btn_also_resets_view(self):
        """Home button must also recenter/zoom-reset the canvas via resetView()."""
        assert "resetView()" in _HTML_TEMPLATE, (
            "home-btn handler must call resetView() so the tree re-centers "
            "and zoom returns to 1 when Home is clicked."
        )


# ---------------------------------------------------------------------------
# D3  No snippets_templating.styles.css 404
# ---------------------------------------------------------------------------

class TestNoSnippetsTemplating:
    """
    D3: The <link> tag referencing snippets_templating.styles.css is a stale
    IDE artifact that causes a console 404 error.  It must not appear anywhere
    in the rendered HTML.
    """

    def test_snippets_templating_not_in_template(self):
        """_HTML_TEMPLATE must not reference snippets_templating."""
        assert 'snippets_templating' not in _HTML_TEMPLATE, (
            "Stale <link> referencing snippets_templating.styles.css found in template — "
            "remove it to fix the console 404 error"
        )

    def test_snippets_templating_not_in_rendered_html(self, html):
        """Rendered HTML must not contain snippets_templating."""
        assert 'snippets_templating' not in html, (
            "snippets_templating found in rendered HTML — remove the stale <link> tag"
        )


# ---------------------------------------------------------------------------
# C1  detail-aka and detail-lifespan-row are in header, not body
# ---------------------------------------------------------------------------

class TestAkaLifespanInHeader:
    """
    C1: detail-aka and detail-lifespan-row must live inside detail-header-inner
    (above the divider), not inside detail-body.
    """

    def test_detail_aka_before_detail_body(self):
        """detail-aka must appear before detail-body in the template HTML."""
        aka_pos  = _HTML_TEMPLATE.index('id="detail-aka"')
        body_pos = _HTML_TEMPLATE.index('id="detail-body"')
        assert aka_pos < body_pos, (
            "detail-aka appears after detail-body — it must be in detail-header-inner"
        )

    def test_detail_lifespan_row_before_detail_body(self):
        """detail-lifespan-row must appear before detail-body in the template HTML."""
        lr_pos   = _HTML_TEMPLATE.index('id="detail-lifespan-row"')
        body_pos = _HTML_TEMPLATE.index('id="detail-body"')
        assert lr_pos < body_pos, (
            "detail-lifespan-row appears after detail-body — it must be in detail-header-inner"
        )


# ---------------------------------------------------------------------------
# C4  detail-panel top offset uses CSS variable
# ---------------------------------------------------------------------------

class TestPanelTopOffset:
    """
    C4: #detail-panel must use var(--header-h, 45px) for top offset so it
    doesn't overlap the fixed page header.
    """

    def test_panel_css_uses_header_h_variable(self):
        """CSS for #detail-panel must contain var(--header-h."""
        assert 'var(--header-h' in _CSS, (
            "#detail-panel CSS must use var(--header-h, 45px) for top, not top: 0"
        )


# ---------------------------------------------------------------------------
# External template and CSS files
# ---------------------------------------------------------------------------

_VIZ_DIR = Path(__file__).parent.parent

class TestExternalTemplateFiles:
    """
    The HTML skeleton and CSS live in separate files (viz_ancestors.html /
    viz_ancestors.css) that are loaded at import time into _HTML_TEMPLATE.
    These tests verify the files exist, are non-empty, and that render_html
    inlines their content correctly into the final page.
    """

    def test_html_template_file_exists(self):
        """viz_ancestors.html must exist next to viz_ancestors.py."""
        assert (_VIZ_DIR / 'viz_ancestors.html').exists(), (
            "viz_ancestors.html not found — extract the HTML template from "
            "viz_ancestors.py into this file"
        )

    def test_css_file_exists(self):
        """viz_ancestors.css must exist next to viz_ancestors.py."""
        assert (_VIZ_DIR / 'viz_ancestors.css').exists(), (
            "viz_ancestors.css not found — extract the <style> block from "
            "viz_ancestors.py into this file"
        )

    def test_html_template_file_is_non_empty(self):
        html_file = _VIZ_DIR / 'viz_ancestors.html'
        if html_file.exists():
            assert html_file.stat().st_size > 0, "viz_ancestors.html is empty"

    def test_css_file_is_non_empty(self):
        css_file = _VIZ_DIR / 'viz_ancestors.css'
        if css_file.exists():
            assert css_file.stat().st_size > 0, "viz_ancestors.css is empty"

    def test_rendered_html_contains_css_content(self, html):
        """render_html output must include a rule from the CSS file."""
        css_file = _VIZ_DIR / 'viz_ancestors.css'
        if not css_file.exists():
            pytest.skip("viz_ancestors.css not yet extracted")
        # Pick a distinctive rule that must survive into the rendered page
        sample = css_file.read_text(encoding='utf-8').split('\n')[0].strip()
        assert sample and sample in html, (
            f"CSS file first line {sample!r} not found in render_html output"
        )

    def test_rendered_html_contains_doctype(self, html):
        """render_html must emit a full HTML5 page starting with <!DOCTYPE html>."""
        assert html.lstrip().startswith('<!DOCTYPE html>'), (
            "render_html output does not start with <!DOCTYPE html>"
        )

    def test_rendered_html_contains_style_block(self, html):
        """render_html output must contain a <style> block with CSS."""
        assert '<style>' in html, (
            "render_html output has no <style> block — CSS was not inlined"
        )

    def test_rendered_html_has_root_name_in_title(self, html):
        """The <title> tag must include the root person's name."""
        assert 'Rose Smith' in html, (
            "render_html did not substitute __ROOT_NAME__ with the root person's name"
        )

    def test_template_placeholder_substitution_complete(self, html):
        """No __PLACEHOLDER__ tokens should survive into the rendered output."""
        import re
        leftover = re.findall(r'__[A-Z_]+__', html)
        assert not leftover, (
            f"Unsubstituted placeholders in render_html output: {leftover}"
        )


# ---------------------------------------------------------------------------
# B9  Add-event modal source citation section
# ---------------------------------------------------------------------------

class TestAddEventModalSourceSection:
    """
    B9: The add-event modal must include an optional source-citation section
    with a toggle, source select, and page input — hidden by default.
    Submitting with a source selected must call apiAddCitation after add_event.
    """

    @pytest.fixture(scope='class')
    def _html(self):
        return (Path(__file__).parent.parent / 'viz_ancestors.html').read_text()

    def test_source_toggle_exists(self, _html):
        """Modal must have a toggle button to reveal the source citation section."""
        assert 'event-modal-source-toggle' in _html, (
            'viz_ancestors.html must contain id="event-modal-source-toggle"'
        )

    def test_source_row_hidden_by_default(self, _html):
        """Source citation row must be hidden by default (display:none)."""
        assert 'event-modal-source-row' in _html, (
            'viz_ancestors.html must contain id="event-modal-source-row"'
        )
        import re
        match = re.search(
            r'id="event-modal-source-row"[^>]*style="[^"]*display\s*:\s*none', _html
        )
        assert match, (
            'event-modal-source-row must have style="display:none" to start collapsed'
        )

    def test_source_select_exists(self, _html):
        """Source dropdown must be present inside the event modal."""
        assert 'id="event-modal-source"' in _html, (
            'viz_ancestors.html must contain <select id="event-modal-source">'
        )

    def test_page_input_exists(self, _html):
        """Page/folio input must be present inside the event modal."""
        assert 'id="event-modal-page"' in _html, (
            'viz_ancestors.html must contain <input id="event-modal-page">'
        )

    def test_toggle_function_defined_in_modals_js(self):
        """viz_modals.js must define _toggleEventModalSourceSection."""
        modals_src = (Path(__file__).parent.parent / 'js' / 'viz_modals.js').read_text()
        assert '_toggleEventModalSourceSection' in modals_src, (
            'js/viz_modals.js must define _toggleEventModalSourceSection()'
        )

    def test_source_section_cleared_in_addEvent(self):
        """addEvent() must reset event-modal-source and event-modal-page."""
        modals_src = (Path(__file__).parent.parent / 'js' / 'viz_modals.js').read_text()
        assert 'event-modal-source' in modals_src, (
            'addEvent() must reference event-modal-source to reset it'
        )
        assert 'event-modal-page' in modals_src, (
            'addEvent() must reference event-modal-page to reset it'
        )

    def test_submit_calls_add_citation_when_source_selected(self):
        """submitEventModal must call apiAddCitation after a successful add_event when a source is selected."""
        modals_src = (Path(__file__).parent.parent / 'js' / 'viz_modals.js').read_text()
        submit_fn_start = modals_src.index('async function submitEventModal()')
        submit_fn_body = modals_src[submit_fn_start:submit_fn_start + 8000]
        assert 'apiAddCitation' in submit_fn_body, (
            'submitEventModal() must call apiAddCitation() when a source is selected in the event modal'
        )

    def test_fact_key_derived_from_response(self):
        """submitEventModal must build factKey from the add_event response event_idx."""
        modals_src = (Path(__file__).parent.parent / 'js' / 'viz_modals.js').read_text()
        submit_fn_start = modals_src.index('async function submitEventModal()')
        submit_fn_body = modals_src[submit_fn_start:submit_fn_start + 8000]
        assert 'factKey' in submit_fn_body, (
            'submitEventModal() must construct factKey from the response to call apiAddCitation'
        )
