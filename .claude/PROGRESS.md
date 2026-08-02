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

## Phase 5 — Live end-to-end verification ✅ (commits `a2ef483`, `e5fa4b4`, `051d5a1`)

With a real `AIML_API_KEY` the 28 previously-skipped tests could finally run, and they
exposed a cluster of defects that mocking could never have caught.

**`frontend/lib/api.ts` had never been committed.** An unanchored `lib/` rule in
`.gitignore` (meant for Python distutils output) also matched `frontend/lib/`, so the API
client every frontend module imports was silently excluded — a fresh clone could not build.

**Search was broken end to end**, in three independent ways: the frontend called
`/search/rag` while the backend served `/search/` (404); it sent `collection="bns_sections"`
while the model accepted only short aliases (422); and it read `results.results[].content`
while the API returns `answer` + `sources[].text` (would have thrown on every success, and
never displayed the generated answer). All three fixed.

**`POST /documents/export/docx` did not exist** despite the frontend calling it, CLAUDE.md
documenting it and the README promising a downloadable .docx. Implemented.

**The two streaming endpoints spoke different SSE dialects** — `/chat` emitted
`{"type":"token","content":…}`, the agent emitted `{"token":…}`, and the frontend parser only
understood the latter, so streaming chat rendered nothing. Unified on `{"token":…}` + `[DONE]`.

Agent and classifier: the analyze node returned a bare dict where the formatter detects
payloads with `hasattr(result, "success")`, so analysis came back empty; and "Tell me about
bail" was answered by *drafting a bail application*, because draft/analyse matched on
ordinary legal vocabulary. Those intents now require an action verb (verified over 21 queries).

The four missing judgements were resolved with Indian Kanoon's `title:` + date operators.
One of them nearly went in wrong: the first Bhajan Lal id matched the expected title tokens
but was a **1992 contempt petition between the same parties**, caught only by checking the
body text. `JudgementSpec` now takes `expect_text` phrases that must appear in the body.

Lint was version-dependent (ruff 0.1.14 → a handful of findings; 0.16 → ~1,300 on identical
code), which is why it was never addressed. `backend/pyproject.toml` now pins the rule set.
Three fixes there were substantive: `zip(..., strict=True)` in the citation path (silent
truncation would have dropped sources backing an answer), `datetime.utcnow()` → `now(UTC)`,
and Pydantic `class Config` → `ConfigDict`.

---

## Current state

- **154 passed, 0 skipped, 0 failed** — including live LLM calls and 8 e2e tests against a
  running server.
- `ruff check .` clean; frontend lint, `tsc --noEmit` and `next build` all clean.
- Corpus: 358 BNS + 531 BNSS + 170 BSA sections + **30** Supreme Court judgements
  = 1,089 documents → 3,320 chunks.
- All three demo flows verified live: bail drafting cites BNSS 479/482; case-law search
  answers the anticipatory-bail duration question citing Sushila Aggarwal and Sibbia;
  analysis flags indemnity and non-refundable-deposit risks.

## Known limitations

- **Bhajan Lal is stored abridged.** Indian Kanoon serves ~27k chars for that judgement
  (ending near paragraph 12), so the famous seven-category list at paragraph 102 is not in
  the corpus. The entry's `subject` describes what is actually stored.
- Judgements are truncated at 60,000 characters before embedding.
- Retrieval is embedding-only, so a query phrased in words absent from a section's text can
  miss it — e.g. "anticipatory bail" does not appear in BNSS 482 ("Direction for grant of
  bail to person apprehending arrest"), which ranks below BNSS 480/483 for that phrase.
  A hybrid keyword + vector search would close this gap.
- Agent streaming is still faux-streaming (the graph runs to completion, then the string is
  chunked). Real token streaming exists on `/chat`.
