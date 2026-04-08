# Knowledge Base Layer - Implementation Plan

## Overview

The Knowledge Base (KB) layer is a persistent learning system that extracts and stores facts from Q&A sessions, tracks confidence with time-based decay, and provides context to LLM prompts. It uses SQLite for storage (built into Python, zero dependencies).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Fast-App Core                          │
│                   (Existing System)                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ Uses
                     │
        ┌────────────▼─────────────┐
        │   Knowledge Base API      │
        │   (Public Interface)      │
        └────────────┬──────────────┘
                     │
        ┌────────────▼──────────────────────────┐
        │          KB Manager Class              │
        │  (src/fast_app/knowledge/kb.py)       │
        │                                         │
        │  - Fact extraction from Q&A             │
        │  - Confidence decay calculation         │
        │  - Search & retrieval                   │
        │  - Generation tracking                  │
        │  - Pattern extraction                   │
        └────────────┬────────────────────────────┘
                     │
        ┌────────────▼────────────────────────────┐
        │         SQLite Database                  │
        │    (~/.fast_app/knowledge.db)           │
        │                                         │
        │  ┌──────────────┐  ┌─────────────────┐  │
        │  │ facts        │  │ generations    │  │
        │  ├──────────────┤  ├─────────────────┤  │
        │  │ fact_usage    │  │ patterns       │  │
        │  └──────────────┘  └─────────────────┘  │
        │                                         │
        │  ┌──────────────┐                      │
        │  │ metadata     │                      │
        │  └──────────────┘                      │
        └─────────────────────────────────────────┘
```

## Database Schema

```sql
-- Facts: Atomic pieces of knowledge
CREATE TABLE facts (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('skill', 'experience', 'achievement', 'preference', 'general')),
    confidence REAL DEFAULT 0.8 CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_confirmed TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT DEFAULT 'qa' CHECK(source IN ('qa', 'profile', 'imported', 'inferred')),
    version INTEGER DEFAULT 1,
    supersedes TEXT,
    job_url TEXT,
    question TEXT,
    metadata TEXT,
    FOREIGN KEY (supersedes) REFERENCES facts(id) ON DELETE SET NULL
);

-- Generations: Track each resume/cover letter generation
CREATE TABLE generations (
    id TEXT PRIMARY KEY,
    job_url TEXT NOT NULL,
    job_title TEXT,
    company TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    rating INTEGER CHECK(rating >= 1 AND rating <= 5),
    feedback TEXT,
    outcome TEXT CHECK(outcome IN ('success', 'failure', 'pending'))
);

-- Fact Usage: Link facts to generations
CREATE TABLE fact_usage (
    generation_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    PRIMARY KEY (generation_id, fact_id),
    FOREIGN KEY (generation_id) REFERENCES generations(id) ON DELETE CASCADE,
    FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
);

-- Patterns: Success/failure patterns
CREATE TABLE patterns (
    id TEXT PRIMARY KEY,
    generation_id TEXT,
    pattern_type TEXT NOT NULL CHECK(pattern_type IN ('success', 'failure')),
    pattern_text TEXT NOT NULL,
    keywords TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (generation_id) REFERENCES generations(id) ON DELETE SET NULL
);

-- Metadata: KB state
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

## Implementation Checklist

### Phase 1: Core Storage (Week 1)

- [x] Create `src/fast_app/knowledge/` directory structure
- [x] Implement database initialization and schema
- [x] Create Pydantic models for all entities
- [x] Implement fact CRUD operations
- [x] Implement confidence decay calculation
- [x] Implement staleness detection
- [x] Write behavior tests

### Phase 2: Integration (Week 2)

- [ ] Implement generation tracking
- [ ] Implement pattern extraction
- [ ] Integrate with CLI (fact extraction)
- [ ] Integrate with prompts (context building)
- [ ] Write integration tests

### Phase 3: Polish (Week 3)

- [ ] Add import/export functionality
- [ ] Add statistics methods
- [ ] Performance optimization
- [ ] Documentation

## Behavior Tests

### Core Behaviors

1. **Fact Storage**: When I add a fact, it should be persisted and retrievable
2. **Fact Search**: When I search for facts, I should get relevant results ordered by confidence and recency
3. **Confidence Decay**: When facts age, their confidence should decay exponentially based on type
4. **Staleness Detection**: When fact confidence drops below threshold, it should appear in stale list
5. **Fact Versioning**: When I update a fact, it should create a new version that supersedes the old one
6. **Generation Tracking**: When I generate a resume, it should be recorded with links to facts used
7. **Pattern Extraction**: When I rate a generation, success/failure patterns should be extracted

## Migration Path

When ready to upgrade to Neo4j + Qdrant:

1. Export SQLite data to JSON
2. Create Neo4j nodes for each fact
3. Create Qdrant embeddings for each fact text
4. Update `KnowledgeBase.__init__()` to accept `use_graph=True` and `use_vectors=True`
5. Maintain backward compatibility with SQLite for metadata

See full migration plan in `/docs/MIGRATION.md` (to be created).