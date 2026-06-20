"""Reseed logic: re-seed ITT torrents the user already has on disk.

Unit3DWebUp is an upload-only pipeline (scan → maketorrent → upload → seed of
a *new* torrent) and exposes nothing for fetching an existing torrent or
listing 0-seed ones. So reseed talks to the ITT/Unit3D API + qBittorrent
directly:

  1. discover ITT torrents with **0 seeders** whose exact byte size matches a
     local single-file media item (movie or single episode), via tmdbId +
     size, reusing the duplicate-check pattern;
  2. download the `.torrent`;
  3. add it to qBit **paused + skip-check**, read the file layout qBit expects
     (`/torrents/files`), hardlink the local content into those paths, then
     recheck — qBit re-hashes and, if the content matches, seeds.

No bencode parsing is needed: qBit is the source of truth for the on-disk
layout.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx

from ..core import VIDEO_EXTENSIONS, hardlink_file, seedings_dir
from ..media import discover_categories, scan_category
from .clients import get_client
from .db import record_upload
from .tmdb_cache import get_many
from .trackers import _human_size, _resolution_for, _type_for

try:
    from guessit import guessit as _guessit
except ImportError:  # pragma: no cover
    _guessit = None  # type: ignore

log = logging.getLogger("unit3dprep.reseed")

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
# Serializes reseed runs: perform_reseed identifies the freshly-added torrent
# by diffing qBit's hash set before/after the add, which is only reliable when
# no other add runs concurrently.
_reseed_lock = asyncio.Lock()

_CHECKING_STATES = {
    "checkingUP", "checkingDL", "checkingResumeData",
    "queuedForChecking", "allocating", "checking", "moving",
}


# ---------------------------------------------------------------------------
# ITT request pacing
#
# Unit3D rate-limits its API; a big auto scan (one request per item) easily
# trips it. We pace all reseed ITT calls to stay under a configurable cap
# (`W_ITT_MAX_RPM`, requests/min, default 50; 0 disables) — a single batch
# stays under the cap so it's not slowed, while heavy/repeated scans get spread
# out — and retry on 429 honouring Retry-After, so the limit slows us down
# instead of failing.
# ---------------------------------------------------------------------------


def _itt_max_rpm() -> int:
    from . import config
    try:
        return int(config.runtime_setting("W_ITT_MAX_RPM", "50") or "50")
    except (TypeError, ValueError):
        return 50


class _RateLimiter:
    """At most `rpm` acquisitions per rolling 60s window, shared across all ITT
    requests. Serialized via a lock so concurrent callers pace correctly."""

    def __init__(self) -> None:
        self._times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        rpm = _itt_max_rpm()
        if rpm <= 0:
            return
        async with self._lock:
            loop = asyncio.get_event_loop()
            while True:
                now = loop.time()
                while self._times and now - self._times[0] >= 60.0:
                    self._times.popleft()
                if len(self._times) < rpm:
                    self._times.append(now)
                    return
                await asyncio.sleep(60.0 - (now - self._times[0]) + 0.05)


_itt_rate = _RateLimiter()


def _retry_after_seconds(resp: httpx.Response) -> float:
    try:
        ra = resp.headers.get("retry-after")
        return float(ra) if ra else 0.0
    except (TypeError, ValueError):
        return 0.0


async def _itt_get(
    client: httpx.AsyncClient, url: str, params: dict[str, str], *, retries: int = 3,
) -> httpx.Response:
    """GET an ITT API URL through the shared limiter, retrying on 429 (honouring
    Retry-After, capped) so a throttle slows us down instead of failing."""
    attempt = 0
    while True:
        await _itt_rate.acquire()
        r = await client.get(url, params=params)
        if r.status_code != 429 or attempt >= retries:
            return r
        wait = _retry_after_seconds(r) or (5.0 * (attempt + 1))
        log.info("ITT 429 — waiting %.0fs then retrying (%d/%d)", min(wait, 30.0), attempt + 1, retries)
        await asyncio.sleep(min(wait, 30.0))
        attempt += 1


# ---------------------------------------------------------------------------
# ITT / Unit3D API helpers
# ---------------------------------------------------------------------------


def _itt_creds(cfg: dict[str, Any]) -> tuple[str, str]:
    base = (cfg.get("ITT_URL") or "").rstrip("/")
    token = (cfg.get("ITT_APIKEY") or "").strip()
    return base, token


def _itt_configured(base: str, token: str) -> bool:
    return bool(base) and bool(token) and token not in {"no_key", ""}


async def _filter(client: httpx.AsyncClient, base: str, params: dict[str, str]) -> list[dict]:
    r = await _itt_get(client, f"{base}/api/torrents/filter", params)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("data") if isinstance(payload, dict) else None
    return items if isinstance(items, list) else []


def _itt_error_msg(e: Exception) -> str:
    """User-facing message for an ITT API failure (notably the 429 rate limit
    Unit3D applies — easy to hit right after a big auto scan)."""
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None) if resp is not None else None
    if code == 429:
        return "Limite di richieste del tracker superato — riprova tra poco."
    if code is not None:
        return f"Errore del tracker (HTTP {code})."
    if isinstance(e, httpx.TimeoutException):
        return "Timeout nella richiesta al tracker — riprova."
    return f"Errore nella richiesta al tracker: {e}"


async def fetch_torrent_meta(base: str, token: str, torrent_id: int) -> dict | None:
    """Single-torrent attributes (name, size, resolution, download_link, …).

    Unit3D's show endpoint returns the resource **without** the `data` envelope
    used by the list/filter endpoints — i.e. ``{type, id, attributes:{…}}`` at
    the top level — so handle both shapes.
    """
    base = base.rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
        r = await _itt_get(c, f"{base}/api/torrents/{torrent_id}", {"api_token": token})
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("attributes"), dict):  # show endpoint (no envelope)
        return payload["attributes"]
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if isinstance(data, dict):
        return data.get("attributes") or data
    return None


async def download_torrent_file(download_link: str) -> bytes:
    """Fetch the raw `.torrent` from the Unit3D ``download_link``.

    Unit3D serves the `.torrent` at ``/torrent/download/{id}.{rsskey}`` — the
    rsskey is baked into the ``download_link`` returned by the torrents API for
    the api_token's owner. The `.torrent` is NOT reachable via ``?api_token=``
    (that route requires a web session and otherwise returns the HTML page), so
    ``download_link`` is the only reliable mechanism. Validates the body is
    bencoded.
    """
    if not download_link:
        raise RuntimeError("download_link assente nella risposta dell'API ITT")
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(download_link)
    if r.status_code == 200 and r.content[:1] == b"d":
        return r.content
    raise RuntimeError(
        f"download .torrent fallito: HTTP {r.status_code} "
        f"(content-type {r.headers.get('content-type', '?')})"
    )


# ---------------------------------------------------------------------------
# Candidate discovery (library-driven, batched)
# ---------------------------------------------------------------------------


def _guess_episode(name: str) -> int | None:
    if _guessit is None:
        return None
    try:
        ep = dict(_guessit(name)).get("episode")
        if isinstance(ep, list):
            ep = ep[0] if ep else None
        return int(ep) if ep is not None else None
    except Exception:
        return None


def _scan_units(category: str) -> list[dict[str, Any]]:
    """Flatten a category into single-file reseed units (one ITT query each).

    Movies → one unit per single-file movie. Series → one unit per episode.
    """
    units: list[dict[str, Any]] = []
    for item in scan_category(category):
        if item.kind == "movie":
            if len(item.video_files) == 1:
                units.append({
                    "item": item, "file": item.video_files[0],
                    "kind": "movie", "season": None, "episode": None,
                })
        else:
            for season in item.seasons:
                for vf in season.video_files:
                    units.append({
                        "item": item, "file": vf, "kind": "episode",
                        "season": season.number, "episode": _guess_episode(vf.name),
                    })
    return units


def _torrent_brief(attrs: dict, tid: int, base: str) -> dict:
    """The shared ReseedTorrent shape sent to the frontend."""
    t_size = 0
    try:
        t_size = int(attrs.get("size") or 0)
    except (TypeError, ValueError):
        pass
    return {
        "tracker": "ITT",
        "id": tid,
        "name": attrs.get("name") or "",
        "type": _type_for(attrs),
        "size": t_size,
        "size_human": _human_size(t_size),
        "resolution": _resolution_for(attrs),
        "seeders": int(attrs.get("seeders") or 0),
        "leechers": int(attrs.get("leechers") or 0),
        "details_link": attrs.get("details_link") or f"{base}/torrents/{tid}",
        "download_link": attrs.get("download_link") or "",
    }


def _local_match(unit: dict[str, Any], size: int) -> dict:
    item = unit["item"]
    return {
        "source_path": str(unit["file"]),
        "item_name": item.name,
        "category": item.category,
        "kind": unit["kind"],
        "size": size,
        "size_human": _human_size(size),
    }


def _index_category(category: str) -> dict[int, list[dict]]:
    """Size -> local matches for a single category (sync; run in an executor)."""
    part: dict[int, list[dict]] = {}
    for unit in _scan_units(category):
        try:
            sz = unit["file"].stat().st_size
        except OSError:
            continue
        part.setdefault(sz, []).append(_local_match(unit, sz))
    return part


def _local_size_index(categories: list[str] | None = None) -> dict[int, list[dict]]:
    """Map exact byte size -> local single-file matches.

    Used by the manual flow to keep only torrents the user can actually reseed
    (a tracker torrent is reseedable iff a local file has its exact size).
    `categories=None` scans them all; pass a subset to narrow (and speed up).
    """
    idx: dict[int, list[dict]] = {}
    for category in (categories if categories is not None else discover_categories()):
        for sz, ms in _index_category(category).items():
            idx.setdefault(sz, []).extend(ms)
    return idx


def _candidate_dict(unit: dict[str, Any], local_size: int, attrs: dict, entry: dict, base: str) -> dict:
    item = unit["item"]
    tid = int(entry.get("id") or attrs.get("id") or 0)
    return {
        "source_path": str(unit["file"]),
        "item_name": item.name,
        "category": item.category,
        "kind": unit["kind"],
        "season": unit["season"],
        "episode": unit["episode"],
        "local_size": local_size,
        "local_size_human": _human_size(local_size),
        "torrent": _torrent_brief(attrs, tid, base),
    }


async def _match_unit(
    client: httpx.AsyncClient, base: str, token: str,
    unit: dict[str, Any], cache: dict[str, dict], max_seeders: int = 0,
) -> dict | str | None:
    """Return a candidate dict, ``"unenriched"`` (no tmdbId), or ``None``.

    A candidate is a tracker torrent with the **exact** byte size of the local
    file (required for the qBit recheck to pass) and ``seeders <= max_seeders``
    (default 0 = only dead torrents; raise to also reseed near-dead ones).
    """
    item = unit["item"]
    tmdb = cache.get(str(item.path)) or {}
    tmdb_id = tmdb.get("tmdb_id", "")
    if not tmdb_id:
        return "unenriched"
    try:
        size = unit["file"].stat().st_size
    except OSError:
        return None
    params: dict[str, str] = {"tmdbId": str(tmdb_id), "api_token": token, "perPage": "100"}
    if unit["kind"] == "episode":
        if unit["season"] is not None:
            params["seasonNumber"] = str(unit["season"])
        if unit["episode"] is not None:
            params["episodeNumber"] = str(unit["episode"])
    data = await _filter(client, base, params)
    for entry in data:
        attrs = entry.get("attributes") or {}
        try:
            t_size = int(attrs.get("size"))
        except (TypeError, ValueError):
            continue
        if t_size != size:
            continue
        if int(attrs.get("seeders") or 0) > max_seeders:
            continue
        return _candidate_dict(unit, size, attrs, entry, base)
    return None


async def stream_reseed_candidates(
    cfg: dict[str, Any], category: str, *, offset: int = 0, limit: int = 20,
    max_seeders: int = 0,
) -> AsyncGenerator[tuple[str, dict], None]:
    """Stream reseed candidates over the `[offset:offset+limit]` window of
    single-file units in `category`, yielding ``("candidate", {...})`` as each
    match is found (bounded ITT concurrency) and a final
    ``("done", {next_offset, has_more, scanned, unenriched})``.

    `max_seeders` (default 0) is the inclusive seeder ceiling for a match —
    0 keeps only dead torrents; raise it to also surface near-dead ones."""
    base, token = _itt_creds(cfg)
    units = _scan_units(category)
    window = units[offset:offset + limit]
    next_offset = offset + len(window)

    def _summary(unenriched: int, failed: int = 0) -> dict:
        return {
            "next_offset": next_offset,
            "has_more": next_offset < len(units),
            "scanned": len(window),
            "unenriched": unenriched,
            "total": len(units),
            "failed": failed,
        }

    if not _itt_configured(base, token) or not window:
        yield ("done", _summary(0))
        return

    item_paths = list({str(u["item"].path) for u in window})
    cache = await get_many(item_paths)
    sem = asyncio.Semaphore(8)
    unenriched = 0
    failed = 0

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        async def check(unit: dict[str, Any]) -> dict | str | None:
            async with sem:
                return await _match_unit(client, base, token, unit, cache, max_seeders)

        tasks = [asyncio.create_task(check(u)) for u in window]
        for fut in asyncio.as_completed(tasks):
            try:
                res = await fut
            except Exception as e:  # noqa: BLE001 — count tracker failures (e.g. 429)
                log.warning("reseed candidate check failed: %s", e)
                failed += 1
                continue
            if res == "unenriched":
                unenriched += 1
            elif res:
                yield ("candidate", res)

    yield ("done", _summary(unenriched, failed))


async def suggest_local_files(cfg: dict[str, Any], torrent_id: int) -> dict[str, Any]:
    """For the manual flow: torrent meta + local single-file items whose size
    matches the torrent exactly (pre-selection)."""
    base, token = _itt_creds(cfg)
    if not _itt_configured(base, token):
        return {"torrent": None, "matches": []}
    meta = await fetch_torrent_meta(base, token, torrent_id)
    if not meta:
        return {"torrent": None, "matches": []}
    try:
        size = int(meta.get("size"))
    except (TypeError, ValueError):
        size = 0
    matches = _local_size_index().get(size, []) if size > 0 else []
    tid = int(meta.get("id") or torrent_id)
    return {"torrent": _torrent_brief(meta, tid, base), "matches": matches}


def _search_categories(category: str | None) -> list[str]:
    """Resolve the category scope for a manual search: a valid single category,
    or all of them when unset/unknown."""
    cats = discover_categories()
    if category and category in cats:
        return [category]
    return cats


async def reseed_search(cfg: dict[str, Any], query: str, category: str | None = None) -> dict[str, Any]:
    """Manual flow search: query ITT by name but return ONLY torrents the user
    can actually reseed — those whose exact byte size matches a local
    single-file item. Each result carries its matching local file(s).
    `category` narrows the local scan (faster)."""
    base, token = _itt_creds(cfg)
    if not _itt_configured(base, token) or not query.strip():
        return {"results": []}
    idx = _local_size_index(_search_categories(category))
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        data = await _filter(client, base, {"api_token": token, "name": query, "perPage": "50"})
    results: list[dict] = []
    for entry in data:
        attrs = entry.get("attributes") or {}
        try:
            tsize = int(attrs.get("size"))
        except (TypeError, ValueError):
            continue
        matches = idx.get(tsize)
        if not matches:
            continue
        tid = int(entry.get("id") or attrs.get("id") or 0)
        results.append({
            "torrent": _torrent_brief(attrs, tid, base),
            "local_matches": matches,
        })
    return {"results": results}


async def stream_reseed_search(
    cfg: dict[str, Any], query: str, category: str | None = None,
) -> AsyncGenerator[tuple[str, dict], None]:
    """Streaming manual search: emits ``("progress", {done, total, category})``
    per local category scanned (the slow part), then a ``("result", {...})`` for
    each reseedable torrent, then ``("done", {count})``."""
    base, token = _itt_creds(cfg)
    if not _itt_configured(base, token) or not query.strip():
        yield ("done", {"count": 0})
        return

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            data = await _filter(client, base, {"api_token": token, "name": query, "perPage": "50"})
    except Exception as e:  # noqa: BLE001 — surface tracker failures (e.g. 429) to the UI
        log.warning("reseed search: ITT query failed: %s", e)
        yield ("error", {"message": _itt_error_msg(e)})
        yield ("done", {"count": 0})
        return

    categories = _search_categories(category)
    total = len(categories)
    loop = asyncio.get_event_loop()
    idx: dict[int, list[dict]] = {}
    for i, cat in enumerate(categories):
        part = await loop.run_in_executor(None, _index_category, cat)
        for sz, ms in part.items():
            idx.setdefault(sz, []).extend(ms)
        yield ("progress", {"done": i + 1, "total": total, "category": cat})

    count = 0
    for entry in data:
        attrs = entry.get("attributes") or {}
        try:
            tsize = int(attrs.get("size"))
        except (TypeError, ValueError):
            continue
        matches = idx.get(tsize)
        if not matches:
            continue
        tid = int(entry.get("id") or attrs.get("id") or 0)
        count += 1
        yield ("result", {
            "torrent": _torrent_brief(attrs, tid, base),
            "local_matches": matches,
        })
    yield ("done", {"count": count})


# ---------------------------------------------------------------------------
# Hardlink planning
# ---------------------------------------------------------------------------


def _video_files_under(root: Path) -> list[Path]:
    if root.is_dir():
        return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
    base = root.parent
    return sorted(p for p in base.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)


def _safe_size(p: Path) -> int | None:
    try:
        return p.stat().st_size
    except OSError:
        return None


def _plan_and_hardlink(files: list[dict], src: Path, save_path: str) -> tuple[list[str], list[str], str | None]:
    """Hardlink local content into the paths qBit expects under `save_path`.

    Returns (linked_names, missing_names, primary_target_path).
    """
    save = Path(save_path)
    linked: list[str] = []
    missing: list[str] = []
    primary: str | None = None

    if len(files) == 1:
        name = files[0].get("name") or src.name
        want = files[0].get("size")
        real_src = src
        if src.is_dir():
            cand = next((p for p in _video_files_under(src) if _safe_size(p) == want), None)
            real_src = cand or next(iter(_video_files_under(src)), src)
        target = save / name
        hardlink_file(real_src, target)
        linked.append(name)
        return linked, missing, str(target)

    # Multi-file (season pack via manual flow): match each torrent file to a
    # local file by exact size.
    pool = _video_files_under(src)
    used: set[Path] = set()
    for f in files:
        name = f.get("name") or ""
        want = f.get("size")
        match = next((p for p in pool if p not in used and _safe_size(p) == want), None)
        if match is None:
            missing.append(name)
            continue
        used.add(match)
        target = save / name
        hardlink_file(match, target)
        linked.append(name)
        if primary is None:
            primary = str(target)
    return linked, missing, primary


# ---------------------------------------------------------------------------
# Reseed orchestration (SSE generator)
# ---------------------------------------------------------------------------


def _ev(event: str, **data: Any) -> dict:
    return {"event": event, "data": json.dumps(data)}


def _log(msg: str) -> dict:
    return {"event": "log", "data": msg}


async def _await_new_hash(client, before: set[str], *, timeout: float = 20.0) -> str | None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        cur = {t.hash for t in await client.list()}
        new = cur - before
        if new:
            return sorted(new)[0]
        await asyncio.sleep(0.5)
    return None


async def _poll_recheck(client, torrent_hash: str, *, timeout: float = 900.0) -> AsyncGenerator[tuple[float, str], None]:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    seen_checking = False
    while loop.time() < deadline:
        info = await client.info_one(torrent_hash)
        if info is not None:
            prog = float(info.get("progress", 0) or 0)
            st = info.get("state", "") or ""
            yield prog, st
            if st in _CHECKING_STATES:
                seen_checking = True
            elif seen_checking or prog >= 0.999:
                return
        await asyncio.sleep(1.0)


async def perform_reseed(
    cfg: dict[str, Any], *, tracker: str, torrent_id: int, source_path: str,
    category: str = "", kind: str = "", title: str = "",
) -> AsyncGenerator[dict, None]:
    base, token = _itt_creds(cfg)
    if not _itt_configured(base, token):
        yield {"event": "error", "data": "ITT non configurato"}
        yield _ev("done", ok=False)
        return
    src = Path(source_path)
    if not src.exists():
        yield {"event": "error", "data": f"File locale non trovato: {source_path}"}
        yield _ev("done", ok=False)
        return

    async with _reseed_lock:
        loop = asyncio.get_event_loop()
        try:
            yield _log("Recupero metadati del torrent…")
            meta = await fetch_torrent_meta(base, token, torrent_id)
            download_link = (meta or {}).get("download_link") or ""

            yield {"event": "progress", "data": json.dumps({"phase": "download", "pct": 0})}
            yield _log("Scarico il file .torrent da ITT…")
            tbytes = await download_torrent_file(download_link)
            yield {"event": "progress", "data": json.dumps({"phase": "download", "pct": 100})}

            client = get_client(cfg)
            save = seedings_dir()
            save.mkdir(parents=True, exist_ok=True)
            save_path = str(save.resolve())

            yield _log("Aggiungo il torrent a qBittorrent (in pausa)…")
            before = {t.hash for t in await client.list()}
            # skip_checking=False so the initial progress reflects reality (files
            # not hardlinked yet → 0%), never a spurious 100%. We hardlink the
            # content next, then trigger an explicit recheck below — that recheck
            # is the real verification of whether the local content matches.
            await client.add_torrent(
                tbytes, save_path=save_path, paused=True,
                skip_checking=False, tags="u3dp-reseed",
            )
            new_hash = await _await_new_hash(client, before)
            if not new_hash:
                yield {"event": "error", "data": "Torrent aggiunto ma non individuato in qBit (forse già presente)."}
                yield _ev("done", ok=False)
                return

            yield {"event": "progress", "data": json.dumps({"phase": "hardlink", "pct": 0})}
            files = await client.torrent_files(new_hash)
            yield _log(f"qBit attende {len(files)} file. Creo gli hardlink…")
            linked, missing, primary = await loop.run_in_executor(
                None, _plan_and_hardlink, files, src, save_path
            )
            for name in linked:
                yield _log(f"→ {name}")
            for name in missing:
                yield _log(f"⚠ nessun file locale per: {name}")
            yield {"event": "progress", "data": json.dumps({"phase": "hardlink", "pct": 100})}

            yield _log("Avvio il recheck in qBittorrent…")
            await client.recheck(new_hash)
            yield {"event": "progress", "data": json.dumps({"phase": "recheck", "pct": 0})}
            final = 0.0
            async for prog, _st in _poll_recheck(client, new_hash):
                final = prog
                yield {"event": "progress", "data": json.dumps({"phase": "recheck", "pct": round(prog * 100)})}

            if final >= 0.999:
                await client.resume(new_hash)
                seeding_path = primary or save_path
                try:
                    await record_upload(
                        category=category or "", kind=kind or "movie",
                        source_path=str(src.resolve()), seeding_path=seeding_path,
                        title=title or "", final_name=Path(seeding_path).name,
                        exit_code=0, hardlink_only=True,
                        duplicate_info={"reseed": True, "tracker": tracker, "torrent_id": torrent_id},
                    )
                except Exception:
                    log.warning("reseed: record_upload failed", exc_info=True)
                yield _log("✓ Reseed completato — il torrent è in seed.")
                yield _ev("done", ok=True, hash=new_hash, progress=final)
            else:
                await client.pause(new_hash)
                yield {"event": "error", "data": (
                    f"Recheck incompleto ({round(final * 100)}%): il contenuto locale non "
                    "corrisponde al torrent. Lasciato in pausa in qBittorrent."
                )}
                yield _ev("done", ok=False, hash=new_hash, progress=final)
        except Exception as e:  # noqa: BLE001 — surface any failure to the UI
            log.exception("reseed failed")
            yield {"event": "error", "data": f"Reseed fallito: {e}"}
            yield _ev("done", ok=False)
