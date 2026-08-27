"""
The specialists that query the corpus, and may query it again.

``statute`` searches the three statute collections; ``case_law`` searches the
judgements. Both go through ``VectorService.search``, which means both get the
whole retrieval stack as it stands -- structured citation lookup, query
expansion, BM25 fused by reciprocal rank fusion, cross-encoder reranking -- and
neither reimplements any of it. A specialist that retrieved differently from
the single-pass path would make the two answer differently for reasons nobody
could see, and ``eval_retrieval.py`` would stop describing what users get.

**The follow-up query is the point of these being agents.** One pass returns
what the question asked for; reading it often shows what the question should
have asked. "Grounds for anticipatory bail" retrieves BNSS 482, whose text
names conditions the court may impose and cross-references other provisions --
and which of those matter is not knowable until 482 is in hand. So after the
first retrieval the specialist may ask for more, and what it asks for is chosen
by a model from what came back.

Three properties keep that from becoming a runaway:

* **the budget is spent, not consulted.** Every query decrements it, including
  the first, so the cap counts total corpus queries rather than follow-ups;
* **a follow-up that names nothing new ends the loop.** A model asked what else
  it needs will always find something to ask for, so an empty or duplicate
  answer is treated as "done" rather than retried;
* **running out of budget is not an error.** The specialist returns what it
  has, exactly as one that failed returns what it had.
"""
from __future__ import annotations

import logging

from agents.contracts import Evidence, PlanStep, SpecialistKind
from agents.specialists.base import (
    RetrievalBudget,
    SpecialistResult,
    register,
)
from services.llm_service import llm_service
from services.model_json import load_json_payload
from services.vector_service import get_vector_service

logger = logging.getLogger(__name__)

STATUTE_COLLECTIONS = ("bns_sections", "bnss_sections", "bsa_sections")
JUDGEMENT_COLLECTION = "sc_judgements"

#: Chunks per collection per query. Matches the single-pass default, so a
#: specialist sees what the one-pass path would have seen.
TOP_K = 5

#: Short: it names follow-up queries, nothing else.
FOLLOW_UP_MAX_TOKENS = 250

FOLLOW_UP_SYSTEM = """You are deciding whether one more corpus lookup would help \
answer a question about Indian criminal law under the 2023 codes.

You are not answering the question and you are not summarising what you have \
been given. You name further searches, or you say there are none."""

FOLLOW_UP_INSTRUCTIONS = """Below is a question and what a first search returned.

Name up to two further searches that would fill a real gap -- a provision the \
retrieved text cross-references and depends on, a term of art it uses without \
defining, the case that read it down.

Return JSON of exactly this shape and nothing else:

{"queries": ["...", "..."]}

Return {"queries": []} if the material already covers the question. That is the \
common answer and a complete one. Do not invent a gap to fill: a search that \
finds nothing costs the same as one that finds something, but a search that \
pulls in unrelated provisions crowds out what was asked for."""


def _search(collections, query: str, budget: RetrievalBudget):
    """One corpus query across the given collections, if the budget allows."""
    if not budget.spend():
        return None, 0
    service = get_vector_service()
    merged: list[Evidence] = []
    for name in collections:
        try:
            results = service.search(name, query, top_k=TOP_K)
        except Exception as error:
            logger.warning(f"search of {name} failed: {error}")
            continue
        if not results.get("documents"):
            continue
        merged.append(
            Evidence(
                specialist=(
                    SpecialistKind.CASE_LAW
                    if name == JUDGEMENT_COLLECTION
                    else SpecialistKind.STATUTE
                ),
                kind="judgements" if name == JUDGEMENT_COLLECTION else "sections",
                payload={
                    "query": query,
                    "documents": results["documents"],
                    "metadatas": results["metadatas"],
                    "distances": results.get("distances", []),
                },
                provenance=name,
            )
        )
    return merged, 1


def _seen_keys(evidence: list[Evidence]) -> set[str]:
    """What has already been retrieved, so a follow-up can be judged new."""
    keys: set[str] = set()
    for item in evidence:
        for metadata in item.payload.get("metadatas", []):
            key = metadata.get("parent_id") or metadata.get("section_number")
            if key:
                keys.add(str(key))
    return keys


def _follow_up_queries(
    question: str, evidence: list[Evidence], service
) -> list[str]:
    """
    What else to look for, chosen from what came back.

    Returns an empty list on any failure, which ends the loop. A follow-up step
    that cannot decide has decided: the specialist keeps what it has rather
    than the query failing over an optional refinement.
    """
    summary_lines: list[str] = []
    for item in evidence:
        for metadata in item.payload.get("metadatas", [])[:TOP_K]:
            label = metadata.get("short_name") or metadata.get("case_name") or "?"
            number = metadata.get("section_number") or metadata.get("year") or ""
            title = metadata.get("title") or metadata.get("subject") or ""
            summary_lines.append(f"- {label} {number} {title}".rstrip())
    if not summary_lines:
        return []

    prompt = (
        f"{FOLLOW_UP_INSTRUCTIONS}\n\nQUESTION:\n{question}\n\n"
        f"ALREADY RETRIEVED:\n" + "\n".join(sorted(set(summary_lines))[:20])
    )
    try:
        raw = service.generate(
            prompt=prompt,
            system=FOLLOW_UP_SYSTEM,
            max_tokens=FOLLOW_UP_MAX_TOKENS,
            temperature=0.0,
        )
    except Exception as error:
        logger.warning(f"follow-up planning failed ({error}); keeping what we have")
        return []

    payload = load_json_payload(raw)
    if isinstance(payload, list):
        payload = {"queries": payload}
    if not isinstance(payload, dict):
        return []
    queries = payload.get("queries")
    if not isinstance(queries, list):
        return []
    return [q.strip() for q in queries if isinstance(q, str) and q.strip()][:2]


def _run(
    collections,
    step: PlanStep,
    query: str,
    budget: RetrievalBudget,
    service=None,
) -> SpecialistResult:
    service = service or llm_service
    question = step.question or query

    evidence, spent = _search(collections, question, budget)
    if evidence is None:
        # Budget already exhausted before this specialist started, which happens
        # when several share one. Not an error; there is simply nothing to add.
        return SpecialistResult()

    result = SpecialistResult(evidence=list(evidence), retrievals=spent)
    if not result.evidence or budget.exhausted:
        return result

    follow_ups = _follow_up_queries(question, result.evidence, service)
    result.model_calls += 1
    if not follow_ups:
        return result

    seen = _seen_keys(result.evidence)
    for follow_up in follow_ups:
        if budget.exhausted:
            break
        more, spent = _search(collections, follow_up, budget)
        result.retrievals += spent
        if not more:
            continue
        # A follow-up that returns only what we already had is the loop telling
        # us it is finished. Keeping it would inflate the context with repeats
        # and make the retrieval count look like work.
        if _seen_keys(more) <= seen:
            logger.debug(f"follow-up {follow_up!r} returned nothing new; stopping")
            break
        seen |= _seen_keys(more)
        result.evidence.extend(more)

    return result


@register(SpecialistKind.STATUTE)
def run_statute(
    step: PlanStep, query: str, budget: RetrievalBudget, service=None
) -> SpecialistResult:
    """Provisions of the BNS, BNSS and BSA bearing on the question."""
    return _run(STATUTE_COLLECTIONS, step, query, budget, service)


@register(SpecialistKind.CASE_LAW)
def run_case_law(
    step: PlanStep, query: str, budget: RetrievalBudget, service=None
) -> SpecialistResult:
    """
    Judgements in the corpus bearing on the question.

    Returns the retrieved text and nothing about what any case *held*. The
    corpus records which sections a judgement is an authority on for only 27 of
    300 judgements, and that relation cannot be derived from the text -- see
    ``docs/ATTRIBUTION_GAP.md``. A specialist that summarised holdings would be
    asserting exactly what the system cannot check.
    """
    return _run((JUDGEMENT_COLLECTION,), step, query, budget, service)
