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

- `cli.py` - Click CLI with `generate` and `test-connection` commands
- `services/job_extractor.py` - Extract job data from URLs using Ollama web_fetch
- `services/ollama.py` - LLM service for question generation and resume generation
- `services/reactive_resume.py` - API client for Reactive Resume
- `services/cache.py` - Cache manager for job data, Q&A, resume data
- `log.py` - Centralized logger with semantic methods
- `models.py` - Pydantic models for config and data structures

### Data Flow

1. **Job Extraction** (`JobExtractor.extract_from_url()`)
   - Uses Ollama `web_fetch` to get job posting
   - Extracts title, company, description, requirements
   - Saved to `job.json`

2. **Question Generation** (`OllamaService.generate_questions()`)
   - Generates 3-5 clarifying questions based on job + profile
   - Saved to `questions.json`

3. **Interactive Q&A** (`ask_questions_interactive()`)
   - Prompts user via Click
   - Saved to `answers.json`

4. **Resume Generation** (`OllamaService.generate_resume()`)
   - Uses job + profile + Q&A to generate tailored resume
   - Enforces Reactive Resume JSON schema
   - Saved to `resume.json`

5. **Cover Letter Generation** (`OllamaService.generate_cover_letter()`)
   - Uses job + profile + Q&A to generate tailored cover letter
   - Returns recipient and content
   - Saved to `cover_letter.json`

6. **Import to Reactive Resume**
   - `create_resume()` - POST to create resume/cover letter with title + company tag
   - `update_resume()` - PUT to add resume/cover letter data
   - Cache reactive_resume ID and reactive_cover_letter ID for deduplication

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

## Testing

Run tests with:
```bash
pytest -v
```

No tests currently defined. When adding tests:
1. Test behavior, not implementation
2. Use pytest fixtures for setup
3. Mock external APIs (Ollama, Reactive Resume)

## Development

### Adding New Features

1. Check existing patterns in similar files
2. Use logger methods for output
3. Cache results when appropriate
4. Add `--force` flag to bypass cache
5. Update both README.md and AGENTS.md

### Debugging

Use `--debug` flag to see:
- LLM prompts and responses
- API requests/responses
- Cache operations

### Code Style

- Type hints on function parameters and returns
- Docstrings for public functions
- No inline comments unless complex
- Prefer explicit over implicit