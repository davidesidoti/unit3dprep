# unit3dprep

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/fastapi-109989?style=for-the-badge&logo=FASTAPI&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-222222?style=for-the-badge&logo=github%20Pages&logoColor=white)

Web UI + CLI di pre-flight per tracker Unit3D — pairing diretto con [`unit3dup`](https://pypi.org/project/unit3dup/).
Verifica tracce audio italiane, rinomina secondo la nomenclatura ItaTorrents (e altri tracker Unit3D), crea hardlink in `~/seedings/` e lancia `unit3dup` per l'upload.

Include un sistema di **auto-update in-app**: polling GitHub Releases + PyPI, badge "update available" nella Sidebar, click → `pip install` live-streamed + restart del servizio + popup changelog dopo il reload.

![Media Library](docs/assets/screenshots/media_library.png)

**Documentazione completa → <https://davidesidoti.github.io/unit3dprep/>**

---

## Quick start

```bash
pip install -e .
python generate_hash.py      # genera U3DP_PASSWORD_HASH + U3DP_SECRET
unit3dprep-web               # avvia la Web UI
```

Variabili d'ambiente minime: `U3DP_PASSWORD_HASH`, `U3DP_SECRET`, `TMDB_API_KEY`, `U3DP_PORT`.
Dettagli completi nella [guida Installazione](https://davidesidoti.github.io/unit3dprep/installazione/).

> Le legacy env vars `ITA_*` sono ancora lette come fallback (deprecated, warning nei log). Rinomina alla prima occasione.

---

## Guide

- [Installazione](https://davidesidoti.github.io/unit3dprep/installazione/)
- [Configurazione](https://davidesidoti.github.io/unit3dprep/configurazione/)
- [Uso › CLI](https://davidesidoti.github.io/unit3dprep/uso-cli/)
- [Uso › Web UI](https://davidesidoti.github.io/unit3dprep/uso-web/)
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
- Nomenclatura (legacy markdown): [`itatorrents-nomenclatura.md`](itatorrents-nomenclatura.md)
