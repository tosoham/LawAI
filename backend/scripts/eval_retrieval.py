#!/usr/bin/env python
"""
Retrieval evaluation harness.

Scores the golden query set in tests/fixtures/golden_queries.json against the
live vector store and writes a diffable JSON report to backend/eval/.

This exists so retrieval changes can be *proved* rather than asserted. The
project has already shipped one retrieval belief that turned out to be wrong
(that a BM25 hybrid would fix the anticipatory-bail miss — it would not, because
the term is absent from the section text), and the only reason that surfaced was
measurement. Anything touching retrieval should be run through here before and
after.

Usage:

    python scripts/eval_retrieval.py                      # current config
    python scripts/eval_retrieval.py --no-expand          # expansion ablation
    python scripts/eval_retrieval.py --rerank             # cross-encoder on top
    python scripts/eval_retrieval.py --no-hybrid          # dense only, no BM25
    python scripts/eval_retrieval.py --label baseline     # name the run
    python scripts/eval_retrieval.py --compare baseline   # diff against a run
    python scripts/eval_retrieval.py --class term_of_art  # one class only

Results are per **class**, not just an overall average: the classes are distinct
failure modes and a mean over them hides which one regressed.
"""
import argparse
import json
import logging
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Rooted at backend/, matching pytest.ini's pythonpath.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.vector_service import get_vector_service

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
GOLDEN_PATH = BACKEND_DIR / "tests" / "fixtures" / "golden_queries.json"
EVAL_DIR = BACKEND_DIR / "eval"

#: Per-class floors, checked by --gate. Set below the committed baseline, not
#: at it: this harness is deterministic, but a corpus change moves every class
#: a little and a gate that fires on noise gets removed. These are "something
#: is wrong", not "something changed" -- use --compare for that.
#:
#: Per class rather than overall, because an overall mean hides a class. The
#: term_of_art regression in CHALLENGES 3.8 cost 0.250 of recall@3 in one class
#: while the overall moved 0.029, which looks like nothing.
FLOORS: dict[str, dict[str, float]] = {
    "citation": {"recall@3": 0.95, "r_precision": 0.90},
    "judgement": {"recall@3": 0.85, "r_precision": 0.55},
    "plain": {"recall@3": 0.95, "r_precision": 0.80},
    "repealed_code": {"recall@3": 0.85, "r_precision": 0.85},
    "term_of_art": {"recall@3": 0.85, "r_precision": 0.75},
}
OVERALL_FLOORS = {"recall@3": 0.95, "map": 0.85, "mrr": 0.88}

# Retrieve deep enough to score recall@10 while staying cheap.
RETRIEVE_K = 20
# The k values reported. 3 is what a user effectively sees; 10 is what a
# reranker would have to work with.
REPORT_AT = (1, 3, 5, 10)


def result_key(collection: str, metadata: dict[str, Any]) -> str | None:
    """
    Reduce a retrieved chunk to the id the golden set expects.

    Statute collections are keyed by section number; judgements by their parent
    document id, because a judgement is indexed as many chunks and any of them
    counts as finding the case.
    """
    if collection == "sc_judgements":
        return metadata.get("parent_id") or metadata.get("id")
    return metadata.get("section_number")


def dedupe(keys: list[str]) -> list[str]:
    """
    Collapse repeated parents, preserving rank order.

    A long section occupies several chunks, so an undeduplicated top-10 can be
    one section ten times. Ranking metrics would then be measuring chunking, not
    retrieval.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def score_query(ranked: list[str], expected: list[str]) -> dict[str, Any]:
    """
    Score one query, several ways, because no single number says enough.

    recall@k      did *any* expected id appear in the top k. What a reader
                  experiences: did the right law come back at all.
    coverage@k    what *share* of the expected ids appeared in the top k. The
                  honest recall for a multi-answer query -- recall@3 is 1.000
                  the moment one of four authorities lands, which flatters.
    precision@k   share of the top k that was expected. **Read with care**:
                  where a query names one expected id, precision@3 cannot
                  exceed 0.333 whatever retrieval does, so a low number there
                  is arithmetic rather than a finding. Reported because it is
                  standard and because it is meaningful for the widened
                  judgement queries; `r_precision` below is the comparable one.
    r_precision   precision at k = the number of expected ids. Scores 1.0 for a
                  perfect ranking whatever the query's shape, so it is the one
                  precision figure that compares across classes.
    average_precision  precision at each hit, averaged -- rewards ranking *all*
                  the correct authorities highly, not just the first. MAP is the
                  mean of these.
    rr            reciprocal rank of the first expected id (0 if absent).
    ndcg@10       graded, with the ideal computed over however many ids the
                  query actually expects.
    """
    wanted = set(expected)
    positions = [i for i, key in enumerate(ranked) if key in wanted]
    found = len(positions)
    total = len(wanted)

    rr = 1.0 / (positions[0] + 1) if positions else 0.0

    dcg = sum(1.0 / math.log2(i + 2) for i in positions if i < 10)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(total, 10)))
    ndcg = dcg / ideal if ideal else 0.0

    # Precision at each rank where something correct was found, averaged over
    # the number expected. A query whose authorities land at 1, 2 and 3 scores
    # 1.0; the same three at 4, 8 and 12 scores far less, which is the point.
    average_precision = (
        sum((rank + 1) / (position + 1) for rank, position in enumerate(positions))
        / total
        if total
        else 0.0
    )

    r_precision = (
        len([p for p in positions if p < total]) / total if total else 0.0
    )

    return {
        "recall": {f"@{k}": bool(positions and positions[0] < k) for k in REPORT_AT},
        "coverage": {
            f"@{k}": (len([p for p in positions if p < k]) / total if total else 0.0)
            for k in REPORT_AT
        },
        "precision": {
            f"@{k}": len([p for p in positions if p < k]) / k for k in REPORT_AT
        },
        "r_precision": r_precision,
        "average_precision": average_precision,
        "rr": rr,
        "ndcg@10": ndcg,
        "first_rank": (positions[0] + 1) if positions else None,
        "expected_count": total,
        "found": found,
        "returned": ranked[:10],
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Mean the per-query scores. Empty input scores zero, not NaN.

    Everything is meaned per class as well as overall, and the per-class table
    is the one to read. The `term_of_art` regression in `CHALLENGES 3.8` cost
    0.250 of recall@3 in one class while the overall mean moved 0.029 -- a
    number small enough to look like noise, hiding a quarter of a class.
    """
    if not rows:
        return {"n": 0}
    n = len(rows)
    summary: dict[str, Any] = {"n": n}
    for k in REPORT_AT:
        summary[f"recall@{k}"] = round(
            sum(r["score"]["recall"][f"@{k}"] for r in rows) / n, 4
        )
        summary[f"coverage@{k}"] = round(
            sum(r["score"]["coverage"][f"@{k}"] for r in rows) / n, 4
        )
        summary[f"precision@{k}"] = round(
            sum(r["score"]["precision"][f"@{k}"] for r in rows) / n, 4
        )
    summary["r_precision"] = round(
        sum(r["score"]["r_precision"] for r in rows) / n, 4
    )
    summary["map"] = round(
        sum(r["score"]["average_precision"] for r in rows) / n, 4
    )
    # F1 over coverage rather than recall@5: recall@5 is a hit/miss flag, and
    # an F1 built from a boolean and a fraction is not a harmonic mean of
    # anything. Coverage and precision are both shares of the same ranking.
    coverage5 = summary["coverage@5"]
    precision5 = summary["precision@5"]
    summary["f1@5"] = round(
        2 * coverage5 * precision5 / (coverage5 + precision5)
        if (coverage5 + precision5)
        else 0.0,
        4,
    )
    summary["mrr"] = round(sum(r["score"]["rr"] for r in rows) / n, 4)
    summary["ndcg@10"] = round(sum(r["score"]["ndcg@10"] for r in rows) / n, 4)
    # Where the first correct result landed, so a slip from rank 1 to rank 2 is
    # visible before it crosses a k boundary and becomes a cliff.
    ranks = [r["score"]["first_rank"] for r in rows if r["score"]["first_rank"]]
    summary["first_rank"] = {
        "1": sum(1 for r in ranks if r == 1),
        "2-3": sum(1 for r in ranks if 2 <= r <= 3),
        "4-10": sum(1 for r in ranks if 4 <= r <= 10),
        "11+": sum(1 for r in ranks if r > 10),
        "absent": n - len(ranks),
    }
    return summary


def run(
    expand: bool,
    only_class: str | None,
    top_k: int,
    rerank: bool = False,
    hybrid: bool = True,
) -> dict[str, Any]:
    """Score every golden query against the current vector store."""
    golden = json.loads(GOLDEN_PATH.read_text())
    service = get_vector_service()

    rows: list[dict[str, Any]] = []
    for query in golden["queries"]:
        if only_class and query["class"] != only_class:
            continue

        results = service.search(
            query["collection"],
            query["query"],
            top_k=top_k,
            expand=expand,
            rerank=rerank,
            hybrid=hybrid,
        )
        ranked = dedupe(
            [result_key(query["collection"], m) for m in results["metadatas"]]
        )
        rows.append({
            "id": query["id"],
            "class": query["class"],
            "query": query["query"],
            "collection": query["collection"],
            "expected": query["expected"],
            "score": score_query(ranked, query["expected"]),
        })

    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_class[row["class"]].append(row)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "expand": expand,
            "top_k": top_k,
            "rerank": rerank,
            "hybrid": hybrid,
            "class_filter": only_class,
        },
        "overall": aggregate(rows),
        "by_class": {name: aggregate(items) for name, items in sorted(by_class.items())},
        "queries": rows,
    }


def print_report(report: dict[str, Any]) -> None:
    config = report["config"]
    print(
        f"\nexpand={config['expand']}  top_k={config['top_k']}  "
        f"rerank={config.get('rerank', False)}  "
        f"hybrid={config.get('hybrid', False)}"
    )
    header = (
        f"{'class':<15}{'n':>3}{'R@1':>7}{'R@3':>7}{'Cov@5':>7}"
        f"{'P@5':>7}{'R-Prec':>8}{'F1@5':>7}{'MAP':>7}{'MRR':>7}{'nDCG':>7}"
    )

    def row(name: str, summary: dict[str, Any]) -> str:
        return (
            f"{name:<15}{summary['n']:>3}{summary['recall@1']:>7.3f}"
            f"{summary['recall@3']:>7.3f}{summary['coverage@5']:>7.3f}"
            f"{summary['precision@5']:>7.3f}{summary['r_precision']:>8.3f}"
            f"{summary['f1@5']:>7.3f}{summary['map']:>7.3f}"
            f"{summary['mrr']:>7.3f}{summary['ndcg@10']:>7.3f}"
        )

    print("-" * len(header))
    print(header)
    for name, summary in report["by_class"].items():
        print(row(name, summary))
    overall = report["overall"]
    print("-" * len(header))
    print(row("OVERALL", overall))

    # P@5 is capped by arithmetic where a query expects one id -- 0.200 is the
    # ceiling there, not a finding. R-Prec is the comparable figure.
    print(
        "\nP@5 is bounded by how many ids a query expects (0.200 for a single-"
        "answer query,\nwhatever retrieval does). R-Prec is precision at that "
        "count and compares across classes."
    )

    ranks = overall["first_rank"]
    print(
        f"\nfirst correct result at rank:  1: {ranks['1']}   2-3: {ranks['2-3']}"
        f"   4-10: {ranks['4-10']}   11+: {ranks['11+']}   absent: {ranks['absent']}"
    )

    missed = [r for r in report["queries"] if r["score"]["first_rank"] is None]
    if missed:
        print(f"\nNot found in top {RETRIEVE_K} ({len(missed)}):")
        for row in missed:
            print(f"  [{row['class']:<13}] {row['query'][:58]:<58} want {row['expected']}")


def check_gate(report: dict[str, Any]) -> list[str]:
    """
    Floors that mean "something is wrong", not "something changed".

    Deliberately below the committed baseline. A gate set *at* the current
    numbers fires on any corpus change and gets switched off within a month,
    which is worse than no gate -- the same reasoning that keeps
    `eval_grounding.py` from asserting float equality between runs.
    """
    failures: list[str] = []
    for name, floors in FLOORS.items():
        summary = report["by_class"].get(name)
        if not summary:
            continue
        for metric, floor in floors.items():
            value = summary.get(metric, 0.0)
            if value < floor:
                failures.append(f"{name} {metric} {value:.3f} < {floor:.3f}")
    for metric, floor in OVERALL_FLOORS.items():
        value = report["overall"].get(metric, 0.0)
        if value < floor:
            failures.append(f"OVERALL {metric} {value:.3f} < {floor:.3f}")
    return failures


def print_comparison(current: dict[str, Any], baseline: dict[str, Any]) -> None:
    """Diff two runs. Regressions are what this is for."""
    print("\nvs baseline")
    print("-" * 62)
    print(
        f"{'class':<16}{'R@3':>9}{'Cov@5':>9}{'R-Prec':>9}"
        f"{'MAP':>9}{'MRR':>9}{'nDCG':>9}"
    )
    names = sorted(set(current["by_class"]) | set(baseline["by_class"]))
    for name in [*names, "OVERALL"]:
        now = current["overall"] if name == "OVERALL" else current["by_class"].get(name)
        was = baseline["overall"] if name == "OVERALL" else baseline["by_class"].get(name)
        if not now or not was:
            continue
        # A metric the baseline predates is shown as "--", not as a rise from
        # zero. The first run after adding one otherwise reports every new
        # column as a large improvement, which is a lie that reads as a win.
        cells = "".join(
            f"{now[m] - was[m]:>+9.3f}" if m in now and m in was else f"{'--':>9}"
            for m in ("recall@3", "coverage@5", "r_precision", "map", "mrr", "ndcg@10")
        )
        print(f"{name:<16}{cells}")

    regressed = [
        row["id"]
        for row in current["queries"]
        if (base := next((b for b in baseline["queries"] if b["id"] == row["id"]), None))
        and base["score"]["first_rank"] is not None
        and (
            row["score"]["first_rank"] is None
            or row["score"]["first_rank"] > base["score"]["first_rank"]
        )
    ]
    if regressed:
        print(f"\nRegressed queries ({len(regressed)}): {', '.join(regressed)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="latest", help="name for this run's report file")
    parser.add_argument("--compare", help="label of an earlier run to diff against")
    parser.add_argument("--no-expand", action="store_true", help="disable query expansion")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero if any class falls below its floor",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="reorder the candidate pool with the cross-encoder",
    )
    parser.add_argument(
        "--no-hybrid",
        action="store_true",
        help="dense only; do not fuse a BM25 ranking",
    )
    parser.add_argument("--class", dest="cls", help="score only one query class")
    parser.add_argument("--top-k", type=int, default=RETRIEVE_K)
    args = parser.parse_args()

    report = run(
        expand=not args.no_expand,
        only_class=args.cls,
        top_k=args.top_k,
        rerank=args.rerank,
        hybrid=not args.no_hybrid,
    )
    print_report(report)

    if args.compare:
        path = EVAL_DIR / f"{args.compare}.json"
        if path.exists():
            print_comparison(report, json.loads(path.read_text()))
        else:
            print(f"\nNo baseline at {path}", file=sys.stderr)

    EVAL_DIR.mkdir(exist_ok=True)
    out = EVAL_DIR / f"{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {out.relative_to(BACKEND_DIR)}")

    if args.gate:
        failures = check_gate(report)
        print("\n" + "=" * 50)
        if failures:
            print("GATE FAILED")
            for failure in failures:
                print(f"  - {failure}")
            return 1
        print("GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
