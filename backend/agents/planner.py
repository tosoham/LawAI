"""
Decide which specialists a complex query needs, and what to ask each.

Runs only after triage has said a query is worth more than one pass, so its
cost is already justified by the time it is called. On the simple path -- 69 of
69 answerable golden queries -- nothing here executes.

**A bad plan degrades; it does not fail.** Two ways, both learned from earlier
bugs in this repository:

* an unparseable plan falls back to the single-pass path rather than erroring,
  because a planning failure is not a reason to refuse a question the one-pass
  path answers well;
* **one bad step is dropped rather than the whole plan discarded.** That is the
  bug fixed in ``9a92ac1``, where a model labelled one claim with a class
  outside the enum and the ``ValidationError`` took three good claims with it,
  abstaining on a question the corpus answers directly. A planner naming five
  specialists and inventing a sixth should get its five.

The planner never retrieves and never answers. It emits a ``Plan`` and nothing
else, so a planning mistake costs a wasted specialist call rather than a wrong
statement of law.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from agents.contracts import Complexity, Plan, PlanStep, SpecialistKind
from services.llm_service import llm_service
from services.model_json import load_json_payload

logger = logging.getLogger(__name__)

# Enough for a handful of steps. A plan is short by construction; a cap this
# size truncates nothing real and bounds a runaway generation.
PLAN_MAX_TOKENS = 700

# More than this and the planner is fanning out for its own sake. Six
# specialists exist; a query needing all of them is a query that should have
# been asked as several.
MAX_STEPS = 4

PLANNER_SYSTEM = """You plan how to research a question about Indian criminal law \
under the 2023 codes: the Bharatiya Nyaya Sanhita (BNS, offences), the Bharatiya \
Nagarik Suraksha Sanhita (BNSS, procedure) and the Bharatiya Sakshya Adhiniyam \
(BSA, evidence).

You do not answer the question. You do not state any law. You choose which \
researchers to send it to and what to ask each one, and everything they find is \
checked against the corpus afterwards by machinery you are not part of.

Choosing a researcher that finds nothing is cheap. Failing to choose one that \
was needed is not, because nothing downstream can retrieve what was never asked \
for."""

PLANNER_INSTRUCTIONS = """Available researchers:

  statute     provisions of the BNS, BNSS and BSA. Choose it for anything about
              what the law says.
  case_law    Supreme Court judgements in the corpus. Choose it when the answer
              depends on how courts have read a provision.
  offence     whether an offence is cognizable, bailable, and which court tries
              it, plus the custody timeline. Read from the First Schedule with
              no model involved, so it is free and cannot be wrong. Choose it
              whenever a named offence appears.
  doctrine    curated doctrine and its lineage. Also free, also a lookup.
  drafting    only when the user asked for a document to be produced.
  analysis    only when the user supplied a document to be examined.

Return JSON of exactly this shape and nothing else:

{"steps": [
  {"specialist": "statute", "question": "...", "reason": "..."}
]}

Rules:
- At most {max_steps} steps. Name each researcher at most once.
- `question` is what that researcher should look for, in its own terms -- not a
  restatement of the user's question.
- `reason` is one clause saying why it bears on the query. It is shown to the
  user in the trace, so a plan can be argued with.
- Prefer `offence` and `doctrine` where they apply. They cost nothing.
- Do not choose `drafting` or `analysis` unless the user actually asked for a
  document to be written or examined.
- No prose outside the JSON."""

# A plain replace, not .format(): the template contains a JSON example and
# every brace in it would have to be doubled to survive formatting.
PLANNER_INSTRUCTIONS = PLANNER_INSTRUCTIONS.replace("{max_steps}", str(MAX_STEPS))


def _fallback(query: str) -> Plan:
    """
    What to do when planning fails.

    Statute plus offence: the two that answer most legal questions, one of them
    free. This is deliberately not "give up" -- a planning failure says nothing
    about whether the corpus can answer the question.
    """
    return Plan(
        complexity=Complexity.COMPLEX,
        steps=[
            PlanStep(
                specialist=SpecialistKind.STATUTE,
                question=query,
                reason="default plan; the planner did not return a usable one",
            ),
            PlanStep(
                specialist=SpecialistKind.OFFENCE,
                question=query,
                reason="free lookup, included whenever the plan is a default",
            ),
        ],
    )


def parse_plan(raw: str, query: str) -> Plan:
    """
    Parse the planner's output, keeping every step that is usable.

    Steps are validated one at a time. A model that names a researcher that
    does not exist has still chosen correctly for the others, and discarding
    those would waste a good plan over a typo.
    """
    payload = load_json_payload(raw)
    if payload is None:
        return _fallback(query)

    if isinstance(payload, list):
        payload = {"steps": payload}
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
        logger.warning(f"plan had no steps list: {str(payload)[:200]}")
        return _fallback(query)

    steps: list[PlanStep] = []
    seen: set[SpecialistKind] = set()
    for index, raw_step in enumerate(payload["steps"]):
        try:
            step = PlanStep.model_validate(raw_step)
        except ValidationError as error:
            logger.warning(f"dropping unusable plan step {index}: {error}")
            continue
        if step.specialist in seen:
            continue
        seen.add(step.specialist)
        steps.append(step)

    if not steps:
        return _fallback(query)
    if len(steps) > MAX_STEPS:
        logger.info(f"plan named {len(steps)} researchers; keeping the first {MAX_STEPS}")
        steps = steps[:MAX_STEPS]
    return Plan(complexity=Complexity.COMPLEX, steps=steps)


def plan_query(
    query: str,
    complexity: Complexity = Complexity.COMPLEX,
    contested_question: str = "",
    service=None,
) -> Plan:
    """
    A research plan for one query.

    ``contested_question`` is carried through untouched: triage decided the
    question is contested and phrased what is in dispute, and the planner is
    not asked to re-litigate that. Specialists still run for a contested query
    -- both advocates need authority to argue from, and neither should be
    retrieving it for the first time mid-argument.
    """
    service = service or llm_service
    try:
        raw = service.generate(
            prompt=f"{PLANNER_INSTRUCTIONS}\n\nQUESTION:\n{query}",
            system=PLANNER_SYSTEM,
            max_tokens=PLAN_MAX_TOKENS,
            temperature=0.0,
        )
    except Exception as error:
        logger.warning(f"planner call failed ({error}); using the default plan")
        return _fallback(query)

    plan = parse_plan(raw, query)
    plan.complexity = complexity
    plan.contested_question = contested_question
    logger.info(
        f"plan: {[step.specialist.value for step in plan.steps]} "
        f"({complexity.value})"
    )
    return plan
