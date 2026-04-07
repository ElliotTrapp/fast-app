"""FastAPI web application for Fast-App."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .background_tasks import process_job
from .log_stream import log_broadcaster
from .state import state_manager

# Background task tracking
current_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    log_broadcaster.setup_logging()

    # Resume any active job
    if state_manager.is_active():
        # Job was interrupted, reset to idle
        state_manager.reset()

    yield

    # Shutdown
    if current_task and not current_task.done():
        current_task.cancel()


app = FastAPI(
    title="Fast-App",
    description="Resume generator webapp",
    version="1.0.0",
    lifespan=lifespan,
)

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
async def get_status():
    """Get current job status."""
    return state_manager.to_dict()


@app.post("/api/submit")
async def submit_job(request: dict[str, Any]):
    """Start processing a new job."""
    global current_task

    url = request.get("url")
    if not url:
        return {"error": "URL is required"}, 400

    # Check if already processing
    if state_manager.is_active():
        return {"error": "A job is already in progress", "state": state_manager.to_dict()}, 409

    # Extract flags
    flags = {
        "force": request.get("flags", {}).get("force", False),
        "debug": request.get("flags", {}).get("debug", False),
        "overwrite_resume": request.get("flags", {}).get("overwrite_resume", False),
        "skip_questions": request.get("flags", {}).get("skip_questions", False),
        "skip_cover_letter": request.get("flags", {}).get("skip_cover_letter", False),
    }

    # Start background processing
    async def run_job():
        await process_job(url, flags, state_manager, log_broadcaster.broadcast)

    current_task = asyncio.create_task(run_job())

    # Wait a bit for state to update
    await asyncio.sleep(0.5)

    return {"job_id": state_manager.job_id, "status": state_manager.state.value}


@app.get("/api/question")
async def get_question():
    """Get the current question."""
    if state_manager.state.value != "waiting_questions":
        return {"error": "No question available", "state": state_manager.state.value}, 400

    return {
        "index": state_manager.current_question_index,
        "total": len(state_manager.questions),
        "question": state_manager.questions[state_manager.current_question_index],
    }


@app.post("/api/answer")
async def submit_answer(request: dict[str, Any]):
    """Submit an answer to the current question."""
    if state_manager.state.value != "waiting_questions":
        return {"error": "Not waiting for answers", "state": state_manager.state.value}, 400

    answer = request.get("answer", "")

    # Submit answer and check if all done
    all_answered = state_manager.submit_answer(answer)

    # Broadcast progress update
    await log_broadcaster.broadcast_progress(state_manager.current_step, state_manager.progress)

    result = {
        "status": "success",
        "next_state": state_manager.state.value,
        "questions_remaining": len(state_manager.questions) - len(state_manager.answers),
    }

    if all_answered:
        await log_broadcaster.broadcast_state_change("waiting_questions", "processing")

    return result


@app.post("/api/reset")
async def reset_job():
    """Reset the job state."""
    global current_task

    # Cancel any running task
    if current_task and not current_task.done():
        current_task.cancel()
        try:
            await current_task
        except asyncio.CancelledError:
            pass

    state_manager.reset()

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
