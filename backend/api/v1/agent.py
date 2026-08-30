"""
Agent API Endpoints

FastAPI routes for LangGraph agent interactions.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.agent_service import get_agent_service
from services.auth import PayingUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# Request/Response Models
class AgentQueryRequest(BaseModel):
    """Request model for agent query"""
    query: str = Field(..., description="User query", min_length=1, max_length=5000)
    stream: bool = Field(default=False, description="Enable streaming response")
    workspace: str | None = Field(
        default=None,
        description=(
            "Which UI workspace the query was typed in: chat, search, "
            "research, draft or analyze. Optional, so every existing caller "
            "keeps working. Where it is given, it settles the intent rather "
            "than leaving it to be inferred from keywords."
        ),
    )
    thread_id: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Conversation this turn belongs to. Only meaningful when the "
            "server has ENABLE_CONVERSATION_MEMORY on; ignored otherwise, so "
            "a client may always send one."
        ),
    )


class AgentQueryResponse(BaseModel):
    """Response model for agent query"""
    response: str = Field(..., description="Agent response")
    intent: str = Field(..., description="Classified intent")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    agent_trail: dict[str, Any] | None = Field(
        default=None,
        description=(
            "How a multi-agent answer was arrived at: what triage decided and "
            "why, which researchers ran and what each cost, any that failed, "
            "and both sides of a contested question with their rebuttals. "
            "Null on the single-pass path, where there is no exchange to show."
        ),
    )
    sources: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Citable hits from the verified local corpus that back this answer."
        ),
    )
    verification: dict[str, Any] | None = Field(
        None,
        description=(
            "Present when the answer went through the grounded path: the typed "
            "claims with their epistemic class, the grounding metrics, and how "
            "many claims the verifier removed. Additive — a client that ignores "
            "it gets the same `response` it always did."
        ),
    )
    live_sources: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Hits retrieved live from public judiciary records. Kept in a "
            "separate field from `sources` on purpose: these are current but "
            "unverified, and must not be presented as equivalent authority."
        ),
    )
    error: str | None = Field(None, description="Error message if any")


class AgentHealthResponse(BaseModel):
    """Response model for agent health check"""
    status: str = Field(..., description="Health status")
    components: dict[str, str] = Field(default_factory=dict, description="Component health")
    tools_count: int = Field(..., description="Number of registered tools")


class AgentInfoResponse(BaseModel):
    """Response model for agent info"""
    status: str = Field(..., description="Agent status")
    available_tools: list[str] = Field(..., description="List of available tools")
    supported_intents: list[str] = Field(..., description="List of supported intents")
    llm_model: str = Field(..., description="LLM model name")
    version: str = Field(..., description="Agent version")


@router.post("/query", response_model=AgentQueryResponse)
async def process_query(request: AgentQueryRequest, _: PayingUser = None):
    """
    Process a user query through the agent.

    Args:
        request: Agent query request

    Returns:
        Agent response with intent and metadata

    Raises:
        HTTPException: If query processing fails
    """
    try:
        logger.info(f"Received agent query: {request.query[:100]}...")

        agent_service = get_agent_service()
        result = await agent_service.process_query(
            request.query,
            workspace=request.workspace,
            thread_id=request.thread_id,
        )

        return AgentQueryResponse(
            response=result["response"],
            intent=result["intent"],
            metadata=result.get("metadata", {}),
            sources=result.get("sources", []),
            live_sources=result.get("live_sources", []),
            verification=result.get("verification"),
            agent_trail=result.get("agent_trail"),
            error=result.get("error")
        )

    except Exception as e:
        logger.error(f"Error processing agent query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {e!s}"
        ) from e


@router.options("/query/stream")
async def options_query_stream():
    """
    Handle OPTIONS preflight request for streaming endpoint.

    Returns:
        Empty response with CORS headers (handled by CORSMiddleware)
    """
    return {}


@router.post("/query/stream")
async def process_query_stream(request: AgentQueryRequest, _: PayingUser = None):
    """
    Process a user query with streaming response.

    Args:
        request: Agent query request

    Returns:
        Streaming response with agent output

    Raises:
        HTTPException: If query processing fails
    """
    try:
        logger.info(f"Received streaming agent query: {request.query[:100]}...")

        agent_service = get_agent_service()

        async def generate():
            try:
                async for chunk in agent_service.process_query_stream(
            request.query,
            workspace=request.workspace,
            thread_id=request.thread_id,
        ):
                    yield chunk
            except Exception as e:
                logger.error(f"Error in streaming: {e}")
                yield f"\n\nError: {e!s}"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    except Exception as e:
        logger.error(f"Error setting up streaming: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup streaming: {e!s}"
        ) from e


@router.get("/health", response_model=AgentHealthResponse)
async def health_check():
    """
    Check agent health status.

    Returns:
        Health status of agent and components
    """
    try:
        agent_service = get_agent_service()
        health = agent_service.health_check()

        return AgentHealthResponse(
            status=health["status"],
            components=health.get("components", {}),
            tools_count=health.get("tools_count", 0)
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return AgentHealthResponse(
            status="unhealthy",
            components={"error": str(e)},
            tools_count=0
        )


@router.get("/info", response_model=AgentInfoResponse)
async def get_agent_info():
    """
    Get agent information.

    Returns:
        Agent information including tools and capabilities
    """
    try:
        agent_service = get_agent_service()
        info = agent_service.get_agent_info()

        return AgentInfoResponse(
            status=info["status"],
            available_tools=info["available_tools"],
            supported_intents=info["supported_intents"],
            llm_model=info["llm_model"],
            version=info["version"]
        )

    except Exception as e:
        logger.error(f"Failed to get agent info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent info: {e!s}"
        ) from e
