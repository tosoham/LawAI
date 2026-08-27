"""
Decide how much machinery a question deserves, before spending any of it.

**Escalation must be rare, and the default must be cheap.** A fanned-out query
costs the planner call plus one per model-backed specialist plus synthesis --
roughly eight model calls against the single-pass path's one. If triage
escalates freely, every "punishment for murder" costs eight times what it did,
for an answer the one-pass path already gets right: retrieval sits at recall@3
1.000 over the golden set and the grounded pipeline verifies every claim it
emits. So this module's job is mostly to say *no*.

It is keyword and lookup driven, with no model call of its own, for the same
reason ``intent_classifier`` is: a triage step that costs a model call has
already spent a meaningful fraction of what escalating would cost, so it cannot
pay for itself on the queries it declines.

Three signals escalate, in descending order of confidence:

* **the user asked** -- "show me both sides", "is this settled" -- which is the
  only signal that is never wrong about intent;
* **a curated contested section is cited**, read from
  ``graph.contested_sections()``. That method has existed since the graph was
  built, its docstring says "this is the list the contested path consults", and
  until now nothing consulted it;
* **constitutional subject matter**, which is contested by nature -- a single
  confident answer to "is the twin-condition bail bar constitutional" is itself
  the error.

Detection failures are the risk worth naming: **a user who does not know a
question is contested will not think to ask.** That is why the curated list
matters as much as the vocabulary, and why `data/curated/doctrines.json` is
where a newly discovered split gets recorded.
"""
from __future__ import annotations

import logging
import re

from agents.contracts import Complexity
from services.legal_graph import get_legal_graph
from services.retrieval.structured_filter import parse_citation

logger = logging.getLogger(__name__)

# The user asking outright. Never wrong about intent, so it wins over
# everything below.
_ASKED_FOR_BOTH_SIDES = re.compile(
    r"\b(both sides|either side|two views|competing|opposing|"
    r"conflicting|disagree(ment)?s?|split|unsettled|settled law|"
    # "is the law on X settled" is the same question as "is this settled",
    # asked at length, and it is exactly the question that deserves both sides.
    r"\bis\b[^?]{0,40}\bsettled\b|arguments? (for and against|on both)|"
    r"contrast|weigh(ing)? up)\b",
    re.IGNORECASE,
)

# A constitutional *challenge*, not constitutional vocabulary.
#
# The first version escalated on any mention of "fundamental right", and it
# caught "privacy is a fundamental right" -- which is settled law, decided
# unanimously by nine judges in Puttaswamy. Asking what a case held is not
# asking whether a provision survives scrutiny, and paying eight model calls to
# be told both sides of a question with one side is pure cost.
#
# So what escalates is the shape of a validity question: something being
# challenged, read down, struck down, or tested against the Constitution.
_CONSTITUTIONAL = re.compile(
    r"\b(unconstitutional|constitutionality|ultra vires|"
    r"violat(es?|ive|ing) (the )?(article|constitution|fundamental)|"
    r"(is|are) .{0,40}\bconstitutional\b|"
    r"read(ing)? down|struck down|strike down|"
    r"challenge[ds]? (the |its )?(validity|constitutionality)|"
    r"basic structure)\b",
    re.IGNORECASE,
)

# More than one thing being asked. Worth gathering in parallel; not contested.
_MULTI_PART = re.compile(
    r"\b(and also|as well as|in addition|furthermore|"
    r"compare|difference between|versus|\bvs\.?\b|"
    r"what about|how does .+ (differ|compare))\b",
    re.IGNORECASE,
)

# A question spanning statute *and* case law, which is what the fan-out is for.
_STATUTE_WORDS = re.compile(
    r"\b(section|sanhita|adhiniyam|bns|bnss|bsa|provision|statute)\b", re.IGNORECASE
)
_CASE_WORDS = re.compile(
    r"\b(case ?law|judgement|judgment|held|ruling|precedent|"
    r"supreme court|high court|bench|authority)\b",
    re.IGNORECASE,
)


def _cited_sections(query: str) -> list[str]:
    """Section keys the query cites, as the graph keys them."""
    citation = parse_citation(query)
    if citation is None or not citation.resolvable or citation.collection is None:
        return []
    act = {"bns_sections": "BNS", "bnss_sections": "BNSS", "bsa_sections": "BSA"}.get(
        citation.collection
    )
    if act is None:
        return []
    return [f"{act} {number}" for number in citation.sections]


def touches_contested_section(query: str) -> list[str]:
    """
    Curated contested sections the query cites.

    The list is hand-curated in ``data/curated/doctrines.json`` and deliberately
    carries no precedential status -- it records *that* authority splits and
    names both sides, never which side won.
    """
    try:
        contested = get_legal_graph().contested_sections()
    except Exception as error:  # pragma: no cover - graph build is tested elsewhere
        logger.warning(f"could not read contested sections ({error}); not escalating")
        return []
    return [key for key in _cited_sections(query) if key in contested]


def triage(query: str) -> tuple[Complexity, str]:
    """
    How much machinery this query deserves, and why.

    Returns the complexity and a one-line reason, which goes into the trace so
    an escalation can be argued with after the fact rather than being a silent
    cost.
    """
    text = query or ""

    if _ASKED_FOR_BOTH_SIDES.search(text):
        return Complexity.CONTESTED, "the question asks for both sides"

    contested = touches_contested_section(text)
    if contested:
        return (
            Complexity.CONTESTED,
            f"{', '.join(contested)} is marked contested in the curated doctrines",
        )

    if _CONSTITUTIONAL.search(text):
        return Complexity.CONTESTED, "constitutional subject matter"

    if _MULTI_PART.search(text):
        return Complexity.COMPLEX, "more than one thing is being asked"

    if _STATUTE_WORDS.search(text) and _CASE_WORDS.search(text):
        return Complexity.COMPLEX, "spans statute and case law"

    return Complexity.SIMPLE, "answerable in one pass"
