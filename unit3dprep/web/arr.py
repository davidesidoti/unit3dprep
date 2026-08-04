"""Radarr / Sonarr — read the monitored state and switch it off.

Pure helpers (index building, payload mutation) are kept apart from the HTTP
calls so they can be exercised without a live Radarr or Sonarr.

Library items are matched to *arr records by path: both sides see the same
filesystem, so the ``path`` field these APIs return is identical to the
library item's own path.
"""
from __future__ import annotations

import asyncio
import logging
import posixpath
import time
from typing import Any

import httpx

from . import config

log = logging.getLogger("unit3dprep.arr")

KINDS = ("radarr", "sonarr")
_TIMEOUT = httpx.Timeout(15.0)
_CACHE_TTL = 60.0

_cache: dict[str, Any] = {"data": None, "at": 0.0}
_cache_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def creds(kind: str) -> tuple[str, str]:
    """(base_url without trailing slash, api_key) for ``radarr`` or ``sonarr``."""
    prefix = "W_RADARR" if kind == "radarr" else "W_SONARR"
    base = config.runtime_setting(f"{prefix}_URL", "").strip().rstrip("/")
    token = config.runtime_setting(f"{prefix}_APIKEY", "").strip()
    return base, token


def configured(kind: str) -> bool:
    if kind not in KINDS:
        return False
    base, token = creds(kind)
    return bool(base) and bool(token) and token not in {"no_key", "no_pass"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def norm_path(p: str) -> str:
    """Canonical form of a path, used as the index key.

    Radarr/Sonarr and unit3dprep always share a Linux filesystem in every
    supported deployment, so normalization is anchored to ``posixpath``
    rather than the host OS's path module — ``os.path.normpath`` would
    rewrite ``/`` to ``\\`` when this module is imported under a native
    Windows interpreter (e.g. for local testing), which is never what the
    actual Radarr/Sonarr paths look like.
    """
    if not p:
        return ""
    n = posixpath.normpath(str(p))
    return n.rstrip("/\\") or n


def movie_index(payload: Any) -> dict[str, dict[str, Any]]:
    """``{path: {id, monitored, title}}`` from Radarr ``GET /api/v3/movie``."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, list):
        return out
    for m in payload:
        if not isinstance(m, dict):
            continue
        path = norm_path(m.get("path") or "")
        mid = m.get("id")
        if not path or not isinstance(mid, int):
            continue
        out[path] = {
            "id": mid,
            "monitored": bool(m.get("monitored")),
            "title": str(m.get("title") or ""),
        }
    return out


def series_index(payload: Any) -> dict[str, dict[str, Any]]:
    """``{path: {id, monitored, seasons, title}}`` from Sonarr ``GET /api/v3/series``.

    ``seasons`` is keyed by season number as a string so it survives the JSON
    round-trip to the frontend.
    """
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, list):
        return out
    for s in payload:
        if not isinstance(s, dict):
            continue
        path = norm_path(s.get("path") or "")
        sid = s.get("id")
        if not path or not isinstance(sid, int):
            continue
        seasons: dict[str, bool] = {}
        for season in s.get("seasons") or []:
            if isinstance(season, dict) and isinstance(season.get("seasonNumber"), int):
                seasons[str(season["seasonNumber"])] = bool(season.get("monitored"))
        out[path] = {
            "id": sid,
            "monitored": bool(s.get("monitored")),
            "seasons": seasons,
            "title": str(s.get("title") or ""),
        }
    return out


def error_msg(e: Exception) -> str:
    """User-facing message for a Radarr/Sonarr failure (Italian, like the ITT one)."""
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None) if resp is not None else None
    if code == 401:
        return "API key rifiutata (401)."
    if code == 404:
        return "Endpoint non trovato (404) — controlla l'URL."
    if code is not None:
        return f"Errore HTTP {code}."
    if isinstance(e, httpx.TimeoutException):
        return "Timeout nella richiesta."
    if isinstance(e, httpx.ConnectError):
        return "Connessione rifiutata — servizio spento o URL errato."
    return f"Richiesta fallita: {e}"


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def _client(base: str, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base,
        headers={"X-Api-Key": token},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )


async def _get_json(kind: str, path: str, params: dict[str, Any] | None = None) -> Any:
    base, token = creds(kind)
    async with _client(base, token) as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r.json()


async def _put_json(kind: str, path: str, body: Any) -> None:
    base, token = creds(kind)
    async with _client(base, token) as c:
        r = await c.put(path, json=body)
        r.raise_for_status()


# ---------------------------------------------------------------------------
# Cached index
# ---------------------------------------------------------------------------

def invalidate_cache() -> None:
    _cache["data"] = None
    _cache["at"] = 0.0


async def build_index(*, force: bool = False) -> dict[str, Any]:
    """Full Radarr + Sonarr index, one request per instance.

    A failure on one instance does not stop the other from populating: it lands
    in ``errors`` and the frontend surfaces it without losing the rest.
    """
    async with _cache_lock:
        cached = _cache["data"]
        if cached is not None and not force and (time.monotonic() - _cache["at"]) < _CACHE_TTL:
            return cached

    movies: dict[str, dict[str, Any]] = {}
    series: dict[str, dict[str, Any]] = {}
    errors: dict[str, str | None] = {"radarr": None, "sonarr": None}
    has_radarr = configured("radarr")
    has_sonarr = configured("sonarr")

    if has_radarr:
        try:
            movies = movie_index(await _get_json("radarr", "/api/v3/movie"))
        except Exception as e:  # noqa: BLE001 — never let this break the library
            errors["radarr"] = error_msg(e)
            log.warning("Radarr: index not built — %s", e)
    if has_sonarr:
        try:
            series = series_index(await _get_json("sonarr", "/api/v3/series"))
        except Exception as e:  # noqa: BLE001
            errors["sonarr"] = error_msg(e)
            log.warning("Sonarr: index not built — %s", e)

    data = {
        "configured": {"radarr": has_radarr, "sonarr": has_sonarr},
        "movies": movies,
        "series": series,
        "errors": errors,
    }
    async with _cache_lock:
        _cache["data"] = data
        _cache["at"] = time.monotonic()
    return data


async def test_connection(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        return {"ok": False, "error": "Servizio sconosciuto."}
    if not configured(kind):
        return {"ok": False, "error": "URL o API key mancanti."}
    try:
        data = await _get_json(kind, "/api/v3/system/status")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": error_msg(e)}
    data = data if isinstance(data, dict) else {}
    return {
        "ok": True,
        "version": str(data.get("version") or ""),
        "instance_name": str(data.get("instanceName") or ""),
    }
