"""Reseed endpoints: discover 0-seed ITT torrents already on disk and re-seed.

- `GET  /api/reseed/scan`     — SSE, batched candidate discovery (library↔ITT)
- `GET  /api/reseed/suggest`  — torrent meta + size-matched local files (manual)
- `POST /api/reseed/start`    — create a reseed session, returns a token
- `GET  /api/reseed/{tok}/run`— SSE, run the reseed (download → qBit → hardlink → recheck)
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...i18n import get_request_lang, t as _i18n_t
from ...media import media_root, seedings_root
from .. import config as web_config
from ..logbuf import emit as log_emit
from ..reseed import (
    perform_reseed,
    reseed_search,
    stream_reseed_candidates,
    stream_reseed_search,
    suggest_local_files,
)

router = APIRouter(prefix="/api", tags=["reseed"])

_sessions: dict[str, dict[str, Any]] = {}
_created: dict[str, float] = {}
_TTL = 3600


def _cleanup() -> None:
    now = time.time()
    for tok in [t for t, ct in _created.items() if now - ct > _TTL]:
        _sessions.pop(tok, None)
        _created.pop(tok, None)


def _create(state: dict[str, Any]) -> str:
    _cleanup()
    tok = secrets.token_urlsafe(24)
    _sessions[tok] = state
    _created[tok] = time.time()
    return tok


def _validate_source(p: str, lang: str | None = None) -> Path:
    resolved = Path(p).resolve()
    allowed = [media_root().resolve(), seedings_root().resolve()]
    if not any(str(resolved).startswith(str(a)) for a in allowed):
        raise HTTPException(403, _i18n_t("err.path_outside", lang))
    if not resolved.exists():
        raise HTTPException(404, _i18n_t("err.path_not_found_at", lang, path=str(resolved)))
    return resolved


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@router.get("/reseed/scan")
async def reseed_scan(category: str, offset: int = 0, limit: int = 20, max_seeders: int = 0):
    cfg = web_config.load()
    safe_limit = max(1, min(int(limit or 20), 100))
    safe_offset = max(0, int(offset or 0))
    safe_max_seeders = max(0, min(int(max_seeders or 0), 100))

    async def generate() -> AsyncGenerator[dict, None]:
        async for kind, data in stream_reseed_candidates(
            cfg, category, offset=safe_offset, limit=safe_limit,
            max_seeders=safe_max_seeders,
        ):
            yield {"event": kind, "data": json.dumps(data)}

    return EventSourceResponse(generate())


@router.get("/reseed/suggest")
async def reseed_suggest(torrent_id: int):
    cfg = web_config.load()
    return JSONResponse(await suggest_local_files(cfg, torrent_id))


@router.get("/reseed/search")
async def reseed_search_ep(q: str, category: str = ""):
    cfg = web_config.load()
    return JSONResponse(await reseed_search(cfg, q, category or None))


@router.get("/reseed/search/stream")
async def reseed_search_stream(q: str, category: str = ""):
    cfg = web_config.load()

    async def generate() -> AsyncGenerator[dict, None]:
        async for kind, data in stream_reseed_search(cfg, q, category or None):
            yield {"event": kind, "data": json.dumps(data)}

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Reseed run
# ---------------------------------------------------------------------------


class StartBody(BaseModel):
    tracker: str = "ITT"
    torrent_id: int
    source_path: str
    category: str = ""
    kind: str = ""
    title: str = ""


@router.post("/reseed/start")
async def reseed_start(request: Request, body: StartBody):
    lang = get_request_lang(request)
    src = _validate_source(body.source_path, lang)
    state = {
        "tracker": (body.tracker or "ITT").upper(),
        "torrent_id": int(body.torrent_id),
        "source_path": str(src),
        "category": body.category,
        "kind": body.kind,
        "title": body.title,
    }
    tok = _create(state)
    return JSONResponse({"token": tok})


@router.get("/reseed/{tok}/run")
async def reseed_run(tok: str, request: Request):
    lang = get_request_lang(request)
    state = _sessions.get(tok)
    if state is None:
        raise HTTPException(404, _i18n_t("err.reseed_session_expired", lang))
    cfg = web_config.load()

    async def generate() -> AsyncGenerator[dict, None]:
        async for ev in perform_reseed(
            cfg,
            tracker=state["tracker"],
            torrent_id=state["torrent_id"],
            source_path=state["source_path"],
            category=state.get("category", ""),
            kind=state.get("kind", ""),
            title=state.get("title", ""),
        ):
            if ev["event"] == "log":
                log_emit("info", ev["data"], "reseed", source="reseed")
            elif ev["event"] == "error":
                log_emit("error", ev["data"], "reseed", source="reseed")
            yield ev

    return EventSourceResponse(generate())
