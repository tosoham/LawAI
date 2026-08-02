"""
RAG Search API endpoint for LawAI
Provides semantic search across legal collections with LLM-generated answers
"""
import logging
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any

from models.requests import RAGSearchRequest
from models.responses import ErrorResponse
from services.rag_service import get_rag_service
from services.vector_service import VectorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# Collection name mapping
COLLECTION_MAP = {
    "bns": VectorService.BNS_COLLECTION,
    "bnss": VectorService.BNSS_COLLECTION,
    "bsa": VectorService.BSA_COLLECTION,
    "judgements": VectorService.SC_JUDGEMENTS_COLLECTION
}


@router.post(
    "/",
    response_model=Dict[str, Any],
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="RAG Search",
    description="Perform semantic search across legal collections with AI-generated contextual answers"
)
def rag_search(request: RAGSearchRequest) -> Dict[str, Any]:
    """
    Perform RAG (Retrieval-Augmented Generation) search
    
    This endpoint:
    1. Searches the specified legal collection using semantic similarity
    2. Retrieves relevant legal provisions/cases
    3. Generates a contextual answer using the configured AIML API model
    4. Returns the answer with source citations
    
    Args:
        request: RAGSearchRequest with query, collection, and top_k
        
    Returns:
        Dict with 'answer', 'sources', 'query', 'collection', 'num_sources'
        
    Raises:
        HTTPException: If search fails or invalid collection specified
    """
    try:
        logger.info(f"RAG search request: query='{request.query}', collection={request.collection}, top_k={request.top_k}")
        
        # Get RAG service
        rag_service = get_rag_service()
        
        # Determine collection(s) to search
        if request.collection:
            # Search specific collection
            if request.collection not in COLLECTION_MAP:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid collection: {request.collection}. Must be one of: {list(COLLECTION_MAP.keys())}"
                )
            
            collection_name = COLLECTION_MAP[request.collection]
            result = rag_service.search_and_generate(
                query=request.query,
                collection=collection_name,
                top_k=request.top_k
            )
        else:
            # Search all collections
            all_collections = list(COLLECTION_MAP.values())
            result = rag_service.multi_collection_search(
                query=request.query,
                collections=all_collections,
                top_k_per_collection=max(1, request.top_k // len(all_collections))
            )
        
        logger.info(f"RAG search completed successfully: {result.get('num_sources', 0)} sources")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG search failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get(
    "/collections",
    response_model=Dict[str, Any],
    summary="List Collections",
    description="Get list of available legal collections with statistics"
)
def list_collections() -> Dict[str, Any]:
    """
    List available collections and their statistics
    
    Returns:
        Dict with collection names and document counts
    """
    try:
        from services.vector_service import get_vector_service
        
        vector_service = get_vector_service()
        collections = {}
        
        for key, collection_name in COLLECTION_MAP.items():
            try:
                stats = vector_service.get_collection_stats(collection_name)
                collections[key] = {
                    "name": collection_name,
                    "count": stats.get("count", 0),
                    "description": _get_collection_description(key)
                }
            except Exception as e:
                logger.warning(f"Could not get stats for {collection_name}: {e}")
                collections[key] = {
                    "name": collection_name,
                    "count": 0,
                    "description": _get_collection_description(key)
                }
        
        return {
            "collections": collections,
            "total_collections": len(collections)
        }
        
    except Exception as e:
        logger.error(f"Failed to list collections: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {str(e)}"
        )


def _get_collection_description(collection_key: str) -> str:
    """Get human-readable description for collection"""
    descriptions = {
        "bns": "Bharatiya Nyaya Sanhita (Indian Penal Code replacement)",
        "bnss": "Bharatiya Nagarik Suraksha Sanhita (Criminal Procedure Code replacement)",
        "bsa": "Bharatiya Sakshya Adhiniyam (Indian Evidence Act replacement)",
        "judgements": "Supreme Court of India Judgements"
    }
    return descriptions.get(collection_key, "Legal collection")


# Made with Bob