# Uso › Web UI

La Web UI è una SPA React servita da FastAPI. Copre l'intero workflow ItaTorrents dal browser: scansione libreria, upload guidato, coda torrent, storico, configurazione, log in tempo reale.

Avvio:

```bash
itatorrents-web
```

Apri l'URL risultante (`http://<ITA_HOST>:<ITA_PORT><ITA_ROOT_PATH>`, default `http://127.0.0.1:8765`).

---

## Login

Schermata iniziale: campo password. Credenziali validate contro `ITA_PASSWORD_HASH` (bcrypt). La sessione è firmata con `ITA_SECRET` (itsdangerous) e dura finché il browser mantiene il cookie.

!!! note "Middleware order"
    Dietro le quinte: `SessionMiddleware` deve essere aggiunto **dopo** il middleware auth (LIFO = l'ultimo è l'outermost). Se vedi `AssertionError: SessionMiddleware must be installed`, è un bug — apri un issue.

---

## Media Library

![Media Library con poster TMDB, badge lingue audio e panel dettaglio](assets/screenshots/media_library.png)

Lista le categorie (sottocartelle di `ITA_MEDIA_ROOT`) e gli item al loro interno.

Funzionalità:

- **Dropdown categoria** — le categorie sono auto-scoperte (`GET /api/library/categories`). Non hardcoded.
- **Lista item** — ogni riga mostra titolo, anno (se da TMDB), dimensione totale, lingue audio rilevate.
- **Ordinamento** — nome, anno, dimensione.
- **Ricerca** — filtro live sul nome.
- **Nascondi uploadati** — toggle controllato da `W_HIDE_UPLOADED`.
- **Detail panel** — click su un item apre un panel laterale (mobile: overlay a tutto schermo) con file list, match TMDB, azioni.
- **Rescan lingue audio** — bottone che stream-a via SSE la scansione `pymediainfo` aggiornando la cache.
- **Match TMDB manuale** — campo per inserire un ID, bottone cerca con preview risultati.

Endpoint coinvolti: `GET /api/library/categories`, `GET /api/library/{category}`, `GET /api/library/{category}/{item}`, `POST /api/library/{category}/{item}/langs`, `POST /api/tmdb/search`, `POST /api/tmdb/fetch`.

---

## Upload Wizard

![Upload Wizard — step TMDB con preview titolo e metadati](assets/screenshots/upload_wizard.png)

Flusso guidato in step. Alternativa alla CLI con più opzioni e storico persistente.

Step tipici:

1. **Seleziona sorgente** — file o cartella sotto `ITA_MEDIA_ROOT`.
2. **Check audio** — se `W_AUDIO_CHECK`, scansiona le tracce.
3. **TMDB** — ricerca o inserimento ID. Se `W_AUTO_TMDB`, auto-fetch da ID esistente.
4. **Preview nome** — editabile; se `W_CONFIRM_NAMES` è OFF, salta la conferma.
5. **Hardlink** — in `ITA_SEEDINGS_DIR`. Se `W_HARDLINK_ONLY`, termina qui e registra exit code `0`.
6. **Upload** — lancia `unit3dup` in PTY e stream-a l'output live via SSE (`GET /wizard/{token}/stream`).
7. **Registrazione storico** — `update_exit_code(seeding_path, code)` scrive in `ITA_DB_PATH`.

### Quick upload

`POST /upload/quick` salta gran parte del wizard per utenti esperti: ricevi direttamente un job ID e consumi `GET /upload/{job}/stream`. Usalo se hai già file rinominati in `~/seedings/`.

---

## Upload Queue

![Upload Queue — coda qBittorrent con progress bar e stato seeding](assets/screenshots/queue.png)

Mostra i torrent attivi nel client configurato (`TORRENT_CLIENT` in `Unit3Dbot.json`: `qbittorrent`, `transmission`, `rtorrent`).

- Filtro per nome e per stato (downloading, seeding, paused, error).
- Refresh automatico.
- Link ai file locali.

Endpoint: `GET /api/queue`. Credenziali client lette da `QBIT_*` / `TRASM_*` / `RTORR_*`.

---

## Uploaded (storico)

Tabella degli upload completati (`GET /api/uploaded`). Campi:

- Path locale in `~/seedings/`.
- Exit code `unit3dup` (0 = ok, ≠0 = errore, `pending` = mai finito).
- Tracker di destinazione.
- Timestamp.
- Dimensione.
- Ricerca e filtro.

Su mobile la tabella ha `overflow-x:auto` con `min-width:820px` per garantire leggibilità su schermi stretti.

!!! bug "Record `pending` che non si chiudono"
    Se un record rimane `pending` dopo un upload riuscito, significa che l'endpoint non ha chiamato `update_exit_code`. È un bug noto in caso di modifiche a `quickupload.py` o `wizard.py` — vedi [Troubleshooting](troubleshooting.md#record-pending-bloccati).

---

## Search Tracker

![Search Tracker — risultati ITT con tag tipo/risoluzione e conteggio seeders](assets/screenshots/search.png)

Ricerca un torrent su ITT (sempre) e su PTT/SIS (se configurati in `Unit3Dbot.json` con URL + API key valide).

- Tab per tracker.
- Mostra link, dimensione, seeders, freeleech, data upload.
- Utile per duplicate-check prima di caricare.

Endpoint: `GET /api/trackers` (status) + `GET /api/search?q=...`.

!!! note "Stato tracker"
    Un tracker appare "Online" solo se URL e API key sono entrambi settati *e* la API key non è il placeholder `"no_key"`. I tracker nella sidebar sono tutti elencati, anche quelli non configurati (badge grigio "Not set").

---

## Settings

![Settings — pannello Preferenze con toggle comportamento upload e screenshot](assets/screenshots/settings.png)

Editor completo di `Unit3Dbot.json` direttamente dal browser.

Sezioni:

- **Tracker** — URL, API key, PID per ITT / PTT / SIS; lista `MULTI_TRACKER`.
- **Metadata** — TMDB, TVDB, IGDB, YouTube.
- **Torrent client** — tipo + credenziali (qBit / Transmission / rTorrent).
- **Image host** — ordine preferenza + API key per PTSCREENS, PASSIMA, IMGBB, ecc.
- **Opzioni upload** — `DUPLICATE_ON`, `ANON`, `NUMBER_OF_SCREENSHOTS`, `COMPRESS_SCSHOT`, ...
- **Seeding Flow** — `ITA_*` con valori effettivi (env vs config) via `env_runtime()`. Read-only per `UNIT3DUP_CONFIG`.
- **App Auto-Update** — `ITA_SYSTEMD_UNIT`, nome della systemd user unit usata dal bottone "Update app" per il restart post-aggiornamento. Default `itatorrents.service`; su Ultra.cc tipicamente `itatorrents-web.service`.
- **Wizard Defaults** — tutte le `W_*`.

Secret mascherati come `__SET__` — il campo appare riempito. Modificare altre chiavi non cancella i secret.

Endpoint: `GET /api/settings`, `PUT /api/settings`, `GET /api/settings/fs-check`.

Mobile: la nav a sinistra diventa una riga orizzontale scrollabile; le griglie 2-col collassano in 1-col.

---

## Auto-update in-app

In basso a sinistra nella Sidebar, sopra la lista tracker, compare un banner quando è disponibile una release più recente della tua versione installata (app o `unit3dup`).

- **App** → GitHub Releases (`api.github.com/repos/.../releases/latest`). Il flow sceglie automaticamente `git pull + pip install -e .` se il sorgente è un checkout git, altrimenti `pip install --upgrade --force-reinstall git+URL@vX`.
- **unit3dup** → PyPI (`pypi.org/pypi/unit3dup/json`). `pip install --upgrade unit3dup`.

Al click:

1. Modal con log `pip`/`git` live-streamed via SSE (`/api/version/update/{app|unit3dup}/stream`).
2. Al termine countdown "Refresh automatico in 5…1" + reload automatico del browser.
3. Post-reload popup con il changelog della nuova versione (release body da GitHub).

Il bottone "Update app" rimane disabilitato (`can_update_app: false`) se la user unit systemd non è accessibile. Vedi [Configurazione › Auto-update in-app](configurazione.md#auto-update-in-app) per dettagli (inclusa la chiave `ITA_SYSTEMD_UNIT`).

Endpoint: `GET /api/version/info`, `GET /api/version/changelog?v=X`, `GET /api/version/update/{app|unit3dup}/stream` (SSE), `POST /api/version/refresh`.

---

## Logs

Stream log in tempo reale via SSE. Tutto ciò che `uvicorn` / l'app scrive su `logbuf` (`itatorrents/web/logbuf.py`) arriva qui.

Utile per debugging senza aprire una shell sul VPS.

---

## Note mobile (≤768px)

La UI è responsive:

- **Sidebar** — si chiude in `translateX(-100%)`, scrim overlay quando aperta.
- **Modal** — full-bleed con padding 14px.
- **Library detail** — overlay `position:fixed; inset:0` invece del panel laterale da 360px.
- **Settings nav** — riga orizzontale scrollabile.
- **Tabelle** — `overflow-x:auto`.

Breakpoint gestito da `isMobile` (App.tsx → Sidebar / TopBar / Library / Settings via props).

---

## Bisogni accesso programmatico?

Tutte le view della UI consumano l'API JSON sotto `{ITA_ROOT_PATH}/api/*`. Puoi chiamarla direttamente con cookie di sessione valido. Vedi `itatorrents/web/api/*.py` per la lista completa dei router.
