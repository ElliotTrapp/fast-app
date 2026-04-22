# Fast-App

Generate tailored resumes from job URLs using AI and import them to Reactive Resume. Fast-App learns from your answers over time, asking smarter questions and building a personal knowledge base.

## Features

- Extract job data from URLs using Ollama or OpenCode Go
- Generate tailored resumes and cover letters with AI
- Interactive Q&A to customize resume content
- **Knowledge system** that learns from your answers across sessions
- **Multi-user auth** with JWT tokens and bcrypt password hashing
- **LLM provider switching** — use Ollama (local/free) or OpenCode Go (cloud)
- Automatic upload to Reactive Resume
- Web interface for easy use
- CLI-first architecture — all features available from the command line

## Installation

```bash
# Core only (no auth, LLM abstraction, or knowledge deps)
pip install -e .

# With LLM provider support (LangChain, ChatOllama, ChatOpenAI)
pip install -e ".[llm]"

# With authentication (SQLModel, JWT, bcrypt)
pip install -e ".[auth]"

# With knowledge system (ChromaDB vector DB, Chonkie chunking)
pip install -e ".[knowledge]"

# Everything
pip install -e ".[llm,auth,knowledge]"

# Development (pytest, mypy, ruff)
pip install -e ".[dev]"
```

## Usage

### CLI

```bash
# Generate a resume from a job URL
fast-app generate <job-url>

# Use OpenCode Go instead of local Ollama
fast-app generate <job-url> --provider opencode-go

# Review extracted facts before storing
fast-app generate <job-url> --review-facts

# Disable knowledge injection
fast-app generate <job-url> --no-knowledge

# Authentication
fast-app auth signup --email you@example.com --password "your-password"
fast-app auth login --email you@example.com --password "your-password"
fast-app auth whoami

# Profile management
fast-app profile list
fast-app profile import ./profile.json --default
fast-app profile export --output profile_export.json

# Knowledge management
fast-app knowledge search "Python experience"
fast-app knowledge list --category skill
```

### Web Interface

```bash
fast-app serve
```

Then open http://localhost:8000 in your browser.

## Configuration

Create a `config.json` file with your settings:

```json
{
  "ollama": {
    "endpoint": "http://localhost:11434",
    "model": "llama3.2"
  },
  "resume": {
    "endpoint": "http://localhost:3000",
    "api_key": "your-api-key"
  },
  "llm": {
    "provider": "ollama",
    "model": "llama3.2",
    "temperature": 0.3
  }
}
```

Switch to OpenCode Go:

```json
{
  "llm": {
    "provider": "opencode-go",
    "model": "gpt-4o",
    "temperature": 0.3,
    "base_url": "https://opencode.ai/zen/go/v1",
    "api_key": "your-opencode-key"
  }
}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FAST_APP_LLM_PROVIDER` | LLM provider (`ollama` or `opencode-go`) | `ollama` |
| `FAST_APP_LLM_MODEL` | Model name | `llama3.2` |
| `FAST_APP_LLM_BASE_URL` | API base URL (for OpenCode Go) | — |
| `FAST_APP_LLM_API_KEY` | API key (for OpenCode Go) | — |
| `FAST_APP_JWT_SECRET` | JWT secret for auth (enables auth when set) | — |
| `FAST_APP_DB_PATH` | SQLite database path | `~/.fast-app/fast_app.db` |
| `FAST_APP_CHROMA_PATH` | ChromaDB storage path | `~/.fast-app/chroma` |

## Knowledge System

Fast-App learns from your answers and uses that knowledge in future sessions:

1. You answer interview questions about a job
2. Facts are extracted from your answers (e.g., "5 years Python experience")
3. Facts are stored in ChromaDB with metadata
4. Next session, relevant facts are injected into question generation
5. The LLM asks about gaps, not things it already knows

See [docs/guide/knowledge.md](docs/guide/knowledge.md) for details.

## Authentication

Auth is **disabled by default** — the system works as a single-user tool without any setup. Enable auth when you need multi-user support:

```bash
# Set a JWT secret
export FAST_APP_JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Create your first user
fast-app auth signup --email you@example.com --password "your-password"
```

See [docs/guide/auth-setup.md](docs/guide/auth-setup.md) for the full guide.

## Documentation

- [Auth Setup Guide](docs/guide/auth-setup.md) — Authentication fundamentals and setup
- [Profile Management](docs/guide/profiles.md) — CLI and webapp profile management
- [Knowledge System](docs/guide/knowledge.md) — How the learning system works
- [LLM Providers](docs/guide/llm-providers.md) — Switching between Ollama and OpenCode Go
- [Architecture Decisions](docs/adr/) — ADRs for major technical decisions

## License

MIT