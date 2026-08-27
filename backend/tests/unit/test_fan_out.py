"""
The multi-agent path through the compiled graph.

The assertions that matter are about what does *not* happen. A fan-out costs
roughly eight model calls against the single pass's one, and the failure mode
is not a wrong answer — it is the expensive path quietly becoming the default,
which nothing in an answer would reveal.

So: an ordinary question must never reach the planner, a draft must never be
fanned out, and everything the specialists gather must still go through the
same verifier as a single-pass answer.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from agents.contracts import (
    Complexity,
    Evidence,
    Plan,
    PlanStep,
    SpecialistKind,
)
from agents.intent_classifier import IntentClassifier
from agents.legal_agent import LegalAgent
from agents.specialists import merge_evidence
from agents.state import create_initial_state


@pytest.fixture
def agent():
    return LegalAgent(IntentClassifier(), MagicMock(), llm_service=MagicMock())


@pytest.fixture(autouse=True)
def store(monkeypatch):
    """
    A stubbed vector store.

    These tests are about routing and cost, not retrieval quality — which
    `eval_retrieval.py` measures exactly over the whole golden set. Against the
    real store they took 96 seconds to assert which nodes ran.
    """
    service = MagicMock()
    service.search.return_value = {
        "documents": ["text of BNSS 480"],
        "metadatas": [
            {
                "short_name": "BNSS",
                "section_number": "480",
                "parent_id": "bnss_480",
                "title": "When bail may be taken",
            }
        ],
        "distances": [0.2],
        "ids": ["bnss_480"],
    }
    monkeypatch.setattr(
        "agents.specialists.retrieval.get_vector_service", lambda: service
    )
    return service


@pytest.fixture
def no_follow_up():
    """A follow-up planner that always says the material is sufficient."""
    service = MagicMock()
    service.generate.return_value = json.dumps({"queries": []})
    with patch("agents.specialists.retrieval.llm_service", service):
        yield service


@pytest.fixture
def grounded():
    with patch("agents.legal_agent.get_grounded_answer_service") as accessor:
        accessor.return_value.answer.return_value = MagicMock(
            answer="answer",
            sources=[],
            abstained=False,
            graph_context={},
            structured=MagicMock(claims=[]),
            metrics=MagicMock(to_dict=lambda: {}, unsupported=0),
            verdicts=[],
            trace={},
        )
        yield accessor.return_value


def a_plan(*specialists):
    return Plan(
        complexity=Complexity.COMPLEX,
        steps=[PlanStep(specialist=s, question="q") for s in specialists],
    )


class TestTheCheapPathStaysCheap:
    @pytest.mark.asyncio
    async def test_an_ordinary_question_never_reaches_the_planner(self, agent):
        with patch("agents.legal_agent.plan_query") as planner:
            state = await agent.graph.ainvoke(
                create_initial_state("punishment for murder")
            )

        planner.assert_not_called()
        assert state["complexity"] == Complexity.SIMPLE.value
        assert state["evidence"] == []

    @pytest.mark.asyncio
    async def test_a_draft_request_is_never_fanned_out(self, agent):
        """
        Only a question *about the law* is escalated. Drafting, analysis, chat
        and live research go to their own nodes whatever triage thought —
        fanning one out would buy nothing but latency.
        """
        with patch("agents.legal_agent.plan_query") as planner:
            await agent.graph.ainvoke(
                create_initial_state(
                    "draft a bail application and compare it with the last one"
                )
            )

        planner.assert_not_called()

    @pytest.mark.asyncio
    async def test_triage_records_its_reason(self, agent):
        """An escalation must be arguable after the fact, not a silent cost."""
        state = await agent.graph.ainvoke(create_initial_state("punishment for theft"))
        assert state["metadata"]["triage"]["reason"]


class TestFanOut:
    @pytest.mark.asyncio
    async def test_a_complex_question_dispatches_every_planned_specialist(
        self, agent, no_follow_up, grounded
    ):
        plan = a_plan(
            SpecialistKind.STATUTE, SpecialistKind.OFFENCE, SpecialistKind.DOCTRINE
        )
        with patch("agents.legal_agent.plan_query", return_value=plan):
            state = await agent.graph.ainvoke(
                create_initial_state(
                    "what does BNSS 480 say and what did the Supreme Court hold"
                )
            )

        assert set(state["tool_results"]) >= {"statute", "offence", "doctrine"}
        assert state["evidence"]

    @pytest.mark.asyncio
    async def test_the_cost_of_each_specialist_is_recorded(
        self, agent, no_follow_up, grounded
    ):
        """The fan-out's whole risk is cost. A number nobody can see is a
        number nobody notices growing."""
        plan = a_plan(SpecialistKind.STATUTE, SpecialistKind.OFFENCE)
        with patch("agents.legal_agent.plan_query", return_value=plan):
            state = await agent.graph.ainvoke(
                create_initial_state("BNSS 480 and the cases on it")
            )

        assert state["tool_results"]["offence"]["model_calls"] == 0, (
            "the First Schedule lookup must stay free"
        )
        assert "retrievals" in state["tool_results"]["statute"]

    @pytest.mark.asyncio
    async def test_the_gathered_evidence_goes_through_the_verifier(
        self, agent, no_follow_up, grounded
    ):
        """
        Specialists change what reaches the prompt and nothing about what is
        checked afterwards. If this ever stops being true, part of an answer is
        verified and part is not, with nothing in the output to say which.
        """
        plan = a_plan(SpecialistKind.STATUTE)
        with patch("agents.legal_agent.plan_query", return_value=plan):
            await agent.graph.ainvoke(
                create_initial_state("BNSS 480 and the cases on it")
            )

        grounded.answer.assert_called_once()
        assert grounded.answer.call_args.args[4] is not None, (
            "the gathered material was passed in rather than re-retrieved"
        )

    @pytest.mark.asyncio
    async def test_an_empty_plan_does_not_stall_the_graph(self, agent, grounded):
        with patch("agents.legal_agent.plan_query", return_value=Plan(steps=[])):
            state = await agent.graph.ainvoke(
                create_initial_state("BNSS 480 and the cases on it")
            )
        assert state["final_response"] or state["tool_results"]

    @pytest.mark.asyncio
    async def test_a_fan_out_that_finds_nothing_falls_back(self, agent, grounded):
        """
        A fan-out that came back empty says the plan was wrong, not that the
        corpus cannot answer the question.
        """
        plan = a_plan(SpecialistKind.OFFENCE)
        with patch("agents.legal_agent.plan_query", return_value=plan):
            state = await agent.graph.ainvoke(
                create_initial_state(
                    "is the law on BNSS 480 settled, and what about the weather"
                )
            )
        assert state["tool_results"]


class TestMergeEvidence:
    @staticmethod
    def _sections(*rows):
        return Evidence(
            specialist=SpecialistKind.STATUTE,
            kind="sections",
            payload={
                "documents": [f"text {p}" for p, _ in rows],
                "metadatas": [{"parent_id": p, "chunk_index": 0} for p, _ in rows],
                "distances": [d for _, d in rows],
            },
        )

    def test_the_same_chunk_found_twice_appears_once(self):
        """
        Two specialists asking adjacent questions overlap. Left in, the
        duplicate takes two prompt slots and reads to the model as
        corroboration — which is exactly wrong: one chunk found twice is not
        two sources agreeing.
        """
        merged = merge_evidence(
            [self._sections(("bnss_480", 0.2)), self._sections(("bnss_480", 0.3))]
        )
        assert merged["ids"] == ["bnss_480#0"]

    def test_results_are_ordered_best_first(self):
        """Fan-out completion order is arbitrary; without an explicit sort the
        prompt's ordering depends on which specialist finished first."""
        merged = merge_evidence(
            [self._sections(("b", 0.9)), self._sections(("a", 0.1))]
        )
        assert merged["distances"] == [0.1, 0.9]

    def test_classification_and_doctrine_are_not_merged_into_the_chunks(self):
        """
        They reach the prompt through the graph block under their own headings.
        Flattened into the retrieved chunks, a First Schedule row becomes
        something the model quotes as if it were statutory text.
        """
        merged = merge_evidence(
            [
                Evidence(
                    specialist=SpecialistKind.OFFENCE,
                    kind="classification",
                    payload={"section": "BNS 103"},
                )
            ]
        )
        assert merged["documents"] == []

    def test_no_evidence_merges_to_an_empty_result(self):
        assert merge_evidence([])["documents"] == []
