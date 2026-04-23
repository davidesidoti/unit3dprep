"""Tracker status (for sidebar online/offline indicators)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import config
from ..trackers import build_trackers

router = APIRouter(prefix="/api", tags=["trackers"])


@router.get("/trackers/status")
async def status():
    trk_map = build_trackers(config.load())
    names = list(trk_map.keys())
    statuses = await asyncio.gather(
        *(trk_map[n].status() for n in names), return_exceptions=True
    )
    out = []
    for name, s in zip(names, statuses):
        trk = trk_map[name]
        out.append({
            "name": name,
            "online": bool(s) if not isinstance(s, Exception) else False,
            "configured": bool(getattr(trk, "configured", False)),
        })
    return JSONResponse({"trackers": out})
