# ADR-001: LangChain for LLM Abstraction

## Context

Fast-App currently talks directly to Ollama using the `ollama` Python SDK. All LLM calls go through `OllamaService` in `services/ollama.py`, which constructs prompts as f-strings, calls `self.client.chat()` with `format=QuestionContent.model_json_schema()`, and manually strips markdown fences from responses.

This approach has several limitations:

1. **Provider lock-in**: The entire service is tightly coupled to Ollama's API. Switching to another provider (e.g., OpenCode Go, OpenAI, Anthropic) requires rewriting every LLM call.
2. **No composability**: Prompts are f-strings assembled in each method. There's no reusable template system, no structured output abstraction beyond Pydantic schema passing, and no way to chain operations.
3. **Rigid retry logic**: The `@with_retry` decorator is custom and Ollama-specific. Each provider has different error patterns and retry semantics.
4. **Future needs**: The knowledge extraction pipeline (Phase 3) needs RAG capabilities (retrieval + generation), which requires composing retrieval with generation — exactly what LangChain chains do.

We need to support at least two providers:
- **Ollama** (local, already working)
- **OpenCode Go** (cloud, OpenAI-compatible API at `https://opencode.ai/zen/go/v1`)

The project also has a learning goal: 20% of this project's purpose is to learn new technologies. LangChain is the most widely used LLM orchestration framework in the Python ecosystem.

## Decision

We will use LangChain (`langchain-core`, `langchain-openai`, `langchain-ollama`, `langchain-community`) as the LLM abstraction layer. `OllamaService` will be refactored to delegate LLM calls to a new `LLMService` class that wraps LangChain's `BaseChatModel`.

Specific choices:

- **Prompt templates**: Replace f-string prompts with LangChain `ChatPromptTemplate` instances in `prompts/templates.py`
- **Structured output**: Replace `format=PydanticClass.model_json_schema()` with LangChain's `with_structured_output()` method or `PydanticOutputParser`
- **Provider switching**: `LLMService._create_llm()` reads `config.llm.provider` and instantiates either `ChatOllama` or `ChatOpenAI` (with custom `base_url` for OpenCode Go)
- **Retry logic**: Replace `@with_retry` decorator with LangChain's built-in retry or tenacity-based callbacks
- **Existing prompts**: Keep `prompts/questions.py`, `prompts/resume.py`, `prompts/cover_letter.py` as they are. The new `prompts/templates.py` will wrap the same logic in `ChatPromptTemplate` instances. This preserves backward compatibility during migration.

### Dependency structure

```toml
[project.optional-dependencies]
llm = [
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",
    "langchain-ollama>=0.3.0",
    "langchain-community>=0.3.0",
    "langchain-chroma>=0.2.0",
]
```

Installed with: `pip install -e ".[llm]"`

### Config changes

```python
@dataclass
class LLMConfig:
    provider: str = "ollama"       # "ollama" or "opencode-go"
    model: str = "llama3.2"        # Model name (passed to both providers)
    temperature: float = 0.3       # Generation temperature
    base_url: str = ""              # OpenCode Go: "https://opencode.ai/zen/go/v1"
    api_key: str = ""               # OpenCode Go API key
```

Environment variable overrides:
- `FAST_APP_LLM_PROVIDER` → `config.llm.provider`
- `FAST_APP_LLM_MODEL` → `config.llm.model`
- `FAST_APP_LLM_BASE_URL` → `config.llm.base_url`
- `FAST_APP_LLM_API_KEY` → `config.llm.api_key`

### Backward compatibility

- When `config.llm.provider == "ollama"` (the default), `LLMService` creates a `ChatOllama` instance backed by the same `config.ollama.endpoint`
- The `OllamaService` class is preserved as a thin wrapper that delegates to `LLMService` internally — all existing CLI and webapp code continues to work
- `OllamaService.check_connection()` and `OllamaService.check_model_available()` remain direct Ollama SDK calls (they're infrastructure checks, not LLM generation)

## Consequences

### Positive

- **Provider switching**: Change `FAST_APP_LLM_PROVIDER=opencode-go` and the entire pipeline uses OpenCode Go instead of Ollama. No code changes.
- **Composability**: LangChain chains make the knowledge extraction pipeline (retrieve facts → inject into prompt → generate) natural to express.
- **Structured output**: `with_structured_output()` is cleaner than f-string JSON schemas and handles provider-specific edge cases.
- **Learning value**: Working with LangChain teaches composable chains, prompt templates, output parsers, and RAG — transferable skills across thousands of projects.
- **Future-proof**: LangChain's ecosystem (LangGraph, LangSmith, callbacks) becomes available if needed.

### Negative

- **Dependency bloat**: LangChain adds ~20 transitive dependencies. Mitigated by using optional dependency groups (`[llm]`, `[auth]`, `[knowledge]`).
- **Migration effort**: Every LLM call must be refactored from direct SDK usage to LangChain chains. This is the bulk of Phase 1 work.
- **Abstraction overhead**: For simple single-provider use cases, LangChain adds indirection. The `LLMService` class absorbs this complexity so callers don't see it.
- **Breaking changes risk**: LangChain moves fast and occasionally breaks APIs. We pin minimum versions (`>=0.3.0`) but should pin exact versions in production.

### Neutral

- The `ollama` Python SDK remains a direct dependency (for `OllamaService.check_connection()` and health checks). It is not removed — it coexists with `langchain-ollama`.