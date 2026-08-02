"""
LangGraph Agent for LawAI

Orchestrates tool execution based on user intent using LangGraph.
"""

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from agents.intent_classifier import IntentClassifier
from agents.state import AgentState, IntentType, set_error, update_state
from tools.base_tool import ToolResult
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
            return set_error(state, f"Intent classification failed: {e!s}")

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
            return set_error(state, f"RAG search failed: {e!s}")

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
            return set_error(state, f"Chat failed: {e!s}")

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

            document_type = self._infer_document_type(query)

            logger.info(
                f"Executing draft document ({document_type}) for: {query[:50]}..."
            )

            result = await tool.execute(
                document_type=document_type,
                case_details={"request": query},
            )

            return update_state(
                state,
                tool_results={"draft_document": result}
            )
        except Exception as e:
            logger.error(f"Draft document execution error: {e}")
            return set_error(state, f"Draft document failed: {e!s}")

    # Keyword -> document type, checked in order. Words that name the document
    # being drafted come before words that merely describe its subject matter,
    # so "legal notice for breach of contract" is a notice, not an agreement.
    _DOCUMENT_TYPE_KEYWORDS = (
        ("bail", "bail_application"),
        ("notice", "notice"),
        ("petition", "petition"),
        ("writ", "petition"),
        ("appeal", "petition"),
        ("agreement", "agreement"),
        ("contract", "agreement"),
        ("mou", "agreement"),
        ("lease", "agreement"),
    )

    @classmethod
    def _infer_document_type(cls, query: str) -> str:
        """
        Infer which document the user wants drafted.

        The agent graph has no structured input, so the type is derived from the
        query text; bail applications remain the default because they are the most
        common request in this domain.
        """
        query_lower = query.lower()
        for keyword, document_type in cls._DOCUMENT_TYPE_KEYWORDS:
            if keyword in query_lower:
                return document_type
        return "bail_application"

    # Queries at least this long are treated as pasted document text rather than a
    # request to analyse a document that has not been supplied yet. Matches the
    # minimum length AnalyzeDocumentTool itself enforces.
    _MIN_INLINE_DOCUMENT_CHARS = 100

    async def _execute_analyze_node(self, state: AgentState) -> AgentState:
        """
        Node: Execute analyze document tool.

        Args:
            state: Current agent state

        Returns:
            Updated state with tool results
        """
        try:
            tool = self.tool_registry.get_tool("analyze_document")
            query = state["user_query"]

            logger.info(f"Executing analyze document for: {query[:50]}...")

            # The agent graph has no file-upload channel, so the only document text
            # available is whatever the user pasted into the query. Anything long
            # enough to plausibly be a document is analysed directly; shorter inputs
            # are a request to analyse something not yet provided.
            document_text = query.strip()

            if tool is not None and len(document_text) >= self._MIN_INLINE_DOCUMENT_CHARS:
                result = await tool.execute(document_text=document_text, analysis_type="full")
            else:
                # Must be a ToolResult, not a bare dict: _format_analyze_response
                # detects the tool's payload via `hasattr(result, "success")`, and a
                # dict fails that check, yielding an empty analysis.
                result = ToolResult(
                    success=True,
                    data={
                        "analysis": (
                            "Please provide the document to analyse. You can paste its "
                            "text directly into your message, or upload a PDF/DOCX to "
                            "the /api/v1/documents/analyze endpoint."
                        ),
                        "risks": [],
                        "recommendations": [
                            "Paste the document text into your message, or",
                            "Upload the file via POST /api/v1/documents/analyze",
                        ],
                    },
                )

            return update_state(
                state,
                tool_results={"analyze_doc": result}
            )
        except Exception as e:
            logger.error(f"Analyze document execution error: {e}")
            return set_error(state, f"Analyze document failed: {e!s}")

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
            return set_error(state, f"Response formatting failed: {e!s}")

    def _format_rag_response(self, result: dict[str, Any]) -> str:
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

    def _format_chat_response(self, result: dict[str, Any]) -> str:
        """Format chat results."""
        if not result:
            return "I'm here to help with legal queries."

        # Handle ToolResult object
        if hasattr(result, 'success'):
            if not result.success:
                return f"Chat failed: {result.error}"
            result = result.data

        return result.get("answer", "I'm here to help with legal queries.")

    def _format_draft_response(self, result: dict[str, Any]) -> str:
        """Format draft document results."""
        if not result:
            return "Failed to generate document."

        # Handle ToolResult object
        if hasattr(result, 'success'):
            if not result.success:
                return f"Draft generation failed: {result.error}"
            result = result.data

        # DraftDocumentTool returns the drafted text under "document".
        content = result.get("document") or result.get("content", "")
        doc_type = result.get("document_type", "document")

        return f"**Generated {doc_type}:**\n\n{content}\n\n*Note: This is an AI-generated draft. Please review with a legal professional.*"

    def _format_analyze_response(self, result: dict[str, Any]) -> str:
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

    async def process(self, query: str) -> dict[str, Any]:
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
