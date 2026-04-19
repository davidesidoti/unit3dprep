"""Quick upload (UploadModal flow) — wraps unit3dup without the full wizard.

Takes a path + mode (u|f|scan), invokes unit3dup directly, streams logs via SSE.
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

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...upload import stream_unit3dup
from ..db import record_upload, update_exit_code
from ..logbuf import emit as log_emit

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
async def create(body: QuickBody):
    p = Path(body.path).resolve()
    if not p.exists():
        raise HTTPException(404, "Path not found")
    if body.mode not in {"u", "f", "scan"}:
        raise HTTPException(400, "Invalid mode")
    args = ["-b"]
    flag = {"u": "-u", "f": "-f", "scan": "-scan"}[body.mode]
    args += [flag, str(p)]
    _cleanup()
    job_id = secrets.token_urlsafe(16)
    _jobs[job_id] = {"args": args, "path": str(p), "tmdb_id": body.tmdb_id}
    _created[job_id] = time.time()
    return JSONResponse({"job": job_id})


@router.get("/upload/{job}/stream")
async def stream(job: str):
    state = _jobs.get(job)
    if state is None:
        raise HTTPException(404, "Job not found")
    args: list[str] = state["args"]
    tmdb_id: str = state.get("tmdb_id", "")
    q: asyncio.Queue = asyncio.Queue()
    state["stdin_queue"] = q

    async def gen() -> AsyncGenerator[dict, None]:
        async for ev in stream_unit3dup(args, input_queue=q, tmdb_id=tmdb_id):
            et = ev["type"]
            if et == "log":
                log_emit("info", ev["data"], "unit3dup")
                yield {"event": "log", "data": ev["data"]}
            elif et == "progress":
                yield {"event": "progress", "data": ev["data"]}
            elif et == "input_needed":
                yield {
                    "event": "input_needed",
                    "data": json.dumps({"text": ev["data"], "kind": ev.get("kind", "tmdb")}),
                }
            elif et == "error":
                log_emit("error", ev["data"], "unit3dup")
                yield {"event": "error", "data": ev["data"]}
            elif et == "done":
                code = ev.get("exit_code", -1)
                state["exit_code"] = code
                state.pop("stdin_queue", None)
                await update_exit_code(state["path"], code)
                log_emit(
                    "ok" if code == 0 else "error",
                    f"unit3dup exit {code}", "quickupload",
                )
                yield {"event": "done", "data": json.dumps({"exit_code": code})}

    return EventSourceResponse(gen())


class StdinBody(BaseModel):
    value: str = "0"


@router.post("/upload/{job}/stdin")
async def stdin(job: str, body: StdinBody):
    state = _jobs.get(job)
    if state is None:
        raise HTTPException(404, "Job not found")
    q: asyncio.Queue | None = state.get("stdin_queue")
    if q is None:
        raise HTTPException(400, "No active process")
    await q.put((body.value or "0").strip() or "0")
    return JSONResponse({"ok": True})
