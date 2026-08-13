#!/usr/bin/env python3
"""
Build the repealed-code concordance: IPC -> BNS, CrPC -> BNSS, Evidence Act -> BSA.

Practitioners search by the old numbers, and they will for years. "CrPC 438"
means BNSS 482 and "IPC 302" means BNS 103, but the numbering did not carry
over, so the retrieval layer refused to translate: BNSS *also* has a section
438, about something else entirely, and resolving it would have turned a miss
into a confident wrong answer.

What was missing was a source. This builds one from the correspondence tables
the Bureau of Police Research and Development publishes -- a Ministry of Home
Affairs body -- which state, for every section of the three new codes, the
provision of the repealed code it corresponds to.

A concordance is a mapping *asserted* by someone rather than enacted text, and
the rule in this repository is that a section number is never taken on trust.
So what can actually be checked is checked, and what cannot is said plainly.

**Checked.** Every new section named must exist in our own parse of the
gazette; rows naming one that does not are dropped. And the whole extraction is
cross-checked against a *second, independently typeset* table -- the comparative
chart in the same publisher's BNS handbook -- with the run failing if the two
disagree beyond a small margin. That is a real test of the thing most likely to
go wrong, which is not the source but this parser: a 38-page table slips a row
and pairs an old section with the wrong new one, silently.

**Recorded, not gated.** Each row carries ``title_agreement``: how far the
table's subject line overlaps the section's own marginal-note title. It was
built as a filter and then demoted on the evidence. All 58 rows scoring below a
third turned out to be *correct* on inspection -- IPC 501 and 502 map to BNS
356, whose title is simply "Defamation"; the forty definitional rows map to BNS
2, titled "Definitions" -- so a title gate would have discarded good mappings
while catching nothing. It stays as a signal a consumer can weigh, and as the
thing to look at when a mapping is disputed.

**Not checked.** That the Bureau's view of which provision replaced which is
correct. This is a considered third-party source, cited as such on every row,
and it is a weaker guarantee than the statutory text alongside it.

Usage:
    python scripts/ingest_concordance.py
    python scripts/ingest_concordance.py --report    # show the weakest rows
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = BACKEND_DIR.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "concordance"
PROCESSED_DIR = DATA_DIR / "processed"
OUT_PATH = PROCESSED_DIR / "repealed_concordance.json"

PUBLISHER = "Bureau of Police Research and Development, Ministry of Home Affairs"


@dataclass(frozen=True)
class TableSpec:
    """One correspondence table: where to get it and how its columns are laid out."""

    key: str
    new_act: str
    old_act: str
    old_act_name: str
    url: str
    filename: str
    #: Column index of each field in a four-column row. The BSA table puts the
    #: old section second and the subject third; the other two are the reverse.
    columns: dict[str, int]
    corpus_file: str
    expected_min_rows: int


TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        key="bns",
        new_act="BNS",
        old_act="IPC",
        old_act_name="Indian Penal Code, 1860",
        url="https://bprd.nic.in/uploads/pdf/COMPARISON%20SUMMARY%20BNS%20to%20IPC%20.pdf",
        filename="bns_to_ipc.pdf",
        columns={"new": 0, "subject": 1, "old": 2},
        corpus_file="bns_sections.json",
        expected_min_rows=250,
    ),
    TableSpec(
        key="bnss",
        new_act="BNSS",
        old_act="CrPC",
        old_act_name="Code of Criminal Procedure, 1973",
        url="https://bprd.nic.in/uploads/pdf/Comparison%20summary%20BNSS%20to%20CrPC.pdf",
        filename="bnss_to_crpc.pdf",
        columns={"new": 0, "subject": 1, "old": 2},
        corpus_file="bnss_sections.json",
        expected_min_rows=350,
    ),
    TableSpec(
        key="bsa",
        new_act="BSA",
        old_act="Evidence Act",
        old_act_name="Indian Evidence Act, 1872",
        url="https://bprd.nic.in/uploads/pdf/Comparison%20Summary%20BSA%20to%20IEA.pdf",
        filename="bsa_to_iea.pdf",
        columns={"new": 0, "old": 1, "subject": 2},
        corpus_file="bsa_sections.json",
        expected_min_rows=120,
    ),
)

# "103", "103(1)", "2(1)(a)" -> the base section number the corpus is keyed by.
_BASE_SECTION = re.compile(r"^\s*(\d{1,3})")
# Section numbers in the old-code column: "302", "304A", "29 and 29A",
# "453/460", "3, para 1". A letter suffix is part of the number -- IPC 498A is
# not IPC 498 -- so it is captured, not stripped.
_OLD_SECTION = re.compile(r"\b(\d{1,3})\s*([A-Z]{1,2})?\b")
# Everything from a qualifier onwards names a part of a section, not another
# section. Without this "3, para 1" and "23\nClause-2" yield sections 1 and 2,
# which is how IPC 1, 2 and 3 came to be mapped onto the BNS definitions
# clause: they are paragraph numbers of IPC 23.
_QUALIFIER = re.compile(
    r"\b(?:clause|para|paragraph|explanation|explanat|illustration|proviso|interpretation)\b",
    re.IGNORECASE,
)
# Rows saying the provision is new, dropped, or has no counterpart.
_NO_COUNTERPART = re.compile(r"^\s*(-+|nil|new(ly added)?|omitted|dropped)\s*\.?\s*$", re.I)
# Words carrying no signal when comparing a subject line to a section title.
_STOPWORDS = frozenset({
    "of", "the", "a", "an", "to", "for", "in", "on", "by", "or", "and", "with",
    "any", "as", "at", "be", "from", "into", "not", "such", "that", "this",
    "which", "who", "whoever", "etc", "section", "sections", "certain",
})
_WORD = re.compile(r"[a-z]+")

# Below this, the table's subject and the section's title share little. Recorded
# on the row and logged, never used to drop one -- see the module docstring.
WEAK_AGREEMENT = 0.34
# The cross-check has to actually cover something. If the chart parse breaks it
# silently compares nothing and passes, which is worse than failing.
MIN_CROSS_CHECKED = 60
MIN_CROSS_CHECK_AGREEMENT = 0.95

HANDBOOK = TableSpec(
    key="handbook",
    new_act="BNS",
    old_act="IPC",
    old_act_name="Indian Penal Code, 1860",
    url="https://bprd.nic.in/uploads/pdf/BNS_English_30-04-2024.pdf",
    filename="bns_handbook.pdf",
    columns={},
    corpus_file="bns_sections.json",
    expected_min_rows=0,
)


def download(spec: TableSpec, force: bool) -> Path:
    """Fetch one correspondence table unless it is already on disk."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / spec.filename
    if target.exists() and not force:
        logger.info(f"{spec.key}: using cached {target.relative_to(DATA_DIR.parent)}")
        return target

    logger.info(f"{spec.key}: downloading {spec.url}")
    response = requests.get(spec.url, timeout=180, headers={"User-Agent": "LawAI/1.0"})
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"{spec.key}: downloaded file is not a PDF")
    target.write_bytes(response.content)
    logger.info(f"{spec.key}: saved {len(response.content):,} bytes")
    return target


def normalise_row(row: list[str | None]) -> list[str] | None:
    """
    Reduce an extracted row to four cells, or reject it.

    The BNS table carries two extra rule lines on some pages, so its rows
    arrive six wide with two empty cells. Collapsing empties is only safe when
    it lands on exactly four; anything else is a row this parser does not
    understand and is dropped rather than guessed at.
    """
    cells = [(c or "").strip() for c in row]
    if len(cells) == 4:
        return cells
    populated = [c for c in cells if c]
    return populated if len(populated) == 4 else None


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def subject_matches_title(subject: str, title: str) -> float:
    """
    How far a table's subject line and the corpus's own section title agree.

    Returns the share of the shorter side's content words present in the other.
    Asymmetric on purpose: the table abbreviates ("Murder.") where the gazette
    marginal note is fuller ("Punishment for murder"), and vice versa, so
    requiring either to contain the other outright would reject good rows.
    """
    left, right = content_words(subject), content_words(title)
    if not left or not right:
        return 0.0
    shared = len(left & right)
    return shared / min(len(left), len(right))


def old_sections(cell: str) -> list[str]:
    """
    Every old-code section named in a cell.

    A cell can list several ("29 and 29A", "453/460") because one new section
    consolidated them; each becomes its own mapping, which is what a user
    searching the old number needs.
    """
    if _NO_COUNTERPART.match(cell):
        return []
    cell = _QUALIFIER.split(cell, maxsplit=1)[0]
    found: list[str] = []
    for number, suffix in _OLD_SECTION.findall(cell):
        section = number + (suffix or "")
        if section not in found:
            found.append(section)
    return found


def load_titles(spec: TableSpec) -> dict[str, str]:
    """``{section number: title}`` from the corpus we parsed ourselves."""
    records = json.loads((PROCESSED_DIR / spec.corpus_file).read_text())
    return {
        r["metadata"]["section_number"]: r["metadata"].get("title", "") for r in records
    }


def parse(spec: TableSpec, pdf_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract one table's mappings, keeping the ones that resolve."""
    titles = load_titles(spec)
    records: list[dict[str, Any]] = []
    counts: dict[str, Any] = {
        "rows": 0, "unparseable": 0, "no_counterpart": 0, "unknown_section": 0
    }
    seen: set[tuple[str, str]] = set()
    weak: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw_row in table:
                    counts["rows"] += 1
                    cells = normalise_row(raw_row)
                    if cells is None:
                        counts["unparseable"] += 1
                        continue

                    new_cell = cells[spec.columns["new"]]
                    subject = cells[spec.columns["subject"]]
                    old_cell = cells[spec.columns["old"]]

                    base = _BASE_SECTION.match(new_cell)
                    if not base:
                        counts["unparseable"] += 1
                        continue
                    new_section = base.group(1)

                    olds = old_sections(old_cell)
                    if not olds:
                        counts["no_counterpart"] += 1
                        continue

                    title = titles.get(new_section)
                    if title is None:
                        counts["unknown_section"] += 1
                        continue

                    agreement = subject_matches_title(subject, title)
                    for old in olds:
                        if (old, new_section) in seen:
                            continue
                        seen.add((old, new_section))
                        record = {
                            "old_act": spec.old_act,
                            "old_act_name": spec.old_act_name,
                            "old_section": old,
                            "new_act": spec.new_act,
                            "new_section": new_section,
                            "new_subsection": new_cell.strip(),
                            "subject": subject.replace("\n", " ").strip(),
                            "title_agreement": round(agreement, 3),
                            "source": PUBLISHER,
                            "source_url": spec.url,
                        }
                        records.append(record)
                        if agreement < WEAK_AGREEMENT:
                            weak.append({**record, "corpus_title": title})

    counts["accepted"] = len(records)
    counts["weak"] = weak
    return records, counts


def parse_handbook_chart(pdf_path: Path) -> dict[str, str]:
    """
    The comparative chart in the BNS handbook, as ``{IPC section: BNS section}``.

    A second table, typeset independently of the correspondence table, covering
    the commonly used sections. It exists here only to check the extraction of
    the first one -- two parses of two documents agreeing on a section number is
    evidence the rows are aligned; one parse agreeing with itself is not.
    """
    mapping: dict[str, str] = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw_row in table:
                    cells = [(c or "").strip() for c in raw_row if (c or "").strip()]
                    if len(cells) != 3:
                        continue
                    old, _, new = cells
                    if not _OLD_SECTION.fullmatch(old.replace(" ", "")):
                        continue
                    base = _BASE_SECTION.match(new)
                    if base:
                        mapping[old] = base.group(1)
    return mapping


def cross_check(records: list[dict[str, Any]], chart: dict[str, str]) -> dict[str, Any]:
    """
    Compare the correspondence table against the independently typeset chart.

    Only IPC rows overlap, and only the commonly used ones, so this covers a
    slice rather than the whole file. That is still the check worth having: a
    parser that has slipped a row slips a run of them, and a run would show up
    here immediately.
    """
    # A set per old section, not a single value: one repealed provision often
    # became several. IPC 376 is answered by both BNS 64 and BNS 65, and IPC
    # 498A by both BNS 85 and BNS 86, so the chart naming one of them is
    # agreement, not conflict. Comparing single values called those two a
    # disagreement and they are not.
    extracted: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if record["old_act"] == "IPC":
            extracted[record["old_section"]].add(record["new_section"])

    shared = sorted(set(chart) & set(extracted))
    disagreements = [
        (old, sorted(extracted[old]), chart[old])
        for old in shared
        if chart[old] not in extracted[old]
    ]
    return {
        "compared": len(shared),
        "agreed": len(shared) - len(disagreements),
        "disagreements": disagreements,
    }


def ingest(force_download: bool, report: bool) -> list[dict[str, Any]]:
    all_records: list[dict[str, Any]] = []
    for spec in TABLES:
        pdf_path = download(spec, force_download)
        records, counts = parse(spec, pdf_path)
        logger.info(
            f"{spec.old_act} -> {spec.new_act}: {counts['accepted']} mappings from "
            f"{counts['rows']} rows "
            f"({counts['no_counterpart']} with no counterpart, "
            f"{counts['unknown_section']} naming a section not in the corpus, "
            f"{counts['unparseable']} unparseable); "
            f"{len(counts['weak'])} with weak title agreement"
        )
        if report:
            for row in counts["weak"][:15]:
                logger.info(
                    f"   weak {row['old_act']} {row['old_section']} -> "
                    f"{row['new_act']} {row['new_section']}: table says "
                    f"{row['subject'][:38]!r}, corpus title is {row['corpus_title'][:38]!r}"
                )
        if len(records) < spec.expected_min_rows:
            logger.warning(
                f"{spec.key}: only {len(records)} mappings, expected at least "
                f"{spec.expected_min_rows} - the source document may have changed"
            )
        all_records.extend(records)

    handbook = download(HANDBOOK, force_download)
    result = cross_check(all_records, parse_handbook_chart(handbook))
    rate = result["agreed"] / result["compared"] if result["compared"] else 0.0
    logger.info(
        f"cross-check against the handbook chart: {result['agreed']}/{result['compared']} "
        f"agree ({rate:.1%})"
    )
    for old, mine, theirs in result["disagreements"]:
        logger.warning(f"   IPC {old}: correspondence table says {mine}, chart says {theirs}")
    if result["compared"] < MIN_CROSS_CHECKED:
        raise RuntimeError(
            f"only {result['compared']} mappings could be cross-checked against the "
            f"handbook chart, expected at least {MIN_CROSS_CHECKED}; the chart parse "
            "has probably broken, and an unchecked concordance is not worth shipping"
        )
    if rate < MIN_CROSS_CHECK_AGREEMENT:
        raise RuntimeError(
            f"the two tables agree on only {rate:.1%} of {result['compared']} shared "
            "mappings; a run of disagreements means a slipped row, so nothing is written"
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(all_records, indent=2, ensure_ascii=False) + "\n")
    logger.info(f"wrote {len(all_records)} mappings to {OUT_PATH.relative_to(DATA_DIR.parent)}")
    return all_records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--report", action="store_true", help="show weak rows")
    args = parser.parse_args()
    try:
        ingest(args.force_download, args.report)
    except Exception as exc:
        logger.error(f"concordance ingestion failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
