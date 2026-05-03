# Ask Mode Rules - LawAI

## Project Context
- Multi-agent Indian legal AI system built on IBM watsonx.ai (Granite-13b-chat-v2)
- LangGraph orchestrates 4 MCP tools: rag_search, draft_document, analyze_doc, chat
- ChromaDB for local vector storage (IPC, CrPC, SC judgements)
- FastAPI backend with streaming, Next.js frontend

## Architecture Overview
```
User Query → LangGraph Agent → Tool Selection → Tool Execution → Response
                    ↓
        [rag_search, draft_document, analyze_doc, chat]
                    ↓
            ChromaDB Collections
        [ipc_sections, crpc_sections, sc_judgements]
```

## Key Demo Flows
1. **Bail Application**: Intent classification → rag_search (CrPC) → draft_document → .docx
2. **Case Law Search**: rag_search (SC judgements) → synthesized answer with citations
3. **Document Analysis**: PDF upload → analyze_doc → risk summary

## Documentation Structure
- Backend code in root or `backend/` directory
- Frontend in `frontend/` directory (Next.js)
- Vector DB collections managed by ChromaDB (local persistence)
- Legal corpus data in separate directory (IPC, CrPC, SC judgements)

## Legal Domain Knowledge
- IPC: Indian Penal Code, 1860 (criminal offenses)
- CrPC: Code of Criminal Procedure, 1973 (procedural law)
- SC: Supreme Court judgements (case law)
- Citation format: "Case Name v. Case Name, (Year) SCC XXX"