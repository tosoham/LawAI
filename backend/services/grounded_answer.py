"""
Answer a legal question as typed claims, check them, and abstain if none stand.

The pipeline:

    citation pre-check -> retrieve -> expand over the graph -> synthesise
    claims -> verify -> regenerate once -> remove what failed -> metrics + trace

Two decisions here are worth stating plainly, because both replace something
that looked more obvious.

**Abstention falls out of verification; it is not a relevance threshold.** The
natural design is to score retrieval and refuse below some cutoff. That was
measured against the golden set and it does not work: the sixty-nine
answerable queries reach a best cosine distance of 0.577 at worst, and the six
adversarial ones -- tax evasion, GST thresholds, parole under the BNSS -- come
in as low as 0.423. The distributions overlap, so any cutoff either refuses
real questions or admits invented answers. What *does* separate them is
whether a single claim survives checking. "How many days of parole under the
BNSS" retrieves plausible-looking prison-adjacent sections and then cannot
ground one sentence against them, and an answer with nothing left in it is an
abstention. So the gate is the verifier, and the threshold is one.

**One pre-check runs before any generation**: a cited section that does not
exist. "What does section 999 of the Bharatiya Nyaya Sanhita provide" is
answerable with certainty -- the BNS has 358 sections -- and there is no reason
to spend a model call discovering that, nor any reason to let a model see the
question and try.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from models.claims import ClaimVerdict, StructuredAnswer

from .answer_metrics import AnswerMetrics, compute
from .claim_verifier import VerificationContext, regeneration_feedback, verify
from .legal_graph import GraphContext, get_legal_graph, section_key
from .llm_service import llm_service
from .rag_service import RAGService, with_disclaimer
from .retrieval.structured_filter import parse_citation
from .vector_service import get_vector_service

logger = logging.getLogger(__name__)

# Models wrap JSON in a fence more often than not, whatever the prompt says.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
# Enough headroom for a structured answer; the default cap truncates one
# mid-object and loses the whole thing to a parse error.
SYNTHESIS_MAX_TOKENS = 2048
# One. A second attempt that still fails is a model that cannot ground the
# claim, and a third would only produce a more confident version of it.
MAX_REGENERATIONS = 1

ABSTENTION_NOTHING_RETRIEVED = (
    "I could not find anything in the corpus bearing on this question. The corpus "
    "covers the Bharatiya Nyaya Sanhita, the Bharatiya Nagarik Suraksha Sanhita, "
    "the Bharatiya Sakshya Adhiniyam and a set of Supreme Court judgements, and "
    "nothing else."
)
ABSTENTION_NOTHING_VERIFIED = (
    "I could not support any part of an answer to this question against the "
    "corpus. Rather than give you an answer I cannot stand behind, I am telling "
    "you that."
)


@dataclass
class GroundedAnswer:
    """A verified answer, and everything needed to defend it afterwards."""

    query: str
    answer: str
    structured: StructuredAnswer
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    metrics: AnswerMetrics = field(default_factory=AnswerMetrics)
    sources: list[dict[str, Any]] = field(default_factory=list)
    graph_context: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def abstained(self) -> bool:
        return self.structured.abstained


def _strip_fence(text: str) -> str:
    match = _FENCE.match(text or "")
    return match.group(1) if match else (text or "").strip()


def _extract_json(body: str) -> str | None:
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


def parse_synthesis(raw: str) -> StructuredAnswer:
    """
    Parse the model's structured output.

    A malformed response yields an empty answer rather than an exception: the
    caller then abstains, which is the correct outcome for a turn that produced
    nothing checkable. Raising here would turn a bad generation into a 500.
    """
    body = _strip_fence(raw)
    payload = None
    for candidate in (body, _extract_json(body)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue

    if payload is None:
        logger.warning(f"synthesis did not return JSON: {body[:300]!r}")
        return StructuredAnswer()

    if isinstance(payload, list):
        payload = {"claims": payload}
    try:
        return StructuredAnswer.model_validate(payload)
    except ValidationError as error:
        logger.warning(f"synthesis JSON did not match the claim schema: {error}")
        return StructuredAnswer()


SYNTHESIS_SYSTEM = """You are a legal analyst working on Indian criminal law under \
the 2023 codes: the Bharatiya Nyaya Sanhita (BNS, offences), the Bharatiya Nagarik \
Suraksha Sanhita (BNSS, procedure) and the Bharatiya Sakshya Adhiniyam (BSA, \
evidence). These replaced the Indian Penal Code, the Code of Criminal Procedure and \
the Indian Evidence Act. Never expand BNSS as "Bharatiya Nyaya Sanhita"; they are \
different statutes with different numbering.

You do not write prose. You emit a list of claims as JSON, each labelled with what \
kind of thing it is, and each of those labels is checked mechanically after you \
answer. A claim that does not check out is deleted from the answer, so an unfounded \
claim does not make your answer fuller -- it makes it shorter."""

SYNTHESIS_INSTRUCTIONS = """Return JSON of exactly this shape and nothing else:

{"claims": [
  {"text": "...", "epistemic_class": "...", "sources": ["..."],
   "verbatim_span": "...", "positions": []}
]}

epistemic_class is one of:

  "statute"         Enacted text. sources must name the section as "BNS 103" or
                    "BNSS 482". If you are quoting, put the exact words from the
                    context in verbatim_span -- they are compared character for
                    character against the section. If you are paraphrasing, leave
                    verbatim_span out. Do not approximate a quotation.
  "classification"  Whether an offence is cognizable, bailable, and which court
                    tries it. Only from the OFFENCE CLASSIFICATION block, which is
                    checked against the First Schedule. Never infer these. sources
                    must be the section that block names, which is the section
                    that *punishes* the offence -- BNS 103 for murder, not BNS
                    101, which defines it.
  "holding"         What a named case decided. sources must include the judgement
                    id exactly as given, and the section it bears on. A case cited
                    for a section it does not concern is rejected.
  "interpretation"  A settled judicial reading. Same requirement: name the case.
  "contested"       A question the authorities answer differently. positions must
                    hold at least two entries, each {"summary": "...",
                    "authority": ["judgement id"]}. One position is not a
                    contested claim, it is a one-sided answer with a warning on
                    it, and it is rejected.
  "inference"       You applying the law to the facts given. Legitimate and often
                    the most useful part of an answer. It may cite nothing, but it
                    must not read like a provision: if you refer to a section by
                    number, cite it in sources.

Rules:
- Cite the act each provision appears under in the LEGAL CONTEXT. The context can
  hold sections of more than one act, and they number independently: BNS 103 and
  BNSS 103 are unrelated provisions.
- Answer the question that was asked. Do not work through every entry in the
  context or the connected material; include only what bears on the question.
- Every claim stands on its own. Do not split one thought across two claims or
  merge a statement of law with a conclusion drawn from it.
- Say only what the context supports. Where the context gives you a case name and
  a one-line subject and not the judgement text, you may say the case bears on the
  provision; you may not say what it held.
- If the context does not support an answer, return {"claims": []}. That is a
  complete and correct response, not a failure.
- No disclaimer. One is appended for you."""


class GroundedAnswerService:
    """Composes retrieval, the graph, synthesis and verification."""

    def __init__(self) -> None:
        self.vector_service = get_vector_service()
        self.llm_service = llm_service
        self.rag = RAGService.__new__(RAGService)  # formatting helpers only
        self.rag.vector_service = self.vector_service
        self.rag.llm_service = self.llm_service

    # -- pre-checks --------------------------------------------------------

    def check_citation(self, query: str) -> str | None:
        """
        Refuse a citation to a section that does not exist, before generating.

        Certain, cheap and worth doing first: the BNS has 358 sections, so
        "section 999" has an answer that needs no model and no retrieval. A
        repealed citation is *not* refused here -- "CrPC 438" names a real
        provision whose replacement the corpus does hold, and the question is
        answerable even though the number is not resolvable.
        """
        citation = parse_citation(query)
        if citation is None or not citation.resolvable or citation.collection is None:
            return None

        act = {"bns_sections": "BNS", "bnss_sections": "BNSS", "bsa_sections": "BSA"}[
            citation.collection
        ]
        key = section_key(act, citation.section)
        graph = get_legal_graph()
        if graph.has_section(key):
            return None

        highest = max(
            (
                int(node.section)
                for node in graph.sections.values()
                if node.act == act and node.section.isdigit()
            ),
            default=0,
        )
        return (
            f"There is no section {citation.section} of the {act}. It runs to "
            f"section {highest}. I have not tried to answer the question, because "
            "the provision it asks about does not exist."
        )

    # -- the pipeline ------------------------------------------------------

    def _synthesis_prompt(
        self, query: str, context: str, graph_context: str, feedback: str = ""
    ) -> str:
        connected = f"\n\nCONNECTED MATERIAL:\n{graph_context}" if graph_context else ""
        correction = (
            f"\n\nYOUR PREVIOUS ATTEMPT FAILED VERIFICATION:\n{feedback}"
            if feedback
            else ""
        )
        return (
            f"LEGAL CONTEXT:\n{context}{connected}\n\n"
            f"QUESTION:\n{query}{correction}\n\n"
            f"{SYNTHESIS_INSTRUCTIONS}"
        )

    def _synthesise(self, prompt: str) -> StructuredAnswer:
        raw = self.llm_service.generate(
            prompt=prompt, system=SYNTHESIS_SYSTEM, max_tokens=SYNTHESIS_MAX_TOKENS
        )
        return parse_synthesis(raw)

    def _retrieve(self, query: str, collections: list[str], top_k: int) -> dict[str, Any]:
        """
        Retrieve from one or several collections, ranked together.

        Merged by distance, which puts exact citation hits first for free --
        they carry a distance of zero. Searching several is what the agent
        needs, since it does not know in advance whether a question is about
        offences, procedure or evidence.
        """
        merged: dict[str, list[Any]] = {
            "ids": [], "documents": [], "metadatas": [], "distances": []
        }
        for name in collections:
            results = self.vector_service.search(
                collection_name=name, query=query, top_k=top_k
            )
            for key in merged:
                merged[key].extend(results.get(key, []))

        order = sorted(range(len(merged["ids"])), key=lambda i: merged["distances"][i])[:top_k]
        return {key: [values[i] for i in order] for key, values in merged.items()}

    def answer(
        self,
        query: str,
        collection: str | list[str] = "bns_sections",
        top_k: int = 5,
    ) -> GroundedAnswer:
        """Answer one question, or say honestly that it cannot be answered."""
        collections = [collection] if isinstance(collection, str) else list(collection)
        trace: dict[str, Any] = {"query": query, "collections": collections, "steps": []}

        refusal = self.check_citation(query)
        if refusal:
            trace["steps"].append({"step": "citation_precheck", "outcome": "refused"})
            return self._abstain(query, refusal, trace)

        search_results = self._retrieve(query, collections, top_k)
        trace["steps"].append({
            "step": "retrieve",
            "ids": list(search_results.get("ids", [])),
            "distances": [round(d, 4) for d in search_results.get("distances", [])],
        })
        if not search_results.get("documents"):
            return self._abstain(query, ABSTENTION_NOTHING_RETRIEVED, trace)

        # The query is passed, not just the results: a classification question
        # is answered from the offence table, which is reached by name rather
        # than by what retrieval happened to return.
        graph = self.rag._expand_over_graph(search_results, query)
        trace["steps"].append({"step": "graph_expansion", **_graph_trace(graph)})

        context = self.rag._format_context(search_results)
        graph_context = self.rag._format_graph_context(graph)
        verification_context = VerificationContext.from_retrieval(search_results)

        feedback = ""
        answer = StructuredAnswer()
        verdicts: list[ClaimVerdict] = []
        for attempt in range(MAX_REGENERATIONS + 1):
            answer = self._synthesise(
                self._synthesis_prompt(query, context, graph_context, feedback)
            )
            answer, verdicts = verify(answer, verification_context)
            trace["steps"].append({
                "step": "synthesis",
                "attempt": attempt + 1,
                "claims": len(answer.claims),
                "failed": sum(1 for v in verdicts if not v.verified),
            })
            feedback = regeneration_feedback(answer, verdicts)
            if not feedback:
                break

        # Metrics are computed over what synthesis asserted, not over what
        # survived: verification rewrote the failures to `unsupported`, and
        # scoring that would delete every failure from the record.
        emitted = StructuredAnswer(
            claims=[
                claim.model_copy(update={"epistemic_class": verdict.original_class})
                for claim, verdict in zip(answer.claims, verdicts, strict=True)
            ]
        )
        metrics = compute(emitted, verdicts)
        surviving = answer.without_unsupported()

        trace["steps"].append({
            "step": "verify",
            "verdicts": [v.model_dump() for v in verdicts],
        })
        trace["metrics"] = metrics.to_dict()

        if surviving.is_empty:
            # Not a failure to answer -- an answer of "I cannot ground this",
            # which is the honest one and the whole reason for the machinery.
            return self._abstain(
                query, ABSTENTION_NOTHING_VERIFIED, trace, metrics=metrics,
                verdicts=verdicts,
            )

        removed = sum(1 for v in verdicts if not v.verified)
        prose = surviving.render()
        if removed:
            prose += (
                f"\n\n_{removed} statement(s) were removed from this answer because "
                "they could not be supported against the corpus._"
            )

        return GroundedAnswer(
            query=query,
            answer=with_disclaimer(prose),
            structured=surviving,
            verdicts=verdicts,
            metrics=metrics,
            sources=self.rag._format_sources(search_results),
            graph_context=_graph_payload(graph),
            trace=trace,
        )

    def _abstain(
        self,
        query: str,
        reason: str,
        trace: dict[str, Any],
        metrics: AnswerMetrics | None = None,
        verdicts: list[ClaimVerdict] | None = None,
    ) -> GroundedAnswer:
        structured = StructuredAnswer(abstained=True, abstention_reason=reason)
        trace["abstained"] = reason
        resolved = metrics or AnswerMetrics(abstained=True)
        resolved.abstained = True
        return GroundedAnswer(
            query=query,
            answer=with_disclaimer(reason),
            structured=structured,
            verdicts=verdicts or [],
            metrics=resolved,
            trace=trace,
        )


def _graph_trace(graph: GraphContext) -> dict[str, Any]:
    return {
        "seeds": list(graph.seeds),
        "related_sections": [s.key for s in graph.related_sections],
        "judgements": [j.id for j in graph.judgements],
        "doctrines": [d.id for d in graph.doctrines],
        "contested": [d.id for d in graph.contested],
    }


def _graph_payload(graph: GraphContext) -> dict[str, Any]:
    return {
        "seeds": list(graph.seeds),
        "related_sections": [
            {"key": s.key, "act": s.act, "section": s.section, "title": s.title}
            for s in graph.related_sections
        ],
        "judgements": [
            {
                "id": j.id,
                "case_name": j.case_name,
                "citation": j.citation,
                "year": j.year,
                "subject": j.subject,
                "source_url": j.source_url,
            }
            for j in graph.judgements
        ],
        "doctrines": [
            {
                "id": d.id,
                "name": d.name,
                "summary": d.summary,
                "contested": d.contested,
                "contest_note": d.contest_note,
            }
            for d in graph.doctrines
        ],
        "classification": list(graph.classification),
    }


_service: GroundedAnswerService | None = None


def get_grounded_answer_service() -> GroundedAnswerService:
    global _service
    if _service is None:
        _service = GroundedAnswerService()
    return _service
