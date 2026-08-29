"""
What production is telling us, captured so it can become a test.

The golden set is a *reference* set: 69 questions we thought to write, held
fixed so a change that breaks something shows up. It cannot tell us what real
users ask, and no amount of care in writing it will — that is the one thing
only production has.

**But production gives queries, not labels.** A user typing "can they hold my
brother past 60 days" does not say what the right answer was, and turning it
into a regression test still needs someone to decide. So the useful question is
narrower: *which production events label themselves?*

Three do, and all three are already computed on every answer:

``abstained``        the system found nothing it could stand behind. Either the
                     question is genuinely out of corpus, or retrieval missed
                     something it should have found. Both are worth reading.
``claims_removed``   the verifier caught the model overreaching. The claim text
                     and the reason are already recorded, so this is a fully
                     specified failure with no labelling needed.
``nothing_retrieved``  no chunk came back at all. Out of scope, or a vocabulary
                     gap in the expansion table -- which is a fix, not a limit.

None of those needs a human to know *something went wrong*. A human is still
needed to say what the right answer was, which is why this is a **queue of
candidates**, not a golden set. `scripts/review_feedback.py` is where a person
turns one into the other.

Nothing here is on the request path. Capture is best-effort and swallows its
own errors: a feedback store that can fail a legal answer is worse than no
feedback store.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FEEDBACK_PATH = Path(
    os.getenv("FEEDBACK_LOG_PATH", str(Path(__file__).resolve().parent.parent / "feedback" / "events.jsonl"))
)

#: Cap on the query text kept. A legal question can carry facts about a real
#: person; this is a diagnostic store, not a case file, and a truncated query
#: is still enough to reproduce a retrieval failure.
MAX_QUERY_CHARS = int(os.getenv("FEEDBACK_MAX_QUERY_CHARS", "500"))


def feedback_enabled() -> bool:
    """
    Whether production events are captured at all.

    Off by default. This writes user-typed text to disk, and that is a decision
    about data handling rather than a default anyone should inherit by
    upgrading.
    """
    return os.getenv("ENABLE_FEEDBACK_CAPTURE", "false").strip().lower() in {
        "1", "true", "yes",
    }


@dataclass
class FeedbackEvent:
    """One production answer worth looking at again."""

    query: str
    signals: list[str]
    """Why this was kept: `abstained`, `claims_removed`, `nothing_retrieved`,
    `user_reported`. More than one can apply."""

    removed: list[dict[str, str]] = field(default_factory=list)
    """The claims the verifier threw out, with reasons. Already a fully
    specified failure -- no labelling needed to act on it."""

    retrieved: list[str] = field(default_factory=list)
    """Which ids came back, so a retrieval miss can be reproduced without
    re-running the model."""

    note: str = ""
    """What a user said, where they said anything."""

    id: str = ""
    at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id or uuid.uuid4().hex[:12],
            "at": self.at or datetime.now(UTC).isoformat(),
            "query": self.query[:MAX_QUERY_CHARS],
            "signals": self.signals,
            "removed": self.removed,
            "retrieved": self.retrieved[:20],
            "note": self.note[:MAX_QUERY_CHARS],
        }


_lock = threading.Lock()


def signals_from(result: Any) -> list[str]:
    """
    Which self-labelling signals an answer tripped.

    Reads the shape ``GroundedAnswer`` already has, so nothing new has to be
    computed on the request path -- these are by-products of answering, not
    measurements taken for this.
    """
    signals: list[str] = []
    if getattr(result, "abstained", False):
        signals.append("abstained")
    if any(not v.verified for v in getattr(result, "verdicts", []) or []):
        signals.append("claims_removed")
    if not (getattr(result, "sources", None) or []):
        signals.append("nothing_retrieved")
    return signals


def capture(result: Any, query: str, note: str = "") -> FeedbackEvent | None:
    """
    Record an answer worth revisiting, or return ``None``.

    An answer that tripped no signal is not stored. The store is meant to be
    read by a person, and a log of everything is a log nobody opens.

    Never raises. This sits beside the answer, not in front of it.
    """
    if not feedback_enabled():
        return None
    try:
        signals = signals_from(result)
        if not signals and not note:
            return None

        event = FeedbackEvent(
            query=query,
            signals=signals + (["user_reported"] if note else []),
            removed=[
                {
                    "class": v.original_class.value,
                    "reason": v.reason,
                    "text": result.structured.claims[v.index].text[:300],
                }
                for v in (result.verdicts or [])
                if not v.verified and v.index < len(result.structured.claims)
            ],
            retrieved=[s.get("citation") or s.get("id", "") for s in (result.sources or [])],
            note=note,
        )
        _append(event)
        return event
    except Exception as error:  # capture must never fail an answer
        logger.warning(f"feedback capture failed, continuing: {error}")
        return None


def _append(event: FeedbackEvent) -> None:
    """
    Append one event as a JSON line.

    JSONL rather than a database: the whole point is that a person reads this
    and turns entries into fixture rows, and a file that `grep` and `jq` work
    on needs no migration, no service and no schema decision made before we
    know what the entries look like.
    """
    payload = event.to_dict()
    with _lock:
        FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_events(limit: int | None = None) -> list[dict[str, Any]]:
    """Every captured event, newest last. Missing file reads as empty."""
    if not FEEDBACK_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # One malformed line must not hide the rest -- the same rule the
            # synthesis parser follows for a bad claim.
            logger.warning("skipping a malformed feedback line")
    return events[-limit:] if limit else events


def summarise() -> dict[str, Any]:
    """Counts by signal, and the most common rejection reasons."""
    from collections import Counter

    events = read_events()
    signals: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for event in events:
        signals.update(event.get("signals", []))
        for removed in event.get("removed", []):
            reasons[removed.get("reason", "")[:70]] += 1
    return {
        "events": len(events),
        "by_signal": dict(signals.most_common()),
        "top_rejection_reasons": dict(reasons.most_common(10)),
        "path": str(FEEDBACK_PATH),
    }
