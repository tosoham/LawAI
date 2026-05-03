# Advanced Mode Rules - LawAI

## IBM watsonx.ai Integration (Critical)
- **MUST use langchain-ibm** - This is non-negotiable for IBM criterion
- Import: `from langchain_ibm import WatsonxLLM`
- Model: `Granite-13b-chat-v2`
- Never use OpenAI or other LLM providers

## LangGraph Agent Pattern
- Agent state machine routes to 4 MCP tools: rag_search, draft_document, analyze_doc, chat
- Each tool must be a separate function with clear input/output schemas
- Use LangGraph's `StateGraph` for orchestration
- Tool selection based on user intent classification

## ChromaDB Collections
- Create separate collections: `ipc_sections`, `crpc_sections`, `sc_judgements`
- Local persistence - no cloud configuration
- Embedding model: Use IBM watsonx.ai embeddings or sentence-transformers

## FastAPI Streaming
- Use `StreamingResponse` for all LLM outputs
- Yield tokens as they arrive from watsonx.ai
- Content-Type: `text/event-stream`
- Handle connection drops gracefully

## Document Processing
- PDF extraction: Use PyPDF2 or pdfplumber
- .docx generation: Use python-docx library
- Sanitize all user uploads before processing
- Max file size limits for uploads

## Legal Domain Specifics
- IPC sections format: "Section XXX, Indian Penal Code, 1860"
- CrPC sections format: "Section XXX, Code of Criminal Procedure, 1973"
- SC citations: "Case Name v. Case Name, (Year) SCC XXX"
- Always include legal disclaimers in generated documents

## Error Handling
- Wrap watsonx.ai calls in try-except with retry logic
- Return user-friendly error messages (hide technical details)
- Log all errors for debugging
- Graceful degradation if RAG search fails

## MCP & Browser Tools
- Advanced mode has access to MCP servers and browser tools
- Can use external APIs and web scraping for legal research
- Integrate with legal databases if available