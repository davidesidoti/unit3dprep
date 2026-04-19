"""FastAPI application: JSON API under /api + SPA from /dist."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import SECRET_KEY
from .db import init_db
from . import logbuf
from .api import (
    auth as auth_api,
    fs as fs_api,
    library as library_api,
    logs as logs_api,
    quickupload as quickupload_api,
    queue as queue_api,
    search as search_api,
    settings as settings_api,
    tmdb as tmdb_api,
    trackers as trackers_api,
    uploaded as uploaded_api,
    wizard as wizard_api,
)

ROOT_PATH = os.environ.get("ITA_ROOT_PATH", "").rstrip("/")
DIST_DIR = Path(__file__).parent / "dist"

app = FastAPI(
    title="ItaTorrents Web",
    docs_url=None,
    redoc_url=None,
    root_path=ROOT_PATH,
)

# Auth guard: /api/* requires session, except /api/auth/login, /api/me.
# Must be added BEFORE SessionMiddleware so that SessionMiddleware ends up
# outermost (last add = outermost in Starlette) and populates request.session
# before _auth_guard reads it.
_AUTH_EXEMPT = {"/api/auth/login", "/api/me"}


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _AUTH_EXEMPT:
        if not request.session.get("authenticated"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=os.environ.get("ITA_HTTPS_ONLY", "0") == "1",
    same_site="lax",
    max_age=86400 * 7,
)


@app.on_event("startup")
async def _startup():
    await init_db()
    logbuf.install(asyncio.get_event_loop())
    logging.getLogger("itatorrents").info("itatorrents-web started")


# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------


for r in (
    auth_api.router,
    fs_api.router,
    library_api.router,
    logs_api.router,
    queue_api.router,
    quickupload_api.router,
    search_api.router,
    settings_api.router,
    tmdb_api.router,
    trackers_api.router,
    uploaded_api.router,
    wizard_api.router,
):
    app.include_router(r)


# ---------------------------------------------------------------------------
# SPA: serve built frontend + catch-all fallback to index.html
# ---------------------------------------------------------------------------


if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str, request: Request):
    # Let /api/* fall through to 404 instead of masking it with index.html
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    # Try exact file hit first (favicon, fonts at /fonts/..., etc.)
    candidate = DIST_DIR / full_path if full_path else DIST_DIR / "index.html"
    if candidate.is_file():
        return FileResponse(candidate)
    index = DIST_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        {"detail": "Frontend not built. Run `cd frontend && npm install && npm run build`."},
        status_code=503,
    )


def run():
    import uvicorn
    host = os.environ.get("ITA_HOST", "127.0.0.1")
    port = int(os.environ.get("ITA_PORT", "8765"))
    uvicorn.run("itatorrents.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
