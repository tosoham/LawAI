#!/usr/bin/env python3
"""
Ingest landmark Supreme Court judgements into the LawAI corpus.

Fetches a curated set of judgements from Indian Kanoon and writes
``data/processed/sc_judgements.json`` in the shape
``VectorService.add_documents`` expects.

Why the manifest is curated and pinned
--------------------------------------
Resolving cases by search alone is not safe here: searching for "Selvi vs State
of Karnataka" returns the unrelated Jayalalitha appeal as its top hit, and
searching for a landmark judgement often surfaces a later order in the same
matter. Citing the wrong authority is a serious failure for a legal assistant,
so every entry below is a document id that was resolved and checked by hand,
and each fetch is re-verified against ``expect`` tokens at ingestion time. If a
page ever stops matching, that entry is skipped loudly rather than silently
stored as the wrong case.

Politeness: Indian Kanoon is a free public service. Requests are rate limited,
identify themselves, and the ``Disallow`` list in robots.txt is honoured.

Usage:
    python scripts/ingest_judgments.py
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "judgements"
PROCESSED_DIR = DATA_DIR / "processed"

BASE_URL = "https://indiankanoon.org"
USER_AGENT = "LawAI/1.0 (legal research corpus builder; contact: todrsoham@gmail.com)"
REQUEST_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT = 45
# Judgements run long; keep enough for retrieval without storing whole volumes.
MAX_JUDGEMENT_CHARS = 60_000


@dataclass(frozen=True)
class JudgementSpec:
    """A hand-verified judgement: its document id and how to confirm identity."""

    doc_id: str
    case_name: str
    year: str
    subject: str
    expect: Tuple[str, ...]
    relevant_sections: str = ""


# Every doc_id below was resolved by search and confirmed against the page title.
JUDGEMENTS: Tuple[JudgementSpec, ...] = (
    # --- Arrest, bail and personal liberty -------------------------------
    JudgementSpec("2982624", "Arnesh Kumar v. State of Bihar", "2014",
                  "Arrest guidelines and notice of appearance", ("arneshkumar", "bihar"),
                  "BNSS 35, BNSS 179"),
    JudgementSpec("123660783", "Sushila Aggarwal v. State (NCT of Delhi)", "2020",
                  "Anticipatory bail cannot be limited in time", ("sushilaaggarwal",),
                  "BNSS 482"),
    JudgementSpec("7148380", "Satender Kumar Antil v. Central Bureau of Investigation", "2022",
                  "Comprehensive bail guidelines by offence category", ("satenderkumarantil",),
                  "BNSS 478, BNSS 480, BNSS 482"),
    JudgementSpec("1308768", "Gurbaksh Singh Sibbia v. State of Punjab", "1980",
                  "Foundational principles of anticipatory bail", ("sibbia", "punjab"),
                  "BNSS 482"),
    JudgementSpec("8258", "State of Rajasthan, Jaipur v. Balchand", "1977",
                  "Bail is the rule, jail the exception", ("balchand",),
                  "BNSS 480"),
    JudgementSpec("1912056", "Moti Ram v. State of Madhya Pradesh", "1978",
                  "Bail conditions must not be onerous", ("motiram",),
                  "BNSS 478"),
    JudgementSpec("768175", "Joginder Kumar v. State of Uttar Pradesh", "1994",
                  "Arrest must be justified, not routine", ("joginderkumar",),
                  "BNSS 35"),
    JudgementSpec("501198", "D.K. Basu v. State of West Bengal", "1997",
                  "Mandatory safeguards on arrest and custodial detention", ("d.k.basu", "basu"),
                  "BNSS 35, BNSS 47"),
    JudgementSpec("1007347", "Hussainara Khatoon v. Home Secretary, State of Bihar", "1979",
                  "Speedy trial and release of undertrial prisoners", ("hussainarakhatoon",),
                  "BNSS 479"),
    JudgementSpec("1108032", "Siddharam Satlingappa Mhetre v. State of Maharashtra", "2010",
                  "Considerations governing anticipatory bail", ("siddharam",),
                  "BNSS 482"),
    JudgementSpec("117859307", "Nikesh Tarachand Shah v. Union of India", "2017",
                  "Twin conditions for bail struck down under PMLA", ("nikeshtarachandshah",),
                  "BNSS 480"),
    JudgementSpec("18346623", "Union of India v. K.A. Najeeb", "2021",
                  "Bail despite statutory bar where trial is delayed", ("najeeb",),
                  "BNSS 480"),
    JudgementSpec("90251163", "P. Chidambaram v. Directorate of Enforcement", "2019",
                  "Bail principles in economic offences", ("chidambaram",),
                  "BNSS 480, BNSS 482"),
    JudgementSpec("84792457", "Arnab Manoranjan Goswami v. State of Maharashtra", "2020",
                  "Personal liberty and the duty to grant bail", ("arnab", "goswami"),
                  "BNSS 480, BNSS 528"),
    JudgementSpec("14485072", "Vijay Madanlal Choudhary v. Union of India", "2022",
                  "PMLA procedure, arrest and bail conditions", ("vijaymadanlalchoudhary",),
                  "BNSS 480"),
    JudgementSpec("174498", "Sheela Barse v. State of Maharashtra", "1983",
                  "Rights of women in police custody", ("sheelabarse",),
                  "BNSS 43, BNSS 47"),

    # --- Investigation and criminal procedure ----------------------------
    JudgementSpec("10239019", "Lalita Kumari v. Government of Uttar Pradesh", "2013",
                  "Registration of FIR is mandatory for cognizable offences",
                  ("lalitakumari",), "BNSS 173"),

    # --- Evidence ---------------------------------------------------------
    JudgementSpec("13149785", "Sharad Birdhichand Sarda v. State of Maharashtra", "1984",
                  "Five golden principles for circumstantial evidence",
                  ("sharadbirdhichandsarda",), "BSA 6"),
    JudgementSpec("1938988", "Nandini Satpathy v. P.L. Dani", "1978",
                  "Right against self-incrimination during interrogation",
                  ("nandinisatpathy",), "BSA 23"),
    JudgementSpec("187283766", "Anvar P.V. v. P.K. Basheer", "2014",
                  "Admissibility of electronic evidence and certification",
                  ("anvar", "basheer"), "BSA 63"),
    JudgementSpec("172105947", "Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal", "2020",
                  "Certificate requirement for electronic records",
                  ("arjunpanditraokhotkar",), "BSA 63"),

    # --- Sentencing -------------------------------------------------------
    JudgementSpec("307021", "Bachan Singh v. State of Punjab", "1980",
                  "Rarest of rare doctrine for capital punishment",
                  ("bachansingh", "punjab"), "BNS 103"),
    JudgementSpec("545301", "Machhi Singh v. State of Punjab", "1983",
                  "Guidelines applying the rarest of rare doctrine",
                  ("machhisingh",), "BNS 103"),

    # --- Constitutional backdrop -----------------------------------------
    JudgementSpec("1766147", "Maneka Gandhi v. Union of India", "1978",
                  "Procedure established by law must be fair, just and reasonable",
                  ("manekagandhi",), ""),
    JudgementSpec("116396036", "Justice K.S. Puttaswamy (Retd.) v. Union of India", "2015",
                  "Reference on the right to privacy", ("puttaswamy",), ""),
    JudgementSpec("110813550", "Shreya Singhal v. Union of India", "2015",
                  "Section 66A IT Act struck down; online free speech",
                  ("shreyasinghal",), ""),
    JudgementSpec("111867", "Kedar Nath Singh v. State of Bihar", "1962",
                  "Sedition confined to incitement to violence",
                  ("kedarnathsingh",), "BNS 152"),
)


def normalise_key(value: str) -> str:
    """Strip everything but alphanumerics for tolerant title comparison."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def load_disallowed_docs(session: requests.Session) -> Set[str]:
    """
    Read robots.txt and collect the document ids disallowed for generic agents.

    The site lists thousands of individual ``/doc/<id>/`` paths (takedown and
    privacy requests). Fetching one would be rude at best, so they are skipped.
    """
    disallowed: Set[str] = set()
    try:
        response = session.get(f"{BASE_URL}/robots.txt", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - a missing robots.txt must not abort ingestion
        logger.warning(f"Could not read robots.txt ({exc}); proceeding without a blocklist")
        return disallowed

    applies = False
    for line in response.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if lowered.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            applies = agent == "*"
            continue
        if applies and lowered.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            match = re.match(r"^/doc(?:fragment)?/+(\d+)", path)
            if match:
                disallowed.add(match.group(1))

    logger.info(f"robots.txt lists {len(disallowed)} disallowed document ids")
    return disallowed


def fetch_judgement(session: requests.Session, spec: JudgementSpec) -> Optional[str]:
    """Download one judgement page, caching the HTML under data/raw."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / f"{spec.doc_id}.html"

    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")

    url = f"{BASE_URL}/doc/{spec.doc_id}/"
    logger.info(f"Fetching {spec.case_name} ({url})")
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    time.sleep(REQUEST_DELAY_SECONDS)

    if response.status_code != 200:
        logger.error(f"{spec.case_name}: HTTP {response.status_code}")
        return None

    cache.write_text(response.text, encoding="utf-8")
    return response.text


def parse_judgement(html: str, spec: JudgementSpec) -> Optional[Dict[str, Any]]:
    """Extract the judgement text and metadata, verifying it is the right case."""
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one(".doc_title")
    if title_el is None:
        logger.error(f"{spec.case_name}: no title on page")
        return None
    page_title = title_el.get_text(" ", strip=True)

    # Guard against the document id pointing at a different case.
    key = normalise_key(page_title)
    missing = [token for token in spec.expect if normalise_key(token) not in key]
    if missing:
        logger.error(
            f"{spec.case_name}: page title {page_title!r} is missing {missing} - "
            "refusing to store a possibly incorrect authority"
        )
        return None

    body_el = soup.select_one(".judgments") or soup.select_one("#doc_content")
    if body_el is None:
        logger.error(f"{spec.case_name}: no judgement body on page")
        return None

    text = re.sub(r"\n{3,}", "\n\n", body_el.get_text("\n", strip=True))
    if len(text) > MAX_JUDGEMENT_CHARS:
        text = text[:MAX_JUDGEMENT_CHARS].rsplit("\n", 1)[0] + "\n\n[Judgement truncated]"

    citation_el = soup.select_one(".doc_citations")
    citation = ""
    if citation_el:
        citation = citation_el.get_text(" ", strip=True)
        citation = re.sub(r"^Equivalent citations:\s*", "", citation)

    bench_el = soup.select_one(".doc_bench")
    bench = bench_el.get_text(" ", strip=True).replace("Bench:", "").strip() if bench_el else ""

    slug = re.sub(r"[^a-z0-9]+", "_", spec.case_name.lower()).strip("_")

    return {
        "id": f"sc_{slug}_{spec.year}",
        "text": f"{spec.case_name} ({spec.year})\nSubject: {spec.subject}\n\n{text}",
        "metadata": {
            "case_name": spec.case_name,
            "citation": citation,
            "year": spec.year,
            "court": "Supreme Court of India",
            "bench": bench,
            "subject": spec.subject,
            "relevant_sections": spec.relevant_sections,
            "page_title": page_title,
            "source": "Indian Kanoon",
            "source_url": f"{BASE_URL}/doc/{spec.doc_id}/",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh", action="store_true",
        help="Ignore cached HTML and re-download every judgement",
    )
    args = parser.parse_args()

    if args.refresh and RAW_DIR.exists():
        for cached in RAW_DIR.glob("*.html"):
            cached.unlink()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    disallowed = load_disallowed_docs(session)

    records: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for spec in JUDGEMENTS:
        if spec.doc_id in disallowed:
            logger.warning(f"{spec.case_name}: disallowed by robots.txt, skipping")
            skipped.append(spec.case_name)
            continue
        try:
            html = fetch_judgement(session, spec)
            if not html:
                skipped.append(spec.case_name)
                continue
            record = parse_judgement(html, spec)
            if record is None:
                skipped.append(spec.case_name)
                continue
            records.append(record)
            logger.info(f"  parsed {spec.case_name} ({len(record['text']):,} chars)")
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
            logger.error(f"{spec.case_name}: {exc}")
            skipped.append(spec.case_name)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "sc_judgements.json"
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))

    logger.info(f"Wrote {len(records)} judgements to {out_path.relative_to(DATA_DIR.parent)}")
    if skipped:
        logger.warning(f"Skipped {len(skipped)}: {', '.join(skipped)}")
    return 0 if records else 1


if __name__ == "__main__":
    sys.exit(main())
