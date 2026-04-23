"""TMDB search + manual cache set/clear."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...core import tmdb_fetch_bilingual, tmdb_poster_url, tmdb_search, tmdb_year
from ..tmdb_cache import delete_cache, set_cache

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

router = APIRouter(prefix="/api", tags=["tmdb"])


@router.get("/tmdb/search")
async def search(q: str, year: str = "", kind: str = "movie"):
    if not TMDB_API_KEY:
        raise HTTPException(400, "TMDB_API_KEY not set")
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            None, tmdb_search, kind, q, year, TMDB_API_KEY
        )
    except Exception as e:
        raise HTTPException(502, str(e))
    return JSONResponse({"results": results})


class SetBody(BaseModel):
    source_path: str
    tmdb_id: str
    tmdb_kind: str = "movie"


@router.post("/tmdb/set")
async def set_manual(body: SetBody):
    if not TMDB_API_KEY:
        raise HTTPException(400, "TMDB_API_KEY not set")
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(
            None, tmdb_fetch_bilingual, body.tmdb_kind, body.tmdb_id, TMDB_API_KEY
        )
    except Exception as e:
        raise HTTPException(502, str(e))
    title = data.get("title") or ""
    year = tmdb_year(data, body.tmdb_kind)
    poster = tmdb_poster_url(data)
    await set_cache(
        body.source_path,
        tmdb_id=body.tmdb_id,
        tmdb_kind=body.tmdb_kind,
        title=title,
        title_en=data.get("title_en", ""),
        original_title=data.get("original_title", ""),
        year=year,
        poster=poster,
        overview=(data.get("overview") or "")[:300],
        overview_en=(data.get("overview_en") or "")[:300],
    )
    return JSONResponse({"ok": True, "title": title, "year": year, "poster": poster})


class ClearBody(BaseModel):
    source_path: str


@router.post("/tmdb/clear")
async def clear(body: ClearBody):
    await delete_cache(body.source_path)
    return JSONResponse({"ok": True})
