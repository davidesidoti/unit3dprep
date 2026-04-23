# Usage › Web UI

The Web UI is a React SPA served by FastAPI. It covers the full ItaTorrents workflow from the browser: library scan, guided upload, torrent queue, history, configuration, real-time logs.

Start:

```bash
itatorrents-web
```

Open the resulting URL (`http://<ITA_HOST>:<ITA_PORT><ITA_ROOT_PATH>`, default `http://127.0.0.1:8765`).

---

## Login

First screen: password field. Credentials are validated against `ITA_PASSWORD_HASH` (bcrypt). The session is signed with `ITA_SECRET` (itsdangerous) and lasts as long as the browser keeps the cookie.

!!! note "Middleware order"
    Behind the scenes: `SessionMiddleware` must be added **after** the auth middleware (LIFO = last added is outermost). If auth tries to read `request.session` before SessionMiddleware is installed, it crashes with `AssertionError: SessionMiddleware must be installed`.

---

## Media Library

![Media Library with TMDB posters, audio language badges and detail panel](assets/screenshots/media_library.png)

Lists categories (subfolders of `ITA_MEDIA_ROOT`) and items inside them.

Features:

- **Category dropdown** — categories are auto-discovered (`GET /api/library/categories`). Not hardcoded.
- **Item list** — each row shows title, year (if from TMDB), total size, detected audio languages.
- **Sorting** — name, year, size.
- **Search** — live filter on name.
- **Hide uploaded** — toggle controlled by `W_HIDE_UPLOADED`.
- **Detail panel** — clicking an item opens a side panel (mobile: full-screen overlay) with file list, TMDB match, actions.
- **Rescan audio languages** — button that streams the `pymediainfo` scan via SSE, updating the cache.
- **Manual TMDB match** — field to enter an ID, search button with result previews.

Relevant endpoints: `GET /api/library/categories`, `GET /api/library/{category}`, `GET /api/library/{category}/{item}`, `POST /api/library/{category}/{item}/langs`, `POST /api/tmdb/search`, `POST /api/tmdb/fetch`.

---

## Upload Wizard

![Upload Wizard — TMDB step with title preview and metadata](assets/screenshots/upload_wizard.png)

Step-by-step flow. Alternative to the CLI with more options and persistent history.

Typical steps:

1. **Select source** — file or folder under `ITA_MEDIA_ROOT`.
2. **Audio check** — if `W_AUDIO_CHECK`, scans the tracks.
3. **TMDB** — search or ID entry. If `W_AUTO_TMDB`, auto-fetch from an existing ID.
4. **Name preview** — editable; if `W_CONFIRM_NAMES` is OFF, skips the confirmation.
5. **Hardlink** — into `ITA_SEEDINGS_DIR`. If `W_HARDLINK_ONLY`, it stops here and records exit code `0`.
6. **Upload** — launches `unit3dup` inside a PTY and streams the output live via SSE (`GET /wizard/{token}/stream`).
7. **History write** — `update_exit_code(seeding_path, code)` persists into `ITA_DB_PATH`.

### Quick upload

`POST /upload/quick` skips most of the wizard for power users: you get a job ID directly and consume `GET /upload/{job}/stream`. Use it when you already have renamed files in `~/seedings/`.

---

## Upload Queue

![Upload Queue — qBittorrent queue with progress bars and seeding status](assets/screenshots/queue.png)

Shows active torrents in the configured client (`TORRENT_CLIENT` in `Unit3Dbot.json`: `qbittorrent`, `transmission`, `rtorrent`).

- Filter by name and state (downloading, seeding, paused, error).
- Auto-refresh.
- Links to local files.

Endpoint: `GET /api/queue`. Client credentials read from `QBIT_*` / `TRASM_*` / `RTORR_*`.

---

## Uploaded (history)

Table of completed uploads (`GET /api/uploaded`). Fields:

- Local path in `~/seedings/`.
- `unit3dup` exit code (0 = ok, ≠0 = error, `pending` = never finished).
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

Searches for a torrent on ITT (always) and on PTT/SIS (if configured in `Unit3Dbot.json` with valid URL + API key).

- Tab per tracker.
- Shows link, size, seeders, freeleech, upload date.
- Handy for duplicate checks before uploading.

Endpoint: `GET /api/trackers` (status) + `GET /api/search?q=...`.

!!! note "Tracker status"
    A tracker shows as "Online" only if URL and API key are both set *and* the API key is not the `"no_key"` placeholder. All trackers appear in the sidebar even unconfigured ones (grey "Not set" badge).

---

## Settings

![Settings — Preferences panel with upload behaviour toggles and screenshot options](assets/screenshots/settings.png)

Full `Unit3Dbot.json` editor right in the browser.

Sections:

- **Trackers** — URL, API key, PID for ITT / PTT / SIS; `MULTI_TRACKER` list.
- **Metadata** — TMDB, TVDB, IGDB, YouTube.
- **Torrent client** — type + credentials (qBit / Transmission / rTorrent).
- **Image host** — preference order + API keys for PTSCREENS, PASSIMA, IMGBB, etc.
- **Upload options** — `DUPLICATE_ON`, `ANON`, `NUMBER_OF_SCREENSHOTS`, `COMPRESS_SCSHOT`, ...
- **Seeding Flow** — `ITA_*` with effective values (env vs config) via `env_runtime()`. `UNIT3DUP_CONFIG` is read-only.
- **App Auto-Update** — `ITA_SYSTEMD_UNIT`, systemd user unit name used by the "Update app" button for the post-update restart. Default `itatorrents.service`; on Ultra.cc typically `itatorrents-web.service`.
- **Wizard Defaults** — all `W_*`.

Secrets masked as `__SET__` — the field still appears populated. Editing other keys does not wipe secrets.

Endpoints: `GET /api/settings`, `PUT /api/settings`, `GET /api/settings/fs-check`.

Mobile: the left nav becomes a horizontally scrollable row; 2-col grids collapse to 1-col.

---

## In-app auto-update

At the bottom-left of the Sidebar, above the trackers list, a banner appears when a newer release of the installed app or `unit3dup` is available.

- **App** → GitHub Releases (`api.github.com/repos/.../releases/latest`). The flow auto-picks `git pull + pip install -e .` if the source is a git checkout, otherwise `pip install --upgrade --force-reinstall git+URL@vX`.
- **unit3dup** → PyPI (`pypi.org/pypi/unit3dup/json`). `pip install --upgrade unit3dup`.

On click:

1. Modal with `pip`/`git` output live-streamed via SSE (`/api/version/update/{app|unit3dup}/stream`).
2. When done, a "Refresh in 5…1" countdown + automatic browser reload.
3. Post-reload popup with the new release changelog (GitHub release body).

The "Update app" button stays disabled (`can_update_app: false`) if the systemd user unit is not reachable. See [Configuration › In-app auto-update](configurazione.en.md#in-app-auto-update) for details (including the `ITA_SYSTEMD_UNIT` key).

Endpoints: `GET /api/version/info`, `GET /api/version/changelog?v=X`, `GET /api/version/update/{app|unit3dup}/stream` (SSE), `POST /api/version/refresh`.

---

## Logs

Real-time log stream via SSE. Anything `uvicorn` / the app writes to `logbuf` (`itatorrents/web/logbuf.py`) shows up here.

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

Every UI view consumes the JSON API under `{ITA_ROOT_PATH}/api/*`. You can call it directly with a valid session cookie. See `itatorrents/web/api/*.py` for the full list of routers.
