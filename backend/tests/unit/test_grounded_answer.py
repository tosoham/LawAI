"""
Unit tests for the grounded answer pipeline.

The model is stubbed throughout: what is being tested is the machinery around
it -- that a malformed generation abstains instead of raising, that an answer
with nothing left after verification abstains instead of shipping an empty
one, that a section which does not exist is refused before any model is called
at all.

The end-to-end behaviour against a real model is in
``tests/integration/test_grounded_answer_live.py``, which is marked ``live``.
"""
from unittest.mock import MagicMock

import pytest

from models.claims import EpistemicClass
from services.grounded_answer import (
    ABSTENTION_NOTHING_RETRIEVED,
    GroundedAnswerService,
    parse_synthesis,
)

MURDER_CHUNK = (
    "Section 103 - Punishment for murder 103. (1) Whoever commits murder shall be "
    "punished with death or imprisonment for life, and shall also be liable to fine."
)

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


def retrieval(section="103", act="BNS", document=MURDER_CHUNK):
    return {
        "ids": [f"bns_{section}"],
        "documents": [document],
        "metadatas": [{
            "short_name": act,
            "section_number": section,
            "act": "Bharatiya Nyaya Sanhita",
            "title": "Punishment for murder",
        }],
        "distances": [0.21],
    }


@pytest.fixture
def service():
    service = GroundedAnswerService.__new__(GroundedAnswerService)
    service.vector_service = MagicMock()
    service.vector_service.search.return_value = retrieval()
    service.llm_service = MagicMock()
    from services.rag_service import RAGService

    service.rag = RAGService.__new__(RAGService)
    service.rag.vector_service = service.vector_service
    service.rag.llm_service = service.llm_service
    return service


class TestParseSynthesis:
    def test_plain_json(self):
        answer = parse_synthesis(GOOD_SYNTHESIS)
        assert len(answer.claims) == 2
        assert answer.claims[0].epistemic_class is EpistemicClass.STATUTE

    def test_a_fenced_response_is_unwrapped(self):
        """Models fence JSON more often than not, whatever the prompt says."""
        assert parse_synthesis(f"```json\n{GOOD_SYNTHESIS}\n```").claims

    def test_a_bare_list_is_accepted(self):
        assert parse_synthesis('[{"text": "x", "epistemic_class": "inference"}]').claims

    def test_json_wrapped_in_prose_is_still_read(self):
        """
        A model that prefaces its object with a sentence has still produced a
        good answer. Treating that as malformed turned answerable questions
        into abstentions intermittently -- four runs in five on one of them,
        for a reason that had nothing to do with the law.
        """
        answer = parse_synthesis(f"Here is the analysis:\n{GOOD_SYNTHESIS}\nLet me know.")
        assert len(answer.claims) == 2

    def test_prose_yields_nothing_rather_than_raising(self):
        """
        A bad generation must not become a 500. An empty answer makes the
        caller abstain, which is the right outcome for a turn that produced
        nothing checkable.
        """
        assert parse_synthesis("I'm sorry, I can't help with that.").claims == []

    def test_a_wrong_shape_yields_nothing(self):
        assert parse_synthesis('{"claims": [{"text": "x", "epistemic_class": "vibes"}]}').claims == []

    def test_empty_input(self):
        assert parse_synthesis("").claims == []


class TestCitationPrecheck:
    def test_a_section_that_does_not_exist_is_refused_without_a_model_call(self, service):
        result = service.answer("What does section 999 of the Bharatiya Nyaya Sanhita provide?")
        assert result.abstained
        assert "no section 999" in result.answer
        assert "358" in result.answer
        service.llm_service.generate.assert_not_called()
        service.vector_service.search.assert_not_called()

    def test_a_section_that_exists_is_not_refused(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        assert not service.answer("What does BNS 103 provide?").abstained

    def test_a_repealed_citation_is_not_refused_here(self, service):
        """
        "CrPC 438" names a real provision whose replacement the corpus holds.
        The number is not resolvable, but the question is answerable.
        """
        assert service.check_citation("CrPC 438 anticipatory bail") is None

    def test_an_ordinary_question_is_not_refused(self, service):
        assert service.check_citation("what is the punishment for murder") is None


class TestAbstention:
    def test_nothing_retrieved_abstains(self, service):
        service.vector_service.search.return_value = {
            "ids": [], "documents": [], "metadatas": [], "distances": []
        }
        result = service.answer("what is the punishment for murder")
        assert result.abstained
        assert result.answer.startswith(ABSTENTION_NOTHING_RETRIEVED[:40])
        service.llm_service.generate.assert_not_called()

    def test_nothing_verified_abstains_rather_than_shipping_an_empty_answer(self, service):
        """
        The gate. A relevance threshold cannot do this job -- the answerable
        and adversarial distance distributions overlap -- so the question is
        whether a single claim survives checking, and the threshold is one.
        """
        service.llm_service.generate.return_value = BAD_SYNTHESIS
        result = service.answer("is murder bailable")
        assert result.abstained
        assert "could not support any part" in result.answer
        assert result.metrics.abstained

    def test_a_refusal_still_carries_the_disclaimer(self, service):
        service.llm_service.generate.return_value = BAD_SYNTHESIS
        assert "DISCLAIMER" in service.answer("is murder bailable").answer


class TestRegeneration:
    def test_a_failed_answer_is_retried_once_with_the_reasons(self, service):
        service.llm_service.generate.side_effect = [BAD_SYNTHESIS, GOOD_SYNTHESIS]
        result = service.answer("what is the punishment for murder")
        assert not result.abstained
        assert service.llm_service.generate.call_count == 2
        second_prompt = service.llm_service.generate.call_args_list[1].kwargs["prompt"]
        assert "PREVIOUS ATTEMPT FAILED" in second_prompt
        assert "Murder is bailable." in second_prompt

    def test_a_clean_answer_is_not_retried(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        service.answer("what is the punishment for murder")
        assert service.llm_service.generate.call_count == 1

    def test_two_failures_stop_rather_than_trying_again(self, service):
        """A third attempt only produces a more confident version of the same
        unfounded claim."""
        service.llm_service.generate.side_effect = [BAD_SYNTHESIS, BAD_SYNTHESIS]
        assert service.answer("is murder bailable").abstained
        assert service.llm_service.generate.call_count == 2


class TestDeliveredAnswer:
    def test_verified_claims_are_rendered(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        result = service.answer("what is the punishment for murder")
        assert "death or imprisonment for life" in result.answer
        assert "Court of Session" in result.answer

    def test_a_removal_is_reported_to_the_reader(self, service):
        """Silently dropping a claim leaves the reader with a shorter answer
        and no idea why."""
        mixed = """{"claims": [
          {"text": "Murder is punished with death or imprisonment for life.",
           "epistemic_class": "statute", "sources": ["BNS 103"],
           "verbatim_span": "death or imprisonment for life"},
          {"text": "Murder is bailable.", "epistemic_class": "classification",
           "sources": ["BNS 103"]}
        ]}"""
        service.llm_service.generate.side_effect = [mixed, mixed]
        result = service.answer("what is the punishment for murder")
        assert "were removed from this answer" in result.answer
        assert "bailable" not in result.answer.split("_1 statement")[0]

    def test_metrics_describe_what_was_asserted_not_what_survived(self, service):
        service.llm_service.generate.side_effect = [BAD_SYNTHESIS, BAD_SYNTHESIS]
        result = service.answer("is murder bailable")
        assert result.metrics.by_class == {"classification": 1}
        assert result.metrics.unsupported == 1


class TestTrace:
    def test_every_stage_is_recorded(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        steps = [s["step"] for s in service.answer("what is murder").trace["steps"]]
        assert steps == ["retrieve", "graph_expansion", "synthesis", "verify"]

    def test_the_retrieved_ids_are_recorded(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        trace = service.answer("what is murder").trace
        assert trace["steps"][0]["ids"] == ["bns_103"]

    def test_graph_edges_traversed_are_recorded(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        expansion = service.answer("what is murder").trace["steps"][1]
        assert expansion["seeds"] == ["BNS 103"]
        assert "sc_bachan_singh_v_state_of_punjab_1980" in expansion["judgements"]
        assert "rarest_of_rare" in expansion["doctrines"]

    def test_per_claim_verdicts_are_recorded(self, service):
        service.llm_service.generate.side_effect = [BAD_SYNTHESIS, BAD_SYNTHESIS]
        verify_step = service.answer("is murder bailable").trace["steps"][-1]
        assert verify_step["step"] == "verify"
        assert verify_step["verdicts"][0]["verified"] is False
        assert "Non-bailable" in verify_step["verdicts"][0]["reason"]

    def test_an_abstention_records_why(self, service):
        service.llm_service.generate.side_effect = [BAD_SYNTHESIS, BAD_SYNTHESIS]
        assert "could not support" in service.answer("is murder bailable").trace["abstained"]

    def test_metrics_are_in_the_trace(self, service):
        service.llm_service.generate.return_value = GOOD_SYNTHESIS
        assert service.answer("what is murder").trace["metrics"]["claims"] == 2
