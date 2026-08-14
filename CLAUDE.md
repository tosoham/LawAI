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
- **The vector store is seeded by `docker-entrypoint.sh` into a volume**, not baked into the image (it is derived data, and baking it would re-run the whole embedding pass on any layer change). The script gates on a `.lawai-seeded` marker rather than on `chroma.sqlite3`, which chromadb creates on first connect — testing for the sqlite file made a half-finished seed look complete on restart and served an empty corpus. `SKIP_DB_INIT=true` bypasses seeding.

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
- **Documents are chunked before embedding.** `all-MiniLM-L6-v2` truncates at ~256 tokens, so a 60k-character judgement would otherwise be indexed by its first paragraph alone. `init_vector_db.py` splits into ~1200-char overlapping chunks carrying `parent_id` so a hit is still citable to its source. 1,089 documents → 3,184 chunks.
- **A cited section is looked up, not searched for** (`services/retrieval/structured_filter.py`, applied inside `VectorService.search`). A section number is nearly invisible to a dense embedder — "482" and "483" embed to almost the same point and a section's text rarely repeats its own number, so `"section 482 BNSS"` did not surface BNSS 482 anywhere in the top 20. `parse_citation` recognises the citation and the section is fetched by metadata and ranked first, with the vector hits kept behind it (a citation is usually only part of what was asked). This took the citation class from recall@3 0.250 to 1.000 with no other class moving. Pass `structured=False` to measure without it. **A repealed code's number is deliberately refused**: "CrPC 438" means BNSS 482, but BNSS 438 exists and is about something else, so resolving it would turn a miss into a confident wrong answer. Repealed citations resolve their *act* and fall through to vector search. A lettered section ("41A", "65B") is refused for the same reason — no section of the 2023 codes carries one.
- **Corpus queries are expanded before embedding** (`services/query_expansion.py`, applied inside `VectorService.search`). Terms of art often do not appear in the statute they govern — "anticipatory" occurs nowhere in BNSS 482 — and repealed code names ("IPC", "CrPC") appear nowhere in the corpus at all. The curated alias table appends the statutory phrasing; expansion is **additive**, so a working query cannot be made worse, and only the embedded text changes (the generation prompt still carries the user's own wording). Pass `expand=False` to measure unexpanded behaviour. Note a hybrid BM25 retriever would *not* fix this class of miss: the term is absent from the text, so there is nothing to match lexically.
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
| `holding` / `interpretation` | the case exists **and** the graph records it as bearing on the cited section |
| `contested` | rejected below two positions, each with authority |
| `inference` | may rest on nothing, but must not carry a citation formatted as law |

Four findings from running it that are easy to reintroduce:

- **A classification claim must be cited to its own offence's section.** A live answer said correctly that theft is non-bailable and cited BNS 304 — snatching, whose text opens "Theft is snatching if…" — and it passed, because snatching carries the same attributes. Right facts, wrong provision, and the citation is what the reader follows. `match_offences` now binds the claim to the section the First Schedule keys that offence to.
- **A section's Schedule rows can disagree.** BNS 303: "Theft" is non-bailable, "Where value of property is less than 5,000 rupees" is bailable. Checking against the *union* let "theft is bailable" pass. `_rows_the_claim_is_about` picks the row by its own offence wording appearing in the claim, and rejects when the candidates disagree.
- **A quotation is checked against the whole section, not the retrieved chunk.** A section is indexed in pieces; a true quotation from a piece that did not rank is still true. `SectionNode.text` carries the full text for this.
- **Trailing punctuation is stripped from the span only.** BNS 303 reads "or with both and in case of second conviction…"; quoting "or with both." is the same words. Interior punctuation is not touched.
- **Classification attaches to the section that punishes, not the one that defines.** The model reliably cited BNS 101 (defines murder) instead of BNS 103 (punishes it). The prompt, the graph block and the verifier's failure message all now say so; without the last one the model returned `{"claims": []}` on regeneration instead of re-citing.

**Abstention falls out of verification; it is not a relevance threshold.** That was measured and rejected: the 69 answerable golden queries reach a worst best-distance of 0.577, the 6 adversarial ones go as low as 0.423. The distributions overlap, so any cutoff either refuses real questions or admits invented answers. The gate is whether one claim survives checking. One pre-check runs before generation — a cited section that does not exist ("section 999 of the BNS") is refused without a model call.

**Failures are removed, not hedged**, and the removal is reported to the reader. One regeneration attempt naming the offending claims comes first; a second failure means the model cannot ground the claim and a third would only produce a more confident version of it.

**Metrics** (`services/answer_metrics.py`) replace a confidence score. `verbatim_fidelity` is measured over *every* statute claim rather than the quoted ones, so a model that stops quoting to avoid being checked shows up as a drop. `unsupported` is totalled across the golden set, never averaged. `metrics.clean` is a per-answer signal, not a shipping gate — the delivered answer never contains an unsupported claim by construction.

`tests/integration/test_grounded_answer_live.py` is the Phase 2 gate: all six adversarial queries must abstain, four answerable ones must not, and murder must never come back bailable. Marked `live`, so it needs `AIML_API_KEY`.

**Audience register** (`services/audience.py`) — `citizen` (default) | `lawyer` | `judge`, on the request. It is a layer on the *synthesis system prompt and nothing else*, and that separation is structural rather than a rule to remember: neither `VectorService.search` nor `claim_verifier.verify` takes an audience argument, so there is no path by which "written for a citizen" could become "checked less carefully for a citizen". Same law retrieved, same claims checked the same way, epistemic classes present in the data whatever the register — a citizen's answer is shorter, not vaguer, and keeps every citation. **Judge mode carries a prohibition the others do not**: set out the provisions, the competing arguments, the authority on each side and the statutory range, and never suggest an outcome — not by implication, ordering or emphasis either. Tested against the real model with prompts that invite one directly.

**The trace panel** (`components/legal/TracePanel.tsx`) is collapsed by default and always one click away: metrics, and every claim the verifier rejected with its reason. "Nothing was removed" is stated rather than left as an absence — otherwise the section's presence reads as a bad sign and its absence as a clean bill of health.

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
| `sc_judgements` | Indian Kanoon (curated, id-pinned) | 30 |
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
- **A conditional cell is never resolved to a boolean.** ~40 rows read "According as offence abetted is cognizable or non-cognizable"; those keep `cognizable`/`bailable` as `null` with the schedule's own wording in `cognizable_text`/`bailable_text`. A guessed "bailable" is the most dangerous value this system can emit.

`tests/unit/test_offence_schedule.py` pins 21 offences transcribed by eye from the PDF, and asserts invariants over the other 444.

### Repealed-code concordance (`ingest_concordance.py`)

IPC → BNS, CrPC → BNSS, Evidence Act → BSA, built from the correspondence tables published by the **Bureau of Police Research and Development** (an MHA body; `bprd.nic.in/robots.txt` allows everything). This is the one dataset here that is *asserted* by a third party rather than parsed from enacted text, so the script is explicit about what it can and cannot check:

- **Checked**: every target section must exist in our own parse of the gazette; and the whole extraction is cross-checked against a **second, independently typeset table** — the comparative chart in the same publisher's BNS handbook — with the run *failing* if the two disagree beyond 5%. Currently **117/117 agree**. That tests the thing most likely to break, which is not the source but the parser: a 38-page table slips a row and mis-pairs sections silently.
- **Recorded, not gated**: `title_agreement` per row. It was built as a filter and demoted on evidence — all 58 rows scoring below a third were *correct* (IPC 501/502 → BNS 356, titled just "Defamation"; forty definitional rows → BNS 2, "Definitions"), so a title gate would have dropped good mappings and caught nothing.
- **Not checked**: whether the Bureau's view is right. Every row carries its `source` and `source_url`.

Two things to know when working on it: a qualifier ("3, para 1", "23 Clause-2") names *part* of a section, and reading those numbers as sections mapped IPC 1/2/3 onto the BNS definitions clause; and one repealed provision often became several (IPC 498A → BNS 85 **and** 86), so mappings are one-to-many and the filter returns all of them.

### Judgement discovery (`discover_judgments.py`) — blocked on source access

Topic-driven expansion of the judgement corpus, written and tested but **unrunnable** while the source is challenged (see below). Its verification model differs from the pinned one by design: rather than "is this the case I expected?", it asks "is this a real judgement, and are its recorded attributes correct?" — title parses into parties and a date, body long enough to be a decision, citations extract.

The finding worth keeping is what it *cannot* do. `relevant_sections` means "is an authority on" and becomes a `judgement --interprets--> section` edge, and **that cannot be derived from a judgement's text.** Measured against the 30 curated judgements: reading the act out of each citation recovers 1 of 27, because judgements write a bare "Section 438" and rely on context — Sushila Aggarwal says it 75 times and names the Code beside it only occasionally. Taking each judgement's most-mentioned act was tested and is worse: Nandini Satpathy is an authority on the Evidence Act while mentioning the CrPC 32 times to its 2; Mohd. Arif is curated to BNS 103 while mentioning CrPC 19 to IPC 6. It would produce confident, wrong edges. So derived sections are written to `cited_sections` — a checkable claim about the document — and never to `relevant_sections`.

`ingest_judgments.py` pins each judgement by document id and re-verifies the fetched page against `expect` tokens. Do not switch it to search-by-name: searching "Selvi vs State of Karnataka" returns the unrelated Jayalalitha appeal. It also honours robots.txt and rate limits.

## Live judiciary access

`services/judiciary_service.py` queries authentic public judiciary records (Indian Kanoon: Supreme Court, High Courts, tribunals) at request time. The corpus is a snapshot; this covers judgements handed down after ingestion.

> **The source is currently unreachable.** As of 2026-08-14 indiankanoon.org sits behind a Cloudflare managed challenge and returns 403 to every path *including `/robots.txt`*. Live research therefore returns errors, and `scripts/discover_judgments.py` cannot run. This is an access control the site has deliberately put in place: **do not attempt to work around it.** The fail-soft path is doing its job — every endpoint degrades to the local corpus rather than erroring — and `GET /research/health` now reports `reachable` and `last_error` so the state is visible instead of showing `enabled: true` while nothing works.

- **Two paths in**: the agent's `live_research` intent (model-driven, via function calling), and the REST endpoints under `/api/v1/research/*` for direct access.
- **It fails soft on purpose.** Errors are returned, never raised, so a slow or unreachable source degrades to the local corpus instead of 500-ing a request. Preserve that.
- **`is_allowed()` fails closed.** If robots.txt cannot be read there is no list to check against, and the disallow list names several thousand documents individually — so not knowing is not permission. It previously logged "proceeding cautiously" and then allowed everything, which is the opposite; found when the whole site went behind a challenge and robots.txt started 403-ing with it. The failure is not cached, since it is usually transient.
- **Live results are retrieved, not curated.** Every hit carries court, date and `source_url`, and both the API and the agent label them as unverified. Do not blend them into corpus output.
- Requests are rate limited (`JUDICIARY_MIN_REQUEST_INTERVAL`), TTL-cached, and the source's robots.txt disallow list is parsed and honoured — it names several thousand individual documents.
- `ENABLE_LIVE_JUDICIARY=false` turns the whole thing off for offline operation; everything else keeps working.

## API surface (`/api/v1`)

- `agent/query`, `agent/query/stream` — main agent entry points
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
- **The deterministic layer renders as cards, not sentences.** `components/legal/` — `OffenceCard` (cognizable / bailable / triable-by / punishment), `ProceduralTimeline` (hand-rolled SVG: no network, inherits theme tokens, prints legibly; the step list beside it is the accessible rendering, not a fallback) and `DoctrineTrail` (a lineage chain, not a network diagram). `OffencePanel` picks the section the answer was *about* — a classification claim's section first, then a statute claim's — and fetches `/offences/{act}/{section}` through `useOffence`, which caches per section because the endpoint answers from committed data. Three things they refuse to do: show an unresolved classification as a "no" (~40 Schedule rows defer to another offence and render "Not stated" with the Schedule's own wording); show a custody limit that could not be determined; say anything about precedential status.
- **A grounded answer renders as claims, not prose.** `components/legal/ClaimList.tsx` keeps the epistemic classes apart on the page: enacted text set apart and quotable, holdings and interpretations attributed, contested questions as two columns with neither presented as the answer, inference demoted and labelled "Reasoning, not law". Rendering every class identically would throw away the only thing distinguishing them, which is what the whole pipeline exists to establish. Colour reuses the existing provenance tokens — `verified` for what the corpus confirms, `brass`/`live` for what is argued rather than enacted. `ChatInterface` falls back to the markdown path when `verification` is absent (chat, drafting, older responses).
- **Answers are stripped before rendering** (`stripAppendedBlocks` in `lib/api.ts`). The backend appends `**Sources:**` and `**DISCLAIMER**` blocks to `response`/`answer` for plain-text consumers; the UI renders both itself, so leaving them in showed the disclaimer twice and the citations twice.
- **Chat uses the non-streaming agent endpoint.** Agent streaming is faux (see above), so it costs nothing in latency and would discard the structured `sources`. Real streaming primitives remain in `lib/api.ts` (`agent.queryStream`, `readStream`) for `/chat`.

## Conventions

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- Project rules live in `RULES.md` and `AGENTS.md`; both defer to this file where they disagree.
