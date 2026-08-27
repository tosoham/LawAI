#!/usr/bin/env python3
"""
LawAI as an MCP server.

Exposes the same services the HTTP API exposes, to a client that speaks Model
Context Protocol rather than REST. Nothing here reimplements anything: every
tool is a thin adapter over a service that is already measured, already tested
and already the thing the API calls.

**Grounding travels with the tools, and this is the whole design constraint.**
``ask`` returns typed claims with their per-claim verdicts and the abstention,
not retrieved text -- because an MCP client that gets raw chunks has routed
around the only property that makes this system safe to use. A model on the
other end of this protocol will happily turn a retrieved paragraph into a
confident sentence about someone's liberty, and it will do so *outside* the
verifier. So the boundary is drawn at the same place the HTTP API draws it: the
caller receives what survived checking, and what was removed, and why.

The corollary is that ``search_corpus`` is deliberately **not** offered as a
raw retrieval tool. It would be the most convenient tool here and the most
dangerous, for exactly that reason.

Two transports:

    python mcp_server.py                # stdio, for Claude Desktop
    python mcp_server.py --http         # streamable HTTP

Run it from ``backend/`` like everything else -- imports are rooted there.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
    # stdio transport speaks JSON-RPC on stdout. A log line written there
    # corrupts the stream and the client sees a protocol error rather than a
    # log, so everything goes to stderr.
    stream=sys.stderr,
)
logger = logging.getLogger("lawai.mcp")

INSTRUCTIONS = """LawAI answers questions about Indian criminal law under the 2023 \
codes: the Bharatiya Nyaya Sanhita (BNS, offences), the Bharatiya Nagarik Suraksha \
Sanhita (BNSS, procedure) and the Bharatiya Sakshya Adhiniyam (BSA, evidence). These \
replaced the Indian Penal Code, the Code of Criminal Procedure and the Indian Evidence \
Act; do not answer from the repealed codes.

Prefer `ask` for anything that needs a statement of law. It returns claims that have \
each been checked against the corpus, and it abstains rather than guessing. The other \
tools are exact lookups over committed data.

Every claim it returns carries an epistemic class saying what kind of thing it is -- \
enacted text, a procedural classification, what a court held, or reasoning. Preserve \
that distinction when you present it. Do not describe a case as holding something \
unless the claim says it did."""


server = MCPServer(
    name="lawai",
    title="LawAI — Indian criminal law",
    instructions=INSTRUCTIONS,
)


@server.tool(
    description=(
        "Answer a question about Indian criminal law with every claim checked "
        "against the corpus. Returns typed claims, the verdict on each, and what "
        "was removed. Abstains rather than guessing when nothing can be "
        "supported. Use this for anything that needs a statement of law."
    )
)
def ask(question: str, audience: str = "citizen") -> dict[str, Any]:
    """
    The grounded answer path, returned whole.

    ``audience`` is ``citizen`` (default), ``lawyer`` or ``judge``. It changes
    the register and nothing else -- the same law is retrieved and the same
    claims are checked the same way, and judge mode additionally refuses to
    suggest an outcome.
    """
    from agents.legal_agent import CORPUS_COLLECTIONS
    from services.audience import parse_audience
    from services.grounded_answer import get_grounded_answer_service

    result = get_grounded_answer_service().answer(
        question, CORPUS_COLLECTIONS, audience=parse_audience(audience)
    )
    return {
        "abstained": result.abstained,
        "answer": result.answer,
        "claims": [
            {
                "text": claim.text,
                "epistemic_class": claim.epistemic_class.value,
                "sources": [
                    {"ref": s.ref, "kind": s.kind.value} for s in claim.sources
                ],
                "verbatim_span": claim.verbatim_span,
            }
            for claim in result.structured.claims
        ],
        # Reported rather than silently applied. An answer that dropped what it
        # could not support looks identical to one that never overreached, and
        # a caller deciding how much to trust this needs the difference.
        "removed": [
            {"reason": verdict.reason, "class": verdict.original_class.value}
            for verdict in result.verdicts
            if not verdict.verified
        ],
        "metrics": result.metrics.to_dict(),
        "sources": result.sources,
    }


@server.tool(
    description=(
        "The full text of one section of the BNS, BNSS or BSA, by citation. "
        "Exact lookup, no model involved."
    )
)
def get_section(act: str, section: str) -> dict[str, Any]:
    """``act`` is BNS, BNSS or BSA; ``section`` is the number, e.g. "103"."""
    from services.legal_graph import get_legal_graph, section_key

    graph = get_legal_graph()
    key = section_key(act.upper(), str(section))
    node = graph.sections.get(key)
    if node is None:
        highest = max(
            (
                int(other.section)
                for other in graph.sections.values()
                if other.act == act.upper() and other.section.isdigit()
            ),
            default=0,
        )
        return {
            "found": False,
            "error": f"There is no section {section} of the {act.upper()}. "
            f"It runs to section {highest}.",
        }
    return {
        "found": True,
        "citation": key,
        "act": node.act,
        "section": node.section,
        "title": node.title,
        "text": node.text,
        "cross_references": sorted(graph.cross_references.get(key, set())),
    }


@server.tool(
    description=(
        "Whether an offence is cognizable and bailable, which court tries it, "
        "and the custody timeline that follows. Read from the BNSS First "
        "Schedule; no model involved, and an unresolved classification is "
        "returned as unresolved rather than guessed."
    )
)
def classify_offence(act: str, section: str) -> dict[str, Any]:
    """
    The deterministic layer for one offence.

    A classification this cannot resolve comes back ``null`` with the
    Schedule's own wording beside it. 27 rows defer to another offence, and a
    guessed "bailable" is the most dangerous value this system can emit.
    """
    from services.procedural_timeline import for_section

    payload = for_section(act.upper(), str(section))
    if payload is None:
        return {"found": False, "error": f"{act.upper()} {section} is not in the corpus"}
    return {"found": True, **payload}


@server.tool(
    description=(
        "Curated doctrine bearing on a section, with the cases that formed it. "
        "Carries no claim about precedential status; where authority splits, "
        "both sides are named and neither is declared the winner."
    )
)
def explain_doctrine(act: str, section: str) -> dict[str, Any]:
    """Doctrine attached to one provision, from `data/curated/doctrines.json`."""
    from services.legal_graph import get_legal_graph, section_key

    graph = get_legal_graph()
    key = section_key(act.upper(), str(section))
    doctrines = graph.doctrines_on(key)
    return {
        "section": key,
        "contested": key in graph.contested_sections(),
        "doctrines": [
            {
                "id": d.id,
                "name": d.name,
                "summary": d.summary,
                "established_by": list(d.established_by),
                "refined_by": list(d.refined_by),
                "contested": d.contested,
                "contest_note": d.contest_note,
            }
            for d in doctrines
        ],
    }


@server.tool(
    description=(
        "What replaced a section of the repealed IPC, CrPC or Evidence Act. "
        "A number with no recorded mapping is refused rather than assumed: the "
        "new acts renumbered, so returning the same number would turn a miss "
        "into a confident wrong answer."
    )
)
def what_replaced(act: str, section: str) -> dict[str, Any]:
    """``act`` is IPC, CrPC or Evidence Act; ``section`` the old number."""
    from services.retrieval.structured_filter import parse_citation

    citation = parse_citation(f"{act} {section}")
    if citation is None:
        # Either the act is not one we recognise or the number is not one a
        # section can carry. Said separately, because "IPC 9999" reported as
        # "IPC is not a repealed code" is a confusing answer to a reasonable
        # question -- the act was fine, the number was not.
        from services.retrieval.structured_filter import REPEALED_ACT_NAMES

        if act.strip().lower() in REPEALED_ACT_NAMES:
            return {
                "found": False,
                "error": f"{section!r} is not a section number the {act} carries.",
            }
        return {
            "found": False,
            "error": f"{act} is not one of the repealed codes (IPC, CrPC, Evidence Act)",
        }
    if not citation.repealed:
        return {
            "found": False,
            "error": f"{act} is not one of the repealed codes (IPC, CrPC, Evidence Act)",
        }
    if not citation.resolvable:
        return {
            "found": False,
            "error": f"{act} {section} has no recorded mapping in this corpus. "
            "The replacement is not assumed, because the acts renumbered.",
        }
    act_name = {
        "bns_sections": "BNS",
        "bnss_sections": "BNSS",
        "bsa_sections": "BSA",
    }[citation.collection]
    return {
        "found": True,
        "repealed": f"{act} {section}",
        "replaced_by": [f"{act_name} {number}" for number in citation.sections],
        "source": "Bureau of Police Research and Development correspondence tables",
    }


@server.tool(
    description=(
        "Search live judiciary sources for current case law. Results are "
        "retrieved, not curated: each carries its court, date and source URL, "
        "and none has been verified against the corpus. Do not present one as "
        "settled law."
    )
)
def search_case_law(query: str, court: str = "supremecourt", limit: int = 5) -> dict[str, Any]:
    """
    Live lookup, kept separate from corpus material on purpose.

    Fails soft: an unreachable source returns an error rather than raising, so
    a caller can fall back to `ask`.
    """
    from services.judiciary_service import get_judiciary_service

    return get_judiciary_service().search_case_law(query, court=court, limit=limit)


@server.tool(
    description=(
        "The text of one judgement from live judiciary sources, by document id."
    )
)
def fetch_judgment(doc_id: str, max_chars: int = 20000) -> dict[str, Any]:
    """Retrieved, unverified material. Attribute it as such."""
    from services.judiciary_service import get_judiciary_service

    return get_judiciary_service().fetch_judgment(doc_id, max_chars=max_chars)


@server.tool(
    description=(
        "Draft a legal document. Returns generated text carrying a disclaimer; "
        "it is a starting point for a lawyer, not a filing."
    )
)
async def draft_document(document_type: str, details: str) -> dict[str, Any]:
    """One of the types `list_document_types` reports."""
    from tools.registry import get_tool_registry

    tool = get_tool_registry().get_tool("draft_document")
    if tool is None:
        return {"success": False, "error": "drafting is not available"}
    result = await tool.safe_execute(document_type=document_type, details=details)
    return {"success": result.success, "data": result.data, "error": result.error}


@server.tool(description="The document types `draft_document` accepts.")
async def list_document_types() -> dict[str, Any]:
    """
    The same list the HTTP API serves, from the same function.

    Not a copy. The frontend once carried its own menu and offered "Affidavit"
    while the API rejected it; a third list here would be the same bug with one
    more place to drift. The server owns the structure.
    """
    from api.v1.documents import get_document_templates

    # Serialised to plain data: the endpoint returns a Pydantic model, and the
    # protocol carries JSON.
    return (await get_document_templates()).model_dump()


@server.tool(
    description=(
        "What the corpus actually contains, so a caller can tell what is out of "
        "scope before asking."
    )
)
def corpus_info() -> dict[str, Any]:
    """Counts from the committed data, not a description of it."""
    from services.legal_graph import get_legal_graph

    graph = get_legal_graph()
    return {
        "acts": ["BNS (offences)", "BNSS (procedure)", "BSA (evidence)"],
        "sections": len(graph.sections),
        "judgements": len(graph.judgements),
        "doctrines": len(graph.doctrines),
        "classified_offences": len(graph.classification),
        "scope": (
            "Indian criminal law under the 2023 codes, and a set of Supreme "
            "Court judgements. Nothing else -- tax, GST, contract and civil "
            "matters are out of scope and will be refused."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve over streamable HTTP instead of stdio",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8765")))
    args = parser.parse_args()

    if args.http:
        logger.info(f"LawAI MCP server on http://{args.host}:{args.port}")
        server.settings.host = args.host
        server.settings.port = args.port
        server.run(transport="streamable-http")
    else:
        logger.info("LawAI MCP server on stdio")
        server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
