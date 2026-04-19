"""Unit3Dbot.json read/write + ITA_* env readonly view."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import config

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings():
    cfg = config.load()
    return JSONResponse({
        "config": config.mask_secrets(cfg),
        "env": config.env_readonly(),
        "config_path": str(config.config_path()),
    })


@router.put("/settings")
async def put_settings(incoming: dict):
    existing = config.load()
    merged = {**existing, **config.merge_secrets(existing, incoming)}
    config.save(merged)
    return JSONResponse({"ok": True, "config": config.mask_secrets(merged)})
