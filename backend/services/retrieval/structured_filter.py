"""
Resolve a citation in a query to an exact section, without the embedder.

Citation lookup is the worst-performing class in ``backend/eval/baseline.json``
by a wide margin -- recall@3 of 0.250, against 0.960 for plain questions. The
reason is not a tuning problem: a section number carries almost no semantic
signal. "482" and "483" embed to nearly the same point, and a section's text
rarely repeats its own number, so ``"section 482 BNSS"`` does not surface BNSS
482 anywhere in the top 20. Reranking cannot fix that, because the ranker works
from the same signal.

But a citation is not a search. "BNS 103" names one document, and the store
already holds it under an exact metadata key. This module parses the citation;
``VectorService.search`` looks it up and puts it first.

Deliberately **not** handled: translating a repealed code's section number.
"CrPC 438" means BNSS 482, but there is no verifiable concordance committed to
this repository, and BNSS *also* has a section 438, about something else
entirely. Returning it would turn a miss into a confident wrong answer.
Repealed citations therefore resolve their act and refuse their number, falling
through to vector search, where ``services.query_expansion`` still helps. See
``Citation.resolvable``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

BNS_COLLECTION = "bns_sections"
BNSS_COLLECTION = "bnss_sections"
BSA_COLLECTION = "bsa_sections"

# How each act can be named.
ACT_NAMES: dict[str, str] = {
    "bns": BNS_COLLECTION,
    "bnss": BNSS_COLLECTION,
    "bsa": BSA_COLLECTION,
    "bharatiya nyaya sanhita": BNS_COLLECTION,
    "bharatiya nagarik suraksha sanhita": BNSS_COLLECTION,
    "bharatiya sakshya adhiniyam": BSA_COLLECTION,
    "nyaya sanhita": BNS_COLLECTION,
    "nagarik suraksha sanhita": BNSS_COLLECTION,
    "sakshya adhiniyam": BSA_COLLECTION,
}

# The codes the 2023 acts replaced. Recognised so the act can be resolved and
# the section number explicitly refused -- see the module docstring.
REPEALED_ACT_NAMES: dict[str, str] = {
    "ipc": BNS_COLLECTION,
    "indian penal code": BNS_COLLECTION,
    "penal code": BNS_COLLECTION,
    "crpc": BNSS_COLLECTION,
    "cr.p.c": BNSS_COLLECTION,
    "code of criminal procedure": BNSS_COLLECTION,
    "criminal procedure code": BNSS_COLLECTION,
    "indian evidence act": BSA_COLLECTION,
    "evidence act": BSA_COLLECTION,
}

_ALL_ACTS = {**ACT_NAMES, **REPEALED_ACT_NAMES}
# Longest first, so "BNSS" is matched before "BNS", which is a prefix of it,
# and "indian evidence act" before "evidence act".
_ACT = "|".join(re.escape(name) for name in sorted(_ALL_ACTS, key=len, reverse=True))

# "103", "103(1)", "65B", "498A". The suffix and sub-clause are captured so
# they can be judged rather than silently discarded. The suffix must be set
# tight against the digits: with any space allowed, "section 111 of the
# Bharatiya Nyaya Sanhita" reads "of" as a suffix and refuses a citation that
# is perfectly good.
_NUMBER = (
    r"(?P<number>\d{1,3})(?P<suffix>[A-Za-z]{1,2})?\s*"
    r"(?P<clauses>(?:\(\s*\w{1,3}\s*\))*)"
)
_SECTION_WORD = r"(?:section|sections|sec|s)\.?"

# "BNS 103", "BNSS section 187", "IPC 302".
_ACT_THEN_NUMBER = re.compile(
    rf"\b(?P<act>{_ACT})\b[\s,]*(?:{_SECTION_WORD}\s*)?{_NUMBER}\b", re.IGNORECASE
)
# "section 482 BNSS", "section 111 of the Bharatiya Nyaya Sanhita".
_NUMBER_THEN_ACT = re.compile(
    rf"\b{_SECTION_WORD}\s*{_NUMBER}\b[\s,]*(?:of\s+)?(?:the\s+)?(?P<act>{_ACT})\b",
    re.IGNORECASE,
)
# "section 187" alone -- the act comes from the collection being searched.
_BARE_NUMBER = re.compile(rf"\b{_SECTION_WORD}\s*{_NUMBER}\b", re.IGNORECASE)
# Any mention of a repealed code anywhere in the query, however far from the
# number. "Indian Evidence Act dying declaration section 32" cites a repealed
# provision even though the two are twenty characters apart, and BSA 32 is not
# the dying-declaration section -- BSA 26 is.
_REPEALED_ACT = "|".join(
    re.escape(name) for name in sorted(REPEALED_ACT_NAMES, key=len, reverse=True)
)
_ANY_REPEALED = re.compile(rf"\b({_REPEALED_ACT})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Citation:
    """A statutory citation found in a query."""

    section: str
    """The base section number, as the corpus keys it: "103(1)" -> "103"."""

    collection: str | None
    """``None`` when the query said "section 187" without naming an act."""

    act_name: str
    """The words the query itself used, for logging and explanation."""

    repealed: bool
    """True when the act named is one of the pre-2023 codes."""

    suffix: str = ""
    """A letter suffix ("498A", "65B"). Only the repealed codes have these."""

    @property
    def resolvable(self) -> bool:
        """
        Whether this citation may be looked up by section number.

        A repealed code's numbering does not survive into its replacement, and
        the replacement usually has a section under the old number meaning
        something else, so refusing is the only safe answer without a
        concordance. A letter suffix is refused for the same reason: no section
        of the 2023 codes carries one, so a query that cites one is citing a
        repealed provision whether or not it named the old act.
        """
        return not self.repealed and not self.suffix


def _build(match: re.Match[str], collection: str | None, act_name: str) -> Citation:
    return Citation(
        section=match.group("number"),
        collection=collection,
        act_name=act_name,
        repealed=act_name.lower() in REPEALED_ACT_NAMES,
        suffix=(match.group("suffix") or "").upper(),
    )


def parse_citation(query: str) -> Citation | None:
    """
    Find a statutory citation in a query.

    Returns ``None`` when the query is not a citation lookup, which is the
    common case -- the caller then does an ordinary vector search. A query
    naming a section without an act yields a ``Citation`` with no collection,
    which the caller resolves against whichever collection it is searching.
    """
    if not query or not query.strip():
        return None

    for pattern in (_ACT_THEN_NUMBER, _NUMBER_THEN_ACT):
        match = pattern.search(query)
        if match:
            act_name = match.group("act")
            citation = _build(match, _ALL_ACTS[act_name.lower()], act_name)
            logger.debug(f"parsed {citation} from {query!r}")
            return citation

    match = _BARE_NUMBER.search(query)
    if match:
        repealed = _ANY_REPEALED.search(query)
        return Citation(
            section=match.group("number"),
            collection=REPEALED_ACT_NAMES[repealed.group(1).lower()] if repealed else None,
            act_name=repealed.group(1) if repealed else "",
            repealed=bool(repealed),
            suffix=(match.group("suffix") or "").upper(),
        )
    return None
