"""Shared .env read/write + runtime U3DP_* env view + filesystem checks."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import config
from ...media import media_root, seedings_root

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings():
    cfg = config.load()
    env_path = config.config_path()
    return JSONResponse({
        "config": config.mask_secrets(cfg),
        "env": config.env_runtime(),
        "config_path": str(env_path),
        "env_path": str(env_path),
        "webup_envpath_dir": str(config.webup_envpath_dir()),
    })


@router.put("/settings")
async def put_settings(incoming: dict):
    existing = config.load()
    merged = {**existing, **config.merge_secrets(existing, incoming)}
    config.save(merged)
    return JSONResponse({"ok": True, "config": config.mask_secrets(merged)})


def _closest_existing(p: Path) -> Path | None:
    cur: Path | None = p
    while cur is not None:
        if cur.exists():
            return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent
    return None


@router.get("/settings/fs-check")
async def settings_fs_check():
    """Return whether MEDIA_ROOT and SEEDINGS_DIR are on the same filesystem.

    Walks up missing paths so a freshly-configured seedings dir still reports
    the parent filesystem it would live on.
    """
    media = media_root()
    seed = seedings_root()
    media_real = _closest_existing(media)
    seed_real = _closest_existing(seed)
    try:
        media_dev = os.stat(media_real).st_dev if media_real else None
    except OSError:
        media_dev = None
    try:
        seed_dev = os.stat(seed_real).st_dev if seed_real else None
    except OSError:
        seed_dev = None
    same = (media_dev is not None) and (media_dev == seed_dev)
    return JSONResponse({
        "media_root": str(media),
        "seedings_dir": str(seed),
        "media_exists": media.exists(),
        "seedings_exists": seed.exists(),
        "media_dev": media_dev,
        "seedings_dev": seed_dev,
        "same_fs": same,
    })
