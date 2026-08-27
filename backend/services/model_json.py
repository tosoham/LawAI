"""
Reading JSON out of a model that was asked for JSON.

Extracted from ``services/grounded_answer.py`` when the planner needed the same
discipline. Duplicating it would have been worse than the extraction: both
callers parse a structured response from the same provider, and two copies of
this drift until one of them silently stops tolerating something the other
does.

Everything here is tolerance for how models actually reply, and each tolerance
was added because its absence produced an abstention rather than an error --
which is the expensive failure, because an abstention looks like a considered
refusal.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Models wrap JSON in a fence more often than not, whatever the prompt says.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def strip_fence(text: str) -> str:
    """Unwrap a ```json fence, or return the text stripped."""
    match = _FENCE.match(text or "")
    return match.group(1) if match else (text or "").strip()


def extract_json(body: str) -> str | None:
    """
    Pull the JSON value out of a response that wrapped it in something.

    Worth doing rather than failing: a model that prefaces its object with a
    sentence has still produced a perfectly good answer, and treating that as a
    malformed generation turned answerable questions into abstentions
    intermittently -- four runs in five on one of them, for a reason that had
    nothing to do with the law.
    """
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = body.find(opener), body.rfind(closer)
        if start != -1 and end > start:
            return body[start : end + 1]
    return None


def load_json_payload(raw: str) -> Any | None:
    """
    The parsed JSON value in a model response, or ``None``.

    Tries the body as-is first and only then the extracted span, so a response
    that is already clean JSON is never reshaped by the salvage path.
    """
    body = strip_fence(raw)
    for candidate in (body, extract_json(body)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    logger.warning(f"model did not return JSON: {body[:300]!r}")
    return None
