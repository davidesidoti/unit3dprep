"""Wizard upload flow: audio → TMDB → names → hardlink → upload (SSE)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...core import (
    extract_specs,
    audio_and_subtitle_languages,
    iter_video_files,
    map_source,
    tmdb_fetch_bilingual,
    tmdb_poster_url,
    tmdb_year,
    build_name,
)
from ...upload import (
    build_episode_names_detailed,
    build_movie_name_from_file_detailed,
    do_hardlink_movie,
    do_hardlink_series,
)
from ...i18n import get_request_lang, t as _i18n_t
from .. import config as web_config
from ..db import record_upload, update_exit_code
from ..tocheck import add_flag
from ..duplicate_check import find_duplicate
from ..logbuf import emit as log_emit
from ..webup_orchestrator import stream_webup

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


def _get(tok: str, lang: str | None = None) -> dict[str, Any]:
    s = _sessions.get(tok)
    if s is None:
        raise HTTPException(404, _i18n_t("err.wizard_session_expired", lang))
    return s


def _validate_path(p: str, lang: str | None = None) -> Path:
    from ...media import media_root, seedings_root
    resolved = Path(p).resolve()
    allowed = [media_root().resolve(), seedings_root().resolve()]
    if not any(str(resolved).startswith(str(a)) for a in allowed):
        raise HTTPException(403, _i18n_t("err.path_outside", lang))
    if not resolved.exists():
        raise HTTPException(404, _i18n_t("err.path_not_found_at", lang, path=str(resolved)))
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/wizard/start")
async def wizard_start(request: Request, body: StartBody):
    lang = get_request_lang(request)
    p = _validate_path(body.path, lang)
    if body.kind not in {"movie", "series", "episode"}:
        raise HTTPException(400, _i18n_t("err.invalid_kind", lang))
    if body.kind == "episode" and not p.is_file():
        raise HTTPException(400, _i18n_t("err.episode_requires_file", lang))
    state: dict[str, Any] = {
        "path": str(p),
        "category": body.category,
        "kind": body.kind,
        "step": "audio",
        "audio_ok": False,
        "audio_override": False,
        "non_ita_paths": [],
        "tmdb_id": body.tmdb_id.strip(),
        "tmdb_kind": body.tmdb_kind or ("tv" if body.kind != "movie" else "movie"),
        "tmdb_title": "",
        "tmdb_year": "",
        "tmdb_poster": "",
        "tmdb_overview": "",
        "final_names": {},
        "file_specs": {},
        "folder_name": "",
        "seeding_path": "",
        "upload_done": False,
        "exit_code": None,
        "hardlink_only": body.hardlink_only,
        "duplicate": None,
        "duplicate_confirmed": False,
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
    state["audio_total"] = len(files)

    async def generate() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()
        all_ok = True
        non_ita: list[str] = []
        ita_sub_paths: list[str] = []
        for f in files:
            try:
                audio_langs, sub_langs = await loop.run_in_executor(
                    None, audio_and_subtitle_languages, f)
                ok = "ITA" in audio_langs
                sub_ita = "ITA" in sub_langs
                payload = {"file": f.name, "ok": ok, "subs": sub_langs, "sub_ita": sub_ita}
            except Exception as e:
                ok = False
                sub_ita = False
                payload = {"file": f.name, "ok": False, "subs": [], "sub_ita": False, "error": str(e)}
            if not ok:
                all_ok = False
                non_ita.append(str(f))
                if sub_ita:
                    ita_sub_paths.append(str(f))
            yield {"event": "file_result", "data": json.dumps(payload)}
            await asyncio.sleep(0)
        state["audio_ok"] = all_ok
        state["non_ita_paths"] = non_ita
        state["ita_sub_paths"] = ita_sub_paths
        state["step"] = "tmdb" if all_ok else "audio_failed"
        yield {"event": "done", "data": json.dumps({
            "all_ok": all_ok, "total": len(files), "has_ita_subs": len(ita_sub_paths) > 0,
        })}

    return EventSourceResponse(generate())


@router.post("/wizard/{tok}/audio-override")
async def wizard_audio_override(tok: str):
    state = _get(tok)
    state["audio_ok"] = True
    state["audio_override"] = True
    state["step"] = "tmdb"
    return JSONResponse({"ok": True})


@router.post("/wizard/{tok}/audio-to-check")
async def wizard_audio_to_check(tok: str):
    """Flag the non-Italian files found during the audio scan as "to-check"
    (deferred), then the wizard is closed by the FE.
    - Movie → flag the movie root (matches the library item path).
    - Series/season pack where **every** scanned episode lacks ITA → flag the
      whole season/series folder in one shot (`state["path"]`) instead of each
      episode, so the library shows the season as flagged.
    - Otherwise (some episodes ITA, some not) → flag each non-ITA episode file."""
    state = _get(tok)
    non_ita = state.get("non_ita_paths", [])
    if not non_ita:
        return JSONResponse({"ok": True, "flagged": 0})
    category = state["category"]
    kind = state["kind"]
    if kind == "movie":
        await add_flag(str(Path(state["path"]).resolve()), category, "movie")
        return JSONResponse({"ok": True, "flagged": 1, "scope": "movie"})
    total = state.get("audio_total", 0)
    if kind == "series" and total > 0 and len(non_ita) >= total:
        await add_flag(str(Path(state["path"]).resolve()), category, "series")
        return JSONResponse({"ok": True, "flagged": 1, "scope": "season"})
    for p in non_ita:
        await add_flag(str(Path(p).resolve()), category, "episode")
    return JSONResponse({"ok": True, "flagged": len(non_ita), "scope": "episodes"})


@router.post("/wizard/{tok}/tmdb")
async def wizard_tmdb(request: Request, tok: str, body: TmdbBody):
    lang = get_request_lang(request)
    state = _get(tok, lang)
    if not state["audio_ok"]:
        raise HTTPException(400, _i18n_t("err.audio_check_not_passed", lang))
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(
            None, tmdb_fetch_bilingual, body.tmdb_kind, body.tmdb_id, TMDB_API_KEY
        )
    except Exception as e:
        raise HTTPException(502, _i18n_t("err.tmdb_fetch_failed", lang, error=str(e)))
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
        "file_specs": state["file_specs"],
        "folder_name": state["folder_name"],
    })


async def _build_proposed_names(state: dict[str, Any]) -> dict[str, str]:
    """Propose a final name per video file and record each file's media profile.

    `state["file_specs"]` maps file path → technical profile (resolution, codec,
    source, …) so the names step can flag the odd file out inside a pack.
    """
    from guessit import guessit as _guessit
    loop = asyncio.get_event_loop()
    path = Path(state["path"])
    kind = state["kind"]
    title = state["tmdb_title"]
    year = state["tmdb_year"]
    specs_map: dict[str, dict[str, str]] = {}
    state["file_specs"] = specs_map
    if kind == "movie":
        files = [path] if path.is_file() else list(iter_video_files(path))
        proposed: dict[str, str] = {}
        for vf in files:
            name, profile = await loop.run_in_executor(
                None, build_movie_name_from_file_detailed, vf, title, year
            )
            proposed[str(vf)] = name
            specs_map[str(vf)] = profile
        return proposed
    if kind == "episode":
        files = [path] if path.is_file() else list(iter_video_files(path))
        if not files:
            raise HTTPException(400, _i18n_t("err.no_video_episode"))
        episode_file = files[0]
        season_folder = episode_file.parent
        folder_guess = dict(_guessit(season_folder.name))
        detailed = await loop.run_in_executor(
            None,
            lambda: {str(k): v for k, v in build_episode_names_detailed(
                season_folder, [episode_file], title, year, folder_guess
            ).items()},
        )
        result = {k: name for k, (name, _) in detailed.items()}
        specs_map.update({k: profile for k, (_, profile) in detailed.items()})
        if not result:
            fallback, profile = await loop.run_in_executor(
                None, build_movie_name_from_file_detailed, episode_file, title, ""
            )
            result = {str(episode_file): fallback}
            specs_map[str(episode_file)] = profile
        return result
    # series
    folder_guess = dict(_guessit(path.name))
    files = list(iter_video_files(path))
    detailed = await loop.run_in_executor(
        None,
        lambda: {str(k): v for k, v in build_episode_names_detailed(
            path, files, title, year, folder_guess
        ).items()},
    )
    result = {k: name for k, (name, _) in detailed.items()}
    specs_map.update({k: profile for k, (_, profile) in detailed.items()})
    if files:
        first = files[0]
        g = dict(_guessit(first.name))
        specs = extract_specs(first)
        source, src_type = map_source(g)
        tag = g.get("release_group", "") or folder_guess.get("release_group", "") or ""
        # Season-pack folder name: include "S<NN>" right after the title.
        # Prefer the season inferred from the first episode's filename;
        # fall back to the folder's own guessit (`Season 1`, `S01`, etc.).
        season = g.get("season") if g.get("season") is not None else folder_guess.get("season")
        if isinstance(season, list):
            season = season[0] if season else None
        season_label = f"S{int(season):02d}" if season is not None else ""
        folder_nm = build_name(
            title=title, year="", se=season_label,
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
    state["step"] = "duplicate_check"
    return JSONResponse({"ok": True})


def _source_fingerprint(state: dict[str, Any]) -> tuple[int | None, int | None, list[int]]:
    """(file_count, total_bytes, sorted per-file sizes) of what we'll upload.

    Movie/episode → the single video file. Series (season pack / full series)
    → every video file that ``hardlink_tree`` will place in the torrent, so the
    fingerprint mirrors the packaged content. ``(None, None, [])`` when nothing
    usable is found.
    """
    path = Path(state["path"])
    if state["kind"] in {"movie", "episode"}:
        src = path if path.is_file() else next(iter(iter_video_files(path)), None)
        if src is None:
            return (None, None, [])
        try:
            sz = src.stat().st_size
        except OSError:
            return (None, None, [])
        return (1, sz, [sz])
    if state["kind"] == "series":
        sizes: list[int] = []
        for f in iter_video_files(path):
            try:
                sizes.append(f.stat().st_size)
            except OSError:
                continue
        if not sizes:
            return (None, None, [])
        return (len(sizes), sum(sizes), sorted(sizes))
    return (None, None, [])


def _duplicate_tolerance_pct(cfg: dict[str, Any]) -> float:
    """Configured size-match tolerance (%), clamped to a sane range."""
    try:
        v = float(cfg.get("W_DUPLICATE_SIZE_TOLERANCE_PCT", 2.0))
    except (TypeError, ValueError):
        v = 2.0
    return max(0.0, min(v, 50.0))


@router.post("/wizard/{tok}/duplicate-check")
async def wizard_duplicate_check(tok: str):
    state = _get(tok)
    cfg = web_config.load()
    enabled = bool(cfg.get("W_DUPLICATE_CHECK", True))
    state["duplicate"] = None
    if not enabled:
        state["step"] = "hardlink"
        return JSONResponse({"enabled": enabled, "duplicate": None})
    num_files, total_size, file_sizes = _source_fingerprint(state)
    tmdb_id = state.get("tmdb_id", "")
    tracker_url = (cfg.get("ITT_URL") or "").strip()
    api_token = (cfg.get("ITT_APIKEY") or "").strip()
    match = await find_duplicate(
        tracker_url=tracker_url,
        api_token=api_token,
        tmdb_id=tmdb_id,
        num_files=num_files,
        total_size=total_size,
        file_sizes=file_sizes,
        tolerance_pct=_duplicate_tolerance_pct(cfg),
    )
    if match is None:
        state["step"] = "hardlink"
        return JSONResponse({"enabled": True, "duplicate": None})
    state["duplicate"] = match
    return JSONResponse({"enabled": True, "duplicate": match})


@router.post("/wizard/{tok}/duplicate-confirm")
async def wizard_duplicate_confirm(tok: str):
    state = _get(tok)
    state["duplicate_confirmed"] = True
    state["step"] = "hardlink"
    return JSONResponse({"ok": True})


@router.post("/wizard/{tok}/duplicate-skip")
async def wizard_duplicate_skip(tok: str):
    """User declined to upload after a duplicate was detected.

    Records a "skipped" entry against the source path so the Library
    hides the item (via the W_HIDE_UPLOADED filter that keys off
    ``source_path``) and the Uploaded history shows a dedicated badge.
    The hardlink is NOT created — the wizard ends here.
    """
    state = _get(tok)
    duplicate = state.get("duplicate")
    if not duplicate:
        raise HTTPException(400, "no duplicate to skip")
    path = Path(state["path"])
    # Match the wizard_hardlink convention so the Library hide filter
    # (which keys off uploaded_paths = {r.source_path}) picks it up:
    # movie/series → state["path"] itself; episode → resolved video file.
    if state["kind"] == "episode":
        src = path if path.is_file() else next(iter(iter_video_files(path)), path)
        source_path = str(src.resolve())
        fallback_name = src.stem
    else:
        source_path = str(path.resolve())
        fallback_name = path.name
    final_name = next(iter(state.get("final_names", {}).values()), "") or fallback_name
    await record_upload(
        category=state["category"],
        kind=state["kind"],
        source_path=source_path,
        seeding_path=source_path,  # no hardlink — reuse src so the row is unique
        tmdb_id=state.get("tmdb_id", ""),
        title=state.get("tmdb_title", ""),
        year=state.get("tmdb_year", ""),
        final_name=final_name,
        exit_code=0,
        hardlink_only=False,
        duplicate_skipped=True,
        duplicate_info=duplicate,
    )
    log_emit(
        "warn",
        f"Duplicate skipped → {duplicate.get('name') or duplicate.get('id')}",
        "wizard",
    )
    state["upload_done"] = True
    state["exit_code"] = 0
    state["step"] = "done"
    return JSONResponse({"ok": True})


@router.post("/wizard/{tok}/hardlink")
async def wizard_hardlink(request: Request, tok: str):
    lang = get_request_lang(request)
    state = _get(tok, lang)
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
                    raise HTTPException(400, _i18n_t("err.no_video", lang))
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
        raise HTTPException(500, _i18n_t("err.hardlink_failed", lang, error=str(e)))


@router.get("/wizard/{tok}/upload")
async def wizard_upload(tok: str, request: Request):
    state = _get(tok)
    seeding_path = state.get("seeding_path", "")
    if not seeding_path:
        async def _err():
            yield {"event": "error", "data": "No seeding path set"}
        return EventSourceResponse(_err())
    kind = state["kind"]
    tmdb_id = state.get("tmdb_id", "")

    app = request.app

    async def generate() -> AsyncGenerator[dict, None]:
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
                state["upload_done"] = True
                await update_exit_code(seeding_path, code)
                log_emit(
                    "ok" if code == 0 else "error",
                    f"webup exit {code}", "wizard",
                )
                yield {"event": "done", "data": json.dumps({"exit_code": code})}

    return EventSourceResponse(generate())


@router.post("/wizard/{tok}/finish-hardlink")
async def wizard_finish(tok: str):
    state = _get(tok)
    state["upload_done"] = True
    state["exit_code"] = 0
    seeding_path = state.get("seeding_path", "")
    if seeding_path:
        await update_exit_code(seeding_path, 0)
    return JSONResponse({"ok": True})
