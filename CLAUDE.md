# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LawAI is a multi-agent Indian legal AI system. A LangGraph agent classifies user intent and routes to one of four tools (rag_search, chat, draft_document, analyze_doc) backed by an IBM watsonx.ai Granite LLM and a ChromaDB vector store of the post-2023 Indian legal codes (BNS/BNSS/BSA + Supreme Court judgements). FastAPI backend, Next.js (Pages Router) frontend.

## Locked constraints (non-negotiable)

- **LLM must be IBM watsonx.ai Granite via `langchain-ibm`** (`from langchain_ibm import WatsonxLLM`). Never substitute OpenAI or another provider — this is a hard project requirement, see `.bob/rules-code/AGENTS.md` and `RULES.md`.
- **Legal framework is the 2023 codes**, not the old ones. Collections are `bns_sections`, `bnss_sections`, `bsa_sections`, `sc_judgements` (defined in `backend/services/vector_service.py`). Note: `.bob/rules-code/AGENTS.md` still references legacy `ipc_sections`/`crpc_sections` names — the code/2023 framework is authoritative, ignore the stale rule.

## Commands

All backend commands run **from the `backend/` directory** — imports are rooted there (e.g. `from api.v1.chat import ...`, `from services.llm_service import ...`), so running from repo root breaks imports.

```bash
# Backend (from backend/)
pip install -r requirements.txt
cp .env.example .env            # then fill IBM_WATSONX_* credentials — required for LLM init
uvicorn main:app --reload       # serves on :8000, docs at /docs
python scripts/init_vector_db.py  # seed ChromaDB collections with sample legal data

pytest                          # all backend tests
pytest tests/unit/test_tools.py -v          # single file
pytest tests/unit/test_tools.py::test_name  # single test
pytest --cov=backend --cov-report=html

ruff check .                    # lint
black .                         # format
mypy .                          # type check

# Frontend (from frontend/)
npm install
cp .env.local.example .env.local
npm run dev                     # serves on :3000
npm run lint
npm run type-check              # tsc --noEmit
```

## Architecture

Request flow: **frontend `lib/api.ts` → FastAPI router (`api/v1/*.py`) → service/tool → LLM/vector store**.

- **Agent orchestration** (`backend/agents/`): `AgentService` (singleton, `get_agent_service()`) wraps `LegalAgent`, a compiled LangGraph `StateGraph`. Flow: `classify_intent` → conditional edge by intent → one tool node → `format_response` → END. State shape is in `agents/state.py` (`AgentState`, `IntentType`). Unknown intent defaults to RAG search.
- **Intent classification** (`agents/intent_classifier.py`): primarily keyword/regex matching against `INTENT_PATTERNS`, with LLM fallback. Not a pure LLM classifier.
- **Tools** (`backend/tools/`): all subclass `BaseTool` and return a `ToolResult`. Registered at startup into a global `ToolRegistry` (`tools/registry.py`, `initialize_tools()` called from `main.py`'s `startup_event`). Add a tool by subclassing `BaseTool` and registering it in `initialize_tools`.
- **Services** (`backend/services/`): `LLMService` (singleton, `WatsonxLLM`), `RAGService` (vector search + prompt + generate, appends a legal disclaimer to every answer), `VectorService` (ChromaDB persistent client), `EmbeddingService` (sentence-transformers), `DataLoader`.
- **Singletons everywhere**: `llm_service`, `get_agent_service()`, `get_rag_service()`, `get_vector_service()`, `get_tool_registry()`. Use the accessors; `reset_agent_service()` exists for tests.

### Non-obvious behaviors

- **"Streaming" is faux-streaming.** `AgentService.process_query_stream` runs the graph to completion, then slices the finished string into 50-char SSE chunks (`data: {"token": ...}` / `data: [DONE]`). It does not stream tokens live from watsonx. `LLMService.generate_stream` (real streaming) exists but the agent path doesn't use it. The frontend `readStream` in `lib/api.ts` parses that SSE format.
- **ChromaDB path is CWD-relative** (`VectorService` defaults to `./chroma_db`). Running from `backend/` uses `backend/chroma_db`; there is also a `chroma_db/` at repo root — be aware which one is active based on where you launched the process.
- The agent's `_execute_draft_node` currently hardcodes `document_type="bail_application"`; `_execute_analyze_node` returns a "please upload" stub. The full draft/analyze functionality lives in the direct REST endpoints (`/api/v1/documents/draft`, `/analyze`), not the agent graph.
- `main.py` startup swallows init errors (logs and continues with limited functionality) so `/health` stays up even without valid credentials.

## API surface (`/api/v1`)

- `agent/query`, `agent/query/stream` — main agent entry points
- `search/rag` — direct RAG search over a chosen collection
- `documents/draft`, `documents/analyze`, `documents/export/docx`, `documents/templates`
- `chat/*`, plus `health`/`info` at several levels

Request/response Pydantic models are in `backend/models/`; the mirrored TypeScript types are in `frontend/lib/api.ts`. Keep them in sync when changing a contract.

## Frontend

Next.js **Pages Router** (`frontend/pages/`), not App Router. Feature UIs in `components/{chat,search,documents,shared}/`, data-fetching in `hooks/use*.ts`, all HTTP centralized in `lib/api.ts`. State via `zustand`. Every AI-generated output must surface the `LegalDisclaimer` component.

## Conventions

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- Legal citations follow the 2023 codes (e.g. "Section X, Bharatiya Nyaya Sanhita, 2023"). AI-generated documents/answers always carry a disclaimer.
- Files carry a `# Made with Bob` trailer — this repo was scaffolded with Bob; project rules live in `RULES.md`, `AGENTS.md`, and `.bob/rules-*/AGENTS.md`.
