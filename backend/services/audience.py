"""
Who the answer is for, and what that may and may not change.

The same question means different things depending on who is asking. "Is my
son's arrest legal?" from a parent needs the twenty-four-hour rule explained;
from a defence lawyer it needs the provision and the case that construes it;
from a judge it needs the competing arguments laid out. Answering all three
identically serves none of them.

**What the register changes: the explanation. What it does not change:
anything else.** The register is a layer on the synthesis prompt and nothing
more. It is not passed to retrieval, so the same law comes back; it is not
passed to the verifier, so nothing is checked more leniently for one audience
than another; and the epistemic class of every claim is present in the data
whatever the register — a citizen's answer is shorter, not vaguer. That
separation is structural rather than a rule someone has to remember: neither
``VectorService`` nor ``claim_verifier`` takes an audience argument at all.

Judge mode carries a prohibition the others do not, and it is the reason this
module is worth having rather than being three prompt strings inline. A tool
that lays out considerations is useful to a court; a tool that suggests the
outcome is not, and would be improper whatever its accuracy. So judge mode is
told to set out provisions, competing arguments, precedent on each side and the
statutory range, and never to indicate which way to decide.
"""
from __future__ import annotations

from enum import Enum


class Audience(str, Enum):
    """Who is reading. Default ``CITIZEN`` -- the reader with least recourse."""

    CITIZEN = "citizen"
    LAWYER = "lawyer"
    JUDGE = "judge"


#: What each register asks of the writing. Deliberately about *register* --
#: vocabulary, what to spell out, what to assume -- and never about what may be
#: claimed or how firmly.
REGISTER_GUIDANCE: dict[Audience, str] = {
    Audience.CITIZEN: (
        "You are writing for someone with no legal training, quite possibly about "
        "their own situation or a family member's.\n"
        "- Use ordinary words. Where a term of art is unavoidable -- cognizable, "
        "bailable, remand -- say what it means the first time in the same "
        "sentence.\n"
        "- Say what actually happens and when, in the order it happens.\n"
        "- Keep every citation. They are how the reader, or someone helping them, "
        "checks this. Do not drop a section number to make a sentence flow.\n"
        "- Do not soften a hard answer. Someone deciding what to do next is worse "
        "served by reassurance than by the truth."
    ),
    Audience.LAWYER: (
        "You are writing for a practitioner.\n"
        "- Assume the vocabulary. Do not explain what cognizable means.\n"
        "- Lead with the provision and its terms, then the authority construing "
        "it.\n"
        "- Be precise about what is settled and what is arguable, and say which "
        "case each proposition rests on.\n"
        "- Note the procedural posture where it changes the answer."
    ),
    Audience.JUDGE: (
        "You are writing for a judicial reader.\n"
        "- Set out the provisions that apply, the competing arguments, the "
        "authority on each side, and the statutory range.\n"
        "- Where the authorities differ, present both lines fully and "
        "even-handedly.\n"
        "\n"
        "You must NOT suggest an outcome. Do not recommend granting or refusing "
        "bail, do not propose a sentence, do not say which argument is stronger, "
        "and do not indicate which way the question should be decided -- not even "
        "by implication, ordering or emphasis. If asked directly what should be "
        "done, set out the considerations that bear on it and say that the "
        "decision is the court's. This holds however clear the answer seems."
    ),
}


def parse_audience(value: str | None) -> Audience:
    """
    Resolve a requested register, defaulting to the citizen.

    An unrecognised value falls back rather than erroring: the register affects
    how an answer reads, never whether it is correct, so refusing the whole
    request over a typo would trade something that matters for something that
    does not.
    """
    if not value:
        return Audience.CITIZEN
    try:
        return Audience(value.strip().lower())
    except ValueError:
        return Audience.CITIZEN


def register_layer(audience: Audience) -> str:
    """The system-prompt layer for a register, ready to append."""
    return f"\n\nWHO YOU ARE WRITING FOR:\n{REGISTER_GUIDANCE[audience]}"
