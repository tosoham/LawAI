# LawAI Rebuild Plan — Drop IBM watsonx.ai, finish the project

**Status:** In progress. Approved 2026-08-03.
**Owner:** tosoham · **Progress log:** [PROGRESS.md](PROGRESS.md) · **Key facts:** [context.md](context.md)

## Context

LawAI was built for a hackathon where IBM watsonx.ai (Granite-13b) was a locked, non-negotiable
requirement. The hackathon is over, so that constraint is gone. We are moving the LLM layer to
**AIML API** (aimlapi.com — OpenAI-compatible endpoint, default model `gpt-4o-mini`) and using the
opportunity to do a full rebuild pass: fix the parts of the agent/tool layer that were stubbed or
inconsistent, and replace the 27-item hardcoded demo dataset with a real ingestion pipeline pulling
verbatim text from official government sources plus curated landmark Supreme Court judgments.

Work proceeds in 4 phases, each implemented and verified before moving on.

## Feasibility verified during planning

- Sandbox has real outbound internet via `curl`/`requests` (not just the summarizing WebFetch tool).
- Official MHA gazette PDFs for all three codes download cleanly (URLs in [context.md](context.md)).
- `pypdf` extracts clean per-page text from the BNS PDF, with `<number>. <title>.—<body>` section
  markers and `CHAPTER <N>` headers → regex splitting is viable for **full** coverage
  (BNS ~358 sections, BNSS ~531, BSA ~170), not just a curated subset.
- `indiankanoon.org/doc/<id>/` pages parse cleanly with BeautifulSoup via `.doc_title`,
  `.doc_citations`, `.doc_bench`, `.judgments` selectors.

## Phase 1 — Swap LLM provider (IBM watsonx.ai → AIML API)

Rewrite `backend/services/llm_service.py` keeping its **exact existing public interface**, so no call
site changes are needed in `chat_tool.py`, `draft_document_tool.py`, `analyze_doc_tool.py`,
`intent_classifier.py`, `rag_service.py`, `chat.py`:

- `generate(prompt: str, **kwargs) -> str`
- `async generate_stream(prompt: str, **kwargs) -> AsyncIterator[str]`
- `get_model_info() -> dict`

Implementation: `openai` SDK pointed at AIML API via `base_url`. Sync `OpenAI` client for
`generate()`; `AsyncOpenAI` with `stream=True` for `generate_stream()` — this also fixes the current
code's fake-async blocking loop. Client construction is **lazy** so a missing API key no longer
crashes the app at import (previously `llm_service = LLMService()` at module scope would raise).

Also in this phase:
- Standardize generation kwargs on OpenAI names (`max_tokens`/`temperature`). `chat.py` currently
  builds the watsonx-ism `max_new_tokens`; accept it as a back-compat alias.
- Update hardcoded model names in `main.py` (`/api/v1/info`), `agents/agent_service.py`,
  `models/responses.py` schema examples, `scripts/health_check.py`.
- Rewrite `tests/unit/test_llm_service.py` (currently patches `WatsonxLLM` directly).
- Delete stale artifacts: `backend/test_phase2a.py`, `backend/health_check_report.txt`.

## Phase 2 — Fix real bugs found while mapping call sites

- `draft_document_tool.py` / `analyze_doc_tool.py` call `llm_service.generate()` synchronously
  without `asyncio.to_thread` (unlike `chat_tool.py`), blocking the event loop → wrap both.
- `draft_document_tool.py` lacks an `agreement` template although `DraftDocumentRequest` permits
  `agreement` → add it.
- `legal_agent.py::_execute_draft_node` hardcodes `document_type="bail_application"` → infer from
  the query with a keyword map, matching how `intent_classifier.py` already routes.
- `models/requests.py` / `responses.py` contain dead duplicate models (`DocumentAnalysisRequest`, a
  second `DraftDocumentRequest`, `RAGSearchResponse`, `DocumentAnalysisResponse`,
  `DraftDocumentResponse`) while `api/v1/documents.py` defines its own local ones → consolidate into
  `models/` as the single source of truth.

## Phase 3 — Real legal data ingestion

- **`backend/scripts/ingest_legal_acts.py`** — download the 3 official MHA PDFs into
  `data/raw/{bns,bnss,bsa}/`, extract with `pypdf`, strip headers/footers, regex-split into sections
  (capturing chapter + section number + title), write `data/processed/{bns,bnss,bsa}_sections.json`.
- **`backend/scripts/ingest_judgments.py`** — read a curated manifest of landmark SC judgments
  (bail, criminal procedure, evidence), fetch each from indiankanoon, parse with BeautifulSoup,
  write `data/processed/sc_judgements.json`.
- Rewrite `services/data_loader.py` to load those JSON files, keeping the same method signatures so
  `scripts/init_vector_db.py` needs no changes. Re-seed ChromaDB.

Output must match the existing dict schema consumed by `VectorService.add_documents` — see
[context.md](context.md#legal-data-schema).

## Phase 4 — Cleanup and rebranding

Remove "Powered by IBM watsonx.ai" / "Granite-13b-chat-v2" from `frontend/pages/index.tsx` and
`demo.tsx`; update `AGENTS.md`, `RULES.md`, `.bob/rules-*/AGENTS.md`,
`docs/COMPLETE_IMPLEMENTATION_PLAN.md`, `README.md`.

## Verification

- `cd backend && pytest` — full suite green.
- `uvicorn main:app --reload`; hit `/api/v1/agent/health`, `/api/v1/chat/health` (needs a real
  `AIML_API_KEY` in `backend/.env`).
- `python scripts/init_vector_db.py`, then `/api/v1/search/collections` — expect real counts
  (300+/500+/150+/25+) instead of 8/7/7/5.
- Exercise the 3 demo flows via `/api/v1/agent/query` and the frontend dev server.
- `cd frontend && npm run lint && npm run type-check`.
