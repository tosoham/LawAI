#!/usr/bin/env python3
"""
Ingest the 2023 Indian criminal codes from their official gazette PDFs.

Downloads the Ministry of Home Affairs publications of the Bharatiya Nyaya
Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya Sakshya Adhiniyam,
splits them into sections and writes ``data/processed/<act>_sections.json`` in
the shape ``VectorService.add_documents`` expects.

Layout notes (why the parser looks the way it does)
---------------------------------------------------
The gazette typesets each section's title as a *marginal note* beside the
section body, not inline. Those notes land in a narrow column: on the left of
even pages and on the right of odd pages. Linear text extraction emits them
out of order -- on one sampled page the note for section 11 appeared after the
note for section 14 -- so titles are matched to sections by vertical position
instead, which lines up to within a couple of points.

Text is extracted with ``x_tolerance=1.0``. The default of 3 glues words
together in this font ("isdoubtfulof"), which would wreck both embeddings and
display.

Usage:
    python scripts/ingest_legal_acts.py            # download if needed, then parse
    python scripts/ingest_legal_acts.py --force-download
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pdfplumber
import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Extraction tuning -----------------------------------------------------------
X_TOLERANCE = 1.0
# A marginal note ends before the body column starts, or begins after it ends.
LEFT_MARGIN_MAX_X1 = 115.0
RIGHT_MARGIN_MIN_X0 = 478.0
# Words on the same typeset line never differ by more than a few points.
LINE_GROUP_TOLERANCE = 3.0

SECTION_START = re.compile(r"^(\d{1,3}[A-Z]?)\.\s*(?=\S)")
# The space after "CHAPTER" is not always present in the extracted text
# ("CHAPTERV", "CHAPTERXX"), so it must be optional.
CHAPTER_HEADING = re.compile(r"^CHAPTER\s*([IVXLC]+|\d+)\s*$")
# Sub-headings such as "Of sexual offences" group sections within a chapter.
SUB_HEADING = re.compile(r"^Of [a-z][^.]{0,60}$")
# Marginal act citations ("45 of 1860.") sit in the same column as the section
# titles -- sometimes even on the same typeset line -- and must not be spliced
# into them.
MARGIN_CITATION = re.compile(r"\b\d{1,3}\s+of\s+\d{4}\.?")
# The marginal column is narrow, so a genuine title line is short. The digital
# signature stamped on the last page shares that column but extracts as one very
# long, digit-heavy run.
MAX_MARGIN_LINE_CHARS = 60
MAX_MARGIN_DIGIT_RATIO = 0.25
# A note may be typeset a few points above the first line of its section.
NOTE_ABOVE_SECTION_TOLERANCE = 6.0
# Running heads, rules and page numbers that must not leak into section text.
NOISE_PATTERNS = (
    re.compile(r"^_{10,}$"),
    re.compile(r"THE GAZETTE OF INDIA", re.IGNORECASE),
    re.compile(r"^\s*Sec\.\s*\d+\]", re.IGNORECASE),
    re.compile(r"^\s*\[?Part\s+II", re.IGNORECASE),
    re.compile(r"^\d{1,4}\s*$"),
    re.compile(r"^\s*$"),
)


@dataclass
class ActSpec:
    """One act: where to fetch it and how to label the sections it yields."""

    key: str
    act_name: str
    short_name: str
    url: str
    filename: str
    id_prefix: str
    expected_min_sections: int


ACTS: Tuple[ActSpec, ...] = (
    ActSpec(
        key="bns",
        act_name="Bharatiya Nyaya Sanhita",
        short_name="BNS",
        url="https://www.mha.gov.in/sites/default/files/250883_english_01042024.pdf",
        filename="bns_2023.pdf",
        id_prefix="bns",
        expected_min_sections=300,
    ),
    ActSpec(
        key="bnss",
        act_name="Bharatiya Nagarik Suraksha Sanhita",
        short_name="BNSS",
        url="https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
        filename="bnss_2023.pdf",
        id_prefix="bnss",
        expected_min_sections=450,
    ),
    ActSpec(
        key="bsa",
        act_name="Bharatiya Sakshya Adhiniyam",
        short_name="BSA",
        url="https://www.mha.gov.in/sites/default/files/250882_english_01042024.pdf",
        filename="bsa_2023.pdf",
        id_prefix="bsa",
        expected_min_sections=140,
    ),
)


@dataclass
class ParsedSection:
    number: str
    chapter: str
    lines: List[str] = field(default_factory=list)
    title: str = ""

    @property
    def text(self) -> str:
        return normalise_whitespace(" ".join(self.lines))


def normalise_whitespace(value: str) -> str:
    """Collapse runs of whitespace and tidy the punctuation gazette PDFs emit."""
    value = value.replace("­", "")  # soft hyphen
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:)])", r"\1", value)
    value = re.sub(r"\(\s+", "(", value)
    return value.strip()


def download_pdf(spec: ActSpec, force: bool) -> Path:
    """Fetch the official PDF unless it is already on disk."""
    target_dir = RAW_DIR / spec.key
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / spec.filename

    if target.exists() and not force:
        logger.info(f"{spec.short_name}: using cached {target.relative_to(DATA_DIR.parent)}")
        return target

    logger.info(f"{spec.short_name}: downloading {spec.url}")
    response = requests.get(spec.url, timeout=120, headers={"User-Agent": "LawAI/1.0"})
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"{spec.short_name}: downloaded file is not a PDF")

    target.write_bytes(response.content)
    logger.info(f"{spec.short_name}: saved {len(response.content):,} bytes")
    return target


def group_words_into_lines(words: Iterable[dict]) -> List[Tuple[float, str]]:
    """Group words sharing a baseline into ``(top, text)`` lines, left to right."""
    lines: Dict[float, List[dict]] = {}
    for word in words:
        for key in lines:
            if abs(word["top"] - key) <= LINE_GROUP_TOLERANCE:
                lines[key].append(word)
                break
        else:
            lines[word["top"]] = [word]

    result = []
    for top in sorted(lines):
        ordered = sorted(lines[top], key=lambda w: w["x0"])
        result.append((top, " ".join(w["text"] for w in ordered)))
    return result


def extract_margin_lines(words: List[dict]) -> List[Tuple[float, str]]:
    """Return the ``(top, text)`` lines from the page's marginal-note column."""
    margin_words = [
        w for w in words
        if w["x1"] < LEFT_MARGIN_MAX_X1 or w["x0"] > RIGHT_MARGIN_MIN_X0
    ]
    if not margin_words:
        return []

    lines = []
    for top, text in group_words_into_lines(margin_words):
        # Drop statute references printed in the margin; they are not title text.
        text = MARGIN_CITATION.sub("", text).strip()
        if not text or text.isdigit():
            continue
        if len(text) > MAX_MARGIN_LINE_CHARS:
            continue
        digits = sum(ch.isdigit() for ch in text)
        if digits / len(text) > MAX_MARGIN_DIGIT_RATIO:
            continue
        lines.append((top, text))
    return lines


def assign_titles(
    margin_lines: List[Tuple[float, str]],
    section_tops: List[Tuple[float, "ParsedSection"]],
) -> int:
    """
    Attach each marginal note to the section it is typeset beside.

    A note starts a point or two below its section's first line and runs down
    the margin, so every note line belongs to the nearest section start at or
    above it. Grouping this way (rather than by vertical gaps between notes)
    avoids merging two titles when they happen to be set close together.

    Returns the number of lines that belonged to no section on this page --
    continuations of a note that began on the previous page.
    """
    if not section_tops:
        return len(margin_lines)

    ordered = sorted(section_tops, key=lambda pair: pair[0])
    collected: Dict[int, List[str]] = {}
    orphans = 0

    for top, text in margin_lines:
        owner: Optional[int] = None
        for index, (section_top, _) in enumerate(ordered):
            if section_top <= top + NOTE_ABOVE_SECTION_TOLERANCE:
                owner = index
            else:
                break
        if owner is None:
            orphans += 1
            continue
        collected.setdefault(owner, []).append(text)

    for index, parts in collected.items():
        section = ordered[index][1]
        if not section.title:
            section.title = normalise_whitespace(" ".join(parts)).rstrip(".")

    return orphans


def is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def parse_act(pdf_path: Path, spec: ActSpec) -> List[ParsedSection]:
    """Split one act PDF into sections, attaching chapter and title metadata."""
    sections: List[ParsedSection] = []
    current: Optional[ParsedSection] = None
    chapter = ""
    pending_chapter_title = False
    unmatched_notes = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf.pages):
            words = page.extract_words(x_tolerance=X_TOLERANCE)
            if not words:
                continue

            body_words = [
                w for w in words
                if not (w["x1"] < LEFT_MARGIN_MAX_X1 or w["x0"] > RIGHT_MARGIN_MIN_X0)
            ]
            margin_lines = extract_margin_lines(words)
            body_lines = group_words_into_lines(body_words)

            # Where each section on this page begins, so notes can be aligned.
            section_tops: List[Tuple[float, ParsedSection]] = []

            for top, line in body_lines:
                if is_noise(line):
                    continue

                stripped = line.strip()

                chapter_match = CHAPTER_HEADING.match(stripped)
                if chapter_match:
                    chapter = f"Chapter {chapter_match.group(1).upper()}"
                    pending_chapter_title = True
                    continue

                # The line after "CHAPTER X" is the chapter's name, in caps.
                if pending_chapter_title:
                    pending_chapter_title = False
                    if stripped and stripped == stripped.upper() and not SECTION_START.match(stripped):
                        chapter = f"{chapter} - {stripped.title()}"
                        continue

                # Sub-headings introduce a group of sections and belong to none.
                if SUB_HEADING.match(stripped):
                    continue

                match = SECTION_START.match(line.strip())
                if match:
                    current = ParsedSection(number=match.group(1), chapter=chapter)
                    sections.append(current)
                    section_tops.append((top, current))

                if current is not None:
                    current.lines.append(line)

            unmatched_notes += assign_titles(margin_lines, section_tops)

    if unmatched_notes:
        logger.info(
            f"{spec.short_name}: {unmatched_notes} marginal notes could not be aligned "
            "to a section start (continuation notes from the previous page)"
        )
    return sections


def build_records(sections: List[ParsedSection], spec: ActSpec) -> List[Dict[str, Any]]:
    """Convert parsed sections into the ingest schema, dropping empty ones."""
    records: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}

    for section in sections:
        body = section.text
        if len(body) < 40:
            # Almost always a cross-reference in a table of contents, not a section.
            continue

        number = section.number
        seen[number] = seen.get(number, 0) + 1
        if seen[number] > 1:
            # The gazette repeats a number when a section spans an odd page break.
            continue

        title = section.title
        heading = f"Section {number}"
        if title:
            heading += f" - {title}"

        records.append({
            "id": f"{spec.id_prefix}_{number}",
            "text": f"{heading}\n{body}",
            "metadata": {
                "section_number": number,
                "title": title,
                "act": spec.act_name,
                "short_name": spec.short_name,
                "year": "2023",
                "chapter": section.chapter,
                "source": "Ministry of Home Affairs, Gazette of India",
                "source_url": spec.url,
            },
        })

    return records


def ingest(spec: ActSpec, force_download: bool) -> List[Dict[str, Any]]:
    pdf_path = download_pdf(spec, force_download)
    logger.info(f"{spec.short_name}: parsing {pdf_path.name}")

    sections = parse_act(pdf_path, spec)
    records = build_records(sections, spec)

    titled = sum(1 for r in records if r["metadata"]["title"])
    logger.info(
        f"{spec.short_name}: {len(records)} sections "
        f"({titled} with titles, {len(records) - titled} without)"
    )

    if len(records) < spec.expected_min_sections:
        logger.warning(
            f"{spec.short_name}: only {len(records)} sections parsed, expected at "
            f"least {spec.expected_min_sections} - the PDF layout may have changed"
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{spec.key}_sections.json"
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    logger.info(f"{spec.short_name}: wrote {out_path.relative_to(DATA_DIR.parent)}")

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-download", action="store_true",
        help="Re-download the PDFs even if they are already cached",
    )
    parser.add_argument(
        "--act", choices=[a.key for a in ACTS],
        help="Only ingest a single act (default: all three)",
    )
    args = parser.parse_args()

    specs = [a for a in ACTS if not args.act or a.key == args.act]
    total = 0
    failed = []

    for spec in specs:
        try:
            total += len(ingest(spec, args.force_download))
        except Exception as exc:  # noqa: BLE001 - report and continue with other acts
            logger.error(f"{spec.short_name}: ingestion failed: {exc}")
            failed.append(spec.short_name)

    logger.info(f"Total sections ingested: {total}")
    if failed:
        logger.error(f"Failed acts: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
