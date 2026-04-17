"""Wizard upload flow: audio check → TMDB → names → hardlink → upload."""
import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from ...core import tmdb_fetch, tmdb_poster_url, tmdb_year
from ..templates_env import ROOT_PATH, templates
from ...upload import (
    build_episode_names,
    build_movie_name_from_file,
    do_hardlink_movie,
    do_hardlink_series,
    stream_unit3dup,
)
from ..auth import get_session_id
from ..db import record_upload, update_exit_code

router = APIRouter()

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

# In-memory wizard state: token → state dict
_wizard_sessions: dict[str, dict] = {}
_wizard_created: dict[str, float] = {}
_TTL = 3600


def _cleanup_sessions():
    now = time.time()
    expired = [t for t, ct in _wizard_created.items() if now - ct > _TTL]
    for t in expired:
        _wizard_sessions.pop(t, None)
        _wizard_created.pop(t, None)


def _create_session(state: dict) -> str:
    _cleanup_sessions()
    token = secrets.token_urlsafe(24)
    _wizard_sessions[token] = state
    _wizard_created[token] = time.time()
    return token


def _get_session(token: str) -> dict:
    s = _wizard_sessions.get(token)
    if s is None:
        raise HTTPException(404, "Wizard session not found or expired")
    return s


def _validate_media_path(path_str: str) -> Path:
    """Ensure path is within ~/media or ~/seedings to prevent traversal."""
    p = Path(path_str).resolve()
    media = (Path.home() / "media").resolve()
    seedings = (Path.home() / "seedings").resolve()
    if not (str(p).startswith(str(media)) or str(p).startswith(str(seedings))):
        raise HTTPException(403, "Path outside allowed directories")
    if not p.exists():
        raise HTTPException(404, f"Path not found: {p}")
    return p


# ---------------------------------------------------------------------------
# Start wizard
# ---------------------------------------------------------------------------

@router.post("/wizard/start")
async def wizard_start(
    request: Request,
    path: str = Form(...),
    category: str = Form(...),
    kind: str = Form(...),
    tmdb_id: str = Form(""),
    tmdb_kind: str = Form(""),
):
    abs_path = _validate_media_path(path)
    token = _create_session({
        "path": str(abs_path),
        "category": category,
        "kind": kind,
        "step": "audio",
        "audio_ok": False,
        "tmdb_id": tmdb_id.strip(),
        "tmdb_kind": tmdb_kind.strip() or ("tv" if kind == "series" else "movie"),
        "tmdb_title": "",
        "tmdb_year": "",
        "tmdb_poster": "",
        "final_names": {},       # file_path_str → new_base_name
        "folder_name": "",
        "seeding_path": "",
        "upload_done": False,
        "exit_code": None,
    })
    return HTMLResponse(
        status_code=303,
        headers={"Location": f"{ROOT_PATH}/wizard/{token}"},
    )


# ---------------------------------------------------------------------------
# Step 1: Audio check
# ---------------------------------------------------------------------------

@router.get("/wizard/{token}", response_class=HTMLResponse)
async def wizard_step1(request: Request, token: str):
    state = _get_session(token)
    return templates.TemplateResponse(request, "wizard.html", {
        "token": token,
        "state": state,
        "step": "audio",
        "active": state["category"],
    })


@router.get("/wizard/{token}/stream/audio")
async def wizard_audio_stream(request: Request, token: str):
    state = _get_session(token)
    path = Path(state["path"])

    from ...core import has_italian_audio, iter_video_files, VIDEO_EXTENSIONS
    if path.is_file():
        video_files = [path]
    else:
        video_files = list(iter_video_files(path))

    async def generate() -> AsyncGenerator[dict, None]:
        all_ok = True
        loop = asyncio.get_event_loop()
        for f in video_files:
            try:
                ok = await loop.run_in_executor(None, has_italian_audio, f)
            except Exception as e:
                ok = False
                yield {
                    "event": "file_result",
                    "data": json.dumps({"file": f.name, "ok": False, "error": str(e)}),
                }
                all_ok = False
                continue
            if not ok:
                all_ok = False
            yield {
                "event": "file_result",
                "data": json.dumps({"file": f.name, "ok": ok}),
            }
            await asyncio.sleep(0)  # yield control

        state["audio_ok"] = all_ok
        state["step"] = "tmdb" if all_ok else "audio_failed"
        yield {
            "event": "done",
            "data": json.dumps({"all_ok": all_ok, "total": len(video_files)}),
        }

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Step 2a: TMDB form (GET, loaded by HTMX after SSE audio done)
# ---------------------------------------------------------------------------

@router.get("/wizard/{token}/tmdb-form", response_class=HTMLResponse)
async def wizard_tmdb_form(request: Request, token: str):
    state = _get_session(token)
    return templates.TemplateResponse(request, "wizard_fragments/tmdb_form.html", {
        "token": token,
        "state": state,
        "tmdb_error": "",
    })


# ---------------------------------------------------------------------------
# Step 2b: TMDB lookup
# ---------------------------------------------------------------------------

@router.post("/wizard/{token}/tmdb", response_class=HTMLResponse)
async def wizard_tmdb(
    request: Request,
    token: str,
    tmdb_id: str = Form(...),
    tmdb_kind: str = Form("movie"),
):
    state = _get_session(token)
    if not state.get("audio_ok"):
        raise HTTPException(400, "Audio check not passed")

    loop = asyncio.get_event_loop()
    try:
        tmdb_data = await loop.run_in_executor(
            None, tmdb_fetch, tmdb_kind, tmdb_id, TMDB_API_KEY
        )
    except Exception as e:
        return templates.TemplateResponse(request, "wizard_fragments/tmdb_form.html", {
            "token": token,
            "state": state,
            "tmdb_error": str(e),
        })

    title = tmdb_data.get("title") or tmdb_data.get("name") or ""
    year = tmdb_year(tmdb_data, tmdb_kind)
    poster = tmdb_poster_url(tmdb_data)

    state["tmdb_id"] = tmdb_id
    state["tmdb_kind"] = tmdb_kind
    state["tmdb_title"] = title
    state["tmdb_year"] = year
    state["tmdb_poster"] = poster
    state["tmdb_data"] = {
        "title": title,
        "year": year,
        "overview": tmdb_data.get("overview", "")[:300],
        "poster": poster,
    }
    state["step"] = "names"

    # Build proposed names
    path = Path(state["path"])
    kind = state["kind"]

    from ...core import iter_video_files
    from guessit import guessit

    if kind == "movie":
        if path.is_file():
            video_files = [path]
        else:
            video_files = list(iter_video_files(path))
        proposed: dict[str, str] = {}
        for vf in video_files:
            loop2 = asyncio.get_event_loop()
            name = await loop2.run_in_executor(
                None, build_movie_name_from_file, vf, title, year
            )
            proposed[str(vf)] = name
    else:
        # series / season folder
        from guessit import guessit as _guessit
        folder_guess = dict(_guessit(path.name))
        video_files = list(iter_video_files(path))
        loop3 = asyncio.get_event_loop()
        proposed = await loop3.run_in_executor(
            None,
            lambda: {str(k): v for k, v in build_episode_names(
                path, video_files, title, year, folder_guess
            ).items()},
        )
        # Compute folder name from first file specs
        if video_files:
            from ...core import extract_specs, map_source, build_name
            first = video_files[0]
            g = dict(_guessit(first.name))
            specs = extract_specs(first)
            source, src_type = map_source(g)
            tag = g.get("release_group", "") or folder_guess.get("release_group", "") or ""
            folder_nm = build_name(title=title, year=year, se="",
                                   specs=specs, source=source, src_type=src_type, tag=tag)
            state["folder_name"] = folder_nm

    state["final_names"] = proposed

    return templates.TemplateResponse(request, "wizard_fragments/names_form.html", {
        "token": token,
        "state": state,
        "proposed": proposed,
    })


# ---------------------------------------------------------------------------
# Step 3: Confirm / edit names
# ---------------------------------------------------------------------------

@router.post("/wizard/{token}/names", response_class=HTMLResponse)
async def wizard_names(request: Request, token: str):
    state = _get_session(token)
    form = await request.form()

    # Collect edited names
    new_names: dict[str, str] = {}
    for key, val in form.items():
        if key.startswith("name_"):
            file_path = key[5:]  # strip "name_" prefix
            new_names[file_path] = str(val).strip()

    folder_name = str(form.get("folder_name", state.get("folder_name", ""))).strip()

    state["final_names"] = new_names
    if folder_name:
        state["folder_name"] = folder_name
    state["step"] = "hardlink"

    return templates.TemplateResponse(request, "wizard_fragments/hardlink_confirm.html", {
        "token": token,
        "state": state,
    })


# ---------------------------------------------------------------------------
# Step 4: Execute hardlink
# ---------------------------------------------------------------------------

@router.post("/wizard/{token}/hardlink", response_class=HTMLResponse)
async def wizard_hardlink(request: Request, token: str):
    state = _get_session(token)
    path = Path(state["path"])
    kind = state["kind"]
    final_names = state["final_names"]

    errors: list[str] = []
    seeding_path = ""

    try:
        loop = asyncio.get_event_loop()
        if kind == "movie":
            if path.is_file():
                src_file = path
            else:
                from ...core import iter_video_files
                files = list(iter_video_files(path))
                src_file = files[0] if files else path
            final_name = next(iter(final_names.values()), src_file.stem)
            target = await loop.run_in_executor(
                None, do_hardlink_movie, src_file, final_name
            )
            seeding_path = str(target)
        else:
            # series
            from ...core import iter_video_files
            video_files = list(iter_video_files(path))
            episode_rename = {Path(k): v for k, v in final_names.items()}
            folder_name = state.get("folder_name", path.name)
            target = await loop.run_in_executor(
                None, do_hardlink_series, path, folder_name, episode_rename
            )
            seeding_path = str(target)

        state["seeding_path"] = seeding_path
        state["step"] = "upload"

        # Pre-record in DB (without exit code)
        await record_upload(
            category=state["category"],
            kind=kind,
            source_path=str(path),
            seeding_path=seeding_path,
            tmdb_id=state.get("tmdb_id", ""),
            title=state.get("tmdb_title", ""),
            year=state.get("tmdb_year", ""),
            final_name=state.get("folder_name") or next(iter(final_names.values()), ""),
        )

    except Exception as e:
        errors.append(str(e))

    return templates.TemplateResponse(request, "wizard_fragments/upload_confirm.html", {
        "token": token,
        "state": state,
        "seeding_path": seeding_path,
        "errors": errors,
    })


# ---------------------------------------------------------------------------
# Step 5: Upload stream (SSE)
# ---------------------------------------------------------------------------

@router.get("/wizard/{token}/stream/upload")
async def wizard_upload_stream(request: Request, token: str):
    state = _get_session(token)
    seeding_path = state.get("seeding_path", "")
    kind = state["kind"]

    if not seeding_path:
        async def _err():
            yield {"event": "error", "data": "No seeding path set"}
        return EventSourceResponse(_err())

    args = ["-b", "-u" if kind == "movie" else "-f", seeding_path]
    tmdb_id = state.get("tmdb_id", "")

    # One queue per upload session; POST /wizard/{token}/stdin puts values here.
    input_queue: asyncio.Queue = asyncio.Queue()
    state["stdin_queue"] = input_queue

    async def generate() -> AsyncGenerator[dict, None]:
        exit_code = 0
        async for event in stream_unit3dup(args, input_queue=input_queue, tmdb_id=tmdb_id):
            if event["type"] == "log":
                yield {"event": "log", "data": event["data"]}
            elif event["type"] == "input_needed":
                yield {"event": "input_needed", "data": event["data"]}
            elif event["type"] == "error":
                yield {"event": "error", "data": event["data"]}
            elif event["type"] == "done":
                exit_code = event.get("exit_code", -1)
                state["exit_code"] = exit_code
                state["upload_done"] = True
                state.pop("stdin_queue", None)
                await update_exit_code(seeding_path, exit_code)
                yield {
                    "event": "done",
                    "data": json.dumps({"exit_code": exit_code}),
                }

    return EventSourceResponse(generate())


@router.post("/wizard/{token}/stdin")
async def wizard_stdin(token: str, request: Request):
    """Forward user input to the running unit3dup subprocess stdin."""
    state = _get_session(token)
    q: asyncio.Queue | None = state.get("stdin_queue")
    if q is None:
        return JSONResponse({"error": "no active process"}, status_code=400)
    body = await request.json()
    value = str(body.get("value", "0")).strip() or "0"
    await q.put(value)
    return JSONResponse({"ok": True})
