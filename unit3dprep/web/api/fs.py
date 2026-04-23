"""Filesystem browser (used by UploadModal FileBrowser)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ...media import media_root, seedings_root

router = APIRouter(prefix="/api", tags=["fs"])


def _allowed_roots() -> tuple[Path, ...]:
    return (media_root(), seedings_root(), Path.home())


def _is_allowed(p: Path) -> bool:
    try:
        rp = p.resolve()
    except Exception:
        return False
    return any(str(rp).startswith(str(r.resolve())) for r in _allowed_roots())


@router.get("/fs")
async def listdir(path: str = ""):
    if not path:
        target = Path.home()
    else:
        target = Path(path)
    if not _is_allowed(target):
        raise HTTPException(403, "Path not allowed")
    if not target.exists():
        raise HTTPException(404, "Path not found")
    if target.is_file():
        return JSONResponse({
            "path": str(target),
            "parent": str(target.parent),
            "entries": [],
            "is_file": True,
        })
    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            entries.append({
                "name": child.name,
                "path": str(child),
                "type": "dir" if is_dir else "file",
            })
    except PermissionError:
        raise HTTPException(403, "Permission denied")
    return JSONResponse({
        "path": str(target),
        "parent": str(target.parent) if target != target.parent else str(target),
        "entries": entries,
        "is_file": False,
    })
