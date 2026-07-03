"""Library scan + per-item TMDB + lang-cache JSON endpoints.

All response shapes are stable and consumed by the React LibraryView.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...core import (
    audio_and_subtitle_languages,
    tmdb_fetch,
    tmdb_fetch_bilingual,
    tmdb_poster_url,
    tmdb_search,
    tmdb_year,
    tv_season_status,
)
from ...media import (
    MediaItem,
    Season,
    discover_categories,
    get_item,
    media_root,
    scan_category,
)
from ...i18n import get_request_lang, t as _i18n_t
from ..db import list_uploads, record_upload
from ..tocheck import add_flag, list_flagged_paths, remove_flag
from ..lang_cache import get_many_langs, set_lang
from ..tmdb_cache import get_cache, get_many, set_cache, set_series_status

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

router = APIRouter(prefix="/api", tags=["library"])


def _season_to_dict(s: Season, uploaded_paths: set[str]) -> dict[str, Any]:
    return {
        "number": s.number,
        "label": s.label,
        "path": str(s.path),
        "episode_count": s.episode_count,
        "size": s.total_size_human,
        "langs": list(s.available_langs),
        "subs": list(s.available_subs),
        "lang_scanned": s.lang_scanned,
        "already_uploaded": s.already_uploaded,
        "uploaded_episodes": len(s.uploaded_episode_paths),
        "all_episodes_uploaded": s.all_episodes_uploaded,
        "to_check": s.to_check,
        "video_files": [
            {
                "path": str(vf),
                "name": vf.name,
                "uploaded": str(vf.resolve()) in uploaded_paths,
                "to_check": str(vf.resolve()) in s.to_check_episode_paths,
            }
            for vf in s.video_files
        ],
    }


def _item_to_dict(item: MediaItem, uploaded_paths: set[str]) -> dict[str, Any]:
    base = {
        "name": item.name,
        "path": str(item.path),
        "category": item.category,
        "kind": item.kind,
        "title": item.tmdb_title or item.title,
        "year": item.year,
        "size": item.total_size_human,
        "total_files": item.total_files,
        "tmdb_id": item.tmdb_id,
        "tmdb_kind": item.tmdb_kind,
        "tmdb_title_en": getattr(item, "tmdb_title_en", ""),
        "tmdb_original_title": getattr(item, "tmdb_original_title", ""),
        "tmdb_poster": item.tmdb_poster,
        "tmdb_overview": item.tmdb_overview,
        "tmdb_overview_en": getattr(item, "tmdb_overview_en", ""),
        "langs": list(item.available_langs),
        "subs": list(item.available_subs),
        "lang_scanned": item.lang_scanned,
        "already_uploaded": str(item.path.resolve()) in uploaded_paths,
        "to_check": item.to_check,
        "any_to_check": item.any_to_check,
    }
    if item.kind == "series":
        base["seasons"] = [_season_to_dict(s, uploaded_paths) for s in item.seasons]
        base["all_seasons_uploaded"] = item.all_seasons_uploaded
    else:
        base["video_files"] = [
            {
                "path": str(vf),
                "name": vf.name,
                "uploaded": str(vf.resolve()) in uploaded_paths,
                "to_check": item.to_check,
            }
            for vf in item.video_files
        ]
    return base


async def _enrich_items(items: list[MediaItem]) -> tuple[set[str], dict, dict]:
    uploads = await list_uploads()
    uploaded_paths = {r["source_path"] for r in uploads if r.get("source_path")}

    # Fallback: records with empty source_path → match via hardlink inode
    seeding_inodes: set[tuple[int, int]] = set()
    for r in uploads:
        sp = r.get("seeding_path", "")
        if sp and not sp.startswith("__manual__"):
            try:
                st = Path(sp).stat()
                if st.st_ino:
                    seeding_inodes.add((st.st_dev, st.st_ino))
            except OSError:
                pass
    if seeding_inodes:
        for item in items:
            if item.kind == "movie":
                for vf in item.video_files:
                    try:
                        st = vf.stat()
                        if st.st_ino and (st.st_dev, st.st_ino) in seeding_inodes:
                            uploaded_paths.add(str(item.path.resolve()))
                            uploaded_paths.add(str(vf.resolve()))
                    except OSError:
                        pass
            else:
                for season in item.seasons:
                    for vf in season.video_files:
                        try:
                            st = vf.stat()
                            if st.st_ino and (st.st_dev, st.st_ino) in seeding_inodes:
                                # Only mark the single episode as uploaded.
                                # `season.already_uploaded` and `all_seasons_uploaded`
                                # propagate via direct season-path / series-root
                                # records (mark-uploaded at season/series level)
                                # or via `all_episodes_uploaded` once *every*
                                # episode has been uploaded individually.
                                uploaded_paths.add(str(vf.resolve()))
                        except OSError:
                            pass
    all_paths: list[str] = []
    for item in items:
        all_paths.append(str(item.path))
        for s in item.seasons:
            all_paths.append(str(s.path))
    cache = await get_many(all_paths)
    lang_cache = await get_many_langs(all_paths)
    to_check_paths = await list_flagged_paths()

    for item in items:
        sp = str(item.path)
        tmdb = cache.get(sp)
        if tmdb:
            item.tmdb_id = tmdb.get("tmdb_id", "")
            item.tmdb_kind = tmdb.get("tmdb_kind", "") or ("tv" if item.kind == "series" else "movie")
            item.tmdb_title = tmdb.get("title", "")
            setattr(item, "tmdb_title_en", tmdb.get("title_en", ""))
            setattr(item, "tmdb_original_title", tmdb.get("original_title", ""))
            item.tmdb_poster = tmdb.get("poster", "")
            item.tmdb_overview = tmdb.get("overview", "")
            setattr(item, "tmdb_overview_en", tmdb.get("overview_en", ""))
        if item.kind == "series":
            uploaded_season_numbers: list[int] = []
            all_langs: list[str] = []
            all_subs: list[str] = []
            any_scanned = False
            series_root = str(item.path.resolve())
            item.to_check = series_root in to_check_paths
            for season in item.seasons:
                ssp = str(season.path)
                ssp_resolved = str(season.path.resolve())
                season.already_uploaded = ssp_resolved in uploaded_paths or series_root in uploaded_paths
                season.to_check = ssp_resolved in to_check_paths or series_root in to_check_paths
                uploaded_ep: set[str] = set()
                to_check_ep: set[str] = set()
                for vf in season.video_files:
                    vf_resolved = str(vf.resolve())
                    if vf_resolved in uploaded_paths:
                        uploaded_ep.add(vf_resolved)
                    if vf_resolved in to_check_paths:
                        to_check_ep.add(vf_resolved)
                season.uploaded_episode_paths = uploaded_ep
                season.to_check_episode_paths = to_check_ep
                if season.already_uploaded or season.all_episodes_uploaded:
                    uploaded_season_numbers.append(season.number)
                if not item.tmdb_id:
                    s_tmdb = cache.get(ssp)
                    if s_tmdb:
                        item.tmdb_id = s_tmdb.get("tmdb_id", "")
                        item.tmdb_kind = s_tmdb.get("tmdb_kind", "") or "tv"
                        item.tmdb_title = s_tmdb.get("title", "")
                        item.tmdb_poster = s_tmdb.get("poster", "")
                        item.tmdb_overview = s_tmdb.get("overview", "")
                lang_entry = lang_cache.get(ssp)
                if lang_entry:
                    season.available_langs = lang_entry.get("langs", [])
                    season.available_subs = lang_entry.get("subs", [])
                    season.lang_scanned = True
                    any_scanned = True
                    for lang in season.available_langs:
                        if lang not in all_langs:
                            all_langs.append(lang)
                    for sub in season.available_subs:
                        if sub not in all_subs:
                            all_subs.append(sub)
            item.uploaded_season_numbers = uploaded_season_numbers
            item.any_to_check = item.to_check or any(
                s.to_check or s.to_check_episode_paths for s in item.seasons
            )
            if any_scanned:
                has_ita = "ITA" in all_langs
                rest = sorted(c for c in all_langs if c != "ITA")
                item.available_langs = (["ITA"] + rest) if has_ita else rest
                has_ita_sub = "ITA" in all_subs
                rest_sub = sorted(c for c in all_subs if c != "ITA")
                item.available_subs = (["ITA"] + rest_sub) if has_ita_sub else rest_sub
                item.lang_scanned = True
        else:
            item.to_check = str(item.path.resolve()) in to_check_paths
            item.any_to_check = item.to_check
            lang_entry = lang_cache.get(sp)
            if lang_entry:
                item.available_langs = lang_entry.get("langs", [])
                item.available_subs = lang_entry.get("subs", [])
                item.episode_langs = lang_entry.get("episode_langs", {})
                item.episode_subs = lang_entry.get("episode_subs", {})
                item.lang_scanned = True
        if not item.tmdb_kind:
            item.tmdb_kind = "tv" if item.kind == "series" else "movie"
    return uploaded_paths, cache, lang_cache


_CATEGORY_LABELS = {
    "movies": "Movies",
    "series": "Series",
    "anime": "Anime",
    "documentaries": "Documentaries",
    "concerts": "Concerts",
}


def _count_entries(path: Path) -> int:
    try:
        return sum(1 for _ in path.iterdir() if not _.name.startswith("."))
    except OSError:
        return 0


@router.get("/library/categories")
async def library_categories():
    root = media_root()
    cats = []
    for name in discover_categories():
        cats.append({
            "id": name,
            "label": _CATEGORY_LABELS.get(name, name.capitalize()),
            "count": _count_entries(root / name),
        })
    return JSONResponse({
        "root": str(root),
        "root_exists": root.exists(),
        "categories": cats,
    })


_STATUS_TTL_SECONDS = 12 * 3600


def _series_status_fresh(fetched_at: Any, show_status: str) -> bool:
    """Cached season status is fresh when the show is finished (immutable) or
    the last fetch is within the TTL."""
    if show_status in ("Ended", "Canceled"):
        return True
    if not isinstance(fetched_at, (int, float)):
        return False
    return (time.time() - fetched_at) < _STATUS_TTL_SECONDS


@router.get("/library/series-status")
async def library_series_status(path: str):
    """Per-season completion (complete vs ongoing) + TMDB episode count for a
    series. Resolves the TMDB id from cache, refetches ``/tv/{id}`` when the
    cached status is missing/stale, then caches it. On-demand only — never hit
    during the library scan, so it costs at most one TMDB call per panel open.
    """
    record = await get_cache(path)
    tmdb_id = (record or {}).get("tmdb_id", "")
    if not tmdb_id:
        return JSONResponse({"tmdb_id": "", "show_status": "", "seasons": {}})

    cached_meta = (record or {}).get("seasons_meta")
    cached_status = (record or {}).get("show_status", "")
    if cached_meta is not None and _series_status_fresh(
        (record or {}).get("status_fetched_at"), cached_status
    ):
        return JSONResponse(
            {"tmdb_id": tmdb_id, "show_status": cached_status, "seasons": cached_meta}
        )

    if not TMDB_API_KEY:
        return JSONResponse(
            {"tmdb_id": tmdb_id, "show_status": cached_status, "seasons": cached_meta or {}}
        )

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, tmdb_fetch, "tv", tmdb_id, TMDB_API_KEY)
    except Exception:
        # TMDB hiccup: serve stale cache if present, else report unknown.
        if cached_meta is not None:
            return JSONResponse(
                {"tmdb_id": tmdb_id, "show_status": cached_status, "seasons": cached_meta}
            )
        return JSONResponse({"tmdb_id": tmdb_id, "show_status": "", "seasons": {}})

    status_obj = tv_season_status(data)
    await set_series_status(path, status_obj["show_status"], status_obj["seasons"])
    return JSONResponse(
        {
            "tmdb_id": tmdb_id,
            "show_status": status_obj["show_status"],
            "seasons": status_obj["seasons"],
        }
    )


@router.get("/library/{category}")
async def library_list(request: Request, category: str):
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", get_request_lang(request)))
    items = scan_category(category)
    uploaded_paths, _cache, _lang = await _enrich_items(items)
    return JSONResponse({
        "category": category,
        "items": [_item_to_dict(i, uploaded_paths) for i in items],
    })


@router.get("/library/{category}/enrich")
async def library_enrich(request: Request, category: str):
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", get_request_lang(request)))
    if not TMDB_API_KEY:
        async def _no_key():
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(_no_key())

    async def generate() -> AsyncGenerator[dict, None]:
        items = scan_category(category)
        paths = [str(i.path) for i in items]
        cache = await get_many(paths)
        loop = asyncio.get_event_loop()
        for item in items:
            sp = str(item.path)
            if sp in cache:
                continue
            kind = "tv" if item.kind == "series" else "movie"
            try:
                results = await loop.run_in_executor(
                    None, tmdb_search, kind, item.title, item.year, TMDB_API_KEY
                )
            except Exception:
                await asyncio.sleep(0.25)
                continue
            if not results:
                await asyncio.sleep(0.25)
                continue
            best = results[0]
            if item.year and best.get("year"):
                try:
                    if abs(int(best["year"]) - int(item.year)) > 1:
                        await asyncio.sleep(0.25)
                        continue
                except ValueError:
                    pass
            tmdb_id = str(best["id"])
            try:
                data = await loop.run_in_executor(
                    None, tmdb_fetch_bilingual, kind, tmdb_id, TMDB_API_KEY
                )
            except Exception:
                await asyncio.sleep(0.25)
                continue
            t = data.get("title") or best["title"]
            y = tmdb_year(data, kind) or best.get("year", "")
            poster = tmdb_poster_url(data) or best.get("poster", "")
            await set_cache(
                sp,
                tmdb_id=tmdb_id,
                tmdb_kind=kind,
                title=t,
                title_en=data.get("title_en", ""),
                original_title=data.get("original_title", ""),
                year=y,
                poster=poster,
                overview=(data.get("overview") or "")[:300],
                overview_en=(data.get("overview_en") or "")[:300],
            )
            yield {
                "event": "enriched",
                "data": json.dumps({
                    "source_path": sp,
                    "tmdb_id": tmdb_id,
                    "title": t,
                    "year": y,
                    "poster": poster,
                }),
            }
            await asyncio.sleep(0.25)
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


def _ita_first(codes: list[str]) -> list[str]:
    """Return codes with ITA first, remaining alphabetically sorted."""
    has_ita = "ITA" in codes
    rest = sorted(c for c in codes if c != "ITA")
    return (["ITA"] + rest) if has_ita else rest


async def _scan_langs_and_subs_stream(video_files, loop):
    """Async-generator variant of :func:`_scan_langs_and_subs`.

    Yields ``("progress", n, path)`` after each file is scanned (``n`` = 1-based
    count of files done so far), then a terminal
    ``("result", merged_audio, episode_langs, merged_subs, episode_subs)``.
    Callers that only need the aggregate use :func:`_scan_langs_and_subs`."""
    episode_langs: dict[str, list[str]] = {}
    episode_subs: dict[str, list[str]] = {}
    seen: list[str] = []
    seen_subs: list[str] = []
    done = 0
    for vf in video_files:
        try:
            langs, subs = await loop.run_in_executor(None, audio_and_subtitle_languages, vf)
        except Exception:
            langs, subs = [], []
        episode_langs[str(vf)] = langs
        episode_subs[str(vf)] = subs
        for lang in langs:
            if lang not in seen:
                seen.append(lang)
        for sub in subs:
            if sub not in seen_subs:
                seen_subs.append(sub)
        done += 1
        yield ("progress", done, str(vf))
        await asyncio.sleep(0.05)
    yield ("result", _ita_first(seen), episode_langs, _ita_first(seen_subs), episode_subs)


async def _scan_langs_and_subs(video_files, loop):
    """Scan each video file once for audio + subtitle languages.

    Returns (merged_audio, episode_langs, merged_subs, episode_subs); audio/subs are ITA-first.
    Yields the event loop between files so SSE streams stay responsive."""
    result = ([], {}, [], {})
    async for ev in _scan_langs_and_subs_stream(video_files, loop):
        if ev[0] == "result":
            result = ev[1:]
    return result


@router.get("/library/{category}/scan-langs")
async def library_scan_langs(request: Request, category: str):
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", get_request_lang(request)))

    async def generate() -> AsyncGenerator[dict, None]:
        items = scan_category(category)
        all_paths: list[str] = []
        for item in items:
            if item.kind == "series":
                for s in item.seasons:
                    all_paths.append(str(s.path))
            else:
                all_paths.append(str(item.path))
        lang_cache = await get_many_langs(all_paths)
        loop = asyncio.get_event_loop()

        # Build the work list up-front (skipping items already scanned with sub
        # support) so the client can render an accurate "done/total" counter.
        tasks: list[tuple[str, object, object]] = []  # (kind, item, season|None)
        for item in items:
            if item.kind == "series":
                for season in item.seasons:
                    entry = lang_cache.get(str(season.path))
                    if entry and "subs" in entry:  # already scanned with sub support
                        continue
                    tasks.append(("series", item, season))
            else:
                entry = lang_cache.get(str(item.path))
                if entry and "subs" in entry:  # already scanned with sub support
                    continue
                tasks.append(("movie", item, None))

        total = len(tasks)
        yield {"event": "progress", "data": json.dumps({"done": 0, "total": total})}
        done = 0
        for kind, item, season in tasks:
            if kind == "series":
                sp = str(season.path)
                merged, episode_langs, merged_subs, episode_subs = \
                    await _scan_langs_and_subs(season.video_files, loop)
                await set_lang(sp, merged, episode_langs, subs=merged_subs, episode_subs=episode_subs)
                yield {
                    "event": "lang_scanned",
                    "data": json.dumps({
                        "source_path": str(item.path),
                        "season_path": sp,
                        "langs": merged,
                        "subs": merged_subs,
                        "has_ita": "ITA" in merged,
                        "has_ita_sub": "ITA" in merged_subs,
                    }),
                }
            else:
                sp = str(item.path)
                multi = len(item.video_files) > 1
                merged, episode_langs, merged_subs, episode_subs = \
                    await _scan_langs_and_subs(item.video_files, loop)
                await set_lang(
                    sp, merged,
                    episode_langs if multi else None,
                    subs=merged_subs,
                    episode_subs=episode_subs if multi else None,
                )
                yield {
                    "event": "lang_scanned",
                    "data": json.dumps({
                        "source_path": sp,
                        "season_path": None,
                        "langs": merged,
                        "subs": merged_subs,
                        "has_ita": "ITA" in merged,
                        "has_ita_sub": "ITA" in merged_subs,
                    }),
                }
            done += 1
            yield {"event": "progress", "data": json.dumps({"done": done, "total": total})}
        yield {"event": "done", "data": json.dumps({"total": total})}

    return EventSourceResponse(generate())


class MarkUploadedBody(BaseModel):
    season_path: str = ""
    episode_path: str = ""


@router.post("/library/{category}/{item_name:path}/mark-uploaded")
async def library_mark_uploaded(request: Request, category: str, item_name: str, body: MarkUploadedBody):
    lang = get_request_lang(request)
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", lang))
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, _i18n_t("err.item_not_found_in_category", lang, name=item_name, category=category))
    if body.episode_path:
        source_path = str(Path(body.episode_path).resolve())
        kind = "episode"
    elif body.season_path:
        source_path = str(Path(body.season_path).resolve())
        kind = "series"
    else:
        source_path = str(item.path.resolve())
        kind = item.kind
    seeding_path = f"__manual__:{source_path}"
    cache_entry = await get_cache(str(item.path)) or await get_cache(source_path)
    title = (cache_entry.get("title") or item.title) if cache_entry else item.title
    year = (cache_entry.get("year") or item.year) if cache_entry else item.year
    tmdb_id = cache_entry.get("tmdb_id", "") if cache_entry else ""
    await record_upload(
        category=category, kind=kind,
        source_path=source_path, seeding_path=seeding_path,
        tmdb_id=tmdb_id, title=title, year=year,
        final_name="", exit_code=0, hardlink_only=True,
    )
    return JSONResponse({"ok": True})


class ToCheckBody(BaseModel):
    season_path: str = ""
    episode_path: str = ""
    flagged: bool = True  # True = mark "to-check", False = clear the flag


@router.post("/library/{category}/{item_name:path}/to-check")
async def library_to_check(request: Request, category: str, item_name: str, body: ToCheckBody):
    """Toggle the persistent "to-check" flag for a movie / episode / season /
    whole series. Mirrors ``mark-uploaded`` path resolution but writes to the
    separate tocheck store and supports clearing (``flagged=False``)."""
    lang = get_request_lang(request)
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", lang))
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, _i18n_t("err.item_not_found_in_category", lang, name=item_name, category=category))
    if body.episode_path:
        source_path = str(Path(body.episode_path).resolve())
        kind = "episode"
    elif body.season_path:
        source_path = str(Path(body.season_path).resolve())
        kind = "series"
    else:
        source_path = str(item.path.resolve())
        kind = item.kind
    if body.flagged:
        await add_flag(source_path, category, kind)
    else:
        await remove_flag(source_path)
    return JSONResponse({"ok": True, "flagged": body.flagged})


@router.post("/library/{category}/{item_name:path}/rescan-langs")
async def library_rescan_langs(request: Request, category: str, item_name: str):
    lang = get_request_lang(request)
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", lang))
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, _i18n_t("err.item_not_found_in_category", lang, name=item_name, category=category))
    loop = asyncio.get_event_loop()
    if item.kind == "series":
        seasons_result = {}
        all_series_langs: list[str] = []
        all_series_subs: list[str] = []
        for season in item.seasons:
            sp = str(season.path)
            merged, episode_langs, merged_subs, episode_subs = \
                await _scan_langs_and_subs(season.video_files, loop)
            await set_lang(sp, merged, episode_langs, subs=merged_subs, episode_subs=episode_subs)
            seasons_result[sp] = {
                "langs": merged, "subs": merged_subs,
                "episode_langs": episode_langs, "episode_subs": episode_subs,
            }
            for lang in merged:
                if lang not in all_series_langs:
                    all_series_langs.append(lang)
            for sub in merged_subs:
                if sub not in all_series_subs:
                    all_series_subs.append(sub)
        return JSONResponse({
            "ok": True,
            "langs": _ita_first(all_series_langs),
            "subs": _ita_first(all_series_subs),
            "seasons": seasons_result,
        })
    sp = str(item.path)
    multi = len(item.video_files) > 1
    merged, episode_langs, merged_subs, episode_subs = \
        await _scan_langs_and_subs(item.video_files, loop)
    await set_lang(
        sp, merged,
        episode_langs if multi else None,
        subs=merged_subs,
        episode_subs=episode_subs if multi else None,
    )
    return JSONResponse({
        "ok": True, "langs": merged, "subs": merged_subs,
        "episode_langs": episode_langs, "episode_subs": episode_subs,
    })


@router.get("/library/{category}/{item_name:path}/rescan-langs/stream")
async def library_rescan_langs_stream(request: Request, category: str, item_name: str):
    """SSE variant of ``rescan-langs`` for a single item. Emits ``progress``
    events ``{done, total}`` per video file (so a series streams a per-episode
    counter) and a terminal ``done`` carrying the same payload as the POST."""
    lang = get_request_lang(request)
    if category not in discover_categories():
        raise HTTPException(404, _i18n_t("err.category_not_found", lang))
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, _i18n_t("err.item_not_found_in_category", lang, name=item_name, category=category))

    async def generate() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()
        if item.kind == "series":
            total = sum(len(s.video_files) for s in item.seasons)
            yield {"event": "progress", "data": json.dumps({"done": 0, "total": total})}
            done = 0
            seasons_result: dict[str, dict] = {}
            all_series_langs: list[str] = []
            all_series_subs: list[str] = []
            for season in item.seasons:
                sp = str(season.path)
                merged, episode_langs, merged_subs, episode_subs = [], {}, [], {}
                async for ev in _scan_langs_and_subs_stream(season.video_files, loop):
                    if ev[0] == "progress":
                        done += 1
                        yield {"event": "progress", "data": json.dumps({"done": done, "total": total})}
                    else:
                        _, merged, episode_langs, merged_subs, episode_subs = ev
                await set_lang(sp, merged, episode_langs, subs=merged_subs, episode_subs=episode_subs)
                seasons_result[sp] = {
                    "langs": merged, "subs": merged_subs,
                    "episode_langs": episode_langs, "episode_subs": episode_subs,
                }
                for lg in merged:
                    if lg not in all_series_langs:
                        all_series_langs.append(lg)
                for sub in merged_subs:
                    if sub not in all_series_subs:
                        all_series_subs.append(sub)
            yield {
                "event": "done",
                "data": json.dumps({
                    "ok": True,
                    "langs": _ita_first(all_series_langs),
                    "subs": _ita_first(all_series_subs),
                    "seasons": seasons_result,
                }),
            }
            return

        sp = str(item.path)
        multi = len(item.video_files) > 1
        total = len(item.video_files)
        yield {"event": "progress", "data": json.dumps({"done": 0, "total": total})}
        done = 0
        merged, episode_langs, merged_subs, episode_subs = [], {}, [], {}
        async for ev in _scan_langs_and_subs_stream(item.video_files, loop):
            if ev[0] == "progress":
                done += 1
                yield {"event": "progress", "data": json.dumps({"done": done, "total": total})}
            else:
                _, merged, episode_langs, merged_subs, episode_subs = ev
        await set_lang(
            sp, merged,
            episode_langs if multi else None,
            subs=merged_subs,
            episode_subs=episode_subs if multi else None,
        )
        yield {
            "event": "done",
            "data": json.dumps({
                "ok": True, "langs": merged, "subs": merged_subs,
                "episode_langs": episode_langs, "episode_subs": episode_subs,
            }),
        }

    return EventSourceResponse(generate())
