"""FastAPI web application for Fast-App."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from ..db import init_db
from ..dotenv import load_dotenv
from ..models.db_models import User
from ..services.auth import get_current_user
from .auth_routes import router as auth_router
from .background_tasks import process_job
from .dependencies import resolve_user_id
from .job_search_routes import router as job_search_router
from .knowledge_routes import router as knowledge_router
from .log_stream import log_broadcaster
from .middleware import setup_middleware
from .page_routes import setup_page_routes, static_dir
from .per_user_state import per_user_state
from .profile_routes import router as profile_router
from .state import state_manager
from .websocket import setup_websocket

current_task: asyncio.Task | None = None

# Per-user task tracking: user_id -> asyncio.Task
user_tasks: dict[int, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    load_dotenv()
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
app.include_router(job_search_router)

setup_middleware(app)
setup_websocket(app)
setup_page_routes(app)

# Mount static files
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "state": state_manager.state.value}


@app.get("/api/status")
async def get_status(user: User | None = Depends(get_current_user)):
    """Get current job status for the authenticated user."""
    user_id = resolve_user_id(user)
    sm = per_user_state.get_state(user_id)
    return sm.to_dict()


@app.post("/api/submit")
async def submit_job(request: dict[str, Any], user: User | None = Depends(get_current_user)):
    """Start processing a new job.

    Accepts either a URL or text input:
    - URL mode: {"url": "https://..."}
    - Text mode: {"title": "Job Title", "content": "Job description text..."}
    """
    user_id = resolve_user_id(user)
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
    user_id = resolve_user_id(user)
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
    user_id = resolve_user_id(user)
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
    user_id = resolve_user_id(user)
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
