# Installation

This guide covers installing on a Linux/macOS/WSL system with Python 3.10+. For production deployment see [VPS](deploy-vps.md) or [Ultra.cc](deploy-ultracc.md).

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | 3.11 recommended. 3.13 works but has a broken `_sqlite3` on pyenv — not blocking because the project uses JSON. |
| **libmediainfo** | System library required by `pymediainfo`. Debian/Ubuntu: `sudo apt install libmediainfo0v5`. macOS: `brew install mediainfo`. |
| **`unit3dup` on PATH** | Official uploader. Install with `pip install unit3dup`. |
| **TMDB API key** | Create an account at <https://www.themoviedb.org/> and request a v3 key from settings. |
| **Shared filesystem** | Media source and `~/seedings/` must live on the **same filesystem** for hardlinks to work. |
| **Node.js** | *Only* if you plan to rebuild the frontend. The package ships with a prebuilt frontend. |

## 1 — Clone and install

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
pip install -e .
```

Editable install lets you `git pull` future updates without reinstalling. Entry points registered:

- `unit3dprep` → interactive CLI
- `unit3dprep-web` → Web UI server

## 2 — Generate password hash and secret

```bash
python generate_hash.py
```

It prompts for a password (double confirmation) and prints the export lines:

```bash
export U3DP_PASSWORD_HASH="$2b$12$..."
export U3DP_SECRET="..."
export TMDB_API_KEY="<your_tmdb_key>"
export U3DP_PORT="8765"
export U3DP_HTTPS_ONLY="1"
```

Copy them into `~/.bashrc` (or `~/.profile` / `~/.zshrc`) and reload with `source ~/.bashrc`.

!!! warning "Required secrets"
    Without `U3DP_PASSWORD_HASH` and `U3DP_SECRET` the Web UI will refuse to start. The secret signs session cookies: never share it, never commit it.

## 3 — Prepare directories

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

## 4 — (Optional) Rebuild the frontend

The React frontend is prebuilt in `unit3dprep/web/dist/` and committed to the repo. Only rebuild it if you modified code in `frontend/`:

```bash
cd frontend
npm install
npm run build
```

The build populates `unit3dprep/web/dist/`. `MANIFEST.in` ships that folder inside the wheel, so users installing via pip never need Node.

## 5 — Launch

```bash
unit3dprep-web
```

Open <http://127.0.0.1:8765>. Log in with the password you chose in `generate_hash.py`.

For the CLI:

```bash
unit3dprep -u /path/to/movie.mkv
unit3dprep -f /path/to/season
```

See [Usage › CLI](uso-cli.md) and [Usage › Web UI](uso-web.md).

## Common issues

- **`ModuleNotFoundError: No module named 'pymediainfo'`** → `pip install -e .` didn't succeed, retry.
- **`pymediainfo` installed but library errors** → `libmediainfo` is missing. Install the system package.
- **`unit3dup: command not found`** → not on PATH. Check with `which unit3dup`; add `~/.local/bin` to PATH if needed.
- **All hardlink operations fail** → media and seedings on different filesystems. See [Troubleshooting](troubleshooting.md).
