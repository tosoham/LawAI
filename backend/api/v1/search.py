"""
RAG Search API endpoint for LawAI
Provides semantic search across legal collections with LLM-generated answers
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from models.requests import RAGSearchRequest
from models.responses import ErrorResponse, GroundedAnswerResponse
from services.grounded_answer import get_grounded_answer_service
from services.rag_service import get_rag_service
from services.vector_service import VectorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# Short aliases used by the API and shown in /search/collections.
COLLECTION_MAP = {
    "bns": VectorService.BNS_COLLECTION,
    "bnss": VectorService.BNSS_COLLECTION,
    "bsa": VectorService.BSA_COLLECTION,
    "judgements": VectorService.SC_JUDGEMENTS_COLLECTION
}

# The frontend and the vector store itself refer to collections by their full
# name ("bns_sections"), so accept either form rather than making callers
# translate. Requests using the full name previously failed validation.
COLLECTION_ALIASES = {
    **COLLECTION_MAP,
    **{full: full for full in COLLECTION_MAP.values()},
}


def resolve_collection(name: str) -> str:
    """Map a short alias or a full collection name to the stored collection."""
    return COLLECTION_ALIASES[name]


@router.post(
    "/rag",
    response_model=dict[str, Any],
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="RAG Search",
    description="Perform semantic search across legal collections with AI-generated contextual answers"
)
# "/search/rag" is canonical (it is what the frontend calls); "/search" is kept
# so older clients do not break.
@router.post("", response_model=dict[str, Any], include_in_schema=False)
def rag_search(request: RAGSearchRequest) -> dict[str, Any]:
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
            if request.collection not in COLLECTION_ALIASES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid collection: {request.collection}. Must be one of: {sorted(COLLECTION_ALIASES)}"
                )

            collection_name = resolve_collection(request.collection)
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
        logger.error(f"RAG search failed: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e!s}"
        ) from e


@router.get(
    "/collections",
    response_model=dict[str, Any],
    summary="List Collections",
    description="Get list of available legal collections with statistics"
)
def list_collections() -> dict[str, Any]:
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
        logger.error(f"Failed to list collections: {e!s}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {e!s}"
        ) from e


def _get_collection_description(collection_key: str) -> str:
    """Get human-readable description for collection"""
    descriptions = {
        "bns": "Bharatiya Nyaya Sanhita (Indian Penal Code replacement)",
        "bnss": "Bharatiya Nagarik Suraksha Sanhita (Criminal Procedure Code replacement)",
        "bsa": "Bharatiya Sakshya Adhiniyam (Indian Evidence Act replacement)",
        "judgements": "Supreme Court of India Judgements"
    }
    return descriptions.get(collection_key, "Legal collection")


@router.post(
    "/grounded",
    response_model=GroundedAnswerResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Grounded search",
    description=(
        "Answer a question as typed claims, each checked against the corpus, and "
        "abstain when none of them stand. Unlike /search/rag this returns the "
        "epistemic class of every claim, the verifier's findings, grounding "
        "metrics and an auditable trace."
    ),
)
def grounded_search(request: RAGSearchRequest) -> GroundedAnswerResponse:
    """
    Answer a question with every claim checked, or say it cannot be answered.

    A single collection is searched. Unlike ``/search/rag`` this endpoint does
    not fan out across all of them when ``collection`` is omitted: verification
    resolves a claim against the act it cites, and merging three collections
    into one context makes the model likelier to cite across them -- BNS 103
    for a procedural point, BNSS 103 for an offence. The default is the BNS.
    """
    collection = request.collection or "bns"
    if collection not in COLLECTION_ALIASES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid collection: {collection}. Must be one of: {sorted(COLLECTION_ALIASES)}",
        )

    try:
        result = get_grounded_answer_service().answer(
            query=request.query,
            collection=resolve_collection(collection),
            top_k=request.top_k,
        )
    except Exception as e:
        logger.error(f"Grounded search failed: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e!s}",
        ) from e

    logger.info(
        f"Grounded search: abstained={result.abstained} "
        f"claims={len(result.structured.claims)} removed={result.metrics.unsupported}"
    )
    return GroundedAnswerResponse(
        query=result.query,
        answer=result.answer,
        abstained=result.abstained,
        claims=[
            {
                "text": claim.text,
                "epistemic_class": claim.epistemic_class.value,
                "sources": [{"ref": s.ref, "kind": s.kind.value} for s in claim.sources],
                "verbatim_span": claim.verbatim_span,
                "positions": [
                    {"summary": p.summary, "authority": p.authority} for p in claim.positions
                ],
            }
            for claim in result.structured.claims
        ],
        verdicts=[
            {
                "index": v.index,
                "verified": v.verified,
                "original_class": v.original_class.value,
                "reason": v.reason,
            }
            for v in result.verdicts
        ],
        metrics=result.metrics.to_dict(),
        sources=result.sources,
        graph_context=result.graph_context,
        trace=result.trace,
    )
