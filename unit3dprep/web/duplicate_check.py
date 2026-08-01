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

# A freshly accepted torrent does not show up in /api/torrents/filter straight
# away — measured misses several seconds after the upload, with the entry
# appearing later. Back off over ~2 minutes before concluding it never landed.
_RECENT_BACKOFF = (3.0, 6.0, 12.0, 20.0, 30.0, 45.0)


def _retry_after_seconds(resp: httpx.Response) -> float:
    """``Retry-After`` in seconds, 0 when absent or unparseable."""
    try:
        ra = resp.headers.get("retry-after")
        return float(ra) if ra else 0.0
    except (TypeError, ValueError):
        return 0.0


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
        # Carries the rsskey — the only way to fetch the .torrent (see
        # reseed.download_torrent_file). Saves re-querying the show endpoint.
        "download_link": attrs.get("download_link") or "",
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


async def _fetch_rows(
    url: str, params: dict[str, str], *, throttle_retries: int = 2,
) -> list[dict[str, Any]] | None:
    """GET a Unit3D torrent listing. ``None`` marks a failed API call — callers
    must not read that as "nothing on the tracker".

    Unit3D throttles its API, so a 429 is waited out (honouring ``Retry-After``,
    capped) rather than reported as a failure.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            for attempt in range(throttle_retries + 1):
                r = await client.get(url, params=params)
                if r.status_code == 429 and attempt < throttle_retries:
                    wait = min(_retry_after_seconds(r) or 10.0, 30.0)
                    log.info("tracker 429 — waiting %.0fs then retrying", wait)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                payload = r.json()
                break
            else:  # pragma: no cover — loop always breaks or raises
                return None
    except (httpx.HTTPError, ValueError) as e:
        log.warning("tracker query failed (%s): %s", url, e)
        return None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict)]


async def _fetch_entries(
    tracker_url: str, api_token: str, tmdb_int: int, *, throttle_retries: int = 2,
) -> list[dict[str, Any]] | None:
    """Tracker entries for a TMDB id, via the search/filter endpoint."""
    base = tracker_url.rstrip("/")
    return await _fetch_rows(
        f"{base}/api/torrents/filter",
        {"tmdbId": str(tmdb_int), "api_token": api_token, "perPage": "100"},
        throttle_retries=throttle_retries,
    )


async def _fetch_newest(
    tracker_url: str, api_token: str, *, per_page: int = 50, throttle_retries: int = 2,
) -> list[dict[str, Any]] | None:
    """The most recently uploaded torrents, newest first.

    ``/api/torrents/filter`` lags badly behind a fresh upload — measured on ITT
    2026-08-01: a torrent created at T was still missing from the filter results
    at T+2min and only showed up around T+7min, while the plain list endpoint
    (a straight newest-first listing) had it. So confirming a just-finished
    upload starts here, and only falls back to the TMDB filter.
    """
    base = tracker_url.rstrip("/")
    return await _fetch_rows(
        f"{base}/api/torrents",
        {"api_token": api_token, "perPage": str(per_page)},
        throttle_retries=throttle_retries,
    )


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
    require_tmdb: bool = True,
) -> dict[str, Any] | None:
    """Newest entry matching the fingerprint and created at/after ``cutoff``.

    An entry without a parseable ``created_at`` is skipped: we cannot tell it
    apart from a torrent that was already on the tracker. With ``require_tmdb``
    an entry that advertises a different ``tmdb_id`` is skipped too — the
    newest-uploads listing spans every title, so the fingerprint alone could in
    principle collide with somebody else's upload in the same window.
    """
    newest: dict[str, Any] | None = None
    newest_at: datetime | None = None
    for entry in entries:
        attrs = entry.get("attributes") or {}
        entry_tmdb = _to_int(attrs.get("tmdb_id"))
        if require_tmdb and entry_tmdb is not None and entry_tmdb != tmdb_int:
            continue
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
    backoff: tuple[float, ...] = _RECENT_BACKOFF,
    on_attempt: Any = None,
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
    never mistaken for our upload.

    A just-accepted torrent is not immediately visible on the filter endpoint,
    so the lookup is retried along ``backoff`` (delays in seconds between
    attempts) before concluding the upload did not land. ``on_attempt`` is an
    optional ``(index, total, found) -> None`` callback for progress reporting.
    """
    prepared = _prepare(tmdb_id, total_size, 0.0)
    if not tracker_url or not api_token or prepared is None:
        return None
    tmdb_int, total_int, tolerance_bytes = prepared
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(0.0, within_seconds))

    def _pick(entries: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        if not entries:
            return None
        return _select_recent(
            entries,
            num_files=num_files,
            total_size=total_int,
            file_sizes=file_sizes,
            tolerance_bytes=tolerance_bytes,
            cutoff=cutoff,
            tmdb_int=tmdb_int,
        )

    delays = tuple(backoff or ())
    total_rounds = len(delays) + 1
    for attempt in range(total_rounds):
        # Newest-uploads listing first: it sees a fresh torrent immediately,
        # the TMDB filter can lag minutes behind (see _fetch_newest).
        match = _pick(await _fetch_newest(tracker_url, api_token))
        if match is None:
            match = _pick(await _fetch_entries(tracker_url, api_token, tmdb_int))
        if on_attempt is not None:
            try:
                on_attempt(attempt + 1, total_rounds, match is not None)
            except Exception:  # a progress callback must never break the lookup
                log.debug("on_attempt callback failed", exc_info=True)
        if match is not None:
            return match
        if attempt < len(delays):
            await asyncio.sleep(delays[attempt])
    return None
