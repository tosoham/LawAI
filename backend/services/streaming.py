"""
Streaming utility for FastAPI StreamingResponse
Handles token-by-token output from LLM
"""
import logging
import json
from typing import AsyncIterator, Optional
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


async def stream_llm_response(
    llm_generator: AsyncIterator[str],
    include_metadata: bool = False
) -> AsyncIterator[str]:
    """
    Format LLM streaming output for FastAPI StreamingResponse
    
    Args:
        llm_generator: Async generator yielding tokens from LLM
        include_metadata: Whether to include metadata in stream
        
    Yields:
        Formatted SSE (Server-Sent Events) strings
    """
    try:
        # Send start event
        if include_metadata:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        # Stream tokens
        async for token in llm_generator:
            if token:
                # Format as SSE
                data = {
                    "type": "token",
                    "content": token
                }
                yield f"data: {json.dumps(data)}\n\n"
        
        # Send end event
        if include_metadata:
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
            
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        # Send error event
        error_data = {
            "type": "error",
            "message": str(e)
        }
        yield f"data: {json.dumps(error_data)}\n\n"


async def stream_text_response(
    text: str,
    chunk_size: int = 10
) -> AsyncIterator[str]:
    """
    Stream a complete text response in chunks (for testing)
    
    Args:
        text: Complete text to stream
        chunk_size: Number of characters per chunk
        
    Yields:
        Text chunks
    """
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield chunk


def create_streaming_response(
    generator: AsyncIterator[str],
    media_type: str = "text/event-stream"
) -> StreamingResponse:
    """
    Create FastAPI StreamingResponse from async generator
    
    Args:
        generator: Async generator yielding content
        media_type: Response media type (default: text/event-stream)
        
    Returns:
        FastAPI StreamingResponse configured for streaming
    """
    return StreamingResponse(
        generator,
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


async def handle_stream_error(
    error: Exception,
    context: Optional[str] = None
) -> AsyncIterator[str]:
    """
    Handle streaming errors gracefully
    
    Args:
        error: Exception that occurred
        context: Optional context about where error occurred
        
    Yields:
        Error message in SSE format
    """
    logger.error(f"Stream error{f' in {context}' if context else ''}: {str(error)}")
    
    error_data = {
        "type": "error",
        "message": "An error occurred during streaming",
        "details": str(error) if logger.level == logging.DEBUG else None
    }
    
    yield f"data: {json.dumps(error_data)}\n\n"

# Made with Bob
