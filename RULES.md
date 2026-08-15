# RULES.md

The development rulebook for LawAI. All contributors — human and AI — follow these.

**Precedence:** [CLAUDE.md](CLAUDE.md) is authoritative where this file disagrees with it.
[AGENTS.md](AGENTS.md) carries the domain rules in condensed form. For the *reasoning* behind
a rule, and the bug that produced it, see
[`docs/CHALLENGES_AND_SOLUTIONS.md`](docs/CHALLENGES_AND_SOLUTIONS.md).

Sections marked **[ASPIRATIONAL]** describe standards not yet met. They are kept because they
are the target, and marked because a rulebook that lies about the current state is worse than
no rulebook.

---

## 1. Development philosophy

- **Plan first, build later.** Discuss and design before implementing.
- **Iterative.** Break work into small testable steps; finish one before starting the next.
- **Test-driven.** Write tests alongside features.
- **Measure, don't assume.** Where a design decision has an obvious answer, build the
  measurement before committing to it. The relevance-threshold abstention design was
  intuitive, standard, and **provably wrong for this corpus** — and only a measurement showed
  that.

---

## 2. The domain constraints (non-negotiable)

### 2.1 The legal framework is the 2023 codes

- **BNS** (Bharatiya Nyaya Sanhita, 2023) replaces the Indian Penal Code
- **BNSS** (Bharatiya Nagarik Suraksha Sanhita, 2023) replaces the CrPC
- **BSA** (Bharatiya Sakshya Adhiniyam, 2023) replaces the Indian Evidence Act

Never cite a repealed provision as current law. Collections are `bns_sections`,
`bnss_sections`, `bsa_sections`, `sc_judgements`.

### 2.2 Citations must be exact

Format: `"Section 103, Bharatiya Nyaya Sanhita, 2023"`; case law as
`"Case Name v. Case Name, (Year) Citation"`.

**A wrong section number is a correctness bug, not a cosmetic one. Omit a citation rather
than guess it.**

### 2.3 Every AI-generated output carries a disclaimer

Appended by the service — **never written by the model**, so no instruction can suppress it.
The frontend must surface `LegalDisclaimer`.

### 2.4 Only official sources

Statutory text from MHA gazette PDFs. Judgements id-pinned and verified on fetch. The
concordance is from a government body (BPR&D) and is labelled as a **weaker guarantee** than
enacted text, because it is asserted rather than enacted.

---

## 3. The honesty rules

These are what the project exists to demonstrate. Violating one is a correctness regression.

| Rule | Why |
|---|---|
| **Never let a model verify a model** | The prior that invented BNS 999 will confirm BNS 999 |
| **Never resolve a conditional value to a boolean** | ~40 First Schedule rows defer to another offence; a guessed "bailable" is the most dangerous value this system can emit |
| **Never add an LLM-inferred graph edge** | A false relation propagates into every answer touching either endpoint, invisibly |
| **Never claim precedential status** | No `overruled_by`, no `still_good_law` — highest value, highest harm, and it ages |
| **Never merge `sources` with `graph_context` or `live_sources`** | Retrieved-by-relevance, reached-by-edge and unverified are different provenance |
| **Never resolve a repealed section number by assumption** | "CrPC 438" means BNSS 482, but BNSS 438 exists and is about something else |
| **Never hedge a failed claim** | Hedging an invented section number still puts the number in front of the reader. Remove it and report the removal |
| **Never let audience reach retrieval or verification** | A citizen's answer is shorter, not vaguer, and keeps every citation |
| **Never present a contested question one-sidedly** | Even when that side is impeccably cited |
| **Never suggest an outcome in judge mode** | Not by implication, ordering or emphasis either |

---

## 4. Tech stack

| Layer | Choice |
|---|---|
| LLM | AIML API (OpenAI-compatible), default `gpt-4o-mini`, via the `openai` SDK |
| Agent | LangGraph `StateGraph` |
| Vector DB | ChromaDB, local |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2`, 384-dim, local |
| Backend | FastAPI, async, Python 3.10+ |
| Frontend | Next.js 14 **Pages Router**, TypeScript, Tailwind |

> **Historical note:** the LLM was IBM watsonx.ai Granite while this was a hackathon entry,
> where that provider was a competition requirement. That constraint no longer applies. The
> LLM layer is isolated behind `services/llm_service.py`, so changing it again means
> rewriting only that module.

---

## 5. Architecture rules

### 5.1 Tools

Five tool nodes, registered into a global `ToolRegistry` at startup: `rag_search`, `chat`,
`draft_document`, `analyze_document`, `live_research`.

Add one by subclassing `BaseTool` and registering it in `initialize_tools()`. **The registry
key is the tool's `name` property** — `AnalyzeDocumentTool` registers as `analyze_document`,
not `analyze_doc`.

Tool nodes must return a `ToolResult`, never a bare dict — the response formatters detect a
payload via `hasattr(result, "success")`.

> These are **not** MCP tools, despite log lines that have said so. An MCP server is
> [ASPIRATIONAL].

### 5.2 Singletons

`llm_service`, `get_agent_service()`, `get_rag_service()`, `get_vector_service()`,
`get_tool_registry()`, `get_legal_graph()`, `get_grounded_answer_service()`,
`get_embedding_service()`.

**Always use the accessors.** `reset_agent_service()` and `reset_legal_graph()` exist for
tests. Everything stays on the `services.*` import convention — importing the same module as
`backend.services.*` would duplicate every singleton.

### 5.3 Streaming

Two endpoints stream, and they share **one SSE dialect**: `data: {"token": …}` lines
terminated by `data: [DONE]`. `frontend/lib/api.ts::readStream` understands only that shape.

**Agent streaming is faux-streaming** — the graph runs to completion, then the finished string
is sliced into 50-char chunks. This is deliberate: real streaming would discard the structured
`sources`. Real token streaming exists via `LLMService.generate_stream` and is used by
`POST /chat`.

### 5.4 Failure behaviour

- **Startup swallows init errors** so `/health` stays up without credentials.
- **LLM clients are built lazily** — a missing `AIML_API_KEY` does not raise until a
  generation is attempted. Do not "fix" this by validating in `__init__`.
- **Live judiciary access fails soft** — errors are *returned*, never raised, so an outage
  degrades to the local corpus instead of 500-ing.
- **`is_allowed()` fails closed** — if robots.txt cannot be read, not knowing is not
  permission.
- **A malformed model response yields an empty answer, not an exception** — the caller then
  abstains, which is correct.

---

## 6. Code quality

### Python

PEP 8 · type hints on all signatures · docstrings on every module, class and public function
· module-level `logger = logging.getLogger(__name__)` · specific exception types · async for
I/O.

```python
async def search_legal_corpus(
    query: str, collection: str, limit: int = 10
) -> list[dict[str, Any]]:
    """
    Search the legal corpus using vector similarity.

    Args:
        query: User's search query
        collection: ChromaDB collection name
        limit: Maximum number of results

    Returns:
        Matching documents with metadata

    Raises:
        ValueError: If collection name is invalid
    """
```

**Comment the non-obvious.** This codebase's docstrings explain *why a thing is the way it
is* — which measurement forced it, which bug it prevents. That convention is load-bearing;
match it.

### TypeScript

Strict mode · interfaces for all data structures · ESLint clean · documented props.

**Colour comes only from semantic tokens** — `canvas`, `surface`, `ink`, `muted`, `line`,
`brand`, `brass`, `verified`, `live`. A raw hex or a stock Tailwind grey breaks dark mode.

### Contracts

`backend/models/` is the single source of truth; routers import from there rather than
defining their own. `frontend/lib/api.ts` mirrors it in TypeScript.

**Keep them in sync.** They have silently diverged before — the agent emitted claim sources as
bare strings while the endpoint emitted typed objects, and it crashed every answer in the UI
while every test passed.

### Linting

`ruff check .` must be clean. **The rule set is pinned in `backend/pyproject.toml`** because
ruff widens its defaults every release — 0.1.14 flagged a handful of findings and 0.16 flagged
~1,300 on identical code. Do not rely on ruff defaults here.

---

## 7. Testing

### Current state

**763 backend tests (755 pass, 8 skip), 106 frontend tests.**

- Tests calling the live API are marked `@pytest.mark.live` and **skip without
  `AIML_API_KEY`**. A plain `pytest` run must stay green with no credentials.
- The 8 skipped e2e tests need a running server.
- Backend tests run **from `backend/`**.

### Requirements

- **Unit tests** for every service, tool and parser.
- **Data-integrity tests** — the corpus *is* the guarantee. 21 offences are transcribed by eye
  from the PDF and pinned exactly, with invariants over the other 444.
- **Verifier tests** with deliberately fabricated claims: a non-existent section, misquoted
  statutory text, a real judgement cited for a section it never mentions, a false bailability
  claim, a one-sided contested claim. All must be caught.
- **Contract tests between surfaces**, not just within one. Two components can each satisfy
  their own tests and still disagree.
- **Retrieval eval** — `eval_retrieval.py --compare concordance` after any retrieval change.
  **No class may regress.**
- **Adversarial** — the six adversarial queries must abstain; murder must never come back
  bailable.

### [ASPIRATIONAL]

80% coverage minimum, 100% on legal-accuracy paths, CI on every commit. None of these are
enforced today.

---

## 8. Security and compliance

### Implemented

- No PII in the vector database
- Input validation via Pydantic on every endpoint
- File type and size restrictions on uploads
- Secrets in environment variables, never committed (`.env` is gitignored)
- CORS configured for the frontend
- `ANONYMIZED_TELEMETRY=False` — chromadb phones home by default, and a legal tool should not
  report query volume
- Disclaimers on all generated output
- robots.txt honoured, rate limiting, and fail-closed policy checks on **outbound** requests

### [ASPIRATIONAL] — not implemented

- JWT authentication
- Inbound API rate limiting
- Audit logging for document generation
- Data retention policy
- Terms-of-service acceptance

**Do not describe these as present.** The previous version of this file listed them as
implemented, and they were not.

---

## 9. Performance

Measured: retrieval is sub-second over 3,184 chunks; deterministic endpoints
(`/offences/{act}/{section}`) involve no model call at all.

### [ASPIRATIONAL] targets

RAG search < 2s to first result · first token < 500ms · document generation < 5s · non-LLM
endpoints < 200ms · 50+ concurrent users · backend < 2GB RAM.

No load testing or production monitoring exists. `scripts/performance_test.py` is a starting
point, not a benchmark suite.

---

## 10. Prohibited

**Development** — implementing without a plan · committing without tests · deploying with
failing tests.

**Security** — PII in the vector DB · committed secrets · skipped input validation ·
disabled CORS.

**Legal** — omitting disclaimers · unofficial sources · giving legal advice (the system
assists) · guessing a citation.

**Data** — citing IPC/CrPC/Evidence Act as current law · mixing old and new frameworks ·
resolving a conditional classification to a boolean · inferring a graph edge · claiming
precedential status.

**Ethics** — working around an access control a source has deliberately put in place. When
Indian Kanoon went behind a Cloudflare challenge, the correct response was to **surface the
blockage** through `/research/health`, not to route around it.

---

## 11. Repository layout

```
LawAI/
├── backend/
│   ├── agents/          legal_agent · agent_service · intent_classifier · state · citations
│   ├── api/v1/          agent · search · offences · research · documents · chat
│   ├── models/          claims · requests · responses  (single source of truth)
│   ├── services/        grounded_answer · claim_verifier · answer_metrics · legal_graph
│   │                    procedural_timeline · query_expansion · rag_service · vector_service
│   │                    embedding_service · llm_service · judiciary_service · audience
│   │   └── retrieval/   structured_filter · offence_lookup
│   ├── tools/           BaseTool subclasses + registry
│   ├── scripts/         ingest_* · init_vector_db · eval_retrieval · discover_judgments
│   ├── tests/           unit/ (23) · integration/ (4) · e2e/ (1)
│   ├── eval/            committed retrieval reports
│   └── main.py
├── frontend/
│   ├── pages/           index (landing) · app (product) · _app · _document
│   ├── components/      legal/ · chat/ · search/ · research/ · documents/ · shared/ · layout/
│   ├── hooks/           useOffence · useSearch · useResearch · useDocuments · useTheme
│   ├── lib/             api.ts (all HTTP) · workspaces · theme
│   └── __tests__/
├── data/
│   ├── processed/       committed corpus JSON
│   ├── curated/         doctrines.json — hand-curated
│   └── raw/             gitignored, re-downloadable
├── docs/                see docs/README.md
├── scripts/verify_setup.py
├── CLAUDE.md · AGENTS.md · RULES.md · README.md · CONTRIBUTING.md
└── docker-compose.yml
```

---

## 12. Git workflow

**Branches:** `feature/` · `bugfix/` · `docs/` · `test/` · `refactor/`

**Commits.** Write what changed and *why it matters*, in the imperative. The history here
reads as a narrative — "Look up cited sections instead of searching for them", "Answer as
verified claims, or abstain", "Fix what the browser found: a crash on every answer" — and
that convention is worth keeping. Conventional-commit prefixes are acceptable but not
required.

**Before committing:**

```bash
cd backend  && pytest && ruff check .
cd frontend && npm test && npm run lint && npm run type-check
```

Retrieval changes additionally require
`python scripts/eval_retrieval.py --compare concordance` with no class regressed.

---

## 13. Development commands

```bash
# Backend — all from backend/
python -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env                 # set AIML_API_KEY
uvicorn main:app --reload            # :8000, docs at /docs
pytest · pytest -m live · pytest --cov=. --cov-report=html
ruff check . · black . · mypy .

# Corpus (rarely needed — outputs are committed)
python scripts/ingest_legal_acts.py
python scripts/ingest_judgments.py
python scripts/ingest_offence_schedule.py
python scripts/ingest_concordance.py
python scripts/init_vector_db.py

# Eval
python scripts/eval_retrieval.py --compare concordance

# Frontend — from frontend/
npm install && cp .env.local.example .env.local
npm run dev · npm test · npm run lint · npm run type-check

# Docker — from the repo root
docker compose up --build
docker compose down -v               # also drops the vector store volume
```

---

## 14. Documentation requirements

- Every module, class and public function has a docstring.
- **Docstrings explain *why*, not just what.** Where a design is non-obvious, record the
  measurement or the bug that forced it — that is what makes this codebase maintainable, and
  it is the strongest convention here.
- API docs auto-generate from FastAPI at `/docs`.
- Architecture and decisions live in [`docs/`](docs/README.md); update them when behaviour
  changes.
- When a fix lands, add its entry to
  [`docs/CHALLENGES_AND_SOLUTIONS.md`](docs/CHALLENGES_AND_SOLUTIONS.md) so it cannot be
  quietly reintroduced.

---

**Last updated:** 2026-08-15 · **Version:** 2.0.0
