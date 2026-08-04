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
from collections.abc import Callable
from typing import Any

import httpx

from . import config

log = logging.getLogger("unit3dprep.arr")

KINDS = ("radarr", "sonarr")
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_CACHE_TTL = 60.0

_cache: dict[str, Any] = {"data": None, "at": 0.0, "gen": 0}
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


def _exc_detail(e: Exception) -> str:
    """``str(e)``, falling back to the exception's class name when that's empty.

    httpx.ReadError/WriteError/ProxyError/UnsupportedProtocol stringify to
    ``""`` when raised without a message — the same trap already hit and
    fixed in ``webup_client.py``'s ``_post``/``_get`` (see the comment
    there). Without this, both the user-facing fallback message and the log
    lines in ``build_index`` would render with nothing after the colon.
    """
    return str(e) or e.__class__.__name__


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
    if isinstance(e, ValueError):
        # r.json() on a non-JSON 200 raises json.JSONDecodeError (a
        # ValueError, not an httpx exception) — realistic with
        # follow_redirects=True, e.g. an auth proxy silently redirecting to
        # an HTML login page instead of answering the API call.
        return "Risposta non valida — l'URL non punta a Radarr/Sonarr."
    return f"Richiesta fallita: {_exc_detail(e)}"


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


async def _skip() -> None:
    """Placeholder awaitable for the ``asyncio.gather`` slot of an unconfigured instance."""
    return None


# ---------------------------------------------------------------------------
# Cached index
# ---------------------------------------------------------------------------

def invalidate_cache() -> None:
    """Drop the cached index and bump the generation counter.

    The counter — not just clearing ``data`` — is what keeps this safe
    against a build already in flight; see ``build_index``.
    """
    _cache["data"] = None
    _cache["at"] = 0.0
    _cache["gen"] += 1


def _parse_index(
    kind: str,
    parse: Callable[[Any], dict[str, dict[str, Any]]],
    raw: Any,
    errors: dict[str, str | None],
) -> dict[str, dict[str, Any]]:
    """Run an index parser, recording a failure instead of propagating it.

    The parsers are total against hostile input today, so this never fires —
    it keeps ``build_index``'s "must never raise" contract structural rather
    than dependent on that staying true through future edits.
    """
    try:
        return parse(raw)
    except Exception as e:  # noqa: BLE001 — never let this break the library
        errors[kind] = error_msg(e)
        log.warning("%s: index not parsed — %s", kind.capitalize(), _exc_detail(e))
        return {}


async def build_index(*, force: bool = False) -> dict[str, Any]:
    """Full Radarr + Sonarr index, fetched concurrently, one request per instance.

    The lock is held across the fetch, not just the cache read/write, so
    concurrent callers single-flight onto one fetch instead of each firing
    its own request to Radarr/Sonarr on every TTL expiry: a waiter re-checks
    the TTL as soon as it acquires the lock and gets the fresh value for
    free, and the httpx timeout bounds how long the critical section can
    run. The generation counter guards the other direction — ``invalidate_cache()``
    deliberately does not take the lock, so it can land while a fetch started
    before it is still in flight; without the check, that fetch would finish
    afterwards and silently resurrect the pre-invalidation state under a
    fresh timestamp, undoing the invalidation for a full TTL.

    A failure on one instance does not stop the other from populating: it
    lands in ``errors`` and the frontend surfaces it without losing the rest.
    """
    async with _cache_lock:
        cached = _cache["data"]
        if cached is not None and not force and (time.monotonic() - _cache["at"]) < _CACHE_TTL:
            return cached  # shared by every caller until the next fetch — read-only
        gen = _cache["gen"]

        errors: dict[str, str | None] = {"radarr": None, "sonarr": None}
        has_radarr = configured("radarr")
        has_sonarr = configured("sonarr")

        raw_radarr, raw_sonarr = await asyncio.gather(
            _get_json("radarr", "/api/v3/movie") if has_radarr else _skip(),
            _get_json("sonarr", "/api/v3/series") if has_sonarr else _skip(),
            return_exceptions=True,
        )

        # `gather(return_exceptions=True)` hands back a child's BaseException
        # (e.g. CancelledError) instead of raising it, and those are not
        # `Exception` — testing the narrower type would let one fall through to
        # the parse branch and publish an empty index as authoritative.
        movies: dict[str, dict[str, Any]] = {}
        if isinstance(raw_radarr, BaseException):
            errors["radarr"] = error_msg(raw_radarr)
            log.warning("Radarr: index not built — %s", _exc_detail(raw_radarr))
        elif has_radarr:
            movies = _parse_index("radarr", movie_index, raw_radarr, errors)

        series: dict[str, dict[str, Any]] = {}
        if isinstance(raw_sonarr, BaseException):
            errors["sonarr"] = error_msg(raw_sonarr)
            log.warning("Sonarr: index not built — %s", _exc_detail(raw_sonarr))
        elif has_sonarr:
            series = _parse_index("sonarr", series_index, raw_sonarr, errors)

        data = {
            "configured": {"radarr": has_radarr, "sonarr": has_sonarr},
            "movies": movies,
            "series": series,
            "errors": errors,
        }
        if _cache["gen"] == gen:  # no invalidate_cache() landed mid-fetch — safe to store
            _cache["data"] = data
            _cache["at"] = time.monotonic()
        return data  # same caveat as the cached branch above — read-only


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
