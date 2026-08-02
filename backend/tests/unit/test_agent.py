"""
Unit Tests for LangGraph Agent Components

Tests for agent state, intent classifier, and agent graph.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from agents.state import (
    IntentType, create_initial_state, 
    update_state, add_message, set_error
)
from agents.intent_classifier import IntentClassifier
from agents.legal_agent import LegalAgent
from agents.agent_service import AgentService


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
        """Test adding message to state"""
        state = create_initial_state("test query")
        updated = add_message(state, "assistant", "test response")
        
        assert len(updated["messages"]) == 2
        assert updated["messages"][1]["role"] == "assistant"
        assert updated["messages"][1]["content"] == "test response"
    
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
        # The document being drafted wins over its subject matter.
        ("Send a legal notice for breach of contract", "notice"),
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
    async def test_agent_process_rag_search(self, mock_classifier, mock_tools):
        """Test agent processing RAG search query"""
        mock_classifier.classify.return_value = IntentType.RAG_SEARCH.value
        agent = LegalAgent(mock_classifier, mock_tools)
        
        result = await agent.process("What are bail provisions?")
        
        assert "response" in result
        assert result["intent"] == IntentType.RAG_SEARCH.value
        assert "Test RAG answer" in result["response"]
    
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
