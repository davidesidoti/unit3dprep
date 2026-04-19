"""Torrent-client queue (qBittorrent/Transmission/rTorrent)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import clients, config

router = APIRouter(prefix="/api", tags=["queue"])


def _client():
    return clients.get_client(config.load())


@router.get("/queue")
async def list_queue():
    cli = _client()
    try:
        items = await cli.list()
    except NotImplementedError as e:
        return JSONResponse({"client": cli.name, "torrents": [], "error": str(e)}, status_code=200)
    except Exception as e:
        raise HTTPException(502, f"{cli.name} error: {e}")
    return JSONResponse({
        "client": cli.name,
        "torrents": [asdict(t) for t in items],
    })


@router.post("/queue/{torrent_hash}/reseed")
async def reseed(torrent_hash: str):
    cli = _client()
    try:
        await cli.reseed(torrent_hash)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))
    return JSONResponse({"ok": True})


@router.delete("/queue/{torrent_hash}")
async def remove(torrent_hash: str, delete_files: bool = False):
    cli = _client()
    try:
        await cli.remove(torrent_hash, delete_files=delete_files)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))
    return JSONResponse({"ok": True})
