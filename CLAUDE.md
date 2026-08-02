# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LawAI is a multi-agent Indian legal AI system. A LangGraph agent classifies user intent and routes to one of four tools (rag_search, chat, draft_document, analyze_doc) backed by an LLM served through **AIML API** and a ChromaDB vector store of the post-2023 Indian legal codes (BNS/BNSS/BSA + Supreme Court judgements). FastAPI backend, Next.js (Pages Router) frontend.

The project began as a hackathon entry that required IBM watsonx.ai. That requirement is gone: the LLM layer now targets AIML API's OpenAI-compatible endpoint and is isolated in `backend/services/llm_service.py`. Docs elsewhere in the repo may still mention watsonx — this file is authoritative.

## Domain constraints (non-negotiable)

- **The legal framework is the 2023 codes**, not the pre-2023 ones: BNS replaces the IPC, BNSS replaces the CrPC, BSA replaces the Evidence Act. Collections are `bns_sections`, `bnss_sections`, `bsa_sections`, `sc_judgements` (constants in `backend/services/vector_service.py`).
- **Citations must be exact.** "Section 103, Bharatiya Nyaya Sanhita, 2023"; case law as "Case Name v. Case Name, (Year) Citation". A wrong section number or misattributed judgement is a correctness bug, not a cosmetic one — omit a citation rather than guess it.
- **Every AI-generated answer or document carries a disclaimer** (appended in `RAGService` and the tools; the frontend must surface `LegalDisclaimer`).

## Commands

All backend commands run **from the `backend/` directory** — imports are rooted there (`from services.llm_service import ...`), and `pytest.ini` sets `pythonpath = .` to match. Running from the repo root breaks imports. There is a virtualenv at `backend/venv`.

```bash
# Backend (from backend/)
python -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env            # then set AIML_API_KEY — required for any LLM call

# One-time corpus setup (already committed under data/processed/, so usually unnecessary)
python scripts/ingest_legal_acts.py   # MHA gazette PDFs -> data/processed/*.json
python scripts/ingest_judgments.py    # Indian Kanoon -> sc_judgements.json
python scripts/init_vector_db.py      # chunk + embed into backend/chroma_db/

uvicorn main:app --reload       # serves on :8000, docs at /docs

pytest                          # all backend tests
pytest tests/unit/test_tools.py -v          # single file
pytest tests/unit/test_tools.py::test_name  # single test
pytest --cov=. --cov-report=html

ruff check .                    # lint (the repo has a large pre-existing backlog)
black .                         # format
mypy .                          # type check

# Frontend (from frontend/)
npm install && cp .env.local.example .env.local
npm run dev                     # serves on :3000
npm run lint
npm run type-check              # tsc --noEmit
```

Tests requiring a live LLM are marked `live` and skip automatically unless `AIML_API_KEY` is set, so a plain `pytest` run is green without credentials (currently 105 passed, 28 skipped).

## Architecture

Request flow: **frontend `lib/api.ts` → FastAPI router (`api/v1/*.py`) → service/tool → LLM/vector store**.

- **Agent orchestration** (`backend/agents/`): `AgentService` (singleton, `get_agent_service()`) wraps `LegalAgent`, a compiled LangGraph `StateGraph`. Flow: `classify_intent` → conditional edge by intent → one tool node → `format_response` → END. State shape is in `agents/state.py`. Unknown intent defaults to RAG search.
- **Intent classification** (`agents/intent_classifier.py`): keyword/regex scoring against `INTENT_PATTERNS`, with an LLM fallback. Three rules make it behave:
  - `REQUIRED_TRIGGERS` gate `draft_document`, `analyze_document` and `live_research`. Their supporting keywords ("bail", "contract", "case law") are ordinary legal vocabulary, so without an action verb — or, for live research, a recency word — those intents score nothing. Otherwise "Tell me about bail" gets answered with a drafted bail application.
  - A fired trigger also *scores* (`TRIGGER_WEIGHT`, 2 for `live_research`). RAG_SEARCH and LIVE_RESEARCH deliberately share case-law vocabulary and recency is the only discriminator, so it must outweigh a shared keyword.
  - `_TIE_BREAK_ORDER` puts RAG_SEARCH **last** — it is the documented fallback, so it must lose ties to narrower intents.
- **Live research** (`agents/legal_agent.py::_execute_live_research_node`): the one node that does not call a predetermined tool. It hands the model the schemas from `tools/live_case_law_tool.py::build_openai_tool_schemas()` and runs `LLMService.generate_with_tools`, so the model chooses between the local corpus and live judiciary sources — whether a question needs current data is not reliably decidable from keywords.
- **Tools** (`backend/tools/`): all subclass `BaseTool` and return a `ToolResult`. Registered at startup into a global `ToolRegistry` (`tools/registry.py`, `initialize_tools()` called from `main.py`'s `startup_event`). Add a tool by subclassing `BaseTool` and registering it there. Note the registry key is the tool's `name` property — `AnalyzeDocumentTool` registers as `analyze_document`, not `analyze_doc`.
- **Services** (`backend/services/`): `LLMService` (singleton, AIML API), `RAGService` (vector search + prompt + generate, appends a disclaimer), `VectorService` (ChromaDB), `EmbeddingService` (sentence-transformers `all-MiniLM-L6-v2`), `LegalDataLoader`, `JudiciaryService` (live case law).
- **Singletons everywhere**: `llm_service`, `get_agent_service()`, `get_rag_service()`, `get_vector_service()`, `get_tool_registry()`. Use the accessors; `reset_agent_service()` exists for tests.

### Non-obvious behaviours

- **`LLMService` builds its clients lazily.** A missing `AIML_API_KEY` does not raise until a generation is actually attempted, so the app still starts and `/health` stays up. Don't "fix" this by validating in `__init__` — that previously made a missing key crash the whole app at import.
- **Generation kwargs use OpenAI names** (`max_tokens`, `temperature`). `max_new_tokens` is accepted as a legacy alias; unrecognised kwargs are dropped rather than forwarded, so they can't become a provider 400.
- **Agent "streaming" is faux-streaming.** `AgentService.process_query_stream` runs the graph to completion, then slices the finished string into 50-char SSE chunks (`data: {"token": ...}` / `data: [DONE]`). Real token streaming exists via `LLMService.generate_stream` and is used by `POST /api/v1/chat` when `stream=true`, but the agent path does not use it. The frontend `readStream` in `lib/api.ts` parses the SSE format.
- **ChromaDB path is CWD-relative** (`VectorService` defaults to `./chroma_db`). Running from `backend/` uses `backend/chroma_db`; a stale `chroma_db/` also exists at the repo root. Both are gitignored — the DB is regenerated by `init_vector_db.py`.
- **Documents are chunked before embedding.** `all-MiniLM-L6-v2` truncates at ~256 tokens, so a 60k-character judgement would otherwise be indexed by its first paragraph alone. `init_vector_db.py` splits into ~1200-char overlapping chunks carrying `parent_id` so a hit is still citable to its source. 1,086 documents → 3,128 chunks.
- **`LegalDataLoader` raises if `data/processed/` is missing** rather than falling back to sample data. Silently serving placeholder text from a legal assistant is worse than an error.
- **`main.py` startup swallows init errors** (logs and continues) so `/health` stays up without credentials.

## Legal corpus

`data/processed/*.json` is committed, so the project runs without re-fetching. Regenerate only when the source changes.

| Collection | Source | Records |
|---|---|---|
| `bns_sections` | MHA gazette PDF | 358 (complete) |
| `bnss_sections` | MHA gazette PDF | 531 (complete) |
| `bsa_sections` | MHA gazette PDF | 170 (complete) |
| `sc_judgements` | Indian Kanoon (curated, id-pinned) | 27 |

Two things about `ingest_legal_acts.py` that look odd but are deliberate:
- Text is extracted with `x_tolerance=1.0`; pdfplumber's default glues words together in this font ("isdoubtfulof"), wrecking embeddings and display.
- Section titles are gazette *marginal notes* and extract out of order, so they are bound to sections by **vertical position**, not reading order.

`ingest_judgments.py` pins each judgement by document id and re-verifies the fetched page against `expect` tokens. Do not switch it to search-by-name: searching "Selvi vs State of Karnataka" returns the unrelated Jayalalitha appeal. It also honours robots.txt and rate limits.

## Live judiciary access

`services/judiciary_service.py` queries authentic public judiciary records (Indian Kanoon: Supreme Court, High Courts, tribunals) at request time. The corpus is a snapshot; this covers judgements handed down after ingestion — verified working against 2026 decisions.

- **Two paths in**: the agent's `live_research` intent (model-driven, via function calling), and the REST endpoints under `/api/v1/research/*` for direct access.
- **It fails soft on purpose.** Errors are returned, never raised, so a slow or unreachable source degrades to the local corpus instead of 500-ing a request. Preserve that.
- **Live results are retrieved, not curated.** Every hit carries court, date and `source_url`, and both the API and the agent label them as unverified. Do not blend them into corpus output.
- Requests are rate limited (`JUDICIARY_MIN_REQUEST_INTERVAL`), TTL-cached, and the source's robots.txt disallow list is parsed and honoured — it names several thousand individual documents.
- `ENABLE_LIVE_JUDICIARY=false` turns the whole thing off for offline operation; everything else keeps working.

## API surface (`/api/v1`)

- `agent/query`, `agent/query/stream` — main agent entry points
- `search/rag` — direct RAG search over a chosen collection
- `research/case-law`, `research/judgment/{doc_id}`, `research/health` — live judiciary lookups
- `documents/draft`, `documents/analyze`, `documents/export/docx`, `documents/templates`
- `chat/*`, plus `health`/`info` at several levels

Request/response Pydantic models live in `backend/models/` (single source of truth — routers import from there rather than defining their own). Mirrored TypeScript types are in `frontend/lib/api.ts`; keep them in sync when changing a contract.

## Frontend

Next.js **Pages Router** (`frontend/pages/`), not App Router. Feature UIs in `components/{chat,search,documents,shared}/`, data-fetching in `hooks/use*.ts`, all HTTP centralised in `lib/api.ts`. State via `zustand`.

## Conventions

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- Project rules live in `RULES.md` and `AGENTS.md`; both defer to this file where they disagree.
