"""
Contract tests for ``POST /api/v1/search/grounded``.

What the endpoint must never do is flatten the distinctions the pipeline
exists to preserve: an unsupported claim leaking into ``claims``, the epistemic
class going missing, or graph-reached material being merged into ``sources`` so
a client cannot tell what was retrieved from what was inferred by an edge.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

GOOD_SYNTHESIS = """{"claims": [
  {"text": "Murder is punished with death or imprisonment for life.",
   "epistemic_class": "statute", "sources": ["BNS 103"],
   "verbatim_span": "death or imprisonment for life"},
  {"text": "Murder is cognizable, non-bailable and triable by a Court of Session.",
   "epistemic_class": "classification", "sources": ["BNS 103"]}
]}"""

BAD_SYNTHESIS = """{"claims": [
  {"text": "Murder is bailable.", "epistemic_class": "classification",
   "sources": ["BNS 103"]}
]}"""

RETRIEVAL = {
    "ids": ["bns_103"],
    "documents": [
        "Section 103 - Punishment for murder 103. (1) Whoever commits murder shall "
        "be punished with death or imprisonment for life, and shall also be liable "
        "to fine."
    ],
    "metadatas": [{
        "short_name": "BNS",
        "section_number": "103",
        "act": "Bharatiya Nyaya Sanhita",
        "title": "Punishment for murder",
    }],
    "distances": [0.21],
}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def stubbed():
    """A grounded service whose retrieval and model are both stubbed."""
    from services.grounded_answer import GroundedAnswerService
    from services.rag_service import RAGService

    service = GroundedAnswerService.__new__(GroundedAnswerService)
    service.vector_service = MagicMock()
    service.vector_service.search.return_value = RETRIEVAL
    service.llm_service = MagicMock()
    service.llm_service.generate.return_value = GOOD_SYNTHESIS
    service.rag = RAGService.__new__(RAGService)
    service.rag.vector_service = service.vector_service
    service.rag.llm_service = service.llm_service

    with patch("api.v1.search.get_grounded_answer_service", return_value=service):
        yield service


def post(client, **body):
    body.setdefault("query", "what is the punishment for murder")
    body.setdefault("collection", "bns")
    return client.post("/api/v1/search/grounded", json=body)


class TestShape:
    def test_a_verified_answer_comes_back_with_its_claims(self, client, stubbed):
        payload = post(client).json()
        assert payload["abstained"] is False
        assert len(payload["claims"]) == 2
        assert payload["answer"]

    def test_every_claim_carries_its_epistemic_class(self, client, stubbed):
        """
        A client that renders every claim identically has thrown away the only
        thing separating enacted text from the model's reasoning.
        """
        classes = [c["epistemic_class"] for c in post(client).json()["claims"]]
        assert classes == ["statute", "classification"]

    def test_sources_are_typed_by_what_they_point_at(self, client, stubbed):
        sources = post(client).json()["claims"][0]["sources"]
        assert sources == [{"ref": "BNS 103", "kind": "section"}]

    def test_metrics_are_returned(self, client, stubbed):
        metrics = post(client).json()["metrics"]
        assert metrics["claims"] == 2
        assert metrics["grounding_rate"] == 1.0
        assert metrics["unsupported"] == 0

    def test_the_trace_is_returned(self, client, stubbed):
        trace = post(client).json()["trace"]
        assert [s["step"] for s in trace["steps"]] == [
            "retrieve", "graph_expansion", "synthesis", "verify"
        ]

    def test_graph_context_stays_out_of_sources(self, client, stubbed):
        """
        One was retrieved by relevance, the other reached by an edge. A client
        that merges them asserts something the API did not.
        """
        payload = post(client).json()
        assert payload["graph_context"]["judgements"]
        source_ids = {s["id"] for s in payload["sources"]}
        assert source_ids == {"bns_103"}


class TestAbstention:
    def test_an_unsupportable_question_returns_an_abstention_not_an_error(
        self, client, stubbed
    ):
        stubbed.llm_service.generate.return_value = BAD_SYNTHESIS
        response = post(client, query="is murder bailable")
        assert response.status_code == 200
        payload = response.json()
        assert payload["abstained"] is True
        assert payload["claims"] == []

    def test_the_verdicts_explain_the_abstention(self, client, stubbed):
        stubbed.llm_service.generate.return_value = BAD_SYNTHESIS
        verdicts = post(client, query="is murder bailable").json()["verdicts"]
        assert verdicts[0]["verified"] is False
        assert "Non-bailable" in verdicts[0]["reason"]
        assert verdicts[0]["original_class"] == "classification"

    def test_no_unsupported_claim_is_ever_returned(self, client, stubbed):
        mixed = """{"claims": [
          {"text": "Murder is punished with death or imprisonment for life.",
           "epistemic_class": "statute", "sources": ["BNS 103"],
           "verbatim_span": "death or imprisonment for life"},
          {"text": "Murder is bailable.", "epistemic_class": "classification",
           "sources": ["BNS 103"]}
        ]}"""
        stubbed.llm_service.generate.side_effect = [mixed, mixed]
        payload = post(client).json()
        assert [c["epistemic_class"] for c in payload["claims"]] == ["statute"]
        assert payload["metrics"]["unsupported"] == 1


class TestRequestValidation:
    def test_an_unknown_collection_is_rejected(self, client, stubbed):
        assert post(client, collection="tax_code").status_code == 422

    def test_the_collection_defaults_to_the_bns(self, client, stubbed):
        assert client.post(
            "/api/v1/search/grounded", json={"query": "what is murder"}
        ).status_code == 200
        assert stubbed.vector_service.search.call_args.kwargs["collection_name"] == (
            "bns_sections"
        )

    def test_a_full_collection_name_is_accepted(self, client, stubbed):
        assert post(client, collection="bns_sections").status_code == 200

    def test_an_empty_query_is_rejected(self, client, stubbed):
        assert post(client, query="").status_code == 422
