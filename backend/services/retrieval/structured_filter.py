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

A repealed code's number is **translated, not assumed**. "CrPC 438" means BNSS
482, and BNSS *also* has a section 438 about something else entirely, so for as
long as there was no concordance in this repository the number was refused
outright -- returning the same number in the new act would have turned a miss
into a confident wrong answer. ``data/processed/repealed_concordance.json`` now
supplies the mapping, built from the correspondence tables the Bureau of Police
Research and Development publishes and cross-checked against a second table
(see ``scripts/ingest_concordance.py``). A repealed citation the concordance
does not cover is still refused, on the original reasoning.

One repealed section often became several: IPC 376 is answered by BNS 64 and
BNS 65, and IPC 498A by BNS 85 and BNS 86. All of them are returned. Picking
one would be an editorial judgement about which the user meant, and the whole
point of an exact lookup is that it makes none.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

CONCORDANCE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "processed"
    / "repealed_concordance.json"
)

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


@lru_cache(maxsize=1)
def _concordance() -> dict[tuple[str, str], list[str]]:
    """``{(old act, old section): [new section, ...]}``, loaded once."""
    if not CONCORDANCE_PATH.exists():
        logger.warning(
            f"{CONCORDANCE_PATH} is missing; repealed citations will be refused "
            "rather than translated. Run scripts/ingest_concordance.py."
        )
        return {}

    mapping: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in json.loads(CONCORDANCE_PATH.read_text()):
        key = (row["old_act"].lower(), row["old_section"].upper())
        if row["new_section"] not in mapping[key]:
            mapping[key].append(row["new_section"])
    return dict(mapping)


# What each repealed act is called in the concordance file.
_CONCORDANCE_ACT = {
    BNS_COLLECTION: "ipc",
    BNSS_COLLECTION: "crpc",
    BSA_COLLECTION: "evidence act",
}


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

    replaces: tuple[str, ...] = field(default_factory=tuple)
    """For a repealed citation, the sections of the new act that answer it.
    More than one where the old provision was split across several."""

    @property
    def resolvable(self) -> bool:
        """
        Whether this citation may be looked up by section number.

        A current citation resolves to its own number. A repealed one resolves
        only through the concordance: the numbering did not carry over, and the
        new act usually has a section under the old number meaning something
        else, so a repealed citation the concordance does not cover is refused
        rather than guessed at.
        """
        if self.repealed:
            return bool(self.replaces)
        return not self.suffix

    @property
    def sections(self) -> tuple[str, ...]:
        """Every section to look up for this citation, in the new act."""
        if not self.resolvable:
            return ()
        return self.replaces if self.repealed else (self.section,)


def _build(match: re.Match[str], collection: str | None, act_name: str) -> Citation:
    repealed = act_name.lower() in REPEALED_ACT_NAMES
    suffix = (match.group("suffix") or "").upper()
    number = match.group("number")
    return Citation(
        section=number,
        collection=collection,
        act_name=act_name,
        repealed=repealed,
        suffix=suffix,
        # The suffix is part of the old number: IPC 498A is not IPC 498, and
        # they map to different sections of the BNS.
        replaces=_translate(collection, number + suffix) if repealed else (),
    )


def _translate(collection: str | None, old_section: str) -> tuple[str, ...]:
    """The new act's sections answering a repealed one, or empty if unknown."""
    act = _CONCORDANCE_ACT.get(collection or "")
    if act is None:
        return ()
    return tuple(_concordance().get((act, old_section.upper()), ()))


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
        collection = REPEALED_ACT_NAMES[repealed.group(1).lower()] if repealed else None
        suffix = (match.group("suffix") or "").upper()
        number = match.group("number")
        return Citation(
            section=number,
            collection=collection,
            act_name=repealed.group(1) if repealed else "",
            repealed=bool(repealed),
            suffix=suffix,
            replaces=_translate(collection, number + suffix) if repealed else (),
        )
    return None
