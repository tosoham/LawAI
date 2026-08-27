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

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from models.claims import Claim, ClaimVerdict, StructuredAnswer

from .answer_metrics import AnswerMetrics, compute
from .audience import Audience, register_layer
from .claim_verifier import VerificationContext, regeneration_feedback, verify
from .legal_graph import (
    GraphContext,
    get_legal_graph,
    parse_section_key,
    section_key,
)
from .llm_service import llm_service
from .model_json import load_json_payload
from .rag_service import RAGService, with_disclaimer
from .retrieval.offence_lookup import find_offences
from .retrieval.structured_filter import parse_citation
from .vector_service import EXACT_MATCH_DISTANCE, get_vector_service

logger = logging.getLogger(__name__)

# Enough headroom for a structured answer; the default cap truncates one
# mid-object and loses the whole thing to a parse error.
SYNTHESIS_MAX_TOKENS = 2048
# One. A second attempt that still fails is a model that cannot ground the
# claim, and a third would only produce a more confident version of it.
MAX_REGENERATIONS = 1

# Which act a collection holds, for turning a parsed citation back into a key.
_ACT_OF_COLLECTION = {
    "bns_sections": "BNS",
    "bnss_sections": "BNSS",
    "bsa_sections": "BSA",
}
_COLLECTION_OF_ACT = {act: collection for collection, act in _ACT_OF_COLLECTION.items()}

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


def parse_synthesis(raw: str) -> StructuredAnswer:
    """
    Parse the model's structured output.

    A malformed response yields an empty answer rather than an exception: the
    caller then abstains, which is the correct outcome for a turn that produced
    nothing checkable. Raising here would turn a bad generation into a 500.

    **One bad claim does not discard the others.** Validating the whole payload
    at once meant a single unrecognised ``epistemic_class`` took the entire
    answer down: judge mode was observed emitting ``"doctrine"`` on claim 3 --
    a reasonable guess, since the graph context has a DOCTRINE block -- and
    claims 0, 1 and 2 went with it, producing an abstention on "what governs
    bail in a non-bailable offence?". Claims are therefore validated one at a
    time and the unusable ones dropped.

    This gives nothing away. Every claim that survives parsing is still
    verified individually afterwards, so salvaging cannot admit an unsupported
    claim -- it only stops a formatting error from destroying claims that would
    have passed. It is the same rule the verifier follows: failures are
    removed, not hedged, and not allowed to take their neighbours with them.
    """
    payload = load_json_payload(raw)
    if payload is None:
        return StructuredAnswer()

    if isinstance(payload, list):
        payload = {"claims": payload}
    try:
        return StructuredAnswer.model_validate(payload)
    except ValidationError as error:
        logger.warning(f"synthesis JSON did not match the claim schema: {error}")

    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        return StructuredAnswer()

    claims = []
    for index, raw_claim in enumerate(payload["claims"]):
        try:
            claims.append(Claim.model_validate(raw_claim))
        except ValidationError as error:
            logger.warning(f"dropping unusable claim {index}: {error}")
    if claims:
        logger.info(
            f"salvaged {len(claims)} of {len(payload['claims'])} claims from a "
            "partially malformed synthesis"
        )
    return StructuredAnswer(claims=claims)


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

        What is checked is ``citation.sections`` -- the sections that will
        actually be looked up -- and not ``citation.section``, the number the
        query wrote down. For a current citation the two are the same. For a
        repealed one they are not, and comparing the old number against the new
        act asks a question with no meaning: "what replaced IPC section 420"
        was refused with "there is no section 420 of the BNS", which is true,
        irrelevant, and the confident wrong refusal this pre-check exists to
        avoid. "IPC 302" survived only by luck -- BNS 302 exists (it is about
        snatching), so an equally meaningless check happened to pass.

        Since a repealed citation is resolvable only through the concordance,
        and every concordance target was checked against our own parse of the
        gazette when it was built, the repealed branch should now never refuse.
        It is still checked rather than assumed: this pre-check is the one
        place that can refuse an answer with no model in the loop, so it must
        be certain rather than nearly certain.
        """
        citation = parse_citation(query)
        if citation is None or not citation.resolvable or citation.collection is None:
            return None

        act = {"bns_sections": "BNS", "bnss_sections": "BNSS", "bsa_sections": "BSA"}[
            citation.collection
        ]
        graph = get_legal_graph()
        missing = [
            number
            for number in citation.sections
            if not graph.has_section(section_key(act, number))
        ]
        if not missing or len(missing) < len(citation.sections):
            # A repealed provision often became several (IPC 498A -> BNS 85 and
            # 86). One of them existing is enough to answer the question.
            return None

        highest = max(
            (
                int(node.section)
                for node in graph.sections.values()
                if node.act == act and node.section.isdigit()
            ),
            default=0,
        )
        numbers = ", ".join(missing)
        plural = "s" if len(missing) > 1 else ""
        return (
            f"There is no section{plural} {numbers} of the {act}. It runs to "
            f"section {highest}. I have not tried to answer the question, because "
            "the provision it asks about does not exist."
        )

    def citation_note(self, query: str, claims: list[Any]) -> str:
        """
        Correct the question itself where the citation in it needs correcting.

        Verification establishes that a claim is *true*. It says nothing about
        whether the answer addresses what was asked, and testing found two ways
        that gap shows:

        - "What does BNSS 103 say about murder?" was answered with BNS 103,
          which is murder; BNSS 103 is about searching closed premises. Every
          claim verified, because every claim was true — of a different
          provision than the one named.
        - "Since IPC 302 still applies..." was answered correctly from BNS 103
          without ever saying the IPC is repealed, leaving the false premise
          standing.

        Both are corrected from the parsed citation and the corpus, not by the
        model, so the correction cannot itself be wrong or argued away.
        """
        citation = parse_citation(query)
        if citation is None or citation.collection is None:
            return ""

        act = _ACT_OF_COLLECTION[citation.collection]
        graph = get_legal_graph()

        if citation.repealed:
            cited = f"{citation.act_name} {citation.section}{citation.suffix}"
            if citation.resolvable:
                replacements = ", ".join(
                    f"{act} {number}" for number in citation.sections
                )
                return (
                    f"{cited} was repealed by the 2023 codes. The corresponding "
                    f"provision is {replacements}, and the answer below is about that."
                )
            return (
                f"{cited} was repealed by the 2023 codes, and this corpus has no "
                "mapping for that section number."
            )

        if not citation.resolvable:
            return ""

        key = section_key(act, citation.section)
        node = graph.sections.get(key)
        if node is None:
            return ""

        referenced = {source.ref for claim in claims for source in claim.sources}
        if key in referenced:
            return ""
        return (
            f"You asked about {key}, which is titled \u201c{node.title}\u201d. "
            "The answer below does not rest on that provision."
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

    def _synthesise(self, prompt: str, audience: Audience) -> StructuredAnswer:
        """
        Generate the claims.

        The register is appended to the *system* prompt and reaches nothing
        else: retrieval already happened, and verification happens after, so
        neither can be influenced by who is asking.
        """
        raw = self.llm_service.generate(
            prompt=prompt,
            system=SYNTHESIS_SYSTEM + register_layer(audience),
            max_tokens=SYNTHESIS_MAX_TOKENS,
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

        # A named offence is as exact a reference as a citation is, and dense
        # retrieval is bad at it: "what is the punishment for theft" ranks BNS
        # 305 (theft in a dwelling house) and BNS 304 (snatching) above BNS 303,
        # so the model quoted and cited the wrong sections. The verifier caught
        # it every time, which turned a basic question into an abstention. The
        # First Schedule names the section, so fetch it.
        for key in find_offences(query):
            self._add_named_section(merged, key)

        order = sorted(range(len(merged["ids"])), key=lambda i: merged["distances"][i])[:top_k]
        return {key: [values[i] for i in order] for key, values in merged.items()}

    def _add_named_section(self, merged: dict[str, list[Any]], key: str) -> None:
        """Put a section the query named at the head of the ranking."""
        parsed = parse_section_key(key)
        if parsed is None:
            return
        act, number = parsed
        collection = _COLLECTION_OF_ACT.get(act)
        if collection is None:
            return

        found = self.vector_service._get_or_create_collection(collection).get(
            where={"section_number": number}, include=["documents", "metadatas"]
        )
        for index, doc_id in enumerate(found.get("ids", [])):
            if doc_id in merged["ids"]:
                continue
            merged["ids"].append(doc_id)
            merged["documents"].append(found["documents"][index])
            merged["metadatas"].append(found["metadatas"][index])
            # Ranks with the exact citation hits, which is what it is.
            merged["distances"].append(EXACT_MATCH_DISTANCE)

    def answer(
        self,
        query: str,
        collection: str | list[str] = "bns_sections",
        top_k: int = 5,
        audience: Audience = Audience.CITIZEN,
        retrieved: dict[str, Any] | None = None,
    ) -> GroundedAnswer:
        """
        Answer one question, or say honestly that it cannot be answered.

        ``audience`` selects the register the answer is written in. It changes
        the explanation and nothing else -- see ``services.audience``.

        ``retrieved`` lets a caller supply material this method would otherwise
        fetch itself, which is how the multi-agent path feeds in what its
        specialists gathered in parallel. Passing it skips **retrieval only**:
        the citation pre-check still runs, and so do graph expansion, the
        synthesis prompt, verification, the single regeneration attempt, the
        abstention rule and the metrics. A fanned-out answer is therefore
        checked by exactly the same machinery as a single-pass one, which is
        the property that makes adding agents safe.
        """
        collections = [collection] if isinstance(collection, str) else list(collection)
        trace: dict[str, Any] = {
            "query": query,
            "collections": collections,
            "audience": audience.value,
            "steps": [],
        }

        refusal = self.check_citation(query)
        if refusal:
            trace["steps"].append({"step": "citation_precheck", "outcome": "refused"})
            return self._abstain(query, refusal, trace)

        if retrieved is None:
            search_results = self._retrieve(query, collections, top_k)
            source = "single pass"
        else:
            # Already gathered, by specialists running in parallel. Everything
            # downstream is unchanged: the same graph expansion, the same
            # prompt, the same verifier, the same abstention rule. That is the
            # whole point of specialists returning *evidence* rather than
            # answers -- the fan-out changes what reaches this prompt and
            # nothing about what is checked after it.
            search_results = retrieved
            source = "gathered by specialists"
        trace["steps"].append({
            "step": "retrieve",
            "source": source,
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
                self._synthesis_prompt(query, context, graph_context, feedback), audience
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
            # The text of what was thrown out, not just that something was.
            # `verdicts` carries an index into the pre-removal claim list, and
            # `structured` below is the list *after* removal -- so by the time
            # anything downstream reads this, the index no longer resolves.
            # Without the text recorded here, "2 statements were removed"
            # cannot be traced back to which two, which is the first question
            # asked whenever the grounding gate fails.
            "rejected": [
                {
                    "index": verdict.index,
                    "epistemic_class": verdict.original_class.value,
                    "reason": verdict.reason,
                    "text": answer.claims[verdict.index].text,
                }
                for verdict in verdicts
                if not verdict.verified
            ],
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

        note = self.citation_note(query, surviving.claims)
        if note:
            prose = f"_{note}_\n\n{prose}"
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
