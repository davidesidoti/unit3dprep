"""Auth helpers: bcrypt password check, session management."""
import bcrypt
from fastapi import Request
from starlette.responses import RedirectResponse

from ._env import env as _env

PASSWORD_HASH = _env("U3DP_PASSWORD_HASH", "ITA_PASSWORD_HASH", "") or ""
SECRET_KEY = _env("U3DP_SECRET", "ITA_SECRET", "changeme-set-U3DP_SECRET") or "changeme-set-U3DP_SECRET"
SESSION_ID_KEY = "session_id"
AUTH_KEY = "authenticated"


def verify_password(plain: str) -> bool:
    if not PASSWORD_HASH:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), PASSWORD_HASH.encode())
    except Exception:
        return False


def login_session(request: Request, session_id: str):
    request.session[AUTH_KEY] = True
    request.session[SESSION_ID_KEY] = session_id


def logout_session(request: Request):
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(AUTH_KEY))


def get_session_id(request: Request) -> str:
    return request.session.get(SESSION_ID_KEY, "")


def redirect_to_login(next_url: str = "/") -> RedirectResponse:
    return RedirectResponse(f"/login?next={next_url}", status_code=303)
