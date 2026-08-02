# AGENTS.md

Guidance for AI coding agents working in this repository.

**[CLAUDE.md](CLAUDE.md) is the authoritative guide** — architecture, commands, and the
non-obvious behaviours worth knowing before changing anything. Read it first. This file
covers only the domain rules that sit on top of it.

## Project

LawAI is a multi-agent Indian legal AI system. A LangGraph agent classifies intent and routes
to one of four tools (`rag_search`, `chat`, `draft_document`, `analyze_doc`) backed by an LLM
served through **AIML API** and a ChromaDB store of the post-2023 Indian legal codes.

## Hard requirements

- **Legal framework is the 2023 codes, not the pre-2023 ones.** BNS replaces the IPC, BNSS
  replaces the CrPC, BSA replaces the Evidence Act. Never cite IPC/CrPC/Evidence Act sections
  as current law.
- **Citations must be accurate.** Format: "Section 103, Bharatiya Nyaya Sanhita, 2023";
  case law as "Case Name v. Case Name, (Year) Citation". A wrong section number or a
  misattributed judgement is a serious defect, not a cosmetic one — prefer omitting a
  citation to guessing it.
- **Every AI-generated answer or document carries a disclaimer.** The backend appends one in
  `RAGService` and the tools; the frontend must surface the `LegalDisclaimer` component.
- **No PII in the vector database.** Sanitise uploads before processing.

## Corpus

The vector store holds verbatim official text, not summaries: 358 BNS, 531 BNSS and 170 BSA
sections parsed from the Ministry of Home Affairs gazette PDFs, plus 27 curated Supreme Court
judgements. Regenerate with `scripts/ingest_legal_acts.py` and `scripts/ingest_judgments.py`,
then reseed with `scripts/init_vector_db.py`.

When adding judgements, pin the document id and give `expect` tokens so ingestion verifies it
fetched the right case. Searching by name alone returns the wrong authority often enough to
matter — see the note at the top of `scripts/ingest_judgments.py`.

## Code style

- Python: PEP 8, type hints, docstrings, module-level `logger = logging.getLogger(__name__)`.
- TypeScript: standard Next.js conventions (Pages Router, not App Router).
- Keep `backend/models/` and the mirrored types in `frontend/lib/api.ts` in sync.
- Write tests alongside features; run `pytest` from `backend/`.
