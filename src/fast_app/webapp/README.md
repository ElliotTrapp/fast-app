# Webapp

Fast-App web interface for generating tailored resumes from job URLs.

## Overview

The webapp provides a browser-based UI for the Fast-App resume generation workflow. It manages job state, streams real-time logs, handles interactive Q&A, and displays results.

## Architecture

### Components

1. **FastAPI Backend** (`app.py`)
   - RESTful API endpoints
   - WebSocket for real-time log streaming
   - Background task processing
   - State management

2. **Frontend** (`static/`)
   - Single-page HTML UI
   - Vanilla JavaScript (no framework dependencies)
   - CSS styling
   - Real-time log display via WebSocket

3. **State Manager** (`state.py`)
   - Persistent state stored in `~/.fast-app/state.json`
   - Tracks job progress, questions/answers, and results
   - Survives server restarts

4. **Background Tasks** (`background_tasks.py`)
   - Async job processing pipeline
   - Job extraction → Question generation → Resume/Cover Letter creation → Upload

### State Machine

```
IDLE → PROCESSING → WAITING_QUESTIONS → PROCESSING → COMPLETE
                      ↓                      ↓
                    ERROR ←─────────────────┘
```

- **IDLE**: No active job, ready to start
- **PROCESSING**: Job is being processed (extraction, generation, upload)
- **WAITING_QUESTIONS**: Waiting for user to answer questions
- **COMPLETE**: Job finished successfully, results available
- **ERROR**: Job failed, error message available

## API Endpoints

### REST Endpoints

#### `GET /`
Serve the main HTML page.

#### `GET /health`
Health check endpoint.
- Returns: `{"status": "healthy", "state": "<current_state>"}`

#### `GET /api/status`
Get current job status.
- Returns: State snapshot including progress, questions, results

#### `POST /api/submit`
Start processing a new job.
- Body: `{"url": "<job_url>", "flags": {...}}`
- Flags: `force`, `debug`, `overwrite_resume`, `skip_questions`, `skip_cover_letter`
- Returns: `{"job_id": "<id>", "status": "<state>"}`

#### `GET /api/question`
Get the current question (when in WAITING_QUESTIONS state).
- Returns: `{"index": <n>, "total": <n>, "question": "<text>"}`

#### `POST /api/answer`
Submit an answer to the current question.
- Body: `{"answer": "<text>"}`
- Returns: `{"status": "success", "next_state": "<state>"}`

#### `POST /api/reset`
Reset the job state and clear all data.
- Returns: `{"status": "reset", "message": "State cleared"}`

### WebSocket Endpoint

#### `WS /ws`
Real-time log streaming.
- Message types:
  - `log`: Log line with emoji, message, level
  - `state_change`: State transition notification
  - `progress`: Progress update
  - `complete`: Job completed successfully
  - `error`: Job failed with error

## User Workflow

1. **Submit Job**
   - User enters job URL on main form
   - Optionally configure flags (force regenerate, debug mode, etc.)
   - Click "Generate Resume" button
   - UI transitions to progress view

2. **Processing Phase**
   - Real-time logs stream via WebSocket
   - Progress bar updates
   - User can click "Cancel" at any time to abort and return to main menu

3. **Question Phase** (if questions generated)
   - Modal appears with question text
   - User types answer and clicks "Submit Answer" or "Skip"
   - Progress indicator shows "Question X of Y"
   - User can click "Cancel" to abort and return to main menu
   - **No timeout** - user can take unlimited time

4. **Completion**
   - Results page shows links to resume and cover letter
   - User can click "Generate another resume" to start over

5. **Error Handling**
   - Errors display in error view
   - User can "Retry" to try again
   - User can "Cancel" to return to main menu

## State Persistence

State is persisted to `~/.fast-app/state.json`:
- Job ID, URL, company, title
- Current state and progress
- Questions and answers
- Results (resume/cover letter URLs)
- Error messages

This allows:
- Resuming interrupted jobs on server restart
- Page refreshes without losing progress
- Debugging failed jobs

## Cancel Behavior

The "Cancel" button is available in all states except IDLE and COMPLETE:
- **During Processing**: Cancels background task, clears state
- **During Questions**: Closes modal, clears state
- **During Error**: Closes error view, clears state

Cancel always:
1. Shows confirmation dialog
2. Stops polling/timers
3. Calls `/api/reset` to clear server state
4. Returns to main menu
5. Re-enables "Generate Resume" button

## File Structure

```
webapp/
├── __init__.py
├── app.py              # FastAPI application
├── state.py            # State manager
├── background_tasks.py # Job processing logic
├── log_stream.py       # Log broadcasting
└── static/
    ├── index.html      # Main HTML page
    ├── app.js          # Frontend logic
    └── style.css       # Styles
```

## Configuration

Environment variables (optional):
- `FAST_APP_STATE_DIR`: Override state directory (default: `~/.fast-app`)
- `FAST_APP_LOG_DIR`: Override log directory (default: `~/.fast-app/logs`)

## Development

### Running the server
```bash
fast-app serve --host 0.0.0.0 --port 8000
```

### Testing
```bash
pytest tests/
```

### Debug Mode
Set `debug=True` in flags to enable verbose logging.

## Differences from CLI

The webapp mirrors CLI functionality with these differences:
- **State persistence**: All progress saved to disk
- **No timeouts**: Users can take unlimited time answering questions
- **Interactive**: Real-time logs and progress updates
- **Browser-based**: No terminal required

## Known Limitations

1. **Single Job**: Only one job can be processed at a time per server instance
2. **State Lock**: Concurrent requests are rejected if a job is active
3. **File Dependencies**: Requires `profile.json`, `base-resume.json`, `base-cover-letter.json` in working directory