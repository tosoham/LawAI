"""
What the agents pass between themselves.

One rule shapes every type here: **specialists gather evidence, only the
synthesiser emits claims.**

The alternative -- each specialist writing its own prose or its own typed
claims -- was rejected before anything was built. It would leave six unverified
answers to merge, and the merge is exactly where a fabrication would enter,
with nothing in the output to show which agent introduced it. Worse, it would
put generation *after* the point where `services/claim_verifier.py` runs, so
the one guarantee this system actually offers -- that every claim in a shipped
answer survived a deterministic check against committed data -- would apply to
some of the answer and not the rest.

So an ``Evidence`` carries retrieved and structured material with its
provenance, never a conclusion. The synthesiser turns the union of evidence
into typed claims and the existing verifier checks each one exactly as it does
for a single-pass answer. The architecture changes what reaches the prompt; it
does not change what is checked.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Complexity(str, Enum):
    """What triage decided a query needs."""

    SIMPLE = "simple"
    """Answerable by the existing single-pass grounded path. The default, and
    deliberately the common case: fanning out costs roughly eight model calls
    against one, and most legal questions are one question."""

    COMPLEX = "complex"
    """Several strands that are worth gathering in parallel before synthesis."""

    CONTESTED = "contested"
    """A question the authorities answer differently. The one shape where more
    than one agent is doing something a single agent cannot: developing a
    reading it is not simultaneously arguing against."""


class SpecialistKind(str, Enum):
    """Which specialist a plan step is addressed to."""

    STATUTE = "statute"
    CASE_LAW = "case_law"
    OFFENCE = "offence"
    DOCTRINE = "doctrine"
    DRAFTING = "drafting"
    ANALYSIS = "analysis"

    @property
    def deterministic(self) -> bool:
        """
        Whether this specialist answers without a model call.

        ``offence`` reads the First Schedule and ``doctrine`` reads the curated
        graph; both are exact lookups over committed data. They are free, they
        cannot hallucinate, and a plan that includes them costs nothing extra --
        which is why triage should prefer them over asking a model the same
        question in prose.
        """
        return self in (SpecialistKind.OFFENCE, SpecialistKind.DOCTRINE)


class PlanStep(BaseModel):
    """One specialist, and what it is being asked for."""

    specialist: SpecialistKind
    question: str = Field(
        description="What this specialist should gather, in its own terms."
    )
    reason: str = Field(
        default="",
        description="Why the planner thinks this bears on the query. Recorded "
        "in the trace so a plan can be argued with after the fact.",
    )


class Plan(BaseModel):
    """The planner's output: which specialists to run, and why."""

    complexity: Complexity = Complexity.COMPLEX
    steps: list[PlanStep] = Field(default_factory=list)
    contested_question: str = ""
    """Set when the plan routes to the contested path: the proposition the two
    positions are arguing about, phrased so both sides can address it."""

    @property
    def specialists(self) -> list[SpecialistKind]:
        """Distinct specialists, in plan order. A planner that names the same
        one twice gets one dispatch, not two."""
        seen: list[SpecialistKind] = []
        for step in self.steps:
            if step.specialist not in seen:
                seen.append(step.specialist)
        return seen


class Evidence(BaseModel):
    """
    Material one specialist gathered. **Not a conclusion.**

    ``payload`` holds whatever that specialist's underlying service returns --
    retrieved chunks, a First Schedule row, a doctrine node -- unchanged and
    unsummarised. Summarising here would be the specialist forming a view, and
    a view that no verifier ever sees is precisely what this design exists to
    prevent.
    """

    specialist: SpecialistKind
    kind: str = Field(
        description="What sort of material this is: 'sections', 'judgements', "
        "'classification', 'doctrine'. The synthesis prompt renders each kind "
        "differently, and that separation is load-bearing -- a pointer to a "
        "case must never be rendered as a holding."
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: str = Field(
        default="",
        description="Where it came from: a collection name, 'First Schedule', "
        "'curated doctrines', or a live source URL. Live material is never "
        "blended with corpus material downstream, so this has to survive.",
    )

    def is_empty(self) -> bool:
        return not self.payload


class AgentError(BaseModel):
    """
    One specialist failing, recorded rather than raised.

    Partial failure is a first-class outcome. A query that consulted five
    specialists and lost one is still answerable from four, and the answer says
    so; failing the whole request would be strictly worse for the reader. This
    is the same rule `services/judiciary_service.py` follows, and it is why
    live research degraded to the local corpus for the two weeks the source was
    behind a challenge instead of 500-ing every request.
    """

    specialist: SpecialistKind | None = None
    stage: str = Field(default="", description="triage, plan, dispatch, synthesis.")
    message: str = ""


class Position(BaseModel):
    """One side of a contested question, as its advocate developed it."""

    label: str = Field(description="A short name for the reading, not a verdict.")
    summary: str
    authority: list[str] = Field(
        default_factory=list,
        description="Judgement ids and section keys supporting this reading. A "
        "position with none is reported as unsupported rather than dropped -- "
        "that a side cannot be supported from this corpus is itself a finding.",
    )
    rebuttal: str = Field(
        default="",
        description="This advocate's answer to the other, written after seeing "
        "it once. Empty until the rebuttal round runs.",
    )

    @property
    def supported(self) -> bool:
        return bool(self.authority)
