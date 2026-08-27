"""
Deciding how much machinery a question deserves.

The gate that matters here is a **cost** gate, and it is the whole golden set:
a fanned-out query costs roughly eight model calls against the single-pass
path's one, so triage escalating freely would multiply the cost of every
ordinary legal question by eight for an answer the one-pass path already gets
right. Retrieval sits at recall@3 1.000 and every claim is verified either way.

So the assertions run in both directions: ordinary questions must stay cheap,
and genuinely contested ones must not be answered with one confident voice.
"""
import json
from pathlib import Path

import pytest

from agents.contracts import Complexity
from agents.triage import touches_contested_section, triage

GOLDEN = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "golden_queries.json").read_text()
)


class TestTheCostGate:
    """The fixture is ordinary legal questions. If triage escalates them, the
    cost model is wrong, and it is wrong silently."""

    @pytest.mark.parametrize(
        "query", [q["query"] for q in GOLDEN["queries"]], ids=[q["id"] for q in GOLDEN["queries"]]
    )
    def test_every_answerable_golden_query_stays_simple(self, query):
        complexity, reason = triage(query)
        assert complexity is Complexity.SIMPLE, f"{query!r} escalated: {reason}"

    @pytest.mark.parametrize(
        "query",
        [q["query"] for q in GOLDEN["adversarial"]["queries"]],
        ids=[q["id"] for q in GOLDEN["adversarial"]["queries"]],
    )
    def test_adversarial_queries_stay_simple(self, query):
        """They abstain whatever path they take, so escalating one buys eight
        model calls' worth of nothing."""
        assert triage(query)[0] is Complexity.SIMPLE


class TestContestedDetection:
    def test_the_user_asking_outright_wins(self):
        """The only signal that is never wrong about intent."""
        complexity, reason = triage("show me both sides on anticipatory bail")
        assert complexity is Complexity.CONTESTED
        assert "asks for both sides" in reason

    def test_a_curated_contested_section_escalates(self):
        """
        `graph.contested_sections()` has existed since the graph was built and
        its docstring has always said "this is the list the contested path
        consults". Nothing consulted it until now.
        """
        complexity, reason = triage("what does BNSS 480 require for bail")
        assert complexity is Complexity.CONTESTED
        assert "BNSS 480" in reason

    def test_a_constitutional_challenge_escalates(self):
        assert triage("is the twin-condition bail bar constitutional")[0] is (
            Complexity.CONTESTED
        )

    def test_asking_whether_the_law_is_settled_escalates(self):
        assert triage("is the law on preventive detention settled")[0] is (
            Complexity.CONTESTED
        )

    def test_a_settled_proposition_using_constitutional_words_does_not(self):
        """
        The false positive this was built with and then measured out.

        "privacy is a fundamental right" is settled -- decided unanimously by
        nine judges in Puttaswamy -- and it was escalating because the first
        pattern fired on any mention of a fundamental right. Asking what a case
        held is not asking whether a provision survives scrutiny.
        """
        assert triage("privacy is a fundamental right")[0] is Complexity.SIMPLE

    def test_an_uncontested_section_does_not_escalate(self):
        assert triage("what does BNS 103 provide")[0] is Complexity.SIMPLE


class TestComplexDetection:
    @pytest.mark.parametrize(
        "query",
        [
            "compare theft and extortion",
            "what is the difference between culpable homicide and murder",
            "what does BNSS 187 say and also what about BNSS 193",
        ],
    )
    def test_multi_part_questions_are_complex(self, query):
        assert triage(query)[0] is Complexity.COMPLEX

    def test_a_question_spanning_statute_and_case_law_is_complex(self):
        complexity, reason = triage(
            "what does section 35 of the BNSS say and what did the Supreme Court hold"
        )
        assert complexity is Complexity.COMPLEX
        assert "statute and case law" in reason


class TestContestedSectionLookup:
    def test_it_reads_the_curated_list(self):
        assert touches_contested_section("BNSS 480 bail") == ["BNSS 480"]

    def test_a_query_citing_nothing_returns_nothing(self):
        assert touches_contested_section("what is bail") == []

    def test_an_uncontested_citation_returns_nothing(self):
        assert touches_contested_section("BNS 103 murder") == []


class TestNoModelCall:
    def test_triage_is_pure(self):
        """
        No model call, deliberately. A triage step that costs a model call has
        already spent a meaningful fraction of what escalating costs, so it
        cannot pay for itself on the queries it declines.
        """
        import inspect

        import agents.triage as module

        source = inspect.getsource(module)
        assert "llm_service" not in source
        assert "generate" not in source

    def test_empty_and_none_are_simple(self):
        assert triage("")[0] is Complexity.SIMPLE
        assert triage(None)[0] is Complexity.SIMPLE
