"""
Query expansion for corpus retrieval.

Retrieval is embedding-only, and `all-MiniLM-L6-v2` is a general-purpose model
with no Indian-law training. That combination fails on a specific, predictable
class of query: a **term of art that does not appear in the statute it names**.

The worked example is anticipatory bail. BNSS 482 governs it, but the section is
titled "Direction for grant of bail to person apprehending arrest" and the word
"anticipatory" appears nowhere in its 1,948 characters. Searching the phrase
therefore ranks BNSS 480 and 483 above the section that actually applies.

Note this is *not* fixed by adding BM25 or any other lexical retriever — the
term is absent from the text, so there is nothing to match lexically. It is a
vocabulary problem, and the fix is a vocabulary layer.

The second class is repealed-code names. Practitioners have decades of muscle
memory for "IPC", "CrPC" and "Evidence Act", none of which appear anywhere in
the post-2023 corpus.

Expansion is **additive**: the statutory phrasing is appended to the query used
for embedding, never substituted. A query that already worked cannot be made
worse, and the prompt sent to the model still carries the user's own wording.
"""
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Terms of art mapped to the language the statute actually uses.
#
# Curated deliberately rather than generated: a wrong entry here silently
# misdirects retrieval, which is worse than the gap it closes. Each entry is a
# phrase whose statutory wording genuinely differs — not a general thesaurus.
LEGAL_ALIASES: dict[str, str] = {
    # --- bail -------------------------------------------------------------
    "anticipatory bail": "direction for grant of bail to person apprehending arrest",
    "pre-arrest bail": "direction for grant of bail to person apprehending arrest",
    "transit bail": "direction for grant of bail to person apprehending arrest",
    "default bail": (
        "release on bail on failure to complete investigation within the "
        "prescribed period of detention"
    ),
    "statutory bail": (
        "release on bail on failure to complete investigation within the "
        "prescribed period of detention"
    ),
    "interim bail": "release on bail pending disposal of the application",
    # --- procedure --------------------------------------------------------
    "fir": "information in cognizable cases first information report",
    "zero fir": (
        "first information report recorded irrespective of the area where the "
        "offence is committed"
    ),
    "double jeopardy": "person once convicted or acquitted not to be tried for same offence",
    "autrefois acquit": "person once convicted or acquitted not to be tried for same offence",
    "plea bargaining": "application for plea bargaining mutually satisfactory disposition",
    "compoundable offence": "compounding of offences",
    "quashing": "power of High Court to prevent abuse of process",
    "police custody": "detention of accused person in custody by police",
    "judicial custody": "remand of accused person to custody by Magistrate",
    "test identification parade": "identification of person arrested",
    "cognizance": "taking cognizance of offences by Magistrate",
    # --- evidence ---------------------------------------------------------
    "dying declaration": (
        "statement by person who cannot be called as witness as to cause of death"
    ),
    "hostile witness": "cross-examination of own witness by the party calling him",
    "res gestae": "facts forming part of same transaction relevancy",
    "electronic evidence": "electronic or digital record admissibility",
    "digital evidence": "electronic or digital record admissibility",
    "expert opinion": "opinion of experts when relevant",
    "burden of proof": "on whom burden of proof lies",
    # --- offences ---------------------------------------------------------
    "culpable homicide not amounting to murder": "punishment for culpable homicide not amounting to murder",
    "dowry death": "dowry death punishment",
    "cheating": "cheating and dishonestly inducing delivery of property",
    "criminal breach of trust": "punishment for criminal breach of trust",
    "organised crime": "organised crime syndicate continuing unlawful activity",
    "mob lynching": (
        "murder by group of five or more persons on ground of race caste community"
    ),
    "hit and run": "causing death by negligence rash driving escaping without reporting",
}

# Repealed codes and their replacements. Practitioners still search by the old
# names, which appear nowhere in the corpus.
REPEALED_CODES: dict[str, str] = {
    "ipc": "Bharatiya Nyaya Sanhita",
    "indian penal code": "Bharatiya Nyaya Sanhita",
    "crpc": "Bharatiya Nagarik Suraksha Sanhita",
    "cr.p.c": "Bharatiya Nagarik Suraksha Sanhita",
    "code of criminal procedure": "Bharatiya Nagarik Suraksha Sanhita",
    "evidence act": "Bharatiya Sakshya Adhiniyam",
    "indian evidence act": "Bharatiya Sakshya Adhiniyam",
}

# Longest phrases first, so "culpable homicide not amounting to murder" is
# matched before any shorter phrase nested inside it.
_ALIAS_ORDER = sorted(LEGAL_ALIASES, key=len, reverse=True)
_CODE_ORDER = sorted(REPEALED_CODES, key=len, reverse=True)


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    r"""
    Build a word-boundary pattern for a phrase.

    `re.escape` handles the dots in "cr.p.c"; \b at each end stops "fir" from
    matching inside "first" or "confirm", which would otherwise fire on almost
    every query.
    """
    return re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)


_ALIAS_PATTERNS = [(_phrase_pattern(p), LEGAL_ALIASES[p]) for p in _ALIAS_ORDER]
_CODE_PATTERNS = [(_phrase_pattern(p), REPEALED_CODES[p]) for p in _CODE_ORDER]


def expand_query(query: str) -> str:
    """
    Append statutory phrasing for any recognised term of art or repealed code.

    Args:
        query: The user's query, verbatim.

    Returns:
        The query with expansions appended. Returns the input unchanged when
        nothing matches, which is the common case.
    """
    if not query or not query.strip():
        return query

    additions: list[str] = []
    seen: set[str] = set()

    for pattern, expansion in _ALIAS_PATTERNS + _CODE_PATTERNS:
        if pattern.search(query) and expansion.lower() not in seen:
            # Skip an expansion whose wording the query already carries --
            # repeating it would just skew the embedding.
            if expansion.lower() in query.lower():
                continue
            additions.append(expansion)
            seen.add(expansion.lower())

    if not additions:
        return query

    expanded = f"{query} {' '.join(additions)}"
    logger.debug(f"Expanded query: {query!r} -> {expanded!r}")
    return expanded


def expansion_report(query: str) -> dict[str, Any]:
    """Explain what expansion did, for diagnostics and tests."""
    expanded = expand_query(query)
    return {
        "original": query,
        "expanded": expanded,
        "changed": expanded != query,
    }
