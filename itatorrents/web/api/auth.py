"""Auth: POST /api/auth/login, POST /api/auth/logout, GET /api/me."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import login_session, logout_session, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/auth/login")
async def login(request: Request, body: LoginBody):
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    login_session(request, secrets.token_urlsafe(16))
    return JSONResponse({"ok": True})


@router.post("/auth/logout")
async def logout(request: Request):
    logout_session(request)
    return JSONResponse({"ok": True})


@router.get("/me")
async def me(request: Request):
    return JSONResponse({"authenticated": bool(request.session.get("authenticated"))})
