# LawAI

**A legal AI for Indian criminal law that tells you when it cannot answer.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)

---

## What it is

LawAI answers questions about Indian criminal law under the **2023 codes** — the Bharatiya
Nyaya Sanhita (BNS), Bharatiya Nagarik Suraksha Sanhita (BNSS) and Bharatiya Sakshya
Adhiniyam (BSA), which replaced the IPC, CrPC and Indian Evidence Act.

The corpus is **parsed from official Ministry of Home Affairs gazette PDFs** — 1,059
statutory sections, complete and verbatim — plus 30 id-pinned Supreme Court judgements, the
BNSS First Schedule as a structured table, and a sourced concordance from the repealed
codes.

## What makes it different

Most legal AI competes on being right. This one is built to **know when it is not**.

**An answer is a list of typed claims, not prose.** Each claim declares what kind of
assertion it is — enacted text, procedural classification, a court's holding, a contested
question, or the model's own inference — and **each class is checked by a rule appropriate to
it, mechanically, against committed data.**

**Nothing asks a model whether a model was right.** Self-grading fails exactly where it is
needed: the prior that invented BNS 999 will confirm BNS 999. Every check is a lookup.

| Class | How it is verified |
|---|---|
| `statute` | the section exists, and any quoted span appears in it **verbatim** |
| `classification` | matches its row in the BNSS First Schedule |
| `holding` / `interpretation` | the case exists **and** the graph records it as bearing on the cited section |
| `contested` | rejected below two positions, each with authority |
| `inference` | may rest on nothing, but must not carry a citation formatted as law |

**A claim that fails is deleted, not hedged** — and the removal is reported to the reader. If
nothing survives, the system abstains and says so.

**Some questions never reach a model at all.** "Is this bailable?" and "how long can they
hold me?" are answered from parsed tables and the text of BNSS 35/57/58/187/193/479 —
deterministically, with every step citing its section.

---

## Measured results

**Retrieval** — 69-query golden set in five failure classes, reports committed in
`backend/eval/`:

| Stage | recall@1 | recall@3 | MRR | nDCG@10 |
|---|---|---|---|---|
| Dense vector only | 0.536 | 0.652 | 0.618 | 0.639 |
| + query expansion | 0.638 | 0.768 | 0.719 | 0.733 |
| + structured citation lookup | 0.725 | 0.855 | 0.802 | 0.815 |
| + concordance | **0.812** | **0.928** | **0.879** | **0.890** |

Per class, each layer moved exactly what it targeted: `term_of_art` 0.500 → **0.875**,
`citation` 0.250 → **1.000**, `repealed_code` 0.125 → **1.000**, with `plain` unchanged at
0.960 throughout.

**Adversarial** — 6/6 prompt injections held; drift 100% consistent across repeated runs on
the consequential values.

**Tests** — 763 backend (755 pass, 8 skip), 106 frontend.

> **What these numbers are not.** `0.93` is *retrieval recall* on a 69-query set written for
> this project. It is not "accuracy", not a public benchmark, and the set is small. Nothing
> here measures "% accurate", and nothing here claims it.

---

## Corpus

| Collection | Source | Records |
|---|---|---|
| `bns_sections` | MHA gazette PDF | 358 (complete) |
| `bnss_sections` | MHA gazette PDF | 531 (complete) |
| `bsa_sections` | MHA gazette PDF | 170 (complete) |
| `sc_judgements` | Indian Kanoon, id-pinned | 30 |
| `offence_classification.json` | BNSS First Schedule, Part I | 465 rows |
| `repealed_concordance.json` | BPR&D correspondence tables | 1,195 mappings |
| `data/curated/doctrines.json` | hand-curated | 16 doctrines |

1,089 documents → **3,184 chunks**. All committed, so the project runs without re-fetching.

The legal graph over this: **1,059 sections, 931 cross-references, 34 interprets edges, 288
classified sections.** No LLM-inferred edges — cross-references are mechanical, judgement
edges are transcribed metadata, doctrine edges are curated by hand.

---

## Architecture

```
Frontend (Next.js, Pages Router)
  /        landing page — static, renders with the backend down
  /app     five workspaces: Ask · Corpus · Live research · Draft · Analyse
                                  │
Backend (FastAPI)                 ▼
  LangGraph agent → classify intent → one of five tool nodes
                                  │
  Grounded answer pipeline:
    citation pre-check → retrieve → graph expansion → synthesise typed claims
      → verify → regenerate once → remove failures → metrics + trace
                                  │
  ChromaDB (3,184 chunks, all-MiniLM-L6-v2)  ·  AIML API (gpt-4o-mini)
  Deterministic layer: offence table · concordance · procedural timeline
```

**Tech:** FastAPI · Next.js 14 + TypeScript + Tailwind · ChromaDB · sentence-transformers
`all-MiniLM-L6-v2` · LangGraph · AIML API (OpenAI-compatible).

Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Quick start

### Docker (recommended)

Needs Docker with Compose v2 and an AIML API key.

```bash
cp backend/.env.example backend/.env   # then set AIML_API_KEY
docker compose up --build
```

- Frontend → `http://localhost:3000`
- Backend  → `http://localhost:8000/docs`

The first start embeds the corpus into a named volume (`chroma_data`) — a few minutes, and
it happens **once**. To rebuild from scratch: `docker compose down -v`.

| Variable | Default | Purpose |
|---|---|---|
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Published host ports |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend address **as the browser sees it**; baked in at build time, so changing it needs `--build` |
| `ENABLE_LIVE_JUDICIARY` | `true` | Set `false` for a fully offline stack |

The backend image bundles the embedding model, so with live judiciary access off the
container needs no network at all.

### Local development

Prerequisites: Python 3.10+, Node.js 18+, an [AIML API](https://aimlapi.com) key.

```bash
# Backend — all commands run from backend/
cd backend
python -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env            # then set AIML_API_KEY
python scripts/init_vector_db.py
uvicorn main:app --reload       # :8000, docs at /docs

# Frontend
cd frontend
npm install && cp .env.local.example .env.local
npm run dev                     # :3000
```

Backend commands **must** run from `backend/` — imports are rooted there and `pytest.ini`
sets `pythonpath = .` to match.

---

## Testing

```bash
# Backend (from backend/)
pytest                          # 755 pass, 8 skip — no credentials needed
pytest -m live                  # live-model tests (needs AIML_API_KEY)
pytest --cov=. --cov-report=html
ruff check . && mypy .

# The hard gate: 6 adversarial queries must abstain, 4 answerable must not,
# and murder must never come back bailable
pytest tests/integration/test_grounded_answer_live.py -v

# Retrieval eval
python scripts/eval_retrieval.py --compare concordance

# Frontend (from frontend/)
npm test && npm run lint && npm run type-check
```

Tests calling the live API are marked `live` and **skip automatically** without
`AIML_API_KEY`, so a plain `pytest` run is green with no credentials.

---

## API

Base: `/api/v1`

| Endpoint | Purpose |
|---|---|
| `POST agent/query`, `agent/query/stream` | Main agent entry points |
| `POST search/grounded` | Typed claims, per-claim verdicts, metrics, trace — abstains rather than guessing |
| `POST search/rag` | Direct RAG over a chosen collection |
| `GET offences/{act}/{section}`, `offences` | Classification, doctrine, case law, custody timeline. **No model involved** |
| `research/case-law`, `research/judgment/{id}`, `research/health` | Live judiciary lookups |
| `documents/draft`, `analyze`, `export/docx`, `templates` | Document generation and analysis |
| `chat/*`, `health`, `info` | |

Pydantic models in `backend/models/` are the single source of truth; TypeScript mirrors in
`frontend/lib/api.ts`.

---

## Documentation

**[`docs/`](docs/README.md) is the index.** The substantive documents:

| Document | Covers |
|---|---|
| **[Engineering Deep Dive](docs/ENGINEERING_DEEP_DIVE.md)** | End-to-end working, every layer, every challenge and fix, honest limitations |
| **[Architecture](docs/ARCHITECTURE.md)** | Diagrams, request flows, data model, module map, invariants |
| **[RAG Pipeline](docs/RAG_PIPELINE.md)** | Chunking, batching, embedding, the four-layer retrieval stack |
| **[Evaluation and Testing](docs/EVALUATION_AND_TESTING.md)** | Golden set, metrics, abstention measurement, adversarial suite |
| **[Challenges and Solutions](docs/CHALLENGES_AND_SOLUTIONS.md)** | 60+ indexed problems as Symptom → Cause → Fix → Guard |
| [CLAUDE.md](CLAUDE.md) | Authoritative guide for AI coding agents |

---

## Known limitations

Stated plainly, because overclaiming is the exact failure this system is built to avoid.

- **This is not multi-agent collaboration.** It is a single agent with keyword-based routing
  to five tool nodes. There is no negotiation, critique or handoff between agents. The
  planner-plus-specialists design, including a dialectical path for contested constitutional
  questions, is **designed and not built**. What exists is a *verification* architecture.
- **The corpus holds 30 judgements, not the planned 300.** Expansion is written and tested
  but unrunnable — the source is behind a Cloudflare challenge that 403s every path including
  `/robots.txt`. That access control is deliberate and has not been worked around; the
  blockage is surfaced through `GET /research/health` instead.
- **Agent streaming is faux-streaming.** The graph runs to completion, then the string is
  chunked into SSE frames. Real token streaming exists on `POST /chat`.
- **No authentication, rate limiting or CI.**
- **`judgement`-class retrieval has never improved** (recall@3 0.833) — no layer targeted it,
  and 12 queries over 30 judgements is a thin sample.
- **The golden set was written by the same person who wrote the system.** A second annotator
  is the fix.

---

## Legal disclaimer

**LawAI is an AI-powered legal assistance tool and does NOT replace professional legal
advice.** Every generated answer carries a disclaimer appended by the service. All output
should be reviewed by a qualified legal professional before use.

The system will not tell a judge how to decide. Judge mode sets out the provisions, the
competing arguments, the authority on each side and the statutory range — and never suggests
an outcome, by implication, ordering or emphasis.

---

## License

MIT — see [LICENSE](LICENSE).

## Author

**tosoham** — [todrsoham@gmail.com](mailto:todrsoham@gmail.com)

## Acknowledgments

Ministry of Home Affairs for the official gazette texts of the 2023 codes · Bureau of Police
Research and Development for the correspondence tables · Indian Kanoon for public access to
Supreme Court judgements · LangGraph, ChromaDB, sentence-transformers, FastAPI and Next.js.
