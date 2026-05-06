"""Auth middleware for Fast-App webapp."""

import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from ..services.auth import is_auth_enabled
from ..services.auth_core import JWT_SECRET, decode_access_token

_auth_enabled_cache: dict[str, tuple[float, bool]] = {}


def _is_auth_enabled_cached() -> bool:
    """Check if auth is enabled, caching the result for 60 seconds."""
    cache_key = JWT_SECRET or "no_secret"
    now = time.time()
    cached = _auth_enabled_cache.get(cache_key)
    if cached is not None:
        cached_time, cached_value = _auth_enabled_cache[cache_key]
        if now - cached_time < 60:
            return cached_value

    if JWT_SECRET:
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
            payload = decode_access_token(token)
            user_id = int(payload.get("sub", 0))
            if user_id > 0:
                return await call_next(request)
        except Exception:
            pass

    return RedirectResponse(url="/login", status_code=303)


def setup_middleware(app: FastAPI):
    """Register auth_guard middleware on the FastAPI app."""
    app.middleware("http")(auth_guard)
