"""Radarr / Sonarr endpoints consumed by the library view."""
from __future__ import annotations

import asyncio

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
    target = body.path or f"{len(body.episode_ids)} episodi"
    try:
        changed = await _resolve_and_unmonitor(body, lang)
    except HTTPException as e:
        # Also log 400/404s, not just transport failures: the index is cached
        # 60s, so the realistic failure is Radarr/Sonarr going down *after*
        # the badge rendered — the click 404s and the Logs tab is the only
        # place that failure is visible besides the button itself.
        logbuf.emit(
            "warn", f"Rimozione monitoraggio fallita ({e.status_code}): {target}",
            "arr", source="arr",
        )
        raise
    except Exception as e:  # noqa: BLE001
        logbuf.emit("error", f"Rimozione monitoraggio fallita: {e}", "arr", source="arr")
        raise HTTPException(502, arr.error_msg(e)) from e
    logbuf.emit("info", f"Monitoraggio rimosso ({body.kind}): {target}", "arr", source="arr")
    return JSONResponse({"ok": True, "changed": changed})


_BULK_FAILURE_LOG_CAP = 10
_BULK_SERIES_CONCURRENCY = 6


async def _cascade_series(semaphore: asyncio.Semaphore, series_id: int) -> int | BaseException:
    """Unmonitor one series under the concurrency cap.

    Returns the changed-episode count, or the exception, instead of raising —
    ``asyncio.gather`` preserves call order, so the caller pairs each result
    back to its path positionally regardless of completion order. Deliberately
    calls only ``unmonitor_series()`` here, never ``arr.build_index()``: that
    helper's cache lock is not reentrant, and every task in this gather would
    deadlock against a sibling holding it.
    """
    async with semaphore:
        try:
            return await arr.unmonitor_series(series_id)
        except Exception as e:  # noqa: BLE001
            return e


@router.post("/arr/unmonitor/bulk")
async def arr_unmonitor_bulk(body: BulkBody):
    """Switch monitoring off across many paths.

    Movies go out in a single call to Radarr's editor endpoint. A series needs
    4 HTTP calls of its own (fetch series, PUT series, fetch episodes, PUT
    episodes), so on a library with hundreds of series a one-at-a-time loop
    takes minutes and outruns nginx's 60s read timeout before the client sees
    a response. The cascades instead run concurrently, bounded by
    ``_BULK_SERIES_CONCURRENCY`` so Radarr/Sonarr aren't hit with hundreds of
    simultaneous requests. One failure does not stop the others — it lands in
    ``failed`` with its own path.

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

    if series_targets:
        semaphore = asyncio.Semaphore(_BULK_SERIES_CONCURRENCY)
        outcomes = await asyncio.gather(
            *(_cascade_series(semaphore, series_id) for _, series_id in series_targets),
            return_exceptions=True,
        )
        # zip(), not the outcome, supplies the path: gather() returns results
        # positionally matched to the input awaitables, not to completion
        # order, so this pairing is correct even though the cascades finish
        # in whatever order their HTTP calls happen to land.
        for (path, _series_id), outcome in zip(series_targets, outcomes):
            if isinstance(outcome, BaseException):
                failed.append({"path": path, "error": arr.error_msg(outcome)})
            else:
                done += 1

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
