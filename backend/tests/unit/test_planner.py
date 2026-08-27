"""
Planning which specialists a complex query needs.

The planner is the one component here whose mistakes are cheap: it emits a
``Plan`` and never states any law, so choosing wrongly costs a wasted
specialist call rather than a wrong statement about a provision. Which is why
everything below is about *degrading well* rather than about planning well —
the expensive failure is a planner that turns a answerable question into an
error or an abstention.
"""
import json
from unittest.mock import MagicMock

import pytest

from agents.contracts import Complexity, SpecialistKind
from agents.planner import MAX_STEPS, parse_plan, plan_query


def step(specialist, question="q", reason="r"):
    return {"specialist": specialist, "question": question, "reason": reason}


def payload(*specialists):
    return json.dumps({"steps": [step(s) for s in specialists]})


def kinds(plan):
    return [s.specialist.value for s in plan.steps]


class TestParsing:
    def test_a_clean_plan_is_read(self):
        plan = parse_plan(payload("statute", "case_law", "offence"), "q")
        assert kinds(plan) == ["statute", "case_law", "offence"]

    def test_one_unusable_step_does_not_discard_the_others(self):
        """
        The bug fixed in 9a92ac1, arriving in a new place. A model labelled one
        claim with a class outside the enum and the ValidationError took three
        good claims with it, abstaining on a question the corpus answers
        directly. A planner naming three researchers and inventing one should
        get its three.
        """
        plan = parse_plan(payload("statute", "telepathy", "offence"), "q")
        assert kinds(plan) == ["statute", "offence"]

    def test_a_repeated_researcher_is_dispatched_once(self):
        assert kinds(parse_plan(payload("statute", "statute"), "q")) == ["statute"]

    def test_a_fenced_response_is_unwrapped(self):
        raw = f"```json\n{payload('statute')}\n```"
        assert kinds(parse_plan(raw, "q")) == ["statute"]

    def test_json_wrapped_in_prose_is_still_read(self):
        raw = f"Here is the plan:\n{payload('statute')}\nLet me know."
        assert kinds(parse_plan(raw, "q")) == ["statute"]

    def test_a_bare_list_is_accepted(self):
        raw = json.dumps([step("statute")])
        assert kinds(parse_plan(raw, "q")) == ["statute"]

    def test_too_many_steps_are_trimmed(self):
        raw = payload("statute", "case_law", "offence", "doctrine", "drafting", "analysis")
        assert len(parse_plan(raw, "q").steps) == MAX_STEPS


class TestDegrading:
    """A planning failure says nothing about whether the corpus can answer the
    question, so none of these may raise or return nothing."""

    @pytest.mark.parametrize(
        "raw",
        [
            "I'm sorry, I can't help with that.",
            "",
            "{}",
            json.dumps({"steps": "nonsense"}),
            json.dumps({"steps": []}),
            json.dumps({"steps": [step("telepathy")]}),
        ],
    )
    def test_an_unusable_response_falls_back_to_a_working_plan(self, raw):
        plan = parse_plan(raw, "what is the punishment for theft")
        assert plan.steps, "a planning failure must not produce an empty plan"
        assert SpecialistKind.STATUTE in plan.specialists

    def test_the_fallback_includes_the_free_lookup(self):
        """`offence` reads the First Schedule with no model involved. Including
        it costs nothing, so a default plan always does."""
        plan = parse_plan("garbage", "q")
        assert SpecialistKind.OFFENCE in plan.specialists

    def test_a_planner_that_raises_still_returns_a_plan(self):
        service = MagicMock()
        service.generate.side_effect = RuntimeError("provider down")

        plan = plan_query("what is the punishment for theft", service=service)
        assert plan.steps


class TestPlanQuery:
    def test_the_complexity_triage_decided_is_preserved(self):
        """The planner is not asked to re-litigate triage's decision."""
        service = MagicMock()
        service.generate.return_value = payload("statute")

        plan = plan_query("q", complexity=Complexity.CONTESTED, service=service)
        assert plan.complexity is Complexity.CONTESTED

    def test_the_contested_question_is_carried_through_untouched(self):
        service = MagicMock()
        service.generate.return_value = payload("statute", "case_law")

        plan = plan_query(
            "is the twin-condition bail bar constitutional",
            complexity=Complexity.CONTESTED,
            contested_question="whether the twin conditions survive Article 21",
            service=service,
        )
        assert plan.contested_question == (
            "whether the twin conditions survive Article 21"
        )

    def test_specialists_still_run_for_a_contested_query(self):
        """
        Both advocates need authority to argue from, and neither should be
        retrieving it for the first time mid-argument.
        """
        service = MagicMock()
        service.generate.return_value = payload("statute", "case_law")

        plan = plan_query("q", complexity=Complexity.CONTESTED, service=service)
        assert len(plan.steps) == 2

    def test_generation_is_deterministic(self):
        """A plan is a routing decision. Sampling it would make the same
        question cost different amounts on different days."""
        service = MagicMock()
        service.generate.return_value = payload("statute")

        plan_query("q", service=service)
        assert service.generate.call_args.kwargs["temperature"] == 0.0

    def test_it_makes_exactly_one_call(self):
        service = MagicMock()
        service.generate.return_value = payload("statute")

        plan_query("q", service=service)
        assert service.generate.call_count == 1


class TestPromptContract:
    def test_the_step_cap_in_the_prompt_matches_the_code(self):
        """Two places would drift; the prompt is generated from the constant."""
        from agents.planner import PLANNER_INSTRUCTIONS

        assert f"At most {MAX_STEPS} steps" in PLANNER_INSTRUCTIONS

    def test_the_planner_is_told_not_to_state_law(self):
        from agents.planner import PLANNER_SYSTEM

        assert "do not state any law" in PLANNER_SYSTEM.lower()

    def test_the_free_lookups_are_described_as_free(self):
        """The planner should prefer them, and it will only do that if it is
        told they cost nothing."""
        from agents.planner import PLANNER_INSTRUCTIONS

        assert "cost nothing" in PLANNER_INSTRUCTIONS
