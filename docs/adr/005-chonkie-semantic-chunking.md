# ADR-005: Chonkie for Semantic Chunking

## Context

Fast-App needs to chunk text before embedding it into the vector database. Different types of content have different chunking requirements:

| Content type | Chunking approach | Why |
|--------------|-------------------|-----|
| **Job descriptions** | Semantic chunking needed | Often 500+ words, mixed sections (qualifications, responsibilities, benefits). Semantic boundaries matter. |
| **Q&A answers** | No chunking needed | Already atomic. "I have 5 years of Python experience" is a single fact. |
| **Extracted facts** | No chunking needed | By definition atomic. "5 years Python experience" — one fact, one embedding. |
| **Profile data** | No chunking needed | Structured JSON fields. Each field maps to one embedding. |

Only job descriptions benefit from chunking. Everything else is already the right granularity for embedding.

### What is chunking?

Chunking is the process of splitting a long text into smaller pieces before embedding. Embedding models have token limits (typically 512-8192 tokens), and semantic meaning is better preserved when chunks align with natural content boundaries.

**Naive chunking** (fixed-size windows) splits at arbitrary character positions:

```
"Qualifications: Python, React, 5 years experience. Responsibilities: Lead team of 8, 
design architectures,----------------------------------------| ← split here mid-sentence
 mentor junior devs. Benefits: Health insurance, 401k, remote work..."
```

**Semantic chunking** splits at topic boundaries:

```
"Qualifications: Python, React, 5 years experience." | "Responsibilities: Lead team of 8, 
design architectures, mentor junior devs." | "Benefits: Health insurance, 401k, remote work..."
```

Semantic chunks preserve meaning within each chunk, making retrieval more accurate.

### What is Chonkie?

[Chonkie](https://github.com/chonkie-inc/chonkie) is a Python library for text chunking. It provides:

- **SemanticChunker**: Splits text at semantic boundaries using embeddings
- **TokenChunker**: Splits by token count
- **SentenceChunker**: Splits by sentences
- **RecursiveChunker**: Splits hierarchically

The `SemanticChunker` uses an embedding model to detect topic shifts in the text. It embeds each sentence, computes similarity between consecutive sentences, and splits where similarity drops below a threshold.

## Decision

Use **Chonkie's `SemanticChunker`** for job description chunking only. Q&A answers and extracted facts are embedded directly without chunking.

### Configuration

```python
# Fact extraction doesn't use chunking — facts are atomic
# Job description chunking uses SemanticChunker

from chonkie import SemanticChunker

chunker = SemanticChunker(
    embedding_model="nomic-embed-text",  # Same model as ChromaDB embeddings
    chunk_size=512,       # Target chunk size in tokens
    threshold=0.5,        # Similarity threshold for splitting
    similarity_window=1,  # Number of sentences to compare
)
```

### Usage pattern

```python
# In job_extractor.py or fact_extractor.py

def chunk_job_description(description: str) -> list[str]:
    """Split a job description into semantic chunks for embedding.
    
    Returns:
        List of text chunks, each representing a coherent topic.
    """
    try:
        from chonkie import SemanticChunker
    except ImportError:
        # Fallback: split by paragraphs if Chonkie is not installed
        return [p.strip() for p in description.split("\n\n") if p.strip()]
    
    chunker = SemanticChunker(
        embedding_model=config.chroma.embedding_model,
        chunk_size=512,
    )
    chunks = chunker.chunk(description)
    return [chunk.text for chunk in chunks]
```

### Dependency

```toml
[project.optional-dependencies]
knowledge = [
    "chromadb>=0.5.0",
    "chonkie[semantic]>=1.0.0",
]
```

`chonkie[semantic]` pulls in sentence-transformers for the semantic similarity computation. This is separate from the `[llm]` group.

### Graceful degradation

If Chonkie is not installed (`pip install -e "."` without `[knowledge]`), job descriptions are split by double-newline paragraphs instead. Functionality degrades, but doesn't crash.

## Consequences

### Positive

- **Semantic coherence**: Chunks align with topic boundaries, improving retrieval accuracy.
- **Right-sized approach**: Only job descriptions are chunked. Facts and Q&A are embedded directly — no over-engineering.
- **Embedding consistency**: Using the same embedding model (`nomic-embed-text`) for both Chonkie and ChromaDB ensures the similarity space is consistent.
- **Graceful degradation**: Fallback to paragraph splitting if Chonkie is unavailable.

### Negative

- **Dependency weight**: `chonkie[semantic]` pulls in `sentence-transformers`, `torch`, and `transformers`. This is substantial for a CLI tool. Mitigated by making it optional (`[knowledge]` group).
- **Extra embedding calls**: `SemanticChunker` embeds every sentence to compute similarities. For a single job description (~500 words), this is ~10-20 extra embedding calls. Acceptable since it happens once per job.
- **Not needed for most content**: 3 out of 4 content types don't need chunking. Could be seen as over-engineering. However, job descriptions are the primary input to the system, and poor chunking means poor retrieval.

### Why not other chunking libraries?

| Library | Why not |
|---------|---------|
| **LangChain TextSplitters** | Available if we have LangChain, but fixed-size/recursive only — no semantic boundary detection |
| **LlamaIndex node parsers** | Heavier dependency, more opinionated framework |
| **Custom regex splitting** | No semantic awareness, fragile across different job posting formats |
| **No chunking (just embed the whole description)** | Exceeds embedding model context limits, dilutes semantic meaning, poor retrieval |