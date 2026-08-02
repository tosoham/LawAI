"""
Live Research API Endpoints

Direct access to authentic judiciary sources, for callers that want current
case law without going through the agent's intent classification.

The local corpus remains the primary source for statute and settled law; these
endpoints cover what a snapshot cannot: judgements handed down after ingestion.
Everything returned here is retrieved rather than curated, and is labelled so.
"""
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from models.requests import LiveCaseLawRequest
from services.judiciary_service import COURTS, get_judiciary_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


@router.post(
    "/case-law",
    response_model=dict[str, Any],
    summary="Search live case law",
    description=(
        "Search authentic judiciary sources for current judgements, including "
        "those handed down after the local corpus was built."
    ),
)
async def search_live_case_law(request: LiveCaseLawRequest) -> dict[str, Any]:
    """Search current case law from authentic public judiciary records."""
    service = get_judiciary_service()

    result = await asyncio.to_thread(
        service.search_case_law,
        query=request.query,
        court=request.court,
        from_date=request.from_date,
        to_date=request.to_date,
        limit=request.limit,
    )

    if not result.get("success"):
        error = result.get("error", "Live search failed")
        # A disabled or unreachable source is a service condition, not a bad request.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error,
        )

    result["disclaimer"] = (
        "Retrieved from public judiciary records and not part of the verified "
        "corpus. Confirm against the official record before relying on it."
    )
    return result


@router.get(
    "/judgment/{doc_id}",
    response_model=dict[str, Any],
    summary="Fetch a judgement",
    description="Retrieve the text of one judgement by its source document id.",
)
async def fetch_judgment(
    doc_id: str,
    max_chars: int = Query(default=8000, ge=500, le=60000),
) -> dict[str, Any]:
    """Retrieve a single judgement located by a live search."""
    service = get_judiciary_service()

    result = await asyncio.to_thread(service.fetch_judgment, doc_id=doc_id, max_chars=max_chars)

    if not result.get("success"):
        error = result.get("error", "Could not fetch judgement")
        if "Invalid document id" in error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
        if "robots" in error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error)

    result["disclaimer"] = (
        "Retrieved from public judiciary records and not part of the verified "
        "corpus. Confirm against the official record before relying on it."
    )
    return result


@router.get("/health", summary="Live research availability")
async def health() -> dict[str, Any]:
    """Report whether live lookups are enabled, without calling the source."""
    service = get_judiciary_service()
    return {
        "status": "healthy",
        "service": "research",
        "courts": sorted(COURTS),
        **service.health_check(),
    }
