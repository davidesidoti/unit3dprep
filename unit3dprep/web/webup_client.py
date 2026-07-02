"""HTTP client for Unit3DWebUp FastAPI bot.

Wraps the endpoints exposed by https://github.com/31December99/Unit3DWebUp.
Singleton pattern (one client per app lifespan) — held in `app.state.webup`.
Base URL resolved at instantiation time from `runtime_setting("WEBUP_URL")`.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import httpx

from .config import runtime_setting


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_HEALTH_TTL = 5.0

# `/scan`, `/maketorrent` and `/upload` are long-blocking calls: webup holds the
# HTTP response open until torrent hashing / TMDB lookup / screenshots finish,
# which for heavy media (season packs, large files) easily exceeds the default
# 180s read timeout. The real ceiling for these phases lives in the orchestrator
# (`asyncio.wait_for(..., SCAN_TIMEOUT / PHASE_TIMEOUT)`), so we disable httpx's
# read timeout here and let those guards bound the call. Otherwise the read
# timeout fires first and reports a spurious "request failed" while webup keeps
# going and completes at 100% — see the empty-message ReadTimeout symptom.
_LONG_OP_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0)

# Sentinel so `_post` can distinguish "caller passed no timeout" from an explicit
# `timeout=None` (which httpx interprets as "disable all timeouts").
_UNSET: Any = object()


def base_url() -> str:
    return runtime_setting("WEBUP_URL", DEFAULT_BASE_URL).rstrip("/")


def compute_job_id(file_or_folder_path: str) -> str:
    """Replicate Unit3DWebUp's job_id derivation: sha256(str(folder/subfolder)).

    Webup normalizes its scan_path with `os.path.normpath` before deriving
    job_ids, so we match that here.
    """
    import os as _os
    return hashlib.sha256(_os.path.normpath(str(file_or_folder_path)).encode()).hexdigest()


def compute_job_list_id(scan_path: str) -> str:
    return hashlib.sha256(str(scan_path).encode()).hexdigest()


class WebupError(RuntimeError):
    pass


class WebupClient:
    def __init__(self, base: str | None = None) -> None:
        self._base = (base or base_url()).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0),
        )
        self._health_at: float = 0.0
        self._health_ok: bool = False
        self._health_payload: dict[str, Any] = {}

    @property
    def base(self) -> str:
        return self._base

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict | None = None, *, timeout: Any = _UNSET) -> httpx.Response:
        try:
            if timeout is _UNSET:
                return await self._client.post(path, json=payload or {})
            return await self._client.post(path, json=payload or {}, timeout=timeout)
        except httpx.HTTPError as e:
            # ReadTimeout et al. stringify to "" — surface the class name so the
            # UI never shows a bare "request failed:" with no cause.
            detail = str(e) or e.__class__.__name__
            raise WebupError(f"webup {path} request failed: {detail}") from e

    async def _get(self, path: str) -> httpx.Response:
        try:
            return await self._client.get(path)
        except httpx.HTTPError as e:
            detail = str(e) or e.__class__.__name__
            raise WebupError(f"webup {path} request failed: {detail}") from e

    async def health(self, force: bool = False) -> dict[str, Any]:
        """Cheap reachability check + version readout. Cached for 5 s."""
        now = time.time()
        if not force and (now - self._health_at) < _HEALTH_TTL:
            return {"ok": self._health_ok, **self._health_payload}
        t0 = time.perf_counter()
        try:
            r = await self._client.post("/setting", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            prefs = data.get("userPreferences") or {}
            payload = {
                "version": prefs.get("UNIT3DWEBUP__VERSION") or prefs.get("VERSION") or "",
                "scan_path": prefs.get("SCAN_PATH"),
                "torrent_archive_path": prefs.get("TORRENT_ARCHIVE_PATH"),
                "torrent_client": prefs.get("TORRENT_CLIENT"),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._health_ok = True
            self._health_payload = payload
        except Exception as e:
            self._health_ok = False
            self._health_payload = {"error": str(e), "latency_ms": int((time.perf_counter() - t0) * 1000)}
        self._health_at = now
        return {"ok": self._health_ok, **self._health_payload}

    async def setting(self) -> dict[str, Any]:
        r = await self._post("/setting")
        r.raise_for_status()
        return r.json()

    async def setenv(self, key: str, value: str) -> dict[str, Any]:
        r = await self._post("/setenv", {"key": key, "value": value})
        r.raise_for_status()
        return r.json()

    async def scan(self) -> dict[str, Any]:
        # `path` field is required by the Pydantic model but ignored by the
        # endpoint — it reads `app.state.scan_path` (set via PREFS__SCAN_PATH).
        r = await self._post("/scan", {"path": "ignored"}, timeout=_LONG_OP_TIMEOUT)
        r.raise_for_status()
        return r.json()

    async def maketorrent(self, job_id: str) -> dict[str, Any] | None:
        r = await self._post("/maketorrent", {"job_id": job_id}, timeout=_LONG_OP_TIMEOUT)
        r.raise_for_status()
        return r.json() if r.text else None

    async def upload(self, job_id: str) -> dict[str, Any] | None:
        r = await self._post("/upload", {"job_id": job_id}, timeout=_LONG_OP_TIMEOUT)
        r.raise_for_status()
        return r.json() if r.text else None

    async def seed(self, job_id: str) -> tuple[int, dict[str, Any] | None]:
        r = await self._post("/seed", {"job_id": job_id})
        body: dict[str, Any] | None = None
        if r.text:
            try:
                body = r.json()
            except ValueError:
                body = None
        return r.status_code, body

    async def processall(self, job_list_id: str) -> dict[str, Any] | None:
        r = await self._post("/processall", {"job_list_id": job_list_id})
        r.raise_for_status()
        return r.json() if r.text else None

    async def set_tmdbid(self, job_id: str, new_id: str) -> None:
        r = await self._post("/settmdbid", {"job_id": job_id, "field_id": "tmdb_id", "new_id": str(new_id)})
        r.raise_for_status()

    async def set_tvdbid(self, job_id: str, new_id: str) -> None:
        r = await self._post("/settvdbid", {"job_id": job_id, "field_id": "tvdb_id", "new_id": str(new_id)})
        r.raise_for_status()

    async def set_imdbid(self, job_id: str, new_id: str) -> None:
        r = await self._post("/setimdbid", {"job_id": job_id, "field_id": "imdb_id", "new_id": str(new_id)})
        r.raise_for_status()

    async def set_poster_url(self, job_id: str, new_url: str) -> None:
        r = await self._post("/setposterurl", {"job_id": job_id, "field_id": "backdrop_path", "new_id": new_url})
        r.raise_for_status()

    async def set_poster_dname(self, job_id: str, new_name: str) -> None:
        r = await self._post("/setposterdname", {"job_id": job_id, "field_id": "display_name", "new_id": new_name})
        r.raise_for_status()

    async def filter_search(self, title: str) -> dict[str, Any]:
        r = await self._post("/filter", {"title": title})
        r.raise_for_status()
        return r.json()

    async def cjoblist(self, job_list_id: str) -> dict[str, Any] | None:
        r = await self._post("/cjoblist", {"job_list_id": job_list_id})
        r.raise_for_status()
        return r.json() if r.text else None


_singleton: WebupClient | None = None


def get_client() -> WebupClient:
    """Lazy singleton. Recreated when WEBUP_URL changes."""
    global _singleton
    target = base_url()
    if _singleton is None or _singleton.base != target:
        _singleton = WebupClient(target)
    return _singleton


async def shutdown_client() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.aclose()
        _singleton = None
