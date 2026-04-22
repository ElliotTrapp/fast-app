# ADR-002: ChromaDB for Vector Memory

## Context

Fast-App needs a vector database to store and retrieve "learned facts" about users. When a user answers a question like "I have 5 years of Python experience," that fact should be:

1. **Extracted**: Distilled into an atomic fact ("5 years Python experience")
2. **Embedded**: Converted to a vector representation
3. **Stored**: Saved with metadata (user ID, category, source, confidence)
4. **Retrievable**: Queried semantically in future sessions ("What Python experience does this user have?")

This vector memory enables intelligent question generation (Phase 4) — asking about gaps between job requirements and known facts, rather than re-asking what we already know.

### Requirements

- Must support per-user collections (user A's facts aren't visible to user B)
- Must work embedded (no external server) for development
- Must support metadata filtering (by category, source, confidence)
- Must integrate with Ollama embeddings for local development
- Must have a Python API (no Docker dependency for dev)
- Must degrade gracefully — if ChromaDB is unavailable, the system works without memory

### Alternatives considered

| Database | Pros | Cons |
|-----------|------|------|
| **ChromaDB** | Python-native, zero-config embedded mode, `OllamaEmbeddingFunction` built-in, simple API, XDG-compliant storage | SQLite locking bugs in PersistentClient, memory leaks in Rust backend, not process-safe |
| **Qdrant** | Better performance at scale, gRPC + REST APIs, filtering, quantization | Requires Docker or separate server for local dev, more complex setup |
| **Milvus** | Distributed, GPU-accelerated, extreme scale | Overkill for our use case, requires Docker, heavy dependencies |
| **Weaviate** | Great search, modules for vectorizers | Requires Docker, more ops complexity |
| **pgvector** | PostgreSQL integration, if we're already using PG | We're using SQLite, not Postgres — adds infra dependency |
| **FAISS** | Facebook-backed, fast | No metadata filtering, no per-collection isolation, just a similarity index |

## Decision

Use **ChromaDB** with `PersistentClient` for development and local use, with a clear path to `HttpClient` for production.

### Configuration

```python
@dataclass
class ChromaConfig:
    path: str = ""                          # Empty = auto-detect (~/.fast-app/chroma)
    embedding_model: str = "nomic-embed-text"  # Ollama embedding model
    client_type: str = "persistent"          # "persistent" or "http"
    host: str = "localhost"                   # For HttpClient
    port: int = 8000                          # For HttpClient
```

### Per-user collections

Each user gets their own ChromaDB collection:

```python
collection_name = f"user_{user_id}_knowledge"
```

Facts are stored with rich metadata:

```python
collection.add(
    ids=["fact_abc123"],
    documents=["5 years Python experience"],
    metadatas=[{
        "category": "skill",
        "source": "qa_session",
        "confidence": 0.9,
        "job_url": "https://...",
        "extracted_at": "2025-01-15T10:30:00Z",
    }]
)
```

### Graceful degradation

```python
try:
    from chromadb import PersistentClient
    client = PersistentClient(path=config.chroma.path)
except ImportError:
    # chromadb not installed — knowledge features disabled
    logger.warning("chromadb not installed; knowledge features disabled")
    client = None
```

All code that uses `KnowledgeService` must check if ChromaDB is available before calling storage/retrieval methods. If unavailable, return empty results and log a warning — never crash.

### Embedding integration

For Ollama (local dev):

```python
from langchain_ollama import OllamaEmbeddings
embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url="http://localhost:11434")
```

For OpenCode Go (cloud):

```python
from langchain_openai import OpenAIEmbeddings
embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key="...")
```

The `LLMService` already handles provider switching, so `KnowledgeService` asks `LLMService` for the appropriate embedding model.

### Import path

ChromaDB is in the `[knowledge]` optional dependency group, not the default install:

```bash
pip install -e ".[knowledge]"   # Full install with ChromaDB + Chonkie
pip install -e ".[llm,knowledge,auth]"  # Everything
```

## Consequences

### Positive

- **Zero-config dev**: `PersistentClient` creates a directory and works. No Docker, no server, no setup.
- **Per-user isolation**: Collections are namespaced by user ID. Clean separation.
- **Metadata filtering**: Query by category, source, confidence — essential for gap analysis.
- **Embedding flexibility**: Swap between Ollama and OpenAI embeddings based on config.
- **Graceful degradation**: System works identically without ChromaDB — just no memory.

### Negative

- **SQLite locking**: ChromaDB's `PersistentClient` uses SQLite internally. Known bugs with concurrent writes. Acceptable for single-user CLI, but will need `HttpClient` for multi-user production.
- **Memory leaks**: The Rust backend has known memory leak issues. For our use case (small collections, short sessions), this is unlikely to matter.
- **Not process-safe**: Only one process should write to a `PersistentClient` at a time. The webapp + CLI running simultaneously could conflict. Mitigated by: (1) typically only one runs at a time, (2) eventual migration to `HttpClient` for production.

### Mitigation: Production path

When moving to production multi-user deployment:
1. Run ChromaDB as a server: `chroma run --host 0.0.0.0 --port 8000`
2. Set `config.chroma.client_type = "http"` and point to the server
3. Same `KnowledgeService` API — no code changes, just config