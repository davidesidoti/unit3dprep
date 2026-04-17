"""Library browse routes: movies / series / anime list + detail."""
import asyncio
import json
import os
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sse_starlette.sse import EventSourceResponse

from ...core import tmdb_fetch, tmdb_poster_url, tmdb_search, tmdb_year
from ...media import CATEGORIES, get_item, scan_category
from ..db import list_uploads
from ..tmdb_cache import get_many, set_cache
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


async def _enrich_item(item, cache: dict, uploaded_source_paths: set):
    """Inject TMDB cache + upload status into a MediaItem in-place."""
    sp = str(item.path)

    # TMDB from series-level cache key
    tmdb = cache.get(sp)
    if tmdb:
        item.tmdb_id = tmdb.get("tmdb_id", "")
        item.tmdb_kind = tmdb.get("tmdb_kind", "") or _default_tmdb_kind(item)
        item.tmdb_title = tmdb.get("title", "")
        item.tmdb_poster = tmdb.get("poster", "")
        item.tmdb_overview = tmdb.get("overview", "")

    if item.kind == "series":
        for season in item.seasons:
            ssp = str(season.path)
            season.already_uploaded = ssp in uploaded_source_paths
            # Fall back to season-level cache if series level has none
            if not item.tmdb_id:
                s_tmdb = cache.get(ssp)
                if s_tmdb:
                    item.tmdb_id = s_tmdb.get("tmdb_id", "")
                    item.tmdb_kind = s_tmdb.get("tmdb_kind", "") or _default_tmdb_kind(item)
                    item.tmdb_title = s_tmdb.get("title", "")
                    item.tmdb_poster = s_tmdb.get("poster", "")
                    item.tmdb_overview = s_tmdb.get("overview", "")
        item.uploaded_season_numbers = [s.number for s in item.seasons if s.already_uploaded]

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

    filtered = []
    for item in items:
        await _enrich_item(item, cache, uploaded_source_paths)
        if item.kind == "movie":
            if str(item.path) in uploaded_source_paths:
                continue  # hide already-uploaded movies
        filtered.append(item)

    has_missing_tmdb = any(not i.tmdb_id for i in filtered)

    return templates.TemplateResponse(request, "library.html", {
        "category": category,
        "label": CATEGORY_LABELS[category],
        "items": filtered,
        "active": category,
        "has_missing_tmdb": has_missing_tmdb,
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
                    None, tmdb_fetch, kind, tmdb_id, TMDB_API_KEY
                )
            except Exception:
                await asyncio.sleep(0.25)
                continue

            t = data.get("title") or data.get("name") or best["title"]
            y = tmdb_year(data, kind) or best.get("year", "")
            poster = tmdb_poster_url(data) or best.get("poster", "")
            overview = (data.get("overview") or "")[:300]

            await set_cache(
                sp,
                tmdb_id=tmdb_id,
                tmdb_kind=kind,
                title=t,
                year=y,
                poster=poster,
                overview=overview,
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

            await asyncio.sleep(0.25)  # ~4 req/s TMDB rate limit

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


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
    await _enrich_item(item, cache, uploaded_source_paths)

    return templates.TemplateResponse(request, "detail.html", {
        "item": item,
        "category": category,
        "label": CATEGORY_LABELS[category],
        "active": category,
    })
