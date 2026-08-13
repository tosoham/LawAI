#!/usr/bin/env python3
"""
Ingest the BNSS First Schedule, Part I -- the classification of BNS offences.

The most common practical question in Indian criminal law is not a prose
question at all: *is this offence cognizable, is it bailable, and which court
tries it?* The First Schedule answers it for every section of the Bharatiya
Nyaya Sanhita, in a six-column table. Stored as prose it is unreadable and
unciteable; stored as rows it is a lookup that needs no model at all.

Writes ``data/processed/offence_classification.json``.

Layout notes (why the parser looks the way it does)
---------------------------------------------------
The table has no ruling lines -- pdfplumber reports zero vertical edges on
every page of it -- so the columns have to be recovered from geometry.

*Columns* are recovered from left edges, and the edges are not the same on
every page: the gazette re-flows the table per page, so the classification
columns move by as much as 19pt between them (column 4 starts at 285 on page
158 and 304 on page 163). Snapping to a single set of edges looked right and
was not -- it silently pushed "2 years" out of the punishment column and into
the cognizable column on page 188, which then read "2 Non-cognizable." and
resolved to nothing.

Each page's edges are therefore measured from that page's own content, using
the fact that four of the six columns open with a closed vocabulary: column 3
with "Imprisonment"/"Simple"/"Rigorous"/"Death"/"Fine"/"Same", columns 4 and 5
with "Cognizable"/"Non-cognizable" and "Bailable"/"Non-bailable", column 6 with
"Any"/"Court"/"Magistrate"/"The". Where a page is all abetment rows, whose
classification reads "According as offence abetted is..." in both columns, the
first "According" on a line fixes column 4 and the second fixes column 5.

Assigning each *word* to a band by its own x0 does not work: a column's text
wraps within its band, so a continuation word can start well to the right of
its own column and land inside the next one ("...person aggrieved by the" puts
"the" at x0=367, two points inside column 5's tolerance). Words are grouped
into **runs** first and the run is placed by its leading word, so continuation
text cannot escape its column. A run breaks on a wide horizontal gap, or where
a word reaches the next column's anchor outright -- the second test is needed
because adjacent columns can be a single space apart ("...7 years" ends at
x1=283 and "According" begins at 286), and the first because a wide section
number pushes its neighbour off the anchor ("111(2)(a)" ends at x1=92 and
"Organised" begins at 97, three points right of column 2).

*Rows* cannot be recovered from vertical gaps and cannot be recovered from the
section column either.

Not gaps, because the leading is not consistent: most pages set rows 15.6pt
apart and lines within a row 9.6pt apart, but page 161 sets *both* at 10.2pt,
so BNS 70(2) and 71 are one gap apart from each other and from their own
wrapped text.

Not the section column, because the schedule classifies several offences twice
under one section number and leaves column 1 blank on the second row. BNS
356(2) is classified once for defamation of the President -- triable by a Court
of Session -- and once "in any other case", triable by a Magistrate. Keying on
the section number merges the two and reports the wrong court.

What is reliable is that a row cannot fill a cell twice. A line opens a new row
when it would overwrite a cell the current row already holds: a second section
number, or a second classification. Column 4 says exactly one of "Cognizable",
"Non-cognizable" or "According as ..." at a row start and nothing else in the
whole table begins there with a capital (its wrapped text continues in lower
case: "abetted is cognizable"), so a capitalised column 4 is an unambiguous new
value. That also leaves room for the row whose classification is typeset on a
*later* line than its section number, which BNS 264 is.

Part II of the Schedule (offences against *other* laws) is deliberately not
ingested: it is keyed by punishment range rather than by section, so it does
not fit this table's shape.

Usage:
    python scripts/ingest_offence_schedule.py
    python scripts/ingest_offence_schedule.py --report   # per-row dump
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import pdfplumber

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts.ingest_legal_acts import (
    ACTS,
    X_TOLERANCE,
    download_pdf,
    normalise_whitespace,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = BACKEND_DIR.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUT_PATH = PROCESSED_DIR / "offence_classification.json"

BNSS = next(spec for spec in ACTS if spec.key == "bnss")

# Where the table starts and stops. Matched against page text rather than
# hardcoded page numbers so a re-paginated gazette fails loudly instead of
# quietly ingesting the wrong pages.
PART_I_HEADING = re.compile(r"I\.\s*[—-]\s*OFFENCES\s+UNDER\s+THE\s+BHARATIYA\s+NYAYA")
PART_II_HEADING = re.compile(r"II\.\s*[—-]\s*CLASSIFICATION\s+OF\s+OFFENCES\s+AGAINST")

COLUMNS = ("section", "offence", "punishment", "cognizable", "bailable", "triable_by")
# Fallback edges, from the first page of the table. Only used for a column a
# page gives no evidence for, and warned about when it happens.
DEFAULT_ANCHORS: tuple[float, ...] = (58.0, 94.0, 193.0, 285.0, 369.0, 453.0)
# How many words must share a left edge before it counts as that page's anchor.
ANCHOR_MIN_SUPPORT = 4
# x0 values within this of each other are the same left edge.
ANCHOR_TOLERANCE = 2.0
# Columns 1 and 2 have no opening vocabulary, but they are the only things left
# of the punishment column, and they are separated by a wide gutter.
SECTION_COLUMN_MAX_X0 = 90.0
# The words each column can open with. Verified against every line of Part I.
PUNISHMENT_OPENERS = frozenset({
    "Imprisonment", "Imprisonment,", "Simple", "Rigorous", "Death", "Death,",
    "Fine", "Fine.", "Same", "One",
})
COGNIZABLE_OPENERS = frozenset({
    "Cognizable", "Cognizable.", "Non-cognizable", "Non-cognizable.",
})
BAILABLE_OPENERS = frozenset({"Bailable", "Bailable.", "Non-bailable", "Non-bailable."})
COURT_OPENERS = frozenset({"Any", "Court", "Court,", "Magistrate", "Magistrate,", "The"})
# Both classification columns can open with this word; position on the line
# decides which one is meant.
DEFERRED_OPENER = "According"
# How far left of its anchor a column's text may start. Wider than the 2pt of
# observed drift would swallow column 4's wrapped text into column 5.
ON_ANCHOR = 2.0
# Wider than a space at this body size, so it separates columns rather than
# words: the widest inter-word gap measured anywhere in the table is 3.8pt and
# the narrowest column transition is 4.0pt. Erring low is free -- a spurious
# break inside a column produces two runs that resolve to the same column and
# are rejoined -- whereas erring high merges two columns into one cell.
RUN_GAP = 4.0
LINE_GROUP_TOLERANCE = 3.0

# The running head and the rule beneath it.
HEADER_MAX_TOP = 70.0
# The rule under the running head extracts as one very wide "word".
MAX_WORD_WIDTH = 300.0
COLUMN_NUMBER_ROW = ["1", "2", "3", "4", "5", "6"]

# "103", "103(1)", "58(a)", "356(3)". The gazette sometimes typesets the
# sub-clause as a separate word ("58 (a)"), so the space is optional here and
# removed on normalisation.
SECTION_NUMBER = re.compile(r"^(\d{1,3})\s*((?:\(\s*\w{1,3}\s*\))*)\.?$")

# Column 4 and 5 are usually one of two words, but not always: abetment
# offences read "According as offence abetted is cognizable or non-cognizable",
# which resolves only once you know what was abetted. Those stay unresolved --
# a guessed "bailable" is the most dangerous value this file could carry.
COGNIZABLE_VALUES = {"cognizable": True, "non-cognizable": False}
BAILABLE_VALUES = {"bailable": True, "non-bailable": False}
# The three ways column 4 opens a value, and the only capitalised words that
# appear at the head of that column anywhere in Part I. Verified by surveying
# every line of the table, not assumed.
CLASSIFICATION_START = re.compile(r"^(Cognizable|Non-cognizable|According)\b")


@dataclass
class Row:
    """One row of the table, accumulated across however many lines it spans."""

    page: int
    cells: dict[str, list[str]] = field(default_factory=dict)

    def add(self, column: str, text: str) -> None:
        self.cells.setdefault(column, []).append(text)

    def cell(self, column: str) -> str:
        return normalise_whitespace(" ".join(self.cells.get(column, [])))

    @property
    def is_empty(self) -> bool:
        return not any(self.cells.values())


def group_words_into_lines(words: Iterable[dict]) -> list[tuple[float, list[dict]]]:
    """Group words sharing a baseline into ``(top, words)``, left to right."""
    lines: dict[float, list[dict]] = {}
    for word in words:
        for key in lines:
            if abs(word["top"] - key) <= LINE_GROUP_TOLERANCE:
                lines[key].append(word)
                break
        else:
            lines[word["top"]] = [word]
    return [(top, sorted(lines[top], key=lambda w: w["x0"])) for top in sorted(lines)]


def modal_x0(values: Sequence[float]) -> float | None:
    """The left edge the most words share, or ``None`` if too few agree."""
    modes: dict[float, int] = {}
    for value in sorted(values):
        for mode in modes:
            if abs(value - mode) <= ANCHOR_TOLERANCE:
                modes[mode] += 1
                break
        else:
            modes[value] = 1
    if not modes:
        return None
    edge, support = max(modes.items(), key=lambda item: item[1])
    return edge if support >= ANCHOR_MIN_SUPPORT else None


def detect_anchors(
    lines: Sequence[tuple[float, list[dict]]], page_number: int
) -> tuple[float, ...]:
    """
    Measure this page's six column left edges from its own content.

    Columns 3 to 6 are found from the words they open with; columns 1 and 2
    from the two left edges that exist to the left of column 3. See the module
    docstring for why the edges cannot simply be assumed.
    """
    opener_x0: dict[str, list[float]] = {name: [] for name in COLUMNS[2:]}
    for _, line in lines:
        deferred = [w["x0"] for w in line if w["text"] == DEFERRED_OPENER]
        if deferred:
            opener_x0["cognizable"].append(deferred[0])
        if len(deferred) > 1:
            opener_x0["bailable"].append(deferred[1])
        for word in line:
            if word["text"] in PUNISHMENT_OPENERS:
                opener_x0["punishment"].append(word["x0"])
            elif word["text"] in COGNIZABLE_OPENERS:
                opener_x0["cognizable"].append(word["x0"])
            elif word["text"] in BAILABLE_OPENERS:
                opener_x0["bailable"].append(word["x0"])

    anchors: dict[str, float | None] = {
        name: modal_x0(opener_x0[name]) for name in ("punishment", "cognizable", "bailable")
    }

    # The court column is the only one whose openers are ordinary words, so it
    # is bounded below by the column that precedes it.
    bailable = anchors["bailable"] or DEFAULT_ANCHORS[4]
    words = [w for _, line in lines for w in line]
    anchors["triable_by"] = modal_x0([
        w["x0"] for w in words if w["text"] in COURT_OPENERS and w["x0"] > bailable + 10
    ])

    punishment = anchors["punishment"] or DEFAULT_ANCHORS[2]
    anchors["section"] = modal_x0(
        [w["x0"] for w in words if w["x0"] < SECTION_COLUMN_MAX_X0]
    )
    anchors["offence"] = modal_x0([
        w["x0"] for w in words if SECTION_COLUMN_MAX_X0 <= w["x0"] < punishment - 10
    ])

    resolved = []
    for index, name in enumerate(COLUMNS):
        if anchors[name] is None:
            logger.warning(
                f"page {page_number}: no evidence for the {name} column; "
                f"falling back to {DEFAULT_ANCHORS[index]}"
            )
        resolved.append(anchors[name] if anchors[name] is not None else DEFAULT_ANCHORS[index])

    if any(b - a < 25 for a, b in pairwise(resolved)):
        logger.warning(f"page {page_number}: implausible column edges {resolved}; using defaults")
        return DEFAULT_ANCHORS
    return tuple(resolved)


def column_index(x0: float, anchors: Sequence[float]) -> int:
    """The column a run leader sits in: the rightmost anchor at or left of it."""
    return max(i for i, anchor in enumerate(anchors) if x0 >= anchor - ON_ANCHOR)


def split_into_runs(line: Sequence[dict], anchors: Sequence[float]) -> list[list[dict]]:
    """
    Break one typeset line wherever a column starts.

    A break is a horizontal gap too wide to be a space, or a word reaching the
    anchor of the column after the run's own. Both are needed -- see the module
    docstring for the row each one rescues.
    """
    runs: list[list[dict]] = []
    leader_column = 0
    previous_x1: float | None = None

    for word in line:
        next_anchor = (
            anchors[leader_column + 1] if leader_column + 1 < len(anchors) else None
        )
        crossed = next_anchor is not None and word["x0"] >= next_anchor
        wide_gap = previous_x1 is not None and word["x0"] - previous_x1 > RUN_GAP
        if not runs or crossed or wide_gap:
            runs.append([word])
            leader_column = column_index(word["x0"], anchors)
        else:
            runs[-1].append(word)
        previous_x1 = word["x1"]
    return runs


def cells_of_line(line: Sequence[dict], anchors: Sequence[float]) -> dict[str, str]:
    """Reduce one typeset line to ``{column: text}``."""
    cells: dict[str, list[str]] = {}
    for run in split_into_runs(line, anchors):
        column = COLUMNS[column_index(run[0]["x0"], anchors)]
        cells.setdefault(column, []).extend(w["text"] for w in run)
    return {column: " ".join(parts) for column, parts in cells.items()}


def body_lines(page: pdfplumber.page.Page) -> tuple[list[tuple[float, list[dict]]], tuple[float, ...]]:
    """
    Return the table lines on one page, plus that page's column anchors.

    Everything above the ``1 2 3 4 5 6`` column-number row is running head,
    schedule heading or the explanatory notes -- full-width prose that would
    otherwise be shredded across six columns.
    """
    words = [
        w
        for w in page.extract_words(x_tolerance=X_TOLERANCE)
        if w["top"] > HEADER_MAX_TOP and w["x1"] - w["x0"] < MAX_WORD_WIDTH
    ]
    lines = group_words_into_lines(words)

    start = None
    for index, (_, line) in enumerate(lines):
        if [w["text"] for w in line] == COLUMN_NUMBER_ROW:
            start = index + 1
            break
    if start is None:
        logger.warning(f"page {page.page_number}: no column-number row; skipped")
        return [], DEFAULT_ANCHORS

    table = lines[start:]
    anchors = detect_anchors(table, page.page_number)
    logger.debug(f"page {page.page_number}: anchors {anchors}")
    return table, anchors


def starts_a_row(cells: dict[str, str], current: Row | None) -> bool:
    """
    Whether this line opens a new row, by asking whether it refills a full cell.

    See the module docstring: neither vertical gaps nor the section column can
    be trusted here. A line belongs to the row above it until it carries a cell
    that row already holds -- a second section number, or a second
    classification. Works unchanged across page breaks, where there is no
    vertical gap to read at all.
    """
    if current is None:
        return True
    if cells.get("section") and current.cell("section"):
        return True
    return bool(
        CLASSIFICATION_START.match(cells.get("cognizable", ""))
        and current.cell("cognizable")
    )


def collect_rows(pdf: pdfplumber.PDF) -> list[Row]:
    """Walk Part I of the Schedule and accumulate its rows."""
    rows: list[Row] = []
    current: Row | None = None
    started = False

    for page in pdf.pages:
        text = page.extract_text(x_tolerance=X_TOLERANCE) or ""
        if not started:
            if not PART_I_HEADING.search(text):
                continue
            started = True

        stop_at = None
        table, anchors = body_lines(page)

        for _, line in table:
            joined = " ".join(w["text"] for w in line)
            if PART_II_HEADING.search(joined):
                stop_at = True
                break

            cells = cells_of_line(line, anchors)
            if starts_a_row(cells, current):
                current = Row(page=page.page_number)
                rows.append(current)

            for column, value in cells.items():
                current.add(column, value)

        if stop_at:
            logger.info(f"page {page.page_number}: Part II heading ends Part I")
            break

    return [row for row in rows if not row.is_empty]


def normalise_section(value: str) -> str | None:
    """``"58 (a)"`` -> ``"58(a)"``. Anything else is not a section number."""
    match = SECTION_NUMBER.match(value.strip())
    if not match:
        return None
    number, clauses = match.groups()
    return number + re.sub(r"\s+", "", clauses)


def classify(value: str, vocabulary: dict[str, bool]) -> bool | None:
    """
    Resolve a classification cell to a boolean, or leave it unresolved.

    The cell is only resolved when it says exactly one of the two words. Rows
    that defer to another offence ("According as offence abetted is cognizable
    or non-cognizable") are genuinely unresolvable from this table and are left
    as ``None`` with the schedule's own wording preserved beside them.
    """
    cleaned = value.strip().rstrip(".").strip().lower()
    return vocabulary.get(cleaned)


def build_records(rows: list[Row]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Turn accumulated rows into records, dropping any that cannot be resolved."""
    records: list[dict[str, Any]] = []
    counts = {"rows": len(rows), "no_section": 0, "no_offence": 0, "variants": 0}
    section: str | None = None
    variant = 0

    for row in rows:
        raw_section = row.cell("section")
        offence = row.cell("offence")

        if raw_section:
            resolved = normalise_section(raw_section)
            if resolved is None:
                counts["no_section"] += 1
                logger.warning(
                    f"page {row.page}: unparseable section {raw_section!r} "
                    f"({offence[:50]!r}) - dropped"
                )
                section = None
                continue
            section, variant = resolved, 0
        elif section is None:
            # A row before any section number: front matter, not an offence.
            counts["no_section"] += 1
            continue
        else:
            # A second classification of the same section -- see module docstring.
            variant += 1
            counts["variants"] += 1

        if not offence:
            counts["no_offence"] += 1
            logger.warning(f"page {row.page}: section {section} has no offence text - dropped")
            continue

        cognizable = row.cell("cognizable")
        bailable = row.cell("bailable")
        records.append({
            "id": f"bns_{section}" + (f"_v{variant}" if variant else ""),
            "section": section,
            "act": "Bharatiya Nyaya Sanhita",
            "short_name": "BNS",
            "variant": variant,
            "offence": offence,
            "punishment": row.cell("punishment"),
            "cognizable": classify(cognizable, COGNIZABLE_VALUES),
            "cognizable_text": cognizable,
            "bailable": classify(bailable, BAILABLE_VALUES),
            "bailable_text": bailable,
            "triable_by": row.cell("triable_by"),
            "source": "First Schedule, Bharatiya Nagarik Suraksha Sanhita, 2023",
            "source_url": BNSS.url,
            "page": row.page,
        })

    return records, counts


def ingest(force_download: bool) -> list[dict[str, Any]]:
    pdf_path = download_pdf(BNSS, force_download)
    logger.info(f"parsing the First Schedule of {pdf_path.name}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        rows = collect_rows(pdf)
    records, counts = build_records(rows)

    unresolved_c = sum(1 for r in records if r["cognizable"] is None)
    unresolved_b = sum(1 for r in records if r["bailable"] is None)
    logger.info(
        f"{len(records)} offences from {counts['rows']} rows "
        f"({counts['variants']} section variants, "
        f"{counts['no_section'] + counts['no_offence']} dropped)"
    )
    logger.info(
        f"unresolved classifications: {unresolved_c} cognizable, {unresolved_b} bailable "
        "(rows that defer to the offence abetted)"
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    logger.info(f"wrote {OUT_PATH.relative_to(DATA_DIR.parent)}")
    return records


def print_report(records: list[dict[str, Any]]) -> None:
    for record in records:
        print(
            f"{record['id']:<14} {record['offence'][:44]:<44} "
            f"C={record['cognizable']!s:<5} B={record['bailable']!s:<5} "
            f"{record['triable_by'][:32]}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--report", action="store_true", help="dump every parsed row")
    args = parser.parse_args()

    try:
        records = ingest(args.force_download)
    except Exception as exc:
        logger.error(f"ingestion failed: {exc}")
        return 1

    if args.report:
        print_report(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
