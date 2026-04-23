"""Tracker search + reseed triggers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import config, trackers

router = APIRouter(prefix="/api", tags=["search"])


def _build():
    return trackers.build_trackers(config.load())


@router.get("/search")
async def search(q: str, tracker: str = "ITT"):
    if not q.strip():
        return JSONResponse({"results": [], "tracker": tracker})
    trk_map = _build()
    trk = trk_map.get(tracker.upper())
    if trk is None:
        raise HTTPException(404, f"Unknown tracker '{tracker}'")
    try:
        results = await trk.search(q)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))
    return JSONResponse({
        "tracker": tracker.upper(),
        "results": [r.to_dict() for r in results],
    })


@router.post("/reseed/{tracker}/{torrent_id}")
async def reseed(tracker: str, torrent_id: int):
    # Placeholder: trigger a unit3dup reseed run for a known torrent id.
    # Real implementation would call unit3dup --reseed or use tracker download
    # endpoint + enqueue in torrent client. For v1 we expose a clean 501.
    raise HTTPException(501, "Reseed by tracker id not implemented")
