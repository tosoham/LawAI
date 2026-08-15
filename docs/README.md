# LawAI Documentation

Start here. Every document below is current as of the latest commit and quotes only numbers
measured from the committed data.

---

## The documents

| Document | What it covers | Read it when |
|---|---|---|
| **[ENGINEERING_DEEP_DIVE.md](ENGINEERING_DEEP_DIVE.md)** | The master document. End-to-end working, every layer, every challenge and its fix, honest limitations. | You want the whole picture. **Start here.** |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System diagram, request flows, data model, module map, invariants, configuration. | You need the reference, not the narrative. |
| **[RAG_PIPELINE.md](RAG_PIPELINE.md)** | Chunking, batching, embedding, the four-layer retrieval stack, the ablation table. | The topic is retrieval. |
| **[EVALUATION_AND_TESTING.md](EVALUATION_AND_TESTING.md)** | Golden set, metrics, abstention measurement, test pyramid, adversarial suite, what tests missed. | The topic is evaluation or testing. |
| **[CHALLENGES_AND_SOLUTIONS.md](CHALLENGES_AND_SOLUTIONS.md)** | 60+ indexed problems as Symptom → Cause → Fix → Guard. | You want to skim, or find one specific bug. |
| **[INTERVIEW_BRIEF.md](INTERVIEW_BRIEF.md)** | Talking points, expected follow-ups, numbers to memorise, honest answers to hard questions. | Preparing to discuss this project. |
| [COMPLETE_IMPLEMENTATION_PLAN.md](COMPLETE_IMPLEMENTATION_PLAN.md) | The original hackathon-era plan. **Historical** — superseded, kept for provenance. | You want to see how the plan changed. |

**Also in the repository root:**

| File | Purpose |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | Authoritative guide for AI coding agents. Dense, non-obvious behaviours, the "do not regress this" list. |
| [`../README.md`](../README.md) | Project overview and quick start. |
| [`../AGENTS.md`](../AGENTS.md) | Domain rules for AI agents; defers to CLAUDE.md. |
| [`../RULES.md`](../RULES.md) | Development rulebook. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contribution workflow. |

---

## Reading paths

**"I have 10 minutes."**
[ENGINEERING_DEEP_DIVE](ENGINEERING_DEEP_DIVE.md) §1–3 (what it is, the thesis, one question
end to end) → §6.1 (the retrieval ablation) → §14 (honest limitations).

**"I want to understand the RAG design."**
[RAG_PIPELINE](RAG_PIPELINE.md) whole → [ENGINEERING_DEEP_DIVE](ENGINEERING_DEEP_DIVE.md) §8
(grounding and verification).

**"I want to understand how it's evaluated."**
[EVALUATION_AND_TESTING](EVALUATION_AND_TESTING.md) whole. §4 (the abstention measurement)
and §7 (what tests didn't catch) are the substantive parts.

**"I'm going to work on the code."**
[`../CLAUDE.md`](../CLAUDE.md) → [ARCHITECTURE](ARCHITECTURE.md) →
[CHALLENGES_AND_SOLUTIONS](CHALLENGES_AND_SOLUTIONS.md) (so you don't reintroduce a fixed
bug).

**"I'm preparing to talk about this project."**
[INTERVIEW_BRIEF](INTERVIEW_BRIEF.md) → then read the deep dive properly, because the brief
assumes you understand the reasoning rather than just the conclusions.

---

## Using these with an LLM

To discuss, extend or be quizzed on this project with an AI assistant, upload in this order:

1. **[ENGINEERING_DEEP_DIVE.md](ENGINEERING_DEEP_DIVE.md)** — the complete picture
2. **[RAG_PIPELINE.md](RAG_PIPELINE.md)** — retrieval depth
3. **[EVALUATION_AND_TESTING.md](EVALUATION_AND_TESTING.md)** — measurement depth
4. **[CHALLENGES_AND_SOLUTIONS.md](CHALLENGES_AND_SOLUTIONS.md)** — the specifics
5. **[INTERVIEW_BRIEF.md](INTERVIEW_BRIEF.md)** — framing
6. **[ARCHITECTURE.md](ARCHITECTURE.md)** — only if the discussion gets structural

Documents 1–3 are enough for most conversations. All six together are about 60 KB of
markdown.

---

## Where the numbers come from

Nothing in these documents is estimated. To reproduce:

```bash
# Corpus counts
python -c "import json; print(len(json.load(open('data/processed/bns_sections.json'))))"

# Graph statistics
cd backend && ./venv/bin/python -c "
from services.legal_graph import get_legal_graph
g = get_legal_graph()
print(len(g.sections), len(g.judgements), len(g.doctrines))"

# Retrieval eval
cd backend && python scripts/eval_retrieval.py --compare concordance

# Tests
cd backend && pytest -q
cd frontend && npm test
```

Committed eval reports in `backend/eval/`, in the order they were produced:
`baseline_no_expand.json` → `baseline.json` → `structured.json` → `concordance.json`
(current).
