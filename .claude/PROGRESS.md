# LawAI rebuild — progress log

Rebuild to drop the hackathon's IBM watsonx.ai requirement and finish the project.
Plan: [plan.md](plan.md) · Key facts: [context.md](context.md)

**All four phases complete.** Suite: **105 passed, 28 skipped** (skips are live-LLM tests,
which need `AIML_API_KEY`).

---

## Phase 1 — LLM provider swap ✅ (commit `fbcab87`)

IBM watsonx.ai → AIML API (OpenAI-compatible, default `gpt-4o-mini`).

- Rewrote `LLMService` on the `openai` SDK, keeping the same public interface
  (`generate` / `generate_stream` / `get_model_info`) so no tool or service call site changed.
- Clients are built **lazily**: a missing key previously crashed the app at import because the
  module-level singleton raised in `__init__`. Health endpoints now stay up.
- `generate_stream` streams for real (`stream=True`) instead of blocking inside an `async def`.
- Standardised generation kwargs on OpenAI names, with `max_new_tokens` kept as an alias.
- Modernised `requirements.txt` — the old pins could not install on Python 3.13.
- Rewrote `test_llm_service.py`; deleted `test_phase2a.py` and `health_check_report.txt`.

## Phase 2 — Real bugs found while tracing call sites ✅ (commit `fbcab87`)

The test suite could not even *collect* before this, which is why these had gone unnoticed.

| Bug | Impact |
|---|---|
| `rag_service` scored distance `0.0` as relevance `0.0` (falsy check) | Perfect matches ranked **worst**; ranking inverted |
| `legal_agent` read draft text from `content`, tool returns `document` | Agent-routed drafts rendered **empty** |
| `legal_agent` looked up `analyze_doc`, tool registers as `analyze_document` | Lookup always returned `None` |
| `legal_agent` hardcoded `document_type="bail_application"` | Every draft was a bail application |
| `intent_classifier` broke ties in enum order | "what can you help me with?" went to vector search |
| `/documents/templates` declared `Dict[str, str]` but sends a list | Endpoint always **500**'d |
| Draft/analyze tools called the LLM synchronously | Blocked the event loop |
| `agreement` accepted by the request model but had no template | Valid request failed |

Also consolidated duplicate request/response models into `backend/models/`, and added
`pytest.ini` (tests imported `backend.*` while the app imports `services.*` — the same modules
under two names would have duplicated every singleton).

## Phase 3 — Real legal corpus ✅ (commit `cbd7433`)

Replaced 27 hand-written demo records with the actual law.

- `scripts/ingest_legal_acts.py` — official MHA gazette PDFs → **358 BNS, 531 BNSS, 170 BSA**
  sections. Complete and correct counts, contiguous, all titled.
- `scripts/ingest_judgments.py` — **27** landmark Supreme Court judgements, each pinned by
  document id and re-verified on fetch.
- `init_vector_db.py` now **chunks before embedding** (the embedding model truncates at ~256
  tokens, so long judgements were indexed by their first paragraph only) and supports reset.
- `data_loader.py` reads `data/processed/` and raises if absent instead of serving placeholders.
- Stopped tracking `backend/chroma_db` (51 MB of binaries were in git).

Retrieval verified end to end — see [context.md](context.md#retrieval).

## Phase 4 — Cleanup and rebranding ✅

- Removed IBM/Granite branding from `frontend/pages/index.tsx` and `demo.tsx`.
- Stripped "Made with Bob" trailers from 54 files and deleted `.bob/` (its rules asserted IBM
  was non-negotiable and referenced legacy `ipc_sections`/`crpc_sections` collection names —
  actively misleading now). Recoverable from git history.
- Rewrote `CLAUDE.md` and `AGENTS.md`; updated `README.md` and `RULES.md`.
- Added a correction banner to `docs/COMPLETE_IMPLEMENTATION_PLAN.md` rather than rewriting
  the historical plan.

---

## Not done / deliberately left

- **Four judgements omitted** — Bhajan Lal, Selvi, the 2017 nine-judge Puttaswamy, and the
  2014 Mohd. Arif review. Search returned the wrong case or a later order, and an unverified
  citation is worse than a missing one. Needs manual id lookup.
- **`ruff` backlog (~400 findings)**, almost entirely pre-existing style/modernisation items.
  Worth its own dedicated commit.
- **Live end-to-end LLM verification** — everything up to the provider call is exercised, but
  no real generation has run because `AIML_API_KEY` is empty. Set it and run
  `pytest -m live` plus the three demo flows.
- **BNSS ingestion logs ~966 unaligned marginal notes.** Output is correct (531/531 sections,
  all titled, spot-checked against real law); the count comes from the long
  arrangement-of-sections index at the front of that PDF. Cosmetic, but worth silencing.
