"""
Agent Service for LawAI

Singleton service for managing the LangGraph agent.
"""

import logging
from typing import Optional, Dict, Any, AsyncGenerator
import asyncio

from agents.legal_agent import LegalAgent
from agents.intent_classifier import IntentClassifier, get_intent_classifier
from tools.registry import ToolRegistry, get_tool_registry
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class AgentService:
    """
    Singleton service for managing the legal agent.
    """
    
    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        tool_registry: Optional[ToolRegistry] = None,
        intent_classifier: Optional[IntentClassifier] = None
    ):
        """
        Initialize agent service.
        
        Args:
            llm_service: LLM service instance
            tool_registry: Tool registry instance
            intent_classifier: Intent classifier instance
        """
        self.llm_service = llm_service or LLMService()
        self.tool_registry = tool_registry or get_tool_registry()
        self.intent_classifier = intent_classifier or get_intent_classifier(self.llm_service)
        
        # Initialize agent
        self.agent = LegalAgent(
            intent_classifier=self.intent_classifier,
            tool_registry=self.tool_registry
        )
        
        logger.info("AgentService initialized successfully")
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process a user query through the agent.
        
        Args:
            query: User query string
            
        Returns:
            Agent response with:
                - response: Final response text
                - intent: Classified intent
                - metadata: Additional metadata
                - error: Error message if any
        """
        try:
            logger.info(f"Processing query: {query[:100]}...")
            
            # Agent.process is now async
            result = await self.agent.process(query)
            
            logger.info(f"Query processed successfully. Intent: {result.get('intent')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            return {
                "response": f"An error occurred while processing your query: {str(e)}",
                "intent": "unknown",
                "metadata": {},
                "error": str(e)
            }
    
    async def process_query_stream(self, query: str) -> AsyncGenerator[str, None]:
        """
        Process a user query with streaming response.
        
        Args:
            query: User query string
            
        Yields:
            Response chunks in SSE format
        """
        import json
        
        try:
            logger.info(f"Processing query with streaming: {query[:100]}...")
            
            # Process query asynchronously
            result = await self.agent.process(query)
            
            response = result.get("response", "")
            
            # Stream response in SSE format with proper JSON structure
            chunk_size = 50
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                # Format as SSE with JSON payload matching frontend expectations
                sse_data = json.dumps({"token": chunk})
                yield f"data: {sse_data}\n\n"
                await asyncio.sleep(0.05)  # Small delay for streaming effect
            
            # Send completion marker
            yield f"data: [DONE]\n\n"
            
            logger.info("Streaming completed successfully")
            
        except Exception as e:
            logger.error(f"Error in streaming query: {e}", exc_info=True)
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"
    
    def get_agent_info(self) -> Dict[str, Any]:
        """
        Get information about the agent.
        
        Returns:
            Agent information including available tools and intents
        """
        return {
            "status": "healthy",
            "available_tools": self.tool_registry.list_tools(),
            "supported_intents": [
                "rag_search",
                "chat",
                "draft_document",
                "analyze_document"
            ],
            "llm_model": "granite-13b-chat-v2",
            "version": "1.0.0"
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on agent and dependencies.
        
        Returns:
            Health status
        """
        try:
            # Check LLM service
            llm_healthy = self.llm_service is not None
            
            # Check tool registry
            tools_healthy = len(self.tool_registry.list_tools()) > 0
            
            # Check agent
            agent_healthy = self.agent is not None
            
            overall_healthy = llm_healthy and tools_healthy and agent_healthy
            
            return {
                "status": "healthy" if overall_healthy else "unhealthy",
                "components": {
                    "llm_service": "healthy" if llm_healthy else "unhealthy",
                    "tool_registry": "healthy" if tools_healthy else "unhealthy",
                    "agent": "healthy" if agent_healthy else "unhealthy"
                },
                "tools_count": len(self.tool_registry.list_tools())
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Singleton instance
_agent_service_instance: Optional[AgentService] = None


def get_agent_service(
    llm_service: Optional[LLMService] = None,
    tool_registry: Optional[ToolRegistry] = None,
    intent_classifier: Optional[IntentClassifier] = None
) -> AgentService:
    """
    Get or create agent service singleton.
    
    Args:
        llm_service: Optional LLM service
        tool_registry: Optional tool registry
        intent_classifier: Optional intent classifier
        
    Returns:
        AgentService instance
    """
    global _agent_service_instance
    if _agent_service_instance is None:
        _agent_service_instance = AgentService(
            llm_service=llm_service,
            tool_registry=tool_registry,
            intent_classifier=intent_classifier
        )
    return _agent_service_instance


def reset_agent_service():
    """Reset the agent service singleton (useful for testing)."""
    global _agent_service_instance
    _agent_service_instance = None

# Made with Bob
