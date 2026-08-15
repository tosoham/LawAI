# Contributing to LawAI

Thanks for your interest. This document covers the workflow; [RULES.md](RULES.md) is the
rulebook and [CLAUDE.md](CLAUDE.md) is the authoritative architecture guide.

---

## Before you start

Read, in this order:

1. **[CLAUDE.md](CLAUDE.md)** — architecture and the non-obvious behaviours. Most of the
   surprising things in this codebase are documented there, with the reason.
2. **[docs/CHALLENGES_AND_SOLUTIONS.md](docs/CHALLENGES_AND_SOLUTIONS.md)** — 60+ fixed bugs
   with their causes. Skim it so you do not reintroduce one.
3. **[RULES.md](RULES.md) §3** — the honesty rules. These are the point of the project.

If you are touching retrieval or grounding, also read
[docs/RAG_PIPELINE.md](docs/RAG_PIPELINE.md) and
[docs/EVALUATION_AND_TESTING.md](docs/EVALUATION_AND_TESTING.md).

---

## Setup

**Prerequisites:** Python 3.10+, Node.js 18+, Git. An [AIML API](https://aimlapi.com) key is
needed only for features that call the LLM — **the app starts and its tests pass without
one.**

```bash
git clone https://github.com/tosoham/LawAI.git
cd LawAI

# Backend
cd backend
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # optionally set AIML_API_KEY
python scripts/init_vector_db.py    # seeds ChromaDB from the committed corpus

# Frontend
cd ../frontend
npm install
cp .env.local.example .env.local

# Verify
cd .. && python scripts/verify_setup.py
```

**Expect a slow first install** — sentence-transformers pulls CPU torch (~1.4 GB).

**Backend commands run from `backend/`.** Imports are rooted there and `pytest.ini` sets
`pythonpath = .` to match. Running from the repo root breaks imports.

Or use Docker: `docker compose up --build`.

---

## Workflow

1. Open an issue describing the change.
2. Branch: `feature/` · `bugfix/` · `docs/` · `test/` · `refactor/`
3. Implement with tests alongside.
4. Run the full check (below).
5. Open a PR.

### The full check

```bash
cd backend
pytest                              # 755 pass, 8 skip — no credentials needed
ruff check .                        # must be clean
mypy .

cd ../frontend
npm test                            # 106 tests
npm run lint
npm run type-check
```

**If you changed retrieval**, additionally:

```bash
cd backend
python scripts/eval_retrieval.py --compare concordance
```

**No class may regress.** The comparison prints a per-class delta and names every query whose
first correct hit moved to a worse rank — that per-query list is the part to read.

**If you changed grounding or verification:**

```bash
pytest tests/integration/test_grounded_answer_live.py -v   # needs AIML_API_KEY
pytest tests/integration/test_adversarial.py -v
```

All six adversarial queries must abstain, four answerable ones must not, and murder must
never come back bailable.

---

## Coding standards

### Python

PEP 8 · type hints · docstrings · specific exception types · async for I/O · module-level
`logger = logging.getLogger(__name__)`.

**Docstrings explain *why*.** This is the strongest convention in the codebase. Where a design
is non-obvious, record the measurement or the bug that forced it:

```python
# Checked against the whole section, not only the chunk retrieval returned.
# Whether a quotation is accurate does not depend on which piece of the
# section happened to rank: asked for the punishment for theft, the model
# quoted BNS 303 correctly while retrieval had returned that section's
# fifth chunk, and checking only the chunk rejected a true statement of the law.
```

A future contributor who does not know why a line exists will "simplify" it back into a bug.

### TypeScript

Strict mode · interfaces for all data structures · documented props · **Pages Router**, not
App Router.

**Colour comes only from semantic tokens** (`canvas`, `surface`, `ink`, `muted`, `line`,
`brand`, `brass`, `verified`, `live`). A raw hex or a stock Tailwind grey breaks dark mode.

### Contracts

`backend/models/` is the single source of truth. `frontend/lib/api.ts` mirrors it.

**Change both together.** They have silently diverged before — the agent emitted claim
`sources` as bare strings while `/search/grounded` emitted typed objects, which crashed every
answer in the UI **while every test passed**, because nothing compared the two payloads.
There is now a test that does; keep it passing.

---

## Domain rules

These are not style preferences. Violating one is a correctness bug.

- **The 2023 codes only.** Never cite IPC/CrPC/Evidence Act as current law.
- **Citations must be exact.** Omit rather than guess.
- **Every generated output carries a disclaimer**, appended by the service.
- **Never let a model verify a model.**
- **Never resolve a conditional value to a boolean** — a guessed "bailable" is the most
  dangerous value this system can emit.
- **Never add an LLM-inferred graph edge.**
- **Never claim precedential status.**
- **Never merge `sources` with `graph_context` or `live_sources`.**
- **Never work around an access control** a source has deliberately put in place. Surface the
  blockage instead.

Full list with reasoning: [RULES.md §3](RULES.md#3-the-honesty-rules).

---

## Adding things

### A tool

Subclass `BaseTool`, return a `ToolResult` (never a bare dict — formatters detect payloads
via `hasattr(result, "success")`), and register it in `initialize_tools()`. **The registry key
is the tool's `name` property.**

### A judgement

Pin the **document id** and give `expect` tokens. Never resolve by name — searching
"Selvi vs State of Karnataka" returns the unrelated Jayalalitha appeal, and one landmark id
matched every expected title token while being a contempt petition between the same parties.
Give `expect_text` phrases from the actual holding.

### A query-expansion alias

Only where the **statutory wording genuinely differs** from the term of art. This is not a
thesaurus — a wrong entry silently misdirects retrieval, which is worse than the gap it
closes. Re-run the eval and confirm no class regressed.

### A doctrine

`data/curated/doctrines.json`, hand-curated. Every lineage edge must trace to a judgement in
the corpus. **No precedential status.** Where authority splits, mark it `contested`, name both
sides, and declare no winner.

---

## Commit messages

Write what changed and **why it matters**, in the imperative. The history reads as a
narrative and that is worth keeping:

```
Look up cited sections instead of searching for them
Answer as verified claims, or abstain
Translate repealed citations through a sourced concordance
Fix what the browser found: a crash on every answer
```

Conventional-commit prefixes (`feat:`, `fix:`) are acceptable but not required. The body
should carry the reasoning — what was measured, what broke, what it now prevents.

---

## Pull requests

**Checklist:**

- [ ] Tests pass (backend and frontend)
- [ ] `ruff check .` clean, `npm run lint` and `type-check` clean
- [ ] Retrieval eval run and no class regressed (if retrieval changed)
- [ ] Adversarial suite passes (if grounding changed)
- [ ] Docs updated — including a
      [CHALLENGES_AND_SOLUTIONS](docs/CHALLENGES_AND_SOLUTIONS.md) entry if you fixed a
      non-obvious bug
- [ ] `backend/models/` and `frontend/lib/api.ts` still in sync
- [ ] No secrets, no PII, no committed binaries

**Template:**

```markdown
## What changed
## Why
## How it was verified
<!-- Test output, eval comparison, or what you exercised in the browser/container. -->
## Risk
<!-- What could this break? Which existing behaviour did you check? -->
```

**On verification:** four real bugs in this project's history got past a fully green test
suite — a payload mismatch that crashed every answer, a container that passed its health check
and 500-ed on every question, a seed marker that made a half-finished index look complete, and
SVG labels clipped outside their viewBox. If your change touches the UI or the container,
**run it** and say so in the PR.

---

## Questions

Open an issue. Check existing ones first.

By contributing you agree your contributions are licensed under the MIT License.
