"""FastAPI application: JSON API under /{ROOT_PATH}/api + SPA served from /dist."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
    version as version_api,
    wizard as wizard_api,
)

# When the reverse proxy does NOT strip the prefix (typical Ultra.cc nginx
# user-proxy without trailing slash on proxy_pass), routes must be registered
# under the prefix — FastAPI's `root_path=` only helps when the proxy strips.
ROOT_PATH = os.environ.get("ITA_ROOT_PATH", "").rstrip("/")
DIST_DIR = Path(__file__).parent / "dist"

API_PREFIX = f"{ROOT_PATH}/api"
_OPENAPI_URL = f"{ROOT_PATH}/openapi.json"
AUTH_EXEMPT = {
    f"{API_PREFIX}/auth/login",
    f"{API_PREFIX}/me",
    f"{API_PREFIX}/docs",
    f"{API_PREFIX}/redoc",
    _OPENAPI_URL,
}

app = FastAPI(
    title="ItaTorrents Web",
    docs_url=f"{API_PREFIX}/docs",
    redoc_url=f"{API_PREFIX}/redoc",
    openapi_url=_OPENAPI_URL,
)


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    path = request.url.path.rstrip("/")
    protected = path.startswith(API_PREFIX) or path == _OPENAPI_URL
    if protected and path not in AUTH_EXEMPT:
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


# Mount all JSON routers under ROOT_PATH (routers themselves already declare
# /api/... so the final path is /{ROOT_PATH}/api/...).
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
    version_api.router,
    wizard_api.router,
):
    app.include_router(r, prefix=ROOT_PATH)


if (DIST_DIR / "assets").exists():
    app.mount(
        f"{ROOT_PATH}/assets",
        StaticFiles(directory=str(DIST_DIR / "assets")),
        name="assets",
    )


def _render_index() -> str:
    idx = DIST_DIR / "index.html"
    if not idx.is_file():
        return ""
    html = idx.read_text(encoding="utf-8")
    inject = f'<script>window.__ROOT_PATH__={ROOT_PATH!r};</script>'
    html = html.replace("</head>", f"{inject}</head>", 1)
    # Vite builds with base='./' producing relative asset paths. When the
    # page is served at /itatorrents (no trailing slash) the browser resolves
    # './' to '/' instead of '/itatorrents/' — fix to absolute paths at serve time.
    if ROOT_PATH:
        html = html.replace('./assets/', f'{ROOT_PATH}/assets/')
    return html


# SPA catch-all. Serves index.html for any non-API path so a deep link to a
# client-side route still boots the app.
_CATCHALL = f"{ROOT_PATH}/{{full_path:path}}" if ROOT_PATH else "/{full_path:path}"


@app.get(_CATCHALL)
async def spa(full_path: str, request: Request):
    if full_path.startswith("api/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404)
    if full_path and not full_path.endswith("/"):
        candidate = DIST_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
    rendered = _render_index()
    if rendered:
        return HTMLResponse(rendered)
    return JSONResponse(
        {"detail": "Frontend not built. Run `cd frontend && npm install && npm run build`."},
        status_code=503,
    )


# When hit at exactly "/itatorrents" (no trailing slash) we still want the
# SPA — the catch-all only fires on /itatorrents/..., so add a bare alias.
if ROOT_PATH:
    @app.get(ROOT_PATH)
    async def _root_alias():
        rendered = _render_index()
        return HTMLResponse(rendered) if rendered else JSONResponse(
            {"detail": "Frontend not built."}, status_code=503,
        )


def run():
    import uvicorn
    host = os.environ.get("ITA_HOST", "127.0.0.1")
    port = int(os.environ.get("ITA_PORT", "8765"))
    uvicorn.run("itatorrents.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
