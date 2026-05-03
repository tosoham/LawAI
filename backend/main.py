"""
LawAI Backend - FastAPI Application Entry Point

This is the main entry point for the LawAI backend API.
It initializes the FastAPI application with CORS, middleware, and routes.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Any
import os
from dotenv import load_dotenv

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

# Configure CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from api.v1.chat import router as chat_router
from api.v1.search import router as search_router
from api.v1.documents import router as documents_router
from api.v1.agent import router as agent_router

app.include_router(chat_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")

# Initialize tools on startup
from services.llm_service import llm_service
from services.rag_service import RAGService
from tools.registry import initialize_tools

@app.on_event("startup")
async def startup_event():
    """Initialize tools on application startup"""
    logger.info("Initializing MCP tools...")
    rag_service = RAGService()
    initialize_tools(llm_service, rag_service)
    logger.info("MCP tools initialized successfully")


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint - API information"""
    return {
        "name": "LawAI API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }


@app.get("/api/v1/health")
async def health_check() -> Dict[str, str]:
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
async def api_info() -> Dict[str, Any]:
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
        "llm": "IBM watsonx.ai - Granite-13b-chat-v2",
        "agent_framework": "LangGraph",
        "vector_db": "ChromaDB"
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "path": str(request.url)
        }
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

# Made with Bob
