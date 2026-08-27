"""
State that survives parallel writes.

The graph was a router until now -- classify, run exactly one tool node, format
-- so no key ever took two updates in one superstep and a bare ``dict`` was the
honest declaration. Fan-out changes that, and it changes it at runtime rather
than at import: LangGraph raises ``InvalidUpdateError`` the first time two
nodes write the same unannotated key, which is the first time anyone runs a
complex query.

Both failures below were reproduced against the real graph before being fixed,
and both are silent in ordinary use -- the second one especially, because
``evidence`` is always empty on the router path and doubling an empty list
looks exactly like working.
"""
import operator

import pytest
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from agents.contracts import (
    AgentError,
    Complexity,
    Evidence,
    Plan,
    PlanStep,
    Position,
    SpecialistKind,
)
from agents.state import (
    AgentState,
    IntentType,
    create_initial_state,
    set_error,
    update_state,
)


def evidence(n: int, specialist=SpecialistKind.STATUTE) -> Evidence:
    return Evidence(specialist=specialist, kind="sections", payload={"n": n})


class TestInitialState:
    def test_accumulating_fields_are_seeded(self):
        """A reducer must never meet a missing key, and nothing downstream
        should have to guard every read."""
        state = create_initial_state("q")
        assert state["evidence"] == []
        assert state["errors"] == []
        assert state["positions"] == []

    def test_the_router_fields_are_unchanged(self):
        state = create_initial_state("what is the punishment for murder")
        assert state["user_query"] == "what is the punishment for murder"
        assert state["intent"] == IntentType.UNKNOWN.value
        assert state["tool_results"] == {}
        assert state["error"] is None

    def test_a_query_starts_simple(self):
        """Fan-out must be the exception. If triage never runs, the cheap path
        is what happens."""
        assert create_initial_state("q")["complexity"] == Complexity.SIMPLE.value


class TestUpdateState:
    def test_an_accumulating_field_is_dropped_when_not_updated(self):
        """
        The doubling bug. Every node returns the whole state, and LangGraph
        applies ``operator.add`` to whatever a node returns -- so a node that
        merely passes ``evidence`` through appends the list to itself.
        """
        state = create_initial_state("q")
        state["evidence"] = [evidence(1)]

        assert "evidence" not in update_state(state, intent="rag_search")

    def test_an_accumulating_field_passed_explicitly_survives(self):
        update = update_state(create_initial_state("q"), evidence=[evidence(1)])
        assert len(update["evidence"]) == 1

    def test_ordinary_fields_are_untouched(self):
        update = update_state(create_initial_state("q"), intent="chat")
        assert update["intent"] == "chat"
        assert update["user_query"] == "q"

    def test_set_error_still_works(self):
        assert set_error(create_initial_state("q"), "boom")["error"] == "boom"


class TestParallelWrites:
    """Against a real compiled graph, because this fails at runtime or not at all."""

    @staticmethod
    def _fan_out_graph(worker):
        graph = StateGraph(AgentState)
        graph.add_node("dispatch", lambda state: {})
        graph.add_node("worker", worker)
        graph.set_entry_point("dispatch")
        graph.add_conditional_edges(
            "dispatch",
            lambda state: [
                Send("worker", {**state, "_kind": kind})
                for kind in (
                    SpecialistKind.STATUTE,
                    SpecialistKind.CASE_LAW,
                    SpecialistKind.OFFENCE,
                )
            ],
            ["worker"],
        )
        graph.add_edge("worker", END)
        return graph.compile()

    def test_three_specialists_writing_at_once_merge(self):
        """Without the reducer this raises InvalidUpdateError: 'Can receive
        only one value per step.'"""
        compiled = self._fan_out_graph(
            lambda state: {"evidence": [evidence(1, state["_kind"])]}
        )
        result = compiled.invoke(create_initial_state("q"))

        assert len(result["evidence"]) == 3
        assert {e.specialist for e in result["evidence"]} == {
            SpecialistKind.STATUTE,
            SpecialistKind.CASE_LAW,
            SpecialistKind.OFFENCE,
        }

    def test_tool_results_merge_by_key_rather_than_replacing(self):
        compiled = self._fan_out_graph(
            lambda state: {"tool_results": {state["_kind"].value: "done"}}
        )
        result = compiled.invoke(create_initial_state("q"))

        assert set(result["tool_results"]) == {"statute", "case_law", "offence"}

    def test_a_failing_specialist_does_not_fail_the_query(self):
        """
        Partial failure is a first-class outcome: a query that consulted three
        specialists and lost one is still answerable from two. Same rule
        `judiciary_service` follows, and the reason live research degraded to
        the corpus rather than 500-ing while the source was unreachable.
        """

        def worker(state):
            kind = state["_kind"]
            if kind is SpecialistKind.CASE_LAW:
                return {"errors": [AgentError(specialist=kind, message="down")]}
            return {"evidence": [evidence(1, kind)]}

        result = self._fan_out_graph(worker).invoke(create_initial_state("q"))

        assert len(result["evidence"]) == 2
        assert len(result["errors"]) == 1
        assert result["error"] is None, "a specialist failure is not a fatal error"

    def test_a_passthrough_node_does_not_double_the_evidence(self):
        """The doubling bug end to end, which is invisible on the router path
        because the list is always empty there."""
        graph = StateGraph(AgentState)
        graph.add_node("seed", lambda s: update_state(s, evidence=[evidence(1)]))
        graph.add_node("pass", lambda s: update_state(s, intent="rag_search"))
        graph.set_entry_point("seed")
        graph.add_edge("seed", "pass")
        graph.add_edge("pass", END)

        result = graph.compile().invoke(create_initial_state("q"))
        assert len(result["evidence"]) == 1


class TestContracts:
    def test_a_plan_names_each_specialist_once(self):
        """A planner that repeats itself gets one dispatch, not two."""
        plan = Plan(
            steps=[
                PlanStep(specialist=SpecialistKind.STATUTE, question="a"),
                PlanStep(specialist=SpecialistKind.STATUTE, question="b"),
                PlanStep(specialist=SpecialistKind.CASE_LAW, question="c"),
            ]
        )
        assert plan.specialists == [SpecialistKind.STATUTE, SpecialistKind.CASE_LAW]

    @pytest.mark.parametrize(
        ("kind", "deterministic"),
        [
            (SpecialistKind.OFFENCE, True),
            (SpecialistKind.DOCTRINE, True),
            (SpecialistKind.STATUTE, False),
            (SpecialistKind.CASE_LAW, False),
        ],
    )
    def test_lookup_specialists_are_marked_deterministic(self, kind, deterministic):
        """They read the First Schedule and the curated graph. Free, and they
        cannot hallucinate — so a plan including them costs nothing."""
        assert kind.deterministic is deterministic

    def test_a_position_without_authority_is_unsupported(self):
        """Reported rather than dropped: that a side cannot be supported from
        this corpus is itself a finding."""
        assert not Position(label="A", summary="x").supported
        assert Position(label="A", summary="x", authority=["BNS 103"]).supported

    def test_evidence_knows_when_it_found_nothing(self):
        assert evidence(1).is_empty() is False
        assert Evidence(specialist=SpecialistKind.STATUTE, kind="sections").is_empty()


class TestReducerChoice:
    def test_evidence_appends_and_tool_results_merge(self):
        """
        Different reducers on purpose. Evidence is a list of findings from
        distinct agents and all of it matters; tool_results is keyed by
        specialist name, where a deep merge would fuse two agents' findings
        into one object and lose which agent produced what.
        """
        annotations = AgentState.__annotations__
        assert operator.add in getattr(annotations["evidence"], "__metadata__", ())
        assert getattr(annotations["tool_results"], "__metadata__", ())


class TestWorkspaceSignal:
    """
    The UI knows which workspace a query was typed in. The classifier was
    guessing it from keywords.

    Honest scope note: the five workspaces already route by *endpoint* --
    Corpus calls /search, Draft calls /documents/draft -- so today only "Ask"
    reaches the agent and this mostly stops the classifier inferring intents
    that cannot legitimately arrive. It becomes load-bearing the moment the UI
    offers one input for everything.
    """

    def test_the_workspace_is_carried_on_the_state(self):
        assert create_initial_state("q", workspace="draft")["workspace"] == "draft"

    def test_it_defaults_to_unknown(self):
        assert create_initial_state("q")["workspace"] is None

    @pytest.mark.parametrize(
        ("workspace", "intent"),
        [
            ("draft", "draft_document"),
            ("analyze", "analyze_document"),
            ("research", "live_research"),
            ("search", "rag_search"),
        ],
    )
    def test_a_specific_workspace_settles_the_intent(self, workspace, intent):
        """A user in the Draft workspace is drafting. There is nothing to
        infer, and inferring it is strictly worse than being told."""
        from agents.intent_classifier import IntentClassifier

        assert IntentClassifier().classify("tell me about bail", workspace) == intent

    def test_the_ask_workspace_still_uses_keywords(self):
        """Ask is where a user may reasonably ask anything, so there the
        keywords still decide."""
        from agents.intent_classifier import IntentClassifier

        classifier = IntentClassifier()
        assert classifier.classify("tell me about bail", "chat") == "rag_search"
        assert classifier.classify("draft me a bail application", "chat") == (
            "draft_document"
        )

    @pytest.mark.parametrize("workspace", [None, "", "nonsense", "  "])
    def test_an_unknown_workspace_falls_through_rather_than_failing(self, workspace):
        """Every existing caller sends nothing, and must keep working."""
        from agents.intent_classifier import IntentClassifier

        assert IntentClassifier().classify("tell me about bail", workspace) == (
            "rag_search"
        )
