"""
Tool Registry

Central registry for managing and accessing all MCP tools.
"""

from typing import Dict, List, Optional
import logging
from .base_tool import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all MCP tools.
    
    Provides methods to register, retrieve, and list tools.
    Supports auto-discovery and tool metadata management.
    """
    
    def __init__(self):
        """Initialize empty tool registry"""
        self._tools: Dict[str, BaseTool] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_tool(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: Tool instance to register
            
        Raises:
            ValueError: If tool with same name already exists
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Tool must be instance of BaseTool, got {type(tool)}")
        
        tool_name = tool.name
        
        if tool_name in self._tools:
            self.logger.warning(f"Tool '{tool_name}' already registered, overwriting")
        
        self._tools[tool_name] = tool
        self.logger.info(f"Registered tool: {tool_name}")
    
    def unregister_tool(self, tool_name: str) -> bool:
        """
        Unregister a tool from the registry.
        
        Args:
            tool_name: Name of tool to unregister
            
        Returns:
            True if tool was unregistered, False if not found
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            self.logger.info(f"Unregistered tool: {tool_name}")
            return True
        return False
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.
        
        Args:
            tool_name: Name of tool to retrieve
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)
    
    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is registered.
        
        Args:
            tool_name: Name of tool to check
            
        Returns:
            True if tool exists, False otherwise
        """
        return tool_name in self._tools
    
    def list_tools(self) -> List[str]:
        """
        List all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """
        Get all registered tools.
        
        Returns:
            Dictionary of tool name to tool instance
        """
        return self._tools.copy()
    
    def get_tool_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """
        Get metadata for a specific tool.
        
        Args:
            tool_name: Name of tool
            
        Returns:
            ToolMetadata or None if tool not found
        """
        tool = self.get_tool(tool_name)
        if tool:
            return tool.get_metadata()
        return None
    
    def get_all_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Get metadata for all registered tools.
        
        Returns:
            Dictionary of tool name to metadata
        """
        metadata = {}
        for name, tool in self._tools.items():
            metadata[name] = tool.get_metadata()
        return metadata
    
    def clear(self) -> None:
        """Clear all registered tools"""
        self._tools.clear()
        self.logger.info("Cleared all tools from registry")
    
    def __len__(self) -> int:
        """Get number of registered tools"""
        return len(self._tools)
    
    def __contains__(self, tool_name: str) -> bool:
        """Check if tool is registered using 'in' operator"""
        return tool_name in self._tools
    
    def __repr__(self) -> str:
        """String representation"""
        return f"<ToolRegistry tools={list(self._tools.keys())}>"


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.
    
    Returns:
        Global ToolRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def initialize_tools(
    llm_service,
    rag_service
) -> ToolRegistry:
    """
    Initialize all tools and register them.
    
    Args:
        llm_service: LLM service instance
        rag_service: RAG service instance
        
    Returns:
        Initialized ToolRegistry
    """
    from .rag_search_tool import RAGSearchTool
    from .chat_tool import ChatTool
    from .draft_document_tool import DraftDocumentTool
    from .analyze_doc_tool import AnalyzeDocumentTool
    
    registry = get_tool_registry()
    
    # Clear existing tools
    registry.clear()
    
    # Register all tools
    registry.register_tool(RAGSearchTool(rag_service))
    registry.register_tool(ChatTool(llm_service))
    registry.register_tool(DraftDocumentTool(llm_service))
    registry.register_tool(AnalyzeDocumentTool(llm_service))
    
    logger.info(f"Initialized {len(registry)} tools: {registry.list_tools()}")
    
    return registry

# Made with Bob
