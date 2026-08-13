"""
Check each claim the way its own class demands.

**Nothing here asks a model whether a model was right.** Self-grading fails
exactly where it is needed: a model that has invented BNS 999 will confirm BNS
999, because the same prior produced both. Every check below is a lookup
against committed data or a structural property of the claim itself, so a
failure is a fact rather than an opinion, and the same claim always gets the
same verdict.

What each class has to survive:

``statute``          the cited section exists, and any quoted span appears in
                     its text verbatim
``classification``   the attribute matches the First Schedule row, which is
                     only checkable because the Schedule was parsed into a table
``holding``          the case exists in the corpus (or in this turn's live
                     results) and the graph records it as bearing on the cited
                     section -- a real case cited for a section it never
                     mentions is the subtlest failure in the whole set, because
                     both halves check out separately
``interpretation``   as for a holding, and it must attribute to a case rather
                     than floating free
``contested``        at least two positions, each with authority. A contested
                     question answered one-sidedly is a failure even when that
                     side is impeccably cited
``inference``        allowed to have no source, but must not carry a citation
                     formatted as if it were law
anything else        unsupported

A claim that fails is reclassified ``unsupported`` and removed downstream, not
softened. Hedging an invented section number still puts the number in front of
the reader.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from models.claims import (
    Claim,
    ClaimVerdict,
    EpistemicClass,
    SourceKind,
    StructuredAnswer,
    looks_like_law,
)

from .legal_graph import LegalGraph, get_legal_graph

logger = logging.getLogger(__name__)

# A quoted span is compared after collapsing whitespace and case, because the
# gazette's line breaks and the model's re-wrapping are not differences in the
# law. Nothing else is normalised -- a changed word is a changed provision.
_WHITESPACE = re.compile(r"\s+")

# What a classification claim asserts. One pattern rather than four, because
# "non-bailable" contains "bailable": matched separately, a claim saying an
# offence is non-bailable also registers as saying it is bailable. The optional
# prefix carries the negation, and finditer does not re-match inside a match.
# "not bailable" is caught for the same reason -- a true claim phrased in prose
# must not be rejected for disagreeing with itself.
_CLASSIFICATION_TERM = re.compile(r"\b(not\s+|non-)?(cognizable|bailable)\b")
_COURTS = ("court of session", "magistrate")
_TRAILING_PUNCTUATION = re.compile(r"[.,;:]+$")


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


@dataclass
class VerificationContext:
    """
    What the verifier is allowed to check against.

    ``live_judgements`` is passed in per turn rather than read from anywhere:
    live judiciary results are retrieved, not curated, and they exist only for
    the request that fetched them. A claim resting on one is verifiable *this
    turn* and carries a different provenance, which the metrics keep separate.
    """

    graph: LegalGraph
    section_texts: dict[str, str] = field(default_factory=dict)
    """Section key -> full text, for verbatim checks. Usually this turn's
    retrieved chunks; a span that was never retrieved cannot be verified."""

    live_judgements: set[str] = field(default_factory=set)

    @classmethod
    def from_retrieval(
        cls,
        search_results: dict[str, Any] | None = None,
        live_judgements: set[str] | None = None,
        graph: LegalGraph | None = None,
    ) -> VerificationContext:
        """Build a context from what retrieval actually returned this turn."""
        texts: dict[str, str] = {}
        if search_results:
            documents = search_results.get("documents", [])
            metadatas = search_results.get("metadatas", [])
            for document, metadata in zip(documents, metadatas, strict=False):
                act = metadata.get("short_name")
                section = metadata.get("section_number")
                if not act or not section:
                    continue
                key = f"{act} {section}"
                # A section is chunked, so its text arrives in pieces; keep them
                # all or a span from the tail looks fabricated.
                texts[key] = f"{texts.get(key, '')} {document}".strip()
        return cls(
            graph=graph or get_legal_graph(),
            section_texts=texts,
            live_judgements=set(live_judgements or ()),
        )


def _section_text(context: VerificationContext, key: str) -> str:
    node = context.graph.sections.get(key)
    return node.text if node else ""


def _sections_of(claim: Claim) -> list[str]:
    return [s.ref for s in claim.sources if s.kind is SourceKind.SECTION]


def _judgements_of(claim: Claim) -> list[str]:
    return [s.ref for s in claim.sources if s.kind is SourceKind.JUDGEMENT]


def _verify_statute(claim: Claim, context: VerificationContext) -> tuple[bool, str]:
    sections = _sections_of(claim)
    if not sections:
        return False, "a statute claim cites no section"

    unknown = [key for key in sections if not context.graph.has_section(key)]
    if unknown:
        return False, f"cites {', '.join(unknown)}, which is not in the corpus"

    if not claim.verbatim_span:
        # A paraphrase is legitimate; it just cannot be checked word for word,
        # and the metrics count it separately rather than crediting it.
        return True, ""

    # Checked against the whole section, not only the chunk retrieval returned.
    # Whether a quotation is accurate does not depend on which piece of the
    # section happened to rank: asked for the punishment for theft, the model
    # quoted BNS 303 correctly while retrieval had returned that section's
    # fifth chunk, and checking only the chunk rejected a true statement of the
    # law. The corpus holds the section entire, so use it.
    # Trailing punctuation is stripped from the span only. A quotation that
    # stops mid-sentence and closes with a full stop is still a faithful
    # quotation of the words -- BNS 303 reads "or with both and in case of
    # second conviction...", and quoting "or with both." was being rejected as
    # a misquote. Interior punctuation is left alone: that is the model
    # rewriting the provision, not ending a sentence.
    span = _normalise(claim.verbatim_span).rstrip(".,;: ")
    for key in sections:
        for text in (context.section_texts.get(key), _section_text(context, key)):
            if text and span in _normalise(text):
                return True, ""
    return False, f"quoted text does not appear in {', '.join(sections)}"


def _verify_classification(claim: Claim, context: VerificationContext) -> tuple[bool, str]:
    sections = _sections_of(claim)
    if not sections:
        return False, "a classification claim cites no section"

    rows = [row for key in sections for row in context.graph.offence_attributes(key)]
    if not rows:
        # Said this way because the mistake is nearly always the same one, and
        # a model told only that its citation was wrong re-answers with nothing
        # instead of re-answering with the right section: asked whether murder
        # is bailable it cites BNS 101, which defines murder, when the
        # classification hangs off BNS 103, which punishes it.
        return False, (
            f"{', '.join(sections)} has no row in the First Schedule. A "
            "classification attaches to the section that punishes an offence, not "
            "the one that defines it"
        )

    text = _normalise(claim.text)
    asserted: dict[str, tuple[bool, str]] = {}
    for match in _CLASSIFICATION_TERM.finditer(text):
        negated, attribute = match.group(1), match.group(2)
        asserted[attribute] = (not negated, match.group(0))

    court = next((name for name in _COURTS if name in text), None)
    if not asserted and court is None:
        return False, "a classification claim states no classification"

    rows = _rows_the_claim_is_about(text, rows)

    for attribute, (value, phrase) in asserted.items():
        recorded = {row[attribute] for row in rows}
        if len(recorded) > 1:
            return False, _ambiguous(sections, rows, f"{attribute}_text")
        if value not in recorded:
            stated = ", ".join(row[f"{attribute}_text"] for row in rows)
            return False, (
                f"claims {phrase!r} for {', '.join(sections)}, but the First Schedule "
                f"records: {stated}"
            )

    if court is not None:
        courts = {row["triable_by"] for row in rows}
        if len(courts) > 1:
            return False, _ambiguous(sections, rows, "triable_by")
        if not any(court in row["triable_by"].lower() for row in rows):
            return False, (
                f"names a {court} for {', '.join(sections)}, but the First Schedule "
                f"records: {', '.join(courts)}"
            )
    return True, ""


def _rows_the_claim_is_about(text: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Narrow a section's Schedule rows to the ones the claim actually concerns.

    A section is often classified more than once, and the rows can disagree.
    BNS 303 is theft: "Theft" is cognizable and non-bailable, while "Where value
    of property is less than 5,000 rupees" is neither. Checking a claim against
    the union of the rows lets "theft is bailable" pass by matching the petty
    case -- which is how a false bailability got through in testing, the exact
    failure this verifier exists to prevent.

    So the row is chosen by its own offence wording appearing in the claim.
    Where that picks nothing out, every row stays a candidate and the caller
    rejects the claim if they disagree.
    """
    selected = [
        row
        for row in rows
        if (phrase := _TRAILING_PUNCTUATION.sub("", row["offence"]).strip().lower())
        and phrase in text
    ]
    return selected or rows


def _ambiguous(sections: list[str], rows: list[dict[str, Any]], field_name: str) -> str:
    variants = "; ".join(f"{row['offence']} -> {row[field_name]}" for row in rows)
    return (
        f"{', '.join(sections)} is classified more than one way and the claim does "
        f"not say which case it means ({variants})"
    )


def _verify_attributed_to_a_case(
    claim: Claim, context: VerificationContext, label: str
) -> tuple[bool, str]:
    judgements = _judgements_of(claim)
    if not judgements:
        return False, f"a {label} claim names no judgement"

    unknown = [
        j
        for j in judgements
        if j not in context.graph.judgements and j not in context.live_judgements
    ]
    if unknown:
        return False, f"cites {', '.join(unknown)}, which is not in the corpus"

    sections = _sections_of(claim)
    if not sections:
        return True, ""

    # The subtle one: a real case cited for a section it has nothing to do
    # with. Both halves check out on their own, and only the edge catches it.
    for judgement in judgements:
        if judgement in context.live_judgements:
            # A live result has no graph edges yet; the case existing is all
            # that can be checked, and its provenance is reported separately.
            continue
        recorded = set(context.graph.interprets.get(judgement, []))
        stray = [key for key in sections if key not in recorded]
        if stray and recorded:
            return False, (
                f"cites {judgement} for {', '.join(stray)}, which it is not recorded "
                f"as interpreting (it bears on {', '.join(sorted(recorded))})"
            )
    return True, ""


def _verify_contested(claim: Claim, context: VerificationContext) -> tuple[bool, str]:
    if len(claim.positions) < 2:
        return False, (
            "a contested claim carries fewer than two positions; a contested "
            "question answered one-sidedly is a failure even when that side is "
            "well cited"
        )
    unattributed = [p.summary for p in claim.positions if not p.is_attributed]
    if unattributed:
        return False, f"{len(unattributed)} of the positions cite no authority"

    unknown = [
        ref
        for position in claim.positions
        for ref in position.authority
        if ref.startswith("sc_")
        and ref not in context.graph.judgements
        and ref not in context.live_judgements
    ]
    if unknown:
        return False, f"cites {', '.join(unknown)}, which is not in the corpus"
    return True, ""


def _verify_inference(claim: Claim) -> tuple[bool, str]:
    """
    Inference is allowed to rest on nothing. It is not allowed to look like law.

    The failure this catches is a claim marked as reasoning that nonetheless
    reads "under section 187(3) you are entitled to release" -- correctly
    labelled in the data and indistinguishable from a provision on the page.
    """
    if looks_like_law(claim.text) and not claim.sources:
        return False, (
            "an inference cites a provision by number without a source; either "
            "attach the section it relies on or state the reasoning without "
            "dressing it as law"
        )
    return True, ""


def verify_claim(claim: Claim, context: VerificationContext) -> tuple[bool, str]:
    """Check one claim against the rule for its class."""
    match claim.epistemic_class:
        case EpistemicClass.STATUTE:
            return _verify_statute(claim, context)
        case EpistemicClass.CLASSIFICATION:
            return _verify_classification(claim, context)
        case EpistemicClass.HOLDING:
            return _verify_attributed_to_a_case(claim, context, "holding")
        case EpistemicClass.INTERPRETATION:
            return _verify_attributed_to_a_case(claim, context, "interpretation")
        case EpistemicClass.CONTESTED:
            return _verify_contested(claim, context)
        case EpistemicClass.INFERENCE:
            return _verify_inference(claim)
        case _:
            return False, "no source resolved"


def verify(
    answer: StructuredAnswer, context: VerificationContext
) -> tuple[StructuredAnswer, list[ClaimVerdict]]:
    """
    Verify every claim, reclassifying the failures.

    Returns the answer with failed claims marked ``unsupported`` -- they are
    still present here so the trace can report what was removed and why --
    together with a verdict for each claim.
    """
    verdicts: list[ClaimVerdict] = []
    claims: list[Claim] = []

    for index, claim in enumerate(answer.claims):
        verified, reason = verify_claim(claim, context)
        verdicts.append(
            ClaimVerdict(
                index=index,
                verified=verified,
                original_class=claim.epistemic_class,
                reason=reason,
                reclassified_to=None if verified else EpistemicClass.UNSUPPORTED,
            )
        )
        if verified:
            claims.append(claim)
        else:
            logger.info(f"claim {index} failed verification ({claim.epistemic_class}): {reason}")
            claims.append(claim.model_copy(update={"epistemic_class": EpistemicClass.UNSUPPORTED}))

    return (
        StructuredAnswer(
            claims=claims,
            abstained=answer.abstained,
            abstention_reason=answer.abstention_reason,
        ),
        verdicts,
    )


def regeneration_feedback(
    answer: StructuredAnswer, verdicts: list[ClaimVerdict]
) -> str:
    """
    Name the offending claims, for one regeneration attempt.

    Given back to the model rather than acted on silently: the failures are
    often fixable by dropping a citation or splitting a claim in two, and a
    model told exactly which sentence failed and why will usually do it. If the
    second attempt still fails, the claims are removed.
    """
    failures = [v for v in verdicts if not v.verified]
    if not failures:
        return ""
    lines = ["These claims did not verify and must be corrected or dropped:"]
    misquoted = False
    for verdict in failures:
        claim = answer.claims[verdict.index]
        lines.append(f"- [{claim.epistemic_class.value}] {claim.text!r}: {verdict.reason}")
        misquoted = misquoted or "quoted text does not appear" in verdict.reason

    if misquoted:
        # Without this the model drops the point altogether and an answerable
        # question -- "what is the punishment for theft" -- comes back as an
        # abstention because the quotation was a few words out. A paraphrase is
        # still checked: the cited section has to exist and be the right one.
        lines.append(
            "Where a quotation did not match, you may keep the point and paraphrase "
            "it instead: omit verbatim_span and state the substance. Only quote "
            "words you can reproduce exactly."
        )
    lines.append(
        "Do not restate a failed claim more cautiously. Either support it, or leave "
        "it out."
    )
    return "\n".join(lines)
