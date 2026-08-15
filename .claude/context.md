# LawAI — crucial details and decisions

Durable facts a future session would otherwise have to rediscover.
See also: [plan.md](plan.md) (the rebuild plan) and [PROGRESS.md](PROGRESS.md) (what shipped).
`../CLAUDE.md` is the authoritative architecture guide.

**Full documentation** is now in [`../docs/`](../docs/README.md) — engineering deep dive,
architecture, RAG pipeline, evaluation and testing, and a catalogue of every fixed bug
([`CHALLENGES_AND_SOLUTIONS.md`](../docs/CHALLENGES_AND_SOLUTIONS.md)). Check that catalogue
before "simplifying" anything that looks odd; most of it is load-bearing.

## Environment

- **Python is Anaconda 3.13.5.** The original `requirements.txt` pins (`numpy==1.24.3`,
  `chromadb==0.4.22`, `pydantic==2.5.3`) cannot install on it. Requirements were modernised
  to floors (`>=`) rather than exact pins.
- **A virtualenv lives at `backend/venv`** (gitignored). Use `./venv/bin/python`, not the
  anaconda `python3` — the base env does not have chromadb, openai or sentence-transformers.
- Installing pulls CPU torch (~1.4 GB) via sentence-transformers. Expect a slow first install.
- The sandbox **has real outbound internet** through `curl`/`requests`, which is what makes
  the ingestion pipeline possible.

## LLM provider

- **AIML API** (`https://api.aimlapi.com/v1`), OpenAI-compatible, accessed with the `openai`
  SDK. Default model `gpt-4o-mini`. Env vars: `AIML_API_KEY`, `AIML_BASE_URL`, `AIML_MODEL`,
  `AIML_MAX_TOKENS`, `AIML_TEMPERATURE`.
- **`backend/.env` holds a working `AIML_API_KEY`** (gitignored). Live generation, real token
  streaming and the full e2e suite have all been verified against it.
- The previous `backend/.env` contained a live IBM watsonx key and project id. Those were
  removed when the file was rewritten. `.env` is gitignored and was never committed, so no
  history scrub is needed.

## Data sources (verified reachable and parseable)

| Act | Official MHA gazette PDF |
|---|---|
| BNS | `https://www.mha.gov.in/sites/default/files/250883_english_01042024.pdf` |
| BNSS | `https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf` |
| BSA | `https://www.mha.gov.in/sites/default/files/250882_english_01042024.pdf` |

Judgements come from `indiankanoon.org/doc/<id>/`, parsed with the `.doc_title`,
`.doc_citations`, `.doc_bench` and `.judgments` selectors.

### Gazette PDF quirks that drove the parser design

1. **`x_tolerance=1.0` is required.** pdfplumber's default (3) glues words together
   ("isdoubtfulof"). pypdf spaces correctly but gives no coordinates, and coordinates are
   needed for titles — hence pdfplumber with a tuned tolerance for both.
2. **Section titles are marginal notes**, in a narrow column: left on even pages, right on
   odd. Linear extraction emits them **out of order** (on one page section 11's note came
   after section 14's), so they are bound to sections by vertical position. A note sits
   roughly 1.5pt below its section's first line, but can sit a few points *above* — the
   tolerance is 6pt, found because section 78 ("Stalking") sat 3.3pt above.
3. **Do not cluster notes by vertical gaps.** Intra-note line spacing is ~9.6pt and the gap
   between two notes can be as little as 14.9pt; a 16pt threshold merged "Punishment for
   murder" into the previous note and left BNS 103 untitled. Segment by section position.
4. **Chapter headings lose their space**: `CHAPTERV`, `CHAPTERXX`. The regex must treat it as
   optional or Chapter V (offences against woman and child) vanishes entirely.
5. **The margin column also carries act citations** ("45 of 1860.") on the same typeset line
   as title words, and the **last page carries the PDF's digital-signature blob**. Both are
   filtered (citation substring removal; line length + digit-ratio caps).

### Judgement sourcing

- **Never resolve cases by search alone.** Searching "Selvi vs State of Karnataka" returns the
  unrelated Jayalalitha appeal; several landmark searches return a later order in the same
  matter instead of the judgement. Every id in the manifest was resolved and eyeballed, and
  ingestion re-verifies each page against `expect` tokens.
- Plain search returns *citing* cases, not the judgement. Indian Kanoon's `title:(...)` plus
  `fromdate:`/`todate:` operators resolve landmarks exactly; that is how the last four were
  found.
- **Title tokens alone are not enough.** The first Bhajan Lal id matched "bhajanlal" and
  "haryana" but was a 1992 *contempt petition* between the same parties. `expect_text` now
  asserts a phrase from the actual holding appears in the body.
- Some Indian Kanoon pages are **abridged**: Bhajan Lal returns ~27k chars ending near
  paragraph 12, so its seven-category list (paragraph 102) is not in the corpus.
- `robots.txt` lists ~3,900 disallowed document ids for generic agents; the script parses and
  honours that list, rate limits to one request per 2s, and caches HTML in `data/raw/`.

## Retrieval

- Embeddings: `all-MiniLM-L6-v2`, 384-dim, **~256-token window**. This is why documents are
  chunked (~1200 chars, 150 overlap, batch 256) before embedding — otherwise a 60k-char
  judgement is represented by its first paragraph and can never match a query about its
  holding.
- 1,089 source documents → 3,184 chunks. Chunks keep `parent_id`, `chunk_index`,
  `chunk_count` so a hit is citable back to its section or case — and so the verifier can
  check a quotation against the **whole** section rather than the retrieved piece.
- Verified working: "punishment for murder" → BNS 103; "how long can an undertrial be
  detained" → BNSS 479; "admissibility of electronic records" → BSA 63; "can anticipatory
  bail be limited to a fixed period" → Sushila Aggarwal; "is registration of an FIR
  mandatory" → Lalita Kumari.
- ~~Known soft spot: "anticipatory bail" does not appear in BNSS 482's text~~ **fixed** by
  `services/query_expansion.py`. Correction to the original note: a hybrid BM25 retriever
  would **not** have closed this gap — the word "anticipatory" appears nowhere in BNSS 482's
  1,948 characters, so there is nothing to match lexically either. It is a vocabulary
  problem, and the fix is a curated alias layer applied before embedding.

### Four retrieval layers, and what each moved (recall@3, 69-query golden set)

| Layer | Class it targeted | Before | After |
|---|---|---|---|
| Dense vector only | — | overall 0.652 | — |
| Query expansion | `term_of_art` | 0.500 | **0.875** |
| Structured citation lookup | `citation` | 0.250 | **1.000** |
| Concordance translation | `repealed_code` | 0.375 | **1.000** |

Overall **0.652 → 0.928**. `plain` stays at 0.960 throughout — every layer is additive, so a
working query cannot be made worse. Reports committed in `backend/eval/`
(`baseline_no_expand` → `baseline` → `structured` → `concordance`).

A section number carries almost no semantic signal ("482" and "483" embed to nearly the same
point), so reranking could not have fixed the citation class — a reranker works from the same
signal. A citation names one document; it is fetched by exact metadata key at distance 0.0.

## Grounding (the numbers behind the design)

- **The relevance-threshold abstention design was measured and rejected.** Over the 69
  answerable golden queries the worst best-distance is **0.577**; over the 6 adversarial ones
  distances go as low as **0.423**. The distributions **overlap**, so no cutoff separates
  them. Abstention is therefore whether one claim survives verification — the threshold is
  one, and it cannot be mis-tuned because there is no parameter.
- **Never let a model verify a model.** The prior that invented BNS 999 will confirm BNS 999.
  Every check in `claim_verifier.py` is a lookup against committed data.
- **Metrics are computed over what synthesis *emitted*,** before failures are rewritten to
  `unsupported`. Scoring the survivors would delete every failure from the record and report
  1.0 for having caught them. `verbatim_fidelity` covers **all** statute claims, not just
  quoted ones, so a model that stops quoting to avoid being checked shows a drop.
- **Corpus/graph counts:** 1,059 sections · 931 cross-references · 34 interprets edges · 16
  doctrines · 288 classified sections · 465 offence rows · 1,195 concordance mappings.
- The concordance is cross-checked against a second, independently typeset table:
  **117/117 agree**. `title_agreement` was built as a filter and **demoted to a recorded
  signal on evidence** — all 58 rows scoring below a third were correct.

## Repository hygiene

- `backend/chroma_db/` **was tracked in git** and had grown to 51 MB of binaries. Now
  untracked and ignored; regenerate with `scripts/init_vector_db.py`.
- `data/raw/` is ignored (re-downloadable). `data/processed/*.json` **is committed** so the
  project runs without re-fetching from mha.gov.in and indiankanoon.org.
- The old `.gitignore` rule `data/raw/*.pdf` did not match subdirectories; it is now
  `data/raw/`.
- `ruff check .` is clean. Rules are pinned in `backend/pyproject.toml` because ruff's
  defaults widen every release — 0.1.14 flagged a handful, 0.16 flagged ~1,300 on identical
  code. Do not rely on ruff defaults here.

## Testing

- `backend/pytest.ini` sets `pythonpath = .`. Before it existed, tests imported `backend.*`
  while the app imported `services.*` — the same module under two names, which would have
  duplicated every singleton. Keep both on the `services.*` convention.
- Live tests are marked `live` and skip without `AIML_API_KEY`. Plain `pytest` must stay green
  with no credentials. Current: **763 collected, 755 passed, 8 skipped** (the 8 are e2e and
  need a running server). Frontend: 106 passed.
- The 8 e2e tests need a server: `./venv/bin/python -m uvicorn main:app --port 8000`.
- **Test the relationship between surfaces, not just each one.** The agent and
  `/search/grounded` both had passing tests while emitting incompatible claim-source shapes,
  which crashed every answer in the UI. `TestPayloadShapesAgree` now compares them directly.


## Contract pitfalls found by live testing (do not regress these)

- `frontend/lib/api.ts` is only tracked because the Python `lib/` ignore was anchored to
  `/lib/`. Re-broadening it would silently drop the API client from the repo again.
- The RAG endpoint is `POST /api/v1/search/rag` (`/search` kept as an alias). It accepts both
  `bns` and `bns_sections` forms, and returns `{answer, sources[], query, num_sources}` —
  **not** `results[]`.
- Both streaming endpoints emit one SSE dialect: `data: {"token": ...}` lines terminated by
  `data: [DONE]`. `frontend/lib/api.ts::readStream` only understands that shape.
- `_format_analyze_response` and friends detect a tool payload via
  `hasattr(result, "success")`, so agent nodes must return a `ToolResult`, never a bare dict.
- Draft and analyse intents require an action verb. Without that guard, "Tell me about bail"
  is answered by drafting a bail application.


## Live judiciary access (added after the corpus work)

- `services/judiciary_service.py` queries Indian Kanoon at request time. Verified returning
  **2026** judgements, which the corpus snapshot can never contain — that is the whole point
  of the feature.
- **AIML API supports OpenAI-style function calling** on `gpt-4o-mini`; confirmed with a real
  `tool_calls` response. `LLMService.generate_with_tools` implements the loop (capped at
  `MAX_TOOL_ROUNDS`, with a final toolless call so the model must answer).
- The model is given three tools — `search_local_corpus`, `live_case_law_search`,
  `fetch_judgment` — and picks. Observed calling **both** corpus and live search for
  "what does BNS say about organised crime, and any recent rulings?".
- Source policy checked: `indiankanoon.org` allows `/search/` and `/doc/` for generic agents
  (only Baiduspider is barred from search) and lists ~3,900 individual documents as
  disallowed — parsed and honoured. `sci.gov.in` allows everything but `/wp-admin`.
  `indiacode.nic.in` **disallows `/discover` and `/simple-search`**, so never use its search;
  direct document URLs are fine.
- Search syntax that matters: plain queries return *citing* cases. Use
  `title:(...)`, `doctypes:supremecourt`, `fromdate:D-M-YYYY`, `todate:D-M-YYYY`.
- The service **fails soft by contract** — errors are returned, never raised — so the agent
  falls back to the corpus rather than erroring. Keep it that way.
- `ENABLE_LIVE_JUDICIARY=false` disables the whole path for offline work.
