# Configurazione

`itatorrents-seeding` si configura su tre livelli, con precedenza:

1. **Variabili d'ambiente** — hanno sempre la priorità.
2. **`Unit3Dbot.json`** — file condiviso con la CLI `unit3dup`, editabile anche dalla Web UI.
3. **Default interni** — usati quando né env né file specificano un valore.

Le chiavi `ITA_*` e `W_*` vengono rilette ad ogni accesso tramite `config.runtime_setting()`: modificarle da Web UI ha effetto immediato, senza riavvio. Le eccezioni sono `ITA_HOST`, `ITA_PORT`, `ITA_ROOT_PATH` e `ITA_HTTPS_ONLY`, lette solo all'avvio del server.

---

## Variabili d'ambiente

### Obbligatorie per la Web UI

| Variabile | Descrizione |
|---|---|
| `ITA_PASSWORD_HASH` | Hash bcrypt della password web. Generato da `generate_hash.py`. |
| `ITA_SECRET` | Secret hex per firmare i cookie di sessione. Generato da `generate_hash.py`. |

### TMDB

| Variabile | Default | Descrizione |
|---|---|---|
| `TMDB_API_KEY` | — | API key TMDB v3. Richiesta per ricerca TMDB automatica e per fetch dei metadati ufficiali. La CLI prompt-a l'utente se manca. |

### Runtime (re-evaluate ad ogni accesso)

| Variabile | Default | Descrizione |
|---|---|---|
| `ITA_HOST` | `127.0.0.1` | Bind address di uvicorn. Usa `0.0.0.0` su VPS con firewall pubblico, `127.0.0.1` dietro nginx reverse proxy. |
| `ITA_PORT` | `8765` | Porta di ascolto. Su Ultra.cc usa una porta riservata (`app-ports free`). |
| `ITA_ROOT_PATH` | `""` | Prefisso nginx (es. `/itatorrents`). Vedi [note ROOT_PATH](#ita_root_path-e-nginx). |
| `ITA_HTTPS_ONLY` | `0` | Se `1` imposta `https_only` sul cookie di sessione (richiesto dietro HTTPS). |
| `ITA_MEDIA_ROOT` | `~/media` | Cartella base dei media. Le sottocartelle diventano categorie. |
| `ITA_SEEDINGS_DIR` | `~/seedings` | Destinazione degli hardlink. Deve stare sullo stesso FS di `ITA_MEDIA_ROOT`. |
| `ITA_TMDB_LANG` | `it-IT` | Lingua delle risposte TMDB. Esempi: `en-US`, `es-ES`. |
| `ITA_DB_PATH` | `~/.itatorrents_db.json` | Storico upload (JSON). |
| `ITA_TMDB_CACHE_PATH` | `~/.itatorrents_tmdb_cache.json` | Cache query TMDB. |
| `ITA_LANG_CACHE_PATH` | `~/.itatorrents_lang_cache.json` | Cache rilevamento lingua audio. |
| `ITA_SYSTEMD_UNIT` | `itatorrents.service` | Nome della systemd user unit usato dal bottone "Update app" per `systemctl --user cat/restart`. Su Ultra.cc impostare a `itatorrents-web.service`. |
| `ITA_GITHUB_REPO` | `davidesidoti/itatorrents-seeding` | Slug `owner/repo` usato per il polling delle release (solo env, letto all'import). |

### Installazione / path

| Variabile | Default | Descrizione |
|---|---|---|
| `UNIT3DUP_CONFIG` | `~/Unit3Dup_config/Unit3Dbot.json` | Override del path al file `Unit3Dbot.json`. Letto solo all'avvio. |

### Wizard Web UI (W_*)

Controllano i default degli switch del wizard di upload. Vivono in `Unit3Dbot.json` e si editano da Settings.

| Chiave | Default | Descrizione |
|---|---|---|
| `W_AUDIO_CHECK` | `true` | Abilita check audio italiano nel wizard. |
| `W_AUTO_TMDB` | `true` | Auto-fetch dei metadati TMDB se è già presente un ID. |
| `W_HIDE_UPLOADED` | `true` | Nasconde dalla Library gli item già caricati. |
| `W_HARDLINK_ONLY` | `false` | Termina il wizard dopo l'hardlink, senza chiamare `unit3dup`. |
| `W_CONFIRM_NAMES` | `true` | Richiede conferma del nome finale prima dell'hardlink. |

---

## File `Unit3Dbot.json`

Il file `Unit3Dbot.json` è lo stesso che usa la CLI `unit3dup`. Path di default: `~/Unit3Dup_config/Unit3Dbot.json`, override via `UNIT3DUP_CONFIG`.

Contiene ~100 chiavi, raggruppate per scopo:

| Gruppo | Chiavi principali |
|---|---|
| Tracker | `ITT_URL`, `ITT_APIKEY`, `ITT_PID`, `PTT_URL`, `PTT_APIKEY`, `PTT_PID`, `SIS_URL`, `SIS_APIKEY`, `SIS_PID`, `MULTI_TRACKER` |
| Metadata | `TMDB_APIKEY`, `TVDB_APIKEY`, `YOUTUBE_KEY`, `IGDB_*` |
| Client torrent | `TORRENT_CLIENT` (`qbittorrent` / `transmission` / `rtorrent`), `QBIT_*`, `TRASM_*`, `RTORR_*` |
| Image host | `PTSCREENS_KEY`, `PASSIMA_KEY`, `IMGBB_KEY`, `IMGFI_KEY`, `IMAGE_HOST_ORDER`, ... |
| Comportamento | `DUPLICATE_ON`, `SKIP_DUPLICATE`, `ANON`, `PERSONAL_RELEASE`, `NUMBER_OF_SCREENSHOTS`, ... |
| Seeding Flow | tutte le `ITA_*` (override del default) |
| Wizard defaults | tutte le `W_*` |

### Mascheratura dei secret

I secret (API key, password, PID) vengono **mascherati** come `"__SET__"` in risposta alle GET `/api/settings`. In PUT, se il client rimanda `"__SET__"` il server conserva il valore originale su disco. Questo evita leak nei log del browser e permette di modificare altre chiavi senza doverli reimmettere.

Le chiavi mascherate sono definite in `itatorrents/web/config.py` (costante `MASKED_KEYS`):
`ITT_APIKEY`, `ITT_PID`, `PTT_APIKEY`, `PTT_PID`, `SIS_APIKEY`, `SIS_PID`, `TMDB_APIKEY`, `TVDB_APIKEY`, `YOUTUBE_KEY`, `IGDB_CLIENT_ID`, `IGDB_ID_SECRET`, `QBIT_PASS`, `TRASM_PASS`, `RTORR_PASS`, `FTPX_PASS`, `PTSCREENS_KEY`, `PASSIMA_KEY`, `IMGBB_KEY`, `IMGFI_KEY`, `FREE_IMAGE_KEY`, `LENSDUMP_KEY`, `IMARIDE_KEY`.

### Scrittura atomica

Le write su `Unit3Dbot.json` passano per `tempfile.mkstemp` + `os.replace` → la CLI `unit3dup` non vede mai un file a metà.

---

## `ITA_ROOT_PATH` e nginx

Se servi la Web UI dietro un reverse proxy a un sottopath (es. `/itatorrents`), imposta:

```bash
export ITA_ROOT_PATH="/itatorrents"
```

**Importante** — su Ultra.cc l'nginx **non strippa** il prefisso: le richieste arrivano a uvicorn *con* `/itatorrents` ancora presente. Per questo l'app monta le route sotto il prefisso con `app.include_router(r, prefix=ROOT_PATH)` invece di `FastAPI(root_path=...)` (che si usa quando il proxy *strippa*).

La SPA legge `window.__ROOT_PATH__` iniettato runtime in `index.html`, quindi asset e chiamate API vanno automaticamente al prefisso giusto senza rebuild.

Su un VPS generico con nginx che strippa il prefisso (`proxy_pass http://127.0.0.1:8765/;` con slash finale), imposta invece `ITA_ROOT_PATH=""` e gestisci il path dal server block.

---

## Auto-update in-app

La Web UI espone un sistema di update integrato (badge in basso a sinistra nella Sidebar, sopra i tracker):

- **App**: confronta la versione installata (`importlib.metadata.version("itatorrents")`) con la [release più recente su GitHub](https://github.com/davidesidoti/itatorrents-seeding/releases). Se `newer == true` compare il bottone "Update app".
- **unit3dup**: confronta la versione installata con PyPI (`https://pypi.org/pypi/unit3dup/json`).

Al click l'endpoint SSE `/api/version/update/{app|unit3dup}/stream` esegue `pip install` live-streamed nel modal, riavvia il servizio systemd e ricarica il browser mostrando il changelog della nuova versione.

### Pre-requisiti app

Il bottone "Update app" rimane disabilitato (`can_update_app: false`) se:

- `systemctl` non è nel PATH, oppure
- l'unit configurata non esiste (`systemctl --user cat <unit>` fallisce).

Su Ultra.cc la user unit tipica si chiama `itatorrents-web.service`, non il default `itatorrents.service`. Imposta:

```ini
# ~/.config/systemd/user/itatorrents-web.service
[Service]
Environment=ITA_SYSTEMD_UNIT=itatorrents-web.service
```

oppure salva la chiave da **Settings › App Auto-Update**. La chiave è letta runtime, quindi ha effetto immediato dopo il Save. `daemon-reload` + restart sono necessari solo per un `Environment=` appena aggiunto.

### Modalità install

`_install_mode()` sceglie il flow in base alla struttura dell'installazione:

- **git** — se la sorgente Python ha una cartella `.git` accessibile (tipico per `pip install -e .` da checkout). Esegue `git pull --ff-only origin main` + `pip install -e .`.
- **pip** — se installato via `pip install git+https://...@vX` (no `.git` nella source). Esegue `pip install --upgrade --force-reinstall git+URL@vX`.

!!! note "Editable install + service WorkingDirectory"
    Se il `[Service]` del systemd ha `WorkingDirectory=<repo>` e la cartella contiene `.git`, Python importa `itatorrents` dalla source locale (editable) anche se hai installato via `pip install git+...`. Il flow diventa "git" di conseguenza. Per forzare il flow pip, usa `WorkingDirectory=%h` e rimuovi/rinomina il checkout.

### Token GitHub (opzionale)

Il rate limit di `api.github.com` per le release pubbliche è 60 richieste/ora per IP anonimo. Dovrebbe essere sufficiente (polling ogni 15 min), ma in caso di saturazione è previsto il supporto a un token via env — non ancora implementato, tracciato come follow-up.

---

## Esempi completi

### Deploy locale (solo tu, su macchina fidata)

```bash
export ITA_PASSWORD_HASH="$2b$12$..."
export ITA_SECRET="..."
export TMDB_API_KEY="..."
export ITA_HOST="127.0.0.1"
export ITA_PORT="8765"
itatorrents-web
```

### Dietro nginx con HTTPS e sottopath

```bash
export ITA_PASSWORD_HASH="..."
export ITA_SECRET="..."
export TMDB_API_KEY="..."
export ITA_HOST="127.0.0.1"
export ITA_PORT="45678"                 # porta backend, non esposta
export ITA_ROOT_PATH="/itatorrents"     # sottopath pubblico
export ITA_HTTPS_ONLY="1"
itatorrents-web
```

### Media in un disco separato

```bash
export ITA_MEDIA_ROOT="/mnt/storage/media"
export ITA_SEEDINGS_DIR="/mnt/storage/seedings"
```

!!! danger "Stesso filesystem"
    `ITA_SEEDINGS_DIR` **deve** trovarsi sul medesimo device di `ITA_MEDIA_ROOT`, altrimenti l'hardlink fallisce con `OSError: [Errno 18] Invalid cross-device link`. Verifica con `df <media> <seedings>`.
