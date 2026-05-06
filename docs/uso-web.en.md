# Usage › Web UI

The Web UI is a React SPA served by FastAPI. It covers the full Unit3D pre-flight workflow from the browser: library scan, guided upload, torrent queue, history, configuration, real-time logs, live integration with Unit3DWebUp. Available in **Italian and English** (TopBar switcher).

Start:

```bash
unit3dprep-web
```

Open the resulting URL (`http://<U3DP_HOST>:<U3DP_PORT><U3DP_ROOT_PATH>`, default `http://127.0.0.1:8765`). Make sure [Unit3DWebUp](integrazione-webup.md) is listening at `WEBUP_URL` (default `127.0.0.1:8000`).

---

## Login

First screen: password field. Credentials are validated against `U3DP_PASSWORD_HASH` (bcrypt). The session is signed with `U3DP_SECRET` (itsdangerous) and lasts as long as the browser keeps the cookie.

!!! note "Middleware order"
    Behind the scenes: `SessionMiddleware` must be added **after** the auth middleware (LIFO = last added is outermost). If you see `AssertionError: SessionMiddleware must be installed`, that's a bug — open an issue.

---

## Media Library

![Media Library with TMDB posters, audio language badges and detail panel](assets/screenshots/media_library.png)

Lists categories (subfolders of `U3DP_MEDIA_ROOT`) and items inside them.

Features:

- **Category dropdown** — auto-discovered (`GET /api/library/categories`). Not hardcoded.
- **Item list** — each row shows title, year (if from TMDB), total size, detected audio languages.
- **Sorting** — name, year, size.
- **Search** — live filter on name.
- **Hide uploaded** — toggle controlled by `W_HIDE_UPLOADED`.
- **Hide non-Italian** — toggle controlled by `W_HIDE_NO_ITALIAN`.
- **Detail panel** — clicking an item opens a side panel (mobile: full-screen overlay) with file list, TMDB match, actions.
- **Rescan audio languages** — button that streams the `pymediainfo` scan via SSE, updating the cache.
- **Manual TMDB match** — field to enter an ID, search button with result previews.
- **Multi-select** — checkbox on each item; action bar with "Select all", "Deselect", "Mark as uploaded" for bulk operations.
- **Type filter** — toggle to show only movies (`kind === 'movie'`), hiding series and seasons.
- **Mark uploaded at every level** — for series: full series, single season, single episode.

Relevant endpoints: `GET /api/library/categories`, `GET /api/library/{category}`, `GET /api/library/{category}/{item}`, `POST /api/library/{category}/{item}/langs`, `POST /api/tmdb/search`, `POST /api/tmdb/fetch`.

---

## Upload Wizard

![Upload Wizard — TMDB step with title preview and metadata](assets/screenshots/upload_wizard.png)

Step-by-step flow. Alternative to the CLI with persistent history, graphical progress bar and live SSE logs.

Typical steps:

1. **Select source** — file or folder under `U3DP_MEDIA_ROOT`.
2. **Audio check** — if `W_AUDIO_CHECK`, scans the tracks.
3. **TMDB** — search or ID entry. If `W_AUTO_TMDB`, auto-fetch from an existing ID.
4. **Name preview** — editable; if `W_CONFIRM_NAMES` is OFF, skips the confirmation.
5. **Hardlink** — into `U3DP_SEEDINGS_DIR/.unit3dprep/<jobid>/...` (per-upload sandbox, see [Unit3DWebUp integration](integrazione-webup.md#scan_path-semantics-per-upload-sandbox)). If `W_HARDLINK_ONLY`, stops here and records exit code `0`.
6. **Upload** — the HTTP bridge runs `setenv → scan → maketorrent → upload → seed` against Unit3DWebUp and streams logs + progress to the frontend over SSE (`GET /wizard/{token}/stream`). Phase weights shown in the bar: setenv 3% / scan 27% / maketorrent 45% / upload 15% / seed 10%.
7. **History write** — `update_exit_code(seeding_path, code)` persists into `U3DP_DB_PATH` (also from `wizard_finish` when `W_HARDLINK_ONLY=1`, exit code 0).

### Quick upload

`POST /upload/quick` skips most of the wizard for power users: you get a job ID and consume `GET /upload/{job}/stream`. Use it when you already have renamed files in `~/seedings/`. The flow calls `stream_webup` directly, no unit3dprep pre-flight.

### Dry-run

When `U3DP_DRY_RUN_TRACKER=1`, the wizard skips `/upload` but runs everything else. Useful in dev/WSL.

---

## Upload Queue

![Upload Queue — qBittorrent queue with progress bars and seeding status](assets/screenshots/queue.png)

Shows active torrents in the configured client (`TORRENT_CLIENT` in the `.env`: `qbittorrent`, `transmission`, `rtorrent`).

- Filter by name and state (downloading, seeding, paused, error).
- Auto-refresh.
- Links to local files.

Endpoint: `GET /api/queue`. Client credentials read from the `QBIT_*` / `TRASM_*` / `RTORR_*` keys of the shared `.env`.

---

## Uploaded (history)

Table of completed uploads (`GET /api/uploaded`). Fields:

- Local path in `~/seedings/`.
- Webup-bridge exit code (0 = ok, ≠0 = error, `pending` = never finished).
- Destination tracker.
- Timestamp.
- Size.
- Search and filter.

On mobile the table uses `overflow-x:auto` with `min-width:820px` to stay readable on narrow screens.

!!! bug "Stuck `pending` records"
    A record stuck as `pending` after a successful upload means the endpoint never called `update_exit_code`. This is a known regression trigger on changes to `quickupload.py` or `wizard.py` — see [Troubleshooting](troubleshooting.md#stuck-pending-records).

---

## Search Tracker

![Search Tracker — ITT results with type/resolution tags and seeder counts](assets/screenshots/search.png)

Searches for a torrent on ITT (always) and on PTT/SIS (if configured with valid URL + API key in the `.env`).

- Tab per tracker.
- Shows link, size, seeders, freeleech, upload date.
- Handy for duplicate checks before uploading.

Endpoint: `GET /api/trackers` (status) + `GET /api/search?q=...`. Under the hood `POST /api/webup/filter` proxies `Unit3DWebUp /filter`.

!!! note "Tracker status"
    A tracker shows as "Online" only if URL and API key are both set *and* the API key is not the `"no_key"` placeholder. All trackers appear in the sidebar even unconfigured ones (grey "Not set" badge).

---

## Settings

![Settings — Preferences panel with upload behaviour toggles and screenshot options](assets/screenshots/settings.png)

Full editor of the shared `.env` right in the browser. Each Save:

1. atomically writes to `$ENVPATH/.env` (canonical naming `TRACKER__* / TORRENT__* / PREFS__*` on disk);
2. propagates the changed keys to Unit3DWebUp via `POST /setenv` (no restart required).

Sections:

- **Trackers** — URL, API key, PID for ITT / PTT / SIS; `MULTI_TRACKER` list.
- **Metadata** — TMDB, TVDB, IGDB, YouTube.
- **Torrent client** — type + credentials (qBit / Transmission / rTorrent).
- **Image hosts** — preference order + API keys for PTSCREENS, PASSIMA, IMGBB, IMGFI, etc. The list order is projected to `PREFS__<HOST>_PRIORITY` (1, 2, …, 99 for hosts not in the list).
- **Upload options** — `ANON`, `PERSONAL_RELEASE`, `NUMBER_OF_SCREENSHOTS`, `COMPRESS_SCSHOT`, `TAG_ORDER_*`, etc.
- **Seeding Flow** — `U3DP_*` with effective values (env vs file) via `env_runtime()`. `UNIT3DUP_CONFIG` is read-only.
- **Version** — see [dedicated section](#version-and-auto-update).
- **App Auto-Update** — `U3DP_SYSTEMD_UNIT`, systemd user unit name used by the "Update app" button for the post-update restart. Default `unit3dprep.service`; on Ultra.cc typically `unit3dprep-web.service`.
- **Wizard Defaults** — all `W_*`.
- **Interface** — language selector (IT / EN); preference saved to `localStorage` and synced to `U3DP_LANG` via `PUT /api/settings`.

Secrets masked as `__SET__` — the field still appears populated. Editing other keys does not wipe secrets.

Endpoints: `GET /api/settings`, `PUT /api/settings`, `GET /api/settings/fs-check`.

Mobile: the left nav becomes a horizontally scrollable row; 2-col grids collapse to 1-col.

---

## Version and auto-update

In **Settings › Version** you find two side-by-side cards:

- **App** — current version (`importlib.metadata` or `pyproject.toml` in git mode) vs latest [GitHub release](https://github.com/davidesidoti/unit3dprep/releases).
- **Unit3DWebUp** — version installed in the webup venv vs latest on [PyPI](https://pypi.org/project/Unit3DwebUp/).

Each card exposes:

- **Check updates** button (force `POST /api/version/refresh` — bypass the 10-min cache).
- **Install update** button (visible only when `newer == true`).
- **Changelog** accordion with the GitHub release body (for app) or PyPI link (for webup).

Click Install:

1. `UpdateProgressModal` modal with `pip` / `git` output live-streamed via SSE (`GET /api/version/update/{app|webup}/stream`).
2. Backend invalidates `/api/version/info` `_cache` on `done`, restarts systemd in a transient scope (`systemd-run --user --on-active=3s`).
3. 5s countdown + browser reload; post-reload changelog popup (`unit3dprep.pendingChangelog` localStorage key).

!!! warning "EventSource auto-reconnects"
    If an SSE endpoint closes the connection (e.g. after `systemctl restart`), the browser re-issues the request → endpoint re-execution. The modal calls `closeSSE()` on `done`/`error` to avoid the loop. If you modify the modal, keep this invariant.

Endpoints: `GET /api/version/info`, `GET /api/version/changelog?v=X`, `GET /api/version/update/{app|webup}/stream` (SSE), `POST /api/version/refresh`.

---

## Unit3DWebUp health

In **Settings › Trackers** (or the Integrations section depending on rendering) the **Unit3DWebUp** card shows up:

- Status `online` / `offline` (5s cache, ping to `WEBUP_URL/setting`).
- Installed version.
- Ping latency in ms.
- WebSocket indicator (active connection to the bot's event channel).
- **Push config** button — runs `POST /api/webup/sync` (push the whole `.env` payload mapped to webup; useful after a backup restore or if you suspect drift).
- **Update** button — quick link to the Version card.

Endpoints: `GET /api/webup/health`, `POST /api/webup/sync`, `GET /api/webup/setting`.

---

## Logs

Real-time log stream via SSE. Anything `uvicorn` / the app writes to `logbuf` (`unit3dprep/web/logbuf.py`) shows up here, classified by:

- **source** — `app`, `wizard`, `quickupload`, `webup` (replaces legacy `unit3dup`), `system`.
- **kind** — `info` / `ok` / `warn` / `error` / `progress`.

Filters persisted in `localStorage` (`unit3dprep.logs.{hiddenSources,hiddenKinds,autoScroll}` keys).

Useful for debugging without opening a shell on the VPS.

---

## Mobile notes (≤768px)

The UI is responsive:

- **Sidebar** — closed via `translateX(-100%)`, scrim overlay when open.
- **Modal** — full-bleed with 14px padding.
- **Library detail** — `position:fixed; inset:0` overlay instead of the 360px side panel.
- **Settings nav** — horizontal scrollable row.
- **Tables** — `overflow-x:auto`.

Breakpoint handled by `isMobile` (App.tsx → Sidebar / TopBar / Library / Settings via props).

---

## Programmatic access?

Every UI view consumes the JSON API under `{U3DP_ROOT_PATH}/api/*`. You can call it directly with a valid session cookie. See `unit3dprep/web/api/*.py` for the full list of routers (settings, version, webup, library, queue, uploaded, search, tmdb, fs).
