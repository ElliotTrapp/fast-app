# Knowledge System Guide

## Overview

Fast-App's knowledge system learns from your interview answers and uses that knowledge to generate better, more targeted questions in future sessions. It's the "memory" of the application.

**In simple terms**: If you tell Fast-App "I have 5 years of Python experience" in one session, it will remember that and won't ask you about your Python experience again. Instead, it will focus on gaps between what it knows about you and what the job requires.

---

## How It Works

### The Learning Pipeline

```
1. You answer questions about a job application
                    │
                    ▼
2. FactExtractor distills your answers into atomic facts
   "I've been coding for 5 years, mostly in Python"
   →  ["5 years coding experience", "Primary language is Python"]
                    │
                    ▼
3. Each fact is embedded and stored in ChromaDB
   (with metadata: category, source, confidence, job_url)
                    │
                    ▼
4. Next session, when generating questions:
   a. Retrieve relevant facts: "What do we know about this user's Python skills?"
   b. Inject those facts into the question generation prompt
   c. The LLM asks about gaps, not known strengths
```

### What Gets Stored

Each fact in ChromaDB has:

| Field | Example | Purpose |
|-------|---------|---------|
| **content** | "5 years Python experience" | The fact itself (embedded for semantic search) |
| **category** | "skill" | Category for filtering (skill, experience, education, etc.) |
| **source** | "qa_session" | Where this fact came from |
| **confidence** | 0.9 | How confident the extraction was (0.0-1.0) |
| **job_url** | "https://..." | The job posting that triggered the Q&A |
| **user_id** | 1 | Per-user isolation — your facts are private |
| **extracted_at** | "2025-01-15T10:30:00Z" | When the fact was extracted |

### Example

**First session (Job: Senior Python Developer at TechCorp):**

Questions asked:
1. "How many years of Python experience do you have?" → "About 5 years"
2. "Have you led any teams?" → "Yes, 8 engineers at Acme Corp"
3. "What databases are you familiar with?" → "PostgreSQL and Redis primarily"

Facts extracted and stored:
- "5 years Python experience" (skill, confidence: 0.95)
- "Led team of 8 engineers at Acme Corp" (experience, confidence: 0.9)
- "PostgreSQL and Redis experience" (skill, confidence: 0.85)

**Second session (Job: Python Backend Engineer at StartupXYZ):**

When generating questions, the system retrieves relevant facts:
- Retrieved: "5 years Python experience", "PostgreSQL and Redis experience"

Question generation prompt includes:
> "## What we already know about this candidate:
> - 5 years Python experience
> - PostgreSQL and Redis experience
>
> ## Instructions
> Focus on areas NOT covered by the above knowledge. Ask about gaps between
> the job requirements and what we already know."

Result: Instead of asking about Python years and databases again, the LLM asks:
1. "The role involves microservices architecture. Have you worked with Docker and Kubernetes?"
2. "This position values CI/CD experience. What deployment pipelines have you built?"

---

## Extraction Modes

### Auto-extract (default)

Facts are extracted and stored automatically after each Q&A session. No user intervention required.

```bash
# Default behavior — auto-extract facts
fast-app generate <url>
```

### Review mode

Facts are extracted but presented for your review before storage. You can accept, reject, or edit each fact.

```bash
# Review each fact before storing
fast-app generate <url> --review-facts
```

Review mode shows each fact and asks:

```
📝 Extracted Facts Review
━━━━━━━━━━━━━━━━━━━━━━━━

  Fact 1: "5 years Python experience" (skill, 95% confident)
  Accept? [Y/n/e(edit)]: Y

  Fact 2: "Led team of 8 at Acme Corp" (experience, 90% confident)
  Accept? [Y/n/e(edit)]: Y

  Fact 3: "Enjoys pair programming" (preference, 60% confident)
  Accept? [Y/n/e(edit)]: n

  2 of 3 facts stored.
```

---

## CLI Commands

### List stored facts

```bash
# List all facts for the current user
fast-app knowledge list

# Filter by category
fast-app knowledge list --category skill

# Limit results
fast-app knowledge list --limit 20
```

### Search facts semantically

```bash
# Search for facts about Python experience
fast-app knowledge search "Python experience"

# Search for leadership experience
fast-app knowledge search "team leadership management"
```

Semantic search finds facts by meaning, not exact keywords. Searching "team leadership" will also find facts about "managed a group of developers."

### Delete a fact

```bash
# Delete a specific fact by ID
fast-app knowledge delete <fact_id>

# Delete all facts from a specific job URL
fast-app knowledge delete --job-url "https://..."
```

### Extract facts manually

```bash
# Extract facts from cached Q&A for a job
fast-app knowledge extract --job-url "https://..."

# Extract from a JSON file
fast-app knowledge extract --from-file qa_answers.json
```

---

## Knowledge and Question Generation

### How knowledge injects into prompts

When generating questions for a new job application, the system:

1. **Retrieves** relevant facts by embedding the job description and searching ChromaDB for similar facts
2. **Injects** those facts into the question generation prompt as a "What We Already Know" section
3. **Instructs** the LLM to focus on gaps — things NOT already known

This means:
- You won't be asked the same questions repeatedly
- Questions are targeted at what matters for THIS job
- The more you use the system, the smarter it gets

### Disabling knowledge

```bash
# Skip knowledge retrieval entirely (pure LLM generation, same as before)
fast-app generate <url> --no-knowledge
```

Use `--no-knowledge` if:
- You want fresh questions without influence from past answers
- ChromaDB is not installed and you want to suppress the warning
- You're testing question generation in isolation

---

## ChromaDB Storage

### Where facts are stored

By default, ChromaDB stores data in `~/.fast-app/chroma/`:

```
~/.fast-app/
├── fast_app.db          # SQLite (users, profiles)
└── chroma/               # ChromaDB (vector store)
    ├── chroma.sqlite3    # Metadata index
    └── collections/      # Per-user collections
        ├── user_1_knowledge/
        ├── user_2_knowledge/
        └── ...
```

### Per-user isolation

Each user has their own ChromaDB collection (`user_{id}_knowledge`). Facts are never shared between users.

### Graceful degradation

If ChromaDB is not installed (`pip install -e "."` without `[knowledge]`):

- Knowledge storage silently fails (logged as warning)
- Knowledge retrieval returns empty results
- The system works identically to how it does without knowledge features
- Use `--no-knowledge` to suppress the warning

---

## Configuration

```bash
# ChromaDB configuration (in config.json or environment variables)
{
  "chroma": {
    "path": "",                    # Auto-detect: ~/.fast-app/chroma
    "embedding_model": "nomic-embed-text",  # Ollama embedding model
    "client_type": "persistent"    # "persistent" (local) or "http" (server)
  }
}
```

**Environment variable overrides:**
```bash
export FAST_APP_CHROMA_PATH="/custom/path/chroma"
export FAST_APP_CHROMA_EMBEDDING_MODEL="nomic-embed-text"
export FAST_APP_CHROMA_CLIENT_TYPE="persistent"
```

### Using ChromaDB server (production)

For multi-user production deployments:

```bash
# Start ChromaDB server
chroma run --host 0.0.0.0 --port 8000

# Configure Fast-App to use HTTP client
export FAST_APP_CHROMA_CLIENT_TYPE="http"
export FAST_APP_CHROMA_HOST="localhost"
export FAST_APP_CHROMA_PORT="8000"
```