# Configurazione

`unit3dprep` si configura su tre livelli con la seguente precedenza:

1. **Variabili d'ambiente** — hanno sempre la priorità.
2. **File `.env` condiviso** — file unico letto sia da `unit3dprep` sia da `Unit3DWebUp` 0.0.20+. Editabile dalla Web UI tramite Settings.
3. **Default interni** — usati quando né env né file specificano un valore.

Le chiavi `U3DP_*` e `W_*` vengono **rilette ad ogni accesso** tramite `config.runtime_setting()`: modificarle da Web UI ha effetto immediato senza riavvio. Le eccezioni sono `U3DP_HOST`, `U3DP_PORT`, `U3DP_ROOT_PATH` e `U3DP_HTTPS_ONLY`, lette solo all'avvio del server uvicorn.

---

## Variabili d'ambiente

### Obbligatorie per la Web UI

| Variabile | Descrizione |
|---|---|
| `U3DP_PASSWORD_HASH` | Hash bcrypt della password web. Generato da `generate_hash.py`. **Sempre tra apici singoli** nei file `.env`/bash (vedi [Installazione](installazione.md#3-genera-hash-password-e-secret)). |
| `U3DP_SECRET` | Secret hex per firmare i cookie di sessione. Generato da `generate_hash.py`. |

### TMDB

| Variabile | Default | Descrizione |
|---|---|---|
| `TMDB_API_KEY` | — | API key TMDB v3. Richiesta per la ricerca TMDB di unit3dprep e per il fetch dei metadati. La CLI prompt-a se manca. Lo stesso valore deve esistere come `TMDB_APIKEY` nel `.env` condiviso (Unit3DWebUp lo richiede). |

### Runtime (re-evaluate ad ogni accesso)

| Variabile | Default | Descrizione |
|---|---|---|
| `U3DP_HOST` | `127.0.0.1` | Bind address di uvicorn. Usa `0.0.0.0` su VPS con firewall pubblico, `127.0.0.1` dietro nginx reverse proxy. *(read-once a startup)* |
| `U3DP_PORT` | `8765` | Porta di ascolto. Su Ultra.cc usa una porta riservata (`app-ports free`). *(read-once a startup)* |
| `U3DP_ROOT_PATH` | `""` | Prefisso nginx (es. `/unit3dprep`). *(read-once)* Vedi [note ROOT_PATH](#u3dp_root_path-e-nginx). |
| `U3DP_HTTPS_ONLY` | `0` | Se `1` imposta `https_only` sul cookie di sessione (richiesto dietro HTTPS). *(read-once)* |
| `U3DP_MEDIA_ROOT` | `~/media` | Cartella base dei media. Le sottocartelle diventano categorie. |
| `U3DP_SEEDINGS_DIR` | `~/seedings` | Destinazione hardlink. Deve stare sullo stesso FS di `U3DP_MEDIA_ROOT`. |
| `U3DP_TMDB_LANG` | `it-IT` | Lingua delle risposte TMDB (lookup interno). Esempi: `en-US`, `es-ES`. |
| `U3DP_LANG` | `it` | Lingua della UI (`it`/`en`). Persiste in `localStorage` + `.env`. |
| `U3DP_DB_PATH` | `~/.unit3dprep_db.json` | Storico upload (JSON). |
| `U3DP_TMDB_CACHE_PATH` | `~/.unit3dprep_tmdb_cache.json` | Cache query TMDB. |
| `U3DP_LANG_CACHE_PATH` | `~/.unit3dprep_lang_cache.json` | Cache rilevamento lingua audio. |
| `U3DP_SYSTEMD_UNIT` | `unit3dprep.service` | Nome systemd user unit dell'app, usato dal bottone "Update app" per `systemctl --user cat/restart`. Su Ultra.cc impostare a `unit3dprep-web.service`. |
| `U3DP_DRY_RUN_TRACKER` | `0` | Se `1` (o `true`/`yes`) il wizard salta la chiamata `/upload` a Unit3DWebUp: utile in dev/WSL per esercitare la pipeline (`setenv→scan→maketorrent→seed`) senza polluire il tracker live. |
| `U3DP_GITHUB_REPO` | `davidesidoti/unit3dprep` | Slug `owner/repo` usato per il polling delle release dell'app (env-only, letto all'import). |

### Bridge Unit3DWebUp

| Variabile | Default | Descrizione |
|---|---|---|
| `WEBUP_URL` | `http://127.0.0.1:8000` | Indirizzo base del bot Unit3DWebUp. |
| `WEBUP_REPO_PATH` | `~/dev/Unit3DWebUp` | Path del clone Unit3DWebUp (legacy). Solo per modalità "git" dell'auto-update di webup. |
| `WEBUP_VENV_BIN` | *auto* | Cartella `bin` del venv che contiene `Unit3DwebUp`. Auto-detect: se non settata, prova `<WEBUP_REPO_PATH>/.venv/bin/python`, fallback a `sys.executable` (canonical PyPI install in stesso venv di unit3dprep). Settala esplicitamente quando webup vive in un venv distinto. |
| `WEBUP_SYSTEMD_UNIT` | `unit3dwebup.service` | Nome systemd user unit di Unit3DWebUp, riavviata dopo l'auto-update via SSE. |

### Storage del `.env` condiviso

| Variabile | Default | Descrizione |
|---|---|---|
| `U3DP_ENV_PATH` | — | Path completo (file) del `.env` condiviso. Override esplicito di unit3dprep. |
| `ENVPATH` | — | **Directory** che contiene il `.env` (file = `<dir>/.env`). Stessa convenzione usata da `Unit3DWebUp`: passa lo stesso valore al `uvicorn` del bot. |
| `UNIT3DUP_CONFIG` | `~/Unit3Dup_config/Unit3Dbot.json` | Path del **vecchio** `Unit3Dbot.json` da cui leggere durante la migration one-shot al primo avvio. Dopo la migration non viene più usato. |

Precedenza per il file `.env` su disco: `U3DP_ENV_PATH` → `ENVPATH/.env` → `~/.config/unit3dprep/.env` (default XDG).

### Wizard Web UI (W_*)

Controllano i default degli switch del wizard di upload. Vivono nel `.env` condiviso e si editano da Settings.

| Chiave | Default | Descrizione |
|---|---|---|
| `W_AUDIO_CHECK` | `true` | Abilita il check audio italiano nel wizard. |
| `W_AUTO_TMDB` | `true` | Auto-fetch dei metadati TMDB se è già presente un ID. |
| `W_HIDE_UPLOADED` | `true` | Nasconde dalla Library gli item già caricati. |
| `W_HIDE_NO_ITALIAN` | `false` | Nasconde dalla Library gli item scansionati senza traccia ITA. |
| `W_HARDLINK_ONLY` | `false` | Termina il wizard dopo l'hardlink, senza lanciare l'upload Unit3DWebUp. |
| `W_CONFIRM_NAMES` | `true` | Richiede conferma del nome finale prima dell'hardlink. |

---

## File `.env` condiviso

Storage unico per app + bot, conforme a `Unit3DWebUp` 0.0.20+. Path di default: `~/.config/unit3dprep/.env` (override via `U3DP_ENV_PATH` o `ENVPATH`).

Sul disco, le chiavi che esistono in webup vengono salvate con la **nomenclatura canonica** che il bot si aspetta (prefissi `TRACKER__`, `TORRENT__`, `PREFS__`); in memoria e nella API `/api/settings` restano i nomi corti storici (`ITT_APIKEY`, `QBIT_HOST`, …). La traduzione è confinata a `unit3dprep/web/config.py` (`WEBUP_KEY_MAP`).

Per lanciare il bot accanto basta puntargli lo stesso `ENVPATH`:

```bash
ENVPATH=~/.config/unit3dprep uvicorn unit3dwup.start:app
```

### Mappatura short ↔ canonical (estratto)

| Nome corto (API/UI) | Nome canonico (su disco / `.env`) |
|---|---|
| `ITT_APIKEY` | `TRACKER__APIKEYS=["..."]` |
| `ITT_URL` | `TRACKER__URLS=["..."]` |
| `ITT_PID` | `TRACKER__PIDS=["..."]` |
| `MULTI_TRACKER` | `TRACKER__MULTI_TRACKER=["itt", ...]` (JSON array) |
| `TMDB_APIKEY` | `TRACKER__TMDB_APIKEY` |
| `TVDB_APIKEY` | `TRACKER__TVDB_APIKEY` |
| `QBIT_HOST` / `QBIT_PORT` / `QBIT_USER` / `QBIT_PASS` | `TORRENT__QBIT_HOST` / `…_PORT` / `…_USER` / `…_PASS` |
| `IMGFI_KEY` | `TRACKER__IMGFI_KEY` |
| `IMAGE_HOST_ORDER` | proiettato in `PREFS__<HOST>_PRIORITY` (1, 2, …, 99 per host non in lista) |
| `TAG_ORDER_MOVIE` / `TAG_ORDER_SERIE` | `PREFS__TAG_POSITION_MOVIE` / `…_SERIE` |
| `NUMBER_OF_SCREENSHOTS`, `ANON`, `PERSONAL_RELEASE`, … | `PREFS__<KEY>` |

La lista completa è in `unit3dprep/web/config.py` (`WEBUP_KEY_MAP`).

### Skip rules

`_to_webup_env_payload` salta dal push a Unit3DWebUp i valori vuoti (`""`, `None`) e i placeholder `no_key` / `no_pass` / `no_path` / `no_comment`: il bot mantiene così i propri default e il suo validator pydantic (`empty_to_none`) non incappa in conversioni `None`-> errore `str` che farebbero `SystemExit(1)` al primo `setenv`.

Tre chiavi sono un'eccezione: `PREFS__TORRENT_ARCHIVE_PATH`, `PREFS__WATCHER_PATH`, `PREFS__WATCHER_DESTINATION_PATH`, `PREFS__SCAN_PATH` vengono materializzate con fallback `.` se nella nostra config sono vuote, perché webup richiede un path "Path-able" che esista (altrimenti `get_settings()` chiama `SystemExit`).

### Migration automatica dal vecchio `Unit3Dbot.json`

Al primo avvio, se esiste `~/Unit3Dup_config/Unit3Dbot.json` (o quanto puntato da `$UNIT3DUP_CONFIG`):

1. il file viene letto;
2. riscritto come `.env` con la nomenclatura canonica;
3. rinominato in `Unit3Dbot.json.migrated-bak`.

La migration è idempotente. Il backup non viene mai cancellato dall'app — l'utente può rimuoverlo manualmente dopo aver verificato.

### Mascheratura dei secret

I secret (API key, password, PID) vengono **mascherati** come `"__SET__"` in risposta alle `GET /api/settings`. In `PUT`, se il client rimanda `"__SET__"` il server conserva il valore originale. Questo evita leak nei log del browser e permette di modificare altre chiavi senza dover reimmettere ogni volta tutti i secret.

Le chiavi mascherate sono definite in `unit3dprep/web/config.py` (`MASKED_KEYS`):
`ITT_APIKEY`, `ITT_PID`, `PTT_APIKEY`, `PTT_PID`, `SIS_APIKEY`, `SIS_PID`, `TMDB_APIKEY`, `TVDB_APIKEY`, `YOUTUBE_KEY`, `IGDB_CLIENT_ID`, `IGDB_ID_SECRET`, `QBIT_PASS`, `TRASM_PASS`, `RTORR_PASS`, `FTPX_PASS`, `PTSCREENS_KEY`, `PASSIMA_KEY`, `IMGBB_KEY`, `IMGFI_KEY`, `FREE_IMAGE_KEY`, `LENSDUMP_KEY`, `IMARIDE_KEY`.

### Scrittura atomica + live sync

Le write sul `.env` passano per `tempfile.mkstemp` + `os.replace` → né `unit3dprep` né `Unit3DWebUp` vedono mai un file a metà.

Ogni `PUT /api/settings` triggera in cascata `webup_client.setenv(key, value)` (POST `/setenv` al bot) per ogni chiave canonica modificata: il bot ricostruisce internamente `Settings()` senza riavvio. Un Save in UI non richiede `systemctl restart unit3dwebup.service`.

Eccezioni che richiedono restart del bot: `REDIS_*` (hardcoded comunque a localhost:6379), modifiche a env-vars del processo non in `.env` (es. `DOCKER`, `PYTHONUNBUFFERED`), e ovviamente l'aggiornamento del pacchetto webup (gestito automaticamente dall'auto-update SSE).

---

## `U3DP_ROOT_PATH` e nginx

Se servi la Web UI dietro un reverse proxy a un sottopath (es. `/unit3dprep`), imposta:

```bash
export U3DP_ROOT_PATH="/unit3dprep"
```

**Importante** — su Ultra.cc l'nginx **non strippa** il prefisso: le richieste arrivano a uvicorn *con* `/unit3dprep` ancora presente. Per questo l'app monta le route sotto il prefisso con `app.include_router(r, prefix=ROOT_PATH)` invece di `FastAPI(root_path=...)` (che si usa quando il proxy *strippa*).

La SPA legge `window.__ROOT_PATH__` iniettato a runtime in `index.html`, quindi asset e chiamate API vanno automaticamente al prefisso giusto senza rebuild.

Su un VPS generico con nginx che strippa il prefisso (`proxy_pass http://127.0.0.1:8765/;` con slash finale), imposta invece `U3DP_ROOT_PATH=""` e gestisci il path dal server block.

---

## Auto-update in-app

La Web UI espone un sistema di update integrato per **due artefatti distinti**:

- **App** (`unit3dprep`) — confronto della versione installata (`importlib.metadata.version("unit3dprep")` o `pyproject.toml` in modalità git) con [GitHub Releases](https://github.com/davidesidoti/unit3dprep/releases).
- **Unit3DWebUp** — confronto della versione installata nel venv del bot (rilevata via subprocess `python -c "import importlib.metadata; print(importlib.metadata.version('Unit3DwebUp'))"`) con [PyPI](https://pypi.org/project/Unit3DwebUp/).

Card visualizzate in **Settings › Versione**. Click su "Installa aggiornamento":

1. Modal con log `pip install --upgrade Unit3DwebUp` o `git pull + pip install -e .` live-streamed via SSE (`/api/version/update/{webup,app}/stream`).
2. Al termine `_cache` di `/api/version/info` viene azzerato e systemd `<unit>` viene riavviato in scope transient (`systemd-run --user --on-active=3s`) per sopravvivere al SIGTERM del processo genitore.
3. Countdown 5s + reload del browser; popup con il body della release post-reload.

### Pre-requisiti app

Il bottone "Update app" rimane disabilitato (`can_update_app: false`) se:

- `systemctl` non è nel PATH, oppure
- l'unit configurata non esiste (`systemctl --user cat <unit>` fallisce).

Su Ultra.cc la user unit tipica si chiama `unit3dprep-web.service`, non il default `unit3dprep.service`. Imposta:

```ini
# ~/.config/systemd/user/unit3dprep-web.service
[Service]
Environment=U3DP_SYSTEMD_UNIT=unit3dprep-web.service
```

oppure salva la chiave da **Settings › App Auto-Update**. La chiave è letta runtime, ha effetto immediato dopo Save. `daemon-reload` + restart sono necessari solo per un `Environment=` appena aggiunto al file unit.

### Pre-requisiti webup

Analogamente, il bottone "Aggiorna" della card webup richiede:

- python con `Unit3DwebUp` installato accessibile. Auto-detect: `WEBUP_VENV_BIN/python` se settata, poi `<WEBUP_REPO_PATH>/.venv/bin/python` (legacy), infine `sys.executable` (canonical PyPI install nello stesso venv di unit3dprep). Settare `WEBUP_VENV_BIN` esplicitamente solo quando webup vive in un venv distinto;
- systemd user unit `unit3dwebup.service` esistente (override con `WEBUP_SYSTEMD_UNIT`).

### Modalità install (app)

`_install_mode()` sceglie il flow in base alla struttura dell'installazione:

- **git** — sorgente Python con `.git` accessibile (tipico di `pip install -e .` da checkout). Esegue `git pull --ff-only origin main` + `pip install -e .`.
- **pip** — installato via `pip install git+https://...@vX` (no `.git` nella source). Esegue `pip install --upgrade --force-reinstall git+URL@vX`.

!!! note "Editable install + service WorkingDirectory"
    Se il `[Service]` del systemd ha `WorkingDirectory=<repo>` e la cartella contiene `.git`, Python importa `unit3dprep` dalla source locale (editable) anche se hai installato via `pip install git+...`. Il flow diventa "git" di conseguenza. Per forzare il flow pip, usa `WorkingDirectory=%h` e rimuovi/rinomina il checkout.

---

## Esempi completi

### Deploy locale (solo tu, su macchina fidata)

```bash
export U3DP_PASSWORD_HASH='$2b$12$...'
export U3DP_SECRET="..."
export TMDB_API_KEY="..."
export U3DP_HOST="127.0.0.1"
export U3DP_PORT="8765"
export ENVPATH="$HOME/.config/unit3dprep"

# bot in background
ENVPATH=$HOME/.config/unit3dprep uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000 &
unit3dprep-web
```

### Dietro nginx con HTTPS e sottopath

```bash
export U3DP_PASSWORD_HASH='$2b$12$...'
export U3DP_SECRET="..."
export TMDB_API_KEY="..."
export U3DP_HOST="127.0.0.1"
export U3DP_PORT="45678"                  # porta backend, non esposta
export U3DP_ROOT_PATH="/unit3dprep"      # sottopath pubblico
export U3DP_HTTPS_ONLY="1"
export ENVPATH="$HOME/.config/unit3dprep"
unit3dprep-web
```

### Media in un disco separato

```bash
export U3DP_MEDIA_ROOT="/mnt/storage/media"
export U3DP_SEEDINGS_DIR="/mnt/storage/seedings"
```

!!! danger "Stesso filesystem"
    `U3DP_SEEDINGS_DIR` **deve** trovarsi sul medesimo device di `U3DP_MEDIA_ROOT`, altrimenti l'hardlink fallisce con `OSError: [Errno 18] Invalid cross-device link`. Verifica con `df <media> <seedings>`.

### Dev WSL — dry-run senza polluire il tracker

```bash
export U3DP_DRY_RUN_TRACKER=1
unit3dprep-web
```

Il wizard farà `setenv → scan → maketorrent → seed` per intero ma salterà `/upload`. Utile per testare modifiche al pre-flight + bridge senza creare upload reali.
