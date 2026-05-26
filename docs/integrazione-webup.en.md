# Unit3DWebUp integration

The entire upload-to-tracker phase is delegated to [`Unit3DWebUp`](https://pypi.org/project/Unit3DwebUp/) — a second FastAPI service `unit3dprep` orchestrates over HTTP + WebSocket. This page covers the bridge architecture, upload flow, config sync, and known limitations.

---

## Architecture

```
┌────────────────────┐                        ┌──────────────────────┐
│   unit3dprep       │   HTTP /setenv /scan   │   Unit3DWebUp        │
│   (FastAPI + UI)   │ ─────────────────────> │   (FastAPI bot)      │
│                    │   /maketorrent /upload │                      │
│                    │   /seed /filter        │                      │
│                    │ <───────────────────── │                      │
│                    │   WebSocket events     │                      │
└────────┬───────────┘   (job_id channels)    └──────────┬───────────┘
         │                                                │
         │                                                │
         │  ─── shared .env ($ENVPATH/.env) ──────────────│
         │                                                │
         ▼                                                ▼
   ~/seedings/                              tracker (HTTPS) + qBittorrent + Redis
```

**Key components** (unit3dprep side):

- `unit3dprep/web/webup_client.py` — singleton `httpx.AsyncClient` covering all bot endpoints.
- `unit3dprep/web/webup_ws.py` — `WebupWSManager`: persistent WS, demultiplex by `job_id`, async queues per consumer.
- `unit3dprep/web/webup_orchestrator.py` — `stream_webup()` async generator: the full upload pipeline.
- `unit3dprep/web/webup_logclass.py` — `classify_msg()` / `is_terminal_success()` / `is_terminal_failure()`.
- `unit3dprep/web/api/webup.py` — FastAPI router: `/api/webup/{health,sync,setting,filter}`.
- `unit3dprep/web/api/version.py` — webup auto-update SSE (`/api/version/update/webup/stream`).

**Singleton + scan-lock**:

- `WebupClient` is singleton-cached per (host, port). One TCP keep-alive.
- `app.state.webup_scan_lock = asyncio.Lock()` serializes concurrent uploads — `SCAN_PATH` is global state in the webup app, two parallel `setenv` calls would clash.

---

## Upload flow (single job)

`stream_webup(seeding_path, kind, tmdb_id)` runs 6 phases with weights for the UI progress bar.

| # | Phase | Webup endpoint | Weight | Purpose |
|---|---|---|---:|---|
| 1 | `setenv` | `POST /setenv {PREFS__SCAN_PATH: <parent>}` | 3% | Sets the path `/scan` will use. Movie: parent(file). Series: parent(folder). |
| 2 | `scan` | `POST /scan` | 27% | Webup scans, runs TMDB/TVDB lookup, generates ffmpeg screenshots, uploads to image hosts. |
| 3 | `settmdbid` | `POST /settmdbid` *(optional)* | — | Only when our passed ID differs from the bot's resolution. |
| 4 | `maketorrent` | `POST /maketorrent` | 45% | Webup builds the `.torrent`. WS emits `[New torrent] FILE - N%` for sub-phase progress. HTTP 200 = phase done. |
| 5 | `upload` | `POST /upload` | 15% | Webup uploads to the tracker (skipped if `U3DP_DRY_RUN_TRACKER=1`). HTTP 200 + 2s log drain. |
| 6 | `seed` | `POST /seed` | 10% | Webup adds the torrent to qBittorrent. 200=ok, 503/409/404 = warning, others = warning. |

**Events yielded by the generator**:

```python
{"type": "log",      "data": str, "kind": str, "event": str}
{"type": "progress", "phase": str, "label": str, "pct": float, "sub_pct": float}
{"type": "error",    "data": str}
{"type": "done",     "exit_code": int}
```

Consumed by:

- Wizard SSE (`/wizard/{token}/stream` + `/upload/{job}/stream`) → frontend with graphical bar.
- CLI `run_webup_sync()` → plain stdout.

### `SCAN_PATH` semantics + per-upload sandbox

Webup's `/scan` processes **everything** inside `SCAN_PATH` (TMDB/TVDB lookup, ffmpeg screenshots, image-host upload) for every file/subfolder. If SCAN_PATH points at a crowded directory (e.g. `~/seedings` with 200 hardlinks), webup scans all entries in parallel, runs out of resources (`[Errno 11] Resource temporarily unavailable`, `cannot reshape array of size 0`), and the target file gets lost in the noise.

To prevent this, the bridge creates a **dedicated sandbox per upload** under `<seedings>/.unit3dprep/<jobid>/`. The `<jobid>` is an 8-char sha256 of the final name, deterministic → re-uploading the same item overwrites the same sandbox.

On-disk layout:

```
~/seedings/
├── .unit3dprep/
│   ├── 1a2b3c4d/                            # movie
│   │   └── Philadelphia (1993) ... .mkv
│   ├── 5e6f7a8b/                            # series
│   │   └── Severance (2022) S02/
│   │       ├── S02E01.mkv
│   │       └── …
│   └── …
```

Webup recognizes per subfolder inside `SCAN_PATH`:

- **Movie**: `SCAN_PATH = <seedings>/.unit3dprep/<jobid>/`, holding ONE file → `Media` for that file.
- **Series**: `SCAN_PATH = <seedings>/.unit3dprep/<jobid>/`, holding ONE subfolder → `Media` (pack) for the series.

No race condition with other files, fast and reliable scan. Hardlinks share the inode with the original file in `media_root`, so the Media Library keeps marking items as "uploaded" via the inode fallback with no changes.

qBittorrent after `/seed` gets the sandbox path as the torrent location: the file must stay there for seeding. Sandboxes are **permanent** — don't delete them by hand if you still want to seed. To clean up removed torrents, delete from the torrent client first, then the directory.

### Deterministic `job_id`

Webup computes `job_id = sha256(str(normpath(folder/subfolder)))`. The bridge computes the same value with `webup_client.compute_job_id(match_path)` and pre-subscribes to the WS channel before issuing `/scan`, avoiding the "scan completes → bot starts emitting → we subscribe later → events lost" race.

### Streaming log handling

`maketorrent` and `upload` return HTTP 200 once they're done (synchronous in the webup process). While the request is in flight, the bot publishes events on the WS. The orchestrator drains the WS in two modes:

- **Concurrent (maketorrent)**: HTTP task runs, while a loop reads from the WS queue and computes the sub-percentage from the regex `[New torrent] FILE - N`.
- **Post-200 (upload)**: right after HTTP 200, drains final events for ~2s (success/failure detection via `is_terminal_success` / `is_terminal_failure`).

---

## Config bridge: short ↔ canonical

On-disk storage is a single shared `.env`. To not break the historical unit3dprep API, `unit3dprep/web/config.py` keeps a bidirectional translation:

```python
WEBUP_KEY_MAP = {
    "ITT_APIKEY": "TRACKER__APIKEYS",
    "ITT_URL": "TRACKER__URLS",
    "QBIT_HOST": "TORRENT__QBIT_HOST",
    "MULTI_TRACKER": "TRACKER__MULTI_TRACKER",
    "TAG_ORDER_MOVIE": "PREFS__TAG_POSITION_MOVIE",
    # ...
}
_WEBUP_TO_SHORT = {v: k for k, v in WEBUP_KEY_MAP.items()}
```

- **In memory / `/api/settings` API**: short names (`ITT_APIKEY`, `QBIT_HOST`, ...).
- **On disk / `.env` / push to webup**: canonical names (`TRACKER__APIKEYS=["..."]`, ...).
- Lists like `MULTI_TRACKER` are serialized as **JSON arrays** (required by webup's pydantic-settings v2), not CSV.

### Skip rules

`_to_webup_env_payload(state)` filters before pushing to webup:

| Value | Skip? | Reason |
|---|---|---|
| `""` (empty string) | Yes | Webup `empty_to_none` validates → `None` on `str` field → `SystemExit` |
| `None` | Yes | Same |
| `"no_key"`, `"no_pass"`, `"no_path"`, `"no_comment"` | Yes | Placeholders without real value |
| Anything else | No | Pushed to webup |

**Exceptions** (always pushed with `.` fallback when empty): `PREFS__TORRENT_ARCHIVE_PATH`, `PREFS__WATCHER_PATH`, `PREFS__WATCHER_DESTINATION_PATH`, `PREFS__SCAN_PATH`. Webup requires those as existing `Path`-able values.

### IMAGE_HOST_ORDER → numeric priorities

unit3dprep keeps a single ordered list `IMAGE_HOST_ORDER=["IMGFI","PTSCREENS","IMGBB"]`. Webup instead uses numeric priorities per host (`PREFS__IMGFI_PRIORITY=1`, `PREFS__PTSCREENS_PRIORITY=2`, ...). The projection assigns `1, 2, 3, ...` to listed hosts and `99` to hosts not in the list — so webup never tries to upload to hosts without a key.

### Secret masking

All secrets (see `MASKED_KEYS` list in `unit3dprep/web/config.py`) are returned as `"__SET__"` from `GET /api/settings`. On `PUT`, `"__SET__"` means "leave the existing value alone". This avoids leaks in browser DevTools / response cache.

---

## Health check

Endpoint: `GET /api/webup/health`. 5s cache.

```json
{
  "online": true,
  "version": "0.0.25",
  "latency_ms": 12.4,
  "ws_connected": true,
  "url": "http://127.0.0.1:8000",
  "envpath_dir": "/home/user/.config/unit3dprep"
}
```

Version lookup chain: HTTP `/setting` → `pip metadata` (subprocess `<WEBUP_VENV_BIN>/python -c "import importlib.metadata; print(importlib.metadata.version('Unit3DwebUp'))"`) → parse `.env`. If all three fail → `null`.

UI render: "Unit3DWebUp" card in Settings with online/offline badge + version + ms latency + WebSocket indicator.

### Manual config push

`POST /api/webup/sync`: re-pushes the entire current `.env` payload to the bot via batched `setenv`. Useful after:

- Restoring a backup.
- Suspecting drift between the on-disk `.env` and the bot's in-memory state.
- Restarting webup without restarting the app (usually unnecessary, but worth it if problems persist).

UI: **"Push config"** button on the webup card.

---

## SSE auto-update

Two separate SSE flows:

- `GET /api/version/update/webup/stream` — runs `pip install --upgrade Unit3DwebUp` in the webup venv, restarts `WEBUP_SYSTEMD_UNIT` in a transient scope.
- `GET /api/version/update/app/stream` — `git pull + pip install -e .` (git mode) or `pip install --upgrade --force-reinstall git+URL@vX` (pip mode), restarts `U3DP_SYSTEMD_UNIT`.

Both:

1. Stream `pip` / `git` logs line by line.
2. On `done`: zero `_cache["data"] = None; _cache["at"] = 0.0` BEFORE emitting the final event (otherwise the version shown in UI after reload is stale for 10 min).
3. Schedule restart via `systemd-run --user --on-active=3s` as a transient scope → survives the parent process SIGTERM when systemd stops the service.
4. Frontend: 5s countdown + browser reload; post-reload popup with the GitHub release body saved in `localStorage["unit3dprep.pendingChangelog"]`.

!!! warning "Never forget the cache flush"
    All 3 generators (webup, app/git, app/pip) MUST `_cache["data"]=None; _cache["at"]=0.0` before `yield _sse("done", ...)`. Omitting it causes stale version + Update button after reload.

---

## Dry-run mode

`U3DP_DRY_RUN_TRACKER=1` (or `true`/`yes`) skips `/upload` but runs the rest:

- `setenv → scan → maketorrent → seed` ✅
- `upload` ❌ (skipped, warning log emitted with `event=upload.dryrun`)

The `.torrent` still ends up in qBit. Useful for:

- Testing in WSL/dev.
- Debugging the unit3dprep pre-flight + bridge without polluting the live tracker.
- Verifying the pipeline end-to-end before enabling the real upload.

Batch upload (`stream_webup_batch`) honors the flag too: in dry-run it runs `maketorrent + seed` per job and skips `processall`.

---

## Known limitations

| Limitation | Cause | Workaround |
|---|---|---|
| `DUPLICATE_ON` / `SKIP_DUPLICATE` don't work | Webup has `# Todo Not yet implemented` in `config/settings.py` | The bridge writes them to the `.env` anyway (for future versions); the bot currently ignores them. |
| Redis cannot move from `127.0.0.1:6379` | Webup hardcoded | Run Redis on the default port. `REDIS_HOST/PORT` ignored. |
| ffmpeg fails silently | Webup screenshot generation | Verify `which ffmpeg` before the first upload. Without it, `/scan` returns `[]`. |
| `DOCKER` truthy-check broken | Webup `config/settings.py`: `if not os.getenv("DOCKER")` | Never set `DOCKER` unless really in Docker (and then `DOCKER=true`). |
| `setenv` lists must be JSON | pydantic-settings v2 runs `json.loads()` | The bridge already serializes JSON. Manual `.env` edits with CSV break the bot on the next `setenv`. |
| Empty values on `str` break webup | `empty_to_none` validator | The bridge already skips them; for hand-edited `.env`, remove empty `KEY=` lines. |
| `PREFERRED_LANG` must be ISO 639-1 | Webup compares against mediainfo's 2-letter `language` field | Use `"it"`, not `"ita"`. Since v0.6.4+ the default is already correct. See [Troubleshooting › silent /upload](troubleshooting.md#upload-returns-200-but-the-torrent-never-appears-on-the-tracker-qbit-says-infohash-not-found). |

---

## Useful debug commands

```bash
# Is the bot up?
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200

# Webup installed version
$WEBUP_VENV_BIN/python -c "import importlib.metadata as m; print(m.version('Unit3DwebUp'))"

# Health from unit3dprep
curl -s http://127.0.0.1:8765/api/webup/health  # if logged in via browser, grab the cookie

# Reset Redis (clear stale job_list_id)
redis-cli FLUSHDB

# Force re-sync of full config to webup
# (from UI: Settings → "Push config" button; or POST /api/webup/sync with session cookie)
```

For specific issues see [Troubleshooting › Unit3DWebUp](troubleshooting.md#unit3dwebup) and [Troubleshooting › Bridge](troubleshooting.md#unit3dprep-webup-bridge).
