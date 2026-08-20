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
# A question about a named offence, whether or not it asks for the
# classification. "What is the punishment for theft?" ranks BNS 305 (theft in a
# dwelling house) and BNS 304 (snatching) above BNS 303, so the model was
# handed the wrong sections and cited them -- correctly rejected by the
# verifier, which turned a basic question into an abstention. The offence
# column names the section as exactly as a citation does, so it is looked up
# the same way.
_OFFENCE_QUESTION = re.compile(
    r"\b(punishment|punishable|sentence|penalty|imprisonment|fine|"
    r"what\s+(is|are|does)|which\s+section|defined?)\b",
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

# The Schedule writes many offences as "<name>, if <condition>" or
# "<name>, where <condition>". The head is the offence's actual name and the
# tail is the case it applies to, so a row too long to index whole may still
# have a usable name in front of the comma.
_QUALIFIER = re.compile(r"^(.{3,}?),\s*(?:if|where|when|in case|and\s+(?:if|where))\b", re.IGNORECASE)


def is_classification_question(query: str) -> bool:
    """Whether the query asks something the First Schedule answers."""
    return bool(_CLASSIFICATION_QUESTION.search(query or ""))


def is_offence_question(query: str) -> bool:
    """Whether the query asks about a named offence at all."""
    text = query or ""
    return bool(_CLASSIFICATION_QUESTION.search(text) or _OFFENCE_QUESTION.search(text))


def _phrase(offence: str) -> str | None:
    """
    The offence name as a searchable phrase, or ``None`` if unusable.

    A row too long to index whole is retried against its head, because the
    Schedule states many offences as "<name>, if <condition>". Dropping those
    rows outright left a hole a shorter offence name fell into: BNS 105 is
    "Culpable homicide not amounting to murder, if act by which the death is
    caused is done with the intention of causing death..." -- eighteen words, so
    it was never indexed, and the only phrase left matching a claim about it was
    the bare "murder" of BNS 103. The verifier then rejected a correctly cited
    claim on the grounds that the Schedule keys the offence to 103.

    Note the direction of that failure: a *true* statement removed from an
    answer. Cheaper than the reverse, but it is the same defect, and a system
    that refuses correct answers gets switched off.
    """
    text = _PUNCTUATION.sub("", offence.strip()).lower()
    if not text:
        return None
    # A conditional variant ("If offence be not committed") describes a case,
    # not an offence, and matches on stopwords.
    if text.startswith(("if ", "in any other case", "same offence", "any other")):
        return None
    if len(text.split()) > MAX_OFFENCE_PHRASE_WORDS:
        qualified = _QUALIFIER.match(text)
        if not qualified:
            return None
        head = qualified.group(1).strip()
        if len(head.split()) > MAX_OFFENCE_PHRASE_WORDS:
            return None
        return head
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

    A match nested inside a longer one is dropped. Offence names in the Schedule
    contain each other -- "murder" sits inside "culpable homicide not amounting
    to murder", "abetment of mutiny" inside itself -- so a passage naming the
    longer offence also matches the shorter, and the shorter one is not
    something the passage says. Sorting the index longest-first is not enough on
    its own: it fixes the *order* of the results while still returning both, and
    a caller that reads the list as "the offences this text is about" gets one
    the text never mentioned. Nesting is judged on the matched spans rather than
    on phrase length, because only overlapping spans are evidence that the two
    matches are the same words.
    """
    lowered = text.lower()
    spans: list[tuple[int, int, str]] = []
    for _, key, matcher in _index():
        for found in matcher.finditer(lowered):
            spans.append((found.start(), found.end(), key))

    matched: list[str] = []
    for start, end, key in spans:
        nested = any(
            (other_start, other_end) != (start, end)
            and other_start <= start
            and end <= other_end
            for other_start, other_end, _ in spans
        )
        if not nested and key not in matched:
            matched.append(key)
    return matched


def find_offences(query: str) -> list[str]:
    """
    The offence a classification question is asking about.

    Returns nothing unless the query is actually asking about an offence:
    injecting the offence table into every query would crowd the prompt with
    material nobody asked for. Returns nothing for a generic phrase that hits
    the whole table, since that is a search rather than a lookup.
    """
    if not is_offence_question(query):
        return []

    matched = match_offences(query)
    if len(matched) > MAX_MATCHES:
        logger.debug(f"offence lookup: {query!r} is too generic to resolve")
        return []
    if matched:
        logger.info(f"offence lookup resolved {query!r} to {matched}")
    return matched
