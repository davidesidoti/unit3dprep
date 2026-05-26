# Troubleshooting

Common problems and their known causes.

---

## Hardlinks

### `OSError: [Errno 18] Invalid cross-device link`

`U3DP_MEDIA_ROOT` and `U3DP_SEEDINGS_DIR` live on different filesystems. Check:

```bash
df <media> <seedings>
```

If the device numbers differ, move `~/seedings/` under the same mount as your media, or point `U3DP_SEEDINGS_DIR` to a valid path.

The UI exposes `GET /api/settings/fs-check` for the same check from the browser.

### Hardlink succeeds but the upload takes double the space

This should not happen: hardlinks share inodes. If you see `du` reporting double, verify the FS really is the same (`stat -c %i <media_file> <seedings_file>` → same inode).

---

## MediaInfo

### `pymediainfo` installs but crashes at runtime

`libmediainfo` is missing. Install the system package:

- Debian/Ubuntu: `sudo apt install libmediainfo0v5`
- Arch: `sudo pacman -S libmediainfo`
- macOS: `brew install mediainfo`
- Alpine: `apk add mediainfo`

On Ultra.cc it should already be present; if missing, open a ticket.

---

## Unit3DWebUp

### Every webup request returns 500

Three common causes:

1. **`DOCKER` env var set** → webup `config/settings.py` does `env_file=ENV_FILE if not os.getenv("DOCKER") else None` (truthy check). Any non-empty value (including `false`) blocks `.env` reading → every `TRACKER__/PREFS__` reports "Field required". **Fix**: remove `DOCKER` from the unit/shell. Use `DOCKER=true` ONLY when actually in Docker.
2. **Empty values on `str` fields in `.env`** → e.g. `TRACKER__APIKEY=` (empty) on pydantic validators with `empty_to_none` → `None` → `SystemExit(1)` on the next `setenv`. **Fix**: the unit3dprep bridge already skips empty values, but if you edited `.env` manually, remove empty `KEY=` lines.
3. **`PREFS__TORRENT_ARCHIVE_PATH` missing / empty / non-existent** → webup's `get_settings()` fails. The bridge inserts `.` as fallback; if you removed the key by hand, reopen Settings → Save in the UI to re-apply the fallback.

### Webup version shows `Current: -` / Update button always visible

The lookup chain is: HTTP `/setting` → `pip metadata` (venv) → parse `.env`. If all three fail, the card stays at `-`.

```bash
# Verify the right venv
ls "$WEBUP_VENV_BIN/python"   # default ~/dev/Unit3DWebUp/.venv/bin/python
$WEBUP_VENV_BIN/python -c "import importlib.metadata as m; print(m.version('Unit3DwebUp'))"
```

If `PackageNotFoundError`, install:

```bash
$WEBUP_VENV_BIN/pip install Unit3DwebUp
```

### `/scan` returns `0 items`

Three causes:

1. **ffmpeg missing** — webup generates screenshots via ffmpeg, fails silently. Check `which ffmpeg`.
2. **Invalid TMDB/TVDB API keys** — webup logs but `/scan` still returns `[]`. Check `TRACKER__TMDB_APIKEY` / `TRACKER__TVDB_APIKEY` in the `.env`.
3. **Image host not configured** — webup tries to upload screenshots before responding. If no host has a valid key, the pipeline fails. Configure at least one host in **Settings → Image hosts**.

### `MULTI_TRACKER` or `TAG_POSITION_*` rejected by `/setenv`

Webup expects lists as **JSON arrays** (not CSV). pydantic-settings v2 runs `json.loads()` on `os.environ` after `/setenv`. Correct example: `TRACKER__MULTI_TRACKER=["itt"]`.

The unit3dprep bridge serializes correctly: if the issue persists, check there are no manual edits to the `.env` with CSV (`itt,ptt`).

### `/upload` returns 200 but the torrent never appears on the tracker — qBit says "InfoHash not found"

Symptom: qBit seeds locally, `/upload` HTTP returns 200 OK within milliseconds, `/seed` succeeds, but the tracker doesn't see the upload and qBit's announce status reads **"InfoHash not found"**. No webup log lines between `POST /upload 200 OK` and `POST /seed`, no upload `posterLogMessage` in the Web UI.

**Cause**: `PREFS__PREFERRED_LANG` is an ISO **639-2** code (`"ita"`, `"eng"`, `"fre"`) instead of **639-1** (`"it"`, `"en"`, `"fr"`). Webup 0.0.25 in `tags_service.mediainfo_audio` compares `PREFERRED_LANG` against each audio track's `language` field (mediainfo emits the 2-letter code). Mismatch → `media.can_upload = False` → `UploadUseCase.execute()` filters the media out (`tasks = [... if media.can_upload]`) → returns 200 OK with `tasks=[]` → no tracker submission, no WS message.

**Fix**:

```bash
sed -i 's/^PREFS__PREFERRED_LANG=.*/PREFS__PREFERRED_LANG=it/' ~/.config/unit3dprep/.env
systemctl --user restart unit3dwebup
# Remove the stale .torrent from the archive (otherwise webup reuses it and skips maketorrent):
rm -f "$(grep ^PREFS__TORRENT_ARCHIVE_PATH ~/.config/unit3dprep/.env | cut -d= -f2-)/ITT/<file>.mkv.torrent"
# Remove the torrent from qBit (UI or CLI) to avoid an infohash conflict, then retry from the Web UI.
```

Since v0.6.4+ the `DEFAULT_CONFIG` default is `"it"`; this only affects existing installs whose `.env` was migrated from v0.6.3.

### Webup `/upload` hangs / no progress

Webup emits `posterLogMessage` like `[New torrent] FILE - N%` during maketorrent, **not** "torrent created/exists". The unit3dprep orchestrator uses `HTTP 200 = phase complete` + ~1.5–2s buffered log drain. If you see hangs:

- Increase `PHASE_TIMEOUT` (default 1800s) in `webup_orchestrator.py`.
- Verify WebSocket is connected: Settings → Unit3DWebUp card must show WS `connected`.
- Restart the bot: `systemctl --user restart unit3dwebup.service`.

### Redis cannot be moved

`Unit3DWebUp` hardcodes Redis at `localhost:6379`. `REDIS_HOST` / `REDIS_PORT` are ignored. If your Redis runs on a non-standard port, also bind it to 6379 or use `iptables`/`socat` redirect.

### Stale Redis `job_list_id` cleanup

If `/processall` (batch upload) acts strange after crash or repeated tests:

```bash
redis-cli FLUSHDB
```

Wipes all cached `job_list_id` keys and lets the bot start fresh.

---

## Auto-update

### Update loops / EventSource keeps reconnecting

The browser's `EventSource` auto-reconnects when an SSE endpoint closes the connection (e.g. after `systemctl restart`). The `UpdateProgressModal` must call `closeSSE()` on `done`/`error`. If you see a loop, that's a regression: the fix is already in v0.6.x — verify you don't have mixed installs with stale frontend.

### Version and Update button stale after reload

`/api/version/info` cache TTL = 10 min. After a successful update, the `update/{webup,app}/stream` endpoint must zero `_cache` BEFORE emitting `done`. If you see the old version + Update button after reload:

1. Force refresh: "Check for updates" button → `POST /api/version/refresh`.
2. If it persists: hard-reload the browser (`Ctrl+Shift+R`).
3. If it still persists: verify `_cache["data"] = None` is called in `update_unit3dup` / `_update_app_from_pip` / `_update_app_from_git` BEFORE `yield _sse("done", ...)`.

### Permanent `can_update_app: false`

Three causes:

1. `systemctl` not in the process PATH.
2. `U3DP_SYSTEMD_UNIT` points to a unit that doesn't exist. **Fix**: set `U3DP_SYSTEMD_UNIT=unit3dprep-web.service` in `[Service] Environment=...` (or save it from Settings → App Auto-Update).
3. The unit exists but is not accessible to `systemctl --user cat`. Verify with `systemctl --user cat <unit>` from the process shell.

### `status=203/EXEC` on `systemctl status`

Path in `ExecStart` does not exist (NOT a Python error). Verify:

```bash
ls -la $(grep -oP 'ExecStart=\K\S+' ~/.config/systemd/user/<unit>.service)
which unit3dprep-web
```

### Webup update fails with "Could not open requirements file"

You're using an old install that runs `pip install -r requirements.txt`. Webup `0.0.x` no longer ships `requirements.txt`. The fix is in v0.6+: ensure the app is updated.

---

## Web UI / FastAPI

### `AssertionError: SessionMiddleware must be installed`

Middleware order is wrong. `SessionMiddleware` must be added **after** the auth middleware (FastAPI applies middlewares LIFO → last added is outermost). If auth tries to read `request.session` before SessionMiddleware is installed, it crashes.

If you see this after touching `unit3dprep/web/app.py`, restore the order: `add_middleware(auth)` **before** `add_middleware(SessionMiddleware, ...)`.

### Silent 401 login

Mutilated bcrypt hash. The `.env` file or systemd `Environment=` has `U3DP_PASSWORD_HASH="$2b$12$..."` with double quotes: bash expands `$2b`/`$12` as empty variables → truncated hash → silent login failure.

**Fix**: use single quotes or escapes:

```bash
U3DP_PASSWORD_HASH='$2b$12$...'    # single quotes
# OR
U3DP_PASSWORD_HASH=\$2b\$12\$...   # escape
```

### 404 on every route under `/unit3dprep`

Mismatch between `U3DP_ROOT_PATH` and the nginx in front. Two valid combos:

| nginx `proxy_pass` | `U3DP_ROOT_PATH` |
|---|---|
| `http://127.0.0.1:8765` (no trailing slash) | `/unit3dprep` |
| `http://127.0.0.1:8765/` (trailing slash) | `""` |

If you are on Ultra.cc, go with the first. `app-nginx restart` after each change.

### Blank page with 404 on assets

The frontend requests assets at `{ROOT_PATH}/assets/...`. The app mounts them via `app.mount(f"{ROOT_PATH}/assets", ...)`. If you see 404 on assets:

1. Verify `unit3dprep/web/dist/` contains `index.html` + `assets/`.
2. Verify `index.html` contains `window.__ROOT_PATH__ = "/unit3dprep"` (injected at serve-time).
3. Restart the service after changing `U3DP_ROOT_PATH`.

### Session cookie not persisting behind HTTPS

Set `U3DP_HTTPS_ONLY=1` and verify nginx forwards `X-Forwarded-Proto: https`. Otherwise Starlette sets `Secure` on the cookie but the browser sees HTTP → cookie dropped.

### SSE (Server-Sent Events) closes immediately

Classic nginx issue: buffering. Add to the server block:

```nginx
proxy_buffering off;
proxy_read_timeout 1h;
```

On Ultra.cc this is already recommended in the [nginx guide](deploy-ultracc.md#8-nginx-user-proxy).

---

## unit3dprep ↔ webup bridge

### Settings → Unit3DWebUp card **red** (offline)

Check in order:

1. Bot running? `systemctl --user status unit3dwebup.service` or `curl http://127.0.0.1:8000/setting -X POST -d '{}' -H 'Content-Type: application/json'`.
2. Does `WEBUP_URL` point to the right place? `echo $WEBUP_URL` (default `http://127.0.0.1:8000`).
3. Redis up? `redis-cli ping` → `PONG`.
4. Logs: `journalctl --user -u unit3dwebup -f` shows startup errors?

### Settings UI Save does not update webup

Every `PUT /api/settings` cascades into `webup_client.setenv(key, value)` for every changed canonical key. If `setenv` fails, the UI Save still succeeds (atomic write to `.env` + best-effort propagation).

Verify:

1. Health card green — webup reachable?
2. Logs tab → filter source `webup` — see `setenv: ...` errors?
3. **"Push config"** button in Settings forces a `POST /api/webup/sync` (full push of the mapped `.env`). Use it after backup restore or if you suspect drift.

### Wizard upload "no Media for X (0 items)" or "(got N items)" with your file missing

The bridge creates a dedicated sandbox per upload at `<seedings>/.unit3dprep/<jobid>/` and uses that as `SCAN_PATH`, so webup only sees the target item. See [Unit3DWebUp integration › per-upload sandbox](integrazione-webup.md#scan_path-semantics-per-upload-sandbox).

If you still see the error:

- **ffmpeg missing** → webup `/scan` silently fails on screenshots. `which ffmpeg`.
- **Invalid or empty TMDB/TVDB API keys** → webup logs `[ERROR] AsyncHttpClient: ... value should be str, int or float, got None`. Set it in **Settings → Metadata** (both `TMDB_APIKEY` for webup and `TMDB_API_KEY` env for unit3dprep — same value).
- **Image host not configured** → webup tries to upload screenshots before responding. Configure at least one key in **Settings → Image hosts**.
- **Legacy flat layout in `~/seedings/<file>.mkv` (no sandbox)** → pre-sandbox install. Re-upload from the UI to generate the sandbox, or move by hand to `<seedings>/.unit3dprep/<random>/<file>.mkv`.
- **Race with other active sandboxes** → `app.state.webup_scan_lock` serializes uploads inside the unit3dprep process. If multiple unit3dprep instances talk to the same webup, suspend one.

---

## TMDB

### `TMDB API error: 401 Unauthorized`

`TMDB_API_KEY` missing or wrong. Check on <https://www.themoviedb.org/settings/api>.

The CLI prompts on every run. The Web UI uses both `TMDB_API_KEY` (unit3dprep env) and `TRACKER__TMDB_APIKEY` (webup key in the shared `.env`) — both must hold the same valid value.

### TMDB search returns zero results

Check `U3DP_TMDB_LANG`. If it is `it-IT` and the title does not exist in Italian, try `en-US`.

---

## Legacy CHANGELOG

### Stuck `pending` records

The record stays `pending` when the endpoint never called `update_exit_code`. Known cases:

- `quickupload.py` must call `await update_exit_code(state["path"], code)` on the `done` event.
- `wizard.py` → `wizard_finish` must call `await update_exit_code(seeding_path, 0)` (the in-memory state does not suffice).

If it happens after an update, verify these calls still exist in the code. They are regression markers: never remove them.

---

## Development / Windows

### Env var `U3DP_ROOT_PATH=/unit3dprep` gets turned into a Windows path

MSYS2 / Git Bash on Windows automatically convert strings that start with `/`. To bypass:

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  env U3DP_ROOT_PATH=/unit3dprep python -m uvicorn unit3dprep.web.app:app
```

Or use PowerShell (`$env:U3DP_ROOT_PATH = "/unit3dprep"`).

### WSL dev: `pip install` error `externally-managed-environment`

You're running uvicorn with `/usr/bin/python3` instead of the venv. The auto-update calls `sys.executable -m pip` → PEP 668 blocks. **Fix**: run uvicorn from `.venv/bin/uvicorn` (or with venv active).

### WSL dev: `systemd unit not available`

Normal in WSL dev. The update flow needs systemd `--user`. Test the full update flow only on Ultra.cc or a real VPS.

### Backend build fails on Python 3.14

Use `setuptools.build_meta`, not `setuptools.backends.legacy` (already correct in `pyproject.toml`).

### `ENVPATH` leaks cross-shell

`ENVPATH` is a convention documented by upstream webup and propagates easily between shells. For maintenance commands use the explicit prefix:

```bash
U3DP_ENV_PATH=$HOME/.config/unit3dprep/.env python -c "from unit3dprep.web import config; config.save(config.load())"
```

otherwise `config_path()` may resolve to `$ENVPATH/.env` (e.g. `/home/<user>/.env`) and write in the wrong place.

---

## JSON history

### The file grows large

`~/.unit3dprep_db.json` grows linearly with uploads. If you worry:

```bash
jq '.[:1000]' ~/.unit3dprep_db.json > ~/.unit3dprep_db.json.trim
mv ~/.unit3dprep_db.json.trim ~/.unit3dprep_db.json
```

Always back up first.

### `_sqlite3` broken on pyenv 3.13 / Ultra.cc

Known. The project **does not use** SQLite for this exact reason: history + caches are JSON files. If you see `_sqlite3 undefined symbol` errors, they come from a different library. Install Python 3.11 via pyenv and point the venv there.

---

## If nothing works

1. `journalctl --user -u unit3dprep-web -u unit3dwebup -f` (Ultra.cc) or `journalctl -u unit3dprep-web -u unit3dwebup -f` (VPS).
2. Live logs in the Web UI → Logs panel (filter source `webup` for bot issues).
3. Open an issue: <https://github.com/davidesidoti/unit3dprep/issues> with:
   - Python version (`python3 --version`)
   - `pip show unit3dprep` and `pip show Unit3DwebUp` outputs
   - Relevant env vars (without secrets)
   - Last ~50 lines of `journalctl` for both units
   - Output of `GET /api/settings/fs-check` and `GET /api/webup/health`
