"""
Conversation memory, and the pause before a document is written.

Both are off by default, and both defaults are decisions rather than caution.

The checkpointer available here keeps threads in process memory: it grows
without bound and is invisible to a second worker, so switching it on is a
choice about where state lives. And the draft pause is useless without it --
``interrupt`` records where it stopped in a checkpoint, so with no checkpointer
the pause would simply lose the turn.
"""
import importlib
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.types import Command

from agents.intent_classifier import IntentClassifier
from agents.state import create_initial_state
from tools.base_tool import ToolResult


def build_agent(monkeypatch, **flags):
    """A LegalAgent built with the given flags, reloaded so they take effect."""
    for key in ("ENABLE_CONVERSATION_MEMORY", "ENABLE_DRAFT_CONFIRMATION"):
        monkeypatch.delenv(key, raising=False)
    for key, value in flags.items():
        monkeypatch.setenv(key, value)

    import agents.legal_agent as module

    importlib.reload(module)

    registry = MagicMock()
    tool = MagicMock()
    tool.execute = AsyncMock(
        return_value=ToolResult(success=True, data={"document": "THE DRAFT"})
    )
    registry.get_tool.return_value = tool
    agent = module.LegalAgent(IntentClassifier(), registry, llm_service=None)
    return agent, tool, module


@pytest.fixture(autouse=True)
def _restore():
    """Reload the module afterwards so a flag set here cannot leak."""
    yield
    for key in ("ENABLE_CONVERSATION_MEMORY", "ENABLE_DRAFT_CONFIRMATION"):
        os.environ.pop(key, None)
    import agents.legal_agent as module

    importlib.reload(module)


class TestTheDefault:
    def test_memory_is_off_and_no_checkpointer_is_attached(self, monkeypatch):
        """
        Compiling with a checkpointer unconditionally would be worse than
        useless: LangGraph then *requires* a thread_id on every invocation, so
        a single-turn caller that never wanted memory would start failing.
        """
        agent, _, _ = build_agent(monkeypatch)
        assert agent.checkpointer is None

    @pytest.mark.asyncio
    async def test_a_thread_id_is_harmless_when_memory_is_off(self, monkeypatch):
        """A client may always send one, so it must never be the thing that
        breaks a request."""
        agent, _, _ = build_agent(monkeypatch)
        result = await agent.process("draft a bail application", thread_id="t1")
        assert result["response"]

    def test_drafting_does_not_pause_by_default(self, monkeypatch):
        _, _, module = build_agent(monkeypatch)
        assert module.draft_confirmation_enabled() is False


class TestConversationMemory:
    @pytest.mark.asyncio
    async def test_turns_accumulate_on_one_thread(self, monkeypatch):
        """
        What memory means here. Without a reducer on `messages` the checkpoint
        faithfully stored one message per thread and every turn started again,
        which looks exactly like working.
        """
        agent, _, _ = build_agent(monkeypatch, ENABLE_CONVERSATION_MEMORY="true")
        for question in ("draft a bail application", "draft a complaint"):
            await agent.process(question, thread_id="t1")

        state = agent.graph.get_state({"configurable": {"thread_id": "t1"}})
        assert [m["content"] for m in state.values["messages"]] == [
            "draft a bail application",
            "draft a complaint",
        ]

    @pytest.mark.asyncio
    async def test_threads_do_not_leak_into_each_other(self, monkeypatch):
        agent, _, _ = build_agent(monkeypatch, ENABLE_CONVERSATION_MEMORY="true")
        await agent.process("draft a bail application", thread_id="t1")

        other = agent.graph.get_state({"configurable": {"thread_id": "t2"}})
        assert not other.values.get("messages")

    @pytest.mark.asyncio
    async def test_a_turn_with_no_thread_still_works(self, monkeypatch):
        """
        Memory being on must not make a thread compulsory. LangGraph refuses to
        run a checkpointed graph without a thread_id, so a caller that switched
        memory on and asked one question got a ValueError instead of an answer.
        A turn with no thread gets a throwaway id and shares memory with nothing.
        """
        agent, _, _ = build_agent(monkeypatch, ENABLE_CONVERSATION_MEMORY="true")
        result = await agent.process("draft a bail application")
        assert result["response"]


class TestDraftConfirmation:
    @pytest.mark.asyncio
    async def test_it_pauses_before_writing_anything(self, monkeypatch):
        """
        A drafted document is the one output here a person may file rather than
        read, and the document type is *inferred* -- inferring "bail
        application" from a question that wanted a complaint produces something
        plausible and wrong in a way an answer never is.
        """
        agent, tool, _ = build_agent(
            monkeypatch,
            ENABLE_CONVERSATION_MEMORY="true",
            ENABLE_DRAFT_CONFIRMATION="true",
        )
        config = {"configurable": {"thread_id": "d1"}}

        result = await agent.graph.ainvoke(
            create_initial_state("draft a bail application"), config=config
        )

        assert "__interrupt__" in result
        tool.execute.assert_not_called(), "nothing may be written before approval"

    @pytest.mark.asyncio
    async def test_the_pause_says_what_it_is_about_to_write(self, monkeypatch):
        agent, _, _ = build_agent(
            monkeypatch,
            ENABLE_CONVERSATION_MEMORY="true",
            ENABLE_DRAFT_CONFIRMATION="true",
        )
        config = {"configurable": {"thread_id": "d1"}}

        result = await agent.graph.ainvoke(
            create_initial_state("draft a bail application"), config=config
        )

        payload = result["__interrupt__"][0].value
        assert payload["awaiting"] == "draft_confirmation"
        assert payload["document_type"] == "bail_application"

    @pytest.mark.asyncio
    async def test_resuming_produces_the_document(self, monkeypatch):
        agent, tool, _ = build_agent(
            monkeypatch,
            ENABLE_CONVERSATION_MEMORY="true",
            ENABLE_DRAFT_CONFIRMATION="true",
        )
        config = {"configurable": {"thread_id": "d1"}}
        await agent.graph.ainvoke(
            create_initial_state("draft a bail application"), config=config
        )

        resumed = await agent.graph.ainvoke(Command(resume="yes"), config=config)

        tool.execute.assert_called_once()
        assert "THE DRAFT" in resumed["final_response"]

    @pytest.mark.asyncio
    async def test_the_pause_is_not_swallowed_by_the_nodes_error_handler(
        self, monkeypatch
    ):
        """
        The bug this was written with. `interrupt` signals by raising
        GraphInterrupt, which is an Exception, so the node's `except Exception`
        caught the pause and reported it as a failed draft -- indistinguishable
        from the flag simply not working.
        """
        agent, _, _ = build_agent(
            monkeypatch,
            ENABLE_CONVERSATION_MEMORY="true",
            ENABLE_DRAFT_CONFIRMATION="true",
        )
        config = {"configurable": {"thread_id": "d1"}}

        result = await agent.graph.ainvoke(
            create_initial_state("draft a bail application"), config=config
        )

        assert result.get("error") is None
        assert "__interrupt__" in result

    def test_the_pause_needs_a_checkpointer_to_resume_from(self, monkeypatch):
        """Without one there is nothing to resume, so the pause would lose the
        turn rather than hold it."""
        agent, _, module = build_agent(monkeypatch, ENABLE_DRAFT_CONFIRMATION="true")
        assert module.draft_confirmation_enabled() is True
        assert agent.checkpointer is None
