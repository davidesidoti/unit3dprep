"""TMDB API + SSE enrichment routes."""
import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from ...core import tmdb_fetch, tmdb_poster_url, tmdb_search, tmdb_year
from ...media import CATEGORIES, scan_category
from ..tmdb_cache import delete_cache, get_many, set_cache
from ..templates_env import ROOT_PATH

router = APIRouter()

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")


# ---------------------------------------------------------------------------
# GET /api/tmdb/search?q=&year=&kind=
# ---------------------------------------------------------------------------

@router.get("/api/tmdb/search")
async def api_tmdb_search(request: Request, q: str = "", year: str = "", kind: str = "movie"):
    if not q:
        return JSONResponse({"results": []})
    if not TMDB_API_KEY:
        raise HTTPException(500, "TMDB_API_KEY not set")
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, tmdb_search, kind, q, year, TMDB_API_KEY)
    except Exception as e:
        raise HTTPException(502, str(e))
    return JSONResponse({"results": results})


# ---------------------------------------------------------------------------
# POST /api/tmdb/set  — fetch from TMDB and persist to cache
# ---------------------------------------------------------------------------

@router.post("/api/tmdb/set")
async def api_tmdb_set(
    request: Request,
    source_path: str = Form(...),
    tmdb_id: str = Form(...),
    tmdb_kind: str = Form("movie"),
):
    if not TMDB_API_KEY:
        raise HTTPException(500, "TMDB_API_KEY not set")
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, tmdb_fetch, tmdb_kind, tmdb_id, TMDB_API_KEY)
    except Exception as e:
        raise HTTPException(502, f"TMDB error: {e}")

    title = data.get("title") or data.get("name") or ""
    year = tmdb_year(data, tmdb_kind)
    poster = tmdb_poster_url(data)
    overview = (data.get("overview") or "")[:300]

    await set_cache(
        source_path,
        tmdb_id=tmdb_id,
        tmdb_kind=tmdb_kind,
        title=title,
        year=year,
        poster=poster,
        overview=overview,
    )

    return JSONResponse({
        "ok": True,
        "tmdb_id": tmdb_id,
        "tmdb_kind": tmdb_kind,
        "title": title,
        "year": year,
        "poster": poster,
        "overview": overview,
    })


# ---------------------------------------------------------------------------
# POST /api/tmdb/clear — remove cache entry
# ---------------------------------------------------------------------------

@router.post("/api/tmdb/clear")
async def api_tmdb_clear(source_path: str = Form(...)):
    await delete_cache(source_path)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# GET /library/{category}/enrich — SSE background TMDB enrichment
# ---------------------------------------------------------------------------

@router.get("/library/{category}/enrich")
async def library_enrich(request: Request, category: str):
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
                continue  # already cached — skip

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
            # Sanity-check: year must roughly match (±1) if both are present
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

            await asyncio.sleep(0.25)  # respect TMDB rate limit (~4 req/s)

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())
