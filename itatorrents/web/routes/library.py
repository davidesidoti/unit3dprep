"""Library browse routes: movies / series / anime list + detail."""
import asyncio
import json
import os
from typing import AsyncGenerator

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from ...core import audio_languages, tmdb_fetch_bilingual, tmdb_poster_url, tmdb_search, tmdb_year
from ...media import CATEGORIES, get_item, scan_category
from ..db import list_uploads, record_upload
from ..lang_cache import delete_lang, get_lang, get_many_langs, set_lang
from ..tmdb_cache import get_cache, get_many, set_cache
from ..templates_env import ROOT_PATH, templates

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

router = APIRouter()

CATEGORY_LABELS = {
    "movies": "Movies",
    "series": "Series",
    "anime": "Anime",
}


def _default_tmdb_kind(item) -> str:
    return "tv" if item.kind == "series" else "movie"


async def _enrich_item(item, cache: dict, uploaded_source_paths: set, lang_cache: dict | None = None):
    """Inject TMDB cache + upload status + lang cache into a MediaItem in-place."""
    sp = str(item.path)                    # unresolved — cache key
    sp_resolved = str(item.path.resolve()) # resolved — DB comparison

    # TMDB from series-level cache key
    tmdb = cache.get(sp)
    if tmdb:
        item.tmdb_id = tmdb.get("tmdb_id", "")
        item.tmdb_kind = tmdb.get("tmdb_kind", "") or _default_tmdb_kind(item)
        item.tmdb_title = tmdb.get("title", "")
        item.tmdb_title_en = tmdb.get("title_en", "")
        item.tmdb_original_title = tmdb.get("original_title", "")
        item.tmdb_poster = tmdb.get("poster", "")
        item.tmdb_overview = tmdb.get("overview", "")
        item.tmdb_overview_en = tmdb.get("overview_en", "")

    if item.kind == "series":
        all_langs: list[str] = []
        any_scanned = False
        for season in item.seasons:
            ssp = str(season.path)
            ssp_resolved = str(season.path.resolve())
            season.already_uploaded = ssp_resolved in uploaded_source_paths
            # Fall back to season-level cache if series level has none
            if not item.tmdb_id:
                s_tmdb = cache.get(ssp)
                if s_tmdb:
                    item.tmdb_id = s_tmdb.get("tmdb_id", "")
                    item.tmdb_kind = s_tmdb.get("tmdb_kind", "") or _default_tmdb_kind(item)
                    item.tmdb_title = s_tmdb.get("title", "")
                    item.tmdb_title_en = s_tmdb.get("title_en", "")
                    item.tmdb_original_title = s_tmdb.get("original_title", "")
                    item.tmdb_poster = s_tmdb.get("poster", "")
                    item.tmdb_overview = s_tmdb.get("overview", "")
                    item.tmdb_overview_en = s_tmdb.get("overview_en", "")
            # Lang cache — per-season
            if lang_cache is not None:
                lang_entry = lang_cache.get(ssp)
                if lang_entry:
                    season.available_langs = lang_entry.get("langs", [])
                    season.lang_scanned = True
                    any_scanned = True
                    for lang in season.available_langs:
                        if lang not in all_langs:
                            all_langs.append(lang)
        item.uploaded_season_numbers = [s.number for s in item.seasons if s.already_uploaded]
        if any_scanned:
            # ITA first
            has_ita = "ITA" in all_langs
            rest = sorted(c for c in all_langs if c != "ITA")
            item.available_langs = (["ITA"] + rest) if has_ita else rest
            item.lang_scanned = True
    else:
        # Movie — single entry keyed by item path
        if lang_cache is not None:
            lang_entry = lang_cache.get(sp)
            if lang_entry:
                item.available_langs = lang_entry.get("langs", [])
                item.episode_langs = lang_entry.get("episode_langs", {})
                item.lang_scanned = True

    if not item.tmdb_kind:
        item.tmdb_kind = _default_tmdb_kind(item)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(f"{ROOT_PATH}/library/movies")


@router.get("/library/{category}", response_class=HTMLResponse)
async def library_list(request: Request, category: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    items = scan_category(category)

    # Uploaded source paths for filtering
    uploads = await list_uploads()
    uploaded_source_paths = {r["source_path"] for r in uploads}

    # Collect all paths for bulk cache lookup
    all_paths = []
    for item in items:
        all_paths.append(str(item.path))
        for s in item.seasons:
            all_paths.append(str(s.path))
    cache = await get_many(all_paths)
    lang_cache = await get_many_langs(all_paths)

    filtered = []
    for item in items:
        await _enrich_item(item, cache, uploaded_source_paths, lang_cache)
        if item.kind == "movie":
            if str(item.path.resolve()) in uploaded_source_paths:
                continue  # hide already-uploaded movies
        filtered.append(item)

    has_missing_tmdb = any(not i.tmdb_id for i in filtered)
    has_missing_langs = any(not i.lang_scanned for i in filtered)

    return templates.TemplateResponse(request, "library.html", {
        "category": category,
        "label": CATEGORY_LABELS[category],
        "items": filtered,
        "active": category,
        "has_missing_tmdb": has_missing_tmdb,
        "has_missing_langs": has_missing_langs,
    })


@router.get("/library/{category}/enrich")
async def library_enrich(request: Request, category: str):
    """SSE: auto-fetch TMDB for items missing cache entries."""
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")

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
                continue  # already cached

            title = item.title
            year = item.year
            kind = "tv" if item.kind == "series" else "movie"

            try:
                results = await loop.run_in_executor(
                    None, tmdb_search, kind, title, year, TMDB_API_KEY
                )
            except Exception:
                await asyncio.sleep(0.25)
                continue

            if not results:
                await asyncio.sleep(0.25)
                continue

            best = results[0]
            # Sanity-check: year must roughly match (±1) if both present
            if year and best.get("year"):
                try:
                    if abs(int(best["year"]) - int(year)) > 1:
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
            t_en = data.get("title_en", "")
            orig = data.get("original_title", "")
            y = tmdb_year(data, kind) or best.get("year", "")
            poster = tmdb_poster_url(data) or best.get("poster", "")
            overview = (data.get("overview") or "")[:300]
            overview_en = (data.get("overview_en") or "")[:300]

            await set_cache(
                sp,
                tmdb_id=tmdb_id,
                tmdb_kind=kind,
                title=t,
                title_en=t_en,
                original_title=orig,
                year=y,
                poster=poster,
                overview=overview,
                overview_en=overview_en,
            )

            yield {
                "event": "enriched",
                "data": json.dumps({
                    "source_path": sp,
                    "tmdb_id": tmdb_id,
                    "title": t,
                    "title_en": t_en,
                    "original_title": orig,
                    "year": y,
                    "poster": poster,
                }),
            }

            await asyncio.sleep(0.25)  # ~4 req/s TMDB rate limit

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


@router.get("/library/{category}/scan-langs")
async def library_scan_langs(request: Request, category: str):
    """SSE: scan audio languages for items/seasons missing lang cache entries."""
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")

    async def generate() -> AsyncGenerator[dict, None]:
        items = scan_category(category)
        # Collect all paths to check cache
        all_paths = []
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
                    # Scan all video files in this season
                    episode_langs: dict[str, list[str]] = {}
                    all_langs: list[str] = []
                    for vf in season.video_files:
                        try:
                            langs = await loop.run_in_executor(None, audio_languages, vf)
                        except Exception:
                            langs = []
                        episode_langs[str(vf)] = langs
                        for lang in langs:
                            if lang not in all_langs:
                                all_langs.append(lang)
                        await asyncio.sleep(0.05)
                    # Normalise: ITA first
                    has_ita = "ITA" in all_langs
                    rest = sorted(c for c in all_langs if c != "ITA")
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
                all_langs: list[str] = []
                for vf in item.video_files:
                    try:
                        langs = await loop.run_in_executor(None, audio_languages, vf)
                    except Exception:
                        langs = []
                    episode_langs[str(vf)] = langs
                    for lang in langs:
                        if lang not in all_langs:
                            all_langs.append(lang)
                    await asyncio.sleep(0.05)
                has_ita = "ITA" in all_langs
                rest = sorted(c for c in all_langs if c != "ITA")
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


@router.post("/library/{category}/{item_name:path}/rescan-langs")
async def library_rescan_langs(request: Request, category: str, item_name: str):
    """Sincrono: force rescan lingue audio per un singolo media. JSON response."""
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, f"'{item_name}' non trovato in {category}")

    loop = asyncio.get_event_loop()
    result: dict = {}

    if item.kind == "series":
        seasons_result = {}
        for season in item.seasons:
            sp = str(season.path)
            episode_langs: dict[str, list[str]] = {}
            all_langs: list[str] = []
            for vf in season.video_files:
                try:
                    langs = await loop.run_in_executor(None, audio_languages, vf)
                except Exception:
                    langs = []
                episode_langs[str(vf)] = langs
                for lang in langs:
                    if lang not in all_langs:
                        all_langs.append(lang)
                await asyncio.sleep(0.05)
            has_ita = "ITA" in all_langs
            rest = sorted(c for c in all_langs if c != "ITA")
            merged = (["ITA"] + rest) if has_ita else rest
            await set_lang(sp, merged, episode_langs)
            seasons_result[sp] = {"langs": merged, "episode_langs": episode_langs}
        # Aggregate all series langs
        all_series_langs: list[str] = []
        for s_data in seasons_result.values():
            for lang in s_data["langs"]:
                if lang not in all_series_langs:
                    all_series_langs.append(lang)
        has_ita_series = "ITA" in all_series_langs
        rest_series = sorted(c for c in all_series_langs if c != "ITA")
        merged_series = (["ITA"] + rest_series) if has_ita_series else rest_series
        result = {
            "langs": merged_series,
            "has_ita": has_ita_series,
            "seasons": seasons_result,
        }
    else:
        sp = str(item.path)
        episode_langs: dict[str, list[str]] = {}
        all_langs: list[str] = []
        for vf in item.video_files:
            try:
                langs = await loop.run_in_executor(None, audio_languages, vf)
            except Exception:
                langs = []
            episode_langs[str(vf)] = langs
            for lang in langs:
                if lang not in all_langs:
                    all_langs.append(lang)
            await asyncio.sleep(0.05)
        has_ita = "ITA" in all_langs
        rest = sorted(c for c in all_langs if c != "ITA")
        merged = (["ITA"] + rest) if has_ita else rest
        await set_lang(sp, merged, episode_langs if len(item.video_files) > 1 else None)
        result = {
            "langs": merged,
            "has_ita": has_ita,
            "episode_langs": episode_langs,
        }

    return JSONResponse({"ok": True, **result})


@router.post("/library/{category}/{item_name:path}/mark-uploaded")
async def library_mark_uploaded(
    request: Request,
    category: str,
    item_name: str,
    season_path: str = Form(""),
):
    """Create a manual DB record so this item is filtered from the library."""
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, f"'{item_name}' non trovato in {category}")

    from pathlib import Path as _Path

    # source_path: season-level for series, item-level for movies
    if season_path:
        source_path = str(_Path(season_path).resolve())
        kind = "series"
    else:
        source_path = str(item.path.resolve())
        kind = item.kind

    seeding_path = f"__manual__:{source_path}"

    # Pull title/year/tmdb_id from cache if available
    cache_entry = await get_cache(str(item.path)) or await get_cache(source_path)
    title = (cache_entry.get("title") or item.title) if cache_entry else item.title
    year = (cache_entry.get("year") or item.year) if cache_entry else item.year
    tmdb_id = cache_entry.get("tmdb_id", "") if cache_entry else ""

    await record_upload(
        category=category,
        kind=kind,
        source_path=source_path,
        seeding_path=seeding_path,
        tmdb_id=tmdb_id,
        title=title,
        year=year,
        final_name="",
        exit_code=0,
    )

    return RedirectResponse(f"{ROOT_PATH}/library/{category}/{item_name}", status_code=303)


@router.get("/library/{category}/{item_name:path}", response_class=HTMLResponse)
async def library_detail(request: Request, category: str, item_name: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, f"'{item_name}' non trovato in {category}")

    uploads = await list_uploads()
    uploaded_source_paths = {r["source_path"] for r in uploads}

    all_paths = [str(item.path)] + [str(s.path) for s in item.seasons]
    cache = await get_many(all_paths)
    lang_cache = await get_many_langs(all_paths)
    await _enrich_item(item, cache, uploaded_source_paths, lang_cache)

    return templates.TemplateResponse(request, "detail.html", {
        "item": item,
        "category": category,
        "label": CATEGORY_LABELS[category],
        "active": category,
    })
