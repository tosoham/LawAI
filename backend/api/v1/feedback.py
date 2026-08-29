"""
Letting a person say an answer was wrong.

The three signals `services/feedback.py` captures on its own — abstained,
claims removed, nothing retrieved — all say *the system noticed something*.
They cannot catch the failure that matters most: **a confident answer that is
simply wrong.** Nothing internal flags that, because every claim in it passed
verification; the only thing that knows is the person reading it.

So this endpoint exists for exactly one thing that automation cannot supply,
and it is deliberately small. It takes a query, an optional note, and stores
them beside the self-labelled events for the same human review.

Two things it does *not* do:

* **no rating scale.** A number tells you a reader was unhappy and nothing
  about why, and "3 out of 5" cannot become a golden-set row. The note can.
* **no user identity, and no session or answer id.** This is a queue of things
  to look at, not a record of who asked what. A query is already the most
  sensitive thing here.
"""
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.feedback import FeedbackEvent, _append, feedback_enabled, summarise

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["Feedback"])


class FeedbackRequest(BaseModel):
    """A reader saying something was wrong."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The question that produced the answer being reported.",
    )
    note: str = Field(
        default="",
        max_length=2000,
        description=(
            "What was wrong, in the reader's own words. This is the part that "
            "can become a test; a rating could not."
        ),
    )


class FeedbackResponse(BaseModel):
    recorded: bool
    message: str


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def report(request: FeedbackRequest) -> FeedbackResponse:
    """
    Record a reported answer for review.

    202 rather than 201: nothing has been decided by accepting this. It is
    queued for a person to read, and saying "created" would overstate what
    happened to it.
    """
    if not feedback_enabled():
        # Not an error. A deployment that has not turned capture on has made a
        # deliberate choice about storing user text, and a client should be
        # told plainly rather than shown a failure.
        return FeedbackResponse(
            recorded=False,
            message="Feedback capture is not enabled on this deployment.",
        )

    try:
        _append(
            FeedbackEvent(
                query=request.query,
                signals=["user_reported"],
                note=request.note,
            )
        )
    except Exception as error:
        logger.error(f"could not record feedback: {error}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not record that. Nothing else was affected.",
        ) from error

    return FeedbackResponse(
        recorded=True, message="Thank you — this will be reviewed."
    )


@router.get("/summary")
async def feedback_summary() -> dict:
    """
    Counts by signal, and the most common rejection reasons.

    No queries and no notes: those are what a reviewer reads locally with
    `scripts/review_feedback.py`, and serving them over HTTP would turn a
    diagnostic store into a way to read other people's questions.
    """
    if not feedback_enabled():
        return {"enabled": False, "events": 0}
    return {"enabled": True, **summarise()}
