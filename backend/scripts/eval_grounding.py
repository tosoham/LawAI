#!/usr/bin/env python
"""
Grounding evaluation harness — the counterpart to ``eval_retrieval.py``.

Retrieval evaluation answers "did the right law come back?". This answers the
question after it: "given what came back, did the system say only things it
could support, and did it refuse when it could not?" The two are independent.
Perfect retrieval still permits a fluent invented holding, and the golden
retrieval set cannot see that, because it never reads the answer.

Runs the golden set through ``GroundedAnswerService``, aggregates
``services.answer_metrics``, and writes a diffable report to ``backend/eval/``.

    python scripts/eval_grounding.py                       # full run
    python scripts/eval_grounding.py --label grounding     # name the run
    python scripts/eval_grounding.py --compare grounding   # diff against a run
    python scripts/eval_grounding.py --class judgement     # one class only
    python scripts/eval_grounding.py --limit 5             # smoke test
    python scripts/eval_grounding.py --adversarial-only    # the abstention gate

**This costs real model calls** — 75 queries, each up to two generations when a
claim fails verification and is regenerated. It is a gate to run deliberately
before a release, not on every commit, and it needs ``AIML_API_KEY``.

## The gates, and why there are three rather than one

``unsupported_total == 0`` over the answerable set is the headline, but on its
own it is worthless: a system that abstains on every question emits no claims,
so nothing can be unsupported, and it scores perfectly. That is not a
hypothetical failure mode — it is the direction every safety change pushes, and
it is invisible unless something holds the other end down.

So the gate has three parts, and the second is what makes the first mean
anything:

1. **No unsupported claim survives on any answerable query.** Totalled, never
   averaged: one bad claim in seventy-five answers is one too many, and a mean
   rounds it into invisibility.
2. **The answerable set must not collapse into abstention.** A ceiling on how
   many of the 69 may refuse. Without this, gate 1 is trivially satisfiable by
   refusing everything.
3. **Every adversarial query must abstain.** All six. These are the questions
   with no corpus basis at all, where a fluent answer is the worst thing this
   system could produce.

## What is *not* asserted, and why

Not exact float equality between runs. Synthesis is a sampled model call, so
claim counts and phrasing vary; asserting stability would produce a flaky gate
that gets disabled, which is worse than no gate. The invariants above hold
regardless of sampling because they are properties of the *verifier*, which is
deterministic — every check is a lookup against committed data. The means
(``grounding_rate``, ``verbatim_fidelity``, ``inference_share``) are reported
for the ``--compare`` diff and trend-watched by a human, not gated.

## How much a number has to move before it means anything

**Measured, because guessing at this is how a change gets credited or blamed
for sampling noise.** Two runs of the identical configuration, back to back:

    run                claims/ans  unsup  abstained   judgement  plain
    grounding                3.29     20          9          13      2
    grounding (repeat)       3.46     18          6           6      7

So on unchanged code the overall unsupported count moved by 2, abstentions by
3, and the **per-class counts by 7** -- larger than most changes worth making.
The classes are small (12 judgement queries, 25 plain), a single answer carries
several claims, and one answer flipping between attempting and abstaining moves
its whole class.

Read accordingly: a per-class swing under about 7 is not evidence of anything,
and a single A/B run of this harness cannot settle a retrieval change. The
*deterministic* eval is what decides those -- ``eval_retrieval.py`` embeds and
ranks with no sampling anywhere, so its diffs are exact. This harness answers a
different question, which is whether the grounding invariants still hold, and
those are gated precisely because they do not depend on sampling.
"""
import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Rooted at backend/, matching pytest.ini's pythonpath.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.answer_metrics import aggregate
from services.grounded_answer import get_grounded_answer_service

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
GOLDEN_PATH = BACKEND_DIR / "tests" / "fixtures" / "golden_queries.json"
EVAL_DIR = BACKEND_DIR / "eval"

# The three statute collections. Adversarial queries are asked against all of
# them, because the point of an adversarial query is that no collection holds
# the answer, and searching only one would make abstention too easy to earn.
CORPUS_COLLECTIONS = ["bns_sections", "bnss_sections", "bsa_sections"]

# How many of the 69 answerable queries may abstain before the run fails.
#
# Not zero. Abstention is sometimes the right answer to a query in this set --
# it is a *retrieval* golden set, and a handful of its entries ask about
# material that is present but thin. A hard zero would make the gate fight the
# behaviour the system is supposed to have. The ceiling exists to catch a
# collapse, not to forbid judgement.
MAX_ANSWERABLE_ABSTENTIONS = 7

# Concurrent in-flight queries. The provider is the bottleneck and the work is
# entirely I/O-bound; 4 keeps a full run to a few minutes without tripping rate
# limits. Drop to 1 when a run needs to be read in order.
DEFAULT_CONCURRENCY = 4


def load_golden() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(GOLDEN_PATH.read_text())
    return payload["queries"], payload["adversarial"]["queries"]


def rejections(result: Any) -> list[dict[str, str]]:
    """
    The claims the verifier threw out, with the reason it gave.

    Recorded per query rather than counted, because the count alone is not
    actionable. When this gate fails, the next question is always "which claim,
    and why", and re-running to find out costs another full set of model calls.

    Read from the trace rather than by indexing ``result.structured`` with
    ``verdict.index``: that index addresses the claim list *before* the failures
    were removed, so against the surviving list it silently resolves to a
    different claim -- reporting an innocent claim as the rejected one, which is
    worse than reporting nothing.
    """
    for step in result.trace.get("steps", []):
        if step.get("step") == "verify":
            return [
                {
                    "claim": item["text"][:200],
                    "epistemic_class": item["epistemic_class"],
                    "reason": item["reason"],
                }
                for item in step.get("rejected", [])
            ]
    return []


def run_one(entry: dict[str, Any], adversarial: bool) -> dict[str, Any]:
    """Answer one query and reduce the result to a scoreable row."""
    service = get_grounded_answer_service()
    collection = (
        CORPUS_COLLECTIONS if adversarial else entry.get("collection", "bns_sections")
    )

    try:
        result = service.answer(entry["query"], collection)
    except Exception as exc:
        # A crash is a result, not a reason to lose the other 74 rows. It is
        # reported as an error row and fails the run below.
        logger.error("%s raised: %s", entry["id"], exc)
        return {
            "id": entry["id"],
            "class": entry.get("class", "adversarial"),
            "query": entry["query"],
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "id": entry["id"],
        "class": entry.get("class", "adversarial"),
        "query": entry["query"],
        "abstained": result.abstained,
        "metrics": result.metrics.to_dict(),
        "rejected": rejections(result),
        "answer_head": result.answer[:200],
    }


def run(
    entries: list[dict[str, Any]], adversarial: bool, concurrency: int
) -> list[dict[str, Any]]:
    if not entries:
        return []
    # Build the singletons on this thread first. The service accessors are
    # plain lazy globals with no lock, and chromadb's
    # PersistentClient additionally creates its tenant on first connect -- so N
    # threads arriving at an unbuilt singleton together race, and chromadb loses
    # the race loudly with "Could not connect to tenant default_tenant".
    # Warming is not an optimisation; without it a concurrent run cannot start.
    get_grounded_answer_service()

    if concurrency <= 1:
        return [run_one(entry, adversarial) for entry in entries]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(lambda e: run_one(e, adversarial), entries))


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate rows, overall and per class.

    Per class for the same reason ``eval_retrieval.py`` reports per class: they
    are distinct failure modes. A judgement query and a citation query fail in
    different ways, and one mean over both hides which moved.
    """
    scored = [r for r in rows if "metrics" in r]
    if not scored:
        return {"n": 0}

    def metrics_of(subset):
        from services.answer_metrics import AnswerMetrics

        return [AnswerMetrics(**_metric_fields(r["metrics"])) for r in subset]

    by_class: dict[str, Any] = {}
    grouped: dict[str, list] = defaultdict(list)
    for row in scored:
        grouped[row["class"]].append(row)
    for name, subset in sorted(grouped.items()):
        by_class[name] = aggregate(metrics_of(subset))

    return {"overall": aggregate(metrics_of(scored)), "by_class": by_class}


def _metric_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """``AnswerMetrics.to_dict`` adds ``clean``, which is a property, not a
    field. Round-tripping without dropping it raises."""
    return {k: v for k, v in payload.items() if k != "clean"}


def check_gates(
    answerable: list[dict[str, Any]], adversarial: list[dict[str, Any]]
) -> list[str]:
    """Return the failures. Empty means the run passes."""
    failures = []

    errored = [r["id"] for r in answerable + adversarial if "error" in r]
    if errored:
        failures.append(f"{len(errored)} quer(ies) raised: {', '.join(errored)}")

    if answerable:
        unsupported = [
            (r["id"], r["metrics"]["unsupported"])
            for r in answerable
            if r.get("metrics", {}).get("unsupported")
        ]
        if unsupported:
            detail = ", ".join(f"{qid}({n})" for qid, n in unsupported)
            failures.append(f"unsupported claims survived on: {detail}")

        abstained = [r["id"] for r in answerable if r.get("abstained")]
        if len(abstained) > MAX_ANSWERABLE_ABSTENTIONS:
            failures.append(
                f"{len(abstained)} of {len(answerable)} answerable queries abstained "
                f"(ceiling {MAX_ANSWERABLE_ABSTENTIONS}): {', '.join(abstained)}"
            )

    if adversarial:
        answered = [r["id"] for r in adversarial if not r.get("abstained")]
        if answered:
            failures.append(
                f"adversarial quer(ies) were answered instead of refused: "
                f"{', '.join(answered)}"
            )

    return failures


def print_report(report: dict[str, Any]) -> None:
    answerable = report["answerable"]
    if answerable.get("summary", {}).get("n") != 0 and answerable["rows"]:
        summary = answerable["summary"]
        print(f"\nanswerable  n={len(answerable['rows'])}")
        print("-" * 78)
        header = f"{'class':<16}{'n':>4}{'claims':>9}{'ground':>9}{'verbatim':>10}{'infer':>8}{'unsup':>7}{'abst':>6}"
        print(header)
        for name, agg in summary["by_class"].items():
            print(_row(name, agg))
        print("-" * 78)
        print(_row("OVERALL", summary["overall"]))

    adversarial = report["adversarial"]["rows"]
    if adversarial:
        refused = sum(1 for r in adversarial if r.get("abstained"))
        print(f"\nadversarial  {refused}/{len(adversarial)} abstained")
        for row in adversarial:
            mark = "ok " if row.get("abstained") else "ANSWERED"
            print(f"  {mark} [{row['id']}] {row['query'][:60]}")
            if not row.get("abstained"):
                print(f"       -> {row.get('answer_head', '')[:120]}")

    rejected = [r for r in answerable["rows"] if r.get("rejected")]
    if rejected:
        print(f"\nClaims removed by the verifier ({sum(len(r['rejected']) for r in rejected)}):")
        for row in rejected:
            for item in row["rejected"]:
                print(f"  [{row['id']:<4}] ({item['epistemic_class']}) {item['claim'][:70]}")
                print(f"         reason: {item['reason'][:100]}")


def _row(name: str, agg: dict[str, Any]) -> str:
    return (
        f"{name:<16}{agg['n']:>4}{agg['claims_per_answer']:>9.2f}"
        f"{agg['grounding_rate']:>9.3f}{agg['verbatim_fidelity']:>10.3f}"
        f"{agg['inference_share']:>8.3f}{agg['unsupported_total']:>7d}"
        f"{agg['abstained']:>6d}"
    )


def print_comparison(current: dict[str, Any], baseline: dict[str, Any]) -> None:
    """Diff two runs. Reported, not gated — synthesis is sampled, so movement
    here is a prompt for a human to look, not a build failure."""
    now = current["answerable"].get("summary", {}).get("overall")
    was = baseline["answerable"].get("summary", {}).get("overall")
    if not now or not was:
        print("\nNo comparable answerable summary in one of the runs.")
        return

    print("\nvs baseline (reported, not gated)")
    print("-" * 50)
    for metric in (
        "claims_per_answer",
        "grounding_rate",
        "verbatim_fidelity",
        "inference_share",
        "unsupported_total",
        "abstained",
    ):
        print(f"  {metric:<28}{now[metric] - was[metric]:>+10.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="grounding-latest", help="name for this run's report")
    parser.add_argument("--compare", help="label of an earlier run to diff against")
    parser.add_argument("--class", dest="cls", help="score only one query class")
    parser.add_argument("--limit", type=int, help="first N answerable queries (smoke test)")
    parser.add_argument("--adversarial-only", action="store_true", help="run the abstention gate alone")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()

    if not os.getenv("AIML_API_KEY"):
        print(
            "AIML_API_KEY is not set. This harness makes real model calls -- "
            "there is nothing meaningful to measure without one.",
            file=sys.stderr,
        )
        return 2

    answerable_entries, adversarial_entries = load_golden()
    if args.cls:
        answerable_entries = [e for e in answerable_entries if e["class"] == args.cls]
    if args.limit:
        answerable_entries = answerable_entries[: args.limit]
    if args.adversarial_only:
        answerable_entries = []

    print(
        f"Running {len(answerable_entries)} answerable + {len(adversarial_entries)} "
        f"adversarial queries at concurrency {args.concurrency}. This makes real "
        f"model calls and will take a few minutes."
    )

    answerable_rows = run(answerable_entries, False, args.concurrency)
    adversarial_rows = run(adversarial_entries, True, args.concurrency)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "class_filter": args.cls,
            "limit": args.limit,
            "adversarial_only": args.adversarial_only,
            "max_answerable_abstentions": MAX_ANSWERABLE_ABSTENTIONS,
        },
        "answerable": {"rows": answerable_rows, "summary": summarise(answerable_rows)},
        "adversarial": {
            "rows": adversarial_rows,
            "abstained": sum(1 for r in adversarial_rows if r.get("abstained")),
            "n": len(adversarial_rows),
        },
    }

    print_report(report)

    if args.compare:
        path = EVAL_DIR / f"{args.compare}.json"
        if path.exists():
            print_comparison(report, json.loads(path.read_text()))
        else:
            print(f"\nNo baseline at {path}", file=sys.stderr)

    failures = check_gates(answerable_rows, adversarial_rows)
    report["gate"] = {"passed": not failures, "failures": failures}

    EVAL_DIR.mkdir(exist_ok=True)
    out = EVAL_DIR / f"{args.label}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {out.relative_to(BACKEND_DIR)}")

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
