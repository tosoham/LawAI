"""
Typed claims: the unit an answer is built from.

A lawyer never confuses "the section says X" with "courts have read X to mean
Y" with "on these facts I would argue Z". Prose flattens all three into the
same confident paragraph, and for the audiences this system serves -- judges,
lawyers, and people with no legal training at all -- that flattening is the
most dangerous property it has. A citizen cannot tell which sentence is
enacted text and which is the model reasoning, because nothing in the output
distinguishes them.

So synthesis does not emit prose. It emits a list of claims, each carrying the
kind of thing it is, and the prose is rendered from that.

**Emitted, not annotated afterwards.** Labelling free text after the fact makes
the epistemic status a guess about a guess: a classifier reading "Section 103
provides for the death penalty in the rarest of rare cases" cannot tell which
half came from the statute and which from Bachan Singh. Emitting the class
alongside the sentence makes it constitutive, and mechanically checkable --
each class in ``EpistemicClass`` names a different check, which is the whole
point of having them (see ``services.claim_verifier``).

Nothing here verifies anything. This module is the shape; the checking, the
metrics and the rendering decisions all key off it.
"""
from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A section key as the legal graph and the corpus use it, optionally with the
# sub-clause the model cited. The sub-clause has to be accepted: asked about
# murder, a model correctly cites "BNS 103(1)", and rejecting that as
# unparseable made every well-cited classification claim fail for citing no
# section. It is normalised away because the corpus keys sections by their
# parent number, and the offence table is looked up through the parent too.
_SECTION_REF = re.compile(r"^(BNS|BNSS|BSA)\s+(\d{1,3})((?:\(\s*\w{1,3}\s*\))*)$")
# Judgement ids are minted by scripts/ingest_judgments.py.
_JUDGEMENT_REF = re.compile(r"^sc_[a-z0-9_]+$")
_URL_REF = re.compile(r"^https?://", re.IGNORECASE)
# Anything shaped like a statutory citation. Used to catch an inference that
# has dressed itself up as law. The optional letter matters: "section 41A" is
# a citation, and requiring a word boundary straight after the digits would
# miss every lettered one.
_LOOKS_LIKE_LAW = re.compile(
    r"\b(?:sections?|BNS|BNSS|BSA)\s+\d{1,3}[A-Za-z]?\b",
    re.IGNORECASE,
)


class EpistemicClass(str, Enum):
    """What kind of thing a claim is, and therefore how it must be checked."""

    STATUTE = "statute"
    """Enacted text, verbatim or a close paraphrase of a specific section."""

    CLASSIFICATION = "classification"
    """A procedural attribute: cognizable, bailable, triable by which court."""

    HOLDING = "holding"
    """What a court actually decided in a named case."""

    INTERPRETATION = "interpretation"
    """A settled judicial reading of a provision, attributable to authority."""

    CONTESTED = "contested"
    """Competing lines of authority, or an open constitutional question."""

    INFERENCE = "inference"
    """The model applying law to facts. Legitimate, and never law."""

    UNSUPPORTED = "unsupported"
    """No source resolved. Only ever assigned by the verifier, never emitted."""

    @property
    def requires_source(self) -> bool:
        """
        Whether a claim of this class is meaningless without a citation.

        Inference is the exception by design: applying law to facts is exactly
        the case where there is nothing to cite, and demanding one would push
        the model into inventing authority for its own reasoning -- the failure
        this whole scheme exists to prevent.
        """
        return self not in {EpistemicClass.INFERENCE, EpistemicClass.UNSUPPORTED}

    @property
    def is_law(self) -> bool:
        """Whether a reader is entitled to treat this claim as a statement of law."""
        return self in {
            EpistemicClass.STATUTE,
            EpistemicClass.CLASSIFICATION,
            EpistemicClass.HOLDING,
            EpistemicClass.INTERPRETATION,
        }


class SourceKind(str, Enum):
    SECTION = "section"
    JUDGEMENT = "judgement"
    DOCTRINE = "doctrine"
    LIVE = "live"
    """A live judiciary result: retrieved this turn, unverified by the corpus."""

    UNKNOWN = "unknown"


class ClaimSource(BaseModel):
    """
    One citation attached to a claim.

    Synthesis emits these as plain strings -- ``"BNS 103"``,
    ``"sc_bachan_singh_v_state_of_punjab_1980"`` -- because asking a model to
    also tag the kind is one more thing for it to get wrong, and the kind is
    recoverable from the shape. Classification happens here, deterministically.
    """

    ref: str
    kind: SourceKind = SourceKind.UNKNOWN

    model_config = ConfigDict(frozen=True)

    @classmethod
    def parse(cls, ref: str) -> ClaimSource:
        return cls(ref=normalise_ref(ref), kind=classify_source(ref))


def classify_source(ref: str) -> SourceKind:
    """Work out what a reference points at from its shape alone."""
    ref = ref.strip()
    if _SECTION_REF.match(ref):
        return SourceKind.SECTION
    if _JUDGEMENT_REF.match(ref):
        return SourceKind.JUDGEMENT
    if _URL_REF.match(ref):
        return SourceKind.LIVE
    if ref and "_" in ref and " " not in ref:
        return SourceKind.DOCTRINE
    return SourceKind.UNKNOWN


def normalise_ref(ref: str) -> str:
    """``"BNS 103(1)"`` -> ``"BNS 103"``; anything else is left alone."""
    match = _SECTION_REF.match(ref.strip())
    return f"{match.group(1)} {match.group(2)}" if match else ref.strip()


def looks_like_law(text: str) -> bool:
    """Whether a passage carries something shaped like a statutory citation."""
    return bool(_LOOKS_LIKE_LAW.search(text))


class Position(BaseModel):
    """
    One side of a contested question.

    A contested claim carrying a single position is not a contested claim; it
    is a one-sided answer wearing a warning label, which is worse than an
    unlabelled one because it looks careful.
    """

    summary: str = Field(..., description="What this line of authority holds")
    authority: list[str] = Field(
        default_factory=list, description="Judgement ids or citations supporting it"
    )

    @property
    def is_attributed(self) -> bool:
        return bool(self.authority)


class Claim(BaseModel):
    """One assertion in an answer, with the kind of assertion it is."""

    text: str = Field(..., description="The claim as it will be read")
    epistemic_class: EpistemicClass
    sources: list[ClaimSource] = Field(default_factory=list)
    verbatim_span: str | None = Field(
        None,
        description=(
            "For a statute claim, the exact words taken from the cited section. "
            "This is what verbatim fidelity is measured against; a paraphrase "
            "leaves it empty rather than approximating it."
        ),
    )
    positions: list[Position] = Field(
        default_factory=list, description="For a contested claim, the competing readings"
    )

    @field_validator("sources", mode="before")
    @classmethod
    def _accept_bare_strings(cls, value: object) -> object:
        """Let synthesis emit ``["BNS 103"]`` and get typed refs back."""
        if isinstance(value, list):
            return [ClaimSource.parse(v) if isinstance(v, str) else v for v in value]
        return value

    @property
    def source_refs(self) -> list[str]:
        return [source.ref for source in self.sources]


class ClaimVerdict(BaseModel):
    """The verifier's finding on one claim."""

    index: int
    verified: bool
    original_class: EpistemicClass
    """What synthesis asserted. Kept because verification rewrites a failure to
    ``unsupported``, and without this the metrics could not tell a statute
    claim that failed its verbatim check from one that was never made -- the
    denominator would shrink and fidelity would score 1.0 for catching it."""

    reason: str = ""
    """Why it failed, in words that can be shown to a user and fed back to the
    model on a regeneration attempt."""

    reclassified_to: EpistemicClass | None = None
    """Set when a claim could not stand as the class it was emitted as."""


class StructuredAnswer(BaseModel):
    """What synthesis produces, and what prose is rendered from."""

    claims: list[Claim] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.claims

    def by_class(self, epistemic_class: EpistemicClass) -> list[Claim]:
        return [c for c in self.claims if c.epistemic_class == epistemic_class]

    def without_unsupported(self) -> StructuredAnswer:
        """
        Drop every unsupported claim.

        Removed rather than softened. A claim with no resolvable source does
        not become true by being hedged -- "it appears that" in front of an
        invented section number still puts the section number in front of the
        reader, and hedged text is what people skim past. What was removed is
        recorded in the trace and reported.
        """
        return StructuredAnswer(
            claims=[c for c in self.claims if c.epistemic_class != EpistemicClass.UNSUPPORTED],
            abstained=self.abstained,
            abstention_reason=self.abstention_reason,
        )

    def render(self) -> str:
        """
        Render the claims as prose for plain-text consumers.

        Inference is set apart under its own heading rather than being woven in
        with the law. A structured client renders the classes itself and
        ignores this; the point of the heading is that a client which does not
        -- an export, a copy-paste, a log -- still cannot present the model's
        reasoning as though it were a provision.
        """
        if self.abstained:
            return self.abstention_reason

        law = [c for c in self.claims if c.epistemic_class.is_law]
        contested = self.by_class(EpistemicClass.CONTESTED)
        inference = self.by_class(EpistemicClass.INFERENCE)

        parts: list[str] = []
        if law:
            parts.append(" ".join(c.text for c in law))

        for claim in contested:
            lines = [claim.text, "", "The authorities differ on this:"]
            for position in claim.positions:
                authority = f" ({', '.join(position.authority)})" if position.authority else ""
                lines.append(f"- {position.summary}{authority}")
            parts.append("\n".join(lines))

        if inference:
            body = " ".join(c.text for c in inference)
            parts.append(f"**Applying this to the facts given** (reasoning, not law): {body}")

        return "\n\n".join(parts)
