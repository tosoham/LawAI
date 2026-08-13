"""
Unit tests for the legal graph.

The graph's whole value rests on its edges being true, because a false relation
does not stay local -- it propagates into every answer that touches either
endpoint, with nothing in the output to show it was invented. So these tests
are weighted towards the ways an edge could be wrong: a reference to a
different statute pointed at the same-numbered section of one of ours, a
doctrine attributed to a case that is not in the corpus, a judgement recorded
against a section that does not exist.
"""
import json

import pytest

from services.legal_graph import (
    CURATED_DIR,
    _extract_references,
    build_graph,
    get_legal_graph,
    parse_section_key,
    reset_legal_graph,
    section_key,
)


@pytest.fixture(scope="module")
def graph():
    return build_graph()


class TestSectionKeys:
    def test_round_trip(self):
        assert parse_section_key(section_key("BNS", "103")) == ("BNS", "103")

    def test_a_case_name_is_not_a_section_key(self):
        assert parse_section_key("Bachan Singh v. State of Punjab") is None

    def test_a_bare_number_is_not_a_section_key(self):
        assert parse_section_key("103") is None


class TestExtractReferences:
    def test_a_bare_reference_stays_in_its_own_act(self):
        text = "the period of twenty-four hours fixed by section 58, and there are"
        assert _extract_references(text, "BNSS") == {("BNSS", "58")}

    def test_a_list_of_sections_yields_every_one(self):
        text = "punishable under sections 173, 174 and 175 of this Sanhita"
        assert _extract_references(text, "BNSS") == {
            ("BNSS", "173"),
            ("BNSS", "174"),
            ("BNSS", "175"),
        }

    def test_a_named_act_redirects_the_reference(self):
        text = "as provided in section 63 of the Bharatiya Sakshya Adhiniyam, 2023"
        assert _extract_references(text, "BNSS") == {("BSA", "63")}

    def test_a_reference_to_another_statute_is_dropped_not_redirected(self):
        """
        "section 2 of the Dowry Prohibition Act" must not become an edge to BNS
        2. There is no way to resolve it against this corpus, and pointing it
        at the same-numbered section of the wrong act invents a relation.
        """
        text = "dowry as defined in section 2 of the Dowry Prohibition Act, 1961"
        assert _extract_references(text, "BNS") == set()

    def test_a_reference_to_the_constitution_is_dropped(self):
        text = "notwithstanding section 3 of the Constitution of India"
        assert _extract_references(text, "BNS") == set()

    def test_prose_without_a_reference_yields_nothing(self):
        assert _extract_references("Whoever commits murder shall be punished", "BNS") == set()


class TestBuiltGraph:
    def test_every_section_of_every_act_is_a_node(self, graph):
        assert graph.stats()["sections"] == 358 + 531 + 170

    def test_cross_references_are_bidirectional(self, graph):
        """Every `cites` edge must have a matching `cited_by` edge."""
        for source, targets in graph.cross_references.items():
            for target in targets:
                assert source in graph.cited_by[target]

    def test_no_section_cites_itself(self, graph):
        for source, targets in graph.cross_references.items():
            assert source not in targets

    def test_every_cross_reference_target_exists(self, graph):
        for targets in graph.cross_references.values():
            for target in targets:
                assert graph.has_section(target)

    def test_references_to_other_statutes_are_not_silently_resolved(self, graph):
        """BNS 2 cites four other Acts by section number and no section of ours."""
        assert "BNS 2" not in graph.cross_references or not any(
            target in {"BNS 2", "BNS 3", "BNS 17", "BNS 20"}
            for target in graph.cross_references["BNS 2"]
        )

    def test_a_judgement_reaches_the_sections_it_interprets(self, graph):
        assert "BNSS 482" in graph.interprets["sc_sushila_aggarwal_v_state_nct_of_delhi_2020"]

    def test_a_section_reaches_the_judgements_interpreting_it(self, graph):
        cases = {j.id for j in graph.judgements_on("BNS 103")}
        assert "sc_bachan_singh_v_state_of_punjab_1980" in cases
        assert "sc_machhi_singh_v_state_of_punjab_1983" in cases

    def test_asking_about_remand_reaches_the_cases_on_bail(self, graph):
        """
        The gap this exists to close: BNSS 482 is anticipatory bail, and the
        five judgements that construe it never say the words a user would.
        """
        assert len(graph.judgements_on("BNSS 482")) >= 4

    def test_doctrine_lineage_is_in_date_order(self, graph):
        rare = graph.doctrines["rarest_of_rare"]
        years = [
            int(graph.judgements[j].year)
            for j in rare.judgements
            if j in graph.judgements
        ]
        assert years == sorted(years)

    def test_a_doctrine_reaches_its_section(self, graph):
        names = {d.name for d in graph.doctrines_on("BNSS 482")}
        assert "Anticipatory bail" in names

    def test_a_contested_doctrine_marks_its_sections(self, graph):
        assert "BNSS 480" in graph.contested_sections()
        statutory_bar = graph.doctrines["statutory_bail_bar"]
        assert statutory_bar.contested
        assert statutory_bar.contest_note

    def test_offence_attributes_attach_to_the_parent_section(self, graph):
        """The Schedule keys 103(1); the corpus keys 103."""
        rows = graph.offence_attributes("BNS 103")
        assert rows
        murder = next(r for r in rows if r["offence"] == "Murder.")
        assert murder["bailable"] is False
        assert murder["triable_by"] == "Court of Session."

    def test_a_section_with_no_offence_row_returns_nothing_rather_than_guessing(self, graph):
        """BNSS is procedure; none of it is a punishable offence."""
        assert graph.offence_attributes("BNSS 187") == []

    def test_neighbourhood_reports_every_edge_kind(self, graph):
        view = graph.neighbourhood("BNS 103")
        assert view["section"].title
        assert view["judgements"]
        assert view["doctrines"]
        assert view["classification"]
        assert view["contested"] is False


class TestNoDanglingCuratedEdges:
    """
    The curated file is hand-maintained, so it is the part most likely to drift
    out of step with the corpus. A doctrine pointing at a case that is not
    there is a dead end in every answer that reaches it.
    """

    @pytest.fixture(scope="class")
    def curated(self):
        return json.loads((CURATED_DIR / "doctrines.json").read_text())

    def test_every_cited_judgement_is_in_the_corpus(self, curated, graph):
        missing = [
            (d["id"], j)
            for d in curated["doctrines"]
            for j in d.get("established_by", []) + d.get("refined_by", [])
            if j not in graph.judgements
        ]
        assert not missing

    def test_every_cited_section_is_in_the_corpus(self, curated, graph):
        missing = [
            (d["id"], key)
            for d in curated["doctrines"]
            for key in d.get("applies_to_sections", [])
            if not graph.has_section(key)
        ]
        assert not missing

    def test_every_doctrine_is_attributed(self, curated):
        """A doctrine with no case behind it is an assertion, not a node."""
        assert not [d["id"] for d in curated["doctrines"] if not d.get("established_by")]

    def test_doctrine_ids_are_unique(self, curated):
        ids = [d["id"] for d in curated["doctrines"]]
        assert len(ids) == len(set(ids))

    def test_no_precedential_status_is_claimed_anywhere(self, curated):
        """
        Deliberately absent, and worth a test because it is exactly the field
        someone will add later without thinking about it: whether a case is
        still good law is the highest-harm claim this file could carry.
        """
        forbidden = {"overruled_by", "overrules", "still_good_law", "per_incuriam"}
        for doctrine in curated["doctrines"]:
            assert not forbidden & set(doctrine)

    def test_a_contested_doctrine_explains_the_split(self, curated):
        """Marking a question contested is only useful with both sides named."""
        for doctrine in curated["doctrines"]:
            if doctrine.get("contested"):
                assert doctrine.get("contest_note")
                assert len(doctrine["established_by"] + doctrine["refined_by"]) >= 2


class TestSingleton:
    def test_the_graph_is_built_once(self):
        reset_legal_graph()
        assert get_legal_graph() is get_legal_graph()

    def test_reset_rebuilds(self):
        first = get_legal_graph()
        reset_legal_graph()
        assert get_legal_graph() is not first
