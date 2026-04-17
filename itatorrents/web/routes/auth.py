"""Login / logout routes."""
import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import login_session, logout_session, verify_password
from ..templates_env import ROOT_PATH, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": ""})


@router.post("/login")
async def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
):
    if verify_password(password):
        login_session(request, secrets.token_urlsafe(16))
        dest = next if (ROOT_PATH and next.startswith(ROOT_PATH)) or (not ROOT_PATH and next.startswith("/")) else f"{ROOT_PATH}/"
        return RedirectResponse(dest or f"{ROOT_PATH}/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html",
        {"next": next, "error": "Password errata."},
        status_code=401,
    )


@router.post("/logout")
async def logout(request: Request):
    logout_session(request)
    return RedirectResponse(f"{ROOT_PATH}/login", status_code=303)
