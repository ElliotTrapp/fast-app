# Fast App

Generate tailored resumes from job URLs and import them into [Reactive Resume](https://github.com/AmruthPillai/Reactive-Resume) automatically.

## Features

- 🔍 **Job URL Scraping**: Extract job details from any job posting URL using Ollama's web_fetch
- 🤖 **AI-Powered Resume Generation**: Use LLMs (via Ollama) to tailor resumes to specific job postings
- 📥 **Automatic Import**: Import generated resumes directly into Reactive Resume
- ⚙️ **XDG-Compliant Config**: Configuration files follow XDG Base Directory Specification

## Prerequisites

1. **Ollama** - [Install Ollama](https://ollama.ai/)
   ```bash
   # Pull a model (llama3.2 recommended)
   ollama pull llama3.2
   ```

2. **Reactive Resume API Key** - Generate an API key from your Reactive Resume instance

## Installation

```bash
cd fast-app
pip install -e .
```

## Configuration

Create a config file at one of these locations:

1. `./config.json` (current directory)
2. `~/.config/fast-app/config.json` (XDG config)
3. Custom path via `--config` flag or `FAST_APP_CONFIG` env var

### Config File Format

```json
{
  "ollama": {
    "endpoint": "http://localhost:11434",
    "model": "llama3.2",
    "cloud": false,
    "debug": false,
    "api_key": ""
  },
  "resume": {
    "endpoint": "http://localhost:3000",
    "api_key": "your-api-key-here"
  }
}
```

**Note**: For Ollama cloud, set `cloud: true` and provide your [Ollama API key](https://ollama.ai/settings/keys).

### Ollama API Key

The `web_fetch` feature requires an Ollama cloud API key. Get one at https://ollama.ai/settings/keys

## Profile File

Create a `profile.json` with your career information. You can copy from the easy-apply profile:

```bash
cp ../easy-apply/profile.json ./profile.json
```

Or specify a custom path:

```bash
fast-app generate <URL> --profile my_profile.json
```

The profile follows the [JSON Resume](https://jsonresume.org/) schema with some extensions for preferences and narrative.

## Usage

### Generate a Resume

```bash
# Basic usage
fast-app generate "https://linkedin.com/jobs/view/123456"

# With custom profile and config
fast-app generate "https://indeed.com/job/123" \
  --profile my_profile.json \
  --config ~/.config/fast-app/config.json

# Save JSON for debugging
fast-app generate "https://linkedin.com/jobs/..." \
  --output debug_resume.json \
  --verbose

# Override API key
fast-app generate "https://..." --api-key YOUR_API_KEY
```

### Test Connections

```bash
fast-app test-connection
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FAST_APP_CONFIG` | Path to config file |
| `RESUME_API_KEY` | Reactive Resume API key (overrides config) |

## How It Works

1. **Job Extraction**: Uses Ollama's `web_fetch` to retrieve the job posting content, then uses an LLM to extract structured job data
2. **Question Generation**: Generates 3-5 clarifying questions to tailor resume (unless `--skip-questions`)
3. **Interactive Q&A**: Prompts user for answers to questions
4. **Resume Generation**: Sends job data + profile + Q&A to LLM to generate tailored resume
5. **Cover Letter Generation**: Sends job data + profile + Q&A to LLM to generate cover letter (unless `--skip-cover-letter`)
6. **Import**: Creates resume and cover letter in Reactive Resume via API, caches data for deduplication

## Caching

The tool caches:
- Job extracted data (`output/<company>/<title>-<hash>/job.json`)
- Generated questions (`questions.json`)
- User answers (`answers.json`)
- Generated resume (`resume.json`)
- Generated cover letter (`cover_letter.json`)
- Reactive Resume ID (`reactive_resume.json`)
- Reactive Cover Letter ID (`reactive_cover_letter.json`)

Use `--force` to regenerate all files, `--overwrite-resume` to replace existing resume/cover letter.

## Reactive Resume API

**Base Path**: `/api/openapi/`

**Endpoints**:
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/openapi/resumes` | List all resumes |
| `POST` | `/api/openapi/resumes` | Create resume (requires `name`, `slug`, `tags`) |
| `GET` | `/api/openapi/resumes/{id}` | Get resume by ID |
| `PUT` | `/api/openapi/resumes/{id}` | Update resume data (send `{data: {...}}`) |
| `DELETE` | `/api/openapi/resumes/{id}` | Delete resume |

**Create Resume Payload**:
```json
{
  "name": "Software Engineer at Acme Resume",
  "slug": "software-engineer-at-acme-resume",
  "tags": ["Acme"]
}
```

Tags are set to the company name for organization.

## Schema Mapping

The tool maps your JSON Resume profile to Reactive Resume's schema:

| Profile Field | ResumeData Field |
|---------------|------------------|
| `basics.name` | `basics.name` |
| `basics.label` | `basics.headline` |
| `basics.summary` | `summary.content` |
| `work[]` | `sections.experience.items[]` |
| `education[]` | `sections.education.items[]` |
| `skills[]` | `sections.skills.items[]` |
| ... | ... |

## Troubleshooting

### LLM Output Invalid

If the LLM generates invalid JSON, the raw output is saved to `debug_llm_output.json`. Check this file to see what the LLM produced.

### Connection Errors

Run `fast-app test-connection` to verify:
- Ollama is running and accessible
- The model is downloaded
- Reactive Resume is running
- API key is valid

### Ollama Cloud API Key

If you see "No API key configured" warnings:
1. Get an API key from https://ollama.ai/settings/keys
2. Add it to your config: `"ollama": {"api_key": "your-key-here"}`

## Related Projects

- [easy-apply](../easy-apply/) - The inspiration for this tool
- [JobSpy](../JobSpy/) - Job scraping library (for search-based scraping)
- [Reactive Resume](../reactive-resume/) - Resume builder

## License

MIT