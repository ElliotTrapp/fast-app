"""FastAPI web application for Fast-App."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..db import init_db
from ..models.db_models import User
from ..services.auth import get_current_user, is_auth_enabled
from .auth_routes import router as auth_router
from .background_tasks import process_job
from .knowledge_routes import router as knowledge_router
from .log_stream import log_broadcaster
from .per_user_state import per_user_state
from .profile_routes import router as profile_router
from .state import state_manager

current_task: asyncio.Task | None = None

# Per-user task tracking: user_id -> asyncio.Task
user_tasks: dict[int, asyncio.Task] = {}


def _resolve_user_id(user: User | None) -> int:
    """Resolve the effective user ID from the authenticated user.

    In auth-disabled mode (user is None), returns the default user ID (1).
    In auth-enabled mode, returns the authenticated user's ID.
    """
    if user is None:
        return 1
    return user.id


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    log_broadcaster.setup_logging()

    try:
        init_db()
    except Exception:
        pass

    if state_manager.is_active():
        state_manager.reset()

    yield

    for task in user_tasks.values():
        if task and not task.done():
            task.cancel()
    if current_task and not current_task.done():
        current_task.cancel()


app = FastAPI(
    title="Fast-App",
    description="Resume generator webapp",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(knowledge_router)

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Connection manager for WebSockets
class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log_broadcaster.add_client(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        log_broadcaster.remove_client(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


async def auth_guard(request: Request, call_next):
    """Middleware that redirects unauthenticated users to /login when auth is enabled.

    Skips auth check for:
    - /login (the login page itself)
    - /static/* (static assets)
    - /api/auth/* (auth endpoints)
    - /health (health check)
    - /ws (WebSocket)
    """
    path = request.url.path

    public_paths = ["/login", "/health", "/ws"]
    public_prefixes = ["/static/", "/api/auth/"]

    if path in public_paths or any(path.startswith(p) for p in public_prefixes):
        return await call_next(request)

    auth_enabled = _is_auth_enabled_cached()

    if not auth_enabled:
        return await call_next(request)

    token = request.cookies.get("fast_app_token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if token:
        try:
            from ..services.auth import decode_access_token

            payload = decode_access_token(token)
            user_id = int(payload.get("sub", 0))
            if user_id > 0:
                return await call_next(request)
        except (ValueError, Exception):
            pass

    return RedirectResponse(url="/login", status_code=303)


_auth_enabled_cache: dict[str, bool] = {}


def _is_auth_enabled_cached() -> bool:
    """Check if auth is enabled, caching the result for 60 seconds."""
    import time

    from ..services.auth import SECRET_KEY

    cache_key = SECRET_KEY or "no_secret"
    now = time.time()
    cached = _auth_enabled_cache.get(cache_key)
    if cached is not None:
        cached_time, cached_value = _auth_enabled_cache[cache_key]
        if now - cached_time < 60:
            return cached_value

    if SECRET_KEY:
        _auth_enabled_cache[cache_key] = (now, True)
        return True

    from sqlmodel import Session

    from ..db import get_engine

    try:
        engine = get_engine()
        with Session(engine) as session:
            result = is_auth_enabled(session)
    except Exception:
        result = False

    _auth_enabled_cache[cache_key] = (now, result)
    return result


app.middleware("http")(auth_guard)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve the login/register page."""
    login_path = static_dir / "login.html"
    if login_path.exists():
        return HTMLResponse(content=login_path.read_text(), status_code=200)
    return HTMLResponse(
        content="<html><body><h1>Login page not found</h1></body></html>",
        status_code=404,
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_page():
    """Serve the profile management page."""
    profile_path = static_dir / "profile.html"
    if profile_path.exists():
        return HTMLResponse(content=profile_path.read_text(), status_code=200)
    return HTMLResponse(
        content="<html><body><h1>Profile page not found</h1></body></html>",
        status_code=404,
    )


@app.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page():
    """Serve the knowledge management page."""
    knowledge_path = static_dir / "knowledge.html"
    if knowledge_path.exists():
        return HTMLResponse(content=knowledge_path.read_text(), status_code=200)
    return HTMLResponse(
        content="<html><body><h1>Knowledge page not found</h1></body></html>",
        status_code=404,
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(), status_code=200)
    else:
        return HTMLResponse(
            content=(
                "<html><body><h1>Fast-App</h1>"
                "<p>Static files not found. Run from project root.</p></body></html>"
            ),
            status_code=200,
        )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "state": state_manager.state.value}


@app.get("/api/status")
async def get_status(user: User | None = Depends(get_current_user)):
    """Get current job status for the authenticated user."""
    user_id = _resolve_user_id(user)
    sm = per_user_state.get_state(user_id)
    return sm.to_dict()


@app.post("/api/submit")
async def submit_job(request: dict[str, Any], user: User | None = Depends(get_current_user)):
    """Start processing a new job.

    Accepts either a URL or text input:
    - URL mode: {"url": "https://..."}
    - Text mode: {"title": "Job Title", "content": "Job description text..."}
    """
    user_id = _resolve_user_id(user)
    sm = per_user_state.get_state(user_id)

    url = request.get("url", "")
    title = request.get("title")
    content = request.get("content")
    job_url = request.get("job_url", "")

    if not url and not (title and content):
        return {"error": "Either 'url' or both 'title' and 'content' are required"}, 400

    # Check if already processing
    if sm.is_active():
        return {"error": "A job is already in progress", "state": sm.to_dict()}, 409

    # Extract flags
    flags = {
        "force": request.get("flags", {}).get("force", False),
        "debug": request.get("flags", {}).get("debug", False),
        "overwrite_resume": request.get("flags", {}).get("overwrite_resume", False),
        "skip_questions": request.get("flags", {}).get("skip_questions", False),
        "skip_cover_letter": request.get("flags", {}).get("skip_cover_letter", False),
        "no_knowledge": request.get("flags", {}).get("no_knowledge", False),
        "review_facts": request.get("flags", {}).get("review_facts", False),
    }

    # Start background processing
    async def run_job():
        await process_job(
            url or job_url,
            flags,
            sm,
            log_broadcaster.broadcast,
            title=title,
            content=content,
            user_id=user_id,
        )

    task = asyncio.create_task(run_job())
    user_tasks[user_id] = task

    # Wait a bit for state to update
    await asyncio.sleep(0.5)

    return {"job_id": sm.job_id, "status": sm.state.value}


@app.get("/api/question")
async def get_question(user: User | None = Depends(get_current_user)):
    """Get the current question."""
    user_id = _resolve_user_id(user)
    sm = per_user_state.get_state(user_id)

    if sm.state.value != "waiting_questions":
        return {"error": "No question available", "state": sm.state.value}, 400

    return {
        "index": sm.current_question_index,
        "total": len(sm.questions),
        "question": sm.questions[sm.current_question_index],
    }


@app.post("/api/answer")
async def submit_answer(request: dict[str, Any], user: User | None = Depends(get_current_user)):
    """Submit an answer to the current question."""
    user_id = _resolve_user_id(user)
    sm = per_user_state.get_state(user_id)

    if sm.state.value != "waiting_questions":
        return {"error": "Not waiting for answers", "state": sm.state.value}, 400

    answer = request.get("answer", "")

    # Submit answer and check if all done
    all_answered = sm.submit_answer(answer)

    # Broadcast progress update
    await log_broadcaster.broadcast_progress(sm.current_step, sm.progress)

    result = {
        "status": "success",
        "next_state": sm.state.value,
        "questions_remaining": len(sm.questions) - len(sm.answers),
    }

    if all_answered:
        await log_broadcaster.broadcast_state_change("waiting_questions", "processing")

    return result


@app.post("/api/reset")
async def reset_job(user: User | None = Depends(get_current_user)):
    """Reset the job state."""
    user_id = _resolve_user_id(user)
    sm = per_user_state.get_state(user_id)

    # Cancel any running task for this user
    task = user_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    sm.reset()

    return {"status": "reset", "message": "State cleared"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back for keepalive
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
