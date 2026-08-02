"""
Agent State Management for LawAI LangGraph Agent

Defines the state structure for the LangGraph agent orchestration.
"""

from enum import Enum
from typing import Any, TypedDict


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
    tool_results: dict[str, Any]
    final_response: str
    error: str | None
    metadata: dict[str, Any]


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
        metadata={}
    )


def update_state(
    state: AgentState,
    **updates: Any
) -> AgentState:
    """
    Update agent state with new values.

    Args:
        state: Current state
        **updates: Fields to update

    Returns:
        Updated AgentState
    """
    new_state = state.copy()
    new_state.update(updates)  # type: ignore
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
