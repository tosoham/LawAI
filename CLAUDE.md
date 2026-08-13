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
python scripts/ingest_offence_schedule.py  # BNSS First Schedule -> offence_classification.json
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

# Docker (from the repo root)
docker compose up --build       # frontend :3000, backend :8000
docker compose down -v          # -v also drops the vector store volume
```

### Docker specifics

Four things here are load-bearing and easy to break:

- **The backend build context is the repo root, not `backend/`.** `data_loader.py` resolves the corpus as `backend/../data/processed`, so the image must preserve that relative layout (`/app/backend` + `/app/data/processed`). Paths in `backend/Dockerfile` are therefore repo-relative.
- **The ignore file is `backend/Dockerfile.dockerignore`**, not `backend/.dockerignore`. BuildKit looks for `<dockerfile>.dockerignore` within the context; since the context is the repo root, a `backend/.dockerignore` would be silently ignored.
- **`NEXT_PUBLIC_*` is inlined at build time**, so `NEXT_PUBLIC_API_URL` is a build arg and must be the address the *browser* uses (`http://localhost:8000`) — never the compose service name. Changing it requires `--build`.
- **The vector store is seeded by `docker-entrypoint.sh` into a volume**, not baked into the image (it is derived data, and baking it would re-run the whole embedding pass on any layer change). The script gates on a `.lawai-seeded` marker rather than on `chroma.sqlite3`, which chromadb creates on first connect — testing for the sqlite file made a half-finished seed look complete on restart and served an empty corpus. `SKIP_DB_INIT=true` bypasses seeding.

`CHROMADB_PATH` is now actually read by `VectorService` (it was documented in `.env.example` for a long time while nothing consumed it); the container points it at the mounted volume.

The image installs **CPU-only torch** (`--index-url .../whl/cpu`) before the requirements, or the default CUDA wheel adds ~2.5 GB for nothing, and bakes `all-MiniLM-L6-v2` in with `HF_HUB_OFFLINE=1` — without that flag sentence-transformers still makes ~20 revalidation calls to huggingface.co on every start.

Tests requiring a live LLM are marked `live` and skip automatically unless `AIML_API_KEY` is set, so a plain `pytest` run is green without credentials (currently 421 passed, 8 skipped).

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
- **Documents are chunked before embedding.** `all-MiniLM-L6-v2` truncates at ~256 tokens, so a 60k-character judgement would otherwise be indexed by its first paragraph alone. `init_vector_db.py` splits into ~1200-char overlapping chunks carrying `parent_id` so a hit is still citable to its source. 1,089 documents → 3,184 chunks.
- **A cited section is looked up, not searched for** (`services/retrieval/structured_filter.py`, applied inside `VectorService.search`). A section number is nearly invisible to a dense embedder — "482" and "483" embed to almost the same point and a section's text rarely repeats its own number, so `"section 482 BNSS"` did not surface BNSS 482 anywhere in the top 20. `parse_citation` recognises the citation and the section is fetched by metadata and ranked first, with the vector hits kept behind it (a citation is usually only part of what was asked). This took the citation class from recall@3 0.250 to 1.000 with no other class moving. Pass `structured=False` to measure without it. **A repealed code's number is deliberately refused**: "CrPC 438" means BNSS 482, but BNSS 438 exists and is about something else, so resolving it would turn a miss into a confident wrong answer. Repealed citations resolve their *act* and fall through to vector search. A lettered section ("41A", "65B") is refused for the same reason — no section of the 2023 codes carries one.
- **Corpus queries are expanded before embedding** (`services/query_expansion.py`, applied inside `VectorService.search`). Terms of art often do not appear in the statute they govern — "anticipatory" occurs nowhere in BNSS 482 — and repealed code names ("IPC", "CrPC") appear nowhere in the corpus at all. The curated alias table appends the statutory phrasing; expansion is **additive**, so a working query cannot be made worse, and only the embedded text changes (the generation prompt still carries the user's own wording). Pass `expand=False` to measure unexpanded behaviour. Note a hybrid BM25 retriever would *not* fix this class of miss: the term is absent from the text, so there is nothing to match lexically.
- **`LegalDataLoader` raises if `data/processed/` is missing** rather than falling back to sample data. Silently serving placeholder text from a legal assistant is worse than an error.
- **`main.py` startup swallows init errors** (logs and continues) so `/health` stays up without credentials.

## The legal graph

`services/legal_graph.py` builds an in-memory graph at first use (`get_legal_graph()`, `reset_legal_graph()` for tests) over committed data only. Nodes are keyed by citation — `"BNS 103"`, `"BNSS 482"` — and judgements and doctrines by their own ids. Currently 1,059 sections, 931 cross-references, 34 interprets edges, 16 doctrines, 288 classified sections.

| Edge | Source |
|---|---|
| `section --cross_references--> section` | regex over the statute text |
| `judgement --interprets--> section` | the judgement's `relevant_sections` metadata |
| `doctrine --established_by/refined_by--> judgement` | `data/curated/doctrines.json` |
| `doctrine --applies_to--> section` | same |
| `section --classified_as--> attributes` | `offence_classification.json` |

- **No LLM-inferred edges, ever.** A false relation propagates into every answer touching either endpoint with nothing in the output to show it was invented. Cross-references are mechanical, judgement edges are transcribed metadata, doctrine edges are curated by hand.
- **A reference to another statute is dropped, not redirected.** "section 2 of the Dowry Prohibition Act" must not become an edge to BNS 2. 28 of 2,038 references are foreign and are dropped; a named act ("of the Bharatiya Sakshya Adhiniyam") redirects instead.
- **`data/curated/doctrines.json` carries no precedential status.** No `overruled_by`, no `still_good_law` — highest value, highest harm, and not something to infer or freeze into a file that ages. Where authority genuinely splits, the doctrine is marked `contested` with both sides named and neither declared the winner (`statutory_bail_bar`, `sedition_confined_to_incitement`). `graph.contested_sections()` is what the contested path will consult, since a user who does not know a question is contested will not think to ask.
- Offence rows key sub-sections (`103(1)`) while the corpus keys the parent (`103`); the graph attaches them to the parent so either lookup works.

## Legal corpus

`data/processed/*.json` is committed, so the project runs without re-fetching. Regenerate only when the source changes.

| Collection | Source | Records |
|---|---|---|
| `bns_sections` | MHA gazette PDF | 358 (complete) |
| `bnss_sections` | MHA gazette PDF | 531 (complete) |
| `bsa_sections` | MHA gazette PDF | 170 (complete) |
| `sc_judgements` | Indian Kanoon (curated, id-pinned) | 30 |
| `offence_classification.json` | BNSS First Schedule, Part I | 465 rows (not a vector collection) |

Two things about `ingest_legal_acts.py` that look odd but are deliberate:
- Text is extracted with `x_tolerance=1.0`; pdfplumber's default glues words together in this font ("isdoubtfulof"), wrecking embeddings and display.
- Section titles are gazette *marginal notes* and extract out of order, so they are bound to sections by **vertical position**, not reading order.

### Offence classification (`ingest_offence_schedule.py`)

The BNSS First Schedule classifies every punishable BNS section as cognizable or not, bailable or not, and names the court that tries it. That is a lookup, not a retrieval problem, so it is parsed into `data/processed/offence_classification.json` and answered without a model. Four things about the parser are load-bearing:

- **Column edges are measured per page, not assumed.** The gazette re-flows the table on every page: column 4 starts at x0 285 on page 158 and 304 on page 163. A single set of edges silently pushed "2 years" into the cognizable column on page 188, which then read "2 Non-cognizable." and resolved to nothing. Edges are recovered from the vocabulary each column opens with (`PUNISHMENT_OPENERS`, `COGNIZABLE_OPENERS`, …).
- **Words are grouped into runs before being placed.** Wrapped text drifts right — a column-4 continuation reaches x0 367, inside column 5's tolerance — so only a run's leading word decides its column.
- **Rows are found by asking whether a line refills a cell**, not by vertical gaps (page 161 sets rows and lines the same 10.2pt apart) and not by the section column (BNS 356(2) is classified twice, once for defamation of the President and once "in any other case", with column 1 blank on the second row).
- **A conditional cell is never resolved to a boolean.** ~40 rows read "According as offence abetted is cognizable or non-cognizable"; those keep `cognizable`/`bailable` as `null` with the schedule's own wording in `cognizable_text`/`bailable_text`. A guessed "bailable" is the most dangerous value this system can emit.

`tests/unit/test_offence_schedule.py` pins 21 offences transcribed by eye from the PDF, and asserts invariants over the other 444.

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

Next.js **Pages Router** (`frontend/pages/`), not App Router. One page (`index.tsx`) hosting five workspaces defined in `lib/workspaces.ts` — Ask, Corpus, Live research, Draft, Analyse — inside `components/layout/AppShell.tsx`. Selection is mirrored to the URL hash. Feature UIs in `components/{chat,search,research,documents,shared}/`, data-fetching in `hooks/use*.ts`, all HTTP centralised in `lib/api.ts`.

- **Colour comes only from tokens.** `styles/globals.css` defines CSS custom properties under `:root` and `.dark`; `tailwind.config.js` maps them to semantic names (`canvas`, `surface`, `ink`, `muted`, `line`, `brand`, `brass`, `verified`, `live`). A raw hex or a stock Tailwind grey in a component breaks dark mode. `darkMode: 'class'`, toggled on `<html>` by `hooks/useTheme.ts`; `pages/_document.tsx` exists solely to apply the stored theme before first paint (React cannot hydrate before the browser paints, so without it dark-mode users get a white flash).
- **Provenance is a visual contract.** Verified corpus hits render through `SourceCard` in the `verified` palette; live judiciary hits render through `research/JudgmentCard` in the `live` palette with a source link. Never merge the two lists — the API deliberately returns `sources` and `live_sources` separately for the same reason.
- **`DraftForm` gets its document types from `GET /documents/templates`**, not a local list. It previously carried its own menu, which offered "Affidavit" while the API rejected it. The server owns the structure; the component owns labels and input types.
- **Answers are stripped before rendering** (`stripAppendedBlocks` in `lib/api.ts`). The backend appends `**Sources:**` and `**DISCLAIMER**` blocks to `response`/`answer` for plain-text consumers; the UI renders both itself, so leaving them in showed the disclaimer twice and the citations twice.
- **Chat uses the non-streaming agent endpoint.** Agent streaming is faux (see above), so it costs nothing in latency and would discard the structured `sources`. Real streaming primitives remain in `lib/api.ts` (`agent.queryStream`, `readStream`) for `/chat`.

## Conventions

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- Project rules live in `RULES.md` and `AGENTS.md`; both defer to this file where they disagree.
