"""Radarr / Sonarr endpoints consumed by the library view."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...i18n import get_request_lang, t as _i18n_t
from .. import arr, logbuf

router = APIRouter(prefix="/api", tags=["arr"])


class UnmonitorBody(BaseModel):
    kind: str
    path: str = ""
    season_number: int | None = None
    episode_ids: list[int] = []


class BulkBody(BaseModel):
    paths: list[str] = []


@router.get("/arr/status")
async def arr_status(force: bool = False):
    """path → monitored index for both instances, cached 60 s."""
    return JSONResponse(await arr.build_index(force=force))


@router.get("/arr/test")
async def arr_test(kind: str):
    return JSONResponse(await arr.test_connection(kind))


@router.get("/arr/series/{series_id}/episodes")
async def arr_series_episodes(request: Request, series_id: int):
    lang = get_request_lang(request)
    if not arr.configured("sonarr"):
        raise HTTPException(400, _i18n_t("err.arr_sonarr_not_configured", lang))
    try:
        raw = await arr.fetch_episodes(series_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, arr.error_msg(e)) from e
    return JSONResponse({"episodes": arr.episodes_to_dicts(raw)})


async def _resolve_and_unmonitor(body: UnmonitorBody, lang: str) -> int:
    """Resolve the *arr id from the path and switch monitoring off. Returns the count."""
    index = await arr.build_index()
    key = arr.norm_path(body.path)

    if body.kind == "movie":
        entry = index["movies"].get(key)
        if not entry:
            raise HTTPException(404, _i18n_t("err.arr_movie_not_found", lang))
        return await arr.unmonitor_movies([entry["id"]])

    if body.kind in {"series", "season"}:
        entry = index["series"].get(key)
        if not entry:
            raise HTTPException(404, _i18n_t("err.arr_series_not_found", lang))
        if body.kind == "season" and body.season_number is None:
            raise HTTPException(400, _i18n_t("err.arr_missing_field", lang, field="season_number"))
        if body.kind == "season" and str(body.season_number) not in entry["seasons"]:
            raise HTTPException(404, _i18n_t("err.arr_season_not_found", lang))
        season = body.season_number if body.kind == "season" else None
        return await arr.unmonitor_series(entry["id"], season)

    if body.kind == "episodes":
        if not body.episode_ids:
            raise HTTPException(400, _i18n_t("err.arr_missing_field", lang, field="episode_ids"))
        return await arr.unmonitor_episode_ids(body.episode_ids)

    raise HTTPException(400, _i18n_t("err.invalid_kind", lang))


@router.post("/arr/unmonitor")
async def arr_unmonitor(request: Request, body: UnmonitorBody):
    lang = get_request_lang(request)
    try:
        changed = await _resolve_and_unmonitor(body, lang)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logbuf.emit("error", f"Rimozione monitoraggio fallita: {e}", "arr", source="arr")
        raise HTTPException(502, arr.error_msg(e)) from e
    target = body.path or f"{len(body.episode_ids)} episodi"
    logbuf.emit("info", f"Monitoraggio rimosso ({body.kind}): {target}", "arr", source="arr")
    return JSONResponse({"ok": True, "changed": changed})


_BULK_FAILURE_LOG_CAP = 10


@router.post("/arr/unmonitor/bulk")
async def arr_unmonitor_bulk(body: BulkBody):
    """Switch monitoring off across many paths.

    Movies go out in a single call to Radarr's editor endpoint; each series gets
    its own cascade. One failure does not stop the others — it lands in
    ``failed``.

    ``done`` counts *targets* (each movie, each series) that succeeded, not
    episodes — unlike ``/arr/unmonitor``'s ``changed``, which counts episodes
    for a series/season target.
    """
    index = await arr.build_index()
    movie_ids: list[int] = []
    series_targets: list[tuple[str, int]] = []
    failed: list[dict[str, str]] = []

    for raw_path in dict.fromkeys(body.paths):  # de-dupe, preserve first-seen order
        key = arr.norm_path(raw_path)
        movie = index["movies"].get(key)
        if movie:
            movie_ids.append(movie["id"])
            continue
        show = index["series"].get(key)
        if show:
            series_targets.append((raw_path, show["id"]))
            continue
        failed.append({"path": raw_path, "error": "Non trovato in Radarr/Sonarr."})

    done = 0
    if movie_ids:
        try:
            await arr.unmonitor_movies(movie_ids)
            done += len(movie_ids)
        except Exception as e:  # noqa: BLE001
            failed.append({"path": f"{len(movie_ids)} film", "error": arr.error_msg(e)})
    for path, series_id in series_targets:
        try:
            await arr.unmonitor_series(series_id)
            done += 1
        except Exception as e:  # noqa: BLE001
            failed.append({"path": path, "error": arr.error_msg(e)})

    level = "warn" if failed else "info"
    logbuf.emit(
        level, f"Monitoraggio in blocco: {done} rimossi, {len(failed)} falliti",
        "arr", source="arr",
    )
    for f in failed[:_BULK_FAILURE_LOG_CAP]:
        logbuf.emit("warn", f"  {f['path']}: {f['error']}", "arr", source="arr")
    extra = len(failed) - _BULK_FAILURE_LOG_CAP
    if extra > 0:
        logbuf.emit("warn", f"  ... e altri {extra} falliti", "arr", source="arr")
    return JSONResponse({"ok": True, "done": done, "failed": failed})
