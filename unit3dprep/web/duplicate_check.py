"""Pre-upload duplicate detection against the ITT Unit3D API.

Webup 0.0.25 does not implement duplicate detection (`DUPLICATE_ON` /
`SKIP_DUPLICATE` are commented `# Todo Not yet implemented` in its
`config/settings.py`). The legacy `unit3dup` CLI used to query the
tracker by TMDB id and refuse the upload when an existing torrent had
the *exact* same file size in bytes — irrespective of name/encode/etc.
We replicate that behaviour here as a pre-flight performed by the
bridge before invoking webup.

Triggered by the `W_DUPLICATE_CHECK` runtime setting (default ON).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("unit3dprep.duplicate_check")

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def find_duplicate(
    *,
    tracker_url: str,
    api_token: str,
    tmdb_id: int | str | None,
    size_bytes: int | None,
) -> dict[str, Any] | None:
    """Query the tracker for any existing torrent that matches `size_bytes`.

    Returns a dict with the matched torrent details (suitable for showing
    to the user) when a duplicate is found, or ``None`` otherwise.

    Returns ``None`` (no false positives) when any of the inputs is
    missing, the API call fails, or the response is unexpected. The
    caller can always treat ``None`` as "no duplicate".
    """
    if not tracker_url or not api_token or not tmdb_id or not size_bytes:
        return None
    try:
        size_int = int(size_bytes)
        tmdb_int = int(tmdb_id)
    except (TypeError, ValueError):
        return None
    if size_int <= 0 or tmdb_int <= 0:
        return None

    base = tracker_url.rstrip("/")
    url = f"{base}/api/torrents/filter"
    params = {"tmdbId": str(tmdb_int), "api_token": api_token, "perPage": "100"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("duplicate check failed (%s): %s", url, e)
        return None

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None

    for entry in items:
        if not isinstance(entry, dict):
            continue
        attrs = entry.get("attributes") or {}
        existing_size = attrs.get("size")
        try:
            existing_size = int(existing_size) if existing_size is not None else None
        except (TypeError, ValueError):
            continue
        if existing_size != size_int:
            continue
        return {
            "id": entry.get("id") or attrs.get("id"),
            "name": attrs.get("name"),
            "size": existing_size,
            "type": attrs.get("type"),
            "resolution": attrs.get("resolution"),
            "category": attrs.get("category"),
            "uploader": attrs.get("uploader"),
            "seeders": attrs.get("seeders"),
            "leechers": attrs.get("leechers"),
            "created_at": attrs.get("created_at"),
            "details_link": attrs.get("details_link"),
            "tmdb_id": tmdb_int,
        }
    return None
