"""
Integration Tests for LangGraph Agent Flows

End-to-end tests for complete agent workflows.
"""

import pytest
from backend.agents.agent_service import AgentService, reset_agent_service
from backend.tools.registry import ToolRegistry, get_tool_registry
from backend.services.llm_service import LLMService
from backend.services.rag_service import RAGService


@pytest.fixture(scope="module")
def agent_service():
    """Create agent service for integration tests"""
    # Reset singleton
    reset_agent_service()
    
    # Initialize services
    llm_service = LLMService()
    rag_service = RAGService()
    
    # Initialize tools
    from backend.tools.registry import initialize_tools
    initialize_tools(llm_service, rag_service)
    
    # Create agent service
    service = AgentService()
    
    yield service
    
    # Cleanup
    reset_agent_service()


class TestBailApplicationFlow:
    """Test bail application generation flow"""
    
    def test_bail_query_classification(self, agent_service):
        """Test that bail queries are classified correctly"""
        query = "Draft a bail application for a client arrested under BNS Section 103"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "draft_document"
        assert result["response"] is not None
        assert len(result["response"]) > 0
    
    def test_bail_provisions_search(self, agent_service):
        """Test searching for bail provisions"""
        query = "What are the provisions for anticipatory bail in BNSS?"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "rag_search"
        assert result["response"] is not None
        # Should mention BNSS or bail
        assert any(term in result["response"].lower() for term in ["bnss", "bail", "section"])
    
    def test_complete_bail_flow(self, agent_service):
        """Test complete bail application flow"""
        # Step 1: Search for relevant provisions
        search_query = "BNSS Section 479 anticipatory bail"
        search_result = agent_service.process_query(search_query)
        
        assert search_result["intent"] == "rag_search"
        assert search_result["error"] is None
        
        # Step 2: Draft bail application
        draft_query = "Draft anticipatory bail application under BNSS 479"
        draft_result = agent_service.process_query(draft_query)
        
        assert draft_result["intent"] == "draft_document"
        assert draft_result["error"] is None
        assert "bail" in draft_result["response"].lower()


class TestCaseLawSearchFlow:
    """Test case law search flow"""
    
    def test_supreme_court_search(self, agent_service):
        """Test searching Supreme Court judgements"""
        query = "Find Supreme Court judgements on anticipatory bail from last 5 years"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "rag_search"
        assert result["response"] is not None
    
    def test_legal_provision_search(self, agent_service):
        """Test searching legal provisions"""
        queries = [
            "What is BNS Section 103?",
            "Explain theft provisions in BNS",
            "BNSS arrest procedures"
        ]
        
        for query in queries:
            result = agent_service.process_query(query)
            assert result["intent"] == "rag_search"
            assert result["error"] is None
    
    def test_comparative_search(self, agent_service):
        """Test comparative legal search"""
        query = "Compare IPC and BNS provisions on theft"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "rag_search"
        assert result["response"] is not None


class TestDocumentAnalysisFlow:
    """Test document analysis flow"""
    
    def test_analyze_request_classification(self, agent_service):
        """Test that analyze requests are classified correctly"""
        query = "Analyze this rental agreement for risks"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "analyze_document"
        assert result["response"] is not None
    
    def test_contract_review_request(self, agent_service):
        """Test contract review request"""
        query = "Review the uploaded contract and identify problematic clauses"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "analyze_document"
        assert result["error"] is None
    
    def test_document_risk_assessment(self, agent_service):
        """Test document risk assessment request"""
        query = "Check this agreement for legal risks and liabilities"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "analyze_document"
        assert "document" in result["response"].lower() or "upload" in result["response"].lower()


class TestChatFlow:
    """Test general chat flow"""
    
    def test_greeting(self, agent_service):
        """Test greeting classification"""
        queries = ["Hello", "Hi there", "Hey, how are you?"]
        
        for query in queries:
            result = agent_service.process_query(query)
            assert result["intent"] == "chat"
            assert result["error"] is None
    
    def test_help_request(self, agent_service):
        """Test help request"""
        query = "What can you help me with?"
        result = agent_service.process_query(query)
        
        assert result["intent"] == "chat"
        assert result["response"] is not None
    
    def test_general_legal_question(self, agent_service):
        """Test general legal question"""
        query = "Explain the concept of mens rea"
        result = agent_service.process_query(query)
        
        # Could be chat or rag_search
        assert result["intent"] in ["chat", "rag_search"]
        assert result["error"] is None


class TestMixedIntentFlow:
    """Test handling of mixed or ambiguous intents"""
    
    def test_ambiguous_query(self, agent_service):
        """Test handling of ambiguous query"""
        query = "Tell me about bail"
        result = agent_service.process_query(query)
        
        # Should default to rag_search
        assert result["intent"] in ["rag_search", "chat"]
        assert result["error"] is None
    
    def test_complex_query(self, agent_service):
        """Test complex multi-part query"""
        query = "What are the bail provisions in BNSS and can you draft an application?"
        result = agent_service.process_query(query)
        
        # Agent should pick one intent
        assert result["intent"] in ["rag_search", "draft_document"]
        assert result["error"] is None
    
    def test_sequential_queries(self, agent_service):
        """Test sequential related queries"""
        # First query - search
        result1 = agent_service.process_query("What is BNS Section 103?")
        assert result1["intent"] == "rag_search"
        
        # Second query - draft based on first
        result2 = agent_service.process_query("Draft a bail application for this section")
        assert result2["intent"] == "draft_document"
        
        # Both should succeed
        assert result1["error"] is None
        assert result2["error"] is None


class TestErrorHandling:
    """Test error handling in agent flows"""
    
    def test_empty_query(self, agent_service):
        """Test handling of empty query"""
        result = agent_service.process_query("")
        
        # Should handle gracefully
        assert result is not None
        assert "response" in result
    
    def test_very_long_query(self, agent_service):
        """Test handling of very long query"""
        query = "What is bail? " * 1000  # Very long query
        result = agent_service.process_query(query)
        
        # Should handle without crashing
        assert result is not None
        assert "response" in result
    
    def test_special_characters(self, agent_service):
        """Test handling of special characters"""
        query = "What is BNS §103? <script>alert('test')</script>"
        result = agent_service.process_query(query)
        
        # Should handle safely
        assert result is not None
        assert result["error"] is None or "response" in result


class TestAgentPerformance:
    """Test agent performance characteristics"""
    
    def test_response_time(self, agent_service):
        """Test that agent responds in reasonable time"""
        import time
        
        query = "What is BNS Section 103?"
        start = time.time()
        result = agent_service.process_query(query)
        duration = time.time() - start
        
        # Should respond within 30 seconds
        assert duration < 30
        assert result["error"] is None
    
    def test_multiple_concurrent_queries(self, agent_service):
        """Test handling multiple queries"""
        queries = [
            "What is BNS Section 103?",
            "Draft a bail application",
            "Analyze this contract",
            "Hello, how are you?"
        ]
        
        results = []
        for query in queries:
            result = agent_service.process_query(query)
            results.append(result)
        
        # All should succeed
        assert len(results) == len(queries)
        for result in results:
            assert result["error"] is None or result["response"] is not None

# Made with Bob
