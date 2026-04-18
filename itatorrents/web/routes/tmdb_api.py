"""TMDB API routes: search, set, clear."""
import asyncio
import os

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from ...core import tmdb_fetch_bilingual, tmdb_poster_url, tmdb_search, tmdb_year
from ..tmdb_cache import delete_cache, set_cache

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
        data = await loop.run_in_executor(None, tmdb_fetch_bilingual, tmdb_kind, tmdb_id, TMDB_API_KEY)
    except Exception as e:
        raise HTTPException(502, f"TMDB error: {e}")

    title = data.get("title") or ""
    title_en = data.get("title_en", "")
    original_title = data.get("original_title", "")
    year = tmdb_year(data, tmdb_kind)
    poster = tmdb_poster_url(data)
    overview = (data.get("overview") or "")[:300]
    overview_en = (data.get("overview_en") or "")[:300]

    await set_cache(
        source_path,
        tmdb_id=tmdb_id,
        tmdb_kind=tmdb_kind,
        title=title,
        title_en=title_en,
        original_title=original_title,
        year=year,
        poster=poster,
        overview=overview,
        overview_en=overview_en,
    )

    return JSONResponse({
        "ok": True,
        "tmdb_id": tmdb_id,
        "tmdb_kind": tmdb_kind,
        "title": title,
        "title_en": title_en,
        "original_title": original_title,
        "year": year,
        "poster": poster,
        "overview": overview,
        "overview_en": overview_en,
    })


# ---------------------------------------------------------------------------
# POST /api/tmdb/clear — remove cache entry
# ---------------------------------------------------------------------------

@router.post("/api/tmdb/clear")
async def api_tmdb_clear(source_path: str = Form(...)):
    await delete_cache(source_path)
    return JSONResponse({"ok": True})
