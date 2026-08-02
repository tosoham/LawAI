"""
Chat endpoint for LawAI
Handles conversational interactions with the configured AIML API model
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from models.requests import ChatRequest
from models.responses import ChatResponse, ErrorResponse
from services.llm_service import llm_service
from services.streaming import create_streaming_response, stream_llm_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Chat with LawAI",
    description="Send a message and get a response from the configured legal AI model"
)
async def chat(request: ChatRequest):
    """
    Chat endpoint with streaming support

    Args:
        request: ChatRequest with message and optional context

    Returns:
        StreamingResponse if stream=True, else ChatResponse

    Raises:
        HTTPException: If generation fails
    """
    try:
        logger.info(f"Chat request received: {request.message[:100]}...")

        # Build prompt with context if provided
        prompt = request.message
        if request.context:
            prompt = f"Context: {request.context}\n\nQuestion: {request.message}"

        # Legal domain instruction, sent as a proper system message
        system_prompt = (
            "You are a legal AI assistant specializing in Indian law. "
            "Provide accurate, helpful responses based on BNS, BNSS, BSA, and Indian case law. "
            "Always cite relevant sections and cases when applicable."
        )

        # Prepare generation parameters
        gen_kwargs = {}
        if request.max_tokens:
            gen_kwargs["max_tokens"] = request.max_tokens
        if request.temperature:
            gen_kwargs["temperature"] = request.temperature

        # Handle streaming vs non-streaming
        if request.stream:
            logger.info("Streaming response requested")

            # Create async generator for streaming
            async def generate():
                try:
                    async for token in llm_service.generate_stream(
                        prompt, system=system_prompt, **gen_kwargs
                    ):
                        yield token
                except Exception as e:
                    logger.error(f"Streaming generation error: {e!s}")
                    raise

            # Return streaming response
            return create_streaming_response(
                stream_llm_response(generate(), include_metadata=True)
            )

        else:
            logger.info("Non-streaming response requested")

            # Generate complete response (offloaded so the event loop stays free)
            response_text = await asyncio.to_thread(
                llm_service.generate, prompt, system=system_prompt, **gen_kwargs
            )

            # Return structured response
            return ChatResponse(
                response=response_text,
                sources=None,  # Will be populated when RAG is integrated
                model=llm_service.get_model_info()["model_id"]
            )

    except Exception as e:
        logger.error(f"Chat endpoint error: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {e!s}"
        ) from e


@router.get(
    "/health",
    summary="Check chat service health",
    description="Verify that the LLM service is operational"
)
async def health():
    """
    Health check for chat service

    Returns:
        Service status and model information
    """
    try:
        model_info = llm_service.get_model_info()
        return {
            "status": "healthy",
            "service": "chat",
            "provider": model_info["provider"],
            "model": model_info["model_id"],
            "max_tokens": model_info["max_tokens"],
            "temperature": model_info["temperature"],
            "configured": llm_service.health_check()["configured"]
        }
    except Exception as e:
        logger.error(f"Health check failed: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {e!s}"
        ) from e
