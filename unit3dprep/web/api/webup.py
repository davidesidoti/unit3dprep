"""Unit3DWebUp bridge endpoints.

- GET  /api/webup/health  → reachability + version readout
- POST /api/webup/sync    → push shared .env mapped subset to webup runtime via /setenv
- GET  /api/webup/setting → proxy webup's /setting (read user preferences)
- POST /api/webup/filter  → proxy webup's /filter (search tracker for title)
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..config import bootstrap_webup_env
from ..webup_client import get_client


router = APIRouter(prefix="/api", tags=["webup"])


@router.get("/webup/health")
async def health(request: Request):
    client = getattr(request.app.state, "webup", None) or get_client()
    info = await client.health(force=True)
    info["base_url"] = client.base
    ws = getattr(request.app.state, "webup_ws", None)
    info["ws_connected"] = bool(ws and ws.connected)
    return JSONResponse(info)


@router.post("/webup/sync")
async def sync(request: Request):
    client = getattr(request.app.state, "webup", None) or get_client()
    pushed = await bootstrap_webup_env(client)
    return JSONResponse({"pushed": pushed, "count": len(pushed)})


@router.get("/webup/setting")
async def setting(request: Request):
    client = getattr(request.app.state, "webup", None) or get_client()
    try:
        data = await client.setting()
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


class FilterBody(BaseModel):
    title: str


@router.post("/webup/filter")
async def filter_search(request: Request, body: FilterBody):
    client = getattr(request.app.state, "webup", None) or get_client()
    try:
        data = await client.filter_search(body.title)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
