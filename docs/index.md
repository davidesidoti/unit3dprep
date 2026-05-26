# unit3dprep

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/fastapi-109989?style=for-the-badge&logo=FASTAPI&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-222222?style=for-the-badge&logo=github%20Pages&logoColor=white)

**Web UI + CLI di pre-flight per tracker Unit3D — accoppiata via HTTP a [`Unit3DWebUp`](https://pypi.org/project/Unit3DwebUp/) come backend di upload.**

`unit3dprep` cura il pre-flight (audio italiano, nomenclatura ItaTorrents, hardlink) e orchestra `Unit3DWebUp` come bot di upload via API HTTP + WebSocket. Niente più subprocess `unit3dup` CLI: tutto passa per `setenv → scan → maketorrent → upload → seed` con log live nel browser.

![Media Library — sfoglia la libreria con poster TMDB e badge audio](assets/screenshots/media_library.png)

!!! tip "Due modalità di utilizzo"
    - **CLI** — flusso interattivo per un singolo file o un'intera stagione. Ideale via SSH. La CLI usa anch'essa il bridge HTTP verso Unit3DWebUp per la fase di upload.
    - **Web UI** — React SPA servita da FastAPI. Wizard guidato, libreria, coda upload, storico, settings, log in tempo reale, auto-update integrato.

---

## Architettura

```
┌─────────────────────┐    HTTP+WS    ┌──────────────────────┐
│   unit3dprep        │ ────────────> │   Unit3DWebUp        │
│   (FastAPI + React) │ <──────────── │   (FastAPI bot)      │
└─────────┬───────────┘     SSE       └──────────┬───────────┘
          │                                      │
          │ hardlink                             │ /maketorrent /upload /seed
          ▼                                      ▼
   ~/seedings/                             tracker (ITT/PTT/SIS) + qBittorrent
          │                                      ▲
          └────────── stesso .env ───────────────┘
                  ($ENVPATH/.env)
```

- `unit3dprep` espone la UI, la libreria media e il wizard di pre-flight.
- `Unit3DWebUp` è il bot di upload (FastAPI + Redis + ffmpeg) che parla con tracker e client torrent.
- I due processi condividono **un solo file `.env`** (path `ENVPATH`/`U3DP_ENV_PATH`) → single source of truth per credenziali tracker, client torrent, image host, preferenze.

---

## Cosa fa

1. **Scansiona** la tua libreria (sottocartelle di `U3DP_MEDIA_ROOT`, default `~/media`).
2. **Verifica** la presenza di tracce audio italiane via `pymediainfo`.
3. **Recupera** i metadati ufficiali da TMDB.
4. **Costruisce** il nome finale secondo la [nomenclatura ItaTorrents](nomenclatura.md).
5. **Hardlinka** il file rinominato in `U3DP_SEEDINGS_DIR` (default `~/seedings`, stesso filesystem richiesto).
6. **Sincronizza** i path in Unit3DWebUp via `POST /setenv` e lancia `/scan` → `/maketorrent` → `/upload` → `/seed`.
7. **Stream-a** in real-time log e progresso dei due processi via SSE/WebSocket nella UI.
8. **Registra** l'esito (exit code, tracker, timestamp) nello storico JSON e lo espone in Web UI.

---

## Avvio rapido

```bash
# 1. Installa entrambi i pacchetti (stesso venv o due venv separati)
pip install -e .
pip install Unit3DwebUp

# 2. Genera hash password + secret di sessione
python generate_hash.py

# 3. Esporta le variabili (o scrivile in ~/.bashrc / .env file di systemd)
export U3DP_PASSWORD_HASH='$2b$12$...'      # apici singoli! il $ non va espanso
export U3DP_SECRET="..."
export TMDB_API_KEY="..."
export U3DP_PORT="8765"
export ENVPATH="$HOME/.config/unit3dprep"   # cartella del .env condiviso

# 4. Avvia Unit3DWebUp (richiede Redis su 127.0.0.1:6379 e ffmpeg installati)
ENVPATH=$HOME/.config/unit3dprep uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000 &

# 5. Avvia la Web UI
unit3dprep-web
```

Apri <http://127.0.0.1:8765>, fai login, vai in **Settings** e completa tracker/qBittorrent/image host. Tutte le impostazioni vengono persistite in `$ENVPATH/.env` con la nomenclatura canonica e propagate a Unit3DWebUp via live `setenv` (no restart).

Per i dettagli completi vedi [Installazione](installazione.md), [Configurazione](configurazione.md) e [Integrazione Unit3DWebUp](integrazione-webup.md).

---

## Guide di deploy

- [**VPS con sudo / Docker**](deploy-vps.md) — server Linux generico con due systemd unit (app + bot), nginx + Let's Encrypt.
- [**Ultra.cc**](deploy-ultracc.md) — seedbox Ultra.cc con porta riservata, systemd user unit per i due processi, nginx user-proxy.

---

## Stack tecnico

| Componente | Tecnologia |
|---|---|
| Backend app | FastAPI + uvicorn + Starlette |
| SSE | sse-starlette |
| Auth | bcrypt + itsdangerous (cookie sessioni) |
| Frontend | React 18 + Vite + TypeScript + lucide-react |
| Parsing filename | guessit |
| MediaInfo | pymediainfo (richiede `libmediainfo`) |
| Metadata | TMDB API v3 (lookup nostro + Unit3DWebUp) |
| Bridge bot | `httpx` + `websockets` verso Unit3DWebUp |
| Backend upload | Unit3DWebUp (FastAPI + Redis + ffmpeg) |
| Persistenza | file JSON (no SQLite — `_sqlite3` rotto su pyenv Python 3.13) |

---

## Link utili

- Repo: <https://github.com/davidesidoti/unit3dprep>
- ItaTorrents: <https://itatorrents.xyz>
- TMDB API: <https://www.themoviedb.org/settings/api>
- Unit3DWebUp (PyPI): <https://pypi.org/project/Unit3DwebUp/>
- Unit3DWebUp (GitHub upstream): <https://github.com/31December99/Unit3DWebUp>
