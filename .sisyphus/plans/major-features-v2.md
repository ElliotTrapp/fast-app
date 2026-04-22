# Fast-App Major Features Implementation Plan v2

> Updated with: LangChain for LLM abstraction, OpenCode Go support, Chonkie for
> chunking, expanded auth documentation, ADR-based decision records.

## Architecture Overview

**Current state**: Single-user CLI + webapp, JSON file caching, no auth, no
database, no vector memory. Direct Ollama SDK calls, Pydantic for structured
output, Click for CLI, FastAPI for webapp.

**Target state**: Multi-user auth, persistent profiles, ChromaDB vector memory,
LangChain LLM abstraction with provider switching (Ollama ↔ OpenCode Go),
knowledge-informed question generation — CLI-first, backward compatible.

---

## Key Architecture Decisions (ADRs)

### ADR-001: LangChain for LLM Abstraction

**Context**: We need to support multiple LLM providers (Ollama for local,
OpenCode Go for cloud). Currently using direct Ollama SDK calls.

**Decision**: Use LangChain (`langchain-core`, `langchain-openai`,
`langchain-ollama`, `langchain-community`) for LLM calls and ChromaDB
integration. Keep SQLModel, Click, FastAPI, and existing retry logic.

**Rationale**:
- 20% learning goal: LangChain teaches composable chains, prompt templates,
  structured output, RAG, and provider abstraction
- Provider switching via one config change (Ollama ↔ OpenCode Go)
- ChromaDB integration through `langchain-community` is well-tested
- Transferable skills across thousands of LangChain projects
- Our pipeline IS linear → LangChain (not LangGraph) is the right choice

**Consequences**:
- Adds ~20 dependencies (langchain-core, langchain-openai, langchain-ollama,
  langchain-community, langchain-chroma, + their transitive deps)
- Requires refactoring existing `services/ollama.py` to use LangChain chains
- Prompt templates move from f-strings to LangChain `ChatPromptTemplate`
- Structured output moves from `format=model_json_schema()` to
  `PydanticOutputParser` or LangChain's `with_structured_output()`

### ADR-002: ChromaDB for Vector Memory

**Context**: Need persistent vector memory for semantic search on learned facts.

**Decision**: ChromaDB with `PersistentClient` for dev, `HttpClient` for prod.

**Rationale**: Simplest API, built-in `OllamaEmbeddingFunction`, zero-config
local dev, same API for production, Python-native.

### ADR-003: SQLModel + SQLite for Auth/Profiles

**Context**: Need user accounts, profiles, and session data.

**Decision**: SQLModel (Pydantic + SQLAlchemy) with SQLite (aiosqlite for async).

**Rationale**: Same author as FastAPI, models = Pydantic schemas + DB tables,
SQLite for dev (zero infra), PostgreSQL later via connection string change.

### ADR-004: JWT Auth with bcrypt Password Hashing

**Context**: Need user authentication for multi-user support.

**Decision**: JWT tokens (python-jose) for stateless auth, bcrypt (passlib) for
password hashing, httpOnly cookies for webapp, Bearer tokens for CLI.

**Rationale**: JWT is standard for APIs, stateless (no session store needed),
bcrypt is purpose-built for passwords (slow by design), httpOnly cookies
prevent XSS token theft.

### ADR-005: Chonkie for Job Description Chunking

**Context**: Need to chunk long job descriptions before embedding. Q&A pairs and
facts are already atomic and don't need chunking.

**Decision**: Use Chonkie's `SemanticChunker` for job descriptions only. Embed
Q&A pairs and extracted facts directly.

**Rationale**: Chonkie provides semantic boundary detection for long text.
Data that's already atomic (facts, Q&A pairs) should be embedded directly.
Job descriptions (often 500+ words) benefit from semantic chunking.

### ADR-006: LLM Provider Abstraction via LangChain

**Context**: Need to support Ollama (local) and OpenCode Go (cloud) with
seamless switching.

**Decision**: Create an `LLMService` that wraps LangChain's `BaseChatModel`,
instantiating `ChatOllama` or `ChatOpenAI` based on configuration.

**Rationale**: LangChain's `BaseChatModel` provides a unified interface. Swap
providers with one config change. `ChatOpenAI` with custom `base_url` works
with OpenCode Go's OpenAI-compatible API.

### ADR-007: Knowledge Extraction via LLM Distillation

**Context**: Raw Q&A answers are verbose; we need atomic facts for embedding.

**Decision**: Use LLM (via LangChain) to distill Q&A pairs into discrete facts
before embedding. Auto-extract by default, optional review mode.

**Rationale**: "I have 5 years of Python experience" is a fact. "Well, I've
been coding for about 5 years, mostly in Python" is a raw answer. The vector
DB should store the fact, not the raw answer.

### ADR-008: CLI-First Architecture

**Context**: All features must work in CLI first, then be exposed via webapp.

**Decision**: All new services (KnowledgeService, ProfileService, LLMService)
are CLI-accessible. The webapp calls the same services, not separate APIs.

**Rationale**: The CLI is the primary interface. The webapp is a thin wrapper.
This ensures feature parity and simplifies testing.

---

## Technology Stack Summary

| Component | Library | Why |
|-----------|----------|-----|
| **LLM calls** | LangChain (`langchain-core`, `langchain-openai`, `langchain-ollama`) | Provider abstraction, composable chains, prompt templates |
| **Vector DB** | ChromaDB (`chromadb`) | Embedded mode, Ollama embeddings, simple API |
| **Embeddings** | LangChain + Ollama (`langchain-community`) | `OllamaEmbeddings` for local, `OpenAIEmbeddings` for cloud |
| **Chunking** | Chonkie (`chonkie[semantic]`) | SemanticChunker for job descriptions |
| **Auth** | python-jose + passlib[bcrypt] | JWT tokens + bcrypt password hashing |
| **ORM** | SQLModel | Pydantic + SQLAlchemy, FastAPI-native |
| **DB** | SQLite (aiosqlite) for dev | Zero infra, file-based, XDG-compliant path |
| **CLI** | Click (existing) | Already in use, no change needed |
| **Web** | FastAPI (existing) | Already in use, add auth routes |

### New Dependencies (pyproject.toml)

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "mypy>=1.0",
    "ruff>=0.1.0",
]
llm = [
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",
    "langchain-ollama>=0.3.0",
    "langchain-community>=0.3.0",
    "langchain-chroma>=0.2.0",
]
auth = [
    "sqlmodel>=0.0.22",
    "aiosqlite>=0.20.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "bcrypt>=4.0.0",
]
knowledge = [
    "chromadb>=0.5.0",
    "chonkie[semantic]>=1.0.0",
]
```

Using optional dependency groups so users can install only what they need:
`pip install -e ".[llm,auth,knowledge]"` for full install.

---

## Phase 1: LLM Abstraction Layer + Auth Foundation

**Goal**: Replace direct Ollama SDK calls with LangChain chains. Add multi-user
auth. Existing flow still works without auth when no users exist.

**Complexity**: High | **Estimated effort**: 5-7 days

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/db.py` | SQLModel engine init, session factory, `get_session()` dependency, `init_db()` startup |
| `src/fast_app/models/db_models.py` | `User`, `UserProfile` SQLModel tables + Pydantic schemas |
| `src/fast_app/services/llm_service.py` | `LLMService` class wrapping LangChain: `generate()`, `generate_with_schema()`, `generate_questions()`, `generate_resume()`, `generate_cover_letter()`, `extract_facts()`. Provider config from `Config` |
| `src/fast_app/services/auth.py` | `hash_password()`, `verify_password()`, `create_access_token()`, `decode_access_token()`, `get_current_user()` dependency |
| `src/fast_app/services/knowledge.py` | `KnowledgeService` class: `store_facts()`, `query_facts()`, `delete_facts()`, `list_facts()`. Wraps ChromaDB with per-user collections |
| `src/fast_app/services/fact_extractor.py` | `FactExtractor` class using LangChain chain to distill facts from Q&A |
| `src/fast_app/prompts/fact_extraction.py` | Prompt template for fact extraction |
| `src/fast_app/prompts/templates.py` | LangChain `ChatPromptTemplate` versions of existing prompts (resume, questions, cover letter, fact extraction) |
| `src/fast_app/webapp/auth_routes.py` | FastAPI router: signup, login, me, password reset |
| `src/fast_app/docs/adr/` | Directory for Architecture Decision Records |
| `tests/test_llm_service.py` | Tests for LLM provider abstraction |
| `tests/test_auth.py` | Auth unit and integration tests |
| `tests/test_knowledge.py` | ChromaDB integration tests |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject.toml` | Add dependency groups: `llm`, `auth`, `knowledge` |
| `src/fast_app/config.py` | Add `DatabaseConfig` (path, jwt_secret, jwt_algorithm, jwt_expire_minutes), `LLMConfig` (provider: ollama/opencode-go, model, temperature, base_url, api_key), `ChromaConfig` (path, embedding_model). Add env var overrides |
| `src/fast_app/services/ollama.py` | Refactor to use `LLMService` internally. Keep `with_retry` decorator. `OllamaService` becomes thin wrapper that delegates to `LLMService` |
| `src/fast_app/cli.py` | Add `--provider` flag (ollama/opencode-go). Add `--token` flag for auth. Add `profile` command group. Add `knowledge` command group |
| `src/fast_app/webapp/app.py` | Include auth routes, profile routes. Add `init_db()` in lifespan. Add `Depends(get_current_user)` on protected endpoints (optional when auth disabled) |
| `src/fast_app/webapp/background_tasks.py` | Accept `profile_id` and `user_id` params. Call `KnowledgeService.store_facts()` after Q&A |
| `src/fast_app/utils/profile.py` | Add `load_profile_from_db()` function. Modify `load_profile()` to try DB first, file fallback |
| `src/fast_app/__init__.py` | Version bump |

### LLM Provider Abstraction — Detailed Design

```python
# src/fast_app/services/llm_service.py

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

class LLMService:
    """Unified LLM interface supporting multiple providers."""

    def __init__(self, config: Config):
        self.config = config
        self._llm = self._create_llm()
        self._embedding_model = self._create_embedding_model()

    def _create_llm(self) -> BaseChatModel:
        """Create LLM instance based on provider config."""
        provider = self.config.llm.provider

        if provider == "ollama":
            return ChatOllama(
                model=self.config.llm.model,
                temperature=self.config.llm.temperature,
                base_url=self.config.ollama.endpoint,
            )
        elif provider == "opencode-go":
            return ChatOpenAI(
                model=self.config.llm.model,
                temperature=self.config.llm.temperature,
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _create_embedding_model(self):
        """Create embedding model for vector operations."""
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(
            model=self.config.chroma.embedding_model,
            base_url=self.config.ollama.endpoint,
        )

    def generate(self, prompt: str, **kwargs) -> str:
        """Simple text generation."""
        from langchain_core.messages import HumanMessage
        response = self._llm.invoke([HumanMessage(content=prompt)], **kwargs)
        return response.content

    def generate_with_schema(self, prompt: str, schema: type, **kwargs):
        """Generate structured output matching a Pydantic schema."""
        structured_llm = self._llm.with_structured_output(schema)
        return structured_llm.invoke(prompt, **kwargs)

    def generate_questions(
        self, job_data: dict, profile_data: dict, **kwargs
    ) -> list[str]:
        """Generate interview questions using LangChain chain."""
        from ..prompts.templates import get_questions_template
        chain = get_questions_template() | self._llm
        result = chain.invoke({
            "job_data": job_data,
            "profile_data": profile_data,
        })
        # Parse result into QuestionContent
        ...

    def generate_resume(self, job_data, profile_data, questions, answers, **kwargs):
        """Generate resume content using LangChain chain."""
        from ..prompts.templates import get_resume_template
        chain = get_resume_template() | self._llm | PydanticOutputParser(pydantic_object=ResumeContent)
        ...

    def generate_cover_letter(self, job_data, profile_data, questions, answers, **kwargs):
        """Generate cover letter using LangChain chain."""
        from ..prompts.templates import get_cover_letter_template
        ...

    def extract_facts(self, qa_pairs, profile_data=None, job_data=None, **kwargs):
        """Extract atomic facts from Q&A pairs using LLM."""
        from ..prompts.templates import get_fact_extraction_template
        chain = get_fact_extraction_template() | self._llm | PydanticOutputParser(pydantic_object=FactExtractionResult)
        ...
```

### Auth Flow

```
Signup: POST /api/auth/signup {email, password} → {access_token, token_type}
Login:  POST /api/auth/login  {email, password} → {access_token, token_type}
Me:    GET  /api/auth/me     Authorization: Bearer <token> → {user}
```

**Backward compatibility**: When `FAST_APP_JWT_SECRET` is not set and no users
exist in DB, auth is **disabled** — all endpoints work as today.

### Config Changes — `src/fast_app/config.py`

```python
@dataclass
class DatabaseConfig:
    path: str = ""  # Empty = auto-detect (~/.fast-app/fast_app.db)
    jwt_secret: str = ""  # Empty = auto-generate on first run
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

@dataclass
class LLMConfig:
    provider: str = "ollama"  # "ollama" or "opencode-go"
    model: str = "llama3.2"
    temperature: float = 0.3
    base_url: str = ""  # OpenCode Go: "https://opencode.ai/zen/go/v1"
    api_key: str = ""  # OpenCode Go API key

@dataclass
class ChromaConfig:
    path: str = ""  # Empty = auto-detect (~/.fast-app/chroma)
    embedding_model: str = "nomic-embed-text"
    client_type: str = "persistent"  # "persistent" or "http"

@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    resume: ReactiveResumeConfig = field(default_factory=ReactiveResumeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)  # NEW
    llm: LLMConfig = field(default_factory=LLMConfig)  # NEW
    chroma: ChromaConfig = field(default_factory=ChromaConfig)  # NEW
```

### Test Strategy — Phase 1

- **Unit**: LLM provider creation (Ollama vs OpenCode Go config), JWT
  creation/decoding, password hashing/verification, ChromaDB store/query
- **Integration**: FastAPI TestClient hitting auth endpoints, LLM chains
- **Backward compat**: existing CLI commands work without auth or DB
- **Provider switching**: test that swapping `llm.provider` from "ollama" to
  "opencode-go" changes the underlying `BaseChatModel` instance

---

## Phase 2: Persistent User Profiles

**Goal**: Users store profiles in SQLite. Profile CRUD via API and CLI. Existing
`profile.json` becomes a migration/seed path.

**Complexity**: Medium | **Estimated effort**: 3-4 days | **Depends on**: Phase 1

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/services/profile_service.py` | `ProfileService` class: CRUD operations, import/export JSON |
| `src/fast_app/webapp/profile_routes.py` | FastAPI router: list, create, get, update, delete, import |
| `tests/test_profile_service.py` | CRUD tests, import/export, validation |

### Modified Files

| File | Changes |
|------|---------|
| `src/fast_app/models/db_models.py` | Add `UserProfile` table (id, user_id, name, profile_data JSON, is_default) |
| `src/fast_app/cli.py` | Add `profile` command group: list, show, create, import, export, delete |
| `src/fast_app/utils/profile.py` | Add `load_profile_from_db()`. Modify `load_profile()` to try DB first |
| `src/fast_app/webapp/app.py` | Include profile routes |

### Profile Schema

`profile_data` is a JSON column storing the same structure as current
`profile.json` (basics, work, education, skills, etc.). This avoids schema
migration when the profile format changes.

### Key Design Decisions

1. **Migration path**: `fast-app profile import ./profile.json` reads existing
   profile and creates a DB record. `fast-app profile export <id>` writes back
   to JSON file. Both directions supported.
2. **`is_default` flag**: Each user has one default profile. CLI `generate`
   uses default if no `--profile-id` specified.
3. **Backward compat**: If no auth/DB, `load_profile()` falls back to file-based
   loading exactly as today.

---

## Phase 3: Vector Memory (Knowledge Extraction & Storage)

**Goal**: When a user answers questions, extract key facts, embed them in
ChromaDB, and retrieve relevant knowledge in future sessions.

**Complexity**: High | **Estimated effort**: 5-6 days | **Depends on**: Phase 1, 2

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/services/knowledge.py` | `KnowledgeService` class: `store_facts()`, `query_facts()`, `delete_facts()`, `list_facts()`. Per-user ChromaDB collections. |
| `src/fast_app/services/fact_extractor.py` | `FactExtractor` class: LangChain chain to distill Q&A into facts |
| `src/fast_app/models/knowledge.py` | Pydantic models: `ExtractedFact`, `FactExtractionResult`, `KnowledgeQuery`, `KnowledgeSearchResult` |
| `src/fast_app/prompts/fact_extraction.py` | Prompt template for fact extraction |
| `tests/test_knowledge.py` | ChromaDB integration tests: store, query, delete, per-user isolation |
| `tests/test_fact_extractor.py` | Fact extraction chain tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/fast_app/cli.py` | Add `knowledge` command group: list, search, delete |
| `src/fast_app/webapp/app.py` | Include knowledge routes |
| `src/fast_app/webapp/background_tasks.py` | After Q&A, call `FactExtractor.extract_facts_from_answers()` → `KnowledgeService.store_facts()` |
| `src/fast_app/services/knowledge.py` | Use LangChain's `Chroma` vectorstore + `OllamaEmbeddings` |

### Knowledge Extraction Flow

```
User answers questions
    ↓
FactExtractor.extract_facts_from_answers(questions, answers, profile, job)
    ↓ LangChain chain: prompt → LLM → PydanticOutputParser → FactExtractionResult
    ↓
[ExtractedFact(content="5 years Python experience", category="skill", confidence=0.9),
 ExtractedFact(content="Led team of 8 at Acme", category="experience", confidence=0.95),
 ...]
    ↓
KnowledgeService.store_facts(user_id, facts, job_url=..., source="qa_session")
    ↓ ChromaDB: embed each fact, store with metadata
```

### Knowledge Retrieval Flow

```
New job URL submitted
    ↓
KnowledgeService.query_facts(user_id, query="Python leadership experience", n=5)
    ↓ ChromaDB: embed query, search with metadata filter (user_id)
    ↓
[KnowledgeSearchResult(content="5 years Python experience", distance=0.23, ...),
 KnowledgeSearchResult(content="Led team of 8 at Acme", distance=0.31, ...)]
    ↓
Inject retrieved knowledge into question generation prompt
```

### ChromaDB Per-User Collections

```python
# Each user gets their own collection
collection_name = f"user_{user_id}_knowledge"

# Facts stored with metadata
collection.add(
    ids=["fact_1", "fact_2"],
    documents=["5 years Python experience", "Led team of 8 at Acme"],
    metadatas=[
        {"category": "skill", "source": "qa_session", "confidence": 0.9, "job_url": "..."},
        {"category": "experience", "source": "qa_session", "confidence": 0.95, "job_url": "..."},
    ]
)

# Query with metadata filtering
results = collection.query(
    query_texts=["Python leadership experience"],
    n_results=5,
    where={"category": {"$in": ["skill", "experience"]}},
)
```

### Graceful Degradation

If ChromaDB or Ollama embeddings are unavailable:
- Knowledge storage silently fails (logged as warning)
- Knowledge retrieval returns empty results (no crash)
- System works identically to today — just without memory-augmented prompts
- `--no-knowledge` flag explicitly disables knowledge features

---

## Phase 4: Intelligent Question Generation

**Goal**: Use retrieved knowledge to ask better, more targeted questions that
fill gaps between job requirements and the user's known profile.

**Complexity**: Medium | **Estimated effort**: 2-3 days | **Depends on**: Phase 3

### Modified Files

| File | Changes |
|------|---------|
| `src/fast_app/prompts/questions.py` | Inject retrieved knowledge into prompt. Add `knowledge` parameter. Add gap analysis instructions ("ask about things NOT already in the knowledge base") |
| `src/fast_app/prompts/resume.py` | Inject retrieved knowledge into resume prompt for better tailoring |
| `src/fast_app/prompts/cover_letter.py` | Inject retrieved knowledge for better cover letter personalization |
| `src/fast_app/cli.py` | Add `--no-knowledge` flag to disable knowledge injection |
| `src/fast_app/services/ollama.py` | Or `LLMService` — add knowledge context to generation calls |
| `src/fast_app/webapp/background_tasks.py` | Fetch relevant knowledge before question generation |

### Prompt Enhancement — Questions

```python
def get_questions_prompt(
    job_data: dict,
    profile_data: dict,
    knowledge_context: list[str] | None = None,  # NEW
) -> str:
    """Generate questions prompt with knowledge context."""
    knowledge_section = ""
    if knowledge_context:
        facts = "\n".join(f"- {fact}" for fact in knowledge_context)
        knowledge_section = f"""
## What We Already Know About This Candidate
{facts}

## INSTRUCTIONS
Focus on areas NOT covered by the above knowledge. Ask about gaps between
the job requirements and what we already know. Avoid asking about things
we already have information on.
"""
    ...
```

### Prompt Enhancement — Resume & Cover Letter

Same pattern: inject `knowledge_context` parameter, include relevant past
learnings in the prompt to produce more tailored content.

---

## Phase 5: Webapp Auth & Profile UI

**Goal**: Add login/signup pages and profile management to the webapp.

**Complexity**: Medium | **Estimated effort**: 3-4 days | **Depends on**: Phase 1, 2

### Modified Files

| File | Changes |
|------|---------|
| `src/fast_app/webapp/static/index.html` | Add login/signup forms, profile management section |
| `src/fast_app/webapp/static/app.js` | Add auth state management, API calls for login/signup/profile, knowledge search |
| `src/fast_app/webapp/static/style.css` | Auth form styles |

### Webapp Auth Flow

1. User opens app → check localStorage for token
2. No token → show login/signup form
3. Signup → POST /api/auth/signup → store token
4. Login → POST /api/auth/login → store token
5. Authenticated → show main app with user profile
6. Profile management → CRUD via /api/profiles/*
7. Knowledge viewer → search via /api/knowledge/search

---

## Documentation Plan

### ADRs (Architecture Decision Records)

Store in `docs/adrs/`:

```
docs/adrs/
├── 001-llm-abstraction-langchain.md
├── 002-chromadb-vector-memory.md
├── 003-sqlmodel-sqlite-auth.md
├── 004-jwt-bcrypt-auth.md
├── 005-chonkie-semantic-chunking.md
├── 006-knowledge-extraction-llm.md
└── 007-cli-first-architecture.md
```

Each ADR follows the format:
- **Context**: What is the issue that we're seeing that is motivating this decision?
- **Decision**: What is the change that we're proposing/making?
- **Consequences**: What becomes easier or harder because of this change?

### AGENTS.md Update

Update `AGENTS.md` with:
- New services (LLMService, KnowledgeService, ProfileService, AuthService)
- LLM provider switching (Ollama ↔ OpenCode Go)
- Auth flow (JWT, httpOnly cookies, backward compatibility)
- Knowledge extraction and retrieval pipeline
- ChromaDB per-user collections

### User-Facing Docs

Create `docs/guide/` with:
- `docs/guide/auth-setup.md` — How to enable auth, create first user
- `docs/guide/profiles.md` — Profile management (CLI + webapp)
- `docs/guide/knowledge.md` — How the learning system works
- `docs/guide/llm-providers.md` — Switching between Ollama and OpenCode Go

---

## Execution Order & Dependencies

```
Phase 1 (LLM + Auth) ──→ Phase 2 (Profiles) ──→ Phase 3 (Knowledge) ──→ Phase 4 (Smart Questions)
                                                      │
                                                      └──→ Phase 5 (Webapp UI) ←── Phase 1 (Auth)
```

- Phase 1 is the foundation — everything depends on it
- Phases 2 and 5 can be done in parallel after Phase 1
- Phase 3 depends on Phases 1 AND 2
- Phase 4 depends on Phase 3

Each phase is independently deployable. The system degrades gracefully:

- Without auth → works like today (single-user mode)
- Without profiles → uses profile.json files (backward compat)
- Without ChromaDB → skips knowledge injection (LLM-only prompts)
- Without smart questions → uses standard question generation

---

## Testing Strategy

Each phase includes:
1. **Unit tests** for service logic
2. **Integration tests** for API endpoints
3. **Backward compatibility tests** ensuring existing flows still work
4. **Manual QA** for CLI and webapp flows

Tests for new features go in `tests/` alongside existing tests.
Existing tests MUST continue to pass at every phase boundary.