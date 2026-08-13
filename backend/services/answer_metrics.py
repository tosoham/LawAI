"""
Measure an answer's grounding, so hallucination is a number rather than a mood.

A confidence score is a summary of the model's own feeling about its output,
which is precisely the thing that fails when the output is wrong. These are
counts over verified claims instead: each one is computed from the claim
structure and the verifier's findings, and each can move a build.

What they are for, one by one:

``grounding_rate``       share of claims that needed a source and resolved one.
                         Drops when the model starts asserting without citing.
``verbatim_fidelity``    of statute claims, the share that quoted the section
                         word for word and matched. A paraphrase is legitimate
                         and is *not* counted as fidelity -- crediting it would
                         make the metric measure confidence rather than
                         accuracy.
``unsupported``          claims removed from the answer. Zero to ship.
``unattributed_interpretation``
                         a settled judicial reading with no case behind it.
                         The classic way an invented holding gets through: the
                         reading is plausible, the class is right, and nobody
                         is named.
``inference_share``      how much of the answer is the model reasoning. A high
                         share on "what does the law say" is a smell even when
                         every individual claim is defensible.
``source_mix``           corpus, curated or live. An answer resting mainly on
                         unverified live results should be visible as such
                         rather than reading like settled law.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.claims import (
    Claim,
    ClaimVerdict,
    EpistemicClass,
    SourceKind,
    StructuredAnswer,
)


def _share(part: int, whole: int) -> float:
    """Zero-safe. An empty answer scores 0.0, never 1.0 -- nothing verified
    perfectly is not the same as nothing to verify."""
    return round(part / whole, 4) if whole else 0.0


@dataclass
class AnswerMetrics:
    """The numbers recorded for one answer."""

    claims: int = 0
    by_class: dict[str, int] = field(default_factory=dict)
    grounding_rate: float = 0.0
    verbatim_fidelity: float = 0.0
    quoted_statute_claims: int = 0
    unsupported: int = 0
    unattributed_interpretation: int = 0
    inference_share: float = 0.0
    source_mix: dict[str, int] = field(default_factory=dict)
    abstained: bool = False

    @property
    def ships(self) -> bool:
        """
        Whether this answer may be shown as it stands.

        One gate, and it is absolute: an answer carrying a claim with no
        resolvable source is not shown. Everything else here is a trend to
        watch, not a blocker.
        """
        return self.unsupported == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": self.claims,
            "by_class": dict(self.by_class),
            "grounding_rate": self.grounding_rate,
            "verbatim_fidelity": self.verbatim_fidelity,
            "quoted_statute_claims": self.quoted_statute_claims,
            "unsupported": self.unsupported,
            "unattributed_interpretation": self.unattributed_interpretation,
            "inference_share": self.inference_share,
            "source_mix": dict(self.source_mix),
            "abstained": self.abstained,
            "ships": self.ships,
        }


def _is_grounded(claim: Claim) -> bool:
    """
    Whether a claim that needed a citation has one.

    A contested claim is grounded by its positions rather than by the claim's
    own sources: the authority lives on each side of the split, which is where
    it has to be for the split to mean anything.
    """
    if claim.epistemic_class is EpistemicClass.CONTESTED:
        return bool(claim.positions) and all(p.is_attributed for p in claim.positions)
    return bool(claim.sources)


def compute(
    answer: StructuredAnswer, verdicts: list[ClaimVerdict] | None = None
) -> AnswerMetrics:
    """
    Compute the metrics for one answer.

    ``answer`` is the answer **as synthesis emitted it**, before the verifier
    rewrites failures to ``unsupported``; ``verdicts`` says which claims
    survived. That way round on purpose: the classes recorded here are the ones
    the model asserted, so a statute claim that failed its verbatim check still
    counts in the denominator of ``verbatim_fidelity``. Passing the rewritten
    answer instead would delete every failure from the record and score a
    perfect 1.0 for having caught them.
    """
    metrics = AnswerMetrics(claims=len(answer.claims), abstained=answer.abstained)

    by_class: dict[str, int] = {}
    for claim in answer.claims:
        key = claim.epistemic_class.value
        by_class[key] = by_class.get(key, 0) + 1
    metrics.by_class = by_class

    verified_indices = (
        {v.index for v in verdicts if v.verified} if verdicts is not None else None
    )
    metrics.unsupported = (
        sum(1 for v in verdicts if not v.verified)
        if verdicts is not None
        else by_class.get(EpistemicClass.UNSUPPORTED.value, 0)
    )

    needing_source = [c for c in answer.claims if c.epistemic_class.requires_source]
    metrics.grounding_rate = _share(
        sum(1 for c in needing_source if _is_grounded(c)), len(needing_source)
    )

    statute = [
        index
        for index, claim in enumerate(answer.claims)
        if claim.epistemic_class is EpistemicClass.STATUTE
    ]
    quoted = [index for index in statute if answer.claims[index].verbatim_span]
    metrics.quoted_statute_claims = len(quoted)
    # Measured against every statute claim, not only the quoted ones: a model
    # that stops quoting to avoid being checked must show up as a drop here,
    # not as an unchanged score over a shrinking denominator.
    matched = [i for i in quoted if verified_indices is None or i in verified_indices]
    metrics.verbatim_fidelity = _share(len(matched), len(statute))

    interpretations = answer.by_class(EpistemicClass.INTERPRETATION)
    metrics.unattributed_interpretation = sum(
        1
        for c in interpretations
        if not any(s.kind is SourceKind.JUDGEMENT for s in c.sources)
    )

    metrics.inference_share = _share(
        len(answer.by_class(EpistemicClass.INFERENCE)), len(answer.claims)
    )

    mix: dict[str, int] = {}
    for claim in answer.claims:
        for source in claim.sources:
            mix[source.kind.value] = mix.get(source.kind.value, 0) + 1
    metrics.source_mix = mix

    return metrics


def aggregate(runs: list[AnswerMetrics]) -> dict[str, Any]:
    """
    Mean the per-answer metrics across a set of queries.

    Used to track the golden set between builds, alongside the retrieval
    numbers in ``backend/eval/``. ``unsupported`` is reported as a total rather
    than a mean: one unsupported claim in fifty answers is one too many, and an
    average would round it into invisibility.
    """
    if not runs:
        return {"n": 0}
    n = len(runs)
    return {
        "n": n,
        "claims_per_answer": round(sum(r.claims for r in runs) / n, 3),
        "grounding_rate": round(sum(r.grounding_rate for r in runs) / n, 4),
        "verbatim_fidelity": round(sum(r.verbatim_fidelity for r in runs) / n, 4),
        "inference_share": round(sum(r.inference_share for r in runs) / n, 4),
        "unsupported_total": sum(r.unsupported for r in runs),
        "unattributed_interpretation_total": sum(
            r.unattributed_interpretation for r in runs
        ),
        "abstained": sum(1 for r in runs if r.abstained),
        "answers_that_ship": sum(1 for r in runs if r.ships),
    }
