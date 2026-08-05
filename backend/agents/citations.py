"""
Citation formatting.

The project's rule is that citations must be exact: "Section 103, Bharatiya
Nyaya Sanhita, 2023" for statute, "Case Name v. Case Name, (Year) Citation" for
judgements. Nothing here is inferred — each component is emitted only when the
metadata actually carries it, because a wrong section number is a correctness
bug and an incomplete citation is merely terse.
"""
from typing import Any

# Present on every corpus chunk and identical across all of them ("Ministry of
# Home Affairs, Gazette of India"). Useful as provenance, useless as a citation,
# so it is only ever a last resort.
_PROVENANCE_KEY = "source"


def _primary_citation(reported: Any) -> str:
    """
    Reduce a judgement's citation list to the one a lawyer would actually cite.

    Indian Kanoon lists every reporter that carried a judgement, so Bachan Singh
    arrives as eleven comma-separated citations running past 200 characters.
    The first is the leading report; the rest are parallel citations that belong
    in a footnote, not in a source label.
    """
    if not reported:
        return ""
    if isinstance(reported, (list, tuple)):
        return str(reported[0]).strip() if reported else ""
    first = str(reported).split(",")[0].strip()
    return first


def format_citation(metadata: dict[str, Any]) -> str:
    """
    Render one retrieved chunk's metadata as a citation.

    Falls back through progressively weaker identifiers, ending at the generic
    provenance string rather than the word "Unknown" — naming the gazette is
    still true, where "Unknown" tells the reader nothing.
    """
    if not metadata:
        return "Source not identified"

    section_number = metadata.get("section_number")
    if section_number:
        parts = [f"Section {section_number}"]
        act = metadata.get("act")
        if act:
            parts.append(act)
        year = metadata.get("year")
        if year:
            parts.append(str(year))
        citation = ", ".join(parts)
        title = metadata.get("title")
        return f"{citation} ({title})" if title else citation

    case_name = metadata.get("case_name")
    if case_name:
        reported = _primary_citation(metadata.get("citation"))
        return f"{case_name}, {reported}" if reported else case_name

    return metadata.get("title") or metadata.get(_PROVENANCE_KEY) or "Source not identified"


def source_payload(source: dict[str, Any]) -> dict[str, Any]:
    """
    Reduce a tool's raw source entry to what a client needs to cite it.

    Deliberately narrow: the full chunk metadata carries internal bookkeeping
    (parent_id, chunk_count) that no caller should start depending on.
    """
    metadata = source.get("metadata", {}) or {}
    return {
        "citation": format_citation(metadata),
        "text": source.get("text", ""),
        "relevance_score": source.get("relevance_score"),
        "section_number": metadata.get("section_number"),
        "act": metadata.get("act"),
        "short_name": metadata.get("short_name"),
        "title": metadata.get("title"),
        "case_name": metadata.get("case_name"),
        "year": metadata.get("year"),
        "chapter": metadata.get("chapter"),
        "source_url": metadata.get("source_url"),
    }
