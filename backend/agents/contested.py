"""
Two advocates, one bounded rebuttal, and no winner.

**This is the only place in the system where more than one agent is doing
something one agent cannot.** Everywhere else, fan-out buys latency and
modularity: the same pipeline asked several questions at once. Here a single
agent is structurally unable to do the job, because developing a reading while
simultaneously arguing against it produces the hedged middle that reads as
balance and is actually neither position stated properly.

The shape, decided before it was built:

* **round one is independent.** Each advocate develops its reading without
  seeing the other, so neither anchors on the other's framing.
* **round two is one rebuttal each.** Each sees the other's argument exactly
  once and answers it. This is where the real disagreement surfaces -- the
  strongest answer to an argument is usually the most useful thing on a
  contested question.
* **it stops there.** Open-ended dialogue converges, and convergence is the
  failure mode: if one advocate concedes, the output is a one-sided answer,
  which ``claim_verifier`` then rejects for carrying fewer than two positions.
  A debate that "succeeded" would produce an abstention.

**Neither advocate may concede, and neither may invent.** An advocate that
cannot find authority for its assigned position says so, and that is recorded
as an unsupported position rather than dropped. That a side cannot be supported
from this corpus is a finding, and a more useful one than a fabricated citation
propping it up.

**The synthesiser must not pick a winner** -- not by conclusion, ordering or
emphasis. This is the same prohibition judge mode already carries and it is
tested the same way, with prompts that invite one directly.
"""
from __future__ import annotations

import logging

from agents.contracts import AgentError, Position
from services.llm_service import llm_service
from services.model_json import load_json_payload

logger = logging.getLogger(__name__)

#: Enough for a position and its authority. Bounded so a runaway generation
#: cannot turn a two-agent exchange into an essay.
POSITION_MAX_TOKENS = 700

#: One. See the module docstring: more rounds converge, and convergence here
#: produces an abstention rather than an answer.
REBUTTAL_ROUNDS = 1

ADVOCATE_SYSTEM = """You are developing one side of a genuinely contested question \
of Indian criminal law under the 2023 codes.

Your job is to state the strongest version of the position you have been given, \
supported by authority from the material provided. You are not deciding the \
question and you are not being asked what you personally think is right.

Two rules that matter more than persuasiveness:

You may not concede. If the material does not support your assigned position, \
say exactly that and leave the authority list empty. That is a real finding and \
it will be reported as one. It is far better than a citation that does not say \
what you need it to say -- every citation you give is checked mechanically \
against the corpus afterwards, and one that fails is deleted.

You may not invent. Cite only judgement ids and section keys that appear in the \
material you were given, exactly as they are written there."""

ADVOCATE_INSTRUCTIONS = """Return JSON of exactly this shape and nothing else:

{"label": "...", "summary": "...", "authority": ["BNSS 480", "sc_..."]}

  label      a short neutral name for the reading -- what it says, not whether
             it wins. "Bail is the rule", not "the correct view". A label
             that announces a verdict has already decided the question.
  summary    the position, stated as strongly as the material allows.
  authority  section keys and judgement ids from the material, verbatim. Empty
             if the material does not support this position."""

REBUTTAL_INSTRUCTIONS = """Below is the position you developed, and the position \
developed independently on the other side.

Answer the other side's argument in two or three sentences. Say where it is \
weakest and what it does not account for.

You may not concede and you may not restate your own position -- this is the \
answer to theirs. If their argument is strong on a point, say what remains of \
yours despite it.

Return JSON of exactly this shape and nothing else:

{"rebuttal": "..."}"""


def _parse_position(raw: str, fallback_label: str) -> Position | None:
    """Read one advocate's reply, or ``None`` if it produced nothing usable."""
    payload = load_json_payload(raw)
    if not isinstance(payload, dict):
        return None
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        return None
    authority = payload.get("authority")
    return Position(
        label=str(payload.get("label") or fallback_label).strip() or fallback_label,
        summary=summary,
        authority=[
            str(a).strip()
            for a in (authority if isinstance(authority, list) else [])
            if str(a).strip()
        ],
    )


def _advocate(
    question: str, side: str, context: str, service
) -> tuple[Position | None, AgentError | None]:
    prompt = (
        f"{ADVOCATE_INSTRUCTIONS}\n\nCONTESTED QUESTION:\n{question}\n\n"
        f"THE POSITION YOU ARE DEVELOPING:\n{side}\n\nMATERIAL:\n{context}"
    )
    try:
        raw = service.generate(
            prompt=prompt,
            system=ADVOCATE_SYSTEM,
            max_tokens=POSITION_MAX_TOKENS,
            temperature=0.2,
        )
    except Exception as error:
        return None, AgentError(stage="contested", message=f"{side}: {error}")

    position = _parse_position(raw, side)
    if position is None:
        return None, AgentError(
            stage="contested", message=f"{side}: no usable position returned"
        )
    return position, None


def _rebut(question: str, mine: Position, theirs: Position, service) -> str:
    prompt = (
        f"{REBUTTAL_INSTRUCTIONS}\n\nCONTESTED QUESTION:\n{question}\n\n"
        f"YOUR POSITION:\n{mine.summary}\n\n"
        f"THE OTHER SIDE:\n{theirs.summary}"
    )
    try:
        raw = service.generate(
            prompt=prompt,
            system=ADVOCATE_SYSTEM,
            max_tokens=POSITION_MAX_TOKENS,
            temperature=0.2,
        )
    except Exception as error:
        logger.warning(f"rebuttal failed ({error}); keeping the position as it stands")
        return ""

    payload = load_json_payload(raw)
    if isinstance(payload, dict):
        return str(payload.get("rebuttal") or "").strip()
    return ""


def develop_positions(
    question: str,
    sides: tuple[str, str],
    context: str,
    service=None,
) -> tuple[list[Position], list[AgentError]]:
    """
    Develop both sides of a contested question, then let each answer the other.

    ``sides`` names the two readings, taken from the curated doctrine's
    ``contest_note`` where there is one -- that file records where authority
    splits and names both sides without declaring a winner, which is exactly
    the input this needs and exactly what a model should not be asked to invent.

    Returns whatever it got. One advocate failing leaves a single position,
    which is honest and which the verifier will refuse to render as a contested
    claim -- correctly, because one position is a one-sided answer with a
    warning on it.
    """
    service = service or llm_service
    positions: list[Position] = []
    errors: list[AgentError] = []

    for side in sides:
        position, error = _advocate(question, side, context, service)
        if error is not None:
            errors.append(error)
        if position is not None:
            positions.append(position)

    if len(positions) == 2:
        # Both written independently; only now does either see the other.
        first, second = positions
        first_rebuttal = _rebut(question, first, second, service)
        second_rebuttal = _rebut(question, second, first, service)
        first.rebuttal = first_rebuttal
        second.rebuttal = second_rebuttal

    unsupported = [p.label for p in positions if not p.supported]
    if unsupported:
        logger.info(
            f"contested: no authority found for {', '.join(unsupported)} "
            "(reported, not dropped)"
        )
    return positions, errors
