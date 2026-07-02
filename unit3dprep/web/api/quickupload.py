"""Quick upload (UploadModal flow) — wraps Unit3DWebUp without the full wizard.

Takes a path + mode (u|f|scan), drives the webup HTTP API, streams logs via SSE.
No audio check, no TMDB lookup. For single-file (``u``) and folder (``f``)
uploads the selected item is hardlinked into a dedicated per-job sandbox
(``<seedings>/.unit3dprep/<jobid>/``) — optionally renamed — so webup's
``/scan`` (which processes the whole SCAN_PATH) only ever sees the item the
user picked, never its unrelated siblings. Recursive ``scan`` is left as a
raw batch over the chosen directory. A DB record is created at hardlink time
and its exit code updated on done.
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

from ...core import VIDEO_EXTENSIONS, iter_video_files
from ...i18n import get_request_lang, t
from ...upload import do_hardlink_movie, do_hardlink_series
from ..db import record_upload, update_exit_code
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


def _sanitize_base(name: str) -> str:
    """Normalise a user-typed rename into a base name (strip slashes + ext)."""
    name = name.strip().strip("/\\")
    p = Path(name)
    if p.suffix.lower() in VIDEO_EXTENSIONS:
        name = p.stem
    return name.strip()


def _prepare_sandbox(path: str, mode: str, final_name: str) -> tuple[str, str, str]:
    """Hardlink the picked item into its per-job sandbox for an isolated /scan.

    Returns ``(seeding_path, source_path, base_name)``. The sandbox lives at
    ``<seedings>/.unit3dprep/<jobid>/`` so webup only ever scans this one item.
    Raises ``ValueError`` on a bad selection.
    """
    src = Path(path)
    if mode == "f":
        if not src.is_dir():
            raise ValueError("folder mode requires a directory")
        base = _sanitize_base(final_name) or src.name
        target = do_hardlink_series(src, base, {})
        return str(target), str(src.resolve()), base
    # mode == "u": single video file
    if src.is_dir():
        src_file = next(iter(iter_video_files(src)), None)
        if src_file is None:
            raise ValueError("no video file in selected folder")
    else:
        src_file = src
    base = _sanitize_base(final_name) or src_file.stem
    target = do_hardlink_movie(src_file, base)
    return str(target), str(src_file.resolve()), base


class QuickBody(BaseModel):
    path: str
    mode: str = "u"            # u|f|scan
    tracker: str = "ITT"
    tmdb_id: str = ""
    final_name: str = ""       # rename target (base name, no ext) for u/f
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
        "final_name": body.final_name.strip(),
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
        final_name: str = state.get("final_name", "")
        loop = asyncio.get_event_loop()
        try:
            seeding_path, source_path, base = await loop.run_in_executor(
                None, _prepare_sandbox, path, mode, final_name
            )
        except Exception as e:
            log_emit("error", f"hardlink failed: {e}", "quickupload")
            yield {"event": "error", "data": str(e)}
            yield {"event": "done", "data": json.dumps({"exit_code": 1})}
            return
        state["seeding_path"] = seeding_path
        log_emit("ok", f"Hardlink → {seeding_path}", "quickupload")
        yield {"event": "log", "data": f"hardlink → {seeding_path}"}
        await record_upload(
            category="", kind=kind,
            source_path=source_path, seeding_path=seeding_path,
            tmdb_id=tmdb_id, final_name=base,
        )
        async for ev in stream_webup(
            client=app.state.webup,
            ws=app.state.webup_ws,
            scan_lock=app.state.webup_scan_lock,
            seeding_path=seeding_path,
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
                await update_exit_code(seeding_path, code)
                log_emit(
                    "ok" if code == 0 else "error",
                    f"webup exit {code}", "quickupload",
                )
                yield {"event": "done", "data": json.dumps({"exit_code": code})}

    return EventSourceResponse(gen())
