"""Quick upload (UploadModal flow) — wraps Unit3DWebUp without the full wizard.

Takes a path + mode (u|f|scan), drives the webup HTTP API, streams logs via SSE.
No audio check, no hardlink: for power users who already staged files in
their seeding path. DB record is created on start; exit code updated on done.
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

from ...i18n import get_request_lang, t
from ..db import update_exit_code
from ..logbuf import emit as log_emit
from ..webup_orchestrator import stream_webup, stream_webup_batch

router = APIRouter(prefix="/api", tags=["quickupload"])

_jobs: dict[str, dict[str, Any]] = {}
_created: dict[str, float] = {}
_TTL = 3600


def _cleanup():
    now = time.time()
    for j in [j for j, ct in _created.items() if now - ct > _TTL]:
        _jobs.pop(j, None)
        _created.pop(j, None)


class QuickBody(BaseModel):
    path: str
    mode: str = "u"            # u|f|scan
    tracker: str = "ITT"
    tmdb_id: str = ""
    skip_tmdb: bool = False
    skip_youtube: bool = False
    anon: bool = False
    webp: bool = False
    screenshots: bool = True


@router.post("/upload/quick")
async def create(request: Request, body: QuickBody):
    lang = get_request_lang(request)
    p = Path(body.path).resolve()
    if not p.exists():
        raise HTTPException(404, t("err.path_not_found", lang))
    if body.mode not in {"u", "f", "scan"}:
        raise HTTPException(400, t("err.invalid_mode", lang))
    _cleanup()
    job_id = secrets.token_urlsafe(16)
    _jobs[job_id] = {
        "path": str(p),
        "mode": body.mode,
        "tmdb_id": body.tmdb_id,
    }
    _created[job_id] = time.time()
    return JSONResponse({"job": job_id})


@router.get("/upload/{job}/stream")
async def stream(request: Request, job: str):
    state = _jobs.get(job)
    if state is None:
        raise HTTPException(404, t("err.job_not_found", get_request_lang(request)))
    path: str = state["path"]
    mode: str = state["mode"]
    tmdb_id: str = state.get("tmdb_id", "")
    app = request.app

    async def gen() -> AsyncGenerator[dict, None]:
        if mode == "scan":
            async for ev in stream_webup_batch(
                client=app.state.webup,
                ws=app.state.webup_ws,
                scan_lock=app.state.webup_scan_lock,
                folder=path,
            ):
                et = ev["type"]
                if et == "log":
                    ev_kind = ev.get("kind", "info")
                    event_slug = ev.get("event")
                    log_emit(ev_kind, ev["data"], "webup", source="webup", event=event_slug)
                    yield {"event": "log", "data": ev["data"]}
                elif et == "job_done":
                    job_path = ev.get("path") or ""
                    if job_path:
                        await update_exit_code(job_path, ev.get("exit_code", -1))
                    yield {"event": "job_done", "data": json.dumps(ev)}
                elif et == "error":
                    log_emit("error", ev["data"], "webup", source="webup")
                    yield {"event": "error", "data": ev["data"]}
                elif et == "done":
                    code = ev.get("exit_code", -1)
                    state["exit_code"] = code
                    log_emit(
                        "ok" if code == 0 else "error",
                        f"webup batch exit {code} (ok={ev.get('ok',0)} fail={ev.get('fail',0)})",
                        "quickupload",
                    )
                    yield {"event": "done", "data": json.dumps({
                        "exit_code": code,
                        "ok": ev.get("ok", 0),
                        "fail": ev.get("fail", 0),
                    })}
            return

        kind = "series" if mode == "f" else "movie"
        async for ev in stream_webup(
            client=app.state.webup,
            ws=app.state.webup_ws,
            scan_lock=app.state.webup_scan_lock,
            seeding_path=path,
            kind=kind,
            tmdb_id=tmdb_id,
        ):
            et = ev["type"]
            if et == "log":
                ev_kind = ev.get("kind", "info")
                event_slug = ev.get("event")
                log_emit(ev_kind, ev["data"], "webup", source="webup", event=event_slug)
                yield {"event": "log", "data": ev["data"]}
            elif et == "progress":
                yield {"event": "progress", "data": json.dumps({
                    "phase": ev.get("phase"),
                    "label": ev.get("label"),
                    "pct": ev.get("pct", 0),
                    "sub_pct": ev.get("sub_pct", 0),
                })}
            elif et == "error":
                log_emit("error", ev["data"], "webup", source="webup")
                yield {"event": "error", "data": ev["data"]}
            elif et == "done":
                code = ev.get("exit_code", -1)
                state["exit_code"] = code
                await update_exit_code(state["path"], code)
                log_emit(
                    "ok" if code == 0 else "error",
                    f"webup exit {code}", "quickupload",
                )
                yield {"event": "done", "data": json.dumps({"exit_code": code})}

    return EventSourceResponse(gen())
