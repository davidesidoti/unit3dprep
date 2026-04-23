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

## `unit3dup`

### `unit3dup: command not found`

Not on the PATH of the process that launched the CLI/Web. Check:

```bash
which unit3dup
```

If you find it but the systemd service cannot, add this to the `.service` file:

```ini
Environment=PATH=%h/.venvs/unit3dprep/bin:/usr/local/bin:/usr/bin:/bin
```

### Non-zero exit code stays in history

Found an `unit3dup` bug? The exit code is faithfully recorded in `U3DP_DB_PATH`. Open the upload log from the Uploaded panel in the Web UI for the full output.

### Stuck `pending` records

The record stays `pending` when the endpoint never called `update_exit_code`. Known cases:

- `quickupload.py` must call `await update_exit_code(state["path"], code)` on the `done` event.
- `wizard.py` → `wizard_finish` must call `await update_exit_code(seeding_path, 0)` (the in-memory state does not suffice).

If it happens after an update, verify these calls still exist in the code. They are regression markers: never remove them.

---

## Web UI / FastAPI

### `AssertionError: SessionMiddleware must be installed`

Middleware order is wrong. `SessionMiddleware` must be added **after** the auth middleware (FastAPI applies middlewares LIFO → last added is outermost). If auth tries to read `request.session` before SessionMiddleware is installed, it crashes.

If you see this after touching `unit3dprep/web/app.py`, restore the order: `add_middleware(auth)` **before** `add_middleware(SessionMiddleware, ...)`.

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

On Ultra.cc this is already recommended in the [nginx guide](deploy-ultracc.md#6-nginx-user-proxy).

---

## TMDB

### `TMDB API error: 401 Unauthorized`

`TMDB_API_KEY` missing or wrong. Check on <https://www.themoviedb.org/settings/api>.

The CLI prompts on every run; the Web UI uses both `TMDB_API_KEY` and `TMDB_APIKEY` inside `Unit3Dbot.json`.

### TMDB search returns zero results

Check `U3DP_TMDB_LANG`. If it is `it-IT` and the title does not exist in Italian, try `en-US`.

---

## Development / Windows

### Env var `U3DP_ROOT_PATH=/unit3dprep` gets turned into a Windows path

MSYS2 / Git Bash on Windows automatically convert strings that start with `/`. To bypass:

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  env U3DP_ROOT_PATH=/unit3dprep python -m uvicorn unit3dprep.web.app:app
```

Or use PowerShell (`$env:U3DP_ROOT_PATH = "/unit3dprep"`).

### Backend build fails on Python 3.14

Use `setuptools.build_meta`, not `setuptools.backends.legacy` (already correct in `pyproject.toml`).

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

Known. The project **does not use** SQLite for this exact reason: history + caches are JSON files. If you see `_sqlite3 undefined symbol` errors, they come from a different library (e.g. something calling `sqlite3` for caching). Install Python 3.11 via pyenv and point the venv there.

---

## If nothing works

1. `journalctl --user -u unit3dprep-web -f` (Ultra.cc) or `journalctl -u unit3dprep-web -f` (VPS).
2. Live logs in the Web UI → Logs panel.
3. Open an issue: <https://github.com/davidesidoti/unit3dprep/issues> with:
   - Python version (`python3 --version`)
   - `pip show unit3dprep` output
   - Relevant env vars (without secrets)
   - Last ~50 lines of `journalctl`
   - Output of `GET /api/settings/fs-check`
