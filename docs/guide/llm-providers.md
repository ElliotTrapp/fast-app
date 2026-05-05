# LLM Providers Guide

## Overview

Fast-App supports multiple LLM providers through LangChain's abstraction layer. You can use:

- **Ollama** — Local, free, private (default)
- **OpenCode Go** — Cloud-based, subscription ($5-10/month), OpenAI-compatible API

Switch between providers with a single environment variable or config change. No code changes needed.

---

## How LLM Abstraction Works

Fast-App uses LangChain's `BaseChatModel` interface to abstract LLM calls:

```python
# Ollama (local)
from langchain_ollama import ChatOllama
llm = ChatOllama(model="llama3.2", base_url="http://localhost:11434")

# OpenCode Go (cloud)
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o", api_key="...", base_url="https://opencode.ai/zen/go/v1")
```

Both implement the same `BaseChatModel` interface. The `LLMService` class reads your configuration and instantiates the correct provider.

```
Config (config.json / env vars)
        │
        ▼
LLMService._create_llm()
        │
        ├── provider="ollama" → ChatOllama
        │                        └── base_url: http://localhost:11434
        │                        └── model: llama3.2
        │
        └── provider="opencode-go" → ChatOpenAI
                                       └── base_url: https://opencode.ai/zen/go/v1
                                       └── api_key: your-api-key
                                       └── model: (varies, see below)
```

---

## Ollama (Default)

### Setup

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the default model
ollama pull llama3.2

# Or pull a larger model
ollama pull llama3.1:70b

# Start the Ollama server (it usually auto-starts)
ollama serve
```

### Configuration

```json
{
  "ollama": {
    "endpoint": "http://localhost:11434",
    "model": "llama3.2"
  },
  "llm": {
    "provider": "ollama",
    "temperature": 0.3
  }
}
```

**Environment variables:**
```bash
export OLLAMA_ENDPOINT="http://localhost:11434"
export OLLAMA_MODEL="llama3.2"
export FAST_APP_LLM_PROVIDER="ollama"
```

### Recommended models

| Model | Parameters | Best for | Memory needed |
|-------|-----------|----------|--------------|
| `llama3.2` | 3B | Quick generation, limited GPU | 2 GB |
| `llama3.2:1b` | 1B | Fastest, lowest quality | 1 GB |
| `llama3.1:8b` | 8B | Good balance of quality and speed | 6 GB |
| `llama3.1:70b` | 70B | Highest quality, slow | 40 GB |
| `mistral` | 7B | Alternative to llama3 | 5 GB |
| `codellama` | 7B-34B | Code-focused generation | 5-20 GB |

### Embedding models (for knowledge)

Ollama also provides embedding models for the knowledge system:

```bash
# Pull the default embedding model
ollama pull nomic-embed-text

# Or use a different one
ollama pull mxbai-embed-large
```

Configure in `config.json`:
```json
{
  "chroma": {
    "embedding_model": "nomic-embed-text"
  }
}
```

---

## OpenCode Go

### What is OpenCode Go?

[OpenCode Go](https://opencode.ai/) is a cloud service that provides access to multiple LLM models through an OpenAI-compatible API. It uses a subscription model ($5-10/month) rather than per-token pricing.

Key features:
- **OpenAI-compatible API**: Works with any OpenAI SDK by changing the `base_url`
- **Multiple models**: Access to GPT-4o, Claude, Llama, and others
- **Simple pricing**: Monthly subscription, not per-token
- **No local GPU required**: All processing happens in the cloud

### Setup

1. Sign up at [opencode.ai](https://opencode.ai/)
2. Get your API key from the dashboard
3. Configure Fast-App

### Configuration

```json
{
  "llm": {
    "provider": "opencode-go",
    "model": "gpt-4o",
    "temperature": 0.3,
    "base_url": "https://opencode.ai/zen/go/v1",
    "api_key": "your-opencode-api-key"
  }
}
```

**Environment variables:**
```bash
export FAST_APP_LLM_PROVIDER="opencode-go"
export FAST_APP_LLM_MODEL="gpt-4o"
export FAST_APP_LLM_BASE_URL="https://opencode.ai/zen/go/v1"
export FAST_APP_LLM_API_KEY="your-opencode-api-key"
```

**Important**: Use the `openai` Python package, not `ollama`. OpenCode Go uses the OpenAI Chat Completions API format.

### Available models

OpenCode Go provides access to various models. Check their documentation for the current list. Common models include:

- `gpt-4o` — OpenAI's latest, best for resume generation
- `gpt-4o-mini` — Faster, cheaper, good for question generation
- `claude-3.5-sonnet` — Anthropic's model (if available)
- Various open-source models

**Note**: Some models on OpenCode Go use Anthropic's Messages API format instead of the OpenAI Chat Completions format. Check OpenCode Go's documentation for model-specific formatting requirements.

### Using MiniMax models

MiniMax models on OpenCode Go use the Anthropic Messages format rather than OpenAI Chat Completions. If you encounter format errors with MiniMax models, you may need to use the Anthropic client instead:

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    model="minimax-model-name",
    api_key="your-opencode-api-key",
    base_url="https://opencode.ai/zen/go/v1",
)
```

This is a known limitation and will be handled automatically in a future update.

---

## Provider Switching

### Switch with environment variable (no restart needed for CLI)

```bash
# Use Ollama (default)
export FAST_APP_LLM_PROVIDER="ollama"
fast-app generate <url>

# Switch to OpenCode Go
export FAST_APP_LLM_PROVIDER="opencode-go"
export FAST_APP_LLM_API_KEY="your-key"
fast-app generate <url>
```

### Switch in config.json (persistent)

Edit your `config.json`:

```json
{
  "llm": {
    "provider": "opencode-go",
    "model": "gpt-4o",
    "base_url": "https://opencode.ai/zen/go/v1",
    "api_key": "your-key"
  }
}
```

### CLI flag (per-command)

```bash
# Use Ollama for this run
fast-app generate <url> --provider ollama

# Use OpenCode Go for this run
fast-app generate <url> --provider opencode-go
```

### Priority order

1. CLI `--provider` flag (highest)
2. Environment variable `FAST_APP_LLM_PROVIDER`
3. `config.json` `llm.provider` field
4. Default: `"ollama"`

---

## Architecture Details

### LLMService

The `LLMService` class (in `services/llm_service.py`) handles all LLM interactions:

```python
from fast_app.services.llm_service import LLMService
from fast_app.config import Config

config = Config(llm=LLMConfig(provider="opencode-go", api_key="..."))
service = LLMService(config)

# Generate text
result = service.generate("Write a Python function to sort a list")

# Generate structured output
from fast_app.models import QuestionContent
questions = service.generate_with_schema(prompt, QuestionContent)

# Generate questions (high-level)
questions = service.generate_questions(job_data, profile_data)
```

### Backward compatibility

The existing `OllamaService` is preserved as a thin wrapper:

```python
# This still works exactly as before
from fast_app.services.ollama import OllamaService
ollama = OllamaService(config.ollama)
questions = ollama.generate_questions(job_data, profile_data)
```

Internally, `OllamaService` now delegates to `LLMService`. The public API is unchanged.

### Embedding models

The knowledge system also needs an embedding model:

- **Ollama**: Uses `nomic-embed-text` (or configured model) via `langchain-community`
- **OpenCode Go**: Uses OpenAI-compatible embeddings

```json
{
  "chroma": {
    "embedding_model": "nomic-embed-text"
  }
}
```

Embedding model selection is independent of the LLM provider. You can use OpenCode Go for generation and Ollama for embeddings (local embeddings are free, after all).

---

## Troubleshooting

### "Cannot connect to Ollama"

```bash
# Check if Ollama is running
ollama list

# Start Ollama
ollama serve

# Check the endpoint
curl http://localhost:11434/api/tags
```

### "Model 'llama3.2' not found"

```bash
# Pull the model
ollama pull llama3.2

# List available models
ollama list
```

### "Invalid API key" (OpenCode Go)

- Verify your API key at [opencode.ai/dashboard](https://opencode.ai/)
- Ensure the key is set: `echo $FAST_APP_LLM_API_KEY`
- Try the key manually: `curl -H "Authorization: Bearer $KEY" https://opencode.ai/zen/go/v1/models`

### "Provider 'opencode-go' not found"

- Install the LLM dependencies: `pip install -e ".[llm]"`
- Ensure `langchain-openai` is installed: `pip install langchain-openai`

### Slow generation with Ollama

- Try a smaller model: `ollama pull llama3.2:1b`
- Reduce temperature: `"temperature": 0.1` (less randomness = faster)
- Check GPU usage: `nvidia-smi` (Linux) or Activity Monitor > GPU (macOS)

### Slow generation with OpenCode Go

- Try `gpt-4o-mini` instead of `gpt-4o`
- Reduce `num_predict` in the options
- Check OpenCode Go status page for outages