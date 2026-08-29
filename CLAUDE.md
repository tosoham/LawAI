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
python scripts/ingest_concordance.py  # BPR&D tables -> repealed_concordance.json
python scripts/init_vector_db.py      # chunk + embed into backend/chroma_db/

uvicorn main:app --reload       # serves on :8000, docs at /docs

pytest                          # all backend tests
pytest tests/unit/test_tools.py -v          # single file
pytest tests/unit/test_tools.py::test_name  # single test
pytest --cov=. --cov-report=html

ruff check .                    # lint (clean; keep it that way)
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

Five things here are load-bearing and easy to break:

- **The backend build context is the repo root, not `backend/`.** `data_loader.py` resolves the corpus as `backend/../data/processed`, so the image must preserve that relative layout (`/app/backend` + `/app/data/processed`). Paths in `backend/Dockerfile` are therefore repo-relative.
- **The ignore file is `backend/Dockerfile.dockerignore`**, not `backend/.dockerignore`. BuildKit looks for `<dockerfile>.dockerignore` within the context; since the context is the repo root, a `backend/.dockerignore` would be silently ignored.
- **`NEXT_PUBLIC_*` is inlined at build time**, so `NEXT_PUBLIC_API_URL` is a build arg and must be the address the *browser* uses (`http://localhost:8000`) — never the compose service name. Changing it requires `--build`.
- **The image must copy `data/curated` as well as `data/processed`.** Both are committed data and both are load-bearing: `legal_graph` refuses to build without `doctrines.json`, which takes the grounded answer path and every `/offences` response down with it. Copying only `data/processed` produced a container that passed its health check and 500-ed on the first real question — found by running it, not by any test.
- **The index can be baked in, and is not by default.** `--build-arg BAKE_INDEX=true` builds it into `/opt/chroma_seed` and the entrypoint copies it into the volume on a first start, turning a ~12-minute cold seed into a copy. Off by default because the layer invalidates whenever `services/` or `scripts/` changes, so every local rebuild would re-embed 9,896 chunks — twelve minutes at build time to save twelve at a start that happens once. CI passes the flag; `docker compose up --build` does not. Written to `/opt` rather than `CHROMADB_PATH` because the latter is a mounted volume at run time and anything written there during the build is masked the moment the volume appears, and copied in only when the volume is empty, since a volume with contents is either current (init is a no-op) or stale (init tops up what moved).
- **The vector store is otherwise seeded by `docker-entrypoint.sh` into a volume**, not baked into the image (it is derived data, and baking it would re-run the whole embedding pass on any layer change). The script gates on a `.lawai-seeded` marker rather than on `chroma.sqlite3`, which chromadb creates on first connect — testing for the sqlite file made a half-finished seed look complete on restart and served an empty corpus. `SKIP_DB_INIT=true` bypasses seeding.

`CHROMADB_PATH` is now actually read by `VectorService` (it was documented in `.env.example` for a long time while nothing consumed it); the container points it at the mounted volume.

The image installs **CPU-only torch** (`--index-url .../whl/cpu`) before the requirements, or the default CUDA wheel adds ~2.5 GB for nothing, and bakes `all-MiniLM-L6-v2` in with `HF_HUB_OFFLINE=1` — without that flag sentence-transformers still makes ~20 revalidation calls to huggingface.co on every start.

Tests requiring a live LLM are marked `live` and skip automatically unless `AIML_API_KEY` is set, so a plain `pytest` run is green without credentials (currently 703 passed (plus 58 live)).

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
- **Documents are chunked before embedding.** `all-MiniLM-L6-v2` truncates at ~256 tokens, so a 60k-character judgement would otherwise be indexed by its first paragraph alone. `init_vector_db.py` splits into ~1200-char overlapping chunks carrying `parent_id` so a hit is still citable to its source. 1,359 documents → 9,896 chunks.
- **A cited section is looked up, not searched for** (`services/retrieval/structured_filter.py`, applied inside `VectorService.search`). A section number is nearly invisible to a dense embedder — "482" and "483" embed to almost the same point and a section's text rarely repeats its own number, so `"section 482 BNSS"` did not surface BNSS 482 anywhere in the top 20. `parse_citation` recognises the citation and the section is fetched by metadata and ranked first, with the vector hits kept behind it (a citation is usually only part of what was asked). This took the citation class from recall@3 0.250 to 1.000 with no other class moving. Pass `structured=False` to measure without it. **A repealed code's number is deliberately refused**: "CrPC 438" means BNSS 482, but BNSS 438 exists and is about something else, so resolving it would turn a miss into a confident wrong answer. Repealed citations resolve their *act* and fall through to vector search. A lettered section ("41A", "65B") is refused for the same reason — no section of the 2023 codes carries one.
- **Corpus queries are expanded before embedding** (`services/query_expansion.py`, applied inside `VectorService.search`). Terms of art often do not appear in the statute they govern — "anticipatory" occurs nowhere in BNSS 482 — and repealed code names ("IPC", "CrPC") appear nowhere in the corpus at all. The curated alias table appends the statutory phrasing; expansion is **additive**, so a working query cannot be made worse, and only the embedded text changes (the generation prompt still carries the user's own wording). Pass `expand=False` to measure unexpanded behaviour. The claim that used to sit here — that a hybrid BM25 retriever would not fix this class of miss, the term being absent from the text — is right about the raw query and was wrong as a reason not to have BM25. Fed the *expanded* query, BM25 takes `term_of_art` from recall@3 0.250 to 0.938, because what expansion appends is the statute's own phrasing and matching literal text is what BM25 is best at. See the hybrid note below.
- **Retrieval is hybrid: dense + BM25, fused by reciprocal rank fusion** (`services/retrieval/lexical.py`, `ENABLE_HYBRID` defaults on). Worth the complexity only because the two retrievers fail on **disjoint sets** — measured alone over the golden set at recall@3 (dense with the structured filter off, so it is retriever against retriever): citation BM25 **0.875** vs dense 0.250; judgement **1.000** vs 0.833; plain **1.000** vs 0.960; term_of_art BM25 **0.250** vs dense **0.875**. Both failures have one cause read from opposite ends — whether the query's words appear in the answer's text. A citation is almost pure lexical signal; a term of art is absent from the section governing it.
  - **RRF, not a weighted score sum.** BM25 scores are unbounded and corpus-dependent while cosine distances sit in a fixed range, so any weighted sum needs a normalisation that is itself a parameter fitted to 69 queries. RRF reads only ranks. `K1`, `B` and `RRF_K` are left at their published defaults for the same reason — 69 queries is far too few to fit them without fitting the queries.
  - **Both rankings are keyed by `parent_id#chunk_index`**, not by chroma id, because the BM25 index is built from `collection.get` which does not return the ids `collection.query` does. Without a shared identity a chunk found by both appears twice and RRF counts it as two documents one retriever liked rather than one both did — inverting the exact property fusion is bought for.
  - **Not stemmed, not stopworded.** Stemming collapses "bailable" into "bail", which the First Schedule and the BNSS use to mean different things; a stopword list drops the "of" in "abuse of the process of any Court", which is doing real work in BNSS 528. The idf is the non-negative BM25+ form — the textbook one goes negative for a term in more than half the corpus, and "court" is in more than half of `sc_judgements`.

  **Every retrieval layer gets the expanded query, and this was got wrong twice.** Both the reranker and BM25 were first built on the user's raw wording, on the reasoning that expansion is a crutch for an embedder that cannot match a word it never sees. Both times that was backwards: the cross-encoder lost `term_of_art` 0.250 of recall@3, and BM25 scored `term_of_art` 0.250 raw against **0.938** expanded with *not one query regressing*. The alias table does not append vocabulary, it appends the statute's own phrasing — "power of High Court to prevent abuse of process" is nearly verbatim BNSS 528 — so it is not a dense-retrieval workaround but the bridge from what a lawyer says to what the gazette printed, and every retriever needs to cross it.

  **The stack now measures recall@3 1.000 on all 69 golden queries**, every class, with recall@1 0.899. `eval/hybrid.json` is the current baseline.

- **Candidates are reranked by a cross-encoder** (`services/retrieval/reranker.py`, applied inside `VectorService.search`, `ENABLE_RERANK` defaults on). The bi-encoder that builds the index embeds query and chunk separately, which is what makes the index searchable offline and is also its ceiling. Measured before building it: recall@1 0.812 against recall@10 0.986 — in ~19% of queries the right chunk was retrieved and ranked below first, which is a precision gap, not a recall one. That is also why a BM25 hybrid was *not* the move: at recall@10 0.986 there is almost nothing left to recall. After: recall@3 +0.043 overall, recall@1 0.812 → 0.870, recall@10 unmoved, no class regressed. Three things make it safe:
  - **It is scored on the expanded query, not the user's wording.** Built the other way first, on the reasoning that expansion is a crutch for a model that never sees the chunk — that cost `term_of_art` 0.250 of recall@3 and made the whole change a net loss. A cross-encoder shown "grounds for anticipatory bail" still reads a chunk of BNSS 482 that never says "anticipatory". Seeing both texts together does not tell a model they are the same thing; the alias table is what says so.
  - **The exact lookup is merged after reranking**, so a cited section cannot be demoted by the same surface signal that put the citation class at recall@3 0.250 to begin with. `citation` and `repealed_code` measure +0.000 across the board, which is the check that this holds.
  - **It fails soft**: a model that cannot load leaves bi-encoder ranking intact. That is also why the reranker is baked into the Docker image alongside the embedder — under `HF_HUB_OFFLINE=1` an unbaked reranker would start, serve, and silently give up the gain.

  It reorders; it cannot add. Expansion and reranking are not alternatives — unexpanded, BNSS 482 sits at rank 18 and the cross-encoder lifts it into the top 6, but only because expansion-class misses are what put a section in the pool at all.
- **`LegalDataLoader` raises if `data/processed/` is missing** rather than falling back to sample data. Silently serving placeholder text from a legal assistant is worse than an error.
- **`main.py` startup swallows init errors** (logs and continues) so `/health` stays up without credentials.

## Grounding: typed claims, verification, abstention

`POST /api/v1/search/grounded` answers a question as a list of **typed claims**, checks each one, and abstains when none stand. **The agent's `rag_search` path uses it too**, searching all three statute collections together and returning a `verification` block alongside the existing `response`/`sources` keys. The plain `RAGSearchTool` is still registered and still served by `/search/rag`. `services/grounded_answer.py` is the pipeline; `models/claims.py` is the shape everything downstream keys off.

**Synthesis emits claims, not prose.** Each carries an `epistemic_class`, and prose is rendered from them. Emitted rather than annotated afterwards: a classifier reading "Section 103 provides for the death penalty in the rarest of rare cases" cannot tell which half came from the statute and which from Bachan Singh, so post-hoc labelling is a guess about a guess.

**The class is a check, not a label** (`services/claim_verifier.py`). Nothing asks a model whether a model was right — the prior that invented BNS 999 will confirm BNS 999. Every check is a lookup against committed data:

| Class | Check |
|---|---|
| `statute` | the section exists and any quoted span appears in it verbatim |
| `classification` | matches the First Schedule row — checkable only because the Schedule was parsed into a table |
| `holding` / `interpretation` | the case exists, any quoted span appears in its text verbatim, **and** where the graph records edges for it, they must cover the cited section |
| `contested` | rejected below two positions, each with authority |
| `inference` | may rest on nothing, but must not carry a citation formatted as law |

Four findings from running it that are easy to reintroduce:

- **A classification claim must be cited to its own offence's section.** A live answer said correctly that theft is non-bailable and cited BNS 304 — snatching, whose text opens "Theft is snatching if…" — and it passed, because snatching carries the same attributes. Right facts, wrong provision, and the citation is what the reader follows. `match_offences` now binds the claim to the section the First Schedule keys that offence to.
- **A section's Schedule rows can disagree.** BNS 303: "Theft" is non-bailable, "Where value of property is less than 5,000 rupees" is bailable. Checking against the *union* let "theft is bailable" pass. `_rows_the_claim_is_about` picks the row by its own offence wording appearing in the claim, and rejects when the candidates disagree.
- **A quotation is checked against the whole section, not the retrieved chunk.** A section is indexed in pieces; a true quotation from a piece that did not rank is still true. `SectionNode.text` carries the full text for this.
- **Trailing punctuation is stripped from the span only.** BNS 303 reads "or with both and in case of second conviction…"; quoting "or with both." is the same words. Interior punctuation is not touched.
- **Classification attaches to the section that punishes, not the one that defines.** The model reliably cited BNS 101 (defines murder) instead of BNS 103 (punishes it). The prompt, the graph block and the verifier's failure message all now say so; without the last one the model returned `{"claims": []}` on regeneration instead of re-citing.

**One gap is counted rather than gated, and that was decided by measurement.** `judgement --interprets--> section` edges are transcribed from curated `relevant_sections`, which only the 30 pinned judgements carry — at 300 judgements **273 have no edge**, so the check that catches "a real case cited for a section it has nothing to do with" fell from covering 90% of the corpus to 9%. It fails open, silently, and every grounding metric *improved* over the same change. A text-mention check was built to close it (does the judgement name the section it is cited for?, with old numbering translated through the concordance) and **measured against the 34 curated pairs — the only ground truth there is — it rejected 41% of them; the narrowest variant still rejected 32%.** The failures are not tuning: State of Rajasthan v. Balchand is the authority for "bail is the rule, jail the exception" and cites no section number anywhere in its 5,609 characters; Satender Kumar Antil reasons through sections 437 and 439 while being an authority on anticipatory bail too. **A judgement is an authority on provisions it may never number**, so a citation's presence is not evidence of the relation. Rejecting on it would delete true statements — this project's most-repeated failure. So `AnswerMetrics.unverifiable_attribution` counts holding and interpretation claims whose case has no edges, and closing the gap properly is a *data* task (curating `relevant_sections` for discovered cases), not a code one.

**Abstention falls out of verification; it is not a relevance threshold.** That was measured and rejected: the 69 answerable golden queries reach a worst best-distance of 0.577, the 6 adversarial ones go as low as 0.423. The distributions overlap, so any cutoff either refuses real questions or admits invented answers. The gate is whether one claim survives checking. One pre-check runs before generation — a cited section that does not exist ("section 999 of the BNS") is refused without a model call.

**A misquotation loses the quotation, not the claim.** A statute or holding claim whose cited source exists and is the right one, carrying a `verbatim_span` that does not appear in it, used to be deleted whole — throwing away a true statement of law to punish a formatting error. `verify` now re-checks the claim without its span; if it passes (it will, since a paraphrase needs no span and everything else already passed), the span is dropped and the statement survives, with the discarded quotation recorded in `ClaimVerdict.quote_dropped` and in the trace. Re-checked rather than assumed, so this can never become a way round verification — a claim citing BNS 999 fails with or without its quotation. **`verbatim_fidelity` still counts the misquote**: a dropped quote is excluded from `matched`, so a model that quotes badly shows up as a drop exactly as one that stops quoting does. Measured over the golden set: unsupported claims **24 → 12**, clean answers **54 → 62 of 69**, fidelity 0.675 → 0.669, adversarial abstention unchanged at 6/6.

**Failures are removed, not hedged**, and the removal is reported to the reader. One regeneration attempt naming the offending claims comes first; a second failure means the model cannot ground the claim and a third would only produce a more confident version of it.

**The retrieval metrics, and how to read them.** `eval_retrieval.py` reports recall@k, **coverage@k** (what *share* of the expected ids landed — recall@3 hits 1.000 the moment one of four authorities does, which flatters), precision@k, **R-precision**, F1@5, MAP, MRR, nDCG@10 and a first-rank distribution, **per class**. Two cautions are printed with the table: **precision@k is bounded by how many ids a query expects** — 0.200 at k=5 for a single-answer query whatever retrieval does, so a low figure there is arithmetic and not a finding; **R-precision** (precision at k = the expected count) is the one that compares across classes. `--gate` checks per-class floors set *below* the baseline rather than at it, because a gate that fires on any corpus change gets switched off within a month. Read `--compare` for movement and the gate for breakage; a metric the baseline predates shows `--` rather than a rise from zero.

**Two evals, and only one of them can settle a retrieval change.** `scripts/eval_retrieval.py` embeds and ranks with no sampling anywhere, so its diffs are exact and it is what decides a retrieval change. `scripts/eval_grounding.py` runs the same golden set through synthesis, which *is* sampled — measured on two back-to-back runs of unchanged code, overall unsupported moved by 2, abstentions by 3, and **per-class counts by 7**. A per-class swing under about 7 is not evidence of anything. What that harness gates is the grounding invariants, which hold regardless of sampling because they are properties of the deterministic verifier: no unsupported claim survives an answerable query, the answerable set does not collapse into abstention (the ceiling that makes the first gate mean anything — a system that refuses everything emits no claims and trivially passes), and all six adversarial queries abstain.

**Metrics** (`services/answer_metrics.py`) replace a confidence score. `verbatim_fidelity` is measured over *every* statute claim rather than the quoted ones, so a model that stops quoting to avoid being checked shows up as a drop. `unsupported` is totalled across the golden set, never averaged. `metrics.clean` is a per-answer signal, not a shipping gate — the delivered answer never contains an unsupported claim by construction.

`tests/integration/test_grounded_answer_live.py` is the Phase 2 gate: all six adversarial queries must abstain, four answerable ones must not, and murder must never come back bailable. Marked `live`, so it needs `AIML_API_KEY`.

**Audience register** (`services/audience.py`) — `citizen` (default) | `lawyer` | `judge`, on the request. It is a layer on the *synthesis system prompt and nothing else*, and that separation is structural rather than a rule to remember: neither `VectorService.search` nor `claim_verifier.verify` takes an audience argument, so there is no path by which "written for a citizen" could become "checked less carefully for a citizen". Same law retrieved, same claims checked the same way, epistemic classes present in the data whatever the register — a citizen's answer is shorter, not vaguer, and keeps every citation. **Judge mode carries a prohibition the others do not**: set out the provisions, the competing arguments, the authority on each side and the statutory range, and never suggest an outcome — not by implication, ordering or emphasis either. Tested against the real model with prompts that invite one directly.

**The trace panel** (`components/legal/TracePanel.tsx`) is collapsed by default and always one click away: metrics, and every claim the verifier rejected with its reason. "Nothing was removed" is stated rather than left as an absence — otherwise the section's presence reads as a bad sign and its absence as a clean bill of health.

## Accounts and saved conversations

Until this existed a conversation lived in React state: a refresh lost it, and there were no accounts, so there was nothing to lose it *from*. Fine for a demo, wrong for a legal tool, where the thing a person most wants to return to is the answer about their own matter.

- **Google only, and no password anywhere.** `services/auth.py` verifies the ID token with `verify_oauth2_token` — signature, issuer, audience, expiry — rather than decoding it. A JWT payload is base64, not encryption, so reading claims out of an unverified token is trusting whatever the caller wrote. Users are keyed on Google's `sub`, not email: an address can be reassigned inside a Workspace domain, and the new holder would inherit the previous person's conversations.
- **The session is a signed cookie carrying a row id**, not a JWT. A JWT saves a database read and cannot be revoked before expiry; a signed id costs one indexed lookup and means deleting the row ends the session. `httponly` (XSS cannot exfiltrate it), `samesite=lax` (CSRF cover), `secure` unless `AUTH_INSECURE_COOKIES=true`, which exists for `http://localhost` and is named to be uncomfortable elsewhere.
- **Every thread query filters by the signed-in user, in the query.** A thread id is a small integer; an endpoint fetching by id alone would serve one person's legal questions to anyone counting upwards. Someone else's thread is **404, not 403** — 403 confirms the id is real, which is what an enumeration attack wants. Five tests try to get round it.
- **The structured half of an answer is stored with the message** — claims, verdicts, sources, agent trail, as JSON. Without it a reloaded conversation shows prose and loses the claim types, citations and the record of what was removed, which is the part that makes an answer defensible. Kept whole rather than normalised because it is rendered, never queried.
- **SQLite by default** (`DATABASE_URL`), on the same volume as the vector store, so a deployment is one service with one volume to back up. Writers serialise; this workload is reads plus a few small writes per conversation, so that limit is far away. When it is not, the URL changes and nothing else does.
- **Optional throughout.** No `GOOGLE_CLIENT_ID` means no sign-in and every other feature works — only history needs identity.

## Production feedback

`services/feedback.py` records answers worth revisiting, and `scripts/review_feedback.py` is where a person turns them into fixture rows. Off by default (`ENABLE_FEEDBACK_CAPTURE`) because it writes user-typed text to disk.

- **Only self-labelling events are kept**: the system abstained, the verifier removed claims, or retrieval returned nothing. Each says *something went wrong* without needing a human to notice. A clean answer is not stored — a log of everything is a log nobody opens.
- **Production gives queries, not labels.** A user's question does not say what the right answer was, so this is a queue of *candidates*. `--candidates` emits fixture stubs with `expected` deliberately **empty**: filling it from what retrieval returned would assert that the system returns what the system returned, which passes by construction and means nothing — the same trap `docs/ATTRIBUTION_GAP.md` describes for unreviewed model-proposed edges.
- **Capture never fails an answer.** It runs after the answer is built, swallows its own errors, and truncates the query — a legal question can carry facts about a real person, and this is a diagnostic store, not a case file. `backend/feedback/` is gitignored.

## Multi-agent orchestration

`agents/legal_agent.py` compiles one `StateGraph` carrying two paths. Most questions take the
cheap one; the expensive one exists for the questions that need it, and keeping that ratio
right is the whole design problem.

```
classify_intent → triage ┬─ simple ──→ existing single pass (one model call)
                         └─ complex ─→ plan ─Send()─┬ statute   ┐
                                                    ├ case_law  │ parallel
                                                    ├ offence   │ (free)
                                                    └ doctrine  ┘ (free)
                                                          ↓
                                                       gather → verifier → format
```

- **Specialists gather evidence; only the synthesiser emits claims.** The rule the whole
  architecture rests on. Six agents emitting their own conclusions would put generation
  *after* the point `claim_verifier` runs, so part of an answer would be checked and part
  would not, with nothing in the output to say which. `grounded_answer.answer()` takes a
  `retrieved` argument that skips retrieval **and only retrieval** — the citation pre-check,
  graph expansion, synthesis prompt, verification, regeneration, abstention and metrics all
  still run. A fanned-out answer is checked by identical machinery to a single-pass one.
- **Triage's job is mostly to say no** (`agents/triage.py`). No model call of its own, because
  a triage step that costs a call has already spent a fraction of what escalating costs.
  Measured over the fixture: **69 of 69 answerable golden queries and 6 of 6 adversarial ones
  stay `simple`.** Only a question *about the law* is ever escalated — drafting, analysis,
  chat and live research go to their own nodes whatever triage thought.
- **Two specialists make no model call at all.** `offence` reads the First Schedule, `doctrine`
  reads the curated graph. Free, identical every run, and incapable of hallucinating; tests
  assert `model_calls == 0` so a refactor cannot quietly put a model in either path. The
  planner prompt is told they cost nothing, so it prefers them.
- **The retrieve loop is bounded three ways** (`agents/specialists/base.py`). The budget is
  *spent* rather than consulted, so the cap counts total corpus queries and not follow-ups; a
  follow-up returning nothing new ends the loop, because a model asked what else it needs will
  always find something to ask for; and a budget of one does not even plan a follow-up, which
  saves the model call rather than just the query.
- **`AgentState` needs reducers, and this fails at runtime rather than import.** `evidence`
  and `errors` accumulate; `tool_results` merges by specialist key rather than deep-merging,
  since a deep merge fuses two agents' findings and loses which produced what. `messages`
  accumulates so a checkpointed conversation appends each turn instead of replacing it.
  **`update_state` drops accumulating fields unless explicitly passed** — every node returns
  the whole state, and LangGraph applies `operator.add` to whatever a node returns, so a
  passthrough node appends the list to itself.
- **The contested path is the one place a second agent does something one agent cannot**
  (`agents/contested.py`). Round one independent so neither anchors; round two one rebuttal
  each; then it stops, because open dialogue converges and **convergence is the failure** — a
  conceding advocate leaves one position, which the verifier rejects for carrying fewer than
  two, so a "successful" debate produces an abstention. Neither may concede or invent; an
  unsupported position is reported, not dropped. The two sides come from the curated
  doctrine's `contest_note`, which already names both without declaring a winner.
- **Memory and the draft pause are off by default** (`ENABLE_CONVERSATION_MEMORY`,
  `ENABLE_DRAFT_CONFIRMATION`). The available checkpointer keeps threads in process memory, so
  switching it on is a decision about where state lives. Note `interrupt` signals by raising
  `GraphInterrupt`, which is an `Exception` — it must sit outside a node's `except Exception`
  or the pause is swallowed and reported as a failed draft.
- **The agent trail is reported** (`agent_trail` on the response, rendered by `TracePanel`).
  Null on the single-pass path. It carries triage's reason, the plan, per-specialist costs and
  both contested positions — because an answer that consulted four researchers and one that
  consulted one look identical once written, and the fan-out's whole risk is that it quietly
  becomes the default.

## Structured lookups

Two things the corpus holds under an exact key, looked up rather than searched for (`services/retrieval/`):

- **`structured_filter.py`** — a cited section (see the retrieval note below), including a repealed one, translated through the concordance.
- **`offence_lookup.py`** — "is murder bailable" → BNS 103. Classification vocabulary ("bailable", "cognizable", "triable by") appears nowhere in the BNS, so the query pulls the embedder towards whatever prose is nearest: BNS 103 ranks *sixth* for that question and never reaches the model, and BNS 303 does not surface in the top 8 for "is theft bailable". The First Schedule names every offence in a column of its own, so the match is exact. Only fires on a classification question, and returns nothing for a phrase generic enough to hit the whole table.

## The procedural timeline

`services/procedural_timeline.py` answers the question behind "is this bailable?" — *how long can they hold me, and when does something have to happen?* — from five sections of the BNSS that scatter the answer: 35 (arrest without warrant), 57 (production before a Magistrate), 58 (24 hours), 187 (remand, and the 60/90-day limit), 193 (investigation report), 479 (undertrial release). Served by `GET /api/v1/offences/{act}/{section}`.

Nothing is generated. The steps and their sections are fixed; the only variation is a branch the statute itself draws in **BNSS 187(3)** — ninety days where the offence is "punishable with death, imprisonment for life or imprisonment for a term of ten years or more", sixty otherwise — read off the First Schedule's punishment column.

- **Where the punishment cannot be read, it refuses to pick.** ~110 rows say things like "Same as for offence abetted" or "Fine only". Telling someone they have sixty days when they have ninety is precisely the confident wrong answer this system exists to refuse, so the step reads "60 or 90 days" and says why.
- **BNSS 479 is withheld where the statute withholds it** — it excludes offences punishable with death or life imprisonment, so it does not appear on a murder timeline.
- A non-cognizable offence marks the warrantless-arrest step *conditional* rather than dropping it; the step still belongs in the sequence.
- Where a section is classified more than once and the rows disagree on severity (theft vs petty theft), the timeline is built from the **most serious**, since that is the exposure a person actually faces.
- The gazette's line-break hyphens survive into the Schedule ("imprison- ment for life"), and are normalised before parsing — otherwise a life sentence reads as no sentence at all.

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

**Expansion into generation.** `RAGService` seeds `graph.expand()` from the top 3 retrieved chunks (a low-ranked chunk drags in material about something the user did not ask about) and renders the result into a `CONNECTED MATERIAL` prompt block. It does **not** change retrieval ranking — the eval is byte-identical with it on and off. The four kinds are rendered separately and that separation is load-bearing, not cosmetic:

| Kind | What the prompt says |
|---|---|
| Offence classification | facts from the First Schedule; **may be stated** |
| Doctrine | curated summary; **may be stated**, attributed to its cases |
| Judgements | case name + one-line subject only; may be cited, **must not** be described as holding anything |
| Cross-referenced sections | titles only; may be pointed to, **must not** be described |
| Contested | both positions must be given; one must not be presented as the answer |

Flattening pointers and content into one "related material" block is exactly how a pointer becomes a fabricated holding. `graph_context` is returned separately from `sources` for the same reason: it was reached by an edge, not retrieved by relevance, and the two must stay distinguishable to the UI. Judgement citations are trimmed to the leading report by `agents/citations.py::primary_citation` — Indian Kanoon lists every reporter, and Siddharam Mhetre alone carries 24 parallel citations past 900 characters.

## Legal corpus

`data/processed/*.json` is committed, so the project runs without re-fetching. Regenerate only when the source changes.

| Collection | Source | Records |
|---|---|---|
| `bns_sections` | MHA gazette PDF | 358 (complete) |
| `bnss_sections` | MHA gazette PDF | 531 (complete) |
| `bsa_sections` | MHA gazette PDF | 170 (complete) |
| `sc_judgements` | Indian Kanoon (30 curated & id-pinned, 270 discovered by topic) | 300 |
| `offence_classification.json` | BNSS First Schedule, Part I | 465 rows (not a vector collection) |
| `repealed_concordance.json` | BPR&D correspondence tables | 1,195 mappings (not a vector collection) |

Two things about `ingest_legal_acts.py` that look odd but are deliberate:
- Text is extracted with `x_tolerance=1.0`; pdfplumber's default glues words together in this font ("isdoubtfulof"), wrecking embeddings and display.
- Section titles are gazette *marginal notes* and extract out of order, so they are bound to sections by **vertical position**, not reading order.

### Offence classification (`ingest_offence_schedule.py`)

The BNSS First Schedule classifies every punishable BNS section as cognizable or not, bailable or not, and names the court that tries it. That is a lookup, not a retrieval problem, so it is parsed into `data/processed/offence_classification.json` and answered without a model. Four things about the parser are load-bearing:

- **Column edges are measured per page, not assumed.** The gazette re-flows the table on every page: column 4 starts at x0 285 on page 158 and 304 on page 163. A single set of edges silently pushed "2 years" into the cognizable column on page 188, which then read "2 Non-cognizable." and resolved to nothing. Edges are recovered from the vocabulary each column opens with (`PUNISHMENT_OPENERS`, `COGNIZABLE_OPENERS`, …).
- **Words are grouped into runs before being placed.** Wrapped text drifts right — a column-4 continuation reaches x0 367, inside column 5's tolerance — so only a run's leading word decides its column.
- **Rows are found by asking whether a line refills a cell**, not by vertical gaps (page 161 sets rows and lines the same 10.2pt apart) and not by the section column (BNS 356(2) is classified twice, once for defamation of the President and once "in any other case", with column 1 blank on the second row).
- **A conditional cell is never resolved to a boolean.** 27 rows leave a classification unresolved (25 of them reading "According as offence abetted is cognizable or non-cognizable"); those keep `cognizable`/`bailable` as `null` with the schedule's own wording in `cognizable_text`/`bailable_text`. A guessed "bailable" is the most dangerous value this system can emit.

`tests/unit/test_offence_schedule.py` pins 21 offences transcribed by eye from the PDF, and asserts invariants over the other 444.

### Repealed-code concordance (`ingest_concordance.py`)

IPC → BNS, CrPC → BNSS, Evidence Act → BSA, built from the correspondence tables published by the **Bureau of Police Research and Development** (an MHA body; `bprd.nic.in/robots.txt` allows everything). This is the one dataset here that is *asserted* by a third party rather than parsed from enacted text, so the script is explicit about what it can and cannot check:

- **Checked**: every target section must exist in our own parse of the gazette; and the whole extraction is cross-checked against a **second, independently typeset table** — the comparative chart in the same publisher's BNS handbook — with the run *failing* if the two disagree beyond 5%. Currently **117/117 agree**. That tests the thing most likely to break, which is not the source but the parser: a 38-page table slips a row and mis-pairs sections silently.
- **Recorded, not gated**: `title_agreement` per row. It was built as a filter and demoted on evidence — all 58 rows scoring below a third were *correct* (IPC 501/502 → BNS 356, titled just "Defamation"; forty definitional rows → BNS 2, "Definitions"), so a title gate would have dropped good mappings and caught nothing.
- **Not checked**: whether the Bureau's view is right. Every row carries its `source` and `source_url`.

Two things to know when working on it: a qualifier ("3, para 1", "23 Clause-2") names *part* of a section, and reading those numbers as sections mapped IPC 1/2/3 onto the BNS definitions clause; and one repealed provision often became several (IPC 498A → BNS 85 **and** 86), so mappings are one-to-many and the filter returns all of them.

### Judgement discovery (`discover_judgments.py`)

Topic-driven expansion of the judgement corpus across 36 topics in bail, arrest, evidence, procedure, sentencing, offences and constitutional criminal law. **Run on 2026-08-27, taking the corpus from 30 to 300.** Its verification model differs from the pinned one by design: rather than "is this the case I expected?", it asks "is this a real judgement, and are its recorded attributes correct?" — title parses into parties and a date, body long enough to be a decision, citations extract.

**What growing the corpus did to retrieval, measured.** The four statute classes moved **+0.000 across the board** — the separation between statute and judgement retrieval holds. The judgement class fell from recall@3 1.000 to 0.833, and reading that as a regression would be wrong: **every expected authority is still retrieved, none below rank 5**, so recall@5 and recall@10 are both 1.000. What changed is the fixture. Each judgement query names one expected case, which at 30 judgements was very nearly the only relevant one in the corpus; at 300 it has to outrank five to ten genuine competitors, and the cases now ranked above it are real authorities on the same question — Shafhi Mohammad above Arjun Panditrao on the section 65B certificate (the case that overruled it), SFIO v. Nittin Johari and Satender Kumar Antil above P. Chidambaram on economic-offence bail. **The expectations were widened instead of the retriever being tuned**, case by case with sign-off, on 2026-08-28 — four policies, recorded in the fixture's `$comment` and in a `note` on each widened query: an overruled authority still counts (it bears on the question, and this corpus records no precedential status); an earlier order in the same litigation counts (the split is an ingestion artefact); a case that *applies* a doctrine counts only where it added something, named individually; and adjacent propositions in the arrest/custody cluster count, because that is how they are litigated. recall@3 returned to **1.000** on every class and judgement recall@1 went 0.500 → 0.667. **That is not retrieval improving** — the same law was being returned the day before. It is the fixture finally expressing what "correct" means for a 300-case corpus. `eval/metrics.json` is the current baseline.

The finding worth keeping is what it *cannot* do. `relevant_sections` means "is an authority on" and becomes a `judgement --interprets--> section` edge, and **that cannot be derived from a judgement's text.** Measured against the 30 curated judgements: reading the act out of each citation recovers 1 of 27, because judgements write a bare "Section 438" and rely on context — Sushila Aggarwal says it 75 times and names the Code beside it only occasionally. Taking each judgement's most-mentioned act was tested and is worse: Nandini Satpathy is an authority on the Evidence Act while mentioning the CrPC 32 times to its 2; Mohd. Arif is curated to BNS 103 while mentioning CrPC 19 to IPC 6. It would produce confident, wrong edges. So derived sections are written to `cited_sections` — a checkable claim about the document — and never to `relevant_sections`.

`ingest_judgments.py` pins each judgement by document id and re-verifies the fetched page against `expect` tokens. Do not switch it to search-by-name: searching "Selvi vs State of Karnataka" returns the unrelated Jayalalitha appeal. It also honours robots.txt and rate limits.

## Live judiciary access

`services/judiciary_service.py` queries authentic public judiciary records (Indian Kanoon: Supreme Court, High Courts, tribunals) at request time. The corpus is a snapshot; this covers judgements handed down after ingestion.

> **Source access has come back, and may go again.** From 2026-08-14 indiankanoon.org sat behind a Cloudflare managed challenge and returned 403 to every path *including `/robots.txt`*; live research errored and `scripts/discover_judgments.py` could not run. As of **2026-08-27** robots.txt, search and document fetches all return 200 and `GET /research/health` reports `reachable: true`. Nothing was changed to achieve that and nothing should be: if the challenge returns, **do not attempt to work around it** — it is an access control the site has deliberately put in place. The fail-soft path is what carried the outage (every endpoint degrades to the local corpus rather than erroring) and `reachable`/`last_error` are what made the state visible instead of showing `enabled: true` while nothing worked. Both stay.

- **Two paths in**: the agent's `live_research` intent (model-driven, via function calling), and the REST endpoints under `/api/v1/research/*` for direct access.
- **It fails soft on purpose.** Errors are returned, never raised, so a slow or unreachable source degrades to the local corpus instead of 500-ing a request. Preserve that.
- **`is_allowed()` fails closed.** If robots.txt cannot be read there is no list to check against, and the disallow list names several thousand documents individually — so not knowing is not permission. It previously logged "proceeding cautiously" and then allowed everything, which is the opposite; found when the whole site went behind a challenge and robots.txt started 403-ing with it. The failure is not cached, since it is usually transient.
- **Live results are retrieved, not curated.** Every hit carries court, date and `source_url`, and both the API and the agent label them as unverified. Do not blend them into corpus output.
- **Requests are rate limited, and the limit adapts upward.** `JUDICIARY_MIN_REQUEST_INTERVAL` is a floor (2.5s); a 429 widens the interval for the rest of the process and is never narrowed again, since the pace the source refused once it will refuse again. `Retry-After` is honoured over our own estimate. **A 429 is an instruction, not a failure** — it used to propagate as an exception, so a discovery run logged a failed search and moved to the next topic at the same pace, losing **21 of 36 topics** with each refusal arriving faster than the request that caused it. With backoff: 0 failed searches and 332 candidates instead of 133. Retries are bounded (`JUDICIARY_MAX_RETRIES`), because a caller that never gets an answer cannot fall back to the local corpus. Responses are TTL-cached and the source's robots.txt disallow list is parsed and honoured — it names several thousand individual documents.
- `ENABLE_LIVE_JUDICIARY=false` turns the whole thing off for offline operation; everything else keeps working.

## MCP server

`backend/mcp_server.py` serves the same services over Model Context Protocol — stdio for
Claude Desktop, `--http` for streamable HTTP. Ten tools, seven of which make no model call at
all. See [`docs/MCP_SERVER.md`](docs/MCP_SERVER.md).

- **Grounding travels with the tools.** `ask` returns typed claims, per-claim verdicts and the
  abstention, never retrieved text — a model on the other end of the protocol will turn a
  paragraph into a confident sentence about someone's liberty, and it would do so *outside* the
  verifier. **There is deliberately no `search_corpus` tool**, and a test asserts its absence,
  because an absence is what gets added back by someone who does not know why it is missing.
- **Logging goes to stderr.** stdio transport speaks JSON-RPC on stdout; a log line written
  there corrupts the stream and the client sees a protocol error rather than a log.
- The tool registry in `tools/registry.py` is **not** MCP and never was, despite saying so in
  its log lines for months. It holds the tools the LangGraph agent dispatches to; the wording
  is now honest.

## API surface (`/api/v1`)

- `agent/query`, `agent/query/stream` — main agent entry points. Optional `workspace` (settles the intent instead of inferring it) and `thread_id` (conversation, when memory is on); both ignored when absent, so every existing caller keeps working. The response carries `agent_trail` when more than one agent was involved.
- `search/rag` — direct RAG search over a chosen collection
- `search/grounded` — typed claims, per-claim verdicts, grounding metrics and a trace; abstains rather than guessing
- `offences/{act}/{section}`, `offences` — classification, connected doctrine and case law, and the custody timeline. No model involved
- `research/case-law`, `research/judgment/{doc_id}`, `research/health` — live judiciary lookups
- `documents/draft`, `documents/analyze`, `documents/export/docx`, `documents/templates`
- `chat/*`, plus `health`/`info` at several levels

Request/response Pydantic models live in `backend/models/` (single source of truth — routers import from there rather than defining their own). Mirrored TypeScript types are in `frontend/lib/api.ts`; keep them in sync when changing a contract.

## Frontend

Next.js **Pages Router** (`frontend/pages/`), not App Router. Two routes: `/` is the landing page and `/app` is the product — one page hosting five workspaces defined in `lib/workspaces.ts` — Ask, Corpus, Live research, Draft, Analyse — inside `components/layout/AppShell.tsx`. Selection is mirrored to the URL hash. Feature UIs in `components/{chat,search,research,documents,shared}/`, data-fetching in `hooks/use*.ts`, all HTTP centralised in `lib/api.ts`.

- **The landing page quotes only measured numbers.** 1,059 sections, 465 offence rows, 1,195 concordance mappings, recall@3 of 0.93 — each cross-checked in `__tests__/landing.test.tsx` against the committed data, so growing the corpus without updating the page fails rather than leaving a stale figure in front of a reader. There is a test asserting the page quotes **no** accuracy percentage: nothing here measures "% accurate", and a landing page is exactly where a system that punishes overclaiming everywhere else would be tempted to start. It is static and data-free so it renders with the backend down.
- **Colour comes only from tokens.** `styles/globals.css` defines CSS custom properties under `:root` and `.dark`; `tailwind.config.js` maps them to semantic names (`canvas`, `surface`, `ink`, `muted`, `line`, `brand`, `brass`, `verified`, `live`). A raw hex or a stock Tailwind grey in a component breaks dark mode. `darkMode: 'class'`, toggled on `<html>` by `hooks/useTheme.ts`; `pages/_document.tsx` exists solely to apply the stored theme before first paint (React cannot hydrate before the browser paints, so without it dark-mode users get a white flash).
- **Provenance is a visual contract.** Verified corpus hits render through `SourceCard` in the `verified` palette; live judiciary hits render through `research/JudgmentCard` in the `live` palette with a source link. Never merge the two lists — the API deliberately returns `sources` and `live_sources` separately for the same reason.
- **`DraftForm` gets its document types from `GET /documents/templates`**, not a local list. It previously carried its own menu, which offered "Affidavit" while the API rejected it. The server owns the structure; the component owns labels and input types.
- **The deterministic layer renders as cards, not sentences.** `components/legal/` — `OffenceCard` (cognizable / bailable / triable-by / punishment), `ProceduralTimeline` (hand-rolled SVG: no network, inherits theme tokens, prints legibly; the step list beside it is the accessible rendering, not a fallback) and `DoctrineTrail` (a lineage chain, not a network diagram). `OffencePanel` picks the section the answer was *about* — a classification claim's section first, then a statute claim's — and fetches `/offences/{act}/{section}` through `useOffence`, which caches per section because the endpoint answers from committed data. Three things they refuse to do: show an unresolved classification as a "no" (27 Schedule rows defer to another offence and render "Not stated" with the Schedule's own wording); show a custody limit that could not be determined; say anything about precedential status.
- **A grounded answer renders as claims, not prose.** `components/legal/ClaimList.tsx` keeps the epistemic classes apart on the page: enacted text set apart and quotable, holdings and interpretations attributed, contested questions as two columns with neither presented as the answer, inference demoted and labelled "Reasoning, not law". Rendering every class identically would throw away the only thing distinguishing them, which is what the whole pipeline exists to establish. Colour reuses the existing provenance tokens — `verified` for what the corpus confirms, `brass`/`live` for what is argued rather than enacted. `ChatInterface` falls back to the markdown path when `verification` is absent (chat, drafting, older responses).
- **Answers are stripped before rendering** (`stripAppendedBlocks` in `lib/api.ts`). The backend appends `**Sources:**` and `**DISCLAIMER**` blocks to `response`/`answer` for plain-text consumers; the UI renders both itself, so leaving them in showed the disclaimer twice and the citations twice.
- **Chat uses the non-streaming agent endpoint.** Agent streaming is faux (see above), so it costs nothing in latency and would discard the structured `sources`. Real streaming primitives remain in `lib/api.ts` (`agent.queryStream`, `readStream`) for `/chat`.

## Conventions

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- Project rules live in `RULES.md` and `AGENTS.md`; both defer to this file where they disagree.
- Docstrings here explain **why** — which measurement forced a design, which bug it prevents. That convention is load-bearing: a contributor who does not know why a line exists will "simplify" it back into a bug. Match it.

## Documentation

`docs/` holds the long-form documentation; [`docs/README.md`](docs/README.md) is the index. This file stays the authoritative *operational* guide — what to know before changing code. The docs carry the reasoning, the measurements and the history.

| Document | Use it for |
|---|---|
| [`docs/ENGINEERING_DEEP_DIVE.md`](docs/ENGINEERING_DEEP_DIVE.md) | End-to-end working, every layer, every challenge and fix, honest limitations |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Diagrams, request flows, data model, module map, cross-cutting invariants |
| [`docs/RAG_PIPELINE.md`](docs/RAG_PIPELINE.md) | Chunking, batching, embedding, the four retrieval layers and the ablation |
| [`docs/EVALUATION_AND_TESTING.md`](docs/EVALUATION_AND_TESTING.md) | Golden set, grounding metrics, the abstention measurement, adversarial suite |
| [`docs/CHALLENGES_AND_SOLUTIONS.md`](docs/CHALLENGES_AND_SOLUTIONS.md) | 60+ fixed bugs as Symptom → Cause → Fix → Guard |
| [`docs/ATTRIBUTION_GAP.md`](docs/ATTRIBUTION_GAP.md) | Why case-to-section attribution cannot be verified automatically; the checks measured and rejected. **Read before attempting one.** |
| [`docs/MCP_SERVER.md`](docs/MCP_SERVER.md) | Running LawAI over MCP, the tool surface, the Claude Desktop config |

**Check `CHALLENGES_AND_SOLUTIONS.md` before removing anything that looks redundant.** Most of the odd-looking code in this repository is load-bearing and the entry says which failure it prevents.

When a non-obvious fix lands, add its entry there and update the affected doc — otherwise the reasoning is lost and the bug returns.
