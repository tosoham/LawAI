# RULES.md

This document defines the master rulebook for all development work on the LawAI project. All contributors, AI agents, and developers must follow these rules strictly.

---

## 1. Development Philosophy

### Core Principles
- **Plan First, Build Later** - NEVER start coding without an approved plan. Always discuss, design, and get user confirmation before implementation.
- **Iterative Development** - Break complex tasks into small, manageable, testable steps. Complete one step before moving to the next.
- **Documentation-Driven** - Document architecture, design decisions, and APIs before writing implementation code.
- **Test-Driven** - Write tests alongside features. Every feature must have corresponding unit and integration tests.

---

## 2. Workflow Rules (CRITICAL)

### Planning Phase
1. **Always start in Plan mode** - Discuss requirements, gather context, and create a detailed plan
2. **Create detailed todo lists** - Use `update_todo_list` for multi-step tasks to track progress
3. **Wait for approval** - Present plan → get user confirmation → switch to Code mode
4. **Ask clarifying questions** - Use `ask_followup_question` when requirements are unclear

### Implementation Phase
1. **One feature at a time** - Complete, test, and commit before moving to the next feature
2. **Frequent commits** - Make small, atomic commits with clear, descriptive messages
3. **Test before commit** - Ensure all tests pass before committing code
4. **Code review** - All code must be reviewed before merging to main branch

### Communication
- Be clear and technical in responses
- Avoid conversational phrases like "Great!", "Certainly!", "Okay!"
- Focus on actionable information and next steps

---

## 3. Tech Stack

### Core Technologies
- **LLM**: AIML API (OpenAI-compatible endpoint), default model `gpt-4o-mini`, via the `openai` SDK

  > Historical note: this was IBM watsonx.ai Granite-13b-chat-v2 while the project was a
  > hackathon entry, where that provider was a competition requirement. That constraint no
  > longer applies and the provider was swapped; the LLM layer is isolated behind
  > `services/llm_service.py`, so changing it again means rewriting only that module.
- **Agent Framework**: LangGraph for complex workflows and state management
- **Vector DB**: ChromaDB (local deployment, no cloud setup)
- **Backend**: FastAPI with async/await and StreamingResponse
- **Frontend**: Next.js with React Server-Side Rendering (SSR)

### Language & Tools
- **Backend Language**: Python 3.10+
- **Frontend Language**: TypeScript
- **Package Management**: pip (backend), npm (frontend)
- **Version Control**: Git with conventional commits

---

## 4. Legal Framework (UPDATED 2023)

### Indian Legal Codes
- **BNS** (Bharatiya Nyaya Sanhita, 2023) - Replaces Indian Penal Code (IPC)
- **BNSS** (Bharatiya Nagarik Suraksha Sanhita, 2023) - Replaces Code of Criminal Procedure (CrPC)
- **BSA** (Bharatiya Sakshya Adhiniyam, 2023) - Replaces Indian Evidence Act
- **Supreme Court Judgements** - Focus on post-2023 rulings under new legal framework

### Legal Data Requirements
- Use only official government sources for legal texts
- Maintain accurate section numbers and citations
- Include amendment dates and version tracking
- Verify legal terminology and definitions

---

## 5. Architecture Rules

### MCP Tools (4 Core Tools)
1. **rag_search** - Query Indian legal corpus (BNS, BNSS, BSA, SC judgements)
2. **draft_document** - Generate legal drafts (bail applications, petitions, notices)
3. **analyze_doc** - Extract and analyze uploaded legal documents (PDF, DOCX)
4. **chat** - General legal Q&A with context-aware responses

### Vector Database Collections
- **Separate ChromaDB collections** for:
  - BNS sections and explanations
  - BNSS procedural provisions
  - BSA evidence rules
  - Supreme Court judgements (categorized by year and topic)

### Agent Orchestration
- **LangGraph State Machine** - Routes user intent to appropriate tool(s)
- **Sequential Tool Execution** - Tools can be chained based on user query
- **Context Preservation** - Maintain conversation context across tool calls

### Streaming Requirements
- **All LLM responses MUST stream tokens** - Use FastAPI StreamingResponse
- **Real-time feedback** - Show progress indicators during long operations
- **Graceful error handling** - Stream error messages when operations fail

---

## 6. Code Quality Standards

### Python (Backend)
- **PEP 8 Compliance** - Follow Python style guide strictly
- **Type Hints** - Use type annotations for all function parameters and return values
- **Docstrings** - Write comprehensive docstrings for all modules, classes, and functions
- **Error Handling** - Use try-except blocks with specific exception types
- **Async/Await** - Use async functions for I/O operations

Example:
```python
async def search_legal_corpus(
    query: str,
    collection: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search the legal corpus using vector similarity.
    
    Args:
        query: User's search query
        collection: ChromaDB collection name (bns, bnss, bsa, judgements)
        limit: Maximum number of results to return
        
    Returns:
        List of matching documents with metadata
        
    Raises:
        ValueError: If collection name is invalid
        ChromaDBError: If database query fails
    """
    # Implementation
```

### TypeScript (Frontend)
- **Strict Mode** - Enable TypeScript strict mode in tsconfig.json
- **Proper Typing** - Define interfaces for all data structures
- **ESLint Compliance** - Follow Next.js and React best practices
- **Component Documentation** - Document props and component behavior

Example:
```typescript
interface SearchResult {
  id: string;
  content: string;
  metadata: {
    section: string;
    act: 'BNS' | 'BNSS' | 'BSA';
    relevance: number;
  };
}

async function searchLegalDatabase(
  query: string,
  filters?: SearchFilters
): Promise<SearchResult[]> {
  // Implementation
}
```

### API Design
- **RESTful Endpoints** - Follow REST conventions for API design
- **Proper HTTP Methods** - GET for reads, POST for creates, PUT/PATCH for updates
- **Error Handling** - Return appropriate HTTP status codes with error messages
- **API Versioning** - Use `/api/v1/` prefix for all endpoints
- **Request Validation** - Validate all input using Pydantic models

### Legal Domain
- **Accurate Citations** - Use proper legal citation format (e.g., "Section 302, BNS")
- **Legal Terminology** - Use correct Indian legal terms and definitions
- **Case Law Format** - Follow standard format for case citations
- **Disclaimer** - Include AI-generated content disclaimer in all outputs

---

## 7. Security & Compliance

### Data Privacy
- **No PII in Vector DB** - Never store personally identifiable information in ChromaDB
- **Data Sanitization** - Remove sensitive information before processing
- **Anonymization** - Anonymize case details in examples and training data

### Input Validation
- **Sanitize User Uploads** - Validate and sanitize all file uploads before processing
- **File Type Restrictions** - Only accept PDF and DOCX files for document analysis
- **Size Limits** - Enforce maximum file size (50MB for documents)
- **Content Scanning** - Scan uploads for malicious content

### API Security
- **Rate Limiting** - Implement rate limiting on all API endpoints
- **Authentication** - Use JWT tokens for user authentication
- **CORS Configuration** - Properly configure CORS for frontend-backend communication
- **API Keys** - Never commit API keys or secrets to version control

### Legal Compliance
- **Legal Disclaimer** - Display prominent disclaimer in UI for AI-generated content
- **Audit Logging** - Track all document generations and searches with timestamps
- **Data Retention** - Define and implement data retention policies
- **Terms of Service** - Require users to accept terms before using the system

---

## 8. Testing Requirements

### Unit Tests
- **Each MCP Tool** - Write unit tests for all four MCP tools
- **Helper Functions** - Test all utility and helper functions
- **Edge Cases** - Test boundary conditions and error scenarios
- **Mock External Services** - Mock LLM and database calls in unit tests

### Integration Tests
- **Agent Flows** - Test complete user journeys through the agent system
- **Tool Chaining** - Test sequential execution of multiple tools
- **Error Recovery** - Test system behavior when tools fail
- **Performance** - Test response times under load

### Data Testing
- **Real Legal Data** - Test with actual BNS, BNSS, and BSA sections
- **SC Judgements** - Test with real Supreme Court judgement samples
- **Document Formats** - Test PDF and DOCX parsing with various formats
- **Edge Cases** - Test with malformed documents and unusual queries

### Document Validation
- **DOCX Generation** - Verify generated documents are valid and properly formatted
- **PDF Parsing** - Ensure accurate text extraction from PDFs
- **Citation Accuracy** - Validate legal citations in generated documents
- **Template Compliance** - Verify documents follow legal templates

### Test Coverage
- **Minimum 80% Coverage** - Maintain at least 80% code coverage
- **Critical Paths** - 100% coverage for security and legal accuracy code
- **Continuous Testing** - Run tests on every commit via CI/CD

---

## 9. Performance Benchmarks

### Response Time Targets
- **RAG Search Response Time**: < 2 seconds from query to first result
- **Streaming Latency**: 
  - First token: < 500ms
  - Between tokens: < 50ms
- **Document Generation**: < 5 seconds for standard bail application
- **PDF Analysis**: < 3 seconds for documents up to 50 pages
- **Vector Search**: < 1 second for similarity search across 10,000+ documents
- **API Response Time**: < 200ms for non-LLM endpoints
- **Database Query**: < 100ms for metadata queries

### Scalability Targets
- **Concurrent Users**: Support 50+ simultaneous users
- **Memory Usage**: 
  - Backend: < 2GB RAM
  - ChromaDB: < 4GB RAM
- **Storage**: Efficient vector storage with compression
- **Throughput**: Handle 100+ requests per minute

### Monitoring
- **Performance Metrics** - Track all benchmark metrics in production
- **Alerting** - Set up alerts when metrics exceed thresholds
- **Logging** - Log slow queries and operations for optimization
- **Regular Audits** - Review performance metrics weekly

---

## 10. Prohibited Actions

### Development
- ❌ **Starting implementation without approved plan** - Always plan first
- ❌ **Skipping tests** - Never commit code without tests
- ❌ **Ignoring code review feedback** - Address all review comments
- ❌ **Deploying without passing tests** - All tests must pass before deployment

### Security
- ❌ **Storing PII in vector database** - Never store personal information
- ❌ **Committing secrets or API keys** - Use environment variables
- ❌ **Skipping input validation** - Always validate and sanitize inputs
- ❌ **Disabling security features** - Never disable CORS, rate limiting, etc.

### Legal
- ❌ **Skipping legal disclaimers** - Always include AI-generated content warnings
- ❌ **Using unofficial legal sources** - Only use government-verified legal texts
- ❌ **Providing legal advice** - System assists, does not replace lawyers
- ❌ **Ignoring legal accuracy** - Verify all citations and legal references

### Data
- ❌ **Using outdated legal codes** - Always use BNS/BNSS/BSA (2023+)
- ❌ **Mixing old and new legal frameworks** - Don't reference IPC/CrPC in new code
- ❌ **Storing unencrypted sensitive data** - Encrypt all sensitive information
- ❌ **Sharing user data** - Never share user queries or documents

---

## 11. File Organization

```
LawAI/
├── backend/                 # FastAPI application
│   ├── agents/             # LangGraph agent logic
│   │   ├── __init__.py
│   │   ├── orchestrator.py # Main agent orchestrator
│   │   └── state.py        # Agent state definitions
│   ├── tools/              # MCP tool implementations
│   │   ├── __init__.py
│   │   ├── rag_search.py   # RAG search tool
│   │   ├── draft_document.py # Document generation
│   │   ├── analyze_doc.py  # Document analysis
│   │   └── chat.py         # Chat tool
│   ├── models/             # Pydantic data models
│   │   ├── __init__.py
│   │   ├── requests.py     # API request models
│   │   └── responses.py    # API response models
│   ├── services/           # Business logic services
│   │   ├── __init__.py
│   │   ├── llm_service.py  # AIML API (OpenAI-compatible) integration
│   │   └── vector_db.py    # ChromaDB operations
│   ├── api/                # API routes
│   │   ├── __init__.py
│   │   └── v1/             # API version 1
│   ├── tests/              # Backend tests
│   │   ├── unit/
│   │   └── integration/
│   ├── main.py             # FastAPI app entry point
│   └── requirements.txt    # Python dependencies
├── frontend/               # Next.js application
│   ├── components/         # React components
│   │   ├── chat/
│   │   ├── search/
│   │   └── documents/
│   ├── pages/              # Next.js pages
│   │   ├── api/            # API routes (if needed)
│   │   ├── index.tsx       # Home page
│   │   └── _app.tsx        # App wrapper
│   ├── lib/                # Utility functions
│   ├── styles/             # CSS/styling
│   ├── tests/              # Frontend tests
│   ├── package.json
│   └── tsconfig.json
├── data/                   # Legal corpus data
│   ├── bns/                # BNS sections
│   ├── bnss/               # BNSS sections
│   ├── bsa/                # BSA sections
│   └── judgements/         # SC judgements
├── docs/                   # Documentation
│   ├── api/                # API documentation
│   ├── architecture/       # Architecture diagrams
│   └── guides/             # User guides
├── scripts/                # Utility scripts
│   ├── setup_db.py         # Initialize ChromaDB
│   └── import_data.py      # Import legal corpus
├── .gitignore
├── AGENTS.md               # Agent-specific guidance
├── RULES.md                # This file
├── README.md               # Project overview
└── LICENSE
```

---

## 12. Git Workflow

### Branch Naming
- `feature/` - New features (e.g., `feature/rag-search`)
- `bugfix/` - Bug fixes (e.g., `bugfix/streaming-error`)
- `docs/` - Documentation updates (e.g., `docs/api-guide`)
- `test/` - Test additions (e.g., `test/integration-tests`)
- `refactor/` - Code refactoring (e.g., `refactor/agent-state`)

### Commit Messages
Follow conventional commits format:
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat(rag): add BNS section search functionality

Implemented vector search for BNS sections with metadata filtering.
Includes unit tests and integration tests.

Closes #123
```

### Pull Request Requirements
- ✅ All tests pass
- ✅ Code reviewed by at least one team member
- ✅ Documentation updated
- ✅ No merge conflicts
- ✅ Follows code quality standards

### Main Branch Protection
- **Protected branch** - Cannot push directly to main
- **Requires PR approval** - At least one approval required
- **Status checks** - All CI/CD checks must pass
- **Linear history** - Use squash or rebase merge

---

## 13. Development Commands

### Backend (FastAPI)
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=backend --cov-report=html

# Type checking
mypy backend/

# Linting
ruff check backend/
```

### Frontend (Next.js)
```bash
# Install dependencies
cd frontend
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Run tests
npm test

# Run tests with coverage
npm test -- --coverage

# Type checking
npm run type-check

# Linting
npm run lint
```

### Vector Database (ChromaDB)
```bash
# ChromaDB runs locally - no separate setup needed
# Initialize database with legal corpus
python scripts/setup_db.py

# Import legal data
python scripts/import_data.py --source data/bns --collection bns
python scripts/import_data.py --source data/bnss --collection bnss
python scripts/import_data.py --source data/bsa --collection bsa
```

---

## 14. Documentation Requirements

### Code Documentation
- **Module Docstrings** - Every Python module must have a docstring
- **Function Docstrings** - Document parameters, return values, and exceptions
- **Class Docstrings** - Document class purpose and attributes
- **Inline Comments** - Explain complex logic and business rules

### API Documentation
- **OpenAPI/Swagger** - Auto-generate API docs from FastAPI
- **Endpoint Documentation** - Document all endpoints with examples
- **Request/Response Examples** - Provide sample JSON payloads
- **Error Codes** - Document all possible error responses

### User Documentation
- **README.md** - Project overview and quick start guide
- **User Guides** - Step-by-step guides for common tasks
- **FAQ** - Frequently asked questions and troubleshooting
- **Legal Disclaimer** - Clear explanation of system limitations

### Architecture Documentation
- **System Architecture** - High-level system design diagrams
- **Data Flow** - Document how data flows through the system
- **Agent Logic** - Explain LangGraph state machine and tool routing
- **Database Schema** - Document ChromaDB collections and metadata

---

## Conclusion

These rules are designed to ensure high-quality, secure, and legally accurate development of the LawAI system. All contributors must follow these guidelines strictly. When in doubt, always prioritize:

1. **Planning over implementation**
2. **Security over convenience**
3. **Legal accuracy over speed**
4. **Code quality over quick fixes**

For questions or clarifications, refer to [`AGENTS.md`](AGENTS.md) for agent-specific guidance or create an issue in the project repository.

---

**Last Updated**: 2026-05-03  
**Version**: 1.0.0