"""Unit tests for _find_orphaned_individuals.

An individual is "connected" — and therefore NOT orphaned — if they have
at least one of: FAMS, FAMC, or ASSOC.  ASSOC covers cases like godparents
or witnesses who have no family record in the tree but are linked to someone
who does.
"""
from gedcom_merge.analysis import _find_orphaned_individuals
from gedcom_merge.model import GedcomNode
from tests.helpers import make_indi, make_file


def _node_with_assoc(xref: str, assoc_xref: str) -> GedcomNode:
    """Build a raw GedcomNode for an INDI record that has one ASSOC child."""
    assoc_child = GedcomNode(level=1, tag='ASSOC', value=assoc_xref, xref=None, children=[])
    return GedcomNode(level=0, tag='INDI', value='', xref=xref, children=[assoc_child])


def _indi_with_assoc(xref: str, assoc_xref: str):
    """Return an Individual whose raw node contains an ASSOC link."""
    indi = make_indi(xref)
    # Replace the plain raw node with one that carries the ASSOC child.
    object.__setattr__(indi, 'raw', _node_with_assoc(xref, assoc_xref))
    return indi


class TestFindOrphanedIndividuals:
    def test_no_individuals(self):
        f = make_file()
        assert _find_orphaned_individuals(f) == []

    def test_individual_with_fams_is_not_orphaned(self):
        indi = make_indi('@I1@', fams=['@F1@'])
        f = make_file(indis={'@I1@': indi})
        assert _find_orphaned_individuals(f) == []

    def test_individual_with_famc_is_not_orphaned(self):
        indi = make_indi('@I1@', famc=['@F1@'])
        f = make_file(indis={'@I1@': indi})
        assert _find_orphaned_individuals(f) == []

    def test_individual_with_assoc_is_not_orphaned(self):
        """An individual linked via ASSOC (e.g. godparent) is connected to the tree."""
        indi = _indi_with_assoc('@I1@', '@I2@')
        f = make_file(indis={'@I1@': indi})
        assert _find_orphaned_individuals(f) == []

    def test_individual_with_no_links_is_orphaned(self):
        indi = make_indi('@I1@')
        f = make_file(indis={'@I1@': indi})
        assert _find_orphaned_individuals(f) == ['@I1@']

    def test_mixed_connected_and_orphaned(self):
        linked = make_indi('@I1@', fams=['@F1@'])
        assoc_linked = _indi_with_assoc('@I2@', '@I1@')
        orphan = make_indi('@I3@')
        f = make_file(indis={
            '@I1@': linked,
            '@I2@': assoc_linked,
            '@I3@': orphan,
        })
        assert _find_orphaned_individuals(f) == ['@I3@']

    def test_multiple_orphans(self):
        indis = {f'@I{i}@': make_indi(f'@I{i}@') for i in range(1, 4)}
        f = make_file(indis=indis)
        assert sorted(_find_orphaned_individuals(f)) == ['@I1@', '@I2@', '@I3@']
