"""
MCP Tools Package

Provides all MCP tools for LawAI agent orchestration.
"""

from .base_tool import BaseTool, ToolParameter, ToolMetadata, ToolResult
from .rag_search_tool import RAGSearchTool
from .chat_tool import ChatTool
from .draft_document_tool import DraftDocumentTool
from .analyze_doc_tool import AnalyzeDocumentTool
from .registry import ToolRegistry, get_tool_registry, initialize_tools

__all__ = [
    # Base classes
    "BaseTool",
    "ToolParameter",
    "ToolMetadata",
    "ToolResult",
    
    # Tools
    "RAGSearchTool",
    "ChatTool",
    "DraftDocumentTool",
    "AnalyzeDocumentTool",
    
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "initialize_tools",
]
