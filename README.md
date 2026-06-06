# unit3dprep

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/fastapi-109989?style=for-the-badge&logo=FASTAPI&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-222222?style=for-the-badge&logo=github%20Pages&logoColor=white)

Web UI + CLI di pre-flight per tracker Unit3D, accoppiata via HTTP a [`Unit3DWebUp`](https://pypi.org/project/Unit3DwebUp/) come backend di upload.
Verifica tracce audio italiane, rinomina secondo la [nomenclatura ItaTorrents](docs/nomenclatura.md), crea hardlink in `~/seedings/` e orchestra il flusso `setenv → scan → maketorrent → upload → seed` su `Unit3DWebUp` con log live via WebSocket/SSE.

Configurazione unificata: un singolo file `.env` condiviso tra `unit3dprep` e `Unit3DWebUp` (path `ENVPATH`/`U3DP_ENV_PATH`). Le modifiche fatte da Settings vengono propagate al bot via `POST /setenv` senza riavvio.

Auto-update integrato per **app** (GitHub Releases) e **Unit3DWebUp** (PyPI): pulsante "Aggiorna" in Settings → Versione, log `pip`/`git` live-streamed via SSE, restart systemd e reload del browser con popup changelog.
La Web UI è disponibile in **italiano e inglese** (selettore nella TopBar).

**Controllo duplicati pre-upload**: prima di costruire il `.torrent` il bridge interroga l'API ITT per `tmdbId` e match esatto sulla dimensione in byte. Se trova un duplicato mostra un pannello con i dettagli + "Carica comunque / Annulla"; l'annullamento traccia "duplicato skippato" nello storico e nasconde l'item dalla Media Library. Replica il vecchio `unit3dup` CLI (Unit3DWebUp 0.0.25 non implementa duplicate detection). Disabilitabile con `W_DUPLICATE_CHECK=false`.

![Media Library](docs/assets/screenshots/media_library.png)

**Documentazione completa → <https://davidesidoti.github.io/unit3dprep/>**

---

## Quick start

```bash
# 1. unit3dprep + Unit3DWebUp nello stesso venv (o due venv separati)
pip install -e .
pip install Unit3DwebUp

# 2. Genera secret e password hash
python generate_hash.py

# 3. Variabili minime in ~/.bashrc
export U3DP_PASSWORD_HASH='$2b$12$...'      # apici singoli — il $ NON va espanso
export U3DP_SECRET="..."
export TMDB_API_KEY="..."
export U3DP_PORT="8765"
export ENVPATH="$HOME/.config/unit3dprep"   # condiviso con Unit3DWebUp

# 4. Avvia Unit3DWebUp (richiede Redis su 127.0.0.1:6379 e ffmpeg)
ENVPATH=$HOME/.config/unit3dprep uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000 &

# 5. Avvia unit3dprep
unit3dprep-web
```

Apri <http://127.0.0.1:8765>, fai login, completa Settings → tracker/qBit/image host. Le credenziali vengono salvate in `$ENVPATH/.env` con la nomenclatura canonica `TRACKER__* / TORRENT__* / PREFS__*` e sincronizzate live a Unit3DWebUp. Per il deploy systemd dei due servizi vedi [`deploy/systemd/`](deploy/systemd/).

### Docker (all-in-one)

Redis + Unit3DWebUp + unit3dprep in un singolo container:

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
cp config.env.example config.env   # compila U3DP_PASSWORD_HASH / U3DP_SECRET / TMDB_API_KEY
docker compose build
docker compose up -d
# apri http://127.0.0.1:8765
```

Guida completa: [Deploy › Docker](https://davidesidoti.github.io/unit3dprep/docker/).

---

## Guide

- [Installazione](https://davidesidoti.github.io/unit3dprep/installazione/)
- [Configurazione](https://davidesidoti.github.io/unit3dprep/configurazione/)
- [Integrazione Unit3DWebUp](https://davidesidoti.github.io/unit3dprep/integrazione-webup/)
- [Uso › CLI](https://davidesidoti.github.io/unit3dprep/uso-cli/)
- [Uso › Web UI](https://davidesidoti.github.io/unit3dprep/uso-web/)
- [Deploy › Docker](https://davidesidoti.github.io/unit3dprep/docker/)
- [Deploy › VPS (sudo/Docker)](https://davidesidoti.github.io/unit3dprep/deploy-vps/)
- [Deploy › Ultra.cc](https://davidesidoti.github.io/unit3dprep/deploy-ultracc/)
- [Nomenclatura](https://davidesidoti.github.io/unit3dprep/nomenclatura/)
- [Troubleshooting](https://davidesidoti.github.io/unit3dprep/troubleshooting/)

English mirror: aggiungi `/en/` al path (es. `/en/installation/`).

---

## Documentazione locale

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Poi apri <http://127.0.0.1:8000>.

---

## Link

- Repo: <https://github.com/davidesidoti/unit3dprep>
- Tracker target principale: <https://itatorrents.xyz>
- Backend upload: <https://pypi.org/project/Unit3DwebUp/> · <https://github.com/31December99/Unit3DWebUp>
- TMDB API: <https://www.themoviedb.org/settings/api>
