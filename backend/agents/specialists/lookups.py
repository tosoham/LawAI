"""
The two specialists that make no model call at all.

``offence`` reads the BNSS First Schedule; ``doctrine`` reads the curated graph.
Both answer from committed data under an exact key, so they are free, they are
the same on every run, and **they cannot hallucinate** -- there is no model in
either path to invent anything.

That is worth stating plainly because it inverts the usual instinct about
adding agents. Every model-backed specialist is a cost and a risk; these two
are neither, so a plan that includes them where they apply is strictly better
than one that does not, and the planner prompt says so. The most valuable
agents in this system are the ones that never call a model.

Neither spends retrieval budget. The budget bounds *corpus queries* because
those are what a runaway loop multiplies; a dictionary lookup is not that.
"""
from __future__ import annotations

import logging

from agents.contracts import AgentError, Evidence, PlanStep, SpecialistKind
from agents.specialists.base import (
    RetrievalBudget,
    SpecialistResult,
    register,
)
from services.legal_graph import get_legal_graph, parse_section_key
from services.procedural_timeline import for_section
from services.retrieval.offence_lookup import find_offences

logger = logging.getLogger(__name__)


@register(SpecialistKind.OFFENCE)
def run_offence(
    step: PlanStep, query: str, budget: RetrievalBudget
) -> SpecialistResult:
    """
    Whether a named offence is cognizable and bailable, which court tries it,
    and how long a person can be held.

    Uses ``find_offences`` -- the same exact matcher retrieval uses -- because
    classification vocabulary appears nowhere in the BNS. "Bailable",
    "cognizable" and "triable by" are First Schedule words, so a dense query
    built from them pulls towards whatever prose is nearest and the section
    carrying the answer sinks: BNS 103 ranks sixth for "is murder bailable".
    The Schedule names every offence in a column of its own, so this is a
    lookup and never a search.

    An unresolved classification is passed through **as unresolved**. 27 rows
    defer to another offence ("according as the offence abetted is cognizable
    or non-cognizable") and keep ``null`` with the Schedule's own wording
    beside it. A guessed "bailable" is the most dangerous value this system can
    emit, and it must not become one by passing through an agent.
    """
    text = f"{step.question} {query}".strip()
    keys = find_offences(text) or find_offences(query)
    if not keys:
        return SpecialistResult()

    graph = get_legal_graph()
    evidence: list[Evidence] = []
    errors: list[AgentError] = []

    for key in keys:
        parsed = parse_section_key(key)
        if parsed is None:
            logger.debug(f"offence specialist could not parse {key!r}")
            continue

        payload = for_section(*parsed, graph=graph)
        if payload is None:
            continue
        evidence.append(
            Evidence(
                specialist=SpecialistKind.OFFENCE,
                kind="classification",
                payload=payload,
                provenance="BNSS First Schedule, Part I",
            )
        )

    return SpecialistResult(evidence=evidence, errors=errors)


@register(SpecialistKind.DOCTRINE)
def run_doctrine(
    step: PlanStep, query: str, budget: RetrievalBudget
) -> SpecialistResult:
    """
    Curated doctrine bearing on the sections a query names, and its lineage.

    Reads ``data/curated/doctrines.json`` through the graph. That file carries
    **no precedential status** -- no ``overruled_by``, no ``still_good_law`` --
    because that is the highest-value and highest-harm claim in the domain and
    not something to freeze into a file that ages. Where authority genuinely
    splits, the doctrine is marked ``contested`` with both sides named and
    neither declared the winner, and this specialist passes that through
    untouched for the contested path to argue over.
    """
    graph = get_legal_graph()
    keys = _sections_named(f"{step.question} {query}")
    evidence: list[Evidence] = []

    for key in keys:
        doctrines = graph.doctrines_on(key)
        if not doctrines:
            continue
        evidence.append(
            Evidence(
                specialist=SpecialistKind.DOCTRINE,
                kind="doctrine",
                payload={
                    "section": key,
                    "doctrines": [
                        {
                            "id": doctrine.id,
                            "name": doctrine.name,
                            "summary": doctrine.summary,
                            "established_by": list(doctrine.established_by),
                            "refined_by": list(doctrine.refined_by),
                            "contested": doctrine.contested,
                            "contest_note": doctrine.contest_note,
                        }
                        for doctrine in doctrines
                    ],
                },
                provenance="data/curated/doctrines.json",
            )
        )

    return SpecialistResult(evidence=evidence)


def _sections_named(text: str) -> list[str]:
    """
    Section keys a passage cites, resolved the way retrieval resolves them.

    Reuses ``parse_citation`` rather than a new regex: it already knows that a
    repealed number must be translated and never assumed, and that a lettered
    section is refused because no section of the 2023 codes carries one.
    Writing a second citation parser here would be writing one that does not
    know those things.
    """
    from services.retrieval.structured_filter import parse_citation

    citation = parse_citation(text)
    if citation is None or not citation.resolvable or citation.collection is None:
        return []
    act = {"bns_sections": "BNS", "bnss_sections": "BNSS", "bsa_sections": "BSA"}.get(
        citation.collection
    )
    if act is None:
        return []
    return [f"{act} {number}" for number in citation.sections]
