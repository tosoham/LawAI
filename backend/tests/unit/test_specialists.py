"""
The specialists a plan dispatches to.

Two properties are worth more than everything else here and are asserted
hardest:

* **the deterministic specialists make no model call.** `offence` reads the
  First Schedule and `doctrine` reads the curated graph, so they are free and
  cannot hallucinate. If a refactor ever puts a model in either path, the cost
  and risk profile of the whole fan-out changes silently, and this is what
  catches it.
* **a specialist never returns a conclusion.** Six agents emitting their own
  answers would put generation after the point the verifier runs, so part of an
  answer would be checked and part would not, with nothing to say which.

Everything else is about bounding the retrieve loop, because an unbounded one
is how a single question costs forty model calls.
"""
import json
from unittest.mock import MagicMock

import pytest

import agents.specialists  # noqa: F401  (registers every runner)
from agents.contracts import AgentError, Evidence, PlanStep, SpecialistKind
from agents.specialists.base import (
    RetrievalBudget,
    SpecialistResult,
    run_specialist,
)
from agents.specialists.retrieval import run_case_law, run_statute


def step(kind, question="grounds for anticipatory bail"):
    return PlanStep(specialist=kind, question=question)


def model_returning(*queries):
    service = MagicMock()
    service.generate.return_value = json.dumps({"queries": list(queries)})
    return service


def _hit(section: str, parent: str):
    return {
        "documents": [f"text of {section}"],
        "metadatas": [
            {
                "short_name": "BNSS",
                "section_number": section,
                "parent_id": parent,
                "title": f"title {section}",
            }
        ],
        "distances": [0.1],
        "ids": [parent],
    }


@pytest.fixture
def store(monkeypatch):
    """
    A stubbed vector store, returning a different section per query.

    These tests are about the retrieve loop's bounds, not about what BNSS 482
    contains -- retrieval itself is measured by `eval_retrieval.py`, exactly and
    over the whole golden set, which a unit test cannot improve on. Against the
    real store they took 3.6 minutes and re-tested the embedder 25 times.
    """
    seen: dict[str, int] = {}

    def search(collection, query, **kwargs):
        seen[query] = seen.get(query, len(seen) + 1)
        return _hit(str(400 + seen[query]), f"bnss_{400 + seen[query]}")

    service = MagicMock()
    service.search.side_effect = search
    monkeypatch.setattr(
        "agents.specialists.retrieval.get_vector_service", lambda: service
    )
    return service


class TestBudget:
    def test_it_refuses_once_spent(self):
        budget = RetrievalBudget(limit=2)
        assert budget.spend() and budget.spend()
        assert not budget.spend()
        assert budget.exhausted

    def test_a_shared_budget_is_shared(self):
        """Several specialists may run against one budget, and the cap is on
        the query as a whole rather than per agent."""
        budget = RetrievalBudget(limit=1)
        budget.spend()
        assert not budget.spend()


class TestDeterministicSpecialists:
    """Free, identical on every run, and incapable of inventing anything."""

    def test_offence_classification_costs_no_model_call(self):
        result = run_specialist(
            step(SpecialistKind.OFFENCE, "is murder bailable"), "is murder bailable"
        )
        assert result.evidence
        assert result.model_calls == 0
        assert result.retrievals == 0

    def test_offence_resolves_the_section_that_punishes(self):
        result = run_specialist(
            step(SpecialistKind.OFFENCE, "is murder bailable"), "is murder bailable"
        )
        payload = result.evidence[0].payload
        assert payload["act"] == "BNS"
        assert payload["number"] == "103", "murder is punished by 103, defined by 101"

    def test_offence_cites_the_first_schedule(self):
        result = run_specialist(
            step(SpecialistKind.OFFENCE, "is theft bailable"), "is theft bailable"
        )
        assert "First Schedule" in result.evidence[0].provenance

    def test_doctrine_costs_no_model_call(self):
        result = run_specialist(step(SpecialistKind.DOCTRINE, "BNSS 480"), "BNSS 480")
        assert result.model_calls == 0
        assert result.retrievals == 0

    def test_doctrine_passes_contested_through_untouched(self):
        """
        `doctrines.json` carries no precedential status by design. Where
        authority splits it says so and names both sides without declaring a
        winner, and that must survive the trip through an agent.
        """
        result = run_specialist(step(SpecialistKind.DOCTRINE, "BNSS 480"), "BNSS 480")
        doctrines = result.evidence[0].payload["doctrines"]
        contested = [d for d in doctrines if d["contested"]]
        assert contested
        assert contested[0]["contest_note"]

    def test_a_query_naming_no_offence_returns_nothing_rather_than_guessing(self):
        result = run_specialist(
            step(SpecialistKind.OFFENCE, "what is the weather"), "what is the weather"
        )
        assert result.evidence == []
        assert result.errors == []


@pytest.mark.usefixtures("store")
class TestIterativeRetrieval:
    """The reason these are agents rather than fixed calls — and its bounds."""

    def test_a_follow_up_naming_new_material_is_pursued(self):
        service = model_returning("default bail after sixty days")
        budget = RetrievalBudget()

        result = run_statute(step(SpecialistKind.STATUTE), "q", budget, service=service)

        assert result.retrievals == 2
        assert len(result.evidence) > 3, "the follow-up added material"

    def test_no_follow_up_is_the_common_and_complete_answer(self):
        service = model_returning()
        result = run_statute(
            step(SpecialistKind.STATUTE), "q", RetrievalBudget(), service=service
        )
        assert result.retrievals == 1

    def test_a_follow_up_returning_nothing_new_ends_the_loop(self):
        """
        A model asked what else it needs will always find something to ask for.
        A repeat is the loop saying it is finished; pursuing it would inflate
        the context and make the retrieval count look like work.
        """
        service = model_returning("grounds for anticipatory bail")
        result = run_statute(
            step(SpecialistKind.STATUTE), "q", RetrievalBudget(), service=service
        )
        # Three collections searched once each; the repeat added nothing.
        assert len(result.evidence) == 3, "no duplicates were kept"

    def test_the_budget_caps_total_corpus_queries(self):
        service = model_returning("a", "b")
        budget = RetrievalBudget(limit=2)

        result = run_statute(step(SpecialistKind.STATUTE), "q", budget, service=service)

        assert result.retrievals <= 2
        assert budget.exhausted

    def test_a_budget_of_one_does_not_even_plan_a_follow_up(self):
        """Short-circuiting before the model saves the cost, not just the query."""
        service = model_returning("something")
        result = run_statute(
            step(SpecialistKind.STATUTE), "q", RetrievalBudget(limit=1), service=service
        )
        assert result.model_calls == 0
        service.generate.assert_not_called()

    def test_an_exhausted_budget_yields_nothing_rather_than_failing(self):
        budget = RetrievalBudget(limit=1)
        budget.spend()

        result = run_statute(step(SpecialistKind.STATUTE), "q", budget, service=MagicMock())
        assert result.evidence == []
        assert result.errors == []

    def test_a_failing_follow_up_planner_keeps_what_was_found(self):
        service = MagicMock()
        service.generate.side_effect = RuntimeError("provider down")

        result = run_statute(step(SpecialistKind.STATUTE), "q", RetrievalBudget(), service=service)

        assert result.evidence, "the first retrieval survives"
        assert result.errors == [], "an optional refinement failing is not an error"

    @pytest.mark.parametrize(
        "raw", ["not json", "{}", json.dumps({"queries": "nope"}), ""]
    )
    def test_an_unusable_follow_up_response_ends_the_loop(self, raw):
        service = MagicMock()
        service.generate.return_value = raw

        result = run_statute(step(SpecialistKind.STATUTE), "q", RetrievalBudget(), service=service)
        assert result.retrievals == 1


@pytest.mark.usefixtures("store")
class TestEvidenceNotConclusions:
    def test_a_statute_specialist_returns_retrieved_text(self):
        result = run_statute(
            step(SpecialistKind.STATUTE), "q", RetrievalBudget(), service=model_returning()
        )
        payload = result.evidence[0].payload
        assert "documents" in payload and "metadatas" in payload

    def test_provenance_survives(self):
        """Live material is never blended with corpus material downstream, so
        where a thing came from has to travel with it."""
        result = run_statute(
            step(SpecialistKind.STATUTE), "q", RetrievalBudget(), service=model_returning()
        )
        assert {e.provenance for e in result.evidence} <= {
            "bns_sections",
            "bnss_sections",
            "bsa_sections",
        }
        assert all(e.provenance for e in result.evidence)

    def test_case_law_returns_text_and_says_nothing_about_holdings(self):
        """
        The corpus records which sections a judgement is an authority on for
        only 27 of 300 (see docs/ATTRIBUTION_GAP.md), and that relation cannot
        be derived from the text. A specialist summarising holdings would be
        asserting exactly what nothing can check.
        """
        result = run_case_law(
            step(SpecialistKind.CASE_LAW), "q", RetrievalBudget(), service=model_returning()
        )
        assert result.evidence[0].kind == "judgements"
        assert set(result.evidence[0].payload) == {
            "query",
            "documents",
            "metadatas",
            "distances",
        }


class TestFailSoft:
    def test_an_unregistered_specialist_is_recorded_not_raised(self):
        from agents.specialists import base

        saved = base._RUNNERS.pop(SpecialistKind.DRAFTING, None)
        try:
            result = run_specialist(step(SpecialistKind.DRAFTING), "q")
            assert result.errors and result.evidence == []
            assert result.errors[0].stage == "dispatch"
        finally:
            if saved is not None:
                base._RUNNERS[SpecialistKind.DRAFTING] = saved

    def test_a_specialist_that_raises_is_recorded_not_raised(self):
        from agents.specialists import base

        saved = base._RUNNERS.get(SpecialistKind.STATUTE)

        def boom(step, query, budget):
            raise RuntimeError("kaboom")

        base._RUNNERS[SpecialistKind.STATUTE] = boom
        try:
            result = run_specialist(step(SpecialistKind.STATUTE), "q")
            assert result.errors[0].message == "kaboom"
            assert result.evidence == []
        finally:
            base._RUNNERS[SpecialistKind.STATUTE] = saved


class TestResultMerging:
    def test_costs_add_up(self):
        a = SpecialistResult(
            evidence=[Evidence(specialist=SpecialistKind.STATUTE, kind="sections")],
            retrievals=2,
            model_calls=1,
        )
        b = SpecialistResult(
            errors=[AgentError(specialist=SpecialistKind.CASE_LAW, message="x")],
            retrievals=1,
            model_calls=1,
        )
        merged = a.merged_into(b)

        assert merged.retrievals == 3
        assert merged.model_calls == 2
        assert len(merged.evidence) == 1
        assert len(merged.errors) == 1
