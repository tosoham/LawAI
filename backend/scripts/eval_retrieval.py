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
    Score one query.

    recall@k  did any expected id appear in the top k
    rr        reciprocal rank of the first expected id (0 if absent)
    ndcg@10   graded, so finding two expected sections beats finding one
    """
    wanted = set(expected)
    positions = [i for i, key in enumerate(ranked) if key in wanted]

    rr = 1.0 / (positions[0] + 1) if positions else 0.0

    dcg = sum(1.0 / math.log2(i + 2) for i in positions if i < 10)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(wanted), 10)))
    ndcg = dcg / ideal if ideal else 0.0

    return {
        "recall": {f"@{k}": bool(positions and positions[0] < k) for k in REPORT_AT},
        "rr": rr,
        "ndcg@10": ndcg,
        "first_rank": (positions[0] + 1) if positions else None,
        "returned": ranked[:10],
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean the per-query scores. Empty input scores zero, not NaN."""
    if not rows:
        return {"n": 0}
    n = len(rows)
    summary: dict[str, Any] = {"n": n}
    for k in REPORT_AT:
        summary[f"recall@{k}"] = round(
            sum(r["score"]["recall"][f"@{k}"] for r in rows) / n, 4
        )
    summary["mrr"] = round(sum(r["score"]["rr"] for r in rows) / n, 4)
    summary["ndcg@10"] = round(sum(r["score"]["ndcg@10"] for r in rows) / n, 4)
    return summary


def run(
    expand: bool, only_class: str | None, top_k: int, rerank: bool = False
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
        f"rerank={config.get('rerank', False)}"
    )
    print("-" * 62)
    print(f"{'class':<16}{'n':>4}{'R@1':>8}{'R@3':>8}{'R@10':>8}{'MRR':>8}{'nDCG':>8}")
    for name, summary in report["by_class"].items():
        print(
            f"{name:<16}{summary['n']:>4}{summary['recall@1']:>8.3f}"
            f"{summary['recall@3']:>8.3f}{summary['recall@10']:>8.3f}"
            f"{summary['mrr']:>8.3f}{summary['ndcg@10']:>8.3f}"
        )
    overall = report["overall"]
    print("-" * 62)
    print(
        f"{'OVERALL':<16}{overall['n']:>4}{overall['recall@1']:>8.3f}"
        f"{overall['recall@3']:>8.3f}{overall['recall@10']:>8.3f}"
        f"{overall['mrr']:>8.3f}{overall['ndcg@10']:>8.3f}"
    )

    missed = [r for r in report["queries"] if r["score"]["first_rank"] is None]
    if missed:
        print(f"\nNot found in top {RETRIEVE_K} ({len(missed)}):")
        for row in missed:
            print(f"  [{row['class']:<13}] {row['query'][:58]:<58} want {row['expected']}")


def print_comparison(current: dict[str, Any], baseline: dict[str, Any]) -> None:
    """Diff two runs. Regressions are what this is for."""
    print("\nvs baseline")
    print("-" * 62)
    print(f"{'class':<16}{'R@3':>10}{'MRR':>10}{'nDCG':>10}")
    names = sorted(set(current["by_class"]) | set(baseline["by_class"]))
    for name in [*names, "OVERALL"]:
        now = current["overall"] if name == "OVERALL" else current["by_class"].get(name)
        was = baseline["overall"] if name == "OVERALL" else baseline["by_class"].get(name)
        if not now or not was:
            continue
        cells = "".join(
            f"{now[m] - was[m]:>+10.3f}" for m in ("recall@3", "mrr", "ndcg@10")
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
        "--rerank",
        action="store_true",
        help="reorder the candidate pool with the cross-encoder",
    )
    parser.add_argument("--class", dest="cls", help="score only one query class")
    parser.add_argument("--top-k", type=int, default=RETRIEVE_K)
    args = parser.parse_args()

    report = run(
        expand=not args.no_expand,
        only_class=args.cls,
        top_k=args.top_k,
        rerank=args.rerank,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
