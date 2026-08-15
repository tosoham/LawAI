# AGENTS.md

Guidance for AI coding agents working in this repository.

**[CLAUDE.md](CLAUDE.md) is the authoritative guide** — architecture, commands, and the
non-obvious behaviours worth knowing before changing anything. Read it first. This file
covers only the domain rules that sit on top of it.

For the reasoning behind any of these rules, see
[`docs/ENGINEERING_DEEP_DIVE.md`](docs/ENGINEERING_DEEP_DIVE.md); for the specific bug a rule
prevents, see [`docs/CHALLENGES_AND_SOLUTIONS.md`](docs/CHALLENGES_AND_SOLUTIONS.md).

## Project

LawAI answers questions about Indian criminal law under the 2023 codes. A LangGraph agent
classifies intent and routes to one of five tool nodes (`rag_search`, `chat`,
`draft_document`, `analyze_document`, `live_research`), backed by an LLM served through
**AIML API** and a ChromaDB store of the post-2023 codes.

The `rag_search` path runs through the **grounded answer pipeline**: retrieve → expand over
the legal graph → synthesise typed claims → verify each one → remove what fails → abstain if
nothing survives.

## Hard requirements

- **The legal framework is the 2023 codes, not the pre-2023 ones.** BNS replaces the IPC,
  BNSS replaces the CrPC, BSA replaces the Evidence Act. Never cite IPC/CrPC/Evidence Act
  sections as current law.
- **Citations must be exact.** Format: "Section 103, Bharatiya Nyaya Sanhita, 2023"; case law
  as "Case Name v. Case Name, (Year) Citation". A wrong section number or a misattributed
  judgement is a correctness bug, not a cosmetic one — **omit a citation rather than guess
  it.**
- **Every AI-generated answer or document carries a disclaimer.** Appended by the service in
  `RAGService` and the tools — never written by the model, so no instruction can remove it.
  The frontend must surface `LegalDisclaimer`.
- **No PII in the vector database.** Sanitise uploads before processing.

## The rules that keep answers honest

Violating any of these is a correctness regression, not a style issue.

- **Never let a model verify a model.** Every check in `services/claim_verifier.py` is a
  lookup against committed data. The prior that invented BNS 999 will confirm BNS 999.
- **Never resolve a conditional value to a boolean.** ~40 First Schedule rows defer to
  another offence ("According as offence abetted is…"); those stay `null` and carry the
  Schedule's own wording. A guessed "bailable" is the most dangerous value this system can
  emit.
- **Never add an LLM-inferred graph edge.** A false relation propagates into every answer
  touching either endpoint with nothing in the output to show it was invented.
- **Never claim precedential status.** No `overruled_by`, no `still_good_law`, anywhere in
  the data or the output. Where authority splits, mark the doctrine `contested`, name both
  sides, and declare no winner.
- **Never merge `sources` with `graph_context` or `live_sources`.** One was retrieved by
  relevance, one reached by an edge, one is unverified. The API keeps them separate and so
  must the UI.
- **Never resolve a repealed section number by assumption.** "CrPC 438" means BNSS 482, but
  BNSS 438 exists and is about something else. Translate through the concordance or refuse.
- **Never hedge a failed claim.** Remove it and report the removal. Hedging an invented
  section number still puts the number in front of the reader.
- **Audience never reaches retrieval or verification.** `services/audience.py` is a layer on
  the synthesis prompt only. Neither `VectorService.search` nor `claim_verifier.verify` takes
  an audience argument, and it must stay that way.

## Corpus

Verbatim official text, not summaries: **358 BNS, 531 BNSS, 170 BSA** sections parsed from
the Ministry of Home Affairs gazette PDFs, plus **30** curated Supreme Court judgements,
**465** First Schedule offence rows and **1,195** concordance mappings.

Regenerate with `scripts/ingest_legal_acts.py`, `scripts/ingest_judgments.py`,
`scripts/ingest_offence_schedule.py` and `scripts/ingest_concordance.py`, then reseed with
`scripts/init_vector_db.py`. All outputs are committed, so this is rarely necessary.

When adding judgements, **pin the document id** and give `expect` tokens so ingestion
verifies it fetched the right case. Searching by name alone returns the wrong authority often
enough to matter — searching "Selvi vs State of Karnataka" returns the unrelated Jayalalitha
appeal, and one landmark id matched its expected title tokens while being a contempt petition
between the same parties. See the note at the top of `scripts/ingest_judgments.py`.

## Code style

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- TypeScript: standard Next.js conventions (**Pages Router**, not App Router).
- Colour in the frontend comes **only from semantic tokens** (`canvas`, `surface`, `ink`,
  `muted`, `line`, `brand`, `brass`, `verified`, `live`). A raw hex or a stock Tailwind grey
  breaks dark mode.
- Keep `backend/models/` and the mirrored types in `frontend/lib/api.ts` in sync — they are
  the same contract in two languages, and they have silently diverged before, crashing every
  answer in the UI.
- Write tests alongside features. Run `pytest` from `backend/`.
- `ruff check .` is clean; keep it that way. The rule set is pinned in `pyproject.toml`
  because ruff widens its defaults every release.

## Before you commit

```bash
cd backend && pytest && ruff check .
cd frontend && npm test && npm run lint && npm run type-check
```

If you changed retrieval, also run
`python scripts/eval_retrieval.py --compare concordance` and confirm no class regressed.
