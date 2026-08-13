"""
The legal corpus as a graph.

Law is not flat prose. Sections cross-reference sections, judgements interpret
sections, doctrines form across judgements, and every offence carries
procedural attributes that decide what actually happens to a person. Retrieval
that only ranks paragraphs by similarity cannot see any of that: ask about BNSS
187 and the cases interpreting it never appear, because they do not talk about
remand in the words the question used.

Four edge kinds, all built from committed data at startup:

    section   --cross_references--> section    regex over the statute text
    judgement --interprets-------> section     the judgement's own metadata
    doctrine  --established_by---> judgement   data/curated/doctrines.json
    doctrine  --refined_by-------> judgement   data/curated/doctrines.json
    section   --classified_as----> attributes  the First Schedule table

**No LLM-inferred edges, ever.** A false relation does not stay local: it
propagates into every answer that touches either endpoint, and there is nothing
in the output to show it was invented. Cross-references are mechanical, the
judgement edges are transcribed metadata, and the doctrine edges are curated by
hand for exactly this reason.

Nodes are keyed by their citation: ``"BNS 103"``, ``"BNSS 482"``, and
judgements and doctrines by their own ids.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
CURATED_DIR = DATA_DIR / "curated"

# The three acts, by the short name used in citations and in the judgement
# metadata's ``relevant_sections``.
ACT_FILES: dict[str, str] = {
    "BNS": "bns_sections.json",
    "BNSS": "bnss_sections.json",
    "BSA": "bsa_sections.json",
}
ACT_LONG_NAMES: dict[str, str] = {
    "BNS": "Bharatiya Nyaya Sanhita",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita",
    "BSA": "Bharatiya Sakshya Adhiniyam",
}

# "section 35", "sections 35 and 36", "sections 173, 174 and 175". The trailing
# list is captured whole and split afterwards, because the gazette punctuates it
# several different ways.
_REFERENCE = re.compile(
    r"\bsections?\s+(\d{1,3})((?:\s*(?:,|and|or|to)\s*\d{1,3})*)", re.IGNORECASE
)
_LIST_NUMBER = re.compile(r"\d{1,3}")
# What follows a reference decides which act it points into. A bare reference
# means the act the section is in; a named act redirects it; a reference to some
# other statute ("section 4 of the Immoral Traffic (Prevention) Act") cannot be
# resolved against this corpus at all and is dropped rather than pointed at the
# same-numbered section of the wrong act.
_LOOKAHEAD = 90
_NAMED_ACT = {
    "nyaya sanhita": "BNS",
    "nagarik suraksha sanhita": "BNSS",
    "sakshya adhiniyam": "BSA",
}
_FOREIGN_ACT = re.compile(r"\bof\s+the\s+[^,.;]{0,60}?\b(Act|Code|Constitution)\b")

# "BNSS 482", the form used in judgement metadata and in the doctrine file.
_CITATION_KEY = re.compile(r"^(BNS|BNSS|BSA)\s+(\d{1,3})$")


def section_key(act: str, section: str) -> str:
    """The graph's node key for a section: ``("BNS", "103") -> "BNS 103"``."""
    return f"{act} {section}"


def parse_section_key(key: str) -> tuple[str, str] | None:
    """Split ``"BNSS 482"`` back into its act and section, or ``None``."""
    match = _CITATION_KEY.match(key.strip())
    return (match.group(1), match.group(2)) if match else None


@dataclass(frozen=True)
class SectionNode:
    key: str
    act: str
    section: str
    title: str
    chapter: str


@dataclass(frozen=True)
class JudgementNode:
    id: str
    case_name: str
    year: str
    citation: str
    subject: str
    source_url: str


@dataclass(frozen=True)
class DoctrineNode:
    id: str
    name: str
    summary: str
    established_by: tuple[str, ...]
    refined_by: tuple[str, ...]
    applies_to: tuple[str, ...]
    contested: bool
    contest_note: str | None

    @property
    def judgements(self) -> tuple[str, ...]:
        """Every judgement the doctrine rests on, oldest attribution first."""
        return self.established_by + self.refined_by


@dataclass
class LegalGraph:
    """An in-memory graph over the committed corpus."""

    sections: dict[str, SectionNode] = field(default_factory=dict)
    judgements: dict[str, JudgementNode] = field(default_factory=dict)
    doctrines: dict[str, DoctrineNode] = field(default_factory=dict)

    cross_references: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    """section key -> the sections its text cites."""

    cited_by: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    """section key -> the sections that cite it."""

    interpreted_by: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    """section key -> judgement ids."""

    interprets: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    """judgement id -> section keys."""

    doctrines_for_section: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    doctrines_for_judgement: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    classification: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    """section key -> its rows in the First Schedule (an offence may have more
    than one, classified differently)."""

    unresolved_references: int = 0
    """References dropped because the target does not exist in this corpus."""

    # -- queries -----------------------------------------------------------

    def has_section(self, key: str) -> bool:
        return key in self.sections

    def related_sections(self, key: str) -> list[str]:
        """Sections this one cites, and sections that cite it."""
        return sorted(self.cross_references.get(key, set()) | self.cited_by.get(key, set()))

    def judgements_on(self, key: str) -> list[JudgementNode]:
        """The judgements recorded as interpreting a section."""
        return [self.judgements[j] for j in self.interpreted_by.get(key, []) if j in self.judgements]

    def doctrines_on(self, key: str) -> list[DoctrineNode]:
        return [self.doctrines[d] for d in self.doctrines_for_section.get(key, [])]

    def offence_attributes(self, key: str) -> list[dict[str, Any]]:
        return list(self.classification.get(key, []))

    def contested_sections(self) -> set[str]:
        """
        Sections a curated doctrine marks as having competing authority.

        This is the list the contested path consults: a user who does not know
        a question is contested will not think to ask for both sides.
        """
        return {
            key
            for doctrine in self.doctrines.values()
            if doctrine.contested
            for key in doctrine.applies_to
        }

    def neighbourhood(self, key: str) -> dict[str, Any]:
        """Everything the graph knows about one section, for expansion and traces."""
        node = self.sections.get(key)
        return {
            "section": node,
            "cites": sorted(self.cross_references.get(key, set())),
            "cited_by": sorted(self.cited_by.get(key, set())),
            "judgements": self.judgements_on(key),
            "doctrines": self.doctrines_on(key),
            "classification": self.offence_attributes(key),
            "contested": key in self.contested_sections(),
        }

    def stats(self) -> dict[str, int]:
        return {
            "sections": len(self.sections),
            "judgements": len(self.judgements),
            "doctrines": len(self.doctrines),
            "cross_references": sum(len(v) for v in self.cross_references.values()),
            "unresolved_references": self.unresolved_references,
            "interprets_edges": sum(len(v) for v in self.interprets.values()),
            "classified_sections": len(self.classification),
        }


def _resolve_reference_act(text: str, position: int, home_act: str) -> str | None:
    """
    Decide which act a ``section N`` reference points into.

    Returns ``None`` when the reference is to some other statute entirely --
    "of the Immoral Traffic (Prevention) Act" -- because pointing it at the
    same-numbered section of one of these three acts would fabricate an edge.
    """
    following = text[position : position + _LOOKAHEAD]
    for name, act in _NAMED_ACT.items():
        if name in following.lower():
            return act
    if _FOREIGN_ACT.search(following):
        return None
    return home_act


def _extract_references(text: str, home_act: str) -> set[tuple[str, str]]:
    """Pull ``(act, section)`` references out of one section's text."""
    found: set[tuple[str, str]] = set()
    for match in _REFERENCE.finditer(text):
        act = _resolve_reference_act(text, match.end(), home_act)
        if act is None:
            continue
        numbers = [match.group(1), *_LIST_NUMBER.findall(match.group(2) or "")]
        for number in numbers:
            found.add((act, number))
    return found


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. The graph is built only from committed data; "
            "run the ingest scripts rather than letting it start up empty."
        )
    return json.loads(path.read_text())


def build_graph() -> LegalGraph:
    """Build the graph from ``data/``. Called once, at startup."""
    graph = LegalGraph()

    # Sections, and the cross-references in their text.
    raw_texts: dict[str, tuple[str, str]] = {}
    for act, filename in ACT_FILES.items():
        for record in _load_json(PROCESSED_DIR / filename):
            metadata = record["metadata"]
            key = section_key(act, metadata["section_number"])
            graph.sections[key] = SectionNode(
                key=key,
                act=act,
                section=metadata["section_number"],
                title=metadata.get("title", ""),
                chapter=metadata.get("chapter", ""),
            )
            raw_texts[key] = (record["text"], act)

    for key, (text, act) in raw_texts.items():
        for target_act, number in _extract_references(text, act):
            target = section_key(target_act, number)
            if target == key:
                continue
            if target not in graph.sections:
                graph.unresolved_references += 1
                continue
            graph.cross_references[key].add(target)
            graph.cited_by[target].add(key)

    # Judgements, and the sections they are recorded as interpreting.
    for record in _load_json(PROCESSED_DIR / "sc_judgements.json"):
        metadata = record["metadata"]
        graph.judgements[record["id"]] = JudgementNode(
            id=record["id"],
            case_name=metadata.get("case_name", ""),
            year=str(metadata.get("year", "")),
            citation=metadata.get("citation", ""),
            subject=metadata.get("subject", ""),
            source_url=metadata.get("source_url", ""),
        )
        for raw in (metadata.get("relevant_sections") or "").split(","):
            key = raw.strip()
            if not key:
                continue
            if key not in graph.sections:
                logger.warning(
                    f"{record['id']}: relevant_sections names {key!r}, which is not "
                    "in the corpus; edge dropped"
                )
                continue
            graph.interprets[record["id"]].append(key)
            graph.interpreted_by[key].append(record["id"])

    # Doctrines, curated.
    for entry in _load_json(CURATED_DIR / "doctrines.json")["doctrines"]:
        established = tuple(entry.get("established_by", []))
        refined = tuple(entry.get("refined_by", []))
        applies = tuple(entry.get("applies_to_sections", []))
        doctrine = DoctrineNode(
            id=entry["id"],
            name=entry["name"],
            summary=entry["summary"],
            established_by=established,
            refined_by=refined,
            applies_to=applies,
            contested=bool(entry.get("contested")),
            contest_note=entry.get("contest_note"),
        )
        graph.doctrines[doctrine.id] = doctrine

        for judgement_id in doctrine.judgements:
            if judgement_id not in graph.judgements:
                logger.warning(
                    f"doctrine {doctrine.id}: {judgement_id} is not in the corpus; "
                    "edge dropped"
                )
                continue
            graph.doctrines_for_judgement[judgement_id].append(doctrine.id)
        for key in doctrine.applies_to:
            if key not in graph.sections:
                logger.warning(
                    f"doctrine {doctrine.id}: applies_to_sections names {key!r}, "
                    "which is not in the corpus; edge dropped"
                )
                continue
            graph.doctrines_for_section[key].append(doctrine.id)

    # Offence classification, if it has been ingested.
    schedule = PROCESSED_DIR / "offence_classification.json"
    if schedule.exists():
        for row in json.loads(schedule.read_text()):
            key = section_key(row["short_name"], row["section"])
            if key not in graph.sections:
                # The Schedule keys sub-sections ("103(1)"); the corpus keys the
                # parent. Attach to the parent so a lookup on either works.
                base = re.match(r"^\d+", row["section"])
                key = section_key(row["short_name"], base.group()) if base else key
            if key in graph.sections:
                graph.classification[key].append(row)
    else:
        logger.warning(
            "offence_classification.json is missing; classification lookups will "
            "return nothing. Run scripts/ingest_offence_schedule.py."
        )

    logger.info(f"Legal graph built: {graph.stats()}")
    return graph


@lru_cache(maxsize=1)
def get_legal_graph() -> LegalGraph:
    """The process-wide graph. Built on first use, then reused."""
    return build_graph()


def reset_legal_graph() -> None:
    """Drop the cached graph. For tests."""
    get_legal_graph.cache_clear()
