# Agent Instructions

This file contains instructions for AI agents working on this codebase.

## User Preferences

1. **Always ask questions** when uncertain - user prefers this over guessing
2. **Small incremental changes** - prefer many small commits over large ones
3. **Test behavior changes** - write tests for new behaviors, not just code changes
4. **Logger pattern** - use semantic methods (`logger.api_request()`, `logger.error()`, etc.)
5. **Debug flag controls output** - no `if self.debug:` checks needed in calling code

## Architecture

### Main Components

- `cli.py` - Click CLI with `generate`, `test-connection`, `list`, `status`, `serve`, `auth`, `profile`, `knowledge` commands
- `config.py` - Configuration dataclasses with XDG-compliant loading and env var overrides
- `db.py` - SQLModel engine init, session factory, `init_db()`, `get_session()` dependency
- `models.py` - Pydantic models for config and data structures (Resume, Job, Question, CoverLetter)
- `models/db_models.py` - SQLModel tables (User, UserProfile) and Pydantic schemas (UserCreate, UserRead, TokenResponse, ProfileCreate, ProfileRead)
- `models/knowledge.py` - Pydantic models for knowledge pipeline (ExtractedFact, FactExtractionResult, KnowledgeQuery, KnowledgeSearchResult)
- `services/ollama.py` - LLM service backing Ollama (delegates to LLMService internally)
- `services/llm_service.py` - Unified LLM interface via LangChain (Ollama + OpenCode Go providers)
- `services/auth.py` - Password hashing (bcrypt), JWT token management, `get_current_user()` dependency
- `services/knowledge.py` - ChromaDB vector storage and retrieval (per-user collections)
- `services/fact_extractor.py` - LLM-based fact extraction from Q&A pairs
- `services/job_extractor.py` - Extract job data from URLs using Ollama web_fetch
- `services/reactive_resume.py` - API client for Reactive Resume
- `services/cache.py` - Cache manager for job data, Q&A, resume data
- `prompts/questions.py` - Question generation prompt (f-string)
- `prompts/resume.py` - Resume generation prompt (f-string)
- `prompts/cover_letter.py` - Cover letter prompt (f-string)
- `prompts/fact_extraction.py` - Fact extraction prompt (f-string)
- `prompts/templates.py` - LangChain ChatPromptTemplate versions of all prompts
- `webapp/app.py` - FastAPI routes + WebSocket + lifespan (includes auth routes)
- `webapp/auth_routes.py` - FastAPI auth endpoints: signup, login, me
- `webapp/background_tasks.py` - Async process_job pipeline
- `webapp/state.py` - Global StateManager (single job at a time)
- `log.py` - Centralized logger with semantic methods

### Data Flow

1. **Job Extraction** (`JobExtractor.extract_from_url()`)
   - Uses Ollama `web_fetch` to get job posting
   - Extracts title, company, description, requirements
   - Saved to `job.json`

2. **Question Generation** (`LLMService.generate_questions()` or `OllamaService.generate_questions()`)
   - Generates 3-5 clarifying questions based on job + profile
   - Knowledge-informed: injects relevant facts from past sessions (Phase 4+)
   - Saved to `questions.json`

3. **Interactive Q&A** (`ask_questions_interactive()`)
   - Prompts user via Click
   - Saved to `answers.json`

4. **Fact Extraction** (`FactExtractor.extract_facts_from_answers()`)
   - Distills Q&A into atomic facts (e.g., "5 years Python experience")
   - Stores facts in ChromaDB per-user collection via `KnowledgeService.store_facts()`
   - Auto-extract by default, optional review mode with `--review-facts`

5. **Resume Generation** (`LLMService.generate_resume()` or `OllamaService.generate_resume()`)
   - Uses job + profile + Q&A + knowledge context to generate tailored resume
   - Enforces Reactive Resume JSON schema
   - Saved to `resume.json`

6. **Cover Letter Generation** (`LLMService.generate_cover_letter()` or `OllamaService.generate_cover_letter()`)
   - Uses job + profile + Q&A + knowledge context to generate tailored cover letter
   - Returns recipient and content
   - Saved to `cover_letter.json`

7. **Import to Reactive Resume**
   - `create_resume()` - POST to create resume/cover letter with title + company tag
   - `update_resume()` - PUT to add resume/cover letter data
   - Cache reactive_resume ID and reactive_cover_letter ID for deduplication

### Auth Flow

**Disabled mode (default):** When `FAST_APP_JWT_SECRET` is not set and no users exist in DB, auth is disabled. All endpoints work without tokens. CLI works as-is.

**Enabled mode:** When `FAST_APP_JWT_SECRET` is set OR users exist in DB:
- Signup: `POST /api/auth/signup` → `hash_password(password)` → store in User table → `create_access_token(user_id)` → return JWT
- Login: `POST /api/auth/login` → `verify_password(password, hash)` → `create_access_token(user_id)` → return JWT + httpOnly cookie
- Authenticated request: `Depends(get_current_user)` → `decode_access_token(token)` → User object or 401

### LLM Provider Abstraction

`LLMService` wraps LangChain's `BaseChatModel`. The provider is selected via configuration:

- `config.llm.provider == "ollama"` → `ChatOllama` (local, free)
- `config.llm.provider == "opencode-go"` → `ChatOpenAI` with custom `base_url` (cloud, subscription)

Provider switching priority: CLI `--provider` flag > `FAST_APP_LLM_PROVIDER` env var > `config.json`

`OllamaService` is preserved as a thin wrapper that delegates to `LLMService` internally. All existing code continues to work unchanged.

### Knowledge Pipeline

```
Q&A responses → FactExtractor → ExtractedFact[] → KnowledgeService.store_facts() → ChromaDB (per-user collection)
Job URL → KnowledgeService.query_facts() → KnowledgeSearchResult[] → inject into question generation prompt
```

Per-user collections: `user_{id}_knowledge`. Facts include metadata (category, confidence, source, job_url). Graceful degradation: if ChromaDB is unavailable, system works identically without memory-augmented prompts.

### Caching

All files cached under `output/<company>/<title>-<hash>/`:
- `job.json` - Extracted job data
- `questions.json` - Generated questions
- `answers.json` - User answers
- `resume.json` - Generated resume data
- `cover_letter.json` - Generated cover letter data
- `reactive_resume.json` - Reactive Resume ID and metadata
- `reactive_cover_letter.json` - Reactive Cover Letter ID and metadata

**Deduplication**:
- Uses job URL hash to find existing cache
- `--force` regenerates all files
- `--overwrite-resume` replaces existing Reactive Resume

### Configuration

New config dataclasses (in `config.py`):

- `DatabaseConfig` - SQLite path, JWT settings (`FAST_APP_DB_PATH`, `FAST_APP_JWT_SECRET`, etc.)
- `LLMConfig` - Provider, model, temperature, base_url, api_key (`FAST_APP_LLM_PROVIDER`, etc.)
- `ChromaConfig` - Path, embedding model, client type (`FAST_APP_CHROMA_PATH`, etc.)

### Dependency Groups

```bash
pip install -e "."                    # Core only (no auth, LLM, knowledge deps)
pip install -e ".[llm]"               # LangChain, ChatOllama, ChatOpenAI
pip install -e ".[auth]"              # SQLModel, python-jose, passlib, bcrypt
pip install -e ".[knowledge]"         # ChromaDB, Chonkie
pip install -e ".[llm,auth,knowledge]" # Everything
pip install -e ".[dev]"               # pytest, mypy, ruff
```

## Reactive Resume API Details

### Endpoints

```
Base: /api/openapi/

GET    /resumes              - List all resumes
POST   /resumes              - Create resume
GET    /resumes/{id}         - Get by ID
PUT    /resumes/{id}         - Update data (send {data: {...}})
DELETE /resumes/{id}         - Delete
```

### Create Resume

```python
# Required fields: name, slug, tags (tags must be array)
payload = {
    "name": "Job Title at Company Resume",
    "slug": "job-title-at-company-resume",
    "tags": ["Company"]
}
# Returns: resume ID (string)
```

### Update Resume

```python
# Send full resume data via PUT (wrap in "data" object)
response = requests.put(
    f"/api/openapi/resumes/{resume_id}",
    json={"data": resume_data}  # Full Reactive Resume schema
)
```

### Resume Schema Structure

```json
{
  "basics": {
    "name": "John Doe",
    "headline": "Software Engineer",
    "photo": {},
    "location": "San Francisco, CA",
    "phone": "555-1234",
    "email": "john@example.com"
  },
  "summary": {
    "content": "Experienced software engineer..."
  },
  "metadata": {
    "notes": "Job URL\n\nJob Description"
  },
  "sections": {
    "experience": {
      "id": "experience",
      "name": "Experience",
      "type": "work",
      "items": [...]
    },
    "education": {...},
    "skills": {...},
    "projects": {...}
  }
}
```

## Common Issues

### Resume creation fails with 400

- Check that `tags` field is an array (even if empty)
- Check that `slug` doesn't contain special characters

### Resume not found after creation

- API returns resume ID directly as string, not wrapped in object
- Verify ID with `get_resume(resume_id)` before updating

### Duplicate resumes

- Use `find_resume_by_title()` to check for existing
- Use `--overwrite-resume` flag to replace existing

### ChromaDB not installed warning

- Knowledge features silently degrade without ChromaDB
- Install with `pip install -e ".[knowledge]"` for full functionality
- Use `--no-knowledge` flag to suppress the warning

### Auth disabled by default

- When `FAST_APP_JWT_SECRET` is not set and no users exist, auth is disabled
- Enable auth: set `FAST_APP_JWT_SECRET` env var and run `fast-app auth signup`
- See `docs/guide/auth-setup.md` for details

## Testing

Run tests with:
```bash
pytest -v
```

When adding tests:
1. Test behavior, not implementation
2. Use pytest fixtures for setup
3. Mock external APIs (Ollama, Reactive Resume, ChromaDB)
4. Auth tests should use `SECRET_KEY` fixture that resets after each test
5. LLM service tests should mock LangChain's `BaseChatModel`

## Development

### CLI-First Architecture

All new services must be CLI-accessible first:

1. Implement service method (e.g., `AuthService.signup()`)
2. Add CLI command (e.g., `fast-app auth signup`)
3. Add webapp route (e.g., `POST /api/auth/signup`)

Webapp routes should be thin wrappers — no business logic in route handlers.

### Adding New Features

1. Check existing patterns in similar files
2. Use logger methods for output
3. Cache results when appropriate
4. Add `--force` flag to bypass cache
5. Update both README.md and AGENTS.md
6. Write ADR in `docs/adr/` for significant decisions

### Debugging

Use `--debug` flag to see:
- LLM prompts and responses
- API requests/responses
- Cache operations

### Code Style

- Type hints on function parameters and returns
- Docstrings for public functions and modules
- No inline comments unless complex or security-related
- Prefer explicit over implicit
- Optional dependencies must gracefully degrade (ImportError handling)

## Documentation

- `docs/adr/` - Architecture Decision Records (001-007)
- `docs/guide/auth-setup.md` - Auth fundamentals and setup guide
- `docs/guide/profiles.md` - Profile management (CLI + webapp)
- `docs/guide/knowledge.md` - Knowledge system guide
- `docs/guide/llm-providers.md` - LLM provider switching guide
- `.sisyphus/plans/major-features-v2.md` - Implementation plan