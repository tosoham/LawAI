"""
Unit Tests for MCP Tools

Tests for all tool implementations including base tool, RAG search,
chat, draft document, and analyze document tools.
"""

from unittest.mock import Mock

import pytest

from tools.analyze_doc_tool import AnalyzeDocumentTool
from tools.base_tool import BaseTool, ToolParameter, ToolResult
from tools.chat_tool import ChatTool
from tools.draft_document_tool import DraftDocumentTool
from tools.rag_search_tool import RAGSearchTool
from tools.registry import ToolRegistry


# Test Base Tool
class MockTool(BaseTool):
    """Mock tool for testing base functionality"""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters(self):
        return {
            "param1": ToolParameter(
                name="param1",
                type="string",
                description="Test parameter",
                required=True
            ),
            "param2": ToolParameter(
                name="param2",
                type="integer",
                description="Optional parameter",
                required=False,
                default=10
            )
        }

    async def execute(self, **kwargs):
        return ToolResult(
            success=True,
            data={"result": "mock_result"},
            metadata={"tool": self.name}
        )


class TestBaseTool:
    """Test base tool functionality"""

    def test_tool_initialization(self):
        """Test tool can be initialized"""
        tool = MockTool()
        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"

    def test_get_metadata(self):
        """Test getting tool metadata"""
        tool = MockTool()
        metadata = tool.get_metadata()
        assert metadata.name == "mock_tool"
        assert "param1" in metadata.parameters
        assert "param2" in metadata.parameters

    def test_validate_parameters_success(self):
        """Test parameter validation with valid params"""
        tool = MockTool()
        is_valid, error = tool.validate_parameters(param1="test", param2=20)
        assert is_valid is True
        assert error is None

    def test_validate_parameters_missing_required(self):
        """Test parameter validation with missing required param"""
        tool = MockTool()
        is_valid, error = tool.validate_parameters(param2=20)
        assert is_valid is False
        assert "param1" in error

    def test_validate_parameters_wrong_type(self):
        """Test parameter validation with wrong type"""
        tool = MockTool()
        is_valid, error = tool.validate_parameters(param1=123)  # Should be string
        assert is_valid is False
        assert "string" in error.lower()

    @pytest.mark.asyncio
    async def test_safe_execute_success(self):
        """Test safe execution with valid params"""
        tool = MockTool()
        result = await tool.safe_execute(param1="test")
        assert result.success is True
        assert result.data["result"] == "mock_result"

    @pytest.mark.asyncio
    async def test_safe_execute_validation_failure(self):
        """Test safe execution with invalid params"""
        tool = MockTool()
        result = await tool.safe_execute(param2=20)  # Missing required param1
        assert result.success is False
        assert result.error is not None


class TestRAGSearchTool:
    """Test RAG search tool"""

    @pytest.fixture
    def mock_rag_service(self):
        """Create mock RAG service"""
        service = Mock()
        service.search_and_generate = Mock(return_value={
            "answer": "Test answer",
            "sources": [{"text": "Test source", "metadata": {}}],
            "query": "test query"
        })
        service.multi_collection_search = Mock(return_value={
            "answer": "Multi-collection answer",
            "sources": [{"text": "Source 1"}, {"text": "Source 2"}],
            "query": "test query"
        })
        return service

    def test_tool_initialization(self, mock_rag_service):
        """Test RAG search tool initialization"""
        tool = RAGSearchTool(mock_rag_service)
        assert tool.name == "rag_search"
        assert "search" in tool.description.lower()

    def test_tool_parameters(self, mock_rag_service):
        """Test RAG search tool parameters"""
        tool = RAGSearchTool(mock_rag_service)
        params = tool.parameters
        assert "query" in params
        assert "collection" in params
        assert "top_k" in params
        assert params["query"].required is True

    @pytest.mark.asyncio
    async def test_execute_specific_collection(self, mock_rag_service):
        """Test RAG search with specific collection"""
        tool = RAGSearchTool(mock_rag_service)
        result = await tool.execute(
            query="test query",
            collection="bns_sections",
            top_k=5
        )
        assert result.success is True
        assert "answer" in result.data
        mock_rag_service.search_and_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_all_collections(self, mock_rag_service):
        """Test RAG search across all collections"""
        tool = RAGSearchTool(mock_rag_service)
        result = await tool.execute(
            query="test query",
            collection="all",
            top_k=8
        )
        assert result.success is True
        mock_rag_service.multi_collection_search.assert_called_once()


class TestChatTool:
    """Test chat tool"""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service"""
        service = Mock()
        service.generate = Mock(return_value="Test response from LLM")
        return service

    def test_tool_initialization(self, mock_llm_service):
        """Test chat tool initialization"""
        tool = ChatTool(mock_llm_service)
        assert tool.name == "chat"
        assert "q&a" in tool.description.lower()

    def test_tool_parameters(self, mock_llm_service):
        """Test chat tool parameters"""
        tool = ChatTool(mock_llm_service)
        params = tool.parameters
        assert "message" in params
        assert "context" in params
        assert params["message"].required is True

    @pytest.mark.asyncio
    async def test_execute_without_context(self, mock_llm_service):
        """Test chat without conversation context"""
        tool = ChatTool(mock_llm_service)
        result = await tool.execute(message="What is mens rea?")
        assert result.success is True
        assert "answer" in result.data
        assert "disclaimer" in result.data["answer"].lower()
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_context(self, mock_llm_service):
        """Test chat with conversation context"""
        tool = ChatTool(mock_llm_service)
        context = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ]
        result = await tool.execute(
            message="Follow-up question",
            context=context
        )
        assert result.success is True
        assert result.data["has_context"] is True


class TestDraftDocumentTool:
    """Test draft document tool"""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service"""
        service = Mock()
        service.generate = Mock(return_value="Generated legal document content")
        return service

    def test_tool_initialization(self, mock_llm_service):
        """Test draft document tool initialization"""
        tool = DraftDocumentTool(mock_llm_service)
        assert tool.name == "draft_document"
        assert "generate" in tool.description.lower()

    def test_tool_parameters(self, mock_llm_service):
        """Test draft document tool parameters"""
        tool = DraftDocumentTool(mock_llm_service)
        params = tool.parameters
        assert "document_type" in params
        assert "case_details" in params

    @pytest.mark.asyncio
    async def test_execute_bail_application(self, mock_llm_service):
        """Test drafting bail application"""
        tool = DraftDocumentTool(mock_llm_service)
        case_details = {
            "accused_name": "John Doe",
            "fir_number": "123/2024",
            "sections": ["BNS 103"],
            "facts": "Test facts"
        }
        result = await tool.execute(
            document_type="bail_application",
            case_details=case_details
        )
        assert result.success is True
        assert "document" in result.data
        assert result.data["document_type"] == "bail_application"
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_invalid_document_type(self, mock_llm_service):
        """Test with invalid document type"""
        tool = DraftDocumentTool(mock_llm_service)
        result = await tool.execute(
            document_type="invalid_type",
            case_details={"test": "data"}
        )
        assert result.success is False
        assert "unsupported" in result.error.lower()


class TestAnalyzeDocumentTool:
    """Test analyze document tool"""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service"""
        service = Mock()
        service.generate = Mock(return_value="Document analysis results")
        return service

    def test_tool_initialization(self, mock_llm_service):
        """Test analyze document tool initialization"""
        tool = AnalyzeDocumentTool(mock_llm_service)
        assert tool.name == "analyze_document"
        assert "analyze" in tool.description.lower()

    def test_tool_parameters(self, mock_llm_service):
        """Test analyze document tool parameters"""
        tool = AnalyzeDocumentTool(mock_llm_service)
        params = tool.parameters
        assert "document_text" in params
        assert "analysis_type" in params
        assert "document_type" in params

    @pytest.mark.asyncio
    async def test_execute_full_analysis(self, mock_llm_service):
        """Test full document analysis"""
        tool = AnalyzeDocumentTool(mock_llm_service)
        document_text = "This is a test legal document with sufficient length for analysis. " * 10
        result = await tool.execute(
            document_text=document_text,
            analysis_type="full",
            document_type="contract"
        )
        assert result.success is True
        assert "analysis" in result.data
        assert result.data["analysis_type"] == "full"
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_risk_analysis(self, mock_llm_service):
        """Test risk analysis"""
        tool = AnalyzeDocumentTool(mock_llm_service)
        document_text = "Test document content. " * 20
        result = await tool.execute(
            document_text=document_text,
            analysis_type="risks"
        )
        assert result.success is True
        assert result.data["analysis_type"] == "risks"

    @pytest.mark.asyncio
    async def test_execute_document_too_short(self, mock_llm_service):
        """Test with document that's too short"""
        tool = AnalyzeDocumentTool(mock_llm_service)
        result = await tool.execute(document_text="Too short")
        assert result.success is False
        assert "too short" in result.error.lower()


class TestToolRegistry:
    """Test tool registry"""

    def test_registry_initialization(self):
        """Test registry can be initialized"""
        registry = ToolRegistry()
        assert len(registry) == 0

    def test_register_tool(self):
        """Test registering a tool"""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register_tool(tool)
        assert len(registry) == 1
        assert "mock_tool" in registry

    def test_get_tool(self):
        """Test retrieving a tool"""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register_tool(tool)
        retrieved = registry.get_tool("mock_tool")
        assert retrieved is tool

    def test_unregister_tool(self):
        """Test unregistering a tool"""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register_tool(tool)
        result = registry.unregister_tool("mock_tool")
        assert result is True
        assert len(registry) == 0

    def test_list_tools(self):
        """Test listing all tools"""
        registry = ToolRegistry()
        tool1 = MockTool()
        registry.register_tool(tool1)
        tools = registry.list_tools()
        assert "mock_tool" in tools

    def test_get_tool_metadata(self):
        """Test getting tool metadata"""
        registry = ToolRegistry()
        tool = MockTool()
        registry.register_tool(tool)
        metadata = registry.get_tool_metadata("mock_tool")
        assert metadata is not None
        assert metadata.name == "mock_tool"

    def test_clear_registry(self):
        """Test clearing all tools"""
        registry = ToolRegistry()
        registry.register_tool(MockTool())
        registry.clear()
        assert len(registry) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
