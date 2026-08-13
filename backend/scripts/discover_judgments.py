#!/usr/bin/env python3
"""
Grow the judgement corpus by topic, and verify what comes back.

The thirty landmark judgements are pinned: each one names a document id, and
ingestion refuses to store it unless the fetched page still says what it was
expected to say. That discipline is right for authorities the doctrine lineage
rests on, and it does not scale -- it requires someone to have already decided
which case they want.

For breadth the question changes. Not *"is this the case I expected?"* but
*"is this a real judgement, and are the attributes we are about to record for
it correct?"*:

- the page is a judgement page with a title, a body and a court;
- the title parses into parties and a date, and the date is a real one;
- the body is long enough to be a decision rather than an order sheet or a
  stub;
- the sections it is recorded against are ones its own text actually cites.

Sections are recorded as ``cited_sections``, **not** as ``relevant_sections``,
and that distinction is the whole finding of this script.

``relevant_sections`` is what becomes ``judgement --interprets--> section`` in
the legal graph, and it says the case is an authority *on* that provision.
That cannot be derived. Measured against the thirty curated judgements: reading
the act out of each citation recovers 1 of 27, because judgements overwhelmingly
write a bare "Section 438" and rely on context -- Sushila Aggarwal says it
seventy-five times and names the Code beside it only occasionally. The obvious
repair, taking the act each judgement mentions most, was tested and is worse
than useless: Nandini Satpathy is an authority on the Evidence Act and mentions
the CrPC thirty-two times to the Evidence Act's two; Mohd. Arif is curated to
BNS 103 and mentions the CrPC nineteen times to the IPC's six; P. Chidambaram
splits 28 to 26. It would have produced confident, wrong edges.

What *is* derivable is weaker and still worth having: the provisions a
judgement's text demonstrably cites, where the act is named in the citation
itself and cited more than once. That is a fact about the document, checkable
by string match, and it is recorded under its own key so it can never be
mistaken for the stronger claim. State of Haryana v. Bhajan Lal yields BNSS 173
this way -- true, and not what it is the authority for.

``subject`` is likewise *not* invented. For a discovered case it records the
topic the search was run under, which is a fact about how it was found, and
nothing more is claimed. Doctrine lineage stays hand-curated in
``data/curated/doctrines.json``.

Usage:
    python scripts/discover_judgments.py --dry-run       # search only
    python scripts/discover_judgments.py --limit 5       # a few per topic
    python scripts/discover_judgments.py --target 300
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.judiciary_service import get_judiciary_service

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = BACKEND_DIR.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "judgements"
PROCESSED_DIR = DATA_DIR / "processed"
OUT_PATH = PROCESSED_DIR / "sc_judgements.json"
CONCORDANCE_PATH = PROCESSED_DIR / "repealed_concordance.json"

BASE_URL = "https://indiankanoon.org"
REQUEST_TIMEOUT = 45
USER_AGENT = "LawAI/1.0 (legal research; respects robots.txt)"

# Discovered judgements are capped shorter than the pinned ones. The corpus is
# a retrieval index, not an archive: a judgement is indexed in ~1,200-character
# chunks, so an uncapped tail of 300 cases buries the 3,184 statute chunks under
# fifteen thousand of its own and every question starts retrieving case law.
# The citable identity and the reasoning fit well inside this, and `source_url`
# is on every record for the full text.
MAX_DISCOVERED_CHARS = 25_000
# Below this a page is an order sheet, a listing notice or a stub, not a
# decision worth indexing.
MIN_JUDGEMENT_CHARS = 3_000

# A section has to be cited more than once before the graph records the
# judgement as bearing on it. A single mention is often a party's argument
# being recited, or a list of provisions the court then sets aside.
MIN_SECTION_MENTIONS = 2
# Sections named this often are procedural furniture (the appeal provision, the
# article the writ was filed under) rather than what the case is about.
MAX_SECTIONS_PER_JUDGEMENT = 6


@dataclass(frozen=True)
class Topic:
    """One search to run, and the subject it records for what it finds."""

    key: str
    query: str
    subject: str


TOPICS: tuple[Topic, ...] = (
    Topic("bail", "anticipatory bail conditions", "Bail: anticipatory bail"),
    Topic("bail", "regular bail non-bailable offence", "Bail: bail in non-bailable offences"),
    Topic("bail", "default bail chargesheet not filed", "Bail: default bail"),
    Topic("bail", "cancellation of bail", "Bail: cancellation"),
    Topic("bail", "bail economic offences", "Bail: economic offences"),
    Topic("arrest", "arrest without warrant police powers", "Arrest: powers and limits"),
    Topic("arrest", "illegal detention custodial violence", "Arrest: custody and detention"),
    Topic("arrest", "notice of appearance police", "Arrest: notice of appearance"),
    Topic("arrest", "remand police custody magistrate", "Arrest: remand"),
    Topic("evidence", "admissibility electronic evidence certificate", "Evidence: electronic records"),
    Topic("evidence", "circumstantial evidence conviction", "Evidence: circumstantial evidence"),
    Topic("evidence", "dying declaration reliability", "Evidence: dying declaration"),
    Topic("evidence", "confession police custody admissibility", "Evidence: confessions"),
    Topic("evidence", "hostile witness testimony", "Evidence: witnesses"),
    Topic("evidence", "expert opinion forensic evidence", "Evidence: expert opinion"),
    Topic("procedure", "quashing FIR inherent powers High Court", "Procedure: quashing"),
    Topic("procedure", "registration of FIR cognizable offence", "Procedure: FIR"),
    Topic("procedure", "charge framing discharge accused", "Procedure: charge and discharge"),
    Topic("procedure", "speedy trial delay undertrial", "Procedure: speedy trial"),
    Topic("procedure", "investigation further investigation police report", "Procedure: investigation"),
    Topic("procedure", "summons warrant proclaimed offender", "Procedure: process"),
    Topic("procedure", "compounding of offences settlement", "Procedure: compounding"),
    Topic("sentencing", "sentencing proportionality mitigating circumstances", "Sentencing: principles"),
    Topic("sentencing", "death sentence rarest of rare", "Sentencing: capital punishment"),
    Topic("sentencing", "life imprisonment remission", "Sentencing: life imprisonment"),
    Topic("sentencing", "probation of offenders first offender", "Sentencing: probation"),
    Topic("offences", "murder culpable homicide distinction", "Offences: homicide"),
    Topic("offences", "cheating criminal breach of trust", "Offences: property offences"),
    Topic("offences", "dowry death cruelty married woman", "Offences: offences against women"),
    Topic("offences", "rape consent testimony of prosecutrix", "Offences: sexual offences"),
    Topic("offences", "criminal conspiracy common intention", "Offences: joint liability"),
    Topic("offences", "abetment of suicide instigation", "Offences: abetment"),
    Topic("constitutional", "article 21 personal liberty criminal", "Constitutional: personal liberty"),
    Topic("constitutional", "self incrimination article 20(3)", "Constitutional: self-incrimination"),
    Topic("constitutional", "fair trial rights of accused", "Constitutional: fair trial"),
    Topic("constitutional", "preventive detention safeguards", "Constitutional: preventive detention"),
)

# "on 5 May, 2020" -- Indian Kanoon appends the decision date to every title.
_TITLE_DATE = re.compile(r"\bon\s+(\d{1,2}\s+\w+,\s+\d{4})\s*$")
# Section references in a judgement's own text, with the act it names.
_SECTION_MENTION = re.compile(
    # The suffix has to sit tight against the digits, or "section 438 Cr.P.C."
    # reads "Cr" as the suffix of 438 and the act disappears. The tail then has
    # to keep its full stops for the same citation to be recognisable at all,
    # and is kept short so it stays inside the citation rather than wandering
    # into the next sentence and picking up an act that governs something else.
    # The tail is a lookahead, not a match: consuming it swallows the next
    # citation, and a judgement that names its act beside every mention was
    # being counted once instead of twice -- below the threshold, so nothing
    # was recorded at all.
    r"\bsections?\s+(?P<number>\d{1,3})(?P<suffix>[A-Za-z]{1,2})?\b"
    r"(?=(?P<tail>[^\n]{0,40}))",
    re.IGNORECASE,
)
_ACT_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"nagarik\s+suraksha|bnss", re.I), "BNSS"),
    (re.compile(r"nyaya\s+sanhita|\bbns\b", re.I), "BNS"),
    (re.compile(r"sakshya\s+adhiniyam|\bbsa\b", re.I), "BSA"),
    (re.compile(r"cr\.?\s*p\.?\s*c|criminal\s+procedure", re.I), "CrPC"),
    (re.compile(r"\bi\.?\s*p\.?\s*c\b|penal\s+code", re.I), "IPC"),
    (re.compile(r"evidence\s+act", re.I), "Evidence Act"),
)
_REPEALED_TO_NEW = {"IPC": "BNS", "CrPC": "BNSS", "Evidence Act": "BSA"}


def load_concordance() -> dict[tuple[str, str], list[str]]:
    """``{(old act, old section): [new section]}`` for translating citations."""
    if not CONCORDANCE_PATH.exists():
        logger.warning(
            f"{CONCORDANCE_PATH} is missing; judgements citing the repealed codes "
            "will record no sections. Run scripts/ingest_concordance.py."
        )
        return {}
    mapping: dict[tuple[str, str], list[str]] = {}
    for row in json.loads(CONCORDANCE_PATH.read_text()):
        key = (row["old_act"], row["old_section"].upper())
        mapping.setdefault(key, [])
        if row["new_section"] not in mapping[key]:
            mapping[key].append(row["new_section"])
    return mapping


def sections_cited(text: str, concordance: dict[tuple[str, str], list[str]]) -> list[str]:
    """
    The provisions a judgement's own text cites, as section keys.

    Read out of the document rather than inferred from the topic, because these
    become graph edges and the graph does not carry inferred ones. A repealed
    citation is translated through the concordance: a 1980 judgement cites the
    CrPC and nothing else, and recording it against no section at all would
    make the older half of the corpus invisible to the graph.
    """
    counts: Counter[str] = Counter()
    for match in _SECTION_MENTION.finditer(text):
        act = next(
            (name for pattern, name in _ACT_HINTS if pattern.search(match.group("tail"))),
            None,
        )
        if act is None:
            continue
        number = match.group("number")
        suffix = (match.group("suffix") or "").upper()

        if act in _REPEALED_TO_NEW:
            for new_section in concordance.get((act, number + suffix), []):
                counts[f"{_REPEALED_TO_NEW[act]} {new_section}"] += 1
        elif not suffix:
            counts[f"{act} {number}"] += 1

    frequent = [key for key, n in counts.most_common() if n >= MIN_SECTION_MENTIONS]
    return frequent[:MAX_SECTIONS_PER_JUDGEMENT]


def parse_title(page_title: str) -> tuple[str, str] | None:
    """Split "X vs Y on 5 May, 2020" into its case name and year."""
    match = _TITLE_DATE.search(page_title)
    if not match:
        return None
    try:
        # A decision date, not a moment: the timezone is irrelevant and
        # attaching one would imply a precision the source does not carry.
        decided = datetime.strptime(match.group(1), "%d %B, %Y").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None
    name = _TITLE_DATE.sub("", page_title).strip(" ,")
    return (name, str(decided.year)) if name else None


def slugify(case_name: str, year: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", case_name.lower()).strip("_")
    return f"sc_{slug}_{year}"[:110]


def fetch(session: requests.Session, doc_id: str) -> str | None:
    """Fetch a judgement page, caching the HTML so a re-run costs nothing."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / f"{doc_id}.html"
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")

    service = get_judiciary_service()
    if not service.is_allowed(doc_id):
        logger.info(f"{doc_id}: disallowed by robots.txt, skipped")
        return None

    service._throttle()
    try:
        response = session.get(f"{BASE_URL}/doc/{doc_id}/", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:
        logger.warning(f"{doc_id}: fetch failed: {exc}")
        return None

    cache.write_text(response.text, encoding="utf-8")
    return response.text


def build_record(
    doc_id: str, html: str, topic: Topic, concordance: dict[tuple[str, str], list[str]]
) -> dict[str, Any] | None:
    """Verify a fetched page and turn it into a corpus record, or reject it."""
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one(".doc_title")
    if title_el is None:
        logger.debug(f"{doc_id}: no title, not a judgement page")
        return None
    page_title = title_el.get_text(" ", strip=True)

    parsed = parse_title(page_title)
    if parsed is None:
        logger.debug(f"{doc_id}: title {page_title!r} does not parse into a case and date")
        return None
    case_name, year = parsed

    body_el = soup.select_one(".judgments") or soup.select_one("#doc_content")
    if body_el is None:
        logger.debug(f"{doc_id}: no judgement body")
        return None

    text = re.sub(r"\n{3,}", "\n\n", body_el.get_text("\n", strip=True))
    if len(text) < MIN_JUDGEMENT_CHARS:
        logger.debug(f"{doc_id}: {len(text)} chars, too short to be a decision")
        return None

    sections = sections_cited(text, concordance)
    if len(text) > MAX_DISCOVERED_CHARS:
        text = text[:MAX_DISCOVERED_CHARS].rsplit("\n", 1)[0] + "\n\n[Judgement truncated]"

    citation_el = soup.select_one(".doc_citations")
    citation = ""
    if citation_el:
        citation = re.sub(
            r"^Equivalent citations:\s*", "", citation_el.get_text(" ", strip=True)
        )

    bench_el = soup.select_one(".doc_bench")
    bench = bench_el.get_text(" ", strip=True).replace("Bench:", "").strip() if bench_el else ""

    return {
        "id": slugify(case_name, year),
        "text": f"{case_name} ({year})\nSubject: {topic.subject}\n\n{text}",
        "metadata": {
            "case_name": case_name,
            "citation": citation,
            "year": year,
            "court": "Supreme Court of India",
            "bench": bench,
            # The topic it was found under. Not a summary of what it held --
            # nothing here reads the judgement and decides that.
            "subject": topic.subject,
            # Deliberately not `relevant_sections`: that key means "is an
            # authority on" and becomes a graph edge. See the module docstring.
            "relevant_sections": "",
            "cited_sections": ", ".join(sections),
            "page_title": page_title,
            "source": "Indian Kanoon",
            "source_url": f"{BASE_URL}/doc/{doc_id}/",
            "discovery": topic.key,
            "verification": "attributes",
        },
    }


def existing_records() -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """The corpus as it stands, plus the ids and source URLs already in it."""
    if not OUT_PATH.exists():
        return [], set(), set()
    records = json.loads(OUT_PATH.read_text())
    return (
        records,
        {r["id"] for r in records},
        {r["metadata"].get("source_url", "") for r in records},
    )


def discover(limit: int, target: int, dry_run: bool) -> int:
    service = get_judiciary_service()
    concordance = load_concordance()
    records, seen_ids, seen_urls = existing_records()
    logger.info(f"starting from {len(records)} judgements")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    counts = Counter[str]()
    for topic in TOPICS:
        if len(records) >= target:
            logger.info(f"reached the target of {target}")
            break

        found = service.search_case_law(topic.query, court="supremecourt", limit=limit)
        if not found.get("success"):
            logger.warning(f"{topic.query!r}: search failed: {found.get('error')}")
            counts["search_failed"] += 1
            continue

        for hit in found["results"]:
            if len(records) >= target:
                break
            url = hit.get("source_url", "")
            doc_id = url.rstrip("/").rsplit("/", 1)[-1]
            if not doc_id.isdigit() or url in seen_urls:
                counts["already_held"] += 1
                continue

            counts["considered"] += 1
            if dry_run:
                logger.info(f"   would fetch {doc_id}: {hit.get('title', '')[:70]}")
                continue

            html = fetch(session, doc_id)
            if html is None:
                counts["unfetchable"] += 1
                continue

            record = build_record(doc_id, html, topic, concordance)
            if record is None:
                counts["rejected"] += 1
                continue
            if record["id"] in seen_ids:
                counts["duplicate"] += 1
                continue

            seen_ids.add(record["id"])
            seen_urls.add(url)
            records.append(record)
            counts["accepted"] += 1
            logger.info(
                f"   + {record['metadata']['case_name'][:56]} ({record['metadata']['year']}) "
                f"[{record['metadata']['cited_sections'] or 'no sections cited'}]"
            )

    logger.info(f"discovery: {dict(counts)}")
    if dry_run:
        return 0

    with_sections = sum(1 for r in records if r["metadata"].get("cited_sections"))
    logger.info(
        f"{len(records)} judgements total, {with_sections} with at least one "
        "explicitly cited section"
    )
    OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    logger.info(f"wrote {OUT_PATH.relative_to(DATA_DIR.parent)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="results per topic search")
    parser.add_argument("--target", type=int, default=300, help="stop at this many judgements")
    parser.add_argument("--dry-run", action="store_true", help="search but do not fetch")
    args = parser.parse_args()
    try:
        return discover(args.limit, args.target, args.dry_run)
    except Exception as exc:
        logger.error(f"discovery failed: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
