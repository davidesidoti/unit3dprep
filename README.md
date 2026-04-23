# itatorrents-seeding

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/fastapi-109989?style=for-the-badge&logo=FASTAPI&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-222222?style=for-the-badge&logo=github%20Pages&logoColor=white)

Web UI + CLI per preparare e automatizzare upload su [ItaTorrents.xyz](https://itatorrents.xyz).
Verifica tracce audio italiane, rinomina secondo la nomenclatura ItaTorrents, crea hardlink in `~/seedings/` e lancia `unit3dup` per l'upload.

Include un sistema di **auto-update in-app**: polling GitHub Releases + PyPI, badge "update available" nella Sidebar, click → `pip install` live-streamed + restart del servizio + popup changelog dopo il reload.

![Media Library](docs/assets/screenshots/media_library.png)

**Documentazione completa → <https://davidesidoti.github.io/itatorrents-seeding/>**

---

## Quick start

```bash
pip install -e .
python generate_hash.py      # genera ITA_PASSWORD_HASH + ITA_SECRET
itatorrents-web              # avvia la Web UI
```

Variabili d'ambiente minime: `ITA_PASSWORD_HASH`, `ITA_SECRET`, `TMDB_API_KEY`, `ITA_PORT`.
Dettagli completi nella [guida Installazione](https://davidesidoti.github.io/itatorrents-seeding/installazione/).

---

## Guide

- [Installazione](https://davidesidoti.github.io/itatorrents-seeding/installazione/)
- [Configurazione](https://davidesidoti.github.io/itatorrents-seeding/configurazione/)
- [Uso › CLI](https://davidesidoti.github.io/itatorrents-seeding/uso-cli/)
- [Uso › Web UI](https://davidesidoti.github.io/itatorrents-seeding/uso-web/)
- [Deploy › VPS (sudo/Docker)](https://davidesidoti.github.io/itatorrents-seeding/deploy-vps/)
- [Deploy › Ultra.cc](https://davidesidoti.github.io/itatorrents-seeding/deploy-ultracc/)
- [Nomenclatura](https://davidesidoti.github.io/itatorrents-seeding/nomenclatura/)
- [Troubleshooting](https://davidesidoti.github.io/itatorrents-seeding/troubleshooting/)

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

- Repo: <https://github.com/davidesidoti/itatorrents-seeding>
- Tracker: <https://itatorrents.xyz>
- Nomenclatura (legacy markdown): [`itatorrents-nomenclatura.md`](itatorrents-nomenclatura.md)
