"""
MCP Tools Package

Provides all MCP tools for LawAI agent orchestration.
"""

from .analyze_doc_tool import AnalyzeDocumentTool
from .base_tool import BaseTool, ToolMetadata, ToolParameter, ToolResult
from .chat_tool import ChatTool
from .draft_document_tool import DraftDocumentTool
from .rag_search_tool import RAGSearchTool
from .registry import ToolRegistry, get_tool_registry, initialize_tools

__all__ = [
    "AnalyzeDocumentTool",
    "BaseTool",
    "ChatTool",
    "DraftDocumentTool",
    "RAGSearchTool",
    "ToolMetadata",
    "ToolParameter",
    "ToolRegistry",
    "ToolResult",
    "get_tool_registry",
    "initialize_tools",
]
