"""
Offence classification and procedural timeline for one section.

Answered entirely from committed data -- the First Schedule table, the legal
graph and the fixed steps in ``services.procedural_timeline``. No model is
called, so the response is the same every time and every value can be traced to
a provision. That is the point: whether an offence is bailable, and how long a
person can be held before something has to happen, are lookups, and treating
them as generation would put the most consequential answers in the system
behind the least reliable mechanism it has.
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from models.responses import ErrorResponse
from services.legal_graph import ACT_FILES, get_legal_graph
from services.procedural_timeline import for_section

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/offences", tags=["offences"])

ACTS = sorted(ACT_FILES)


@router.get(
    "/{act}/{section}",
    response_model=dict[str, Any],
    responses={404: {"model": ErrorResponse}},
    summary="Offence classification and procedural timeline",
    description=(
        "Everything the deterministic layer knows about a section: its "
        "First Schedule classification, the doctrines and judgements the graph "
        "connects to it, and the custody timeline that follows from its "
        "punishment. No model is involved."
    ),
)
def get_offence(act: str, section: str) -> dict[str, Any]:
    """
    Look up one section.

    A section with no First Schedule row -- all of the BNSS, most of the BSA --
    returns its identity with ``classification`` empty and ``timeline`` null.
    That is a real answer, not a miss: those provisions have no classification
    to state, and an empty card is more honest than a fabricated one.
    """
    if act.upper() not in ACT_FILES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown act {act!r}. Must be one of: {ACTS}",
        )

    payload = for_section(act, section)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{act.upper()} has no section {section}",
        )
    return payload


@router.get(
    "",
    response_model=dict[str, Any],
    summary="Offence table summary",
    description="What the classification table covers, and what it leaves unresolved.",
)
def summary() -> dict[str, Any]:
    """
    Report the table's coverage, including what it cannot resolve.

    The unresolved count is published rather than buried: around forty rows of
    the First Schedule defer to another offence ("According as offence abetted
    is cognizable or non-cognizable"), and a client showing a classification UI
    needs to know that "not stated" is a real outcome.
    """
    graph = get_legal_graph()
    rows = [row for rows in graph.classification.values() for row in rows]
    return {
        "acts": ACTS,
        "classified_sections": len(graph.classification),
        "rows": len(rows),
        "unresolved_cognizable": sum(1 for r in rows if r["cognizable"] is None),
        "unresolved_bailable": sum(1 for r in rows if r["bailable"] is None),
        "source": "First Schedule, Bharatiya Nagarik Suraksha Sanhita, 2023",
    }
