"""
LawAI Backend - FastAPI Application Entry Point

This is the main entry point for the LawAI backend API.
It initializes the FastAPI application with CORS, middleware, and routes.
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LawAI API",
    description="Multi-agent Indian legal AI system for lawyers, courts, and public",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS - Must be added BEFORE including routers
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
logger.info(f"Configuring CORS with origins: {origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with body for debugging"""
    logger.info(f"Request: {request.method} {request.url.path}")

    # Log request body for POST requests
    if request.method == "POST":
        try:
            body = await request.body()
            if body:
                try:
                    body_json = json.loads(body)
                    logger.info(f"Request body: {json.dumps(body_json, indent=2)}")
                except json.JSONDecodeError:
                    logger.info(f"Request body (raw): {body.decode()[:500]}")
        except Exception as e:
            logger.warning(f"Could not read request body: {e}")

    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Add validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Report *which* field was wrong, never what was in it.

    This used to return `exc.errors()` and `str(exc.body)` verbatim, which put
    the whole request back in the response and in the logs. On this API the
    request body is a legal question or a set of case details -- a draft
    request rejected for a missing field echoed "Jane Doe, PAN ABCDE1234F"
    twice, once in `input` and once in `body`, into a response and a log line
    that will outlive the request by however long logs are kept.

    A caller needs the field and the reason to fix their call. They already
    know what they sent.
    """
    fields = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "problem": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    logger.warning(
        f"Validation error on {request.method} {request.url.path}: "
        f"{[f['field'] for f in fields]}"
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "message": "Request validation failed",
            "details": fields,
        },
    )

# Import and include routers
from api.v1.agent import router as agent_router
from api.v1.chat import router as chat_router
from api.v1.documents import router as documents_router
from api.v1.feedback import router as feedback_router
from api.v1.offences import router as offences_router
from api.v1.research import router as research_router
from api.v1.search import router as search_router

app.include_router(chat_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(offences_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")

# Initialize tools on startup
from services.llm_service import llm_service
from services.rag_service import RAGService
from tools.registry import initialize_tools


@app.on_event("startup")
async def startup_event():
    """Initialize tools on application startup"""
    try:
        logger.info("Starting LawAI backend...")
        logger.info("Initializing agent tools...")
        rag_service = RAGService()
        initialize_tools(llm_service, rag_service)
        logger.info("Agent tools initialized successfully")
        logger.info("LawAI backend ready!")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        # Don't fail startup, allow health checks to work
        logger.warning("Continuing with limited functionality")


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint - API information"""
    return {
        "name": "LawAI API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check_root() -> dict[str, str]:
    """
    Health check endpoint (root level)

    Returns:
        Dict with status and version information
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "LawAI Backend"
    }


@app.get("/api/v1/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint

    Returns:
        Dict with status and version information
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "LawAI Backend"
    }


@app.get("/api/v1/info")
async def api_info() -> dict[str, Any]:
    """
    API information endpoint

    Returns:
        Dict with API capabilities and configuration
    """
    return {
        "name": "LawAI API",
        "version": "1.0.0",
        "description": "Multi-agent Indian legal AI system",
        "features": [
            "RAG Search - Query Indian legal corpus (BNS, BNSS, BSA, SC judgements)",
            "Draft Document - Generate legal drafts (bail applications, petitions)",
            "Analyze Document - Extract and analyze uploaded legal documents",
            "Chat - General legal Q&A with context"
        ],
        "legal_framework": {
            "BNS": "Bharatiya Nyaya Sanhita, 2023",
            "BNSS": "Bharatiya Nagarik Suraksha Sanhita, 2023",
            "BSA": "Bharatiya Sakshya Adhiniyam, 2023"
        },
        "llm": llm_service.get_model_info(),
        "agent_framework": "LangGraph",
        "vector_db": "ChromaDB"
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """
    Handle 404s, keeping any message the route took the trouble to write.

    This used to replace every 404 body with "The requested resource was not
    found", which is right for a wrong URL and wrong for a route that raised
    one deliberately: "BNS has no section 999" and "Unknown act 'IPC'. Must be
    one of: BNS, BNSS, BSA" were both being thrown away, and those are the
    answer rather than an error.
    """
    # Starlette gives an unmatched route the stock detail "Not Found", which is
    # not a message a route wrote and should not displace the generic one.
    detail = getattr(exc, "detail", None)
    written = detail if detail and detail != "Not Found" else None
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": written or "The requested resource was not found",
            "detail": written,
            "path": str(request.url),
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    reload = os.getenv("RELOAD", "True").lower() == "true"

    logger.info(f"Starting LawAI API on {host}:{port}")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
