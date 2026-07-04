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


def _to_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _entry_file_sizes(attrs: dict[str, Any]) -> list[int]:
    """Sorted per-file byte sizes from a tracker torrent's ``files`` list."""
    files = attrs.get("files")
    if not isinstance(files, list):
        return []
    sizes: list[int] = []
    for f in files:
        if isinstance(f, dict):
            s = _to_int(f.get("size"))
            if s is not None:
                sizes.append(s)
    return sorted(sizes)


def _entry_delta(
    attrs: dict[str, Any],
    *,
    num_files: int | None,
    total_size: int,
    file_sizes: list[int] | None,
    tolerance_bytes: int,
) -> int | None:
    """Absolute size delta if ``attrs`` matches the fingerprint, else ``None``.

    A match requires the same file count (when both sides expose ``num_file``)
    and a total size within ``tolerance_bytes``. In exact mode (tolerance 0)
    the per-file size multiset must also match when both sides provide it —
    this rules out same-total/same-count torrents with a different make-up.
    Name/encode/release-group are irrelevant.
    """
    existing_size = _to_int(attrs.get("size"))
    if existing_size is None or existing_size <= 0:
        return None
    existing_num = _to_int(attrs.get("num_file"))
    if num_files and existing_num and existing_num != num_files:
        return None
    delta = abs(existing_size - total_size)
    if delta > tolerance_bytes:
        return None
    if tolerance_bytes == 0 and file_sizes:
        existing_sizes = _entry_file_sizes(attrs)
        if existing_sizes and existing_sizes != sorted(file_sizes):
            return None
    return delta


async def find_duplicate(
    *,
    tracker_url: str,
    api_token: str,
    tmdb_id: int | str | None,
    num_files: int | None,
    total_size: int | None,
    file_sizes: list[int] | None = None,
    tolerance_pct: float = 0.0,
) -> dict[str, Any] | None:
    """Query the tracker for an existing torrent matching the local fingerprint.

    The fingerprint is the number of video files (``num_files``), their total
    byte size (``total_size``) and — optionally — the sorted list of per-file
    byte sizes (``file_sizes``). ``tolerance_pct`` widens the total-size match
    to catch near-identical re-encodes (e.g. 12.00 vs 12.02 GB); ``0`` means an
    exact match and additionally compares the per-file size multiset.

    Returns a dict with the matched torrent details (the closest one when
    several qualify) or ``None`` when nothing matches, an input is missing, or
    the API call fails. ``None`` is always safe to treat as "no duplicate".
    """
    if not tracker_url or not api_token or not tmdb_id or not total_size:
        return None
    try:
        total_int = int(total_size)
        tmdb_int = int(tmdb_id)
    except (TypeError, ValueError):
        return None
    if total_int <= 0 or tmdb_int <= 0:
        return None

    try:
        tol = max(0.0, float(tolerance_pct))
    except (TypeError, ValueError):
        tol = 0.0
    tolerance_bytes = int(round(total_int * tol / 100.0))

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

    best: dict[str, Any] | None = None
    best_delta = -1
    for entry in items:
        if not isinstance(entry, dict):
            continue
        attrs = entry.get("attributes") or {}
        delta = _entry_delta(
            attrs,
            num_files=num_files,
            total_size=total_int,
            file_sizes=file_sizes,
            tolerance_bytes=tolerance_bytes,
        )
        if delta is None:
            continue
        if best is None or delta < best_delta:
            best_delta = delta
            best = {
                "id": entry.get("id") or attrs.get("id"),
                "name": attrs.get("name"),
                "size": _to_int(attrs.get("size")),
                "num_file": _to_int(attrs.get("num_file")),
                "type": attrs.get("type"),
                "resolution": attrs.get("resolution"),
                "category": attrs.get("category"),
                "uploader": attrs.get("uploader"),
                "seeders": attrs.get("seeders"),
                "leechers": attrs.get("leechers"),
                "created_at": attrs.get("created_at"),
                "details_link": attrs.get("details_link"),
                "tmdb_id": tmdb_int,
                "size_delta": delta,
                "approx": delta > 0,
            }
        if best_delta == 0:
            break
    return best
