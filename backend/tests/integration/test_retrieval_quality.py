"""
Retrieval quality tests.

These run against the real embedded corpus (no LLM, so no API key needed) and
pin the ranking behaviour that query expansion was built to fix. They are the
only tests that would catch a regression in retrieval *quality* — the unit tests
cover the expansion strings, not whether the right section comes back.

Skipped when the vector store has not been seeded, so a fresh checkout that has
not run scripts/init_vector_db.py still gets a green suite.
"""
import pytest

from services.vector_service import VectorService, get_vector_service

pytestmark = pytest.mark.integration

# How far down the ranking a section may appear and still count as "found".
# Deliberately loose: the claim being tested is that the governing section is
# retrievable at all, not that it pins to exactly rank 1 forever.
TOP_N = 3


@pytest.fixture(scope="module")
def vector_service():
    service = get_vector_service()
    stats = service.get_collection_stats(VectorService.BNSS_COLLECTION)
    if not stats.get("count"):
        pytest.skip(
            "Vector store is empty - run scripts/init_vector_db.py to enable "
            "retrieval quality tests"
        )
    return service


def sections(service, collection, query, *, expand=True, top_k=6, rerank=None,
             hybrid=None):
    """Section numbers returned for a query, in rank order."""
    results = service.search(
        collection, query, top_k=top_k, expand=expand, rerank=rerank,
        hybrid=hybrid,
    )
    return [metadata.get("section_number") for metadata in results["metadatas"]]


class TestVocabularyMismatch:
    """
    Terms of art absent from the statute they govern.

    This is the failure mode query expansion exists for, and it is not fixable
    with a lexical retriever: the word "anticipatory" does not occur anywhere in
    BNSS 482, so there is nothing for BM25 to match either.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "anticipatory bail",
            "grounds for anticipatory bail",
            "can I get pre-arrest bail",
        ],
    )
    def test_anticipatory_bail_reaches_bnss_482(self, vector_service, query):
        ranked = sections(
            vector_service, VectorService.BNSS_COLLECTION, query
        )
        assert "482" in ranked[:TOP_N], f"{query!r} ranked: {ranked}"

    def test_bnss_482_is_unreachable_by_the_embedder_alone(self, vector_service):
        """
        Documents *why* the expansion layer exists. If this ever starts failing
        because 482 now ranks unaided — a better embedding model, say — the
        expansion entry for anticipatory bail has become redundant and this
        whole module deserves rethinking rather than patching.

        Reranking and lexical fusion are held off along with expansion,
        because the claim under test is about what the *embedder* can reach.
        That is not a hypothetical distinction — both of the other layers do
        reach 482 unexpanded (see the tests below), and reading either as "the
        alias is redundant now" would be wrong. Measured over the golden set,
        dropping expansion costs the cross-encoder 0.250 of term_of_art
        recall@3 and costs BM25 0.688.
        """
        ranked = sections(
            vector_service,
            VectorService.BNSS_COLLECTION,
            "anticipatory bail",
            expand=False,
            rerank=False,
            hybrid=False,
        )
        assert "482" not in ranked, (
            "BNSS 482 is now retrievable by the embedder alone; reconsider "
            f"whether the alias is still needed. Ranked: {ranked}"
        )

    def test_the_reranker_recovers_482_from_deep_in_the_unexpanded_pool(
        self, vector_service
    ):
        """
        What a cross-encoder is for, on the hardest class in the corpus.

        Unexpanded, the embedder puts BNSS 482 at rank 18 — retrieved, and far
        below anything a reader sees. The cross-encoder scores the query
        against the chunk rather than comparing two separately-embedded points,
        and lifts it into the top 6.

        This does not make expansion redundant, and the two are not
        alternatives: reranking can only reorder what was retrieved, so it
        depends on 482 being in the candidate pool at all. Expansion is what
        puts it there for the queries where it is not.
        """
        ranked = sections(
            vector_service,
            VectorService.BNSS_COLLECTION,
            "anticipatory bail",
            expand=False,
            rerank=True,
            hybrid=False,
        )
        assert "482" in ranked, f"ranked: {ranked}"

    def test_a_deeper_pool_is_still_cut_back_to_top_k(self, vector_service):
        """
        Fusion pulls thirty candidates and reranking is what cuts them back.
        With reranking off nothing did, and a caller asking for six chunks got
        thirty — five times the context budget, silently.
        """
        ranked = sections(
            vector_service,
            VectorService.BNSS_COLLECTION,
            "anticipatory bail",
            top_k=6,
            rerank=False,
            hybrid=True,
        )
        assert len(ranked) <= 6, f"got {len(ranked)}: {ranked}"

    def test_default_bail_reaches_the_detention_limit_provisions(self, vector_service):
        """
        "Default bail" is judicial shorthand for release when investigation
        overruns the permitted detention period — BNSS 187(3), enforced via the
        undertrial detention limit in BNSS 479. Neither section uses the phrase.
        """
        ranked = sections(
            vector_service, VectorService.BNSS_COLLECTION, "default bail", top_k=8
        )
        assert {"187", "479"} & set(ranked), f"ranked: {ranked}"


class TestRepealedCodeNames:
    """A query naming the pre-2023 codes must still land in the new ones."""

    def test_crpc_query_returns_bnss_sections(self, vector_service):
        results = vector_service.search(
            VectorService.BNSS_COLLECTION, "CrPC bail provisions", top_k=3
        )
        acts = {metadata.get("act") for metadata in results["metadatas"]}
        assert acts == {"Bharatiya Nagarik Suraksha Sanhita"}, acts


class TestNoRegression:
    """Expansion is additive, so queries that already worked must still work."""

    @pytest.mark.parametrize(
        "collection,query,expected",
        [
            # BNS 104 ("Punishment for murder by life-convict") outranks BNS 103
            # ("Punishment for murder") for this query — a quirk of embedding
            # similarity on near-identical titles that predates query expansion
            # and is identical with it disabled. Asserting top-N rather than
            # rank 1 records the real behaviour instead of a wish.
            (VectorService.BNS_COLLECTION, "punishment for murder", "103"),
            (VectorService.BNSS_COLLECTION, "double jeopardy", "337"),
        ],
    )
    def test_direct_queries_still_retrieve_the_governing_section(
        self, vector_service, collection, query, expected
    ):
        ranked = sections(vector_service, collection, query)
        assert expected in ranked[:TOP_N], f"{query!r} ranked: {ranked}"

    def test_unrecognised_query_is_unaffected_by_expansion(self, vector_service):
        """No alias matches, so expanded and unexpanded must be identical."""
        query = "punishment for theft of a motor vehicle"
        with_expansion = sections(
            vector_service, VectorService.BNS_COLLECTION, query, expand=True
        )
        without = sections(
            vector_service, VectorService.BNS_COLLECTION, query, expand=False
        )
        assert with_expansion == without
