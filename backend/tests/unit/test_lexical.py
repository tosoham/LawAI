"""
BM25 and reciprocal rank fusion.

The scoring formula is textbook and not interesting to pin. What is tested is
the reasoning the layer rests on:

* the two retrievers fail on disjoint sets, which is the only thing that makes
  fusing them worth the complexity;
* a chunk both retrievers find must fuse as *one* document, or RRF counts it as
  two documents one retriever liked instead of one both did -- which inverts
  the property fusion is bought for;
* a retriever that fails completely on a query must contribute nothing rather
  than drag the ranking down, because BM25 does fail completely on a term of
  art and dense does on a bare section number.
"""
import pytest

from services.retrieval.lexical import (
    BM25Index,
    hybrid_enabled,
    reciprocal_rank_fusion,
    tokenise,
)
from services.vector_service import VectorService


class TestTokenise:
    def test_case_is_folded(self):
        assert tokenise("Bail") == ["bail"]

    def test_section_numbers_survive_as_tokens(self):
        """Where most of BM25's advantage on the citation class comes from: a
        dense embedder puts 482 and 483 at nearly the same point, and BM25
        matches the literal token."""
        assert "482" in tokenise("section 482 BNSS")

    def test_words_are_not_stemmed(self):
        """"Bailable" and "bail" mean different things in the First Schedule
        and the BNSS. Stemming would collapse them."""
        assert tokenise("bailable") == ["bailable"]
        assert tokenise("bail") == ["bail"]

    def test_punctuation_separates(self):
        assert tokenise("Cr.P.C., 1973") == ["cr", "p", "c", "1973"]


class TestBM25Index:
    @pytest.fixture
    def index(self):
        return BM25Index(
            documents=[
                "Saving of inherent powers of High Court to prevent abuse of "
                "the process of any Court",
                "Any police officer may without a warrant arrest any person",
                "The Court may direct that a person be released on bail",
            ],
            metadatas=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        )

    def test_a_rare_phrase_finds_its_document(self, index):
        assert index.top("abuse of the process", 1) == [0]

    def test_a_query_matching_nothing_returns_nothing(self, index):
        """
        Load-bearing for fusion. BM25 fails *completely* on a term of art --
        "anticipatory" appears in no section of the BNSS -- and it must return
        an empty ranking rather than an arbitrary one, so RRF sees it abstain
        instead of voting for noise.
        """
        assert index.top("zzzz nonexistent", 5) == []

    def test_results_come_back_best_first(self, index):
        assert index.top("bail released Court", 3)[0] == 2

    def test_the_index_keeps_its_documents(self, index):
        """A lexical-only hit has to reach the prompt with its text; refetching
        it from chroma one id at a time would undo holding this in memory."""
        assert "inherent powers" in index.documents[0]

    def test_a_term_in_most_documents_does_not_score_negative(self):
        """
        The textbook idf goes negative for a term in more than half the
        corpus, and "court" is in more than half of sc_judgements -- a
        negative idf would score a judgement *down* for mentioning a court.
        """
        index = BM25Index(
            documents=["the court held", "the court found", "the court said"],
            metadatas=[{}, {}, {}],
        )
        assert all(value >= 0 for value in index.idf.values())

    def test_an_empty_corpus_does_not_divide_by_zero(self):
        index = BM25Index(documents=[], metadatas=[])
        assert index.top("anything", 5) == []


class TestReciprocalRankFusion:
    def test_one_ranking_is_the_identity(self):
        assert reciprocal_rank_fusion([["a", "b", "c"]]) == ["a", "b", "c"]

    def test_agreement_outranks_a_single_retrievers_favourite(self):
        """
        The property being bought. "b" is third for both retrievers; "a" is
        first for one and absent from the other. A document both retrievers
        like is more likely to be right than one either loves alone.
        """
        fused = reciprocal_rank_fusion([["a", "x", "b"], ["y", "z", "b"]])
        assert fused[0] == "b"

    def test_a_retriever_that_returns_nothing_drags_nothing_down(self):
        assert reciprocal_rank_fusion([["a", "b"], []]) == ["a", "b"]

    def test_a_document_only_one_retriever_found_still_appears(self):
        """Fusion must not filter to the intersection — the whole point is that
        each retriever reaches things the other cannot."""
        fused = reciprocal_rank_fusion([["a"], ["b"]])
        assert set(fused) == {"a", "b"}

    def test_no_input_fuses_to_nothing(self):
        assert reciprocal_rank_fusion([]) == []


class TestChunkIdentity:
    def test_the_same_chunk_from_both_retrievers_is_one_document(self):
        """
        Without a shared identity the chunk appears twice and RRF reads it as
        two documents one retriever liked, rather than one both did.
        """
        metadata = {"parent_id": "bnss_482", "chunk_index": 0}
        assert VectorService._chunk_key(metadata) == "bnss_482#0"

    def test_chunks_of_one_section_stay_distinct(self):
        first = VectorService._chunk_key({"parent_id": "sc_x", "chunk_index": 0})
        second = VectorService._chunk_key({"parent_id": "sc_x", "chunk_index": 3})
        assert first != second

    def test_metadata_without_a_parent_falls_back(self):
        assert VectorService._chunk_key({}, "chroma-id") == "chroma-id"


class TestEnableFlag:
    def test_on_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_HYBRID", raising=False)
        assert hybrid_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no"])
    def test_can_be_turned_off(self, monkeypatch, value):
        monkeypatch.setenv("ENABLE_HYBRID", value)
        assert hybrid_enabled() is False
