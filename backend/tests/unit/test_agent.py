"""
Unit Tests for LangGraph Agent Components

Tests for agent state, intent classifier, and agent graph.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from agents.agent_service import AgentService
from agents.intent_classifier import IntentClassifier
from agents.legal_agent import LegalAgent
from agents.state import IntentType, add_message, create_initial_state, set_error, update_state


class TestAgentState:
    """Test agent state management"""

    def test_create_initial_state(self):
        """Test creating initial agent state"""
        query = "What are bail provisions in BNSS?"
        state = create_initial_state(query)

        assert state["user_query"] == query
        assert state["intent"] == IntentType.UNKNOWN.value
        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][0]["content"] == query
        assert state["tool_results"] == {}
        assert state["final_response"] == ""
        assert state["error"] is None

    def test_update_state(self):
        """Test updating agent state"""
        state = create_initial_state("test query")
        updated = update_state(state, intent="rag_search", final_response="test response")

        assert updated["intent"] == "rag_search"
        assert updated["final_response"] == "test response"
        assert updated["user_query"] == "test query"  # Original fields preserved

    def test_add_message(self):
        """
        Returns only the new message, not the whole list.

        ``messages`` accumulates through a reducer so that a checkpointed
        conversation appends each turn instead of replacing it. Returning the
        existing list alongside the new one would therefore append the entire
        history to itself on every turn.
        """
        state = create_initial_state("test query")
        update = add_message(state, "assistant", "test response")

        assert update["messages"] == [
            {"role": "assistant", "content": "test response"}
        ]

    def test_set_error(self):
        """Test setting error in state"""
        state = create_initial_state("test query")
        updated = set_error(state, "test error")

        assert updated["error"] == "test error"


class TestIntentClassifier:
    """Test intent classification"""

    def test_classify_rag_search_intent(self):
        """Test RAG search intent classification"""
        classifier = IntentClassifier()

        queries = [
            "What are the provisions for bail in BNSS?",
            "Explain Section 103 of BNS",
            "Find Supreme Court judgements on anticipatory bail",
            "Search for IPC sections on theft"
        ]

        for query in queries:
            intent = classifier.classify(query)
            assert intent == IntentType.RAG_SEARCH.value

    def test_classify_draft_document_intent(self):
        """Test draft document intent classification"""
        classifier = IntentClassifier()

        queries = [
            "Draft a bail application for BNS 103",
            "Generate a petition for anticipatory bail",
            "Create a legal notice for breach of contract",
            "Write an affidavit for court"
        ]

        for query in queries:
            intent = classifier.classify(query)
            assert intent == IntentType.DRAFT_DOCUMENT.value

    def test_classify_analyze_document_intent(self):
        """Test analyze document intent classification"""
        classifier = IntentClassifier()

        queries = [
            "Analyze this rental agreement",
            "Review the uploaded contract",
            "Check this document for risks",
            "Examine the clauses in this deed"
        ]

        for query in queries:
            intent = classifier.classify(query)
            assert intent == IntentType.ANALYZE_DOCUMENT.value

    def test_classify_chat_intent(self):
        """Test chat intent classification"""
        classifier = IntentClassifier()

        queries = [
            "Hello, how are you?",
            "What can you help me with?",
            "Thank you for your help",
            "Hi there"
        ]

        for query in queries:
            intent = classifier.classify(query)
            assert intent == IntentType.CHAT.value

    @pytest.mark.parametrize("query", [
        "Tell me about bail",
        "What are the provisions for bail in BNSS?",
        "Find Supreme Court judgements on anticipatory bail",
        "Explain the petition process",
        "What are the risks under a contract?",
    ])
    def test_legal_vocabulary_alone_does_not_mean_draft_or_analyse(self, query):
        """
        Regression: "bail", "petition", "contract" and "risks" are ordinary legal
        vocabulary. Without an action verb they are questions about the law, not
        requests to produce or inspect a document.
        """
        assert IntentClassifier().classify(query) == IntentType.RAG_SEARCH.value

    @pytest.mark.parametrize("query,expected", [
        ("Draft a bail application", IntentType.DRAFT_DOCUMENT.value),
        ("Prepare a petition", IntentType.DRAFT_DOCUMENT.value),
        ("Review this contract for risks", IntentType.ANALYZE_DOCUMENT.value),
        ("Summarise the attached agreement", IntentType.ANALYZE_DOCUMENT.value),
    ])
    def test_action_verb_enables_document_intents(self, query, expected):
        assert IntentClassifier().classify(query) == expected

    @pytest.mark.parametrize("query", [
        "Recent Supreme Court judgments on anticipatory bail",
        "What are the latest rulings on default bail?",
        "Supreme Court judgements on bail in 2026",
        "Has the Supreme Court decided anything new on BNS this year?",
        "Current case law on organised crime under BNS 111",
        "latest High Court orders on electronic evidence",
    ])
    def test_recent_case_law_questions_go_live(self, query):
        """The corpus is a snapshot, so recency questions must escalate."""
        assert IntentClassifier().classify(query) == IntentType.LIVE_RESEARCH.value

    @pytest.mark.parametrize("query", [
        "Find Supreme Court judgements on anticipatory bail",
        "What is BNS Section 103?",
        "Explain the case law on circumstantial evidence",
        "Tell me about bail",
    ])
    def test_settled_law_questions_stay_local(self, query):
        """Without a recency signal, answer from the verified corpus."""
        assert IntentClassifier().classify(query) == IntentType.RAG_SEARCH.value

    def test_classify_with_llm_fallback(self):
        """Test LLM fallback classification"""
        mock_llm = Mock()
        mock_llm.generate.return_value = "rag_search"

        classifier = IntentClassifier(llm_service=mock_llm)
        intent = classifier.classify("ambiguous query without clear keywords")

        # Should default to RAG_SEARCH or use LLM
        assert intent in [i.value for i in IntentType]

    def test_get_intent_description(self):
        """Test getting intent descriptions"""
        classifier = IntentClassifier()

        desc = classifier.get_intent_description(IntentType.RAG_SEARCH.value)
        assert "search" in desc.lower()

        desc = classifier.get_intent_description(IntentType.DRAFT_DOCUMENT.value)
        assert "draft" in desc.lower()


class TestLegalAgent:
    """Test LangGraph legal agent"""

    @pytest.fixture
    def grounded(self):
        """
        Stub the grounded pipeline the RAG node now calls.

        Patched rather than left live because the node reaches the vector store
        and the model otherwise -- which is how this fixture came to exist: the
        test that used to mock the RAG tool silently started making real calls
        when the node changed under it.
        """
        from models.claims import Claim, EpistemicClass, StructuredAnswer
        from services.answer_metrics import compute
        from services.grounded_answer import GroundedAnswer

        answer = StructuredAnswer(claims=[
            Claim(
                text="Murder is punished with death or imprisonment for life.",
                epistemic_class=EpistemicClass.STATUTE,
                sources=["BNS 103"],
                verbatim_span="death or imprisonment for life",
            )
        ])
        service = Mock()
        service.answer = Mock(return_value=GroundedAnswer(
            query="q",
            answer=answer.render(),
            structured=answer,
            metrics=compute(answer),
            sources=[{"id": "bns_103", "metadata": {"section_number": "103",
                                                    "act": "Bharatiya Nyaya Sanhita"}}],
        ))
        with patch("agents.legal_agent.get_grounded_answer_service", return_value=service):
            yield service

    @pytest.fixture
    def mock_tools(self):
        """Create mock tool registry"""
        mock_registry = Mock()

        # Mock RAG search tool
        mock_rag_tool = Mock()
        mock_rag_tool.execute = AsyncMock()
        mock_rag_tool.execute.return_value = {
            "answer": "Test RAG answer",
            "sources": [{"metadata": {"source": "BNS Section 103"}}]
        }

        # Mock chat tool
        mock_chat_tool = Mock()
        mock_chat_tool.execute = AsyncMock()
        mock_chat_tool.execute.return_value = {
            "response": "Test chat response"
        }

        # Mock draft tool
        mock_draft_tool = Mock()
        mock_draft_tool.execute = AsyncMock()
        mock_draft_tool.execute.return_value = {
            "document": "Test draft content",
            "document_type": "bail_application"
        }

        # Mock analyze tool
        mock_analyze_tool = Mock()
        mock_analyze_tool.execute = AsyncMock()
        mock_analyze_tool.execute.return_value = {
            "analysis": "Test analysis",
            "risks": ["Risk 1"],
            "recommendations": ["Recommendation 1"]
        }

        def get_tool(name):
            tools = {
                "rag_search": mock_rag_tool,
                "chat": mock_chat_tool,
                "draft_document": mock_draft_tool,
                "analyze_doc": mock_analyze_tool
            }
            return tools.get(name)

        mock_registry.get_tool = get_tool
        return mock_registry

    @pytest.fixture
    def mock_classifier(self):
        """Create mock intent classifier"""
        classifier = Mock()
        classifier.classify.return_value = IntentType.RAG_SEARCH.value
        classifier.get_intent_description.return_value = "Search legal information"
        return classifier

    @pytest.mark.parametrize("query,expected", [
        ("Draft an anticipatory bail application under BNSS 482", "bail_application"),
        ("Draft a rental agreement between two parties", "agreement"),
        ("Prepare a contract for services", "agreement"),
        ("File a writ petition in the High Court", "petition"),
        ("Draft a legal notice", "notice"),
        ("Prepare an affidavit for the deponent", "affidavit"),
        # The document being drafted wins over its subject matter.
        ("Send a legal notice for breach of contract", "notice"),
        # "affidavit in support of the bail application" is an affidavit; it is
        # listed ahead of "notice"/"petition" but after "bail" would mis-route,
        # so ordering matters here.
        ("Draft an affidavit in support of the bail application", "affidavit"),
        # No recognisable keyword falls back to the most common request.
        ("Draft something for my client", "bail_application"),
    ])
    def test_infer_document_type(self, query, expected):
        assert LegalAgent._infer_document_type(query) == expected

    def test_agent_initialization(self, mock_classifier, mock_tools):
        """Test agent initialization"""
        agent = LegalAgent(mock_classifier, mock_tools)

        assert agent.intent_classifier == mock_classifier
        assert agent.tool_registry == mock_tools
        assert agent.graph is not None

    @pytest.mark.asyncio
    async def test_agent_process_rag_search(self, mock_classifier, mock_tools, grounded):
        """
        The RAG intent goes through the grounded pipeline, not the plain tool.

        The tool is still registered and still served by /search/rag; what
        changed is that the agent's main path now runs the verifier, so a claim
        it cannot support never reaches the user.
        """
        mock_classifier.classify.return_value = IntentType.RAG_SEARCH.value
        agent = LegalAgent(mock_classifier, mock_tools)

        result = await agent.process("What are bail provisions?")

        assert result["intent"] == IntentType.RAG_SEARCH.value
        assert "Murder is punished with death" in result["response"]
        grounded.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_agent_searches_every_statute_collection(
        self, mock_classifier, mock_tools, grounded
    ):
        """It cannot know in advance whether a question is about offences,
        procedure or evidence."""
        mock_classifier.classify.return_value = IntentType.RAG_SEARCH.value
        await LegalAgent(mock_classifier, mock_tools).process("what is bail")

        assert grounded.answer.call_args.kwargs["collection"] == [
            "bns_sections", "bnss_sections", "bsa_sections"
        ]

    @pytest.mark.asyncio
    async def test_verification_reaches_the_client(self, mock_classifier, mock_tools, grounded):
        """
        Additive to the existing response shape: a client that ignores it still
        works, and one that reads it can render a claim as what it actually is.
        """
        mock_classifier.classify.return_value = IntentType.RAG_SEARCH.value
        agent = LegalAgent(mock_classifier, mock_tools)

        state = await agent.graph.ainvoke(create_initial_state("what is bail"))
        verification = state["tool_results"]["rag_search"]["verification"]

        assert verification["claims"][0]["epistemic_class"] == "statute"
        assert verification["metrics"]["claims"] == 1
        assert verification["removed"] == 0

    @pytest.mark.asyncio
    async def test_an_abstention_is_passed_through(self, mock_classifier, mock_tools, grounded):
        """A refusal is an answer, and must not be dressed up as a failure."""
        from models.claims import StructuredAnswer
        from services.grounded_answer import GroundedAnswer

        grounded.answer.return_value = GroundedAnswer(
            query="q",
            answer="I could not support any part of an answer.",
            structured=StructuredAnswer(abstained=True, abstention_reason="no"),
        )
        mock_classifier.classify.return_value = IntentType.RAG_SEARCH.value

        result = await LegalAgent(mock_classifier, mock_tools).process("parole days")
        assert "could not support" in result["response"]

    @pytest.mark.asyncio
    async def test_agent_process_chat(self, mock_classifier, mock_tools):
        """Test agent processing chat query"""
        mock_classifier.classify.return_value = IntentType.CHAT.value
        agent = LegalAgent(mock_classifier, mock_tools)

        result = await agent.process("Hello, how are you?")

        assert "response" in result
        assert result["intent"] == IntentType.CHAT.value

    @pytest.mark.asyncio
    async def test_agent_process_draft(self, mock_classifier, mock_tools):
        """Test agent processing draft document query"""
        mock_classifier.classify.return_value = IntentType.DRAFT_DOCUMENT.value
        agent = LegalAgent(mock_classifier, mock_tools)

        result = await agent.process("Draft a bail application")

        assert "response" in result
        assert result["intent"] == IntentType.DRAFT_DOCUMENT.value
        assert "draft" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_agent_error_handling(self, mock_classifier, mock_tools):
        """Test agent error handling"""
        mock_classifier.classify.side_effect = Exception("Classification error")
        agent = LegalAgent(mock_classifier, mock_tools)

        result = await agent.process("test query")

        assert result["error"] is not None


class TestAgentService:
    """Test agent service"""

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent"""
        agent = Mock()
        agent.process = AsyncMock()
        agent.process.return_value = {
            "response": "Test response",
            "intent": "rag_search",
            "metadata": {},
            "error": None
        }
        return agent

    def test_agent_service_initialization(self):
        """Test agent service initialization"""
        with patch('agents.agent_service.LegalAgent'):
            service = AgentService()
            assert service.agent is not None

    @pytest.mark.asyncio
    async def test_process_query(self, mock_agent):
        """Test processing query through service"""
        with patch('agents.agent_service.LegalAgent', return_value=mock_agent):
            service = AgentService()
            result = await service.process_query("test query")

            assert result["response"] == "Test response"
            assert result["intent"] == "rag_search"

    def test_get_agent_info(self):
        """Test getting agent info"""
        with patch('agents.agent_service.LegalAgent'):
            service = AgentService()
            info = service.get_agent_info()

            assert "status" in info
            assert "available_tools" in info
            assert "supported_intents" in info

    def test_health_check(self):
        """Test agent health check"""
        with patch('agents.agent_service.LegalAgent'):
            service = AgentService()
            health = service.health_check()

            assert "status" in health
            assert "components" in health
