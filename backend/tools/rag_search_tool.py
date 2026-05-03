"""
RAG Search Tool

Search Indian legal corpus (BNS, BNSS, BSA, SC judgements) using RAG.
"""

from typing import Dict, Optional
from .base_tool import BaseTool, ToolParameter, ToolResult
from backend.services.rag_service import RAGService


class RAGSearchTool(BaseTool):
    """
    Tool for searching Indian legal corpus using RAG.
    
    Searches across BNS, BNSS, BSA, and SC judgements collections
    and returns relevant information with citations.
    """
    
    def __init__(self, rag_service: RAGService):
        """
        Initialize RAG search tool.
        
        Args:
            rag_service: RAG service instance
        """
        super().__init__()
        self.rag_service = rag_service
        self.examples = [
            "Find provisions for anticipatory bail",
            "What are the sections related to theft in BNS?",
            "Search for Supreme Court rulings on bail in murder cases",
            "Find sections about arrest procedures in BNSS"
        ]
    
    @property
    def name(self) -> str:
        return "rag_search"
    
    @property
    def description(self) -> str:
        return "Search Indian legal corpus (BNS, BNSS, BSA, SC judgements) for relevant legal information"
    
    @property
    def parameters(self) -> Dict[str, ToolParameter]:
        return {
            "query": ToolParameter(
                name="query",
                type="string",
                description="Search query for legal information",
                required=True
            ),
            "collection": ToolParameter(
                name="collection",
                type="string",
                description="Specific collection to search (bns|bnss|bsa|sc_judgements|all)",
                required=False,
                default="all"
            ),
            "top_k": ToolParameter(
                name="top_k",
                type="integer",
                description="Number of results to return",
                required=False,
                default=5
            )
        }
    
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute RAG search.
        
        Args:
            query: Search query
            collection: Collection to search (optional, default: all)
            top_k: Number of results (optional, default: 5)
            
        Returns:
            ToolResult with answer and sources
        """
        try:
            query = kwargs.get("query")
            collection = kwargs.get("collection", "all")
            top_k = kwargs.get("top_k", 5)
            
            self.logger.info(f"RAG search: query='{query}', collection={collection}, top_k={top_k}")
            
            # Perform RAG search
            if collection == "all":
                # Search across all collections
                collections = ["bns_sections", "bnss_sections", "bsa_sections", "sc_judgements"]
                result = self.rag_service.multi_collection_search(
                    query=query,
                    collections=collections,
                    top_k_per_collection=max(1, top_k // len(collections))
                )
            else:
                # Search specific collection
                result = self.rag_service.search_and_generate(
                    query=query,
                    collection=collection,
                    top_k=top_k
                )
            
            if not result:
                return ToolResult(
                    success=False,
                    error="No results found for the query"
                )
            
            # Format response
            response_data = {
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
                "query": query,
                "collection": collection,
                "num_results": len(result.get("sources", []))
            }
            
            return ToolResult(
                success=True,
                data=response_data,
                metadata={
                    "tool": self.name,
                    "collection": collection,
                    "top_k": top_k
                }
            )
            
        except Exception as e:
            self.logger.error(f"RAG search failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"RAG search failed: {str(e)}"
            )

# Made with Bob
