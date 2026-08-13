"""
Resolve "is murder bailable" to the section that answers it.

Classification questions are the most common practical questions in Indian
criminal law and the ones dense retrieval is worst at, for a reason that has
nothing to do with tuning: *the words are not in the statute*. "Bailable",
"cognizable" and "triable by" are First Schedule vocabulary. They appear
nowhere in the Bharatiya Nyaya Sanhita, so a query built out of them pulls the
embedder towards whatever prose is nearest, and the section that actually
carries the answer sinks.

Measured: "Is murder a bailable offence and which court tries it?" puts BNS 103
at rank 6, outside a top_k of 5, so it never reaches the model at all. "Is
theft bailable" does not surface BNS 303 in the top 8. The model then either
attributes the classification to whichever section it *was* given -- BNS 101,
the definition of murder, which has no classification -- or gives up. Both are
verifier failures rather than answers.

But the First Schedule names every offence in a column of its own, so this is
not a search either. "Murder." is a key. Matching the query against those names
is exact, deterministic, and cannot invent a section.

This is the same move as ``structured_filter``: where the corpus holds the
answer under an exact key, look it up instead of searching for it.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "processed"
    / "offence_classification.json"
)

# What makes a question a classification question. Deliberately narrow: these
# are the words the First Schedule answers and the statute does not.
_CLASSIFICATION_QUESTION = re.compile(
    r"\b(bailable|cognizable|triable|which court|what court|arrest(ed)?\s+without\s+"
    r"(a\s+)?warrant|court of session|magistrate)\b",
    re.IGNORECASE,
)

# An offence name short enough to be a phrase someone would use. The long
# entries are conditional clauses -- "Abetment of any offence, if the act
# abetted is committed in consequence, and where no express provision is made
# for its punishment" -- which nobody types and which would match nothing.
MAX_OFFENCE_PHRASE_WORDS = 6
# More than a handful means the phrase was too generic to be a lookup.
MAX_MATCHES = 4

_PUNCTUATION = re.compile(r"[.,;:]+$")


def is_classification_question(query: str) -> bool:
    """Whether the query asks something the First Schedule answers."""
    return bool(_CLASSIFICATION_QUESTION.search(query or ""))


def _phrase(offence: str) -> str | None:
    """The offence name as a searchable phrase, or ``None`` if unusable."""
    text = _PUNCTUATION.sub("", offence.strip()).lower()
    if not text or len(text.split()) > MAX_OFFENCE_PHRASE_WORDS:
        return None
    # A conditional variant ("If offence be not committed") describes a case,
    # not an offence, and matches on stopwords.
    if text.startswith(("if ", "in any other case", "same offence", "any other")):
        return None
    return text


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, str, re.Pattern[str]]]:
    """``[(phrase, section key, matcher)]``, longest phrase first."""
    if not TABLE_PATH.exists():
        logger.warning(f"{TABLE_PATH} is missing; offence lookup disabled")
        return []

    entries: list[tuple[str, str, re.Pattern[str]]] = []
    for row in json.loads(TABLE_PATH.read_text()):
        phrase = _phrase(row["offence"])
        if phrase is None:
            continue
        base = re.match(r"^\d+", row["section"])
        if not base:
            continue
        key = f"{row['short_name']} {base.group()}"
        entries.append((phrase, key, re.compile(rf"\b{re.escape(phrase)}\b")))

    # Longest first so "murder by life-convict" is preferred over "murder"
    # when the query is specific enough to say which one it means.
    entries.sort(key=lambda entry: len(entry[0]), reverse=True)
    return entries


def match_offences(text: str) -> list[str]:
    """
    Section keys whose First Schedule offence name appears in a passage.

    Used two ways. Retrieval asks it what section a classification question is
    about; the verifier asks it what section a classification *claim* is about,
    so a claim naming one offence cannot be cited to another. Those came apart
    in testing: an answer stated correctly that theft is non-bailable and cited
    BNS 304, which is snatching, and the classification check passed because
    snatching happens to carry the same attributes.
    """
    lowered = text.lower()
    matched: list[str] = []
    for _, key, matcher in _index():
        if matcher.search(lowered) and key not in matched:
            matched.append(key)
    return matched


def find_offences(query: str) -> list[str]:
    """
    The offence a classification question is asking about.

    Returns nothing unless the query is asking a classification question:
    injecting the offence table into every query would crowd the prompt with
    material nobody asked for. Returns nothing for a generic phrase that hits
    the whole table, since that is a search rather than a lookup.
    """
    if not is_classification_question(query):
        return []

    matched = match_offences(query)
    if len(matched) > MAX_MATCHES:
        logger.debug(f"offence lookup: {query!r} is too generic to resolve")
        return []
    if matched:
        logger.info(f"offence lookup resolved {query!r} to {matched}")
    return matched
