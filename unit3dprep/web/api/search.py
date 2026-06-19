"""Tracker search + reseed triggers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ...i18n import get_request_lang, t
from .. import config, trackers

router = APIRouter(prefix="/api", tags=["search"])


def _build():
    return trackers.build_trackers(config.load())


@router.get("/search")
async def search(request: Request, q: str, tracker: str = "ITT"):
    if not q.strip():
        return JSONResponse({"results": [], "tracker": tracker})
    trk_map = _build()
    trk = trk_map.get(tracker.upper())
    if trk is None:
        raise HTTPException(404, t("err.tracker_unknown", get_request_lang(request), tracker=tracker))
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
