"""
What actually happens to a person, step by step, with the section for each.

"Is this bailable?" is rarely the whole question. The one behind it is usually
*how long can they hold me, and when does something have to happen?* -- and
that answer lives scattered across five sections of the BNSS that nobody
without training would think to put together.

Every step below quotes the provision it comes from and names it. Nothing here
is generated: the steps are fixed, their sections are fixed, and the only thing
that varies is a branch the statute itself draws.

That branch is the ninety-vs-sixty day limit in BNSS 187(3), which turns on
whether the offence is "punishable with death, imprisonment for life or
imprisonment for a term of ten years or more". That is read out of the First
Schedule's punishment column. **Where it cannot be read, the timeline says so
rather than picking one** -- telling somebody they have sixty days when they
have ninety, or ninety when they have sixty, is exactly the kind of confident
wrong answer this system is built to refuse.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .legal_graph import LegalGraph, get_legal_graph, section_key

logger = logging.getLogger(__name__)

# The gazette hyphenates across line breaks ("imprison- ment"), and the
# Schedule carries those breaks into the punishment column.
_SOFT_HYPHEN = re.compile(r"(\w)-\s+(\w)")
_YEARS = re.compile(r"\b(\d{1,2})\s*years?\b", re.IGNORECASE)
_LIFE = re.compile(r"\bimprisonment\s+for\s+life\b|\blife\s+imprisonment\b", re.IGNORECASE)
_DEATH = re.compile(r"\bdeath\b", re.IGNORECASE)

# BNSS 187(3)(i): the longer limit applies at ten years or more.
LONG_CUSTODY_YEARS = 10
LONG_CUSTODY_DAYS = 90
SHORT_CUSTODY_DAYS = 60


def _normalise(punishment: str) -> str:
    return _SOFT_HYPHEN.sub(r"\1\2", punishment)


@dataclass(frozen=True)
class Severity:
    """How the statute's own thresholds classify an offence's punishment."""

    death_or_life: bool
    max_years: int | None
    resolved: bool
    """False when the punishment column says nothing this can be read from."""

    @property
    def custody_limit_days(self) -> int | None:
        """The BNSS 187(3) limit, or ``None`` when it cannot be determined."""
        if not self.resolved:
            return None
        if self.death_or_life:
            return LONG_CUSTODY_DAYS
        if self.max_years is None:
            return None
        return (
            LONG_CUSTODY_DAYS
            if self.max_years >= LONG_CUSTODY_YEARS
            else SHORT_CUSTODY_DAYS
        )


def classify_punishment(punishment: str) -> Severity:
    """
    Read an offence's punishment against the thresholds the BNSS uses.

    Deliberately narrow. It recognises death, imprisonment for life and a
    number of years, and gives up on anything else -- "Same as for offence
    abetted", "One half of the imprisonment for life", "Fine only". Giving up
    is a result, not a failure: the caller reports that the limit depends on
    the underlying offence instead of inventing one.
    """
    text = _normalise(punishment or "")
    if not text.strip():
        return Severity(False, None, resolved=False)

    if _DEATH.search(text) or _LIFE.search(text):
        return Severity(True, None, resolved=True)

    years = [int(y) for y in _YEARS.findall(text)]
    if years:
        return Severity(False, max(years), resolved=True)
    return Severity(False, None, resolved=False)


@dataclass(frozen=True)
class TimelineStep:
    """One thing the law requires, and where it is required."""

    stage: str
    detail: str
    section: str
    """The section key, so a client can link it and a reader can check it."""
    section_title: str = ""
    conditional: bool = False
    """True where the step applies only in some cases -- said, not hidden."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "detail": self.detail,
            "section": self.section,
            "section_title": self.section_title,
            "conditional": self.conditional,
        }


@dataclass
class Timeline:
    steps: list[TimelineStep] = field(default_factory=list)
    custody_limit_days: int | None = None
    limit_basis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "custody_limit_days": self.custody_limit_days,
            "limit_basis": self.limit_basis,
        }


def _years(count: int | None) -> str:
    return "1 year" if count == 1 else f"{count} years"


def _title(graph: LegalGraph, key: str) -> str:
    node = graph.sections.get(key)
    return node.title if node else ""


def build_timeline(
    severity: Severity, cognizable: bool | None, graph: LegalGraph | None = None
) -> Timeline:
    """
    The custody timeline for an offence of this severity.

    ``cognizable`` decides only whether arrest without warrant is shown as
    available; it is passed as ``None`` where the Schedule leaves it
    conditional, and the step is then marked conditional rather than dropped.
    """
    graph = graph or get_legal_graph()
    limit = severity.custody_limit_days

    if limit is None:
        basis = (
            "The sixty- or ninety-day limit in BNSS 187(3) turns on the punishment "
            "for the offence, which could not be determined from the First Schedule "
            "for this section."
        )
    elif severity.death_or_life:
        basis = (
            "Ninety days: BNSS 187(3)(i) applies where the offence is punishable "
            "with death or imprisonment for life."
        )
    elif limit == LONG_CUSTODY_DAYS:
        basis = (
            f"Ninety days: BNSS 187(3)(i) applies at ten years or more, and this "
            f"offence carries up to {_years(severity.max_years)}."
        )
    else:
        basis = (
            f"Sixty days: BNSS 187(3)(ii) applies to any other offence, and this "
            f"one carries up to {_years(severity.max_years)}."
        )

    steps = [
        TimelineStep(
            stage="Arrest without warrant",
            detail=(
                "A police officer may arrest without a warrant for a cognizable "
                "offence, subject to the conditions in the section."
            ),
            section="BNSS 35",
            section_title=_title(graph, "BNSS 35"),
            conditional=cognizable is not True,
        ),
        TimelineStep(
            stage="Taken before a Magistrate",
            detail=(
                "The arrested person must be taken or sent before a Magistrate "
                "having jurisdiction without unnecessary delay."
            ),
            section="BNSS 57",
            section_title=_title(graph, "BNSS 57"),
        ),
        TimelineStep(
            stage="24 hours",
            detail=(
                "Police custody may not exceed twenty-four hours without an order "
                "of a Magistrate, excluding the time needed for the journey to "
                "court."
            ),
            section="BNSS 58",
            section_title=_title(graph, "BNSS 58"),
        ),
        TimelineStep(
            stage="Remand",
            detail=(
                "A Magistrate may authorise further detention, and beyond fifteen "
                "days only on being satisfied that adequate grounds exist."
            ),
            section="BNSS 187",
            section_title=_title(graph, "BNSS 187"),
        ),
        TimelineStep(
            stage=(
                f"{limit} days — release on bail"
                if limit
                else "60 or 90 days — release on bail"
            ),
            detail=basis
            + " On the expiry of that period the accused shall be released on bail "
            "if he is prepared to and does furnish bail.",
            section="BNSS 187",
            section_title=_title(graph, "BNSS 187"),
            conditional=limit is None,
        ),
        TimelineStep(
            stage="Investigation report",
            detail=(
                "Investigation must be completed without unnecessary delay, and the "
                "report forwarded to the Magistrate on completion."
            ),
            section="BNSS 193",
            section_title=_title(graph, "BNSS 193"),
        ),
    ]

    # BNSS 479 excludes offences punishable with death or life imprisonment from
    # the undertrial release it provides, so it is not shown as available there.
    if not severity.death_or_life:
        steps.append(
            TimelineStep(
                stage="Undertrial limit",
                detail=(
                    "A person detained for up to one-half of the maximum "
                    "imprisonment for the offence shall be released on bail, and a "
                    "first-time offender on bond after one-third. This does not "
                    "apply where death or life imprisonment is a punishment."
                ),
                section="BNSS 479",
                section_title=_title(graph, "BNSS 479"),
                conditional=not severity.resolved,
            )
        )

    return Timeline(steps=steps, custody_limit_days=limit, limit_basis=basis)


def for_section(act: str, section: str, graph: LegalGraph | None = None) -> dict[str, Any] | None:
    """
    Everything the deterministic layer knows about one offence.

    Returns ``None`` when the section is not in the corpus. A section with no
    First Schedule row -- all of the BNSS, most of the BSA -- returns its
    identity and no classification, rather than an empty card that looks like a
    lookup failure.
    """
    graph = graph or get_legal_graph()
    key = section_key(act.upper(), section)
    node = graph.sections.get(key)
    if node is None:
        return None

    rows = graph.offence_attributes(key)
    payload: dict[str, Any] = {
        "section": key,
        "act": act.upper(),
        "number": node.section,
        "title": node.title,
        "chapter": node.chapter,
        "classification": rows,
        "doctrines": [
            {"id": d.id, "name": d.name, "summary": d.summary, "contested": d.contested}
            for d in graph.doctrines_on(key)
        ],
        "judgements": [
            {"id": j.id, "case_name": j.case_name, "citation": j.citation, "year": j.year}
            for j in graph.judgements_on(key)
        ],
        "timeline": None,
    }

    if not rows:
        return payload

    # Where a section is classified more than once the rows can disagree about
    # severity -- theft and petty theft. The timeline is built from the most
    # serious of them, since that is the exposure a person actually faces.
    severities = [classify_punishment(row["punishment"]) for row in rows]
    severity = max(
        severities,
        key=lambda s: (s.death_or_life, s.max_years or 0, s.resolved),
    )
    cognizable = {row["cognizable"] for row in rows}
    payload["timeline"] = build_timeline(
        severity,
        cognizable.pop() if len(cognizable) == 1 else None,
        graph,
    ).to_dict()
    return payload
