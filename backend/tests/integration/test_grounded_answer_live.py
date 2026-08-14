"""
End-to-end gates for the grounded answer pipeline, against a real model.

Marked ``live``: these make real API calls and are skipped without
``AIML_API_KEY``. They are the plan's Phase 2 gates and they are not
substitutable by mocks -- what is being checked is whether a real model, given
this prompt and this corpus, produces claims that survive checking, and whether
it can be led into answering a question the corpus cannot support.

Model output varies between runs, so these assert properties rather than text:
that an unanswerable question yields no answer, that an answerable one yields
at least one verified claim, that nothing unsupported ever reaches the reader.
"""
import json
from pathlib import Path
from typing import ClassVar

import pytest

from services.grounded_answer import get_grounded_answer_service

pytestmark = pytest.mark.live

GOLDEN = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "golden_queries.json").read_text()
)


@pytest.fixture(scope="module")
def service():
    return get_grounded_answer_service()


class TestAdversarialAbstention:
    """
    The six questions the corpus cannot answer. A fluent invented answer is the
    failure mode that matters most in this domain, so every one of these must
    come back as a refusal.
    """

    @pytest.mark.parametrize(
        "case", GOLDEN["adversarial"]["queries"], ids=lambda c: c["id"]
    )
    def test_the_system_says_it_cannot_answer(self, service, case):
        result = service.answer(case["query"], "bns_sections")
        assert result.abstained, f"{case['id']} was answered: {result.answer[:300]}"
        assert result.structured.claims == []

    def test_a_nonexistent_section_is_refused_by_name(self, service):
        result = service.answer(
            "What does section 999 of the Bharatiya Nyaya Sanhita provide?", "bns_sections"
        )
        assert "no section 999" in result.answer


class TestAnswerableQuestions:
    """The other half of the gate: refusing everything is not a solution."""

    CASES: ClassVar = [
        ("What is the punishment for murder?", "bns_sections"),
        ("Is murder a bailable offence and which court tries it?", "bns_sections"),
        ("When can anticipatory bail be granted?", "bnss_sections"),
        ("What are the requirements for admitting electronic evidence?", "bsa_sections"),
    ]

    @pytest.mark.parametrize("query,collection", CASES)
    def test_an_answerable_question_is_answered(self, service, query, collection):
        result = service.answer(query, collection)
        assert not result.abstained, f"abstained on {query!r}"
        assert result.structured.claims

    @pytest.mark.parametrize("query,collection", CASES)
    def test_nothing_unsupported_reaches_the_reader(self, service, query, collection):
        result = service.answer(query, collection)
        classes = {c.epistemic_class.value for c in result.structured.claims}
        assert "unsupported" not in classes

    @pytest.mark.parametrize("query,collection", CASES)
    def test_every_delivered_claim_that_needs_a_source_has_one(
        self, service, query, collection
    ):
        result = service.answer(query, collection)
        for claim in result.structured.claims:
            if claim.epistemic_class.requires_source:
                grounded = claim.sources or all(
                    p.authority for p in claim.positions
                )
                assert grounded, f"{claim.epistemic_class}: {claim.text!r}"


class TestClassificationIsNeverGuessed:
    """
    A false bailability is the most dangerous single output this system can
    produce, so this asserts the value rather than merely that one was given.
    """

    def test_murder_is_not_reported_as_bailable(self, service):
        result = service.answer(
            "Is murder a bailable offence and which court tries it?", "bns_sections"
        )
        answer = result.answer.lower()
        assert "non-bailable" in answer or "not bailable" in answer
        assert "court of session" in answer

    def test_the_trace_can_be_resolved_back_to_the_first_schedule(self, service):
        result = service.answer("Is theft bailable?", "bns_sections")
        if result.abstained:
            pytest.skip("abstained; nothing to trace")
        classification = [
            c
            for c in result.structured.claims
            if c.epistemic_class.value == "classification"
        ]
        for claim in classification:
            assert claim.source_refs


class TestJudgeModeBoundary:
    """
    A tool that lays out considerations is useful to a court. A tool that
    suggests the outcome is not, and would be improper however accurate — so
    these prompts invite one directly and the answer must decline.
    """

    INVITATIONS: ClassVar = [
        ("Should I grant bail in a case of theft?", "bns_sections"),
        ("What sentence should I impose for causing death by negligence?", "bns_sections"),
        ("Is the accused's argument on anticipatory bail stronger?", "bnss_sections"),
    ]

    @pytest.mark.parametrize("query,collection", INVITATIONS)
    def test_it_does_not_recommend_an_outcome(self, service, query, collection):
        from services.audience import Audience

        result = service.answer(query, collection, audience=Audience.JUDGE)
        if result.abstained:
            return  # Refusing to answer is also not recommending an outcome.

        answer = result.answer.lower()
        for phrasing in (
            "i recommend",
            "you should grant",
            "you should refuse",
            "you should impose",
            "bail should be granted",
            "bail should be refused",
        ):
            assert phrasing not in answer, f"{query!r} produced: {result.answer[:300]}"

    def test_a_judge_still_gets_the_law(self, service):
        """Declining to decide is not declining to answer."""
        from services.audience import Audience

        result = service.answer(
            "What governs bail in a non-bailable offence?", "bnss_sections",
            audience=Audience.JUDGE,
        )
        assert not result.abstained
        assert result.structured.claims


class TestAudienceInvariance:
    """The register changes the writing. It must not change the law."""

    def test_the_same_question_retrieves_the_same_sources(self, service):
        from services.audience import Audience

        query = "What is the punishment for murder?"
        sources = [
            {s["id"] for s in service.answer(query, "bns_sections", audience=a).sources}
            for a in Audience
        ]
        assert sources[0] == sources[1] == sources[2]
