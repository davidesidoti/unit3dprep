"""Torrent-client abstraction.

v1 wires up qBittorrent (Web API). Transmission/rTorrent surface as "not
implemented" so the Settings page can advertise them without crashing the
Queue view.
"""
from __future__ import annotations

import base64
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Torrent:
    hash: str
    name: str
    size: int
    progress: float
    state: str       # seeding|uploading|queued|error|pending|paused|other
    ratio: float
    category: str
    tracker: str
    save_path: str


class TorrentClient(ABC):
    name: str = "generic"

    @abstractmethod
    async def list(self) -> list[Torrent]: ...

    @abstractmethod
    async def reseed(self, torrent_hash: str) -> None: ...

    @abstractmethod
    async def remove(self, torrent_hash: str, delete_files: bool = False) -> None: ...

    async def add_torrent(
        self,
        torrent_bytes: bytes,
        *,
        save_path: str,
        paused: bool = True,
        skip_checking: bool = False,
        category: str | None = None,
        tags: str | None = None,
    ) -> None:
        raise NotImplementedError(f"{self.name} client does not support add_torrent")

    async def torrent_files(self, torrent_hash: str) -> list[dict]:
        raise NotImplementedError(f"{self.name} client does not support torrent_files")

    async def info_one(self, torrent_hash: str) -> dict | None:
        raise NotImplementedError(f"{self.name} client does not support info_one")

    async def recheck(self, torrent_hash: str) -> None:
        raise NotImplementedError(f"{self.name} client does not support recheck")

    async def resume(self, torrent_hash: str) -> None:
        raise NotImplementedError(f"{self.name} client does not support resume")

    async def pause(self, torrent_hash: str) -> None:
        raise NotImplementedError(f"{self.name} client does not support pause")


# ---------------------------------------------------------------------------
# qBittorrent Web API (v2)
# ---------------------------------------------------------------------------


_QBIT_STATE_MAP = {
    "uploading": "seeding",
    "stalledUP": "seeding",
    "forcedUP": "seeding",
    "queuedUP": "queued",
    "checkingUP": "seeding",
    "downloading": "uploading",
    "forcedDL": "uploading",
    "stalledDL": "uploading",
    "queuedDL": "queued",
    "checkingDL": "uploading",
    "metaDL": "uploading",
    "pausedUP": "paused",
    "pausedDL": "paused",
    "error": "error",
    "missingFiles": "error",
    "unknown": "pending",
    "allocating": "pending",
    "moving": "pending",
}


class QBittorrentClient(TorrentClient):
    name = "qbittorrent"

    def __init__(self, host: str, port: str | int, user: str, password: str):
        self.base = f"http://{host}:{port}"
        self.user = user
        self.password = password
        self._client: httpx.AsyncClient | None = None
        self._logged_in_at: float = 0.0

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base, timeout=15.0)
        # Re-login every 30 min to keep cookie fresh
        if time.time() - self._logged_in_at > 1800:
            r = await self._client.post(
                "/api/v2/auth/login",
                data={"username": self.user, "password": self.password},
                headers={"Referer": self.base},
            )
            if r.status_code != 200 or r.text.strip() != "Ok.":
                raise RuntimeError(f"qBittorrent login failed: {r.status_code} {r.text!r}")
            self._logged_in_at = time.time()
        return self._client

    async def list(self) -> list[Torrent]:
        cli = await self._http()
        r = await cli.get("/api/v2/torrents/info")
        r.raise_for_status()
        out: list[Torrent] = []
        for t in r.json():
            state = _QBIT_STATE_MAP.get(t.get("state", "unknown"), "pending")
            out.append(Torrent(
                hash=t.get("hash", ""),
                name=t.get("name", ""),
                size=int(t.get("size", 0) or 0),
                progress=float(t.get("progress", 0) or 0),
                state=state,
                ratio=float(t.get("ratio", 0) or 0),
                category=t.get("category", ""),
                tracker=t.get("tracker", ""),
                save_path=t.get("save_path", ""),
            ))
        return out

    async def reseed(self, torrent_hash: str) -> None:
        cli = await self._http()
        r = await cli.post("/api/v2/torrents/recheck", data={"hashes": torrent_hash})
        r.raise_for_status()
        r2 = await cli.post("/api/v2/torrents/resume", data={"hashes": torrent_hash})
        r2.raise_for_status()

    async def add_torrent(
        self,
        torrent_bytes: bytes,
        *,
        save_path: str,
        paused: bool = True,
        skip_checking: bool = False,
        category: str | None = None,
        tags: str | None = None,
    ) -> None:
        """Add a .torrent (raw bytes) pointing at `save_path`.

        For reseed the caller adds **paused** (so it never announces before the
        content is in place), hardlinks the matching files into the layout qBit
        reports via `torrent_files()`, then triggers an explicit `recheck()`.
        Keep `skip_checking` False so the initial progress reflects reality
        (0% until the content is hardlinked) rather than a spurious 100%. qBit's
        add endpoint does not return the infohash; callers diff `list()`
        before/after.
        """
        cli = await self._http()
        data: dict[str, str] = {
            "savepath": save_path,
            "paused": "true" if paused else "false",
            "skip_checking": "true" if skip_checking else "false",
            "autoTMM": "false",
        }
        if category:
            data["category"] = category
        if tags:
            data["tags"] = tags
        files = {"torrents": ("reseed.torrent", torrent_bytes, "application/x-bittorrent")}
        r = await cli.post("/api/v2/torrents/add", data=data, files=files)
        r.raise_for_status()
        if r.text.strip().lower() == "fails.":
            raise RuntimeError("qBittorrent rejected the .torrent file")

    async def torrent_files(self, torrent_hash: str) -> list[dict]:
        """Files qBit expects for a torrent: ``[{name, size, ...}]``.

        ``name`` is the path relative to the torrent root — the source of
        truth for where to hardlink the local content under the save path.
        """
        cli = await self._http()
        r = await cli.get("/api/v2/torrents/files", params={"hash": torrent_hash})
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []

    async def info_one(self, torrent_hash: str) -> dict | None:
        """Raw qBit torrent info for a single hash (raw `state` + `progress`)."""
        cli = await self._http()
        r = await cli.get("/api/v2/torrents/info", params={"hashes": torrent_hash})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
        return None

    async def recheck(self, torrent_hash: str) -> None:
        cli = await self._http()
        r = await cli.post("/api/v2/torrents/recheck", data={"hashes": torrent_hash})
        r.raise_for_status()

    async def resume(self, torrent_hash: str) -> None:
        cli = await self._http()
        r = await cli.post("/api/v2/torrents/resume", data={"hashes": torrent_hash})
        r.raise_for_status()

    async def pause(self, torrent_hash: str) -> None:
        cli = await self._http()
        r = await cli.post("/api/v2/torrents/pause", data={"hashes": torrent_hash})
        r.raise_for_status()

    async def remove(self, torrent_hash: str, delete_files: bool = False) -> None:
        cli = await self._http()
        r = await cli.post(
            "/api/v2/torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true" if delete_files else "false"},
        )
        r.raise_for_status()


class _NotImplementedClient(TorrentClient):
    def __init__(self, name: str):
        self.name = name

    async def list(self) -> list[Torrent]:
        raise NotImplementedError(f"{self.name} client not implemented yet")

    async def reseed(self, torrent_hash: str) -> None:
        raise NotImplementedError(f"{self.name} client not implemented yet")

    async def remove(self, torrent_hash: str, delete_files: bool = False) -> None:
        raise NotImplementedError(f"{self.name} client not implemented yet")


_client_cache: tuple[tuple, TorrentClient] | None = None


def get_client(cfg: dict[str, Any]) -> TorrentClient:
    global _client_cache
    which = (cfg.get("TORRENT_CLIENT") or "qbittorrent").lower()
    if which == "qbittorrent":
        host = cfg.get("QBIT_HOST", "127.0.0.1")
        port = cfg.get("QBIT_PORT", "15491")
        user = cfg.get("QBIT_USER", "admin")
        password = cfg.get("QBIT_PASS", "")
        key = ("qbittorrent", host, str(port), user, password)
        if _client_cache is not None and _client_cache[0] == key:
            return _client_cache[1]
        cli = QBittorrentClient(host=host, port=port, user=user, password=password)
        _client_cache = (key, cli)
        return cli
    if which == "transmission":
        return _NotImplementedClient("transmission")
    if which == "rtorrent":
        return _NotImplementedClient("rtorrent")
    return _NotImplementedClient(which)
