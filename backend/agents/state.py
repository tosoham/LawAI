"""
Agent State Management for LawAI LangGraph Agent

Defines the state structure for the LangGraph agent orchestration.

**Why some fields carry reducers and most do not.** LangGraph applies every
update returned within one superstep to the same state, and for a plain key it
refuses more than one:

    InvalidUpdateError: At key 'tool_results': Can receive only one value per
    step. Use an Annotated key to handle multiple values.

While the graph was a router -- classify, run exactly one tool node, format --
that never arose, and a bare ``dict`` was the honest declaration. Fan-out makes
several specialists write in the same step, so the fields they write are
annotated with a reducer that merges rather than replaces. The rest stay
single-writer on purpose: ``final_response`` having a reducer would mean two
nodes could both be writing the answer, which is a design error the type
system should keep out rather than merge away.
"""

import operator
from enum import Enum
from typing import Annotated, Any, TypedDict

from agents.contracts import AgentError, Complexity, Evidence, Plan


class IntentType(str, Enum):
    """Supported agent intents"""
    RAG_SEARCH = "rag_search"
    CHAT = "chat"
    DRAFT_DOCUMENT = "draft_document"
    ANALYZE_DOCUMENT = "analyze_document"
    #: Questions about recent or current case law. The corpus is a snapshot, so
    #: these are answered by letting the model call live judiciary sources.
    LIVE_RESEARCH = "live_research"
    UNKNOWN = "unknown"


def _merge_results(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """
    Merge two ``tool_results`` updates from the same superstep.

    Last write wins per key, which is safe because the keys are specialist
    names and no two specialists share one. A plain ``dict.update`` rather than
    a deep merge on purpose: a deep merge would silently combine two
    specialists' findings into one object and lose which agent produced what,
    and provenance is the whole point of gathering evidence separately.
    """
    return {**(left or {}), **(right or {})}


class AgentState(TypedDict):
    """
    State structure for LangGraph agent.

    Fields:
        messages: List of conversation messages
        user_query: Current user query
        intent: Classified intent type
        tool_results: Results from tool execution
        final_response: Formatted final response
        error: Error message if any
        metadata: Additional metadata
    """
    messages: list[dict[str, str]]
    user_query: str
    intent: str
    tool_results: Annotated[dict[str, Any], _merge_results]
    final_response: str
    error: str | None
    metadata: dict[str, Any]

    # -- multi-agent fields ------------------------------------------------
    # Absent on the router path, which is why every one of them is optional
    # and why nothing existing reads them. `create_initial_state` seeds the
    # accumulating ones so a reducer never meets a missing key.

    complexity: str
    """What triage decided: simple, complex or contested. Simple keeps the
    existing single-pass path, and that is what stops fan-out becoming the
    default cost of asking a question."""

    plan: Plan | None
    evidence: Annotated[list[Evidence], operator.add]
    """Written by every specialist in the same superstep, hence the reducer.
    Order is not meaningful: fan-out completion order is arbitrary, so anything
    downstream that cares about precedence must sort explicitly."""

    errors: Annotated[list[AgentError], operator.add]
    """Specialist failures, accumulated rather than raised. A query that lost
    one specialist is still answerable from the others, and the answer says so.
    Distinct from ``error``, which is the router's single fatal field."""

    positions: list[Any]
    """The contested path's two readings. Single-writer: the advocates run in
    a bounded sequence, not a fan-out, because the rebuttal round requires each
    to have seen the other."""


def create_initial_state(user_query: str) -> AgentState:
    """
    Create initial agent state from user query.

    Args:
        user_query: User's input query

    Returns:
        Initial AgentState
    """
    return AgentState(
        messages=[{"role": "user", "content": user_query}],
        user_query=user_query,
        intent=IntentType.UNKNOWN.value,
        tool_results={},
        final_response="",
        error=None,
        metadata={},
        # Seeded even on the router path, so a reducer never meets a missing
        # key and so nothing downstream has to guard every read.
        complexity=Complexity.SIMPLE.value,
        plan=None,
        evidence=[],
        errors=[],
        positions=[],
    )


#: Fields whose reducer *appends*. Returning one of these unchanged from a node
#: re-adds it, because LangGraph applies the reducer to whatever the node
#: returns rather than diffing it against what was there.
_ACCUMULATING = ("evidence", "errors")


def update_state(
    state: AgentState,
    **updates: Any
) -> AgentState:
    """
    Update agent state with new values.

    Every node here returns the whole state rather than the keys it changed,
    which was harmless while no key had a reducer. It stopped being harmless
    with ``evidence``: LangGraph applies ``operator.add`` to whatever a node
    returns, so a node that merely passes the list through appends it to
    itself. Measured on a two-node graph, one seeded item came out twice.

    So an accumulating field is dropped from the returned update unless the
    caller is deliberately adding to it. Nothing else changes: single-writer
    fields are returned as before, and a node that wants to append passes the
    field explicitly and gets exactly what it passed appended.

    Args:
        state: Current state
        **updates: Fields to update

    Returns:
        Updated AgentState
    """
    new_state = state.copy()
    new_state.update(updates)  # type: ignore
    for key in _ACCUMULATING:
        if key not in updates:
            new_state.pop(key, None)  # type: ignore[misc]
    return new_state


def add_message(
    state: AgentState,
    role: str,
    content: str
) -> AgentState:
    """
    Add a message to the state.

    Args:
        state: Current state
        role: Message role (user/assistant/system)
        content: Message content

    Returns:
        Updated AgentState
    """
    new_state = state.copy()
    new_state["messages"].append({"role": role, "content": content})
    return new_state


def set_error(
    state: AgentState,
    error: str
) -> AgentState:
    """
    Set error in state.

    Args:
        state: Current state
        error: Error message

    Returns:
        Updated AgentState
    """
    new_state = state.copy()
    new_state["error"] = error
    return new_state
