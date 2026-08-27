"""
What every specialist shares: a retrieval budget, and a rule about what it may return.

**A specialist may query the corpus more than once.** Retrieving, reading what
came back, and deciding another lookup is needed is the thing that makes an
agent worth having over a single fixed call -- a question about anticipatory
bail conditions genuinely needs the section *and* the case that read it down,
and which case that is is not knowable before the section arrives.

**And it is bounded, deliberately and visibly.** An agent that decides for
itself when it is finished decides badly under uncertainty, and the failure is
expensive rather than wrong: an unbounded retrieve loop is how one question
costs forty model calls. So ``MAX_RETRIEVALS`` caps the loop, the count goes
into the trace beside the model-call count, and hitting the cap ends the loop
rather than the request -- a specialist that ran out of budget returns what it
has, exactly as one that failed returns what it had.

**Whatever it returns is Evidence, never a claim.** This is the rule the whole
architecture rests on and the reason the fan-out is safe: six agents emitting
their own conclusions would put generation *after* the point
``services/claim_verifier.py`` runs, so part of the answer would be checked and
part would not, with nothing in the output to say which. A specialist that has
read ten chunks and formed a view still hands over the ten chunks.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from agents.contracts import AgentError, Evidence, PlanStep, SpecialistKind

logger = logging.getLogger(__name__)

#: How many times one specialist may query the corpus for one plan step.
#:
#: Three, because the shape it exists for is "retrieve, notice a gap, fill it"
#: and that is two; the third is slack for a follow-up that opens one more.
#: Beyond that a specialist is searching rather than researching, and the
#: planner should have asked a different question.
MAX_RETRIEVALS = int(os.getenv("SPECIALIST_MAX_RETRIEVALS", "3"))


@dataclass
class SpecialistResult:
    """What one specialist produced, and what it cost."""

    evidence: list[Evidence] = field(default_factory=list)
    errors: list[AgentError] = field(default_factory=list)
    retrievals: int = 0
    """Corpus queries made. Recorded because the fan-out's whole risk is cost,
    and a number nobody can see is a number nobody will notice growing."""

    model_calls: int = 0
    """Model calls made. Zero for the deterministic specialists, and the test
    that asserts it is what keeps them free."""

    def merged_into(self, other: SpecialistResult) -> SpecialistResult:
        return SpecialistResult(
            evidence=self.evidence + other.evidence,
            errors=self.errors + other.errors,
            retrievals=self.retrievals + other.retrievals,
            model_calls=self.model_calls + other.model_calls,
        )


class RetrievalBudget:
    """
    A counter a specialist checks before every corpus query.

    Passed in rather than read from a global so a test can set it to one and a
    contested advocate can be given a smaller budget than a planner-dispatched
    specialist, without either of them knowing about the other.
    """

    def __init__(self, limit: int = MAX_RETRIEVALS) -> None:
        self.limit = limit
        self.used = 0

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def spend(self) -> bool:
        """Take one query from the budget, or refuse. ``False`` means stop."""
        if self.exhausted:
            return False
        self.used += 1
        return True


#: Registered specialist runners, filled by each module at import.
_RUNNERS: dict[SpecialistKind, object] = {}


def register(kind: SpecialistKind):
    """Attach a runner to a specialist kind."""

    def decorate(function):
        _RUNNERS[kind] = function
        return function

    return decorate


def run_specialist(
    step: PlanStep, query: str, budget: RetrievalBudget | None = None
) -> SpecialistResult:
    """
    Run one plan step, and never raise.

    A specialist failing is recorded and the query continues on what the others
    found -- the same rule ``services/judiciary_service.py`` follows, and the
    reason live research degraded to the local corpus for the fortnight the
    source sat behind a challenge instead of failing every request. Six agents
    means six chances to fail, so this matters more here than it did there.
    """
    runner = _RUNNERS.get(step.specialist)
    if runner is None:
        return SpecialistResult(
            errors=[
                AgentError(
                    specialist=step.specialist,
                    stage="dispatch",
                    message=f"no runner registered for {step.specialist.value}",
                )
            ]
        )

    try:
        return runner(step, query, budget or RetrievalBudget())
    except Exception as error:  # a specialist must not kill the query
        logger.warning(f"{step.specialist.value} specialist failed: {error}")
        return SpecialistResult(
            errors=[
                AgentError(
                    specialist=step.specialist,
                    stage="run",
                    message=str(error),
                )
            ]
        )
