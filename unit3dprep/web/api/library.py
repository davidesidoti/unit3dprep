"""Library scan + per-item TMDB + lang-cache JSON endpoints.

All response shapes are stable and consumed by the React LibraryView.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...core import (
    audio_languages,
    tmdb_fetch_bilingual,
    tmdb_poster_url,
    tmdb_search,
    tmdb_year,
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
from ..lang_cache import get_many_langs, set_lang
from ..tmdb_cache import get_cache, get_many, set_cache

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
        "lang_scanned": s.lang_scanned,
        "already_uploaded": s.already_uploaded,
        "uploaded_episodes": len(s.uploaded_episode_paths),
        "all_episodes_uploaded": s.all_episodes_uploaded,
        "video_files": [
            {
                "path": str(vf),
                "name": vf.name,
                "uploaded": str(vf.resolve()) in uploaded_paths,
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
        "lang_scanned": item.lang_scanned,
        "already_uploaded": str(item.path.resolve()) in uploaded_paths,
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
            any_scanned = False
            series_root = str(item.path.resolve())
            for season in item.seasons:
                ssp = str(season.path)
                ssp_resolved = str(season.path.resolve())
                season.already_uploaded = ssp_resolved in uploaded_paths or series_root in uploaded_paths
                uploaded_ep: set[str] = set()
                for vf in season.video_files:
                    if str(vf.resolve()) in uploaded_paths:
                        uploaded_ep.add(str(vf.resolve()))
                season.uploaded_episode_paths = uploaded_ep
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
                    season.lang_scanned = True
                    any_scanned = True
                    for lang in season.available_langs:
                        if lang not in all_langs:
                            all_langs.append(lang)
            item.uploaded_season_numbers = uploaded_season_numbers
            if any_scanned:
                has_ita = "ITA" in all_langs
                rest = sorted(c for c in all_langs if c != "ITA")
                item.available_langs = (["ITA"] + rest) if has_ita else rest
                item.lang_scanned = True
        else:
            lang_entry = lang_cache.get(sp)
            if lang_entry:
                item.available_langs = lang_entry.get("langs", [])
                item.episode_langs = lang_entry.get("episode_langs", {})
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
        for item in items:
            if item.kind == "series":
                for season in item.seasons:
                    sp = str(season.path)
                    if sp in lang_cache:
                        continue
                    episode_langs: dict[str, list[str]] = {}
                    seen: list[str] = []
                    for vf in season.video_files:
                        try:
                            langs = await loop.run_in_executor(None, audio_languages, vf)
                        except Exception:
                            langs = []
                        episode_langs[str(vf)] = langs
                        for lang in langs:
                            if lang not in seen:
                                seen.append(lang)
                        await asyncio.sleep(0.05)
                    has_ita = "ITA" in seen
                    rest = sorted(c for c in seen if c != "ITA")
                    merged = (["ITA"] + rest) if has_ita else rest
                    await set_lang(sp, merged, episode_langs)
                    yield {
                        "event": "lang_scanned",
                        "data": json.dumps({
                            "source_path": str(item.path),
                            "season_path": sp,
                            "langs": merged,
                            "has_ita": has_ita,
                        }),
                    }
            else:
                sp = str(item.path)
                if sp in lang_cache:
                    continue
                episode_langs: dict[str, list[str]] = {}
                seen: list[str] = []
                for vf in item.video_files:
                    try:
                        langs = await loop.run_in_executor(None, audio_languages, vf)
                    except Exception:
                        langs = []
                    episode_langs[str(vf)] = langs
                    for lang in langs:
                        if lang not in seen:
                            seen.append(lang)
                    await asyncio.sleep(0.05)
                has_ita = "ITA" in seen
                rest = sorted(c for c in seen if c != "ITA")
                merged = (["ITA"] + rest) if has_ita else rest
                await set_lang(sp, merged, episode_langs if len(item.video_files) > 1 else None)
                yield {
                    "event": "lang_scanned",
                    "data": json.dumps({
                        "source_path": sp,
                        "season_path": None,
                        "langs": merged,
                        "has_ita": has_ita,
                    }),
                }
        yield {"event": "done", "data": "{}"}

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
        for season in item.seasons:
            sp = str(season.path)
            episode_langs: dict[str, list[str]] = {}
            seen: list[str] = []
            for vf in season.video_files:
                try:
                    langs = await loop.run_in_executor(None, audio_languages, vf)
                except Exception:
                    langs = []
                episode_langs[str(vf)] = langs
                for lang in langs:
                    if lang not in seen:
                        seen.append(lang)
            has_ita = "ITA" in seen
            rest = sorted(c for c in seen if c != "ITA")
            merged = (["ITA"] + rest) if has_ita else rest
            await set_lang(sp, merged, episode_langs)
            seasons_result[sp] = {"langs": merged, "episode_langs": episode_langs}
            for lang in merged:
                if lang not in all_series_langs:
                    all_series_langs.append(lang)
        has_ita_series = "ITA" in all_series_langs
        rest_series = sorted(c for c in all_series_langs if c != "ITA")
        merged_series = (["ITA"] + rest_series) if has_ita_series else rest_series
        return JSONResponse({"ok": True, "langs": merged_series, "seasons": seasons_result})
    sp = str(item.path)
    episode_langs: dict[str, list[str]] = {}
    seen: list[str] = []
    for vf in item.video_files:
        try:
            langs = await loop.run_in_executor(None, audio_languages, vf)
        except Exception:
            langs = []
        episode_langs[str(vf)] = langs
        for lang in langs:
            if lang not in seen:
                seen.append(lang)
    has_ita = "ITA" in seen
    rest = sorted(c for c in seen if c != "ITA")
    merged = (["ITA"] + rest) if has_ita else rest
    await set_lang(sp, merged, episode_langs if len(item.video_files) > 1 else None)
    return JSONResponse({"ok": True, "langs": merged, "episode_langs": episode_langs})
