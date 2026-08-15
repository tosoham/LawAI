# Architecture

**System design, request flows, data model, and module map.**

Narrative explanation of *why* each piece exists is in
[`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md). This document is the reference.

---

## 1. System overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Frontend — Next.js 14, Pages Router, TypeScript, Tailwind                 │
│                                                                            │
│   /          landing page (static, data-free, renders with backend down)   │
│   /app       AppShell hosting 5 workspaces, selection mirrored to URL hash  │
│              Ask · Corpus · Live research · Draft · Analyse                │
│                                                                            │
│   components/legal/   ClaimList · OffenceCard · ProceduralTimeline         │
│                       DoctrineTrail · OffencePanel · TracePanel            │
│   lib/api.ts          ALL HTTP; TypeScript mirror of backend/models/       │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │  HTTP / SSE
┌────────────────────────────────▼──────────────────────────────────────────┐
│  Backend — FastAPI                                                         │
│                                                                            │
│  api/v1/  agent · search · offences · research · documents · chat          │
│                     │                                                      │
│  ┌──────────────────▼───────────────────────────────────────────────┐     │
│  │  AgentService → LegalAgent  (LangGraph StateGraph)                │     │
│  │                                                                    │     │
│  │   classify_intent ─┬─ rag_search ──────► GroundedAnswerService     │     │
│  │                    ├─ chat                                          │     │
│  │                    ├─ draft_document ──► ToolRegistry               │     │
│  │                    ├─ analyze_document ─►                           │     │
│  │                    └─ live_research ───► LLM function calling       │     │
│  │                              ▼                                      │     │
│  │                      format_response → END                          │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                            │
│  services/                                                                 │
│    grounded_answer   retrieve → graph → synthesise → verify → metrics      │
│    claim_verifier    deterministic checks, no LLM                          │
│    answer_metrics    grounding rate, verbatim fidelity, unsupported        │
│    legal_graph       1,059 sections · 931 xrefs · 34 interprets · 16 doct. │
│    procedural_timeline   BNSS custody timeline — no model                  │
│    retrieval/        structured_filter (citations) · offence_lookup        │
│    query_expansion   term-of-art alias table                               │
│    rag_service · vector_service · embedding_service · llm_service          │
│    judiciary_service  live case law, robots-aware, fails soft              │
│    audience          citizen | lawyer | judge — synthesis prompt only      │
└──────────┬──────────────────────────────────┬─────────────────────────────┘
           │                                  │
┌──────────▼─────────────┐      ┌─────────────▼──────────────────────────┐
│  ChromaDB              │      │  AIML API (OpenAI-compatible)          │
│  bns/bnss/bsa_sections │      │  gpt-4o-mini · generate · stream ·      │
│  sc_judgements         │      │  function calling                      │
│  3,184 chunks          │      └────────────────────────────────────────┘
│  all-MiniLM-L6-v2      │
└────────────────────────┘      ┌────────────────────────────────────────┐
                                │  Committed data — NOT vector indexed    │
┌────────────────────────┐      │  offence_classification.json  465 rows  │
│  Indian Kanoon (live)  │      │  repealed_concordance.json  1,195 maps  │
│  currently unreachable │      │  doctrines.json               16 nodes  │
└────────────────────────┘      └────────────────────────────────────────┘
```

---

## 2. The grounded answer pipeline

The core path. `services/grounded_answer.py`.

```
query
  │
  ├─▶ 1. citation pre-check ────────────── "BNS 999"? ──► REFUSE (no model call)
  │
  ├─▶ 2. retrieve
  │       ├─ parse_citation()  → exact metadata fetch @ distance 0.0
  │       ├─ find_offences()   → exact metadata fetch @ distance 0.0
  │       ├─ expand_query()    → statutory phrasing appended before embedding
  │       └─ dense search over 1–3 collections, merged by distance
  │                                     │
  │                          nothing? ──► ABSTAIN
  │
  ├─▶ 3. graph expansion (seeded from top 3 only)
  │       cross-refs · interpreting judgements · doctrines · Schedule attributes
  │       rendered as CONNECTED MATERIAL, each kind kept separate
  │
  ├─▶ 4. synthesis  → JSON claims, not prose
  │       system prompt + audience register layer
  │
  ├─▶ 5. verify each claim by its class ──── all failed? ──┐
  │                                                         │
  ├─▶ 6. regenerate ONCE with named failures ◄──────────────┘
  │                                     │
  │                          still failing? → remove those claims
  │
  ├─▶ 7. metrics  (computed over what synthesis EMITTED, not what survived)
  │
  └─▶ 8. render
          nothing survived ──► ABSTAIN
          otherwise: prose + citation_note + "N statements removed" + trace
```

**Two abstention paths and one refusal path**, all of which produce a 200 with an honest
answer — never an error.

---

## 3. Data model

### 3.1 The typed claim (`backend/models/claims.py`)

Everything downstream — verification, metrics, rendering — keys off this shape.

```python
class Claim:
    text:            str
    epistemic_class: EpistemicClass
    sources:         list[Source]        # {ref, kind}
    verbatim_span:   str | None          # for statute claims that quote
    positions:       list[Position]      # for contested claims only

class Source:
    ref:  str                            # "BNS 103" | "sc_bachan_singh_1980"
    kind: SourceKind                     # SECTION | JUDGEMENT | ...

class Position:                          # a side of a contested question
    summary:   str
    authority: list[str]                 # must be non-empty
```

| `EpistemicClass` | Requires source | Verified by |
|---|---|---|
| `STATUTE` | yes | section exists + span appears verbatim |
| `CLASSIFICATION` | yes | matches its First Schedule row |
| `HOLDING` | yes | case exists **and** graph edge to the cited section |
| `INTERPRETATION` | yes | same, and must attribute to a case |
| `CONTESTED` | via positions | ≥2 positions, each with authority |
| `INFERENCE` | no | must not carry a citation formatted as law |
| `UNSUPPORTED` | — | terminal; removed from the answer |

### 3.2 Verdicts and metrics

```python
class ClaimVerdict:
    index:           int
    verified:        bool
    original_class:  EpistemicClass    # preserved so metrics can score honestly
    reason:          str               # shown in the trace panel
    reclassified_to: EpistemicClass | None
```

`original_class` is the load-bearing field: metrics are computed over the classes **synthesis
asserted**, so a statute claim that failed its verbatim check still counts in the denominator
of `verbatim_fidelity`.

### 3.3 Chunk metadata (ChromaDB)

```python
{
  "short_name":     "BNS",          # act abbreviation
  "section_number": "103",
  "act":            "Bharatiya Nyaya Sanhita",
  "title":          "Punishment for murder",
  "parent_id":      "bns_103",      # ← citability + whole-section verification
  "chunk_index":    0,
  "chunk_count":    1,
}
```

### 3.4 The legal graph

Nodes keyed by citation (`"BNS 103"`, `"BNSS 482"`); judgements and doctrines by their own
ids.

| Edge | Count | Source | Derivation |
|---|---|---|---|
| `section --cross_references--> section` | 931 | statute text | regex, mechanical |
| `judgement --interprets--> section` | 34 | judgement metadata | transcribed |
| `doctrine --established_by/refined_by--> judgement` | — | `doctrines.json` | hand-curated |
| `doctrine --applies_to--> section` | — | `doctrines.json` | hand-curated |
| `section --classified_as--> attributes` | 288 | First Schedule | parsed table |

**No LLM-inferred edges, ever.**

---

## 4. Module map

### Backend

| Path | Responsibility |
|---|---|
| `main.py` | FastAPI app; `startup_event` initialises the tool registry. **Swallows init errors** so `/health` stays up without credentials |
| `agents/legal_agent.py` | LangGraph `StateGraph`; nodes and conditional routing |
| `agents/agent_service.py` | Singleton wrapper; `process_query`, `process_query_stream` |
| `agents/intent_classifier.py` | Keyword/regex scoring + `REQUIRED_TRIGGERS` + tie-break order |
| `agents/state.py` | Graph state shape, `IntentType` |
| `agents/citations.py` | Citation formatting; `primary_citation` trims parallel reporters |
| `services/grounded_answer.py` | The pipeline above |
| `services/claim_verifier.py` | Per-class deterministic checks |
| `services/answer_metrics.py` | Grounding metrics + `aggregate()` |
| `services/legal_graph.py` | In-memory graph, `get_legal_graph()` / `reset_legal_graph()` |
| `services/procedural_timeline.py` | BNSS custody timeline, fully deterministic |
| `services/retrieval/structured_filter.py` | `parse_citation`, concordance translation |
| `services/retrieval/offence_lookup.py` | `find_offences`, `match_offences`, `is_offence_question` |
| `services/query_expansion.py` | `LEGAL_ALIASES`, additive expansion |
| `services/vector_service.py` | ChromaDB; `search()` applies structured filter + expansion |
| `services/embedding_service.py` | `all-MiniLM-L6-v2` singleton |
| `services/rag_service.py` | Context formatting, graph expansion rendering, disclaimer |
| `services/llm_service.py` | AIML API; `generate`, `generate_stream`, `generate_with_tools` |
| `services/judiciary_service.py` | Live case law; robots-aware, rate-limited, fails soft |
| `services/audience.py` | `register_layer()` — synthesis system prompt only |
| `services/data_loader.py` | Reads `data/processed/`; **raises** if absent |
| `tools/` | `BaseTool` subclasses → `ToolResult`, registered in `ToolRegistry` |
| `models/` | Pydantic request/response models — single source of truth |

### Scripts

| Script | Purpose |
|---|---|
| `ingest_legal_acts.py` | MHA gazette PDFs → `data/processed/*.json` |
| `ingest_judgments.py` | Indian Kanoon, id-pinned + `expect` verification |
| `ingest_offence_schedule.py` | BNSS First Schedule → offence table |
| `ingest_concordance.py` | BPR&D tables → repealed concordance, cross-checked |
| `init_vector_db.py` | Chunk + batch + embed into ChromaDB |
| `eval_retrieval.py` | Golden-set retrieval eval, reports to `eval/` |
| `discover_judgments.py` | Topic-driven corpus expansion — **blocked on source access** |

### Frontend

| Path | Responsibility |
|---|---|
| `pages/index.tsx` | Landing page — static, data-free, all figures test-pinned |
| `pages/app.tsx` | The product; five workspaces in `AppShell` |
| `pages/_document.tsx` | Applies stored theme **before first paint** (prevents white flash) |
| `lib/api.ts` | All HTTP; TS mirror of `backend/models/`; `stripAppendedBlocks`, `readStream` |
| `lib/workspaces.ts` | Workspace definitions, mirrored to URL hash |
| `components/legal/ClaimList.tsx` | Renders each epistemic class differently |
| `components/legal/OffencePanel.tsx` | Picks the section the answer was *about*, fetches `/offences` |
| `components/legal/ProceduralTimeline.tsx` | Hand-rolled SVG + accessible step list |
| `components/legal/TracePanel.tsx` | Metrics + every rejected claim and reason |
| `hooks/use*.ts` | Data fetching; `useOffence` caches per section |
| `styles/globals.css` + `tailwind.config.js` | Semantic colour tokens; `darkMode: 'class'` |

---

## 5. Singletons

`llm_service`, `get_agent_service()`, `get_rag_service()`, `get_vector_service()`,
`get_tool_registry()`, `get_legal_graph()`, `get_grounded_answer_service()`,
`get_embedding_service()`.

**Always use the accessors.** `reset_agent_service()` and `reset_legal_graph()` exist for
tests.

> Historical note: `backend/pytest.ini` sets `pythonpath = .` because tests once imported
> `backend.*` while the app imported `services.*` — **the same module under two names, which
> would have duplicated every singleton.** Keep everything on the `services.*` convention.

---

## 6. Request flow examples

### `POST /api/v1/agent/query` — the main path

```
lib/api.ts
  → api/v1/agent.py
    → AgentService.process_query()
      → LegalAgent graph
        → classify_intent → "rag_search"
        → _execute_rag_search_node
          → GroundedAnswerService.answer(query, CORPUS_COLLECTIONS, audience)
        → format_response
  ← { response, sources[], graph_context, verification: {claims, verdicts, metrics, trace} }
```

The frontend renders `verification.claims` through `ClaimList`, falling back to the markdown
path when `verification` is absent (chat, drafting, older responses).

### `GET /api/v1/offences/{act}/{section}` — no model involved

```
api/v1/offences.py
  → legal_graph.offence_attributes()        First Schedule row
  → procedural_timeline.build()             BNSS 35/57/58/187/193/479
  → legal_graph doctrines + judgements      connected material
  ← { classification, timeline, doctrines, judgements }
```

Deterministic and cacheable — `useOffence` caches per section because the answer comes
entirely from committed data.

---

## 7. Cross-cutting invariants

These hold across the whole system and are each protected by a test:

1. **Every AI-generated answer carries a disclaimer**, appended by the service — never
   written by the model, so nothing an instruction says can remove it.
2. **`sources` and `graph_context`/`live_sources` are never merged.** Retrieved-by-relevance
   and reached-by-edge are different provenance, and the UI must be able to distinguish them.
3. **No claim reaches the user without passing its class's check.** Unsupported claims are
   removed by construction.
4. **Audience never reaches retrieval or verification** — enforced structurally, since
   neither function takes an audience argument.
5. **No LLM-inferred graph edges.**
6. **A conditional or unresolvable value is never rendered as a boolean** — not in the
   offence table, not in the timeline, not in the UI.
7. **`backend/models/` and `frontend/lib/api.ts` stay in sync.** They are the same contract
   in two languages.

---

## 8. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AIML_API_KEY` | — | Required for any LLM call. **Missing ≠ crash** — clients are built lazily so `/health` stays up |
| `AIML_BASE_URL` | `https://api.aimlapi.com/v1` | OpenAI-compatible endpoint |
| `AIML_MODEL` | `gpt-4o-mini` | |
| `CHROMADB_PATH` | `./chroma_db` | CWD-relative; the container points it at a volume |
| `ENABLE_LIVE_JUDICIARY` | `true` | `false` for a fully offline stack |
| `JUDICIARY_MIN_REQUEST_INTERVAL` | — | Rate limit for live lookups |
| `SKIP_DB_INIT` | `false` | Bypass entrypoint seeding |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | **Build-time inlined**; the address the *browser* uses |

---

*See also: [`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md) ·
[`RAG_PIPELINE.md`](RAG_PIPELINE.md) · [`../CLAUDE.md`](../CLAUDE.md)*
