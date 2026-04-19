"""Wizard upload flow: audio → TMDB → names → hardlink → upload (SSE)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...core import (
    extract_specs,
    has_italian_audio,
    iter_video_files,
    map_source,
    tmdb_fetch_bilingual,
    tmdb_poster_url,
    tmdb_year,
    build_name,
)
from ...upload import (
    build_episode_names,
    build_movie_name_from_file,
    do_hardlink_movie,
    do_hardlink_series,
    stream_unit3dup,
)
from ..db import record_upload, update_exit_code
from ..logbuf import emit as log_emit

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

router = APIRouter(prefix="/api", tags=["wizard"])

_sessions: dict[str, dict[str, Any]] = {}
_created: dict[str, float] = {}
_TTL = 3600


def _cleanup():
    now = time.time()
    for t in [t for t, ct in _created.items() if now - ct > _TTL]:
        _sessions.pop(t, None)
        _created.pop(t, None)


def _create(state: dict[str, Any]) -> str:
    _cleanup()
    tok = secrets.token_urlsafe(24)
    _sessions[tok] = state
    _created[tok] = time.time()
    return tok


def _get(tok: str) -> dict[str, Any]:
    s = _sessions.get(tok)
    if s is None:
        raise HTTPException(404, "Wizard session not found or expired")
    return s


def _validate_path(p: str) -> Path:
    from ...media import media_root, seedings_root
    resolved = Path(p).resolve()
    allowed = [media_root().resolve(), seedings_root().resolve()]
    if not any(str(resolved).startswith(str(a)) for a in allowed):
        raise HTTPException(403, "Path outside allowed directories")
    if not resolved.exists():
        raise HTTPException(404, f"Path not found: {resolved}")
    return resolved


# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------


class StartBody(BaseModel):
    path: str
    category: str
    kind: str              # movie|series|episode
    tmdb_id: str = ""
    tmdb_kind: str = ""
    hardlink_only: bool = False


class TmdbBody(BaseModel):
    tmdb_id: str
    tmdb_kind: str = "movie"


class NamesBody(BaseModel):
    final_names: dict[str, str]
    folder_name: str = ""


class StdinBody(BaseModel):
    value: str = "0"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/wizard/start")
async def wizard_start(body: StartBody):
    p = _validate_path(body.path)
    if body.kind not in {"movie", "series", "episode"}:
        raise HTTPException(400, "Invalid kind")
    if body.kind == "episode" and not p.is_file():
        raise HTTPException(400, "Episode mode requires a file path")
    state: dict[str, Any] = {
        "path": str(p),
        "category": body.category,
        "kind": body.kind,
        "step": "audio",
        "audio_ok": False,
        "audio_override": False,
        "tmdb_id": body.tmdb_id.strip(),
        "tmdb_kind": body.tmdb_kind or ("tv" if body.kind != "movie" else "movie"),
        "tmdb_title": "",
        "tmdb_year": "",
        "tmdb_poster": "",
        "tmdb_overview": "",
        "final_names": {},
        "folder_name": "",
        "seeding_path": "",
        "upload_done": False,
        "exit_code": None,
        "hardlink_only": body.hardlink_only,
    }
    tok = _create(state)
    return JSONResponse({"token": tok, "state": state})


@router.get("/wizard/{tok}")
async def wizard_state(tok: str):
    return JSONResponse(_get(tok))


@router.get("/wizard/{tok}/audio")
async def wizard_audio(tok: str):
    state = _get(tok)
    path = Path(state["path"])
    files = [path] if path.is_file() else list(iter_video_files(path))

    async def generate() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()
        all_ok = True
        for f in files:
            try:
                ok = await loop.run_in_executor(None, has_italian_audio, f)
                payload = {"file": f.name, "ok": ok}
            except Exception as e:
                ok = False
                payload = {"file": f.name, "ok": False, "error": str(e)}
            if not ok:
                all_ok = False
            yield {"event": "file_result", "data": json.dumps(payload)}
            await asyncio.sleep(0)
        state["audio_ok"] = all_ok
        state["step"] = "tmdb" if all_ok else "audio_failed"
        yield {"event": "done", "data": json.dumps({"all_ok": all_ok, "total": len(files)})}

    return EventSourceResponse(generate())


@router.post("/wizard/{tok}/audio-override")
async def wizard_audio_override(tok: str):
    state = _get(tok)
    state["audio_ok"] = True
    state["audio_override"] = True
    state["step"] = "tmdb"
    return JSONResponse({"ok": True})


@router.post("/wizard/{tok}/tmdb")
async def wizard_tmdb(tok: str, body: TmdbBody):
    state = _get(tok)
    if not state["audio_ok"]:
        raise HTTPException(400, "Audio check not passed")
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(
            None, tmdb_fetch_bilingual, body.tmdb_kind, body.tmdb_id, TMDB_API_KEY
        )
    except Exception as e:
        raise HTTPException(502, f"TMDB fetch failed: {e}")
    title = data.get("title") or ""
    year = tmdb_year(data, body.tmdb_kind)
    state["tmdb_id"] = body.tmdb_id
    state["tmdb_kind"] = body.tmdb_kind
    state["tmdb_title"] = title
    state["tmdb_year"] = year
    state["tmdb_poster"] = tmdb_poster_url(data)
    state["tmdb_overview"] = (data.get("overview") or "")[:300]
    state["step"] = "names"

    proposed = await _build_proposed_names(state)
    state["final_names"] = proposed
    return JSONResponse({
        "ok": True,
        "tmdb": {
            "title": title,
            "title_en": data.get("title_en", ""),
            "original_title": data.get("original_title", ""),
            "year": year,
            "overview": state["tmdb_overview"],
            "overview_en": (data.get("overview_en") or "")[:300],
            "poster": state["tmdb_poster"],
        },
        "proposed": proposed,
        "folder_name": state["folder_name"],
    })


async def _build_proposed_names(state: dict[str, Any]) -> dict[str, str]:
    from guessit import guessit as _guessit
    loop = asyncio.get_event_loop()
    path = Path(state["path"])
    kind = state["kind"]
    title = state["tmdb_title"]
    year = state["tmdb_year"]
    if kind == "movie":
        files = [path] if path.is_file() else list(iter_video_files(path))
        proposed: dict[str, str] = {}
        for vf in files:
            name = await loop.run_in_executor(
                None, build_movie_name_from_file, vf, title, year
            )
            proposed[str(vf)] = name
        return proposed
    if kind == "episode":
        files = [path] if path.is_file() else list(iter_video_files(path))
        if not files:
            raise HTTPException(400, "No video file found for episode mode")
        episode_file = files[0]
        season_folder = episode_file.parent
        folder_guess = dict(_guessit(season_folder.name))
        result = await loop.run_in_executor(
            None,
            lambda: {str(k): v for k, v in build_episode_names(
                season_folder, [episode_file], title, year, folder_guess
            ).items()},
        )
        if not result:
            fallback = await loop.run_in_executor(
                None, build_movie_name_from_file, episode_file, title, year
            )
            result = {str(episode_file): fallback}
        return result
    # series
    folder_guess = dict(_guessit(path.name))
    files = list(iter_video_files(path))
    result = await loop.run_in_executor(
        None,
        lambda: {str(k): v for k, v in build_episode_names(
            path, files, title, year, folder_guess
        ).items()},
    )
    if files:
        first = files[0]
        g = dict(_guessit(first.name))
        specs = extract_specs(first)
        source, src_type = map_source(g)
        tag = g.get("release_group", "") or folder_guess.get("release_group", "") or ""
        folder_nm = build_name(
            title=title, year=year, se="",
            specs=specs, source=source, src_type=src_type, tag=tag,
        )
        state["folder_name"] = folder_nm
    return result


@router.post("/wizard/{tok}/names")
async def wizard_names(tok: str, body: NamesBody):
    state = _get(tok)
    state["final_names"] = {k: v.strip() for k, v in body.final_names.items()}
    if body.folder_name:
        state["folder_name"] = body.folder_name.strip()
    state["step"] = "hardlink"
    return JSONResponse({"ok": True})


@router.post("/wizard/{tok}/hardlink")
async def wizard_hardlink(tok: str):
    state = _get(tok)
    path = Path(state["path"])
    kind = state["kind"]
    final_names = state["final_names"]
    loop = asyncio.get_event_loop()
    try:
        if kind == "movie":
            if path.is_file():
                src = path
            else:
                files = list(iter_video_files(path))
                if not files:
                    raise HTTPException(400, "No video file found")
                src = files[0]
            final_name = next(iter(final_names.values()), src.stem)
            target = await loop.run_in_executor(None, do_hardlink_movie, src, final_name)
            state["seeding_path"] = str(target)
            source_path = str(path.resolve())
        elif kind == "episode":
            src = path if path.is_file() else list(iter_video_files(path))[0]
            final_name = next(iter(final_names.values()), src.stem)
            target = await loop.run_in_executor(None, do_hardlink_movie, src, final_name)
            state["seeding_path"] = str(target)
            source_path = str(src.resolve())
        else:
            rename = {Path(k): v for k, v in final_names.items()}
            folder = state.get("folder_name", path.name)
            target = await loop.run_in_executor(None, do_hardlink_series, path, folder, rename)
            state["seeding_path"] = str(target)
            source_path = str(path.resolve())
        state["step"] = "upload"
        await record_upload(
            category=state["category"], kind=kind,
            source_path=source_path, seeding_path=state["seeding_path"],
            tmdb_id=state.get("tmdb_id", ""),
            title=state.get("tmdb_title", ""),
            year=state.get("tmdb_year", ""),
            final_name=state.get("folder_name") or next(iter(final_names.values()), ""),
            hardlink_only=state.get("hardlink_only", False),
        )
        log_emit("ok", f"Hardlink done → {state['seeding_path']}", "wizard")
        return JSONResponse({"ok": True, "seeding_path": state["seeding_path"]})
    except HTTPException:
        raise
    except Exception as e:
        log_emit("error", f"Hardlink failed: {e}", "wizard")
        raise HTTPException(500, f"Hardlink failed: {e}")


@router.get("/wizard/{tok}/upload")
async def wizard_upload(tok: str):
    state = _get(tok)
    seeding_path = state.get("seeding_path", "")
    if not seeding_path:
        async def _err():
            yield {"event": "error", "data": "No seeding path set"}
        return EventSourceResponse(_err())
    kind = state["kind"]
    args = ["-b", "-u" if kind in {"movie", "episode"} else "-f", seeding_path]
    q: asyncio.Queue = asyncio.Queue()
    state["stdin_queue"] = q
    tmdb_id = state.get("tmdb_id", "")

    async def generate() -> AsyncGenerator[dict, None]:
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
                state["upload_done"] = True
                state.pop("stdin_queue", None)
                await update_exit_code(seeding_path, code)
                log_emit(
                    "ok" if code == 0 else "error",
                    f"unit3dup exit {code}", "wizard",
                )
                yield {"event": "done", "data": json.dumps({"exit_code": code})}

    return EventSourceResponse(generate())


@router.post("/wizard/{tok}/stdin")
async def wizard_stdin(tok: str, body: StdinBody):
    state = _get(tok)
    q: asyncio.Queue | None = state.get("stdin_queue")
    if q is None:
        return JSONResponse({"error": "no active process"}, status_code=400)
    await q.put((body.value or "0").strip() or "0")
    return JSONResponse({"ok": True})


@router.post("/wizard/{tok}/finish-hardlink")
async def wizard_finish(tok: str):
    state = _get(tok)
    state["upload_done"] = True
    state["exit_code"] = 0
    seeding_path = state.get("seeding_path", "")
    if seeding_path:
        await update_exit_code(seeding_path, 0)
    return JSONResponse({"ok": True})
