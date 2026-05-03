# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
**LawAI** - Multi-agent Indian legal AI system for lawyers, courts, and public
- **LLM**: IBM watsonx.ai with Granite-13b-chat-v2 (via langchain-ibm)
- **Agent Framework**: LangGraph for orchestration
- **Vector DB**: ChromaDB (local, no cloud setup)
- **Backend**: FastAPI with StreamingResponse for real-time tokens
- **Frontend**: Next.js (deploy to Vercel)

## Architecture
LangGraph agent orchestrates 4 MCP tools:
1. **rag_search** - Query Indian legal corpus (IPC, CrPC, SC judgements)
2. **draft_document** - Generate legal drafts (bail applications, petitions)
3. **analyze_doc** - Extract and analyze uploaded legal documents (PDF)
4. **chat** - General legal Q&A with context

## Core Demo Flows
1. **Bail Application**: "Client arrested under IPC 302" → rag_search (CrPC 437/439) → draft_document → .docx download
2. **Case Law Search**: "SC anticipatory bail rulings last 5 years" → rag_search → synthesized answer with citations
3. **Document Analysis**: Upload rental agreement PDF → analyze_doc → risk summary (termination clauses, indemnity traps)

## Development Commands
```bash
# Backend (FastAPI)
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (Next.js)
cd frontend
npm install
npm run dev

# Vector DB setup
# ChromaDB runs locally - no separate setup needed
```

## Key Implementation Notes
- **IBM watsonx.ai**: Use langchain-ibm for API integration (non-negotiable requirement)
- **Streaming**: FastAPI StreamingResponse for token-by-token output
- **RAG Collections**: Separate ChromaDB collections for IPC, CrPC, SC judgements
- **Document Processing**: PDF text extraction for analyze_doc tool
- **Agent Logic**: LangGraph state machine routes user intent to appropriate tool(s)

## Code Style
- Python: PEP 8, type hints, docstrings
- TypeScript/Next.js: Standard Next.js conventions
- API: RESTful endpoints, proper error handling
- Legal Domain: Accurate citation formats, Indian legal terminology

## Testing
- Unit tests for each MCP tool
- Integration tests for agent flows
- Test with real IPC/CrPC sections and SC judgement samples
- Verify .docx generation and PDF parsing

## Security & Compliance
- No PII storage in vector DB
- Sanitize user uploads before processing
- Rate limiting on API endpoints
- Legal disclaimer in UI (AI-generated content)