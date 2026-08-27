"""
LangGraph Agent for LawAI

Orchestrates tool execution based on user intent using LangGraph.
"""

import asyncio
import logging
import os
from typing import Any
from uuid import uuid4

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from agents.citations import format_citation, source_payload
from agents.contested import develop_positions
from agents.contracts import Complexity
from agents.intent_classifier import IntentClassifier
from agents.planner import plan_query
from agents.specialists import RetrievalBudget, merge_evidence, run_specialist
from agents.state import AgentState, IntentType, set_error, update_state
from agents.triage import triage
from services.audience import Audience
from services.grounded_answer import GroundedAnswer, get_grounded_answer_service
from services.legal_graph import ACT_LONG_NAMES, get_legal_graph
from services.vector_service import VectorService
from tools.base_tool import ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def conversation_memory_enabled() -> bool:
    """
    Whether the agent remembers a conversation across turns.

    Off by default. The saver available here keeps threads in process memory,
    so it grows without bound and does not survive a restart or a second
    worker -- fine for a desktop session or a test, wrong for a deployment
    that has not chosen it. Turning it on is a decision about where state
    lives, not a convenience.
    """
    return os.getenv("ENABLE_CONVERSATION_MEMORY", "false").strip().lower() in {
        "1", "true", "yes",
    }


def draft_confirmation_enabled() -> bool:
    """
    Whether drafting pauses for confirmation before it writes.

    Requires conversation memory: ``interrupt`` records where it stopped in a
    checkpoint, so without one there is nothing to resume from and the pause
    would simply lose the turn.
    """
    return os.getenv("ENABLE_DRAFT_CONFIRMATION", "false").strip().lower() in {
        "1", "true", "yes",
    }


def _make_checkpointer():
    """The checkpointer, or ``None`` when memory is off."""
    if not conversation_memory_enabled():
        return None
    from langgraph.checkpoint.memory import InMemorySaver

    logger.info("conversation memory is on (in-process; not shared between workers)")
    return InMemorySaver()

# The three statute collections, searched together. Judgements are reached
# through the graph rather than by searching that collection directly: a
# judgement chunk carries no section number, so it seeds no expansion and
# cannot be verified against a provision.
CORPUS_COLLECTIONS = [
    VectorService.BNS_COLLECTION,
    VectorService.BNSS_COLLECTION,
    VectorService.BSA_COLLECTION,
]


def _grounded_payload(grounded: GroundedAnswer) -> dict[str, Any]:
    """
    Flatten a GroundedAnswer into the shape the rest of the agent expects.

    ``answer`` and ``sources`` keep their existing meaning so nothing
    downstream breaks; ``verification`` is additive, and carries the part a
    client needs in order to render a claim as what it actually is.
    """
    return {
        "answer": grounded.answer,
        "sources": grounded.sources,
        "abstained": grounded.abstained,
        "graph_context": grounded.graph_context,
        "verification": {
            "claims": [
                {
                    "text": claim.text,
                    "epistemic_class": claim.epistemic_class.value,
                    # Typed {ref, kind}, matching ClaimResponse on
                    # /search/grounded exactly. These were plain strings, and
                    # the two endpoints disagreeing about the shape of the same
                    # field crashed the UI on every answer -- the component
                    # reads source.ref, the tests used the typed shape, and
                    # nothing compared the two payloads.
                    "sources": [
                        {"ref": s.ref, "kind": s.kind.value} for s in claim.sources
                    ],
                    "verbatim_span": claim.verbatim_span,
                    "positions": [
                        {"summary": p.summary, "authority": p.authority}
                        for p in claim.positions
                    ],
                }
                for claim in grounded.structured.claims
            ],
            "metrics": grounded.metrics.to_dict(),
            # Every check, not only the failures: an answer that quietly drops
            # what it could not support looks identical to one that never
            # overreached, and the difference is the record worth keeping.
            "verdicts": [
                {
                    "index": v.index,
                    "verified": v.verified,
                    "original_class": v.original_class.value,
                    "reason": v.reason,
                }
                for v in grounded.verdicts
            ],
            "removed": grounded.metrics.unsupported,
        },
        "trace": grounded.trace,
    }


class LegalAgent:
    """
    LangGraph-based agent for orchestrating legal AI tools.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        tool_registry: ToolRegistry,
        llm_service=None,
    ):
        """
        Initialize legal agent.

        Args:
            intent_classifier: Intent classification service
            tool_registry: Tool registry for accessing tools
            llm_service: LLM service, required only for the live-research node,
                which lets the model call tools for itself
        """
        self.intent_classifier = intent_classifier
        self.tool_registry = tool_registry
        self.llm_service = llm_service
        self.checkpointer = _make_checkpointer()
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
        graph.add_node("triage", self._triage_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("run_specialist", self._specialist_node)
        graph.add_node("gather", self._gather_node)
        graph.add_node("execute_rag_search", self._execute_rag_search_node)
        graph.add_node("execute_chat", self._execute_chat_node)
        graph.add_node("execute_draft", self._execute_draft_node)
        graph.add_node("execute_analyze", self._execute_analyze_node)
        graph.add_node("execute_live_research", self._execute_live_research_node)
        graph.add_node("format_response", self._format_response_node)

        # Set entry point
        graph.set_entry_point("classify_intent")

        # Triage sits between classification and routing: it can only escalate
        # a question *about the law*, so it needs the intent first, and routing
        # needs its verdict.
        graph.add_edge("classify_intent", "triage")

        # The multi-agent path. `plan` fans out with Send() to as many copies
        # of `run_specialist` as the plan names; `gather` runs once they have
        # all reported, which LangGraph arranges by making it their only edge.
        graph.add_conditional_edges(
            "plan", self._dispatch_specialists, ["run_specialist", "gather"]
        )
        graph.add_edge("run_specialist", "gather")
        graph.add_edge("gather", "format_response")

        # Add conditional edges from triage
        graph.add_conditional_edges(
            "triage",
            self._route_by_intent,
            {
                "plan": "plan",
                IntentType.RAG_SEARCH.value: "execute_rag_search",
                IntentType.CHAT.value: "execute_chat",
                IntentType.DRAFT_DOCUMENT.value: "execute_draft",
                IntentType.ANALYZE_DOCUMENT.value: "execute_analyze",
                IntentType.LIVE_RESEARCH.value: "execute_live_research",
                IntentType.UNKNOWN.value: "execute_rag_search",  # Default to RAG
            }
        )

        # All tool nodes go to format_response
        graph.add_edge("execute_rag_search", "format_response")
        graph.add_edge("execute_chat", "format_response")
        graph.add_edge("execute_draft", "format_response")
        graph.add_edge("execute_analyze", "format_response")
        graph.add_edge("execute_live_research", "format_response")

        # format_response goes to END
        graph.add_edge("format_response", END)

        # Compile graph.
        #
        # A checkpointer is attached only when conversation memory is switched
        # on. Compiling with one unconditionally would be worse than useless:
        # LangGraph then *requires* a thread_id on every invocation, so a
        # single-turn caller that never wanted memory would start failing, and
        # the in-memory saver grows without bound for a server that never reads
        # a thread back.
        return graph.compile(checkpointer=self.checkpointer)

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
            intent = self.intent_classifier.classify(
                query, workspace=state.get("workspace")
            )

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

    async def _triage_node(self, state: AgentState) -> AgentState:
        """
        Node: decide how much machinery this question deserves.

        Cheap and model-free, so it runs on every query without changing what
        an ordinary one costs. Measured over the fixture, 69 of 69 answerable
        golden queries and all 6 adversarial ones come out ``simple``.
        """
        complexity, reason = triage(state["user_query"])
        logger.info(f"Triage: {complexity.value} ({reason})")
        return update_state(
            state,
            complexity=complexity.value,
            metadata={
                **state.get("metadata", {}),
                "triage": {"complexity": complexity.value, "reason": reason},
            },
        )

    def _route_by_intent(self, state: AgentState) -> str:
        """
        Route to a tool, or to the multi-agent path.

        Only a question *about the law* is ever escalated. A draft, an
        analysis, a greeting or a live-research request goes to its own node
        whatever triage thought: those are not research questions, and fanning
        one out would buy nothing but latency.
        """
        intent = state.get("intent", IntentType.UNKNOWN.value)
        complexity = state.get("complexity", Complexity.SIMPLE.value)

        researchable = intent in (IntentType.RAG_SEARCH.value, IntentType.UNKNOWN.value)
        if researchable and complexity != Complexity.SIMPLE.value:
            logger.info(f"Routing to the multi-agent path ({complexity})")
            return "plan"

        logger.info(f"Routing to intent: {intent}")
        return intent

    async def _plan_node(self, state: AgentState) -> AgentState:
        """Node: choose which specialists to run."""
        complexity = Complexity(state.get("complexity", Complexity.SIMPLE.value))
        plan = await asyncio.to_thread(
            plan_query, state["user_query"], complexity
        )
        return update_state(
            state,
            plan=plan,
            metadata={
                **state.get("metadata", {}),
                "plan": [
                    {"specialist": s.specialist.value, "reason": s.reason}
                    for s in plan.steps
                ],
            },
        )

    def _dispatch_specialists(self, state: AgentState) -> list:
        """
        Fan out to one ``run_specialist`` per plan step.

        ``Send`` carries the step on the message rather than on the state,
        because every copy runs against the same state and would otherwise have
        no way to know which step is its own. Returning the gather node
        directly for an empty plan keeps the graph from stalling on a fan-out
        of nothing.
        """
        plan = state.get("plan")
        if plan is None or not plan.steps:
            return ["gather"]
        return [
            Send("run_specialist", {**state, "_step": step}) for step in plan.steps
        ]

    async def _specialist_node(self, state: AgentState) -> dict[str, Any]:
        """
        Node: run one specialist.

        Returns a **partial** update rather than the whole state. Several of
        these run in the same superstep and their `evidence` lists are merged
        by the reducer; returning the full state would re-append whatever was
        already there.
        """
        step = state["_step"]
        result = await asyncio.to_thread(
            run_specialist, step, state["user_query"], RetrievalBudget()
        )
        return {
            "evidence": result.evidence,
            "errors": result.errors,
            "tool_results": {
                step.specialist.value: {
                    "retrievals": result.retrievals,
                    "model_calls": result.model_calls,
                    "evidence": len(result.evidence),
                }
            },
        }

    async def _gather_node(self, state: AgentState) -> AgentState:
        """
        Node: turn what the specialists found into a verified answer.

        The evidence is folded back into the shape ``GroundedAnswerService``
        already consumes and handed to it. Everything after this point --
        graph expansion, the synthesis prompt, per-claim verification, the one
        regeneration attempt, abstention, metrics -- is the single-pass code
        path, unchanged and unbypassed. Specialists changed what reaches the
        prompt; they changed nothing about what is checked afterwards.
        """
        retrieved = merge_evidence(state.get("evidence") or [])
        if not retrieved.get("documents"):
            # Nothing found. Falling through to the ordinary path rather than
            # abstaining here: a fan-out that came back empty says the plan was
            # wrong, not that the corpus cannot answer the question.
            logger.info("specialists found nothing; falling back to a single pass")
            return await self._execute_rag_search_node(state)

        positions: list[Any] = []
        if state.get("complexity") == Complexity.CONTESTED.value:
            # The debate runs on what the specialists gathered rather than
            # retrieving for itself: both advocates must argue from the same
            # material, or the disagreement between them is partly a
            # disagreement about what they were shown.
            positions, contest_errors = await asyncio.to_thread(
                develop_positions,
                state["user_query"],
                self._contested_sides(state),
                self.rag_context(retrieved),
            )
            state = update_state(state, errors=contest_errors)

        grounded = await asyncio.to_thread(
            get_grounded_answer_service().answer,
            state["user_query"],
            CORPUS_COLLECTIONS,
            5,
            Audience.CITIZEN,
            retrieved,
        )
        payload = _grounded_payload(grounded)
        if positions:
            # Reported alongside the verified answer, never merged into it. The
            # advocates' prose is unverified argument; the claims beside it went
            # through the verifier. Flattening the two would make an argument
            # indistinguishable from a checked statement of law, which is the
            # single distinction this system exists to preserve.
            payload["positions"] = [
                {
                    "label": p.label,
                    "summary": p.summary,
                    "authority": p.authority,
                    "rebuttal": p.rebuttal,
                    "supported": p.supported,
                }
                for p in positions
            ]

        return update_state(
            state,
            positions=positions,
            tool_results={"rag_search": payload},
            metadata={
                **state.get("metadata", {}),
                "specialist_errors": [e.model_dump() for e in state.get("errors") or []],
            },
        )

    def _contested_sides(self, state: AgentState) -> tuple[str, str]:
        """
        The two readings to develop, taken from curated data where it exists.

        `data/curated/doctrines.json` records where authority splits and names
        both sides without declaring a winner -- exactly the input this needs,
        and exactly what a model should not be asked to invent. Where the
        question is contested for another reason (a constitutional challenge
        with no curated doctrine behind it), the sides fall back to the generic
        pair, because a question can be genuinely open without this repository
        having catalogued it.
        """
        graph = get_legal_graph()
        for doctrine in graph.doctrines.values():
            if not doctrine.contested:
                continue
            if any(key in state["user_query"] for key in doctrine.applies_to):
                note = doctrine.contest_note or doctrine.summary
                return (f"{doctrine.name}: {note}", f"The contrary reading of {doctrine.name}")
        return (
            "the provision should be read narrowly",
            "the provision should be read broadly",
        )

    @staticmethod
    def rag_context(retrieved: dict[str, Any]) -> str:
        """The gathered material as text, for an advocate to argue from."""
        lines: list[str] = []
        for index, document in enumerate(retrieved.get("documents", [])[:12]):
            metadata = retrieved.get("metadatas", [])[index] if index < len(
                retrieved.get("metadatas", [])
            ) else {}
            label = metadata.get("short_name") or metadata.get("case_name") or "?"
            number = metadata.get("section_number") or metadata.get("parent_id") or ""
            lines.append(f"[{label} {number}] {document[:800]}")
        return "\n\n".join(lines)

    async def _execute_rag_search_node(self, state: AgentState) -> AgentState:
        """
        Node: answer from the corpus, with every claim checked.

        This is the grounded pipeline rather than the plain RAG tool, so the
        agent's main path gets the verifier: a claim that cannot be supported
        is removed, and a question nothing supports is refused instead of
        answered. The tool is still registered and still reachable through
        ``/search/rag`` -- what changed is what the agent does by default.

        All three statute collections are searched. The agent cannot know in
        advance whether a question is about offences, procedure or evidence,
        and a merged ranking puts an exact citation hit first for free.
        """
        try:
            query = state["user_query"]
            logger.info(f"Executing grounded search for: {query[:50]}...")

            grounded = await asyncio.to_thread(
                get_grounded_answer_service().answer,
                query=query,
                collection=CORPUS_COLLECTIONS,
                top_k=5,
            )

            return update_state(
                state,
                tool_results={"rag_search": _grounded_payload(grounded)},
            )
        except Exception as e:
            logger.error(f"Grounded search execution error: {e}", exc_info=True)
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
        query = state["user_query"]
        document_type = self._infer_document_type(query)

        # Pause for confirmation before producing a document, when asked to.
        # A drafted legal document is the one output here a person may file
        # rather than read, and the document type is *inferred* from the query
        # -- inferring "bail application" from a question that wanted a
        # complaint produces something plausible and wrong in a way an answer
        # never is. Off by default: it needs a checkpointer and a caller that
        # knows how to resume.
        #
        # Deliberately outside the try below. `interrupt` signals by raising
        # GraphInterrupt, which is an Exception, so an `except Exception` around
        # it swallows the pause and reports it as a failed draft -- which is
        # exactly what happened the first time this was written, and it looked
        # like the flag simply not working.
        if draft_confirmation_enabled() and self.checkpointer is not None:
            from langgraph.types import interrupt

            interrupt(
                {
                    "awaiting": "draft_confirmation",
                    "document_type": document_type,
                    "query": query,
                }
            )

        try:
            tool = self.tool_registry.get_tool("draft_document")

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
        # Ahead of "bail": an "affidavit in support of the bail application" is
        # an affidavit. Same principle that puts "notice" ahead of "contract".
        ("affidavit", "affidavit"),
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

    LIVE_RESEARCH_SYSTEM_PROMPT = (
        "You are a legal research assistant for Indian law.\n\n"
        "You have two kinds of source available:\n"
        "1. search_local_corpus - a verified corpus holding the complete text of the "
        "Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya "
        "Sakshya Adhiniyam (2023), plus landmark Supreme Court judgements. Prefer it "
        "for statutory provisions and settled law.\n"
        "2. live_case_law_search and fetch_judgment - authentic judiciary sources "
        "queried live. The corpus is a snapshot, so use these for recent, current or "
        "dated judgements it cannot contain.\n\n"
        "Start with whichever fits the question, and consult both when a recent "
        "decision needs to be read against the statute. Cite the section or case you "
        "rely on, give the court and date for judgements, and say plainly when the "
        "sources do not settle the question. Never invent a citation."
    )

    async def _execute_live_research_node(self, state: AgentState) -> AgentState:
        """
        Node: answer using live judiciary sources, letting the model drive.

        Unlike the other nodes, which call one predetermined tool, this hands the
        model a set of tools and lets it decide what to consult -- the corpus, a
        live search, or both -- because whether a question needs current data is
        a judgement the classifier cannot reliably make on keywords alone.
        """
        try:
            query = state["user_query"]
            logger.info(f"Executing live research for: {query[:50]}...")

            if self.llm_service is None:
                return set_error(
                    state, "Live research is unavailable: no LLM service configured"
                )

            from tools.live_case_law_tool import build_openai_tool_schemas

            result = await asyncio.to_thread(
                self.llm_service.generate_with_tools,
                prompt=query,
                tools=build_openai_tool_schemas(),
                executor=self._run_research_tool,
                system=self.LIVE_RESEARCH_SYSTEM_PROMPT,
            )

            return update_state(
                state,
                tool_results={"live_research": result},
                metadata={
                    **state.get("metadata", {}),
                    "tools_invoked": [c["name"] for c in result.get("tool_calls", [])],
                },
            )
        except Exception as e:
            logger.error(f"Live research execution error: {e}", exc_info=True)
            return set_error(state, f"Live research failed: {e!s}")

    def _run_research_tool(self, name: str, arguments: dict) -> dict:
        """
        Execute a tool the model asked for.

        Runs synchronously because it is already off the event loop, inside the
        thread running ``generate_with_tools``.
        """
        tool = self.tool_registry.get_tool(
            "rag_search" if name == "search_local_corpus" else name
        )
        if tool is None:
            return {"success": False, "error": f"Unknown tool: {name}"}

        if name == "search_local_corpus":
            arguments = {
                "query": arguments.get("query", ""),
                "collection": arguments.get("collection"),
                "top_k": 5,
            }

        result = asyncio.run(tool.safe_execute(**arguments))

        if not result.success:
            return {"success": False, "error": result.error}
        return {"success": True, "data": result.data}

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
            elif IntentType.LIVE_RESEARCH.value in intent:
                response = self._format_live_research_response(
                    tool_results.get("live_research", {})
                )
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
        cited = self._cited_sources(result)

        response = answer
        if cited:
            response += "\n\n**Sources:**\n"
            for i, citation in enumerate(cited, 1):
                response += f"{i}. {citation}\n"

        return response

    @staticmethod
    def _cited_sources(result: dict[str, Any]) -> list[str]:
        """
        The authority the answer actually rests on, not what retrieval returned.

        Listing the retrieved chunks was misleading in both directions: it
        repeated a section whose chunks both ranked, and it named provisions no
        claim relied on. An answer about theft footnoted BNSS 480 twice and a
        section about failing to appear on bail, none of which it cited.

        Falls back to the retrieved sources when there are no typed claims --
        an abstention, or a caller that is not using the grounded path.
        """
        claims = (result.get("verification") or {}).get("claims") or []
        refs: list[str] = []
        for claim in claims:
            for source in claim.get("sources", []):
                # Typed {ref, kind}, matching the API. Read as bare strings this
                # raised "unhashable type: dict" into the response formatter,
                # which swallowed it and returned an empty answer.
                ref = source["ref"] if isinstance(source, dict) else source
                if ref not in refs:
                    refs.append(ref)

        if refs:
            graph = get_legal_graph()
            citations = []
            for ref in refs:
                node = graph.sections.get(ref)
                if node:
                    citations.append(
                        format_citation({
                            "section_number": node.section,
                            "act": ACT_LONG_NAMES.get(node.act, node.act),
                            "title": node.title,
                        })
                    )
                elif ref in graph.judgements:
                    judgement = graph.judgements[ref]
                    citations.append(
                        format_citation({
                            "case_name": judgement.case_name,
                            "citation": judgement.citation,
                        })
                    )
            return citations

        return [
            format_citation(source.get("metadata", {}))
            for source in result.get("sources", [])[:3]
        ]

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

    def _format_live_research_response(self, result: dict[str, Any]) -> str:
        """
        Format a tool-assisted answer, listing the live authorities consulted.

        Live results are retrieved rather than curated, so they are surfaced with
        court, date and source URL and labelled as such.
        """
        if not result:
            return "No research results available."

        answer = result.get("content", "").strip()
        if not answer:
            answer = "I could not produce an answer from the available sources."

        live_sources: list[str] = []
        seen: set[str] = set()
        for call in result.get("tool_calls", []):
            data = (call.get("result") or {}).get("data") or {}
            for hit in data.get("results", []):
                url = hit.get("source_url")
                if not url or url in seen:
                    continue
                seen.add(url)
                bits = [b for b in (hit.get("title"), hit.get("court"), hit.get("date")) if b]
                live_sources.append(f"- {' — '.join(bits)}\n  {url}")
            if data.get("doc_id") and data.get("source_url") not in seen:
                seen.add(data["source_url"])
                bits = [b for b in (data.get("title"), data.get("date")) if b]
                live_sources.append(f"- {' — '.join(bits)}\n  {data['source_url']}")

        if live_sources:
            answer += (
                "\n\n**Live sources consulted** (retrieved from public judiciary "
                "records, not the verified corpus — please confirm before relying "
                "on them):\n" + "\n".join(live_sources[:8])
            )

        answer += (
            "\n\n*DISCLAIMER: AI-generated legal information. Verify against the "
            "official record and consult a qualified lawyer.*"
        )
        return answer

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

    @staticmethod
    def _unwrap(result: Any) -> dict[str, Any]:
        """Get the payload out of a ToolResult, or pass a plain dict through."""
        if hasattr(result, "success"):
            return result.data if result.success and result.data else {}
        return result if isinstance(result, dict) else {}

    def _collect_sources(self, tool_results: dict[str, Any]) -> tuple[list, list]:
        """
        Pull citable sources out of whatever tools ran.

        Returns ``(corpus_sources, live_sources)`` as two separate lists rather
        than one tagged list. Corpus hits are verified; live judiciary hits are
        retrieved and unverified. Keeping them in distinct keys means a client
        cannot accidentally render them as one body of authority — which is the
        whole reason the distinction exists.
        """
        corpus: list[dict[str, Any]] = []
        live: list[dict[str, Any]] = []

        rag = self._unwrap(tool_results.get("rag_search"))
        corpus.extend(source_payload(source) for source in rag.get("sources", []))

        # The live-research node records every tool the model chose to call, so
        # both local and live hits can turn up here.
        research = self._unwrap(tool_results.get("live_research"))
        for call in research.get("tool_calls", []) or []:
            payload = call.get("result") or {}
            if not isinstance(payload, dict) or not payload.get("success", True):
                continue

            if call.get("name") == "search_local_corpus":
                corpus.extend(
                    source_payload(source) for source in payload.get("sources", [])
                )
                continue

            for hit in payload.get("results", []) or []:
                live.append({
                    "doc_id": hit.get("doc_id"),
                    "title": hit.get("title"),
                    "court": hit.get("court"),
                    "date": hit.get("date"),
                    "snippet": hit.get("snippet"),
                    "source_url": hit.get("source_url"),
                    "cited_by": hit.get("cited_by"),
                })

        return corpus, live

    async def process(
        self,
        query: str,
        workspace: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Process a user query through the agent.

        Args:
            query: User query
            workspace: Which UI workspace it came from, when known
            thread_id: Conversation this turn belongs to. Only meaningful when
                ENABLE_CONVERSATION_MEMORY is on; ignored otherwise, so a
                caller that always sends one keeps working either way.

        Returns:
            Agent response with the answer, the classified intent, the sources
            behind it, and any error.
        """
        from agents.state import create_initial_state

        # Create initial state
        initial_state = create_initial_state(query, workspace=workspace)

        # Run graph asynchronously.
        #
        # The config is only passed when there is a checkpointer to use it.
        # LangGraph rejects a thread_id on a graph compiled without one, so
        # sending it unconditionally would make every caller that passes a
        # thread fail the moment memory is switched off -- which is the
        # default, and therefore the configuration nobody would test.
        config = None
        if self.checkpointer is not None:
            # A checkpointer makes thread_id compulsory -- LangGraph refuses to
            # run without one -- so a caller that switched memory on and then
            # asked a single question would get a ValueError rather than an
            # answer. A turn with no thread gets a throwaway one: it runs
            # normally, checkpoints to an id nothing will ask for again, and
            # shares memory with nothing.
            config = {
                "configurable": {"thread_id": thread_id or f"anon-{uuid4()}"}
            }
        final_state = await self.graph.ainvoke(initial_state, config=config)

        corpus_sources, live_sources = self._collect_sources(
            final_state.get("tool_results", {}) or {}
        )

        tool_results = final_state.get("tool_results", {}) or {}
        verification = self._unwrap(tool_results.get("rag_search")).get("verification")

        return {
            "response": final_state["final_response"],
            "intent": final_state.get("intent", ""),
            "metadata": final_state.get("metadata", {}),
            "sources": corpus_sources,
            "live_sources": live_sources,
            # Present only on the grounded path, and additive: a client that
            # ignores it still gets the same answer it always did, and one that
            # reads it can show a claim as what it actually is rather than as
            # another sentence.
            "verification": verification,
            "error": final_state.get("error")
        }
