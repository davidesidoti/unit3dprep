# itatorrents-seeding

Web UI + CLI per preparare e automatizzare upload su [ItaTorrents.xyz](https://itatorrents.xyz).

Verifica tracce audio italiane, rinomina secondo nomenclatura ItaTorrents, crea hardlink in `~/seedings` e avvia upload con `unit3dup`.

---

## Funzionalità

### Web UI (React SPA + FastAPI)
- **Media Library** — scansione `~/media/{movies,series,anime}`, ricerca e matching TMDB (automatico o manuale), ordinamento per nome/anno/dimensione, visualizzazione lingue audio
- **Upload Wizard** — flusso guidato per film, episodi singoli e intere stagioni
- **Upload Queue** — monitoraggio torrent dal client (qBittorrent/Transmission/rTorrent) con filtro per nome e stato
- **Upload History** — storico completo con stato exit code `unit3dup`, filtri e ricerca
- **Search Tracker** — ricerca torrent su ITT (e PTT/SIS se configurati)
- **Settings** — configurazione completa `Unit3Dbot.json` da browser, con mascheratura secret
- **Logs** — stream log in tempo reale via SSE
- **Tracker status** — indicatore online/offline per tracker configurati (solo se URL + API key validi)

### CLI
- Verifica tracce audio (`pymediainfo`)
- Rinomina secondo nomenclatura ItaTorrents
- Crea hardlink verso `~/seedings/`
- Lancia `unit3dup -u` (film/episodio) o `unit3dup -f` (serie/stagione)

---

## Requisiti

- Python 3.10+
- `unit3dup` nel PATH
- Media organizzati sotto `~/media/{movies,series,anime}`
- Sorgente media e `~/seedings` sullo stesso filesystem (per hardlink)
- `TMDB_API_KEY` per matching automatico e ricerca TMDB

---

## Installazione

```bash
pip install -e .
```

Genera hash password e secret per la web UI:

```bash
python generate_hash.py
```

---

## Avvio Web

```bash
itatorrents-web
```

Default: `127.0.0.1:8765`. Configurabile via variabili ambiente (vedi sotto).

---

## Variabili ambiente

| Variabile | Richiesta | Default | Descrizione |
|---|---|---|---|
| `ITA_PASSWORD_HASH` | ✓ | — | Hash bcrypt password web UI |
| `ITA_SECRET` | ✓ | — | Secret sessione (itsdangerous) |
| `ITA_PORT` | ✓ | — | Porta ascolto |
| `TMDB_API_KEY` | — | — | API key TMDB v3 |
| `ITA_HOST` | — | `127.0.0.1` | Bind address |
| `ITA_ROOT_PATH` | — | — | Prefisso nginx (es. `/itatorrents`) |
| `ITA_HTTPS_ONLY` | — | `0` | Cookie session secure (`1` dietro HTTPS) |
| `ITA_TMDB_LANG` | — | `it-IT` | Lingua risposta TMDB |
| `ITA_DB_PATH` | — | `~/.itatorrents_db.json` | Path storico upload |
| `ITA_TMDB_CACHE_PATH` | — | `~/.itatorrents_tmdb_cache.json` | Cache TMDB |
| `ITA_LANG_CACHE_PATH` | — | `~/.itatorrents_lang_cache.json` | Cache scan lingue audio |
| `UNIT3DUP_CONFIG` | — | `~/Unit3Dup_config/Unit3Dbot.json` | Path config unit3dup |

---

## CLI

Film o episodio singolo:

```bash
itatorrents -u /path/al/file.mkv
```

Serie o cartella stagione:

```bash
itatorrents -f /path/alla/cartella
```

---

## Build frontend (solo sviluppo locale)

Il frontend React è pre-buildato in `itatorrents/web/dist/` (committato nel repo — Ultra.cc non ha Node).

Per aggiornarlo:

```bash
cd frontend
npm install
npm run build
```

---

## Stack tecnico

- **Backend**: FastAPI + uvicorn, SSE (sse-starlette), auth bcrypt + itsdangerous
- **Frontend**: React 18 + Vite + TypeScript + lucide-react (SPA servita staticamente)
- **DB**: JSON file plain (no SQLite — `_sqlite3` rotto su pyenv Python 3.13/Ultra.cc)
- **Config**: `Unit3Dbot.json` condiviso con `unit3dup` CLI

---

## Nomenclatura

Regole naming ItaTorrents: [`itatorrents-nomenclatura.md`](itatorrents-nomenclatura.md)
