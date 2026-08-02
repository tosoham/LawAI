# LawAI - Complete Implementation Plan

**Last Updated**: 2026-08-03
**Status**: Historical planning document — superseded in part, see below
**Approach**: Iterative, phased development with testing after each phase

---

> ## ⚠️ What actually shipped differs from this plan
>
> This document records the original plan and is kept for context. Two things have since
> changed, so read it with these corrections in mind. **[CLAUDE.md](../CLAUDE.md) describes
> the system as it actually is.**
>
> **1. The LLM provider is no longer IBM watsonx.ai.** Phase 2 below specifies watsonx.ai
> with Granite-13b-chat-v2 and `langchain-ibm`, which was a hackathon requirement. That
> constraint no longer applies. The system now calls **AIML API** (an OpenAI-compatible
> endpoint, default model `gpt-4o-mini`) through the `openai` SDK. Everything is isolated in
> `backend/services/llm_service.py`. `scripts/setup_ibm_watsonx.py` and
> `docs/setup/IBM_WATSONX_SETUP.md` referenced below were never created and never will be.
>
> **2. Phase 3's data collection was implemented differently — and its targets were met.**
> The planned `collect_legal_data.py` / `process_legal_data.py` / `import_data.py` scripts
> do not exist. The equivalent pipeline is:
>
> | Planned | Actual |
> |---|---|
> | `scripts/collect_legal_data.py` | `backend/scripts/ingest_legal_acts.py` (downloads + parses the MHA gazette PDFs) |
> | `scripts/process_legal_data.py` | same script; writes `data/processed/*.json` |
> | `scripts/import_data.py` | `backend/scripts/init_vector_db.py` (chunks + embeds) |
> | — | `backend/scripts/ingest_judgments.py` (curated Supreme Court judgements) |
> | `backend/services/vector_db.py` | `backend/services/vector_service.py` |
>
> Collection names are `bns_sections`, `bnss_sections`, `bsa_sections`, `sc_judgements`.
>
> Phase 3's volume criteria are met: **358 BNS** (target 300+), **531 BNSS** (target 500+),
> **170 BSA** (target 150+). Judgements are **27** against a 50+ target — deliberately, as
> each is verified by document id rather than resolved by search, which returns the wrong
> authority often enough to matter for citations.

---

## 🎯 Overview

This document outlines the complete 10-phase implementation plan for LawAI, a multi-agent Indian legal AI system. Each phase builds upon the previous one, with clear deliverables and success criteria.

**Key Principles**:
- Plan first, build later
- Iterative development with frequent testing
- One feature at a time
- Test before moving to next phase

---

## 📋 Phase 1: Project Foundation & Setup

**Goal**: Establish project structure, dependencies, and development environment (WITHOUT data collection)

**Duration**: 6-8 hours

### Tasks

#### 1.1 Project Structure
- Create directory structure:
  ```
  LawAI/
  ├── backend/
  │   ├── agents/
  │   ├── tools/
  │   ├── models/
  │   ├── services/
  │   ├── api/v1/
  │   ├── tests/
  │   ├── main.py
  │   ├── requirements.txt
  │   └── .env.example
  ├── frontend/
  │   ├── components/
  │   ├── pages/
  │   ├── lib/
  │   ├── styles/
  │   ├── package.json
  │   ├── tsconfig.json
  │   └── .env.local.example
  ├── data/
  │   ├── raw/              # Placeholder for Phase 3
  │   └── processed/        # Placeholder for Phase 3
  ├── scripts/
  ├── docs/
  ├── .gitignore
  └── README.md
  ```

#### 1.2 Backend Setup
- Create `backend/requirements.txt`:
  ```txt
  fastapi==0.109.0
  uvicorn[standard]==0.27.0
  langchain-ibm==0.1.0
  langgraph==0.0.26
  chromadb==0.4.22
  pydantic==2.5.3
  python-multipart==0.0.6
  pypdf==3.17.4
  python-docx==1.1.0
  pytest==7.4.4
  pytest-asyncio==0.23.3
  pytest-cov==4.1.0
  ruff==0.1.14
  ```
- Create `backend/.env.example`
- Create `backend/main.py` with basic FastAPI app
- Set up Python virtual environment
- Install dependencies

#### 1.3 Frontend Setup
- Move root `package.json` to `frontend/package.json`
- Create `frontend/package.json` with:
  - Next.js 14.1.0
  - React 18.2.0
  - TypeScript 5.3.3
  - Tailwind CSS 3.4.1
  - Axios for API calls
- Create `frontend/tsconfig.json` (strict mode)
- Create `frontend/tailwind.config.js`
- Create `frontend/.env.local.example`
- Install dependencies

#### 1.4 Git Configuration
- Update `.gitignore` for Python, Node.js, ChromaDB
- Create `CONTRIBUTING.md` with Git workflow
- Set up branch naming conventions
- Configure conventional commits

#### 1.5 Documentation
- Update `README.md` with project overview
- Create `docs/setup/DEVELOPMENT_SETUP.md`
- Create `docs/setup/IBM_WATSONX_SETUP.md` (guide only, setup in Phase 2)

#### 1.6 Verification
- Create `scripts/verify_setup.py` to check:
  - Python version (3.10+)
  - Node.js version (18+)
  - Dependencies installed
  - Directory structure correct

### Deliverables
- ✅ Complete directory structure
- ✅ Backend dependencies installed
- ✅ Frontend dependencies installed
- ✅ Git workflow configured
- ✅ Basic documentation in place
- ✅ Verification script passes

### Success Criteria
- `python scripts/verify_setup.py` passes all checks
- `cd backend && uvicorn main:app --reload` starts successfully
- `cd frontend && npm run dev` starts successfully
- No errors in dependency installation

---

## 📋 Phase 2: Backend Core Infrastructure & IBM watsonx.ai Integration

**Goal**: Build FastAPI foundation and integrate IBM watsonx.ai with Granite-13b-chat-v2

**Duration**: 8-10 hours

### Tasks

#### 2.1 IBM watsonx.ai Setup
- Create IBM Cloud account
- Provision watsonx.ai service
- Generate API key and Project ID
- Test connection to Granite-13b-chat-v2 model
- Create `scripts/setup_ibm_watsonx.py` for credential validation
- Document setup process in `docs/setup/IBM_WATSONX_SETUP.md`

#### 2.2 LLM Service Layer
- Create `backend/services/llm_service.py`:
  - Initialize langchain-ibm client
  - Configure Granite-13b-chat-v2 model
  - Implement streaming response handler
  - Add error handling and retries
  - Add token counting and rate limiting

#### 2.3 FastAPI Application
- Create `backend/main.py`:
  - Initialize FastAPI app
  - Configure CORS for frontend
  - Set up middleware (logging, error handling)
  - Add API versioning (`/api/v1/`)
  - Implement health check endpoint

#### 2.4 Pydantic Models
- Create `backend/models/requests.py`:
  - ChatRequest
  - SearchRequest
  - DocumentRequest
  - AnalyzeRequest
- Create `backend/models/responses.py`:
  - ChatResponse
  - SearchResponse
  - DocumentResponse
  - AnalyzeResponse
  - ErrorResponse

#### 2.5 API Routes Structure
- Create `backend/api/v1/__init__.py`
- Create placeholder route files:
  - `backend/api/v1/chat.py`
  - `backend/api/v1/search.py`
  - `backend/api/v1/documents.py`
  - `backend/api/v1/analyze.py`

#### 2.6 Testing
- Create `backend/tests/test_llm_service.py`
- Create `backend/tests/test_main.py`
- Test IBM watsonx.ai connection
- Test streaming responses
- Test error handling

### Deliverables
- ✅ IBM watsonx.ai credentials configured
- ✅ LLM service layer implemented
- ✅ FastAPI app with CORS and middleware
- ✅ Pydantic models for all requests/responses
- ✅ API route structure in place
- ✅ Unit tests passing

### Success Criteria
- IBM watsonx.ai connection successful
- Health check endpoint returns 200
- Streaming response works with test prompt
- All unit tests pass (>80% coverage)
- API documentation auto-generated at `/docs`

---

## 📋 Phase 3: Legal Corpus Data Collection & Vector Database Setup

**Goal**: Collect Indian legal data (BNS, BNSS, BSA, SC judgements) and set up ChromaDB

**Duration**: 12-15 hours

### Tasks

#### 3.1 Data Collection Strategy
- Create `docs/setup/DATA_COLLECTION_GUIDE.md`:
  - BNS (Bharatiya Nyaya Sanhita, 2023) sources
  - BNSS (Bharatiya Nagarik Suraksha Sanhita, 2023) sources
  - BSA (Bharatiya Sakshya Adhiniyam, 2023) sources
  - Supreme Court judgements sources (post-2023)

#### 3.2 Data Collection Scripts
- Create `scripts/collect_legal_data.py`:
  - Web scraping utilities (with rate limiting)
  - Data validation and formatting
  - Automated download from official sources
  - Save to `data/raw/` directories

#### 3.3 Data Processing
- Create `scripts/process_legal_data.py`:
  - Parse raw legal texts
  - Extract sections, titles, descriptions
  - Add metadata (section numbers, dates, citations)
  - Format for ChromaDB ingestion
  - Save to `data/processed/`

#### 3.4 ChromaDB Setup
- Create `backend/services/vector_db.py`:
  - Initialize ChromaDB client
  - Create 4 collections:
    - `bns_collection`
    - `bnss_collection`
    - `bsa_collection`
    - `judgements_collection`
  - Configure embedding model
  - Implement CRUD operations

#### 3.5 Data Import
- Create `scripts/import_data.py`:
  - Load processed data
  - Generate embeddings
  - Insert into ChromaDB collections
  - Verify data integrity
  - Create collection statistics

#### 3.6 Testing
- Create `backend/tests/test_vector_db.py`
- Test collection creation
- Test data insertion
- Test similarity search
- Test metadata filtering

### Deliverables
- ✅ Legal corpus data collected (BNS, BNSS, BSA, SC judgements)
- ✅ Data processed and formatted
- ✅ ChromaDB initialized with 4 collections
- ✅ Data imported successfully
- ✅ Vector search working
- ✅ Unit tests passing

### Success Criteria
- All 4 collections created in ChromaDB
- Minimum data requirements met:
  - BNS: 300+ sections
  - BNSS: 500+ provisions
  - BSA: 150+ sections
  - SC Judgements: 50+ cases
- Vector search returns relevant results
- All tests pass

---

## 📋 Phase 4: LangGraph Agent & MCP Tools Implementation

**Goal**: Implement LangGraph orchestrator and 4 MCP tools

**Duration**: 15-18 hours

### Tasks

#### 4.1 Agent State Definition
- Create `backend/agents/state.py`:
  - Define AgentState class
  - User query
  - Conversation history
  - Tool results
  - Current step
  - Final response

#### 4.2 LangGraph Orchestrator
- Create `backend/agents/orchestrator.py`:
  - Initialize LangGraph state machine
  - Define state transitions
  - Implement intent classification
  - Route to appropriate tools
  - Handle tool chaining
  - Manage conversation context

#### 4.3 MCP Tool 1: RAG Search
- Create `backend/tools/rag_search.py`:
  - Query ChromaDB collections
  - Implement semantic search
  - Filter by metadata (act, section, date)
  - Rank and return top results
  - Format citations properly

#### 4.4 MCP Tool 2: Draft Document
- Create `backend/tools/draft_document.py`:
  - Define document templates (bail application, petition, notice)
  - Use RAG search for relevant sections
  - Generate document with LLM
  - Format as DOCX
  - Add legal disclaimers

#### 4.5 MCP Tool 3: Analyze Document
- Create `backend/tools/analyze_doc.py`:
  - Extract text from PDF/DOCX
  - Identify key clauses
  - Analyze risks and obligations
  - Cross-reference with legal corpus
  - Generate summary report

#### 4.6 MCP Tool 4: Chat
- Create `backend/tools/chat.py`:
  - Context-aware Q&A
  - Use conversation history
  - Cite relevant legal provisions
  - Handle follow-up questions
  - Maintain legal accuracy

#### 4.7 Testing
- Create `backend/tests/test_orchestrator.py`
- Create `backend/tests/test_tools.py`
- Test each tool independently
- Test tool chaining
- Test error handling

### Deliverables
- ✅ LangGraph orchestrator implemented
- ✅ All 4 MCP tools working
- ✅ Intent classification accurate
- ✅ Tool chaining functional
- ✅ Unit tests passing

### Success Criteria
- Agent correctly routes queries to tools
- RAG search returns relevant legal sections
- Document generation produces valid DOCX
- Document analysis extracts key information
- Chat maintains context across turns
- All tests pass (>80% coverage)

---

## 📋 Phase 5: FastAPI Endpoints & Streaming

**Goal**: Implement REST API endpoints with streaming support

**Duration**: 10-12 hours

### Tasks

#### 5.1 Chat Endpoint
- Implement `backend/api/v1/chat.py`:
  - POST `/api/v1/chat`
  - Accept user query
  - Call LangGraph orchestrator
  - Stream LLM responses
  - Return conversation history

#### 5.2 Search Endpoint
- Implement `backend/api/v1/search.py`:
  - POST `/api/v1/search`
  - Accept search query and filters
  - Call rag_search tool
  - Return formatted results with citations

#### 5.3 Document Generation Endpoint
- Implement `backend/api/v1/documents.py`:
  - POST `/api/v1/documents/generate`
  - Accept document type and parameters
  - Call draft_document tool
  - Stream generation progress
  - Return DOCX file for download

#### 5.4 Document Analysis Endpoint
- Implement `backend/api/v1/analyze.py`:
  - POST `/api/v1/analyze`
  - Accept file upload (PDF/DOCX)
  - Validate file type and size
  - Call analyze_doc tool
  - Return analysis report

#### 5.5 Streaming Implementation
- Implement `StreamingResponse` for all LLM outputs
- Add progress indicators
- Handle connection errors gracefully
- Implement timeout handling

#### 5.6 Testing
- Create `backend/tests/test_api.py`
- Test all endpoints
- Test streaming responses
- Test file uploads
- Test error handling

### Deliverables
- ✅ All API endpoints implemented
- ✅ Streaming working for LLM responses
- ✅ File upload/download working
- ✅ Error handling robust
- ✅ API tests passing

### Success Criteria
- All endpoints return correct responses
- Streaming latency < 500ms for first token
- File uploads validated properly
- Error messages clear and helpful
- All tests pass

---

## 📋 Phase 6: Frontend Development

**Goal**: Build Next.js frontend with Tailwind CSS

**Duration**: 15-18 hours

### Tasks

#### 6.1 Layout & Navigation
- Create `frontend/components/Layout.tsx`
- Create `frontend/components/Navbar.tsx`
- Create `frontend/components/Sidebar.tsx`
- Implement responsive design
- Add legal disclaimer banner

#### 6.2 Chat Interface
- Create `frontend/components/chat/ChatInterface.tsx`
- Create `frontend/components/chat/MessageList.tsx`
- Create `frontend/components/chat/MessageInput.tsx`
- Implement streaming message display
- Add typing indicators

#### 6.3 Search Interface
- Create `frontend/components/search/SearchBar.tsx`
- Create `frontend/components/search/SearchFilters.tsx`
- Create `frontend/components/search/SearchResults.tsx`
- Display citations properly
- Add pagination

#### 6.4 Document Generation Interface
- Create `frontend/components/documents/DocumentForm.tsx`
- Create `frontend/components/documents/TemplateSelector.tsx`
- Create `frontend/components/documents/GenerationProgress.tsx`
- Implement file download
- Show generation status

#### 6.5 Document Analysis Interface
- Create `frontend/components/analyze/FileUpload.tsx`
- Create `frontend/components/analyze/AnalysisReport.tsx`
- Create `frontend/components/analyze/RiskHighlights.tsx`
- Display extracted clauses
- Show risk assessment

#### 6.6 API Integration
- Create `frontend/lib/api.ts`:
  - Axios client configuration
  - API endpoint functions
  - Error handling
  - Streaming response handling

#### 6.7 State Management
- Implement React Context or Zustand
- Manage conversation state
- Manage search state
- Manage document state

#### 6.8 Styling
- Configure Tailwind CSS
- Create custom theme
- Implement dark mode (optional)
- Ensure responsive design

#### 6.9 Testing
- Create component tests
- Test API integration
- Test user interactions
- Test responsive design

### Deliverables
- ✅ Complete UI for all features
- ✅ Responsive design working
- ✅ API integration functional
- ✅ Streaming display working
- ✅ Component tests passing

### Success Criteria
- All pages render correctly
- API calls successful
- Streaming messages display in real-time
- File upload/download works
- Mobile responsive
- All tests pass

---

## 📋 Phase 7: Integration & Testing

**Goal**: End-to-end testing of complete system

**Duration**: 10-12 hours

### Tasks

#### 7.1 Integration Tests
- Create `backend/tests/integration/test_flows.py`:
  - Test bail application flow
  - Test case law search flow
  - Test document analysis flow
  - Test multi-turn conversations

#### 7.2 Demo Flows Testing
- **Flow 1: Bail Application**
  - User: "Client arrested under BNS 103"
  - System: RAG search → draft_document → DOCX download
  - Verify: Correct sections cited, valid DOCX generated

- **Flow 2: Case Law Search**
  - User: "SC anticipatory bail rulings last 5 years"
  - System: RAG search → synthesized answer
  - Verify: Relevant judgements found, citations accurate

- **Flow 3: Document Analysis**
  - User: Upload rental agreement PDF
  - System: analyze_doc → risk summary
  - Verify: Key clauses extracted, risks identified

#### 7.3 Performance Testing
- Test response times against benchmarks:
  - RAG search: < 2 seconds
  - First token: < 500ms
  - Document generation: < 5 seconds
  - PDF analysis: < 3 seconds
- Load testing with multiple concurrent users

#### 7.4 Error Handling Testing
- Test network failures
- Test invalid inputs
- Test file upload errors
- Test LLM timeouts
- Test database errors

#### 7.5 Legal Accuracy Testing
- Verify BNS/BNSS/BSA citations
- Check legal terminology
- Validate document formats
- Review generated content

#### 7.6 Bug Fixes
- Fix issues found during testing
- Optimize slow operations
- Improve error messages
- Refine UI/UX

### Deliverables
- ✅ All demo flows working
- ✅ Integration tests passing
- ✅ Performance benchmarks met
- ✅ Error handling robust
- ✅ Legal accuracy verified

### Success Criteria
- All 3 demo flows complete successfully
- Performance targets met
- No critical bugs
- Legal citations accurate
- User experience smooth

---

## 📋 Phase 8: Security & Compliance

**Goal**: Implement security measures and legal compliance

**Duration**: 8-10 hours

### Tasks

#### 8.1 Input Validation
- Sanitize all user inputs
- Validate file uploads (type, size)
- Prevent SQL injection (N/A for ChromaDB)
- Prevent XSS attacks
- Add content scanning for uploads

#### 8.2 Authentication & Authorization
- Implement JWT authentication
- Add user registration/login
- Protect API endpoints
- Add role-based access control (optional)

#### 8.3 Rate Limiting
- Implement rate limiting on all endpoints
- Configure limits per user/IP
- Add rate limit headers
- Handle rate limit errors gracefully

#### 8.4 Data Privacy
- Ensure no PII in vector database
- Anonymize example data
- Implement data retention policies
- Add audit logging

#### 8.5 Legal Compliance
- Add prominent AI disclaimer in UI
- Create Terms of Service
- Create Privacy Policy
- Add consent checkboxes
- Log all document generations

#### 8.6 Security Testing
- Run security audit
- Test authentication
- Test rate limiting
- Test input validation
- Check for vulnerabilities

### Deliverables
- ✅ Input validation implemented
- ✅ Authentication working
- ✅ Rate limiting active
- ✅ Legal disclaimers in place
- ✅ Security audit passed

### Success Criteria
- No security vulnerabilities found
- Rate limiting prevents abuse
- Legal disclaimers visible
- Audit logs working
- Terms of Service accepted by users

---

## 📋 Phase 9: Performance Optimization

**Goal**: Optimize system performance and scalability

**Duration**: 8-10 hours

### Tasks

#### 9.1 Backend Optimization
- Profile slow endpoints
- Optimize database queries
- Implement caching (Redis optional)
- Optimize LLM prompts
- Reduce token usage

#### 9.2 Frontend Optimization
- Implement code splitting
- Optimize bundle size
- Add lazy loading
- Optimize images
- Implement service worker (optional)

#### 9.3 Database Optimization
- Optimize ChromaDB queries
- Implement query caching
- Optimize embedding generation
- Compress vector storage

#### 9.4 Monitoring Setup
- Add performance metrics
- Set up logging
- Create dashboards
- Configure alerts

#### 9.5 Load Testing
- Test with 50+ concurrent users
- Measure memory usage
- Test throughput
- Identify bottlenecks

#### 9.6 Optimization Implementation
- Fix identified bottlenecks
- Implement caching strategies
- Optimize critical paths
- Reduce latency

### Deliverables
- ✅ Performance benchmarks met
- ✅ System handles 50+ concurrent users
- ✅ Memory usage optimized
- ✅ Monitoring in place
- ✅ Load tests passing

### Success Criteria
- All performance targets met
- System stable under load
- Memory usage < 6GB total
- No performance regressions
- Monitoring dashboards working

---

## 📋 Phase 10: Documentation & Deployment

**Goal**: Complete documentation and prepare for deployment

**Duration**: 10-12 hours

### Tasks

#### 10.1 API Documentation
- Complete OpenAPI/Swagger docs
- Add request/response examples
- Document error codes
- Create API usage guide

#### 10.2 User Documentation
- Write user guide
- Create tutorial videos (optional)
- Write FAQ
- Document common workflows

#### 10.3 Developer Documentation
- Document architecture
- Create contribution guide
- Document deployment process
- Add troubleshooting guide

#### 10.4 Deployment Preparation
- Create production environment config
- Set up environment variables
- Configure production database
- Set up SSL certificates

#### 10.5 Backend Deployment
- Deploy FastAPI to production server
- Configure reverse proxy (Nginx)
- Set up process manager (systemd/supervisor)
- Configure logging

#### 10.6 Frontend Deployment
- Build Next.js for production
- Deploy to Vercel
- Configure custom domain
- Set up CDN

#### 10.7 Post-Deployment Testing
- Test production environment
- Verify all features working
- Test with real users
- Monitor for issues

#### 10.8 Launch Preparation
- Create launch checklist
- Prepare announcement
- Set up support channels
- Plan monitoring strategy

### Deliverables
- ✅ Complete documentation
- ✅ Backend deployed
- ✅ Frontend deployed to Vercel
- ✅ Production testing complete
- ✅ Launch ready

### Success Criteria
- All documentation complete
- Production environment stable
- All features working in production
- No critical issues
- Ready for users

---

## 📊 Overall Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Foundation | 6-8 hours | 6-8 hours |
| Phase 2: Backend Core | 8-10 hours | 14-18 hours |
| Phase 3: Data & Vector DB | 12-15 hours | 26-33 hours |
| Phase 4: Agent & Tools | 15-18 hours | 41-51 hours |
| Phase 5: API & Streaming | 10-12 hours | 51-63 hours |
| Phase 6: Frontend | 15-18 hours | 66-81 hours |
| Phase 7: Integration | 10-12 hours | 76-93 hours |
| Phase 8: Security | 8-10 hours | 84-103 hours |
| Phase 9: Optimization | 8-10 hours | 92-113 hours |
| Phase 10: Deployment | 10-12 hours | 102-125 hours |

**Total Estimated Time**: 102-125 hours (~3-4 weeks of full-time work)

---

## 🎯 Success Metrics

### Technical Metrics
- ✅ All unit tests passing (>80% coverage)
- ✅ All integration tests passing
- ✅ Performance benchmarks met
- ✅ Security audit passed
- ✅ Zero critical bugs

### Functional Metrics
- ✅ All 3 demo flows working
- ✅ RAG search accurate
- ✅ Document generation valid
- ✅ Document analysis accurate
- ✅ Chat maintains context

### User Experience Metrics
- ✅ Response time < 2 seconds
- ✅ Streaming latency < 500ms
- ✅ UI responsive on mobile
- ✅ Error messages clear
- ✅ Legal disclaimers visible

---

## 🚀 Next Steps

1. **Review this plan** - Ensure all phases align with your vision
2. **Approve Phase 1** - Get confirmation to start implementation
3. **Switch to Code mode** - Begin building Phase 1
4. **Iterate** - Complete each phase, test, then move to next
5. **Deploy** - Launch after Phase 10 complete

---

## 📝 Notes

- Each phase builds on the previous one
- Testing is mandatory after each phase
- No phase can be skipped
- Modifications allowed with approval
- GitHub Actions CI/CD added as needed per phase
- Data collection moved to Phase 3 (not Phase 1)

---

**Ready to begin?** Let's start with Phase 1 implementation!