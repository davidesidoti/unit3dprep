"""FastAPI application factory."""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .auth import SECRET_KEY, is_authenticated
from .db import init_db
from .routes import auth as auth_router
from .routes import library as library_router
from .routes import uploaded as uploaded_router
from .routes import wizard as wizard_router
from .templates_env import ROOT_PATH

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ItaTorrents Web", docs_url=None, redoc_url=None)

_LOGIN_PATH = f"{ROOT_PATH}/login"
_STATIC_PREFIX = f"{ROOT_PATH}/static"


async def _auth_guard(request: Request, call_next):
    path = request.url.path
    if path.startswith(_STATIC_PREFIX) or path == _LOGIN_PATH:
        return await call_next(request)
    if not is_authenticated(request):
        return RedirectResponse(f"{_LOGIN_PATH}?next={path}", status_code=303)
    return await call_next(request)


# Middleware order: LAST add_middleware = OUTERMOST = runs first.
# SessionMiddleware must be outermost so session is populated before auth_guard.
app.add_middleware(BaseHTTPMiddleware, dispatch=_auth_guard)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=os.environ.get("ITA_HTTPS_ONLY", "0") == "1",
    same_site="lax",
    max_age=86400 * 7,
)


@app.on_event("startup")
async def startup():
    await init_db()


app.mount(f"{ROOT_PATH}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router.router, prefix=ROOT_PATH)
app.include_router(library_router.router, prefix=ROOT_PATH)
app.include_router(wizard_router.router, prefix=ROOT_PATH)
app.include_router(uploaded_router.router, prefix=ROOT_PATH)


def run():
    import uvicorn
    host = os.environ.get("ITA_HOST", "127.0.0.1")
    port = int(os.environ.get("ITA_PORT", "8765"))
    uvicorn.run("itatorrents.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
