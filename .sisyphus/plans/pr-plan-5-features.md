# 5-PR Implementation Plan

## User Decisions
- **Frontend**: htmx + Alpine.js (no full SPA framework, no build step)
- **CI/CD trigger**: Watchtower (polling-based, ~60s delay)
- **Chat streaming**: Token-by-token (like ChatGPT)
- **Auth scope**: Login UI + per-user state refactor
- **Docker registry**: Docker Hub (current, `trapper137/fast-app`)
- **Chatbot architecture**: Full LangGraph agent (`create_agent()` + `interrupt()` + checkpointers)
- **CLI chat**: REPL mode only (`fast-app chat` opens interactive session)
- **Chat memory**: LangGraph checkpointer (`langgraph-checkpoint-sqlite`)
- **Confirm flows**: All destructive actions confirm (save resume, save cover letter, delete facts)

## PR Dependency Chain

```
PR1 (CI/CD) ─────────── independent, merge first
PR2 (Auth UI + per-user state) ──── independent, merge second
PR3 (Profile management) ─────── depends on PR2 (needs auth)
PR4 (Knowledge management) ────── depends on PR2 (needs auth)
PR5 (Career chatbot) ──────────── depends on PR2, PR3, PR4 (needs auth + profile + knowledge)
```

---

## PR1: CI/CD Pipeline — GitHub Actions → Docker Hub → Watchtower

### Summary
Automate Docker image builds on push to main, push to Docker Hub with multi-arch support, and enable the Synology NAS to auto-pull via Watchtower. No more manual `docker-build-push.sh` on the MacBook.

### Changes
1. **`.dockerignore`** — Exclude `.venv/`, `.git/`, `__pycache__/`, `tests/`, `docs/`, `.mypy_cache/`, `.pytest_cache/`, `generated/`, `*.egg-info/`, `.sisyphus/`
2. **`Dockerfile`** — Rewrite with multi-stage build:
   - Stage 1 (builder): `python:3.12-slim`, install `.[llm,auth,knowledge]`, cache pip deps
   - Stage 2 (runtime): `python:3.12-slim`, copy installed packages from builder, create non-root user, expose 8000
3. **`.github/workflows/ci.yml`** — Add `docker` job after existing `build` job:
   - Trigger on push to main + version tags (`v*`)
   - Login to Docker Hub via `docker/login-action` (secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`)
   - Set up QEMU + Buildx for multi-arch
   - Build `linux/amd64` + `linux/arm64` via `docker/build-push-action`
   - Tag: `trapper137/fast-app:latest` + `trapper137/fast-app:sha-<short>` + `trapper137/fast-app:<version>` on tags
   - Use `docker/metadata-action` for auto-tagging
   - Cache layers with `cache-from: type=gha` / `cache-to: type=gha,mode=max`
4. **`docker-compose.yml`** — Add Watchtower service with `WATCHTOWER_POLL_INTERVAL=60`, `WATCHTOWER_CLEANUP=true`, `WATCHTOWER_LABEL_ENABLE=true`. Add `com.centurylinklabs.watchtower.enable=true` label to fast-app service. Update image tag pattern to support version pinning.
5. **`docker-build-push.sh`** — Add version tag support and `--cache-to` flag. Keep as local fallback.

### Required GitHub Secrets
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (access token from Docker Hub settings)

### Manual Steps (one-time)
1. Create Docker Hub access token: https://hub.docker.com/settings/security
2. Add secrets to GitHub repo: Settings → Secrets and variables → Actions
3. On Synology NAS: `docker compose pull && docker compose up -d` once manually
4. Verify Watchtower container starts and monitors fast-app

### Testing
- Push to feature branch → CI lint/test/build pass, no Docker push (only on main)
- Merge to main → CI builds and pushes Docker image with `:latest` + `:sha-<short>` tags
- On NAS: Watchtower detects new image within 60s, pulls and restarts automatically

---

## PR2: Auth UI + Per-User State (htmx + Alpine.js Foundation)

### Summary
Add login/register pages to the webapp using htmx + Alpine.js. Refactor the global StateManager to be per-user so concurrent users don't block each other. This PR establishes the htmx + Alpine.js infrastructure that PR3, PR4, and PR5 build on.

### Changes

#### Frontend Infrastructure
1. **Add htmx + Alpine.js CDN links** to `index.html` `<head>`:
   - `<script src="https://unpkg.com/htmx.org@2.0.x"></script>`
   - `<script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>`
   - Or download to `static/vendor/` for offline/Docker use
2. **Create `static/app.css`** — Extract shared layout styles (navbar, container, page structure) from `style.css`. Add new navigation bar styles.
3. **Create `static/app-base.js`** — Alpine.js store initialization:
   - `Alpine.store('auth', { user: null, token: null, isLoggedIn: false, ... })` for global auth state
   - `fetchWithAuth(url, options)` — helper that attaches JWT from localStorage to requests
   - `checkAuth()` — on page load, check `/api/auth/me`, update auth store
   - `logout()` — POST `/api/auth/logout`, clear token, redirect to `/login`
4. **Create `static/navbar.js`** — Alpine.js navbar component:
   - Shows app name, navigation links (Generator, Profile, Knowledge, Chat)
   - Shows user email + Logout button when authenticated
   - Shows Login button when not authenticated
5. **Refactor `index.html`** — Add navbar `<div x-data="navbar()">`, wrap content in layout, link new CSS/JS files

#### Auth Pages
6. **Create `static/login.html`** — Login/register page:
   - Toggle between Login and Register forms via Alpine.js `x-show`
   - Login form: email + password → htmx POST `/api/auth/login`
   - Register form: email + password + confirm → htmx POST `/api/auth/signup`
   - Error display via Alpine.js `x-show="error"`
   - On success: store token in localStorage, redirect to `/`
7. **Create `static/login.js`** — Auth form logic:
   - `x-data="loginForm()"` with email, password, error, mode (login/register)
   - `submitLogin()` / `submitRegister()` → fetch with error handling
   - `onSuccess(token)` → store in localStorage, set auth store, redirect

#### Auth Middleware
8. **Add `/login` route to `webapp/app.py`** — Serve `login.html` at `/login`
9. **Add auth guard middleware to `webapp/app.py`** — If auth enabled and no valid token, redirect `/` to `/login`. Skip for `/login`, `/static/*`, `/api/auth/*`, `/health`
10. **Update `webapp/auth_routes.py`** — Add `/api/auth/logout` endpoint: clear httpOnly cookie, return 200
11. **Update `webapp/auth_routes.py`** — Ensure login returns token in JSON body (not just cookie) for localStorage storage

#### Per-User State
12. **Create `webapp/per_user_state.py`** — Per-user state manager:
    - `PerUserStateManager` class with `dict[int, UserState]` internally
    - `get_state(user_id: int) -> UserState` — get or create state for user
    - `remove_state(user_id: int)` — cleanup when user session ends
    - TTL eviction: states idle > 1 hour are cleaned up via periodic task
    - `UserState` class mirrors current `StateManager` fields but per-user
13. **Update `webapp/state.py`** — Keep `StateManager` as `UserState` (rename/refactor). Export `PerUserStateManager` as the new global singleton.
14. **Update `webapp/background_tasks.py`** — Accept `user_id` parameter, use `per_user_state.get_state(user_id)`
15. **Update all `/api/*` routes in `webapp/app.py`** — Accept `user: User | None = Depends(get_current_user)`, resolve `user_id`, pass to `per_user_state.get_state(user_id)`
16. **Update `webapp/app.py`** — Replace `state_manager` singleton with `per_user_state` singleton in lifespan and routes

#### Tests
17. **Update `tests/test_auth.py`** — Add tests for:
    - Login page serves correctly at `/login`
    - Auth guard redirects unauthenticated users to `/login`
    - Auth guard passes for authenticated users
    - Logout clears cookie and redirects
18. **Add `tests/test_per_user_state.py`** — Tests for:
    - Per-user state isolation (two users don't see each other's jobs)
    - TTL eviction of idle user states
    - Concurrent access safety

### Key Decisions
- Auth-disabled mode: `/login` page is skipped entirely, user_id defaults to `1` (existing behavior preserved)
- Per-user state uses in-memory dict with TTL (not DB) — state is ephemeral, same as current but per-user
- Tokens stored in both httpOnly cookie (for API calls) and localStorage (for JS auth state)
- htmx handles form submissions; Alpine.js handles reactive UI state
- CDN scripts downloaded to `static/vendor/` for Docker/offline use (no runtime internet dependency)

---

## PR3: Profile Management Page

### Summary
Add a webapp page for viewing, editing, and managing user profiles. All fields editable with auto-save, changes persist immediately to the database.

### Depends On
PR2 (needs auth, per-user state, htmx + Alpine.js infrastructure, navbar)

### Changes

#### Backend
1. **Update `webapp/profile_routes.py`** — Add PATCH endpoint for partial profile updates:
   - `PATCH /api/profiles/{id}` — Accept partial profile_data fields, merge with existing, save
   - Return updated profile
2. **Update `services/profile_service.py`** — Add `patch_profile()` method for partial updates
3. **Update `models/db_models.py`** — Add `ProfilePatch` Pydantic schema for partial updates (optional fields)

#### Frontend
4. **Create `static/profile.html`** — Profile management page:
   - Page structure: navbar (from PR2) + main content
   - Profile selector sidebar (tabs if multiple profiles, "Create Profile" button)
   - Edit form for all profile_data fields:
     - Personal info: name, email, phone, location, headline
     - Summary: textarea
     - Skills: tag input (add/remove)
     - Experience: repeatable section (company, title, dates, description)
     - Education: repeatable section (institution, degree, dates)
     - Certifications: tag input
     - Projects: repeatable section (name, description, url)
   - Auto-save indicator: "Saving..." → "Saved ✓" → idle (3s fade)
   - Import/export buttons
   - "Set as default" toggle
   - Delete profile button (with confirmation)
5. **Create `static/profile.js`** — Alpine.js profile editor component:
   - `x-data="profileEditor()"` — loads profiles list, default profile fields
   - `saveField(field, value)` → PATCH `/api/profiles/{id}` with debounced 500ms
   - `addProfile(name)` → POST `/api/profiles`
   - `deleteProfile(id)` → DELETE `/api/profiles/{id}` with confirmation
   - `importProfile()` → file picker → POST `/api/profiles/import`
   - `exportProfile(id)` → GET `/api/profiles/{id}/export` → download JSON
   - Repeater field add/remove for experience, education, projects
6. **Create `static/profile.css`** — Profile page styles (form layout, save indicators, repeater sections)

#### Navigation
7. **Update navbar** — "Profile" link already exists from PR2; ensure it links to `/profile`

### Key Decisions
- Profile data is stored as JSON string in `UserProfile.profile_data`. The editor parses this JSON into form fields dynamically.
- Auto-save on field change (debounced 500ms) — no explicit "Save" button needed
- If user has no profile, show "Create your first profile" CTA that creates a blank profile
- Auth-disabled: profile_id defaults to user_id=1

---

## PR4: Knowledge Management Page

### Summary
Add a page for viewing and managing the knowledge base. Browse all facts, search semantically, edit content and metadata, delete facts.

### Depends On
PR2 (needs auth, per-user state, htmx + Alpine.js infrastructure, navbar)

### Changes

#### Backend
1. **Update `webapp/knowledge_routes.py`** — Add endpoints:
   - `POST /api/knowledge/facts` — Manually add a fact (content, category, confidence, source)
   - `PUT /api/knowledge/facts/{id}` — Update a fact's content, category, or confidence
   - `GET /api/knowledge/categories` — List available fact categories
2. **Update `services/knowledge.py`** — Add methods:
   - `add_fact(content, category, confidence, source)` — Add a single fact to ChromaDB
   - `update_fact(fact_id, content, category, confidence)` — Delete old + reinsert with updated content (ChromaDB limitation: no in-place update)
   - `get_categories()` — Return list of valid ExtractedFact categories
3. **Add `models/knowledge.py` schemas** — `FactCreate`, `FactUpdate` Pydantic models for request validation

#### Frontend
4. **Create `static/knowledge.html`** — Knowledge management page:
   - Search bar at top (semantic search via `/api/knowledge/search`)
   - Category filter tabs (All, Skill, Experience, Education, Certification, Preference, Personality, Goal)
   - Fact cards grid showing:
     - Content (editable inline)
     - Category badge (colored by type)
     - Confidence bar (0-100%)
     - Source (job URL or "manual")
     - Extracted date
     - Edit / Delete buttons
   - "Add Fact" button (opens modal with content, category, confidence fields)
   - Pagination or infinite scroll
5. **Create `static/knowledge.js`** — Alpine.js knowledge editor component:
   - `x-data="knowledgeEditor()"` — loads facts, categories
   - `searchFacts(query)` → GET `/api/knowledge/search?query=...&n=20`
   - `filterByCategory(category)` → GET `/api/knowledge/facts?category=...`
   - `editFact(id)` → toggle inline edit on card
   - `saveFact(id)` → PUT `/api/knowledge/facts/{id}` (auto-save on blur)
   - `deleteFact(id)` → DELETE `/api/knowledge/facts` with confirmation prompt
   - `addFact(content, category, confidence)` → POST `/api/knowledge/facts`
6. **Create `static/knowledge.css`** — Knowledge page styles (fact cards, category badges, confidence indicator, search)

#### Navigation
7. **Update navbar** — "Knowledge" link already exists from PR2; ensure it links to `/knowledge`

### Key Decisions
- ChromaDB doesn't support in-place document update — `update_fact()` does delete-then-reinsert, which changes the UUID
- Frontend must handle changed UUID after edit (refetch the updated fact)
- Delete confirms via htmx `hx-confirm="Are you sure?"` or Alpine.js modal
- Auth-disabled: uses user_id=1

---

## PR5: Career Chatbot (Full LangGraph Agent)

### Summary
Add a conversational career chatbot that uses a LangGraph agent with tools to access the user's profile, knowledge base, job extractor, and Reactive Resume API. All destructive actions (save resume, save cover letter, delete facts) require user confirmation via LangGraph `interrupt()`. Streaming responses token-by-token via WebSocket. Available in CLI (REPL) and webapp.

### Depends On
PR2 (auth + per-user state), PR3 (profile endpoints), PR4 (knowledge endpoints)

### Architecture

**LangGraph Agent** — `create_agent()` with `interrupt()` for confirm-before-execute and `langgraph-checkpoint-sqlite` for conversation memory:

```
User message → LangGraph Agent (ReAct loop)
    ↓
Agent decides which tools to invoke:
    ├── query_knowledge → KnowledgeService.query_facts()
    ├── get_profile → ProfileService.get_default_profile()
    ├── search_jobs → JobExtractor.extract_from_url()
    ├── generate_resume → LLMService.generate_resume() → interrupt("Save to Reactive Resume?") → resume/Reject
    ├── generate_cover_letter → LLMService.generate_cover_letter() → interrupt("Save to Reactive Resume?") → resume/Reject
    ├── save_to_reactive_resume → ReactiveResumeClient (only after interrupt confirmation)
    └── (no tool) → direct text response

Streaming: astream_events() yields tokens between tool calls
Confirmations: interrupt() pauses agent, sends chat_interrupt to client
Client responds: chat_resume with approved=true/false
If approved: Command(resume=True) continues agent → save_to_reactive_resume executes
```

### New Dependencies
- `langgraph>=0.3.0` — Agent framework with `create_agent()`, `interrupt()`, `Command`
- `langgraph-checkpoint-sqlite>=2.0.0` — SQLite-based checkpointer for conversation memory

### Changes

#### LangChain Tools
1. **Create `services/chatbot_tools.py`** — LangChain `@tool` definitions:
   - `query_knowledge(query: str, n: int = 5)` — Semantic search over user's facts via KnowledgeService
   - `get_profile()` — Fetch user's default profile via ProfileService
   - `search_jobs(url: str)` — Extract job data from URL via JobExtractor
   - `generate_resume(job_data: dict, profile_data: dict)` — Generate resume data (does NOT save to Reactive Resume)
   - `generate_cover_letter(job_data: dict, profile_data: dict)` — Generate cover letter data (does NOT save to Reactive Resume)
   - `save_to_reactive_resume(content_type: str, title: str, data: dict)` — Save generated content to Reactive Resume (only callable after interrupt confirmation)
   - Tools use `InjectedToolArg` for `user_id`, `config` — never passed by the LLM
   - Tools are closures capturing service instances at ChatService creation time

#### Chat Service
2. **Create `services/chatbot.py`** — `ChatService` class:
   - `ChatService(config, user_id, session_id)` — creates services, tools, agent
   - `create_agent()` — builds LangGraph agent with `create_agent(model, tools, prompt)`
   - `stream_chat(message: str) -> AsyncGenerator[ChatEvent, None]` — streams via `agent.astream_events()`
   - `confirm_action(action_id: str, approved: bool)` — resumes agent after `interrupt()`
   - System prompt: career advisor persona with tool usage instructions
   - Conversation memory via `langgraph-checkpoint-sqlite` (stores in existing `.fast-app/` directory)
   - `ChatEvent` union type: `TokenEvent`, `ToolCallEvent`, `ToolResultEvent`, `InterruptEvent`, `CompleteEvent`

#### LLM Service Streaming
3. **Update `services/llm_service.py`** — Add streaming method:
   - `generate_stream(prompt: str, **kwargs) -> AsyncGenerator[str, None]` — yields tokens via `self._llm.astream()`
   - Used by the chatbot for direct responses (non-tool-call text)

#### Backend API
4. **Create `webapp/chat_routes.py`** — Chat endpoints:
   - `WS /ws/chat/{session_id}` — WebSocket for streaming chat:
     - Client→Server: `{"type": "chat_message", "content": "..."}`, `{"type": "chat_resume", "action_id": "...", "approved": true/false}`
     - Server→Client: `{"type": "chat_token", "content": "..."}`, `{"type": "chat_tool_call", "tool": "...", "args": {...}}`, `{"type": "chat_tool_result", "tool": "...", "result": "..."}`, `{"type": "chat_interrupt", "action_id": "...", "action": "save_resume", "message": "..."}`, `{"type": "chat_complete"}`, `{"type": "chat_error", "message": "..."}`
   - `POST /api/chat/message` — REST fallback (non-streaming)
   - `GET /api/chat/history/{session_id}` — Get recent chat history from checkpointer
   - `DELETE /api/chat/history/{session_id}` — Clear chat history
5. **Update `webapp/app.py`** — Include chat_router

#### Frontend
6. **Create `static/chat.html`** — Chat interface page:
   - Message list: user messages right-aligned, bot messages left-aligned
   - Streaming text rendered token-by-token (append to current bot message)
   - Tool call indicators between messages: "🔍 Searching knowledge base...", "📄 Generating resume..."
   - Interrupt prompts: "Save this cover letter to Reactive Resume?" with Accept/Reject buttons
   - Input field at bottom with Send button (Enter to send, Shift+Enter for newline)
   - "Clear Chat" button
7. **Create `static/chat.js`** — Alpine.js chat component:
   - `x-data="chatApp()"` — messages array, input, streaming state
   - WebSocket connection to `/ws/chat/{session_id}`
   - `sendMessage()` → WS send `chat_message`
   - Token rendering: append to current bot message div
   - Tool call rendering: show tool name + args badge
   - Interrupt handling: show confirmation buttons, `confirmAction(id, approved)` → WS send `chat_resume`
   - Auto-scroll on new content
8. **Create `static/chat.css`** — Chat UI styles (message bubbles, tool indicators, interrupt prompt, input area)

#### CLI
9. **Update `cli.py`** — Add `chat` command:
   - `fast-app chat` — Start interactive REPL session
   - Prompt: `You: ` input, streaming bot response below
   - Tool calls shown inline: `[Tool: query_knowledge] Searching for "python experience"...`
   - Interrupt prompts: "Save this cover letter to Reactive Resume? [y/N]: "
   - Input via Python `input()`, output via `sys.stdout.write()` for streaming tokens
   - Ctrl+C or Ctrl+D to exit with "Goodbye!" message
   - Uses same `ChatService` as webapp

#### ADR
10. **Create `docs/adr/008-career-chatbot-langgraph.md`** — Document architecture decision:
    - Why LangGraph over manual routing or AgentExecutor
    - Tool design philosophy (closures with InjectedToolArg)
    - Interrupt pattern for destructive action confirmation
    - Streaming architecture (astream_events → WebSocket → Alpine.js)
    - Checkpointer choice (SQLite) and trade-offs

#### Tests
11. **Create `tests/test_chatbot.py`** — Tests for:
    - Tool definitions: names, descriptions, signatures
    - ChatService initialization with mocked services
    - Agent creation with correct tool list
    - Streaming response (mock LLM, verify AsyncGenerator yields TokenEvents)
    - Tool invocation: verify correct service methods called
    - Interrupt flow: generate cover letter → interrupt → confirm → save
    - Interrupt flow: generate cover letter → interrupt → reject → no save
    - WebSocket protocol: send chat_message, receive chat_token stream + chat_complete
    - Auth-disabled: chatbot works with user_id=1
12. **Create `tests/test_chatbot_tools.py`** — Tests for each tool:
    - `query_knowledge` calls `KnowledgeService.query_facts()`
    - `get_profile` calls `ProfileService.get_default_profile()`
    - `search_jobs` calls `JobExtractor.extract_from_url()`
    - `save_to_reactive_resume` calls `ReactiveResumeClient` methods
    - `user_id` is never a parameter the LLM must provide (InjectedToolArg)

### Key Decisions

**Full LangGraph agent** — `create_agent()` with ReAct pattern. The agent decides which tools to call and when, enabling multi-step reasoning (e.g., "First get my profile → then compare against job → then generate cover letter → confirm save").

**Interrupt for destructive actions** — `interrupt()` pauses the agent graph when a destructive action needs confirmation. The frontend sends `chat_resume` with `approved=true/false`. If approved, `Command(resume=True)` continues the graph and executes `save_to_reactive_resume`. If rejected, the agent receives the rejection and responds accordingly.

**Streaming via astream_events()** — LangGraph supports `agent.astream_events()`, which yields events for each step of the ReAct loop. We map these to WebSocket message types:
- `on_chat_model_stream` → `chat_token`
- `on_tool_start` → `chat_tool_call`
- `on_tool_end` → `chat_tool_result`
- Custom interrupt handling → `chat_interrupt`

**Conversation memory via langgraph-checkpoint-sqlite** — Stored in `~/.fast-app/chat_checkpoints.db`. Each session_id gets its own thread in the checkpointer. History persists across server restarts. The checkpointer serializes the full agent state (messages, tool calls, interrupts).

**CLI/Webapp shared service** — `ChatService` is the same for both. CLI reads tokens synchronously from the async generator; webapp streams tokens via WebSocket.

**Tool security** — `user_id` injected via `InjectedToolArg`, never trust LLM-provided user_id. Services created at ChatService init time, captured in tool closures.

**Rate of token emission** — To avoid overwhelming the frontend, buffer tokens for 50ms batches before sending to WebSocket.

---

## Implementation Order

1. **PR1** — Independent, no blockers. Merge first so CI works for subsequent PRs.
2. **PR2** — Foundation for PR3/PR4/PR5. htmx + Alpine.js setup + auth + per-user state.
3. **PR3** & **PR4** — Can be developed in parallel (both depend on PR2, independent of each other).
4. **PR5** — Depends on PR2 + PR3 + PR4 (needs profile + knowledge endpoints for tools).

### PR3/PR4 Parallel Development Note
Since PR3 and PR4 are independent after PR2 merges, they can be developed on separate branches from PR2's branch. Both modify the navbar, so the second to merge will need to resolve that conflict (trivial — just adding a nav link).

---

## Cross-PR Shared Patterns

These patterns are established in PR2 and followed by all subsequent PRs:

1. **Navbar** — Shared navigation bar component loaded on every page via Alpine.js
2. **Auth flow** — `fetchWithAuth()` helper for all API calls, `Alpine.store('auth')` for auth state
3. **Per-user state** — `per_user_state.get_state(user_id)` for job state, `user_id` in all service calls
4. **Page structure** — Each page is a standalone HTML file served by FastAPI, linked to shared CSS/JS
5. **API pattern** — All routes accept `user: User | None = Depends(get_current_user)`, use `_resolve_user_id(user)`