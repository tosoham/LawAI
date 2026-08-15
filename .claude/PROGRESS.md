# LawAI — progress log

What shipped, in order. Plan: [plan.md](plan.md) · Key facts: [context.md](context.md) ·
`../CLAUDE.md` is the authoritative architecture guide.

**Current state: 755 backend tests passing (8 skipped, needing a server), 106 frontend.**
`ruff check .` clean; frontend lint, `tsc --noEmit` and `next build` all clean.

Full engineering narrative: [`../docs/ENGINEERING_DEEP_DIVE.md`](../docs/ENGINEERING_DEEP_DIVE.md).
Every bug and fix: [`../docs/CHALLENGES_AND_SOLUTIONS.md`](../docs/CHALLENGES_AND_SOLUTIONS.md).

---

## Part I — Rebuild (dropping the watsonx requirement)

### Phase 1 — LLM provider swap ✅ `fbcab87`

IBM watsonx.ai → AIML API (OpenAI-compatible, `gpt-4o-mini`). Rewrote `LLMService` on the
`openai` SDK keeping the same public interface, so no call site changed. Clients now build
**lazily** — a missing key previously crashed the app at import. `generate_stream` streams for
real. Modernised `requirements.txt` (old pins could not install on Python 3.13).

### Phase 2 — Bugs found by tracing call sites ✅ `fbcab87`

The suite could not even *collect* before this, which is why these had gone unnoticed:

| Bug | Impact |
|---|---|
| `rag_service` scored distance `0.0` as relevance `0.0` (falsy check) | Perfect matches ranked **worst** |
| `legal_agent` read draft text from `content`, tool returns `document` | Agent drafts rendered **empty** |
| Looked up `analyze_doc`, tool registers as `analyze_document` | Lookup always `None` |
| Hardcoded `document_type="bail_application"` | Every draft was a bail application |
| Classifier broke ties in enum order | "what can you help me with?" → vector search |
| `/documents/templates` declared `Dict[str,str]`, sends a list | Endpoint always **500**'d |
| Draft/analyze called the LLM synchronously | Blocked the event loop |

### Phase 3 — Real legal corpus ✅ `cbd7433`

27 hand-written demo records → the actual law. **358 BNS, 531 BNSS, 170 BSA** from MHA gazette
PDFs; 27 landmark judgements id-pinned. `init_vector_db.py` now **chunks before embedding**.
Stopped tracking 51 MB of ChromaDB binaries.

### Phase 4 — Cleanup ✅

Removed IBM/Bob branding from 54 files. Rewrote `CLAUDE.md`/`AGENTS.md`.

### Phase 5 — Live end-to-end verification ✅ `a2ef483` `e5fa4b4` `051d5a1`

With a real key, 28 previously-skipped tests ran and exposed defects mocking could never
catch:

- **`frontend/lib/api.ts` had never been committed** — an unanchored `lib/` rule in
  `.gitignore` excluded it. A fresh clone could not build.
- **Search was broken end to end in three independent ways** — wrong path (404), wrong
  collection alias (422), wrong response shape.
- **`POST /documents/export/docx` did not exist** despite the frontend calling it.
- **The two streaming endpoints spoke different SSE dialects.**
- **"Tell me about bail" was answered by drafting a bail application.**
- The first Bhajan Lal id was a **1992 contempt petition between the same parties** — caught
  only by checking body text. `expect_text` added.
- Lint was version-dependent (ruff 0.1.14 → a handful; 0.16 → ~1,300 on identical code). Rule
  set pinned.

### Phase 6 — Live judiciary integration ✅ `8cd76c3`

`judiciary_service.py` — robots-aware, rate-limited, TTL-cached, **fails soft**.
`generate_with_tools` implements real OpenAI function calling. New `live_research` intent.
Verified returning 2026 judgements the corpus snapshot can never contain.

### Containerisation ✅ `de417df` · UI rebuild ✅ `9d9dca1` `7c0fb54`

Token-based design system, dark mode, frontend test suite.

---

## Part II — Grounding architecture

### Retrieval foundations ✅ `e5327cf` `41d1dc2` `fd40ef5`

- **Query expansion** — terms of art absent from the statute they govern. `term_of_art`
  recall@3 **0.500 → 0.875**.
- **BNSS 531 swallowed the First Schedule** — 129,022 chars → 1,873. Chunks 3,320 → 3,184.
  Invisible in aggregate counts; only the length *distribution* showed it.
- **Eval harness + baseline committed.** 69 golden queries in five failure classes.

### Structured lookups ✅ `9e190d6` `786ff6f` `5888953`

- **First Schedule parsed** into 465 offence rows — per-page column edges, runs not words,
  rows by cell-refill, conditional cells kept `null`.
- **Citations looked up, not searched for** — `citation` recall@3 **0.250 → 1.000**.
- **Concordance** — 1,195 BPR&D mappings, cross-checked against a second table, 117/117 agree.
  `repealed_code` **0.375 → 1.000**.

### The graph ✅ `35a4406` `7fc2469`

1,059 sections · 931 cross-references · 34 interprets edges · 16 doctrines · 288 classified.
No LLM-inferred edges. Expansion into generation, with the four kinds rendered separately.

### Typed claims and verification ✅ `c93f675` `257b21f` `d1a4685`

Claims **emitted, not annotated**. Deterministic per-class verification. **Abstention falls
out of verification** — the relevance-threshold design was measured (answerable worst 0.577,
adversarial best 0.423, overlapping) and rejected. Agent's main path routed through it.

### Deterministic layer and UI ✅ `3140112` `cac2c60` `5da9669` `24f86ca`

Procedural timeline (no model). Claims rendered by class. Offence cards, doctrine trail, trace
panel, audience register.

### Landing page ✅ `a278658`

Leads with the refusal. Every figure cross-checked against committed data in tests; a test
asserts it quotes **no** accuracy percentage.

### Adversarial and container testing ✅ `79339d9` `7d18c89`

- **6/6 prompt injections held**; drift 100% consistent.
- **Two question-substitution bugs found** — BNSS 103 answered from BNS 103; IPC 302 answered
  without noting repeal. `citation_note()` added.
- **A retrieval bug the verifier exposed** — "punishment for theft" abstained 1-in-3 because
  BNS 305/304 outranked BNS 303.
- **A container that passed its health check and 500-ed on every question** — missing
  `data/curated`.
- **A payload-shape mismatch that crashed every answer in the UI** — agent emitted bare-string
  sources, endpoint emitted typed objects. Every test passed because nothing compared the two.
- **SVG labels clipped outside the viewBox.**

### Documentation ✅

`docs/` rewritten: engineering deep dive, architecture, RAG pipeline, evaluation and testing,
challenge catalogue, interview brief. README, RULES, AGENTS and CONTRIBUTING brought current —
RULES previously listed JWT auth and rate limiting as implemented; neither exists.

---

## Not built

- **Phase 3 corpus depth (~300 judgements)** — `discover_judgments.py` is written and tested
  but **unrunnable**: indiankanoon.org is behind a Cloudflare challenge returning 403 to every
  path including `/robots.txt`. Deliberately not worked around; surfaced via
  `/research/health`. Unblock is the official API (~₹78).
- **Phase 5 retrieval quality** — cross-encoder reranking, small-to-big, hybrid BM25,
  embedding upgrade, **reindex-safety manifest**. All designed, none built. The manifest is
  the highest-risk gap: swapping the embedder against an existing volume silently serves an
  index built by a different model.
- **Phase 6 multi-agent orchestration** — planner, parallel specialists, and the dialectical
  contested path. **This is why the project should not be described as multi-agent
  collaboration.** What exists is a verification architecture with intent routing.
- **Phase 7 MCP server.**
- Auth, inbound rate limiting, CI, load testing.

---

## Known limitations

- **Bhajan Lal is stored abridged** (~27k chars); its seven-category list at paragraph 102 is
  not in the corpus. The entry's `subject` describes what is actually stored.
- Judgements truncated at 60,000 characters before embedding.
- **`judgement`-class recall@3 has never moved** (0.833) — no layer targeted it, and 12 queries
  over 30 judgements is thin.
- BNS 104 ("murder by life-convict") outranks BNS 103 for "punishment for murder" — near
  identical titles. The generated answer still cites 103 correctly, and offence lookup now
  fetches 103 exactly.
- **Agent streaming is faux-streaming** — deliberate, since real streaming would discard the
  structured `sources`.
- **The golden set was written by the same person who wrote the system.**
