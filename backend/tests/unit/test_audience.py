"""
Unit tests for the audience register.

Two things are being protected here, and they pull in opposite directions.

The register has to actually change the writing, or it is decoration. And it
has to change *nothing else* — not what is retrieved, not what passes
verification, not which claims survive — or "written for a citizen" quietly
becomes "checked less carefully for a citizen", which is the failure mode that
would matter.

The strongest guarantee is structural rather than tested: neither
``VectorService.search`` nor ``claim_verifier.verify`` takes an audience
argument, so there is no path by which the register could reach them. These
tests pin the parts that are not structural.
"""
import inspect
from unittest.mock import MagicMock

import pytest

from services import claim_verifier, vector_service
from services.audience import (
    REGISTER_GUIDANCE,
    Audience,
    parse_audience,
    register_layer,
)
from services.grounded_answer import GroundedAnswerService

GOOD_SYNTHESIS = """{"claims": [
  {"text": "Murder is punished with death or imprisonment for life.",
   "epistemic_class": "statute", "sources": ["BNS 103"],
   "verbatim_span": "death or imprisonment for life"}
]}"""

RETRIEVAL = {
    "ids": ["bns_103"],
    "documents": [
        "Whoever commits murder shall be punished with death or imprisonment for life."
    ],
    "metadatas": [{"short_name": "BNS", "section_number": "103", "act": "BNS"}],
    "distances": [0.2],
}


@pytest.fixture
def service():
    from services.rag_service import RAGService

    svc = GroundedAnswerService.__new__(GroundedAnswerService)
    svc.vector_service = MagicMock()
    svc.vector_service.search.return_value = RETRIEVAL
    svc.llm_service = MagicMock()
    svc.llm_service.generate.return_value = GOOD_SYNTHESIS
    svc.rag = RAGService.__new__(RAGService)
    svc.rag.vector_service = svc.vector_service
    svc.rag.llm_service = svc.llm_service
    return svc


class TestParseAudience:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("citizen", Audience.CITIZEN),
            ("lawyer", Audience.LAWYER),
            ("judge", Audience.JUDGE),
            ("JUDGE", Audience.JUDGE),
            ("  lawyer  ", Audience.LAWYER),
        ],
    )
    def test_recognised_registers(self, value, expected):
        assert parse_audience(value) is expected

    @pytest.mark.parametrize("value", [None, "", "magistrate", "student"])
    def test_anything_else_falls_back_to_the_citizen(self, value):
        """
        The default is the reader with least recourse, and an unrecognised
        value falls back rather than erroring: the register affects how an
        answer reads, never whether it is correct, so refusing the request over
        a typo trades something that matters for something that does not.
        """
        assert parse_audience(value) is Audience.CITIZEN


class TestRegisterGuidance:
    def test_every_register_has_guidance(self):
        assert set(REGISTER_GUIDANCE) == set(Audience)

    def test_the_citizen_register_keeps_citations(self):
        """A shorter answer, not a vaguer one. Dropping section numbers to make
        a sentence flow removes the reader's only way to check it."""
        assert "citation" in REGISTER_GUIDANCE[Audience.CITIZEN].lower()

    def test_no_register_licenses_a_softer_standard(self):
        """
        The register is about vocabulary and what to spell out. If one of these
        starts talking about how firmly something may be asserted, the line
        between "written for" and "checked for" has been crossed.
        """
        for guidance in REGISTER_GUIDANCE.values():
            lowered = guidance.lower()
            assert "you may assume" not in lowered
            assert "without a source" not in lowered


class TestJudgeMode:
    """
    A tool that lays out considerations is useful to a court. A tool that
    suggests the outcome is not, and would be improper however accurate.
    """

    def test_the_prohibition_is_explicit(self):
        guidance = REGISTER_GUIDANCE[Audience.JUDGE]
        assert "must NOT suggest an outcome" in guidance

    @pytest.mark.parametrize(
        "forbidden", ["bail", "sentence", "which argument is stronger", "decided"]
    )
    def test_it_names_the_ways_an_outcome_leaks(self, forbidden):
        assert forbidden in REGISTER_GUIDANCE[Audience.JUDGE].lower() or (
            forbidden in REGISTER_GUIDANCE[Audience.JUDGE]
        )

    def test_it_forbids_implying_one_as_well_as_stating_one(self):
        """Ordering and emphasis are how a recommendation survives a rule that
        only bans stating one."""
        guidance = REGISTER_GUIDANCE[Audience.JUDGE]
        assert "implication" in guidance
        assert "emphasis" in guidance

    def test_the_other_registers_carry_no_such_prohibition(self):
        for audience in (Audience.CITIZEN, Audience.LAWYER):
            assert "must NOT suggest an outcome" not in REGISTER_GUIDANCE[audience]


class TestTheRegisterReachesOnlySynthesis:
    def test_retrieval_cannot_see_the_audience(self):
        """Structural: there is no parameter to pass it through."""
        assert "audience" not in inspect.signature(vector_service.VectorService.search).parameters

    def test_verification_cannot_see_the_audience(self):
        assert "audience" not in inspect.signature(claim_verifier.verify).parameters
        assert "audience" not in inspect.signature(claim_verifier.verify_claim).parameters

    def test_the_same_query_retrieves_the_same_law_for_every_register(self, service):
        for audience in Audience:
            service.answer("what is the punishment for murder", audience=audience)
        calls = service.vector_service.search.call_args_list
        assert len({str(call.kwargs) for call in calls}) == 1

    def test_the_register_appears_in_the_system_prompt(self, service):
        service.answer("what is the punishment for murder", audience=Audience.JUDGE)
        system = service.llm_service.generate.call_args.kwargs["system"]
        assert "WHO YOU ARE WRITING FOR" in system
        assert "must NOT suggest an outcome" in system

    def test_a_different_register_gives_a_different_system_prompt(self, service):
        prompts = []
        for audience in Audience:
            service.llm_service.generate.reset_mock()
            service.answer("q", audience=audience)
            prompts.append(service.llm_service.generate.call_args.kwargs["system"])
        assert len(set(prompts)) == len(Audience)

    def test_the_user_prompt_is_identical_across_registers(self, service):
        """Only the system layer changes. The question, the context and the
        instructions are the same for everyone."""
        prompts = []
        for audience in Audience:
            service.llm_service.generate.reset_mock()
            service.answer("q", audience=audience)
            prompts.append(service.llm_service.generate.call_args.kwargs["prompt"])
        assert len(set(prompts)) == 1

    def test_the_sources_are_identical_across_registers(self, service):
        results = [
            service.answer("what is the punishment for murder", audience=a) for a in Audience
        ]
        assert len({str(r.sources) for r in results}) == 1

    def test_the_verdicts_are_identical_across_registers(self, service):
        """Same claims in, same verdicts out. Nothing is verified more leniently
        for one audience."""
        results = [
            service.answer("what is the punishment for murder", audience=a) for a in Audience
        ]
        assert len({str([v.model_dump() for v in r.verdicts]) for r in results}) == 1

    def test_the_register_is_recorded_in_the_trace(self, service):
        result = service.answer("q", audience=Audience.LAWYER)
        assert result.trace["audience"] == "lawyer"

    def test_the_default_is_the_citizen(self, service):
        assert service.answer("q").trace["audience"] == "citizen"


class TestLayer:
    def test_it_is_appendable(self):
        layer = register_layer(Audience.CITIZEN)
        assert layer.startswith("\n\n")
        assert "WHO YOU ARE WRITING FOR" in layer
