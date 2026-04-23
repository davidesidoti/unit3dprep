# unit3dprep

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/fastapi-109989?style=for-the-badge&logo=FASTAPI&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-222222?style=for-the-badge&logo=github%20Pages&logoColor=white)

**Web UI + CLI pre-flight uploader for Unit3D trackers — direct pairing with [`unit3dup`](https://pypi.org/project/unit3dup/).**

Checks for Italian audio tracks, renames files according to the ItaTorrents naming convention (and other Unit3D trackers), hardlinks them into `~/seedings/`, and launches `unit3dup` to perform the upload. Works from a terminal or from a browser.

![Media Library — browse your library with TMDB posters and audio badges](assets/screenshots/media_library.png)

!!! tip "Two usage modes"
    - **CLI** — interactive flow for a single file or an entire season. Ideal over SSH.
    - **Web UI** — React SPA served by FastAPI. Guided wizard, upload queue, history, settings, real-time logs.

---

## What it does

1. **Scans** your library (`~/media/{movies,series,anime}` or custom folders).
2. **Checks** for Italian audio tracks via `pymediainfo`.
3. **Fetches** official metadata from TMDB (by manual ID or via search).
4. **Builds** the final filename per the [ItaTorrents naming convention](nomenclatura.md).
5. **Hardlinks** the renamed file into `~/seedings/` (same filesystem required).
6. **Launches** `unit3dup -b -u` or `unit3dup -b -f` to upload it.
7. **Records** the exit code into the history (JSON) and exposes it in the Web UI.

---

## Quick start

```bash
# 1. Install the package
pip install -e .

# 2. Generate password hash + session secret
python generate_hash.py

# 3. Export the variables (or put them into ~/.bashrc)
export U3DP_PASSWORD_HASH="..."
export U3DP_SECRET="..."
export TMDB_API_KEY="..."
export U3DP_PORT="8765"

# 4. Start the Web UI
unit3dprep-web
```

Open <http://127.0.0.1:8765> and enter the password.

For full details see [Installation](installazione.md) and [Configuration](configurazione.md).

---

## Deployment guides

- [**VPS with sudo / Docker**](deploy-vps.md) — generic Linux server using systemd, nginx + Let's Encrypt.
- [**Ultra.cc**](deploy-ultracc.md) — Ultra.cc seedbox with reserved port, user-level systemd unit, and nginx user-proxy.

---

## Tech stack

| Component | Technology |
|---|---|
| Backend | FastAPI + uvicorn + Starlette |
| SSE | sse-starlette |
| Auth | bcrypt + itsdangerous (session cookies) |
| Frontend | React 18 + Vite + TypeScript + lucide-react |
| Filename parsing | guessit |
| MediaInfo | pymediainfo (requires `libmediainfo`) |
| Metadata | TMDB API v3 |
| Upload | `unit3dup` (external CLI) |
| Persistence | JSON files (no SQLite — `_sqlite3` broken on pyenv Python 3.13) |

---

## Useful links

- Repo: <https://github.com/davidesidoti/unit3dprep>
- ItaTorrents: <https://itatorrents.xyz>
- TMDB API: <https://www.themoviedb.org/settings/api>
- `unit3dup`: <https://pypi.org/project/unit3dup/>
