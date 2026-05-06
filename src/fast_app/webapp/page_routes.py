"""HTML page routes for Fast-App webapp."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

static_dir = Path(__file__).parent.parent / "static"


def setup_page_routes(app: FastAPI):
    """Register HTML page routes on the FastAPI app."""

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

    @app.get("/search", response_class=HTMLResponse)
    async def search_page():
        """Serve the job search page."""
        search_path = static_dir / "search.html"
        if search_path.exists():
            return HTMLResponse(content=search_path.read_text(), status_code=200)
        return HTMLResponse(
            content="<html><body><h1>Search page not found</h1></body></html>",
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
