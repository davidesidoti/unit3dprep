"""Tracker lookups by TMDB id + content fingerprint.

Two users of the same primitive:

* :func:`find_duplicate` — pre-upload duplicate detection. Webup 0.0.25 does
  not implement it (`DUPLICATE_ON` / `SKIP_DUPLICATE` are commented
  `# Todo Not yet implemented` in its `config/settings.py`). The legacy
  `unit3dup` CLI used to query the tracker by TMDB id and refuse the upload
  when an existing torrent had the *exact* same file size in bytes —
  irrespective of name/encode/etc. We replicate that as a bridge pre-flight.
  Triggered by the `W_DUPLICATE_CHECK` runtime setting (default ON).
* :func:`find_recent_match` — post-upload confirmation, used when webup cannot
  tell us whether the tracker accepted the torrent.

Both identify a torrent by *content* (file count, per-file byte sizes, total
size), never by name.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

log = logging.getLogger("unit3dprep.duplicate_check")

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# How far back a tracker entry may have been created and still count as "the
# torrent we just uploaded". Generous, to absorb clock skew against the tracker.
DEFAULT_RECENT_WINDOW = 1800.0


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


def _parse_created_at(value: Any) -> datetime | None:
    """Parse a tracker ``created_at`` into an aware datetime (UTC assumed)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _summarize(entry: dict[str, Any], attrs: dict[str, Any], tmdb_int: int, delta: int) -> dict[str, Any]:
    """Flatten a tracker entry into the dict shape the API/UI consume."""
    return {
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


def _prepare(
    tmdb_id: int | str | None, total_size: int | None, tolerance_pct: float,
) -> tuple[int, int, int] | None:
    """``(tmdb_id, total_bytes, tolerance_bytes)`` or ``None`` if unusable."""
    if not tmdb_id or not total_size:
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
    return tmdb_int, total_int, int(round(total_int * tol / 100.0))


async def _fetch_entries(tracker_url: str, api_token: str, tmdb_int: int) -> list[dict[str, Any]] | None:
    """Tracker entries for a TMDB id. ``None`` marks a failed API call —
    callers must not read that as "nothing on the tracker"."""
    base = tracker_url.rstrip("/")
    url = f"{base}/api/torrents/filter"
    params = {"tmdbId": str(tmdb_int), "api_token": api_token, "perPage": "100"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("tracker query failed (%s): %s", url, e)
        return None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict)]


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
    prepared = _prepare(tmdb_id, total_size, tolerance_pct)
    if not tracker_url or not api_token or prepared is None:
        return None
    tmdb_int, total_int, tolerance_bytes = prepared

    entries = await _fetch_entries(tracker_url, api_token, tmdb_int)
    if not entries:
        return None

    best: dict[str, Any] | None = None
    best_delta = -1
    for entry in entries:
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
            best = _summarize(entry, attrs, tmdb_int, delta)
        if best_delta == 0:
            break
    return best


def _select_recent(
    entries: list[dict[str, Any]],
    *,
    num_files: int | None,
    total_size: int,
    file_sizes: list[int] | None,
    tolerance_bytes: int,
    cutoff: datetime,
    tmdb_int: int,
) -> dict[str, Any] | None:
    """Newest entry matching the fingerprint and created at/after ``cutoff``.

    An entry without a parseable ``created_at`` is skipped: we cannot tell it
    apart from a torrent that was already on the tracker.
    """
    newest: dict[str, Any] | None = None
    newest_at: datetime | None = None
    for entry in entries:
        attrs = entry.get("attributes") or {}
        delta = _entry_delta(
            attrs,
            num_files=num_files,
            total_size=total_size,
            file_sizes=file_sizes,
            tolerance_bytes=tolerance_bytes,
        )
        if delta is None:
            continue
        created = _parse_created_at(attrs.get("created_at"))
        if created is None or created < cutoff:
            continue
        if newest_at is None or created > newest_at:
            newest_at = created
            newest = _summarize(entry, attrs, tmdb_int, delta)
    return newest


async def find_recent_match(
    *,
    tracker_url: str,
    api_token: str,
    tmdb_id: int | str | None,
    num_files: int | None,
    total_size: int | None,
    file_sizes: list[int] | None = None,
    within_seconds: float = DEFAULT_RECENT_WINDOW,
    attempts: int = 2,
    retry_delay: float = 2.0,
) -> dict[str, Any] | None:
    """Confirm that a torrent we just sent actually reached the tracker.

    Webup raises when the tracker answers the upload POST with anything other
    than JSON (ITT replies ``200 text/html`` on success, and
    `itt_tracker_helper._post` calls `resp.json()` unconditionally), so a
    perfectly successful upload surfaces to us as an HTTP 500. This looks the
    torrent up by TMDB id + exact content fingerprint instead of trusting that
    response.

    The match is exact — same file count, same per-file sizes, same total — and
    the entry must be younger than ``within_seconds``, so an older duplicate is
    never mistaken for our upload. The API call is retried once because a
    transient failure would otherwise read as "the upload did not land".
    """
    prepared = _prepare(tmdb_id, total_size, 0.0)
    if not tracker_url or not api_token or prepared is None:
        return None
    tmdb_int, total_int, tolerance_bytes = prepared
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(0.0, within_seconds))

    rounds = max(1, attempts)
    for attempt in range(rounds):
        entries = await _fetch_entries(tracker_url, api_token, tmdb_int)
        if entries:
            match = _select_recent(
                entries,
                num_files=num_files,
                total_size=total_int,
                file_sizes=file_sizes,
                tolerance_bytes=tolerance_bytes,
                cutoff=cutoff,
                tmdb_int=tmdb_int,
            )
            if match is not None:
                return match
        if attempt + 1 < rounds:
            await asyncio.sleep(retry_delay)
    return None
