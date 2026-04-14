"""
Tests for half-sibling detection in build_relatives_json().

Fixture family structure (half_siblings_sample.ged):

  Bob (I2) ─── Carol (I3)          Bob (I2) ─── Diane (I6)    Ernest (I8) ─── Carol (I3)
       |                                   |                            |
  ┌────┴────┐                           I5 Eve                      I7 Frank
  I1 Alice  I4 David
  (subject)

Alice (I1) shares F1 with David (I4) → full siblings
Alice shares Bob (I2) with Eve (I5, from F2) → half-sibling on Bob's side, other parent = Diane
Alice shares Carol (I3) with Frank (I7, from F3) → half-sibling on Carol's side, other parent = Ernest
"""
from pathlib import Path

import pytest

from viz_ancestors import parse_gedcom, build_relatives_json

FIXTURE = Path(__file__).parent / 'fixtures' / 'half_siblings_sample.ged'


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
def relatives(indis, fams):
    return build_relatives_json({}, indis, fams)


class TestFullSiblings:
    """Full siblings share the same FAMC record — David is Alice's only full sibling."""

    def test_alice_full_sibling_is_david(self, relatives):
        sibs = relatives['@I1@']['siblings']
        assert '@I4@' in sibs

    def test_alice_has_exactly_one_full_sibling(self, relatives):
        assert len(relatives['@I1@']['siblings']) == 1

    def test_half_siblings_excluded_from_siblings(self, relatives):
        sibs = set(relatives['@I1@']['siblings'])
        assert '@I5@' not in sibs  # Eve is a half-sib, not a full sib
        assert '@I7@' not in sibs  # Frank is a half-sib, not a full sib

    def test_david_full_sibling_is_alice(self, relatives):
        assert '@I1@' in relatives['@I4@']['siblings']


class TestHalfSiblings:
    """Half-siblings share exactly one parent."""

    def test_alice_has_two_half_sib_groups(self, relatives):
        groups = relatives['@I1@'].get('half_siblings', [])
        assert len(groups) == 2

    def test_half_sib_on_bobs_side(self, relatives):
        groups = relatives['@I1@']['half_siblings']
        bob_group = next((g for g in groups if g['shared_parent'] == '@I2@'), None)
        assert bob_group is not None, "Expected a half-sibling group on Bob's side"
        assert '@I5@' in bob_group['half_sibs']   # Eve
        assert bob_group['other_parent'] == '@I6@'  # Diane

    def test_half_sib_on_carols_side(self, relatives):
        groups = relatives['@I1@']['half_siblings']
        carol_group = next((g for g in groups if g['shared_parent'] == '@I3@'), None)
        assert carol_group is not None, "Expected a half-sibling group on Carol's side"
        assert '@I7@' in carol_group['half_sibs']    # Frank
        assert carol_group['other_parent'] == '@I8@'  # Ernest

    def test_full_sibling_not_in_any_half_sib_group(self, relatives):
        groups = relatives['@I1@'].get('half_siblings', [])
        all_half_sibs = {cx for g in groups for cx in g['half_sibs']}
        assert '@I4@' not in all_half_sibs  # David is a full sibling, not half

    def test_person_not_in_own_half_sib_group(self, relatives):
        groups = relatives['@I1@'].get('half_siblings', [])
        all_half_sibs = {cx for g in groups for cx in g['half_sibs']}
        assert '@I1@' not in all_half_sibs

    def test_eve_has_half_siblings_on_bobs_side(self, relatives):
        # Eve (I5) is Bob+Diane's child. Bob also has Alice (I1) and David (I4) with Carol (I3).
        # So Eve should see Alice and David as half-siblings on Bob's side.
        groups = relatives.get('@I5@', {}).get('half_siblings', [])
        bob_group = next((g for g in groups if g['shared_parent'] == '@I2@'), None)
        assert bob_group is not None, "Eve should have a half-sibling group on Bob's side"
        assert set(bob_group['half_sibs']) == {'@I1@', '@I4@'}
        assert bob_group['other_parent'] == '@I3@'  # Carol

    def test_alice_bob_group_contains_only_eve(self, relatives):
        """No extra people should appear in the Bob-side group for Alice."""
        groups = relatives['@I1@']['half_siblings']
        bob_group = next(g for g in groups if g['shared_parent'] == '@I2@')
        assert set(bob_group['half_sibs']) == {'@I5@'}

    def test_alice_carol_group_contains_only_frank(self, relatives):
        """No extra people should appear in the Carol-side group for Alice."""
        groups = relatives['@I1@']['half_siblings']
        carol_group = next(g for g in groups if g['shared_parent'] == '@I3@')
        assert set(carol_group['half_sibs']) == {'@I7@'}

    def test_no_duplicate_half_sibs_for_alice(self, relatives):
        groups = relatives['@I1@'].get('half_siblings', [])
        all_half_sibs = [cx for g in groups for cx in g['half_sibs']]
        assert len(all_half_sibs) == len(set(all_half_sibs)), "Duplicate half-siblings found"

    def test_frank_sees_alice_and_david_as_half_sibs_on_carols_side(self, relatives):
        # Frank (I7) is Ernest+Carol's child. Carol also has Alice (I1) and David (I4) with Bob.
        groups = relatives.get('@I7@', {}).get('half_siblings', [])
        carol_group = next((g for g in groups if g['shared_parent'] == '@I3@'), None)
        assert carol_group is not None, "Frank should have a half-sibling group on Carol's side"
        assert set(carol_group['half_sibs']) == {'@I1@', '@I4@'}
        assert carol_group['other_parent'] == '@I2@'  # Bob

    def test_frank_has_no_half_sibs_on_ernests_side(self, relatives):
        # Ernest (I8) has no other families, so no half-siblings on his side.
        groups = relatives.get('@I7@', {}).get('half_siblings', [])
        ernest_group = next((g for g in groups if g['shared_parent'] == '@I8@'), None)
        assert ernest_group is None

    def test_david_has_same_half_siblings_as_alice(self, relatives):
        # David (I4) shares both parents with Alice, so same half-sib groups.
        alice_groups = relatives['@I1@'].get('half_siblings', [])
        david_groups = relatives['@I4@'].get('half_siblings', [])
        alice_all = {cx for g in alice_groups for cx in g['half_sibs']}
        david_all = {cx for g in david_groups for cx in g['half_sibs']}
        assert alice_all == david_all

    def test_half_sibling_relationship_is_symmetric(self, relatives):
        # Eve sees exactly Alice+David on Bob's side (already tested),
        # and Frank sees exactly Alice+David on Carol's side.
        eve_groups = relatives.get('@I5@', {}).get('half_siblings', [])
        eve_all = {cx for g in eve_groups for cx in g['half_sibs']}
        assert eve_all == {'@I1@', '@I4@'}, "Eve's half-sibs should be exactly Alice and David"

        frank_groups = relatives.get('@I7@', {}).get('half_siblings', [])
        frank_all = {cx for g in frank_groups for cx in g['half_sibs']}
        assert frank_all == {'@I1@', '@I4@'}, "Frank's half-sibs should be exactly Alice and David"

    def test_unknown_other_parent_handled(self, indis, fams):
        """When a parent's other family has no spouse recorded, other_parent should be None."""
        # Build a minimal scenario: add a family with Bob only (no wife), one child
        indis_copy = {k: dict(v) for k, v in indis.items()}
        fams_copy = {k: dict(v) for k, v in fams.items()}
        # Inject a family where Bob has a child but no wife listed
        indis_copy['@I2@'] = dict(indis_copy['@I2@'])
        indis_copy['@I2@']['fams'] = list(indis_copy['@I2@'].get('fams', [])) + ['@F99@']
        indis_copy['@I99@'] = {'name': 'Mystery Child', 'birth_year': None, 'death_year': None,
                               'sex': None, 'famc': '@F99@', 'fams': [], 'events': [],
                               'notes': [], 'source_xrefs': [], 'source_urls': {}}
        fams_copy['@F99@'] = {'husb': '@I2@', 'wife': None, 'chil': ['@I99@'], 'marrs': []}

        rels = build_relatives_json({}, indis_copy, fams_copy)
        alice_groups = rels['@I1@'].get('half_siblings', [])
        bob_group = next((g for g in alice_groups if g['shared_parent'] == '@I2@'), None)
        # Find any group where the mystery child is listed
        mystery_group = next(
            (g for g in alice_groups if '@I99@' in g.get('half_sibs', [])), None
        )
        assert mystery_group is not None, "Mystery child (unknown other parent) should appear as half-sibling"
        assert mystery_group['other_parent'] is None


class TestNoFamilyData:
    """People with no parents or only one parent should be handled gracefully."""

    def test_person_with_no_parents_has_no_half_siblings(self, relatives):
        # Bob (I2) has no FAMC, so no half-siblings from his side
        groups = relatives.get('@I2@', {}).get('half_siblings', [])
        assert groups == []
