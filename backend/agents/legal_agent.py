"""
LangGraph Agent for LawAI

Orchestrates tool execution based on user intent using LangGraph.
"""

import logging
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END

from agents.state import AgentState, IntentType, update_state, add_message, set_error
from agents.intent_classifier import IntentClassifier
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class LegalAgent:
    """
    LangGraph-based agent for orchestrating legal AI tools.
    """
    
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        tool_registry: ToolRegistry
    ):
        """
        Initialize legal agent.
        
        Args:
            intent_classifier: Intent classification service
            tool_registry: Tool registry for accessing tools
        """
        self.intent_classifier = intent_classifier
        self.tool_registry = tool_registry
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph state graph.
        
        Returns:
            Compiled StateGraph
        """
        # Create graph
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("classify_intent", self._classify_intent_node)
        graph.add_node("execute_rag_search", self._execute_rag_search_node)
        graph.add_node("execute_chat", self._execute_chat_node)
        graph.add_node("execute_draft", self._execute_draft_node)
        graph.add_node("execute_analyze", self._execute_analyze_node)
        graph.add_node("format_response", self._format_response_node)
        
        # Set entry point
        graph.set_entry_point("classify_intent")
        
        # Add conditional edges from classify_intent
        graph.add_conditional_edges(
            "classify_intent",
            self._route_by_intent,
            {
                IntentType.RAG_SEARCH.value: "execute_rag_search",
                IntentType.CHAT.value: "execute_chat",
                IntentType.DRAFT_DOCUMENT.value: "execute_draft",
                IntentType.ANALYZE_DOCUMENT.value: "execute_analyze",
                IntentType.UNKNOWN.value: "execute_rag_search",  # Default to RAG
            }
        )
        
        # All tool nodes go to format_response
        graph.add_edge("execute_rag_search", "format_response")
        graph.add_edge("execute_chat", "format_response")
        graph.add_edge("execute_draft", "format_response")
        graph.add_edge("execute_analyze", "format_response")
        
        # format_response goes to END
        graph.add_edge("format_response", END)
        
        # Compile graph
        return graph.compile()
    
    async def _classify_intent_node(self, state: AgentState) -> AgentState:
        """
        Node: Classify user intent.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with intent
        """
        try:
            query = state["user_query"]
            intent = self.intent_classifier.classify(query)
            
            logger.info(f"Classified intent: {intent} for query: {query[:50]}...")
            
            return update_state(
                state,
                intent=intent,
                metadata={
                    **state.get("metadata", {}),
                    "intent_description": self.intent_classifier.get_intent_description(intent)
                }
            )
        except Exception as e:
            logger.error(f"Intent classification error: {e}", exc_info=True)
            return set_error(state, f"Intent classification failed: {str(e)}")
    
    def _route_by_intent(self, state: AgentState) -> str:
        """
        Route to appropriate tool based on intent.
        
        Args:
            state: Current agent state
            
        Returns:
            Next node name
        """
        intent = state.get("intent", IntentType.UNKNOWN.value)
        logger.info(f"Routing to intent: {intent}")
        return intent
    
    async def _execute_rag_search_node(self, state: AgentState) -> AgentState:
        """
        Node: Execute RAG search tool.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with tool results
        """
        try:
            tool = self.tool_registry.get_tool("rag_search")
            query = state["user_query"]
            
            logger.info(f"Executing RAG search for: {query[:50]}...")
            
            result = await tool.execute(query=query, top_k=5)
            
            return update_state(
                state,
                tool_results={"rag_search": result}
            )
        except Exception as e:
            logger.error(f"RAG search execution error: {e}")
            return set_error(state, f"RAG search failed: {str(e)}")
    
    async def _execute_chat_node(self, state: AgentState) -> AgentState:
        """
        Node: Execute chat tool.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with tool results
        """
        try:
            tool = self.tool_registry.get_tool("chat")
            query = state["user_query"]
            
            logger.info(f"Executing chat for: {query[:50]}...")
            
            result = await tool.execute(message=query, context=[])
            
            return update_state(
                state,
                tool_results={"chat": result}
            )
        except Exception as e:
            logger.error(f"Chat execution error: {e}")
            return set_error(state, f"Chat failed: {str(e)}")
    
    async def _execute_draft_node(self, state: AgentState) -> AgentState:
        """
        Node: Execute draft document tool.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with tool results
        """
        try:
            tool = self.tool_registry.get_tool("draft_document")
            query = state["user_query"]
            
            logger.info(f"Executing draft document for: {query[:50]}...")
            
            # Extract document type and details from query
            # For now, use simple defaults
            result = await tool.execute(
                document_type="bail_application",
                case_details=query,
                legal_provisions=""
            )
            
            return update_state(
                state,
                tool_results={"draft_document": result}
            )
        except Exception as e:
            logger.error(f"Draft document execution error: {e}")
            return set_error(state, f"Draft document failed: {str(e)}")
    
    async def _execute_analyze_node(self, state: AgentState) -> AgentState:
        """
        Node: Execute analyze document tool.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with tool results
        """
        try:
            tool = self.tool_registry.get_tool("analyze_doc")
            query = state["user_query"]
            
            logger.info(f"Executing analyze document for: {query[:50]}...")
            
            # For now, return a message asking for document upload
            result = {
                "success": True,
                "data": {
                    "analysis": "Please upload a document to analyze. Supported formats: PDF, DOCX",
                    "risks": [],
                    "recommendations": ["Upload document via the document upload endpoint"]
                }
            }
            
            return update_state(
                state,
                tool_results={"analyze_doc": result}
            )
        except Exception as e:
            logger.error(f"Analyze document execution error: {e}")
            return set_error(state, f"Analyze document failed: {str(e)}")
    
    async def _format_response_node(self, state: AgentState) -> AgentState:
        """
        Node: Format final response from tool results.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with final response
        """
        try:
            # Check for errors
            if state.get("error"):
                return update_state(
                    state,
                    final_response=f"Error: {state['error']}"
                )
            
            # Get tool results
            tool_results = state.get("tool_results", {})
            intent = state.get("intent", "")
            
            # Format based on intent
            if IntentType.RAG_SEARCH.value in intent:
                response = self._format_rag_response(tool_results.get("rag_search", {}))
            elif IntentType.CHAT.value in intent:
                response = self._format_chat_response(tool_results.get("chat", {}))
            elif IntentType.DRAFT_DOCUMENT.value in intent:
                response = self._format_draft_response(tool_results.get("draft_document", {}))
            elif IntentType.ANALYZE_DOCUMENT.value in intent:
                response = self._format_analyze_response(tool_results.get("analyze_doc", {}))
            else:
                response = "I'm not sure how to help with that. Please try rephrasing your query."
            
            return update_state(
                state,
                final_response=response
            )
        except Exception as e:
            logger.error(f"Response formatting error: {e}", exc_info=True)
            return set_error(state, f"Response formatting failed: {str(e)}")
    
    def _format_rag_response(self, result: Dict[str, Any]) -> str:
        """Format RAG search results."""
        if not result:
            return "No results found for your query."
        
        # Handle ToolResult object
        if hasattr(result, 'success'):
            if not result.success:
                return f"Search failed: {result.error}"
            result = result.data
        
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        
        response = answer
        if sources:
            response += "\n\n**Sources:**\n"
            for i, source in enumerate(sources[:3], 1):
                response += f"{i}. {source.get('metadata', {}).get('source', 'Unknown')}\n"
        
        return response
    
    def _format_chat_response(self, result: Dict[str, Any]) -> str:
        """Format chat results."""
        if not result:
            return "I'm here to help with legal queries."
        
        # Handle ToolResult object
        if hasattr(result, 'success'):
            if not result.success:
                return f"Chat failed: {result.error}"
            result = result.data
        
        return result.get("answer", "I'm here to help with legal queries.")
    
    def _format_draft_response(self, result: Dict[str, Any]) -> str:
        """Format draft document results."""
        if not result:
            return "Failed to generate document."
        
        # Handle ToolResult object
        if hasattr(result, 'success'):
            if not result.success:
                return f"Draft generation failed: {result.error}"
            result = result.data
        
        content = result.get("content", "")
        doc_type = result.get("document_type", "document")
        
        return f"**Generated {doc_type}:**\n\n{content}\n\n*Note: This is an AI-generated draft. Please review with a legal professional.*"
    
    def _format_analyze_response(self, result: Dict[str, Any]) -> str:
        """Format analyze document results."""
        if not result:
            return "Failed to analyze document."
        
        # Handle ToolResult object
        if hasattr(result, 'success'):
            if not result.success:
                return f"Analysis failed: {result.error}"
            result = result.data
        
        analysis = result.get("analysis", "")
        risks = result.get("risks", [])
        recommendations = result.get("recommendations", [])
        
        response = f"**Analysis:**\n{analysis}\n"
        
        if risks:
            response += "\n**Identified Risks:**\n"
            for risk in risks:
                response += f"- {risk}\n"
        
        if recommendations:
            response += "\n**Recommendations:**\n"
            for rec in recommendations:
                response += f"- {rec}\n"
        
        return response
    
    async def process(self, query: str) -> Dict[str, Any]:
        """
        Process a user query through the agent.
        
        Args:
            query: User query
            
        Returns:
            Agent response with final_response and metadata
        """
        from agents.state import create_initial_state
        
        # Create initial state
        initial_state = create_initial_state(query)
        
        # Run graph asynchronously
        final_state = await self.graph.ainvoke(initial_state)
        
        return {
            "response": final_state["final_response"],
            "intent": final_state.get("intent", ""),
            "metadata": final_state.get("metadata", {}),
            "error": final_state.get("error")
        }

# Made with Bob
