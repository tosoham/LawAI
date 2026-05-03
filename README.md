# LawAI

**Multi-agent Indian Legal AI System for Lawyers, Courts, and Public**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)

---

## 🎯 Overview

LawAI is an advanced AI-powered legal assistant system designed specifically for the Indian legal framework. It leverages IBM watsonx.ai's Granite-13b-chat-v2 model, LangGraph for agent orchestration, and ChromaDB for vector search to provide intelligent legal assistance.

### Key Features

- 🔍 **RAG Search** - Query Indian legal corpus (BNS, BNSS, BSA, Supreme Court judgements)
- 📝 **Draft Document** - Generate legal drafts (bail applications, petitions, notices)
- 📄 **Analyze Document** - Extract and analyze uploaded legal documents (PDF/DOCX)
- 💬 **Chat** - Context-aware legal Q&A with accurate citations

### Legal Framework (2023+)

- **BNS** - Bharatiya Nyaya Sanhita, 2023 (replaces IPC)
- **BNSS** - Bharatiya Nagarik Suraksha Sanhita, 2023 (replaces CrPC)
- **BSA** - Bharatiya Sakshya Adhiniyam, 2023 (replaces Evidence Act)
- **SC Judgements** - Supreme Court rulings under new legal framework

---

## 🏗️ Architecture

### Tech Stack

- **LLM**: IBM watsonx.ai - Granite-13b-chat-v2
- **Agent Framework**: LangGraph for complex workflows
- **Vector DB**: ChromaDB (local deployment)
- **Backend**: FastAPI with async/await and streaming
- **Frontend**: Next.js 14 with TypeScript and Tailwind CSS

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                    │
│  Chat Interface | Search | Document Gen | Doc Analysis  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Backend (FastAPI)                       │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │         LangGraph Agent Orchestrator            │    │
│  │  (Intent Classification & Tool Routing)         │    │
│  └────────────────────────────────────────────────┘    │
│                            │                             │
│         ┌──────────────────┼──────────────────┐        │
│         ▼                  ▼                  ▼         │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐     │
│  │   RAG    │      │  Draft   │      │ Analyze  │     │
│  │  Search  │      │ Document │      │   Doc    │     │
│  └──────────┘      └──────────┘      └──────────┘     │
│         │                  │                  │         │
│         └──────────────────┼──────────────────┘        │
│                            ▼                             │
│  ┌────────────────────────────────────────────────┐    │
│  │         IBM watsonx.ai (Granite-13b)           │    │
│  └────────────────────────────────────────────────┘    │
│                            │                             │
│                            ▼                             │
│  ┌────────────────────────────────────────────────┐    │
│  │  ChromaDB (BNS, BNSS, BSA, SC Judgements)     │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- IBM watsonx.ai account and credentials

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your IBM watsonx.ai credentials

# Run development server
uvicorn main:app --reload
```

Backend will be available at `http://localhost:8000`
API documentation at `http://localhost:8000/docs`

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Copy environment file
cp .env.local.example .env.local

# Run development server
npm run dev
```

Frontend will be available at `http://localhost:3000`

---

## 📚 Documentation

- [Complete Implementation Plan](docs/COMPLETE_IMPLEMENTATION_PLAN.md)
- [Agent Guidelines](AGENTS.md)
- [Development Rules](RULES.md)
- [IBM watsonx.ai Setup Guide](docs/setup/IBM_WATSONX_SETUP.md) *(Coming in Phase 2)*
- [Data Collection Guide](docs/setup/DATA_COLLECTION_GUIDE.md) *(Coming in Phase 3)*

---

## 🧪 Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov-report=html

# Run specific test file
pytest tests/test_main.py -v
```

### Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run in watch mode
npm run test:watch
```

---

## 🎯 Demo Flows

### 1. Bail Application Generation

```
User: "Client arrested under BNS 103"
System: 
  → RAG Search (finds relevant BNSS sections 479/482)
  → Draft Document (generates bail application)
  → Returns downloadable .docx file
```

### 2. Case Law Search

```
User: "SC anticipatory bail rulings last 5 years"
System:
  → RAG Search (queries SC judgements collection)
  → Synthesizes answer with accurate citations
  → Returns formatted response
```

### 3. Document Analysis

```
User: Uploads rental agreement PDF
System:
  → Analyze Document (extracts text and clauses)
  → Identifies risks (termination clauses, indemnity)
  → Returns comprehensive risk summary
```

---

## 📋 Project Status

**Current Phase**: Phase 1 - Project Foundation & Setup ✅

See [COMPLETE_IMPLEMENTATION_PLAN.md](docs/COMPLETE_IMPLEMENTATION_PLAN.md) for detailed roadmap.

---

## 🔒 Security & Compliance

- ✅ No PII stored in vector database
- ✅ Input validation and sanitization
- ✅ Rate limiting on all endpoints
- ✅ JWT authentication
- ✅ Legal disclaimers for AI-generated content
- ✅ Audit logging for document generation

---

## 🤝 Contributing

This project follows strict development guidelines. Please read:

1. [RULES.md](RULES.md) - Master rulebook for development
2. [AGENTS.md](AGENTS.md) - Agent-specific guidance
3. [CONTRIBUTING.md](CONTRIBUTING.md) *(Coming soon)*

### Development Workflow

1. Plan first, build later
2. Create feature branch (`feature/your-feature`)
3. Write tests alongside code
4. Ensure all tests pass
5. Submit pull request
6. Code review required

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Legal Disclaimer

**IMPORTANT**: LawAI is an AI-powered legal assistance tool and does NOT replace professional legal advice. All generated content should be reviewed by qualified legal professionals before use. The system is designed to assist, not replace, lawyers and legal experts.

---

## 👥 Authors

- **tosoham** - [todrsoham@gmail.com](mailto:todrsoham@gmail.com)

---

## 🙏 Acknowledgments

- IBM watsonx.ai for Granite-13b-chat-v2 model
- LangChain and LangGraph for agent framework
- ChromaDB for vector database
- FastAPI and Next.js communities

---

**Built with ❤️ for the Indian Legal Community**