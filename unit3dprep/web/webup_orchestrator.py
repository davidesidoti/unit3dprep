"""Orchestrate Unit3DWebUp upload pipeline.

Replaces `unit3dprep.upload.stream_unit3dup`. Public entry point:

    async for ev in stream_webup(seeding_path, kind, tmdb_id):
        ...

Yields the same dict shape consumed by wizard/quickupload SSE handlers:
    {"type": "log",      "data": str}
    {"type": "progress", "data": str}
    {"type": "error",    "data": str}
    {"type": "done",     "exit_code": int}

The pipeline (per upload):
    1. acquire SCAN_PATH lock (serialize concurrent uploads — see plan).
    2. open WS subscription (wildcard, then rekey to job_id).
    3. POST /setenv {PREFS__SCAN_PATH: <parent_dir>} so /scan picks the right folder.
    4. POST /scan and await results.
    5. compute job_id deterministically from seeding_path; verify it's in scan results.
    6. POST /settmdbid if our tmdb_id differs from webup's resolution.
    7. POST /maketorrent → drain WS until torrent.created/exists or error.
    8. POST /upload      → drain WS until upload.done success or failure.
    9. POST /seed        → 200 ok / 503/409/404 mapped to warning or error.
   10. emit {"type":"done","exit_code": 0|1}.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from .config import runtime_setting
from .webup_client import WebupClient, compute_job_id
from .webup_job_fix import (
    DEFAULT_TRACKER_SIGNATURE,
    maybe_force_can_upload,
    maybe_inject_season,
    maybe_replace_signature,
    render_signature,
)
from .webup_logclass import classify_msg, is_terminal_failure, is_terminal_success
from .webup_ws import WILDCARD, WebupWSManager


_log = logging.getLogger(__name__)

# Hard ceilings to avoid hung uploads.
SCAN_TIMEOUT = 300.0   # 5 min for /scan + TMDB/TVDB lookup + screenshots
PHASE_TIMEOUT = 1800.0  # 30 min per phase (maketorrent / upload)


# Coarse phase weights for the wizard's overall progress bar. They don't have
# to match wall-clock proportions exactly — they just give the user a sense of
# motion. Sum is 100.
_PHASE_WEIGHTS: dict[str, float] = {
    "setenv": 3.0,
    "scan": 27.0,
    "maketorrent": 45.0,
    "upload": 15.0,
    "seed": 10.0,
}
_PHASE_ORDER = list(_PHASE_WEIGHTS.keys())
_PHASE_LABELS: dict[str, str] = {
    "setenv": "Configuro path",
    "scan": "Scansione + TMDB + screenshots",
    "maketorrent": "Creo torrent",
    "upload": "Upload al tracker",
    "seed": "Aggiungo a qBittorrent",
}

# Webup emits posterLogMessage like "[New torrent] FILE - 12.34" during
# maketorrent. The tail "- N" carries the percentage.
import re
_RX_MAKETORRENT_PCT = re.compile(r"-\s*(\d+(?:\.\d+)?)\s*$")


# ---------------------------------------------------------------------------
# .torrent announce-URL workaround
#
# Webup builds the announce URL with `f"{settings.tracker.ITT_URL}/announce/
# {settings.tracker.ITT_PID}"` (see unit3dwup/config/api_data.py). Pydantic-
# settings normalizes `HttpUrl` fields by appending a trailing slash, so the
# resulting URL contains a doubled slash:
#
#     https://itatorrents.xyz//announce/<pid>
#
# ItaTorrents (and other Unit3D trackers) returns 404 on that path. qBittorrent
# reports "not found" on the announce, the torrent never registers, and the
# upload appears completed but is invisible on the tracker. We patch the
# .torrent file on disk between /maketorrent and /seed so qBit receives a
# clean announce URL. The info-dict bytes are preserved verbatim to keep the
# infohash stable.
# ---------------------------------------------------------------------------

_BAD_ANNOUNCE = b"//announce/"
_GOOD_ANNOUNCE = b"/announce/"


def _bdecode(data: bytes, idx: int):
    c = data[idx:idx+1]
    if c.isdigit():
        colon = data.index(b":", idx)
        n = int(data[idx:colon])
        start = colon + 1
        return data[start:start+n], start + n
    if c == b"i":
        end = data.index(b"e", idx)
        return int(data[idx+1:end]), end + 1
    if c == b"l":
        items = []
        idx += 1
        while data[idx:idx+1] != b"e":
            v, idx = _bdecode(data, idx)
            items.append(v)
        return items, idx + 1
    if c == b"d":
        d: dict = {}
        idx += 1
        while data[idx:idx+1] != b"e":
            k, idx = _bdecode(data, idx)
            v, idx = _bdecode(data, idx)
            d[k] = v
        return d, idx + 1
    raise ValueError(f"invalid bencode at {idx}: {c!r}")


def _bencode(v) -> bytes:
    if isinstance(v, bytes):
        return f"{len(v)}:".encode() + v
    if isinstance(v, int):
        return f"i{v}e".encode()
    if isinstance(v, list):
        return b"l" + b"".join(_bencode(x) for x in v) + b"e"
    if isinstance(v, dict):
        out = b"d"
        for k in sorted(v.keys()):
            out += _bencode(k) + _bencode(v[k])
        return out + b"e"
    raise TypeError(type(v))


def _candidate_torrent_paths(media: dict[str, Any], match_path: Path):
    """Yield possible on-disk paths for the .torrent webup just built.

    Webup's media dict ships several path-shaped fields with confusingly
    similar names:

    - ``torrent_file_path`` — the .torrent file webup just generated
      (canonical for our use case).
    - ``torrent_path``      — the *source* media file path (NOT a .torrent;
      typically the multi-GiB .mkv inside the sandbox).
    - ``file_name``         — same as ``torrent_path``.

    We try ``torrent_file_path`` first, then fall back to deriving the path
    from ``<TORRENT_ARCHIVE_PATH>/<TRACKER>/<filename>.torrent`` using
    webup's published archive root and the tracker shorthand
    (``ITT``/``PTT``/``SIS``). Caller filters by ``Path.exists()`` and the
    bencode magic-byte check inside ``_normalize_announce_in_torrent``.
    """
    seen: set[str] = set()

    def _emit(p):
        s = str(p)
        if s and s not in seen:
            seen.add(s)
            yield Path(p)

    # 1. Canonical field for the .torrent file webup just wrote
    tfp = media.get("torrent_file_path")
    if isinstance(tfp, str) and tfp:
        yield from _emit(tfp)

    # 2. Derived from torrent_name (or file name) + tracker archive root
    base_name = (
        media.get("torrent_name")
        or media.get("file_name") and Path(str(media["file_name"])).name
        or match_path.name
    )
    archive = runtime_setting("WEBUP_TORRENT_ARCHIVE", "")
    if not archive:
        # Webup defaults to its working directory; on Ultra.cc HOME is the
        # canonical archive root since systemd unit doesn't override it.
        archive = str(Path.home())
    for tracker in ("ITT", "PTT", "SIS"):
        yield from _emit(Path(archive) / tracker / f"{base_name}.torrent")

    # 3. Inside the sandbox (webup occasionally writes alongside the source)
    yield from _emit(match_path.parent / f"{base_name}.torrent")
    yield from _emit(match_path.with_suffix(match_path.suffix + ".torrent"))


_TORRENT_MAX_BYTES = 16 * 1024 * 1024  # 16 MiB; .torrent files are tiny


def _normalize_announce_in_torrent(path: Path) -> bool:
    """Strip ``//announce/`` -> ``/announce/`` in a .torrent file's tracker URLs.

    Preserves the info dict bytes verbatim so the infohash stays stable.
    Returns True iff the file was modified. Fails fast on non-bencode files
    (e.g. when a candidate path accidentally points at a multi-GiB media
    source) by checking the magic byte and the file size before reading.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size == 0 or size > _TORRENT_MAX_BYTES:
        return False
    with path.open("rb") as f:
        magic = f.read(1)
        if magic != b"d":
            return False
        raw = magic + f.read()
    if not raw.startswith(b"d"):
        return False
    try:
        decoded, end = _bdecode(raw, 0)
    except (ValueError, IndexError):
        return False
    if end != len(raw) or not isinstance(decoded, dict):
        return False

    changed = False

    if isinstance(decoded.get(b"announce"), bytes) and _BAD_ANNOUNCE in decoded[b"announce"]:
        decoded[b"announce"] = decoded[b"announce"].replace(_BAD_ANNOUNCE, _GOOD_ANNOUNCE)
        changed = True

    if isinstance(decoded.get(b"announce-list"), list):
        new_list = []
        for tier in decoded[b"announce-list"]:
            if isinstance(tier, list):
                new_tier = []
                for u in tier:
                    if isinstance(u, bytes) and _BAD_ANNOUNCE in u:
                        new_tier.append(u.replace(_BAD_ANNOUNCE, _GOOD_ANNOUNCE))
                        changed = True
                    else:
                        new_tier.append(u)
                new_list.append(new_tier)
            else:
                new_list.append(tier)
        decoded[b"announce-list"] = new_list

    if not changed:
        return False

    # Find the byte range of the original "info" value to copy it verbatim,
    # avoiding any infohash drift from re-encoding nested structures.
    info_value_bytes: bytes | None = None
    idx = 1
    while idx < len(raw) and raw[idx:idx+1] != b"e":
        colon = raw.index(b":", idx)
        klen = int(raw[idx:colon])
        kstart = colon + 1
        kend = kstart + klen
        key = raw[kstart:kend]
        _, vend = _bdecode(raw, kend)
        if key == b"info":
            info_value_bytes = raw[kend:vend]
        idx = vend

    out = bytearray(b"d")
    for key in sorted(decoded.keys()):
        out += _bencode(key)
        if key == b"info" and info_value_bytes is not None:
            out += info_value_bytes
        else:
            out += _bencode(decoded[key])
    out += b"e"

    path.write_bytes(bytes(out))
    return True


def _overall_pct(phase: str, sub_pct: float = 0.0) -> float:
    """Map (phase, 0..100 sub-progress) to overall 0..100 across all phases."""
    cumulative = 0.0
    for p in _PHASE_ORDER:
        if p == phase:
            return min(100.0, cumulative + (max(0.0, min(sub_pct, 100.0)) / 100.0) * _PHASE_WEIGHTS[p])
        cumulative += _PHASE_WEIGHTS[p]
    return 100.0


def _progress_event(phase: str, sub_pct: float = 0.0, *, label: str | None = None) -> dict[str, Any]:
    return {
        "type": "progress",
        "phase": phase,
        "label": label or _PHASE_LABELS.get(phase, phase),
        "pct": round(_overall_pct(phase, sub_pct), 1),
        "sub_pct": round(max(0.0, min(sub_pct, 100.0)), 1),
    }


def _ensure_str(v: Any) -> str:
    return "" if v is None else str(v)


def _render_tracker_signature() -> str:
    """Resolve the tracker description footer, rendering the ``{version}``
    placeholder with unit3dprep's own version. Empty setting → no replacement.
    """
    template = runtime_setting("W_TRACKER_SIGNATURE", DEFAULT_TRACKER_SIGNATURE)
    if "{version}" not in (template or ""):
        return template
    try:
        from .api.version import _current_app_version
        version = _current_app_version()
    except Exception:
        version = ""
    return render_signature(template, version)


def _media_for_path(scan_results: dict[str, Any], target: Path) -> dict[str, Any] | None:
    """Find the Media dict in /scan response that matches the requested path.

    Webup builds Media with folder=scan_path and subfolder=<entry name>; the
    full path is `folder / subfolder`. Match by job_id (deterministic) or fall
    back to path comparison. Path strings are normpath'd because webup applies
    `os.path.normpath` to the scan path before deriving the job_id.
    """
    import os
    s_target = os.path.normpath(str(target))
    expected_id = compute_job_id(s_target)
    items = (scan_results.get("results") or [])
    for it in items:
        if it.get("job_id") == expected_id:
            return it
    for it in items:
        folder = it.get("folder") or ""
        sub = it.get("subfolder") or ""
        if os.path.normpath(str(Path(folder) / sub)) == s_target:
            return it
        if os.path.normpath(it.get("torrent_path") or "") == s_target:
            return it
    return None


async def _drain_buffered(
    queue: asyncio.Queue, job_id: str, *, window: float = 1.5,
):
    """Yield (ev_dict, raw_msg) for messages currently in queue + arriving within
    `window` seconds. Filters by job_id (or no job_id). Stops when queue is
    empty AND `window` seconds have passed since the last message.
    """
    loop = asyncio.get_event_loop()
    last_seen = loop.time()
    while True:
        try:
            timeout = max(0.0, window - (loop.time() - last_seen))
            msg = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return
        last_seen = loop.time()
        jid = msg.get("job_id")
        if jid not in (None, "", job_id):
            continue
        ev_kind, slug, text = classify_msg(msg)
        yield {"type": "log", "data": text, "kind": ev_kind, "event": slug}, msg


async def stream_webup(
    *,
    client: WebupClient,
    ws: WebupWSManager,
    scan_lock: asyncio.Lock,
    seeding_path: str,
    kind: str,
    tmdb_id: str = "",
    do_seed: bool = True,
) -> AsyncGenerator[dict, None]:
    """Drive the webup pipeline for a single hardlinked path.

    `kind`: 'movie' | 'episode' | 'series'. Webup figures out category by itself
    from filename; we use this only to pick the scan parent dir:
      - movie/episode → parent of the file
      - series        → the folder itself
    """
    target = Path(seeding_path)
    is_series = kind == "series"
    if is_series:
        # For a series pack, webup builds ONE Media object per *subfolder* of
        # SCAN_PATH (containing all episodes) — NOT per file inside that
        # folder. So we point SCAN_PATH at the parent of the series folder
        # and the match_path is the series folder itself.
        target_dir = target if target.is_dir() else target.parent
        scan_dir = str(target_dir.parent)
        match_path = str(target_dir)
    else:
        scan_dir = str(target.parent)
        match_path = str(target)

    expected_job_id = compute_job_id(match_path)

    queue = await ws.subscribe(WILDCARD)
    locked = False

    async def emit_msg_to_log(msg: dict[str, Any]) -> dict[str, Any]:
        ev_kind, slug, text = classify_msg(msg)
        return {"type": "log", "data": text, "kind": ev_kind, "event": slug}

    try:
        await scan_lock.acquire()
        locked = True

        yield _progress_event("setenv", 0)
        yield {"type": "log", "data": f"webup: setting SCAN_PATH={scan_dir}"}
        try:
            await client.setenv("PREFS__SCAN_PATH", scan_dir)
        except Exception as e:
            yield {"type": "error", "data": f"setenv SCAN_PATH failed: {e}"}
            yield {"type": "done", "exit_code": 1}
            return

        # Push PREFERRED_LANG before /scan so the language-gate check in
        # tags_service.mediainfo_audio uses the correct value even when the
        # Media object is reconstructed from a stale Redis cache entry
        # (same job_id = same path → Redis hit with old can_upload=False).
        preferred_lang = runtime_setting("PREFERRED_LANG", "ita")
        try:
            await client.setenv("PREFS__PREFERRED_LANG", preferred_lang)
        except Exception as e:
            yield {"type": "log", "data": f"webup: setenv PREFERRED_LANG failed (non-fatal): {e}", "kind": "warn"}
        yield _progress_event("setenv", 100)

        yield _progress_event("scan", 0)
        yield {"type": "log", "data": "webup: /scan…"}
        try:
            scan_result = await asyncio.wait_for(client.scan(), timeout=SCAN_TIMEOUT)
        except asyncio.TimeoutError:
            yield {"type": "error", "data": f"/scan timeout after {SCAN_TIMEOUT}s"}
            yield {"type": "done", "exit_code": 1}
            return
        except Exception as e:
            yield {"type": "error", "data": f"/scan failed: {e}"}
            yield {"type": "done", "exit_code": 1}
            return

        media = _media_for_path(scan_result, Path(match_path))
        if not media:
            n_items = len(scan_result.get("results") or [])
            hint = ""
            if n_items == 0:
                hint = (
                    " — webup's /scan dropped it. Common causes: "
                    "ffmpeg missing (screenshots fail), TMDB/TVDB API key invalid, "
                    "or image host upload failed. Check webup logs."
                )
            yield {
                "type": "error",
                "data": f"webup: no Media for {match_path} in scan results "
                        f"(got {n_items} items){hint}",
            }
            yield {"type": "done", "exit_code": 1}
            return

        job_id = str(media.get("job_id") or expected_job_id)
        await ws.rekey(WILDCARD, job_id, queue)

        webup_tmdb = _ensure_str(media.get("tmdb_id"))
        wanted_tmdb = _ensure_str(tmdb_id)
        if wanted_tmdb and wanted_tmdb != webup_tmdb:
            yield {"type": "log", "data": f"webup: override tmdb_id {webup_tmdb} → {wanted_tmdb}"}
            try:
                await client.set_tmdbid(job_id, wanted_tmdb)
            except Exception as e:
                yield {"type": "log", "data": f"webup: settmdbid failed (continuing): {e}"}

        yield {"type": "log", "data": f"webup: job_id={job_id} title={media.get('title')!r}"}

        # Webup 0.0.25 bug workaround: `tags_service.mediainfo_audio` only
        # ever flips can_upload to False — never back to True — so a file
        # whose FIRST audio track isn't in PREFERRED_LANG is silently
        # rejected even when a later track matches. Re-check ourselves and
        # patch the Redis-backed Media record before /maketorrent.
        try:
            fix = await maybe_force_can_upload(job_id, preferred_lang)
            if fix.get("patched"):
                yield {
                    "type": "log", "kind": "ok",
                    "data": f"webup: {fix['reason']}",
                }
        except Exception as exc:
            yield {
                "type": "log", "kind": "warn",
                "data": f"webup: can_upload patch skipped ({exc!r})",
            }

        # Webup 0.0.25 bug workaround: the tracker display_name is built from
        # `PREFS__TAG_POSITION_SERIE`, but webup reads that into a module-global
        # `settings` captured at import (media.py / tags_service.py), so a
        # corrected tag order only takes effect after a webup *restart*. To make
        # the season label appear without restarting webup, patch the Redis job's
        # display_name directly, inserting the S##(E##) token after the title.
        try:
            sinj = await maybe_inject_season(job_id)
            if sinj.get("patched"):
                yield {
                    "type": "log", "kind": "ok",
                    "data": f"webup: {sinj['reason']}",
                }
        except Exception as exc:
            yield {
                "type": "log", "kind": "warn",
                "data": f"webup: season inject skipped ({exc!r})",
            }

        # Swap webup's hardcoded "by Unit3DwebUp <ver>" description footer for
        # our own credit. Webup builds the description (with its footer) at /scan
        # and persists it in Redis; /upload reloads it and sends it to the
        # tracker. Patch the Redis record here, before /upload. Controlled by the
        # W_TRACKER_SIGNATURE runtime setting (empty = keep webup's footer).
        try:
            signature = _render_tracker_signature()
            sig = await maybe_replace_signature(job_id, signature)
            if sig.get("patched"):
                yield {
                    "type": "log", "kind": "ok",
                    "data": f"webup: {sig['reason']}",
                    "event": "upload.signature",
                }
        except Exception as exc:
            yield {
                "type": "log", "kind": "warn",
                "data": f"webup: signature patch skipped ({exc!r})",
            }

        yield _progress_event("scan", 100)

        # ---- Maketorrent ----
        # Webup runs the torrent build inside the HTTP request; HTTP 200 means
        # it's done. Progress messages stream via WS while the call is in
        # flight; we drain them after the HTTP returns.
        yield _progress_event("maketorrent", 0)
        yield {"type": "log", "data": "webup: /maketorrent…"}
        maketorrent_task = asyncio.create_task(
            asyncio.wait_for(client.maketorrent(job_id), timeout=PHASE_TIMEOUT)
        )

        # Drain WS messages while maketorrent is running so the user sees the
        # progress bar move in real time. Webup emits posterLogMessages with
        # "[New torrent] FILE - N" where N is the percentage.
        loop = asyncio.get_event_loop()
        while not maketorrent_task.done():
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            jid = msg.get("job_id")
            if jid not in (None, "", job_id):
                continue
            ev_kind, slug, text = classify_msg(msg)
            yield {"type": "log", "data": text, "kind": ev_kind, "event": slug}
            m = _RX_MAKETORRENT_PCT.search(text)
            if m:
                try:
                    yield _progress_event("maketorrent", float(m.group(1)))
                except ValueError:
                    pass
            if is_terminal_failure(msg):
                maketorrent_task.cancel()
                yield {"type": "error", "data": f"/maketorrent reported failure: {msg.get('message')!r}"}
                yield {"type": "done", "exit_code": 1}
                return

        try:
            await maketorrent_task
        except asyncio.TimeoutError:
            yield {"type": "error", "data": f"/maketorrent timeout after {PHASE_TIMEOUT}s"}
            yield {"type": "done", "exit_code": 1}
            return
        except Exception as e:
            yield {"type": "error", "data": f"/maketorrent failed: {e}"}
            yield {"type": "done", "exit_code": 1}
            return

        # Drain any final messages buffered after HTTP returned.
        async for ev, msg in _drain_buffered(queue, job_id, window=0.8):
            yield ev
            if is_terminal_failure(msg):
                yield {"type": "error", "data": f"/maketorrent reported failure: {msg.get('message')!r}"}
                yield {"type": "done", "exit_code": 1}
                return

        # Workaround for upstream webup bug: announce URL has `//announce/`
        # because pydantic HttpUrl appends a trailing slash before webup's
        # f-string concatenation in api_data.py. Patch the .torrent on disk
        # before /seed so qBittorrent and the tracker see a clean URL.
        candidates = list(_candidate_torrent_paths(media, Path(match_path)))
        patched_any = False
        for tp in candidates:
            try:
                if tp.exists() and _normalize_announce_in_torrent(tp):
                    patched_any = True
                    yield {
                        "type": "log",
                        "data": f"webup: patched announce URL in {tp.name} "
                                "(workaround pydantic HttpUrl trailing-slash bug)",
                        "kind": "warn",
                        "event": "torrent.announce_patch",
                    }
            except Exception as e:
                yield {
                    "type": "log",
                    "data": f"webup: announce-URL patch failed for {tp}: {e}",
                    "kind": "warn",
                }
        if not patched_any and candidates:
            _log.debug("announce patch: no candidate matched. tried=%s", [str(p) for p in candidates])

        yield _progress_event("maketorrent", 100)

        # ---- Upload ----
        # Dry-run mode (U3DP_DRY_RUN_TRACKER=1) skips the actual tracker call so
        # WSL/dev can exercise the full pipeline without polluting the live
        # tracker. Maketorrent and seed still run, the .torrent ends up in qBit.
        dry_run = runtime_setting("U3DP_DRY_RUN_TRACKER", "0") in {"1", "true", "True", "yes"}
        if dry_run:
            yield _progress_event("upload", 0)
            yield {
                "type": "log",
                "data": "webup: /upload SKIPPED (U3DP_DRY_RUN_TRACKER=1)",
                "kind": "warn",
                "event": "upload.dryrun",
            }
            yield _progress_event("upload", 100)
        else:
            yield _progress_event("upload", 0)
            yield {"type": "log", "data": "webup: /upload…"}
            try:
                upload_http_resp = await asyncio.wait_for(client.upload(job_id), timeout=PHASE_TIMEOUT)
            except asyncio.TimeoutError:
                yield {"type": "error", "data": f"/upload timeout after {PHASE_TIMEOUT}s"}
                yield {"type": "done", "exit_code": 1}
                return
            except Exception as e:
                yield {"type": "error", "data": f"/upload failed: {e}"}
                yield {"type": "done", "exit_code": 1}
                return

            # webup's /upload endpoint returns JSON null regardless of outcome
            # (FastAPI default for endpoints with no explicit return value).
            # The actual tracker result comes exclusively through WebSocket
            # posterLogMessage events broadcast inside UploadUseCase.execute().
            # Do NOT treat None here as an error — drain WS for the real status.

            _log.info(
                "upload: /upload HTTP done, ws_connected=%s queue_size=%d — draining WS",
                ws.connected, queue.qsize(),
            )

            upload_failed = False
            upload_succeeded = False
            async for ev, msg in _drain_buffered(queue, job_id, window=8.0):
                yield ev
                if is_terminal_failure(msg):
                    upload_failed = True
                elif is_terminal_success(msg):
                    upload_succeeded = True

            _log.info(
                "upload: drain done — succeeded=%s failed=%s queue_size=%d ws_connected=%s",
                upload_succeeded, upload_failed, queue.qsize(), ws.connected,
            )

            if upload_succeeded:
                pass  # WS confirmed success
            elif upload_failed:
                yield {"type": "error", "data": "/upload tracker rejected — see log above for details"}
                yield {"type": "done", "exit_code": 1}
                return
            else:
                # No posterLogMessage arrived within 8 s.
                # This is a WS delivery issue (timing race, connection glitch)
                # rather than a definitive upload failure — the HTTP 200 from
                # webup means execute() completed and the tracker call was made.
                # Log a warning and proceed to seed so the workflow still
                # completes; the operator should verify the tracker manually.
                yield {
                    "type": "log",
                    "data": (
                        f"webup: /upload — no WS status received within 8 s "
                        f"(ws_connected={ws.connected}, queue_size={queue.qsize()}). "
                        "Proceeding to seed. Check the tracker to confirm the upload succeeded."
                    ),
                    "kind": "warn",
                    "event": "upload.tracker_response",
                }
            yield _progress_event("upload", 100)

        # ---- Seed (optional) ----
        if do_seed:
            yield _progress_event("seed", 0)
            yield {"type": "log", "data": "webup: /seed…"}
            try:
                code, body = await client.seed(job_id)
            except Exception as e:
                yield {"type": "log", "data": f"webup: /seed failed (non-fatal): {e}", "kind": "warn"}
                code = 599
            if code == 200:
                yield {"type": "log", "data": "webup: torrent seeded", "kind": "ok", "event": "upload.qbit"}
            elif code in (503, 409, 404):
                yield {
                    "type": "log",
                    "data": f"webup: /seed returned {code} (not fatal)",
                    "kind": "warn",
                    "event": "upload.qbit",
                }
            else:
                yield {"type": "log", "data": f"webup: /seed returned {code}", "kind": "warn"}
            yield _progress_event("seed", 100)

        yield {"type": "done", "exit_code": 0}
    finally:
        try:
            await ws.unsubscribe(WILDCARD, queue)
        except Exception:
            pass
        try:
            await ws.unsubscribe(expected_job_id, queue)
        except Exception:
            pass
        if locked:
            scan_lock.release()


async def stream_webup_batch(
    *,
    client: WebupClient,
    ws: WebupWSManager,
    scan_lock: asyncio.Lock,
    folder: str,
) -> AsyncGenerator[dict, None]:
    """Recursive scan + processall for a folder of media.

    Maps to the legacy `unit3dup -b -scan <folder>` mode used by quickupload.
    Yields a stream of log/progress events; emits one synthetic 'done' per
    completed job and a final 'done_all' event with overall counts.
    """
    target = Path(folder)
    queue = await ws.subscribe(WILDCARD)
    locked = False
    try:
        await scan_lock.acquire()
        locked = True

        yield {"type": "log", "data": f"webup: setting SCAN_PATH={target}"}
        await client.setenv("PREFS__SCAN_PATH", str(target))

        yield {"type": "log", "data": "webup: /scan (batch)…"}
        scan_result = await asyncio.wait_for(client.scan(), timeout=SCAN_TIMEOUT)
        items = scan_result.get("results") or []
        if not items:
            yield {"type": "error", "data": "webup: /scan returned no items"}
            yield {"type": "done", "exit_code": 1}
            return

        job_ids = [str(it.get("job_id")) for it in items if it.get("job_id")]
        path_by_job = {str(it.get("job_id")): str(Path(it.get("folder") or "") / (it.get("subfolder") or ""))
                       for it in items if it.get("job_id")}
        yield {"type": "log", "data": f"webup: scan found {len(job_ids)} items"}

        # Swap webup's "by Unit3DwebUp" description footer for ours on every job
        # before upload (same mechanism as the single-path flow).
        signature = _render_tracker_signature()
        for jid in job_ids:
            try:
                sig = await maybe_replace_signature(jid, signature)
                if sig.get("patched"):
                    yield {
                        "type": "log", "kind": "ok",
                        "data": f"webup: {jid[:8]} {sig['reason']}",
                        "event": "upload.signature",
                    }
            except Exception as exc:
                yield {
                    "type": "log", "kind": "warn",
                    "data": f"webup: signature patch skipped for {jid[:8]} ({exc!r})",
                }

        from .webup_client import compute_job_list_id
        job_list_id = compute_job_list_id(str(target))
        # In dry-run mode `/processall` would still call the tracker for every
        # item. Run only `/maketorrent` + `/seed` per job instead, skipping the
        # tracker upload. Loops sequentially to keep the WS log readable.
        dry_run = runtime_setting("U3DP_DRY_RUN_TRACKER", "0") in {"1", "true", "True", "yes"}
        if dry_run:
            yield {
                "type": "log",
                "data": "webup: batch /upload SKIPPED (U3DP_DRY_RUN_TRACKER=1)",
                "kind": "warn",
                "event": "upload.dryrun",
            }
            for jid in job_ids:
                try:
                    await asyncio.wait_for(client.maketorrent(jid), timeout=PHASE_TIMEOUT)
                except Exception as e:
                    yield {"type": "log", "data": f"maketorrent {jid[:8]} failed: {e}", "kind": "error"}
                try:
                    await client.seed(jid)
                except Exception as e:
                    yield {"type": "log", "data": f"seed {jid[:8]} failed: {e}", "kind": "warn"}
                yield {"type": "job_done", "job_id": jid, "path": path_by_job.get(jid, ""), "exit_code": 0}
            yield {"type": "done", "exit_code": 0, "ok": len(job_ids), "fail": 0, "dry_run": True}
            return

        yield {"type": "log", "data": "webup: /processall…"}
        await client.processall(job_list_id)

        # Drain until each job_id has a terminal success/failure.
        loop = asyncio.get_event_loop()
        pending = set(job_ids)
        results: dict[str, int] = {}
        deadline = loop.time() + PHASE_TIMEOUT * 2
        while pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                for j in pending:
                    yield {"type": "log", "data": f"webup: timeout for job {j}", "kind": "warn"}
                    results[j] = 1
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                continue
            ev_kind, slug, text = classify_msg(msg)
            yield {"type": "log", "data": text, "kind": ev_kind, "event": slug}
            jid = msg.get("job_id")
            if jid in pending:
                if is_terminal_success(msg):
                    pending.discard(jid)
                    results[jid] = 0
                    yield {"type": "job_done", "job_id": jid, "path": path_by_job.get(jid, ""), "exit_code": 0}
                elif is_terminal_failure(msg):
                    pending.discard(jid)
                    results[jid] = 1
                    yield {"type": "job_done", "job_id": jid, "path": path_by_job.get(jid, ""), "exit_code": 1}

        ok_count = sum(1 for v in results.values() if v == 0)
        fail_count = len(results) - ok_count
        yield {
            "type": "done",
            "exit_code": 0 if fail_count == 0 else 1,
            "ok": ok_count,
            "fail": fail_count,
        }
    finally:
        try:
            await ws.unsubscribe(WILDCARD, queue)
        except Exception:
            pass
        if locked:
            scan_lock.release()
