#!/usr/bin/env python
"""
Turn production failures into golden-set candidates.

The half of the loop a machine cannot do. `services/feedback.py` captures
answers that tripped a self-labelling signal -- the system abstained, the
verifier removed claims, retrieval returned nothing -- and each of those says
*something went wrong* without saying what the right answer was. Only a person
can supply that, which is why this prints a queue for review rather than
writing fixture rows.

    python scripts/review_feedback.py                 # the queue, newest first
    python scripts/review_feedback.py --signal abstained
    python scripts/review_feedback.py --summary       # counts only
    python scripts/review_feedback.py --candidates    # fixture-shaped stubs

**A candidate is not a golden query.** `--candidates` emits stubs with the
query filled in and `expected` deliberately left empty, because filling it from
what the system returned would test the system against its own output and
score beautifully while meaning nothing. That is the same trap
`docs/ATTRIBUTION_GAP.md` describes for LLM-proposed edges: the review has to
be real, or it is worse than not doing it.

Reading it costs nothing -- no model, no corpus, no network.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.feedback import FEEDBACK_PATH, read_events, summarise

#: What each signal usually means, printed beside the queue so a reviewer knows
#: which question to ask of each entry rather than reading them all the same
#: way.
SIGNAL_MEANING = {
    "abstained": (
        "found nothing it could stand behind. Either genuinely out of corpus "
        "(correct, and worth an adversarial fixture row) or a retrieval miss "
        "(a bug, and worth a golden row)."
    ),
    "claims_removed": (
        "the verifier caught the model overreaching. Already fully specified: "
        "the claim and the reason are recorded, so this needs no labelling to "
        "act on."
    ),
    "nothing_retrieved": (
        "no chunk came back at all. Out of scope, or a vocabulary gap in the "
        "expansion table -- the second is a fix, not a limit."
    ),
    "user_reported": "a person said something was wrong. Read the note.",
}


def print_queue(events: list[dict], signal: str | None) -> None:
    if signal:
        events = [e for e in events if signal in e.get("signals", [])]
    if not events:
        print(f"Nothing queued{f' for {signal}' if signal else ''}.")
        return

    for event in reversed(events):
        print(f"\n{'-' * 74}")
        print(f"{event['at'][:19]}  {event['id']}  {', '.join(event['signals'])}")
        print(f"  query: {event['query']}")
        if event.get("note"):
            print(f"  note : {event['note']}")
        for removed in event.get("removed", []):
            print(f"  removed [{removed['class']}] {removed['text'][:90]}")
            print(f"          -> {removed['reason'][:90]}")
        if event.get("retrieved"):
            print(f"  retrieved: {', '.join(str(r) for r in event['retrieved'][:6])}")


def print_candidates(events: list[dict]) -> None:
    """
    Fixture-shaped stubs, with `expected` left empty on purpose.

    Filling it from what retrieval returned would produce a test the system
    passes by construction: it would assert that the system returns what the
    system returned. The empty list is the reviewer's job and the whole point
    of the exercise.
    """
    seen: set[str] = set()
    stubs = []
    for index, event in enumerate(events, 1):
        query = event["query"].strip()
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        stubs.append({
            "id": f"prod{index:03d}",
            "class": "TODO: plain | term_of_art | citation | repealed_code | judgement",
            "collection": "TODO: bns_sections | bnss_sections | bsa_sections | sc_judgements",
            "query": query,
            "expected": [],
            "note": f"from production; signals: {', '.join(event['signals'])}",
        })
    print(json.dumps({"queries": stubs}, indent=2, ensure_ascii=False))
    print(
        f"\n{len(stubs)} candidates. `expected` is empty deliberately -- filling it "
        "from what\nthe system returned would test the system against its own output.",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", help="show only events with this signal")
    parser.add_argument("--summary", action="store_true", help="counts only")
    parser.add_argument(
        "--candidates", action="store_true", help="emit fixture-shaped stubs"
    )
    args = parser.parse_args()

    events = read_events()
    if not events:
        print(
            f"No feedback captured yet ({FEEDBACK_PATH}).\n"
            "Set ENABLE_FEEDBACK_CAPTURE=true to start recording.",
            file=sys.stderr,
        )
        return 0

    if args.summary:
        print(json.dumps(summarise(), indent=2))
        return 0
    if args.candidates:
        print_candidates(events)
        return 0

    print(f"{len(events)} events in {FEEDBACK_PATH}")
    counts = Counter(s for e in events for s in e.get("signals", []))
    for name, count in counts.most_common():
        print(f"  {count:4d}  {name}: {SIGNAL_MEANING.get(name, '')}")
    print_queue(events, args.signal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
