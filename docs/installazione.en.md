# Installation

This guide covers installing on a Linux/macOS/WSL system with Python 3.12+, both `unit3dprep` (Web UI + CLI) and the upload backend `Unit3DWebUp`. For production deployment see [VPS](deploy-vps.md) or [Ultra.cc](deploy-ultracc.md).

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.12+** | **Required by Unit3DWebUp 0.0.25** (`requires_python >=3.12`): on 3.10/3.11 the `pip install Unit3DwebUp` in step 2 fails with a *Requires-Python* error. `unit3dprep` alone runs on 3.10+, but the full stack needs 3.12+. 3.13 works (the project uses JSON, not `_sqlite3`). |
| **libmediainfo** | System library required by `pymediainfo`. Debian/Ubuntu: `sudo apt install libmediainfo0v5`. macOS: `brew install mediainfo`. |
| **ffmpeg** | Required by Unit3DWebUp to generate screenshots. Without it `/scan` silently returns 0 items. Debian/Ubuntu: `sudo apt install ffmpeg`. |
| **Redis** | Required by Unit3DWebUp. Hardcoded to `127.0.0.1:6379` (the `REDIS_HOST`/`REDIS_PORT` env vars are ignored by webup). Debian/Ubuntu: `sudo apt install redis-server && sudo systemctl enable --now redis-server`. |
| **TMDB API key** | Create an account at <https://www.themoviedb.org/> and request a v3 key from settings. Same value goes to both unit3dprep (`TMDB_API_KEY`) and Unit3DWebUp (`TMDB_APIKEY` in the shared `.env`). |
| **Shared filesystem** | `U3DP_MEDIA_ROOT` and `U3DP_SEEDINGS_DIR` must live on the **same filesystem** for hardlinks to work. |
| **Node.js** | *Only* if you plan to rebuild the frontend. The package ships with a prebuilt frontend. |

## 1 — Clone unit3dprep and install

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

!!! tip "Also on PyPI"
    The package is published: `pip install unit3dprep` (handy to integrate it into an existing environment). For the full flow in this guide a `git clone` is still preferable: `generate_hash.py` (step 3) and the systemd templates live in the repo. Otherwise use the [all-in-one Docker setup](docker.md), which needs none of this.

Entry points registered:

- `unit3dprep` → interactive CLI
- `unit3dprep-web` → Web UI server

## 2 — Install Unit3DWebUp

`Unit3DWebUp` is the HTTP backend that performs the actual upload to the tracker. Install it from PyPI in the same venv (simpler) or in a dedicated one:

!!! danger "Python 3.12+ required"
    `Unit3DwebUp` 0.0.25 declares `requires_python >=3.12`: if the venv from step 1 runs Python 3.10/3.11, `pip install Unit3DwebUp` fails with `ERROR: ... requires a different Python`. Check with `python3 --version` and recreate the venv with a 3.12+ interpreter if needed.

```bash
# Same venv (simple)
pip install Unit3DwebUp

# Or dedicated venv
mkdir -p ~/dev/Unit3DWebUp && cd ~/dev/Unit3DWebUp
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install Unit3DwebUp
.venv/bin/python -c "import unit3dwup.start; print(unit3dwup.start.app)"
```

!!! warning "No `requirements.txt`"
    The `0.0.x` branch of `Unit3DWebUp` **no longer ships `requirements.txt`**. Canonical install is via PyPI as above. The integrated auto-update in `unit3dprep` runs `pip install --upgrade Unit3DwebUp` (NOT `-r requirements.txt`).

## 3 — Generate password hash and secret

```bash
python generate_hash.py
```

Prompts for a password (double confirmation) and prints the export lines:

```bash
export U3DP_PASSWORD_HASH='$2b$12$...'      # MUST be single quotes
export U3DP_SECRET="..."
export TMDB_API_KEY="<your_tmdb_key>"
export U3DP_PORT="8765"
export U3DP_HTTPS_ONLY="1"
export ENVPATH="$HOME/.config/unit3dprep"   # directory of the shared .env
```

Copy them into `~/.bashrc` (or `~/.profile` / `~/.zshrc`) and reload with `source ~/.bashrc`.

!!! danger "Single quotes around the bcrypt hash"
    `U3DP_PASSWORD_HASH` contains the `$` character (e.g. `$2b$12$...`). In bash with double quotes, `$2b` and `$12` get expanded as empty variables → mutilated hash → silent 401 login failures with no startup error. **Always** use single quotes, or escape the `$`, even inside systemd `.env` files.

!!! warning "Required secrets"
    Without `U3DP_PASSWORD_HASH` and `U3DP_SECRET` the Web UI refuses to start. The secret signs session cookies: never share it, never commit it.

## 4 — Prepare directories

Default expected layout:

```
~/
├── media/
│   ├── movies/
│   │   └── <film-title>/file.mkv
│   ├── series/
│   │   └── <series-title>/Season 01/S01E01.mkv
│   └── anime/
└── seedings/          # must live on the same FS as ~/media
```

Categories are **auto-discovered** as subfolders of `~/media/`. Name them however you want (`movies`, `film`, `anime`, `documentaries`, ...) — no code changes required.

### Verify shared filesystem

Hardlinks only work inside the same filesystem. Check:

```bash
df ~/media ~/seedings
```

Both paths must report the **same device**. If they differ, move `~/seedings/` onto the media FS, or point `U3DP_SEEDINGS_DIR` elsewhere (see [Configuration](configurazione.md)).

The Web UI exposes `GET /api/settings/fs-check` which runs the same test.

## 5 — (Optional) Rebuild the frontend

The React frontend is prebuilt in `unit3dprep/web/dist/` and committed to the repo. Only rebuild it if you modified code in `frontend/`:

```bash
cd frontend
npm install
npm run build
```

The build populates `unit3dprep/web/dist/`. `MANIFEST.in` ships that folder inside the wheel, so users installing via pip never need Node.

## 6 — Start Unit3DWebUp

The bot must be running before `unit3dprep-web` (the app can start without it, but the upload wizard will fail on the first request). Start it manually:

```bash
ENVPATH=$HOME/.config/unit3dprep \
  uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000
```

To make it persistent see the templates in [`deploy/systemd/`](https://github.com/davidesidoti/unit3dprep/tree/main/deploy/systemd) (the `unit3dwebup.service` section) or the [VPS](deploy-vps.md) / [Ultra.cc](deploy-ultracc.md) guides.

Smoke test:

```bash
curl -s -X POST http://127.0.0.1:8000/setting -H 'Content-Type: application/json' -d '{}' | head -c 200
```

Must return a JSON `{"userPreferences": {...}}`. If you see `500` on everything, see [Troubleshooting › Unit3DWebUp](troubleshooting.md#unit3dwebup).

## 7 — Launch unit3dprep

```bash
unit3dprep-web
```

Open <http://127.0.0.1:8765>. Log in with the password chosen in `generate_hash.py`. Go to **Settings** and complete:

- **Trackers** — URL + API key + PID for ITT (and optionally PTT, SIS).
- **Torrent client** — qBittorrent host/port/credentials.
- **Image hosts** — at least one configured key, ordered in `IMAGE_HOST_ORDER`.
- **Metadata** — TMDB key (same as `TMDB_API_KEY`), optionally TVDB and IGDB.

Settings are persisted atomically to `$ENVPATH/.env` with the canonical naming (`TRACKER__*`, `TORRENT__*`, `PREFS__*`) and synced to Unit3DWebUp via `POST /setenv` with no restart.

For the CLI:

```bash
unit3dprep -u /path/to/movie.mkv
unit3dprep -f /path/to/season
```

See [Usage › CLI](uso-cli.md) and [Usage › Web UI](uso-web.md).

## Migration from legacy `Unit3Dbot.json`

If you previously used `unit3dup` directly there is likely a `~/Unit3Dup_config/Unit3Dbot.json` with your historical config. On the first `load()` of `unit3dprep`:

1. the file is read;
2. rewritten as `.env` at `$ENVPATH/.env` with the canonical naming;
3. renamed to `Unit3Dbot.json.migrated-bak` (never deleted — the user decides).

The operation is idempotent: if `.migrated-bak` already exists, nothing is redone. To point at a non-standard path use `UNIT3DUP_CONFIG=/path/to/Unit3Dbot.json`.

## Common issues

- **`ModuleNotFoundError: No module named 'pymediainfo'`** → `pip install -e .` didn't succeed, retry.
- **`pymediainfo` installed but library errors** → `libmediainfo` is missing. Install the system package.
- **All hardlink operations fail** → media and seedings on different filesystems. See [Troubleshooting](troubleshooting.md).
- **Silent 401 login** → mutilated bcrypt hash. Use single quotes around `U3DP_PASSWORD_HASH`.
- **Webup returns 500 on everything** → typically empty values in `.env` or `DOCKER` set. See [Troubleshooting › Unit3DWebUp](troubleshooting.md#unit3dwebup).
