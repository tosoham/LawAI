"""
Unit tests for citation parsing and exact-section lookup.

The point of this component is that it answers with certainty where the
embedder cannot, so the tests are mostly about the two ways certainty goes
wrong: claiming it for a citation that was never made, and claiming it for a
repealed section number that does not mean what it used to.
"""
from unittest.mock import MagicMock

import pytest

from services.retrieval.structured_filter import parse_citation
from services.vector_service import VectorService


class TestParsingCurrentCitations:
    @pytest.mark.parametrize(
        "query,section,collection",
        [
            ("BNS 103", "103", "bns_sections"),
            ("BNSS section 187", "187", "bnss_sections"),
            ("section 482 BNSS", "482", "bnss_sections"),
            ("BSA 63", "63", "bsa_sections"),
            ("s. 103 BNS", "103", "bns_sections"),
            ("section 39 Bharatiya Sakshya Adhiniyam", "39", "bsa_sections"),
            (
                "what does section 111 of the Bharatiya Nyaya Sanhita say",
                "111",
                "bns_sections",
            ),
            ("section 35 of BNSS on arrest without warrant", "35", "bnss_sections"),
        ],
    )
    def test_resolves(self, query, section, collection):
        citation = parse_citation(query)
        assert citation is not None, query
        assert citation.section == section
        assert citation.collection == collection
        assert citation.resolvable

    def test_bnss_is_not_read_as_bns(self):
        """"BNS" is a prefix of "BNSS"; the longer name has to win."""
        assert parse_citation("BNSS 187").collection == "bnss_sections"

    def test_a_sub_clause_resolves_to_its_parent_section(self):
        """The corpus indexes 103, not 103(1)."""
        assert parse_citation("BNS 103(1)").section == "103"

    def test_a_section_without_an_act_leaves_the_act_to_the_caller(self):
        citation = parse_citation("what does section 187 say")
        assert citation.section == "187"
        assert citation.collection is None
        assert citation.resolvable


class TestRefusingRepealedCitations:
    """
    The dangerous case. CrPC 438 is BNSS 482, but BNSS 438 exists and is about
    something else, so resolving the number would replace a miss with a
    confident wrong answer.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "IPC 302 murder",
            "what replaced IPC section 420 cheating",
            "CrPC 438 anticipatory bail",
            "CrPC 482 inherent powers",
            "section 154 of the Code of Criminal Procedure",
            "Evidence Act section 65B electronic records",
            "IPC 498A cruelty",
        ],
    )
    def test_the_number_is_refused(self, query):
        citation = parse_citation(query)
        assert citation is not None
        assert citation.repealed
        assert not citation.resolvable

    def test_the_act_is_still_resolved(self):
        """Knowing which act replaced it is safe, and useful downstream."""
        assert parse_citation("IPC 302").collection == "bns_sections"

    def test_a_repealed_act_named_far_from_the_number_still_refuses(self):
        """
        "Indian Evidence Act dying declaration section 32" cites a repealed
        provision even though the act and the number are twenty characters
        apart. BSA 32 is not the dying-declaration section -- BSA 26 is.
        """
        citation = parse_citation("Indian Evidence Act dying declaration section 32")
        assert citation.section == "32"
        assert citation.repealed
        assert not citation.resolvable

    def test_a_lettered_section_is_refused_even_without_a_named_act(self):
        """No section of the 2023 codes carries a letter, so "41A" is a CrPC
        citation whether or not the query said so."""
        citation = parse_citation("tell me about section 41A")
        assert citation.suffix == "A"
        assert not citation.resolvable


class TestNotACitation:
    @pytest.mark.parametrize(
        "query",
        [
            "what is the punishment for murder",
            "explain anticipatory bail",
            "Bachan Singh v State of Punjab",
            "how long can the police detain me",
            "BNS for causing 5 deaths",
            "",
            "   ",
        ],
    )
    def test_returns_nothing(self, query):
        assert parse_citation(query) is None


class TestExactSectionHits:
    """The lookup itself, against a stubbed collection."""

    def service(self):
        service = VectorService.__new__(VectorService)
        return service

    def collection(self, ids=("bns_103_0",), documents=("Section 103 - Murder",)):
        collection = MagicMock()
        collection.get.return_value = {
            "ids": list(ids),
            "documents": list(documents),
            "metadatas": [{"section_number": "103"} for _ in ids],
        }
        return collection

    def test_a_cited_section_is_fetched_by_metadata(self):
        collection = self.collection()
        hits = self.service()._exact_section_hits(collection, "bns_sections", "BNS 103")
        collection.get.assert_called_once()
        assert collection.get.call_args.kwargs["where"] == {"section_number": "103"}
        assert hits["ids"] == ["bns_103_0"]
        assert hits["distances"] == [0.0]

    def test_a_citation_to_another_act_is_not_looked_up_here(self):
        """Searching BNS for "BNSS 187" must not return BNS 187."""
        collection = self.collection()
        hits = self.service()._exact_section_hits(collection, "bns_sections", "BNSS 187")
        assert hits == {}
        collection.get.assert_not_called()

    def test_a_repealed_citation_is_not_looked_up(self):
        collection = self.collection()
        hits = self.service()._exact_section_hits(
            collection, "bnss_sections", "CrPC 438 anticipatory bail"
        )
        assert hits == {}
        collection.get.assert_not_called()

    def test_a_bare_section_number_resolves_against_the_collection_searched(self):
        collection = self.collection()
        hits = self.service()._exact_section_hits(
            collection, "bnss_sections", "what does section 187 say"
        )
        assert hits["ids"] == ["bns_103_0"]

    def test_a_cited_section_the_corpus_lacks_falls_through(self):
        collection = MagicMock()
        collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}
        hits = self.service()._exact_section_hits(collection, "bns_sections", "BNS 999")
        assert hits == {}

    def test_a_non_citation_never_reaches_the_store(self):
        collection = self.collection()
        hits = self.service()._exact_section_hits(
            collection, "bns_sections", "what is the punishment for murder"
        )
        assert hits == {}
        collection.get.assert_not_called()


class TestMergeExactHits:
    def merge(self, exact, vector, top_k):
        return VectorService._merge_exact_hits(exact, vector, top_k)

    def build(self, ids, distance=0.5):
        return {
            "ids": list(ids),
            "documents": [f"doc {i}" for i in ids],
            "metadatas": [{"section_number": i} for i in ids],
            "distances": [distance] * len(ids),
        }

    def test_the_cited_section_ranks_first(self):
        merged = self.merge(self.build(["482"], 0.0), self.build(["480", "483"]), 5)
        assert merged["ids"] == ["482", "480", "483"]

    def test_vector_results_are_kept_not_replaced(self):
        """
        "section 35 of BNSS on arrest without warrant" is a citation *and* a
        question; the neighbouring sections are often what the reader needs.
        """
        merged = self.merge(self.build(["35"], 0.0), self.build(["36", "37"]), 5)
        assert len(merged["ids"]) == 3

    def test_top_k_still_bounds_the_result(self):
        merged = self.merge(self.build(["1"], 0.0), self.build(["2", "3", "4", "5"]), 3)
        assert merged["ids"] == ["1", "2", "3"]

    def test_a_duplicated_chunk_is_not_returned_twice(self):
        """The vector search often finds the cited section too."""
        merged = self.merge(self.build(["482"], 0.0), self.build(["482", "480"]), 5)
        assert merged["ids"] == ["482", "480"]

    def test_every_parallel_list_stays_the_same_length(self):
        merged = self.merge(self.build(["1"], 0.0), self.build(["2", "3"]), 5)
        lengths = {len(merged[key]) for key in ("ids", "documents", "metadatas", "distances")}
        assert lengths == {3}
