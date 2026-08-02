# Contributing to LawAI

Thank you for your interest in contributing to LawAI! This document provides guidelines for contributing to the project.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Git Workflow](#git-workflow)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)

---

## 🤝 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Prioritize legal accuracy and security
- Follow the project's rules and guidelines

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- Git
- An AIML API key (https://aimlapi.com) — required only for features that call the LLM;
  the app starts and its tests pass without one

### Initial Setup

1. **Fork the repository**
   ```bash
   git clone https://github.com/tosoham/LawAI.git
   cd LawAI
   ```

2. **Set up backend**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   # Configure .env with your credentials
   ```

3. **Set up frontend**
   ```bash
   cd frontend
   npm install
   cp .env.local.example .env.local
   ```

4. **Verify setup**
   ```bash
   python scripts/verify_setup.py
   ```

---

## 🔄 Development Workflow

### Core Principles

1. **Plan First, Build Later** - Always discuss and plan before coding
2. **Iterative Development** - Complete one feature at a time
3. **Test-Driven** - Write tests alongside features
4. **Documentation-Driven** - Document before implementing

### Workflow Steps

1. **Create an issue** - Describe the feature/bug
2. **Get approval** - Wait for maintainer approval
3. **Create branch** - Follow naming conventions
4. **Implement** - Write code with tests
5. **Test** - Ensure all tests pass
6. **Commit** - Use conventional commits
7. **Push** - Push to your fork
8. **Pull Request** - Submit for review

---

## 🌿 Git Workflow

### Branch Naming

Use the following prefixes:

- `feature/` - New features (e.g., `feature/rag-search`)
- `bugfix/` - Bug fixes (e.g., `bugfix/streaming-error`)
- `docs/` - Documentation (e.g., `docs/api-guide`)
- `test/` - Test additions (e.g., `test/integration-tests`)
- `refactor/` - Code refactoring (e.g., `refactor/agent-state`)

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style (formatting)
- `refactor` - Code refactoring
- `test` - Adding tests
- `chore` - Maintenance tasks

**Examples:**

```bash
feat(rag): add BNS section search functionality

Implemented vector search for BNS sections with metadata filtering.
Includes unit tests and integration tests.

Closes #123
```

```bash
fix(streaming): handle connection drops gracefully

Added error handling for streaming responses when client disconnects.

Fixes #456
```

### Branching Strategy

```bash
# Create feature branch from main
git checkout main
git pull origin main
git checkout -b feature/your-feature

# Make changes and commit
git add .
git commit -m "feat(scope): description"

# Push to your fork
git push origin feature/your-feature

# Create pull request on GitHub
```

---

## 💻 Coding Standards

### Python (Backend)

- **PEP 8 Compliance** - Follow Python style guide
- **Type Hints** - Use type annotations
- **Docstrings** - Document all functions/classes
- **Error Handling** - Use specific exception types
- **Async/Await** - Use for I/O operations

**Example:**

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
        collection: ChromaDB collection name
        limit: Maximum results to return
        
    Returns:
        List of matching documents with metadata
        
    Raises:
        ValueError: If collection name is invalid
        ChromaDBError: If database query fails
    """
    # Implementation
```

### TypeScript (Frontend)

- **Strict Mode** - Enable in tsconfig.json
- **Proper Typing** - Define interfaces
- **ESLint Compliance** - Follow Next.js conventions
- **Component Documentation** - Document props

**Example:**

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

### Code Quality Tools

**Backend:**
```bash
# Linting
ruff check backend/

# Type checking
mypy backend/

# Formatting
black backend/
```

**Frontend:**
```bash
# Linting
npm run lint

# Type checking
npm run type-check

# Formatting
npm run format
```

---

## 🧪 Testing Requirements

### Test Coverage

- **Minimum 80% coverage** for all code
- **100% coverage** for security and legal accuracy code
- Write tests alongside features

### Backend Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov-report=html

# Run specific test
pytest tests/test_main.py -v
```

### Frontend Testing

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run in watch mode
npm run test:watch
```

### Test Structure

- **Unit Tests** - Test individual functions/components
- **Integration Tests** - Test complete workflows
- **Mock External Services** - Mock LLM and database calls

---

## 🔍 Pull Request Process

### Before Submitting

1. ✅ All tests pass
2. ✅ Code follows style guidelines
3. ✅ Documentation updated
4. ✅ No merge conflicts
5. ✅ Commit messages follow conventions

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] All tests passing

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No breaking changes
- [ ] Legal accuracy verified (if applicable)

## Related Issues
Closes #123
```

### Review Process

1. **Automated Checks** - CI/CD runs tests
2. **Code Review** - At least one approval required
3. **Legal Review** - For legal accuracy changes
4. **Merge** - Squash and merge to main

---

## 🚫 Prohibited Actions

### Development
- ❌ Starting implementation without approved plan
- ❌ Skipping tests
- ❌ Ignoring code review feedback
- ❌ Deploying without passing tests

### Security
- ❌ Storing PII in vector database
- ❌ Committing secrets or API keys
- ❌ Skipping input validation
- ❌ Disabling security features

### Legal
- ❌ Skipping legal disclaimers
- ❌ Using unofficial legal sources
- ❌ Providing legal advice (system assists only)
- ❌ Ignoring legal accuracy

---

## 📚 Additional Resources

- [RULES.md](RULES.md) - Master rulebook
- [AGENTS.md](AGENTS.md) - Agent-specific guidance
- [Complete Implementation Plan](docs/COMPLETE_IMPLEMENTATION_PLAN.md)
- [API Documentation](http://localhost:8000/docs) (when running)

---

## 💬 Questions?

- Create an issue for questions
- Tag maintainers for urgent matters
- Check existing issues first

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to LawAI! 🙏**